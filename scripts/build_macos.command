#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-python3}"
BUILD_ENV=".venv-build"
VERSION="${MEDMASK_VERSION:-1.1.1}"

"$PYTHON_BIN" -m venv "$BUILD_ENV"
"$BUILD_ENV/bin/python" -m pip install --upgrade pip
"$BUILD_ENV/bin/python" -m pip install ".[build]"
"$BUILD_ENV/bin/pyinstaller" \
  --noconfirm \
  --clean \
  --windowed \
  --additional-hooks-dir hooks \
  --collect-data medmask \
  --name MedMask \
  --osx-bundle-identifier ru.medmask.local \
  main.py

plutil -replace CFBundleShortVersionString -string "$VERSION" dist/MedMask.app/Contents/Info.plist
codesign --force --deep --sign - dist/MedMask.app

echo
echo "Готово: dist/MedMask.app"
