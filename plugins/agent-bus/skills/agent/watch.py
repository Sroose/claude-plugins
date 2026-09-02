#!/usr/bin/env python3
"""agent-bus watcher.

Watches ~/.claude/bus/inbox/ for new message files. Per event, looks up the
current session's registered agent name (via $CLAUDE_CODE_SESSION_ID and the
registry) and only emits a line if the message is addressed to this session.

Output per relevant message (one line per notification):
    📨 from <FROM>: <body-truncated> (id=<filename-without-ext>)

Picks the best available file-watch backend at startup:
  inotifywait (Linux) → fswatch (macOS) → shell-poll fallback (universal).

Pre-filtering at this layer means Claude only sees notifications meant for it,
which dramatically cuts UI noise and per-event tool-call cost on the receiver.
"""
import json, os, re, sys, time, atexit, shutil, secrets, threading, subprocess, signal, socket, hashlib
from pathlib import Path
from datetime import datetime

BUS_ROOT = Path(os.environ.get("BUS_ROOT", os.path.expanduser("~/.claude/bus")))
INBOX = BUS_ROOT / "inbox"
REGISTRY = BUS_ROOT / "registry"
LOG_DIR = BUS_ROOT / "log"
INBOX.mkdir(parents=True, exist_ok=True)
REGISTRY.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "watcher.log"
# One watcher per host/container. Orphans (their session died without SIGTERM-ing
# them) otherwise accumulate and every one of them EMITs the same message, so the
# receiving session sees N copies of each notification.
PID_FILE = LOG_DIR / ("watcher-%s.pid" % re.sub(r"[^A-Za-z0-9_.-]", "_", socket.gethostname() or "unknown"))
HEARTBEAT_EVERY = 60  # seconds between lease refreshes (bus.py's LEASE_TTL is 300)


def log(msg):
    try:
        with open(LOG_FILE, "a") as fh:
            fh.write(f"{datetime.utcnow().isoformat()}Z [{os.getpid()}] {msg}\n")
    except Exception:
        pass


def resolve_host_cwd():
    """The host-side directory this session belongs to: $HOST_CWD (Docker
    wrappers) → the session-cwd memo the SessionStart hook wrote (captured
    before the session could `cd`) → the process cwd. Plain os.getcwd() is wrong
    for a session that has `cd`-ed: it would resolve a different cwd-memo than
    the one the session registered under. Mirrors bus.py resolve_host_cwd()."""
    hc = os.environ.get("HOST_CWD", "")
    if hc:
        return hc
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if sid:
        try:
            memo = json.loads((BUS_ROOT / "session-cwd" / f"{sid}.json").read_text())
            if memo.get("host_cwd"):
                return memo["host_cwd"]
        except Exception:
            pass
    return os.getcwd()


def auto_rebind_from_memo():
    """If this session's host_cwd has a cwd-memo and no live registration
    exists for that name, claim it. Makes /resume transparent: the new session
    (often in a fresh Docker container) reclaims the name the prior session
    held in this host directory. Idempotent — safe to call multiple times.

    Skipped if:
      - no host_cwd resolvable / no hostname / no memo
      - the name is currently held by a DIFFERENT host (conflict)
    """
    host = socket.gethostname()
    host_cwd = resolve_host_cwd()
    if not host or not host_cwd:
        return
    memo_hash = hashlib.sha256(host_cwd.encode()).hexdigest()[:16]
    memo_path = BUS_ROOT / "cwd-memo" / f"{memo_hash}.json"
    if not memo_path.exists():
        return
    try:
        memo = json.loads(memo_path.read_text())
    except Exception:
        return
    name = memo.get("name", "")
    if not name:
        return
    entry_path = REGISTRY / f"{name}.json"
    if entry_path.exists():
        try:
            existing = json.loads(entry_path.read_text())
        except Exception:
            existing = {}
        if existing.get("container") == host:
            log(f"AUTO-REBIND: already registered as {name}")
            return
        else:
            log(f"AUTO-REBIND skipped: '{name}' held by other container {existing.get('container', '?')}")
            return
    data = {
        "name": name,
        "container": host,
        "session_id": os.environ.get("CLAUDE_CODE_SESSION_ID", ""),
        # Same lease fields bus.py register writes — this IS a registration.
        "instance": secrets.token_hex(8),
        "heartbeat_at": int(time.time()),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cwd": os.environ.get("PWD", ""),
        "host_cwd": host_cwd,
        "auto_rebind": True,
    }
    entry_path.write_text(json.dumps(data, indent=2))
    log(f"AUTO-REBIND: registered as {name} from cwd-memo {host_cwd}")


def registry_entries():
    """Every parseable registry entry, as a list of dicts."""
    out = []
    for f in sorted(REGISTRY.glob("*.json")):
        try:
            with open(f) as fh:
                out.append(json.load(fh))
        except Exception:
            continue
    return out


