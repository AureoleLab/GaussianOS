from __future__ import annotations

import os
import subprocess
import sys

import pytest

from packages.external_process import external_environment, run_external


def test_portable_child_discards_developer_abi_and_toolchain_paths(tmp_path):
    runtime = tmp_path / "Runtime/tools/ffmpeg/bin"
    runtime.mkdir(parents=True)
    env = external_environment({
        "GAUSSIANOS_DISTRIBUTION_ROOT": str(tmp_path), "SystemRoot": os.environ.get("SystemRoot", "/"),
        "PATH": "C:/developer/Conda;C:/frozen/Application/_internal",
        "CONDA_PREFIX": "C:/developer/Conda", "CONDA_PREFIX_1": "C:/older",
        "PYTHONPATH": "C:/polluted", "PYTHONHOME": "C:/polluted",
        "CUDA_PATH_V12_8": "C:/developer/CUDA", "CUDA_HOME": "C:/developer/CUDA",
        "QT_PLUGIN_PATH": "C:/frozen/Qt", "_PYI_APPLICATION_HOME_DIR": "C:/frozen",
        "GAUSSIAN_FACTORY_ATTEMPT_ID": "retain-this",
    })
    assert str(runtime) in env["PATH"]
    assert "developer" not in env["PATH"] and "_internal" not in env["PATH"]
    assert not any(k.startswith(("CONDA_", "_PYI_", "CUDA_PATH")) for k in env)
    assert "PYTHONHOME" not in env and "PYTHONPATH" not in env and "QT_PLUGIN_PATH" not in env
    assert env["GAUSSIAN_FACTORY_ATTEMPT_ID"] == "retain-this"
    assert env["TORCH_HOME"] == str(tmp_path / "Cache/Torch")


def test_source_process_keeps_explicit_environment():
    env = {"PATH": "a-local-tool", "CUSTOM_VARIABLE": "retained"}
    assert external_environment(env) == env


def test_native_run_preserves_failure_and_unicode_output():
    result = run_external([sys.executable, "-X", "utf8", "-c", "print('中文 路径')"],
                          capture_output=True, text=True, encoding="utf-8", check=True)
    assert result.returncode == 0 and result.stdout.strip() == "中文 路径"
    with pytest.raises(subprocess.CalledProcessError) as failure:
        run_external([sys.executable, "-c", "import sys; print('native failure'); sys.exit(7)"],
                     capture_output=True, text=True, check=True)
    assert failure.value.returncode == 7 and "native failure" in failure.value.stdout


def test_native_timeout_terminates_child():
    with pytest.raises(subprocess.TimeoutExpired):
        run_external([sys.executable, "-c", "import time; time.sleep(60)"], timeout=0.1,
                     capture_output=True)
