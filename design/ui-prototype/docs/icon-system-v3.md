# Icon system · revision 3

## Construction

- 24×24 SVG view box with a consistent optical safe area.
- 1.75 px monochrome stroke, round caps, and round joins.
- Standard render size 18 px; primary topbar and Viewer tools 20 px.
- Compact/Comfortable sizes are derived only from `Density.qml`.
- `AppIcon.qml` is the only SVG loader. Buttons compose it through
  `IconButton.qml` or `ToolbarButton.qml`.
- No PNG, emoji, Unicode stand-ins, text icons, dots, or diamond placeholders.
- Normal state has no heavy tile. Hover, Pressed, Selected, and Focus introduce
  a low-contrast radius-8 surface.

## Asset inventory

| Group | Assets |
| --- | --- |
| Brand | brand |
| Navigation | viewer, library, project, folder, archive, trash, favorite |
| Application | sidebar, inspector, settings, sliders, activity, pipeline |
| Appearance | sun, moon, system |
| Viewer | grid, camera, expand, collapse, images, video |
| Workflow | add, import, play, stop, export, refresh |
| Library actions | search, sort, list, manage, rename, copy, restore, delete |
| Status / utility | check, info, warning, error, chevron-down, chevron-right, close |

The asset audit checks all 44 files for the same view box, stroke width, cap,
and join declarations. The project-list management affordance uses `manage.svg`
and is visible only while its row is hovered.
