import QtQuick
import QtQuick.Controls
import QtQuick.Window

ApplicationWindow {
    id: window
    objectName: "voxpadWindow"
    width: 391; height: 510
    minimumWidth: 300; minimumHeight: 391
    title: "VoxPad"
    color: "transparent"
    flags: Qt.Window | Qt.FramelessWindowHint | Qt.CustomizeWindowHint | Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint
    visible: !startHidden
    property QtObject resizeGeometry
    property string currentPage: "home"
    property string pendingPage: "home"
    onClosing: function(close) { close.accepted = false; controller.requestClose() }
    QtObject {
        id: appTheme
        objectName: "appTheme"
        readonly property real uiScale: stage.scale
        property bool transitioning: false
        readonly property bool dark: controller.preferences.ui_theme === "dark"
        readonly property int hoverDuration: 150
        readonly property int leaveDuration: 120
        readonly property int pressDuration: 90
        readonly property real shadowBlur: 22
        readonly property real shadowOffset: 8
        property color shadowColor: Qt.rgba(0, 0, 0, dark ? 0.34 : 0.14)
        property color bevelStart: dark ? "#55555b" : "#ffffff"
        property color bevelEnd: dark ? "#27272c" : "#cfcfd5"
        onDarkChanged: { transitioning = true; themeTransitionTimer.restart() }
        property color surface: dark ? "#29292c" : "#f7f7f9"
        property color frame: dark ? "#222225" : "#f5f5f7"
        property color ink: dark ? "#f6f6f7" : "#080809"
        property color secondaryInk: dark ? "#c1c1c6" : "#555557"
        property color muted: dark ? "#acacb2" : "#77777a"
        property color border: dark ? "#404044" : "#dedee3"
        property color controlBorder: dark ? "#56565a" : "#c9c9cf"
        property color highlight: dark ? "#48484c" : "#ffffff"
        property color raised: dark ? "#343438" : "#ffffff"
        property color hover: dark ? "#3a3a3e" : "#e8e8ed"
        property color pressed: dark ? "#202023" : "#e6e6eb"
        property color track: dark ? "#343437" : "#eeeef1"
        property color selection: dark ? "#656571" : "#d6d6e3"
        property color chartSelected: dark ? "#f4f4f6" : "#101010"
        property color chartBar: dark ? "#616166" : "#d0d0d3"
        property color primary: dark ? "#f3f3f5" : "#111111"
        property color primaryEdge: dark ? "#d9d9dd" : "#303030"
        property color primaryBevel: dark ? "#18000000" : "#22ffffff"
        property color switchOn: dark ? "#f3f3f5" : "#111111"
        property color switchOff: dark ? "#55555c" : "#d1d1d3"
        property color switchKnob: dark ? "#252528" : "#ffffff"
        property color scrollbar: dark ? "#77777f" : "#b8b8bb"
        Behavior on surface { ColorAnimation { duration: 320; easing.type: Easing.InOutCubic } }
        Behavior on frame { ColorAnimation { duration: 320; easing.type: Easing.InOutCubic } }
        Behavior on ink { ColorAnimation { duration: 320; easing.type: Easing.InOutCubic } }
        Behavior on secondaryInk { ColorAnimation { duration: 320; easing.type: Easing.InOutCubic } }
        Behavior on muted { ColorAnimation { duration: 320; easing.type: Easing.InOutCubic } }
        Behavior on border { ColorAnimation { duration: 320; easing.type: Easing.InOutCubic } }
        Behavior on controlBorder { ColorAnimation { duration: 320; easing.type: Easing.InOutCubic } }
        Behavior on highlight { ColorAnimation { duration: 320; easing.type: Easing.InOutCubic } }
        Behavior on raised { ColorAnimation { duration: 320; easing.type: Easing.InOutCubic } }
        Behavior on hover { ColorAnimation { duration: 320; easing.type: Easing.InOutCubic } }
        Behavior on pressed { ColorAnimation { duration: 320; easing.type: Easing.InOutCubic } }
        Behavior on track { ColorAnimation { duration: 320; easing.type: Easing.InOutCubic } }
        Behavior on selection { ColorAnimation { duration: 320; easing.type: Easing.InOutCubic } }
        Behavior on chartSelected { ColorAnimation { duration: 320; easing.type: Easing.InOutCubic } }
        Behavior on chartBar { ColorAnimation { duration: 320; easing.type: Easing.InOutCubic } }
        Behavior on primary { ColorAnimation { duration: 320; easing.type: Easing.InOutCubic } }
        Behavior on primaryEdge { ColorAnimation { duration: 320; easing.type: Easing.InOutCubic } }
        Behavior on primaryBevel { ColorAnimation { duration: 320; easing.type: Easing.InOutCubic } }
        Behavior on switchOn { ColorAnimation { duration: 320; easing.type: Easing.InOutCubic } }
        Behavior on switchOff { ColorAnimation { duration: 320; easing.type: Easing.InOutCubic } }
        Behavior on switchKnob { ColorAnimation { duration: 320; easing.type: Easing.InOutCubic } }
        Behavior on scrollbar { ColorAnimation { duration: 320; easing.type: Easing.InOutCubic } }
        Behavior on shadowColor { ColorAnimation { duration: 320; easing.type: Easing.InOutCubic } }
        Behavior on bevelStart { ColorAnimation { duration: 320; easing.type: Easing.InOutCubic } }
        Behavior on bevelEnd { ColorAnimation { duration: 320; easing.type: Easing.InOutCubic } }
    }
    Timer { id: themeTransitionTimer; interval: 340; onTriggered: appTheme.transitioning = false }
    Item {
        id: sceneViewport
        objectName: "sceneViewport"
        anchors.fill: parent
        clip: true
        Item {
            id: stage
            objectName: "stage"
            width: 1100; height: 1430
            scale: Math.min(window.width / 978, window.height / 1276)
            transformOrigin: Item.TopLeft
            x: (window.width - 978 * scale) / 2 - 61 * scale
            y: (window.height - 1276 * scale) / 2 - 78 * scale
        Rectangle {
            objectName: "windowPanel"
            x: 61; y: 78; width: 978; height: 1276; radius: 72
            color: appTheme.frame
            gradient: Gradient {
                GradientStop { position: 0; color: Qt.lighter(appTheme.frame, 1.018) }
                GradientStop { position: 1; color: appTheme.frame }
            }
            border.width: 1 / stage.scale
            border.color: appTheme.border
            antialiasing: true
            Bevel { anchors.fill: parent; radius: 72; thickness: 1.5 }
        }
        MouseArea {
            objectName: "windowDragArea"
            x: 61; y: 78; width: 978; height: 72
            onPressed: window.startSystemMove()
        }
        Item {
            id: screens
            anchors.fill: parent
            transform: Translate { id: screenShift }
            HomePage { anchors.fill: parent; visible: window.currentPage === "home"; enabled: visible }
            HistoryPage { anchors.fill: parent; visible: window.currentPage === "history"; enabled: visible }
            StatisticsPage { id: statisticsPage; anchors.fill: parent; visible: window.currentPage === "statistics"; enabled: visible }
            SettingsPage { anchors.fill: parent; visible: window.currentPage === "settings"; enabled: visible }
        }
        Surface {
            id: toast
            x: (parent.width - width) / 2; y: 1340 - height
            width: Math.min(840, toastText.implicitWidth + 70); height: toastText.implicitHeight + 35
            radius: 24; visible: opacity > 0; opacity: 0
            Text {
                id: toastText
                anchors.centerIn: parent
                width: Math.min(770, implicitWidth)
                wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
                color: appTheme.ink; font.family: "Segoe UI"; font.pixelSize: 25
            }
            Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.InOutCubic } }
            Timer { id: toastTimer; interval: 2700; onTriggered: toast.opacity = 0 }
        }
        Rectangle {
            id: exitShade
            anchors.fill: parent; color: "#70000000"; visible: exitDialog.visible
            MouseArea { anchors.fill: parent }
        }
        Popup {
            id: exitDialog
            scale: appTheme.uiScale
            transformOrigin: Popup.TopLeft
            x: 210; y: 510; width: 680; height: 340
            modal: true; focus: true; closePolicy: Popup.CloseOnEscape
            background: Surface { radius: 40; }
            Text {
                x: 35; y: 30; width: 590
                text: "Завершить работу?"; color: appTheme.ink
                font.family: "Segoe UI"; font.pixelSize: 38; font.weight: Font.DemiBold
            }
            Text {
                x: 35; y: 95; width: 590; wrapMode: Text.Wrap
                text: "Текущая запись будет завершена и сохранена."
                color: appTheme.muted; font.family: "Segoe UI"; font.pixelSize: 28
            }
            Row {
                x: 30; y: 225; spacing: 20
                Repeater {
                    model: ["Отмена", "Завершить"]
                    delegate: SoftButton {
                        required property string modelData
                        required property int index
                        width: 295; height: 75; cornerRadius: 23
                        accessibleLabel: modelData
                        contentItem: Text {
                            text: modelData; color: appTheme.ink
                            font.family: "Segoe UI"; font.pixelSize: 29
                            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                        }
                        onActivated: { exitDialog.close(); if (index === 1) controller.confirmQuit() }
                    }
                }
            }
        }
    }
    }
    SequentialAnimation {
        id: transition
        onFinished: if (window.currentPage !== window.pendingPage) transition.start()
        ParallelAnimation {
            NumberAnimation { target: screens; property: "opacity"; to: 0; duration: 100; easing.type: Easing.InOutCubic }
            NumberAnimation { target: screenShift; property: "y"; from: 0; to: 8; duration: 100; easing.type: Easing.InOutCubic }
        }
        ScriptAction { script: { window.currentPage = window.pendingPage; screenShift.y = 10 } }
        ParallelAnimation {
            NumberAnimation { target: screens; property: "opacity"; to: 1; duration: 200; easing.type: Easing.InOutCubic }
            NumberAnimation { target: screenShift; property: "y"; to: 0; duration: 230; easing.type: Easing.InOutCubic }
        }
    }
    Connections {
        target: controller
        function onNavigationRequested(page) {
            if (["home", "history", "statistics", "settings"].indexOf(page) < 0) return
            window.pendingPage = page
            if (page !== window.currentPage && !transition.running) transition.start()
        }
        function onToastRequested(message) { toastText.text = message; toast.opacity = 1; toastTimer.restart() }
        function onExitConfirmationRequested() { exitDialog.open() }
    }
    Shortcut { sequence: "Escape"; enabled: window.currentPage !== "home" && !controller.capturingShortcut; onActivated: controller.navigate("home") }
    Shortcut { sequence: "Alt+edgeleft"; onActivated: controller.navigate("home") }
    Repeater {
        model: [Qt.LeftEdge | Qt.TopEdge, Qt.TopEdge, Qt.RightEdge | Qt.TopEdge, Qt.LeftEdge,
                Qt.RightEdge, Qt.LeftEdge | Qt.BottomEdge, Qt.BottomEdge, Qt.RightEdge | Qt.BottomEdge]
        delegate: MouseArea {
            required property int modelData
            objectName: "windowResize" + modelData
            property bool edgeleft: (modelData & Qt.LeftEdge) !== 0
            property bool edgeright: (modelData & Qt.RightEdge) !== 0
            property bool edgetop: (modelData & Qt.TopEdge) !== 0
            property bool edgebottom: (modelData & Qt.BottomEdge) !== 0
            readonly property bool corner: (edgeleft || edgeright) && (edgetop || edgebottom)
            readonly property int grip: corner ? 20 : 12
            property point pressPoint
            property rect pressGeometry
            x: edgeleft ? 0 : edgeright ? window.width - grip : 20
            y: edgetop ? 0 : edgebottom ? window.height - grip : 20
            width: edgeleft || edgeright ? grip : window.width - 40
            height: edgetop || edgebottom ? grip : window.height - 40
            cursorShape: corner ? (edgeleft === edgetop ? Qt.SizeFDiagCursor : Qt.SizeBDiagCursor)
                                : (edgeleft || edgeright ? Qt.SizeHorCursor : Qt.SizeVerCursor)
            preventStealing: true
            onPressed: function(mouse) {
                pressPoint = mapToGlobal(mouse.x, mouse.y)
                pressGeometry = Qt.rect(window.x, window.y, window.width, window.height)
            }
            onPositionChanged: function(mouse) {
                if (!pressed || !window.resizeGeometry) return
                const point = mapToGlobal(mouse.x, mouse.y)
                window.resizeGeometry.resize_from_drag(modelData, pressGeometry,
                    Qt.point(point.x - pressPoint.x, point.y - pressPoint.y))
            }
        }
    }
}
