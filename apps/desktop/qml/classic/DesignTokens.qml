import QtQuick

QtObject {
    id: root

    property string mode: "light"
    readonly property bool systemDark: (systemPalette.window.r + systemPalette.window.g + systemPalette.window.b) / 3 < 0.5
    readonly property bool dark: mode === "dark" || (mode === "system" && systemDark)

    readonly property color background: dark ? "#111111" : "#f7f7f7"
    readonly property color surface: dark ? "#181818" : "#f6f6f5"
    readonly property color surfaceRaised: dark ? "#1c1c1c" : "#ffffff"
    readonly property color surfaceSunken: dark ? "#101010" : "#eeeeec"
    readonly property color control: dark ? "#222222" : "#ffffff"
    readonly property color controlHover: dark ? "#292929" : "#eeeeec"
    readonly property color controlPressed: dark ? "#303030" : "#e4e4e1"
    readonly property color primaryControl: dark ? "#303030" : "#2e2e2e"
    readonly property color primaryHover: dark ? "#383838" : "#3a3a3a"
    readonly property color primaryPressed: dark ? "#282828" : "#242424"
    readonly property color selection: dark ? "#242629" : "#e7e7e4"
    readonly property color selectionStrong: dark ? "#2d3034" : "#dcdcd8"
    readonly property color border: dark ? "#343434" : "#dedede"
    readonly property color borderSubtle: dark ? "#292929" : "#e9e9e9"
    readonly property color divider: dark ? "#303030" : "#e5e5e5"

    readonly property color text: dark ? "#f2f2f2" : "#202124"
    readonly property color textSecondary: dark ? "#b3b3b3" : "#666a73"
    readonly property color textTertiary: dark ? "#7f7f7f" : "#9297a1"
    readonly property color textDisabled: dark ? "#5e5e5e" : "#b2b5bb"
    readonly property color accent: dark ? "#7f95b5" : "#536b8c"
    readonly property color accentHover: dark ? "#93a6c1" : "#465e7e"
    readonly property color accentPressed: dark ? "#6d819f" : "#3c526f"
    readonly property color accentSoft: dark ? "#252a31" : "#e3e7ec"
    readonly property color success: dark ? "#66a787" : "#4f866b"
    readonly property color warning: dark ? "#b99a61" : "#987b45"
    readonly property color error: dark ? "#bb7378" : "#a6575d"
    readonly property color info: dark ? "#8798ae" : "#64758a"
    readonly property color shimmerBase: dark ? "#202020" : "#e7e7e4"
    readonly property color shimmerHighlight: dark ? "#303030" : "#f7f7f5"

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
