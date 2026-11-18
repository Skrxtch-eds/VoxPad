import QtQuick
import QtQuick.Shapes

Shape {
    id: bevel
    property real radius: 30
    property real thickness: 1.2
    property color topColor: appTheme.bevelStart
    property color bottomColor: appTheme.bevelEnd
    preferredRendererType: Shape.CurveRenderer
    ShapePath {
        strokeWidth: -1
        fillRule: ShapePath.OddEvenFill
        fillGradient: LinearGradient {
            x1: 0; y1: 0; x2: bevel.width; y2: bevel.height
            GradientStop { position: 0; color: bevel.topColor }
            GradientStop { position: 0.25; color: bevel.topColor }
            GradientStop { position: 1; color: bevel.bottomColor }
        }
        PathRectangle { width: bevel.width; height: bevel.height; radius: bevel.radius }
        PathRectangle {
            x: bevel.thickness; y: bevel.thickness
            width: Math.max(0, bevel.width - bevel.thickness * 2)
            height: Math.max(0, bevel.height - bevel.thickness * 2)
            radius: Math.max(0, bevel.radius - bevel.thickness)
        }
    }
}
