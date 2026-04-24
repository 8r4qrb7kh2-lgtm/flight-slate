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
import re
import socketserver
import threading
import time
import urllib.parse

from ui.flight import weather


_DEFAULT_PORT = 8080
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _parse_to_fahrenheit(raw: str) -> float | None:
    """Extract a temperature from a permissive string; convert C→F if needed.

    Accepts plain numbers ("72", "72.4") and Measurement strings as iOS
    Shortcuts renders them ("72° F", "22°C", "22 C", "295.15 K"). When the
    string contains a 'C' but no 'F', the number is treated as Celsius and
    converted; otherwise it's assumed to already be Fahrenheit (the param
    is named ``f``). Returns None if no number is found.
    """
    if not raw:
        return None
    match = _NUMBER_RE.search(raw)
    if match is None:
        return None
    try:
        value = float(match.group(0))
    except ValueError:
        return None
    upper = raw.upper()
    has_f = "F" in upper
    has_c = "C" in upper
    if has_c and not has_f:
        value = value * 9.0 / 5.0 + 32.0
    return value


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

        raw = (params.get("f") or [""])[0]
        temp_f = _parse_to_fahrenheit(raw)
        if temp_f is None:
            self._reply(400, "need ?f=<temperature> (e.g. 72, 72F, 22C)")
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
