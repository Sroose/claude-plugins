#!/usr/bin/env python3
"""UserPromptSubmit hook for agent-bus: sync the session's display name
(sessionTitle) to whatever THIS session is registered as in the bus registry.

Resolution order matches bus.py my_entry(): session_id first, then a *unique*
hostname match. A bare hostname match would label every native session on a Mac
with whichever registration the directory listing happened to return first."""
import json, sys, os, glob, socket

BUS_ROOT = os.environ.get("BUS_ROOT", os.path.expanduser("~/.claude/bus"))

# The hook input carries this session's id; env is the fallback.
try:
    inp = json.loads(sys.stdin.read() or "{}")
except Exception:
    inp = {}
sid = inp.get("session_id", "") or os.environ.get("CLAUDE_CODE_SESSION_ID", "")
host = socket.gethostname()

entries = []
for f in sorted(glob.glob(os.path.join(BUS_ROOT, "registry", "*.json"))):
    try:
        with open(f) as fh:
            entries.append(json.load(fh))
    except Exception:
        continue

name = ""
for d in entries:
    if sid and d.get("session_id") == sid:
        name = d.get("name", "")
        break
else:
    mine = [d for d in entries if host and d.get("container") == host]
    if len(mine) == 1:
        name = mine[0].get("name", "")

if name:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "sessionTitle": name,
        }
    }))

sys.exit(0)
