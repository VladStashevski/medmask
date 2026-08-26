import QtQuick
import MedMask

/*
  Нижняя панель: этап, процент, время, полоса и действия. Идет во всю ширину,
  отступ сверху и снизу такой же, как у панели инструментов. Высота
  постоянная — переход между состояниями меняет подписи и кнопки, но не
  двигает верстку.
*/
GlassPanel {
    id: panel

    property string stageText: ""
    property string stageTone: "muted"
    property string percentText: ""
    property string timeText: ""
    property string etaText: ""
    property real value: 0
    property bool indeterminate: false
    property string tone: "primary"

    property bool busy: false
    property bool cancelling: false
    property bool startEnabled: false
    property bool hasResult: false

    signal startRequested()
    signal cancelRequested()
    signal openRequested()

    implicitHeight: Theme.panelPadding * 2 + 18 + Theme.space3 + Theme.buttonHeight
    radius: 0
    elevated: false
    borderColor: "transparent"
    edgeColor: "transparent"

    Item {
        anchors.fill: parent
        anchors.leftMargin: Theme.contentMargin
        anchors.rightMargin: Theme.contentMargin
        anchors.topMargin: Theme.panelPadding
        anchors.bottomMargin: Theme.panelPadding

        Text {
            id: stage
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: numbers.left
            anchors.rightMargin: Theme.space4
            text: panel.stageText
            elide: Text.ElideRight
            color: Theme.toneColor(panel.stageTone)
            font.family: Theme.uiFamily
            font.pixelSize: Theme.fontSmall
            font.weight: panel.stageTone === "muted" ? Font.Normal : Font.Medium

            Behavior on color { ColorAnimation { duration: Theme.base } }
        }

        Row {
            id: numbers
            anchors.top: parent.top
            anchors.right: parent.right
            height: stage.height
            spacing: Theme.space2

            // Проценты и время набраны моноширинным: в пропорциональном
            // шрифте цифры скачут по ширине и строка дрожит.
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: panel.percentText
                color: Theme.text
                font.family: Theme.monoFamily
                font.pixelSize: Theme.fontSmall
                font.weight: Font.DemiBold
                visible: text !== ""
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: panel.percentText !== "" && panel.timeText !== "" ? "·" : ""
                color: Theme.faint
                font.family: Theme.uiFamily
                font.pixelSize: Theme.fontSmall
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: panel.timeText
                color: Theme.muted
                font.family: Theme.monoFamily
                font.pixelSize: Theme.fontSmall
                visible: text !== ""
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: panel.etaText
                color: Theme.faint
                font.family: Theme.uiFamily
                font.pixelSize: Theme.fontSmall
                visible: text !== ""
            }
        }

        Row {
            id: actions
            anchors.bottom: parent.bottom
            anchors.right: parent.right
            spacing: Theme.space2

            PillButton {
                anchors.verticalCenter: parent.verticalCenter
                visible: !panel.busy && panel.hasResult
                text: "Открыть результат"
                variant: "primary"
                onClicked: panel.openRequested()
            }

            PillButton {
                anchors.verticalCenter: parent.verticalCenter
                visible: !panel.busy
                text: "Обезличить"
                variant: panel.hasResult ? "secondary" : "primary"
                enabled: panel.startEnabled
                onClicked: panel.startRequested()
            }

            PillButton {
                anchors.verticalCenter: parent.verticalCenter
                visible: panel.busy
                text: panel.cancelling ? "Останавливаем" : "Отменить"
                variant: "quiet"
                enabled: !panel.cancelling
                onClicked: panel.cancelRequested()
            }
        }

        // Пустая полоса до запуска — просто серая плашка. Она появляется,
        // когда есть что показывать, но место под нее занято всегда, иначе
        // кнопки прыгали бы при старте.
        ProgressBar {
            opacity: panel.busy || panel.value > 0 ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: Theme.base } }
            anchors.bottom: parent.bottom
            anchors.bottomMargin: (Theme.buttonHeight - Theme.progressHeight) / 2
            anchors.left: parent.left
            anchors.right: actions.left
            anchors.rightMargin: Theme.space4
            value: panel.value
            indeterminate: panel.indeterminate
            tone: panel.tone
        }
    }
}
