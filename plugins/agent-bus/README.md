# agent-bus

Let two or more Claude Code sessions on the same machine talk to each other.

Register each session as a named agent (`OBSIDIAN`, `CODE`, `INFRA`, …) and they can send messages back and forth. Incoming messages wake the receiving Claude automatically and surface in its transcript — no user typing needed. Especially useful when agents on different codebases need to coordinate (e.g. contract negotiation, design alignment, sharing answers without you ferrying them by hand).

![demo](demo/demo.gif)
<!-- regenerate with: `vhs demo/res/demo.tape` from the repo root -->

## Install

```
/plugin marketplace add Sroose/claude-plugins
/plugin install agent-bus@sroose-plugins
```

For local development, clone the repo and either:
- Add it as a local marketplace: `/plugin marketplace add /path/to/claude-plugins` then `/plugin install agent-bus@sroose-plugins`
- Or load the plugin directly with `--plugin-dir`: `claude --plugin-dir /path/to/claude-plugins/plugins/agent-bus`

## Use

Either with the explicit slash forms:

```
/agent register OBSIDIAN          # claim a name in this session
/agent ask CODE "what's X?"       # send to another agent
/agent list                       # who's currently registered
/agent unregister                 # release the name
```

Or — easier — just ask Claude in natural language:

```
"register as OBSIDIAN"
"ask CODE our most-used linter preference and align with them for this project"
```

Incoming messages are auto-handled by the receiving Claude — you'll see lines like:

```
📨 from CODE (id=…):
src/server/auth/middleware.ts
📨 end
```

…and Claude decides whether to reply or hand off to you.

## Why it's interesting

- **Auto-rebind on `/resume`.** Register once in a directory; future sessions there reclaim the name automatically, even in a fresh Docker container.
- **Pre-filtered notifications.** The watcher only emits messages addressed to *you* — no UI noise from unrelated traffic.
- **Backlog replay.** Messages that arrive before you register are surfaced on your first `/agent register`.
- **Native file watcher.** Uses `fswatch` (macOS) or `inotifywait` (Linux) for zero-cost idle waits; falls back to a shell poll if neither is installed.
- **Send-time visibility.** `/agent send X` warns immediately if no session is currently registered as `X`.

## Commands

| Command | Effect |
|---|---|
| `/agent register <NAME>` | Claim a name in this session. Surfaces any pending messages addressed to it. |
| `/agent unregister` | Release the name and clear its cwd-memo. |
| `/agent whoami` | Show this session's current registered name. |
| `/agent list` | List all live registrations on this machine. |
| `/agent ask <T> "<msg>"` (alias: `send`) | Send to another named session. |
| `/agent inbox [NAME]` | List pending messages. |
| `/agent read <id>.json` | Show full message JSON. |
| `/agent archive <id>.json` | Move a handled message out of the inbox. |

Names: `^[A-Z][A-Z0-9_-]{0,31}$` — auto-uppercased.

## Dependencies

- Python 3.7+
- One of (for low-latency notifications; falls back to shell-poll otherwise):
  - macOS: `brew install fswatch`
  - Linux: `apt install inotify-tools`

## Docs

- [DESIGN.md](DESIGN.md) — how it works, state layout, identity model, Docker/HOST_CWD notes, statusline integration
- [CHANGELOG.md](CHANGELOG.md) — version history

## License

MIT — see the repo-level [LICENSE](../../LICENSE).
