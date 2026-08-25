# -*- mode: python ; coding: utf-8 -*-
"""Единая спецификация сборки для Windows и macOS.

BUNDLE отрабатывает только в macOS, поэтому один и тот же файл даёт
dist/MedMask/MedMask.exe в Windows и dist/MedMask.app в macOS.
"""

import re
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

VERSION = re.search(
    r'__version__ = "([^"]+)"',
    Path("medmask/__init__.py").read_text(encoding="utf-8"),
).group(1)

# Модели OCR и шрифт лежат в medmask/assets и обязаны попасть в сборку.
datas = collect_data_files("medmask")


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MedMask',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    # Окно с трейсбеком в оконной сборке ждёт нажатия кнопки: на сервере
    # сборки его некому закрыть, и процесс висит до таймаута.
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MedMask',
)
app = BUNDLE(
    coll,
    name='MedMask.app',
    icon=None,
    bundle_identifier='ru.medmask.local',
    version=VERSION,
    info_plist={
        'CFBundleShortVersionString': VERSION,
        'CFBundleVersion': VERSION,
        'NSHighResolutionCapable': True,
        'LSApplicationCategoryType': 'public.app-category.medical',
    },
)
