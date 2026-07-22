import QtQuick

QtObject {
    id: root

    property string mode: "light"
    readonly property bool systemDark: (systemPalette.window.r + systemPalette.window.g + systemPalette.window.b) / 3 < 0.5
    readonly property bool dark: mode === "dark" || (mode === "system" && systemDark)

    readonly property color background: dark ? "#111111" : "#f7f7f7"
    readonly property color surface: dark ? "#171717" : "#ffffff"
    readonly property color surfaceRaised: dark ? "#1d1d1d" : "#fbfbfb"
    readonly property color surfaceSunken: dark ? "#0d0d0d" : "#f2f2f2"
    readonly property color control: dark ? "#222222" : "#ffffff"
    readonly property color controlHover: dark ? "#292929" : "#f2f6fc"
    readonly property color controlPressed: dark ? "#303030" : "#e7effb"
    readonly property color selection: dark ? "#17365f" : "#eaf3ff"
    readonly property color selectionStrong: dark ? "#1e4f91" : "#d5e8ff"
    readonly property color border: dark ? "#343434" : "#dedede"
    readonly property color borderSubtle: dark ? "#292929" : "#e9e9e9"
    readonly property color divider: dark ? "#303030" : "#e5e5e5"

    readonly property color text: dark ? "#f2f2f2" : "#202124"
    readonly property color textSecondary: dark ? "#b3b3b3" : "#666a73"
    readonly property color textTertiary: dark ? "#7f7f7f" : "#9297a1"
    readonly property color textDisabled: dark ? "#5e5e5e" : "#b2b5bb"
    readonly property color accent: "#2f7df6"
    readonly property color accentHover: "#438bf7"
    readonly property color accentPressed: "#2167cc"
    readonly property color accentSoft: dark ? "#17345c" : "#e8f2ff"
    readonly property color success: "#48b982"
    readonly property color warning: "#d49b38"
    readonly property color error: "#e65f65"
    readonly property color info: "#5a92ed"

    readonly property int radiusSmall: 4
    readonly property int radiusMedium: 6
    readonly property int radiusLarge: 8
    readonly property int controlHeight: 34
    readonly property int compactHeight: 28
    readonly property int toolbarHeight: 58
    readonly property int space4: 4
    readonly property int space6: 6
    readonly property int space8: 8
    readonly property int space10: 10
    readonly property int space12: 12
    readonly property int space16: 16
    readonly property int space20: 20
    readonly property int space24: 24

    readonly property int typeCaption: 10
    readonly property int typeSmall: 11
    readonly property int typeBody: 13
    readonly property int typeLabel: 12
    readonly property int typeTitle: 20
    readonly property int typeHero: 25
    readonly property string uiFont: Qt.platform.os === "windows" ? "Segoe UI Variable" : ".AppleSystemUIFont"
    readonly property string monoFont: Qt.platform.os === "windows" ? "Cascadia Mono" : "SF Mono"
    readonly property int motionFast: 120
    readonly property int motionNormal: 170
    readonly property int motionSlow: 220

    property SystemPalette systemPalette: SystemPalette { colorGroup: SystemPalette.Active }
}
