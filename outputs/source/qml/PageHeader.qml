import QtQuick

Item {
    property string title: ""
    width: 1100; height: 300
    Text {
        x: 116; y: 205
        text: title
        font.family: "Segoe UI"; font.pixelSize: 73; font.weight: Font.DemiBold
        color: appTheme.ink
    }
    SoftButton {
        objectName: "backButton"
        x: 839; y: 181; width: 142; height: 150
        glyph: "back"; iconSize: 76
        accessibleLabel: "Назад"
        onActivated: controller.navigate("home")
    }
}
