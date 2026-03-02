import os
import threading
import tempfile
import math
import queue
import logging
from typing import Any, Callable, Literal, TypeAlias, cast
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from datetime import timedelta

from .config import (
    AUDIO_INITIAL_DIR,
    FASTER_WHISPER_MODEL,
    GROQ_API_KEY,
    LLM_PROVIDER,
    TARGET_FLASHCARDS,
    TARGET_GLOSSARY,
    TARGET_QUESTIONS,
    TRANSCRIPTION_PROVIDER,
    UI_LANG,
    WHISPER_MODEL,
)
from .fp_core import (
    build_postprocess_plan,
    build_abstract_prompt,
    build_keypoints_prompt,
    build_outline_prompt,
    extract_json_candidate,
    normalize_outline_nodes,
    parse_key_points,
)
from .processing_mixin import ProcessingMixin
from .translations import TRANSLATIONS
from .ui_results_mixin import UIResultsMixin


"""
===========================
 App Tkinter: Trascrivi Lezioni + Riassunti & Flashcard
===========================

NOTE:
 - Imposta la tua chiave via variabile d'ambiente GROQ_API_KEY quando usi provider Groq.
 - Supporta file audio comuni: .wav .mp3 .m4a .aac .flac .ogg .wma
 - Trascrizione a chunk per file lunghi (provider: Groq o faster-whisper).
 - Post-process con LLM (provider: Groq o Ollama) per generare:
     • Abstract
     • Riassunto corposo in Markdown (con titoli e sottotitoli)
     • Outline (mappa ad albero degli argomenti)
     • Key points
     • Domande (con difficoltà e risposte)
     • Flashcard (stile Anki: front/back) + export CSV
     • Glossario (termini e definizioni)
 - Interfaccia a schede con pulsanti di copia/salvataggio per ogni sezione.

Modelli di default:
 - Whisper:   whisper-large-v3-turbo
 - LLM chat:  llama-3.3-70b-versatile
"""

QueueKind: TypeAlias = Literal[
    "append", "progress", "status", "error", "open_results", "partial_result", "enable_llm", "done"
]
QueueMessage: TypeAlias = tuple[QueueKind, Any]
ScrollbarCommand: TypeAlias = Callable[..., Any]
LOGGER = logging.getLogger(__name__)

GROQ_TRANSCRIPTION_MODELS = (
    "whisper-large-v3-turbo",
    "whisper-large-v3",
)

FASTER_WHISPER_TRANSCRIPTION_MODELS = (
    "tiny",
    "base",
    "small",
    "medium",
    "large-v2",
    "large-v3",
    "distil-large-v3",
)


