"""Freshservice MCP — Requesters & Requester Groups tools (consolidated).

Exposes 2 tools instead of the original 12:
  • manage_requester       — CRUD + list + filter + get_fields + add_to_group
  • manage_requester_group — CRUD + list + get + list_members
"""
from typing import Any, Dict, List, Optional

from ..http_client import api_get, api_post, api_put, handle_error, parse_link_header


def register_requesters_tools(mcp) -> None:
    """Register requester-related tools on *mcp*."""

    # ------------------------------------------------------------------ #
    #  manage_requester                                                   #
    # ------------------------------------------------------------------ #
    @mcp.tool()
    async def manage_requester(
        action: str,
        requester_id: Optional[int] = None,
        # create / update
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        job_title: Optional[str] = None,
        primary_email: Optional[str] = None,
        secondary_emails: Optional[List[str]] = None,
        work_phone_number: Optional[str] = None,
        mobile_phone_number: Optional[str] = None,
        department_ids: Optional[List[int]] = None,
        can_see_all_tickets_from_associated_departments: Optional[bool] = None,
        reporting_manager_id: Optional[int] = None,
        address: Optional[str] = None,
        time_zone: Optional[str] = None,
        time_format: Optional[str] = None,
        language: Optional[str] = None,
        location_id: Optional[int] = None,
        background_information: Optional[str] = None,
        custom_fields: Optional[Dict[str, Any]] = None,
        # filter
        query: Optional[str] = None,
        include_agents: bool = False,
        # add_to_group
        group_id: Optional[int] = None,
        # list
        page: int = 1,
        per_page: int = 30,
    ) -> Dict[str, Any]:
        """Unified requester operations.

        Args:
            action: 'create', 'update', 'get', 'list', 'filter', 'get_fields', 'add_to_group'
            requester_id: Required for get, update, add_to_group
            first_name: MANDATORY for create
            query: Filter query string (filter)
            include_agents: Include agents in filter results (filter)
            group_id: Group ID (add_to_group)
            page/per_page: Pagination (list)
        """
        action = action.lower().strip()

        if action == "get_fields":
            try:
                resp = await api_get("requester_fields")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "get requester fields")

        if action == "list":
            try:
                resp = await api_get("requesters", params={"page": page, "per_page": per_page})
                resp.raise_for_status()
                pagination_info = parse_link_header(resp.headers.get("Link", ""))
                return {
                    "requesters": resp.json(),
                    "pagination": {
                        "current_page": page,
                        "next_page": pagination_info.get("next"),
                        "prev_page": pagination_info.get("prev"),
                    },
                }
            except Exception as e:
                return handle_error(e, "list requesters")

        if action == "get":
            if not requester_id:
                return {"error": "requester_id required for get"}
            try:
                resp = await api_get(f"requesters/{requester_id}")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "get requester")

        if action == "filter":
            if not query:
                return {"error": "query required for filter"}
            import urllib.parse
            encoded = urllib.parse.quote(query)
            params: Dict[str, Any] = {}
            if include_agents:
                params["include_agents"] = "true"
            try:
                resp = await api_get(f"requesters?query={encoded}", params=params)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "filter requesters")

        if action == "create":
            if not first_name:
                return {"error": "first_name required for create"}
            data: Dict[str, Any] = {"first_name": first_name}
            for k, v in [("last_name", last_name), ("job_title", job_title),
                         ("primary_email", primary_email),
                         ("secondary_emails", secondary_emails),
                         ("work_phone_number", work_phone_number),
                         ("mobile_phone_number", mobile_phone_number),
                         ("department_ids", department_ids),
                         ("can_see_all_tickets_from_associated_departments",
                          can_see_all_tickets_from_associated_departments),
                         ("reporting_manager_id", reporting_manager_id),
                         ("address", address), ("time_zone", time_zone),
                         ("time_format", time_format), ("language", language),
                         ("location_id", location_id),
                         ("background_information", background_information),
                         ("custom_fields", custom_fields)]:
                if v is not None:
                    data[k] = v
            try:
                resp = await api_post("requesters", json=data)
                resp.raise_for_status()
                return {"success": True, "requester": resp.json()}
            except Exception as e:
                return handle_error(e, "create requester")

        if action == "update":
            if not requester_id:
                return {"error": "requester_id required for update"}
            data: Dict[str, Any] = {}
            for k, v in [("first_name", first_name), ("last_name", last_name),
                         ("job_title", job_title), ("primary_email", primary_email),
                         ("secondary_emails", secondary_emails),
                         ("work_phone_number", work_phone_number),
                         ("mobile_phone_number", mobile_phone_number),
                         ("department_ids", department_ids),
                         ("can_see_all_tickets_from_associated_departments",
                          can_see_all_tickets_from_associated_departments),
                         ("reporting_manager_id", reporting_manager_id),
                         ("address", address), ("time_zone", time_zone),
                         ("time_format", time_format), ("language", language),
                         ("location_id", location_id),
                         ("background_information", background_information),
                         ("custom_fields", custom_fields)]:
                if v is not None:
                    data[k] = v
            if not data:
                return {"error": "No fields provided for update"}
            try:
                resp = await api_put(f"requesters/{requester_id}", json=data)
                resp.raise_for_status()
                return {"success": True, "requester": resp.json()}
            except Exception as e:
                return handle_error(e, "update requester")

        if action == "add_to_group":
            if not requester_id or not group_id:
                return {"error": "requester_id and group_id required for add_to_group"}
            try:
                resp = await api_post(f"requester_groups/{group_id}/members/{requester_id}")
                resp.raise_for_status()
                return {"success": True, "message": "Requester added to group"}
            except Exception as e:
                return handle_error(e, "add requester to group")

        return {"error": f"Unknown action '{action}'. Valid: create, update, get, list, filter, get_fields, add_to_group"}

    # ------------------------------------------------------------------ #
    #  manage_requester_group                                             #
    # ------------------------------------------------------------------ #
    @mcp.tool()
    async def manage_requester_group(
        action: str,
        group_id: Optional[int] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        page: int = 1,
        per_page: int = 30,
    ) -> Dict[str, Any]:
        """Manage requester groups.

        Args:
            action: 'create', 'update', 'get', 'list', 'list_members'
            group_id: Required for get, update, list_members
            name: Group name (create — MANDATORY)
            description: Group description
            page/per_page: Pagination (list)
        """
        action = action.lower().strip()

        if action == "list":
            try:
                resp = await api_get("requester_groups", params={"page": page, "per_page": per_page})
                resp.raise_for_status()
                pagination_info = parse_link_header(resp.headers.get("Link", ""))
                return {
                    "requester_groups": resp.json(),
                    "pagination": {
                        "current_page": page,
                        "next_page": pagination_info.get("next"),
                        "prev_page": pagination_info.get("prev"),
                    },
                }
            except Exception as e:
                return handle_error(e, "list requester groups")

        if action == "get":
            if not group_id:
                return {"error": "group_id required for get"}
            try:
                resp = await api_get(f"requester_groups/{group_id}")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "get requester group")

        if action == "create":
            if not name:
                return {"error": "name required for create"}
            data: Dict[str, Any] = {"name": name}
            if description is not None:
                data["description"] = description
            try:
                resp = await api_post("requester_groups", json=data)
                resp.raise_for_status()
                return {"success": True, "requester_group": resp.json()}
            except Exception as e:
                return handle_error(e, "create requester group")

        if action == "update":
            if not group_id:
                return {"error": "group_id required for update"}
            data: Dict[str, Any] = {}
            if name is not None:
                data["name"] = name
            if description is not None:
                data["description"] = description
            if not data:
                return {"error": "No fields provided for update"}
            try:
                resp = await api_put(f"requester_groups/{group_id}", json=data)
                resp.raise_for_status()
                return {"success": True, "requester_group": resp.json()}
            except Exception as e:
                return handle_error(e, "update requester group")

        if action == "list_members":
            if not group_id:
                return {"error": "group_id required for list_members"}
            try:
                resp = await api_get(f"requester_groups/{group_id}/members")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "list requester group members")

        return {"error": f"Unknown action '{action}'. Valid: create, update, get, list, list_members"}
