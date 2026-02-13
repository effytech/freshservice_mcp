"""Freshservice MCP — Shared HTTP client utilities."""
import re
import base64
import httpx
from typing import Optional, Dict, Any

from .config import FRESHSERVICE_DOMAIN, FRESHSERVICE_APIKEY


def get_auth_headers() -> Dict[str, str]:
    """Return Basic-auth + JSON content-type headers."""
    return {
        "Authorization": f"Basic {base64.b64encode(f'{FRESHSERVICE_APIKEY}:X'.encode()).decode()}",
        "Content-Type": "application/json",
    }


def parse_link_header(link_header: str) -> Dict[str, Optional[int]]:
    """Parse the HTTP Link header to extract pagination page numbers."""
    pagination: Dict[str, Optional[int]] = {"next": None, "prev": None}
    if not link_header:
        return pagination
    for link in link_header.split(","):
        match = re.search(r'<(.+?)>;\s*rel="(.+?)"', link)
        if match:
            url, rel = match.groups()
            page_match = re.search(r"page=(\d+)", url)
            if page_match:
                pagination[rel] = int(page_match.group(1))
    return pagination


def api_url(path: str) -> str:
    """Build a full Freshservice API v2 URL."""
    return f"https://{FRESHSERVICE_DOMAIN}/api/v2/{path.lstrip('/')}"


async def api_get(path: str, params: Optional[Dict[str, Any]] = None) -> httpx.Response:
    """Perform an authenticated GET request."""
    async with httpx.AsyncClient() as client:
        return await client.get(api_url(path), headers=get_auth_headers(), params=params)


async def api_post(path: str, json: Optional[Dict[str, Any]] = None) -> httpx.Response:
    """Perform an authenticated POST request."""
    async with httpx.AsyncClient() as client:
        return await client.post(api_url(path), headers=get_auth_headers(), json=json)


async def api_put(path: str, json: Optional[Dict[str, Any]] = None) -> httpx.Response:
    """Perform an authenticated PUT request."""
    async with httpx.AsyncClient() as client:
        return await client.put(api_url(path), headers=get_auth_headers(), json=json)


async def api_delete(path: str) -> httpx.Response:
    """Perform an authenticated DELETE request."""
    async with httpx.AsyncClient() as client:
        return await client.delete(api_url(path), headers=get_auth_headers())


def handle_error(e: Exception, action: str = "request") -> Dict[str, Any]:
    """Standardised error response builder."""
    if isinstance(e, httpx.HTTPStatusError):
        try:
            details = e.response.json()
        except Exception:
            details = e.response.text
        return {"success": False, "error": f"Failed to {action}: {e}", "details": details}
    return {"success": False, "error": f"Unexpected error during {action}: {e}"}
