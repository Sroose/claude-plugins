# jira-fetch

A Claude Code plugin for pulling Jira Cloud issues into local Markdown — **read-only against Jira**.

Fetch a ticket (key, metadata, description, comments) into a Markdown file so Claude can read it while working in your repo. The sibling of [confluence-sync](../confluence-sync): same session-cookie auth model and `markdownify` HTML→Markdown pipeline, but for issues instead of wiki pages, and one-way (no apply/verify loop — you don't shadow-edit tickets).

## Install

```
/plugin marketplace add Sroose/claude-plugins
/plugin install jira-fetch@sroose-plugins
pip install markdownify    # one-time, required dependency
```

**Recommended: connect the Atlassian connector.** In claude.ai go to Settings → Connectors and connect Atlassian, then run `/mcp` in Claude Code to check it shows as connected. With the connector available Claude reads issues through it and you never need to set a cookie. It drops some formatting (user mentions, links), so the cookie below stays as the fallback, and as the path for a faithful Markdown file.

## Quickstart

```
set jira cookie 'tenant.session.token=eyJ...'           # ~ once per week (separate from Confluence)
fetch https://your-tenant.atlassian.net/browse/PROJ-123  # Claude pulls it to Markdown and reads it
```

You can also pass a bare key (`fetch PROJ-123`) if you give Claude the tenant base URL or set `JIRA_BASE_URL`.

## What you get

A single Markdown file:

- `# PROJ-123: <summary>` + browse link
- metadata table — type, status, priority, assignee, reporter, resolution, parent, labels, created, updated
- the rendered description
- all comments (author, timestamp, body)

## How auth works

With the Atlassian connector connected, auth is the connector's own OAuth login and nothing is stored by this plugin. Otherwise the plugin uses your browser session cookie (typically `tenant.session.token=eyJ...` for Jira Cloud), stored at `~/.claude/secrets/jira-session` (mode 600). This is a **different cookie value than Confluence** — Atlassian issues distinct session tokens per product surface — so it's kept in a separate file. Validity is usually ~7 days; when it expires Claude will tell you to paste a fresh one.

> **API token alternative**: Atlassian also supports long-lived API tokens, which would be a cleaner auth model. This plugin doesn't support them yet, and API access may be disabled by your organisation.

## Read-only by design

The plugin never writes to Jira — no transitions, comments, or edits; no `POST`/`PUT`/`DELETE` to `/rest/api/...`. On the connector path it uses only read tools, even though the connector also offers write tools. See `SKILL.md` for the full rationale.

## Reference

- [SKILL.md](skills/jira-fetch/SKILL.md) — the workflow Claude follows
- [CHANGELOG.md](CHANGELOG.md) — version history

## License

MIT — see the repo-level [LICENSE](../../LICENSE).
