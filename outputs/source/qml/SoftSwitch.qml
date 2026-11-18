import QtQuick
import QtQuick.Controls

SoftButton {
    id: control
    implicitWidth: 90
    implicitHeight: 46
    checkable: false
    background: Surface {
        objectName: "switchSurface"
        radius: control.height / 2
        fill: control.checked ? appTheme.switchOn : appTheme.switchOff
        topFill: fill
        hoverProgress: control.hoverProgress
        edge: "transparent"
        bevel: false
    }
    contentItem: Item {
        Rectangle {
            id: knob
            x: control.checked ? control.width - width - 4 : 4
            y: 4
            width: control.height - 8; height: width
            radius: width / 2
            color: appTheme.switchKnob
            antialiasing: true
            Behavior on x { NumberAnimation { duration: 200; easing.type: Easing.InOutCubic } }
        }
    }
    Accessible.role: Accessible.CheckBox
    Accessible.checkable: true
    Accessible.checked: checked
}
