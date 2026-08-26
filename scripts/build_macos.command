#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-python3}"
BUILD_ENV=".venv-build"

"$PYTHON_BIN" -m venv "$BUILD_ENV"
"$BUILD_ENV/bin/python" -m pip install --upgrade pip
"$BUILD_ENV/bin/python" -m pip install -c constraints.txt ".[build]"
"$BUILD_ENV/bin/python" scripts/test_all.py
"$BUILD_ENV/bin/pyinstaller" --noconfirm --clean MedMask.spec

codesign --force --deep --sign - dist/MedMask.app

"$BUILD_ENV/bin/python" scripts/smoke_test.py dist/MedMask.app/Contents/MacOS/MedMask

VERSION="$("$BUILD_ENV/bin/python" -c 'import medmask; print(medmask.__version__)')"
ARCHIVE="dist/MedMask-macOS-$VERSION.zip"
rm -f "$ARCHIVE"
ditto -c -k --sequesterRsrc --keepParent dist/MedMask.app "$ARCHIVE"

echo
echo "Готово: $ARCHIVE"
