---
name: subcodex
description: |
  Collaborate with Codex (GPT-5.2) via named sessions. Trigger: user asks to work with Codex, use Codex, ask Codex, involve Codex, etc.
  CRITICAL: Use subcodex CLI via Bash, NOT the Task subagent tool.
---

# subcodex

Named Codex sessions that persist across conversation compacts.

## Execution

**ALWAYS run in background** — Codex takes 1-30+ minutes. Use `run_in_background: true` and stop immediately. You'll be notified via `<task-notification>` when Codex responds.

```bash
# Start a session (runs in background)
./skills/subcodex/subcodex new my-task <<'EOF'
Your prompt here.
EOF

# Resume a session
./skills/subcodex/subcodex resume my-task-x7k2 <<'EOF'
Follow-up prompt.
EOF

# List sessions
./skills/subcodex/subcodex list
```

After starting a background command, **stop and tell the user you're waiting for Codex**. Don't poll or check — you'll get the response automatically.

## Codex Capabilities

**By default, Codex can read, write, and execute** — just like you. It works in the same directory with full access to edit files and run commands. If you want changes made, tell Codex to make them directly.

| Mode | Read | Write | Execute |
|------|------|-------|---------|
| Regular (default) | Anywhere | Workspace | Yes |
| Review (`subcodex review`) | Anywhere | No | No |
| Dangerous (`--dangerous`) | Anywhere | Anywhere | Yes |

## Options

```bash
./skills/subcodex/subcodex new [options] <name> [prompt]
```

- `--reasoning` — low, medium, high, xhigh
- `--model` — gpt-5.2 (default), gpt-5.2-codex, gpt-5.1-codex-max, gpt-5-codex-mini
- `--read-only` — Read-only sandbox
- `--dangerous` — Full system access

## Code Reviews

```bash
# Target-based reviews
subcodex review --uncommitted my-review
subcodex review --base main my-feature-review
subcodex review --commit HEAD my-commit-review

# Custom review (you specify what to review)
subcodex review my-review "Check src/auth.rs for security issues"

# Combined: target + custom instructions
subcodex review --uncommitted my-review "Focus on error handling"
subcodex review --base main my-review <<'EOF'
Focus on:
- Security vulnerabilities
- Performance issues
EOF
```

Reviews default to `--reasoning xhigh` and read-only mode. Custom prompts can be combined with any target flag.

## Collaboration Philosophy

**Claude leads, Codex executes.** Use Codex to poke holes in your designs and implement hard tasks. Push back on over-engineering.

Push for simple, elegant, maintainable code:
- Less code, fewer abstractions
- Use existing functions
- Fail-fast over fallbacks
- No "just in case" code

Typical flow:
1. Claude proposes approach
2. Codex reviews/suggests
3. Claude decides
4. Codex implements
5. Claude reviews and course-corrects

## Files

- Config: `~/.subcodex/config.json`
- Conversations: `~/.subcodex/conversations/<name>.txt`
