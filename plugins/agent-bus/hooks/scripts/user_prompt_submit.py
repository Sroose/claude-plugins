#!/usr/bin/env python3
"""UserPromptSubmit hook for agent-bus: sync the session's display name
(sessionTitle) to whatever THIS session is registered as in the bus registry.

session_id match only — deliberately NOT bus.py my_entry()'s hostname fallback.
That fallback exists for the watcher, which keeps a stale session_id in its env
after /resume. This hook gets the current session_id from its input, so a
hostname match can only ever name some other session: on a Mac every native
session shares one hostname, and a lone registration there labelled them all."""
import json, sys, os, glob

BUS_ROOT = os.environ.get("BUS_ROOT", os.path.expanduser("~/.claude/bus"))

# The hook input carries this session's id; env is the fallback.
try:
    inp = json.loads(sys.stdin.read() or "{}")
except Exception:
    inp = {}
sid = inp.get("session_id", "") or os.environ.get("CLAUDE_CODE_SESSION_ID", "")

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

if name:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "sessionTitle": name,
        }
    }))

sys.exit(0)
