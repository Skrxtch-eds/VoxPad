import QtQuick
import QtQuick.Effects

Item {
    id: control
    property real radius: 50
    property color fill: appTheme.surface
    property color topFill: Qt.lighter(fill, 1.012)
    property color edge: appTheme.border
    property real edgeWidth: bevel ? 0.8 : 0
    property bool castsShadow: true
    property real hoverProgress: 0
    property bool bevel: true
    property color innerEdge: appTheme.bevelStart
    property color innerEdgeEnd: appTheme.bevelEnd
    default property alias content: body.data

    RectangularShadow {
        objectName: "restShadow"
        anchors.fill: panel
        offset.y: appTheme.shadowOffset
        radius: control.radius
        blur: appTheme.shadowBlur
        spread: 1
        color: appTheme.shadowColor
        cached: true
        opacity: 1 - control.hoverProgress
        visible: control.castsShadow && opacity > 0
    }
    RectangularShadow {
        objectName: "hoverShadow"
        anchors.fill: panel
        offset.y: appTheme.shadowOffset * 0.85
        radius: control.radius
        blur: appTheme.shadowBlur * 0.86
        spread: 0
        color: appTheme.shadowColor
        cached: true
        opacity: control.hoverProgress
        visible: control.castsShadow && opacity > 0
    }
    Rectangle {
        id: panel
        anchors.fill: parent
        radius: control.radius
        gradient: Gradient {
            GradientStop { position: 0; color: control.topFill }
            GradientStop { position: 1; color: control.fill }
        }
        border.width: control.edgeWidth
        border.color: control.edge
        antialiasing: true
        Bevel {
            anchors.fill: parent
            anchors.margins: 1
            radius: Math.max(0, control.radius - 1)
            thickness: 1.2
            topColor: control.innerEdge
            bottomColor: control.innerEdgeEnd
            visible: control.bevel
        }
    }
    Item { id: body; anchors.fill: parent }
}
