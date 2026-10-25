from __future__ import annotations

import json
import shutil
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import aggregate
from .datasets import DATASETS, ROOT

SITE = ROOT / "site"
_cache = {"at": 0.0, "body": b""}
_lock = threading.Lock()


def data_json(images: str) -> bytes:
    with _lock:
        if time.monotonic() - _cache["at"] > 5:
            data = aggregate.build()
            data["images"] = images
            data["image_repos"] = {k: d.repo for k, d in DATASETS.items()}
            _cache.update(at=time.monotonic(), body=json.dumps(data, separators=(",", ":")).encode())
        return _cache["body"]


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SITE), **kwargs)

    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def send_bytes(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/data.json":
            return self.send_bytes(data_json("local"), "application/json")
        if path.startswith("/img/"):  # /img/<dataset>/<id>.png
            parts = path.split("/")
            if len(parts) == 4 and parts[2] in DATASETS and parts[3].removesuffix(".png").isdigit():
                f = DATASETS[parts[2]].dir / f"sim_{int(parts[3].removesuffix('.png'))}_initial.png"
                if f.exists():
                    return self.send_bytes(f.read_bytes(), "image/png")
            return self.send_error(404)
        return super().do_GET()


def main_serve(port: int) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def main_export(out: Path) -> None:
    """Site files plus a data.json snapshot; images load from HuggingFace."""
    out.mkdir(parents=True, exist_ok=True)
    for f in SITE.iterdir():
        if f.is_file():
            shutil.copy2(f, out / f.name)
    _cache["at"] = 0
    (out / "data.json").write_bytes(data_json("hf"))
    print(f"wrote {out}")
