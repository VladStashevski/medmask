import QtQuick
import QtQuick.Effects
import MedMask

/*
  Список документов. Держит на экране только видимые строки, поэтому папка на
  тысячу файлов открывается так же быстро, как папка на десять.

  Подходя к пилюле, строка растворяется и под стекло уходит уже прозрачной.
  Растворяется именно по вертикали, а не гаснет целиком: кромка стекла делит
  строку надвое — над кромкой четкая, под кромкой размытая, — и разрыв
  читается как обрубленный текст. Растворять нечего, если строки там уже нет.

  headerHeight и footerHeight — сколько сверху и снизу закрыто пилюлей: на
  столько отступают поля прокрутки, поэтому первая строка стоит под верхней
  пилюлей, а последняя доезжает до нижней и скрывается.
*/
Item {
    id: list

    property alias model: view.model
    property real headerHeight: 0
    property real footerHeight: 0

    // Насколько строка растворяется, подходя к пилюле.
    readonly property real fade: Theme.pillHeight / 2

    function share(y) { return Math.min(1, Math.max(0, y / Math.max(1, height))); }

    readonly property real hiddenTop: share(headerHeight - fade)
    readonly property real solidTop: Math.max(hiddenTop, share(headerHeight + fade))
    readonly property real hiddenBottom: Math.max(
        solidTop, share(height - footerHeight + fade))
    readonly property real solidBottom: Math.max(
        solidTop, Math.min(hiddenBottom, share(height - footerHeight - fade)))

    // Обрезка сделана маской слоя, а не накладкой: окно прозрачное, и
    // накладка любого цвета легла бы на обои мутным пятном.
    Item {
        id: viewport
        anchors.fill: parent
        // Слой с маской живет только вместе со стеклом: программный рендерер
        // не умеет ни слоев, ни шейдеров, и список остался бы пустым местом.
        layer.enabled: Theme.glass
        layer.effect: MultiEffect {
            maskEnabled: true
            maskSource: fadeMask
            // Порог именно 0.5: при нуле MultiEffect не отсекает ничего —
            // «ниже нуля» пикселей не бывает, и маска висит вхолостую.
            maskThresholdMin: 0.5
            maskSpreadAtMin: 0.5
        }

        ListView {
            id: view
            objectName: "documents"
            anchors.fill: parent
            clip: true
            // Список не участвует в обходе по Tab: он не действие, а содержимое,
            // и без видимой рамки фокус на нем выглядел бы потерянным.
            activeFocusOnTab: false
            boundsBehavior: Flickable.StopAtBounds
            maximumFlickVelocity: 2200
            cacheBuffer: Theme.rowHeight * 6
            topMargin: list.headerHeight + Theme.space2
            bottomMargin: list.footerHeight + Theme.space2

            delegate: FileRow {
                width: view.width
                name: model.name
                kind: model.kind
                status: model.status
                statusText: model.statusText
                badge: model.badge
                hovered: pointer.hovered

                HoverHandler { id: pointer }

                onStatusChanged: if (status === "active") list.follow(index)
            }
        }
    }

    // Сама маска: непрозрачная между пилюлями и сходящая на нет к их кромке.
    // Порог отсекает нижнюю половину полутонов, поэтому полоса перехода в
    // маске вдвое шире того, что видно на экране.
    Item {
        id: fadeShape
        anchors.fill: parent
        visible: false

        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0) }
                GradientStop { position: list.hiddenTop; color: Qt.rgba(1, 1, 1, 0) }
                GradientStop { position: list.solidTop; color: "#FFFFFF" }
                GradientStop { position: list.solidBottom; color: "#FFFFFF" }
                GradientStop { position: list.hiddenBottom; color: Qt.rgba(1, 1, 1, 0) }
                GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0) }
            }
        }
    }

    ShaderEffectSource {
        id: fadeMask
        anchors.fill: parent
        visible: false
        live: true
        hideSource: true
        sourceItem: fadeShape
    }

    // Показывать строку, которая обрабатывается прямо сейчас. Прыжки
    // придерживаются таймером: в параллельном режиме активных строк
    // несколько, и список иначе дергается на каждом сообщении.
    function follow(index) {
        if (index < 0 || view.moving || view.dragging)
            return;
        followTimer.target = index;
        if (!followTimer.running)
            followTimer.start();
    }

    // Видимая часть списка — не все окно: сверху и снизу его закрывают
    // пилюли, и строка, подведенная к самому краю, оказалась бы под стеклом.
    readonly property real visibleTop: view.contentY + list.headerHeight
    readonly property real visibleBottom: view.contentY + view.height - list.footerHeight

    function scrollTo(position) {
        var lowest = -view.topMargin;
        var highest = Math.max(
            lowest, view.contentHeight + view.bottomMargin - view.height);
        view.contentY = Math.max(lowest, Math.min(highest, position));
    }

    Timer {
        id: followTimer
        property int target: -1
        interval: 320
        onTriggered: {
            if (target < 0 || view.moving || view.dragging)
                return;
            var top = target * Theme.rowHeight;
            var bottom = top + Theme.rowHeight;
            if (top < list.visibleTop)
                list.scrollTo(top - list.headerHeight);
            else if (bottom > list.visibleBottom)
                list.scrollTo(bottom + list.footerHeight - view.height);
        }
    }

    // Полоса прокрутки живет между пилюлями, а не во всю высоту окна: под
    // стеклом от нее остался бы только размытый след.
    Rectangle {
        id: scrollbar
        anchors.right: parent.right
        anchors.rightMargin: 3
        width: 4
        radius: 2
        antialiasing: true
        color: Theme.faint

        readonly property real band: Math.max(
            0, view.height - list.headerHeight - list.footerHeight - Theme.space2 * 2)
        readonly property real span: Math.max(
            1, view.contentHeight + view.topMargin + view.bottomMargin - view.height)
        readonly property real shift: Math.min(
            1, Math.max(0, (view.contentY + view.topMargin) / span))

        visible: view.contentHeight > band + 1
        opacity: view.moving || scrollHover.hovered ? 0.65 : 0.28
        y: view.y + list.headerHeight + Theme.space2 + (band - height) * shift
        height: Math.max(28, band * Math.min(1, band / Math.max(1, view.contentHeight)))

        Behavior on opacity { NumberAnimation { duration: Theme.base } }
    }

    HoverHandler { id: scrollHover }
}
