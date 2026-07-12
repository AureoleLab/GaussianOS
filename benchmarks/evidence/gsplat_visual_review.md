# Candidate-only fixed-view visual review

Reviewed 2026-07-12 from `holdout_00_gt-render.png` for each formal gsplat
artifact. Each image places ground truth on the left and the candidate render
on the right. This is not a Postshot or legacy comparison.

| Scene | Floaters | Noise | Edge swelling | Near-field tearing | Detail/color notes |
|---|---|---|---|---|---|
| 001 | Low in reviewed view | Low | Mild–moderate on distant skyline/fog | Not observable; aerial view | Main tower/signage retained; background is softer and slightly smeared |
| 002 | Moderate–high ghost structures above skyline | Moderate | High around upper building silhouettes | Not observable; aerial view | Major sky/building tearing and blur; foreground waterfront/color remain recognizable |
| 003 | Low in reviewed view | Low | Mild around high-contrast lights | Not observable; aerial view | Strong structure/color match; some highlight blur and loss of fine road detail |

The fixed views are stored inside the immutable artifacts named in
`gsplat_training.json`. Remaining holdout views have numeric metrics but were
not all manually scored. The formal cross-product scorecard remains blank until
Postshot and legacy reference renders are imported.
