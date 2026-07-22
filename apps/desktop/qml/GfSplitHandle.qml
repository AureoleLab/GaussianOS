import QtQuick
import QtQuick.Controls

Rectangle {
    id: root
    required property var tokens
    property int splitOrientation: Qt.Horizontal
    readonly property bool handleHovered: SplitHandle.hovered
    readonly property bool handlePressed: SplitHandle.pressed
    signal resetRequested()
    implicitWidth: splitOrientation === Qt.Horizontal ? 7 : 40
    implicitHeight: splitOrientation === Qt.Horizontal ? 40 : 7
    color: "transparent"

    Rectangle {
        anchors.centerIn: parent
        width: root.splitOrientation === Qt.Horizontal ? 1 : Math.min(48, root.width * 0.35)
        height: root.splitOrientation === Qt.Horizontal ? Math.min(48, root.height * 0.35) : 1
        radius: 1
        color: root.handlePressed ? root.tokens.accent : root.handleHovered ? root.tokens.textTertiary : root.tokens.divider
        scale: root.handlePressed ? 1.18 : 1
        Behavior on color { ColorAnimation { duration: root.tokens.motionFast } }
        Behavior on scale { NumberAnimation { duration: root.tokens.motionFast } }
    }
    HoverHandler { cursorShape: root.splitOrientation === Qt.Horizontal ? Qt.SplitHCursor : Qt.SplitVCursor }
    TapHandler { acceptedButtons: Qt.LeftButton; onDoubleTapped: root.resetRequested() }
}
