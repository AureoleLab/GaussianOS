import QtQuick

Rectangle {
    id: panel
    required property var tokens
    property bool raised: false
    property bool sunken: false
    color: sunken ? tokens.surfaceSunken : raised ? tokens.surfaceRaised : tokens.surface
    radius: tokens.radiusLarge
    border.width: 1
    border.color: tokens.border
    opacity: visible ? 1 : 0
    scale: visible ? 1 : 0.992
    Behavior on color { ColorAnimation { duration: tokens.motionNormal } }
    Behavior on opacity { NumberAnimation { duration: tokens.motionNormal; easing.type: Easing.OutCubic } }
    Behavior on scale { NumberAnimation { duration: tokens.motionNormal; easing.type: Easing.OutCubic } }
}
