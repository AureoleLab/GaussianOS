# ModernUI migration boundary

## Status

Implemented on the independent migration branch. ClassicUI remains a supported
compatibility shell.

## Initial state

At migration start, `main`, `origin/main`, and the local
`ui/macos-industrial-redesign` branch all pointed to commit `3a55ed9`. The
accepted prototype existed only as untracked files under
`design/ui-prototype/`; the remote exposed no prototype branch or prototype
commit. The prototype's own revision-3 verification and 125% screenshots are
retained as design evidence.

## Boundary

- `apps/desktop/qml/classic/` is the former production QML tree. Its backend
  calls, Viewer behavior, LocalStorage layout state, and visual tokens remain
  intact.
- `apps/desktop/qml/modern/` contains the accepted black-and-white shell,
  Montserrat typography, SVG assets, design tokens, split panes, Project
  Library, and production bindings.
- Both shells receive the same `Backend(QObject)` instance from
  `apps/desktop/main.py`.
- `ProjectStore`, `PipelineController`, `VideoImportSession`,
  `load_viewer_scene`, Runtime paths, Viewer receipt validation, and export
  destinations are not duplicated.

## Startup selection

The resolution order is:

1. `--safe-ui` (Classic) or `--ui modern|classic`
2. atomic `ui-settings.json`
3. Modern

Modern load failure creates a new engine for Classic and appends an explicit
message to `logs/desktop-ui.log`. Runtime hot switching is intentionally not
implemented.

## Persistence

- Process-level shell preference: atomic `UiSettingsStore`.
- Modern appearance, density, typography, reduced-motion, last-project, and
  split sizes: `QtCore.Settings` category `modern-ui-v1`.
- Classic layout and appearance: existing QML LocalStorage database, unchanged.
- Project data remains one atomically replaced JSON document per project under
  `ProjectStore`; UI preferences never enter project JSON.

## Invariants

The migration does not change project directory ownership, `project_id`,
`run_id`, generation checks, locks, atomic lifecycle transactions, Viewer
receipt validation, PLY encoding, or SceneBundle export.
