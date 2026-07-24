import QtQuick
import QtQuick.Controls

TextField {
    id: root
    required property var theme
    required property var type

    implicitHeight: theme.density.controlHeight
    leftPadding: 11
    rightPadding: 11
    selectByMouse: true
    color: theme.ink
    selectionColor: theme.accentSoft
    selectedTextColor: theme.ink
    placeholderTextColor: theme.inkTertiary
    font.family: type.family
    font.pixelSize: type.labelSize
    background: Rectangle {
        radius: theme.radiusControl
        color: root.enabled ? theme.control : theme.surfaceSunken
        border.width: root.activeFocus ? 2 : 1
        border.color: root.activeFocus ? theme.focus : theme.line
    }
    Behavior on implicitHeight {
        NumberAnimation { duration: theme.motion.densityDuration; easing.type: Easing.OutCubic }
    }
}
