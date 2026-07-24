# ModernUI migration verification

Date: 2026-07-25
Branch: `codex/modern-ui-migration`

## Startup matrix

| Case | Result | Evidence |
| --- | --- | --- |
| `--ui modern` | Modern QML root loaded | `modern-ui-light-125.png` |
| `--ui classic` | Classic QML root loaded | `classic-ui-dark-125.png` |
| `--safe-ui` with `--ui modern` | Classic selected from command line | startup log |
| persisted Classic, no CLI selector | Classic selected from persisted setting | startup log |
| forced missing Modern root | Explicit error logged; fresh Classic engine loaded | `modern-fallback-classic-100.png` |

The forced failure uses the suppressed acceptance flag
`--acceptance-force-modern-failure`; production fallback follows the same
missing-root path.

## DPI and appearance

| Qt scale | Modern preset | Captured pixels | Result |
| --- | --- | --- | --- |
| 100% | Light / Compact / Light weight | 1600×900 | Pass |
| 125% | Light / Standard / Balanced | 2000×1125 | Pass |
| 150% | Dark / Comfortable / Strong | 2400×1350 | Pass |

The 150% settings capture verifies that the modal remains bounded and
scrollable at high scale. Native SVG rendering is visible in all non-offscreen
captures.

## Screenshots

- `modern-ui-light-compact-100.png`
- `modern-ui-light-125.png`
- `modern-ui-dark-comfortable-150.png`
- `modern-ui-project-library-125.png`
- `modern-ui-settings-dark-150.png`
- `classic-ui-dark-125.png`
- `modern-fallback-classic-100.png`

## Automated checks

- QML lint: exit 0; no parser errors.
- Full repository tests: 168 passed, 2 external compatibility checks skipped.
- Wheel audit: 83 QML/SVG assets; both roots, Modern design tokens, and SVG
  icons present.

## Hardware-dependent follow-up

This host's Runtime doctor reports the reconstruction/training assets absent,
so a real video → COLMAP → gsplat run and a completed-scene Viewer receipt
could not be newly generated during this migration. Existing unit, contract,
and integration coverage for video ingest, project/run/generation isolation,
Viewer ownership, PLY, and SceneBundle remained green.
