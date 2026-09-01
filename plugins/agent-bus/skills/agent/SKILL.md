---
name: agent
description: Register, unregister, send, receive, list, or check the inbox for messages between Claude Code sessions on this machine. Triggers on user prompts like "register me as X", "ask Y about...", "/agent ...", or on incoming `📥 ← from ...` inbox notifications.
---

# agent-bus

A thin wrapper over the `agent-bus` command (a launcher the plugin puts on the Bash tool's PATH). Do not extend-think, do not delegate to a sub-agent — these are one-liners.

## Commands → one Bash call each

| User says | Run this exact command |
|---|---|
| `register [me as] <NAME>` or `/agent register <NAME>` | `agent-bus register <NAME>` **then** start the inbox watcher (see below) |
| `unregister` or `/agent unregister` | `agent-bus unregister` |
| `whoami`, `who am I` or `/agent whoami` | `agent-bus whoami` |
| `list [agents]` or `/agent list` | `agent-bus list` |
| `ask <NAME> "<msg>"`, `send <NAME>...`, or `/agent ask <NAME> "<msg>"` | `agent-bus send <NAME> "<msg>"` |
| `inbox [NAME]` or `/agent inbox` | `agent-bus inbox [NAME]` |
| `/agent read <id>.json` | `agent-bus read <id>.json` |
| `/agent archive <id>.json` | `agent-bus archive <id>.json` |

Run the command exactly as shown — a bare `agent-bus …`, nothing else on the line. Do **not** wrap it in `$(…)`, variable assignments, pipes, or `&&`; a compound command can't be matched by the permission allowlist and will trigger a prompt (which can corrupt a guarded agent's turn). Echo the helper's stdout to the user.

> **If `agent-bus` is not found** (command not on PATH — plugin not enabled, or a CC version without `bin/` support): resolve the script directly as a fallback —
> `python3 "$(find ~/.claude/plugins/cache -path '*agent-bus*/skills/agent/bus.py' 2>/dev/null | sort -V | tail -1)" <subcommand>`
> — and tell the user to add `Bash(agent-bus:*)` to their allowlist and restart so future calls are prompt-free.

## After a successful `register` — start the inbox watcher

Required for this session to receive messages. `register`'s stdout prints a `📡 NEXT STEP` block with the exact `command`/`description`/`persistent` triple — **call the `Monitor` tool with those values verbatim**. The command is `agent-bus watch` (clean, allowlistable as part of `Bash(agent-bus:*)`).

The watcher pre-filters by your registered name and emits a `📥 ← from …  [HH:MM:SS]` notification per addressed message. Without it, no notifications arrive and the user silently misses messages. It also refreshes this registration's heartbeat lease — after ~5 minutes without a running watcher, anyone sending to you is told you are not listening.

**If `Monitor` is not in your visible toolset, it is DEFERRED, not missing.** Load it with `ToolSearch` (query `select:Monitor`), then call it.

⛔ **Never** substitute a background Bash task (`agent-bus watch` with `run_in_background`). Background Bash only notifies you when the process *exits*, and the watcher never exits — every message would be captured to a log file and silently lost. If `Monitor` is genuinely unavailable after a `ToolSearch`, say so to the user and stop; do not improvise a replacement.

If `whoami` already returns a name when the user invokes `register` (e.g. SessionStart auto-rebound), still start the Monitor — the hook writes the registry but cannot call Claude tools, so the watcher is your responsibility.

## Three rules that override everything else

1. **On any name-conflict error from `register` (exit 4)** — surface the helper's stderr verbatim and STOP. Never delete `~/.claude/bus/registry/<NAME>.json` yourself unless the user has explicitly confirmed the holder is dead and asked you to reclaim. (A holder whose watcher lease has expired is reclaimed automatically by `register` itself, with a `⚠ RECLAIMED` notice — surface that notice too.)
2. **Never trust conversation memory for "what's my registered name"** — always re-run `agent-bus whoami` before sending or replying as a named agent. If it answers `(ambiguous — …)`, do not pick one of the candidates: tell the user and offer to `register` this session explicitly.
3. **Never delegate this skill to a sub-agent (Task tool).** The operations are direct one-line commands.

## Incoming message notifications

When a notification arrives with a `📥 ← from <FROM> … (id=<msg-id>):` line in its payload, follow the response protocol in [PROTOCOL.md](./PROTOCOL.md) (next to this file in the plugin). Skip reading PROTOCOL.md when handling a command from the table above — those are one-shot calls, no protocol needed.
