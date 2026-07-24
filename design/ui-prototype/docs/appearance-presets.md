# Appearance presets

## Density tokens

| Token | Compact | Standard | Comfortable |
| --- | ---: | ---: | ---: |
| Toolbar | 52 | 58 | 64 |
| Sidebar | 236 | 260 | 284 |
| Inspector | 296 | 320 | 344 |
| Control | 32 | 36 | 40 |
| Icon button hit target | 32 | 34 | 36 |
| List row | 48 | 56 | 64 |
| Page padding | 20 | 28 | 36 |
| Default / primary glyph | 13 / 15 | 14 / 16 | 15 / 17 |
| Base type offset | −1 | 0 | +1 |

Density changes each component token independently. The application root is
never scaled. Geometry and opacity settle over 160 ms with OutCubic easing.

## Typography presets

Montserrat Regular (400), Medium (500), SemiBold (600), and Bold (700) are
loaded as real font files.

| Role | Light | Balanced | Strong |
| --- | --- | --- | --- |
| Body / metadata | 400 | 400 | 500 |
| Button / list primary | 500 | 500 | 600 |
| Page / panel / selected | 600 | 600 | 700 |

The size ramp is Page Title 26–28, Panel Title 17–18, Section Header 10–11,
List Primary 13–14, Body/Button 12–13, and Metadata 10–11 px.

## Theme and persistence

Theme supports Light, Dark, and Follow system. Theme, density, typography
weight, and Reduce Motion are stored by the standalone prototype in the
`appearance-v3` settings category and update immediately.
