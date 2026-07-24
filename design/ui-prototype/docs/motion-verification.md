# Motion verification

The revised QML was loaded in a real Qt 6 event loop and sampled during
transitions. The values below are rendered object properties, not inferred
only from source code.

## Sidebar and Inspector

Both panes use a 290 ms emphasized width/opacity/translation transition.

| Sample | Sidebar width / opacity | Inspector width / opacity |
| --- | --- | --- |
| Expanded | 232 px / 1.00 | 290 px / 1.00 |
| 145 ms | 27.85 px / 0.11 | 34.81 px / 0.11 |
| 350 ms | 0 px / 0.00 | 0 px / 0.00 |

Content translation is synchronized with the width and opacity curves. Pane
dividers animate to zero width so no one-pixel seam remains.

## Activity Log

The section uses one 210 ms curve for height, content opacity, divider opacity,
and chevron rotation.

| Sample | Height |
| --- | ---: |
| Expanded | 154 px |
| 145 ms | 42.41 px |
| Collapsed | 38 px |

The panel stays clipped during the transition; log rows remain in the object
tree until their opacity reaches zero.

## Dialog and Toast

At open, Dialog and Toast start at 0 opacity and 0.975 scale with an 8 px
travel offset.

| Sample | Dialog opacity / scale | Toast opacity / scale |
| --- | --- | --- |
| Start | 0.00 / 0.975 | 0.00 / 0.975 |
| 125 ms | 0.88 / 1.00 | 0.92 / 1.00 |
| 310 ms | 1.00 / 1.00 | 1.00 / 1.00 |

Dialog uses 250 ms and Toast 220 ms. Both use non-linear emphasized Bézier
easing and animate on exit as well as entry.

## Viewer and Pipeline state

Ready and Running surfaces crossfade with vertical travel and a small scale
delta over 260 ms.

| Sample | Ready opacity / scale | Running opacity / scale |
| --- | --- | --- |
| Ready | 1.00 / 1.000 | 0.00 / 0.985 |
| 130 ms | 0.10 / 0.987 | 0.90 / 0.998 |
| 320 ms | 0.00 / 0.985 | 1.00 / 1.000 |

Pipeline progress width and active-row color use the same state duration and
standard curve, avoiding unrelated motion rhythms.

## Reduced Motion

With Reduce Motion enabled, timings resolve to 1 ms, translation resolves to
0, and scale resolves to 1.0. A 20 ms sample after toggling panes and Activity
Log showed the final 232 px / 290 px / 154 px states with full opacity.
