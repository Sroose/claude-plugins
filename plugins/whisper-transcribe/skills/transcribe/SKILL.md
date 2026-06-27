---
name: transcribe
description: Transcribe an audio/meeting recording via a whisper.cpp server (local, LAN, or tailnet) and write a concise summary using caller-supplied context files. Asks for the server URL once on first use. Triggers on "/transcribe", "transcribe <file>", or any request to transcribe + summarize a recording.
---

# transcribe — whisper-server transcription + context-aware summary

This skill sends a recording to a **whisper.cpp `whisper-server`** over HTTP, gets the raw
transcript back, then writes a **concise summary** (action points + decisions/agreements),
optionally sharpened with context files the user names per run. The server can be on **this same
machine** (`http://127.0.0.1:8777`) or on **another machine** on your LAN / Tailscale tailnet —
the only thing exposed is the transcription endpoint (no shell access). The model that does the
summary runs locally in this session.

The server URL is **not hardcoded** — it is asked once on first use and stored in
`${XDG_CONFIG_HOME:-$HOME/.config}/whisper-transcribe/config`.

Scripts live under `${CLAUDE_PLUGIN_ROOT}/skills/transcribe/` (this skill's directory).

## Invocation

```
/transcribe <recording> [--prompt "vocab terms"] [--lang xx]
            [--context-text "one-liner context"] [context1.md context2.md ...]
```

- **First argument** = path to the recording on this machine (wav; other formats work if the
  server was started with `--convert` and has ffmpeg).
- **`--prompt "…"`** (optional) = a short whisper *spelling* hint for names/jargon (e.g.
  `--prompt "Acme Corp, Kubernetes, Jira"`). It is NOT instructions and NOT summary context — it
  only biases transcription spelling. Pass its value to the script via the `WHISPER_PROMPT` env var.
- **`--lang xx`** (optional) = force the spoken language (e.g. `--lang nl`, `--lang en`). Default
  is auto-detect. Pass via the `WHISPER_LANG` env var.
- **`--context-text "…"`** (optional, repeatable) = inline Phase B context as a short string
  (e.g. `--context-text "Connor Rousseau over steun voor jobbonus"`). Use this for one-liner
  context that doesn't justify a file. Treated identically to context-file content in Phase B.
- **Remaining arguments** = zero or more context files (meeting notes, an issue/ticket register,
  a glossary…). Use exactly the ones given, resolved relative to the current directory or as
  absolute paths.

If neither `--context-text` nor any context file is given, skip Phase B.

After extracting any `--prompt` / `--lang` / `--context-text` flags, treat what remains (besides
the recording) as context files.

**Natural-language invocation** is supported too. If the user phrases the call as free text
(e.g. `transcribe foo.wav, language nl, context is: "..."`), parse it into the same parameters —
treat a quoted/inline context sentence as if it had been passed via `--context-text`.

## Procedure — follow the ordering, do not skip it

### Step 0 — ensure a server is configured (first-use prompt)
Check for a configured server:
```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/transcribe/transcribe-config.sh" get-server
```
- If it prints a URL, use it.
- If it prints **nothing**, ask the user:
  > "What's the base URL of your whisper-server? Use `http://127.0.0.1:8777` if it runs on this
  > machine, or `http://<host-or-ip>:8777` for one on your LAN / tailnet."

  Then save their answer (only once):
  ```bash
  bash "${CLAUDE_PLUGIN_ROOT}/skills/transcribe/transcribe-config.sh" set-server "<their-url>"
  ```
  (To change it later: same `set-server` command.)

### Step 1 — transcribe over HTTP (deterministic, no judgment)
Run the transport script, forwarding flags only if the user gave them. Capture its **last stdout
line**, which is the local path of the transcript text file:
```bash
WHISPER_PROMPT="<if given>" WHISPER_LANG="<if given>" \
  bash "${CLAUDE_PLUGIN_ROOT}/skills/transcribe/transcribe-http.sh" "<recording>"
```
This uploads the file and runs the model on the server — it can take a while for long meetings.
Let it run; do not poll or re-invoke it. If the script exits non-zero, report the stderr and
**STOP** — never summarize a transcript that failed to produce. (Most common cause: the server
isn't running or isn't reachable at the configured URL.)

### Step 2 — Phase A: summarize BLIND (transcript only)
Read **only** the transcript file from Step 1. Nothing else. Produce a **very brief** summary
**in the same language as the transcript**, focused on:
- **Action points** — who / what, where stated.
- **Decisions / new agreements.**

Keep it terse and dense — no preamble, no restating the whole meeting. Note its length; that's
your budget for Phase B.

### Step 3 — Phase B: sharpen WITH context (do not rewrite, do not lengthen)
Only if the user provided context — either context files or one or more `--context-text "…"`
strings (or both). Read the files and treat each `--context-text` value as an additional context
snippet. Use the combined context **only** to:
- **Cross-link identifiers** — where a topic in the summary matches an entry in a provided
  register/notes (ticket id, issue id, project code, agenda item…), annotate the item with that
  identifier.
- **Sharpen wording in place** — fix names/terms, disambiguate references.

Hard constraints:
- **Keep the same items.** Do not add action points or agreements that weren't in the blind
  summary. Do not add explanatory sentences.
- **Do not materially lengthen.** Stay within ~110% of the Phase A length. Linking an id and
  tightening a word is the entire allowed scope.

Doing A before B keeps the summary grounded in what was actually said before context can bias it.

### Step 4 — name the outputs
Choose a short descriptive **title = the subject of the recording** (in the transcript's
language, 3–8 words). Slugify: lowercase, spaces → underscores, strip anything not `[a-z0-9_-]`.
Call it `<slug>`.

### Step 5 — write both files next to the recording
- `summary_<slug>.md`  — the final summary (after Phase B if context was given, else Phase A).
- `summary_<slug>.txt`  — the **full raw transcript** from Step 1, copied verbatim.

(The raw transcript is intentionally named `summary_<slug>.txt` so the pair shares a stem.)

### Step 6 — report
Show the summary inline and tell the user the two paths written. Done.

## Failure modes
- Server down / unreachable / wrong URL → `curl` fails; report it and stop. Re-point with
  `transcribe-config.sh set-server <url>`.
- Very long meeting → the transcript may be large; still summarize, but if it's enormous say so
  rather than silently truncating.
- Nothing accumulates on the server: it holds the model in memory and writes no per-job files.
