#!/usr/bin/env bash
# Start, stop or check the headless Blender that backs the `blender` MCP server
# in .mcp.json (Blender Lab's official MCP add-on, background mode).
#
#   tools/blender-mcp.sh start | stop | status | restart
#
# It runs under nohup rather than systemd: the user OK'd that on 2026-10-12, so
# it does not come back after a reboot. Run `start` again then. The socket has
# no auth, so it binds loopback only. Each request runs synchronously, with a
# 300 s cap, so long Cycles renders belong in batch scripts (`blender -b -P`).
set -euo pipefail

BLENDER="${BLENDER_PATH:-$HOME/opt/blender-5.2.2-linux-x64/blender}"
HOST=127.0.0.1
PORT="${BLENDER_MCP_PORT:-9876}"
LOG_DIR="$HOME/.local/state/blender-mcp"
LOG="$LOG_DIR/blender-mcp.log"

pid() { ss -ltnpH "sport = :$PORT" 2>/dev/null | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2; }

case "${1:-status}" in
  start)
    if [[ -n "$(pid)" ]]; then echo "already running (pid $(pid)) on $HOST:$PORT"; exit 0; fi
    mkdir -p "$LOG_DIR"
    setsid nohup "$BLENDER" --online-mode -b --command blender_mcp --host "$HOST" --port "$PORT" \
      >"$LOG" 2>&1 </dev/null &
    for _ in $(seq 1 30); do [[ -n "$(pid)" ]] && break; sleep 1; done
    if [[ -n "$(pid)" ]]; then echo "started (pid $(pid)) on $HOST:$PORT; log $LOG"; else echo "failed; see $LOG" >&2; exit 1; fi
    ;;
  stop)
    p="$(pid)"; if [[ -z "$p" ]]; then echo "not running"; exit 0; fi
    kill "$p"; echo "stopped (pid $p)"
    ;;
  restart) "$0" stop; sleep 1; "$0" start ;;
  status)
    p="$(pid)"; if [[ -n "$p" ]]; then echo "running (pid $p) on $HOST:$PORT"; else echo "not running"; exit 1; fi
    ;;
  *) echo "usage: $0 start|stop|status|restart" >&2; exit 2 ;;
esac
