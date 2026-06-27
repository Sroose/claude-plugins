#!/usr/bin/env bash
# transcribe-http.sh — POST a recording to a whisper.cpp server, get the transcript back.
# Server-agnostic: works against a local (http://127.0.0.1:8777), LAN, or tailnet whisper-server.
#
# Usage:   transcribe-http.sh <recording>
# Prints:  the local path of the transcript text file as the LAST line of stdout.
#          (Progress/info goes to stderr so the last stdout line is just the path.)
#
# Server resolution (first non-empty wins):
#   $WHISPER_SERVER env  >  config file (WHISPER_SERVER=)  >  error
# Config file: ${XDG_CONFIG_HOME:-$HOME/.config}/whisper-transcribe/config
#
# Other tunables (env overrides config, config overrides default):
#   WHISPER_LANG    language code or 'auto'  (default auto)
#   WHISPER_PROMPT  optional spelling/vocab hint for names & jargon (default empty)
#   WHISPER_MAXTIME curl total timeout, seconds (default 7200 = 2h, for long meetings)
set -euo pipefail

WAV="${1:?usage: transcribe-http.sh <recording>}"
[ -f "$WAV" ] || { echo "error: no such file: $WAV" >&2; exit 1; }

CONFIG_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/whisper-transcribe/config"
cfg() { [ -f "$CONFIG_FILE" ] && grep -E "^$1=" "$CONFIG_FILE" | tail -1 | cut -d= -f2- || true; }

SERVER="${WHISPER_SERVER:-$(cfg WHISPER_SERVER)}"
LANG_CODE="${WHISPER_LANG:-$(cfg WHISPER_LANG)}"; LANG_CODE="${LANG_CODE:-auto}"
PROMPT="${WHISPER_PROMPT:-}"
MAXTIME="${WHISPER_MAXTIME:-7200}"

if [ -z "$SERVER" ]; then
  echo "error: no whisper server configured." >&2
  echo "       Set one with: transcribe-config.sh set-server http://127.0.0.1:8777" >&2
  echo "       (use 127.0.0.1 if the server runs on this machine, else its LAN/tailnet URL)" >&2
  exit 3
fi
SERVER="${SERVER%/}"

OUT="$(mktemp -d)/transcript.txt"   # mktemp -d is portable (GNU + BSD); avoids the BSD-only `-t prefix` form
log() { echo "[transcribe] $*" >&2; }

args=(
  -sS --fail-with-body
  --connect-timeout 10 --max-time "$MAXTIME"
  -X POST "$SERVER/inference"
  -F "file=@${WAV}"
  -F "response_format=text"
  -F "language=${LANG_CODE}"
  -F "carry_initial_prompt=true"
)
[ -n "$PROMPT" ] && args+=(-F "prompt=${PROMPT}")

log "server=$SERVER  lang=$LANG_CODE  file=$(du -h "$WAV" | cut -f1)${PROMPT:+  prompt set}"
log "uploading + transcribing (the model stays resident on the server; this can take a while) ..."
if ! curl "${args[@]}" -o "$OUT"; then
  echo "error: transcription request failed. Is the whisper server up and reachable at $SERVER ?" >&2
  echo "       server said:" >&2
  cat "$OUT" >&2 || true
  rm -rf "$(dirname "$OUT")"
  exit 1
fi

log "done -> $OUT"
echo "$OUT"
