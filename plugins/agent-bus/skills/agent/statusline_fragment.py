#!/usr/bin/env python3
"""Statusline fragment for agent-bus. Prints the registered agent name for
THIS session, or empty if unregistered.

Matches on the session_id from CC's session JSON on stdin (falling back to
$CLAUDE_CODE_SESSION_ID) only — deliberately NOT bus.py my_entry()'s hostname
fallback, which exists for a watcher holding a stale session_id after /resume.
The statusline always has the current one, so a hostname match can only name
some other session: every native session on a Mac shares one hostname.
"""
import json, sys, os, glob

BUS_ROOT = os.environ.get("BUS_ROOT", os.path.expanduser("~/.claude/bus"))

# Drain stdin so the parent doesn't block; it carries CC's session JSON.
raw = ""
try:
    if not sys.stdin.isatty():
        raw = sys.stdin.read()
except Exception:
    pass
try:
    sid = (json.loads(raw or "{}").get("session_id", "") or "")
except Exception:
    sid = ""
sid = sid or os.environ.get("CLAUDE_CODE_SESSION_ID", "")

entries = []
for f in sorted(glob.glob(os.path.join(BUS_ROOT, "registry", "*.json"))):
    try:
        with open(f) as fh:
            entries.append(json.load(fh))
    except Exception:
        continue

name = ""
for d in entries:
    if sid and d.get("session_id") == sid:
        name = d.get("name", "")
        break

if name:
    print(name)
