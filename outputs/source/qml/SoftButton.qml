import QtQuick
import QtQuick.Controls

AbstractButton {
    id: control
    property string glyph: ""
    property real iconSize: 62
    property real cornerRadius: 45
    property bool flat: false
    property bool primary: false
    property bool lightIcon: primary ? !appTheme.dark : appTheme.dark
    property bool compact: false
    property bool holdAction: false
    property bool immediatePress: false
    readonly property real hoverProgress: motion.amount
    signal activated()
    signal pressReady()
    signal releaseReady()
    property string accessibleLabel: text
    implicitWidth: 142
    implicitHeight: 150
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    Accessible.name: accessibleLabel
    scale: motion.scaleValue
    opacity: enabled ? 1 : 0.46
    onPressed: motion.press()
    onReleased: motion.release()
    onClicked: motion.click()
    onCanceled: motion.cancel()
    ButtonMotion {
        id: motion
        hovered: control.hovered
        holdAction: control.holdAction
        immediatePress: control.immediatePress
        onActivated: control.activated()
        onPressReady: control.pressReady()
        onReleaseReady: control.releaseReady()
    }
    Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.InOutCubic } }
    background: Surface {
        radius: control.cornerRadius
        objectName: "buttonSurface"
        fill: control.primary ? appTheme.primary : control.flat ? "transparent" : appTheme.surface
        topFill: control.primary ? Qt.lighter(fill, 1.8) : Qt.lighter(fill, 1.012)
        edge: control.flat ? "transparent" : control.primary ? appTheme.primaryEdge : control.compact ? appTheme.controlBorder : appTheme.highlight
        castsShadow: !control.flat && !control.compact
        hoverProgress: motion.amount
        bevel: !control.flat && !control.compact
        edgeWidth: control.flat ? 0 : control.compact ? 1 : 0.8
        innerEdge: control.primary ? appTheme.primaryBevel : appTheme.highlight
        innerEdgeEnd: control.primary ? appTheme.primaryEdge : appTheme.bevelEnd
    }
    contentItem: Item {
        Glyph {
            anchors.centerIn: parent
            width: control.iconSize; height: control.iconSize
            name: control.glyph
            light: control.lightIcon
            visible: control.glyph !== ""
        }
    }
    Rectangle {
        objectName: "keyboardFocusRing"
        anchors.fill: parent
        radius: control.cornerRadius
        color: "transparent"
        border.color: appTheme.muted
        border.width: 2
        visible: control.activeFocus && control.focusReason !== Qt.MouseFocusReason
    }
    HoverHandler { cursorShape: Qt.PointingHandCursor }
}
