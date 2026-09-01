#!/usr/bin/env python3
"""agent-bus: registry + inbox operations for cross-session messaging.

Bus layout:
  ~/.claude/bus/registry/<NAME>.json  - active registrations
  ~/.claude/bus/inbox/                - flat dir; filename = <TO>--<TS>--<FROM>--<RAND>.json
  ~/.claude/bus/archive/              - processed messages moved here
  ~/.claude/bus/session-cwd/<SID>.json - per-session host_cwd captured at session start
"""
import json, os, sys, time, re, secrets, socket, hashlib
from pathlib import Path

BUS_ROOT = Path(os.environ.get("BUS_ROOT", os.path.expanduser("~/.claude/bus")))
# Identity is (session_id, hostname). session_id is exact but changes across
# /resume within the same process — watchers spawned before the resume keep the
# old value in their env — so hostname stays as the fallback. Hostname alone is
# NOT sufficient: a fresh Docker container gets a unique hostname, but every
# native session on the same Mac shares one, so a hostname match is only trusted
# when it is unique. See my_entry().
SELF_HOST = socket.gethostname()
SELF_ID = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
NAME_RE = re.compile(r"^[A-Z][A-Z0-9_-]{0,31}$")
# A registration carries a watcher lease: the watcher refreshes `heartbeat_at`
# every ~60s. No heartbeat for LEASE_TTL seconds means the session is gone
# (force-kill, OOM, container removed) even though the file is still there.
LEASE_TTL = 300
# session-cwd memos of sessions that never fired SessionEnd are swept eventually.
SESSION_CWD_TTL = 30 * 86400


def init_dirs():
    for d in ("registry", "inbox", "archive", "cwd-memo", "session-cwd"):
        (BUS_ROOT / d).mkdir(parents=True, exist_ok=True)
    gc_session_cwd()


