---
name: subcodex
description: |
  Collaborate with Codex (GPT-5.2) via named sessions. Trigger: user asks to work with Codex, use Codex, ask Codex, involve Codex, etc.
  CRITICAL: Use subcodex CLI via Bash, NOT the Task subagent tool.
---

# subcodex

Named Codex sessions that persist across conversation compacts.

## Codex Capabilities

**Regular sessions** (default `--full-auto`):
- Runs in **same working directory** as Claude Code
- Can **read** any file on the system
- Can **write** files in the workspace (current project)
- Can **execute** shell commands (git, npm, cargo, etc.)

**Review sessions** (`subcodex review`):
- Read-only - can only read files, cannot write or execute commands

**Dangerous mode** (`--dangerous`):
- Full system access, no sandbox restrictions

## CRITICAL: Execution Rules

1. **NEVER run in background** - run synchronously and wait
2. **High timeout** - at least 600000ms (10 min), ideally 1200000ms (20 min)
3. **Be patient** - Codex can take 5-30+ minutes. Just wait for completion.
4. **One call per session at a time** - can run different sessions in parallel, but same session is sequential
5. **Requires jq** - if you get a `jq: command not found` error, install it (`brew install jq` or `apt install jq`)

## Usage

```bash
# New session - creates "my-task-x7k2" and runs prompt with Codex
./skills/subcodex/subcodex new my-task <<'EOF'
Your prompt here.
EOF

# Resume session - continues existing session with new prompt
./skills/subcodex/subcodex resume my-task-x7k2 <<'EOF'
Follow-up prompt.
EOF

# List sessions
./skills/subcodex/subcodex list

# Import existing Codex session (user provides UUID)
./skills/subcodex/subcodex import --name <name> --uuid <codex-uuid>
```

Both `new` and `resume` are long-running commands that send the prompt to Codex and wait for completion. Use the full session name from output (e.g., `my-task-x7k2`) when resuming.

## Code Reviews

```bash
# Review uncommitted changes
./skills/subcodex/subcodex review --uncommitted my-review

# Review against base branch
./skills/subcodex/subcodex review --base main my-feature-review

# Review specific commit
./skills/subcodex/subcodex review --commit HEAD my-commit-review

# Custom review prompt
./skills/subcodex/subcodex review my-security-review <<'EOF'
Check src/auth.rs for security issues.
EOF

# With options
./skills/subcodex/subcodex review --base main --title "Feature X" my-review
```

Reviews use `xhigh` reasoning by default. Resume works the same as regular sessions.

## Options

Options go after the subcommand:

```bash
./skills/subcodex/subcodex new --reasoning high my-task <<'EOF'
Your prompt here.
EOF

./skills/subcodex/subcodex new --read-only my-task "Review this code"
./skills/subcodex/subcodex new --dangerous my-task "Run system commands"
```

Available options:
- `--reasoning`: low, medium, high, xhigh
- `--model`: gpt-5.2 (default), gpt-5.2-codex, gpt-5.1-codex-max, gpt-5-codex-mini
- `--read-only`: Read-only sandbox
- `--dangerous`: Full system access

Config: `~/.subcodex/config.json` (created on first run)
Conversations: `~/.subcodex/conversations/<name>.txt`

## Working with Codex

**Claude is in charge** - you have taste, Codex tends to over-engineer.

Push for:
- Simple, elegant, maintainable code
- Less code - use existing functions, simpler approaches
- Fail-fast over fallbacks
- No shortcuts, no "just in case" code, no premature abstractions

## Collaboration Flow

1. **Claude proposes** approach
2. **Codex reviews** - may suggest improvements
3. **Claude decides** direction
4. **Codex implements**
5. **Claude reviews** - course-correct via follow-up
