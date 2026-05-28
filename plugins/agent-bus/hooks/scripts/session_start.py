#!/usr/bin/env python3
"""SessionStart hook for agent-bus.

Two jobs:
1. Inject protocol guidance into the session so Claude knows how to handle
   inbox notifications and how to resolve the helper script.
2. Auto-rebind if there's a cwd-memo indicating this host directory was
   previously registered as some agent name.

(No symlink maintenance. The helper is resolved at call time via a
cache-scoped `find … | sort -V | tail -1` — see SKILL.md. Symlinks were
removed in 0.1.3 because a single shared ~/.claude/bus link can't serve a
container and the host at once, and the repair logic was unreachable through
a broken link.)
"""
import json, sys, os, glob, socket, hashlib
from pathlib import Path

try:
    inp = json.load(sys.stdin)
except Exception:
    inp = {}

sid = inp.get("session_id", "")
# $HOST_CWD is set by Docker wrappers that bind-mount the host cwd (so the
# in-container cwd like /workspace can be disambiguated back to a real host
# path). Outside of containers, fall back to the cwd the hook input reports.
host_cwd = os.environ.get("HOST_CWD", "") or inp.get("cwd", "")

guidance = (
    "[agent-bus plugin active]\n\n"
    "Invoke the bus via the `agent-bus` launcher (on PATH while the plugin is "
    "enabled): `agent-bus register <NAME>`, `agent-bus send <TO> \"...\"`, "
    "`agent-bus whoami`, etc. Run each bare — no `$(...)`, pipes, or `&&` — so it "
    "stays allowlistable and never triggers a permission prompt.\n\n"
    "This session may receive Monitor notifications from the inbox watcher. It "
    "pre-filters by your registered name — you only get events for messages addressed "
    "to you. Each notification's event payload looks like:\n\n"
    "    📨 from <FROM> (id=<msg-id>):\n"
    "    <body, may be multi-line>\n"
    "    📨 end\n\n"
    "Handle each one: print the body to the user, optionally reply via "
    "`agent-bus send …`, then `agent-bus archive <id>.json`. "
    "See the `/agent` skill for the full operation set."
)

# If a cwd-memo exists for this host_cwd, and this container isn't already
# registered, and the remembered name isn't currently held by some other live
# container, nudge Claude to auto-rebind on its next turn. This makes /resume
# (which spawns a new container with a fresh hostname) transparent: the
# resumed session reclaims its identity without the user having to type
# /agent register manually.
if host_cwd:
    memo_hash = hashlib.sha256(host_cwd.encode()).hexdigest()[:16]
    memo_path = os.path.expanduser(f"~/.claude/bus/cwd-memo/{memo_hash}.json")
    try:
        with open(memo_path) as fh:
            memo = json.load(fh)
        remembered = memo.get("name", "")
    except Exception:
        remembered = ""

    if remembered:
        my_host = socket.gethostname()
        held_by_other = False
        already_me = False
        for f in glob.glob(os.path.expanduser("~/.claude/bus/registry/*.json")):
            try:
                with open(f) as fh:
                    d = json.load(fh)
                if d.get("name") == remembered:
                    if d.get("container") == my_host:
                        already_me = True
                    else:
                        held_by_other = True
                    break
            except Exception:
                continue
        if not already_me and not held_by_other:
            # Auto-rebind directly here so the watcher (which is lazy-started
            # on first /agent invocation) sees the registration the moment it
            # comes up. Without this, /resume would leave the user "unbound"
            # until they manually invoke /agent.
            try:
                entry = Path.home() / ".claude" / "bus" / "registry" / f"{remembered}.json"
                entry.parent.mkdir(parents=True, exist_ok=True)
                import time as _time
                entry.write_text(json.dumps({
                    "name": remembered,
                    "container": my_host,
                    "session_id": sid,
                    "started_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
                    "cwd": os.environ.get("PWD", ""),
                    "host_cwd": host_cwd,
                    "auto_rebind": True,
                }, indent=2))
                rebind_status = f"already auto-rebound by SessionStart hook"
            except Exception:
                rebind_status = "auto-rebind attempt failed — please run /agent register {remembered}"
            guidance += (
                f"\n\n[host_cwd memo — auto-rebound as `{remembered}`]\n"
                f"This host directory's prior session was registered as `{remembered}`; "
                f"this session has been {rebind_status}. To actually receive messages you "
                f"must still start the inbox watcher: call the `Monitor` tool with "
                f"`command: agent-bus watch`, `description: agent-bus: incoming messages for "
                f"{remembered}`, `persistent: true`. (The hook writes the registry but cannot "
                f"call tools.) If the user wanted a different name, run `/agent unregister` then "
                f"register the desired name instead."
            )

out = {
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": guidance,
    }
}
print(json.dumps(out))
sys.exit(0)
