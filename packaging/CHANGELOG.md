# GaussianOS 0.1.0-alpha

- Preserves ModernUI and ClassicUI on one production backend.
- Adds complete Scene Bundle export with Gaussian PLY, point cloud, cameras,
  COLMAP text data, and a verified manifest.
- Separates Portable Core from the locked Offline Runtime.
- Adds component-level Runtime detection, offline import, full verification,
  repair, resume/retry, staging, and atomic commit.
- Adds double-click Offline Runtime install and ModernUI/ClassicUI launch
  entry points that locate the matching Portable Core without duplicating it.
- Separates Application, Runtime, Settings, Cache, Logs, Projects, and Exports.
- Removes only audited debug resources, bytecode caches, and debug symbols
  from the Core package. Training, reconstruction, Viewer, and export behavior
  are unchanged.
