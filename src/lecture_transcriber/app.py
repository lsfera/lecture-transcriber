import os
import threading
import tempfile
import math
import queue
import json
import re
import importlib
from typing import Any, Callable, Literal, Protocol, TypeAlias, cast
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from datetime import timedelta


"""
===========================
 App Tkinter: Trascrivi Lezioni + Riassunti & Flashcard (Groq)
===========================

REQUISITI (installazione):
    pip install groq pydub

NOTE:
 - Imposta la tua chiave via variabile d'ambiente GROQ_API_KEY (consigliato).
 - Supporta file audio comuni: .wav .mp3 .m4a .aac .flac .ogg .wma
 - Trascrizione con Whisper (Groq) a chunk per file lunghi.
 - Post-process con LLM (Groq) per generare:
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

# ==========================
#  CONFIGURAZIONE
# ==========================
# NON inserire qui la chiave. Usa:  setx GROQ_API_KEY "la_tua_chiave"  (Windows)
#                                   export GROQ_API_KEY="la_tua_chiave" (macOS/Linux)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
WHISPER_MODEL = "whisper-large-v3-turbo"
LLM_MODEL = "llama-3.3-70b-versatile"

# Target/parametri generazione
TARGET_SUMMARY_WORDS_MIN = 1700
TARGET_SUMMARY_WORDS_MAX = 2200
TARGET_QUESTIONS = 16
TARGET_FLASHCARDS = 30
TARGET_GLOSSARY = 20
LLM_TEMP = 0.2
LLM_MAX_TOKENS = 4000    # alza se supportato dal servizio/modello
# per map-reduce note (circa 4-5k token grezzi equivalenti)
CHUNK_CHARLEN = 6000


UI_LANG = os.getenv("UI_LANG", "it")

TRANSLATIONS: dict[str, dict[str, str]] = {
    "it": {
        "window_title": "Lezione → Trascrizione, Riassunti, Domande & Flashcard (Groq)",
        "label_audio_file": "File audio:",
        "button_browse": "Sfoglia…",
        "label_whisper_model": "Modello Whisper:",
        "label_audio_lang": "Lingua:",
        "label_chunk_sec": "Chunk (s):",
        "label_ui_lang": "UI:",
        "button_transcribe": "Trascrivi",
        "button_cancel": "Annulla",
        "button_generate": "Genera Riassunti/Quiz/Flashcard",
        "button_save_text": "Salva testo…",
        "status_ready": "Pronto.",
        "status_init_transcription": "Inizializzo trascrizione…",
        "status_canceling": "Annullamento in corso…",
        "status_no_running_transcription": "Nessuna trascrizione in corso.",
        "status_transcription_completed": "Trascrizione completata.",
        "status_chunk_completed": "Chunk {current}/{total} completato",
        "status_canceled_by_user": "Annullato dall'utente.",
        "status_llm_generating": "LLM: generazione contenuti in corso…",
        "status_llm_notes": "LLM: sintetizzo note/outline…",
        "status_llm_abstract": "LLM: genero abstract…",
        "status_llm_summary": "LLM: genero riassunto lungo…",
        "status_llm_outline": "LLM: costruisco outline…",
        "status_llm_keypoints": "LLM: estraggo key points…",
        "status_llm_questions": "LLM: genero domande…",
        "status_llm_flashcards": "LLM: genero flashcard…",
        "status_llm_glossary": "LLM: genero glossario…",
        "status_tag": "[STATUS] {message}\n",
        "status_llm_note_line": "[STATUS] LLM: generazione note e contenuti…\n",
        "tab_transcription": "Trascrizione",
        "tab_abstract": "Abstract",
        "tab_summary": "Riassunto (Markdown)",
        "tab_outline": "Outline",
        "tab_key_points": "Key Points",
        "tab_questions": "Domande",
        "tab_flashcards": "Flashcard",
        "tab_glossary": "Glossario",
        "button_copy": "Copia",
        "button_save_txt": "Salva .txt",
        "button_save_md": "Salva .md",
        "button_export_anki": "Esporta CSV (Anki)",
        "dialog_title_in_progress": "In corso",
        "dialog_msg_in_progress": "Una trascrizione è già in corso…",
        "dialog_title_error": "Errore",
        "dialog_msg_missing_api": "API Key Groq mancante: imposta la variabile d'ambiente GROQ_API_KEY.",
        "dialog_msg_invalid_audio": "Seleziona un file audio valido.",
        "dialog_title_audio_error": "Errore audio",
        "dialog_msg_cannot_open_audio": "Impossibile aprire l'audio: {error}",
        "dialog_title_empty": "Vuoto",
        "dialog_msg_nothing_to_save": "Non c'è testo da salvare.",
        "dialog_msg_transcribe_or_paste": "Prima trascrivi o incolla del testo nella scheda Trascrizione.",
        "dialog_title_no_cards": "Nessuna carta",
        "dialog_msg_flashcard_tab_missing": "Scheda Flashcard non disponibile.",
        "dialog_msg_no_cards_export": "Nessuna flashcard trovata da esportare.",
        "dialog_title_exported": "Esportato",
        "dialog_msg_saved_flashcards": "Flashcard salvate in: {path}",
        "dialog_msg_export_csv_error": "Impossibile esportare CSV: {error}",
        "dialog_title_saved": "Salvato",
        "dialog_msg_saved_file": "File salvato in: {path}",
        "file_dialog_choose_audio": "Scegli file audio",
        "file_dialog_audio": "Audio",
        "file_dialog_all": "Tutti i file",
        "file_dialog_save_transcript": "Salva trascrizione",
        "file_dialog_text": "Testo",
        "file_dialog_export_csv": "Esporta flashcard CSV (Anki)",
        "file_dialog_csv": "CSV",
        "file_dialog_save": "Salva",
        "worker_error_groq": "Errore Groq: {error}",
        "worker_error_open_audio": "Errore aprendo l'audio: {error}",
        "worker_error_export_chunk": "Errore esportando chunk {chunk}: {error}",
        "worker_error_groq_chunk": "Errore Groq chunk {chunk}: {error}",
        "worker_error_llm": "LLM: errore {error}",
        "answer_label": "Risposta",
        "difficulty_label": "Difficoltà",
    },
    "en": {
        "window_title": "Lecture → Transcription, Summaries, Questions & Flashcards (Groq)",
        "label_audio_file": "Audio file:",
        "button_browse": "Browse…",
        "label_whisper_model": "Whisper model:",
        "label_audio_lang": "Language:",
        "label_chunk_sec": "Chunk (s):",
        "label_ui_lang": "UI:",
        "button_transcribe": "Transcribe",
        "button_cancel": "Cancel",
        "button_generate": "Generate Summaries/Quiz/Flashcards",
        "button_save_text": "Save text…",
        "status_ready": "Ready.",
        "status_init_transcription": "Initializing transcription…",
        "status_canceling": "Cancelling…",
        "status_no_running_transcription": "No transcription is currently running.",
        "status_transcription_completed": "Transcription completed.",
        "status_chunk_completed": "Chunk {current}/{total} completed",
        "status_canceled_by_user": "Canceled by user.",
        "status_llm_generating": "LLM: generating content…",
        "status_llm_notes": "LLM: synthesizing notes/outline…",
        "status_llm_abstract": "LLM: generating abstract…",
        "status_llm_summary": "LLM: generating long summary…",
        "status_llm_outline": "LLM: building outline…",
        "status_llm_keypoints": "LLM: extracting key points…",
        "status_llm_questions": "LLM: generating questions…",
        "status_llm_flashcards": "LLM: generating flashcards…",
        "status_llm_glossary": "LLM: generating glossary…",
        "status_tag": "[STATUS] {message}\n",
        "status_llm_note_line": "[STATUS] LLM: generating notes and content…\n",
        "tab_transcription": "Transcription",
        "tab_abstract": "Abstract",
        "tab_summary": "Summary (Markdown)",
        "tab_outline": "Outline",
        "tab_key_points": "Key Points",
        "tab_questions": "Questions",
        "tab_flashcards": "Flashcards",
        "tab_glossary": "Glossary",
        "button_copy": "Copy",
        "button_save_txt": "Save .txt",
        "button_save_md": "Save .md",
        "button_export_anki": "Export CSV (Anki)",
        "dialog_title_in_progress": "In progress",
        "dialog_msg_in_progress": "A transcription is already running…",
        "dialog_title_error": "Error",
        "dialog_msg_missing_api": "Missing Groq API key: set the GROQ_API_KEY environment variable.",
        "dialog_msg_invalid_audio": "Select a valid audio file.",
        "dialog_title_audio_error": "Audio error",
        "dialog_msg_cannot_open_audio": "Unable to open audio: {error}",
        "dialog_title_empty": "Empty",
        "dialog_msg_nothing_to_save": "There is no text to save.",
        "dialog_msg_transcribe_or_paste": "Transcribe or paste text in the Transcription tab first.",
        "dialog_title_no_cards": "No cards",
        "dialog_msg_flashcard_tab_missing": "Flashcards tab is not available.",
        "dialog_msg_no_cards_export": "No flashcards found to export.",
        "dialog_title_exported": "Exported",
        "dialog_msg_saved_flashcards": "Flashcards saved to: {path}",
        "dialog_msg_export_csv_error": "Unable to export CSV: {error}",
        "dialog_title_saved": "Saved",
        "dialog_msg_saved_file": "File saved to: {path}",
        "file_dialog_choose_audio": "Choose audio file",
        "file_dialog_audio": "Audio",
        "file_dialog_all": "All files",
        "file_dialog_save_transcript": "Save transcription",
        "file_dialog_text": "Text",
        "file_dialog_export_csv": "Export flashcards CSV (Anki)",
        "file_dialog_csv": "CSV",
        "file_dialog_save": "Save",
        "worker_error_groq": "Groq error: {error}",
        "worker_error_open_audio": "Error opening audio: {error}",
        "worker_error_export_chunk": "Error exporting chunk {chunk}: {error}",
        "worker_error_groq_chunk": "Groq error on chunk {chunk}: {error}",
        "worker_error_llm": "LLM: error {error}",
        "answer_label": "Answer",
        "difficulty_label": "Difficulty",
    },
}


class AudioSegmentLike(Protocol):
    def set_channels(self, channels: int) -> "AudioSegmentLike": ...

    def set_frame_rate(self, frame_rate: int) -> "AudioSegmentLike": ...

    def __len__(self) -> int: ...

    def __getitem__(self, key: slice) -> "AudioSegmentLike": ...

    def export(self, out_f: str, format: str) -> Any: ...


class AudioSegmentFactory(Protocol):
    @staticmethod
    def from_file(file: str) -> AudioSegmentLike: ...


class TranscriptionLike(Protocol):
    text: str | None


class TranscriptionsAPI(Protocol):
    def create(self, **kwargs: Any) -> TranscriptionLike: ...


class AudioAPI(Protocol):
    transcriptions: TranscriptionsAPI


class MessageLike(Protocol):
    content: str


class ChoiceLike(Protocol):
    message: MessageLike


class CompletionResponseLike(Protocol):
    choices: list[ChoiceLike]


class CompletionsAPI(Protocol):
    def create(self, **kwargs: Any) -> CompletionResponseLike: ...


class ChatAPI(Protocol):
    completions: CompletionsAPI


class GroqClientLike(Protocol):
    audio: AudioAPI
    chat: ChatAPI


class GroqFactory(Protocol):
    def __call__(self, *, api_key: str) -> GroqClientLike: ...


def _require_module_attr(module_name: str, attr_name: str, install_message: str) -> Any:
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise SystemExit(install_message) from exc

    attr = getattr(module, attr_name, None)
    if attr is None:
        raise SystemExit(
            f"Modulo '{module_name}' senza attributo richiesto '{attr_name}'."
        )
    return attr


AudioSegment = cast(
    AudioSegmentFactory,
    _require_module_attr("pydub", "AudioSegment",
                         "Manca pydub. Installa con: pip install pydub"),
)
Groq = cast(
    GroqFactory,
    _require_module_attr(
        "groq", "Groq", "Manca groq. Installa con: pip install groq"),
)


QueueKind: TypeAlias = Literal[
    "append", "progress", "status", "error", "open_results", "enable_llm", "done"
]
QueueMessage: TypeAlias = tuple[QueueKind, Any]
StrDict: TypeAlias = dict[str, str]
AnyDict: TypeAlias = dict[str, Any]
ScrollbarCommand: TypeAlias = Callable[..., Any]


class LectureTranscriberApp(tk.Tk):
    """App Tkinter per caricare un file audio di una lezione, trascriverlo con Groq Whisper
    e generare riassunti, domande e flashcard con un LLM (Groq).
    """

    def __init__(self):
        super().__init__()
        self.ui_lang = UI_LANG if UI_LANG in TRANSLATIONS else "it"
        self.ui_lang_var = tk.StringVar(value=self.ui_lang)
        self.title(self._t("window_title"))
        self.geometry("1200x820")

        # Stato
        self.audio_path = None
        self.worker_thread = None
        self.cancel_event = threading.Event()
        self.msg_queue: queue.Queue[QueueMessage] = queue.Queue()
        self.total_ms = 0
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

    def _on_ui_language_change(self, _event: Any = None) -> None:
        self._set_ui_lang(self.ui_lang_var.get())

    def _refresh_ui_texts(self) -> None:
        notebook = cast(Any, self.nb)
        self.title(self._t("window_title"))
        self.lbl_audio_file.config(text=self._t("label_audio_file"))
        self.btn_browse.config(text=self._t("button_browse"))
        self.lbl_model.config(text=self._t("label_whisper_model"))
        self.lbl_audio_lang.config(text=self._t("label_audio_lang"))
        self.lbl_chunk.config(text=self._t("label_chunk_sec"))
        self.lbl_ui_lang.config(text=self._t("label_ui_lang"))
        self.btn_start.config(text=self._t("button_transcribe"))
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
        self.btn_browse = ttk.Button(row1, text=self._t("button_browse"),
                                     command=self._browse)
        self.btn_browse.pack(side="left")

        # Riga 2: Modello + Lingua + Chunk
        row2 = ttk.Frame(self)
        row2.pack(fill="x", **pad)
        self.lbl_model = ttk.Label(row2, text=self._t("label_whisper_model"))
        self.lbl_model.pack(side="left")
        self.model_var = tk.StringVar(value=WHISPER_MODEL)
        ttk.Combobox(row2, textvariable=self.model_var, state="readonly", values=[
            "whisper-large-v3-turbo",
            "whisper-large-v3"
        ], width=26).pack(side="left", padx=(6, 16))

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

        # Riga 3: Pulsanti
        row3 = ttk.Frame(self)
        row3.pack(fill="x", **pad)
        self.btn_start = ttk.Button(
            row3, text=self._t("button_transcribe"), command=self._start)
        self.btn_start.pack(side="left")
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

    # ------------------------- Azioni UI -------------------------
    def _browse(self):
        path = filedialog.askopenfilename(title=self._t("file_dialog_choose_audio"),
                                          initialdir="/input",
                                          filetypes=[
                                              (self._t("file_dialog_audio"),
                                               ".wav .mp3 .m4a .aac .flac .ogg .wma"),
                                              (self._t("file_dialog_all"), "*.*"),
        ])
        if path:
            self.audio_path = path
            self.audio_entry.delete(0, tk.END)
            self.audio_entry.insert(0, path)

    def _start(self):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo(
                self._t("dialog_title_in_progress"), self._t("dialog_msg_in_progress"))
            return

        api_key = GROQ_API_KEY
        if not api_key:
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
        self.btn_start.config(state="disabled")
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
        try:
            client = Groq(api_key=api_key)
        except Exception as e:
            self.msg_queue.put(
                ("error", self._t("worker_error_groq", error=e)))
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

            # Chiamata API Groq (Whisper)
            try:
                with open(tmp_path, "rb") as f:
                    transcription_args: dict[str, Any] = {
                        "file": f,
                        "model": model,
                        "temperature": 0.0,
                    }
                    if lang != "auto":
                        transcription_args["language"] = lang
                    transcription = client.audio.transcriptions.create(
                        **transcription_args)
                os.unlink(tmp_path)
            except Exception as e:
                self.msg_queue.put(
                    ("error", self._t("worker_error_groq_chunk", chunk=i+1, error=e)))
                break

            text_piece = getattr(transcription, "text",
                                 None) or str(transcription)

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
        if not api_key:
            messagebox.showerror(self._t("dialog_title_error"),
                                 self._t("dialog_msg_missing_api"))
            return

        self.btn_llm.config(state="disabled")
        self.status_var.set(self._t("status_llm_generating"))
        self.text_transc.insert(tk.END, self._t("status_llm_note_line"))

        def worker():
            try:
                client = Groq(api_key=api_key)
                notes_label = self._llm_notes_label()
                system_prompt = self._llm_academic_system_prompt()

                # 1) Map-Reduce su trascrizione → NOTE COMPLETE
                self.msg_queue.put(("status", self._t("status_llm_notes")))
                notes = self._map_reduce_notes(client, full_text)

                # 2) Abstract (breve)
                self.msg_queue.put(("status", self._t("status_llm_abstract")))
                if self._is_english_ui():
                    abstract_user = (
                        f"Write an abstract of 6-8 sentences, faithful to the {notes_label} below. "
                        f"No bullet lists, prose only. {notes_label}:\n" + notes
                    )
                else:
                    abstract_user = (
                        "Scrivi un abstract di 6-8 frasi, fedele alle NOTE COMPLETE qui sotto. "
                        "Niente liste, solo prosa. NOTE COMPLETE:\n" + notes
                    )
                abstract = self._llm(client, system_prompt, abstract_user)

                # 3) Riassunto lungo con controllo parole
                self.msg_queue.put(("status", self._t("status_llm_summary")))
                summary_md = self._gen_summary(client, notes)

                # 4) Outline (JSON) → render testuale
                self.msg_queue.put(("status", self._t("status_llm_outline")))
                outline_json_txt = self._llm(
                    client,
                    system_prompt,
                    (
                        (
                            f'From the {notes_label}, create a hierarchical outline (max 3 levels) '
                            f'in JSON with this shape '
                        )
                        if self._is_english_ui()
                        else (
                            'Dalle NOTE COMPLETE crea un outline gerarchico (max 3 livelli) '
                            'in JSON della forma '
                        )
                    ) +
                    '[{"title":"...", "children":[...]}]. '
                    + ('ONLY JSON.\n\n' + f'{notes_label}:\n' if self._is_english_ui(
                    ) else 'SOLO JSON.\n\nNOTE COMPLETE:\n')
                    + notes
                )
                outline_json = cast(
                    list[dict[str, Any]],
                    self._extract_json(outline_json_txt) or []
                )

                # 5) Key points (lista semplice)
                self.msg_queue.put(("status", self._t("status_llm_keypoints")))
                keypoints_txt = self._llm(
                    client,
                    system_prompt,
                    (
                        "Extract 10-16 concise key points (single-line bullets) from the "
                        f"{notes_label}:\n"
                        if self._is_english_ui()
                        else
                        "Estrai 10-16 punti chiave sintetici "
                        "(bullet singola riga) dalle NOTE COMPLETE:\n"
                    ) + notes
                )
                key_points = [s.strip("-• ").strip()
                              for s in keypoints_txt.splitlines() if s.strip()]

                # 6) Domande
                self.msg_queue.put(("status", self._t("status_llm_questions")))
                questions = self._gen_list_with_count(
                    client, notes, "questions", TARGET_QUESTIONS)

                # 7) Flashcard
                self.msg_queue.put(
                    ("status", self._t("status_llm_flashcards")))
                flashcards = self._gen_list_with_count(
                    client, notes, "flashcards", TARGET_FLASHCARDS)

                # 8) Glossario
                self.msg_queue.put(("status", self._t("status_llm_glossary")))
                glossary = self._gen_list_with_count(
                    client, notes, "glossary", TARGET_GLOSSARY)

                outs: dict[str, Any] = {
                    "abstract": abstract,
                    "summary_markdown": summary_md,
                    "outline": outline_json,
                    "key_points": key_points,
                    "questions": questions,
                    "flashcards": flashcards,
                    "glossary": glossary,
                }
                self.msg_queue.put(("open_results", outs))
            except Exception as e:
                self.msg_queue.put(
                    ("error", self._t("worker_error_llm", error=e)))
            finally:
                self.msg_queue.put(("status", self._t("status_ready")))
                self.msg_queue.put(("enable_llm", None))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------- LLM helpers & generatori -------------------------
    def _llm(self, client: GroqClientLike, system: str, user: str) -> str:
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=LLM_TEMP,
            max_tokens=LLM_MAX_TOKENS,
        )
        return resp.choices[0].message.content.strip() if (resp and resp.choices) else ""

    def _split_for_llm(self, text: str, chunk_chars: int) -> list[str]:
        text = re.sub(r"\s+", " ", text).strip()
        return [text[i:i+chunk_chars] for i in range(0, len(text), chunk_chars)]

    def _is_english_ui(self) -> bool:
        return self.ui_lang == "en"

    def _llm_notes_label(self) -> str:
        return "COMPLETE NOTES" if self._is_english_ui() else "NOTE COMPLETE"

    def _llm_academic_system_prompt(self) -> str:
        if self._is_english_ui():
            return "You are an academic assistant. Be faithful to the source and do not invent facts."
        return "Sei un assistente accademico. Sii fedele alla fonte e non inventare informazioni."

    def _map_reduce_notes(self, client: GroqClientLike, transcript_text: str) -> str:
        system = self._llm_academic_system_prompt()
        chunks = self._split_for_llm(transcript_text, CHUNK_CHARLEN)

        partials: list[str] = []
        for idx, ch in enumerate(chunks, 1):
            if self._is_english_ui():
                user = (
                    f"This is transcript chunk {idx}/{len(chunks)}.\n"
                    "1) Extract numbered key concepts.\n"
                    "2) List technical terms with short definitions.\n"
                    "3) Propose a mini-outline (max 2 levels).\n\n"
                    f"CHUNK:\n{ch}"
                )
            else:
                user = (
                    f"Questo è il chunk {idx}/{len(chunks)} della trascrizione.\n"
                    "1) Estrai i concetti chiave numerati.\n"
                    "2) Elenca termini tecnici con brevi definizioni.\n"
                    "3) Proponi un mini-outline (max 2 livelli).\n\n"
                    f"CHUNK:\n{ch}"
                )
            out = self._llm(client, system, user)
            partials.append(out)

        if self._is_english_ui():
            reduce_user = (
                "Merge the notes below into:\n"
                "A) A global OUTLINE (max 3 levels)\n"
                "B) KEY POINTS (concise bullets)\n"
                "C) GLOSSARY CANDIDATES (term: short definition)\n\n"
                "PARTIAL NOTES:\n" + "\n\n---\n\n".join(partials)
            )
        else:
            reduce_user = (
                "Unisci le note qui sotto in:\n"
                "A) OUTLINE complessivo (max 3 livelli)\n"
                "B) KEY POINTS (bullet concisi)\n"
                "C) GLOSSARY CANDIDATES (termini: definizione breve)\n\n"
                "NOTE PARZIALI:\n" + "\n\n---\n\n".join(partials)
            )
        merged = self._llm(client, system, reduce_user)
        return merged

    def _count_words(self, s: str) -> int:
        return len(re.findall(r"\w+", s or ""))

    def _gen_summary(self, client: GroqClientLike, notes: str) -> str:
        output_language = "English" if self._is_english_ui() else "italiano"
        if self._is_english_ui():
            system = (
                "You are an academic assistant. "
                "Produce summaries in English, structured in Markdown."
            )
        else:
            system = (
                "Sei un assistente accademico. "
                "Produci riassunti in italiano, strutturati in Markdown."
            )
        notes_label = self._llm_notes_label()
        attempt = 0
        best = ""
        while attempt < 3:
            if self._is_english_ui():
                user = (
                    f"Using the {notes_label} below, write a **substantial** Markdown summary "
                    + (
                        f"between {TARGET_SUMMARY_WORDS_MIN}-{TARGET_SUMMARY_WORDS_MAX} words, "
                        "with headings (#, ##, ###), examples, and textual formulas. "
                    )
                    + f"Write in {output_language}.\n"
                    "Do not invent facts; if information is not in the notes, omit it.\n\n"
                    "At the end, add one HTML comment line with exact syntax:\n"
                    "<!-- WORDS: <number> -->\n\n"
                    + f"{notes_label}:\n" + notes
                )
            else:
                user = (
                    "In base alle NOTE COMPLETE qui sotto, scrivi un **riassunto corposo** in Markdown " +
                    (
                        f"tra {TARGET_SUMMARY_WORDS_MIN}-{TARGET_SUMMARY_WORDS_MAX} parole, "
                        "con titoli (#, ##, ###), esempi e formule testuali. "
                    ) +
                    "Non inventare; se un’informazione non è nelle note, omettila.\n\n"
                    "Al termine, aggiungi una riga HTML commentata con il conteggio parole con esatta sintassi:\n"
                    "<!-- WORDS: <numero> -->\n\n"
                    "NOTE COMPLETE:\n" + notes
                )
            md = self._llm(client, system, user)
            best = md or best
            m = re.search(r"<!--\s*WORDS:\s*(\d+)\s*-->",
                          md or "", re.IGNORECASE)
            wc = int(m.group(1)) if m else self._count_words(md)
            if wc >= TARGET_SUMMARY_WORDS_MIN:
                return md
            attempt += 1
            if self._is_english_ui():
                notes = notes + \
                    "\n\n[NOTE: expand coverage of examples, practical applications, and edge cases.]"
            else:
                notes = notes + \
                    "\n\n[NOTA: amplia copertura di esempi/applicazioni pratiche e casi limite.]"
        return best

    def _gen_list_with_count(self, client: GroqClientLike, notes: str, kind: str, n: int) -> list[StrDict]:
        """
        kind in {'questions','flashcards','glossary'}
        Restituisce lista di dict.
        """
        notes_label = self._llm_notes_label()
        if self._is_english_ui():
            system = "You are an academic assistant. Strictly follow the required JSON schema."
            schema_examples = {
                "questions": (
                    'Return **ONLY** JSON (array) in this form:\n'
                    '[{"q":"...", "a":"...", "difficulty":"easy|medium|hard"}, ...]\n'
                ),
                "flashcards": (
                    'Return **ONLY** JSON (array) in this form:\n'
                    '[{"front":"...", "back":"..."}, ...]\n'
                ),
                "glossary": (
                    'Return **ONLY** JSON (array) in this form:\n'
                    '[{"term":"...", "definition":"..."}, ...]\n'
                ),
            }
        else:
            system = "Sei un assistente accademico. Rispetta rigorosamente lo schema JSON richiesto."
            schema_examples = {
                "questions": (
                    'Restituisci **SOLO** JSON (lista) della forma:\n'
                    '[{"q":"...", "a":"...", "difficulty":"facile|medio|difficile"}, ...]\n'
                ),
                "flashcards": (
                    'Restituisci **SOLO** JSON (lista) della forma:\n'
                    '[{"front":"...", "back":"..."}, ...]\n'
                ),
                "glossary": (
                    'Restituisci **SOLO** JSON (lista) della forma:\n'
                    '[{"term":"...", "definition":"..."}, ...]\n'
                ),
            }

        def key_for(item: StrDict) -> tuple[str, ...]:
            if kind == "questions":
                return (item.get("q", "").strip().lower(), item.get("a", "").strip().lower())
            elif kind == "flashcards":
                return (
                    item.get("front", "").strip().lower(),
                    item.get("back", "").strip().lower()
                )
            else:
                return (item.get("term", "").strip().lower(),)

        collected: list[StrDict] = []
        seen: set[tuple[str, ...]] = set()
        guard = 0
        while len(collected) < n and guard < 4:
            remaining = n - len(collected)
            if self._is_english_ui():
                user = (
                    (
                        f"From the {notes_label} below, generate **exactly {remaining}** "
                        f"{kind} items. "
                    ) +
                    "Do not repeat concepts already used. Do not invent beyond the notes.\n\n"
                    + schema_examples[kind] +
                    f"\n{notes_label}:\n" + notes
                )
            else:
                user = (
                    (
                        f"In base alle NOTE COMPLETE qui sotto, genera **esattamente {remaining}** "
                        f"elementi di tipo {kind}. "
                    ) +
                    "Non ripetere concetti già usati. Non inventare oltre le note.\n\n"
                    + schema_examples[kind] +
                    "\nNOTE COMPLETE:\n" + notes
                )
            out = self._llm(client, system, user)

            arr: list[StrDict] | None = None
            try:
                parsed = json.loads(out)
                arr = self._to_str_dict_list(parsed)
            except Exception:
                extracted = self._extract_json(out)
                arr = self._to_str_dict_list(extracted)

            if arr:
                for item in arr:
                    k = key_for(item)
                    if not k:
                        continue
                    if k in seen:
                        continue
                    seen.add(k)
                    collected.append(item)
            guard += 1

        return collected[:n]

    # ------------------------- Utils -------------------------
    def _get_yview_command(self, widget: tk.Text) -> ScrollbarCommand:
        yview = getattr(widget, "yview", None)
        if not callable(yview):
            raise TypeError("Widget Tkinter senza metodo yview valido.")
        return cast(ScrollbarCommand, yview)

    def _load_audio_segment(self, path: str) -> AudioSegmentLike:
        from_file = getattr(AudioSegment, "from_file", None)
        if not callable(from_file):
            raise RuntimeError("pydub AudioSegment.from_file non disponibile.")
        segment = from_file(path)
        return cast(AudioSegmentLike, segment)

    def _to_any_dict_list(self, value: Any) -> list[AnyDict]:
        if not isinstance(value, list):
            return []
        result: list[AnyDict] = []
        for item in cast(list[Any], value):
            if isinstance(item, dict):
                result.append(cast(AnyDict, item))
        return result

    def _to_str_dict_list(self, value: Any) -> list[StrDict]:
        source = self._to_any_dict_list(value)
        return [{str(k): str(v) for k, v in item.items()} for item in source]

    def _extract_json(self, text: str) -> Any | None:
        if not text:
            return None
        # tentativo diretto
        try:
            return json.loads(text)
        except Exception:
            pass

        # blocco ```json ... ```
        m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass

        # fallback: prima { e ultima }
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end+1]
            try:
                return json.loads(candidate)
            except Exception:
                pass
        return None

    def _open_results(self, outs: dict[str, Any]):
        # Popola le tab con i contenuti
        def set_tab(name: str, value: Any):
            widget = self.sections.get(name)
            if widget is not None:
                widget.delete("1.0", tk.END)
                widget.insert("1.0", str(value or ""))

        set_tab("abstract", outs.get("abstract", ""))
        set_tab("summary_markdown", outs.get("summary_markdown", ""))

        # Outline formattato come lista
        outline_items: list[str] = []

        def fmt_outline(nodes: Any, level: int = 0):
            for node in self._to_any_dict_list(nodes):
                title = str(node.get("title", "")).strip()
                outline_items.append(
                    "  " * level + ("- " + title if title else "-"))
                fmt_outline(node.get("children", []), level+1)
        fmt_outline(outs.get("outline", []))
        set_tab("outline", "\n".join(outline_items))

        # Key points
        kp = outs.get("key_points", [])
        if isinstance(kp, list):
            set_tab("key_points", "\n".join(str(item)
                    for item in cast(list[Any], kp)))
        else:
            set_tab("key_points", str(kp))

        # Domande formattate
        qlines: list[str] = []
        for i, qa in enumerate(self._to_any_dict_list(outs.get("questions", [])), 1):
            q = str(qa.get("q", "")).strip()
            a = str(qa.get("a", "")).strip()
            d = str(qa.get("difficulty", "")).strip()
            qlines.append(
                f"{i:02d}) {q}\n   {self._t('answer_label')}: {a}\n   {self._t('difficulty_label')}: {d}\n")
        set_tab("questions", "\n".join(qlines))

        # Flashcard
        flines: list[str] = []
        for i, fc in enumerate(self._to_any_dict_list(outs.get("flashcards", [])), 1):
            flines.append(
                (
                    f"{i:02d}) FRONT: {str(fc.get('front', '')).strip()}\n"
                    f"    BACK: {str(fc.get('back', '')).strip()}\n"
                )
            )
        set_tab("flashcards", "\n".join(flines))

        # Glossario
        glines: list[str] = []
        for term in self._to_any_dict_list(outs.get("glossary", [])):
            glines.append(
                (
                    f"- {str(term.get('term', '')).strip()}: "
                    f"{str(term.get('definition', '')).strip()}"
                )
            )
        set_tab("glossary", "\n".join(glines))

    def _export_flashcards_csv(self):
        flashcard_widget = self.sections.get("flashcards")
        if flashcard_widget is None:
            messagebox.showinfo(self._t("dialog_title_no_cards"), self._t(
                "dialog_msg_flashcard_tab_missing"))
            return
        text = flashcard_widget.get("1.0", tk.END)
        # ricaviamo front/back con una regex semplice
        cards: list[dict[str, str]] = []
        current: dict[str, str] = {"front": "", "back": ""}
        for line in text.splitlines():
            if line.strip().startswith("FRONT:"):
                current = {"front": line.split(
                    "FRONT:", 1)[1].strip(), "back": ""}
            elif line.strip().startswith("BACK:"):
                current["back"] = line.split("BACK:", 1)[1].strip()
                if current.get("front"):
                    cards.append(current)
        if not cards:
            messagebox.showinfo(self._t("dialog_title_no_cards"), self._t(
                "dialog_msg_no_cards_export"))
            return
        path = filedialog.asksaveasfilename(title=self._t("file_dialog_export_csv"),
                                            defaultextension=".csv",
                                            filetypes=[(self._t("file_dialog_csv"), ".csv")],)
        if not path:
            return
        try:
            import csv
            with open(path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                # Formato Anki semplice: Front, Back
                writer.writerow(["Front", "Back"])
                for c in cards:
                    writer.writerow([c.get("front", ""), c.get("back", "")])
            messagebox.showinfo(self._t("dialog_title_exported"), self._t(
                "dialog_msg_saved_flashcards", path=path))
        except Exception as e:
            messagebox.showerror(self._t("dialog_title_error"), self._t(
                "dialog_msg_export_csv_error", error=e))

    # -------- Helpers vari --------
    def _safe_name(self, s: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "_", s).strip("_") or "output"

    def _copy_to_clip(self, s: str):
        try:
            self.clipboard_clear()
            self.clipboard_append(s)
            self.update()
        except Exception:
            pass

    def _save_string(self, s: str, default_name: str):
        path = filedialog.asksaveasfilename(title=self._t("file_dialog_save"), defaultextension=".txt",
                                            initialfile=default_name,
                                            filetypes=[(self._t("file_dialog_text"), ".txt"), (self._t("file_dialog_all"), "*.*")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(s)
            messagebox.showinfo(self._t("dialog_title_saved"), self._t(
                "dialog_msg_saved_file", path=path))

    # ------------------------- Aggiornamento UI (main thread) -------------------------
    def _process_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "append":
                    self.text_transc.insert(tk.END, payload)
                    self.text_transc.see(tk.END)
                elif kind == "progress":
                    self.progress['value'] = payload
                elif kind == "status":
                    self.status_var.set(str(payload))
                    try:
                        self.text_transc.insert(tk.END, self._t(
                            "status_tag", message=payload))
                        self.text_transc.see(tk.END)
                    except Exception:
                        pass
                elif kind == "error":
                    self.status_var.set(self._t("dialog_title_error"))
                    messagebox.showerror(
                        self._t("dialog_title_error"), str(payload))
                elif kind == "open_results":
                    self._open_results(payload)
                elif kind == "enable_llm":
                    self.btn_llm.config(state="normal")
                elif kind == "done":
                    self.btn_start.config(state="normal")
                    self.btn_cancel.config(state="disabled")
        except queue.Empty:
            pass
        finally:
            self.after(100, self._process_queue)


def main() -> None:
    app = LectureTranscriberApp()
    app.mainloop()


if __name__ == "__main__":
    main()
