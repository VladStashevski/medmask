import QtQuick
import QtQuick.Effects
import MedMask

/*
  Список документов. Держит на экране только видимые строки, поэтому папка на
  тысячу файлов открывается так же быстро, как папка на десять.

  Строка уходит под пилюлю и видна под ней до самого дальнего ее края, но
  ровно по ее силуэту: обрезанная по прямой строка выглядывала бы из-за
  скругленных концов капсулы полоской и углом — и слева, и справа.

  headerHeight и footerHeight — сколько сверху и снизу закрыто пилюлей: на
  столько отступают поля прокрутки, поэтому первая строка стоит под верхней
  пилюлей, а последняя доезжает до нижней и скрывается.
*/
Item {
    id: list

    property alias model: view.model
    property real headerHeight: 0
    property real footerHeight: 0

    // Обрезка сделана маской слоя, а не накладкой: окно прозрачное, и
    // накладка любого цвета легла бы на обои мутным пятном.
    Item {
        id: viewport
        anchors.fill: parent
        layer.enabled: true
        layer.effect: MultiEffect {
            maskEnabled: true
            maskSource: fadeMask
            // Порог именно 0.5: при нуле MultiEffect не отсекает ничего —
            // «ниже нуля» пикселей не бывает, и маска висит вхолостую.
            maskThresholdMin: 0.5
            maskSpreadAtMin: 0.15
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

    // Сама маска — полоса между пилюлями плюс силуэты обеих пилюль: строка
    // видна на просвет ровно там, где ее прикрывает капсула, и нигде больше.
    Item {
        id: fadeShape
        anchors.fill: parent
        visible: false

        // Полоса заходит под пилюли до их средней линии, а не кончается на
        // кромке: у капсулы концы скругленные, и у самой кромки она уже
        // полосы — на этой разнице строка и обрывалась по прямой.
        Rectangle {
            y: list.headerHeight / 2
            width: parent.width
            height: Math.max(
                0, parent.height - list.headerHeight / 2 - list.footerHeight / 2)
            color: "#FFFFFF"
        }

        Rectangle {
            x: Theme.pillMargin
            width: Math.max(0, parent.width - Theme.pillMargin * 2)
            height: list.headerHeight
            radius: Theme.pillRadius
            antialiasing: true
            color: "#FFFFFF"
        }

        Rectangle {
            x: Theme.pillMargin
            y: parent.height - list.footerHeight
            width: Math.max(0, parent.width - Theme.pillMargin * 2)
            height: list.footerHeight
            radius: Theme.pillRadius
            antialiasing: true
            color: "#FFFFFF"
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
