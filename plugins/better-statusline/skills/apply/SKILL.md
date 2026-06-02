---
name: apply
description: Wire the better-statusline status line into the user's ~/.claude/settings.json. Triggers on "/better-statusline:apply".
allowed-tools: Read, Edit
---

# better-statusline:apply

Add (or update) the `statusLine` entry in the user's **`~/.claude/settings.json`** so Claude
Code renders this plugin's status line. This is a one-shot configuration command — do not
extend-think or delegate to a sub-agent.

## The exact value to write

The `statusLine.command` must be this self-contained resolver. It is intentionally **not** a
bare `better-statusline` name: a plugin's `bin/` is only on the Bash *tool's* PATH, not the
PATH of the status-line subprocess, so a bare name would not resolve. This line globs the
plugin cache for the newest installed copy and runs it, so it survives version bumps and prints
nothing if the plugin is ever disabled.

It also degrades gracefully: prints nothing if the plugin is disabled, and shows a visible
`[better-statusline: python3 not found]` (instead of a silent blank line) if `python3` is not on
PATH. It always exits 0 so the status-line subsystem never errors.

The `statusLine` block, exactly:

```json
"statusLine": {
  "type": "command",
  "command": "sh -c 'f=$(ls -1 \"$HOME\"/.claude/plugins/cache/*/better-statusline/*/lib/statusline.py 2>/dev/null | sort -V | tail -1); [ -n \"$f\" ] || exit 0; command -v python3 >/dev/null 2>&1 || { echo \"[better-statusline: python3 not found]\"; exit 0; }; exec python3 \"$f\"'"
}
```

## Steps

1. **Read** `~/.claude/settings.json` (resolve `~` to the real home dir). If the file does not
   exist, create it as `{}` and proceed.
2. **Inspect** the current `statusLine` key:
   - **Absent** → add the block above.
   - **Present and `command` already contains `better-statusline`** → it is already wired up.
     Report "already configured" and stop. Do not rewrite.
   - **Present but points elsewhere** (a different status line) → **do not overwrite silently.**
     Show the user their current `statusLine.command` and the new one, and ask them to confirm
     the replacement before editing.
3. **Edit** the file to set the `statusLine` block. Preserve every other key and the file's
   existing formatting/indentation; produce valid JSON (no trailing commas, no comments).
4. **Confirm** to the user: the status line is wired up; it appears on the next render (a
   `/reload-plugins` or new prompt is enough — no restart). Remind them the `better-statusline`
   plugin must stay **enabled** for the resolver to find the script.

## Notes

- Editing `~/.claude/settings.json` directly is correct and expected here — that is the user's
  own top-level settings file. (Never touch project-level or other `settings.json` files.)
- This command only manages the `statusLine` key. It never changes permissions, env, hooks, or
  other settings.
