# wispr-notes

A Claude Code plugin that gives Claude read-only access to your [Wispr Flow](https://wisprflow.ai) notetaker data, straight from the app's local storage on macOS. No network, no Wispr API or MCP: it reads the files Wispr Flow already keeps on your Mac.

Useful when your organisation hasn't enabled the Wispr Flow connector, or when you'd rather keep lookups local.

## Install

```
/plugin marketplace add Sroose/claude-plugins
/plugin install wispr-notes@sroose-plugins
```

Requires macOS, Wispr Flow's notetaker, and `python3` (stdlib only).

## Usage

Just ask: "what did we decide about X in yesterday's meeting?", "who raised the budget concern?", "recap my meetings this week". Claude picks the right command:

| Command | Returns |
| --- | --- |
| `wispr-notes list [--since 7d]` | meetings, newest first, with duration and participants |
| `wispr-notes show <meeting>` | Wispr's AI summary and your own notes |
| `wispr-notes transcript <meeting> [--grep term]` | speaker-resolved transcript, optionally filtered |
| `wispr-notes search <term>` | hits across titles, summaries, notes and transcripts |
| `wispr-notes notes [note]` | standalone notes |

`<meeting>` is an id prefix or a title fragment.

To skip permission prompts, allowlist `Bash(wispr-notes:*)`.

## Summary vs transcript

Wispr's summaries are generated without your project context and sometimes flatten hedged statements into decisions or drop technical arguments. The skill tells Claude to read the transcript whenever details matter and to use the summary only for quick recaps, saying so when it does.

## What it reads

From `~/Library/Application Support/Wispr Flow/`:

- `flow.sqlite`, opened read-only: meeting titles, times, summaries, your notes, speaker map, standalone notes
- `meetings/<id>/refined.ndjson` (or `live.ndjson` as fallback): transcript segments

Deleted meetings, deleted transcripts and the onboarding demo meeting are skipped. Audio is never read.

## Caveats

- **Unofficial.** This relies on Wispr Flow's internal storage format, which can change with an app update. The script fails with an error rather than guess.
- **This Mac only.** Meetings recorded on other devices aren't in local storage.
- **Unnamed speakers** stay `Speaker N` until you assign them in Wispr Flow.
