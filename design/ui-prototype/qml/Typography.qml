import QtQuick

QtObject {
    id: root
    property string densityMode: "standard"
    property string weightPreset: "balanced"

    readonly property int sizeOffset: densityMode === "compact" ? -1 : densityMode === "comfortable" ? 1 : 0
    readonly property string family: "Montserrat"
    readonly property string monoFamily: "Cascadia Mono"

    // Montserrat static families are loaded by the prototype launcher.
    readonly property int regular: weightPreset === "strong" ? Font.Medium : Font.Normal
    readonly property int medium: weightPreset === "strong" ? Font.DemiBold : Font.Medium
    readonly property int semibold: weightPreset === "strong" ? Font.Bold : Font.DemiBold
    readonly property int bold: Font.Bold

    readonly property int pageTitleSize: 27 + sizeOffset
    readonly property int panelTitleSize: densityMode === "compact" ? 17 : 18
    readonly property int sectionHeaderSize: densityMode === "comfortable" ? 11 : 10
    readonly property int listPrimarySize: densityMode === "comfortable" ? 14 : 13
    readonly property int bodySize: densityMode === "comfortable" ? 13 : 12
    readonly property int buttonSize: densityMode === "comfortable" ? 13 : 12
    readonly property int metadataSize: densityMode === "comfortable" ? 11 : 10

    // Compatibility aliases used by existing prototype surfaces.
    readonly property int displaySize: pageTitleSize
    readonly property int titleSize: panelTitleSize
    readonly property int headingSize: 14 + Math.max(0, sizeOffset)
    readonly property int labelSize: bodySize
    readonly property int captionSize: metadataSize
    readonly property int microSize: Math.max(9, metadataSize - 1)

    readonly property real displayLine: 1.18
    readonly property real titleLine: 1.25
    readonly property real bodyLine: 1.45
    readonly property real compactLine: 1.25
}