def my_entry():
    """This session's registration, or None when it can't be resolved
    unambiguously. Same order as bus.py my_entry():

    1. session_id match — exact, and the only thing that separates two native
       sessions on one Mac (they share a hostname);
    2. else a *unique* hostname match whose host_cwd doesn't contradict ours —
       kept because a watcher spawned before a /resume carries a stale
       session_id in its env, and resolves the same directory through that old
       sid's session-cwd record;
    3. else None. Two same-hostname candidates used to make this watcher answer
       (and emit) as whichever entry the glob happened to return first."""
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    entries = registry_entries()
    if sid:
        for d in entries:
            if d.get("session_id") and d.get("session_id") == sid:
                return d
    host = socket.gethostname()
    if not host:
        return None
    mine = [d for d in entries if d.get("container") == host]
    if len(mine) != 1:
        return None
    # host_cwd decides only when both sides know it; unknown keeps prior behavior.
    theirs, ours = mine[0].get("host_cwd") or "", resolve_host_cwd()
    if theirs and ours and theirs != ours:
        return None
    return mine[0]


def my_name():
    """Return the name this session is registered as, or None."""
    d = my_entry()
    return d.get("name") if d else None


# ---------------------------------------------------------------- lease -----
# The registration this watcher keeps alive. `instance` is regenerated on every
# register, so a watcher that has been superseded can tell — and must then stop
# refreshing a heartbeat that would otherwise vouch for a session that is gone.
_lease = {"name": None, "instance": None, "bound": False}


def bind_lease():
    """Bind to the registration this watcher serves. Returns True on success."""
    d = my_entry()
    if not d or not d.get("name"):
        return False
    _lease.update(name=d["name"], instance=d.get("instance"), bound=True)
    log(f"LEASE bound: name={d['name']} instance={d.get('instance') or '(legacy entry)'}")
    return True


def heartbeat_once():
    """Refresh `heartbeat_at` on the bound entry.

    Re-reads first: if the entry is gone, or has been re-registered (different
    `instance`), this watcher no longer owns that lease — stop touching it and
    keep watching, since a later registration in this session may hand us a new
    one (picked up by the bind attempt below)."""
    if not _lease["bound"]:
        bind_lease()
        return
    path = REGISTRY / f"{_lease['name']}.json"
    try:
        with open(path) as fh:
            d = json.load(fh)
    except Exception:
        log(f"LEASE released: {path.name} is gone or unreadable — heartbeat stopped")
        _lease.update(bound=False)
        return
    if d.get("instance") != _lease["instance"]:
        log(f"LEASE released: '{_lease['name']}' was re-registered "
            f"(instance {_lease['instance']} → {d.get('instance')}) — heartbeat stopped")
        _lease.update(bound=False)
        return
    d["heartbeat_at"] = int(time.time())
    # tmp + rename, and NOT named *.json, so a concurrent registry scan can
    # never see a half-written entry or the temp file itself.
    tmp = REGISTRY / f".hb-{os.getpid()}.tmp"
    try:
        tmp.write_text(json.dumps(d, indent=2))
        tmp.replace(path)
    except Exception as e:
        log(f"LEASE refresh failed: {type(e).__name__}: {e}")


def heartbeat_loop():
    """Daemon thread: keeps the lease fresh for every backend, including the two
    that block forever inside a read() and never return to an event loop."""
    while True:
        time.sleep(HEARTBEAT_EVERY)
        try:
            heartbeat_once()
        except Exception as e:
            log(f"LEASE thread error: {type(e).__name__}: {e}")


# -------------------------------------------------------------- pidfile -----


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def pid_cmdline(pid):
    """The command line of a running pid, or "". Via `ps` because macOS has no
    /proc — and the host is where the orphans actually pile up."""
    try:
        out = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                             capture_output=True, text=True, timeout=5)
        return (out.stdout or "").strip()
    except Exception:
        return ""


def claim_pidfile():
    """Become the single watcher for this host/container: SIGTERM whatever the
    pidfile points at (if it is still one of ours), then record our own pid.

    The command-line check matters: pids are recycled, and killing an unrelated
    process because it inherited a dead watcher's pid would be far worse than
    tolerating one duplicate."""
    old = 0
    try:
        old = int(PID_FILE.read_text().strip())
    except Exception:
        old = 0
    if old and old != os.getpid() and pid_alive(old):
        cmd = pid_cmdline(old)
        if "watch.py" in cmd or "agent-bus" in cmd:
            log(f"PIDFILE takeover: SIGTERM previous watcher pid={old} ({cmd})")
            try:
                os.kill(old, signal.SIGTERM)
            except Exception as e:
                log(f"PIDFILE takeover: kill failed: {type(e).__name__}: {e}")
            deadline = time.time() + 2.0
            while time.time() < deadline and pid_alive(old):
                time.sleep(0.1)
            if pid_alive(old):
                log(f"PIDFILE takeover: pid={old} still alive after 2s — proceeding anyway")
        else:
            log(f"PIDFILE: pid={old} is not an agent-bus watcher ({cmd or 'unknown'}) — ignoring")
    try:
        PID_FILE.write_text(str(os.getpid()))
    except Exception as e:
        log(f"PIDFILE write failed: {type(e).__name__}: {e}")


