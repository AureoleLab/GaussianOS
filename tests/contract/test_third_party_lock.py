from __future__ import annotations

import json
import re
from pathlib import Path


LOCK_PATH = Path(__file__).parents[2] / "third_party" / "locks" / "p1_candidates.lock.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


def _lock() -> dict:
    return json.loads(LOCK_PATH.read_text(encoding="utf-8"))


def test_all_required_candidates_are_present_and_source_pinned() -> None:
    payload = _lock()
    assert payload["schema_version"] == "third-party-lock/v1"
    production = {entry["id"]: entry for entry in payload["production_candidates"]}
    research = {entry["id"]: entry for entry in payload["research_only"]}
    assert set(production) == {
        "ffmpeg",
        "colmap",
        "mapanything_apache",
        "gsplat",
        "faster_gs",
        "brush",
        "splat_transform",
    }
    assert set(research) == {"gluemap", "vggt_omega", "improved_gs"}
    for entry in [*production.values(), *research.values(), *payload["supporting_locks"]]:
        assert COMMIT.fullmatch(entry["source"]["commit"])
        assert entry["source"]["repository"].startswith("https://")


def test_production_checkpoint_hashes_and_licenses_are_complete() -> None:
    payload = _lock()
    production = {entry["id"]: entry for entry in payload["production_candidates"]}
    for entry in production.values():
        assert entry["allowed_in_production"] is True
        assert entry["license"].get("expression") or entry["license"].get(
            "expression_for_approved_build"
        )
        for weight in entry["weights"]:
            assert SHA256.fullmatch(weight["sha256"])
            assert COMMIT.fullmatch(weight["revision"])
            assert weight["size_bytes"] > 0
            assert weight["license"]
    mapanything_weight = production["mapanything_apache"]["weights"]
    assert len(mapanything_weight) == 2
    hashes = {weight["path"]: weight["sha256"] for weight in mapanything_weight}
    assert hashes == {
        "model.safetensors": "fa06c0fdccefc5048e072c85935d5789b1e36b307f3859033c17f9dcb9fd5201",
        "dinov2_vitg14_pretrain.pth": "baf8467e50af277596bbbafa06887c177ee899ab46033649c383577d7e9309d3",
    }


def test_research_candidates_are_never_production_eligible() -> None:
    for entry in _lock()["research_only"]:
        assert entry["allowed_in_production"] is False
        assert entry["block_reason"]
