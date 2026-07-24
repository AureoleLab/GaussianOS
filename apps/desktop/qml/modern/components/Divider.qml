import QtQuick

Rectangle {
    required property var theme
    property bool vertical: false
    implicitWidth: vertical ? 1 : 20
    implicitHeight: vertical ? 20 : 1
    color: theme.lineSubtle
}
