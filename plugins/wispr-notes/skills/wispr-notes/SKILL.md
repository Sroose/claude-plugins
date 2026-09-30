---
name: wispr-notes
description: Read the user's Wispr Flow meeting notes, AI summaries, transcripts and standalone notes stored locally on this Mac. Use when the user refers to a meeting, call or brainstorm, asks what was said or decided, who said something, wants a recap, or mentions Wispr, the notetaker or "my notes".
---

# Wispr Flow notes

Wispr Flow keeps its notetaker data locally in `~/Library/Application Support/Wispr Flow/` (SQLite `flow.sqlite` plus per-meeting transcript files). The `wispr-notes` command reads it read-only. Never write to that folder and never query the database by hand when a command covers the need.

`wispr-notes` is on PATH while the plugin is enabled. Run it bare, without `$(...)`, pipes or `&&`, so it stays allowlistable as `Bash(wispr-notes:*)`.

## Commands

| Command | Returns |
| --- | --- |
| `wispr-notes list [--since 7d]` | one line per meeting: id prefix, local start time, duration, title, participants. `--since` takes `24h`, `7d`, `2w` or an ISO date |
| `wispr-notes show <meeting>` | AI summary and the user's own notes, speaker placeholders replaced by names |
| `wispr-notes transcript <meeting> [--grep term] [--context N]` | `[mm:ss] Speaker: text` lines; with `--grep` only matching segments plus N neighbours (default 2) |
| `wispr-notes search <term> [--max-hits N]` | matches across titles, summaries, notes, transcripts and standalone notes, with snippets |
| `wispr-notes notes [note]` | standalone notes: list, or full content of one |

`<meeting>` is an id prefix (from `list`) or a title fragment. An ambiguous fragment prints the candidates; rerun with the id prefix.

## Summary or transcript

Wispr's summaries are written without the project context, so they are sometimes off: they drop technical arguments and alternatives, and turn hedged statements into firm decisions. The transcript is the source of truth.

1. Locate: `list` (optionally `--since`) or `search <term>` when the user names a topic rather than a meeting.
2. When details matter (the answer feeds a ticket, design doc, open item or design decision, or the question is technical), go straight to the transcript. Under ~30 minutes, read it in full (an 18 minute meeting is ~145 lines). Longer, use `transcript <id> --grep <term>` for each of the topic's terms. Use the summary only to find where to look, never as the answer.
3. Only for a quick recap, who does what, or what was decided in broad terms, answer from `show`. Say it comes from Wispr's summary.

## Reading the output

- Quote content in the language it was spoken; translate only when asked.
- Transcript timestamps are the offset from the start of the recording in `[mm:ss]`, and minutes don't roll over into hours: `[105:59]` is 1h45m59s in. Convert to hours when you cite a time to the user.
- `Speaker N` means Wispr has no name mapped to that voice. Say so; do not guess who it is.
- The summary is Wispr's AI output, not the user's words. "My notes" is what the user typed. Keep the distinction when reporting.
- Only meetings recorded on this Mac are present. Deleted meetings and deleted transcripts are skipped.