def gc_session_cwd():
    """Best-effort sweep of session-cwd memos left by sessions that died without
    firing SessionEnd. A handful of stat() calls; never fatal."""
    cutoff = time.time() - SESSION_CWD_TTL
    try:
        for f in (BUS_ROOT / "session-cwd").glob("*.json"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
            except Exception:
                continue
    except Exception:
        pass


def session_cwd_path(sid: str) -> Path:
    return BUS_ROOT / "session-cwd" / f"{sid}.json"


def resolve_host_cwd() -> str:
    """The host-side directory this session belongs to.

    $HOST_CWD (set by Docker wrappers) → the session-cwd memo the SessionStart
    hook wrote (captured before the session could `cd`, rewritten on /resume) →
    the process cwd as a last resort. Plain os.getcwd() is wrong for any session
    that has `cd`-ed since it started: it would read and write a *different*
    cwd-memo than the one the session registered under."""
    hc = os.environ.get("HOST_CWD", "")
    if hc:
        return hc
    if SELF_ID:
        try:
            memo = json.loads(session_cwd_path(SELF_ID).read_text())
            if memo.get("host_cwd"):
                return memo["host_cwd"]
        except Exception:
            pass
    return os.getcwd()


def lease_age(d: dict):
    """Seconds since the entry's watcher last refreshed its lease, or None when
    the entry has no `heartbeat_at` at all — a legacy 0.1.x registration whose
    liveness is simply *unknown*. Callers must treat None conservatively (i.e.
    exactly as they behaved before leases existed): never auto-reclaim it."""
    hb = d.get("heartbeat_at")
    if not isinstance(hb, (int, float)):
        return None
    return int(time.time() - hb)


def lease_is_stale(d: dict) -> bool:
    age = lease_age(d)
    return age is not None and age > LEASE_TTL


def lease_label(d: dict) -> str:
    """One-column human summary of an entry's lease, for list/diagnostic output."""
    age = lease_age(d)
    if age is None:
        return "lease=legacy(unknown)"
    if age > LEASE_TTL:
        return f"lease=STALE({age}s)"
    return f"lease=fresh({age}s)"


def memo_path_for(host_cwd: str) -> Path:
    """The cwd-memo file path for a given host_cwd. Survives unregister so a
    later session in the same host directory (e.g. when a Docker container is
    re-created on /resume) can auto-rebind to the same agent name."""
    h = hashlib.sha256((host_cwd or "").encode()).hexdigest()[:16]
    return BUS_ROOT / "cwd-memo" / f"{h}.json"


def registry_entries():
    """Every parseable registry entry, as a list of dicts."""
    out = []
    for f in sorted((BUS_ROOT / "registry").glob("*.json")):
        try:
            out.append(json.loads(f.read_text()))
        except Exception:
            continue
    return out


def my_entry():
    """Resolve this session's registration → (entry_or_None, ambiguous_list).

    1. the entry whose `session_id` is ours — exact, and the only thing that
       distinguishes two native sessions on one Mac (they share a hostname);
    2. else the *only* entry for this hostname — kept as a fallback because a
       watcher spawned before a /resume carries a stale session_id in its env,
       and 0.1.x entries may have none at all;
    3. else None plus the same-hostname candidates, so the caller can say
       "ambiguous, re-register" instead of picking one at random (which is how
       a bystander session used to answer as somebody else's agent).
    """
    entries = registry_entries()
    if SELF_ID:
        for d in entries:
            if d.get("session_id") and d.get("session_id") == SELF_ID:
                return d, []
    if not SELF_HOST:
        return None, []
    mine = [d for d in entries if d.get("container") == SELF_HOST]
    if len(mine) == 1:
        return mine[0], []
    return None, mine


def whoami():
    d, _ = my_entry()
    return d.get("name") if d else None


def cmd_whoami(args):
    d, ambiguous = my_entry()
    if d:
        print(d.get("name", "(unnamed entry)"))
        return 0
    if ambiguous:
        # Several registrations share this hostname and none of them carries our
        # session_id — typical for native sessions on a Mac, where hostname is
        # not an identity. Guessing would answer as the wrong agent.
        print(f"(ambiguous — {len(ambiguous)} registrations share hostname '{SELF_HOST}' "
              f"and none matches this session_id)")
        for c in ambiguous:
            print(f"  {c.get('name', '?'):16}  sid={(c.get('session_id') or '?')[:8]}…  "
                  f"{lease_label(c)}  host_cwd={c.get('host_cwd', '?')}")
        print("Run `/agent register <NAME>` in this session to bind a name to it unambiguously.")
        return 0
    print("(unregistered)")
    return 0


def cmd_register(args):
    if len(args) != 1:
        print("usage: bus.py register <NAME>", file=sys.stderr); return 2
    name = args[0].upper()  # accept any case; normalize to uppercase
    if not NAME_RE.match(name):
        print(f"ERROR: name must match {NAME_RE.pattern} (letters, digits, _ and -; max 32 chars; must start with a letter)", file=sys.stderr); return 2
    if not SELF_HOST:
        print("ERROR: could not determine container hostname", file=sys.stderr); return 3

    init_dirs()
    entry = BUS_ROOT / "registry" / f"{name}.json"
    reclaim_notice = []  # printed only once the registration actually goes through

    if entry.exists():
        try:
            d = json.loads(entry.read_text())
        except Exception:
            d = {}
        if d.get("container") != SELF_HOST:
            age = lease_age(d)
            if age is not None and age > LEASE_TTL:
                # The holder's watcher stopped refreshing its lease long ago:
                # that session is gone (force-kill, OOM, container removed) and
                # left a file behind. Reclaim without asking — but say so
                # loudly, because the name is changing hands.
                reclaim_notice = [
                    f"⚠  RECLAIMED '{name}' from a dead registration (watcher lease expired):",
                    f"     previous container: {d.get('container', '?')}",
                    f"     previous host_cwd:  {d.get('host_cwd', '?')}",
                    f"     registered at:      {d.get('started_at', '?')}",
                    f"     lease expired {age - LEASE_TTL}s ago "
                    f"(last heartbeat {age}s ago, TTL {LEASE_TTL}s)",
                    "",
                ]
            else:
                print(f"ERROR: name '{name}' is already held by another container:", file=sys.stderr)
                print(f"  container:  {d.get('container', '?')}", file=sys.stderr)
                print(f"  host_cwd:   {d.get('host_cwd', '?')}", file=sys.stderr)
                print(f"  started:    {d.get('started_at', '?')}", file=sys.stderr)
                if age is None:
                    print(f"  lease:      none — entry predates heartbeat leases (0.1.x), liveness unknown", file=sys.stderr)
                else:
                    print(f"  lease:      fresh, last heartbeat {age}s ago — that watcher is alive", file=sys.stderr)
                print(f"  ", file=sys.stderr)
                print(f"  DO NOT auto-recover. If the holding container is dead, ASK THE USER to confirm before reclaiming.", file=sys.stderr)
                return 4
        # same container, fine — refresh below

    existing_entry, _ = my_entry()
    existing = existing_entry.get("name") if existing_entry else None
    if existing and existing != name:
        print(f"ERROR: this session is already registered as '{existing}'. Run /agent unregister first.", file=sys.stderr)
        if existing_entry.get("session_id") != SELF_ID:
            # Resolved via the hostname fallback, which is not proof of ownership
            # on a host where every native session shares one hostname.
            print(f"  NOTE: matched on hostname '{SELF_HOST}', not on this session's id. If "
                  f"'{existing}' belongs to a DIFFERENT session on this machine, do not "
                  f"unregister it — ask the user.", file=sys.stderr)
        return 5

    for line in reclaim_notice:
        print(line)

    host_cwd = resolve_host_cwd()
    data = {
        "name": name,
        "container": SELF_HOST,
        "session_id": SELF_ID,       # primary identity; hostname is the fallback
        # `instance` identifies THIS registration. The watcher binds to it and
        # stops heartbeating if it ever changes — so a superseded watcher can
        # never keep somebody else's lease alive.
        "instance": secrets.token_hex(8),
        "heartbeat_at": int(time.time()),  # refreshed ~every 60s by the watcher
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cwd": os.environ.get("PWD", ""),
        "host_cwd": host_cwd,
    }
    entry.write_text(json.dumps(data, indent=2))
    # Write the cwd-memo so a future session in this host_cwd can auto-rebind.
    # Survives /resume (which creates a new container) and clean exits.
    if host_cwd:
        memo = memo_path_for(host_cwd)
        memo.write_text(json.dumps({
            "name": name,
            "host_cwd": host_cwd,
            "last_registered_at": data["started_at"],
            "last_container": SELF_HOST,
        }, indent=2))
    print(f"registered as {name}")
    # Print the exact Monitor command the agent must invoke next. The SKILL.md
    # also instructs this; printing it here means Claude sees the directive
    # in tool output regardless of which doc was loaded. Use the `agent-bus`
    # launcher (clean, allowlistable, no $(...) — a prompt mid-turn can corrupt
    # a guarded agent). Fallback to the sibling watch.py path if the launcher
    # isn't on PATH.
    watch_path = Path(__file__).resolve().parent / "watch.py"
    print("")
    print(f"📡 NEXT STEP — start the inbox watcher (REQUIRED for this session to receive messages).")
    print(f"   Call the `Monitor` tool with:")
    print(f"     command:     agent-bus watch")
    print(f"     description: agent-bus: incoming messages for {name}")
    print(f"     persistent:  true")
    print(f"   (If `agent-bus` is not on PATH, use: python3 {watch_path})")
    print(f"   If `Monitor` is not in your visible toolset it is almost certainly a")
    print(f"   DEFERRED tool, not a missing one: load it with ToolSearch (query")
    print(f"   `select:Monitor`), then call it.")
    print(f"   ⛔ Do NOT fall back to running `agent-bus watch` as a background Bash")
    print(f"   task. Background Bash only notifies on process EXIT and the watcher")
    print(f"   never exits, so every message would be silently swallowed into a log.")
    print(f"   If Monitor is genuinely unavailable, TELL THE USER instead of improvising.")
    print(f"   Without a Monitor watcher, no incoming messages will surface in this session.")
    # Surface any messages that arrived BEFORE this registration — the watcher
    # would have dropped them with "unregistered, dropping" because my_name()
    # returned None at the time. They sit in the inbox; we replay them now.
    pending = sorted((BUS_ROOT / "inbox").glob(f"{name}--*.json"))
    if pending:
        print(f"")
        print(f"📬 {len(pending)} pending message(s) addressed to {name} (arrived before registration):")
        for p in pending:
            try:
                d = json.loads(p.read_text())
                body = d.get("body", "") or ""
                first_line = body.split("\n", 1)[0]
                preview = first_line[:80] + ("…" if (len(first_line) > 80 or "\n" in body) else "")
                print(f"  • from={d.get('from', '?')}  id={p.stem}")
                print(f"    {preview}")
            except Exception:
                print(f"  • {p.name} (parse error)")
        print(f"")
        print(f"Use `/agent read <id>.json` for full body, then `/agent archive <id>.json` when handled.")
    return 0


def cmd_unregister(args):
    name = whoami()
    if not name:
        print("not currently registered", file=sys.stderr); return 0
    (BUS_ROOT / "registry" / f"{name}.json").unlink()
    # Explicit unregister also forgets the cwd-memo, so a future session in
    # this host_cwd won't auto-rebind to the old name. Clean exit via SessionEnd
    # keeps the memo (only deletes the registry entry).
    host_cwd = resolve_host_cwd()
    if host_cwd:
        memo = memo_path_for(host_cwd)
        if memo.exists():
            memo.unlink()
    print(f"unregistered ({name})")
    return 0


def cmd_send(args):
    if len(args) < 2:
        print("usage: bus.py send <TO> <BODY...>", file=sys.stderr); return 2
    me = whoami()
    if not me:
        print("ERROR: this session is not registered. Run /agent register <NAME> first.", file=sys.stderr); return 3
    to = args[0].upper()  # accept any case; normalize to uppercase
    if not NAME_RE.match(to):
        print(f"ERROR: target name must match {NAME_RE.pattern}", file=sys.stderr); return 2
    body = " ".join(args[1:])
    init_dirs()

    ts = int(time.time())
    rand = secrets.token_hex(3)
    fname = f"{to}--{ts}--{me}--{rand}.json"
    ts_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())  # canonical, UTC
    hhmmss = time.strftime("%H:%M:%S", time.localtime())          # display, local
    payload = {
        "from": me, "to": to, "body": body,
        "ts": ts,
        "ts_iso": ts_iso,
        "id": fname[:-5],
    }
    # atomic write: tmp + rename within same dir → inotify fires MOVED_TO
    tmp = BUS_ROOT / "inbox" / f".tmp-{rand}.json"
    final = BUS_ROOT / "inbox" / fname
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.rename(final)
    print(f"sent to {to}: {fname}")
    # 📤 → = outbound. Timestamped so long bus exchanges stay legible on scrollback.
    print(f"📤 → to {to}  [{hhmmss}]: {body}")
    # Warn the sender if no one is currently registered to receive this name.
    # The message still lands in the inbox — it just won't be auto-processed
    # until some session registers as <to>.
    target_entry = BUS_ROOT / "registry" / f"{to}.json"
    if not target_entry.exists():
        print(f"⚠  warning: no session is currently registered as '{to}'. "
              f"The message is sitting in {final.name} but won't surface until "
              f"some session runs `/agent register {to}`.", file=sys.stderr)
    else:
        # A registry file is not proof of a listener: force-killed sessions leave
        # theirs behind for months, which made the absence of the warning above
        # falsely reassuring (senders would blind-retry into a dead name). The
        # watcher lease is the liveness signal.
        try:
            td = json.loads(target_entry.read_text())
        except Exception:
            td = {}
        age = lease_age(td)
        if age is not None and age > LEASE_TTL:
            print(f"⚠  warning: '{to}' is registered but its watcher lease expired "
                  f"{age - LEASE_TTL}s ago (last heartbeat {age}s ago) — that session is "
                  f"likely NOT listening. The message is queued in {final.name} and will "
                  f"surface when a session registers as '{to}' again.", file=sys.stderr)
    return 0


