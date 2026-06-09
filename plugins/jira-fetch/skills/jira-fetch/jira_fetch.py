#!/usr/bin/env python3
"""jira_fetch.py — Read-only fetch of Jira Cloud issues to Markdown.

Subcommands:
  set-token <value>           Store the browser session cookie at ~/.claude/secrets/jira-session
  fetch <url|key> -o <path>   Download a Jira issue and write Markdown to <path>

`fetch` accepts either a browse URL (https://<tenant>.atlassian.net/browse/HN-123)
or a bare issue key (HN-123). A bare key requires --base (or the JIRA_BASE_URL env var)
to know which tenant to hit.

On HTTP 401, fetch deletes the stored token and exits with ERR_AUTH_INVALID on stderr.
On missing token, fetch exits with ERR_AUTH_MISSING on stderr.

The Jira session cookie is stored separately from the Confluence one
(~/.claude/secrets/jira-session vs ~/.claude/secrets/confluence-session) — Atlassian
issues distinct tenant.session.token values per product surface.

Dependencies:
  - markdownify (pip install markdownify) — HTML->Markdown converter
  - curl on PATH — used for HTTP because we force --http1.1 (kept consistent with
    confluence_sync.py; some Atlassian Cloud instances 5xx on HTTP/2)
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    from markdownify import markdownify as md
except ImportError:
    print(
        "ERROR: missing dependency 'markdownify'. Install with:\n"
        "  pip install markdownify\n"
        "  (or use pipx / virtualenv as appropriate for your setup)",
        file=sys.stderr,
    )
    sys.exit(1)

TOKEN_PATH = Path.home() / ".claude" / "secrets" / "jira-session"

ERR_AUTH_MISSING = "ERR_AUTH_MISSING"
ERR_AUTH_INVALID = "ERR_AUTH_INVALID"

EXIT_OK = 0
EXIT_GENERIC = 1
EXIT_AUTH = 2

# Fields we pull. renderedFields gives us HTML for description + comment bodies
# (the same trick confluence_sync uses with body.export_view), so we can reuse
# the markdownify pipeline instead of parsing Atlassian Document Format JSON.
FIELDS = "summary,status,issuetype,priority,assignee,reporter,labels,created,updated,resolution,parent,description,comment"


def read_token() -> str:
    if not TOKEN_PATH.exists():
        print(ERR_AUTH_MISSING, file=sys.stderr)
        sys.exit(EXIT_AUTH)
    return TOKEN_PATH.read_text().strip()


def write_token(token: str) -> None:
    """Persist the cookie value verbatim. We require the user to paste the full
    Cookie header value (name=value) — Atlassian Cloud tenant cookie names vary
    (typically `tenant.session.token` but not universal), so we deliberately
    don't try to autocomplete the name."""
    value = token.strip()
    if "=" not in value:
        print(
            "ERROR: cookie value must include the cookie name, e.g. 'tenant.session.token=eyJ...'\n"
            "       Copy the full Cookie header line from your browser's DevTools\n"
            "       (Network -> any Jira request -> Headers -> Cookie).\n"
            "       The Jira Cloud session cookie is typically called 'tenant.session.token',\n"
            "       but may differ depending on your Atlassian Cloud tenant.\n"
            "       Note: this is a DIFFERENT cookie value than the Confluence one.",
            file=sys.stderr,
        )
        sys.exit(EXIT_GENERIC)
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(value + "\n", encoding="utf-8")
    TOKEN_PATH.chmod(0o600)


def clear_token() -> None:
    if TOKEN_PATH.exists():
        TOKEN_PATH.unlink()


def resolve_issue(ref: str, base_override: str | None) -> tuple[str, str]:
    """Return (base_url, issue_key) from a browse URL or a bare key."""
    # Browse URL: https://<tenant>.atlassian.net/browse/HN-25476
    m = re.match(r"(https://[^/]+)/browse/([A-Z][A-Z0-9_]+-\d+)", ref)
    if m:
        return m.group(1), m.group(2)

    # Any Atlassian URL that carries a selectedIssue / issue key somewhere
    m_base = re.match(r"(https://[^/]+)", ref)
    m_key = re.search(r"\b([A-Z][A-Z0-9_]+-\d+)\b", ref)
    if m_base and m_key:
        return m_base.group(1), m_key.group(1)

    # Bare key: HN-25476 — needs a base URL from --base or env
    if re.fullmatch(r"[A-Z][A-Z0-9_]+-\d+", ref):
        if not base_override:
            print(
                "ERROR: a bare issue key needs a tenant base URL.\n"
                "       Pass --base https://<tenant>.atlassian.net or set JIRA_BASE_URL,\n"
                "       or just pass the full browse URL instead.",
                file=sys.stderr,
            )
            sys.exit(EXIT_GENERIC)
        return base_override.rstrip("/"), ref

    print(f"ERROR: could not extract an issue key from: {ref}", file=sys.stderr)
    sys.exit(EXIT_GENERIC)


