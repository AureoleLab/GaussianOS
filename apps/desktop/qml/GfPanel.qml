import QtQuick

Rectangle {
    required property var tokens
    property bool raised: false
    property bool sunken: false
    color: sunken ? tokens.surfaceSunken : raised ? tokens.surfaceRaised : tokens.surface
    radius: tokens.radiusLarge
    border.width: 1
    border.color: tokens.border
}
