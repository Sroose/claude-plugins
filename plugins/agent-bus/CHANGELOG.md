# Changelog — agent-bus

## 0.1.2 — 2026-05-28

- **Symlinks at `~/.claude/bus/` are now relative.** Previously they stored an absolute target (e.g. `/home/claude/.claude/plugins/.../bus.py`), which broke when `~/.claude` is a shared bind-mount between a Docker container and the host — the absolute path is only valid in one namespace, so a session in the other namespace (or a native host session reusing a container-written link) failed with "no such file." Relative targets resolve correctly from both namespaces since link and target share the `~/.claude` root. Affects the SessionStart hook and `bus.py register`.

## 0.1.1 — 2026-05-20

- **Watcher startup is now deterministic.** The declarative `monitors/` entry has been removed; `bus.py register` now prints the exact `Monitor` tool invocation in its stdout, and `SKILL.md` instructs the agent to call it after every successful register. Previously the declarative `when: "on-skill-invoke"` trigger fired inconsistently — some sessions never got a live watcher and silently dropped messages.
- Added `~/.claude/bus/watch.py` to the stable-symlink set maintained by SessionStart and `bus.py register`.
- Removed redundant `version` field from `.claude-plugin/marketplace.json`'s plugin entry — `plugin.json` is the single source of truth.

## 0.1.0 — 2026-05-19

Initial release.

- `/agent register|unregister|whoami|list|ask|send|inbox|read|archive` subcommands
- Container-hostname-based session identity (stable across `/resume`)
- `cwd-memo` so the watcher auto-rebinds the prior name on `/resume` (no user action needed)
- Pre-filtered watcher: notifications only arrive for messages addressed to the registered name
- Pre-formatted notifications (full body, no JSON parsing required by the receiver)
- Send-time warning when target name has no live listener
- Backlog replay: messages that arrived before registration are surfaced on `/agent register`
- Auto-unregister on clean session exit; preserves `cwd-memo` for next session
- SessionStart hook maintains `~/.claude/bus/bus.py` symlink for stable invocation path
- File watcher selects best available backend: `inotifywait` → `fswatch` → shell-poll
- Optional statusline integration via `statusline_fragment.py`
- Diagnostic log at `~/.claude/bus/log/watcher.log`
