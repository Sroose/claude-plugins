# Changelog

## 0.2.0 — 2026-09-30

- Prefers the Atlassian MCP connector when it is available: Claude reads the issue through it and answers directly, writing a file only on request. The session cookie becomes the fallback, and the path for a faithful Markdown file (the connector drops mentions and links). Only the connector's read tools are used.
- `ERR_AUTH_MISSING` now prints a tip on enabling the connector; README install steps recommend it.
- Examples use a neutral `PROJ-123` issue key.

## 0.1.0 — 2026-06-09

- Initial release.
- `set-token` stores the Jira Cloud session cookie at `~/.claude/secrets/jira-session` (separate from confluence-sync's cookie).
- `fetch` downloads an issue (by browse URL or bare key + `--base`/`JIRA_BASE_URL`) to Markdown: heading, browse link, metadata table, rendered description, and comments.
- Read-only against Jira by design. HTTP 401 clears the stored token and exits `ERR_AUTH_INVALID`; missing token exits `ERR_AUTH_MISSING`.
