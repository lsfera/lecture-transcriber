from typing import cast

from pydub import AudioSegment as _AudioSegment  # type: ignore[import-untyped]

from .faster_whisper_provider import create_faster_whisper_transcription_client
from .groq_provider import GrokProvider
from .ollama_provider import OllamaProvider
from .provider_protocols import AudioSegmentFactory, LLMClientLike, TranscriptionClientLike

AudioSegment = cast(AudioSegmentFactory, _AudioSegment)


def _normalize_choice(value: str, valid: set[str], default: str) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in valid else default


def normalize_transcription_provider(value: str) -> str:
    return _normalize_choice(value, {"groq", "faster-whisper"}, "groq")


def normalize_llm_provider(value: str) -> str:
    return _normalize_choice(value, {"groq", "ollama"}, "groq")


def create_transcription_client_for_provider(
    *,
    provider: str,
    api_key: str,
    model_name: str,
    device: str,
    compute_type: str,
) -> TranscriptionClientLike:
    normalized_provider = normalize_transcription_provider(provider)
    if normalized_provider == "groq":
        if not api_key:
            raise RuntimeError("GROQ_API_KEY non impostata.")
        return GrokProvider().create_transcription_client(api_key=api_key)
    if normalized_provider == "faster-whisper":
        return create_faster_whisper_transcription_client(
            model_name=model_name,
            device=device,
            compute_type=compute_type,
        )
    raise RuntimeError(
        f"Provider trascrizione non supportato: {normalized_provider}")


def create_llm_client_for_provider(
    *,
    provider: str,
    api_key: str,
    model: str,
    temperature: float,
    max_tokens: int,
    host: str,
) -> LLMClientLike:
    normalized_provider = normalize_llm_provider(provider)
    if normalized_provider == "groq":
        if not api_key:
            raise RuntimeError("GROQ_API_KEY non impostata.")
        return GrokProvider().create_llm_client(
            api_key=api_key,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    if normalized_provider == "ollama":
        return OllamaProvider(host=host).create_llm_client(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    raise RuntimeError(f"Provider LLM non supportato: {normalized_provider}")
