# Lecture Transcriber

This software was originally shared by [specchioinfranto](https://youtu.be/No0DJwVNEtE?t=226).

It's a Tkinter app for lecture transcription and study materials generation (using Grok and|or faster whisperer + Ollama).

## Run locally

```bash
pip install -e .
lecture-transcriber
```

Alternative module execution:

```bash
python -m lecture_transcriber
```

Legacy entrypoint is still available at `project/main.py`.

## Docker image publishing

This repository includes a multi-stage `Dockerfile` that builds wheel artifacts and installs the app from those artifacts in the runtime image.

Local build with explicit tag:

```bash
make docker-build
# or override the tag
make docker-build IMAGE=lecture-transcriber:dev
```
Run local container (from built image):
```bash
make docker-run
```

GitHub Actions workflow: `.github/workflows/docker-publish.yml`

- Publishes on push to `main`
- Publishes on version tags matching `v*.*.*`
- Supports manual runs via `workflow_dispatch`

## Desktop binaries (PyInstaller)

GitHub Actions workflow: `.github/workflows/pyinstaller-publish.yml`

When a new release is created (tag `v*.*.*`), prebuilt binaries are attached to the GitHub Release assets.

Artifact naming format:

- `lecture-transcriber-<tag>-linux-amd64.tar.gz`
- `lecture-transcriber-<tag>-windows-amd64.zip`
- `lecture-transcriber-<tag>-macos-arm64.tar.gz`

Download from: `[releases](./releases)`

### Passing configuration variables to executables

The packaged app reads configuration from environment variables:

- `GROQ_API_KEY` (required only when a selected provider is `groq`): API key used for Groq transcription and/or Groq LLM generation
- `UI_LANG` (optional): `it` (default) or `en`
- `AUDIO_INITIAL_DIR` (optional): initial folder for the audio file picker; if unset, the app uses the user home/profile directory
- `FFMPEG_BINARY` (optional): override path to `ffmpeg` executable (release bundles already include `ffmpeg`)
- `TRANSCRIPTION_PROVIDER` (optional): `groq` (default) or `faster-whisper`
- `WHISPER_MODEL` (optional): Groq Whisper model for transcription when `TRANSCRIPTION_PROVIDER=groq` (default `whisper-large-v3-turbo`)
- `FASTER_WHISPER_MODEL` (optional): local model name for faster-whisper (default `small`)
- `HUGGINGFACE_API_KEY` (optional): Hugging Face access token used to download gated/private faster-whisper models
- `FASTER_WHISPER_DEVICE` (optional): `cpu`, `cuda`, or `auto` (default `auto`)
- `FASTER_WHISPER_COMPUTE_TYPE` (optional): faster-whisper compute type (default `int8`)
- `LLM_PROVIDER` (optional): `groq` (default) or `ollama` for local LLM post-processing
- `LLM_MODEL` (optional): Groq model name when `LLM_PROVIDER=groq`
- `OLLAMA_BASE_URL` (optional): Ollama endpoint (default `http://127.0.0.1:11434`)
- `OLLAMA_MODEL` (optional): Ollama model name (default `llama3.2:3b`)

In the GUI, the transcription model dropdown is provider-dependent:

- `groq` → Groq Whisper models (`whisper-large-v3-turbo`, `whisper-large-v3`)
- `faster-whisper` → local faster-whisper models (`tiny`, `base`, `small`, `medium`, `large-v2`, `large-v3`, `distil-large-v3`)

Fully local mode (no Groq for transcription or LLM):

```bash
ollama serve
ollama pull llama3.2:3b
TRANSCRIPTION_PROVIDER=faster-whisper \
LLM_PROVIDER=ollama \
FASTER_WHISPER_MODEL=small \
OLLAMA_MODEL=llama3.2:3b \
./lecture-transcriber
```

Use local Ollama for LLM post-processing (no Groq key required for summaries/flashcards):

```bash
OLLAMA_BASE_URL=http://127.0.0.1:11434 ollama serve
OLLAMA_MODEL=llama3.2:3b ollama pull llama3.2:3b
LLM_PROVIDER=ollama UI_LANG=en ./lecture-transcriber
```

Linux/macOS (single run):

```bash
GROQ_API_KEY=<your_key> UI_LANG=en ./lecture-transcriber
```

Linux/macOS (current shell session):

```bash
export GROQ_API_KEY=<your_key>
export UI_LANG=en
./lecture-transcriber
```

Windows PowerShell:

```powershell
$env:GROQ_API_KEY="<your_key>"
$env:UI_LANG="en"
.\lecture-transcriber.exe
```

Windows CMD:

```bat
set GROQ_API_KEY=<your_key>
set UI_LANG=en
lecture-transcriber.exe
```

Persist variables on Windows for future sessions:

```powershell
setx GROQ_API_KEY "<your_key>"
setx UI_LANG "en"
```

Published image names:

- GHCR: `ghcr.io/lsfera/lecture-transcriber`

Generated tags include:

- branch name
- git tag (for tagged releases)
- commit SHA
- `latest` (default branch only)

Pull and run examples:

For GUI/X11 use, set your X11 host first (example shown with `IP`) and pass `DISPLAY`, the X11 socket, and an `/input` mount:

```bash
export IP=$(/usr/sbin/ipconfig getifaddr en0)
```

or use

```bash
export IP="host.docker.internal"
```


```bash
# GHCR
docker pull ghcr.io/<owner>/<repo>:latest
docker run --rm \
	-e GROQ_API_KEY=<your_key> \
	-e DISPLAY=$IP:0 \
	-v /tmp/.X11-unix:/tmp/.X11-unix:rw \
	-v "$(pwd)/input":/input:cached \
	ghcr.io/<owner>/<repo>:latest

# Pinned release tag (recommended for reproducibility)
docker pull ghcr.io/<owner>/<repo>:v1.2.3
docker run --rm \
	-e GROQ_API_KEY=<your_key> \
	-e DISPLAY=$IP:0 \
	-v /tmp/.X11-unix:/tmp/.X11-unix:rw \
	-v "$(pwd)/input":/input:cached \
	ghcr.io/<owner>/<repo>:v1.2.3
```

If the GUI cannot open on Linux hosts, allow local Docker clients to access your X server before running the container:

```bash
xhost +local:docker
```

When finished, revoke access:

```bash
xhost -local:docker
```

Wayland note: if `DISPLAY` is unset, launch an XWayland/X11 session (or set `DISPLAY` to your active XWayland display) before running the Docker commands above.

## GUI localization

The app supports localized GUI text and localized LLM output.

- `UI_LANG=it` (default): Italian UI and Italian LLM-generated content
- `UI_LANG=en`: English UI and English LLM-generated content

Run examples:

```bash
# Italian (default)
UI_LANG=it lecture-transcriber

# English
UI_LANG=en lecture-transcriber
```

In Docker, pass it as an environment variable:

```bash
docker run --rm \
	-e GROQ_API_KEY=<your_key> \
	-e UI_LANG=en \
	-e DISPLAY=$IP:0 \
	-v /tmp/.X11-unix:/tmp/.X11-unix:rw \
	-v "$(pwd)/input":/input:cached \
	ghcr.io/<owner>/<repo>:latest
```