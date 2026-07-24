import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    required property var theme
    required property var type
    property bool running: false
    property int progress: 64

    color: theme.chrome

    ScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            width: parent.width
            spacing: 0

            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 16
                Layout.rightMargin: 16
                Layout.topMargin: 14
                Layout.bottomMargin: 12
                Text {
                    Layout.fillWidth: true
                    text: "Inspector"
                    color: theme.ink
                    font.family: type.family
                    font.pixelSize: type.headingSize
                    font.weight: type.semibold
                }
                StatusBadge {
                    theme: root.theme
                    type: root.type
                    text: root.running ? "RUNNING" : "READY"
                    status: root.running ? "running" : "success"
                }
            }

            Divider { theme: root.theme; Layout.fillWidth: true }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: 16
                spacing: 9
                SectionHeader { theme: root.theme; type: root.type; Layout.fillWidth: true; title: "Reconstruction profile" }
                ComboField {
                    theme: root.theme
                    type: root.type
                    Layout.fillWidth: true
                    model: ["Preview", "Balanced", "Quality"]
                    currentIndex: 1
                }
                Text {
                    Layout.fillWidth: true
                    text: "Recommended balance · 3,000 steps · auto frames"
                    color: theme.inkSecondary
                    font.family: type.family
                    font.pixelSize: type.microSize
                    lineHeight: type.bodyLine
                    wrapMode: Text.Wrap
                }
            }

            Divider { theme: root.theme; Layout.fillWidth: true }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: 16
                spacing: 9
                SectionHeader { theme: root.theme; type: root.type; Layout.fillWidth: true; title: "Frame sampling" }
                ComboField {
                    theme: root.theme
                    type: root.type
                    Layout.fillWidth: true
                    model: ["Auto", "Target count", "Interval", "All frames"]
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Text {
                        text: "Trim"
                        color: theme.inkSecondary
                        font.family: type.family
                        font.pixelSize: type.labelSize
                    }
                    AppTextField { theme: root.theme; type: root.type; Layout.fillWidth: true; text: "0" }
                    Text {
                        text: "to"
                        color: theme.inkTertiary
                        font.family: type.family
                        font.pixelSize: type.labelSize
                    }
                    AppTextField { theme: root.theme; type: root.type; Layout.fillWidth: true; text: "2,447" }
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    ToolbarButton {
                        theme: root.theme; type: root.type
                        Layout.fillWidth: true
                        text: "Apply"
                        compact: true
                    }
                    ToolbarButton {
                        theme: root.theme; type: root.type
                        Layout.fillWidth: true
                        text: "Reanalyze"
                        iconName: "refresh"
                        primary: true
                        compact: true
                    }
                }
                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    rowSpacing: 7
                    columnSpacing: 10
                    Repeater {
                        model: [
                            ["Source", "2,448 frames"],
                            ["Duration / FPS", "81.6 s · 30.0"],
                            ["Resolution", "3,840 × 2,160"],
                            ["Selected", "184 / 220"],
                            ["Estimate", "18 min · 7.2 GiB"]
                        ]
                        delegate: Item {
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.columnSpan: 2
                            implicitHeight: 16
                            RowLayout {
                                anchors.fill: parent
                                Text {
                                    Layout.fillWidth: true
                                    text: modelData[0]
                                    color: theme.inkSecondary
                                    font.family: type.family
                                    font.pixelSize: type.microSize
                                }
                                Text {
                                    text: modelData[1]
                                    color: theme.ink
                                    font.family: type.family
                                    font.pixelSize: type.microSize
                                    font.weight: type.medium
                                }
                            }
                        }
                    }
                }
            }

            Divider { theme: root.theme; Layout.fillWidth: true }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: 16
                spacing: 8
                SectionHeader { theme: root.theme; type: root.type; Layout.fillWidth: true; title: "Quality & status" }
                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        Layout.fillWidth: true
                        text: root.running ? "Training Gaussian field" : "Ready to reconstruct"
                        color: theme.ink
                        font.family: type.family
                        font.pixelSize: type.labelSize
                        font.weight: type.medium
                    }
                    Text {
                        text: root.running ? root.progress + "%" : "0%"
                        color: root.running ? theme.accent : theme.inkTertiary
                        font.family: type.family
                        font.pixelSize: type.labelSize
                        font.weight: type.semibold
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 4
                    radius: theme.radiusProgress
                    color: theme.surfaceSunken
                    Rectangle {
                        width: parent.width * (root.running ? root.progress / 100 : 0)
                        height: parent.height
                        radius: parent.radius
                        color: theme.accent
                        Behavior on width {
                            NumberAnimation {
                                duration: theme.motion.stateDuration
                                easing.type: Easing.BezierSpline
                                easing.bezierCurve: theme.motion.standardCurve
                            }
                        }
                    }
                }
            }

            Divider { theme: root.theme; Layout.fillWidth: true }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: 16
                spacing: 5
                SectionHeader { theme: root.theme; type: root.type; Layout.fillWidth: true; title: "Pipeline stages" }
                Repeater {
                    model: [
                        ["Ingest", "Complete", "success"],
                        ["COLMAP", "Complete", "success"],
                        ["Fallback", "Not needed", "neutral"],
                        ["Train", "Waiting", "neutral"],
                        ["Validate", "Waiting", "neutral"],
                        ["Export", "Waiting", "neutral"]
                    ]
                    delegate: Rectangle {
                        required property var modelData
                        Layout.fillWidth: true
                        implicitHeight: 34
                        radius: theme.radiusItem
                        color: root.running && index === 3 ? theme.accentSoft : "transparent"
                        Behavior on color {
                            ColorAnimation {
                                duration: theme.motion.stateDuration
                                easing.type: Easing.OutCubic
                            }
                        }
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 8
                            anchors.rightMargin: 6
                            AppIcon {
                                name: modelData[2] === "success" ? "check" : root.running && index === 3 ? "activity" : "chevron-right"
                                size: theme.density.iconMicro
                                color: modelData[2] === "success" ? theme.success : root.running && index === 3 ? theme.accent : theme.inkTertiary
                            }
                            Text {
                                Layout.fillWidth: true
                                text: modelData[0]
                                color: theme.ink
                                font.family: type.family
                                font.pixelSize: type.labelSize
                                font.weight: root.running && index === 3 ? type.semibold : type.medium
                            }
                            Text {
                                text: root.running && index === 3 ? root.progress + "%" : modelData[1]
                                color: modelData[2] === "success" ? theme.success : root.running && index === 3 ? theme.accent : theme.inkTertiary
                                font.family: type.family
                                font.pixelSize: type.microSize
                                font.weight: type.semibold
                            }
                        }
                    }
                }
            }
        }
    }
}
