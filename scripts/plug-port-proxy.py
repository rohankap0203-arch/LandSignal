#!/usr/bin/env python3
"""Mirror Cursor IDE plug port 51866 → Next.js :3000 when socat is unavailable.

Some Cloud Agent images remap the IDE preview to a high port (commonly 51866)
while the app still listens on 3000. Without this bridge the right-panel plug
gets ECONNREFUSED even though LandSignal is healthy on :3000.
"""
from __future__ import annotations

import select
import socket
import threading

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 51866
TARGET = ("127.0.0.1", 3000)


def _pipe(a: socket.socket, b: socket.socket) -> None:
    try:
        while True:
            ready, _, _ = select.select([a, b], [], [], 120)
            if not ready:
                break
            for src in ready:
                data = src.recv(65536)
                if not data:
                    return
                (b if src is a else a).sendall(data)
    except OSError:
        return
    finally:
        for s in (a, b):
            try:
                s.close()
            except OSError:
                pass


def main() -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((LISTEN_HOST, LISTEN_PORT))
    srv.listen(128)
    print(f"[plug-proxy] listening on {LISTEN_HOST}:{LISTEN_PORT} → {TARGET[0]}:{TARGET[1]}", flush=True)
    while True:
        client, _ = srv.accept()
        try:
            upstream = socket.create_connection(TARGET, timeout=5)
        except OSError:
            client.close()
            continue
        threading.Thread(target=_pipe, args=(client, upstream), daemon=True).start()


if __name__ == "__main__":
    main()
