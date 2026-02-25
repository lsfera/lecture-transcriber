# syntax=docker/dockerfile:1.7

FROM python:3.11-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY pyproject.toml README.md ./
COPY src ./src

RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip build \
    && python -m build --wheel --outdir /artifacts


FROM python:3.11-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg tk\
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /artifacts /artifacts

RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip \
    && python -m pip install /artifacts/*.whl

CMD ["lecture-transcriber"]