# GaussianOS Portable Troubleshooting

- `Core: damaged`: restore `Application` and `runtime-manifest.json` from the
  same Portable Core archive.
- `Runtime: not_installed`: import the matching Offline Runtime, or use the
  Runtime manager for components with an approved download source.
- `Runtime: incomplete` or `integrity_failed`: run
  `Runtime_Manager.ps1 -Verify`, then repair the named component with
  `-Repair <component_id> -Source <offline-package>`.
- `GPU: unavailable` or `incompatible`: install a supported NVIDIA driver and
  confirm the GPU meets the VRAM requirement in `runtime-manifest.json`.
- Viewer/WebEngine start failure: keep the complete `Application/_internal`
  tree together and run `Doctor.ps1`; do not copy individual DLLs.
- Moving the package: move the distribution root containing all seven sibling
  directories. No absolute development path is stored in the Runtime manifest.

Runtime operations never overwrite `Projects` or `Exports`. A failed import or
repair remains in `Runtime/.staging` only until cleanup and is never committed
over a verified component.