def fetch_issue_json(ref: str, token: str, base_override: str | None) -> tuple[dict, str]:
    base_url, key = resolve_issue(ref, base_override)
    api_url = f"{base_url}/rest/api/3/issue/{key}?fields={FIELDS}&expand=renderedFields"
    print(f"Fetching issue {key} from {base_url} ...", file=sys.stderr)

    marker = "__HTTP_STATUS__"
    # --http1.1 kept consistent with confluence_sync.py. Safe to drop if your
    # tenant is fine on HTTP/2 (or to swap the call for urllib.request).
    result = subprocess.run(
        [
            "curl", "-s", "--http1.1",
            "-H", f"Cookie: {token}",
            "-H", "Accept: application/json",
            "-w", f"\n{marker}%{{http_code}}",
            api_url,
        ],
        capture_output=True, text=True,
    )

    if result.returncode != 0:
        print(f"ERROR: curl failed (exit {result.returncode}): {result.stderr.strip()}", file=sys.stderr)
        sys.exit(EXIT_GENERIC)

    body, _, code_str = result.stdout.rpartition(marker)
    try:
        status = int(code_str.strip())
    except ValueError:
        print("ERROR: could not parse HTTP status from curl output", file=sys.stderr)
        sys.exit(EXIT_GENERIC)

    if status == 401:
        clear_token()
        print(ERR_AUTH_INVALID, file=sys.stderr)
        sys.exit(EXIT_AUTH)

    if status == 404:
        print(f"ERROR: issue {key} not found (HTTP 404) — wrong key, or no access.", file=sys.stderr)
        sys.exit(EXIT_GENERIC)

    if status != 200:
        print(f"ERROR: Jira returned HTTP {status}", file=sys.stderr)
        print(body[:500].strip(), file=sys.stderr)
        sys.exit(EXIT_GENERIC)

    body = body.rstrip("\n")
    try:
        return json.loads(body), base_url
    except json.JSONDecodeError as e:
        print(f"ERROR: response was not JSON: {e}", file=sys.stderr)
        print(body[:500], file=sys.stderr)
        sys.exit(EXIT_GENERIC)


def jira_html_to_md(html: str) -> str:
    if not html:
        return ""
    result = md(html, heading_style="ATX", bullets="-")
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _name(field) -> str:
    """displayName / name out of a Jira user or named-object field, or '—'."""
    if not field:
        return "—"
    if isinstance(field, dict):
        return field.get("displayName") or field.get("name") or "—"
    return str(field)


def issue_to_markdown(data: dict, base_url: str) -> tuple[str, str]:
    key = data.get("key", "ISSUE")
    fields = data.get("fields", {}) or {}
    rendered = data.get("renderedFields", {}) or {}
    summary = fields.get("summary") or ""

    lines = [f"# {key}: {summary}".rstrip(), ""]
    lines.append(f"**Link:** {base_url}/browse/{key}")
    lines.append("")

    # Metadata table
    parent = fields.get("parent") or {}
    parent_str = "—"
    if parent:
        pk = parent.get("key", "")
        ps = (parent.get("fields") or {}).get("summary", "")
        parent_str = f"{pk} {ps}".strip()

    meta = [
        ("Type", _name(fields.get("issuetype"))),
        ("Status", _name(fields.get("status"))),
        ("Priority", _name(fields.get("priority"))),
        ("Assignee", _name(fields.get("assignee"))),
        ("Reporter", _name(fields.get("reporter"))),
        ("Resolution", _name(fields.get("resolution"))),
        ("Parent", parent_str),
        ("Labels", ", ".join(fields.get("labels") or []) or "—"),
        ("Created", rendered.get("created") or fields.get("created") or "—"),
        ("Updated", rendered.get("updated") or fields.get("updated") or "—"),
    ]
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    for k, v in meta:
        lines.append(f"| {k} | {v} |")
    lines.append("")

    # Description
    lines.append("## Description")
    lines.append("")
    desc = jira_html_to_md(rendered.get("description") or "")
    lines.append(desc if desc else "_(no description)_")
    lines.append("")

    # Comments
    comment_field = rendered.get("comment") or {}
    comments = comment_field.get("comments") if isinstance(comment_field, dict) else None
    if comments:
        lines.append(f"## Comments ({len(comments)})")
        lines.append("")
        for c in comments:
            author = _name(c.get("author"))
            when = c.get("created") or ""
            lines.append(f"### {author} — {when}".rstrip())
            lines.append("")
            lines.append(jira_html_to_md(c.get("body") or "") or "_(empty)_")
            lines.append("")

    markdown = "\n".join(lines).rstrip() + "\n"
    return summary or key, markdown


def cmd_set_token(args: argparse.Namespace) -> None:
    write_token(args.token)
    print(f"token written to {TOKEN_PATH}", file=sys.stderr)


def cmd_fetch(args: argparse.Namespace) -> None:
    import os
    base = args.base or os.environ.get("JIRA_BASE_URL")
    token = read_token()
    data, base_url = fetch_issue_json(args.url, token, base)
    title, markdown = issue_to_markdown(data, base_url)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown, encoding="utf-8")
    print(f'"{data.get("key", "")}: {title}" -> {out} ({len(markdown):,} chars)', file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Jira -> Markdown fetch helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_set = sub.add_parser("set-token", help="Store the Jira session cookie")
    p_set.add_argument("token", help="Full Cookie header value, e.g. 'tenant.session.token=eyJ...'")
    p_set.set_defaults(func=cmd_set_token)

    p_fetch = sub.add_parser("fetch", help="Download a Jira issue as Markdown")
    p_fetch.add_argument("url", help="Jira browse URL or bare issue key (e.g. HN-25476)")
    p_fetch.add_argument("-o", "--output", required=True, help="Output .md path")
    p_fetch.add_argument("--base", help="Tenant base URL (needed only for a bare key); or set JIRA_BASE_URL")
    p_fetch.set_defaults(func=cmd_fetch)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
