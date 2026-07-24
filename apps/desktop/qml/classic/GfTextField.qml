import QtQuick
import QtQuick.Controls

TextField {
    id: control
    required property var tokens
    implicitHeight: tokens.controlHeight
    color: enabled ? tokens.text : tokens.textDisabled
    placeholderTextColor: tokens.textTertiary
    selectionColor: tokens.accent
    selectedTextColor: "#ffffff"
    font.family: tokens.uiFont
    font.pixelSize: tokens.typeBody
    leftPadding: 11
    rightPadding: 11
    opacity: enabled ? 1 : 0.42
    Behavior on opacity { NumberAnimation { duration: tokens.motionFast } }
    background: Rectangle {
        radius: tokens.radiusSmall
        color: control.hovered ? tokens.controlHover : tokens.control
        border.width: 1
        border.color: control.activeFocus ? tokens.accent : tokens.border
        Behavior on color { ColorAnimation { duration: tokens.motionFast } }
        Behavior on border.color { ColorAnimation { duration: tokens.motionFast } }
    }
}
