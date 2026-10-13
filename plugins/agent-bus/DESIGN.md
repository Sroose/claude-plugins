# agent-bus design notes

How the plugin works under the hood, and the design choices behind it. Read this if you want to extend it, debug a problem, or understand why a particular decision was made.

## Mechanism at a glance

| Concern | Mechanism |
|---|---|
| Routing | Filename encodes addressing: `<TO>--<TS>--<FROM>--<RAND>.json` in `~/.claude/bus/inbox/` (flat directory, atomic writes via tmp+rename) |
| Wake-up | Each session runs a watcher via the plugin's `monitors/` declaration; events arrive as Claude Code task notifications, even between user prompts |
| Pre-filtering | The watcher emits only messages addressed to the registered name — receiving Claude doesn't filter again |
| Session identity | `session_id` first, hostname only as a *unique* fallback — see [Identity](#identity) |
| Liveness | Each registration carries a watcher heartbeat lease; no refresh for 300s ⇒ the session is dead — see [Heartbeat leases](#heartbeat-leases) |
| One watcher per host | `log/watcher-<hostname>.pid`: a starting watcher SIGTERMs the previous one |
| Compaction resilience | State is re-derivable (`agent-bus status`) and re-injected by `SessionStart`, which also fires on `source=compact` — see [Compaction](#compaction) |
| Surviving `/resume` | A `cwd-memo` per host directory persists past unregister; the next session's watcher auto-rebinds to that name on startup |
| Conflict avoidance | One decision table decides refresh / reclaim / refuse — see [Claiming a name](#claiming-a-name). A live holder is never displaced silently; `--force` is the confirmed override |
| Late delivery | Messages that arrived before registration are surfaced on `/agent register` |
| Clean exit | `SessionEnd` hook unregisters **only the exiting session's own entry** (matched on `session_id`). The cwd-memo persists so the next session in the same host directory rebinds automatically. |

## State layout

```
~/.claude/bus/
  registry/<NAME>.json          live registrations (see Identity + Heartbeat leases)
  inbox/<TO>--<TS>--<FROM>--<RAND>.json   pending messages
  archive/<filename>.json       handled messages
  cwd-memo/<sha>.json           per-host-directory remembered name (survives unregister)
  session-cwd/<session_id>.json host_cwd captured by SessionStart, before any `cd`
  log/watcher.log               per-watcher diagnostics
  log/watcher-<hostname>.pid    the one live watcher for this host/container
```

A registry entry (0.2.0):

```json
{
  "name": "OBSIDIAN", "container": "mac5", "session_id": "a1b2…",
  "instance": "9f3c…",          // regenerated on every register; the watcher binds to it
  "heartbeat_at": 1756713600,   // refreshed every ~60s by that watcher
  "started_at": "…", "cwd": "…", "host_cwd": "…"
}
```

The helper scripts (`bus.py`, `watch.py`) are **not** copied or symlinked here —
they're invoked via the `agent-bus` launcher (the plugin's `bin/agent-bus`, placed
on the Bash tool's PATH while the plugin is enabled). See Helper resolution below.

## Identity

Resolution order (`my_entry()`, implemented identically in `bus.py` and `watch.py`):

1. the registry entry whose `session_id` equals `$CLAUDE_CODE_SESSION_ID` — exact;
2. else, the entry for this hostname **if exactly one exists and its `host_cwd` doesn't contradict ours** (either side unknown ⇒ accepted, as before);
3. else none — `whoami` prints the candidates and asks you to re-register.

Rule 2's directory check is what stops a bystander session answering as an agent that merely shares its hostname; a pre-`/resume` watcher still passes it, because the stale `session_id` in its env resolves — via that sid's session-cwd record — to the same directory the entry names.

Up to 0.1.5 identity was keyed on hostname alone. That works for containers (each gets a unique hostname) but is actively wrong on a Mac: **every native session shares one hostname**, so to the bus they were all the same agent. Consequences seen in the field: `whoami` answering with a bystander's name, and — worse — any native session's clean exit unregistering a long-running agent (see [Lifecycle](#hooks)).

Hostname survives as a *fallback* because `session_id` changes when you `/resume` within a single process, and subprocesses spawned before the resume keep the stale value in env — including the watcher. The fallback is only trusted when it is unambiguous.

The display labels — `sessionTitle` from `UserPromptSubmit` and `statusline_fragment.py` — use **rule 1 only**. They always receive the current `session_id` from CC, so the stale-env reason for rule 2 doesn't apply to them, and a hostname match could only label this session with another session's name. Cost: after a `/resume` the entry keeps the pre-resume `session_id` (auto-rebind sees a same-hostname entry and leaves it alone), so the label stays blank until `agent-bus register <NAME>` refreshes it via claim rule 2.

## Heartbeat leases

A registry file is not proof that anyone is listening: a force-killed session leaves its entry behind indefinitely (stale entries months old have been observed in the wild), which made the send-time "no session registered as X" warning *falsely reassuring* — its absence meant nothing, and senders blind-retried into a dead name.

So every registration carries a lease:

- `register` (and hook/watcher auto-rebind) writes `instance` (random, per registration) and `heartbeat_at`.
- The session's watcher binds to `(name, instance)` at startup and refreshes `heartbeat_at` every ~60s from a daemon thread — a thread, because the `inotifywait`/`fswatch` backends block inside a read and never return to an event loop.
- Before each refresh the watcher re-reads the entry. If it is gone, or `instance` changed (someone re-registered the name), the watcher **stops heartbeating** — it must never vouch for a registration it no longer owns — and keeps watching, rebinding if a later registration in this session hands it a new lease.
- `heartbeat_at` older than **300s** ⇒ stale ⇒ that session is treated as dead.

What consumes the lease:

| Caller | Fresh lease | Stale lease | No `heartbeat_at` (0.1.x entry) |
|---|---|---|---|
| `register <NAME>` conflict (rules 3–5 of [Claiming a name](#claiming-a-name)) | refuse (exit 4), `--force` to override | auto-reclaim + loud notice (old container, host_cwd, how long expired) | refuse (exit 4) — liveness unknown, stay conservative |
| `send <NAME>` | silent | "registered but watcher lease expired Ns ago — likely not listening; message queued" | silent |
| `list` | `lease=fresh(Ns)` | `lease=STALE(Ns)` | `lease=legacy(unknown)` |

Legacy entries are deliberately treated exactly as 0.1.5 did, so a 0.1.5 session running concurrently during a rollout can never be reclaimed out from under itself.

## Claiming a name

`bus.py claim_decision(entry, my_host_cwd)` is the single authority on whether a session may take over an existing registration; `register` does nothing but act on its answer. Evaluated in order:

| # | Condition | Action | Why |
|---|---|---|---|
| 1 | entry's `session_id` is non-empty and equals ours | **refresh** | it is literally this session |
| 2 | entry's `container` == our hostname **and** both `host_cwd`s are non-empty and equal | **refresh-resume** | same host directory: a `/resume` renumbered our `session_id`, or this is the entry a pre-resume watcher still serves. Prints one line recording the `session_id` change. |
| 3 | lease stale (`heartbeat_at` older than 300s) | **reclaim** | the holder is dead — loud notice, name changes hands |
| 4 | no `heartbeat_at` (0.1.x entry) | **refuse** (exit 4) | liveness unknown; stay conservative |
| 5 | lease fresh | **refuse** (exit 4) | a live session holds this name |

`--force` overrides 4 and 5 (never 1–3, which don't refuse) and always prints what it displaced. It exists because the docs have always said "ASK THE USER to confirm before reclaiming" while giving the user no way to say yes; the alternative was agents deleting registry files by hand.

**`host_cwd` is the lineage key.** Hostname equality is not evidence of ownership — every native session on a Mac shares one — so rule 2 additionally requires the host directory to match. That's the same invariant the cwd-memo auto-rebind has always relied on ("the next session in this directory is the successor of the last one"), so it adds no new way to be wrong. An **unknown** `host_cwd` on either side (empty string) is never read as either answer: rule 2 doesn't fire and the lease rules decide.

Before 0.2.0's fix, rules 1–5 were a single `container != SELF_HOST` test, so on a Mac any native session could `register` a name a live session already held: the entry was silently rewritten with the new sid and instance, the displaced session's watcher released its lease on the instance change, and both `whoami`s still answered with the name. That is the exact configuration this release exists to prevent.

**Residual limit:** two native sessions in the *same* host directory remain indistinguishable to rule 2, so the second still takes the name (with the informational refresh line). That is outside the plugin's one-agent-per-host-directory contract — the same assumption the cwd-memo makes — and is not fixable without a per-session identity that survives `/resume`.

The identity resolution in [Identity](#identity) uses the same discriminator: a unique hostname match is only accepted when its `host_cwd` doesn't contradict ours, so a bystander session in another directory no longer answers `whoami` as the registered agent.

## Watcher singleton

Each watcher writes `~/.claude/bus/log/watcher-<hostname>.pid` at startup, after SIGTERM-ing whatever the previous pid was — but only if that pid is alive *and* its `ps -p <pid> -o command=` mentions `watch.py` or `agent-bus` (pids get recycled; `ps` rather than `/proc` because macOS has none). The pidfile is removed on clean exit, and only if it still names us.

Without this, orphaned watchers from dead sessions accumulate on the host: a live `watcher.log` showed ~9 pids reacting to each message and two of them emitting the same one, i.e. duplicate notifications in the receiving session.

## Compaction

Compaction destroys nothing on disk and kills no process: the Monitor task keeps running, `watch.py` keeps watching, the registration keeps its lease. What it destroys is the **model's** knowledge that any of it exists — and an agent that no longer remembers its watcher re-registers, or starts a second one, which then fights the incumbent over the pidfile.

The fix is that none of this state has to be remembered:

- **`agent-bus status`** re-derives it in one allowlist-clean call: registration (or `ambiguous`/`unregistered`), sid, instance, lease label, the watcher's pid and whether it is alive (`ps` cross-checked, so a recycled pid doesn't read as a watcher), pending message count, and a one-line verdict naming the single next action. It always exits 0 — it is a diagnostic, and a non-zero exit would itself read as "the bus is broken".
- **The `SessionStart` hook** fires with `source` in `startup` / `resume` / `clear` / **`compact`**, and appends an `[agent-bus live state]` block whenever this session resolves to a registration: the name, the lease, the watcher pid and liveness, and an explicit "do not re-register, do not start a second watcher if one is alive". Ambiguous identity gets its own variant. Unregistered sessions get nothing — there is no state to preserve, and the general guidance already covers registering.

The hook inlines its own copies of `my_entry` / `lease_label` / `watcher_state` rather than importing `bus.py`: a SessionStart hook that raises costs the user their session start, so it must not depend on the plugin's layout or on anything being on `PATH`. `bus.py` remains the authoritative implementation.

## Stable `host_cwd`

`host_cwd` decides which `cwd-memo` a session reads and writes. It used to be `$HOST_CWD or os.getcwd()`, evaluated per call — so a session that `cd`-ed after registering silently addressed a *different* memo (two memos for one agent, in two directories, have been observed).

The `SessionStart` hook now records `session-cwd/<session_id>.json` = `{"host_cwd": …}` from `$HOST_CWD` or the hook input's `cwd`. That hook also runs on `/resume`, so the record is always fresh and always pre-`cd`. Resolution everywhere is: `$HOST_CWD` → the session-cwd record for `$CLAUDE_CODE_SESSION_ID` → `os.getcwd()` as a last resort. `SessionEnd` deletes its own record; `bus.py init_dirs()` sweeps records older than 30 days left by sessions that were force-killed.

## Auto-rebind via cwd-memo

When you `/agent register OBSIDIAN`, the plugin writes a memo to `~/.claude/bus/cwd-memo/<sha-of-host_cwd>.json` containing `{name: OBSIDIAN, host_cwd: …}`.

On `SessionEnd`, that session's own registry entry is removed, but the memo is **kept**. When a fresh session starts in the same host directory, its watcher reads the memo on startup, finds no live registration for the remembered name, and claims it automatically.

`/agent unregister` (the explicit user command) **does** delete the memo — that's the opt-out path. `SessionEnd` (automatic cleanup on clean exit) does not.

## Helper resolution

The skill, the hooks, and the watcher all need to invoke `bus.py` / `watch.py`, which live in the versioned plugin cache (`~/.claude/plugins/cache/<marketplace>/agent-bus/<version>/skills/agent/`).

**Primary path — the `agent-bus` launcher (0.1.4+).** The plugin ships `bin/agent-bus`, and Claude Code adds a plugin's `bin/` to the Bash tool's PATH while the plugin is enabled. So callers just run `agent-bus <subcommand>`. The launcher resolves `bus.py`/`watch.py` relative to its own location (it's in the same version dir), and dispatches. Two payoffs:

- **Allowlistable.** `agent-bus register X` is a clean prefix → matches `Bash(agent-bus:*)` → no permission prompt. This matters beyond ergonomics: a prompt mid-turn can corrupt a guarded/limited-permission agent's transcript.
- **No path baked anywhere.** The launcher finds its siblings at runtime in the caller's namespace.

**Fallback — call-time `find`.** If the launcher isn't on PATH (plugin disabled, or a CC build without `bin/` support), resolve directly:

```bash
find ~/.claude/plugins/cache -path '*agent-bus*/skills/agent/bus.py' 2>/dev/null | sort -V | tail -1
```

- Scoped to `~/.claude/plugins/cache` — a blanket `~/.claude` search also matches the marketplace **repo clone** under `plugins/marketplaces/…` (no version dir), which sorts last lexically and would be picked wrongly by `tail -1`.
- `sort -V | tail -1` picks the highest installed version; runs in the caller's namespace.
- This form contains `$(…)` so it is **not** allowlistable — it will prompt. Use only as a degraded fallback.

**Why not a symlink?** Versions ≤0.1.2 symlinked `~/.claude/bus/bus.py` → the versioned script. That broke repeatedly: a single shared link can't serve a container ($HOME=/home/claude) and the host ($HOME=/Users/…) at once; the repair logic was only reachable *through* the link (circular when it dangled); version-pinned targets went stale. Dropped in 0.1.3 for call-time resolution; superseded in 0.1.4 by the launcher.

`--plugin-dir` dev installs live outside the cache — for dev, invoke the script by its explicit path.

## File watcher

The plugin picks the best available backend at startup:

1. `fswatch` (macOS, uses FSEvents) — `brew install fswatch`
2. `inotifywait` (Linux, uses inotify) — `apt install inotify-tools`
3. Shell-poll loop (~0.5s latency, no install) — fallback

All three produce the same output stream and feed the same pre-filtering logic. The watcher uses `stdbuf -oL` to line-buffer `inotifywait`'s stdout — without it, events can sit in the pipe buffer indefinitely under low traffic.

## Lifecycle of a message

The watcher is started by the **`Monitor` tool** — never as a background Bash task. Background Bash notifies only when the process *exits*, and the watcher never exits, so a `Bash(agent-bus watch, run_in_background)` fallback silently swallows every message into a log file. This actually happened: in recent Claude Code builds `Monitor` is a **deferred** tool (invisible until loaded), agents concluded it did not exist, and improvised the Bash fallback. `register`'s output, the SessionStart guidance, SKILL.md and PROTOCOL.md therefore all say the same thing: if `Monitor` isn't visible, load it with `ToolSearch` (`select:Monitor`); if it is genuinely unavailable, tell the user rather than improvise.

1. **Sender** runs `/agent send TO "body"`.
   `bus.py send`: validates TO and sender's own registration, generates a filename `<TO>--<TS>--<FROM>--<RAND>.json`, writes it atomically (tmp + rename) into `~/.claude/bus/inbox/`. Prints `📤 to TO: <body>` to its own stdout so the sender sees what was sent.
2. **Recipient's watcher** sees the new file. Looks up its own registered name via hostname → registry → name. If the filename's `TO` prefix matches, reads the JSON and emits a pre-formatted `📨 from FROM (id=…): <body> 📨 end` line.
3. **Claude Code** delivers that line to the recipient session as a task notification. Receiving Claude prints a brief acknowledgement, optionally replies via `bus.py send`, and archives via `bus.py archive <id>.json`.

## Hooks

| Hook | Purpose |
|---|---|
| `SessionStart` | Inject protocol guidance into Claude's context, plus the `[agent-bus live state]` block (fires on `source=compact` too — see [Compaction](#compaction)). Record `session-cwd/<session_id>.json`. If a cwd-memo exists for the current host_cwd and the name is free, auto-rebind (write the registry entry, with lease fields) and tell Claude to start the watcher. |
| `UserPromptSubmit` | Sync `sessionTitle` (the `/resume` picker label) to the registered name — `session_id` match only, see [Identity](#identity). |
| `SessionEnd` | Unregister **the entry whose `session_id` matches the hook input's** — never a bare hostname match, which used to let any exiting native session delete a colleague's registration. Also deletes its own session-cwd record. Skipped on `exit_reason=resume`. |

An entry whose `session_id` has drifted (a `/resume` renumbers it while the registry keeps the pre-resume value) is consequently no longer deleted by `SessionEnd`. That is intended: it expires on its own when the heartbeat lease runs out, which is a correct liveness signal rather than a guess.

## Running inside a Docker container

If you launch `claude` from a Docker wrapper that bind-mounts your project directory:

- Install `inotify-tools` in the image (`apt install -y inotify-tools`) for native low-latency events.
- Set `$HOST_CWD` to the host-side path of the mounted directory before exec'ing `claude`. The plugin uses this to disambiguate which **host** directory the session is in — the in-container cwd will typically be `/workspace` for every container, so it alone can't tell two projects apart. Without `$HOST_CWD`, auto-rebind still works but treats every container as the same "directory."
- Make sure the wrapper Dockerfile uses `ENTRYPOINT ["claude"]` (not `CMD`) so flags like `--plugin-dir` pass through to `claude` instead of being eaten by the base image's entrypoint. With `CMD`, `docker run image --plugin-dir …` replaces the command entirely; with `ENTRYPOINT`, args are appended to it.

## Statusline integration (live visible label)

`sessionTitle` set via the `UserPromptSubmit` hook is only visible in the `/resume` picker, not in the running session's header. For a live label, integrate `skills/agent/statusline_fragment.py` into your existing `~/.claude/statusline.py`:

```python
import subprocess, sys

session_json = sys.stdin.read()
# Use whichever absolute path the plugin actually lives at; for marketplace
# installs, it's somewhere under ~/.claude/plugins/cache/.
agent_name = subprocess.run(
    ["python3", "/path/to/agent-bus/skills/agent/statusline_fragment.py"],
    input=session_json, text=True, capture_output=True,
).stdout.strip()
# Prepend "[<agent_name>] " (or your preferred decoration) to your existing render.
```

The fragment script reads CC's session JSON from stdin (and falls back to `$CLAUDE_CODE_SESSION_ID`), looks up the registry, and prints the registered name or empty.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| After a compaction: "am I still registered? is my watcher running?" | Run `agent-bus status` — one call re-derives registration, lease, watcher pid/liveness, pending messages, and prints the next action. The `SessionStart` hook (which fires on `source=compact`) also re-injects an `[agent-bus live state]` block, so the answer is usually already in context. Never re-register or start a second watcher just because you don't remember the first. |
| "no session is currently registered as X" when sending | Target session hasn't run `/agent register X` yet — the message is queued in the inbox until it does |
| "registered but its watcher lease expired Ns ago" when sending | X's session is dead (force-killed) or never started its Monitor watcher. The message is queued; don't retry into it. `/agent list` shows the lease state of every name. |
| Incoming message never surfaced | Check `~/.claude/bus/log/watcher.log`. If no `EMIT` line for the filename appears, the watcher's `my_name()` doesn't match — the receiver isn't registered, or its identity is ambiguous. `/agent whoami` to check; `/agent register <NAME>` to force a backlog replay. |
| `whoami` prints "(ambiguous — N registrations share hostname …)" | Several sessions on this host and none carries this session's `session_id` (typical for native Mac sessions plus a pre-`/resume` entry). Run `/agent register <NAME>` here to bind the name to *this* session. |
| Every message arrives 2–9 times | Orphaned watchers from dead sessions. 0.2.0 kills them via the pidfile at watcher startup; to clear immediately, start one watcher (it SIGTERMs the incumbent) or `pkill -f watch.py`. |
| Watcher runs but nothing is ever delivered to Claude | The watcher was started as a background **Bash** task instead of via the `Monitor` tool. Background Bash only notifies on exit; the watcher never exits. Kill it and start it with `Monitor` (load the tool with `ToolSearch select:Monitor` if it isn't visible). |
| After `/resume`, monitor not running / no incoming events | `--plugin-dir` is per-launch — must be passed again on `claude --resume <id> --plugin-dir <path>`. Marketplace installs don't need the flag. |
| Old stale `*.json` in `registry/` | A session was force-killed without firing `SessionEnd`. Its lease expires after 300s, after which the next `/agent register <NAME>` reclaims the name automatically (with a notice). Entries written by 0.1.x have no lease and still require user-confirmed reclaim. |
| An agent lost its name to a "RECLAIMED" notice while alive | Its watcher wasn't running (or was killed), so the lease expired. Restart the watcher via `Monitor`, then re-register. |
| `register` refuses: "already held by a different directory on THIS host" | Another session on this machine holds the name and is alive. Ask the user. If that session is really dead its lease expires within 300s and the name is reclaimed automatically; otherwise have it run `/agent unregister`, or — with the user's explicit yes — `agent-bus register --force <NAME>`. |

## Known limits

- Two Claude sessions in the *same* container (or two native sessions on the same Mac) share a hostname. They are told apart by `session_id`, but only one watcher runs per hostname — the second one to start takes the pidfile and terminates the first.
- Force-kill (Ctrl-C twice, OOM, container kill) skips `SessionEnd` and leaves a registry entry behind; it becomes reclaimable 300s later when the lease expires.
- Hand-off to a truly idle Claude relies on Claude Code's notification delivery; in extreme cases (auto-compaction stripping system reminders), a message may not surface until the next user prompt. Backlog replay on `/agent register` is the recovery path.
