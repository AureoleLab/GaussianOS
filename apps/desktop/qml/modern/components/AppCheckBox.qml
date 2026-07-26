import QtQuick
import QtQuick.Controls

CheckBox {
    id: root
    required property var theme
    required property var type

    spacing: 9
    implicitHeight: theme.density.controlHeight
    font.family: type.family
    font.pixelSize: type.labelSize
    palette.text: theme.ink
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    opacity: enabled ? 1 : 0.46

    indicator: Rectangle {
        implicitWidth: 20
        implicitHeight: 20
        x: 0
        y: Math.round((root.height - height) / 2)
        radius: theme.radiusControl
        color: root.checked ? theme.accent
            : root.down ? theme.controlPressed
            : root.hovered ? theme.controlHover
            : theme.control
        border.width: root.activeFocus ? 2 : 1
        border.color: root.activeFocus ? theme.focus : root.checked ? theme.accent : theme.lineStrong
        scale: root.down ? theme.motion.pressScale : 1
        AppIcon {
            anchors.centerIn: parent
            name: "check"
            size: theme.density.iconMicro
            color: theme.inkOnAccent
            opacity: root.checked ? 1 : 0
            scale: root.checked ? 1 : theme.motion.pressScale
            Behavior on opacity {
                NumberAnimation { duration: theme.motion.stateDuration; easing.type: Easing.OutCubic }
            }
            Behavior on scale {
                NumberAnimation {
                    duration: theme.motion.stateDuration
                    easing.type: Easing.BezierSpline
                    easing.bezierCurve: theme.motion.emphasizedCurve
                }
            }
        }
        Behavior on color {
            ColorAnimation { duration: theme.motion.hoverDuration; easing.type: Easing.OutCubic }
        }
        Behavior on scale {
            NumberAnimation { duration: theme.motion.pressDuration; easing.type: Easing.OutCubic }
        }
    }

    contentItem: Text {
        leftPadding: root.indicator.width + root.spacing
        text: root.text
        color: root.enabled ? theme.ink : theme.inkDisabled
        font: root.font
        verticalAlignment: Text.AlignVCenter
    }
    Behavior on implicitHeight {
        NumberAnimation { duration: theme.motion.densityDuration; easing.type: Easing.OutCubic }
    }
}
