from __future__ import annotations

from pathlib import Path

from apps.desktop.camera_timeline import build_camera_timeline


def test_real_source_extract_colmap_camera_join_preserves_unregistered(tmp_path: Path) -> None:
    images = tmp_path / "images"; images.mkdir()
    for index in (0, 5, 9):
        (images / f"frame_{index:06d}.png").write_bytes(b"png")
    sparse = tmp_path / "sparse"; sparse.mkdir()
    (sparse / "cameras.txt").write_text(
        "# cameras\n7 PINHOLE 1920 1080 1000 990 960 540\n", encoding="utf-8"
    )
    (sparse / "images.txt").write_text(
        "# images\n"
        "41 1 0 0 0 0 0 0 7 frame_000000.png\n\n"
        "77 1 0 0 0 -2 0 0 7 frame_000009.png\n\n",
        encoding="utf-8",
    )
    sampling = {
        "fps": 30.0,
        "selected_frame_indices": [0, 5, 9],
        "timeline": [
            {"index": 0, "timestamp_seconds": 0.0, "status": "selected", "candidate": True, "reason": None},
            {"index": 5, "timestamp_seconds": 5 / 30, "status": "selected", "candidate": True, "reason": None},
            {"index": 6, "timestamp_seconds": 0.2, "status": "rejected", "candidate": True, "reason": "near-duplicate"},
        ],
    }
    timeline = build_camera_timeline(sampling, images, sparse)
    by_index = {item["source_frame_index"]: item for item in timeline}
    assert list(by_index) == [0, 5, 6, 9]
    assert by_index[0]["colmap_image_id"] == 41
    assert by_index[0]["camera"]["intrinsics"][0][0] == 1000
    assert by_index[0]["camera"]["width"] == 1920
    assert by_index[5]["registration_status"] == "unregistered"
    assert by_index[5]["camera"] is None
    assert by_index[6]["registration_status"] == "not_applicable"
    assert by_index[6]["reason"] == "near-duplicate"
    assert by_index[9]["colmap_image_id"] == 77
    assert by_index[9]["camera"]["cam2world"][0][3] == 2.0

