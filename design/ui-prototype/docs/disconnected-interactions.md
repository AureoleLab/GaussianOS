# Disconnected and mock interactions

Phase one intentionally contains no production integration.

## Local interactions that work

- page and project selection;
- Sidebar, Inspector, and Activity Log visibility;
- Light/Dark/Follow system, density, typography-weight, and reduced-motion
  settings persisted for the standalone prototype;
- Project Library search, filter, sorting, List/Grid, and selection;
- dialog open/close and basic field validation;
- typed permanent-delete confirmation;
- a local Timer-driven Run/Cancel progress simulation;
- short mock-action notifications.

## Static mock actions

The following actions only show a notification or update local display state:

- create, rename, copy, archive, restore, and permanently delete project;
- choose project library;
- duplicate project;
- selective cleanup;
- archive, trash, restore, and permanent deletion;
- import video Easy/Pro selection;
- import image folder;
- sample Apply/Reanalyze;
- run, cancel, export, open artifact;
- reset workspace layout.

## Deliberately not connected

- `Backend`, `PipelineController`, `Viewer`, `ProjectStore`, project sessions,
  worker processes, artifact storage, and filesystem pickers;
- durable project CRUD or lifecycle recovery;
- video metadata preflight, drag-and-drop ingestion, thumbnail analysis, and
  generation;
- real 3D WebEngine scene loading and viewer commands;
- timeline thumbnails, filtering, zoom, camera playback, persisted position,
  and stale-camera regeneration;
- project layout persistence;
- real logs, warnings, progress, stages, metrics, and export folders.

These remain phase-two integration work and require explicit visual approval
before any production file is changed.
