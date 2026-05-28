# Changelog

## 0.1.1 — 2026-05-28

- **Symlink at `~/.claude/confluence-sync/confluence_sync.py` is now relative.** Same fix as agent-bus 0.1.2: an absolute symlink target breaks when `~/.claude` is a shared bind-mount between a Docker container and the host. Relative targets resolve from both namespaces.

## 0.1.0 — 2026-05-23

Initial release.

- `set-token` and `fetch` subcommands via `confluence_sync.py`
- Read-only against Confluence by design — the user applies changes manually in the Confluence editor
- Pre-edit `X.PREV.<TS>.md` checkpoints; rotating `X.CUR.<TS>.md` Confluence snapshots
- Drift triage table (silent rebase for export-converter artifacts; explicit confirmation for substantive drift)
- Deviation triage on close: distinguishes wording reworks, formatting artifacts, missing sentences, and additions
- `ERR_AUTH_MISSING` / `ERR_AUTH_INVALID` sentinels on stderr for clean skill-level error handling
- SessionStart hook maintains `~/.claude/confluence-sync/confluence_sync.py` symlink for stable invocation path
- Session cookie stored at `~/.claude/secrets/confluence-session` (mode 600); cleared automatically on HTTP 401

### Known limits

- Auth is session-cookie only (typically ~7-day validity, must refresh weekly). API-token auth would be cleaner but might be blocked by the tenant.
- `--http1.1` is forced on the curl call because some Confluence Cloud instances 5xx'd on HTTP/2 during early testing. Remove the flag locally if your tenant is fine on HTTP/2.
- Requires `pip install markdownify`. The script exits with a clear error if the import fails.
