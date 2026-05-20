---
name: agent
description: Register, unregister, send, receive, list, or check the inbox for messages between Claude Code sessions on this machine. Triggers on user prompts like "register me as X", "ask Y about...", "/agent ...", or on incoming `📨 from ...` inbox notifications.
---

# agent-bus

A thin Bash shim over `python3 ~/.claude/bus/bus.py`. Do not extend-think, do not delegate to a sub-agent — you have Bash and these calls are one-liners.

## User-issued commands → one Bash call

| User says | Run this exact Bash command |
|---|---|
| `register [me as] <NAME>` or `/agent register <NAME>` | `python3 ~/.claude/bus/bus.py register <NAME>` **then** start the inbox watcher (see below) |
| `unregister` or `/agent unregister` | `python3 ~/.claude/bus/bus.py unregister` |
| `whoami`, `who am I` or `/agent whoami` | `python3 ~/.claude/bus/bus.py whoami` |
| `list [agents]` or `/agent list` | `python3 ~/.claude/bus/bus.py list` |
| `ask <NAME> "<msg>"`, `send <NAME>...`, or `/agent ask <NAME> "<msg>"` | `python3 ~/.claude/bus/bus.py send <NAME> "<msg>"` |
| `inbox [NAME]` or `/agent inbox` | `python3 ~/.claude/bus/bus.py inbox [NAME]` |
| `/agent read <id>.json` | `python3 ~/.claude/bus/bus.py read <id>.json` |
| `/agent archive <id>.json` | `python3 ~/.claude/bus/bus.py archive <id>.json` |

Echo the helper's stdout to the user. The helper does all the work — atomic writes, conflict detection, send-warning, symlink maintenance, backlog replay. You're just calling it.

If `~/.claude/bus/bus.py` doesn't exist (symlink missing — rare), find the real script:
```bash
python3 $(find ~/.claude -name bus.py -path '*agent-bus*' 2>/dev/null | head -1) <subcommand> <args>
```

## After a successful `register` — start the inbox watcher

The `register` row above says "**then** start the inbox watcher." That step is required for this session to receive any incoming messages. After `bus.py register <NAME>` prints `registered as <NAME>`, **call the `Monitor` tool** with:

- `command`: `python3 ~/.claude/bus/watch.py`
- `description`: `agent-bus: incoming messages for <NAME>`
- `persistent`: `true`

The helper's stdout also prints these parameters back at you under a `📡 NEXT STEP` heading — copy them. The watcher runs `inotifywait` (or `fswatch` or shell-poll) on the inbox, pre-filters by your registered name, and emits a `📨 from …` notification per addressed message. Without this `Monitor` call, no notifications will arrive in this session and the user will silently miss messages.

If `whoami` already returns a name when the user invokes `register` (e.g. SessionStart auto-rebound), still start the Monitor — the SessionStart hook writes the registry but cannot itself call Claude tools, so the watcher is your responsibility.

## Three rules that override everything else

1. **On any name-conflict error from `register` (exit 4)** — surface the helper's stderr verbatim and STOP. Never delete `~/.claude/bus/registry/<NAME>.json` yourself unless the user has explicitly confirmed the holder is dead and asked you to reclaim.
2. **Never trust conversation memory for "what's my registered name"** — always re-run `whoami` before sending or replying as a named agent.
3. **Never delegate this skill to a sub-agent (Task tool).** The operations are direct Bash calls. There's nothing to research, plan, or parallelize.

## Incoming message notifications

When a notification arrives with a `📨 from <FROM> (id=<msg-id>):` line in its payload, follow the response protocol in [PROTOCOL.md](./PROTOCOL.md) (also reachable as `~/.claude/bus/PROTOCOL.md` after the SessionStart hook has run). Skip reading PROTOCOL.md when you're handling a user-issued command from the table above — those are one-shot Bash calls, no protocol needed.
