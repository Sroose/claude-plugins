---
name: jira-fetch
description: Use this skill when the user wants to pull a Jira Cloud issue into a local Markdown file for reference, or to set/refresh their Jira session cookie. Trigger on requests like "fetch HN-25476", "grab that Jira ticket", "pull the issue at <atlassian browse URL>", "what's in HN-12345", or "set jira cookie '<value>'".
---

# jira-fetch

Fetch Jira Cloud issues into local Markdown so you can read a ticket (summary, metadata, description, comments) while working in the repo. **Read-only against Jira** — this skill never creates, edits, transitions, or comments on issues.

## Hard rule: Jira access is READ-ONLY

Never write to Jira — not via the bundled script, not via direct `curl`, not via any API call (`POST`/`PUT`/`DELETE` on `/rest/api/...`), not via any MCP server. If a request seems to want a write-back ("transition this to Done", "add a comment", "assign it to me"), refuse and say this skill is read-only. If they insist, escalate by asking explicitly — don't quietly add a write path.

## What it produces

`fetch` writes a single Markdown file:

- `# <KEY>: <summary>` heading and a browse link
- a metadata table (type, status, priority, assignee, reporter, resolution, parent, labels, created, updated)
- the rendered description (HTML → Markdown)
- all comments (author, timestamp, rendered body)

The script requests `expand=renderedFields`, so description and comments arrive as HTML and go through the same `markdownify` pipeline as confluence-sync (no ADF JSON parsing).

## Resolving the helper script

The helper lives inside the installed plugin under a version directory. Resolve the newest installed copy at call time — don't cache the path:

```bash
JFETCH=$(find ~/.claude/plugins/cache -path '*jira-fetch*/jira_fetch.py' 2>/dev/null | sort -V | tail -1)
```

`~/.claude/plugins/cache` is scoped deliberately — a blanket `~/.claude` search also matches the marketplace repo clone under `plugins/marketplaces/…`, which has no version dir and would sort last. `sort -V | tail -1` picks the highest installed version. Re-resolve `JFETCH` at the start of each Bash call (each tool call is a fresh shell).

> If `$JFETCH` comes back empty (e.g. testing via `--plugin-dir`), invoke the script by its explicit plugin path instead.

## Fetching an issue

Accepts a browse URL or a bare key:

```bash
JFETCH=$(find ~/.claude/plugins/cache -path '*jira-fetch*/jira_fetch.py' 2>/dev/null | sort -V | tail -1)

# From a browse URL (preferred — carries the tenant):
python3 "$JFETCH" fetch 'https://your-tenant.atlassian.net/browse/HN-25476' -o HN-25476.md

# From a bare key — needs the tenant base URL:
python3 "$JFETCH" fetch HN-25476 --base https://your-tenant.atlassian.net -o HN-25476.md
# (or set JIRA_BASE_URL in the environment instead of --base)
```

Pick an output path that fits the user's intent. For throwaway reference, write under a scratch/ dir or /tmp and don't commit it. If `fetch` exits non-zero with `ERR_AUTH_*` on stderr, see Auth below — do not retry.

After fetching, read the file and answer the user's question from it; don't dump the whole file back unless asked.

## Auth — the Jira session cookie

The user authenticates by copying their browser session cookie from DevTools (Network → any Jira request → Headers → Cookie). For Jira Cloud the relevant cookie is typically `tenant.session.token=eyJ...`, but the exact cookie name can vary by tenant — when in doubt, copy the full Cookie header value rather than extracting the JWT alone. Session validity is typically ~7 days.

The script stores the value verbatim at `~/.claude/secrets/jira-session` (mode 600). This is a **separate file from confluence-sync's** `~/.claude/secrets/confluence-session` — Atlassian issues distinct `tenant.session.token` values per product surface, so the Confluence cookie will generally not work for Jira and vice versa. On HTTP 401, the script deletes the Jira file and exits non-zero with `ERR_AUTH_INVALID` on stderr.

> **Why session cookie and not an Atlassian API token?** API tokens are normally the cleaner choice (long-lived, no weekly refresh). This plugin defaults to session cookies because some organizations disable API-token access entirely. If your tenant allows API tokens, prefer them and propose a PR.

### Setting the cookie

When the user says `set jira cookie '<value>'`, `update jira key '<value>'`, or similar:

```bash
JFETCH=$(find ~/.claude/plugins/cache -path '*jira-fetch*/jira_fetch.py' 2>/dev/null | sort -V | tail -1)
python3 "$JFETCH" set-token '<value>'
```

`<value>` is the full Cookie header content from browser DevTools, including the cookie name — e.g. `tenant.session.token=eyJ...`. The script rejects values without `=` with a helpful error so users notice if they only pasted the JWT.

### Error handling

If a `fetch` call prints `ERR_AUTH_INVALID` or `ERR_AUTH_MISSING` on stderr:

1. Stop immediately. Do not retry the call.
2. Tell the user the Jira session expired (or was never set) and they need to paste a fresh cookie via `set jira cookie '<value>'`. Remind them it's a different cookie than Confluence.
3. Wait. Do not attempt any further `fetch` until the user has set a new token.

## House rules

- Never `git add` fetched issue Markdown unless the user explicitly wants it committed, and never anything in `~/.claude/secrets/`.
- Never echo the session cookie back in chat after the user has provided it.
- The script is read-only against Jira by design (see the hard rule at the top).
