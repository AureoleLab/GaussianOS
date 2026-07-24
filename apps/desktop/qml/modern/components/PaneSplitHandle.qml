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

    Rectangle {
        anchors.centerIn: parent
        width: root.orientation === Qt.Horizontal ? 1 : parent.width
        height: root.orientation === Qt.Vertical ? 1 : parent.height
        color: root.emphasized ? theme.lineStrong : theme.line
        Behavior on color {
            ColorAnimation { duration: theme.motion.hoverDuration; easing.type: Easing.OutCubic }
        }
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
}
