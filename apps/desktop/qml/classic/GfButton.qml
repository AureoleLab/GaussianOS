import QtQuick
import QtQuick.Controls

Control {
    id: control
    required property var tokens
    property string text: ""
    property string iconText: ""
    property bool primary: false
    property bool quiet: false
    property bool compact: false
    property bool loading: false
    property string toolTip: text
    signal clicked()

    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    implicitHeight: compact ? tokens.compactHeight : tokens.controlHeight
    implicitWidth: Math.max(70, label.implicitWidth + (iconText ? 38 : 24))
    opacity: enabled ? 1 : 0.42
    scale: mouse.pressed ? 0.985 : 1.0
    transformOrigin: Item.Center
    Behavior on opacity { NumberAnimation { duration: tokens.motionFast } }
    Behavior on scale { NumberAnimation { duration: tokens.motionFast; easing.type: Easing.OutCubic } }
    Accessible.role: Accessible.Button
    Accessible.name: text

    background: Rectangle {
        radius: tokens.radiusSmall
        color: {
            if (control.primary) return mouse.pressed ? tokens.primaryPressed : mouse.containsMouse ? tokens.primaryHover : tokens.primaryControl
            if (control.quiet) return mouse.pressed ? tokens.controlPressed : mouse.containsMouse ? tokens.controlHover : "transparent"
            return mouse.pressed ? tokens.controlPressed : mouse.containsMouse ? tokens.controlHover : tokens.control
        }
        border.width: control.quiet && !control.activeFocus ? 0 : 1
        border.color: control.activeFocus ? tokens.accent : (control.primary ? tokens.border : tokens.border)
        Behavior on color { ColorAnimation { duration: tokens.motionFast } }
        Behavior on border.color { ColorAnimation { duration: tokens.motionFast } }
    }

    contentItem: Item {
        implicitWidth: contentRow.implicitWidth
        implicitHeight: contentRow.implicitHeight
        Row {
            id: contentRow
            anchors.centerIn: parent
            spacing: 7
            Text {
                visible: control.iconText !== "" || control.loading
                text: control.loading ? "◌" : control.iconText
                color: control.primary ? "#ffffff" : control.tokens.textSecondary
                font.family: control.tokens.uiFont
                font.pixelSize: control.tokens.typeBody
                anchors.verticalCenter: parent.verticalCenter
                RotationAnimator on rotation { running: control.loading; from: 0; to: 360; loops: Animation.Infinite; duration: 900 }
            }
            Text {
                id: label
                text: control.text
                color: control.primary ? "#ffffff" : control.tokens.text
                font.family: control.tokens.uiFont
                font.pixelSize: control.tokens.typeBody
                font.weight: control.primary ? Font.Medium : Font.Normal
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        enabled: control.enabled
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: control.clicked()
    }
    GfToolTip { tokens: control.tokens; tipText: control.toolTip; requested: mouse.containsMouse && control.toolTip !== "" && control.enabled }
    Keys.onSpacePressed: if (enabled) clicked()
    Keys.onReturnPressed: if (enabled) clicked()
}
