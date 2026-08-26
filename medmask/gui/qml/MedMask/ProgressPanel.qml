import QtQuick
import MedMask

/*
  Пилюля состояния: этап, проценты, время, полоса и действия — все в одной
  строке, чтобы высота совпадала с пилюлей папки. Высота постоянная: смена
  состояния меняет подписи и кнопки, но не двигает верстку.

  В узком окне первой уступает полоса, затем подпись этапа: проценты, время и
  кнопка нужны всегда, а полоса и слова повторяют то же самое.
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

    implicitHeight: Theme.pillHeight
    radius: Theme.pillRadius

    Item {
        anchors.fill: parent
        anchors.leftMargin: Theme.pillPadding
        anchors.rightMargin: Theme.pillPadding

        Text {
            id: stage
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.right: bar.left
            anchors.rightMargin: Theme.space3
            text: panel.stageText
            elide: Text.ElideRight
            color: Theme.toneColor(panel.stageTone)
            font.family: Theme.uiFamily
            font.pixelSize: Theme.fontSmall
            font.weight: panel.stageTone === "muted" ? Font.Normal : Font.Medium

            Behavior on color { ColorAnimation { duration: Theme.base } }
        }

        // Пустая полоса до запуска не занимает места: пока считать нечего,
        // подпись этапа забирает всю строку.
        ProgressBar {
            id: bar
            anchors.verticalCenter: parent.verticalCenter
            anchors.right: numbers.left
            anchors.rightMargin: width > 0 ? Theme.space4 : 0

            // Подписи слева важнее полосы, поэтому им остается не меньше
            // половины ее полной ширины, а сама полоса ужимается.
            readonly property real room: parent.width - actions.width - numbers.width
                                         - Theme.progressWidth / 2 - Theme.space4 * 3
            width: panel.busy || panel.value > 0
                   ? Math.max(0, Math.min(Theme.progressWidth, room))
                   : 0
            opacity: width > 0 ? 1 : 0
            value: panel.value
            indeterminate: panel.indeterminate
            tone: panel.tone

            Behavior on width { NumberAnimation { duration: Theme.base; easing.type: Theme.easing } }
            Behavior on opacity { NumberAnimation { duration: Theme.base } }
        }

        Row {
            id: numbers
            anchors.verticalCenter: parent.verticalCenter
            anchors.right: actions.left
            anchors.rightMargin: width > 0 ? Theme.space4 : 0
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
                visible: text !== ""
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
                // Оставшееся время — первая подпись, которой жертвует узкое
                // окно: она самая длинная и самая приблизительная.
                text: panel.etaText
                color: Theme.faint
                font.family: Theme.uiFamily
                font.pixelSize: Theme.fontSmall
                visible: text !== "" && panel.width > Theme.windowWidth / 2
            }
        }

        Row {
            id: actions
            anchors.verticalCenter: parent.verticalCenter
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
    }
}
