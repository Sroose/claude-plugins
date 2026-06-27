# Changelog

## 0.1.0 — 2026-06-27

- Initial release.
- `/transcribe <recording>` sends a local audio file to a whisper.cpp `whisper-server` over HTTP, then writes `summary_<slug>.md` (action points + decisions) and `summary_<slug>.txt` (raw transcript) next to the recording.
- Server URL is asked once on first use and stored at `${XDG_CONFIG_HOME:-$HOME/.config}/whisper-transcribe/config` — no hardcoded host. The server can be local, on a LAN box, or on a Tailscale tailnet.
- Optional flags: `--prompt "vocab terms"` (whisper spelling hint via `WHISPER_PROMPT`), `--lang xx` (force language via `WHISPER_LANG`), `--context-text "..."` (inline Phase B context, repeatable). Remaining args are treated as context files. Natural-language invocations (e.g. `transcribe foo.wav, language nl, context is "..."`) are parsed into the same parameters.
- Summary procedure is two-phase: Phase A summarizes blind from the transcript only, Phase B sharpens with any supplied context (cross-link ids, fix names) without rewriting or lengthening (~110% length budget).
- Ships `server-setup/` with a step-by-step README and a macOS LaunchAgent template (`whisper-server.plist.template`) with an inlined placeholder table — `__MODEL__` is the model basename with `.bin` (e.g. `ggml-large-v3.bin`), not a friendly name.
- Transport script (`transcribe-http.sh`) fails loudly and stops the skill if the server is unreachable, so no summary is ever produced from an empty transcript.
