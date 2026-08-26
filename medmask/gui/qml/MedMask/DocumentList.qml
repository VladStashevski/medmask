import QtQuick
import MedMask

/*
  Список документов. Держит на экране только видимые строки, поэтому папка на
  тысячу файлов открывается так же быстро, как папка на десять.

  Список идет во всю высоту окна, а пилюли лежат на нем: строки проходят под
  ними — ради этого пилюли и матовые. Отступы сверху и снизу заданы полями
  прокрутки, а не обрезкой, поэтому первая строка начинается под верхней
  пилюлей, а последняя доезжает до нижней и уходит под нее.
*/
Item {
    id: list

    property alias model: view.model
    property real headerHeight: 0
    property real footerHeight: 0

    ListView {
        id: view
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
