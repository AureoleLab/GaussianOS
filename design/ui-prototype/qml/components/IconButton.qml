import QtQuick
import QtQuick.Controls

AbstractButton {
    id: root
    required property var theme
    required property var type
    property string iconName: "settings"
    property string toolTip: ""
    property bool selected: false
    property bool danger: false
    property bool prominent: false
    property bool muted: false
    property bool toggle: false

    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    implicitWidth: theme.density.iconButtonSize
    implicitHeight: theme.density.iconButtonSize
    Accessible.name: toolTip
    Accessible.role: Accessible.Button
    scale: root.down ? theme.motion.pressScale : 1

    background: Rectangle {
        radius: theme.radiusControl
        color: !root.enabled ? "transparent"
              : root.down ? theme.controlPressed
              : root.hovered ? theme.controlHover
              : root.selected ? theme.selected
              : "transparent"
        border.width: root.visualFocus ? 1 : 0
        border.color: theme.focus
        Behavior on color {
            ColorAnimation { duration: theme.motion.hoverDuration; easing.type: Easing.OutCubic }
        }
    }

    contentItem: Item {
        implicitWidth: theme.density.iconMajor
        implicitHeight: theme.density.iconMajor
        AppIcon {
            objectName: root.objectName.length > 0 ? root.objectName + "Glyph" : ""
            anchors.centerIn: parent
            name: root.iconName
            size: root.prominent ? theme.density.iconMajor : theme.density.iconDefault
            opacity: !root.toggle || root.selected ? 1 : 0.58
            scale: !root.toggle || root.selected ? 1 : 0.86
            color: !root.enabled ? theme.inkDisabled
                 : root.danger ? theme.ink
                 : root.hovered || root.down ? theme.ink
                 : root.selected ? theme.accent
                 : root.muted ? theme.inkTertiary
                 : theme.inkSecondary
            Behavior on color {
                ColorAnimation { duration: theme.motion.hoverDuration; easing.type: Easing.OutCubic }
            }
            Behavior on opacity {
                NumberAnimation {
                    duration: theme.motion.navigationSelectionDuration
                    easing.type: Easing.OutCubic
                }
            }
            Behavior on scale {
                NumberAnimation {
                    duration: theme.motion.navigationSelectionDuration
                    easing.type: Easing.BezierSpline
                    easing.bezierCurve: theme.motion.navigationCurve
                }
            }
        }
    }

    ToolTip.visible: root.hovered && root.toolTip.length > 0
    ToolTip.text: root.toolTip
    ToolTip.delay: 450

    Behavior on scale {
        NumberAnimation {
            duration: theme.motion.pressDuration
            easing.type: Easing.BezierSpline
            easing.bezierCurve: theme.motion.emphasizedCurve
        }
    }
    Behavior on implicitWidth {
        NumberAnimation { duration: theme.motion.densityDuration; easing.type: Easing.OutCubic }
    }
    Behavior on implicitHeight {
        NumberAnimation { duration: theme.motion.densityDuration; easing.type: Easing.OutCubic }
    }
}
