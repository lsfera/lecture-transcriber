from typing import cast

from ollama import Client as OllamaClient

from .provider_protocols import LLMClientLike, OllamaChatResponseLike, OllamaClientLike


class OllamaLLMClient:
    def __init__(self, client: OllamaClientLike, host: str, model: str, temperature: float, max_tokens: int):
        self._client = client
        self._host = host
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    def complete(self, *, system: str, user: str) -> str:
        try:
            parsed: OllamaChatResponseLike = self._client.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                options={
                    "temperature": self._temperature,
                    "num_predict": self._max_tokens,
                },
            )
        except Exception as exc:
            raise RuntimeError(
                f"Impossibile contattare Ollama su {self._host}. "
                f"Avvia il server Ollama e verifica OLLAMA_BASE_URL. Dettaglio: {exc}"
            ) from exc

        content_str = str(parsed.message.content).strip()
        if not content_str:
            message_any = parsed.message
            message_type = type(message_any).__name__
            raise RuntimeError(
                f"Risposta Ollama vuota o non valida. message_type={message_type}")
        return content_str


class OllamaProvider:
    def __init__(self, *, host: str):
        self._host = host

    def create_llm_client(self, *, model: str, temperature: float, max_tokens: int) -> LLMClientLike:
        return OllamaLLMClient(
            cast(OllamaClientLike, OllamaClient(host=self._host)),
            host=self._host,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
