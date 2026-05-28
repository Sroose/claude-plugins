#!/usr/bin/env python3
"""agent-bus: registry + inbox operations for cross-session messaging.

Bus layout:
  ~/.claude/bus/registry/<NAME>.json  - active registrations
  ~/.claude/bus/inbox/                - flat dir; filename = <TO>--<TS>--<FROM>--<RAND>.json
  ~/.claude/bus/archive/              - processed messages moved here
"""
import json, os, sys, time, re, secrets, socket, hashlib
from pathlib import Path

BUS_ROOT = Path(os.environ.get("BUS_ROOT", os.path.expanduser("~/.claude/bus")))
# Identify sessions by *hostname*, not session_id. session_id changes across
# /resume within the same process, which breaks watchers spawned before the
# resume (they keep their old env). Hostname is stable for the host/container's
# lifetime, and a fresh Docker container gets a new hostname automatically.
SELF_HOST = socket.gethostname()
SELF_ID = os.environ.get("CLAUDE_CODE_SESSION_ID", "")  # retained for diagnostics
NAME_RE = re.compile(r"^[A-Z][A-Z0-9_-]{0,31}$")


def init_dirs():
    for d in ("registry", "inbox", "archive", "cwd-memo"):
        (BUS_ROOT / d).mkdir(parents=True, exist_ok=True)


def memo_path_for(host_cwd: str) -> Path:
    """The cwd-memo file path for a given host_cwd. Survives unregister so a
    later session in the same host directory (e.g. when a Docker container is
    re-created on /resume) can auto-rebind to the same agent name."""
    h = hashlib.sha256((host_cwd or "").encode()).hexdigest()[:16]
    return BUS_ROOT / "cwd-memo" / f"{h}.json"


def whoami():
    if not SELF_HOST:
        return None
    for f in (BUS_ROOT / "registry").glob("*.json"):
        try:
            d = json.loads(f.read_text())
            if d.get("container") == SELF_HOST:
                return d["name"]
        except Exception:
            continue
    return None


def cmd_whoami(args):
    name = whoami()
    if name:
        print(name)
    else:
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

    if entry.exists():
        try:
            d = json.loads(entry.read_text())
        except Exception:
            d = {}
        if d.get("container") != SELF_HOST:
            print(f"ERROR: name '{name}' is already held by another container:", file=sys.stderr)
            print(f"  container:  {d.get('container', '?')}", file=sys.stderr)
            print(f"  host_cwd:   {d.get('host_cwd', '?')}", file=sys.stderr)
            print(f"  started:    {d.get('started_at', '?')}", file=sys.stderr)
            print(f"  ", file=sys.stderr)
            print(f"  DO NOT auto-recover. If the holding container is dead, ASK THE USER to confirm before reclaiming.", file=sys.stderr)
            return 4
        # same container, fine — refresh below

    existing = whoami()
    if existing and existing != name:
        print(f"ERROR: this container is already registered as '{existing}'. Run /agent unregister first.", file=sys.stderr)
        return 5

    # $HOST_CWD is set by Docker wrappers that bind-mount the host cwd into the
    # container (so /workspace inside the container can be traced to a real host
    # path). On a native (non-container) install, fall back to the process cwd.
    host_cwd = os.environ.get("HOST_CWD", "") or os.getcwd()
    data = {
        "name": name,
        "container": SELF_HOST,
        "session_id": SELF_ID,  # diagnostic only; not the identity
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
    print(f"   Without this, no incoming messages will surface in this session.")
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
    # $HOST_CWD is set by Docker wrappers that bind-mount the host cwd into the
    # container (so /workspace inside the container can be traced to a real host
    # path). On a native (non-container) install, fall back to the process cwd.
    host_cwd = os.environ.get("HOST_CWD", "") or os.getcwd()
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
    payload = {
        "from": me, "to": to, "body": body,
        "ts": ts,
        "ts_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "id": fname[:-5],
    }
    # atomic write: tmp + rename within same dir → inotify fires MOVED_TO
    tmp = BUS_ROOT / "inbox" / f".tmp-{rand}.json"
    final = BUS_ROOT / "inbox" / fname
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.rename(final)
    print(f"sent to {to}: {fname}")
    print(f"📤 to {to}: {body}")
    # Warn the sender if no one is currently registered to receive this name.
    # The message still lands in the inbox — it just won't be auto-processed
    # until some session registers as <to>.
    target_entry = BUS_ROOT / "registry" / f"{to}.json"
    if not target_entry.exists():
        print(f"⚠  warning: no session is currently registered as '{to}'. "
              f"The message is sitting in {final.name} but won't surface until "
              f"some session runs `/agent register {to}`.", file=sys.stderr)
    return 0


def cmd_list(args):
    init_dirs()
    found = False
    for f in sorted((BUS_ROOT / "registry").glob("*.json")):
        try:
            d = json.loads(f.read_text())
            sid = (d.get("session_id", "") or "?")[:8]
            print(f"{d['name']:16}  sid={sid}…  cwd={d.get('cwd', '?')}  started={d.get('started_at', '?')}")
            found = True
        except Exception as e:
            print(f"{f.name}: parse error: {e}", file=sys.stderr)
    if not found:
        print("(no registered agents)")
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
