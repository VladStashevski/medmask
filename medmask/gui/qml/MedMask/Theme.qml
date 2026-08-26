pragma Singleton

import QtQuick

/*
  Единственный источник чисел и цветов интерфейса.

  Логический пиксель здесь совпадает с пикселем макета: масштабирование
  экрана Qt берет на себя, поэтому на Retina и на Windows со 150 % одни и те
  же значения дают одинаковую верстку.

  dark, glass и motion выставляет Main.qml из системных настроек.
*/
QtObject {
    id: theme

    property bool glass: true
    property bool systemBackdrop: false
    property real glassOpacity: 0.8
    property bool motion: true

    // ---------- ритм ----------

    readonly property real space1: 4
    readonly property real space2: 8
    readonly property real space3: 12
    readonly property real space4: 16
    readonly property real space5: 20
    readonly property real space6: 24

    readonly property real windowWidth: 760
    readonly property real windowHeight: 600
    readonly property real windowMinWidth: 560
    readonly property real windowMinHeight: 480

    readonly property real contentMargin: 16

    readonly property real panelRadius: 12
    readonly property real windowRadius: 10

    // Окно — одна прозрачная поверхность от края до края, полоса со значком
    // включительно. Панели на ней не полосы, а пилюли: одна высота на обе,
    // радиус в половину высоты, общий отступ от краев окна.
    readonly property real pillHeight: 60
    readonly property real pillRadius: pillHeight / 2
    readonly property real pillMargin: 12
    // Содержимое отступает от края пилюли ровно настолько, насколько кнопка
    // внутри отступает сверху и снизу: вложенная пилюля садится по центру.
    readonly property real pillPadding: (pillHeight - buttonHeight) / 2

    // Верхняя полоса отдана системным кнопкам и значку программы: слева
    // светофор macOS или свои кнопки Windows, справа значок.
    readonly property real titleBarHeight: 30
    // Сколько занято сверху и снизу — на столько отступает список.
    readonly property real toolbarHeight: titleBarHeight + pillHeight
    readonly property real statusHeight: pillHeight + pillMargin
    readonly property real rowHeight: 44
    readonly property real buttonHeight: 34
    readonly property real progressHeight: 12
    // Полоса прогресса живет в одной строке с подписью и кнопкой.
    readonly property real progressWidth: 180
    readonly property real statusIconSize: 16
    readonly property real fileIconWidth: 26
    readonly property real fileIconHeight: 32
    readonly property real captionButtonWidth: 44

    readonly property real hairline: 1

    // ---------- типографика ----------

    readonly property string uiFamily: Qt.application.font.family
    readonly property string monoFamily: Qt.platform.os === "windows" ? "Consolas" : "Menlo"

    readonly property int fontHeading: 15
    readonly property int fontBody: 13
    readonly property int fontSmall: 12
    readonly property int fontMicro: 11

    // ---------- движение ----------

    readonly property int fast: motion ? 120 : 0
    readonly property int base: motion ? 160 : 0
    readonly property int slow: motion ? 220 : 0
    readonly property int easing: Easing.OutCubic

    // ---------- цвет ----------

    // Тема одна — светлая. Программа читает медицинские документы, и белый
    // лист с темным текстом остается самым спокойным фоном для такой работы.

    // Поверхность окна: почти белый лист с холодным отливом. Он же фон
    // списка, поэтому держится светлым — на нем читают имена документов.
    // Один фон на все окно: сквозь него виден рабочий стол, и панели не
    // подкладывают под себя ничего своего.
    readonly property color appFill: Qt.rgba(1, 1, 1, glassOpacity)

    readonly property color pageTop: "#FFFFFF"
    readonly property color pageBottom: "#EDF2FA"
    readonly property color glowCool: Qt.rgba(0.62, 0.76, 0.98, 0.30)
    readonly property color glowWarm: Qt.rgba(1, 1, 1, 0.65)

    // Пилюли не подкладывают белый лист: под ними системное матовое стекло,
    // и им хватает легкого осветления. Без системного стекла заливка плотнее,
    // иначе строки просвечивают сквозь пилюлю.
    readonly property color panelFill: systemBackdrop
        ? Qt.rgba(1, 1, 1, 0.35)
        : (glass ? Qt.rgba(1, 1, 1, 0.82) : "#FBFCFE")
    // Внутренний блик приглушен: яркая белая нить по кромке перечеркивала
    // строку, которая проходит под пилюлей, и читалась как рез по прямой.
    readonly property color panelEdge: Qt.rgba(1, 1, 1, 0)
    // Строки лежат прямо на стекле, поэтому подсветка чуть заметнее.
    readonly property color rowGlassHover: Qt.rgba(1, 1, 1, 0.45)
    // Исходный цвет подсветки — прозрачный белый, а не «transparent»:
    // «transparent» это прозрачный черный, и переход к белому проходит
    // через серую вспышку.
    readonly property color rowIdle: Qt.rgba(1, 1, 1, 0)
    readonly property color panelBorder: Qt.rgba(0.06, 0.09, 0.16, 0)

    // Список читают глазами, поэтому он заметно плотнее панелей.
    readonly property color cardFill: systemBackdrop ? "transparent" : "#FFFFFF"
    readonly property color cardBorder: Qt.rgba(0.06, 0.09, 0.16, 0.08)

    readonly property color divider: Qt.rgba(0.06, 0.09, 0.16, 0.07)
    readonly property color rowHover: Qt.rgba(0.06, 0.09, 0.16, 0.035)
    // Строка в работе подсвечивается едва заметно: она указывает место,
    // а не требует внимания.
    readonly property color rowActive: Qt.rgba(0.15, 0.39, 0.92, 0.07)

    readonly property color ink: "#0F172A"
    readonly property color text: "#334155"
    readonly property color muted: "#64748B"
    readonly property color faint: "#94A3B8"

    readonly property color primary: "#2563EB"
    readonly property color primaryHover: "#1D4ED8"
    readonly property color primaryPress: "#1E40AF"
    readonly property color inkOnPrimary: "#FFFFFF"

    readonly property color success: "#059669"
    readonly property color warning: "#D97706"
    readonly property color danger: "#DC2626"
    // Закрытие окна в Windows краснеет целиком — это системная привычка.
    readonly property color closeHover: "#E11D48"
    readonly property color closePress: "#B91C1C"

    readonly property color track: Qt.rgba(0.06, 0.09, 0.16, 0.09)
    readonly property color shadow: Qt.rgba(0.06, 0.12, 0.28, 0.18)
    readonly property color focusRing: "#2563EB"

    readonly property color controlFill: Qt.rgba(1, 1, 1, 0.85)
    readonly property color controlHover: Qt.rgba(1, 1, 1, 1.0)
    readonly property color controlPress: Qt.rgba(0.90, 0.92, 0.96, 1.0)
    readonly property color controlBorder: Qt.rgba(0.06, 0.09, 0.16, 0.12)

    // Полупрозрачные оттенки, которыми пользуются значки и пометки.
    readonly property real tintSoft: 0.09
    readonly property real tintMedium: 0.12
    readonly property real tintStrong: 0.42

    // Цвет значка документа по виду файла.
    function kindColor(kind) {
        switch (kind) {
        case "pdf": return danger;
        case "sheet": return success;
        case "doc": return primary;
        case "image": return "#0891B2";
        default: return muted;
        }
    }

    function toneColor(tone) {
        switch (tone) {
        case "success": return success;
        case "warning": return warning;
        case "danger": return danger;
        case "primary": return primary;
        default: return muted;
        }
    }

    function statusColor(status) {
        switch (status) {
        case "done": return success;
        case "review": return warning;
        case "failed": return danger;
        case "active": return primary;
        default: return faint;
        }
    }
}
