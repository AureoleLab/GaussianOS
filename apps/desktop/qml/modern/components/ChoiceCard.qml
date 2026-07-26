import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

AbstractButton {
    id: root
    required property var theme
    required property var type
    property bool selected: false
    property int contentMargin: 14
    default property alias cardData: cardContent.data

    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    implicitHeight: 132
    scale: down ? theme.motion.pressScale : 1
    opacity: root.enabled ? 1 : 0.46

    background: Rectangle {
        radius: theme.radiusPanel
        antialiasing: true
        color: root.down ? theme.controlPressed
            : root.selected && root.hovered ? theme.selectedHover
            : root.selected ? theme.accentSoft
            : root.hovered ? theme.controlHover
            : theme.surface
        border.width: root.visualFocus ? 2 : 1
        border.color: root.visualFocus ? theme.focus
            : root.selected ? theme.accent
            : root.hovered ? theme.lineStrong
            : theme.line
        Behavior on color {
            ColorAnimation { duration: theme.motion.hoverDuration; easing.type: Easing.OutCubic }
        }
        Behavior on border.color {
            ColorAnimation { duration: theme.motion.hoverDuration; easing.type: Easing.OutCubic }
        }
    }

    contentItem: ColumnLayout {
        id: cardContent
        spacing: 6
    }

    leftPadding: contentMargin
    rightPadding: contentMargin
    topPadding: contentMargin
    bottomPadding: contentMargin

    Behavior on scale {
        NumberAnimation {
            duration: theme.motion.pressDuration
            easing.type: Easing.BezierSpline
            easing.bezierCurve: theme.motion.emphasizedCurve
        }
    }
}
