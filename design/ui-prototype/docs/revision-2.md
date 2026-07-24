# Visual revision 2 delivery

## Modified files

Foundations and launch:

- `prototype.py`
- `qml/Main.qml`
- `qml/Theme.qml`
- `qml/Motion.qml` (new)

Reusable components:

- `AppIcon.qml`
- `AppCheckBox.qml` (new)
- `IconButton.qml`
- `ToolbarButton.qml`
- `SidebarItem.qml`
- `StatusBadge.qml`
- `Panel.qml`
- `Dialog.qml`
- `AppTextField.qml`
- `ComboField.qml`
- `Sidebar.qml`
- `ViewerPane.qml`
- `Inspector.qml`

Assets:

- all 39 files in `qml/icons/`
- Light/Dark 1600×900 previews in `screenshots/`

Documentation:

- `README.md`
- `docs/design-system.md`
- `docs/components.md`
- `docs/motion-verification.md`
- `docs/revision-2.md`

## DPI validation

| Qt scale | Logical test window | Result |
| --- | --- | --- |
| 100% | 1180×720 | Pass; compact toolbar, no horizontal clipping |
| 125% | 1600×900 | Pass; canonical Light/Dark previews |
| 150% | 1180×720 | Pass; compact labels, scrollable Inspector, no seams |

The canonical images are exactly 1600×900 pixels. Temporary compact-window QA
captures are also retained in `screenshots/qa-100.png` and `qa-150.png`.

## Isolation

This revision remains entirely inside `design/ui-prototype/`. It does not
import or call the production Backend, Pipeline, Viewer, ProjectStore, project
session, worker, artifact, or filesystem logic. Existing application QML and
business files are unchanged.
