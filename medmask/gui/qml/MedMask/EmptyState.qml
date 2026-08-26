import QtQuick
import MedMask

/*
  Заглушка вместо списка: папка не выбрана, читаем папку, ничего не нашлось,
  обработка не начиналась. Появляется коротким проявлением, чтобы смена
  состояния не выглядела подменой окна.
*/
Item {
    id: placeholder

    property string kind: "folder"
    property string title: ""
    property string hint: ""

    readonly property string glyphName: kind === "scan" ? "search"
        : kind === "none" ? "document"
        : kind === "error" ? "alert" : "folder"
    readonly property color accent: kind === "error" ? Theme.danger
        : kind === "none" ? Theme.warning : Theme.muted

    Column {
        anchors.centerIn: parent
        width: Math.min(parent.width - Theme.space6 * 2, 380)
        spacing: Theme.space4

        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            // Папку значком не поясняем: он уже стоит в шапке слева от имени,
            // и такой же в середине окна ничего не сообщает. Остальные виды
            // заглушки говорят о состоянии, которого в шапке нет.
            visible: placeholder.kind !== "folder"
            width: 54
            height: 54
            radius: width / 2
            antialiasing: true
            color: Qt.rgba(placeholder.accent.r, placeholder.accent.g, placeholder.accent.b,
                           Theme.tintSoft)

            Glyph {
                anchors.centerIn: parent
                name: placeholder.glyphName
                size: 26
                weight: 1.7
                color: placeholder.accent
            }
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: placeholder.title
            color: Theme.ink
            font.family: Theme.uiFamily
            font.pixelSize: Theme.fontHeading
            font.weight: Font.DemiBold
            wrapMode: Text.WordWrap
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            visible: placeholder.hint !== ""
            text: placeholder.hint
            color: Theme.ink
            font.family: Theme.uiFamily
            font.pixelSize: Theme.fontSmall
            lineHeight: 1.35
            wrapMode: Text.WordWrap
        }
    }
}
