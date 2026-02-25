# Lecture Transcriber

Python project structured with a `src/` package layout.

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



## Run with Pipenv

```bash
pipenv install
pipenv run start
```

## Pipenv development commands

```bash
# Open subshell in virtualenv
pipenv shell

# Recreate lock file after dependency changes
pipenv lock

# Install exactly from lock file
pipenv sync

# Reinstall environment from scratch
pipenv --rm && pipenv install
```

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
- `lecture-transcriber-<tag>-macos-amd64.tar.gz`
- `lecture-transcriber-<tag>-macos-arm64.tar.gz`

Download from: `https://github.com/lsfera/lecture-transcriber/releases`

### Passing configuration variables to executables

The packaged app reads configuration from environment variables:

- `GROQ_API_KEY` (required): API key used for transcription and LLM generation
- `UI_LANG` (optional): `it` (default) or `en`

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