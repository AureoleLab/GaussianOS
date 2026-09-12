# GaussianOS 0.1.0-beta.1

- Adds a per-user Windows installer with automatic, verified reconstruction resource setup.
- Reuses installed components and resumes interrupted downloads; downloads MapAnything resources when needed.
- Ships independent Python workers and a precompiled gsplat CUDA extension, with isolated DLL and Python paths.
- Fixes native COLMAP output under Unicode/long installation paths and standard fallback PLY Scene Bundle export.
- Isolates the GUI build and checks every collected native dependency against its approved source.
- Preserves ModernUI, ClassicUI, project formats and recovery, Viewer, Camera Timeline and complete Scene Bundle exports.
- Verifies Runtime integrity and produces local diagnostics without including source media.

# GaussianOS 0.1.0-alpha

- Preserves ModernUI and ClassicUI on one production backend.
- Adds complete Scene Bundle export with Gaussian PLY, point cloud, cameras,
  COLMAP text data, and a verified manifest.
- Separates Portable Core from the locked Offline Runtime.
- Adds component-level Runtime detection, offline import, full verification,
  repair, resume/retry, staging, and atomic commit.
- Adds double-click Offline Runtime install and ModernUI/ClassicUI launch
  entry points that locate the matching Portable Core without duplicating it.
- Adds a single-folder Full Offline product for users who need Application and
  Runtime in one extract-and-run archive.
- Separates Application, Runtime, Settings, Cache, Logs, Projects, and Exports.
- Removes only audited debug resources, bytecode caches, and debug symbols
  from the Core package. Training, reconstruction, Viewer, and export behavior
  are unchanged.
