import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ApplicationWindow {
    id: previewWindow
    visible: true
    width: 920
    height: 920
    minimumWidth: 560
    minimumHeight: 640
    title: "GaussianOS Loader Preview"
    color: "#f7f6f3"

    property bool freezeFrame: false

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 28
        spacing: 18

        GaussianOSLoader {
            id: loader
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 480
            running: true
            loop: true
            durationSeconds: 2.4
            backgroundColor: "#f7f6f3"
            frameColor: "#aab5c6"
            dotColor: "#126df5"
            frameProgress: previewWindow.freezeFrame ? timelineSlider.value : -1
        }

        Slider {
            id: timelineSlider
            Layout.fillWidth: true
            from: 0
            to: 1
            value: 0.64
            enabled: previewWindow.freezeFrame
        }

        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            spacing: 10

            Button {
                text: previewWindow.freezeFrame ? "Play live" : "Freeze"
                onClicked: previewWindow.freezeFrame = !previewWindow.freezeFrame
            }
            Button {
                text: "Start"
                onClicked: {
                    previewWindow.freezeFrame = true
                    timelineSlider.value = 0
                }
            }
            Button {
                text: "Draw midpoint"
                onClicked: {
                    previewWindow.freezeFrame = true
                    timelineSlider.value = 0.245
                }
            }
            Button {
                text: "Dots"
                onClicked: {
                    previewWindow.freezeFrame = true
                    timelineSlider.value = 0.39
                }
            }
            Button {
                text: "Hold"
                onClicked: {
                    previewWindow.freezeFrame = true
                    timelineSlider.value = 0.565
                }
            }
            Button {
                text: "Erase"
                onClicked: {
                    previewWindow.freezeFrame = true
                    timelineSlider.value = 0.78
                }
            }
        }
    }
}
