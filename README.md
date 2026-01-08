# claude-skills

Claude Code skills by zippoxer.

## Skills

- **[subcodex](#subcodex)** — Collaborate with Codex (GPT-5.2) via persistent named sessions
- **[stealth-browser](#stealth-browser)** — Browser automation with Cloudflare/anti-bot bypass

## Installation

```bash
/plugin marketplace add zippoxer/claude-skills

# Install subcodex
/plugin install subcodex@zippoxer/claude-skills

# Install stealth-browser
/plugin install stealth-browser@zippoxer/claude-skills
```

Then restart Claude Code.

---

## subcodex

Collaborate with Codex like a subagent. Conversations are named and saved to files, so the agent can trivially pick up later with `subcodex list`.

### Examples

**Coding:**
- "Implement the auth system with Codex"
- "Use the same Codex session to add tests"
- "Keep working on it with Codex until you're both satisfied"

**Reviewing:**
- "Review this PR with Codex"
- "Review that commit with Codex"
- "Review uncommitted changes with Codex on xhigh reasoning"

### How it works

Sessions get human-readable names instead of UUIDs. Conversations are saved as plain text files—just messages, no thinking tokens or clutter—so Claude can read them anytime to catch up.

### Prerequisites

- [Codex CLI](https://github.com/openai/codex) installed and authenticated
- [jq](https://jqlang.github.io/jq/) (`brew install jq` or `apt install jq`)

---

## stealth-browser

Like [dev-browser](https://github.com/SawyerHood/dev-browser) but with anti-bot/Cloudflare bypass. Uses nodriver instead of Playwright.

### What can you do with it?

- "Scrape the forum posts from lowendtalk.com"
- "Get data from this Cloudflare-protected site"
- "This site blocks regular automation, use stealth-browser"

### Prerequisites

Python 3.8+ must be installed. Dependencies are auto-installed on first run.

---

## Manual Installation

```bash
# subcodex
cp -r skills/subcodex ~/.claude/skills/
chmod +x ~/.claude/skills/subcodex/subcodex

# stealth-browser
cp -r skills/stealth-browser ~/.claude/skills/
chmod +x ~/.claude/skills/stealth-browser/server.sh
```

## License

MIT
