import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root
    required property var theme
    required property var type
    property string text: "Ready"
    property string status: "neutral"

    implicitWidth: row.implicitWidth + 14
    implicitHeight: 22
    radius: theme.radiusPill
    color: status === "success" ? theme.successSoft
         : status === "warning" ? theme.warningSoft
         : status === "danger" ? theme.dangerSoft
         : status === "running" ? theme.accentSoft
         : theme.surfaceSunken

    RowLayout {
        id: row
        anchors.centerIn: parent
        spacing: 5
        AppIcon {
            name: root.status === "success" ? "check"
                : root.status === "warning" ? "warning"
                : root.status === "danger" ? "error"
                : root.status === "running" ? "activity"
                : "info"
            size: theme.density.iconMicro
            color: root.status === "success" ? theme.success
                 : root.status === "warning" ? theme.warning
                 : root.status === "danger" ? theme.danger
                 : root.status === "running" ? theme.accent
                 : theme.inkTertiary
        }
        Text {
            text: root.text
            color: root.status === "success" ? theme.success
                 : root.status === "warning" ? theme.warning
                 : root.status === "danger" ? theme.danger
                 : root.status === "running" ? theme.accent
                 : theme.inkSecondary
            font.family: type.family
            font.pixelSize: type.microSize
            font.weight: type.semibold
            font.letterSpacing: 0.2
        }
    }

    Behavior on color {
        ColorAnimation { duration: theme.motion.stateDuration; easing.type: Easing.OutCubic }
    }
    Behavior on scale {
        NumberAnimation {
            duration: theme.motion.stateDuration
            easing.type: Easing.BezierSpline
            easing.bezierCurve: theme.motion.emphasizedCurve
        }
    }
}
