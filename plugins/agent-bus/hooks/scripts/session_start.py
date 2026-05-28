#!/usr/bin/env python3
"""SessionStart hook for agent-bus.

Three jobs:
1. Maintain a stable symlink at ~/.claude/bus/bus.py → the actual bus.py for
   this plugin install, so the SKILL.md and user commands can reference one
   fixed path regardless of where the plugin lives on disk.
2. Inject protocol guidance into the session so Claude knows how to handle
   inbox notifications.
3. Nudge auto-rebind if there's a cwd-memo indicating this host directory was
   previously registered as some agent name.
"""
import json, sys, os, glob, socket, hashlib
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = PLUGIN_ROOT / "skills" / "agent"

# (1) Maintain stable symlinks for bus.py, PROTOCOL.md, and watch.py so
# SKILL.md, the user, and the Monitor-tool command have fixed invocation paths.
#
# Use RELATIVE symlink targets. ~/.claude is often a shared bind-mount between a
# Docker container ($HOME=/home/claude) and the host ($HOME=/Users/<you>): same
# files, different absolute paths. An absolute symlink target is only valid in
# one namespace; a relative one (e.g. ../plugins/cache/.../bus.py) resolves
# correctly in both, since the link and target share the ~/.claude root.
try:
    bus_dir = Path.home() / ".claude" / "bus"
    bus_dir.mkdir(parents=True, exist_ok=True)
    for name in ("bus.py", "PROTOCOL.md", "watch.py"):
        target = SKILL_DIR / name
        link = bus_dir / name
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(os.path.relpath(target, link.parent))
except Exception:
    pass  # non-fatal; SKILL.md has a find-based fallback

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
    "The bus helper is invokable as `python3 ~/.claude/bus/bus.py <subcommand>` — a "
    "symlink maintained by this hook. (Fallback if the symlink is missing: "
    "`find ~/.claude -name bus.py -path '*agent-bus*' 2>/dev/null | head -1`.)\n\n"
    "This session may receive Monitor notifications from `agent-bus-inbox`. The watcher "
    "pre-filters by your registered name — you only get events for messages addressed to "
    "you. Each notification's event payload looks like:\n\n"
    "    📨 from <FROM> (id=<msg-id>):\n"
    "    <body, may be multi-line>\n"
    "    📨 end\n\n"
    "Handle each one: brief acknowledge to the user, optionally reply via `bus.py send`, "
    "then `bus.py archive <id>.json`. See `/agent` for the full operation set."
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
                f"this session has been {rebind_status}. If the user wanted a different name, "
                f"run `/agent unregister` and then register the desired name. Otherwise "
                f"continue normally — incoming messages addressed to `{remembered}` will flow to you."
            )

out = {
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": guidance,
    }
}
print(json.dumps(out))
sys.exit(0)
