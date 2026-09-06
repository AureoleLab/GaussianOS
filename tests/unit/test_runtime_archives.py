from pathlib import Path
import stat
import zipfile

import pytest

from apps.desktop.portable import _safe_extract


@pytest.mark.parametrize("name", ["../escape", "root/../../escape", "C:/escape", "root/NUL.txt", "root/file:stream", "root/trailing. "])
def test_archive_rejects_windows_unsafe_paths_before_stripping(tmp_path: Path, name: str):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as out:
        out.writestr(name, b"bad")
    with pytest.raises((ValueError, RuntimeError)):
        _safe_extract(archive, tmp_path / "staged", strip_components=1)
    assert not list((tmp_path / "staged").rglob("*"))


def test_archive_rejects_links_duplicates_and_expansion_budget(tmp_path: Path):
    for case in ("link", "duplicate", "oversize"):
        archive = tmp_path / f"{case}.zip"
        with zipfile.ZipFile(archive, "w") as out:
            if case == "link":
                info = zipfile.ZipInfo("link")
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                out.writestr(info, "../outside")
            else:
                out.writestr("file", b"valid")
                if case == "duplicate":
                    out.writestr("FILE", b"invalid")
        with pytest.raises(RuntimeError):
            _safe_extract(archive, tmp_path / case, max_bytes=4 if case == "oversize" else 100)
        assert not list((tmp_path / case).rglob("*"))
