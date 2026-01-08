---
name: stealth-browser
description: Stealth browser automation with anti-bot bypass and persistent page state. Use when users need to navigate Cloudflare-protected sites, fill forms, take screenshots, extract web data, or automate browser workflows on sites that block regular automation. Trigger phrases include "go to [url]", "click on", "fill out the form", "take a screenshot", "scrape", "automate", "bypass cloudflare", or any browser interaction request on protected sites.
---

# Stealth Browser Skill

Browser automation using nodriver for anti-bot/Cloudflare bypass. Maintains page state across script executions. Write small, focused scripts to accomplish tasks incrementally.

**Key difference from dev-browser**: Uses nodriver instead of Playwright, which bypasses most anti-bot detection including Cloudflare Turnstile.

## Choosing Your Approach

- **Local/source-available sites**: Read the source code first to write selectors directly
- **Unknown page layouts**: Use `get_ai_snapshot()` to discover elements and `select_snapshot_ref()` to interact with them
- **Visual feedback**: Take screenshots to see what the user sees

## Setup

**Important: Each session needs its own server. Do not reuse servers started by other sessions.**

Start your server:

```bash
./skills/stealth-browser/server.sh &
```

- Default port is 6222. If in use, the script will tell you which port to use instead.
- Add `--headless` flag if user requests headless mode.
- **Wait for the `Ready on port XXXX` message before running scripts.**
- **Remember the port number** - you'll need it for `connect(port=XXXX)`.

If you see "Port 6222 is in use", that's another session's server. Start your own on the suggested port:

```bash
./skills/stealth-browser/server.sh --port 6223 &
```

## Writing Scripts

Execute scripts inline using heredocs. **Use the port from your server startup:**

```bash
cd skills/stealth-browser && source venv/bin/activate && python <<'EOF'
from client import connect

client = connect(port=6222)  # Use YOUR server's port!
page = client.page("example")  # descriptive name like "cnn-homepage"

page.goto("https://example.com")

print(f"Title: {page.title()}")
print(f"URL: {page.url}")

client.disconnect()
EOF
```

**Write to `tmp/` files only when** the script needs reuse, is complex, or user explicitly requests it.

### Key Principles

1. **Small scripts**: Each script does ONE thing (navigate, click, fill, check)
2. **Evaluate state**: Print state at the end to decide next steps
3. **Descriptive page names**: Use `"checkout"`, `"login"`, not `"main"`
4. **Disconnect to exit**: `client.disconnect()` - pages persist on server
5. **Plain JS in evaluate**: `page.evaluate()` runs in browser - use JavaScript syntax

## Workflow Loop

Follow this pattern for complex tasks:

1. **Write a script** to perform one action
2. **Run it** and observe the output
3. **Evaluate** - did it work? What's the current state?
4. **Decide** - is the task complete or do we need another script?
5. **Repeat** until task is done

## Client API

```python
from client import connect

client = connect(port=6222)                 # Connect to YOUR server's port!
page = client.page("name")                  # Get or create named page
pages = client.list()                       # List all page names
client.close("name")                        # Close a page
client.disconnect()                         # Disconnect (pages persist)

# ARIA Snapshot methods
snapshot = client.get_ai_snapshot("name")   # Get accessibility tree (YAML)
ref = client.select_snapshot_ref("name", "e5")  # Get element proxy by ref
ref.click()                                 # Click the ref
ref.fill("text")                            # Fill the ref with text
```

## Page Operations

```python
client = connect(port=6222)  # Your server's port
page = client.page("mypage")

# Navigation
page.goto("https://example.com")

# Get state
url = page.url                    # Current URL (property)
title = page.title()              # Page title

# Interaction
page.click("button.submit")       # Click by CSS selector
page.fill("input[name=q]", "search term")  # Fill input

# JavaScript
result = page.evaluate("document.title")   # Run JS, get result

# Screenshots
page.screenshot("screenshot.png")          # Saves to tmp/ directory

# Waiting
page.wait_for_selector(".results")         # Wait for element
```

## Inspecting Page State

### Screenshots

```python
page.screenshot("screenshot.png")      # Saves to tmp/screenshot.png
page.screenshot("tmp/full.png")        # Explicit path
```

### ARIA Snapshot (Element Discovery)

Use `get_ai_snapshot()` to discover page elements. Returns YAML-formatted accessibility tree:

```yaml
- banner:
  - link "Hacker News" [ref=e1]
  - navigation:
    - link "new" [ref=e2]
- main:
  - list:
    - listitem:
      - link "Article Title" [ref=e8]
      - link "328 comments" [ref=e9]
- contentinfo:
  - textbox [ref=e10]
    - /placeholder: "Search"
```

**Interpreting refs:**

- `[ref=eN]` - Element reference for interaction (visible, clickable elements only)
- `[checked]`, `[disabled]`, `[expanded]` - Element states
- `[level=N]` - Heading level
- `/url:`, `/placeholder:` - Element properties

**Interacting with refs:**

```python
snapshot = client.get_ai_snapshot("hackernews")
print(snapshot)  # Find the ref you need

element = client.select_snapshot_ref("hackernews", "e2")
element.click()
```

## Error Recovery

Page state persists after failures. Debug with:

```bash
cd skills/stealth-browser && source venv/bin/activate && python <<'EOF'
from client import connect

client = connect(port=6222)  # Your server's port
page = client.page("debug")

page.screenshot("debug.png")
print(f"URL: {page.url}")
print(f"Title: {page.title()}")
print(f"Body: {page.evaluate('document.body.innerText.substring(0, 200)')}")

client.disconnect()
EOF
```

## Cloudflare Bypass

This skill uses nodriver which has built-in stealth patches. Sites protected by Cloudflare (like lowendtalk.com) work automatically:

```python
page.goto("https://lowendtalk.com/")
# No Cloudflare challenge - loads directly!
print(page.title())  # "LowEndTalk" (not "Just a moment...")
```

## Differences from dev-browser

| Aspect | dev-browser | stealth-browser |
|--------|-------------|-----------------|
| Language | TypeScript | Python |
| Browser lib | Playwright | nodriver (stealth) |
| Anti-bot | None | Built-in bypass |
| Port | 9222 | 6222 |
| Extension mode | Yes | No |
| Script syntax | `npx tsx <<'EOF'` | `python <<'EOF'` |
