"""Тонкая обертка над Objective-C для окна macOS.

Нужна ровно для трех вещей: убрать серую системную полосу, пустить содержимое
под нее и спросить у системы настройки доступности. Все вызовы завернуты в
try/except: если что-то не сработает, окно останется обычным системным.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import sys

NS_WINDOW_STYLE_MASK_FULL_SIZE_CONTENT_VIEW = 1 << 15
NS_WINDOW_TITLE_HIDDEN = 1

# NSVisualEffectView: матовое стекло, сквозь которое видно рабочий стол.
# Размытие делает система, поэтому оно такое же, как у окон самой macOS.
# Материалы отличаются плотностью: чем ниже в списке, тем меньше видно фон.
NS_MATERIALS = {
    "menu": 5,
    "popover": 6,
    "sidebar": 7,
    "header": 10,
    "window": 12,
    "content": 18,
    "under": 21,
}
NS_BLENDING_BEHIND_WINDOW = 0
NS_EFFECT_STATE_ACTIVE = 1
NS_VIEW_WIDTH_SIZABLE = 2
NS_VIEW_HEIGHT_SIZABLE = 16
NS_WINDOW_BELOW = -1


class NSRect(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_double),
        ("y", ctypes.c_double),
        ("width", ctypes.c_double),
        ("height", ctypes.c_double),
    ]

_library = None


def _objc():
    global _library
    if _library is None:
        path = ctypes.util.find_library("objc")
        if path is None:
            raise OSError("libobjc не найдена")
        library = ctypes.cdll.LoadLibrary(path)
        library.objc_getClass.restype = ctypes.c_void_p
        library.objc_getClass.argtypes = [ctypes.c_char_p]
        library.sel_registerName.restype = ctypes.c_void_p
        library.sel_registerName.argtypes = [ctypes.c_char_p]
        _library = library
    return _library


def _selector(name: str) -> ctypes.c_void_p:
    return ctypes.c_void_p(_objc().sel_registerName(name.encode()))


def _class(name: str) -> ctypes.c_void_p:
    return ctypes.c_void_p(_objc().objc_getClass(name.encode()))


def _send(restype, argtypes, receiver, selector: str, *args):
    """objc_msgSend с явными типами.

    Без argtypes ctypes передает аргументы по умолчанию, и на arm64 BOOL или
    NSUInteger уезжают в соседний регистр — окно тихо получает мусор.
    """
    prototype = ctypes.CFUNCTYPE(restype, ctypes.c_void_p, ctypes.c_void_p, *argtypes)
    call = ctypes.cast(_objc().objc_msgSend, prototype)
    return call(receiver, _selector(selector), *args)


def available() -> bool:
    return sys.platform == "darwin"


def _nsstring(text: str) -> ctypes.c_void_p:
    return ctypes.c_void_p(
        _send(
            ctypes.c_void_p,
            [ctypes.c_char_p],
            _class("NSString"),
            "stringWithUTF8String:",
            text.encode(),
        )
    )


def _ns_window(window) -> ctypes.c_void_p | None:
    """NSWindow за окном Qt, если оно уже создано системой."""
    handle = int(window.winId())
    if not handle:
        return None
    ns_window = _send(ctypes.c_void_p, [], ctypes.c_void_p(handle), "window")
    return ctypes.c_void_p(ns_window) if ns_window else None


def style_window(window, glass: bool = True) -> bool:
    """Приводит окно к виду программы: своя шапка, светлый вид, прозрачность."""
    if not (make_titlebar_transparent(window) and force_light_appearance(window)):
        return False
    if glass:
        make_translucent(window)
        # Системное матовое стекло размывает фон так сильно, что обои
        # превращаются в ровное пятно. По умолчанию его нет: окно просто
        # полупрозрачное, и рабочий стол виден как есть. Кому нужен матовый
        # вариант — включается переменной с именем материала.
        material = os.environ.get("MEDMASK_GLASS_MATERIAL", "").strip().lower()
        if material in NS_MATERIALS:
            install_glass_backdrop(window, NS_MATERIALS[material])
    return True


def make_translucent(window) -> bool:
    """Снимает у окна непрозрачность, чтобы сквозь него был виден стол."""
    if not available():
        return False
    try:
        ns_window = _ns_window(window)
        if ns_window is None:
            return False
        _send(None, [ctypes.c_bool], ns_window, "setOpaque:", False)
        clear = _send(ctypes.c_void_p, [], _class("NSColor"), "clearColor")
        if clear:
            _send(
                None,
                [ctypes.c_void_p],
                ns_window,
                "setBackgroundColor:",
                ctypes.c_void_p(clear),
            )
        return True
    except Exception:
        return False


def install_glass_backdrop(window, material: int) -> bool:
    """Кладет под содержимое системное матовое стекло.

    Размытие рабочего стола умеет только система, поэтому фоном окна
    становится NSVisualEffectView, а само окно — прозрачным. Панели после
    этого не нуждаются в белой подложке: под ними настоящее стекло.

    Вид добавляется соседом под содержимое Qt, а не оборачивает его. Обертка
    ломает изменение размера: Qt продолжает менять размер своего вида, а
    внешний остается прежним, и окно перестает обновляться.

    Повторный вызов ничего не делает: вид ставится один раз и живет с окном.
    """
    if not available():
        return False
    try:
        ns_window = _ns_window(window)
        if ns_window is None:
            return False
        handle = int(window.winId())
        if not handle:
            return False
        qt_view = ctypes.c_void_p(handle)
        parent = _send(ctypes.c_void_p, [], qt_view, "superview")
        if not parent:
            return False
        parent = ctypes.c_void_p(parent)

        if _find_backdrop(parent) is not None:
            return True

        effect = _send(ctypes.c_void_p, [], _class("NSVisualEffectView"), "alloc")
        if not effect:
            return False
        effect = ctypes.c_void_p(_send(ctypes.c_void_p, [], ctypes.c_void_p(effect), "init"))
        _send(None, [ctypes.c_long], effect, "setMaterial:", ctypes.c_long(material))
        _send(
            None,
            [ctypes.c_long],
            effect,
            "setBlendingMode:",
            ctypes.c_long(NS_BLENDING_BEHIND_WINDOW),
        )
        _send(None, [ctypes.c_long], effect, "setState:", ctypes.c_long(NS_EFFECT_STATE_ACTIVE))
        bounds = _send(NSRect, [], parent, "bounds")
        _send(None, [NSRect], effect, "setFrame:", bounds)
        _send(
            None,
            [ctypes.c_ulong],
            effect,
            "setAutoresizingMask:",
            ctypes.c_ulong(NS_VIEW_WIDTH_SIZABLE | NS_VIEW_HEIGHT_SIZABLE),
        )
        _send(
            None,
            [ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p],
            parent,
            "addSubview:positioned:relativeTo:",
            effect,
            ctypes.c_long(NS_WINDOW_BELOW),
            qt_view,
        )

        return True
    except Exception:
        return False


def _find_backdrop(parent) -> ctypes.c_void_p | None:
    """Ищет уже поставленное стекло среди соседей содержимого."""
    subviews = _send(ctypes.c_void_p, [], parent, "subviews")
    if not subviews:
        return None
    subviews = ctypes.c_void_p(subviews)
    count = _send(ctypes.c_ulong, [], subviews, "count")
    for index in range(count):
        view = _send(
            ctypes.c_void_p, [ctypes.c_ulong], subviews, "objectAtIndex:", ctypes.c_ulong(index)
        )
        if not view:
            continue
        view = ctypes.c_void_p(view)
        name = _send(ctypes.c_void_p, [], view, "className")
        if name and _to_text(name) == "NSVisualEffectView":
            return view
    return None


def _to_text(ns_string) -> str:
    raw = _send(ctypes.c_char_p, [], ctypes.c_void_p(ns_string), "UTF8String")
    return raw.decode() if raw else ""


def force_light_appearance(window) -> bool:
    """Держит светлое оформление, даже когда система в темной теме.

    Тема у программы одна, и системный светофор с меню тоже должен быть
    светлым: иначе шапка окна спорит с его содержимым.
    """
    if not available():
        return False
    try:
        ns_window = _ns_window(window)
        if ns_window is None:
            return False
        appearance = _send(
            ctypes.c_void_p,
            [ctypes.c_void_p],
            _class("NSAppearance"),
            "appearanceNamed:",
            _nsstring("NSAppearanceNameAqua"),
        )
        if not appearance:
            return False
        _send(
            None,
            [ctypes.c_void_p],
            ns_window,
            "setAppearance:",
            ctypes.c_void_p(appearance),
        )
        return True
    except Exception:
        return False


def make_titlebar_transparent(window) -> bool:
    """Пускает содержимое под системную полосу, оставляя светофор на месте.

    Так окно получает свою стеклянную шапку и при этом сохраняет родное
    поведение: перетаскивание, изменение размера и полноэкранный режим.
    """
    if not available():
        return False
    try:
        ns_window = _ns_window(window)
        if ns_window is None:
            return False
        mask = _send(ctypes.c_ulong, [], ns_window, "styleMask")
        _send(
            None,
            [ctypes.c_ulong],
            ns_window,
            "setStyleMask:",
            ctypes.c_ulong(mask | NS_WINDOW_STYLE_MASK_FULL_SIZE_CONTENT_VIEW),
        )
        _send(None, [ctypes.c_bool], ns_window, "setTitlebarAppearsTransparent:", True)
        _send(
            None,
            [ctypes.c_long],
            ns_window,
            "setTitleVisibility:",
            ctypes.c_long(NS_WINDOW_TITLE_HIDDEN),
        )
        return True
    except Exception:
        return False


def _accessibility_flag(selector: str) -> bool:
    if not available():
        return False
    try:
        workspace = _send(ctypes.c_void_p, [], _class("NSWorkspace"), "sharedWorkspace")
        if not workspace:
            return False
        return bool(_send(ctypes.c_bool, [], ctypes.c_void_p(workspace), selector))
    except Exception:
        return False


def reduce_motion() -> bool:
    return _accessibility_flag("accessibilityDisplayShouldReduceMotion")


def increase_contrast() -> bool:
    return _accessibility_flag("accessibilityDisplayShouldIncreaseContrast")
