"""Freshservice MCP — Form field discovery with TTL cache.

Provides a tool that dynamically reads the form-field templates from the
Freshservice organisation (ticket fields, change fields, agent fields,
requester fields, asset types …) and caches them locally so we don't
hammer the API on every invocation.
"""
import time
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from .http_client import api_get, handle_error

# ---------------------------------------------------------------------------
# Cache configuration
# ---------------------------------------------------------------------------
_CACHE_DIR = Path(os.getenv("FRESHSERVICE_CACHE_DIR", Path.home() / ".cache" / "freshservice_mcp"))
_CACHE_TTL = int(os.getenv("FRESHSERVICE_CACHE_TTL", 3600))  # seconds – default 1 h

# In-memory + on-disk two-level cache
_mem_cache: Dict[str, Dict[str, Any]] = {}


def _cache_path(key: str) -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / f"{key}.json"


def _read_cache(key: str) -> Optional[Dict[str, Any]]:
    """Return cached data if still valid, else None."""
    # 1) in-memory
    if key in _mem_cache:
        entry = _mem_cache[key]
        if time.time() - entry["ts"] < _CACHE_TTL:
            return entry["data"]
        del _mem_cache[key]

    # 2) on-disk
    p = _cache_path(key)
    if p.exists():
        try:
            raw = json.loads(p.read_text())
            if time.time() - raw["ts"] < _CACHE_TTL:
                _mem_cache[key] = raw  # promote to memory
                return raw["data"]
        except (json.JSONDecodeError, KeyError):
            pass
    return None


def _write_cache(key: str, data: Any) -> None:
    entry = {"ts": time.time(), "data": data}
    _mem_cache[key] = entry
    try:
        p = _cache_path(key)
        p.write_text(json.dumps(entry, default=str))
    except OSError:
        pass  # non-fatal — memory cache still works


def invalidate_cache(key: Optional[str] = None) -> None:
    """Clear cache for *key*, or all caches if key is None."""
    global _mem_cache
    if key is None:
        _mem_cache.clear()
        if _CACHE_DIR.exists():
            for f in _CACHE_DIR.glob("*.json"):
                f.unlink(missing_ok=True)
    else:
        _mem_cache.pop(key, None)
        _cache_path(key).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Entity → API path mapping
# ---------------------------------------------------------------------------
_FIELD_ENDPOINTS: Dict[str, str] = {
    "ticket": "ticket_form_fields",
    "change": "change_form_fields",
    "agent": "agent_fields",
    "requester": "requester_fields",
}


async def _fetch_fields(entity_type: str) -> Dict[str, Any]:
    """Fetch the form-field definitions from Freshservice API."""
    endpoint = _FIELD_ENDPOINTS.get(entity_type)
    if not endpoint:
        return {"error": f"Unknown entity type '{entity_type}'. Valid types: {list(_FIELD_ENDPOINTS.keys())}"}

    cache_key = f"fields_{entity_type}"
    cached = _read_cache(cache_key)
    if cached is not None:
        return {"source": "cache", "fields": cached}

    try:
        resp = await api_get(endpoint)
        resp.raise_for_status()
        data = resp.json()
        _write_cache(cache_key, data)
        return {"source": "api", "fields": data}
    except Exception as e:
        return handle_error(e, f"fetch {entity_type} fields")


async def _fetch_asset_types() -> Dict[str, Any]:
    """Fetch all asset types (paginated) and cache them."""
    cache_key = "asset_types"
    cached = _read_cache(cache_key)
    if cached is not None:
        return {"source": "cache", "asset_types": cached}

    all_types = []
    page = 1
    try:
        while True:
            resp = await api_get("asset_types", params={"page": page, "per_page": 100})
            resp.raise_for_status()
            data = resp.json()
            types = data.get("asset_types", [])
            if not types:
                break
            all_types.extend(types)
            page += 1
    except Exception as e:
        return handle_error(e, "fetch asset types")

    _write_cache(cache_key, all_types)
    return {"source": "api", "asset_types": all_types}


# ---------------------------------------------------------------------------
# Tool registration (called from server.py)
# ---------------------------------------------------------------------------
def register_discovery_tools(mcp) -> None:
    """Register discovery-related tools on the MCP server."""

    @mcp.tool()
    async def discover_form_fields(
        entity_type: str,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """Discover the form-field definitions for an entity type in your Freshservice organisation.

        Returns the list of fields (name, label, type, required, choices…) that
        your org has configured.  Results are cached locally for 1 hour.

        Args:
            entity_type: One of 'ticket', 'change', 'agent', 'requester', 'asset_type'
            force_refresh: Set to true to bypass the cache and re-fetch from Freshservice
        """
        if force_refresh:
            invalidate_cache(f"fields_{entity_type}" if entity_type != "asset_type" else "asset_types")

        if entity_type == "asset_type":
            return await _fetch_asset_types()
        return await _fetch_fields(entity_type)

    @mcp.tool()
    async def clear_field_cache(entity_type: Optional[str] = None) -> Dict[str, Any]:
        """Clear the cached form-field definitions.

        Args:
            entity_type: Specific entity to clear ('ticket', 'change', …) or omit to clear all.
        """
        if entity_type:
            key = f"fields_{entity_type}" if entity_type != "asset_type" else "asset_types"
            invalidate_cache(key)
            return {"success": True, "message": f"Cache cleared for '{entity_type}'"}
        invalidate_cache()
        return {"success": True, "message": "All field caches cleared"}
