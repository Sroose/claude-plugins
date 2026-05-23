#!/usr/bin/env python3
"""confluence_sync.py — Read-only sync of Confluence pages to Markdown.

Subcommands:
  set-token <value>           Store the browser session cookie at ~/.claude/secrets/confluence-session
  fetch <url> -o <path>       Download a Confluence page and write Markdown to <path>

On HTTP 401, fetch deletes the stored token and exits with ERR_AUTH_INVALID on stderr.
On missing token, fetch exits with ERR_AUTH_MISSING on stderr.

Dependencies:
  - markdownify (pip install markdownify) — HTML→Markdown converter
  - curl on PATH — used for HTTP because we force --http1.1 (some Confluence
    Cloud instances 5xx on HTTP/2; left as curl until that's verified to be
    a non-issue in your tenant)
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

TOKEN_PATH = Path.home() / ".claude" / "secrets" / "confluence-session"

ERR_AUTH_MISSING = "ERR_AUTH_MISSING"
ERR_AUTH_INVALID = "ERR_AUTH_INVALID"

EXIT_OK = 0
EXIT_GENERIC = 1
EXIT_AUTH = 2


def read_token() -> str:
    if not TOKEN_PATH.exists():
        print(ERR_AUTH_MISSING, file=sys.stderr)
        sys.exit(EXIT_AUTH)
    return TOKEN_PATH.read_text().strip()


def write_token(token: str) -> None:
    """Persist the cookie value verbatim. We require the user to paste the full
    Cookie header value (name=value) — Confluence Cloud tenant cookie names
    vary (typically `tenant.session.token` but not universal), so we deliberately
    don't try to autocomplete the name."""
    value = token.strip()
    if "=" not in value:
        print(
            "ERROR: cookie value must include the cookie name, e.g. 'tenant.session.token=eyJ...'\n"
            "       Copy the full Cookie header line from your browser's DevTools\n"
            "       (Network → any Confluence request → Headers → Cookie).\n"
            "       The Confluence Cloud session cookie is typically called 'tenant.session.token',\n"
            "       but may differ depending on your Atlassian Cloud tenant.",
            file=sys.stderr,
        )
        sys.exit(EXIT_GENERIC)
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(value + "\n", encoding="utf-8")
    TOKEN_PATH.chmod(0o600)


def clear_token() -> None:
    if TOKEN_PATH.exists():
        TOKEN_PATH.unlink()


def fetch_page_json(url: str, token: str) -> dict:
    # Published-page URL: /wiki/spaces/<SPACE>/pages/<id>/...
    match = re.search(r"/pages/(\d+)", url)
    is_draft = False
    if not match:
        # Draft URLs: /wiki/pages/resumedraft.action?draftId=<id>&...
        #             /wiki/spaces/<SPACE>/pages/edit-v2/<id>?...
        m = re.search(r"[?&]draftId=(\d+)", url) or re.search(r"/pages/edit-v2/(\d+)", url)
        if m:
            match = m
            is_draft = True
    if not match:
        print(f"ERROR: could not extract page ID from URL: {url}", file=sys.stderr)
        sys.exit(EXIT_GENERIC)
    page_id = match.group(1)

    base_match = re.match(r"(https://[^/]+/wiki)", url)
    if not base_match:
        print(f"ERROR: could not extract base URL from: {url}", file=sys.stderr)
        sys.exit(EXIT_GENERIC)
    base_url = base_match.group(1)

    api_url = f"{base_url}/rest/api/content/{page_id}?expand=body.export_view"
    if is_draft:
        api_url += "&status=draft"
    kind = "draft" if is_draft else "page"
    print(f"Fetching {kind} {page_id} from {base_url} ...", file=sys.stderr)

    marker = "__HTTP_STATUS__"
    # --http1.1 forces HTTP/1.1 — some Confluence Cloud instances returned 5xx
    # on HTTP/2 during early testing. Safe to remove if your tenant works fine
    # on HTTP/2 (or to swap the whole call for urllib.request).
    result = subprocess.run(
        [
            "curl", "-s", "--http1.1",
            "-H", f"Cookie: {token}",
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
        print(f"ERROR: could not parse HTTP status from curl output", file=sys.stderr)
        sys.exit(EXIT_GENERIC)

    if status == 401:
        clear_token()
        print(ERR_AUTH_INVALID, file=sys.stderr)
        sys.exit(EXIT_AUTH)

    if status != 200:
        print(f"ERROR: Confluence returned HTTP {status}", file=sys.stderr)
        print(body[:500].strip(), file=sys.stderr)
        sys.exit(EXIT_GENERIC)

    # Strip the trailing newline left between body and marker
    body = body.rstrip("\n")

    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        print(f"ERROR: response was not JSON: {e}", file=sys.stderr)
        print(body[:500], file=sys.stderr)
        sys.exit(EXIT_GENERIC)


def confluence_html_to_md(html: str) -> str:
    # Convert Confluence <ac:structured-macro ac:name="code"> blocks to <pre><code>
    html = re.sub(
        r'<ac:structured-macro[^>]*ac:name="code"[^>]*>.*?'
        r"<ac:plain-text-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-body>.*?"
        r"</ac:structured-macro>",
        r"<pre><code>\1</code></pre>",
        html,
        flags=re.DOTALL,
    )
    # Drop all other Confluence-specific tags
    html = re.sub(r"<ac:[^>]+>.*?</ac:[^>]+>", "", html, flags=re.DOTALL)
    html = re.sub(r"<ac:[^/][^>]*/>", "", html)
    html = re.sub(r"<ri:[^>]+/?>", "", html)

    result = md(html, heading_style="ATX", bullets="-")
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def cmd_set_token(args: argparse.Namespace) -> None:
    write_token(args.token)
    print(f"token written to {TOKEN_PATH}", file=sys.stderr)


def cmd_fetch(args: argparse.Namespace) -> None:
    token = read_token()
    data = fetch_page_json(args.url, token)
    title = data.get("title", "Page")
    html = data["body"]["export_view"]["value"]
    markdown = f"# {title}\n\n" + confluence_html_to_md(html)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown, encoding="utf-8")
    print(f'"{title}" -> {out} ({len(markdown):,} chars)', file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Confluence -> Markdown sync helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_set = sub.add_parser("set-token", help="Store the Confluence session cookie")
    p_set.add_argument("token", help="Full Cookie header value, e.g. 'tenant.session.token=eyJ...'")
    p_set.set_defaults(func=cmd_set_token)

    p_fetch = sub.add_parser("fetch", help="Download a Confluence page as Markdown")
    p_fetch.add_argument("url", help="Confluence page URL")
    p_fetch.add_argument("-o", "--output", required=True, help="Output .md path")
    p_fetch.set_defaults(func=cmd_fetch)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
