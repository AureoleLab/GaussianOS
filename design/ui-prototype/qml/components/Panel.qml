import QtQuick

Rectangle {
    required property var theme
    property bool raised: false
    radius: theme.radiusPanel
    antialiasing: true
    color: raised ? theme.surfaceRaised : theme.surface
    border.width: 1
    border.color: theme.lineSubtle
}
