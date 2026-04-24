"""Tiny HTTP listener for inside-temperature pushes.

Designed to be the receiving end of an iOS Shortcut that reads the
HomePod's temperature sensor and POSTs/GETs the value here.

Endpoint:
    /inside-temp?f=<value>     (GET or POST)
        Update the cached inside temperature in degrees Fahrenheit.
        Returns 204 on success, 400 on a bad ?f=, 404 on any other path.

Optional second query param:
    /inside-temp?f=72.4&c=22.4   (c is ignored — accepted for clients
        that find it easier to send both units)

Status endpoint:
    /                          (GET)
        Returns a one-line status string for sanity checks
        (curl http://flight-slate.local:8080/).

iOS Shortcut wiring:
    1. Shortcut steps:
         - Get state of <HomePod accessory>'s Current Temperature
         - URL → http://flight-slate.local:8080/inside-temp?f=<Magic Variable>
         - Get Contents of URL (Method: GET)
    2. Add a Personal Automation that runs the Shortcut on a schedule
       (every 15 min works well; HomePod sensors update slowly).
"""

from __future__ import annotations

import http.server
import socketserver
import threading
import time
import urllib.parse

from ui.flight import weather


_DEFAULT_PORT = 8080


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 — http.server API
        self._dispatch()

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch()

    def _dispatch(self) -> None:
        try:
            parsed = urllib.parse.urlparse(self.path)
        except ValueError:
            self._reply(400, "bad url")
            return

        if parsed.path in ("", "/"):
            self._reply_status()
            return
        if parsed.path == "/inside-temp":
            self._handle_inside_temp(parsed.query)
            return
        self._reply(404, "not found")

    def _handle_inside_temp(self, query: str) -> None:
        # Accept ?f=NN.N from the URL; if the client posted form data, also
        # try the body. Anything else is ignored.
        params = urllib.parse.parse_qs(query)
        if "f" not in params:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length).decode("utf-8", errors="replace") if length > 0 else ""
            params = urllib.parse.parse_qs(body)

        raw = (params.get("f") or [""])[0].strip()
        try:
            temp_f = float(raw)
        except ValueError:
            self._reply(400, "need ?f=<fahrenheit>")
            return

        weather.set_inside_temp_f(temp_f)
        self._reply(204, "")

    def _reply_status(self) -> None:
        temp = weather.inside_temp_f()
        outside = weather.outside_temp_f()
        body = (
            f"flight-slate: ok\n"
            f"inside_f={temp if temp is not None else '--'}\n"
            f"outside_f={outside if outside is not None else '--'}\n"
            f"server_time={time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        )
        self._reply(200, body, content_type="text/plain")

    def _reply(self, status: int, body: str, *, content_type: str = "text/plain") -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        if data:
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if data:
            self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 — http.server API
        # Quiet — don't spam the journal with every Shortcut ping.
        return


class _ReusableTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def start(port: int = _DEFAULT_PORT) -> None:
    """Start the listener in a background daemon thread.

    Safe to call once at startup. Errors (e.g. port in use) are printed
    but do not crash the display.
    """
    try:
        server = _ReusableTCPServer(("0.0.0.0", port), _Handler)
    except OSError as exc:
        print(f"[flight-slate] inside-temp server: {exc}", flush=True)
        return
    thread = threading.Thread(
        target=server.serve_forever,
        name="inside-temp-http",
        daemon=True,
    )
    thread.start()
    print(f"[flight-slate] inside-temp listener on :{port}/inside-temp?f=...", flush=True)
