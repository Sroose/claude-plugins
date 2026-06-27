# whisper-transcribe

A Claude Code plugin that transcribes audio/meeting recordings via a
[whisper.cpp](https://github.com/ggerganov/whisper.cpp) server and writes a concise,
context-aware summary — without leaving your machines for the cloud.

```
/transcribe <recording> [--prompt "vocab"] [--lang xx]
            [--context-text "one-liner context"] [context1.md context2.md ...]
```

- Sends the recording to a `whisper-server` over HTTP (the heavy model runs there, resident).
- The server can be **local** (`http://127.0.0.1:8777`) or on **another machine** on your LAN /
  Tailscale tailnet — handy when you record on a small laptop but transcribe on a beefier box.
- The server URL is **asked once on first use** and stored in
  `${XDG_CONFIG_HOME:-$HOME/.config}/whisper-transcribe/config` — nothing is hardcoded.
- Then, locally: a blind summary (action points + decisions) is sharpened with any context files
  you name (cross-linking ticket/issue ids, fixing names) — without rewriting or lengthening it.
- Writes `summary_<title>.md` (the summary) and `summary_<title>.txt` (full transcript) next to
  the recording.

## Install

```
/plugin marketplace add Sroose/claude-plugins
/plugin install whisper-transcribe@sroose-plugins
```

Then run a whisper-server somewhere reachable (see [`server-setup/`](server-setup/README.md)) and
run `/transcribe` — it will ask for the server URL the first time.

## Layout
- `skills/transcribe/SKILL.md`          — the `/transcribe` skill
- `skills/transcribe/transcribe-http.sh` — HTTP transport (curl to the server)
- `skills/transcribe/transcribe-config.sh` — first-use server URL config (get/set)
- `server-setup/`                        — how to run whisper-server + a macOS LaunchAgent template

## Privacy / security
Audio and transcripts stay on your own machines. `whisper-server` has **no authentication** —
keep it on localhost or a trusted LAN/tailnet, never exposed to the internet.

## Requirements
- A reachable whisper.cpp `whisper-server`.
- `curl` (preinstalled on macOS/Linux).
