import QtQuick
import QtQuick.Controls

Item {
    id: page
    SoftButton {
        objectName: "pauseButton"
        x: 119; y: 181; width: 142; height: 150
        glyph: controller.paused ? "play" : "pause"; iconSize: 73
        accessibleLabel: controller.paused ? "Продолжить диктовку" : "Приостановить диктовку"
        onActivated: controller.togglePause()
    }
    SoftButton {
        id: microphone
        objectName: "recordButton"
        x: 315; y: 159; width: 469; height: 198
        cornerRadius: 70; primary: true
        enabled: controller.canRecord || controller.phase === "starting"
        glyph: controller.phase === "recording" ? "" : "mic"
        iconSize: 132
        holdAction: true
        immediatePress: true
        accessibleLabel: "Запись"
        onPressReady: controller.recordPressed()
        onReleaseReady: controller.recordReleased()
        RecordingDots {
            objectName: "recordingDots"
            anchors.centerIn: parent
            width: 108; height: 52
            visible: controller.phase === "recording"
            running: visible && page.visible
        }
    }
    SoftButton {
        objectName: "settingsButton"
        x: 839; y: 181; width: 142; height: 150
        glyph: "settings"; iconSize: 82; accessibleLabel: "Настройки"
        onActivated: controller.navigate("settings")
    }
    Text {
        objectName: "recordingStatus"
        x: 115; y: 406; width: 870; height: 60
        text: controller.status
        font.family: "Segoe UI"; font.pixelSize: text.length > 45 ? 29 : 38
        color: appTheme.muted
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
    Surface {
        x: 97; y: 497; width: 906; height: 622; radius: 51
        Flickable {
            id: editorScroll
            x: 53; y: 53; width: 798; height: 450
            clip: true
            contentWidth: width
            contentHeight: editor.height
            boundsBehavior: Flickable.StopAtBounds
            TextArea.flickable: TextArea {
                id: editor
                objectName: "transcriptEditor"
                width: editorScroll.width
                text: controller.text
                wrapMode: TextEdit.Wrap
                selectByMouse: true
                persistentSelection: true
                color: appTheme.ink; selectionColor: appTheme.selection
                selectedTextColor: appTheme.ink
                font.family: "Segoe UI"; font.pixelSize: 48
                padding: 0
                background: null
                onTextChanged: if (text !== controller.text) controller.setText(text)
                Accessible.name: "Распознанный текст"
            }
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded; width: 10 }
        }
        SoftButton {
            objectName: "copyTranscriptButton"
            x: 792; y: 500; width: 88; height: 88
            flat: true; glyph: "copy"; iconSize: 61; cornerRadius: 22
            accessibleLabel: "Копировать текст"
            enabled: controller.text.length > 0
            onActivated: controller.copyText(controller.text)
        }
    }
    Surface {
        x: 90; y: 1162; width: 919; height: 141; radius: 72
        edge: appTheme.highlight
        Repeater {
            model: [{title: "История", icon: "history", page: "history"},
                    {title: "Статистика", icon: "statistics", page: "statistics"}]
            delegate: SoftButton {
                required property var modelData
                required property int index
                x: index * 459; y: 8; width: 459; height: 125
                flat: true; cornerRadius: 64
                accessibleLabel: modelData.title
                contentItem: Item {
                    Row {
                        anchors.centerIn: parent; spacing: 27
                        Glyph { name: modelData.icon; light: appTheme.dark; width: 80; height: 80 }
                        Text {
                            text: modelData.title; color: appTheme.ink
                            font.family: "Segoe UI"; font.pixelSize: 38; font.weight: Font.DemiBold
                            height: 80; verticalAlignment: Text.AlignVCenter
                        }
                    }
                }
                onActivated: controller.navigate(modelData.page)
            }
        }
    }
}
