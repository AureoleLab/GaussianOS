import QtQuick
import QtQuick.Controls

ProgressBar {
    id: control
    required property var tokens
    implicitHeight: 8
    background: Rectangle { radius: height / 2; color: tokens.surfaceSunken }
    contentItem: Item {
        implicitHeight: 8
        Rectangle {
            width: control.indeterminate ? parent.width * 0.34 : parent.width * control.visualPosition
            height: parent.height
            radius: height / 2
            color: tokens.accent
            x: control.indeterminate ? motion.phase * Math.max(0, parent.width - width) : 0
            Behavior on width { NumberAnimation { duration: tokens.motionNormal; easing.type: Easing.OutCubic } }
        }
    }
    QtObject { id: motion; property real phase: 0 }
    NumberAnimation { target: motion; property: "phase"; from: 0; to: 1; duration: 900; loops: Animation.Infinite; running: control.indeterminate }
}
