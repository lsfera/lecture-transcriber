from typing import Any, cast

from groq import Groq

from .provider_protocols import GroqClientLike, LLMClientLike, TranscriptionClientLike


class GroqTranscriptionClient:
    def __init__(self, client: GroqClientLike):
        self._client = client

    def transcribe(
        self,
        audio: str | None = None,
        *,
        wav_path: str | None = None,
        model: str | None = None,
        lang: str = "auto",
        language: str | None = None,
    ) -> str:
        audio_path = audio or wav_path
        if not audio_path:
            raise ValueError("audio (or wav_path) is required")
        if not model:
            raise ValueError("model is required for Groq transcription")

        effective_language = language
        if effective_language is None:
            effective_language = None if lang == "auto" else lang

        with open(audio_path, "rb") as f:
            transcription_args: dict[str, Any] = {
                "file": f,
                "model": model,
                "temperature": 0.0,
            }
            if effective_language:
                transcription_args["language"] = effective_language
            transcription = self._client.audio.transcriptions.create(
                **transcription_args)
        return getattr(transcription, "text", None) or str(transcription)


class GroqLLMClient:
    def __init__(self, client: GroqClientLike, model: str, temperature: float, max_tokens: int):
        self._client = client
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    def complete(self, *, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        if not resp:
            raise RuntimeError("Risposta vuota da Groq API.")
        if not resp.choices:
            raise RuntimeError("Nessuna scelta nella risposta Groq.")
        return str(resp.choices[0].message.content).strip()


def create_groq_llm_client(*, api_key: str, model: str, temperature: float, max_tokens: int) -> LLMClientLike:
    groq_factory = cast(Any, Groq)
    return GroqLLMClient(
        groq_factory(api_key=api_key),
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def create_groq_transcription_client(*, api_key: str) -> TranscriptionClientLike:
    groq_factory = cast(Any, Groq)
    return GroqTranscriptionClient(groq_factory(api_key=api_key))


class GrokProvider:
    def create_llm_client(self, *, api_key: str, model: str, temperature: float, max_tokens: int) -> LLMClientLike:
        return create_groq_llm_client(
            api_key=api_key,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def create_transcription_client(self, *, api_key: str) -> TranscriptionClientLike:
        return create_groq_transcription_client(api_key=api_key)
