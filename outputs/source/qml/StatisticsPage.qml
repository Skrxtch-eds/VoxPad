import QtQuick
import QtQuick.Controls

Item {
    id: page
    objectName: "statisticsPage"
    property real countProgress: 0
    property int hoverIndex: -1
    property int selectedIndex: -1
    signal revealRequested()
    function spaced(number) { return Math.round(number).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ") }
    function duration(seconds) {
        var minutes = Math.floor(seconds / 60)
        var hours = Math.floor(minutes / 60)
        return hours > 0 ? hours + " ч " + minutes % 60 + " мин" : minutes + " мин"
    }
    function shortDuration(seconds) {
        var value = Math.round(seconds)
        return value >= 60 ? Math.floor(value / 60) + " мин " + value % 60 + " с" : value + " с"
    }
    function reveal() {
        counters.stop()
        countProgress = 0
        hoverIndex = -1
        selectedIndex = -1
        revealRequested()
        startCounters.restart()
    }
    onVisibleChanged: {
        if (visible) reveal()
        else { counters.stop(); startCounters.stop(); countProgress = 0; hoverIndex = -1 }
    }
    Connections {
        target: controller
        function onDataChanged() { if (page.visible) page.reveal() }
    }
    Timer { id: startCounters; interval: 24; onTriggered: counters.restart() }
    NumberAnimation {
        id: counters
        target: page; property: "countProgress"; from: 0; to: 1
        duration: 680; easing.type: Easing.InOutCubic
    }
    PageHeader { title: "Статистика" }
    Surface {
        x: 97; y: 378; width: 906; height: 440; radius: 51
        Text {
            x: 48; y: 30
            text: "За всё время"; color: appTheme.muted
            font.family: "Segoe UI"; font.pixelSize: 38
        }
        Row {
            x: 48; y: 82; spacing: 25
            Text {
                objectName: "wordCounter"
                text: page.spaced((controller.statistics.words || 0) * page.countProgress)
                font.family: "Segoe UI"; font.pixelSize: 112; font.weight: Font.Normal
                color: appTheme.ink
            }
            Text {
                text: "слов"; color: appTheme.ink
                font.family: "Segoe UI"; font.pixelSize: 43
                anchors.baseline: parent.children[0].baseline
            }
        }
        Text {
            x: 48; y: 256
            objectName: "dictationCounter"
            text: page.spaced((controller.statistics.dictations || 0) * page.countProgress)
            font.family: "Segoe UI"; font.pixelSize: 64; color: appTheme.ink
        }
        Text { x: 48; y: 339; text: "Диктовок"; font.family: "Segoe UI"; font.pixelSize: 36; color: appTheme.muted }
        Text {
            x: 486; y: 256
            text: page.duration((controller.statistics.audio_seconds || 0) * page.countProgress)
            font.family: "Segoe UI"; font.pixelSize: 63; color: appTheme.ink
        }
        Text { x: 486; y: 339; text: "Записи"; font.family: "Segoe UI"; font.pixelSize: 36; color: appTheme.muted }
    }
    Surface {
        id: chart
        x: 97; y: 847; width: 906; height: 449; radius: 51
        property real peak: Math.max(1, ...controller.daily.map(function(day) { return day.words }))
        Text {
            x: 48; y: 30; text: "Слова за 7 дней"
            color: appTheme.ink; font.family: "Segoe UI"; font.pixelSize: 43; font.weight: Font.DemiBold
        }
        Text {
            x: 590; y: 40; width: 270; horizontalAlignment: Text.AlignRight
            text: controller.dateRange; color: appTheme.muted
            font.family: "Segoe UI"; font.pixelSize: 34
        }
        Repeater {
            model: controller.daily
            delegate: Item {
                id: column
                required property var modelData
                required property int index
                property real revealProgress: 0
                property bool selected: page.selectedIndex === index || (page.selectedIndex < 0 && index === 6)
                x: 52 + index * 117.3; y: 135; width: 98; height: 258
                Rectangle {
                    id: bar
                    objectName: "dayBar" + column.index
                    anchors.bottom: parent.bottom; anchors.bottomMargin: 50
                    width: 98
                    height: (column.modelData.words / chart.peak) * 190 * column.revealProgress
                    radius: 17
                    color: column.selected ? appTheme.chartSelected : appTheme.chartBar
                    antialiasing: true
                    scale: barMotion.scaleValue
                    transformOrigin: Item.Bottom
                    Behavior on color { enabled: !appTheme.transitioning; ColorAnimation { duration: 180; easing.type: Easing.InOutCubic } }
                }
                Text {
                    y: 219; width: parent.width
                    text: column.modelData.label
                    color: appTheme.secondaryInk
                    font.family: "Segoe UI"; font.pixelSize: 34
                    horizontalAlignment: Text.AlignHCenter
                }
                HoverHandler {
                    id: hover
                    cursorShape: Qt.PointingHandCursor
                    onHoveredChanged: if (hovered) page.hoverIndex = column.index; else if (page.hoverIndex === column.index) page.hoverIndex = -1
                }
                ButtonMotion {
                    id: barMotion
                    hovered: hover.hovered
                    onActivated: page.selectedIndex = page.selectedIndex === column.index ? -1 : column.index
                }
                TapHandler {
                    id: press
                    onPressedChanged: if (pressed) barMotion.press(); else barMotion.release()
                    onTapped: barMotion.click()
                    onCanceled: barMotion.cancel()
                }
                Accessible.role: Accessible.Button
                Accessible.name: modelData.dateLabel + ": " + modelData.words + " слов"
                Connections { target: page; function onRevealRequested() { column.revealProgress = 0; grow.restart() } }
                SequentialAnimation {
                    id: grow
                    PauseAnimation { duration: 24 + column.index * 32 }
                    NumberAnimation {
                        target: column; property: "revealProgress"; from: 0; to: 1
                        duration: 640; easing.type: Easing.InOutCubic
                    }
                }
                Component.onCompleted: if (page.visible) grow.start()
            }
        }
        Surface {
            id: tooltip
            property int dayIndex: page.hoverIndex >= 0 ? page.hoverIndex : page.selectedIndex
            property var day: dayIndex >= 0 && dayIndex < controller.daily.length ? controller.daily[dayIndex] : ({})
            x: Math.max(25, Math.min(510, 52 + dayIndex * 117.3 - 350)); y: 83
            width: 368; height: 202; radius: 30
            opacity: dayIndex >= 0 ? 1 : 0
            visible: opacity > 0
            scale: dayIndex >= 0 ? 1 : 0.96
            Behavior on opacity { NumberAnimation { duration: 150; easing.type: Easing.InOutCubic } }
            Behavior on scale { NumberAnimation { duration: 180; easing.type: Easing.InOutCubic } }
            Text {
                x: 30; y: 16; text: tooltip.day.dateLabel || ""
                font.family: "Segoe UI"; font.pixelSize: 30; font.weight: Font.DemiBold; color: appTheme.ink
            }
            Repeater {
                model: ["Слов", "Диктовок", "Записи"]
                delegate: Item {
                    required property string modelData
                    required property int index
                    x: 30; y: 66 + index * 39; width: 310; height: 38
                    Text { text: modelData; font.family: "Segoe UI"; font.pixelSize: 28; color: appTheme.muted }
                    Text {
                        anchors.right: parent.right
                        text: index === 0 ? (tooltip.day.words || 0) : index === 1 ? (tooltip.day.dictations || 0) : page.shortDuration(tooltip.day.audio_seconds || 0)
                        font.family: "Segoe UI"; font.pixelSize: 28; color: appTheme.ink
                    }
                }
            }
        }
    }
}
