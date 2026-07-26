import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: root
    required property var theme
    required property var type
    property string title: ""
    property string actionText: ""
    signal action()

    implicitHeight: theme.density.compactRowHeight
    Text {
        Layout.fillWidth: true
        text: root.title.toUpperCase()
        color: theme.inkTertiary
        font.family: type.family
        font.pixelSize: type.sectionHeaderSize
        font.weight: type.medium
        font.letterSpacing: 0.9
    }
    AbstractButton {
        id: actionButton
        visible: root.actionText.length > 0
        hoverEnabled: true
        focusPolicy: Qt.StrongFocus
        implicitHeight: theme.density.compactControlHeight
        implicitWidth: actionLabel.implicitWidth + 12
        scale: down ? theme.motion.pressScale : 1
        onClicked: root.action()
        background: Rectangle {
            radius: theme.radiusControl
            color: actionButton.down ? theme.controlPressed
                : actionButton.hovered ? theme.controlHover : "transparent"
            border.width: actionButton.visualFocus ? 1 : 0
            border.color: theme.focus
            Behavior on color {
                ColorAnimation { duration: theme.motion.hoverDuration; easing.type: Easing.OutCubic }
            }
        }
        contentItem: Text {
            id: actionLabel
            text: root.actionText
            color: actionButton.enabled ? theme.accent : theme.inkDisabled
            font.family: type.family
            font.pixelSize: type.sectionHeaderSize
            font.weight: type.medium
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        Behavior on scale {
            NumberAnimation { duration: theme.motion.pressDuration; easing.type: Easing.OutCubic }
        }
    }
}
