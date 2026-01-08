"""Stealth Browser Client - HTTP client for interacting with the stealth-browser server."""

from typing import Any, List, Optional
import httpx


def connect(server_url: str = None, port: int = None) -> "StealthBrowserClient":
    """Connect to the stealth-browser server.

    Args:
        server_url: Full URL like "http://localhost:6222"
        port: Just the port number (convenience, constructs URL automatically)

    If neither provided, defaults to port 6222.
    """
    if server_url is None:
        port = port or 6222
        server_url = f"http://localhost:{port}"
    return StealthBrowserClient(server_url)


class StealthBrowserClient:
    """Client for interacting with the stealth-browser server."""

    def __init__(self, server_url: str):
        self.server_url = server_url.rstrip("/")
        self._client = httpx.Client(timeout=60.0)

    def page(self, name: str) -> "PageProxy":
        """Get or create a named page."""
        resp = self._client.post(f"{self.server_url}/pages", json={"name": name})
        resp.raise_for_status()
        return PageProxy(self._client, self.server_url, name)

    def list(self) -> List[str]:
        """List all page names."""
        resp = self._client.get(f"{self.server_url}/pages")
        resp.raise_for_status()
        return resp.json()["pages"]

    def close(self, name: str) -> bool:
        """Close a named page."""
        resp = self._client.delete(f"{self.server_url}/pages/{name}")
        if resp.status_code == 404:
            return False
        resp.raise_for_status()
        return resp.json().get("success", False)

    def disconnect(self):
        """Disconnect from the server (close HTTP client)."""
        self._client.close()

    def get_ai_snapshot(self, name: str) -> str:
        """Get ARIA accessibility snapshot of a page."""
        resp = self._client.get(f"{self.server_url}/pages/{name}/snapshot")
        resp.raise_for_status()
        return resp.json()["yaml"]

    def select_snapshot_ref(self, name: str, ref: str) -> "RefProxy":
        """Get a proxy for interacting with an element by its snapshot ref."""
        return RefProxy(self._client, self.server_url, name, ref)


class PageProxy:
    """Proxy for interacting with a named page via HTTP."""

    def __init__(self, client: httpx.Client, server_url: str, name: str):
        self._client = client
        self._server_url = server_url
        self._name = name
        self._base = f"{server_url}/pages/{name}"

    def goto(self, url: str) -> dict:
        """Navigate to a URL."""
        resp = self._client.post(f"{self._base}/goto", json={"url": url})
        resp.raise_for_status()
        return resp.json()

    def click(self, selector: str) -> dict:
        """Click an element by CSS selector."""
        resp = self._client.post(f"{self._base}/click", json={"selector": selector})
        resp.raise_for_status()
        return resp.json()

    def fill(self, selector: str, text: str) -> dict:
        """Fill an input element with text."""
        resp = self._client.post(f"{self._base}/fill", json={"selector": selector, "text": text})
        resp.raise_for_status()
        return resp.json()

    def _unwrap_cdp_value(self, val: Any) -> Any:
        """Recursively unwrap CDP-style values from nodriver.

        nodriver returns values in several formats:
        - Primitives: {'type': 'string', 'value': 'x'}
        - Objects: [['key', {'type': 'string', 'value': 'v'}], ...]
        - Arrays: [{'type': 'number', 'value': 1}, ...]

        This extracts the actual values for a cleaner API.
        """
        if val is None:
            return None
        if isinstance(val, dict):
            # CDP wrapped primitive: {'type': 'string', 'value': 'x'}
            if 'type' in val and 'value' in val and len(val) == 2:
                return self._unwrap_cdp_value(val['value'])
            # Regular dict - unwrap values recursively
            return {k: self._unwrap_cdp_value(v) for k, v in val.items()}
        if isinstance(val, list):
            # Check if this is a nodriver object representation: [['key', value], ...]
            if val and all(
                isinstance(item, list) and len(item) == 2 and isinstance(item[0], str)
                for item in val
            ):
                # Convert to dict
                return {k: self._unwrap_cdp_value(v) for k, v in val}
            # Regular array - unwrap items recursively
            return [self._unwrap_cdp_value(item) for item in val]
        return val

    def evaluate(self, script: str) -> Any:
        """Execute JavaScript and return result."""
        resp = self._client.post(f"{self._base}/evaluate", json={"script": script})
        resp.raise_for_status()
        result = resp.json().get("result")
        return self._unwrap_cdp_value(result)

    def screenshot(self, path: str, full_page: bool = False) -> str:
        """Take a screenshot and save to path."""
        resp = self._client.post(f"{self._base}/screenshot", json={"path": path, "full_page": full_page})
        resp.raise_for_status()
        return resp.json()["path"]

    def wait_for_selector(self, selector: str, timeout: int = 30000) -> dict:
        """Wait for an element to appear."""
        resp = self._client.post(f"{self._base}/wait", json={"selector": selector, "timeout": timeout})
        resp.raise_for_status()
        return resp.json()

    @property
    def url(self) -> str:
        """Get current URL."""
        resp = self._client.get(f"{self._base}/url")
        resp.raise_for_status()
        return resp.json()["url"]

    def title(self) -> str:
        """Get current page title."""
        resp = self._client.get(f"{self._base}/title")
        resp.raise_for_status()
        return resp.json()["title"]

    def wait_for_load(self, timeout: int = 30000) -> bool:
        """Wait for page to finish loading (document.readyState == 'complete').

        Args:
            timeout: Maximum wait time in milliseconds (default 30000)

        Returns:
            True if page loaded, False if timeout
        """
        resp = self._client.post(f"{self._base}/wait-load", json={"timeout": timeout})
        resp.raise_for_status()
        return resp.json().get("success", False)


class RefProxy:
    """Proxy for interacting with an element by its snapshot ref."""

    def __init__(self, client: httpx.Client, server_url: str, page_name: str, ref: str):
        self._client = client
        self._base = f"{server_url}/pages/{page_name}/ref/{ref}"

    def click(self) -> dict:
        """Click the element."""
        resp = self._client.post(self._base, json={"action": "click"})
        resp.raise_for_status()
        return resp.json()

    def fill(self, text: str) -> dict:
        """Fill the element with text."""
        resp = self._client.post(self._base, json={"action": "fill", "text": text})
        resp.raise_for_status()
        return resp.json()
