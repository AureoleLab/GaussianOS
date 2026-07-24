# GaussianOS visual system · revision 3

## Direction

The interface now uses a strictly achromatic application palette. Light mode is
white and neutral gray with black text; Dark mode is near-black and gray-black
with white text. Hierarchy comes from luminance, border contrast, spacing, and
type weight—not hue.

Blue, terracotta, brown, orange, and saturated accents are absent. Muted green,
yellow, and red appear only in compact state markers.

The brand mark is a purpose-built vector `GF` glyph. It is not text and follows
the same 24×24 construction, stroke, cap, and join rules as the icon system.

## Color tokens

`Theme.qml` is the only QML file containing literal interface colors.

| Role | Light | Dark | Use |
| --- | --- | --- | --- |
| Canvas | `#F5F5F5` | `#151515` | Main workspace |
| Chrome | `#FAFAFA` | `#1B1B1B` | Toolbar, Sidebar, Inspector |
| Surface | `#FFFFFF` | `#202020` | Logs and flat sections |
| Raised | `#FFFFFF` | `#282828` | Dialogs, menus, floating controls |
| Sunken | `#EFEFEF` | `#111111` | Search, empty tracks, inset regions |
| Viewer | `#F0F0F0` | `#0E0E0E` | Viewer field |
| Primary ink | `#171717` | `#F5F5F5` | Text and icons |
| Secondary ink | `#5E5E5E` | `#B8B8B8` | Supporting text |
| Primary action | `#171717` | `#F1F1F1` | Black/white action fill |
| Selected | `#EAEAEA` | `#303030` | Neutral selection |
| Divider | `#E7E7E7` | `#2C2C2C` | Low-contrast hairlines |

Status tokens are deliberately desaturated:

- success `#5E7964` / `#86A18C`;
- warning `#81744F` / `#B0A17B`;
- danger `#835C5C` / `#AE8585`.

Destructive controls remain monochrome. Status hues are restricted to small
badges, icons, and compact pipeline labels.

## Typography

`Typography.qml` defines the Montserrat system and `Density.qml` applies the
Compact/Standard/Comfortable size offsets:

| Style | Size | Weight | Line height |
| --- | ---: | --- | ---: |
| Page Title | 26–28 px | 600 | 1.18 |
| Panel Title | 17–18 px | 600 | 1.25 |
| Section Header | 10–11 px | 500 | 1.25 |
| List Primary | 13–14 px | 500; selected 600 | 1.25 |
| Body | 12–13 px | 400 | 1.45 |
| Button | 12–13 px | 500 | 1.25 |
| Metadata | 10–11 px | 400 | 1.25 |

Control content uses layout centering rather than font-specific offsets.
Operational timestamps use Cascadia Mono.

## Curvature system

Every container radius comes from `Theme.qml`.

| Token | Radius | Use |
| --- | ---: | --- |
| `radiusControl` | 8 | Buttons, inputs, compact controls |
| `radiusItem` | 12 | Sidebar rows, popup rows, pipeline rows |
| `radiusPanel` | 16 | Panels, viewer empty-state glyph |
| `radiusToast` | 22 | Toasts and floating messages |
| `radiusDialog` | 28 | Modal dialogs |
| `radiusPill` | optical pill | Status badges |
| `radiusProgress` | 2 | Four-pixel progress track only |

Large surfaces use antialiased 16–28 px curvature to approximate continuous
squircle geometry within Qt Rectangle constraints. Nested surfaces maintain at
least one spacing step between outer and inner edges, and the inner radius is
always smaller than the outer radius.

## SVG icon system

All 44 assets in `qml/icons/` now share:

- 24×24 view box, including the GF brand glyph;
- 1.75 px optical stroke;
- round line caps and joins;
- monochrome white source geometry;
- runtime tint through `AppIcon.qml`;
- no emoji, Unicode icon, dot placeholder, diamond placeholder, text glyph, or
  raster production asset.

Visible glyphs are independent from their hit targets. Compact/Standard/
Comfortable render normal tools at 13/14/15 px and primary Viewer/topbar tools
at 15/16/17 px, while icon buttons remain 32/34/36 px. Every SVG is loaded
through `AppIcon`; other components never address SVG files directly. Normal
tools have no permanent backing box; neutral backgrounds appear only for
Hover, Pressed, Selected, or Focus states.

## Motion system

`Motion.qml` centralizes all timings, travel, scale, and easing:

| Motion | Duration | Composition |
| --- | ---: | --- |
| Button press | 105 ms | scale + background |
| Hover | 130 ms | background/color |
| Section | 210 ms | height + opacity + arrow rotation |
| Menu | 190 ms | opacity + y + scale |
| Toast | 220 ms | opacity + y + scale |
| Dialog | 250 ms | opacity + y + scale + overlay |
| Sidebar / Inspector | 290 ms | width + opacity + translated content |
| Viewer / pipeline state | 260 ms | crossfade + y + scale + color |
| Appearance preset | 160 ms | geometry interpolation + restrained crossfade |
| Page navigation | 290 ms | opacity + ±18 px x + 0.992 scale |
| Split snap | 140 ms | size only after pointer release |

Standard and emphasized cubic Bézier curves are tokens. Reduced Motion changes
durations to 1 ms, removes travel, and sets all scale deltas to 1.0 while
preserving final state and interaction order.

## DPI and resizing

- Logical minimum: 1180×720.
- Sidebar/Inspector are 236/296, 260/320, or 284/344 px by density.
- User split sizes override density defaults without being overwritten by later
  density changes.
- Lower-priority toolbar labels disappear before Viewer width is reduced.
- Inspector and Sidebar animate to zero width without leaving layout gaps.
- Grid lines and separators are integer-positioned device-independent pixels.
- Project Library retains a minimum table canvas and introduces horizontal
  scrolling only when the window cannot display every field without overlap.
- Verified at Qt scale 1.0, 1.25, and 1.5, including the 1180×720 minimum.
