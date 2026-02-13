"""Freshservice MCP — Canned Responses & Workspaces tools (consolidated).

Exposes 2 tools instead of the original 6:
  • manage_canned_response — list + get (responses & folders)
  • manage_workspace       — list + get
"""
from typing import Any, Dict, Optional

from ..http_client import api_get, handle_error


def register_misc_tools(mcp) -> None:
    """Register canned response and workspace tools on *mcp*."""

    # ------------------------------------------------------------------ #
    #  manage_canned_response                                             #
    # ------------------------------------------------------------------ #
    @mcp.tool()
    async def manage_canned_response(
        action: str,
        response_id: Optional[int] = None,
        folder_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Manage canned responses.

        Args:
            action: 'list', 'get', 'list_folders', 'get_folder'
            response_id: Required for get
            folder_id: Required for get_folder
        """
        action = action.lower().strip()

        if action == "list":
            try:
                resp = await api_get("canned_responses")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "list canned responses")

        if action == "get":
            if not response_id:
                return {"error": "response_id required for get"}
            try:
                resp = await api_get(f"canned_responses/{response_id}")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "get canned response")

        if action == "list_folders":
            try:
                resp = await api_get("canned_response_folders")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "list canned response folders")

        if action == "get_folder":
            if not folder_id:
                return {"error": "folder_id required for get_folder"}
            try:
                resp = await api_get(f"canned_response_folders/{folder_id}")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "get canned response folder")

        return {"error": f"Unknown action '{action}'. Valid: list, get, list_folders, get_folder"}

    # ------------------------------------------------------------------ #
    #  manage_workspace                                                   #
    # ------------------------------------------------------------------ #
    @mcp.tool()
    async def manage_workspace(
        action: str,
        workspace_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Manage workspaces.

        Args:
            action: 'list', 'get'
            workspace_id: Required for get
        """
        action = action.lower().strip()

        if action == "list":
            try:
                resp = await api_get("workspaces")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "list workspaces")

        if action == "get":
            if not workspace_id:
                return {"error": "workspace_id required for get"}
            try:
                resp = await api_get(f"workspaces/{workspace_id}")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "get workspace")

        return {"error": f"Unknown action '{action}'. Valid: list, get"}
