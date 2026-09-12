from pathlib import Path
import pytest
from packages.native_paths import native_output_directory


@pytest.mark.parametrize("fail", [False, True])
def test_worker_native_output_restores_cwd_after_success_or_failure(tmp_path: Path, fail: bool):
    original = Path.cwd()
    target = tmp_path / "中文 用户" / ("nested-" + "x" * 70) / ("nested-" + "y" * 70)
    try:
        with native_output_directory(target) as relative:
            assert relative == "."
            Path(relative, "native-output.bin").write_bytes(b"native result")
            if fail:
                raise OSError("Native writer failed")
    except OSError:
        assert fail
    assert Path.cwd() == original
    assert (target / "native-output.bin").read_bytes() == b"native result"