def cmd_list(args):
    init_dirs()
    found = False
    for f in sorted((BUS_ROOT / "registry").glob("*.json")):
        try:
            d = json.loads(f.read_text())
            sid = (d.get("session_id", "") or "?")[:8]
            print(f"{d['name']:16}  sid={sid}…  {lease_label(d):22}  "
                  f"cwd={d.get('cwd', '?')}  started={d.get('started_at', '?')}")
            found = True
        except Exception as e:
            print(f"{f.name}: parse error: {e}", file=sys.stderr)
    if not found:
        print("(no registered agents)")
    else:
        print(f"(lease: fresh = watcher heartbeat within {LEASE_TTL}s · STALE = session most "
              f"likely dead · legacy = 0.1.x entry, liveness unknown)")
    return 0


def cmd_inbox(args):
    init_dirs()
    target = args[0].upper() if args else whoami()
    if not target:
        print("not registered; specify a name: /agent inbox <NAME>", file=sys.stderr); return 2
    if not NAME_RE.match(target):
        print(f"ERROR: name must match {NAME_RE.pattern}", file=sys.stderr); return 2
    found = False
    for f in sorted((BUS_ROOT / "inbox").glob(f"{target}--*.json")):
        try:
            d = json.loads(f.read_text())
            print(f"{f.name}  from={d.get('from', '?')}  ts={d.get('ts_iso', '?')}  body={d.get('body', '')[:60]}")
        except Exception:
            print(f.name)
        found = True
    if not found:
        print(f"(no messages for {target})")
    return 0


