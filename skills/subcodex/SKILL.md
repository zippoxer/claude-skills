---
name: subcodex
description: |
  Collaborate with Codex (GPT-5.2) via named sessions. Trigger: user asks to work with Codex, use Codex, ask Codex, involve Codex, etc.
  CRITICAL: Use subcodex CLI via Bash, NOT the Task subagent tool.
---

# subcodex

Named Codex sessions that persist across conversation compacts.

## Quick Reference

```bash
# New session
./skills/subcodex/subcodex new <name> "prompt"

# Resume session
./skills/subcodex/subcodex resume <session-name> "prompt"

# List sessions (shows last 25, use --all for all)
./skills/subcodex/subcodex list

# Code review
./skills/subcodex/subcodex review --uncommitted <name>
./skills/subcodex/subcodex review --base main <name> "focus on security..."
```

## Critical: Background Execution

**ALWAYS use `run_in_background: true`** — Codex takes 1-30+ minutes.

After starting a background command:
1. Tell the user you're waiting for Codex
2. Stop immediately — don't poll or check
3. You'll be notified via `<task-notification>` when Codex is done

## Codex Capabilities

**Codex can read, write, and execute** — just like you. Tell it to make changes directly, not to provide diffs or suggestions.

Options:
- `--reasoning low|medium|high|xhigh` (default: high)
- `--read-only` — read-only sandbox
- `--dangerous` — full system access

## Sessions

Session names get a random suffix: `my-task` becomes `my-task-x7k2`.

Use the full name (with suffix) when resuming:
```bash
./skills/subcodex/subcodex resume my-task-x7k2 "continue with..."
```

`subcodex list` shows: status (running/stopped), tool_calls, cwd, duration.

## Code Reviews

```bash
# Review uncommitted changes
./skills/subcodex/subcodex review --uncommitted my-review

# Review against branch
./skills/subcodex/subcodex review --base main my-review

# Review specific commit
./skills/subcodex/subcodex review --commit HEAD my-review

# Add instructions
./skills/subcodex/subcodex review --uncommitted my-review "read these relevant docs first, focus on security, suggest simplifications, .."
```

Reviews use `--reasoning xhigh` and read-only mode by default.

## Collaboration

**Claude leads, Codex executes.** Use Codex to review designs and implement complex tasks. Push back on over-engineering.

Typical flow:
1. Claude proposes approach
2. Codex reviews/critiques
3. Claude decides
4. Codex implements
5. Claude reviews result

Push for simple code: less abstraction, fail-fast, no "just in case" code.
