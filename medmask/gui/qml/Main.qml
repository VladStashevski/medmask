import QtQuick
import QtQuick.Window
import QtQuick.Dialogs
import MedMask

/*
  Окно MedMask.

  Одна прозрачная поверхность от края до края, полоса со значком включительно.
  Панели не делят ее на полосы: папка сверху и состояние снизу лежат на ней
  двумя пилюлями одной высоты, а список идет во всю высоту окна и уходит под
  них — потому пилюли и матовые.

  Слой behind — то, что видно сквозь стекло. Пилюли живут рядом с ним, а не
  внутри: слепок для размытия берется по их собственным x и y, и вложенность
  дала бы рекурсию.
*/
Window {
    id: window

    width: Theme.windowWidth
    height: Theme.windowHeight
    minimumWidth: Theme.windowMinWidth
    minimumHeight: Theme.windowMinHeight
    visible: true
    title: "MedMask"
    color: env.systemBackdrop ? "transparent" : Theme.pageTop
    flags: env.frameless ? (Qt.Window | Qt.FramelessWindowHint) : Qt.Window

    readonly property bool maximized: visibility === Window.Maximized
                                      || visibility === Window.FullScreen

    Binding { target: Theme; property: "glass"; value: env.glass }
    Binding { target: Theme; property: "systemBackdrop"; value: env.systemBackdrop }
    Binding { target: Theme; property: "glassOpacity"; value: env.glassOpacity }
    Binding { target: Theme; property: "motion"; value: env.motion }

    Component.onCompleted: {
        x = Math.round(Screen.virtualX + (Screen.width - width) / 2);
        y = Math.round(Screen.virtualY + (Screen.height - height) / 2.4);
    }

    // ---------- слой под стеклом ----------

    Item {
        id: behind
        anchors.fill: parent

        Backdrop { anchors.fill: parent }

        DocumentList {
            anchors.fill: parent
            // Строки уходят под пилюли и видны сквозь стекло. Обрезает их
            // маска на шейдере, а без стекла (высокий контраст, программный
            // рендерер) шейдеров нет — тогда список просто кончается там,
            // где начинается пилюля.
            anchors.topMargin: Theme.glass ? Theme.titleBarHeight : Theme.toolbarHeight
            anchors.bottomMargin: Theme.glass ? Theme.pillMargin : Theme.statusHeight
            headerHeight: Theme.glass ? Theme.pillHeight : 0
            footerHeight: Theme.glass ? Theme.pillHeight : 0
            model: controller.documents
            opacity: controller.showList ? 1 : 0
            visible: opacity > 0
            Behavior on opacity { NumberAnimation { duration: Theme.base } }
        }

        EmptyState {
            anchors.fill: parent
            anchors.topMargin: Theme.toolbarHeight
            anchors.bottomMargin: Theme.statusHeight
            kind: controller.emptyKind
            title: controller.emptyTitle
            hint: controller.emptyHint
            opacity: controller.showList ? 0 : 1
            visible: opacity > 0
            Behavior on opacity { NumberAnimation { duration: Theme.base } }
        }
    }

    // ---------- матовые пилюли поверх списка ----------

    FolderBar {
        id: folderBar
        x: Theme.pillMargin
        y: Theme.titleBarHeight
        width: parent.width - Theme.pillMargin * 2
        height: Theme.pillHeight
        blurSource: behind

        folderName: controller.folderName
        folderPath: controller.folderPath
        countLabel: controller.countLabel
        countCompact: controller.countCompact
        known: controller.hasFolder
        chooseEnabled: controller.canChoose

        onChooseRequested: folderDialog.open()
        onMoveRequested: controls.startMove(window)
        onToggleMaximizeRequested: controls.toggleMaximize(window)
    }

    ProgressPanel {
        id: statusPanel
        x: Theme.pillMargin
        y: parent.height - height - Theme.pillMargin
        width: parent.width - Theme.pillMargin * 2
        height: Theme.pillHeight
        blurSource: behind

        stageText: controller.stageText
        stageTone: controller.stageTone
        percentText: controller.percentText
        timeText: controller.timeText
        etaText: controller.etaText
        value: controller.progress
        indeterminate: controller.indeterminate
        tone: controller.progressTone
        busy: controller.busy
        cancelling: controller.state === "cancelling"
        startEnabled: controller.canStart
        hasResult: controller.hasResult

        onStartRequested: controller.start()
        onCancelRequested: controller.cancel()
        onOpenRequested: controller.openResult()
    }

    // Верхняя полоса панели инструментов: системные кнопки и значок.
    TitleBar {
        id: titleBar
        width: parent.width
        height: Theme.titleBarHeight
        frameless: env.frameless
        maximized: window.maximized

        onMoveRequested: controls.startMove(window)
        onToggleMaximizeRequested: controls.toggleMaximize(window)
        onMinimizeRequested: controls.minimize(window)
        onCloseRequested: window.close()
        onMaximizeRectChanged: controls.setMaximizeButtonRect(
            maximizeRect.x, maximizeRect.y, maximizeRect.width, maximizeRect.height)
    }

    ResizeEdges {
        visible: env.frameless && !window.maximized
        enabled: visible
        onResizeRequested: edge => controls.startResize(window, edge)
    }

    // ---------- ввод ----------

    FolderDialog {
        id: folderDialog
        title: "Выберите папку с медицинскими документами"
        currentFolder: controller.initialFolder
        onAccepted: controller.setFolderUrl(selectedFolder)
    }

    Shortcut {
        sequences: ["Ctrl+O"]
        enabled: controller.canChoose
        onActivated: folderDialog.open()
    }

    Shortcut {
        sequences: ["Ctrl+Return", "Ctrl+Enter"]
        onActivated: controller.toggleStart()
    }

    Shortcut {
        sequence: "Esc"
        onActivated: controller.cancel()
    }

    Shortcut {
        sequences: ["Ctrl+Shift+O"]
        enabled: controller.hasResult
        onActivated: controller.openResult()
    }

    Shortcut {
        sequences: ["Ctrl+W"]
        onActivated: window.close()
    }
}
