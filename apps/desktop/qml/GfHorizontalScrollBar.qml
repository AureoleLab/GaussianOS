import QtQuick
import QtQuick.Controls

ScrollBar {
    id: control
    required property var tokens
    orientation: Qt.Horizontal
    policy: ScrollBar.AlwaysOn
    interactive: true
    hoverEnabled: true
    implicitHeight: 12
    minimumSize: 0.08
    padding: 3

    background: Rectangle {
        implicitHeight: 8
        radius: 4
        color: control.tokens.surfaceSunken
        border.width: 1
        border.color: control.tokens.borderSubtle
    }
    contentItem: Rectangle {
        implicitHeight: 6
        radius: 3
        color: control.pressed ? control.tokens.accentPressed
            : control.hovered ? control.tokens.textSecondary
            : control.tokens.textTertiary
        Behavior on color { ColorAnimation { duration: control.tokens.motionFast } }
    }
}
