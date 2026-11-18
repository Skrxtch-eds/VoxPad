import QtQuick

Item {
    id: motion
    property bool hovered: false
    property bool holdAction: false
    property bool immediatePress: false
    property real amount: 0
    readonly property real scaleValue: 1 + 0.03 * amount
    property bool _cycle: false
    property bool _clickPending: false
    property bool _pressPending: false
    property bool _pressDelivered: false
    property bool _releasePending: false
    signal activated()
    signal pressReady()
    signal releaseReady()

    function move(target, duration) {
        travel.stop()
        travel.to = target
        travel.duration = duration
        if (Math.abs(amount - target) < 0.0001) {
            amount = target
            deliver()
        } else travel.start()
    }
    function press() {
        _cycle = true
        _clickPending = false
        _releasePending = false
        _pressPending = holdAction
        _pressDelivered = false
        move(0, appTheme.pressDuration)
        if (immediatePress) deliver()
    }
    function release() {
        _releasePending = true
        if (_pressDelivered) {
            _pressDelivered = false
            _releasePending = false
            releaseReady()
        }
        if (!hovered) _cycle = false
    }
    function click() {
        if (holdAction) return
        _clickPending = true
        if (!travel.running) deliver()
    }
    function cancel() {
        _clickPending = false
        _pressPending = false
        release()
        if (!hovered) _cycle = false
    }
    function deliver() {
        if (_pressPending) {
            _pressPending = false
            _pressDelivered = true
            pressReady()
            if (_releasePending) release()
        }
        if (_clickPending) {
            _clickPending = false
            activated()
            if (!hovered) _cycle = false
        }
    }
    onHoveredChanged: {
        if (!hovered) _cycle = false
        if (!_cycle && !_clickPending && !_pressPending)
            move(hovered ? 1 : 0, hovered ? appTheme.hoverDuration : appTheme.leaveDuration)
    }
    NumberAnimation {
        id: travel
        target: motion; property: "amount"
        easing.type: Easing.InOutCubic
        onFinished: motion.deliver()
    }
}
