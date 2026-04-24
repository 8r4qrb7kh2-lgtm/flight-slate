"""Periodic poll of a Google Nest thermostat for the inside temperature.

Reads the *ambient* temperature trait via Google's Smart Device Management
(SDM) API, converts to Fahrenheit, and feeds it to ``weather.set_inside_temp_f``.

One-time setup (see README in module docstring):
  1. Pay $5 at https://console.nest.google.com/device-access (Device Access).
  2. Create a Google Cloud project, enable the SDM API, create OAuth client.
  3. Run an OAuth flow once to obtain a refresh token.
  4. Set the four env vars below in env.flight-slate.sh on the Pi.

Required env vars:
  NEST_PROJECT_ID       — the Device Access project ID (UUID)
  NEST_CLIENT_ID        — OAuth 2.0 client ID
  NEST_CLIENT_SECRET    — OAuth 2.0 client secret
  NEST_REFRESH_TOKEN    — long-lived refresh token from the OAuth flow
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from ui.flight import weather


_TOKEN_URL = "https://oauth2.googleapis.com/token"
_SDM_DEVICES_URL = "https://smartdevicemanagement.googleapis.com/v1/enterprises/{project_id}/devices"
_TIMEOUT_S = 10.0
_THERMOSTAT_TYPE = "sdm.devices.types.THERMOSTAT"
_TEMPERATURE_TRAIT = "sdm.devices.traits.Temperature"


class _AuthState:
    def __init__(self) -> None:
        self.access_token: str | None = None
        self.access_token_expires_at: float = 0.0  # monotonic deadline


def _refresh_access_token(
    state: _AuthState,
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> str | None:
    payload = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode("utf-8")
    request = urllib.request.Request(
        _TOKEN_URL,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
        print(f"[flight-slate] nest token refresh failed: {exc}", flush=True)
        return None

    token = body.get("access_token")
    expires_in = body.get("expires_in", 3000)  # default ~50 min
    if not isinstance(token, str) or not token:
        return None
    state.access_token = token
    # Refresh 60s before actual expiry to avoid edge-of-validity races.
    state.access_token_expires_at = time.monotonic() + max(60.0, float(expires_in) - 60.0)
    return token


def _get_access_token(
    state: _AuthState,
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> str | None:
    if state.access_token is not None and time.monotonic() < state.access_token_expires_at:
        return state.access_token
    return _refresh_access_token(state, client_id, client_secret, refresh_token)


def _read_thermostat_temp_f(project_id: str, access_token: str) -> float | None:
    url = _SDM_DEVICES_URL.format(project_id=urllib.parse.quote(project_id, safe=""))
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
        print(f"[flight-slate] nest device fetch failed: {exc}", flush=True)
        return None

    devices = data.get("devices") if isinstance(data, dict) else None
    if not isinstance(devices, list):
        return None
    for device in devices:
        if not isinstance(device, dict) or device.get("type") != _THERMOSTAT_TYPE:
            continue
        traits = device.get("traits") or {}
        temp_c = (traits.get(_TEMPERATURE_TRAIT) or {}).get("ambientTemperatureCelsius")
        if isinstance(temp_c, (int, float)):
            return float(temp_c) * 9.0 / 5.0 + 32.0
    return None


def _poll_loop(
    project_id: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    interval_s: float,
) -> None:
    state = _AuthState()
    while True:
        token = _get_access_token(state, client_id, client_secret, refresh_token)
        if token is not None:
            temp_f = _read_thermostat_temp_f(project_id, token)
            if temp_f is not None:
                weather.set_inside_temp_f(temp_f)
        # Sleep regardless of success — bad credentials shouldn't hammer the API.
        time.sleep(interval_s)


def start(*, interval_s: float = 900.0) -> bool:
    """Start the background poller if all four env vars are set.

    Returns True if the poller started, False if any required env var is
    missing (silently — the inside-temp slot will simply stay empty).
    """
    project_id = os.environ.get("NEST_PROJECT_ID", "").strip()
    client_id = os.environ.get("NEST_CLIENT_ID", "").strip()
    client_secret = os.environ.get("NEST_CLIENT_SECRET", "").strip()
    refresh_token = os.environ.get("NEST_REFRESH_TOKEN", "").strip()
    if not (project_id and client_id and client_secret and refresh_token):
        print("[flight-slate] nest poller disabled (env vars not set)", flush=True)
        return False

    thread = threading.Thread(
        target=_poll_loop,
        args=(project_id, client_id, client_secret, refresh_token, interval_s),
        name="nest-poll",
        daemon=True,
    )
    thread.start()
    print(f"[flight-slate] nest poller running (every {int(interval_s)}s)", flush=True)
    return True
