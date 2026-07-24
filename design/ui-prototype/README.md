# GaussianOS UI Prototype

This directory is a standalone Qt 6 / PySide6 / QML visual prototype. It does
not import `apps.desktop`, expose a backend object, read project data, or start
pipeline work. All projects, progress, logs, files, and actions are static mock
content.

## Launch

From the repository root:

```powershell
.\design\ui-prototype\launch.ps1
```

Dark theme:

```powershell
.\design\ui-prototype\launch.ps1 -Theme dark
```

Open Project Library with a specific appearance preset:

```powershell
.\design\ui-prototype\launch.ps1 -Page library -Density comfortable -Weight strong
```

The launcher uses the repository's locked `desktop` dependency set through
`uv`. The prototype expects Montserrat to be installed. The current Windows
development machine has the complete Montserrat family installed.

## Preview capture

```powershell
.\design\ui-prototype\capture-preview.ps1
.\design\ui-prototype\capture-preview.ps1 -Theme dark
```

The committed previews are:

- `screenshots/gaussianos-light-1600x900-125.png`
- `screenshots/gaussianos-dark-1600x900-125.png`

## Prototype interactions

- Switch Workspace / Project Library from the sidebar.
- Filter Project Library by All, Active, Archived, or Trash; search, sort,
  switch List/Grid, select projects, and trigger lifecycle mock actions.
- Select projects and open the Manage Project dialog.
- Open New Project, Import Video, Settings, and permanent-delete dialogs.
- Toggle Light / Dark / Follow system, Compact / Standard / Comfortable,
  Light / Balanced / Strong typography, Sidebar, Inspector, and Activity Log.
- Run and cancel a local progress simulation.
- Trigger mock notifications from import, export, restore, archive, cleanup,
  rename, and layout actions.

No interaction calls production code.

## Documentation

- [Design system](docs/design-system.md)
- [Component inventory](docs/components.md)
- [Existing UI function map](docs/function-map.md)
- [Disconnected interactions](docs/disconnected-interactions.md)
- [Revision 2 delivery notes](docs/revision-2.md)
- [Motion verification](docs/motion-verification.md)
- [Revision 3 delivery notes](docs/revision-3.md)
- [Icon specification and assets](docs/icon-system-v3.md)
- [Project Library architecture](docs/project-library.md)
- [Appearance presets](docs/appearance-presets.md)
- [Revision 3 verification](docs/verification-v3.md)
- [Targeted icon, navigation, and split correction](docs/targeted-correction.md)
