import QtQuick
import MedMask

/*
  Строка документа: значок вида и имя слева, состояние справа. Плотная —
  список остается главным содержимым окна, а не набором карточек.
*/
Item {
    id: row

    property string name: ""
    property string kind: "text"
    property string status: ""
    property string statusText: ""
    property string badge: ""
    property bool hovered: false

    implicitHeight: Theme.rowHeight

    Rectangle {
        anchors.fill: parent
        anchors.leftMargin: Theme.space1
        anchors.rightMargin: Theme.space1
        anchors.topMargin: 1
        anchors.bottomMargin: 1
        radius: Theme.rowRadius
        antialiasing: true
        color: row.status === "active" ? Theme.rowActive
             : row.hovered ? (Theme.systemBackdrop ? Theme.rowGlassHover : Theme.rowHover)
             : Theme.rowIdle
        Behavior on color { ColorAnimation { duration: Theme.fast } }
    }

    FileIcon {
        id: icon
        anchors.verticalCenter: parent.verticalCenter
        anchors.left: parent.left
        anchors.leftMargin: Theme.space3
        kind: row.kind
        opacity: row.status === "failed" ? 0.55 : 1
        Behavior on opacity { NumberAnimation { duration: Theme.base } }
    }

    Text {
        id: label
        anchors.verticalCenter: parent.verticalCenter
        anchors.left: icon.right
        anchors.leftMargin: Theme.space3
        anchors.right: state.left
        anchors.rightMargin: Theme.space4
        text: row.name
        elide: Text.ElideMiddle
        color: row.status === "failed" ? Theme.muted : Theme.ink
        font.family: Theme.uiFamily
        font.pixelSize: Theme.fontBody
        Behavior on color { ColorAnimation { duration: Theme.base } }
    }

    Row {
        id: state
        anchors.verticalCenter: parent.verticalCenter
        anchors.right: parent.right
        anchors.rightMargin: Theme.space4
        spacing: Theme.space2

        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            visible: row.badge !== ""
            width: badgeLabel.implicitWidth + Theme.space2 * 2
            height: 19
            radius: height / 2
            antialiasing: true
            color: Qt.rgba(Theme.warning.r, Theme.warning.g, Theme.warning.b, Theme.tintMedium)

            Text {
                id: badgeLabel
                anchors.centerIn: parent
                text: row.badge
                color: Theme.warning
                font.family: Theme.uiFamily
                font.pixelSize: Theme.fontMicro
                font.weight: Font.Medium
            }
        }

        StatusIndicator {
            anchors.verticalCenter: parent.verticalCenter
            status: row.status
        }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            // Ширина подписи закреплена по самой длинной: иначе значки
            // состояния прыгают по горизонтали при каждой смене строки.
            width: 104
            horizontalAlignment: Text.AlignLeft
            text: row.statusText
            elide: Text.ElideRight
            color: row.status === "" ? Theme.faint : Theme.statusColor(row.status)
            font.family: Theme.uiFamily
            font.pixelSize: Theme.fontSmall
            Behavior on color { ColorAnimation { duration: Theme.base } }
        }
    }
}
