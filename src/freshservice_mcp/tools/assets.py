"""Freshservice MCP — Assets tools (consolidated).

Exposes 3 tools instead of the original 22:
  • manage_asset           — CRUD + list + search + filter + delete + restore + move + get_types
  • manage_asset_details   — components, assignment history, requests, contracts
  • manage_asset_relationship — CRUD + list + types + job status
"""
import urllib.parse
from typing import Any, Dict, List, Optional

from ..http_client import (
    api_delete,
    api_get,
    api_post,
    api_put,
    handle_error,
    parse_link_header,
)


def register_assets_tools(mcp) -> None:
    """Register asset-related tools on *mcp*."""

    # ------------------------------------------------------------------ #
    #  manage_asset                                                       #
    # ------------------------------------------------------------------ #
    @mcp.tool()
    async def manage_asset(
        action: str,
        # identifiers
        display_id: Optional[int] = None,
        asset_type_id: Optional[int] = None,
        # create / update fields
        name: Optional[str] = None,
        asset_tag: Optional[str] = None,
        impact: Optional[str] = None,
        usage_type: Optional[str] = None,
        description: Optional[str] = None,
        user_id: Optional[int] = None,
        location_id: Optional[int] = None,
        department_id: Optional[int] = None,
        agent_id: Optional[int] = None,
        group_id: Optional[int] = None,
        assigned_on: Optional[str] = None,
        workspace_id: Optional[int] = None,
        type_fields: Optional[Dict[str, Any]] = None,
        asset_fields: Optional[Dict[str, Any]] = None,
        # search / filter / list
        search_query: Optional[str] = None,
        filter_query: Optional[str] = None,
        include: Optional[str] = None,
        order_by: Optional[str] = None,
        order_type: Optional[str] = None,
        trashed: bool = False,
        page: int = 1,
        per_page: int = 30,
    ) -> Dict[str, Any]:
        """Unified asset operations.

        Args:
            action: One of 'create', 'update', 'delete', 'delete_permanently',
                    'restore', 'get', 'list', 'search', 'filter', 'move',
                    'get_types', 'get_type'
            display_id: Asset display ID (get, update, delete, restore, move, details)
            asset_type_id: Asset type ID (create — MANDATORY, get_type)
            name: Asset name (create — MANDATORY)
            asset_tag: Asset tag (e.g. 'ASSET-9')
            impact: 'low', 'medium', or 'high' (default: 'low')
            usage_type: 'permanent' or 'loaner' (default: 'permanent')
            description: Asset description
            user_id: User ID (Used By)
            location_id: Location ID
            department_id: Department ID
            agent_id: Agent ID (Managed By)
            group_id: Group ID (Managed By Group)
            assigned_on: ISO date when assigned
            workspace_id: Workspace ID (create, list, move)
            type_fields: Asset-type-specific fields dict
            asset_fields: Generic update fields dict (update — alternative to explicit params)
            search_query: Search by name/tag/serial (search)
            filter_query: Filter expression (filter)
            include: Include extra data, e.g. 'type_fields' (list, get)
            order_by: Sort field (list)
            order_type: 'asc' or 'desc' (list)
            trashed: Include trashed assets (list, search)
            page: Page number
            per_page: Items per page
        """
        action = action.lower().strip()

        # ---------- list ----------
        if action == "list":
            params: Dict[str, Any] = {"page": page, "per_page": per_page}
            if include:
                params["include"] = include
            if order_by:
                params["order_by"] = order_by
            if order_type:
                params["order_type"] = order_type
            if trashed:
                params["trashed"] = "true"
            if workspace_id is not None:
                params["workspace_id"] = workspace_id
            try:
                resp = await api_get("assets", params=params)
                resp.raise_for_status()
                pagination_info = parse_link_header(resp.headers.get("Link", ""))
                return {
                    "assets": resp.json(),
                    "pagination": {
                        "current_page": page,
                        "next_page": pagination_info.get("next"),
                        "prev_page": pagination_info.get("prev"),
                        "per_page": per_page,
                    },
                }
            except Exception as e:
                return handle_error(e, "list assets")

        # ---------- get ----------
        if action == "get":
            if not display_id:
                return {"error": "display_id required for get"}
            params = {}
            if include:
                params["include"] = include
            try:
                resp = await api_get(f"assets/{display_id}", params=params or None)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "get asset")

        # ---------- search ----------
        if action == "search":
            if not search_query:
                return {"error": "search_query required for search"}
            encoded = urllib.parse.quote(f'"{search_query}"')
            params = {"page": page}
            if trashed:
                params["trashed"] = "true"
            try:
                resp = await api_get(f"assets?search={encoded}", params=params)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "search assets")

        # ---------- filter ----------
        if action == "filter":
            if not filter_query:
                return {"error": "filter_query required for filter"}
            encoded = urllib.parse.quote(f'"{filter_query}"')
            params: Dict[str, Any] = {"page": page}
            if include:
                params["include"] = include
            try:
                resp = await api_get(f"assets?filter={encoded}", params=params)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "filter assets")

        # ---------- create ----------
        if action == "create":
            if not name or not asset_type_id:
                return {"error": "name and asset_type_id are required for create"}
            # Validate enums
            valid_impacts = {"low", "medium", "high"}
            valid_usage = {"permanent", "loaner"}
            imp = (impact or "low").lower()
            usg = (usage_type or "permanent").lower()
            if imp not in valid_impacts:
                return {"error": f"impact must be one of {valid_impacts}"}
            if usg not in valid_usage:
                return {"error": f"usage_type must be one of {valid_usage}"}

            data: Dict[str, Any] = {
                "name": name,
                "asset_type_id": asset_type_id,
                "impact": imp,
                "usage_type": usg,
            }
            for k, v in [("asset_tag", asset_tag), ("description", description),
                         ("user_id", user_id), ("location_id", location_id),
                         ("department_id", department_id), ("agent_id", agent_id),
                         ("group_id", group_id), ("assigned_on", assigned_on),
                         ("workspace_id", workspace_id)]:
                if v is not None:
                    data[k] = v
            if type_fields:
                data["type_fields"] = type_fields
            try:
                resp = await api_post("assets", json=data)
                resp.raise_for_status()
                return {"success": True, "asset": resp.json()}
            except Exception as e:
                return handle_error(e, "create asset")

        # ---------- update ----------
        if action == "update":
            if not display_id:
                return {"error": "display_id required for update"}
            fields = asset_fields or {}
            # Allow explicit params to override
            for k, v in [("name", name), ("asset_tag", asset_tag),
                         ("impact", impact), ("usage_type", usage_type),
                         ("description", description), ("user_id", user_id),
                         ("location_id", location_id), ("department_id", department_id),
                         ("agent_id", agent_id), ("group_id", group_id),
                         ("assigned_on", assigned_on)]:
                if v is not None:
                    fields[k] = v
            if type_fields:
                fields["type_fields"] = type_fields
            if not fields:
                return {"error": "No fields provided for update"}
            try:
                resp = await api_put(f"assets/{display_id}", json=fields)
                resp.raise_for_status()
                return {"success": True, "asset": resp.json()}
            except Exception as e:
                return handle_error(e, "update asset")

        # ---------- delete ----------
        if action == "delete":
            if not display_id:
                return {"error": "display_id required for delete"}
            try:
                resp = await api_delete(f"assets/{display_id}")
                if resp.status_code == 204:
                    return {"success": True, "message": "Asset moved to trash"}
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "delete asset")

        # ---------- delete_permanently ----------
        if action == "delete_permanently":
            if not display_id:
                return {"error": "display_id required for delete_permanently"}
            try:
                resp = await api_put(f"assets/{display_id}/delete_forever")
                if resp.status_code == 204:
                    return {"success": True, "message": "Asset permanently deleted"}
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "permanently delete asset")

        # ---------- restore ----------
        if action == "restore":
            if not display_id:
                return {"error": "display_id required for restore"}
            try:
                resp = await api_put(f"assets/{display_id}/restore")
                resp.raise_for_status()
                return {"success": True, "message": "Asset restored"}
            except Exception as e:
                return handle_error(e, "restore asset")

        # ---------- move ----------
        if action == "move":
            if not display_id or workspace_id is None:
                return {"error": "display_id and workspace_id required for move"}
            data = {"workspace_id": workspace_id}
            if agent_id is not None:
                data["agent_id"] = agent_id
            if group_id is not None:
                data["group_id"] = group_id
            try:
                resp = await api_put(f"assets/{display_id}/move_workspace", json=data)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "move asset")

        # ---------- get_types ----------
        if action == "get_types":
            params = {"page": page, "per_page": per_page}
            try:
                resp = await api_get("asset_types", params=params)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "list asset types")

        # ---------- get_type ----------
        if action == "get_type":
            if not asset_type_id:
                return {"error": "asset_type_id required for get_type"}
            try:
                resp = await api_get(f"asset_types/{asset_type_id}")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "get asset type")

        return {"error": f"Unknown action '{action}'. Valid: create, update, delete, delete_permanently, restore, get, list, search, filter, move, get_types, get_type"}

    # ------------------------------------------------------------------ #
    #  manage_asset_details                                               #
    # ------------------------------------------------------------------ #
    @mcp.tool()
    async def manage_asset_details(
        action: str,
        display_id: int,
    ) -> Dict[str, Any]:
        """Retrieve asset sub-resources.

        Args:
            action: 'components', 'assignment_history', 'requests', 'contracts'
            display_id: The asset display ID
        """
        action = action.lower().strip()
        endpoints = {
            "components": "components",
            "assignment_history": "assignment-history",
            "requests": "requests",
            "contracts": "contracts",
        }
        if action not in endpoints:
            return {"error": f"Unknown action '{action}'. Valid: {', '.join(endpoints)}"}
        try:
            resp = await api_get(f"assets/{display_id}/{endpoints[action]}")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return handle_error(e, f"get asset {action}")

    # ------------------------------------------------------------------ #
    #  manage_asset_relationship                                          #
    # ------------------------------------------------------------------ #
    @mcp.tool()
    async def manage_asset_relationship(
        action: str,
        display_id: Optional[int] = None,
        relationship_id: Optional[int] = None,
        relationship_ids: Optional[List[int]] = None,
        relationships: Optional[List[Dict[str, Any]]] = None,
        job_id: Optional[str] = None,
        page: int = 1,
        per_page: int = 30,
    ) -> Dict[str, Any]:
        """Manage asset relationships.

        Args:
            action: 'list_for_asset', 'list_all', 'get', 'create', 'delete',
                    'get_types', 'job_status'
            display_id: Asset display ID (list_for_asset)
            relationship_id: Relationship ID (get)
            relationship_ids: List of rel IDs to delete (delete)
            relationships: List of relationship dicts for bulk create (create).
                Each dict: {relationship_type_id, primary_id, primary_type,
                            secondary_id, secondary_type}
            job_id: Job ID returned by async operations (job_status)
            page: Page number (list_all)
            per_page: Items per page (list_all)
        """
        action = action.lower().strip()

        if action == "list_for_asset":
            if not display_id:
                return {"error": "display_id required for list_for_asset"}
            try:
                resp = await api_get(f"assets/{display_id}/relationships")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "list asset relationships")

        if action == "list_all":
            try:
                resp = await api_get("relationships", params={"page": page, "per_page": per_page})
                resp.raise_for_status()
                pagination_info = parse_link_header(resp.headers.get("Link", ""))
                return {
                    "relationships": resp.json(),
                    "pagination": {
                        "current_page": page,
                        "next_page": pagination_info.get("next"),
                        "prev_page": pagination_info.get("prev"),
                    },
                }
            except Exception as e:
                return handle_error(e, "list all relationships")

        if action == "get":
            if not relationship_id:
                return {"error": "relationship_id required for get"}
            try:
                resp = await api_get(f"relationships/{relationship_id}")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "get relationship")

        if action == "create":
            if not relationships:
                return {"error": "relationships list required for create"}
            try:
                resp = await api_post("relationships/bulk-create", json=relationships)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "create relationships")

        if action == "delete":
            if not relationship_ids:
                return {"error": "relationship_ids list required for delete"}
            ids_str = ",".join(str(i) for i in relationship_ids)
            try:
                resp = await api_delete(f"relationships?ids={ids_str}")
                if resp.status_code == 204:
                    return {"success": True, "message": "Relationships deleted"}
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "delete relationships")

        if action == "get_types":
            try:
                resp = await api_get("relationship_types")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "get relationship types")

        if action == "job_status":
            if not job_id:
                return {"error": "job_id required for job_status"}
            try:
                resp = await api_get(f"jobs/{job_id}")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "get job status")

        return {"error": f"Unknown action '{action}'. Valid: list_for_asset, list_all, get, create, delete, get_types, job_status"}
