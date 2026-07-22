import QtQuick

Item {
    id: root
    required property var tokens
    property string status: "idle"
    property bool pulse: status === "running" || status === "loading"
    property color statusColor: status === "succeeded" ? tokens.success
        : status === "failed" ? tokens.error
        : status === "warning" || status === "interrupted" ? tokens.warning
        : status === "running" || status === "loading" ? tokens.accent
        : tokens.textDisabled
    implicitWidth: 12
    implicitHeight: 12

    Rectangle {
        anchors.centerIn: parent
        width: 8; height: 8; radius: 4
        color: root.statusColor
        Behavior on color { ColorAnimation { duration: root.tokens.motionNormal } }
    }
    Rectangle {
        anchors.centerIn: parent
        width: 8; height: 8; radius: 4
        color: "transparent"
        border.width: 1
        border.color: root.statusColor
        visible: root.pulse
        SequentialAnimation on scale {
            running: root.pulse; loops: Animation.Infinite
            NumberAnimation { from: 1; to: 1.85; duration: 700; easing.type: Easing.OutCubic }
            PauseAnimation { duration: 180 }
        }
        SequentialAnimation on opacity {
            running: root.pulse; loops: Animation.Infinite
            NumberAnimation { from: 0.7; to: 0; duration: 700 }
            PauseAnimation { duration: 180 }
        }
    }
}
