import QtQuick
import QtQuick.Controls

Item {
    PageHeader { title: "Настройки" }
    component SectionLabel: Text {
        x: 113; color: appTheme.secondaryInk
        font.family: "Segoe UI"; font.pixelSize: 35; font.weight: Font.DemiBold
    }
    component RowLabel: Text {
        x: 29; height: 75
        verticalAlignment: Text.AlignVCenter
        color: appTheme.ink; font.family: "Segoe UI"; font.pixelSize: 31
    }
    component Divider: Rectangle { x: 29; width: 849; height: 1.2; color: appTheme.border }
    SectionLabel { y: 353; text: "Запись" }
    Surface {
        x: 96; y: 408; width: 908; height: 235; radius: 31; RowLabel { y: 3; text: "Режим записи" }
        SoftCombo {
            objectName: "recordModeCombo"
            x: 532; y: 16
            model: ["Удержание", "Переключение"]
            currentIndex: controller.preferences.trigger_mode === "hold" ? 0 : 1
            onActivated: function(index) { controller.setSetting("trigger_mode", index === 0 ? "hold" : "toggle") }
            Accessible.name: "Режим записи"
        }
        Divider { y: 81 }
        RowLabel { y: 78; text: "Клавиша для записи" }
        SoftButton {
            objectName: "shortcutButton"
            x: 542; y: 91; width: 340; height: 55; cornerRadius: 17
            compact: true; accessibleLabel: "Изменить клавишу записи"
            contentItem: Item {
                Text {
                    x: 26; width: parent.width - 80; height: parent.height
                    text: controller.shortcutLabel
                    elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter
                    font.family: "Segoe UI"; font.pixelSize: controller.capturingShortcut ? 24 : 31; color: appTheme.ink
                }
                Glyph { x: parent.width - 50; y: 10; width: 34; height: 34; name: "edit"; light: appTheme.dark }
            }
            onActivated: if (controller.capturingShortcut) controller.cancelShortcut(); else controller.captureShortcut()
        }
        Divider { y: 155 }
        RowLabel { y: 153; text: "Звуки начала и конца" }
        SoftSwitch {
            objectName: "soundsSwitch"
            x: 790; y: 171; checked: controller.preferences.sounds
            Accessible.name: "Звуки начала и конца"
            onActivated: controller.setSetting("sounds", !checked)
        }
    }
    SectionLabel { y: 662; text: "Микрофон" }
    Surface {
        x: 96; y: 717; width: 908; height: 162; radius: 31; RowLabel { y: 3; text: "Устройство" }
        SoftCombo {
            objectName: "microphoneCombo"
            x: 532; y: 15
            model: controller.devices
            currentIndex: controller.deviceIndex
            onActivated: function(index) { controller.selectDevice(index) }
            Accessible.name: "Микрофон"
        }
        Divider { y: 81 }
        RowLabel { y: 77; text: "Автосмена микрофона" }
        SoftSwitch {
            objectName: "fallbackSwitch"
            x: 790; y: 96; checked: controller.preferences.microphone_fallback
            Accessible.name: "Автосмена микрофона"
            onActivated: controller.setSetting("microphone_fallback", !checked)
        }
    }
    SectionLabel { y: 898; text: "Оформление" }
    Surface {
        x: 96; y: 952; width: 908; height: 86; radius: 29; RowLabel { y: 4; text: "Тема" }
        SoftCombo {
            objectName: "themeCombo"
            x: 532; y: 15
            model: ["Светлая", "Тёмная"]
            currentIndex: controller.preferences.ui_theme === "dark" ? 1 : 0
            onActivated: function(index) { controller.setSetting("ui_theme", ["light", "dark"][index]) }
            Accessible.name: "Тема оформления"
        }
    }
    SectionLabel { y: 1056; text: "Приложение" }
    Surface {
        x: 96; y: 1111; width: 908; height: 157; radius: 31; RowLabel { y: 1; text: "Запуск с Windows" }
        SoftSwitch {
            objectName: "autostartSwitch"
            x: 790; y: 20; checked: controller.preferences.autostart
            Accessible.name: "Запуск с Windows"
            onActivated: controller.setSetting("autostart", !checked)
        }
        Divider { y: 78 }
        RowLabel { y: 77; text: "Работа в фоне" }
        SoftSwitch {
            objectName: "backgroundSwitch"
            x: 790; y: 93; checked: controller.preferences.background_mode
            Accessible.name: "Работа в фоне"
            onActivated: controller.setSetting("background_mode", !checked)
        }
    }
}
