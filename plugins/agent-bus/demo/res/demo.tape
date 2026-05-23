# VHS tape — generates demo.gif showing two Claude Code sessions talking via agent-bus.
#
# Install VHS (one-time):   brew install vhs
# Regenerate the GIF:       vhs plugins/agent-bus/demo/res/demo.tape    # invoked from the repo root
#
# Prerequisites:
#   - agent-bus installed (e.g. /plugin install agent-bus@sroose-plugins,
#     or pass --plugin-dir on the cld invocations below for local dev)
#   - tmux available on PATH
#
# What this records:
#   - Two tmux panes side-by-side
#   - Left pane = PRODUCER, working out of /tmp/PRODUCER (with its own CLAUDE.md
#     dropped from plugins/agent-bus/demo/res/producer-CLAUDE.md)
#   - Right pane = CONSUMER, working out of /tmp/CONSUMER (CLAUDE.md from
#     plugins/agent-bus/demo/res/consumer-CLAUDE.md)
#   - CONSUMER asks PRODUCER a contract question, PRODUCER replies from its
#     CLAUDE.md, CONSUMER auto-replies with a follow-up.

# Output is relative to vhs's cwd. Run vhs from the repo root and this writes
# plugins/agent-bus/demo/demo.gif (where the agent-bus README image points).
Output plugins/agent-bus/demo/demo.gif

Set Shell "bash"
Set FontSize 14
Set Width 1400
Set Height 800
# Set Theme "Catppuccin Mocha"   # uncomment to override the default theme
# Theme names list: https://github.com/charmbracelet/vhs/blob/main/THEMES.md
# Other common picks: "Dracula", "Nord", "Tokyo Night", "GitHub Dark Dimmed"
Set TypingSpeed 50ms
Set PlaybackSpeed 1.0

# Open two side-by-side panes via tmux. Hide/Show suppresses these from the
# final recording so the viewer never sees the tmux plumbing.
Hide

# Kill any leftover tmux session from a previous recording — otherwise
# `tmux new-session` silently fails (name already exists) and `attach`
# reconnects to the ghost session with its old pane content visible.
Type "tmux kill-session -t agentbus 2>/dev/null; true"
Enter
Sleep 200ms

# Wipe leftover bus state. If we don't, registering PRODUCER/CONSUMER this run
# will hit a "name already held by another container" conflict against stale
# registry entries from previous recordings.
Type "rm -rf ~/.claude/bus/registry ~/.claude/bus/inbox ~/.claude/bus/cwd-memo ~/.claude/bus/archive ~/.claude/bus/log 2>/dev/null; true"
Enter
Sleep 200ms

# Set up the two demo workspaces with fresh CLAUDE.md files. Each pane will cd
# into one of these dirs before launching `cld`, so the Claude session in that
# pane picks up the project-level CLAUDE.md as context (PRODUCER gets the API
# spec; CONSUMER gets the integration-questions checklist).
Type "rm -rf /tmp/PRODUCER /tmp/CONSUMER; mkdir -p /tmp/PRODUCER /tmp/CONSUMER"
Enter
Sleep 200ms
Type "cp plugins/agent-bus/demo/res/producer-CLAUDE.md /tmp/PRODUCER/CLAUDE.md && cp plugins/agent-bus/demo/res/consumer-CLAUDE.md /tmp/CONSUMER/CLAUDE.md"
Enter
Sleep 200ms

Type "tmux new-session -d -s agentbus -x 240 -y 50"
Enter
Sleep 200ms
Type "tmux split-window -h -t agentbus"
Enter
Sleep 200ms
Type "tmux attach -t agentbus"
Enter
Sleep 1s

# `tmux split-window -h` focuses the NEW (right) pane by default, so jump back
# to the left (original) pane before we start typing the PRODUCER setup.
Ctrl+b
Type "o"
Sleep 500ms
Show

# Scenario: two Claude sessions in two different repos that share a contract —
# a PRODUCER (the service exposing an API) and a CONSUMER (the client calling
# into it). They need to align on field names and request shapes before the
# CONSUMER commits its integration code.

# --- Left pane: launch session A, register as PRODUCER ---
Type "cd /tmp/PRODUCER"
Enter
Sleep 200ms
Type "cld"
Enter
Sleep 3s
Type "/agent register PRODUCER"
Enter
Sleep 3s

# --- Right pane: launch session B, register as CONSUMER ---
Ctrl+b
Type "o"
Sleep 500ms

Type "cd /tmp/CONSUMER"
Enter
Sleep 200ms
Type "cld"
Enter
Sleep 3s
Type "register as CONSUMER"
Enter
Sleep 2s

# --- From CONSUMER, ask PRODUCER about the contract.
# Two-question prompt → reply answers both → CONSUMER naturally follows up
# on the edge case (the PATCH semantics) → multi-turn exchange.
Type `ask PRODUCER "Quick contract check before I wire up the prefs client: what's the field name for the user's preferred locale — lang, locale, or language? And does PATCH on /prefs expect a full object or only the changed keys?"`
Enter
Sleep 3s

# --- Switch back to PRODUCER; the first message arrives + reply auto-fires ---
Ctrl+b
Type "o"
Sleep 8s

# --- Watch the second pong: PRODUCER's auto-reply lands in CONSUMER's pane,
#     CONSUMER auto-replies (refining on PATCH semantics). Give it room.
Sleep 30s

# --- Final pause so the viewer can read the full thread ---
Sleep 4s

# --- Clean up ---
Type "exit"
Enter
Sleep 500ms
Ctrl+b
Type "o"
Sleep 500ms
Type "exit"
Enter
Sleep 500ms
