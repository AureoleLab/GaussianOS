import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ComboBox {
    id: root
    required property var theme
    required property var type

    implicitHeight: theme.density.controlHeight
    leftPadding: 11
    rightPadding: 30
    font.family: type.family
    font.pixelSize: type.labelSize
    palette.text: theme.ink

    background: Rectangle {
        radius: theme.radiusControl
        color: root.down ? theme.controlPressed : root.hovered ? theme.controlHover : theme.control
        border.width: root.activeFocus ? 2 : 1
        border.color: root.activeFocus ? theme.focus : theme.line
    }
    contentItem: Text {
        leftPadding: 0
        text: root.displayText
        color: root.enabled ? theme.ink : theme.inkDisabled
        font: root.font
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: AppIcon {
        name: "chevron-down"
        size: theme.density.iconMicro
        color: theme.inkSecondary
        x: root.width - width - 10
        y: Math.round((root.height - height) / 2)
    }
    popup: Popup {
        id: popupMenu
        property real restingY: root.height + 4
        y: restingY
        width: root.width
        implicitHeight: contentItem.implicitHeight + 8
        padding: 4
        transformOrigin: Item.Top
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: root.popup.visible ? root.delegateModel : null
            currentIndex: root.highlightedIndex
        }
        background: Rectangle {
            radius: theme.radiusPanel
            antialiasing: true
            color: theme.surfaceRaised
            border.width: 1
            border.color: theme.line
        }
        enter: Transition {
            ParallelAnimation {
                NumberAnimation {
                    property: "opacity"; from: 0; to: 1
                    duration: theme.motion.menuDuration
                    easing.type: Easing.OutCubic
                }
                NumberAnimation {
                    property: "scale"; from: theme.motion.dialogScale; to: 1
                    duration: theme.motion.menuDuration
                    easing.type: Easing.BezierSpline
                    easing.bezierCurve: theme.motion.emphasizedCurve
                }
                NumberAnimation {
                    property: "y"; from: popupMenu.restingY - theme.motion.smallTravel; to: popupMenu.restingY
                    duration: theme.motion.menuDuration
                    easing.type: Easing.BezierSpline
                    easing.bezierCurve: theme.motion.emphasizedCurve
                }
            }
        }
        exit: Transition {
            ParallelAnimation {
                NumberAnimation {
                    property: "opacity"; from: 1; to: 0
                    duration: theme.motion.menuDuration
                    easing.type: Easing.InCubic
                }
                NumberAnimation {
                    property: "scale"; from: 1; to: theme.motion.dialogScale
                    duration: theme.motion.menuDuration
                    easing.type: Easing.InCubic
                }
            }
        }
    }
    delegate: ItemDelegate {
        id: delegateRoot
        required property var model
        width: root.width - 8
        height: 32
        highlighted: root.highlightedIndex === index
        contentItem: Text {
            text: model[root.textRole] || modelData
            color: theme.ink
            font.family: type.family
            font.pixelSize: type.labelSize
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            radius: theme.radiusItem
            color: delegateRoot.highlighted ? theme.selected : "transparent"
        }
    }
    Behavior on implicitHeight {
        NumberAnimation { duration: theme.motion.densityDuration; easing.type: Easing.OutCubic }
    }
}
