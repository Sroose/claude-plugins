#!/usr/bin/env python3
"""SessionStart hook for agent-bus.

Four jobs:
1. Inject protocol guidance into the session so Claude knows how to handle
   inbox notifications and how to resolve the helper script.
2. Record this session's host_cwd in `session-cwd/<session_id>.json`. This hook
   runs at session start AND on /resume, so the value is always fresh and — the
   point — captured before the session can `cd` anywhere. Everything that keys
   off host_cwd (cwd-memo, auto-rebind) reads it back instead of calling
   os.getcwd() at some arbitrary later moment.
3. Re-inject this session's LIVE bus state (registration + watcher liveness).
   This hook also fires with `source == "compact"`, which is the case that
   matters: compaction does not kill the Monitor task or watch.py, it destroys
   the *model's* knowledge that they exist — after which the agent re-registers
   or starts a second watcher. Re-stating the facts after every compaction is
   the fix.
4. Auto-rebind — on `source == "resume"` ONLY — if there's a cwd-memo
   indicating this host directory was previously registered as some agent
   name. A brand-new session (`startup`, `clear`) starts unnamed even when a
   memo exists; it gets a one-line hint instead. The hook also records the
   resume flag in `session-cwd/<session_id>.json` so watch.py (which has no
   `source` of its own) applies the same rule when it starts.

(No symlink maintenance. The helper is resolved at call time via a
cache-scoped `find … | sort -V | tail -1` — see SKILL.md. Symlinks were
removed in 0.1.3 because a single shared ~/.claude/bus link can't serve a
container and the host at once, and the repair logic was unreachable through
a broken link.)
"""
import json, sys, os, re, glob, time, socket, hashlib, secrets, subprocess
from pathlib import Path

BUS_ROOT = Path(os.environ.get("BUS_ROOT", os.path.expanduser("~/.claude/bus")))
LEASE_TTL = 300  # keep in step with bus.py


# The three helpers below mirror bus.py (my_entry / lease_label / watcher_state),
# which is the authoritative implementation — `agent-bus status` prints the same
# picture. They are inlined rather than imported so this hook keeps working no
# matter where the plugin sits or what is on PATH: a hook that raises costs the
# user their session start.
def registry_entries():
    out = []
    for f in sorted(glob.glob(str(BUS_ROOT / "registry" / "*.json"))):
        try:
            with open(f) as fh:
                out.append(json.load(fh))
        except Exception:
            continue
    return out


def resolve_entry(sid, host, my_host_cwd):
    """(entry_or_None, unresolved_candidates) — session_id match first, then a
    *unique* hostname match whose host_cwd doesn't contradict ours. Hostname
    alone is not an identity (every native session on a Mac shares one), so
    without the directory check a bystander session would be told it is
    registered as its neighbour's agent."""
    entries = registry_entries()
    if sid:
        for d in entries:
            if d.get("session_id") and d.get("session_id") == sid:
                return d, []
    mine = [d for d in entries if d.get("container") == host] if host else []
    if len(mine) == 1:
        theirs = mine[0].get("host_cwd") or ""
        if theirs and my_host_cwd and theirs != my_host_cwd:
            return None, mine
        return mine[0], []
    return None, mine


def lease_is_stale(d):
    hb = d.get("heartbeat_at")
    return isinstance(hb, (int, float)) and (time.time() - hb) > LEASE_TTL


def lease_label(d):
    hb = d.get("heartbeat_at")
    if not isinstance(hb, (int, float)):
        return "lease=legacy(unknown)"
    age = int(time.time() - hb)
    return f"lease=STALE({age}s)" if age > LEASE_TTL else f"lease=fresh({age}s)"


def watcher_state(host):
    """(pid, alive) for this host's watcher pidfile, or (None, False)."""
    pf = BUS_ROOT / "log" / ("watcher-%s.pid" % re.sub(r"[^A-Za-z0-9_.-]", "_", host or "unknown"))
    try:
        pid = int(pf.read_text().strip())
    except Exception:
        return None, False
    try:
        os.kill(pid, 0)
    except Exception:
        return pid, False
    try:
        out = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                             capture_output=True, text=True, timeout=5)
        cmd = (out.stdout or "").strip()
    except Exception:
        cmd = ""
    # Only call it dead when `ps` positively names a different process; saying
    # "dead" about a live watcher would push the agent into starting a second one.
    if cmd and "watch.py" not in cmd and "agent-bus" not in cmd:
        return pid, False
    return pid, True


try:
    inp = json.load(sys.stdin)
except Exception:
    inp = {}

