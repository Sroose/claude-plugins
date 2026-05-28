#!/usr/bin/env python3
"""SessionStart hook for confluence-sync.

Maintains a stable symlink at ~/.claude/confluence-sync/confluence_sync.py
pointing at the actual script for this plugin install, so SKILL.md and user
invocations can reference one fixed path regardless of where the plugin lives
on disk (plugin cache layout includes version dirs that change on upgrade).

The symlink target is RELATIVE. ~/.claude is often a shared bind-mount between a
Docker container ($HOME=/home/claude) and the host ($HOME=/Users/<you>): same
files, different absolute paths. An absolute target is only valid in one
namespace; a relative one (e.g. ../plugins/cache/.../confluence_sync.py)
resolves in both, since link and target share the ~/.claude root.
"""
import os
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_SRC = PLUGIN_ROOT / "skills" / "confluence-sync" / "confluence_sync.py"

LINK_DIR = Path.home() / ".claude" / "confluence-sync"
LINK_PATH = LINK_DIR / "confluence_sync.py"

try:
    LINK_DIR.mkdir(parents=True, exist_ok=True)
    if LINK_PATH.is_symlink() or LINK_PATH.exists():
        LINK_PATH.unlink()
    LINK_PATH.symlink_to(os.path.relpath(SCRIPT_SRC, LINK_PATH.parent))
except Exception:
    # Non-fatal: SKILL.md instructs a find-based fallback.
    pass