def cmd_read(args):
    if len(args) != 1:
        print("usage: bus.py read <filename>", file=sys.stderr); return 2
    fname = args[0]
    src = Path(fname) if "/" in fname else BUS_ROOT / "inbox" / fname
    if not src.exists():
        print(f"ERROR: {src} not found", file=sys.stderr); return 4
    print(src.read_text())
    return 0


def cmd_archive(args):
    if len(args) != 1:
        print("usage: bus.py archive <filename>", file=sys.stderr); return 2
    fname = args[0]
    src = Path(fname) if "/" in fname else BUS_ROOT / "inbox" / fname
    if not src.exists():
        print(f"ERROR: {src} not found", file=sys.stderr); return 4
    init_dirs()
    dst = BUS_ROOT / "archive" / src.name
    src.rename(dst)
    print(f"archived: {dst}")
    return 0


def cmd_parse_filename(args):
    """Parse a bus filename into JSON {to, ts, from, rand}. For hooks/monitors."""
    if len(args) != 1:
        print("usage: bus.py parse-filename <filename>", file=sys.stderr); return 2
    base = args[0].rstrip().split("/")[-1]
    if base.endswith(".json"):
        base = base[:-5]
    if base.startswith(".tmp-"):
        print(json.dumps({"skip": "tmp"})); return 0
    parts = base.split("--")
    if len(parts) < 4:
        print(json.dumps({"error": "not a bus filename", "raw": args[0]})); return 0
    print(json.dumps({"to": parts[0], "ts": parts[1], "from": parts[2], "rand": parts[3]}))
    return 0


COMMANDS = {
    "init":          lambda a: (init_dirs(), print(f"initialized {BUS_ROOT}"))[1] or 0,
    "whoami":        cmd_whoami,
    "register":      cmd_register,
    "unregister":    cmd_unregister,
    "send":          cmd_send,
    "list":          cmd_list,
    "inbox":         cmd_inbox,
    "read":          cmd_read,
    "archive":       cmd_archive,
    "parse-filename": cmd_parse_filename,
}


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"usage: bus.py {{{','.join(COMMANDS)}}} [args...]", file=sys.stderr)
        sys.exit(2)
    sys.exit(COMMANDS[sys.argv[1]](sys.argv[2:]) or 0)
