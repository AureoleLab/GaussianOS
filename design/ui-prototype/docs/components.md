# Component inventory

## Foundations

- `Theme.qml` — Light/Dark/System colors and monochrome surface hierarchy.
- `Density.qml` — Compact/Standard/Comfortable geometry and icon tokens.
- `Typography.qml` — Montserrat type ramp, true weights, and weight presets.
- `Motion.qml` — reduced-motion aware timing, travel, scale, and Bézier tokens.
- `AppIcon.qml` — monochrome SVG loader and token-driven tint.
- `BrandGlyph.qml` — dedicated GaussianOS GF vector mark.

## Controls

- `IconButton.qml` — icon-only Hover, Pressed, Selected, Disabled, Focus, and
  danger states with accessible tooltip names.
- `ToolbarButton.qml` — text/icon button with primary, quiet, selected,
  compact, and destructive variants.
- `SidebarItem.qml` — navigation/project row with selected state, metadata,
  status treatment, and project management action.
- `AppTextField.qml` — Montserrat text field with focus ring and disabled
  treatment.
- `ComboField.qml` — themed selection field and popup.
- `AppCheckBox.qml` — SVG-check indicator with tokenized press/state motion.
- `StatusBadge.qml` — success, warning, danger, running, and neutral badges.

## Structure

- `SectionHeader.qml` — tracked uppercase section title with optional action.
- `Divider.qml` — horizontal or vertical low-contrast hairline.
- `Panel.qml` — restrained semantic grouping surface.
- `Dialog.qml` — modal shell with overlay, title, subtitle, close action, and
  reusable content area.
- `PaneSplitHandle.qml` — 8 px horizontal/vertical drag target with a one-pixel
  visual rule, resize cursor, and double-click reset.

## Complete surfaces

- `Sidebar.qml` — Workspace, Project Library, recent/current/favorite projects,
  artifacts, and library location.
- `ViewerPane.qml` — Viewer toolbar, empty state, grid, mock actions, and
  collapsible Activity Log.
- `Inspector.qml` — profile, sampling, quality, progress, and Pipeline stages.
- `ProjectLibrary.qml` — All/Active/Archived/Trash filters, search, sorting,
  List/Grid views, selection, and lifecycle mock actions.
- `ProjectDetailsInspector.qml` — selection-driven metadata and actions.
- `Main.qml` — application chrome, interruptible Workspace/Library navigation,
  persistent horizontal split layout, theme/pane controls, New
  Project, Project Management, Import, Settings, and destructive dialogs.

## SVG assets

The 44-asset 24×24 / 1.75 px icon set covers brand, projects, folders, viewer,
camera, grid, list, library, sorting, system appearance, favorite, new,
video/images import, run, cancel, export, settings, Sidebar, Inspector,
activity, pipeline, search, manage, rename, copy, archive, trash, restore,
delete, status, warning, information, theme, expand/collapse, and refresh.
