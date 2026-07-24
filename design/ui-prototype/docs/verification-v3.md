# Revision 3 verification

## Runtime and animation sampling

Qt 6 loaded the prototype without QML runtime warnings. During an actual event
loop, panes and Dialog were sampled at transition boundaries:

| Sample | Sidebar | Inspector | Settings Dialog |
| --- | --- | --- | --- |
| Start | 260 px / 1.00 | 320 px / 1.00 | 0.00 / scale 0.975 |
| 120 ms | 42.3 px / 0.174 | 52.1 px / 0.174 | 0.884 / scale 0.999 |
| 330 ms | 0 px / 0.00 | 0 px / 0.00 | 1.00 / scale 1.000 |
| Return +120 ms | 189.6 px / 0.769 | 233.3 px / 0.769 | — |
| Return +350 ms | 260 px / 1.00 | 320 px / 1.00 | — |

Project Library enters with opacity + 8 px travel over 260 ms. At its +120 ms
sample it rendered opacity 0.880 and y 1.5 px, then settled to 1.00 / 0 px.
Project selection updates the details Inspector with a restrained 180 ms pulse.
Settings Dialog uses the existing 250 ms opacity + y + scale composition.

## DPI matrix

| Qt scale | Preset | Window | Result |
| --- | --- | --- | --- |
| 100% | Compact / Light weight | 1180×720 | Pass |
| 125% | Standard / Balanced | 1600×900 | Pass |
| 150% | Comfortable / Strong | 1180×720 | Pass |

The checks cover column labels, toolbar compression, pane dividers, row
selection, Inspector actions, and icon rasterization. No half-pixel separator,
one-pixel seam, text overlap, or clipped control was observed. At minimum width,
the Library table scrolls horizontally rather than collapsing columns.

## Static checks

- QML lint: no parser errors, missing properties, or layout-positioning warnings.
- SVG audit: 44/44 assets use 24×24, 1.75, round-cap, round-join declarations.
- Asset routing: only `AppIcon.qml` addresses `qml/icons/` directly.
- Isolation: no production file differs from the requested baseline.
