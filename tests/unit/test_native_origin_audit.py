from pathlib import Path

from scripts.audit_native_origins import audit_native_origins


def test_packager_rejects_unrelated_same_named_dll_and_changed_bytes(tmp_path: Path):
    locked = tmp_path / "locked"
    unrelated = tmp_path / "poppler"
    app = tmp_path / "app"
    for directory in (locked, unrelated, app / "_internal"):
        directory.mkdir(parents=True)
    for directory in (locked, unrelated, app / "_internal"):
        (directory / "icuuc.dll").write_bytes(b"wrong ABI even when filename matches")
    toc = tmp_path / "Analysis.toc"
    toc.write_text(repr([[("icuuc.dll", str(unrelated / "icuuc.dll"), "BINARY")]]))
    rejected = audit_native_origins(toc, app, {"locked": locked})
    assert rejected["status"] == "failed"
    assert any("Unapproved native origin" in issue for issue in rejected["issues"])
    toc.write_text(repr([[("icuuc.dll", str(locked / "icuuc.dll"), "BINARY")]]))
    assert audit_native_origins(toc, app, {"locked": locked})["status"] == "succeeded"
    (app / "_internal" / "icuuc.dll").write_bytes(b"tampered collected file")
    assert audit_native_origins(toc, app, {"locked": locked})["status"] == "failed"
