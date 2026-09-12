import hashlib
import json
from pathlib import Path
import pytest
from scripts import bundle_colmap_crt as crt


def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(crt, "ROOT", tmp_path)
    redist, component = tmp_path / "redist", tmp_path / "colmap"
    redist.mkdir(); (component / "bin").mkdir(parents=True)
    (component / "bin/colmap.exe").write_bytes(b"native executable fixture")
    lock_dir = tmp_path / "third_party/locks"; lock_dir.mkdir(parents=True)
    entries = []
    for name in ("msvcp140.dll", "vcruntime140.dll"):
        payload = ("locked " + name).encode()
        (redist / name).write_bytes(payload)
        entries.append({"source": name, "filename": name, "size_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
    (lock_dir / "microsoft-vc-runtime.json").write_text(json.dumps({"files": entries}))
    return redist, component


def test_invalid_crt_input_does_not_partially_modify_component(tmp_path, monkeypatch):
    redist, component = fixture(tmp_path, monkeypatch)
    (redist / "vcruntime140.dll").write_bytes(b"unverified")
    with pytest.raises(RuntimeError, match="locked input"):
        crt.bundle_colmap_crt(redist, component)
    assert not (component / "bin/msvcp140.dll").exists()


def test_unknown_existing_crt_is_preserved(tmp_path, monkeypatch):
    redist, component = fixture(tmp_path, monkeypatch)
    target = component / "bin/msvcp140.dll"; target.write_bytes(b"existing unknown bytes")
    with pytest.raises(RuntimeError, match="unknown existing"):
        crt.bundle_colmap_crt(redist, component)
    assert target.read_bytes() == b"existing unknown bytes"


def test_locked_crt_bundle_is_repeatable_and_hash_verifiable(tmp_path, monkeypatch):
    redist, component = fixture(tmp_path, monkeypatch)
    checks = crt.bundle_colmap_crt(redist, component)
    assert checks == crt.bundle_colmap_crt(redist, component)
    for check in checks:
        assert hashlib.sha256((component / check["path"]).read_bytes()).hexdigest() == check["sha256"]
    assert (component / "MICROSOFT-VC-RUNTIME-NOTICE.txt").is_file()
