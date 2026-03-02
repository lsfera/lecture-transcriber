import json
import os
import re
import shutil
import sys
from typing import Any, cast

from .fp_core import (
    academic_system_prompt,
    build_list_prompt,
    build_map_chunk_prompt,
    build_reduce_prompt,
    build_summary_prompt,
    count_words,
    debug_preview,
    extract_json_candidate,
    list_schema_examples,
    list_system_prompt,
    notes_label,
    normalize_current_language,
    split_text_chunks,
    summary_retry_note,
    summary_system_prompt,
    to_str_dict_list,
)

from .config import (
    CHUNK_CHARLEN,
    FASTER_WHISPER_COMPUTE_TYPE,
    FASTER_WHISPER_DEVICE,
    GROQ_API_KEY,
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_TEMP,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
)
from .providers import (
    AudioSegment,
    LLMClientLike,
    TranscriptionClientLike,
    create_llm_client_for_provider,
    create_transcription_client_for_provider,
    normalize_llm_provider,
    normalize_transcription_provider,
)
from .translations import TRANSLATIONS


class ProcessingMixin:
    status_var: Any
    transcription_provider_var: Any
    llm_provider_var: Any
    ui_lang: str

    def _t(self, key: str, **kwargs: Any) -> str:
        language_map = TRANSLATIONS.get(
            getattr(self, "ui_lang", "it"), TRANSLATIONS["it"])
        template = language_map.get(key, TRANSLATIONS["it"].get(key, key))
        try:
            return template.format(**kwargs)
        except Exception:
            return template

    def _normalize_transcription_provider(self, value: str) -> str:
        return normalize_transcription_provider(value)

    def _normalize_llm_provider(self, value: str) -> str:
        return normalize_llm_provider(value)

    def _on_transcription_provider_change(self, _event: Any = None) -> None:
        self.transcription_provider_var.set(
            self._normalize_transcription_provider(
                self.transcription_provider_var.get())
        )
        self._update_provider_env_hint()

    def _on_llm_provider_change(self, _event: Any = None) -> None:
        self.llm_provider_var.set(
            self._normalize_llm_provider(self.llm_provider_var.get())
        )
        self._update_provider_env_hint()

    def _update_provider_env_hint(self) -> None:
        missing: list[str] = []
        requires_groq = (
            self._transcription_provider() == "groq"
            or self._llm_provider() == "groq"
        )
        if requires_groq and not GROQ_API_KEY:
            missing.append("GROQ_API_KEY")

        if missing:
            self.status_var.set(
                self._t("status_missing_env", vars=", ".join(missing)))
            return

        missing_values = {
            v.get("status_missing_env", "").format(vars="GROQ_API_KEY")
            for v in TRANSLATIONS.values()
        }
        if self.status_var.get() in missing_values:
            self.status_var.set(self._t("status_ready"))

    def _transcription_provider(self) -> str:
        return self._normalize_transcription_provider(self.transcription_provider_var.get())

    def _create_transcription_client(self, api_key: str, model_name: str) -> TranscriptionClientLike:
        return create_transcription_client_for_provider(
            provider=self._transcription_provider(),
            api_key=api_key,
            model_name=model_name,
            device=FASTER_WHISPER_DEVICE,
            compute_type=FASTER_WHISPER_COMPUTE_TYPE,
        )

    def _transcribe_audio_chunk(self, client: Any, wav_path: str, model: str, lang: str) -> str:
        transcription_client = cast(TranscriptionClientLike, client)
        return transcription_client.transcribe(wav_path=wav_path, model=model, lang=lang)

    def _llm_provider(self) -> str:
        return self._normalize_llm_provider(self.llm_provider_var.get())

    def _create_llm_client(self, api_key: str) -> Any:
        provider = self._llm_provider()
        model = OLLAMA_MODEL if provider == "ollama" else LLM_MODEL
        return create_llm_client_for_provider(
            provider=provider,
            api_key=api_key,
            model=model,
            temperature=LLM_TEMP,
            max_tokens=LLM_MAX_TOKENS,
            host=OLLAMA_BASE_URL,
        )

    def _llm(self, client: Any, system: str, user: str) -> str:
        llm_client = cast(LLMClientLike, client)
        return llm_client.complete(system=system, user=user)

    def _current_language(self) -> str:
        return normalize_current_language(self.ui_lang)

    def _llm_notes_label(self) -> str:
        return notes_label(self._current_language())

    def _llm_academic_system_prompt(self) -> str:
        return academic_system_prompt(self._current_language())

    def _map_reduce_notes(self, client: Any, transcript_text: str) -> str:
        system = self._llm_academic_system_prompt()
        chunks = split_text_chunks(transcript_text, CHUNK_CHARLEN)

        partials: list[str] = []
        current_language = self._current_language()
        for idx, ch in enumerate(chunks, 1):
            user = build_map_chunk_prompt(
                current_language=current_language,
                idx=idx,
                total=len(chunks),
                chunk_text=ch,
            )
            out = self._llm(client, system, user)
            partials.append(out)

        reduce_user = build_reduce_prompt(
            current_language=current_language, partials=partials)
        merged = self._llm(client, system, reduce_user)
        return merged

    def _gen_summary(self, client: Any, notes: str) -> str:
        from .config import TARGET_SUMMARY_WORDS_MIN, TARGET_SUMMARY_WORDS_MAX

        current_language = self._current_language()
        system = summary_system_prompt(current_language)
        notes_label = self._llm_notes_label()
        attempt = 0
        best = ""
        while attempt < 3:
            user = build_summary_prompt(
                current_language=current_language,
                notes=notes,
                notes_label_value=notes_label,
                target_min=TARGET_SUMMARY_WORDS_MIN,
                target_max=TARGET_SUMMARY_WORDS_MAX,
            )
            md = self._llm(client, system, user)
            best = md or best
            m = re.search(r"<!--\s*WORDS:\s*(\d+)\s*-->",
                          md or "", re.IGNORECASE)
            wc = int(m.group(1)) if m else count_words(md)
            if wc >= TARGET_SUMMARY_WORDS_MIN:
                return md
            attempt += 1
            notes = notes + summary_retry_note(current_language)
        return best

    def _gen_list_with_count(self, client: Any, notes: str, kind: str, n: int) -> list[dict[str, str]]:
        notes_label = self._llm_notes_label()
        current_language = self._current_language()
        system = list_system_prompt(current_language)
        schema_examples = list_schema_examples(current_language)

        def key_for(item: dict[str, str]) -> tuple[str, ...]:
            if kind == "questions":
                q = item.get("q") or ""
                a = item.get("a") or ""
                return (str(q).strip().lower(), str(a).strip().lower())
            elif kind == "flashcards":
                front = item.get("front") or ""
                back = item.get("back") or ""
                return (
                    str(front).strip().lower(),
                    str(back).strip().lower()
                )
            else:
                term = item.get("term") or ""
                return (str(term).strip().lower(),)

        collected: list[dict[str, str]] = []
        seen: set[tuple[str, ...]] = set()
        guard = 0
        while len(collected) < n and guard < 4:
            remaining = n - len(collected)
            user = build_list_prompt(
                current_language=current_language,
                notes=notes,
                notes_label_value=notes_label,
                kind=kind,
                remaining=remaining,
                schema_example=schema_examples[kind],
            )
            out = self._llm(client, system, user)

            arr: list[dict[str, str]] | None = None
            try:
                parsed = json.loads(out)
                arr = to_str_dict_list(parsed)
            except Exception:
                extracted = extract_json_candidate(out)
                arr = to_str_dict_list(extracted)

            if not arr:
                preview = debug_preview(out)
                queue_obj = getattr(self, "msg_queue", None)
                if queue_obj is not None and hasattr(queue_obj, "put"):
                    status_msg = (
                        f"LLM debug ({kind}): JSON parse failed. Preview: {preview}"
                        if current_language == "en"
                        else f"LLM debug ({kind}): parsing JSON fallito. Anteprima: {preview}"
                    )
                    queue_obj.put(("status", status_msg))

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

    def _resolve_ffmpeg_binary(self) -> str:
        env_binary = os.getenv("FFMPEG_BINARY", "").strip()
        if env_binary:
            return env_binary

        candidates: list[str] = []
        if getattr(sys, "frozen", False):
            bundle_dir = getattr(sys, "_MEIPASS", "")
            exec_dir = os.path.dirname(sys.executable)
            if bundle_dir:
                candidates.extend([
                    os.path.join(bundle_dir, "ffmpeg"),
                    os.path.join(bundle_dir, "ffmpeg.exe"),
                ])
            candidates.extend([
                os.path.join(exec_dir, "ffmpeg"),
                os.path.join(exec_dir, "ffmpeg.exe"),
            ])

        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                return candidate

        found = shutil.which("ffmpeg") or shutil.which("avconv")
        if found:
            return found

        raise RuntimeError(
            "FFmpeg non trovato. Installa ffmpeg (o avconv) e assicurati che sia nel PATH, "
            "oppure imposta la variabile FFMPEG_BINARY con il percorso completo dell'eseguibile."
        )

    def _configure_audio_binaries(self) -> None:
        ffmpeg_binary = self._resolve_ffmpeg_binary()
        setattr(AudioSegment, "converter", ffmpeg_binary)
        setattr(AudioSegment, "ffmpeg", ffmpeg_binary)
        ffprobe_binary = shutil.which("ffprobe") or shutil.which("avprobe")
        if ffprobe_binary:
            setattr(AudioSegment, "ffprobe", ffprobe_binary)

    def _load_audio_segment(self, path: str) -> Any:
        self._configure_audio_binaries()
        from_file = getattr(AudioSegment, "from_file", None)
        if not callable(from_file):
            raise RuntimeError("pydub AudioSegment.from_file non disponibile.")
        return from_file(path)