sid = inp.get("session_id", "")
# "startup" | "resume" | "clear" | "compact" — `compact` is why the live-state
# block below exists at all.
source = inp.get("source", "")
# $HOST_CWD is set by Docker wrappers that bind-mount the host cwd (so the
# in-container cwd like /workspace can be disambiguated back to a real host
# path). Outside of containers, fall back to the cwd the hook input reports.
host_cwd = os.environ.get("HOST_CWD", "") or inp.get("cwd", "")

# Persist host_cwd for this session_id. bus.py/watch.py prefer this over
# os.getcwd(), which drifts the moment the session `cd`s and used to make one
# session write two different cwd-memos.
#
# `resumed` is what gates the cwd-memo auto-rebind (here and in watch.py): only
# a `/resume` inherits the directory's remembered name. A `compact` fires on an
# already-running session, so it must not reset the flag — read the prior
# record and carry it forward.
resumed = source == "resume"
if sid and host_cwd and re.match(r"^[A-Za-z0-9_.-]+$", sid):
    try:
        d = BUS_ROOT / "session-cwd"
        d.mkdir(parents=True, exist_ok=True)
        rec = d / f"{sid}.json"
        if source == "compact":
            try:
                resumed = bool(json.loads(rec.read_text()).get("resumed", False))
            except Exception:
                resumed = False
        rec.write_text(json.dumps({"host_cwd": host_cwd, "source": source,
                                   "resumed": resumed}, indent=2))
    except Exception:
        pass

MONITOR_NOTE = (
    "If `Monitor` is not in your visible toolset, it is almost certainly a DEFERRED "
    "tool rather than a missing one — load it with ToolSearch (query `select:Monitor`) "
    "and then call it. Never substitute a background Bash `agent-bus watch` task: "
    "background Bash only notifies on process exit and the watcher never exits, so "
    "every message would be silently swallowed. If Monitor is genuinely unavailable, "
    "tell the user instead of improvising."
)

# Claude Code's built-in ListAgents/SendMessage already reach every native
# session on this machine, so on the host the bus is only needed to talk to a
# container. $HOST_CWD is what the Docker wrappers set; /.dockerenv covers one
# that doesn't. ASSUMPTION (untested): container sessions are NOT reachable
# through the built-in tools — that is the bus's remaining job.
in_container = bool(os.environ.get("HOST_CWD")) or os.path.exists("/.dockerenv")
NATIVE_NOTE = (
    "This is a native host session. To message other sessions on this machine, "
    "prefer Claude Code's built-in `ListAgents` / `SendMessage` tools (if not visible they are "
    "deferred: load them with ToolSearch). Use agent-bus only when a container session is "
    "involved, or when the user asks for it by name.\n\n"
)

guidance = (
    "[agent-bus plugin active]\n\n"
    + ("" if in_container else NATIVE_NOTE) +
    "Invoke the bus via the `agent-bus` launcher (on PATH while the plugin is "
    "enabled): `agent-bus register <NAME>`, `agent-bus send <TO> \"...\"`, "
    "`agent-bus whoami`, etc. Run each bare — no `$(...)`, pipes, or `&&` — so it "
    "stays allowlistable and never triggers a permission prompt.\n\n"
    "This session may receive Monitor notifications from the inbox watcher. It "
    "pre-filters by your registered name — you only get events for messages addressed "
    "to you. Each notification's event payload looks like:\n\n"
    "    📥 ← from <FROM>  [HH:MM:SS] (id=<msg-id>):\n"
    "    <body, may be multi-line>\n"
    "    📥 end\n\n"
    "Handle each one: print the body to the user, optionally reply via "
    "`agent-bus send …`, then `agent-bus archive <id>.json`. "
    "See the `/agent` skill for the full operation set.\n\n"
    + MONITOR_NOTE
)

