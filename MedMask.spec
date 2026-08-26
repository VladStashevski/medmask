# -*- mode: python ; coding: utf-8 -*-
"""Единая спецификация сборки для Windows и macOS.

BUNDLE отрабатывает только в macOS, поэтому один и тот же файл даёт
dist/MedMask/MedMask.exe в Windows и dist/MedMask.app в macOS.
"""

import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

VERSION = re.search(
    r'__version__ = "([^"]+)"',
    Path("medmask/__init__.py").read_text(encoding="utf-8"),
).group(1)

# Модели OCR, шрифт и файлы интерфейса лежат внутри пакета и обязаны попасть
# в сборку: QML читается с диска и в собранном приложении тоже.
datas = collect_data_files(
    "medmask",
    includes=[
        "assets/*.onnx",
        "assets/*.ttf",
        "assets/app_icon.png",
        "assets/app_glyph.png",
        "gui/qml/*.qml",
        "gui/qml/MedMask/*.qml",
        "gui/qml/MedMask/qmldir",
    ],
)

# Модули Qt, которые вызывает только QML: анализатор их не видит в коде.
QT_HIDDEN = [
    "PySide6.QtQuick",
    "PySide6.QtQuickControls2",
    "PySide6.QtQml",
    "PySide6.QtOpenGL",
    "PySide6.QtNetwork",
]

# Остальной Qt в приложении не участвует. Без этого списка в сборку уезжают
# браузерный движок, 3D и мультимедиа — сотни мегабайт мертвого груза.
QT_UNUSED = [
    "PySide6.Qt3DAnimation", "PySide6.Qt3DCore", "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DRender",
    "PySide6.QtBluetooth", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtDesigner", "PySide6.QtGraphs", "PySide6.QtGraphsWidgets",
    "PySide6.QtHelp", "PySide6.QtHttpServer", "PySide6.QtLocation",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtNfc",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtPositioning",
    "PySide6.QtQuick3D", "PySide6.QtRemoteObjects", "PySide6.QtScxml",
    "PySide6.QtSensors", "PySide6.QtSerialBus", "PySide6.QtSerialPort",
    "PySide6.QtSpatialAudio", "PySide6.QtSql", "PySide6.QtStateMachine",
    "PySide6.QtTest", "PySide6.QtTextToSpeech", "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets", "PySide6.QtWebSockets", "PySide6.QtWebView",
]
ICON_DIR = Path("medmask/assets")
EXE_ICON = ICON_DIR / ("app_icon.icns" if sys.platform == "darwin" else "app_icon.ico")


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=QT_HIDDEN,
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=QT_UNUSED,
    noarchive=False,
    optimize=1,
)
# excludes отсекает только модули Python. Библиотеки Qt приходят как
# зависимости и остаются в сборке: один QtWebEngineCore — это 217 МБ, которые
# приложение никогда не открывает. Их убирает уже собранный список файлов.
QT_DROP = (
    "webengine", "webview", "webchannel", "websockets",
    "quick3d", "qt3d",
    "multimedia", "spatialaudio", "texttospeech",
    "qtcharts", "datavisualization", "qtgraphs",
    "qtsensors", "qtpositioning", "qtlocation", "qtbluetooth", "qtnfc",
    "qtserialport", "qtserialbus", "qtremoteobjects", "qtscxml",
    "qtsql", "sqldrivers",
    "qttest", "qtdesigner", "qthelp", "qthttpserver",
    "qtpdf",
)


def _is_unused_qt(name):
    # Windows называет библиотеки Qt6Foo, macOS — QtFoo: сравниваем одинаково.
    probe = str(name).lower().replace("\\", "/").replace("qt6", "qt")
    return any(mark in probe for mark in QT_DROP)


a.binaries = [entry for entry in a.binaries if not _is_unused_qt(entry[0])]
a.datas = [entry for entry in a.datas if not _is_unused_qt(entry[0])]

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
    icon=str(EXE_ICON),
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
    icon=str(ICON_DIR / 'app_icon.icns'),
    bundle_identifier='ru.medmask.local',
    version=VERSION,
    info_plist={
        'CFBundleShortVersionString': VERSION,
        'CFBundleVersion': VERSION,
        'NSHighResolutionCapable': True,
        'LSApplicationCategoryType': 'public.app-category.medical',
    },
)
