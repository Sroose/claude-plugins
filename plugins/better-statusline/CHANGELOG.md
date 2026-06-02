# Changelog

## 0.1.0

- Initial release.
- Status line: model, 5-hour + weekly rate-limit usage with resets, context-window %, cwd (with `$HOST_CWD` host path when set). Red at ≥ 75%.
- `/better-statusline:apply` wires the `statusLine` entry into `~/.claude/settings.json` (idempotent; asks before replacing an existing status line).
- Resolver-based `statusLine.command` resolves the newest cached `lib/statusline.py`, surviving version bumps. Degrades gracefully: blank when the plugin is disabled, and `[better-statusline: python3 not found]` (not a silent blank) when `python3` is off PATH; always exits 0.
