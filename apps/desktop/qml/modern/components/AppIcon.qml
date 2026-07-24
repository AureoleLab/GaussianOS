import QtQuick
import QtQuick.Effects

Item {
    id: root
    property string name: "project"
    required property color color
    property int size: 18
    implicitWidth: size
    implicitHeight: size

    Image {
        id: sourceImage
        anchors.fill: parent
        source: root.name.length > 0 ? "../icons/" + root.name + ".svg" : ""
        sourceSize.width: root.size * 2
        sourceSize.height: root.size * 2
        fillMode: Image.PreserveAspectFit
        smooth: true
        visible: false
    }

    MultiEffect {
        anchors.fill: sourceImage
        source: sourceImage
        colorization: 1
        colorizationColor: root.color
        antialiasing: true
    }
}
