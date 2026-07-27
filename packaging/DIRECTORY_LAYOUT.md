# Portable directory layout

- `Application`: immutable executable, Python, Qt/QML, and WebEngine Core.
- `Runtime`: version-locked tools, Python worker environments, sources, models.
- `Settings`: UI and application preferences.
- `Cache`: resumable downloads, temporary files, and artifact cache.
- `Logs`: doctor, Runtime manager, UI, and diagnostic reports.
- `Projects`: user project control-plane data and workspace entries.
- `Exports`: user-selected durable exports.

The updater replaces only `Application` and release documentation. Runtime and
user data are siblings, so deleting or replacing `Application` does not delete
projects or exports.
