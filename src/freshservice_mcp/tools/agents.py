"""Freshservice MCP — Agents & Groups tools (consolidated).

Exposes 2 tools instead of the original 10:
  • manage_agent       — CRUD + list + filter + get_fields
  • manage_agent_group — CRUD + list + get
"""
from typing import Any, Dict, List, Optional

from ..http_client import api_get, api_post, api_put, handle_error, parse_link_header


def register_agents_tools(mcp) -> None:
    """Register agent-related tools on *mcp*."""

    # ------------------------------------------------------------------ #
    #  manage_agent                                                       #
    # ------------------------------------------------------------------ #
    @mcp.tool()
    async def manage_agent(
        action: str,
        agent_id: Optional[int] = None,
        # create / update
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        email: Optional[str] = None,
        occasional: Optional[bool] = None,
        job_title: Optional[str] = None,
        work_phone_number: Optional[int] = None,
        mobile_phone_number: Optional[int] = None,
        department_ids: Optional[List[int]] = None,
        can_see_all_tickets_from_associated_departments: Optional[bool] = None,
        reporting_manager_id: Optional[int] = None,
        address: Optional[str] = None,
        time_zone: Optional[str] = None,
        time_format: Optional[str] = None,
        language: Optional[str] = None,
        location_id: Optional[int] = None,
        background_information: Optional[str] = None,
        scoreboard_level_id: Optional[int] = None,
        # filter / list
        query: Optional[str] = None,
        page: int = 1,
        per_page: int = 30,
    ) -> Dict[str, Any]:
        """Unified agent operations.

        Args:
            action: 'create', 'update', 'get', 'list', 'filter', 'get_fields'
            agent_id: Required for get, update
            first_name: MANDATORY for create
            email: Agent email (create)
            query: Filter query string (filter)
            page/per_page: Pagination (list)
        """
        action = action.lower().strip()

        if action == "get_fields":
            try:
                resp = await api_get("agent_fields")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "get agent fields")

        if action == "list":
            try:
                resp = await api_get("agents", params={"page": page, "per_page": per_page})
                resp.raise_for_status()
                pagination_info = parse_link_header(resp.headers.get("Link", ""))
                return {
                    "agents": resp.json(),
                    "pagination": {
                        "current_page": page,
                        "next_page": pagination_info.get("next"),
                        "prev_page": pagination_info.get("prev"),
                    },
                }
            except Exception as e:
                return handle_error(e, "list agents")

        if action == "get":
            if not agent_id:
                return {"error": "agent_id required for get"}
            try:
                resp = await api_get(f"agents/{agent_id}")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "get agent")

        if action == "filter":
            if not query:
                return {"error": "query required for filter"}
            import urllib.parse
            encoded = urllib.parse.quote(f'"{query}"')
            all_agents: List[Any] = []
            current_page = 1
            while True:
                try:
                    resp = await api_get(f"agents?query={encoded}", params={"page": current_page})
                    resp.raise_for_status()
                    data = resp.json()
                    agents = data.get("agents", [])
                    if not agents:
                        break
                    all_agents.extend(agents)
                    link = resp.headers.get("Link", "")
                    if 'rel="next"' not in link:
                        break
                    current_page += 1
                except Exception as e:
                    return handle_error(e, "filter agents")
            return {"agents": all_agents, "total": len(all_agents)}

        if action == "create":
            if not first_name:
                return {"error": "first_name required for create"}
            data: Dict[str, Any] = {"first_name": first_name}
            for k, v in [("last_name", last_name), ("email", email),
                         ("occasional", occasional), ("job_title", job_title),
                         ("work_phone_number", work_phone_number),
                         ("mobile_phone_number", mobile_phone_number),
                         ("department_ids", department_ids),
                         ("reporting_manager_id", reporting_manager_id),
                         ("address", address), ("time_zone", time_zone),
                         ("time_format", time_format), ("language", language),
                         ("location_id", location_id),
                         ("background_information", background_information),
                         ("scoreboard_level_id", scoreboard_level_id),
                         ("can_see_all_tickets_from_associated_departments",
                          can_see_all_tickets_from_associated_departments)]:
                if v is not None:
                    data[k] = v
            try:
                resp = await api_post("agents", json=data)
                resp.raise_for_status()
                return {"success": True, "agent": resp.json()}
            except Exception as e:
                return handle_error(e, "create agent")

        if action == "update":
            if not agent_id:
                return {"error": "agent_id required for update"}
            data: Dict[str, Any] = {}
            for k, v in [("first_name", first_name), ("last_name", last_name),
                         ("email", email), ("occasional", occasional),
                         ("job_title", job_title),
                         ("work_phone_number", work_phone_number),
                         ("mobile_phone_number", mobile_phone_number),
                         ("department_ids", department_ids),
                         ("reporting_manager_id", reporting_manager_id),
                         ("address", address), ("time_zone", time_zone),
                         ("time_format", time_format), ("language", language),
                         ("location_id", location_id),
                         ("background_information", background_information),
                         ("scoreboard_level_id", scoreboard_level_id),
                         ("can_see_all_tickets_from_associated_departments",
                          can_see_all_tickets_from_associated_departments)]:
                if v is not None:
                    data[k] = v
            if not data:
                return {"error": "No fields provided for update"}
            try:
                resp = await api_put(f"agents/{agent_id}", json=data)
                resp.raise_for_status()
                return {"success": True, "agent": resp.json()}
            except Exception as e:
                return handle_error(e, "update agent")

        return {"error": f"Unknown action '{action}'. Valid: create, update, get, list, filter, get_fields"}

    # ------------------------------------------------------------------ #
    #  manage_agent_group                                                 #
    # ------------------------------------------------------------------ #
    @mcp.tool()
    async def manage_agent_group(
        action: str,
        group_id: Optional[int] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        agent_ids: Optional[List[int]] = None,
        auto_ticket_assign: Optional[bool] = None,
        escalate_to: Optional[int] = None,
        unassigned_for: Optional[str] = None,
        group_fields: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Manage agent groups.

        Args:
            action: 'create', 'update', 'get', 'list'
            group_id: Required for get, update
            name: Group name (create — MANDATORY)
            description: Group description
            agent_ids: List of agent IDs in the group
            auto_ticket_assign: Auto-assign tickets
            escalate_to: Agent ID for escalation
            unassigned_for: Duration before escalation (e.g. '30m', '1h')
            group_fields: Generic fields dict (update — alternative to explicit params)
        """
        action = action.lower().strip()

        if action == "list":
            try:
                resp = await api_get("groups")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "list agent groups")

        if action == "get":
            if not group_id:
                return {"error": "group_id required for get"}
            try:
                resp = await api_get(f"groups/{group_id}")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "get agent group")

        if action == "create":
            if not name:
                return {"error": "name required for create"}
            data: Dict[str, Any] = {"name": name}
            for k, v in [("description", description), ("agent_ids", agent_ids),
                         ("auto_ticket_assign", auto_ticket_assign),
                         ("escalate_to", escalate_to),
                         ("unassigned_for", unassigned_for)]:
                if v is not None:
                    data[k] = v
            try:
                resp = await api_post("groups", json=data)
                resp.raise_for_status()
                return {"success": True, "group": resp.json()}
            except Exception as e:
                return handle_error(e, "create agent group")

        if action == "update":
            if not group_id:
                return {"error": "group_id required for update"}
            data = group_fields or {}
            for k, v in [("name", name), ("description", description),
                         ("agent_ids", agent_ids),
                         ("auto_ticket_assign", auto_ticket_assign),
                         ("escalate_to", escalate_to),
                         ("unassigned_for", unassigned_for)]:
                if v is not None:
                    data[k] = v
            if not data:
                return {"error": "No fields provided for update"}
            try:
                resp = await api_put(f"groups/{group_id}", json=data)
                resp.raise_for_status()
                return {"success": True, "group": resp.json()}
            except Exception as e:
                return handle_error(e, "update agent group")

        return {"error": f"Unknown action '{action}'. Valid: create, update, get, list"}
