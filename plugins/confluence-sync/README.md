# confluence-sync

A Claude Code plugin for keeping local Markdown files in sync with Confluence Cloud pages — **read-only against Confluence**.

The flow: the plugin pulls a fresh snapshot of the Confluence page → you (or Claude) edit your local Markdown → you diff the proposal against the snapshot and apply changes manually in the Confluence editor → the plugin re-pulls and triages deviations between what you proposed and what actually landed.

Why manual apply: Markdown ↔ Confluence storage-format round-trips are lossy (table widths, info/warning macros, panel layouts, image placement). Owning the last leg in the Confluence editor keeps page quality high.

## Install

```
/plugin marketplace add Sroose/claude-plugins
/plugin install confluence-sync@sroose-plugins
pip install markdownify    # one-time, required dependency
```

## Quickstart

```
set confluence cookie 'tenant.session.token=eyJ...'   # ~ once per week
check the ARCH doc                                     # triggers the Begin step
# Claude pulls fresh snapshot, diffs, asks you about substantive drift
# You edit the markdown
# Claude tells you to diff in your IDE and apply in Confluence
# After you apply: ask Claude to close
# Claude re-pulls and triages deviations
```

## Configuration

Each project lists its Confluence-shadowed docs in a `confluence-sync.yaml`:

```yaml
docs:
  - name: ARCH                       # short id, used in user references
    title: System architecture
    path: docs/architecture.md
    url: https://your-tenant.atlassian.net/wiki/spaces/.../pages/12345
```

The plugin looks for `confluence-sync.yaml` in cwd then in the repo root.

## How auth works

The plugin uses your browser session cookie (typically `tenant.session.token=eyJ...` for Confluence Cloud). Validity is usually ~7 days; when it expires Claude will tell you to paste a fresh one.

> **API token alternative**: Atlassian also supports long-lived API tokens, which would be a cleaner auth model. This plugin doesn't support them yet, and also API access might be disabled by your organisation.

## Read-only by design

The plugin never writes to Confluence — no `PUT`, no `POST` to `/rest/api/content/...`, no MCP write paths. This is a deliberate constraint, not a limitation. See `SKILL.md` for the full rationale.

## Reference

- [SKILL.md](skills/confluence-sync/SKILL.md) — the full workflow Claude follows (Begin → Edit → Hand off → Close → Abort)
- [CHANGELOG.md](CHANGELOG.md) — version history

## License

MIT — see the repo-level [LICENSE](../../LICENSE).
