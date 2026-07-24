import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Popup {
    id: root
    required property var theme
    required property var type
    property string title: ""
    property string subtitle: ""
    property int dialogWidth: 480
    default property alias bodyData: bodyColumn.data

    parent: Overlay.overlay
    x: Math.round((parent.width - width) / 2)
    property real restingY: Math.round((parent.height - height) / 2)
    y: restingY
    width: Math.min(dialogWidth, parent.width - 40)
    implicitHeight: shell.implicitHeight
    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape
    padding: 0

    Overlay.modal: Rectangle { color: theme.overlay }
    background: Rectangle {
        radius: theme.radiusDialog
        antialiasing: true
        color: theme.surfaceRaised
        border.width: 1
        border.color: theme.line
    }

    contentItem: ColumnLayout {
        id: shell
        spacing: 0
        RowLayout {
            Layout.fillWidth: true
            Layout.margins: 20
            Layout.bottomMargin: 14
            spacing: 12
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Text {
                    text: root.title
                    color: theme.ink
                    font.family: type.family
                    font.pixelSize: type.titleSize
                    font.weight: type.semibold
                }
                Text {
                    visible: root.subtitle.length > 0
                    Layout.fillWidth: true
                    text: root.subtitle
                    color: theme.inkSecondary
                    font.family: type.family
                    font.pixelSize: type.labelSize
                    lineHeight: type.bodyLine
                    wrapMode: Text.Wrap
                }
            }
            IconButton {
                theme: root.theme
                type: root.type
                iconName: "close"
                toolTip: "Close"
                onClicked: root.close()
            }
        }
        Divider { Layout.fillWidth: true; theme: root.theme }
        ColumnLayout {
            id: bodyColumn
            Layout.fillWidth: true
            Layout.margins: 20
            spacing: 14
        }
    }

    enter: Transition {
        ParallelAnimation {
            NumberAnimation {
                property: "opacity"; from: 0; to: 1
                duration: theme.motion.dialogDuration
                easing.type: Easing.OutCubic
            }
            NumberAnimation {
                property: "y"; from: root.restingY + theme.motion.smallTravel; to: root.restingY
                duration: theme.motion.dialogDuration
                easing.type: Easing.BezierSpline
                easing.bezierCurve: theme.motion.emphasizedCurve
            }
            NumberAnimation {
                property: "scale"; from: theme.motion.dialogScale; to: 1
                duration: theme.motion.dialogDuration
                easing.type: Easing.BezierSpline
                easing.bezierCurve: theme.motion.emphasizedCurve
            }
        }
    }
    exit: Transition {
        ParallelAnimation {
            NumberAnimation {
                property: "opacity"; from: 1; to: 0
                duration: theme.motion.dialogDuration
                easing.type: Easing.InCubic
            }
            NumberAnimation {
                property: "y"; from: root.restingY; to: root.restingY + theme.motion.smallTravel
                duration: theme.motion.dialogDuration
                easing.type: Easing.InCubic
            }
            NumberAnimation {
                property: "scale"; from: 1; to: theme.motion.dialogScale
                duration: theme.motion.dialogDuration
                easing.type: Easing.InCubic
            }
        }
    }
}
