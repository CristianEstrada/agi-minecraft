"""Minimal Source RCON client (the protocol Minecraft servers speak).

Spec: https://minecraft.wiki/w/RCON
"""

import socket
import struct
import threading

SERVERDATA_AUTH = 3
SERVERDATA_EXECCOMMAND = 2


class RconError(Exception):
    pass


class RconClient:
    def __init__(self, host: str, port: int, password: str, timeout: float = 10.0):
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._next_id = 1
        self._lock = threading.Lock()

    def connect(self) -> None:
        self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        req_id = self._send(SERVERDATA_AUTH, self.password)
        resp_id, _ = self._recv()
        if resp_id == -1 or resp_id != req_id:
            self.close()
            raise RconError("RCON authentication failed: check RCON_PASSWORD")

    def close(self) -> None:
        if self._sock:
            self._sock.close()
            self._sock = None

    def command(self, cmd: str) -> str:
        with self._lock:
            if self._sock is None:
                self.connect()
            try:
                return self._command(cmd)
            except (OSError, RconError):
                # Reconnect once: the server may have restarted.
                self.close()
                self.connect()
                return self._command(cmd)

    def _command(self, cmd: str) -> str:
        req_id = self._send(SERVERDATA_EXECCOMMAND, cmd)
        resp_id, body = self._recv()
        if resp_id != req_id:
            raise RconError(f"unexpected response id {resp_id}, expected {req_id}")
        return body

    def _send(self, ptype: int, body: str) -> int:
        req_id = self._next_id
        self._next_id += 1
        payload = struct.pack("<ii", req_id, ptype) + body.encode("utf-8") + b"\x00\x00"
        self._sock.sendall(struct.pack("<i", len(payload)) + payload)
        return req_id

    def _recv(self) -> tuple[int, str]:
        (length,) = struct.unpack("<i", self._read_exact(4))
        data = self._read_exact(length)
        resp_id, _ptype = struct.unpack("<ii", data[:8])
        return resp_id, data[8:-2].decode("utf-8", errors="replace")

    def _read_exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise RconError("connection closed by server")
            buf += chunk
        return buf

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.close()
