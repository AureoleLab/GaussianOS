import QtQuick
import QtQuick.Layouts

RowLayout {
    id: root
    required property var theme
    required property var type
    property string title: ""
    property string actionText: ""
    signal action()

    implicitHeight: theme.density.compactRowHeight
    Text {
        Layout.fillWidth: true
        text: root.title.toUpperCase()
        color: theme.inkTertiary
        font.family: type.family
        font.pixelSize: type.sectionHeaderSize
        font.weight: type.medium
        font.letterSpacing: 0.9
    }
    Text {
        visible: root.actionText.length > 0
        text: root.actionText
        color: theme.accent
        font.family: type.family
        font.pixelSize: type.sectionHeaderSize
        font.weight: type.medium
        TapHandler { onTapped: root.action() }
    }
}
