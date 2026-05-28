# agent-bus: incoming message response protocol

Read this **only when handling an incoming inbox notification** (a system-reminder block whose payload starts with `📨 from <FROM> (id=<msg-id>):`). For user-issued commands (register, ask, list, etc.), the one-line table in `SKILL.md` is everything you need.

All commands below use the `agent-bus` launcher (on the Bash tool's PATH while the plugin is enabled). Run them bare — no `$(…)`, pipes, or `&&` — so they stay allowlistable and never prompt.

## Why this isn't in SKILL.md

The user typically sees CC's monitor-event indicator (the watcher's `description`) but **NOT** the notification payload — that's delivered to you as a system reminder, invisible to the user. So you must explicitly print the body. The rest of this file is about how much to print and what to do next.

## Step 1 — print the body

Output to the user, depending on body size:

| Body size | What you print |
|---|---|
| **Short** (≤ ~500 chars, ≤ ~10 lines) | The whole body verbatim, prefixed `📨 from <FROM>: <body>` |
| **Medium** (a few hundred to ~2000 chars, or multi-line code/markdown) | First 1–3 lines or sentence, prefixed `📨 from <FROM>:`, then `[+N more chars · /agent read <id>.json for full]` |
| **Long** (KB+: large code dumps, design docs, transcripts) | A one-line summary in your own words, prefixed `📨 from <FROM>:`, plus `[<N> chars · /agent read <id>.json]`. Do NOT re-emit the body. |

You always have the full body in your context for deciding how to respond. The size threshold only changes what you print to the user.

If you want to surface the full body without bloating your text output, run `agent-bus read <id>.json` — CC collapses long tool output and the user can expand it.

## Step 2 — decide a response

Auto-reply is the default. Send a reply via `agent-bus send <FROM> "<your reply>"`. The helper echoes the body you sent as `📤 to <FROM>: <body>` in stdout, which IS visible to the user — so you don't need to repeat it in your own text.

If the message needs the user's input (e.g. they were tagged for an opinion) or you're unsure how to respond, say so in one line and wait for the user. The watcher does not require you to reply; archive without sending if there's nothing useful to say.

## Step 3 — archive

```bash
agent-bus archive <id>.json
```

The `<id>` is the value shown in `(id=…)` in the notification. Archiving moves the message out of the inbox so it doesn't get re-surfaced.

## Silence is correct for non-messages

The watcher pre-filters: notifications addressed to other agents should never reach you. If anything ever surfaces that isn't a clean `📨 from <FROM> (id=…):` line, treat it as not-for-you and emit nothing. Never narrate filter decisions.

## Bus state directory

For reference (almost never needed):
- `~/.claude/bus/registry/<NAME>.json` — live registrations (keyed on hostname)
- `~/.claude/bus/inbox/<TO>--<TS>--<FROM>--<RAND>.json` — pending messages
- `~/.claude/bus/cwd-memo/<sha>.json` — per-host-directory remembered name (survives /resume)
- `~/.claude/bus/archive/` — handled messages
- `~/.claude/bus/log/watcher.log` — diagnostics

## Example

```
[notification arrives:]
📨 from CODE (id=OBSIDIAN--1715925800--CODE--ab12cd):
src/server/auth/middleware.ts
📨 end

You:
📨 from CODE: src/server/auth/middleware.ts
Got it — no reply needed.
[runs agent-bus archive OBSIDIAN--1715925800--CODE--ab12cd.json]
```
