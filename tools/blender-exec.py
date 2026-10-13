#!/usr/bin/env python3
"""Run Python inside the persistent headless Blender (tools/blender-mcp.sh).

This is a CLI stand-in for the `blender` MCP server's `execute_blender_code`, for
sessions or scripts where the MCP tools aren't loaded. It talks to the same socket.

    tools/blender-exec.py script.py [--arg value ...]   # run a file
    tools/blender-exec.py -c "import bpy; result = {...}" # run a snippet

Each call runs in a fresh Python namespace, while the Blender scene (`bpy.data`)
persists between calls. Put return values in `result = {...}`. Arguments after the
script path are exposed inside Blender as the list `ARGS`. The exit status is 1 when
Blender reports an error.
"""
import json
import os
import socket
import sys

HOST = os.environ.get("BLENDER_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("BLENDER_MCP_PORT", "9876"))


def call(code: str, timeout: float = 300.0) -> dict:
    with socket.create_connection((HOST, PORT), timeout=timeout) as s:
        s.sendall(json.dumps({"type": "execute", "code": code, "strict_json": True}).encode() + b"\0")
        buf = b""
        while not buf.endswith(b"\0"):
            chunk = s.recv(1 << 16)
            if not chunk:
                break
            buf += chunk
    return json.loads(buf.rstrip(b"\0"))


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    if sys.argv[1] == "-c":
        code, args = sys.argv[2], sys.argv[3:]
    else:
        with open(sys.argv[1], encoding="utf-8") as f:
            code, args = f.read(), sys.argv[2:]
    code = "ARGS = {!r}\n".format(args) + code
    resp = call(code)
    print(json.dumps(resp, indent=1, default=str))
    return 0 if resp.get("status") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
