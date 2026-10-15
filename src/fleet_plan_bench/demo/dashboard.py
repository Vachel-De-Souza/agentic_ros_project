"""Live demo dashboard: a stdlib HTTP server with one self-contained page.

GET /        the page (Gazebo view via noVNC on the left, live panels on the right)
GET /state   JSON snapshot from ``get_state``
POST /start  starts (or restarts) the demo through ``on_start``
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

PAGE_FILE = Path(__file__).with_name("static") / "index.html"


class Dashboard:
    def __init__(
        self,
        get_state: Callable[[], dict[str, Any]],
        on_start: Callable[[], None],
        host: str = "0.0.0.0",
        port: int = 8080,
        novnc_port: int = 6080,
        view: str = "map",
    ) -> None:
        """``view`` is ``map`` (browser-only demo) or ``gazebo`` (embeds the noVNC view)."""
        page = PAGE_FILE.read_text(encoding="utf-8")
        page_bytes = (
            page.replace("__NOVNC_PORT__", str(novnc_port)).replace("__VIEW__", view).encode()
        )

        class Handler(BaseHTTPRequestHandler):
            def _send(self, code: int, body: bytes, ctype: str) -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                if self.path in ("/", "/index.html"):
                    self._send(200, page_bytes, "text/html; charset=utf-8")
                elif self.path.startswith("/state"):
                    self._send(200, json.dumps(get_state()).encode(), "application/json")
                else:
                    self._send(404, b"not found", "text/plain")

            def do_POST(self) -> None:
                if self.path.startswith("/start"):
                    on_start()
                    self._send(202, b"{}", "application/json")
                else:
                    self._send(404, b"not found", "text/plain")

            def log_message(self, *args: Any) -> None:
                pass

        self.server = ThreadingHTTPServer((host, port), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
