import QtQuick

QtObject {
    id: root

    property string mode: "light"
    property var motion
    property var density
    readonly property bool systemDark: (systemPalette.window.r + systemPalette.window.g + systemPalette.window.b) / 3 < 0.5
    readonly property bool dark: mode === "dark" || (mode === "system" && systemDark)

    // Achromatic application palette. Status hues stay muted and local.
    readonly property color canvas: dark ? "#151515" : "#F5F5F5"
    readonly property color chrome: dark ? "#1B1B1B" : "#FAFAFA"
    readonly property color surface: dark ? "#202020" : "#FFFFFF"
    readonly property color surfaceRaised: dark ? "#282828" : "#FFFFFF"
    readonly property color surfaceSunken: dark ? "#111111" : "#EFEFEF"
    readonly property color viewer: dark ? "#0E0E0E" : "#F0F0F0"
    readonly property color control: dark ? "#292929" : "#FFFFFF"
    readonly property color controlHover: dark ? "#343434" : "#F0F0F0"
    readonly property color controlPressed: dark ? "#3D3D3D" : "#E3E3E3"
    readonly property color selected: dark ? "#303030" : "#EAEAEA"
    readonly property color selectedHover: dark ? "#3A3A3A" : "#E1E1E1"
    readonly property color overlay: dark ? "#000000B8" : "#00000052"

    readonly property color ink: dark ? "#F5F5F5" : "#171717"
    readonly property color inkSecondary: dark ? "#B8B8B8" : "#5E5E5E"
    readonly property color inkTertiary: dark ? "#818181" : "#8A8A8A"
    readonly property color inkDisabled: dark ? "#595959" : "#B8B8B8"
    readonly property color inkOnAccent: dark ? "#141414" : "#FFFFFF"

    readonly property color accent: dark ? "#F1F1F1" : "#171717"
    readonly property color accentHover: dark ? "#FFFFFF" : "#000000"
    readonly property color accentPressed: dark ? "#D2D2D2" : "#303030"
    readonly property color accentSoft: dark ? "#353535" : "#E8E8E8"
    readonly property color focus: dark ? "#F0F0F0" : "#181818"

    readonly property color success: dark ? "#86A18C" : "#5E7964"
    readonly property color successSoft: dark ? "#252C27" : "#EDF1ED"
    readonly property color warning: dark ? "#B0A17B" : "#81744F"
    readonly property color warningSoft: dark ? "#2D2A22" : "#F2F0E9"
    readonly property color danger: dark ? "#AE8585" : "#835C5C"
    readonly property color dangerSoft: dark ? "#302727" : "#F2ECEC"
    readonly property color info: dark ? "#A0A0A0" : "#696969"

    readonly property color line: dark ? "#3A3A3A" : "#D7D7D7"
    readonly property color lineSubtle: dark ? "#2C2C2C" : "#E7E7E7"
    readonly property color lineStrong: dark ? "#515151" : "#BDBDBD"
    readonly property color gridLine: dark ? "#202020" : "#DEDEDE"
    readonly property color gridAxis: dark ? "#2C2C2C" : "#D0D0D0"

    readonly property int space2: 2
    readonly property int space4: 4
    readonly property int space6: 6
    readonly property int space8: 8
    readonly property int space10: 10
    readonly property int space12: 12
    readonly property int space16: 16
    readonly property int space20: 20
    readonly property int space24: 24
    readonly property int space32: 32
    readonly property int space40: 40

    // Curvature scale: control, item, panel, floating surface, dialog.
    readonly property int radiusControl: 8
    readonly property int radiusItem: 12
    readonly property int radiusPanel: 16
    readonly property int radiusToast: 22
    readonly property int radiusDialog: 28
    readonly property int radiusPill: 999
    readonly property int radiusProgress: 2
    readonly property int hairline: 1

    property SystemPalette systemPalette: SystemPalette { colorGroup: SystemPalette.Active }
}
