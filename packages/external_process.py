"""Keep frozen GUI DLLs and developer toolchains out of native child processes."""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

_dll_lock = threading.RLock()


def external_environment(environment: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if environment is None else environment)
    override = env.get("GAUSSIANOS_DISTRIBUTION_ROOT")
    if not (override or getattr(sys, "frozen", False)):
        return env
    executable_root = Path(sys.executable).resolve().parent
    root = Path(override).resolve() if override else (
        executable_root.parent if executable_root.name.casefold() == "application" else executable_root)
    for name in list(env):
        if name.startswith(("CONDA_", "_PYI_", "CUDA_PATH")) or name in {
            "PYTHONHOME", "PYTHONPATH", "PYTHONUSERBASE", "PYTHONSTARTUP", "VIRTUAL_ENV",
            "CUDA_HOME", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH",
            "CUDA_VISIBLE_DEVICES",
        }:
            env.pop(name, None)
    windows = Path(env.get("SystemRoot", r"C:\Windows"))
    paths = [root / "Runtime/tools/ffmpeg/bin", root / "Runtime/tools/colmap/3.13.0/bin",
             root / "Runtime/tools/git/cmd", windows / "System32", windows, windows / "System32/Wbem"]
    env["PATH"] = os.pathsep.join(str(p) for p in paths if p.is_dir())
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONUTF8"] = "1"
    env["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
    for name, relative in {"TORCH_HOME": "Torch", "HF_HOME": "HuggingFace",
                           "TORCH_EXTENSIONS_DIR": "TorchExtensions", "CUDA_CACHE_PATH": "CUDA"}.items():
        env[name] = str(root / "Cache" / relative)
    return env


@contextmanager
def clean_dll_search():
    if os.name != "nt" or not getattr(sys, "frozen", False):
        yield
        return
    # PyInstaller's SetDllDirectory is inherited independently of PATH. Keep
    # the change scoped to CreateProcess, restoring it before Qt loads again.
    with _dll_lock:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        get_directory = kernel.GetDllDirectoryW
        get_directory.argtypes = [ctypes.c_ulong, ctypes.c_wchar_p]
        get_directory.restype = ctypes.c_ulong
        set_directory = kernel.SetDllDirectoryW
        set_directory.argtypes = [ctypes.c_wchar_p]
        set_directory.restype = ctypes.c_int
        buffer = ctypes.create_unicode_buffer(32768)
        length = get_directory(len(buffer), buffer)
        if length >= len(buffer):
            raise RuntimeError("Inherited DLL directory exceeds supported size")
        previous = buffer.value if length else None
        if not set_directory(None):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            yield
        finally:
            if not set_directory(previous):
                raise ctypes.WinError(ctypes.get_last_error())


def popen_external(*args, **kwargs):
    kwargs["env"] = external_environment(kwargs.get("env"))
    with clean_dll_search():
        return subprocess.Popen(*args, **kwargs)


def run_external(*popenargs, input=None, capture_output=False, timeout=None, check=False, **kwargs):
    # Match subprocess.run while holding the DLL lock only during process
    # creation, not while COLMAP or FFmpeg executes.
    if input is not None:
        if kwargs.get("stdin") is not None:
            raise ValueError("stdin and input arguments may not both be used")
        kwargs["stdin"] = subprocess.PIPE
    if capture_output:
        if kwargs.get("stdout") is not None or kwargs.get("stderr") is not None:
            raise ValueError("stdout and stderr arguments may not be used with capture_output")
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    with popen_external(*popenargs, **kwargs) as process:
        try:
            stdout, stderr = process.communicate(input, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            exc.stdout, exc.stderr = process.communicate()
            raise
        except BaseException:
            process.kill()
            raise
        code = process.poll()
        if check and code:
            raise subprocess.CalledProcessError(code, process.args, output=stdout, stderr=stderr)
        return subprocess.CompletedProcess(process.args, code, stdout, stderr)
