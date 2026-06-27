#!/usr/bin/env bash
# transcribe-config.sh — read/write the whisper-transcribe client config.
# Config is stored OUTSIDE the plugin (which lives in a read-only cache) at:
#   ${XDG_CONFIG_HOME:-$HOME/.config}/whisper-transcribe/config
# Format is plain KEY=VALUE lines (WHISPER_SERVER=..., optional WHISPER_LANG=...).
set -euo pipefail

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/whisper-transcribe"
CONFIG_FILE="$CONFIG_DIR/config"

put_key() {  # put_key KEY VALUE  — set/replace one key, preserving the others
  local key="$1" val="$2" tmp
  mkdir -p "$CONFIG_DIR"
  tmp="$(mktemp)"
  [ -f "$CONFIG_FILE" ] && grep -vE "^${key}=" "$CONFIG_FILE" > "$tmp" || true
  printf '%s=%s\n' "$key" "$val" >> "$tmp"
  mv "$tmp" "$CONFIG_FILE"
}

get_key() {  # get_key KEY
  [ -f "$CONFIG_FILE" ] && grep -E "^$1=" "$CONFIG_FILE" | tail -1 | cut -d= -f2- || true
}

case "${1:-}" in
  get-server) get_key WHISPER_SERVER ;;
  set-server)
    url="${2:?usage: set-server <url>}"
    url="${url%/}"                       # strip trailing slash
    case "$url" in http://*|https://*) ;; *) echo "error: URL must start with http:// or https:// (e.g. http://127.0.0.1:8777)" >&2; exit 2;; esac
    put_key WHISPER_SERVER "$url"
    echo "saved WHISPER_SERVER=$url -> $CONFIG_FILE" >&2 ;;
  get-lang)   get_key WHISPER_LANG ;;
  set-lang)   put_key WHISPER_LANG "${2:?usage: set-lang <code|auto>}"; echo "saved WHISPER_LANG=$2" >&2 ;;
  path)       echo "$CONFIG_FILE" ;;
  *) echo "usage: transcribe-config.sh {get-server|set-server <url>|get-lang|set-lang <code>|path}" >&2; exit 2 ;;
esac
