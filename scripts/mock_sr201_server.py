#!/usr/bin/env python3
"""Minimal SR201 TCP mock for Python, Go and Rust clients."""

import argparse
import socketserver
import threading
from dataclasses import dataclass, field


@dataclass
class RelayState:
    relays: list[str]
    lock: threading.Lock = field(default_factory=threading.Lock)

    @classmethod
    def from_initial_state(cls, relay_count: int, initial_state: str | None) -> "RelayState":
        if initial_state is None:
            return cls(["0"] * relay_count)
        cleaned = initial_state.strip()
        if len(cleaned) != relay_count or any(ch not in "01" for ch in cleaned):
            raise ValueError(
                f"initial state must be exactly {relay_count} characters of 0/1, got {cleaned!r}"
            )
        return cls(list(cleaned))

    def snapshot(self) -> str:
        with self.lock:
            return "".join(self.relays)

    def handle_command(self, command: str) -> str:
        command = command.strip()
        with self.lock:
            before = "".join(self.relays)
            if not command:
                return before
            if command[0] == "0":
                return before

            action = command[0]
            relay_spec = command[1:].split(":", 1)[0].upper()
            targets = self._targets_for(relay_spec)
            if action == "1":
                for idx in targets:
                    self.relays[idx] = "1"
            elif action == "2":
                for idx in targets:
                    self.relays[idx] = "0"
            return before

    def _targets_for(self, relay_spec: str) -> list[int]:
        if relay_spec == "X":
            return list(range(len(self.relays)))
        if len(relay_spec) != 1 or not relay_spec.isdigit():
            raise ValueError(f"unsupported relay selector: {relay_spec!r}")
        relay_num = int(relay_spec)
        if relay_num < 1 or relay_num > len(self.relays):
            raise ValueError(f"relay {relay_num} out of range 1..{len(self.relays)}")
        return [relay_num - 1]


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


class SR201Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        state: RelayState = self.server.relay_state  # type: ignore[attr-defined]
        verbose: bool = self.server.verbose  # type: ignore[attr-defined]
        while True:
            data = self.request.recv(1024)
            if not data:
                return
            command = data.decode("ascii", errors="ignore").strip()
            try:
                response = state.handle_command(command)
                after = state.snapshot()
                if verbose:
                    print(
                        f"[{self.client_address[0]}:{self.client_address[1]}] {command or '<empty>'} -> "
                        f"before={response} after={after}",
                        flush=True,
                    )
            except Exception as exc:
                response = state.snapshot()
                if verbose:
                    print(
                        f"[{self.client_address[0]}:{self.client_address[1]}] {command or '<empty>'} -> error: {exc}",
                        flush=True,
                    )
            self.request.sendall(response.encode("ascii"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Mock SR201 TCP relay server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument("--port", type=int, default=6722, help="TCP port")
    parser.add_argument("--relays", type=int, default=8, help="Number of relays to emulate")
    parser.add_argument(
        "--initial-state",
        help="Initial relay state string, e.g. 01000000. Defaults to all open.",
    )
    parser.add_argument("--quiet", action="store_true", help="Disable per-command logging")
    args = parser.parse_args()

    if args.relays < 1 or args.relays > 8:
        raise SystemExit("--relays must be between 1 and 8")

    relay_state = RelayState.from_initial_state(args.relays, args.initial_state)
    with ThreadedTCPServer((args.host, args.port), SR201Handler) as server:
        server.relay_state = relay_state  # type: ignore[attr-defined]
        server.verbose = not args.quiet  # type: ignore[attr-defined]
        print(
            f"Mock SR201 listening on {args.host}:{args.port} with state {relay_state.snapshot()}",
            flush=True,
        )
        server.serve_forever()


if __name__ == "__main__":
    main()
