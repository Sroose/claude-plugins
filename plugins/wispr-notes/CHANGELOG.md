# Changelog

## 0.1.0 — 2026-09-30

- Initial release.
- `wispr-notes` launcher on PATH (allowlistable as `Bash(wispr-notes:*)`) with `list`, `show`, `transcript`, `search` and `notes`.
- Reads Wispr Flow's local `flow.sqlite` in read-only mode plus the per-meeting `refined.ndjson` (falls back to `live.ndjson`). Speaker placeholders in summaries and transcripts are resolved to names from the meeting's speaker map; unmapped voices stay `Speaker N`.
- Tolerant of what it reads: NULL database fields, timestamps with or without fractional seconds or an offset, and blank, damaged or half-written transcript lines (skipped, so one bad file can't abort `search`). Runs on the macOS system Python 3.9.
- `<meeting>` resolves an exact id first, then an id prefix, then a title fragment; several matches at a level list the candidates instead of guessing.
- Skill steers Claude to the transcript whenever details matter, since Wispr's summaries lack project context.
