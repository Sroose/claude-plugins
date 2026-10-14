# Changelog

## 0.1.3 — 2026-08-03

- **Inline task lists (checkboxes) now keep their state.** Confluence renders them as `<li class="checked" data-inline-task-id="N">`, and the state lives only in that class attribute, which markdownify discards. Every option came out as a plain bullet, so a fully answered checklist read as an empty one, and any conclusion drawn from it was wrong in a way that looked plausible. Items now convert to `- [x] ` / `- [ ] `. Matching is on `data-inline-task-id` rather than on the enclosing `<ul class="inline-task-list">`, so nested task lists are handled too.
  - Note for the print/PDF route: Confluence's own PDF export draws the checkmarks as vectors, so PDF text extraction does **not** recover the state. The API `export_view` HTML this script uses is the reliable source.

## 0.1.2 — 2026-05-28

- **Dropped the `~/.claude/confluence-sync/` script symlink; helper is now resolved at call time** via `find ~/.claude/plugins/cache -path '*confluence-sync*/confluence_sync.py' | sort -V | tail -1`. Same rationale as agent-bus 0.1.3 — a shared symlink can't serve a container and the host simultaneously. The SessionStart hook (whose only job was the symlink) has been removed entirely.

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
