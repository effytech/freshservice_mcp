"""Freshservice MCP — Products tools (consolidated).

Exposes 1 tool instead of the original 4:
  • manage_product — CRUD + list
"""
from typing import Any, Dict, Optional, Union

from ..http_client import api_get, api_post, api_put, handle_error, parse_link_header


def register_products_tools(mcp) -> None:
    """Register product-related tools on *mcp*."""

    @mcp.tool()
    async def manage_product(
        action: str,
        product_id: Optional[int] = None,
        name: Optional[str] = None,
        asset_type_id: Optional[int] = None,
        manufacturer: Optional[str] = None,
        status: Optional[Union[str, int]] = None,
        mode_of_procurement: Optional[str] = None,
        depreciation_type_id: Optional[int] = None,
        description: Optional[str] = None,
        description_text: Optional[str] = None,
        page: int = 1,
        per_page: int = 30,
    ) -> Dict[str, Any]:
        """Unified product operations.

        Args:
            action: 'create', 'update', 'get', 'list'
            product_id: Required for get, update
            name: Product name (create — MANDATORY)
            asset_type_id: Asset type ID (create — MANDATORY)
            manufacturer: Manufacturer name
            status: Product status (str or int)
            mode_of_procurement: e.g. 'buy', 'lease'
            depreciation_type_id: Depreciation type ID
            description: HTML description
            description_text: Plain text description
            page/per_page: Pagination (list)
        """
        action = action.lower().strip()

        if action == "list":
            try:
                resp = await api_get("products", params={"page": page, "per_page": per_page})
                resp.raise_for_status()
                pagination_info = parse_link_header(resp.headers.get("Link", ""))
                return {
                    "products": resp.json(),
                    "pagination": {
                        "current_page": page,
                        "next_page": pagination_info.get("next"),
                        "prev_page": pagination_info.get("prev"),
                    },
                }
            except Exception as e:
                return handle_error(e, "list products")

        if action == "get":
            if not product_id:
                return {"error": "product_id required for get"}
            try:
                resp = await api_get(f"products/{product_id}")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "get product")

        if action == "create":
            if not name or not asset_type_id:
                return {"error": "name and asset_type_id required for create"}
            data: Dict[str, Any] = {"name": name, "asset_type_id": asset_type_id}
            for k, v in [("manufacturer", manufacturer), ("status", status),
                         ("mode_of_procurement", mode_of_procurement),
                         ("depreciation_type_id", depreciation_type_id),
                         ("description", description),
                         ("description_text", description_text)]:
                if v is not None:
                    data[k] = v
            try:
                resp = await api_post("products", json=data)
                resp.raise_for_status()
                return {"success": True, "product": resp.json()}
            except Exception as e:
                return handle_error(e, "create product")

        if action == "update":
            if not product_id:
                return {"error": "product_id required for update"}
            data: Dict[str, Any] = {}
            for k, v in [("name", name), ("asset_type_id", asset_type_id),
                         ("manufacturer", manufacturer), ("status", status),
                         ("mode_of_procurement", mode_of_procurement),
                         ("depreciation_type_id", depreciation_type_id),
                         ("description", description),
                         ("description_text", description_text)]:
                if v is not None:
                    data[k] = v
            if not data:
                return {"error": "No fields provided for update"}
            try:
                resp = await api_put(f"products/{product_id}", json=data)
                resp.raise_for_status()
                return {"success": True, "product": resp.json()}
            except Exception as e:
                return handle_error(e, "update product")

        return {"error": f"Unknown action '{action}'. Valid: create, update, get, list"}
