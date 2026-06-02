# better-statusline

A richer Claude Code status line:

![better-statusline](statusline.png)

One line showing:

- **Model** in use
- **5-hour** rate-limit usage + when it resets
- **Weekly** rate-limit usage + reset day
- **Context-window** % used
- **Working directory** (and the host path via `$HOST_CWD` when set, e.g. containerized sessions)

Percentages turn red at ≥ 75%.

## Install

```
/plugin marketplace add Sroose/claude-plugins
/plugin install better-statusline@sroose-plugins
/reload-plugins
/better-statusline:apply
```

`/better-statusline:apply` adds the `statusLine` entry to your `~/.claude/settings.json` for
you (it asks first if you already have a different status line configured). The status line
appears on the next render — no restart needed.

## How it's wired

Claude Code can't set a `statusLine` automatically when a plugin is enabled — that key isn't
among the ones a plugin's bundled `settings.json` is allowed to contribute, and plugin install
runs no setup step. So the `apply` command does it on your explicit request.

The `statusLine.command` it writes is a self-contained resolver:

```sh
sh -c 'f=$(ls -1 "$HOME"/.claude/plugins/cache/*/better-statusline/*/lib/statusline.py 2>/dev/null | sort -V | tail -1); [ -n "$f" ] || exit 0; command -v python3 >/dev/null 2>&1 || { echo "[better-statusline: python3 not found]"; exit 0; }; exec python3 "$f"'
```

It runs the newest installed copy of [`lib/statusline.py`](lib/statusline.py) from the plugin
cache. A bare `better-statusline` command can't be used here because a plugin's `bin/` is only
on the Bash *tool's* PATH, not the status-line subprocess's PATH. Resolving from the cache means
the line keeps working across plugin updates. It degrades gracefully: prints nothing if the
plugin is disabled/uninstalled, and shows `[better-statusline: python3 not found]` if `python3`
isn't on PATH (rather than a silent blank line). It always exits 0 so the status-line subsystem
never errors.

## Uninstall

Remove the `statusLine` block from `~/.claude/settings.json`, then
`/plugin uninstall better-statusline@sroose-plugins`.

## Requires

`python3` on PATH.