class LectureTranscriberApp(UIResultsMixin, ProcessingMixin, tk.Tk):
    """App Tkinter per caricare un file audio di una lezione, trascriverlo
    con provider selezionabile e generare riassunti, domande e flashcard
    con un LLM selezionabile.
    """

    def __init__(self):
        super().__init__()
        self.ui_lang = UI_LANG if UI_LANG in TRANSLATIONS else "it"
        self.ui_lang_var = tk.StringVar(value=self.ui_lang)
        self.transcription_provider_var = tk.StringVar(
            value=self._normalize_transcription_provider(
                TRANSCRIPTION_PROVIDER)
        )
        self.llm_provider_var = tk.StringVar(
            value=self._normalize_llm_provider(LLM_PROVIDER)
        )
        self.title(self._t("window_title"))
        self.geometry("1200x820")

        # Stato
        self.audio_path = None
        self.worker_thread = None
        self.cancel_event = threading.Event()
        self.msg_queue: queue.Queue[QueueMessage] = queue.Queue()
        self.total_ms = 0
        self.partial_outs: dict[str, Any] = {}
        self.section_tab_ids = [
            ("abstract", "tab_abstract"),
            ("summary_markdown", "tab_summary"),
            ("outline", "tab_outline"),
            ("key_points", "tab_key_points"),
            ("questions", "tab_questions"),
            ("flashcards", "tab_flashcards"),
            ("glossary", "tab_glossary"),
        ]

        # UI
        self._build_ui()
        self._update_provider_env_hint()
        self.after(100, self._process_queue)

    def _t(self, key: str, **kwargs: Any) -> str:
        language_map = TRANSLATIONS.get(self.ui_lang, TRANSLATIONS["it"])
        template = language_map.get(key, TRANSLATIONS["it"].get(key, key))
        return template.format(**kwargs)

    def _set_ui_lang(self, lang: str) -> None:
        if lang not in TRANSLATIONS:
            return
        self.ui_lang = lang
        self.ui_lang_var.set(lang)
        self._refresh_ui_texts()
        self._update_provider_env_hint()

    def _on_ui_language_change(self, _event: Any = None) -> None:
        self._set_ui_lang(self.ui_lang_var.get())

    def _refresh_ui_texts(self) -> None:
        notebook = cast(Any, self.nb)
        self.title(self._t("window_title"))
        self.lbl_audio_file.config(text=self._t("label_audio_file"))
        self.btn_browse.config(text=self._t("button_browse"))
        self.lbl_model.config(text=self._t(self._model_label_key()))
        self.lbl_audio_lang.config(text=self._t("label_audio_lang"))
        self.lbl_chunk.config(text=self._t("label_chunk_sec"))
        self.lbl_ui_lang.config(text=self._t("label_ui_lang"))
        self.lbl_transcription_provider.config(
            text=self._t("label_transcription_provider"))
        self.lbl_llm_provider.config(text=self._t("label_llm_provider"))
        self.btn_transcribe.config(text=self._t("button_transcribe"))
        self.btn_cancel.config(text=self._t("button_cancel"))
        self.btn_llm.config(text=self._t("button_generate"))
        self.btn_save_text.config(text=self._t("button_save_text"))
        notebook.tab(self.tab_transc, text=self._t("tab_transcription"))

        for section_id, tab_title_key in self.section_tab_ids:
            tab = self.section_frames.get(section_id)
            if tab is not None:
                notebook.tab(tab, text=self._t(tab_title_key))

        for widget, text_key in self.section_buttons:
            widget.config(text=self._t(text_key))

        ready_values = {v.get("status_ready", "")
                        for v in TRANSLATIONS.values()}
        if self.status_var.get() in ready_values:
            self.status_var.set(self._t("status_ready"))

    def _transcription_model_values(self, provider: str) -> tuple[str, ...]:
        if self._normalize_transcription_provider(provider) == "faster-whisper":
            return FASTER_WHISPER_TRANSCRIPTION_MODELS
        return GROQ_TRANSCRIPTION_MODELS

    def _model_label_key(self) -> str:
        provider = self._normalize_transcription_provider(
            self.transcription_provider_var.get()
        )
        if provider == "faster-whisper":
            return "label_faster_whisper_model"
        return "label_groq_model"

    def _sync_model_choices_for_provider(self) -> None:
        provider = self._normalize_transcription_provider(
            self.transcription_provider_var.get()
        )
        self.lbl_model.config(text=self._t(self._model_label_key()))
        model_values = self._transcription_model_values(provider)
        self.combo_model.configure(values=model_values)

        current_value = self.model_var.get().strip()
        if current_value in model_values:
            return

        default_value = (
            FASTER_WHISPER_MODEL
            if provider == "faster-whisper"
            else WHISPER_MODEL
        )
        if default_value in model_values:
            self.model_var.set(default_value)
        elif model_values:
            self.model_var.set(model_values[0])

    def _on_transcription_provider_change(self, _event: Any = None) -> None:
        ProcessingMixin._on_transcription_provider_change(self, _event)
        self._sync_model_choices_for_provider()

    def _has_selected_audio_file(self) -> bool:
        path = self.audio_entry.get().strip()
        return bool(path and os.path.isfile(path))

    def _has_transcription_text(self) -> bool:
        return bool(self.text_transc.get("1.0", tk.END).strip())

    def _update_transcribe_button_state(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            self.btn_transcribe.config(state="disabled")
            return

        can_transcribe = self._has_selected_audio_file() or self._has_transcription_text()
        self.btn_transcribe.config(state="normal" if can_transcribe else "disabled")

    def _on_audio_entry_change(self, _event: Any = None) -> None:
        self._update_transcribe_button_state()

    def _on_transcription_text_change(self, _event: Any = None) -> None:
        self._update_transcribe_button_state()

    def _resolve_audio_initial_dir(self) -> str:
        if AUDIO_INITIAL_DIR and os.path.isdir(AUDIO_INITIAL_DIR):
            return AUDIO_INITIAL_DIR

        profile_dir = os.path.expanduser("~")
        if profile_dir and os.path.isdir(profile_dir):
            return profile_dir

        return os.getcwd()

    # ------------------------- UI -------------------------
    def _build_ui(self):
        pad: dict[str, Any] = {"padx": 8, "pady": 6}

        # Riga 1: Selettore file
        row1 = ttk.Frame(self)
        row1.pack(fill="x", **pad)
        self.lbl_audio_file = ttk.Label(row1, text=self._t("label_audio_file"))
        self.lbl_audio_file.pack(side="left")
        self.audio_entry = ttk.Entry(row1)
        self.audio_entry.pack(side="left", fill="x", expand=True, padx=(6, 6))
        self.audio_entry.bind("<KeyRelease>", self._on_audio_entry_change)
        self.audio_entry.bind("<FocusOut>", self._on_audio_entry_change)
        self.btn_browse = ttk.Button(row1, text=self._t("button_browse"),
                                     command=self._browse)
        self.btn_browse.pack(side="left")

        # Riga 2: Modello + Lingua + Chunk
        row2 = ttk.Frame(self)
        row2.pack(fill="x", **pad)
        self.lbl_model = ttk.Label(row2, text=self._t(self._model_label_key()))
        self.lbl_model.pack(side="left")
        initial_provider = self._normalize_transcription_provider(
            self.transcription_provider_var.get()
        )
        initial_model = (
            FASTER_WHISPER_MODEL
            if initial_provider == "faster-whisper"
            else WHISPER_MODEL
        )
        self.model_var = tk.StringVar(value=initial_model)
        self.combo_model = ttk.Combobox(
            row2,
            textvariable=self.model_var,
            state="readonly",
            values=self._transcription_model_values(initial_provider),
            width=26,
        )
        self.combo_model.pack(side="left", padx=(6, 16))

        self.lbl_audio_lang = ttk.Label(row2, text=self._t("label_audio_lang"))
        self.lbl_audio_lang.pack(side="left")
        self.lang_var = tk.StringVar(value="auto")
        ttk.Combobox(row2, textvariable=self.lang_var, state="readonly", values=[
            "auto", "it", "en", "es", "fr", "de", "pt", "nl"
        ], width=8).pack(side="left", padx=(6, 16))

        self.lbl_chunk = ttk.Label(row2, text=self._t("label_chunk_sec"))
        self.lbl_chunk.pack(side="left")
        self.chunk_var = tk.IntVar(value=90)
        ttk.Spinbox(row2, from_=15, to=300, increment=5,
                    textvariable=self.chunk_var, width=6).pack(side="left")

        self.lbl_ui_lang = ttk.Label(row2, text=self._t("label_ui_lang"))
        self.lbl_ui_lang.pack(side="left", padx=(16, 0))
        self.combo_ui_lang = ttk.Combobox(
            row2,
            textvariable=self.ui_lang_var,
            state="readonly",
            values=list(TRANSLATIONS.keys()),
            width=5,
        )
        self.combo_ui_lang.pack(side="left", padx=(6, 0))
        self.combo_ui_lang.bind("<<ComboboxSelected>>",
                                self._on_ui_language_change)

        self.lbl_transcription_provider = ttk.Label(
            row2, text=self._t("label_transcription_provider"))
        self.lbl_transcription_provider.pack(side="left", padx=(16, 0))
        self.combo_transcription_provider = ttk.Combobox(
            row2,
            textvariable=self.transcription_provider_var,
            state="readonly",
            values=["groq", "faster-whisper"],
            width=16,
        )
        self.combo_transcription_provider.pack(side="left", padx=(6, 0))
        self.combo_transcription_provider.bind(
            "<<ComboboxSelected>>", self._on_transcription_provider_change)
        self._sync_model_choices_for_provider()

        self.lbl_llm_provider = ttk.Label(
            row2, text=self._t("label_llm_provider"))
        self.lbl_llm_provider.pack(side="left", padx=(16, 0))
        self.combo_llm_provider = ttk.Combobox(
            row2,
            textvariable=self.llm_provider_var,
            state="readonly",
            values=["groq", "ollama"],
            width=10,
        )
        self.combo_llm_provider.pack(side="left", padx=(6, 0))
        self.combo_llm_provider.bind(
            "<<ComboboxSelected>>", self._on_llm_provider_change)

        # Riga 3: Pulsanti
        row3 = ttk.Frame(self)
        row3.pack(fill="x", **pad)
        self.btn_transcribe = ttk.Button(
            row3, text=self._t("button_transcribe"), command=self._start, state="disabled")
        self.btn_transcribe.pack(side="left")
        self.btn_cancel = ttk.Button(
            row3, text=self._t("button_cancel"), command=self._cancel, state="disabled")
        self.btn_cancel.pack(side="left", padx=(8, 0))

        self.btn_llm = ttk.Button(
            row3,
            text=self._t("button_generate"),
            command=self._postprocess,
            state="normal"
        )
        self.btn_llm.pack(side="right")
        self.btn_save_text = ttk.Button(
            row3,
            text=self._t("button_save_text"),
            command=self._save_text,
        )
        self.btn_save_text.pack(side="right", padx=(0, 8))

        # Riga 4: Stato
        row4 = ttk.Frame(self)
        row4.pack(fill="x", **pad)
        self.progress = ttk.Progressbar(row4, mode="determinate")
        self.progress.pack(fill="x", expand=True)
        self.status_var = tk.StringVar(value=self._t("status_ready"))
        self.lbl_status = ttk.Label(row4, textvariable=self.status_var)
        self.lbl_status.pack(
            fill="x", expand=True, anchor="w")

        # Riga 5: Notebook Tabs per contenuti
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, **pad)

        # Tab: Trascrizione (live)
        self.tab_transc = ttk.Frame(self.nb)
        self.nb.add(self.tab_transc, text=self._t("tab_transcription"))
        self.text_transc = tk.Text(self.tab_transc, wrap="word")
        self.text_transc.pack(side="left", fill="both", expand=True)
        yscroll = ttk.Scrollbar(
            self.tab_transc,
            orient="vertical",
            command=self._get_yview_command(self.text_transc)
        )
        yscroll.pack(side="right", fill="y")
        self.text_transc.configure(yscrollcommand=yscroll.set)
        self.text_transc.bind("<Control-v>", self._paste_into_transcription)
        self.text_transc.bind("<Control-V>", self._paste_into_transcription)
        self.text_transc.bind("<Shift-Insert>", self._paste_into_transcription)
        self.text_transc.bind("<Command-v>", self._paste_into_transcription)
        self.text_transc.bind("<Command-V>", self._paste_into_transcription)
        self.text_transc.bind("<KeyRelease>", self._on_transcription_text_change)
        self.text_transc.bind("<FocusOut>", self._on_transcription_text_change)

        # Tab vuote che popoleremo dopo LLM
        self.sections: dict[str, tk.Text] = {}
        self.section_frames: dict[str, ttk.Frame] = {}
        self.section_buttons: list[tuple[ttk.Button, str]] = []
        for section_id, tab_title_key in self.section_tab_ids:
            frame = ttk.Frame(self.nb)
            self.section_frames[section_id] = frame
            self.nb.add(frame, text=self._t(tab_title_key))
            text = tk.Text(frame, wrap="word")
            text.pack(side="left", fill="both", expand=True)
            sb = ttk.Scrollbar(
                frame,
                orient="vertical",
                command=self._get_yview_command(text)
            )
            sb.pack(side="right", fill="y")
            text.configure(yscrollcommand=sb.set)

            btns = ttk.Frame(frame)
            btns.pack(fill="x")

            btn_copy = ttk.Button(btns, text=self._t("button_copy"), command=lambda t=text: self._copy_to_clip(
                t.get("1.0", tk.END)))
            btn_copy.pack(side="left")
            self.section_buttons.append((btn_copy, "button_copy"))

            btn_save_txt = ttk.Button(
                btns,
                text=self._t("button_save_txt"),
                command=lambda t=text, title_key=tab_title_key: self._save_string(
                    t.get(
                        "1.0", tk.END), f"{self._safe_name(self._t(title_key))}.txt"
                )
            )
            btn_save_txt.pack(side="left", padx=6)
            self.section_buttons.append((btn_save_txt, "button_save_txt"))

            if section_id == "summary_markdown":
                btn_save_md = ttk.Button(btns, text=self._t("button_save_md"), command=lambda t=text: self._save_string(
                    t.get("1.0", tk.END), "riassunto.md"))
                btn_save_md.pack(side="left", padx=6)
                self.section_buttons.append((btn_save_md, "button_save_md"))
            if section_id == "flashcards":
                btn_export = ttk.Button(btns, text=self._t("button_export_anki"),
                                        command=self._export_flashcards_csv)
                btn_export.pack(side="left", padx=6)
                self.section_buttons.append((btn_export, "button_export_anki"))

            self.sections[section_id] = text

        self._update_transcribe_button_state()

    # ------------------------- Azioni UI -------------------------
    def _browse(self):
        path = filedialog.askopenfilename(title=self._t("file_dialog_choose_audio"),
                                          initialdir=self._resolve_audio_initial_dir(),
                                          filetypes=[
                                              (self._t("file_dialog_audio"),
                                               ".wav .mp3 .m4a .aac .flac .ogg .wma"),
                                              (self._t("file_dialog_all"), "*.*"),
        ])
        if path:
            self.audio_path = path
            self.audio_entry.delete(0, tk.END)
            self.audio_entry.insert(0, path)
        self._update_transcribe_button_state()

    def _start(self):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo(
                self._t("dialog_title_in_progress"), self._t("dialog_msg_in_progress"))
            return

        api_key = GROQ_API_KEY
        if self._transcription_provider() == "groq" and not api_key:
            messagebox.showerror(self._t("dialog_title_error"),
                                 self._t("dialog_msg_missing_api"))
            return

        path = self.audio_entry.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showerror(self._t("dialog_title_error"),
                                 self._t("dialog_msg_invalid_audio"))
            return

        try:
            audio = self._load_audio_segment(path)
            self.total_ms = len(audio)
        except Exception as e:
            messagebox.showerror(self._t("dialog_title_audio_error"), self._t(
                "dialog_msg_cannot_open_audio", error=e))
            return

        # Reset UI
        self.text_transc.delete("1.0", tk.END)
        self.progress['value'] = 0
        self.status_var.set(self._t("status_init_transcription"))
        self.text_transc.insert(
            tk.END,
            self._t("status_tag", message=self._t(
                "status_init_transcription")),
        )
        self.btn_transcribe.config(state="disabled")
        self.btn_cancel.config(state="normal")
        self.cancel_event.clear()

        # Avvia worker
        self.worker_thread = threading.Thread(
            target=self._worker_transcribe,
            args=(api_key, path, self.model_var.get(),
                  self.lang_var.get(), int(self.chunk_var.get())),
            daemon=True,
        )
        self.worker_thread.start()

    def _cancel(self):
        if self.worker_thread and self.worker_thread.is_alive():
            self.cancel_event.set()
            self.status_var.set(self._t("status_canceling"))
            self.text_transc.insert(tk.END, self._t(
                "status_tag", message=self._t("status_canceling")))
        else:
            self.status_var.set(self._t("status_no_running_transcription"))

    def _save_text(self):
        content = self.text_transc.get("1.0", tk.END).strip()
        if not content:
            messagebox.showinfo(self._t("dialog_title_empty"),
                                self._t("dialog_msg_nothing_to_save"))
            return
        path = filedialog.asksaveasfilename(title=self._t("file_dialog_save_transcript"),
                                            defaultextension=".txt",
                                            filetypes=[(self._t("file_dialog_text"), ".txt"), (self._t("file_dialog_all"), "*.*")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self.status_var.set(self._t("dialog_msg_saved_file", path=path))

    # ------------------------- Worker: Trascrizione -------------------------
    def _worker_transcribe(self, api_key: str, path: str, model: str, lang: str, chunk_sec: int):
        transcription_provider = self._transcription_provider()
        try:
            client = self._create_transcription_client(
                api_key, self.model_var.get())
        except Exception as e:
            self.msg_queue.put(("error", str(e)))
            return

        try:
            audio = self._load_audio_segment(path)
            audio = audio.set_channels(1).set_frame_rate(16000)
            total_ms = len(audio)
        except Exception as e:
            self.msg_queue.put(
                ("error", self._t("worker_error_open_audio", error=e)))
            return

        chunk_ms = max(10, chunk_sec) * 1000
        n_chunks = math.ceil(total_ms / chunk_ms)

        for i in range(n_chunks):
            if self.cancel_event.is_set():
                self.msg_queue.put(
                    ("status", self._t("status_canceled_by_user")))
                break

            start = i * chunk_ms
            end = min((i + 1) * chunk_ms, total_ms)
            seg = audio[start:end]

            # Esporta in WAV temporaneo
            try:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp_path = tmp.name
                    seg.export(tmp_path, format="wav")
            except Exception as e:
                self.msg_queue.put(
                    ("error", self._t("worker_error_export_chunk", chunk=i+1, error=e)))
                break

            # Chiamata provider trascrizione
            try:
                text_piece = self._transcribe_audio_chunk(
                    client, tmp_path, model, lang)
            except Exception as e:
                if transcription_provider == "groq":
                    self.msg_queue.put(
                        ("error", self._t("worker_error_groq_chunk", chunk=i+1, error=e)))
                else:
                    self.msg_queue.put(
                        ("error", f"Errore faster-whisper chunk {i+1}: {e}"))
                break
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

            # Anteprima con timestamp
            h1 = str(timedelta(milliseconds=start))
            h2 = str(timedelta(milliseconds=end))
            preview_line = f"[{h1} → {h2}]\n{text_piece}\n\n"
            self.msg_queue.put(("append", preview_line))

            progress_val = (end / total_ms) * 100
            self.msg_queue.put(("progress", progress_val))
            self.msg_queue.put(
                ("status", self._t("status_chunk_completed", current=i+1, total=n_chunks)))
        else:
            self.msg_queue.put(
                ("status", self._t("status_transcription_completed")))

        self.msg_queue.put(("done", None))

    # ------------------------- Post-processing LLM (nuova pipeline) -------------------------
    def _postprocess(self):
        full_text = self.text_transc.get("1.0", tk.END).strip()
        if not full_text:
            messagebox.showinfo(self._t("dialog_title_empty"), self._t(
                "dialog_msg_transcribe_or_paste"))
            return

        api_key = GROQ_API_KEY
        if self._llm_provider() == "groq" and not api_key:
            messagebox.showerror(self._t("dialog_title_error"),
                                 self._t("dialog_msg_missing_api"))
            return

        self.btn_llm.config(state="disabled")
        self.status_var.set(self._t("status_llm_generating"))
        self.text_transc.insert(tk.END, self._t("status_llm_note_line"))
        self.partial_outs = {}

        def worker():
            try:
                client = self._create_llm_client(api_key)
                notes_label = self._llm_notes_label()
                system_prompt = self._llm_academic_system_prompt()

                # 1) Map-Reduce su trascrizione → NOTE COMPLETE
                self.msg_queue.put(("status", self._t("status_llm_notes")))
                notes = self._map_reduce_notes(client, full_text)

                current_language = self._current_language()
                steps = build_postprocess_plan(
                    target_questions=TARGET_QUESTIONS,
                    target_flashcards=TARGET_FLASHCARDS,
                    target_glossary=TARGET_GLOSSARY,
                )

                outs: dict[str, Any] = {}
                for step in steps:
                    self.msg_queue.put(("status", self._t(step["status_key"])))

                    if step["kind"] == "summary":
                        result = self._gen_summary(client, notes)
                    elif step["kind"] == "list":
                        result = self._gen_list_with_count(
                            client,
                            notes,
                            step["list_kind"],
                            step["target"],
                        )
                    else:
                        prompt_name = step["prompt_name"]
                        if prompt_name == "abstract":
                            user_prompt = build_abstract_prompt(
                                current_language=current_language,
                                notes_text=notes,
                                notes_label_value=notes_label,
                            )
                            result = self._llm(
                                client, system_prompt, user_prompt)
                        elif prompt_name == "outline":
                            user_prompt = build_outline_prompt(
                                current_language=current_language,
                                notes_text=notes,
                                notes_label_value=notes_label,
                            )
                            outline_json_txt = self._llm(
                                client, system_prompt, user_prompt)
                            outline_raw = extract_json_candidate(
                                outline_json_txt)
                            result = normalize_outline_nodes(outline_raw)
                        elif prompt_name == "key_points":
                            user_prompt = build_keypoints_prompt(
                                current_language=current_language,
                                notes_text=notes,
                                notes_label_value=notes_label,
                            )
                            keypoints_txt = self._llm(
                                client, system_prompt, user_prompt)
                            result = parse_key_points(keypoints_txt)
                        else:
                            raise RuntimeError(
                                f"Prompt non supportato nel piano: {prompt_name}")

                    outs[step["section"]] = result
                    self.msg_queue.put(
                        ("partial_result", {step["section"]: result}))

                self.msg_queue.put(("open_results", outs))
            except Exception as e:
                self.msg_queue.put(
                    ("error", self._t("worker_error_llm", error=e)))
            finally:
                self.msg_queue.put(("status", self._t("status_ready")))
                self.msg_queue.put(("enable_llm", None))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------- Utils -------------------------
    def _get_yview_command(self, widget: tk.Text) -> ScrollbarCommand:
        yview = getattr(widget, "yview", None)
        if not callable(yview):
            raise TypeError("Widget Tkinter senza metodo yview valido.")
        return cast(ScrollbarCommand, yview)

    def _paste_into_transcription(self, _event: Any = None) -> str:
        try:
            pasted = self.clipboard_get()
        except Exception:
            return "break"
        self.text_transc.insert(tk.INSERT, pasted)
        self.text_transc.see(tk.INSERT)
        self._update_transcribe_button_state()
        return "break"

    def _handle_queue_partial_result(self, payload: Any) -> None:
        partial_payload = cast(dict[str, Any], payload)
        self.partial_outs.update(partial_payload)
        self._open_results(self.partial_outs)
        for section_id in partial_payload.keys():
            tab = self.section_frames.get(section_id)
            if tab is not None:
                cast(Any, self.nb).select(tab)
                break

    def _handle_queue_message(self, kind: QueueKind, payload: Any) -> None:
        def handle_append(p: Any) -> None:
            self.text_transc.insert(tk.END, p)
            self.text_transc.see(tk.END)

        def handle_progress(p: Any) -> None:
            self.progress.configure(value=p)

        def handle_status(p: Any) -> None:
            self.status_var.set(str(p))
            self.text_transc.insert(tk.END, self._t("status_tag", message=p))
            self.text_transc.see(tk.END)

        def handle_error(p: Any) -> None:
            self.status_var.set(self._t("dialog_title_error"))
            messagebox.showerror(self._t("dialog_title_error"), str(p))

        def handle_open_results(p: Any) -> None:
            self._open_results(p)

        def handle_enable_llm(_p: Any) -> None:
            self.btn_llm.config(state="normal")

        def handle_done(_p: Any) -> None:
            self._update_transcribe_button_state()
            self.btn_cancel.config(state="disabled")

        handlers: dict[QueueKind, Callable[[Any], None]] = {
            "append": handle_append,
            "progress": handle_progress,
            "status": handle_status,
            "error": handle_error,
            "open_results": handle_open_results,
            "partial_result": self._handle_queue_partial_result,
            "enable_llm": handle_enable_llm,
            "done": handle_done,
        }

        if kind == "status":
            try:
                handlers[kind](payload)
            except Exception:
                self.status_var.set(str(payload))
            return

        handler = handlers.get(kind)
        if handler is not None:
            handler(payload)

    # ------------------------- Aggiornamento UI (main thread) -------------------------
    def _process_queue(self):
        try:
            while not self.msg_queue.empty():
                kind, payload = self.msg_queue.get()
                self._handle_queue_message(kind, payload)
        except Exception as e:
            LOGGER.exception("Unhandled error while processing UI queue")
            self.status_var.set(self._t("dialog_title_error"))
            messagebox.showerror(self._t("dialog_title_error"), str(e))
        finally:
            self.after(100, self._process_queue)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = LectureTranscriberApp()
    app.mainloop()


if __name__ == "__main__":
    main()
