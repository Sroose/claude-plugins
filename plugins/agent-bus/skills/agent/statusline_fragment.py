#!/usr/bin/env python3
"""Statusline fragment for agent-bus. Prints the registered agent name for
THIS session, or empty if unregistered.

Resolution order matches bus.py my_entry(): the session_id from CC's session
JSON on stdin (falling back to $CLAUDE_CODE_SESSION_ID), then a *unique*
hostname match. Hostname alone is not an identity — every native session on a
Mac shares one, so a first-match wins scan labels them all the same.
"""
import json, sys, os, glob, socket

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
host = socket.gethostname()

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
else:
    mine = [d for d in entries if host and d.get("container") == host]
    if len(mine) == 1:
        name = mine[0].get("name", "")

if name:
    print(name)
