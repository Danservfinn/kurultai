"""Python helper client for the local brain-service Unix socket."""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any


def call(socket_path: str | Path, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(str(socket_path))
        sock.sendall((json.dumps({"method": method, "params": params or {}}) + "\n").encode("utf-8"))
        data = b""
        while not data.endswith(b"\n"):
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
    return json.loads(data.decode("utf-8"))
