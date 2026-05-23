# Demo

The `demo.gif` shown in the agent-bus README is generated from `demo.tape` by [VHS](https://github.com/charmbracelet/vhs).

## Regenerate the GIF

Run **from the repo root** so the tape's relative paths (Output, `plugins/agent-bus/demo/res/*-CLAUDE.md`) resolve correctly:

```
brew install vhs              # one-time, macOS
# or: go install github.com/charmbracelet/vhs@latest

vhs plugins/agent-bus/demo/res/demo.tape
```

This will:
1. Launch a headless terminal
2. Wipe any leftover tmux session and `~/.claude/bus/` state from previous recordings
3. Create `/tmp/PRODUCER/` and `/tmp/CONSUMER/`, drop the matching `CLAUDE.md` into each, and `cd` into them
4. Split into two tmux panes and launch a Claude Code session in each
5. Record the result to `plugins/agent-bus/demo/demo.gif`

Make sure `agent-bus` is installed (e.g. via marketplace or `--plugin-dir`) and that you have either `fswatch` or `inotifywait` available — otherwise the watcher falls back to shell-poll, which still works but with a ~0.5s delay between sender and receiver.

## Contents of this directory

- `demo.tape` — the VHS script
- `producer-CLAUDE.md` — copied to `/tmp/PRODUCER/CLAUDE.md` at recording time; gives the PRODUCER session its API-spec context
- `consumer-CLAUDE.md` — copied to `/tmp/CONSUMER/CLAUDE.md` at recording time; gives CONSUMER the integration-questions checklist

## Tweaking

`demo.tape` is plain text — edit `Sleep` values to control pacing, change `Width`/`Height` for resolution, swap `Theme` for a different colour scheme, etc. VHS docs: https://github.com/charmbracelet/vhs#commands.

## Why not a model-generated video?

The demo is a real recording of the plugin running. A model-generated video would fabricate visuals that may not reflect actual behaviour — and the moment the plugin changes, the video would lie. VHS regenerates from source, so it always matches the current code.
