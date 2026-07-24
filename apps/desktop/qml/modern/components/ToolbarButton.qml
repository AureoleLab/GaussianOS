import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

AbstractButton {
    id: root
    required property var theme
    required property var type
    property string iconName: ""
    property bool primary: false
    property bool quiet: false
    property bool selected: false
    property bool danger: false
    property bool compact: false
    property bool prominentIcon: false
    property string toolTip: ""

    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    implicitHeight: compact ? theme.density.compactControlHeight : theme.density.controlHeight
    implicitWidth: contentRow.implicitWidth + (compact ? 18 : 22)
    leftPadding: compact ? 9 : 11
    rightPadding: compact ? 9 : 11
    Accessible.name: text
    Accessible.role: Accessible.Button
    ToolTip.visible: hovered && toolTip.length > 0
    ToolTip.text: toolTip
    ToolTip.delay: 500
    scale: root.down ? theme.motion.pressScale : 1

    background: Rectangle {
        radius: theme.radiusControl
        color: {
            if (!root.enabled || root.quiet && !root.hovered && !root.down && !root.selected) return "transparent"
            if (root.primary) return root.down ? theme.accentPressed : root.hovered ? theme.accentHover : theme.accent
            if (root.danger) return root.down ? theme.controlPressed : root.hovered ? theme.controlHover : "transparent"
            if (root.down) return theme.controlPressed
            if (root.selected) return theme.selectedHover
            if (root.hovered) return theme.controlHover
            return theme.control
        }
        border.width: root.visualFocus ? 1 : root.primary || root.quiet || root.danger ? 0 : 1
        border.color: root.visualFocus ? theme.focus : theme.line
        Behavior on color {
            ColorAnimation { duration: theme.motion.hoverDuration; easing.type: Easing.OutCubic }
        }
    }

    contentItem: Item {
        implicitWidth: contentRow.implicitWidth
        implicitHeight: contentRow.implicitHeight
        RowLayout {
            id: contentRow
            anchors.centerIn: parent
            spacing: 7
            AppIcon {
                visible: root.iconName.length > 0
                Layout.alignment: Qt.AlignVCenter
                name: root.iconName
                size: root.prominentIcon ? theme.density.iconMajor : theme.density.iconDefault
                color: !root.enabled ? theme.inkDisabled
                     : root.primary ? theme.inkOnAccent
                     : root.danger ? theme.inkSecondary
                     : root.selected ? theme.accent
                     : theme.inkSecondary
            }
            Text {
                Layout.alignment: Qt.AlignVCenter
                text: root.text
                color: !root.enabled ? theme.inkDisabled
                     : root.primary ? theme.inkOnAccent
                     : root.danger ? theme.ink
                     : theme.ink
                font.family: type.family
                font.pixelSize: type.buttonSize
                font.weight: root.primary ? type.semibold : type.medium
                verticalAlignment: Text.AlignVCenter
            }
        }
    }

    Behavior on scale {
        NumberAnimation {
            duration: theme.motion.pressDuration
            easing.type: Easing.BezierSpline
            easing.bezierCurve: theme.motion.emphasizedCurve
        }
    }
    Behavior on implicitHeight {
        NumberAnimation { duration: theme.motion.densityDuration; easing.type: Easing.OutCubic }
    }
}
