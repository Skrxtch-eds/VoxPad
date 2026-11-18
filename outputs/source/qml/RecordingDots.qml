import QtQuick

Item {
    id: dots
    property bool running: false
    property color dotColor: appTheme.dark ? "#101010" : "#ffffff"
    Behavior on dotColor { ColorAnimation { duration: 320; easing.type: Easing.InOutCubic } }
    implicitWidth: 108
    implicitHeight: 52
    Repeater {
        model: 3
        delegate: Rectangle {
            id: dot
            required property int index
            objectName: "recordingDot" + index
            x: index * 38
            y: 20
            width: 20; height: 20; radius: 10
            color: dots.dotColor
            property real lift: 0
            transform: Translate { y: -dot.lift }
            SequentialAnimation {
                id: bob
                running: dots.running && dots.visible
                loops: Animation.Infinite
                PauseAnimation { duration: dot.index * 130 }
                NumberAnimation { target: dot; property: "lift"; from: 0; to: 10; duration: 190; easing.type: Easing.InOutCubic }
                NumberAnimation { target: dot; property: "lift"; from: 10; to: 0; duration: 190; easing.type: Easing.InOutCubic }
                PauseAnimation { duration: 520 - dot.index * 130 }
                onStopped: dot.lift = 0
            }
        }
    }
}
