import QtQuick

Item {
    id: glyph
    property string name: "mic"
    property bool light: false
    Image {
        anchors.fill: parent
        source: glyph.name ? "../assets/icons/" + glyph.name + ".png" : ""
        fillMode: Image.PreserveAspectFit
        sourceSize.width: width * 2; sourceSize.height: height * 2
        smooth: true; mipmap: true
        opacity: glyph.light ? 0 : 1
        Behavior on opacity { NumberAnimation { duration: 320; easing.type: Easing.InOutCubic } }
    }
    Image {
        anchors.fill: parent
        source: glyph.name ? "../assets/icons/" + glyph.name + "-white.png" : ""
        fillMode: Image.PreserveAspectFit
        sourceSize.width: width * 2; sourceSize.height: height * 2
        smooth: true; mipmap: true
        opacity: glyph.light ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 320; easing.type: Easing.InOutCubic } }
    }
}
