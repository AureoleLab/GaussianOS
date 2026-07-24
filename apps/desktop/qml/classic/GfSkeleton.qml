import QtQuick

Rectangle {
    id: root
    required property var tokens
    property bool running: visible
    color: tokens.shimmerBase
    radius: tokens.radiusSmall
    clip: true

    Rectangle {
        width: Math.max(80, root.width * 0.36)
        height: root.height * 1.6
        y: -root.height * 0.3
        opacity: root.running ? 0.72 : 0
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: "transparent" }
            GradientStop { position: 0.5; color: root.tokens.shimmerHighlight }
            GradientStop { position: 1.0; color: "transparent" }
        }
        NumberAnimation on x {
            running: root.running
            from: -width
            to: root.width
            duration: 1150
            loops: Animation.Infinite
            easing.type: Easing.InOutSine
        }
        Behavior on opacity { NumberAnimation { duration: root.tokens.motionNormal } }
    }
}
