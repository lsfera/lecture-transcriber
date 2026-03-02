import inspect
import os
from typing import Any

from faster_whisper import WhisperModel

from .config import HUGGINGFACE_API_KEY
from .provider_protocols import TranscriptionClientLike


class FasterWhisperTranscriptionClient:
    def __init__(self, model: WhisperModel):
        self._model = model

    def transcribe(
        self,
        audio: str | None = None,
        *,
        wav_path: str | None = None,
        model: str | None = None,
        lang: str = "auto",
        language: str | None = None,
        **kwargs: Any,
    ) -> str:
        del model

        audio_path = audio or wav_path
        if not audio_path:
            raise ValueError("audio (or wav_path) is required")

        effective_language = language
        if effective_language is None:
            effective_language = None if lang == "auto" else lang

        segments, _ = self._model.transcribe(
            audio_path,
            language=effective_language,
            **kwargs,
        )
        text_lines = [str(getattr(seg, "text", "")).strip()
                      for seg in segments]
        return " ".join(line for line in text_lines if line)


def create_faster_whisper_transcription_client(*, model_name: str, device: str, compute_type: str) -> TranscriptionClientLike:
    normalized_device = device.strip().lower()
    if normalized_device == "auto":
        normalized_device = "cpu"

    hf_token = HUGGINGFACE_API_KEY.strip()
    if hf_token:
        os.environ["HF_TOKEN"] = hf_token

    whisper_kwargs: dict[str, Any] = {
        "device": normalized_device,
        "compute_type": compute_type,
    }

    if hf_token:
        try:
            params = inspect.signature(WhisperModel).parameters
        except (TypeError, ValueError):
            params = {}

        if "token" in params:
            whisper_kwargs["token"] = hf_token
        elif "hf_token" in params:
            whisper_kwargs["hf_token"] = hf_token

    model = WhisperModel(model_name, **whisper_kwargs)
    return FasterWhisperTranscriptionClient(model)
