"""Stealth Browser Server - FastAPI server with nodriver for anti-bot browser automation."""

import asyncio
import atexit
import os
import signal
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

import nodriver as uc
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn


# === Request/Response Models ===

class PageRequest(BaseModel):
    name: str

class GotoRequest(BaseModel):
    url: str

class ClickRequest(BaseModel):
    selector: str

class FillRequest(BaseModel):
    selector: str
    text: str

class EvaluateRequest(BaseModel):
    script: str

class ScreenshotRequest(BaseModel):
    path: str
    full_page: bool = False

class WaitRequest(BaseModel):
    selector: str
    timeout: int = 30000

class WaitLoadRequest(BaseModel):
    timeout: int = 30000  # ms

class RefActionRequest(BaseModel):
    action: str  # "click" or "fill"
    text: Optional[str] = None


# === Browser Manager ===

class BrowserManager:
    """Manages a single browser instance with multiple named pages (tabs)."""

    def __init__(self, profile_dir: str, headless: bool = False):
        self.profile_dir = profile_dir
        self.headless = headless
        self.browser: Optional[uc.Browser] = None
        self.pages: Dict[str, uc.Tab] = {}
        self._browser_pid: Optional[int] = None

    async def start(self):
        """Start the browser."""
        print(f"Starting browser (headless={self.headless})...")
        print(f"Profile directory: {self.profile_dir}")

        self.browser = await uc.start(
            user_data_dir=self.profile_dir,
            headless=self.headless,
        )

        # Track the browser process PID for cleanup
        if hasattr(self.browser, '_process') and self.browser._process:
            self._browser_pid = self.browser._process.pid
            print(f"Browser started (PID: {self._browser_pid})")
        else:
            print("Browser started successfully")

    async def get_or_create_page(self, name: str) -> uc.Tab:
        """Get existing page by name or create a new one."""
        if name in self.pages:
            return self.pages[name]

        # Create new tab
        tab = await self.browser.get("about:blank", new_tab=True)
        self.pages[name] = tab
        print(f"Created new page: {name}")
        return tab

    def get_page(self, name: str) -> Optional[uc.Tab]:
        """Get page by name, returns None if not found."""
        return self.pages.get(name)

    async def close_page(self, name: str) -> bool:
        """Close a page by name."""
        if name not in self.pages:
            return False

        tab = self.pages[name]
        try:
            await tab.close()
        except Exception:
            pass  # Tab might already be closed

        del self.pages[name]
        print(f"Closed page: {name}")
        return True

    def list_pages(self) -> list:
        """List all page names."""
        return list(self.pages.keys())

    async def shutdown(self):
        """Shutdown the browser and all pages."""
        print("Shutting down browser...")

        # Close all pages
        for name in list(self.pages.keys()):
            await self.close_page(name)

        # Stop browser
        if self.browser:
            try:
                self.browser.stop()
            except Exception:
                pass

        # Force kill browser process if still running
        if self._browser_pid:
            try:
                os.kill(self._browser_pid, signal.SIGTERM)
                print(f"Sent SIGTERM to browser (PID: {self._browser_pid})")
            except ProcessLookupError:
                pass  # Already dead
            except Exception as e:
                print(f"Failed to kill browser: {e}")

        print("Browser shutdown complete")


# === Global State ===

manager: Optional[BrowserManager] = None
_browser_pid_for_cleanup: Optional[int] = None


def _cleanup_browser_on_exit():
    """Backup cleanup in case normal shutdown doesn't happen."""
    if _browser_pid_for_cleanup:
        try:
            os.kill(_browser_pid_for_cleanup, signal.SIGTERM)
        except:
            pass


# Register atexit handler
atexit.register(_cleanup_browser_on_exit)


# === Lifespan ===

