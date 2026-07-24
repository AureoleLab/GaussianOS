# Existing UI function map

This map was produced by a read-only audit of
`apps/desktop/qml/Main.qml` at baseline
`3a55ed9a5a23c3ef4795a7ef06b3859719834f7a`.

| Existing capability / entry | Prototype location | Phase-one representation |
| --- | --- | --- |
| Create project | Toolbar, Sidebar NEW, empty Viewer | New Project dialog with name/library validation |
| Open/select recent project | Sidebar Projects | Three selectable mock projects |
| Project rename | Project Manage dialog | Rename field and action |
| Duplicate inputs/settings | Project Manage dialog | Independent-copy action |
| Duplicate complete valid project | Project Manage dialog | Complete-project copy action |
| Selective output cleanup | Project Manage dialog | Reconstruction, Training, Viewer/Timeline, Exports |
| Archive/unarchive | Project Manage dialog | Archive action |
| Move to Trash | Project Manage dialog | Destructive trash action |
| Full project lifecycle library | Project Library | All/Active/Archived/Trash views with search, sort, List/Grid |
| Trash list and estimated size | Project Library → Trash | Trash is a filter state, not a standalone page |
| Open directory / rename / copy | Library row and Inspector | Selection-driven mock actions |
| Restore project | Project Library row and Inspector | Restore action and notification |
| Permanent deletion confirmation | Project Library → Trash | Name-typed confirmation dialog |
| Import video picker / drop | Toolbar | Import Video dialog; file I/O intentionally mocked |
| Video preflight | Import dialog | Static resolution/FPS/duration summary |
| Easy / Pro import workflows | Import dialog | Separate workflow choices and notifications |
| Import image folder | Toolbar | SVG entry and mock notification |
| Reconstruction profile | Inspector | Preview/Balanced/Quality selector |
| Sampling mode and trim | Inspector | Mode selector, In/Out fields, Apply/Reanalyze |
| Sampling analysis metrics | Inspector | Source, duration/FPS, resolution, selected, estimate |
| Run/resume pipeline | Toolbar and empty Viewer | Local-only progress simulation |
| Cancel pipeline | Toolbar | Stops local simulation |
| Pipeline stages and status | Inspector | Ingest through Export rows |
| Pipeline progress/current stage | Toolbar/Inspector | Badge, progress track, active Train row |
| Empty Viewer | Main workspace | Purpose-built empty state and Viewer tools |
| Open validated artifact | Viewer | Mock artifact-picker action |
| Viewer camera/grid/fullscreen tools | Viewer toolbar | Complete SVG controls |
| Camera/keyframe timeline | Activity/Viewer region | Entry represented; detailed timeline remains disconnected |
| Artifacts list | Sidebar | PLY and camera-path mock artifacts |
| Activity Log | Viewer bottom panel | Collapsible structured log with Clear |
| Export / open export folder | Toolbar | Mock export action |
| Sidebar toggle | Toolbar | Working local toggle |
| Inspector toggle | Toolbar | Working local toggle |
| Theme Light/Dark/System | Toolbar/Settings | Working and persisted in prototype settings |
| Interface density | Settings | Compact/Standard/Comfortable token presets |
| Typography weight | Settings | Light/Balanced/Strong Montserrat presets |
| Reduce motion | Settings | Working and persisted in prototype settings |
| Restore last project | Settings | Visual checkbox only |
| Reset workspace layout | Settings | Restores local pane visibility |
| Global status | Toolbar/status bar | Ready/running and explicit backend-disconnected state |

No original entry was removed from the design inventory. Entries that need a
larger dedicated workflow (notably Pro video import and camera timeline) remain
identified for the integration plan instead of being silently collapsed.
