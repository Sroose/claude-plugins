# Changelog

## 0.2.0 — 2026-10-14

- **Compact layout** for narrow terminal panes: ~100 chars instead of ~178. `Opus 5.5 (1M) │ 5H 2% (22:59) │ WEEK 13% (sunday) │ CTX 12% │ cache █████ 59m │ ~/path`. Thin grey `│` separators; `usage`/`reset`/`cwd:` wording dropped; `(1M context)` → `(1M)`; home folder → `~`; 5H shows the reset clock time instead of a countdown.
- **Color, sparingly.** Labels bold grey, brackets and separators grey, path blue; values plain until they warn: yellow ≥ 60%, red ≥ 80% (was red only, ≥ 75%).
- **Prompt-cache countdown** from CC's `prompt_cache` (≥ 2.1.251): 5-cell bar + time left, yellow in the last 20% of the TTL, red in the last 5%, `cold` when expired. Omitted when CC doesn't send it.
- **Clickable path**: OSC 8 `file://` link (to `$HOST_CWD` in a container), cmd-click opens it in Finder.
- `/better-statusline:apply` now writes `refreshInterval: 30` (and adds it to an existing better-statusline entry) so the countdown ticks while idle.

## 0.1.0

- Initial release.
- Status line: model, 5-hour + weekly rate-limit usage with resets, context-window %, cwd (with `$HOST_CWD` host path when set). Red at ≥ 75%.
- `/better-statusline:apply` wires the `statusLine` entry into `~/.claude/settings.json` (idempotent; asks before replacing an existing status line).
- Resolver-based `statusLine.command` resolves the newest cached `lib/statusline.py`, surviving version bumps. Degrades gracefully: blank when the plugin is disabled, and `[better-statusline: python3 not found]` (not a silent blank) when `python3` is off PATH; always exits 0.