def release_pidfile():
    """Remove the pidfile only if it still names us — a successor that took over
    while we were shutting down must keep its claim."""
    try:
        if int(PID_FILE.read_text().strip()) == os.getpid():
            PID_FILE.unlink()
    except Exception:
        pass


def emit_if_relevant(filename: str):
    filename = filename.strip()
    if not filename:
        return
    if filename.startswith(".tmp-"):
        log(f"skip tmp: {filename}")
        return
    name = my_name()
    if not name:
        log(f"event {filename}: unregistered, dropping")
        return
    if "--" not in filename:
        log(f"event {filename}: malformed, dropping")
        return
    to = filename.split("--", 1)[0]
    if to != name:
        log(f"event {filename}: not for me ({to} != {name}), dropping")
        return
    path = INBOX / filename
    if not path.exists():
        log(f"event {filename}: file vanished before read")
        return
    try:
        with open(path) as fh:
            d = json.load(fh)
    except Exception as e:
        log(f"event {filename}: json parse failed: {e}")
        return
    body = d.get("body", "") or ""
    msg_id = d.get("id", filename[:-5] if filename.endswith(".json") else filename)
    # Show the sender's send-time in LOCAL time (HH:MM:SS). The payload stores
    # epoch `ts` (and UTC ts_iso); datetime.fromtimestamp() converts to local.
    hhmmss = ""
    try:
        hhmmss = datetime.fromtimestamp(d["ts"]).strftime("%H:%M:%S")
    except Exception:
        sent = d.get("ts_iso", "") or ""
        hhmmss = sent[11:19] if len(sent) >= 19 else sent  # fallback: UTC slice
    stamp = f"  [{hhmmss}]" if hhmmss else ""
    log(f"EMIT {filename}: from={d.get('from','?')} bytes={len(body)}")
    # 📥 ← = inbound (distinct tray + arrow from the 📤 → outbound echo).
    print(f"📥 ← from {d.get('from', '?')}{stamp} (id={msg_id}):", flush=True)
    print(body, flush=True)
    print(f"📥 end", flush=True)


def watch_inotify():
    # inotifywait block-buffers stdout when piped, which can sit on events
    # indefinitely under low traffic. stdbuf -oL forces line-buffering.
    cmd = ["inotifywait", "-m", "-q", "-e", "create,moved_to", "--format", "%f", str(INBOX)]
    if shutil.which("stdbuf"):
        cmd = ["stdbuf", "-oL"] + cmd
    log(f"watch_inotify start: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    try:
        for line in proc.stdout:
            emit_if_relevant(line)
    finally:
        log(f"watch_inotify exit: returncode={proc.poll()}")
        proc.terminate()


def watch_fswatch():
    proc = subprocess.Popen(
        ["fswatch", "-0", "--event", "Created", "--event", "Renamed", str(INBOX)],
        stdout=subprocess.PIPE, bufsize=0,
    )
    try:
        buf = bytearray()
        while True:
            ch = proc.stdout.read(1)
            if not ch:
                break
            if ch == b"\0":
                full = buf.decode(errors="replace")
                emit_if_relevant(os.path.basename(full))
                buf.clear()
            else:
                buf.extend(ch)
    finally:
        proc.terminate()


def watch_poll():
    seen = {p.name for p in INBOX.iterdir() if p.is_file()}
    while True:
        time.sleep(0.5)
        try:
            cur = {p.name for p in INBOX.iterdir() if p.is_file()}
        except FileNotFoundError:
            INBOX.mkdir(parents=True, exist_ok=True)
            cur = set()
        for f in sorted(cur - seen):
            emit_if_relevant(f)
        seen = cur


def main():
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    atexit.register(release_pidfile)  # covers both SIGTERM (via sys.exit) and clean exit
    host = socket.gethostname()
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "(no-sid)")
    if shutil.which("inotifywait"):
        backend = "inotifywait"
    elif shutil.which("fswatch"):
        backend = "fswatch"
    else:
        backend = "poll"
    log(f"START backend={backend} host={host} session_id={sid} inbox={INBOX}")
    claim_pidfile()
    auto_rebind_from_memo()
    bind_lease()
    threading.Thread(target=heartbeat_loop, daemon=True).start()
    try:
        if backend == "inotifywait":
            watch_inotify()
        elif backend == "fswatch":
            watch_fswatch()
        else:
            watch_poll()
    except Exception as e:
        log(f"FATAL: {type(e).__name__}: {e}")
        raise


if __name__ == "__main__":
    main()
