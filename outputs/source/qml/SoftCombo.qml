import QtQuick
import QtQuick.Controls

Control {
    id: control
    property var model: []
    property int currentIndex: 0
    readonly property string displayText: currentIndex >= 0 && currentIndex < model.length ? model[currentIndex] : ""
    signal activated(int index)
    implicitWidth: 350
    implicitHeight: 56
    font.family: "Segoe UI"
    font.pixelSize: 31
    background: null
    contentItem: SoftButton {
        id: trigger
        objectName: "comboButton"
        cornerRadius: 18
        compact: true
        accessibleLabel: control.Accessible.name
        onActivated: menu.open()
        contentItem: Item {
            Text {
                x: 25; width: parent.width - 83; height: parent.height
                text: control.displayText
                font: control.font; color: appTheme.ink
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
            }
            Glyph {
                name: "chevron"; light: appTheme.dark
                width: 26; height: 26
                x: parent.width - width - 20; y: (parent.height - height) / 2
                rotation: menu.visible ? 180 : 0
                Behavior on rotation { NumberAnimation { duration: 200; easing.type: Easing.InOutCubic } }
            }
        }
        Keys.onDownPressed: { menu.open(); options.currentIndex = control.currentIndex; options.forceActiveFocus() }
        Keys.onUpPressed: { menu.open(); options.currentIndex = control.currentIndex; options.forceActiveFocus() }
    }
    Popup {
        id: menu
        objectName: "comboPopup"
        scale: appTheme.uiScale
        transformOrigin: Popup.TopLeft
        x: 0; y: control.height + 8
        width: control.width
        padding: 8
        focus: true
        implicitHeight: Math.min(options.contentHeight + padding * 2, 330)
        background: Surface { radius: 20 }
        contentItem: ListView {
            id: options
            clip: true
            model: control.model
            currentIndex: control.currentIndex
            boundsBehavior: Flickable.StopAtBounds
            delegate: SoftButton {
                required property var modelData
                required property int index
                objectName: "comboOption" + index
                width: options.width
                height: 62
                flat: true
                cornerRadius: 12
                accessibleLabel: String(modelData)
                onActivated: { control.activated(index); menu.close() }
                contentItem: Text {
                    text: String(modelData)
                    leftPadding: 12; rightPadding: 12
                    font: control.font
                    color: appTheme.ink
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                }
            }
            Keys.onReturnPressed: { control.activated(currentIndex); menu.close() }
            Keys.onEnterPressed: { control.activated(currentIndex); menu.close() }
            Keys.onEscapePressed: menu.close()
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
        }
        enter: Transition {
            ParallelAnimation {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 180; easing.type: Easing.InOutCubic }
                NumberAnimation { property: "scale"; from: appTheme.uiScale * 0.97; to: appTheme.uiScale; duration: 180; easing.type: Easing.InOutCubic }
            }
        }
        exit: Transition { NumberAnimation { property: "opacity"; to: 0; duration: 120; easing.type: Easing.InOutCubic } }
    }
    Accessible.role: Accessible.ComboBox
}
