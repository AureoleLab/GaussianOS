from __future__ import annotations

import hashlib
import io
import zipfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from apps.desktop.runtime_downloads import download_verified, SegmentedReader


@pytest.fixture
def server():
    data = b"beta-component-payload-" * 300
    requests = []
    mode = {"value": "range"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            requests.append(self.headers.get("Range"))
            offset = int(self.headers.get("Range", "bytes=0-").split("=")[1].split("-")[0])
            if mode["value"] == "ignore":
                offset = 0
            self.send_response(206 if offset else 200)
            payload = data[offset:]
            if offset:
                start = offset + 1 if mode["value"] == "wrong-range" else offset
                self.send_header("Content-Range", f"bytes {start}-{len(data)-1}/{len(data)}")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    yield f"http://127.0.0.1:{httpd.server_port}/component", data, requests, mode
    httpd.shutdown()
    httpd.server_close()
    worker.join()


@pytest.mark.parametrize("mode", ["range", "ignore"])
def test_interrupted_download_resumes_or_restarts_safely(server, tmp_path, mode):
    url, data, requests, settings = server
    settings["value"] = mode
    target = tmp_path / "runtime.zip"
    target.with_suffix(".zip.part").write_bytes(data[:123])
    result = download_verified(url, target, size=len(data), digest=hashlib.sha256(data).hexdigest())
    assert result.read_bytes() == data
    assert requests == ["bytes=123-"]
    assert not target.with_suffix(".zip.part").exists()


def test_complete_corrupt_partial_is_replaced_instead_of_looping_416(server, tmp_path):
    url, data, requests, _ = server
    target = tmp_path / "runtime.zip"
    target.with_suffix(".zip.part").write_bytes(b"x" * len(data))
    download_verified(url, target, size=len(data), digest=hashlib.sha256(data).hexdigest())
    assert requests == [None] and target.read_bytes() == data


def test_wrong_content_range_never_commits_partial_bytes(server, tmp_path):
    url, data, _, settings = server
    settings["value"] = "wrong-range"
    target = tmp_path / "runtime.zip"
    target.with_suffix(".zip.part").write_bytes(data[:123])
    with pytest.raises(RuntimeError, match="invalid resume range"):
        download_verified(url, target, size=len(data), digest=hashlib.sha256(data).hexdigest(), attempts=1)
    assert not target.exists()


def test_valid_cached_asset_does_not_access_network(server, tmp_path):
    url, data, requests, _ = server
    target = tmp_path / "runtime.zip"
    target.write_bytes(data)
    download_verified(url, target, size=len(data), digest=hashlib.sha256(data).hexdigest())
    assert requests == []


def test_zip_reads_across_arbitrary_segment_boundaries_without_reassembly(tmp_path):
    contents = bytes(range(256)) * 257
    source = io.BytesIO()
    with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("中文/payload.bin", contents)
    payload = source.getvalue()
    parts = []
    for i, offset in enumerate(range(0, len(payload), 71)):
        path = tmp_path / f"part-{i}"
        path.write_bytes(payload[offset:offset+71])
        parts.append(path)
    with SegmentedReader(parts) as stream, zipfile.ZipFile(stream) as archive:
        assert archive.read("中文/payload.bin") == contents
