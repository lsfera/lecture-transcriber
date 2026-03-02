#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"

if command -v sudo >/dev/null 2>&1; then
	APT_PREFIX=(sudo)
else
	APT_PREFIX=()
fi

"${APT_PREFIX[@]}" apt-get update
"${APT_PREFIX[@]}" apt-get install -y ffmpeg

PYTHON_ABI_VERSION="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}{sys.version_info.minor}")')"
STDLIB_ZIP="/usr/local/lib/python${PYTHON_ABI_VERSION}.zip"
if [ ! -f "$STDLIB_ZIP" ]; then
	"${APT_PREFIX[@]}" "$PYTHON_BIN" - <<PY
from pathlib import Path
import zipfile

path = Path("$STDLIB_ZIP")
path.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(path, "w"):
	pass
print(f"Created {path}")
PY
fi

"$PYTHON_BIN" -m pip install --user --upgrade pip
"$PYTHON_BIN" -m pip install --user -e .
"$PYTHON_BIN" -m pip install --user debugpy

EGG_INFO_DIR="/workspace/src/lecture_transcriber.egg-info"
if [ -f "$EGG_INFO_DIR/PKG-INFO" ] && [ ! -f "$EGG_INFO_DIR/METADATA" ]; then
	cp "$EGG_INFO_DIR/PKG-INFO" "$EGG_INFO_DIR/METADATA"
fi
