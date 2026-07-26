import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

AbstractButton {
    id: root
    required property var theme
    required property var type
    property string detail: ""
    property string iconName: "project"
    property bool selected: false
    property string status: ""
    readonly property bool pointerHovered: rowHover.hovered
    readonly property bool manageVisible: detail.length > 0 && (pointerHovered || selected)
    signal manageClicked()

    hoverEnabled: false
    implicitHeight: detail.length > 0 ? theme.density.listRowHeight : theme.density.compactRowHeight
    focusPolicy: Qt.StrongFocus
    leftPadding: 10
    rightPadding: 6
    scale: root.down ? theme.motion.pressScale : 1
    opacity: enabled ? 1 : 0.46

    background: Rectangle {
        radius: theme.radiusItem
        color: root.selected ? theme.selected
             : root.down ? theme.controlPressed
             : root.pointerHovered ? theme.controlHover
             : "transparent"
        border.width: root.visualFocus ? 1 : 0
        border.color: theme.focus
        Behavior on color {
            enabled: root.pointerHovered || root.selected || root.down
            ColorAnimation {
                duration: root.selected
                    ? theme.motion.navigationSelectionDuration
                    : theme.motion.hoverDuration
                easing.type: Easing.BezierSpline
                easing.bezierCurve: theme.motion.navigationCurve
            }
        }
    }

    contentItem: RowLayout {
        spacing: 10
        AppIcon {
            name: root.iconName
            size: theme.density.iconDefault
            color: root.selected ? theme.accent
                : root.pointerHovered ? theme.ink
                : theme.inkSecondary
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text {
                Layout.fillWidth: true
                text: root.text
                color: theme.ink
                font.family: type.family
                font.pixelSize: type.listPrimarySize
                font.weight: root.selected ? type.semibold : type.medium
                elide: Text.ElideRight
            }
            Text {
                visible: root.detail.length > 0
                Layout.fillWidth: true
                text: root.detail
                color: root.status === "warning" ? theme.warning : theme.inkTertiary
                font.family: type.family
                font.pixelSize: type.metadataSize
                elide: Text.ElideRight
            }
        }
        IconButton {
            visible: root.manageVisible
            opacity: root.manageVisible ? 1 : 0
            theme: root.theme
            type: root.type
            iconName: "manage"
            toolTip: "Manage project"
            implicitWidth: theme.density.compactControlHeight
            implicitHeight: theme.density.compactControlHeight
            onClicked: root.manageClicked()
            Behavior on opacity {
                NumberAnimation {
                    duration: theme.motion.hoverDuration
                    easing.type: Easing.OutCubic
                }
            }
        }
    }

    HoverHandler {
        id: rowHover
        enabled: root.enabled
        cursorShape: Qt.PointingHandCursor
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
