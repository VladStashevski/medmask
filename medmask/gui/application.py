"""Сборка окна: приложение Qt, движок QML и объекты, видимые из QML."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QResource, Qt, QUrl
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface

from .. import __version__
from .controller import Controller
from .environment import Environment
from .window import WindowControls

QML_DIR = Path(__file__).resolve().parent / "qml"
ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "app_icon.png"

# Во время защищённой сборки этот модуль генерирует pyside6-rcc, а Nuitka
# компилирует его в основной исполняемый файл. В checkout его намеренно нет:
# разработчик продолжает редактировать и загружать обычные QML-файлы.
try:
    from . import _qml_resources as _QML_RESOURCES
except ImportError:
    _QML_RESOURCES = None


def _qml_source() -> tuple[str, QUrl]:
    if _QML_RESOURCES is not None:
        main_resource = ":/medmask/gui/qml/Main.qml"
        if not QResource(main_resource).isValid():
            raise RuntimeError("Встроенный интерфейс QML повреждён.")
        return "qrc:/medmask/gui/qml", QUrl("qrc:/medmask/gui/qml/Main.qml")
    return str(QML_DIR), QUrl.fromLocalFile(str(QML_DIR / "Main.qml"))


def configure_application(application: QGuiApplication) -> None:
    # macOS по умолчанию пускает Tab только по полям ввода, а их в окне нет:
    # без этой строки клавиша не делает ничего. Кнопок здесь три, обход по ним
    # короткий и предсказуемый.
    hints = application.styleHints()
    if hints is not None:
        hints.setTabFocusBehavior(Qt.TabFocusBehavior.TabFocusAllControls)
    application.setApplicationName("MedMask")
    application.setApplicationDisplayName("MedMask")
    application.setApplicationVersion(__version__)
    application.setOrganizationName("MedMask")
    application.setOrganizationDomain("medmask.local")
    if _QML_RESOURCES is not None:
        application.setWindowIcon(QIcon(":/medmask/assets/app_icon.png"))
    elif ICON_PATH.is_file():
        application.setWindowIcon(QIcon(str(ICON_PATH)))


def create_engine(
    application: QGuiApplication,
    controller: Controller | None = None,
) -> tuple[QQmlApplicationEngine, Controller]:
    # Объекты принадлежат движку, а не приложению: при выходе движок и его
    # объекты QML исчезают первыми, и привязки не успевают увидеть пустоту.
    engine = QQmlApplicationEngine(application)
    if controller is None:
        controller = Controller(engine)
    else:
        controller.setParent(engine)
    environment = Environment(engine)
    controls = WindowControls(environment, engine)

    import_path, main_url = _qml_source()
    engine.addImportPath(import_path)
    context = engine.rootContext()
    context.setContextProperty("controller", controller)
    context.setContextProperty("env", environment)
    context.setContextProperty("controls", controls)

    engine.load(main_url)
    if not engine.rootObjects():
        raise RuntimeError("Не удалось загрузить интерфейс QML.")

    window = engine.rootObjects()[0]
    controls.configure(window)
    if isinstance(window, QQuickWindow):
        _watch_renderer(window, environment)
    application.aboutToQuit.connect(controller.shutdown)
    return engine, controller


def _watch_renderer(window: QQuickWindow, environment: Environment) -> None:
    """Если сцену рисует процессор, стекло выключается: размытие на software
    рендерере не поддерживается, и панели остались бы пустыми."""

    def check() -> None:
        interface = window.rendererInterface()
        if interface is None:
            return
        software = interface.graphicsApi() in (
            QSGRendererInterface.GraphicsApi.Software,
            QSGRendererInterface.GraphicsApi.Unknown,
        )
        environment.note_renderer(software)

    window.sceneGraphInitialized.connect(check)
    check()


def main() -> None:
    # Дробные масштабы Windows (125 %, 150 %) без округления до целого:
    # иначе окно на 150 % получает шрифты от 200 % и разъезжается.
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    # Окно должно уметь быть прозрачным: под него кладется системное матовое
    # стекло. Слой альфы запрашивается до создания окна, позже уже поздно.
    QQuickWindow.setDefaultAlphaBuffer(True)
    # На прозрачном окне субпиксельное сглаживание дает цветную кайму у букв:
    # текст рисуется собственным движком Qt, серым сглаживанием.
    QQuickWindow.setTextRenderType(QQuickWindow.TextRenderType.QtTextRendering)

    application = QGuiApplication(sys.argv)
    configure_application(application)
    engine, controller = create_engine(application)
    controller.select_from_arguments()
    sys.exit(application.exec())
