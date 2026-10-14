---
name: confluence-sync
description: Use this skill when reviewing or modifying a Markdown file that shadows a Confluence page, or when the user wants to set/refresh their Confluence session cookie. The skill manages CUR snapshots, orchestrates the edit→apply→verify loop, and triages deviations between the proposed edits and what landed in Confluence. Trigger on user requests like "check the ARCH doc", "update the onboarding page", "review what's in confluence for X", "set confluence cookie '<value>'", or any time you are about to edit a file listed in the project's `confluence-sync.yaml` registry.
---

# confluence-sync

Keep Markdown shadow files in sync with their Confluence source pages. This skill orchestrates the workflow around Confluence; the user always applies changes manually in the Confluence editor.

## Hard rule: Confluence access is READ-ONLY

You must never write to Confluence — not via the bundled script, not via direct `curl`, not via any API call (`PUT`, `POST`, `DELETE` on `/rest/api/content/...`), not via any MCP server or other tool. This is a deliberate constraint, not a limitation:

- The export → markdown → re-import roundtrip is lossy (table column widths, info/warning macros, panel layouts).
- The user wants to do the last leg manually so they can redact, reformat, and place images deliberately.

If a future request seems to want a write-back ("just push this to Confluence", "save my edits"), refuse and remind them why. If they insist, escalate by asking explicitly — don't quietly add a write path.

## Doc registry

Each project lists its Confluence-shadowed docs in `confluence-sync.yaml`. Search locations (first match wins):

- `confluence-sync.yaml` in cwd
- `<repo-root>/confluence-sync.yaml`

Schema:

```yaml
docs:
  - name: ARCH                       # short id, used in user references
    title: System architecture       # human description
    path: docs/architecture.md       # path relative to where the yaml lives
    url: https://...                 # Confluence page URL (may be null for "TBD")
```

Resolve user references (e.g. "the architecture doc", "ARCH") by matching against `name` or `title` case-insensitively. If no registry entry exists or `url` is null, tell the user and stop — don't guess.

## The flow

### 1. Begin (before editing)

Two things happen here: checkpoint the user's working file, and take a fresh snapshot of Confluence. Run from the directory the file lives in:

```bash
TS=$(date +%Y%m%d-%H%M%S)

# Checkpoint the working file so the user can roll back if our edits are wrong.
# Skipped on cold start (no X.md yet).
[ -f X.md ] && cp X.md "X.PREV.$TS.md"

# Rotate any existing Confluence snapshot
[ -f X.CUR.md ] && mv X.CUR.md "X.CUR.$TS.md"

# Pull fresh from Confluence
CSYNC=$(find ~/.claude/plugins/cache -path '*confluence-sync*/confluence_sync.py' 2>/dev/null | sort -V | tail -1)
python3 "$CSYNC" fetch '<URL>' -o X.CUR.md

# Cold start: if no working file yet, seed it from the snapshot
[ ! -f X.md ] && cp X.CUR.md X.md
```

File roles:

| File | Meaning |
|---|---|
| `X.md` | The working file. You edit this. Never overwritten by Begin unless cold-starting. |
| `X.CUR.md` | Snapshot of Confluence at the start of the current cycle. The diff target the user uses when applying changes. |
| `X.PREV.<TS>.md` | Snapshot of `X.md` *before* our edits this cycle. Recovery point if you trash the working file. |
| `X.CUR.<TS>.md` | Older Confluence snapshots. Kept for history; pruned to last 3 at Close. |

If `fetch` exits non-zero with `ERR_AUTH_*` on stderr, see the Auth section below — do not retry.

After Begin, diff `X.md` against `X.CUR.md` and triage drift before editing. Default behaviour is to rebase on Confluence (overwrite the working file) — only stop if the user has real local edits that risk being lost.

| Drift | Action |
|---|---|
| None | Proceed. |
| Only export-converter artifacts (table `<br>` noise, escaped punctuation in headings, link href reformatting, whitespace, code-block collapse) | Rebase silently: `cp X.CUR.md X.md`. Mention in one line. Proceed. |
| Substantive content drift (text added/removed/reworded, fields renamed, semantics changed) | Stop. Show a short sample of the substantive hunks and ask the user: **Overwrite** (`cp X.CUR.md X.md`, local edits discarded but recoverable from `X.PREV.<TS>.md`) or **Stop** (back down without editing, user investigates manually). Do not stack your edit on top of unsynced semantic edits. |

Why default-to-overwrite: stacking your edit on a stale working file produces a proposal that diffs uselessly against the current page, even if the stale content is "just formatting". The recovery point in `X.PREV.<TS>.md` makes overwrite safe to default to.

### 2. Edit

Modify `X.md` in place using your normal editing tools. Do not touch `X.CUR.md`.

### 3. Hand off

Tell the user `X.CUR.md` (current Confluence) and `X.md` (your proposal) are both ready, and they should diff in their IDE and apply manually in Confluence. **Do not print the diff in the terminal** — line wrapping makes it unusable; the IDE is the source of truth.

### 4. Close (after user confirms they applied changes in Confluence)

Re-pull from Confluence and triage the deviations between what you proposed and what actually landed:

