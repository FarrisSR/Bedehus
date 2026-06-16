#!/usr/bin/env python3
"""Minimal Mill controller HTTP mock for Python, Go and Rust clients."""

import argparse
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, UTC
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


@dataclass
class MillState:
    temp_type: str
    target_value: float
    current_temperature: float
    last_updated: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    lock: threading.Lock = field(default_factory=threading.Lock)

    def control_status(self) -> dict[str, object]:
        with self.lock:
            return {
                "ok": True,
                "type": self.temp_type,
                "target_temperature": self.target_value,
                "current_temperature": self.current_temperature,
                "last_updated": self.last_updated,
            }

    def set_temperature(self, payload: dict[str, object]) -> dict[str, object]:
        with self.lock:
            if "type" in payload and isinstance(payload["type"], str):
                self.temp_type = payload["type"]
            if "value" not in payload:
                raise ValueError("missing JSON field 'value'")
            self.target_value = float(payload["value"])
            self.last_updated = datetime.now(UTC).isoformat()
            return {
                "ok": True,
                "type": self.temp_type,
                "value": self.target_value,
                "last_updated": self.last_updated,
            }


class MillHandler(BaseHTTPRequestHandler):
    server_version = "MockMill/1.0"

    def _json_response(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        state: MillState = self.server.mill_state  # type: ignore[attr-defined]
        if self.path == "/control-status":
            self._json_response(200, state.control_status())
            return
        if self.path == "/health":
            self._json_response(200, {"ok": True})
            return
        self._json_response(404, {"ok": False, "error": f"unknown path: {self.path}"})

    def do_POST(self) -> None:
        state: MillState = self.server.mill_state  # type: ignore[attr-defined]
        if self.path != "/set-temperature":
            self._json_response(404, {"ok": False, "error": f"unknown path: {self.path}"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("JSON body must be an object")
            result = state.set_temperature(payload)
        except Exception as exc:
            self._json_response(400, {"ok": False, "error": str(exc)})
            return
        self._json_response(200, result)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mock Mill controller HTTP server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument("--port", type=int, default=18080, help="HTTP port")
    parser.add_argument("--temp-type", default="Normal", help="Initial Mill type")
    parser.add_argument("--target", type=float, default=17.0, help="Initial target temperature")
    parser.add_argument(
        "--current-temperature",
        type=float,
        default=17.0,
        help="Initial measured temperature for /control-status",
    )
    args = parser.parse_args()

    state = MillState(
        temp_type=args.temp_type,
        target_value=args.target,
        current_temperature=args.current_temperature,
    )
    with ThreadingHTTPServer((args.host, args.port), MillHandler) as server:
        server.mill_state = state  # type: ignore[attr-defined]
        print(
            f"Mock Mill controller listening on http://{args.host}:{args.port} "
            f"target={args.target:.1f} type={args.temp_type}",
            flush=True,
        )
        server.serve_forever()


if __name__ == "__main__":
    main()
