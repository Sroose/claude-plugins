# agent-bus design notes

How the plugin works under the hood, and the design choices behind it. Read this if you want to extend it, debug a problem, or understand why a particular decision was made.

## Mechanism at a glance

| Concern | Mechanism |
|---|---|
| Routing | Filename encodes addressing: `<TO>--<TS>--<FROM>--<RAND>.json` in `~/.claude/bus/inbox/` (flat directory, atomic writes via tmp+rename) |
| Wake-up | Each session runs a watcher via the plugin's `monitors/` declaration; events arrive as Claude Code task notifications, even between user prompts |
| Pre-filtering | The watcher emits only messages addressed to the registered name — receiving Claude doesn't filter again |
| Session identity | Hostname (stable across `/resume`, unique per host or fresh container) — see [Identity](#identity) |
| Surviving `/resume` | A `cwd-memo` per host directory persists past unregister; the next session's watcher auto-rebinds to that name on startup |
| Conflict avoidance | Name conflicts are refused; reclaiming requires explicit user confirmation |
| Late delivery | Messages that arrived before registration are surfaced on `/agent register` |
| Clean exit | `SessionEnd` hook auto-unregisters on `/clear`, `Ctrl-D`, logout. The cwd-memo persists so the next session in the same host directory rebinds automatically. |

## State layout

```
~/.claude/bus/
  registry/<NAME>.json          live registrations (keyed on hostname)
  inbox/<TO>--<TS>--<FROM>--<RAND>.json   pending messages
  archive/<filename>.json       handled messages
  cwd-memo/<sha>.json           per-host-directory remembered name (survives unregister)
  log/watcher.log               per-watcher diagnostics
  bus.py                        symlink → the helper for the currently-running plugin
```

## Identity

Identity is keyed on **hostname** (`socket.gethostname()`), not `CLAUDE_CODE_SESSION_ID`.

Why: `session_id` changes when you `/resume` within a single process. Subprocesses spawned before the resume keep their stale `session_id` in env — including the watcher. Hostname is stable for the host/container's lifetime and a fresh Docker container automatically gets a new hostname, so it's the natural durable identity key.

Side effect: two distinct Claude sessions running in the same container share a hostname. The plugin assumes one Claude per host/container (which is the typical configuration). If you need to run multiple, only one can hold a given agent name at a time — the second would see a name conflict.

## Auto-rebind via cwd-memo

When you `/agent register OBSIDIAN`, the plugin writes a memo to `~/.claude/bus/cwd-memo/<sha-of-host_cwd>.json` containing `{name: OBSIDIAN, host_cwd: …}`.

On `SessionEnd`, the registry entry is removed, but the memo is **kept**. When a fresh session starts in the same host directory, its watcher reads the memo on startup, finds no live registration for the remembered name, and claims it automatically.

`/agent unregister` (the explicit user command) **does** delete the memo — that's the opt-out path. `SessionEnd` (automatic cleanup on clean exit) does not.

## File watcher

The plugin picks the best available backend at startup:

1. `fswatch` (macOS, uses FSEvents) — `brew install fswatch`
2. `inotifywait` (Linux, uses inotify) — `apt install inotify-tools`
3. Shell-poll loop (~0.5s latency, no install) — fallback

All three produce the same output stream and feed the same pre-filtering logic. The watcher uses `stdbuf -oL` to line-buffer `inotifywait`'s stdout — without it, events can sit in the pipe buffer indefinitely under low traffic.

## Lifecycle of a message

1. **Sender** runs `/agent send TO "body"`.
   `bus.py send`: validates TO and sender's own registration, generates a filename `<TO>--<TS>--<FROM>--<RAND>.json`, writes it atomically (tmp + rename) into `~/.claude/bus/inbox/`. Prints `📤 to TO: <body>` to its own stdout so the sender sees what was sent.
2. **Recipient's watcher** sees the new file. Looks up its own registered name via hostname → registry → name. If the filename's `TO` prefix matches, reads the JSON and emits a pre-formatted `📨 from FROM (id=…): <body> 📨 end` line.
3. **Claude Code** delivers that line to the recipient session as a task notification. Receiving Claude prints a brief acknowledgement, optionally replies via `bus.py send`, and archives via `bus.py archive <id>.json`.

## Hooks

| Hook | Purpose |
|---|---|
| `SessionStart` | Maintain `~/.claude/bus/bus.py` symlink to the live plugin's helper. Inject protocol guidance into Claude's context. If a cwd-memo exists for the current host_cwd and the name is free, nudge Claude to auto-rebind. |
| `UserPromptSubmit` | Sync `sessionTitle` (the `/resume` picker label) to the registered name. |
| `SessionEnd` | Auto-unregister this session on clean exit. Skipped on `exit_reason=resume` so `/resume`-ing in the same container doesn't drop the registration. |

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
| "Note: no session is registered as X" when sending | Target session hasn't run `/agent register X` yet — the message is queued in the inbox until it does |
| Incoming message never surfaced | Check `~/.claude/bus/log/watcher.log`. If no `EMIT` line for the filename appears, the watcher's `my_name()` doesn't match — usually the receiver isn't registered. `/agent whoami` to check; `/agent register <NAME>` to force a backlog replay. |
| After `/resume`, monitor not running / no incoming events | `--plugin-dir` is per-launch — must be passed again on `claude --resume <id> --plugin-dir <path>`. Marketplace installs don't need the flag. |
| Old stale `*.json` in `registry/` | A session was force-killed without firing `SessionEnd`. The next `/agent register <NAME>` for that name will surface a conflict and ask whether to reclaim. |

## Known limits

- Two Claude sessions in the *same* container share a hostname — only one can hold a given name at a time.
- Force-kill (Ctrl-C twice, OOM, container kill) skips `SessionEnd` and leaves a stale registry entry. Recovery is user-confirmed reclaim.
- Hand-off to a truly idle Claude relies on Claude Code's notification delivery; in extreme cases (auto-compaction stripping system reminders), a message may not surface until the next user prompt. Backlog replay on `/agent register` is the recovery path.
