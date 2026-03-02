from typing import Any, Protocol


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


class TranscriptionClientLike(Protocol):
    def transcribe(
        self,
        audio: str | None = None,
        *,
        wav_path: str | None = None,
        model: str | None = None,
        lang: str = "auto",
        language: str | None = None,
    ) -> str: ...


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


class OllamaClientLike(Protocol):
    def chat(self, **kwargs: Any) -> "OllamaChatResponseLike": ...


class OllamaMessageLike(Protocol):
    content: str


class OllamaChatResponseLike(Protocol):
    message: OllamaMessageLike


class OllamaClientFactory(Protocol):
    def __call__(self, *, host: str | None = None, **
                 kwargs: Any) -> OllamaClientLike: ...


class LLMClientLike(Protocol):
    def complete(self, *, system: str, user: str) -> str: ...
