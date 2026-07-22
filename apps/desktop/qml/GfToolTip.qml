import QtQuick
import QtQuick.Controls

Popup {
    id: root
    required property var tokens
    property string tipText: ""
    property bool requested: false
    x: parent ? Math.round((parent.width - width) / 2) : 0
    y: parent ? parent.height + 6 : 0
    width: tip.implicitWidth + 18
    height: 28
    padding: 0
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
    z: 10000

    onRequestedChanged: {
        if (requested) showDelay.restart()
        else { showDelay.stop(); close() }
    }
    Timer { id: showDelay; interval: 420; onTriggered: if (root.requested) root.open() }
    contentItem: Text {
        id: tip
        text: root.tipText
        color: root.tokens.text
        font.family: root.tokens.uiFont
        font.pixelSize: root.tokens.typeSmall
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
    background: Rectangle { color: root.tokens.surfaceRaised; border.color: root.tokens.border; radius: root.tokens.radiusSmall }
    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: root.tokens.motionFast }
            NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: root.tokens.motionNormal; easing.type: Easing.OutCubic }
        }
    }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: root.tokens.motionFast } }
}
