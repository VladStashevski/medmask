#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-python3}"
BUILD_ENV=".venv-build"

"$PYTHON_BIN" -m venv "$BUILD_ENV"
"$BUILD_ENV/bin/python" -m pip install --upgrade pip
"$BUILD_ENV/bin/python" -m pip install ".[build]"
"$BUILD_ENV/bin/pyinstaller" \
  --noconfirm \
  --clean \
  --windowed \
  --name MedMask \
  --osx-bundle-identifier ru.medmask.local \
  main.py

echo
echo "Готово: dist/MedMask.app"
