import QtQuick
import MedMask

/*
  Список документов. Держит на экране только видимые строки, поэтому папка на
  тысячу файлов открывается так же быстро, как папка на десять.

  Строки уходят под панель инструментов и под нижнюю панель — ради этого они
  и матовые: движение под стеклом видно, а имена остаются читаемыми.
*/
Item {
    id: list

    property alias model: view.model
    property real headerHeight: 0
    property real footerHeight: 0

    ListView {
        id: view
        anchors.fill: parent
        anchors.topMargin: list.headerHeight
        anchors.bottomMargin: list.footerHeight
        // Клип по прямоугольнику: строки не доходят до скругленных углов
        // карточки, поэтому подсветка их не задевает.
        clip: true
        // Список не участвует в обходе по Tab: он не действие, а содержимое,
        // и без видимой рамки фокус на нем выглядел бы потерянным.
        activeFocusOnTab: false
        boundsBehavior: Flickable.StopAtBounds
        maximumFlickVelocity: 2200
        cacheBuffer: Theme.rowHeight * 6
        bottomMargin: Theme.space2
        topMargin: Theme.space1

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

    Timer {
        id: followTimer
        property int target: -1
        interval: 320
        onTriggered: {
            if (target < 0 || view.moving || view.dragging)
                return;
            var top = target * Theme.rowHeight;
            var bottom = top + Theme.rowHeight;
            if (top < view.contentY || bottom > view.contentY + view.height)
                view.positionViewAtIndex(target, ListView.Contain);
        }
    }

    Rectangle {
        id: scrollbar
        anchors.right: parent.right
        anchors.rightMargin: 3
        width: 4
        radius: 2
        antialiasing: true
        color: Theme.faint
        visible: view.contentHeight > view.height + 1
        opacity: view.moving || scrollHover.hovered ? 0.65 : 0.28
        y: view.y + Theme.space2
           + (view.height - Theme.space2 * 2 - height)
             * (view.contentHeight > view.height
                ? Math.min(1, Math.max(0, view.contentY / (view.contentHeight - view.height)))
                : 0)
        height: Math.max(28, (view.height - Theme.space2 * 2)
                             * Math.min(1, view.height / Math.max(1, view.contentHeight)))

        Behavior on opacity { NumberAnimation { duration: Theme.base } }
    }

    HoverHandler { id: scrollHover }
}
