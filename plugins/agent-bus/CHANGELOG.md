# Changelog — agent-bus

## 0.1.4 — 2026-05-28

- **Added a `bin/agent-bus` launcher** (on the Bash tool's PATH while the plugin is enabled). All operations are now invoked as a clean, statically-analyzable command — `agent-bus register OBSIDIAN`, `agent-bus send CODE "..."`, `agent-bus watch` — instead of the 0.1.3 `BUS=$(find …); python3 "$BUS" …` resolver. That resolver could **never** be matched by the permission allowlist (leading assignment + `$(…)` → "cannot be statically analyzed"), so guarded/limited-permission agents got a prompt on every call — and a prompt mid-turn can corrupt a guarded agent's transcript. With the launcher, allowlist `Bash(agent-bus:*)` and calls are prompt-free.
- SKILL.md, PROTOCOL.md, the SessionStart guidance, and the register-printed Monitor command all now emit bare `agent-bus …` commands. The `$(find …)` form remains documented only as a fallback for when the launcher isn't on PATH.
- The launcher resolves its sibling `bus.py`/`watch.py` by its own location (no find in the common case), falling back to a cache-scoped find.

## 0.1.3 — 2026-05-28

- **Dropped the `~/.claude/bus/` script symlinks entirely; helper is now resolved at call time.** The symlink approach (0.1.1 relative-target fix included) had a fatal flaw: a single shared `~/.claude/bus/bus.py` link can't point at both a container's and the host's plugin copy at once, and the link-repair logic lived *inside* `bus.py` — unreachable when you invoke `bus.py` *through* a dangling link (circular). SKILL.md, PROTOCOL.md, the SessionStart hook, and the register-printed Monitor command now resolve the script via `find ~/.claude/plugins/cache -path '*agent-bus*/skills/agent/bus.py' | sort -V | tail -1` — newest installed version, caller's namespace, nothing cached, nothing to dangle.
- The `find` is **cache-scoped** on purpose: a blanket `~/.claude` search also matches the marketplace repo clone under `plugins/marketplaces/…` (no version dir), which sorts last and would be picked wrongly.
- SessionStart no longer maintains symlinks; it injects guidance + auto-rebinds from cwd-memo as before.

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
