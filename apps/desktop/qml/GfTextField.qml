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
    background: Rectangle {
        radius: tokens.radiusSmall
        color: tokens.control
        border.width: 1
        border.color: control.activeFocus ? tokens.accent : tokens.border
        Behavior on border.color { ColorAnimation { duration: tokens.motionFast } }
    }
}
