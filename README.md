# Gaussian Factory

This repository contains P1's versioned contracts and a P2 PySide6 + Qt 6 +
QML desktop control plane. P2 preserves isolated Worker execution and uses the
same Artifact Store for durable task state and exports.

The canonical acceptance record is [`docs/adr/P1.md`](docs/adr/P1.md).

## Bootstrap

```powershell
uv sync --extra test --extra compatibility
uv run pytest
uv run gaussian-factory --help
uv sync --extra desktop
uv run gaussian-factory-gui
```

Runtime artifacts and benchmark outputs are written outside source-controlled
package directories.
