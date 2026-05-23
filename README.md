# Sroose's Claude Code plugins

A small marketplace of Claude Code plugins maintained by [@Sroose](https://github.com/Sroose).

## Install the marketplace

```
/plugin marketplace add Sroose/claude-plugins
```

Then install individual plugins:

```
/plugin install <plugin-name>@sroose-plugins
```

## Plugins

### [agent-bus](plugins/agent-bus/) — inter-session messaging

> Let two or more Claude Code sessions on the same machine talk to each other. Register each session as a named agent (`OBSIDIAN`, `CODE`, `INFRA`, …) and they exchange messages, with incoming messages auto-surfacing in the recipient's transcript — no user typing needed.

```
/plugin install agent-bus@sroose-plugins
```

![demo](plugins/agent-bus/demo/demo.gif)

→ [plugins/agent-bus/README.md](plugins/agent-bus/README.md) for usage, [DESIGN.md](plugins/agent-bus/DESIGN.md) for internals.

### [confluence-sync](plugins/confluence-sync/) — Confluence Cloud ↔ Markdown sync

> Keep local Markdown shadow files in sync with Confluence Cloud pages. Read-only against Confluence: pulls snapshots, manages pre-edit checkpoints, orchestrates the edit→apply→verify loop, and triages deviations after you apply changes manually in the Confluence editor.

```
/plugin install confluence-sync@sroose-plugins
pip install markdownify    # one-time, required dependency
```

→ [plugins/confluence-sync/README.md](plugins/confluence-sync/README.md) for usage, [SKILL.md](plugins/confluence-sync/skills/confluence-sync/SKILL.md) for the full workflow.

## Marketplace-level changes

See [CHANGELOG.md](CHANGELOG.md) for plugin additions, removals, and renames at the marketplace level. Each plugin tracks its own version history in `plugins/<name>/CHANGELOG.md`.

## License

MIT — see [LICENSE](LICENSE). Same license applies to all plugins in this marketplace.
