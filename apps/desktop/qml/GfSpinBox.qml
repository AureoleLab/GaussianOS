import QtQuick
import QtQuick.Controls

SpinBox {
    id: control
    required property var tokens
    editable: true
    implicitHeight: tokens.controlHeight
    font.family: tokens.uiFont
    font.pixelSize: tokens.typeBody
    leftPadding: 10
    rightPadding: 28
    opacity: enabled ? 1 : 0.42
    Behavior on opacity { NumberAnimation { duration: tokens.motionFast } }
    contentItem: TextInput {
        text: control.textFromValue(control.value, control.locale)
        color: control.enabled ? tokens.text : tokens.textDisabled
        font: control.font
        horizontalAlignment: Text.AlignRight
        verticalAlignment: Text.AlignVCenter
        readOnly: !control.editable
        validator: control.validator
        inputMethodHints: Qt.ImhFormattedNumbersOnly
        selectByMouse: true
    }
    up.indicator: Rectangle {
        x: control.width - width; y: 1; width: 26; height: (control.height - 2) / 2
        color: control.up.pressed ? tokens.controlPressed : control.up.hovered ? tokens.controlHover : "transparent"
        Behavior on color { ColorAnimation { duration: tokens.motionFast } }
        Text { anchors.centerIn: parent; text: "▴"; color: tokens.textSecondary; font.pixelSize: 9 }
    }
    down.indicator: Rectangle {
        x: control.width - width; y: control.height / 2; width: 26; height: (control.height - 2) / 2
        color: control.down.pressed ? tokens.controlPressed : control.down.hovered ? tokens.controlHover : "transparent"
        Behavior on color { ColorAnimation { duration: tokens.motionFast } }
        Text { anchors.centerIn: parent; text: "▾"; color: tokens.textSecondary; font.pixelSize: 9 }
    }
    background: Rectangle {
        radius: tokens.radiusSmall
        color: tokens.control
        border.width: 1
        border.color: control.activeFocus ? tokens.accent : tokens.border
        Behavior on border.color { ColorAnimation { duration: tokens.motionFast } }
    }
}
