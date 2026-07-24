# Targeted correction · icons, navigation, and split layout

## Modified files

- Tokens and shell: `qml/Density.qml`, `qml/Motion.qml`, `qml/Main.qml`.
- Components: `IconButton.qml`, new `PaneSplitHandle.qml`, `ViewerPane.qml`,
  `SidebarItem.qml`, and `ProjectLibrary.qml`.
- Asset: redrawn `qml/icons/settings.svg`.
- Delivery: README, design-system/appearance/component documentation, and
  Light/Dark preview screenshots.

No production Main.qml, Backend, Pipeline, Viewer engine, ProjectStore, or
project-data file changed.

## Icon correction

The prior `IconButton` passed `AppIcon` directly as the Qt Controls
`contentItem`. Qt expanded that item to the complete hit rectangle, so a nominal
16 px token could render close to 34 px. The new control places a fixed-size
glyph inside a separate hit-target item.

| Standard-density role | Before, rendered | After, rendered | Hit target |
| --- | ---: | ---: | ---: |
| Project row action | approximately 34 px | 14 px | 34 px |
| Right Actions icon | approximately 34 px | 14 px | 34 px |
| Top/Viewer primary tool | approximately 34 px | 16 px | 34 px |
| Settings gear | malformed, approximately 34 px | symmetric 16 px | 34 px |

Compact/Standard/Comfortable normal glyphs are 13/14/15 px; primary glyphs are
15/16/17 px. SVGs retain a 24×24 board, 1.75 px stroke, round caps/joins, and
monochrome runtime tint. Table actions use wider tokenized spacing, tertiary
contrast at rest, and primary ink on Hover.

The Settings asset is a symmetric eight-tooth outline with flat optical tooth
caps, rounded joins, a 2.85-unit center bore, and 3.5-unit outer safe margin.

## Workspace ↔ Project Library transition

Both pages remain mounted in a common clipped navigation host; page visibility
is never switched abruptly.

| Parameter | Standard | Reduced Motion |
| --- | --- | --- |
| Duration | 290 ms | 150 ms |
| Curve | cubic-bezier(0.22, 1, 0.36, 1) | fade easing |
| Exit | opacity 1→0, x 0→±18, scale 1→0.992 | opacity only |
| Enter | opacity 0→1, x ∓18→0, scale 0.992→1 | opacity only |
| Inspector | 40 ms delay, 240 ms fade + 10 px | 150 ms fade |
| Sidebar selection | 180 ms crossfade | 120 ms crossfade |

QML Behaviors are interruptible. A Library transition reversed at 120 ms and
reversed again 90 ms later continued from the current values; the two page
opacities remained complementary and settled at exactly 0/1 without a blank or
double-active frame.

## Adjustable split layout

- Horizontal handles resize Sidebar (180–420 px) and Inspector (260–520 px).
- The central page host preserves at least 520 px width.
- The vertical handle resizes Activity Log from its 38 px collapsed header to
  45% of Viewer height while retaining at least 280 px Viewer height.
- Each handle has an 8 px pointer target and one-pixel visible rule. Hover uses
  the correct horizontal/vertical resize cursor and a slightly stronger line.
- Dragging updates geometry without animation. Release snaps to an even logical
  pixel over 140 ms with the navigation ease-out curve.
- Double-click restores the active Density default.
- Collapsing panes preserves the last custom width; reopening restores it.
- Custom split sizes persist in the standalone `appearance-v3` settings and
  are not changed by Compact/Standard/Comfortable switching.

Runtime persistence test restored 308/376/218 px after a complete engine
restart. Switching to Comfortable left all three custom dimensions unchanged.

## DPI validation

| Scale | Preset / page | Window | Result |
| --- | --- | --- | --- |
| 100% | Compact / Project Library | 1180×720 | Pass |
| 125% | Standard / Library + Workspace | 1600×900 | Pass |
| 150% | Comfortable / Workspace | 1180×720 | Pass |

No QML parser, missing-property, or layout-positioning warning was produced.
The checks found no overlapping content, clipped controls, half-pixel divider,
one-pixel seam, page flash, or resize-content collision.