```bash
python3 "$CSYNC" fetch '<URL>' -o X.NEW.md   # CSYNC resolved as in "Resolving the helper script"
diff -u X.md X.NEW.md   # for your eyes; do not paste the output to the user
```

Triage rules:

| Deviation type | Action |
|---|---|
| Wording changes inside your edited sentences | Silent (user reworded — their call) |
| Whitespace, blank-line drift, link normalization, table column-width changes | Silent (export-converter artifact) |
| Your sentence/paragraph completely missing from Confluence | **Ask** — likely a copy-paste miss |
| New sentence/paragraph not in your proposal | **Ask** — likely intentional addition, but worth confirming |
| Section reordering you did not propose | **Ask** |

If only silent deviations → promote and clean up:

```bash
mv X.NEW.md X.CUR.md
cp X.CUR.md X.md
# Prune old timestamped artifacts, keep latest 3 of each:
ls -t X.CUR.*-*.md  2>/dev/null | tail -n +4 | xargs -r rm
ls -t X.PREV.*-*.md 2>/dev/null | tail -n +4 | xargs -r rm
```

If anything triggered an Ask → batch all questions into one user prompt. On confirmation that the deviations are intentional, promote as above.

### Abort

If the user says to scrap mid-flow: restore `X.md` from the latest `X.PREV.*.md` (newest by mtime — this is the pre-edit checkpoint of the working file, not the Confluence snapshot) and stop. Do not re-pull from Confluence.

```bash
latest=$(ls -t X.PREV.*-*.md 2>/dev/null | head -1)
[ -n "$latest" ] && cp "$latest" X.md
```

## Resolving the helper script

The helper lives inside the installed plugin under a version directory. Resolve the newest installed copy at call time — don't cache the path:

```bash
CSYNC=$(find ~/.claude/plugins/cache -path '*confluence-sync*/confluence_sync.py' 2>/dev/null | sort -V | tail -1)
```

`~/.claude/plugins/cache` is scoped deliberately — a blanket `~/.claude` search also matches the marketplace repo clone under `plugins/marketplaces/…`, which has no version dir and would sort last. `sort -V | tail -1` picks the highest installed version.

Set `CSYNC` at the start of each Bash call below (each tool call is a fresh shell, so re-resolve every time), then `python3 "$CSYNC" <args>`. In the snippets below, `$CSYNC` means exactly that expression.

> If `$CSYNC` comes back empty (e.g. testing via `--plugin-dir`), invoke the script by its explicit plugin path instead.

## Auth — the Confluence session cookie

The user authenticates by copying their browser session cookie from DevTools (Network → any Confluence request → Headers → Cookie). For Confluence Cloud the relevant cookie is typically `tenant.session.token=eyJ...`, but the exact cookie name can vary by tenant — when in doubt, copy the full Cookie header value rather than extracting the JWT alone. Session validity is typically ~7 days.

The script stores the value verbatim at `~/.claude/secrets/confluence-session` (mode 600). On HTTP 401, the script deletes that file and exits non-zero with `ERR_AUTH_INVALID` on stderr.

> **Why session cookie and not an Atlassian API token?** Atlassian's API tokens are normally the cleaner choice (long-lived, no weekly refresh). This plugin defaults to session cookies because some organizations disable API-token access entirely. If your tenant allows API tokens, prefer them and propose a PR.

### Error handling

If a `fetch` call prints `ERR_AUTH_INVALID` or `ERR_AUTH_MISSING` on stderr:

1. Stop immediately. Do not retry the call.
2. Tell the user the session expired (or was never set) and they need to paste a fresh cookie via `update confluence key '<value>'`.
3. Wait. Do not attempt any further `fetch` until the user has set a new token.

### Setting the cookie

When the user says `set confluence cookie '<value>'`, `update confluence key '<value>'`, or similar:

```bash
CSYNC=$(find ~/.claude/plugins/cache -path '*confluence-sync*/confluence_sync.py' 2>/dev/null | sort -V | tail -1)
python3 "$CSYNC" set-token '<value>'
```

`<value>` is the full Cookie header content from browser DevTools, including the cookie name — e.g. `tenant.session.token=eyJ...`. The script rejects values without `=` with a helpful error so users notice if they only pasted the JWT.

## House rules

- Never `git add` `X.CUR*.md`, `X.NEW.md`, or anything in `~/.claude/secrets/`. Suggest a `.gitignore` entry for `*.CUR*.md` and `*.NEW.md` if the project doesn't have one.
- Never echo the session cookie back in chat after the user has provided it.
- The script is read-only against Confluence by design (see the hard rule at the top).
- Confluence checkboxes convert to `- [x] ` / `- [ ] ` (since 0.1.3). Trust those markers: they come from the `checked` class in the page HTML. If you ever see a page whose checklists are all plain bullets, suspect the conversion before concluding the checklist is unanswered, and never treat an option list as "not filled in" without a marker to back it. Confluence's PDF export draws the checkmarks as vectors, so a PDF is not a usable cross-check.
- If you find yourself about to edit a markdown file that's in the registry but you have not run Begin, stop and run Begin first.
