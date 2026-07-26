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
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    scale: root.down ? theme.motion.pressScale : 1
    opacity: enabled ? 1 : 0.46

    background: Rectangle {
        radius: theme.radiusControl
        color: root.down ? theme.controlPressed : root.hovered ? theme.controlHover : theme.control
        border.width: root.activeFocus ? 2 : 1
        border.color: root.activeFocus ? theme.focus : theme.line
        Behavior on color {
            ColorAnimation { duration: theme.motion.hoverDuration; easing.type: Easing.OutCubic }
        }
        Behavior on border.color {
            ColorAnimation { duration: theme.motion.hoverDuration; easing.type: Easing.OutCubic }
        }
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
        color: root.enabled
            ? root.hovered || root.down ? theme.ink : theme.inkSecondary
            : theme.inkDisabled
        x: root.width - width - 10
        y: Math.round((root.height - height) / 2)
        Behavior on color {
            ColorAnimation { duration: theme.motion.hoverDuration; easing.type: Easing.OutCubic }
        }
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
        required property int index
        width: root.width - 8
        height: 32
        hoverEnabled: true
        focusPolicy: Qt.StrongFocus
        highlighted: hovered || root.highlightedIndex === delegateRoot.index
        scale: down ? theme.motion.pressScale : 1
        opacity: enabled ? 1 : 0.46
        contentItem: Text {
            text: root.textAt(delegateRoot.index)
            color: delegateRoot.enabled ? theme.ink : theme.inkDisabled
            font.family: type.family
            font.pixelSize: type.labelSize
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            radius: theme.radiusItem
            color: delegateRoot.down ? theme.controlPressed
                : delegateRoot.highlighted ? theme.selected : "transparent"
            border.width: delegateRoot.visualFocus ? 1 : 0
            border.color: theme.focus
            Behavior on color {
                ColorAnimation { duration: theme.motion.hoverDuration; easing.type: Easing.OutCubic }
            }
        }
        Behavior on scale {
            NumberAnimation { duration: theme.motion.pressDuration; easing.type: Easing.OutCubic }
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
