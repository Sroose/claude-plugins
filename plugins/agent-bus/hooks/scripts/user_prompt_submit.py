#!/usr/bin/env python3
"""UserPromptSubmit hook for agent-bus: sync the session's display name
(sessionTitle) to whatever THIS session is registered as in the bus registry.

session_id match only — deliberately NOT bus.py my_entry()'s hostname fallback.
That fallback exists for the watcher, which keeps a stale session_id in its env
after /resume. This hook gets the current session_id from its input, so a
hostname match can only ever name some other session: on a Mac every native
session shares one hostname, and a lone registration there labelled them all.

A session the user renamed with /rename is never retitled: their name wins over
the registry's for the rest of the session's life."""
import json, sys, os, glob

RENAME_TAG = "<command-name>/rename</command-name>"


def manually_renamed(transcript_path):
    """True if the transcript holds a /rename the user ran. Only the record CC
    writes for the command counts (type=system, subtype=local_command, content
    starting with the tag): the bare string also turns up in tool calls and
    pasted text, e.g. a session that greps transcripts for it. A fork carries
    its parent's records, so it inherits the parent's rename — fine, when in
    doubt leave the title alone."""
    if not transcript_path:
        return False
    needle = RENAME_TAG.encode()
    try:
        with open(transcript_path, "rb") as fh:
            for line in fh:
                if needle not in line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if (isinstance(d, dict) and d.get("type") == "system"
                        and d.get("subtype") == "local_command"
                        and str(d.get("content", "")).lstrip().startswith(RENAME_TAG)):
                    return True
    except Exception:
        pass
    return False


BUS_ROOT = os.environ.get("BUS_ROOT", os.path.expanduser("~/.claude/bus"))

# The hook input carries this session's id; env is the fallback.
try:
    inp = json.loads(sys.stdin.read() or "{}")
except Exception:
    inp = {}
sid = inp.get("session_id", "") or os.environ.get("CLAUDE_CODE_SESSION_ID", "")

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

if name and not manually_renamed(inp.get("transcript_path", "")):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "sessionTitle": name,
        }
    }))

sys.exit(0)
