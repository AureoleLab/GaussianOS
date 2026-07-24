import QtQuick
import QtQuick.Controls

ComboBox {
    id: control
    required property var tokens
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    implicitHeight: tokens.controlHeight
    font.family: tokens.uiFont
    font.pixelSize: tokens.typeBody
    leftPadding: 12
    rightPadding: 30
    opacity: enabled ? 1 : 0.42
    scale: pressed ? 0.99 : 1
    Behavior on opacity { NumberAnimation { duration: tokens.motionFast } }
    Behavior on scale { NumberAnimation { duration: tokens.motionFast; easing.type: Easing.OutCubic } }

    contentItem: Text {
        text: control.displayText
        color: control.enabled ? tokens.text : tokens.textDisabled
        font: control.font
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: Text {
        text: "⌄"
        color: tokens.textSecondary
        font.family: tokens.uiFont
        font.pixelSize: 15
        x: control.width - width - 11
        y: (control.height - height) / 2 - 1
    }
    background: Rectangle {
        radius: tokens.radiusSmall
        color: control.pressed ? tokens.controlPressed : control.hovered ? tokens.controlHover : tokens.control
        border.width: 1
        border.color: control.activeFocus ? tokens.accent : tokens.border
        Behavior on color { ColorAnimation { duration: tokens.motionFast } }
        Behavior on border.color { ColorAnimation { duration: tokens.motionFast } }
    }
    delegate: ItemDelegate {
        required property var modelData
        required property int index
        width: ListView.view.width
        height: tokens.controlHeight
        highlighted: control.highlightedIndex === index
        contentItem: Text {
            text: String(modelData)
            color: tokens.text
            font.family: tokens.uiFont
            font.pixelSize: tokens.typeBody
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle { color: highlighted ? tokens.selectionStrong : hovered ? tokens.controlHover : "transparent"; radius: tokens.radiusSmall }
    }
    popup: Popup {
        id: menuPopup
        y: control.height + 3
        width: control.width
        implicitHeight: Math.min(contentItem.implicitHeight + 8, 280)
        padding: 4
        transformOrigin: Item.Top
        onVisibleChanged: {
            if (visible) {
                opacity = 0
                scale = 0.94
                Qt.callLater(function() { if (menuPopup.visible) menuOpenMotion.restart() })
            }
        }
        ParallelAnimation {
            id: menuOpenMotion
            NumberAnimation { target: menuPopup; property: "opacity"; from: 0; to: 1; duration: tokens.motionNormal; easing.type: Easing.OutCubic }
            NumberAnimation { target: menuPopup; property: "scale"; from: 0.94; to: 1; duration: tokens.motionSlow; easing.type: Easing.OutCubic }
        }
        exit: Transition {
            ParallelAnimation {
                NumberAnimation { property: "opacity"; from: 1; to: 0; duration: tokens.motionFast }
                NumberAnimation { property: "scale"; from: 1; to: 0.98; duration: tokens.motionFast }
            }
        }
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator { }
        }
        background: Rectangle { color: tokens.surfaceRaised; border.color: tokens.border; radius: tokens.radiusMedium }
    }
}
