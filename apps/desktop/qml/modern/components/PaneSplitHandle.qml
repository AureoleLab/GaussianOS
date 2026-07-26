import QtQuick

Item {
    id: root
    required property var theme
    property int orientation: Qt.Horizontal
    property bool interactive: true
    property bool emphasized: hover.hovered || drag.active

    signal dragStarted()
    signal dragMoved(real delta)
    signal dragFinished()
    signal resetRequested()

    implicitWidth: orientation === Qt.Horizontal ? theme.density.splitHandleExtent : 1
    implicitHeight: orientation === Qt.Vertical ? theme.density.splitHandleExtent : 1
    enabled: interactive
    activeFocusOnTab: interactive
    opacity: enabled ? 1 : 0.35
    scale: drag.active ? theme.motion.pressScale : 1

    Keys.onPressed: function(event) {
        var step = event.modifiers & Qt.ShiftModifier ? 24 : 8
        var delta = 0
        if (root.orientation === Qt.Horizontal) {
            if (event.key === Qt.Key_Left) delta = -step
            if (event.key === Qt.Key_Right) delta = step
        } else {
            if (event.key === Qt.Key_Up) delta = -step
            if (event.key === Qt.Key_Down) delta = step
        }
        if (delta !== 0) {
            root.dragStarted()
            root.dragMoved(delta)
            root.dragFinished()
            event.accepted = true
        }
    }

    Rectangle {
        anchors.centerIn: parent
        width: root.orientation === Qt.Horizontal ? 1 : parent.width
        height: root.orientation === Qt.Vertical ? 1 : parent.height
        color: root.emphasized ? theme.lineStrong : theme.line
        Behavior on color {
            ColorAnimation { duration: theme.motion.hoverDuration; easing.type: Easing.OutCubic }
        }
    }

    Rectangle {
        anchors.fill: parent
        anchors.margins: 1
        color: "transparent"
        border.width: root.activeFocus ? 1 : 0
        border.color: theme.focus
        radius: theme.radiusControl
    }

    HoverHandler {
        id: hover
        enabled: root.interactive
        cursorShape: root.orientation === Qt.Horizontal
            ? Qt.SizeHorCursor : Qt.SizeVerCursor
    }

    DragHandler {
        id: drag
        enabled: root.interactive
        target: null
        xAxis.enabled: root.orientation === Qt.Horizontal
        yAxis.enabled: root.orientation === Qt.Vertical
        onActiveChanged: {
            if (active)
                root.dragStarted()
            else
                root.dragFinished()
        }
        onTranslationChanged: {
            if (active)
                root.dragMoved(
                    root.orientation === Qt.Horizontal ? translation.x : translation.y
                )
        }
    }

    TapHandler {
        enabled: root.interactive
        acceptedButtons: Qt.LeftButton
        onDoubleTapped: root.resetRequested()
    }

    Behavior on scale {
        NumberAnimation { duration: theme.motion.pressDuration; easing.type: Easing.OutCubic }
    }
}
