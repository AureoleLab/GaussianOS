# Gaussian Factory

This repository currently contains **P1 only**: versioned contracts, isolated
worker execution, SceneBundle v1, deterministic PLY interchange, licensing
gates, and a reproducible benchmark/validation harness. It is intentionally not
a desktop GUI and does not claim that unavailable third-party reconstruction or
training stacks have run successfully.

The canonical acceptance record is [`docs/adr/P1.md`](docs/adr/P1.md).

## Bootstrap

```powershell
uv sync --extra test --extra compatibility
uv run pytest
uv run gaussian-factory --help
```

Runtime artifacts and benchmark outputs are written outside source-controlled
package directories.
