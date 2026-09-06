"""Graphical first-use setup, backed by the same verified Runtime installer."""
from __future__ import annotations

import threading

from .portable import ensure_runtime_phase, install, layout_paths, load_manifest, verify_runtime


def run_setup() -> int:
    from PySide6.QtCore import QObject, Signal, Qt
    from PySide6.QtWidgets import QApplication, QDialog, QLabel, QProgressBar, QPushButton, QVBoxLayout

    app = QApplication.instance() or QApplication([])
    dialog = QDialog()
    dialog.setWindowTitle("GaussianOS · 准备重建功能")
    dialog.setMinimumWidth(580)
    layout = QVBoxLayout(dialog)
    title = QLabel("首次使用正在准备重建功能")
    title.setStyleSheet("font-size: 20px; font-weight: 600; margin: 16px 0;")
    manifest = load_manifest()
    base_components = [c for c in manifest["components"] if c.get("install_phase", "base") == "base"]
    total_download = sum(c["source"].get("artifact", {}).get("size_bytes", 0) for c in base_components)
    installed_size = sum(c["installed_size_bytes"] for c in base_components)
    description = QLabel(f"基础资源首次下载最多 {total_download / 1024**3:.2f} GiB，安装后 {installed_size / 1024**3:.2f} GiB。\n"
                         "已安装的资源会复用。中断的下载会保留，下次继续。\n高级重建模型将在用到时自动下载。")
    description.setWordWrap(True)
    status = QLabel("正在检查已安装组件…")
    status.setWordWrap(True)
    progress = QProgressBar()
    progress.setRange(0, 1000)
    cancel = QPushButton("取消并稍后继续")
    for widget in (title, description, status, progress, cancel):
        layout.addWidget(widget)
    cancelled = threading.Event()

    class Signals(QObject):
        progress = Signal(str, int)
        finished = Signal(int, str)

    signals = Signals()
    result = {"exit_code": 2}

    def request_cancel():
        cancelled.set()
        cancel.setEnabled(False)
        status.setText("正在安全停止，已下载的内容会保留…")

    def display(message, value):
        status.setText(message)
        progress.setValue(value)

    def finish(code, message):
        result["exit_code"] = code
        status.setText(message)
        if code == 0:
            dialog.accept()
        else:
            cancel.setEnabled(True)
            cancel.setText("关闭")
            cancel.clicked.disconnect()
            cancel.clicked.connect(dialog.reject)

    def worker():
        try:
            def report(name, done, total):
                if cancelled.is_set():
                    raise InterruptedError("已停止安装，下次启动时可继续。")
                signals.progress.emit(f"正在下载重建资源：{done / 1024**2:.0f} / {total / 1024**2:.0f} MB",
                                      round(1000 * done / total) if total else 0)
            ensure_runtime_phase("base", report)
            # Missing on-demand components are normal. If an installed optional
            # component was damaged, restore it so preflight can proceed.
            repair_ids = {issue.component_id for issue in verify_runtime()
                          if issue.category != "runtime_missing" and issue.component_id}
            for component_id in sorted(repair_ids):
                if cancelled.is_set():
                    raise InterruptedError("已停止安装，下次启动时可继续。")
                install(component_id, report)
            signals.finished.emit(0, "重建功能准备就绪。")
        except Exception as exc:
            log = layout_paths(create=True).logs / "runtime-setup-error.txt"
            log.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
            signals.finished.emit(2, f"准备未完成：{exc}\n再次启动即可重试。诊断记录：{log}")

    signals.progress.connect(display, Qt.QueuedConnection)
    signals.finished.connect(finish, Qt.QueuedConnection)
    cancel.clicked.connect(request_cancel)
    # Keep the worker alive until it has safely closed its download/transaction.
    dialog.setWindowFlag(Qt.WindowCloseButtonHint, False)
    thread = threading.Thread(target=worker, name="GaussianOS-runtime-setup", daemon=False)
    thread.start()
    dialog.exec()
    cancelled.set()
    thread.join()
    return result["exit_code"]
