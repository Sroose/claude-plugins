---
name: agent
description: Register, unregister, send, receive, list, or check the inbox for messages between Claude Code sessions on this machine. Triggers on user prompts like "register me as X", "ask Y about...", "/agent ...", or on incoming `📥 ← from ...` inbox notifications. For messaging between native (non-container) sessions, prefer the built-in ListAgents / SendMessage tools; use this when a container session is involved or the user names agent-bus.
---

# agent-bus

A thin wrapper over the `agent-bus` command (a launcher the plugin puts on the Bash tool's PATH). Do not extend-think, do not delegate to a sub-agent — these are one-liners.

## Host session? Use the built-in tools first

On a native host session (no `$HOST_CWD`, not in Docker), Claude Code's own `ListAgents` / `SendMessage` tools already reach every other native session on the machine — no registration, no watcher. Prefer them there. The bus is for traffic that involves a **container** session (ASSUMPTION, untested: those are not reachable through the built-in tools), or when the user explicitly asks for agent-bus.

The built-in tools address a session by its title, and a registered session's title is its bus name (the `UserPromptSubmit` hook sets it — unless the user renamed the session with `/rename`, which always wins). So `agent-bus register <NAME>` also gives a session a stable built-in address.

## Commands → one Bash call each

| User says | Run this exact command |
|---|---|
| `register [me as] <NAME>` or `/agent register <NAME>` | `agent-bus register <NAME>` **then** start the inbox watcher (see below) |
| user has confirmed taking a name off a live session | `agent-bus register --force <NAME>` (never without that confirmation) |
| `unregister` or `/agent unregister` | `agent-bus unregister` |
| `whoami`, `who am I` or `/agent whoami` | `agent-bus whoami` |
| `status`, "am I still registered/listening", or after a compaction | `agent-bus status` |
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

## After a compaction — look, don't guess

Compaction does not kill the Monitor task or the watcher process; it erases *your* memory that they exist. Re-registering or starting a second watcher on that basis is the standard failure. One call re-derives everything:

```bash
agent-bus status
```

It prints your registration (or "ambiguous"/"unregistered"), the watcher pid and whether it's alive, pending message count, and a verdict line with the single next action. Follow that verdict — do not start a watcher when one is already alive. The `SessionStart` hook also re-injects this state into your context after every compaction, so it's usually already there.

## Three rules that override everything else

1. **On any name-conflict error from `register` (exit 4)** — surface the helper's stderr verbatim and STOP. A holder whose watcher lease has expired is reclaimed automatically (`⚠ RECLAIMED` notice — surface that too), so an exit 4 means the holder is either alive or of unknown liveness. Do **not** work around it: never delete `~/.claude/bus/registry/<NAME>.json` by hand. If the user explicitly confirms the holder should be displaced, run `agent-bus register --force <NAME>`, which prints what it displaced.
2. **Never trust conversation memory for "what's my registered name"** — always re-run `agent-bus whoami` before sending or replying as a named agent. If it answers `(ambiguous — …)`, do not pick one of the candidates: tell the user and offer to `register` this session explicitly.
3. **Never delegate this skill to a sub-agent (Task tool).** The operations are direct one-line commands.

## Incoming message notifications

When a notification arrives with a `📥 ← from <FROM> … (id=<msg-id>):` line in its payload, follow the response protocol in [PROTOCOL.md](./PROTOCOL.md) (next to this file in the plugin). Skip reading PROTOCOL.md when handling a command from the table above — those are one-shot calls, no protocol needed.
