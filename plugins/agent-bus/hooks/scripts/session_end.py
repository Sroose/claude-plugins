#!/usr/bin/env python3
"""SessionEnd hook for agent-bus: auto-unregister *this* session.

Skip on `exit_reason=resume` — that means the user is /resume-ing within the
same container; the container is alive and may still want to receive messages
under its registered name. Only unregister on actual session terminations
(clear, prompt_input_exit, logout, etc.).

Ownership is by `session_id`, NOT hostname. Every native session on one Mac
shares a hostname, so a hostname match made any bystander session's clean exit
unregister a long-running agent that happened to live on the same machine — the
exiting session deleted somebody else's entry.

Entries whose session_id drifted (a /resume renumbers it, and the registry keeps
the pre-resume value) are therefore no longer deleted here. They expire on their
own via the watcher heartbeat lease — that is the intended replacement.
"""
import json, sys, os, re, glob
from pathlib import Path

BUS_ROOT = Path(os.environ.get("BUS_ROOT", os.path.expanduser("~/.claude/bus")))

try:
    inp = json.load(sys.stdin)
except Exception:
    sys.exit(0)

if inp.get("exit_reason") == "resume":
    sys.exit(0)

sid = inp.get("session_id", "")
if not sid:
    sys.exit(0)

for f in glob.glob(str(BUS_ROOT / "registry" / "*.json")):
    try:
        with open(f) as fh:
            d = json.load(fh)
        if d.get("session_id") == sid:
            os.unlink(f)
            break
    except Exception:
        continue

# The cwd-memo is deliberately kept (that's what lets the next session in this
# host directory auto-rebind); only this session's own host_cwd record goes.
if re.match(r"^[A-Za-z0-9_.-]+$", sid):
    try:
        (BUS_ROOT / "session-cwd" / f"{sid}.json").unlink()
    except Exception:
        pass

sys.exit(0)
