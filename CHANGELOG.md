# Changelog — marketplace

This file tracks marketplace-level changes: plugins added, removed, renamed, or marketplace-wide reshuffles. Per-plugin version history lives in `plugins/<name>/CHANGELOG.md`.

## 2026-05-28

- agent-bus → 0.1.2, confluence-sync → 0.1.1: both fix absolute→relative symlinks so the `~/.claude` stable-path links survive a shared container/host bind-mount. See each plugin's CHANGELOG.

## 2026-05-23

- Added [confluence-sync](plugins/confluence-sync/) (initial release at 0.1.0).
- Split per-plugin docs out of the top-level: `README.md`, `DESIGN.md`, `CHANGELOG.md`, and `demo/` for agent-bus moved into `plugins/agent-bus/`. The top-level `README.md` is now a marketplace overview, and this `CHANGELOG.md` is marketplace-scope only.

## 2026-05-20

- agent-bus bumped to 0.1.1 — see [plugins/agent-bus/CHANGELOG.md](plugins/agent-bus/CHANGELOG.md).

## 2026-05-19

- Marketplace renamed: repo `Sroose/agent-bus` → `Sroose/claude-plugins`; marketplace `agent-bus-marketplace` → `sroose-plugins`. Install command is now `/plugin marketplace add Sroose/claude-plugins`.
- agent-bus initial release at 0.1.0.
