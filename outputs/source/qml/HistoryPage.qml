import QtQuick
import QtQuick.Controls

Item {
    id: page
    PageHeader { title: "История" }
    Surface {
        x: 97; y: 378; width: 906; height: 926; radius: 51
        ListView {
            id: list
            objectName: "historyList"
            x: 40; y: 39; width: 838; height: 847
            clip: true
            model: controller.history
            boundsBehavior: Flickable.StopAtBounds
            spacing: 0
            cacheBuffer: 400
            delegate: Item {
                id: entry
                required property var modelData
                required property int index
                width: list.width - 18
                height: Math.max(137, historyText.implicitHeight + (historyText.lineCount >= 3 ? 49 : 70))
                Text {
                    id: historyText
                    x: 0; y: entry.index === 0 ? 15 : 35; width: 610
                    text: entry.modelData.text
                    textFormat: Text.PlainText
                    color: appTheme.ink
                    font.family: "Segoe UI"; font.pixelSize: 43
                    wrapMode: Text.Wrap
                }
                SoftButton {
                    x: 635; y: entry.index === 0 ? 9 : 29; width: 78; height: 84
                    flat: true; glyph: "copy"; iconSize: 60; cornerRadius: 22
                    accessibleLabel: "Копировать запись"
                    onActivated: controller.copyText(entry.modelData.text)
                }
                SoftButton {
                    x: 734; y: entry.index === 0 ? 9 : 29; width: 78; height: 84
                    flat: true; glyph: "delete"; iconSize: 59; cornerRadius: 22
                    accessibleLabel: "Удалить запись"
                    onActivated: controller.deleteHistory(entry.modelData.id)
                }
                Rectangle { x: 1; y: parent.height - 1; width: 819; height: 1.3; color: appTheme.border }
            }
            remove: Transition {
                ParallelAnimation {
                    NumberAnimation { property: "opacity"; to: 0; duration: 150; easing.type: Easing.InOutCubic }
                    NumberAnimation { property: "x"; to: -24; duration: 180; easing.type: Easing.InOutCubic }
                }
            }
            displaced: Transition { NumberAnimation { properties: "x,y"; duration: 230; easing.type: Easing.InOutCubic } }
            ScrollBar.vertical: ScrollBar {
                id: scrollbar
                width: 13; policy: ScrollBar.AsNeeded
                contentItem: Rectangle {
                    implicitWidth: 12; radius: 7
                    color: scrollbar.pressed ? Qt.darker(appTheme.scrollbar, 1.3) : scrollbar.hovered ? Qt.darker(appTheme.scrollbar, 1.15) : appTheme.scrollbar
                    opacity: scrollbar.size < 1 ? 1 : 0
                    Behavior on color { enabled: !appTheme.transitioning; ColorAnimation { duration: 150; easing.type: Easing.InOutCubic } }
                }
                background: Rectangle { radius: 7; color: appTheme.track }
            }
        }
        Text {
            anchors.centerIn: parent
            visible: list.count === 0
            text: "История пока пуста"
            font.family: "Segoe UI"; font.pixelSize: 36; color: appTheme.muted
        }
    }
}