# If a cwd-memo exists for this host_cwd, this session is a /resume, this
# container isn't already registered, and the remembered name isn't currently
# held by some other live container: auto-rebind. This makes /resume (which
# spawns a new container with a fresh hostname) transparent: the resumed
# session reclaims its identity without the user having to type /agent
# register manually.
#
# A brand-new session (startup, clear) does NOT inherit the name: the memo is
# keyed on the directory, not the session, and directories like $HOME or
# ~/code host many unrelated sessions. Those get a one-line hint and nothing
# is written. `compact` never rebinds either — a compacting session that was
# registered is already covered by the live-state block below.
memo_hint = ""
if host_cwd:
    memo_hash = hashlib.sha256(host_cwd.encode()).hexdigest()[:16]
    memo_path = BUS_ROOT / "cwd-memo" / f"{memo_hash}.json"
    try:
        with open(memo_path) as fh:
            memo = json.load(fh)
        remembered = memo.get("name", "")
        remembered_at = memo.get("last_registered_at", "")
    except Exception:
        remembered = ""
        remembered_at = ""

    if remembered and source != "resume":
        # Hint only on a genuinely new session. A `compact` re-fires on a
        # running session, which either is registered already (live-state block
        # below says so) or chose not to be — nagging it mid-session helps nobody.
        if source != "compact":
            memo_hint = (
                f"\n\n[host_cwd memo — not applied]\n"
                f"This host directory was last registered on the bus as `{remembered}`"
                + (f" ({remembered_at})" if remembered_at else "") +
                f", but this is a {source or 'new'} session, not a /resume, so it starts "
                f"unregistered. Do not register on your own initiative; if the user wants "
                f"that name back, `agent-bus register {remembered}` reclaims it."
            )
        remembered = ""

    if remembered:
        my_host = socket.gethostname()
        held_by_other = False
        already_me = False
        for f in glob.glob(str(BUS_ROOT / "registry" / "*.json")):
            try:
                with open(f) as fh:
                    d = json.load(fh)
                if d.get("name") == remembered:
                    if d.get("session_id") == sid or d.get("container") == my_host:
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
                entry = BUS_ROOT / "registry" / f"{remembered}.json"
                entry.parent.mkdir(parents=True, exist_ok=True)
                entry.write_text(json.dumps({
                    "name": remembered,
                    "container": my_host,
                    "session_id": sid,
                    # Lease fields, same as bus.py register: the watcher binds to
                    # `instance` and refreshes `heartbeat_at` every ~60s. Without
                    # them this entry would look like a legacy one and could
                    # never be reclaimed automatically.
                    "instance": secrets.token_hex(8),
                    "heartbeat_at": int(time.time()),
                    "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
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
                f"call tools.) The registration also carries a watcher lease that expires "
                f"after 5 minutes without a running watcher, so senders will be warned that "
                f"`{remembered}` is not listening. {MONITOR_NOTE} "
                f"If the user wanted a different name, run `/agent unregister` then "
                f"register the desired name instead."
            )
guidance += memo_hint

# ---- live state, re-injected on every start AND after every compaction ------
# Runs last so it also reports a registration the auto-rebind above just wrote.
# Silent when this session has no registration at all: nothing to preserve, and
# the guidance above already covers how to register.
try:
    _entry, _ambiguous = resolve_entry(sid, socket.gethostname(), host_cwd)
    _pid, _alive = watcher_state(socket.gethostname())
    if _entry:
        _watcher = (f"A watcher pidfile for this host names pid {_pid} ({'ALIVE' if _alive else 'DEAD'})."
                    if _pid is not None else
                    "There is no watcher pidfile for this host, so no watcher is running.")
        if _alive and lease_is_stale(_entry):
            # A live watcher that isn't refreshing THIS lease is bound to a
            # different registration — same verdict `agent-bus status` gives.
            _action = ("That watcher is alive but is NOT refreshing this registration's lease, so "
                       "it is serving a different one: re-run `agent-bus register <NAME>` to take "
                       "the lease back. Do not start a second watcher.")
        elif _alive:
            _action = ("Do NOT re-register and do NOT start a second watcher: a duplicate persistent "
                       "Monitor plus the pidfile takeover would fight each other, and the survivor "
                       "would be the wrong one.")
        else:
            _action = ("The watcher is not running — start it via the `Monitor` tool (`command: "
                       "agent-bus watch`, `persistent: true`; load Monitor with ToolSearch "
                       "`select:Monitor` if it isn't visible, and never substitute a background "
                       "Bash task). Do NOT re-register: the name is already yours.")
        guidance += (
            f"\n\n[agent-bus live state]\n"
            f"This session is registered as `{_entry.get('name', '?')}` ({lease_label(_entry)}). "
            f"{_watcher} {_action} "
            f"Run `agent-bus status` to re-verify this at any time — it re-derives "
            f"registration, watcher liveness and pending messages in one call."
        )
    elif _ambiguous:
        guidance += (
            f"\n\n[agent-bus live state]\n"
            f"{len(_ambiguous)} registrations share this hostname "
            f"({', '.join(c.get('name', '?') for c in _ambiguous)}) and none matches this "
            f"session's id, so this session's identity is AMBIGUOUS. Do not act as any of them; "
            f"run `agent-bus status` for the details, and `agent-bus register <NAME>` to bind a "
            f"name to this session."
        )
except Exception:
    pass  # never let diagnostics break a session start

out = {
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": guidance,
    }
}
print(json.dumps(out))
sys.exit(0)
