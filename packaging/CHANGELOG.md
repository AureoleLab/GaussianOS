# GaussianOS 0.1.0-alpha

- Preserves ModernUI and ClassicUI on one production backend.
- Adds complete Scene Bundle export with Gaussian PLY, point cloud, cameras,
  COLMAP text data, and a verified manifest.
- Separates Portable Core from the locked Offline Runtime.
- Adds component-level Runtime detection, offline import, full verification,
  repair, resume/retry, staging, and atomic commit.
- Separates Application, Runtime, Settings, Cache, Logs, Projects, and Exports.
- Removes only audited debug resources, bytecode caches, and debug symbols
  from the Core package. Training, reconstruction, Viewer, and export behavior
  are unchanged.