# Store the port globally so lifespan can access it
_server_port = 6222


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage browser lifecycle with FastAPI."""
    global manager, _browser_pid_for_cleanup

    # Get config from environment
    script_dir = Path(__file__).parent
    # Use port-specific profile directory for isolation
    profile_dir = str(script_dir / "profiles" / f"browser-data-{_server_port}")
    headless = os.environ.get("HEADLESS", "false").lower() == "true"

    # Create profile directory
    Path(profile_dir).mkdir(parents=True, exist_ok=True)

    # Start browser
    manager = BrowserManager(profile_dir=profile_dir, headless=headless)
    await manager.start()

    # Store PID for backup cleanup (atexit handler)
    _browser_pid_for_cleanup = manager._browser_pid

    print(f"\nReady on port {_server_port}")
    print("Press Ctrl+C to stop\n")

    yield

    # Shutdown
    if manager:
        await manager.shutdown()


# === FastAPI App ===

app = FastAPI(title="Stealth Browser", lifespan=lifespan)


# === Helper Functions ===

def get_tab(name: str) -> uc.Tab:
    """Get tab by name, raise 404 if not found."""
    tab = manager.get_page(name)
    if not tab:
        raise HTTPException(status_code=404, detail=f"Page '{name}' not found")
    return tab


async def wait_for_page_load(tab: uc.Tab, timeout: int = 30):
    """Wait for page to finish loading."""
    try:
        for _ in range(timeout * 10):  # Check every 100ms
            ready_state = await tab.evaluate("document.readyState")
            if ready_state == "complete":
                return
            await asyncio.sleep(0.1)
    except Exception:
        pass  # Best effort


# === Endpoints: Server Info ===

@app.get("/")
async def root():
    """Server status."""
    return {"status": "ready"}


# === Endpoints: Page Registry ===

@app.get("/pages")
async def list_pages():
    """List all named pages."""
    return {"pages": manager.list_pages()}


@app.post("/pages")
async def get_or_create_page(request: PageRequest):
    """Get or create a named page."""
    name = request.name

    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if len(name) > 256:
        raise HTTPException(status_code=400, detail="name too long (max 256)")

    created = name not in manager.pages
    await manager.get_or_create_page(name)

    return {"name": name, "created": created}


@app.delete("/pages/{name}")
async def close_page(name: str):
    """Close a named page."""
    success = await manager.close_page(name)
    if not success:
        raise HTTPException(status_code=404, detail=f"Page '{name}' not found")
    return {"success": True}


# === Endpoints: Page State ===

@app.get("/pages/{name}/url")
async def get_url(name: str):
    """Get current URL of a page."""
    tab = get_tab(name)
    return {"url": tab.url or ""}


@app.get("/pages/{name}/title")
async def get_title(name: str):
    """Get current title of a page."""
    tab = get_tab(name)
    try:
        title = await tab.evaluate("document.title")
        return {"title": title or ""}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Endpoints: Page Operations ===

@app.post("/pages/{name}/goto")
async def goto(name: str, request: GotoRequest):
    """Navigate to a URL."""
    tab = get_tab(name)

    try:
        await tab.get(request.url)
        await wait_for_page_load(tab)
        title = await tab.evaluate("document.title")
        return {"url": tab.url, "title": title}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pages/{name}/click")
async def click(name: str, request: ClickRequest):
    """Click an element by CSS selector."""
    tab = get_tab(name)

    try:
        element = await tab.select(request.selector)
        if not element:
            raise HTTPException(status_code=404, detail=f"Element not found: {request.selector}")
        await element.click()
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pages/{name}/fill")
async def fill(name: str, request: FillRequest):
    """Fill an input element with text."""
    tab = get_tab(name)

    try:
        element = await tab.select(request.selector)
        if not element:
            raise HTTPException(status_code=404, detail=f"Element not found: {request.selector}")
        await element.clear_input()
        await element.send_keys(request.text)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pages/{name}/evaluate")
async def evaluate(name: str, request: EvaluateRequest):
    """Execute JavaScript and return result."""
    tab = get_tab(name)

    try:
        result = await tab.evaluate(request.script)
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pages/{name}/screenshot")
async def screenshot(name: str, request: ScreenshotRequest):
    """Take a screenshot."""
    tab = get_tab(name)

    # Ensure path is within tmp directory
    script_dir = Path(__file__).parent
    if not request.path.startswith("tmp/"):
        path = script_dir / "tmp" / request.path
    else:
        path = script_dir / request.path

    # Create parent directory if needed
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        await tab.save_screenshot(str(path))
        return {"path": str(path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pages/{name}/wait")
async def wait_for_selector(name: str, request: WaitRequest):
    """Wait for an element to appear."""
    tab = get_tab(name)
    timeout_sec = request.timeout / 1000

    try:
        for _ in range(int(timeout_sec * 10)):
            element = await tab.select(request.selector)
            if element:
                return {"success": True}
            await asyncio.sleep(0.1)

        raise HTTPException(status_code=408, detail=f"Timeout waiting for: {request.selector}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pages/{name}/wait-load")
async def wait_for_page_load_endpoint(name: str, request: WaitLoadRequest):
    """Wait for page to finish loading (document.readyState == 'complete')."""
    tab = get_tab(name)
    timeout_sec = request.timeout / 1000

    try:
        ready_state = None
        for _ in range(int(timeout_sec * 10)):  # Poll every 100ms
            result = await tab.evaluate("document.readyState")
            # Handle CDP-wrapped value from nodriver
            if isinstance(result, dict) and 'value' in result:
                ready_state = result['value']
            else:
                ready_state = result

            if ready_state == "complete":
                return {"success": True, "readyState": "complete"}
            await asyncio.sleep(0.1)

        return {"success": False, "readyState": ready_state, "timedOut": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Endpoints: Snapshot ===

@app.get("/pages/{name}/snapshot")
async def get_snapshot(name: str):
    """Get ARIA accessibility snapshot of the page."""
    tab = get_tab(name)

    try:
        # Import snapshot script (will be implemented later)
        from snapshot import get_ai_snapshot
        yaml_str = await get_ai_snapshot(tab)
        return {"yaml": yaml_str}
    except ImportError:
        raise HTTPException(status_code=501, detail="Snapshot not yet implemented")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pages/{name}/ref/{ref}")
async def interact_with_ref(name: str, ref: str, request: RefActionRequest):
    """Interact with an element by its snapshot ref."""
    tab = get_tab(name)

    try:
        from snapshot import select_snapshot_ref
        element = await select_snapshot_ref(tab, ref)

        if not element:
            raise HTTPException(status_code=404, detail=f"Ref not found: {ref}")

        if request.action == "click":
            await element.click()
        elif request.action == "fill":
            if not request.text:
                raise HTTPException(status_code=400, detail="text required for fill action")
            await element.clear_input()
            await element.send_keys(request.text)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")

        return {"success": True}
    except ImportError:
        raise HTTPException(status_code=501, detail="Snapshot not yet implemented")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Main ===

if __name__ == "__main__":
    # Get port from environment (set by server.sh)
    port_str = os.environ.get("PORT", "")
    if not port_str:
        print("Error: PORT environment variable not set. Use server.sh to start.")
        sys.exit(1)

    port = int(port_str)

    # Set module-level port so lifespan can use it for profile directory
    _server_port = port

    # Print port in a clear, parseable format
    print(f"STEALTH_BROWSER_PORT={port}")
    sys.stdout.flush()

    uvicorn.run(app, host="127.0.0.1", port=port)
