import QtQuick
import MedMask

/*
  Пилюля состояния: полоса, проценты, этап, время и действия — все в одной
  строке, чтобы высота совпадала с пилюлей папки.

  Ничто здесь не двигается с места. Полоса стоит слева всегда, даже пустая:
  доля сделанного — главное, что панель сообщает, и место под нее держится
  постоянно. Проценты и время набраны моноширинным и стоят в слотах, ширина
  которых посчитана по самому длинному значению: меняется текст, а не верстка.
  Раньше подписи то появлялись, то исчезали, а полоса подгоняла ширину под
  них — строка дрожала на каждой секунде работы.

  Гибкая здесь одна подпись — этап: она забирает остаток строки и обрезается,
  если он мал. В узком окне уходит слот времени: оно приблизительное, а
  проценты и кнопка нужны всегда.
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

    // Слоты цифр меряются по образцу, а не по текущему значению: «100%»
    // шире, чем «7%», и слот, посчитанный по живому тексту, ездил бы.
    TextMetrics {
        id: percentSample
        font.family: Theme.monoFamily
        font.pixelSize: Theme.fontSmall
        font.weight: Font.DemiBold
        text: "100%"
    }

    TextMetrics {
        id: timingSample
        font.family: Theme.monoFamily
        font.pixelSize: Theme.fontSmall
        text: "~00:00"
    }

    TextMetrics {
        id: timingLabelSample
        font.family: Theme.uiFamily
        font.pixelSize: Theme.fontSmall
        text: "осталось"
    }

    Item {
        anchors.fill: parent
        anchors.leftMargin: Theme.pillPadding
        anchors.rightMargin: Theme.pillPadding

        // Время приблизительное — им и жертвует узкое окно.
        readonly property bool roomForTiming: panel.width >= 620

        ProgressBar {
            id: bar
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            width: Theme.progressWidth
            value: panel.value
            indeterminate: panel.indeterminate
            tone: panel.tone
        }

        Text {
            id: percent
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: bar.right
            anchors.leftMargin: Theme.space3
            width: Math.ceil(percentSample.width)
            horizontalAlignment: Text.AlignRight
            text: panel.percentText
            color: Theme.ink
            font.family: Theme.monoFamily
            font.pixelSize: Theme.fontSmall
            font.weight: Font.DemiBold
        }

        Text {
            id: stage
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: percent.right
            anchors.leftMargin: Theme.space4
            anchors.right: timing.visible ? timing.left : actions.left
            anchors.rightMargin: Theme.space4
            text: panel.stageText
            elide: Text.ElideRight
            color: Theme.toneColor(panel.stageTone)
            font.family: Theme.uiFamily
            font.pixelSize: Theme.fontSmall
            font.weight: panel.stageTone === "muted" ? Font.Normal : Font.Medium

            Behavior on color { ColorAnimation { duration: Theme.base } }
        }

        // Время — одно число, а не два. Пока работа идет, спрашивают
        // «сколько еще», когда закончилась — «сколько заняло»; показывать
        // оба разом значит занимать вдвое больше места ради одного ответа.
        //
        // Подпись стоит в своем слоте, посчитанном по длинному слову: иначе
        // смена «прошло» на «осталось» толкала бы число вбок.
        Row {
            id: timing
            anchors.verticalCenter: parent.verticalCenter
            anchors.right: actions.left
            anchors.rightMargin: Theme.space4
            spacing: Theme.space2
            // Только пока работа идет: закончилась — длительность уходит в
            // итог, где ей место рядом с числом файлов.
            visible: panel.busy && parent.roomForTiming && timingValue.text !== ""

            Text {
                anchors.verticalCenter: parent.verticalCenter
                width: Math.ceil(timingLabelSample.width)
                horizontalAlignment: Text.AlignRight
                text: panel.etaText !== "" ? "осталось" : "прошло"
                color: Theme.ink
                font.family: Theme.uiFamily
                font.pixelSize: Theme.fontSmall
            }

            Text {
                id: timingValue
                anchors.verticalCenter: parent.verticalCenter
                width: Math.ceil(timingSample.width)
                horizontalAlignment: Text.AlignRight
                text: panel.etaText !== "" ? panel.etaText : panel.timeText
                color: Theme.ink
                font.family: Theme.monoFamily
                font.pixelSize: Theme.fontSmall
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

            // Когда работа сделана, запуск с панели уходит: делать эту же
            // папку второй раз незачем, а новая папка возвращает кнопку сама.
            // Повторный проход остается на Ctrl+Enter.
            PillButton {
                anchors.verticalCenter: parent.verticalCenter
                visible: !panel.busy && !panel.hasResult
                text: "Обезличить"
                variant: "primary"
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
