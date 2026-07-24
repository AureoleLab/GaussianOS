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
    signal manageClicked()

    hoverEnabled: true
    implicitHeight: detail.length > 0 ? theme.density.listRowHeight : theme.density.compactRowHeight
    focusPolicy: Qt.StrongFocus
    leftPadding: 10
    rightPadding: 6
    scale: root.down ? theme.motion.pressScale : 1

    background: Rectangle {
        radius: theme.radiusItem
        color: root.selected ? theme.selected
             : root.down ? theme.controlPressed
             : root.hovered ? theme.controlHover
             : "transparent"
        border.width: root.visualFocus ? 1 : 0
        border.color: theme.focus
        Behavior on color {
            ColorAnimation {
                duration: theme.motion.navigationSelectionDuration
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
            color: root.selected ? theme.accent : theme.inkSecondary
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
            visible: root.detail.length > 0 && root.hovered
            theme: root.theme
            type: root.type
            iconName: "manage"
            toolTip: "Manage project"
            implicitWidth: theme.density.compactControlHeight
            implicitHeight: theme.density.compactControlHeight
            onClicked: root.manageClicked()
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
