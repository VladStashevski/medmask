import QtQuick
import MedMask

/*
  Пилюля папки: какая папка открыта, сколько в ней документов и кнопка выбора.
  Лежит поверх общей поверхности окна, а не делит его полосой, поэтому строки
  списка проходят под ней и видны сквозь стекло.

  Системные кнопки и значок программы живут выше, на самой поверхности:
  пилюля начинается под ними и не мешает светофору.
*/
GlassPanel {
    id: bar

    property string folderName: ""
    property string folderPath: ""
    property string countLabel: ""
    property string countCompact: ""
    property bool known: false
    property bool chooseEnabled: true

    signal chooseRequested()
    signal moveRequested()
    signal toggleMaximizeRequested()

    implicitHeight: Theme.pillHeight
    radius: Theme.pillRadius

    // Окно тянется за всю пилюлю, а не только за полосу системных кнопок.
    // Область лежит под содержимым, поэтому кнопка забирает свои щелчки
    // первой, а подписи мышь не ловят и передают перетаскивание сюда.
    MouseArea {
        anchors.fill: parent
        property bool armed: false
        onPressed: armed = true
        onReleased: armed = false
        onPositionChanged: {
            if (armed) {
                armed = false;
                bar.moveRequested();
            }
        }
        onDoubleClicked: bar.toggleMaximizeRequested()
    }

    Item {
        anchors.fill: parent
        anchors.leftMargin: Theme.pillPadding
        anchors.rightMargin: Theme.pillPadding

        Rectangle {
            id: tile
            anchors.verticalCenter: parent.verticalCenter
            // Плитка ростом с кнопку на другом конце пилюли: два предмета
            // одной высоты держат строку, а мельче кнопки значок выглядел
            // случайно уменьшенным.
            width: Theme.buttonHeight
            height: Theme.buttonHeight
            radius: 10
            antialiasing: true
            color: bar.known
                ? Qt.rgba(Theme.primary.r, Theme.primary.g, Theme.primary.b, Theme.tintSoft)
                : Qt.rgba(Theme.muted.r, Theme.muted.g, Theme.muted.b, Theme.tintSoft)
            Behavior on color { ColorAnimation { duration: Theme.base } }

            Glyph {
                anchors.centerIn: parent
                name: "folder"
                size: 19
                weight: 1.7
                color: bar.known ? Theme.primary : Theme.muted
                Behavior on color { ColorAnimation { duration: Theme.base } }
            }
        }

        Column {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: tile.right
            anchors.leftMargin: Theme.space3
            anchors.right: meta.left
            anchors.rightMargin: Theme.space4
            spacing: 1

            Text {
                width: parent.width
                text: bar.folderName
                elide: Text.ElideMiddle
                color: Theme.ink
                font.family: Theme.uiFamily
                font.pixelSize: Theme.fontBody
                font.weight: Font.DemiBold
                Behavior on color { ColorAnimation { duration: Theme.base } }
            }

            Text {
                width: parent.width
                text: bar.folderPath
                elide: Text.ElideMiddle
                color: Theme.ink
                font.family: Theme.uiFamily
                font.pixelSize: Theme.fontMicro
            }
        }

        Row {
            id: meta
            anchors.verticalCenter: parent.verticalCenter
            anchors.right: parent.right
            spacing: Theme.space4

            // В узком окне счетчик уступает место имени папки: сначала
            // отпадает «без поддержки», потом счетчик целиком.
            Text {
                anchors.verticalCenter: parent.verticalCenter
                visible: bar.width > 470 && text !== ""
                text: bar.width > 640 ? bar.countLabel : bar.countCompact
                color: Theme.ink
                font.family: Theme.uiFamily
                font.pixelSize: Theme.fontSmall
                opacity: text === "" ? 0 : 1
                Behavior on opacity { NumberAnimation { duration: Theme.base } }
            }

            PillButton {
                anchors.verticalCenter: parent.verticalCenter
                text: "Выбрать папку"
                variant: "secondary"
                enabled: bar.chooseEnabled
                onClicked: bar.chooseRequested()
            }
        }
    }
}
