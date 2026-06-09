# Changelog

## 0.1.0 — 2026-06-09

- Initial release.
- `set-token` stores the Jira Cloud session cookie at `~/.claude/secrets/jira-session` (separate from confluence-sync's cookie).
- `fetch` downloads an issue (by browse URL or bare key + `--base`/`JIRA_BASE_URL`) to Markdown: heading, browse link, metadata table, rendered description, and comments.
- Read-only against Jira by design. HTTP 401 clears the stored token and exits `ERR_AUTH_INVALID`; missing token exits `ERR_AUTH_MISSING`.
