"""Freshservice MCP — Changes tools (consolidated).

Exposes 5 tools instead of the original 33:
  • manage_change           — CRUD + list + filter + close + move + get_fields
  • manage_change_note      — create, view, list, update, delete
  • manage_change_task      — create, view, list, update, delete
  • manage_change_time_entry — create, view, list, update, delete
  • manage_change_approval  — groups + approvals CRUD, chain rule, reminders
"""
import urllib.parse
from typing import Any, Dict, List, Optional, Union

from ..config import (
    ChangeImpact,
    ChangePriority,
    ChangeRisk,
    ChangeStatus,
    ChangeType,
)
from ..http_client import (
    api_delete,
    api_get,
    api_post,
    api_put,
    handle_error,
    parse_link_header,
)


# ── registration ───────────────────────────────────────────────────────────
def register_changes_tools(mcp) -> None:  # noqa: C901 – large by nature
    """Register change-related tools on *mcp*."""

    # ------------------------------------------------------------------ #
    #  manage_change                                                      #
    # ------------------------------------------------------------------ #
    @mcp.tool()
    async def manage_change(
        action: str,
        change_id: Optional[int] = None,
        # create / update fields
        requester_id: Optional[int] = None,
        subject: Optional[str] = None,
        description: Optional[str] = None,
        priority: Optional[Union[int, str]] = None,
        impact: Optional[Union[int, str]] = None,
        status: Optional[Union[int, str]] = None,
        risk: Optional[Union[int, str]] = None,
        change_type: Optional[Union[int, str]] = None,
        group_id: Optional[int] = None,
        agent_id: Optional[int] = None,
        department_id: Optional[int] = None,
        category: Optional[str] = None,
        sub_category: Optional[str] = None,
        item_category: Optional[str] = None,
        planned_start_date: Optional[str] = None,
        planned_end_date: Optional[str] = None,
        reason_for_change: Optional[str] = None,
        change_impact: Optional[str] = None,
        rollout_plan: Optional[str] = None,
        backout_plan: Optional[str] = None,
        custom_fields: Optional[Dict[str, Any]] = None,
        assets: Optional[List[Dict[str, Any]]] = None,
        # close
        change_result_explanation: Optional[str] = None,
        # move
        workspace_id: Optional[int] = None,
        # list / filter
        query: Optional[str] = None,
        view: Optional[str] = None,
        sort: Optional[str] = None,
        order_by: Optional[str] = None,
        updated_since: Optional[str] = None,
        page: int = 1,
        per_page: int = 30,
    ) -> Dict[str, Any]:
        """Unified change operations.

        Args:
            action: One of 'create', 'update', 'delete', 'get', 'list', 'filter',
                    'close', 'move', 'get_fields'
            change_id: Required for get, update, delete, close, move
            requester_id: Initiator ID (create — MANDATORY)
            subject: Change subject (create — MANDATORY)
            description: HTML description (create — MANDATORY)
            priority: 1=Low, 2=Medium, 3=High, 4=Urgent
            impact: 1=Low, 2=Medium, 3=High
            status: 1=Open, 2=Planning, 3=Awaiting Approval, 4=Pending Release,
                    5=Pending Review, 6=Closed
            risk: 1=Low, 2=Medium, 3=High, 4=Very High
            change_type: 1=Minor, 2=Standard, 3=Major, 4=Emergency
            group_id: Agent group ID
            agent_id: Agent ID
            department_id: Department ID
            category: Category string
            sub_category: Sub-category string
            item_category: Item category string
            planned_start_date: ISO datetime
            planned_end_date: ISO datetime
            reason_for_change: Planning field — reason (text/HTML)
            change_impact: Planning field — impact analysis (text/HTML)
            rollout_plan: Planning field — rollout plan (text/HTML)
            backout_plan: Planning field — backout plan (text/HTML)
            custom_fields: Custom fields dict
            assets: Assets list, e.g. [{"display_id": 1}]
            change_result_explanation: Result explanation (close)
            workspace_id: Target workspace (move / list / filter)
            query: Filter query string (list/filter)
            view: View name or ID (list)
            sort: Sort field (list)
            order_by: 'asc' or 'desc' (list)
            updated_since: ISO datetime (list)
            page: Page number
            per_page: Items per page 1-100
        """
        action = action.lower().strip()

        # ---------- get_fields ----------
        if action == "get_fields":
            try:
                resp = await api_get("change_form_fields")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "fetch change fields")

        # ---------- list / filter ----------
        if action in ("list", "filter"):
            params: Dict[str, Any] = {"page": page, "per_page": per_page}
            if query:
                params["query"] = query
            if view:
                params["view"] = view
            if sort:
                params["sort"] = sort
            if order_by:
                params["order_by"] = order_by
            if updated_since:
                params["updated_since"] = updated_since
            if workspace_id is not None:
                params["workspace_id"] = workspace_id
            try:
                resp = await api_get("changes", params=params)
                resp.raise_for_status()
                pagination_info = parse_link_header(resp.headers.get("Link", ""))
                return {
                    "changes": resp.json(),
                    "pagination": {
                        "current_page": page,
                        "next_page": pagination_info.get("next"),
                        "prev_page": pagination_info.get("prev"),
                        "per_page": per_page,
                    },
                }
            except Exception as e:
                return handle_error(e, "list changes")

        # ---------- get ----------
        if action == "get":
            if not change_id:
                return {"error": "change_id required for get"}
            try:
                resp = await api_get(f"changes/{change_id}")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "get change")

        # ---------- create ----------
        if action == "create":
            if not requester_id or not subject or not description:
                return {"error": "requester_id, subject, and description are required for create"}
            # Validate enums
            try:
                p = int(priority) if priority else ChangePriority.LOW.value
                im = int(impact) if impact else ChangeImpact.LOW.value
                st = int(status) if status else ChangeStatus.OPEN.value
                ri = int(risk) if risk else ChangeRisk.LOW.value
                ct = int(change_type) if change_type else ChangeType.STANDARD.value
            except ValueError:
                return {"error": "Invalid value for priority, impact, status, risk, or change_type"}

            data: Dict[str, Any] = {
                "requester_id": requester_id,
                "subject": subject,
                "description": description,
                "priority": p,
                "impact": im,
                "status": st,
                "risk": ri,
                "change_type": ct,
            }
            for k, v in [("group_id", group_id), ("agent_id", agent_id),
                         ("department_id", department_id), ("category", category),
                         ("sub_category", sub_category), ("item_category", item_category),
                         ("planned_start_date", planned_start_date),
                         ("planned_end_date", planned_end_date)]:
                if v is not None:
                    data[k] = v

            # planning fields
            planning = {}
            for fname, fval in [("reason_for_change", reason_for_change),
                                ("change_impact", change_impact),
                                ("rollout_plan", rollout_plan),
                                ("backout_plan", backout_plan)]:
                if fval is not None:
                    planning[fname] = {"description": fval}
            if planning:
                data["planning_fields"] = planning
            if custom_fields:
                data["custom_fields"] = custom_fields
            if assets:
                data["assets"] = assets

            try:
                resp = await api_post("changes", json=data)
                resp.raise_for_status()
                return {"success": True, "change": resp.json()}
            except Exception as e:
                return handle_error(e, "create change")

        # ---------- update ----------
        if action == "update":
            if not change_id:
                return {"error": "change_id required for update"}
            update_data: Dict[str, Any] = {}
            for k, v in [("subject", subject), ("description", description),
                         ("group_id", group_id), ("agent_id", agent_id),
                         ("department_id", department_id), ("category", category),
                         ("sub_category", sub_category), ("item_category", item_category),
                         ("planned_start_date", planned_start_date),
                         ("planned_end_date", planned_end_date)]:
                if v is not None:
                    update_data[k] = v
            for k, v in [("priority", priority), ("impact", impact),
                         ("status", status), ("risk", risk),
                         ("change_type", change_type)]:
                if v is not None:
                    try:
                        update_data[k] = int(v)
                    except ValueError:
                        return {"error": f"Invalid {k} value: {v}"}
            if custom_fields:
                update_data["custom_fields"] = custom_fields
            if assets:
                update_data["assets"] = assets
            planning = {}
            for fname, fval in [("reason_for_change", reason_for_change),
                                ("change_impact", change_impact),
                                ("rollout_plan", rollout_plan),
                                ("backout_plan", backout_plan)]:
                if fval is not None:
                    planning[fname] = {"description": fval}
            if planning:
                update_data["planning_fields"] = planning
            if not update_data:
                return {"error": "No fields provided for update"}
            try:
                resp = await api_put(f"changes/{change_id}", json=update_data)
                resp.raise_for_status()
                return {"success": True, "change": resp.json()}
            except Exception as e:
                return handle_error(e, "update change")

        # ---------- close ----------
        if action == "close":
            if not change_id:
                return {"error": "change_id required for close"}
            close_data: Dict[str, Any] = {"status": ChangeStatus.CLOSED.value}
            cf = dict(custom_fields or {})
            if change_result_explanation:
                cf["change_result_explanation"] = change_result_explanation
            if cf:
                close_data["custom_fields"] = cf
            try:
                resp = await api_put(f"changes/{change_id}", json=close_data)
                resp.raise_for_status()
                return {"success": True, "change": resp.json()}
            except Exception as e:
                return handle_error(e, "close change")

        # ---------- delete ----------
        if action == "delete":
            if not change_id:
                return {"error": "change_id required for delete"}
            try:
                resp = await api_delete(f"changes/{change_id}")
                if resp.status_code == 204:
                    return {"success": True, "message": "Change deleted"}
                return {"error": f"Unexpected status {resp.status_code}"}
            except Exception as e:
                return handle_error(e, "delete change")

        # ---------- move ----------
        if action == "move":
            if not change_id or workspace_id is None:
                return {"error": "change_id and workspace_id required for move"}
            try:
                resp = await api_put(f"changes/{change_id}/move_workspace", json={"workspace_id": workspace_id})
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "move change")

        return {"error": f"Unknown action '{action}'. Valid: create, update, delete, get, list, filter, close, move, get_fields"}

    # ------------------------------------------------------------------ #
    #  manage_change_note                                                 #
    # ------------------------------------------------------------------ #
    @mcp.tool()
    async def manage_change_note(
        action: str,
        change_id: int,
        note_id: Optional[int] = None,
        body: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Manage notes on a change.

        Args:
            action: 'create', 'view', 'list', 'update', 'delete'
            change_id: The change ID
            note_id: Required for view, update, delete
            body: Note body HTML (create, update)
        """
        action = action.lower().strip()
        base = f"changes/{change_id}/notes"

        if action == "list":
            try:
                resp = await api_get(base)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "list change notes")

        if action == "create":
            if not body:
                return {"error": "body required for create"}
            try:
                resp = await api_post(base, json={"body": body})
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "create change note")

        if action == "view":
            if not note_id:
                return {"error": "note_id required for view"}
            try:
                resp = await api_get(f"{base}/{note_id}")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "view change note")

        if action == "update":
            if not note_id or not body:
                return {"error": "note_id and body required for update"}
            try:
                resp = await api_put(f"{base}/{note_id}", json={"body": body})
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "update change note")

        if action == "delete":
            if not note_id:
                return {"error": "note_id required for delete"}
            try:
                resp = await api_delete(f"{base}/{note_id}")
                if resp.status_code == 204:
                    return {"success": True, "message": "Note deleted"}
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "delete change note")

        return {"error": f"Unknown action '{action}'. Valid: create, view, list, update, delete"}

    # ------------------------------------------------------------------ #
    #  manage_change_task                                                 #
    # ------------------------------------------------------------------ #
    @mcp.tool()
    async def manage_change_task(
        action: str,
        change_id: int,
        task_id: Optional[int] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        task_status: Optional[int] = None,
        task_priority: Optional[int] = None,
        assigned_to_id: Optional[int] = None,
        task_group_id: Optional[int] = None,
        due_date: Optional[str] = None,
        task_fields: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Manage tasks on a change.

        Args:
            action: 'create', 'view', 'list', 'update', 'delete'
            change_id: The change ID
            task_id: Required for view, update, delete
            title: Task title (create)
            description: Task description (create)
            task_status: Task status int (create/update)
            task_priority: Task priority int (create/update)
            assigned_to_id: Agent ID to assign (create/update)
            task_group_id: Group ID (create/update)
            due_date: ISO date (create/update)
            task_fields: Dict of fields (update — alternative to individual params)
        """
        action = action.lower().strip()
        base = f"changes/{change_id}/tasks"

        if action == "list":
            try:
                resp = await api_get(base)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "list change tasks")

        if action == "create":
            if not title or not description:
                return {"error": "title and description required for create"}
            data: Dict[str, Any] = {"title": title, "description": description}
            if task_status is not None:
                data["status"] = task_status
            if task_priority is not None:
                data["priority"] = task_priority
            if assigned_to_id:
                data["assigned_to_id"] = assigned_to_id
            if task_group_id:
                data["group_id"] = task_group_id
            if due_date:
                data["due_date"] = due_date
            try:
                resp = await api_post(base, json=data)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "create change task")

        if action == "view":
            if not task_id:
                return {"error": "task_id required for view"}
            try:
                resp = await api_get(f"{base}/{task_id}")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "view change task")

        if action == "update":
            if not task_id:
                return {"error": "task_id required for update"}
            fields = task_fields or {}
            try:
                resp = await api_put(f"{base}/{task_id}", json=fields)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "update change task")

        if action == "delete":
            if not task_id:
                return {"error": "task_id required for delete"}
            try:
                resp = await api_delete(f"{base}/{task_id}")
                if resp.status_code == 204:
                    return {"success": True, "message": "Task deleted"}
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "delete change task")

        return {"error": f"Unknown action '{action}'. Valid: create, view, list, update, delete"}

    # ------------------------------------------------------------------ #
    #  manage_change_time_entry                                           #
    # ------------------------------------------------------------------ #
    @mcp.tool()
    async def manage_change_time_entry(
        action: str,
        change_id: int,
        time_entry_id: Optional[int] = None,
        time_spent: Optional[str] = None,
        note: Optional[str] = None,
        te_agent_id: Optional[int] = None,
        executed_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Manage time entries on a change.

        Args:
            action: 'create', 'view', 'list', 'update', 'delete'
            change_id: The change ID
            time_entry_id: Required for view, update, delete
            time_spent: Format "hh:mm" (create/update)
            note: Work description (create/update)
            te_agent_id: Agent ID who did the work (create)
            executed_at: ISO datetime (create)
        """
        action = action.lower().strip()
        base = f"changes/{change_id}/time_entries"

        if action == "list":
            try:
                resp = await api_get(base)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "list time entries")

        if action == "create":
            if not time_spent or not note or not te_agent_id:
                return {"error": "time_spent, note, and te_agent_id required for create"}
            data: Dict[str, Any] = {"time_spent": time_spent, "note": note, "agent_id": te_agent_id}
            if executed_at:
                data["executed_at"] = executed_at
            try:
                resp = await api_post(base, json=data)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "create time entry")

        if action == "view":
            if not time_entry_id:
                return {"error": "time_entry_id required for view"}
            try:
                resp = await api_get(f"{base}/{time_entry_id}")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "view time entry")

        if action == "update":
            if not time_entry_id:
                return {"error": "time_entry_id required for update"}
            data = {}
            if time_spent is not None:
                data["time_spent"] = time_spent
            if note is not None:
                data["note"] = note
            try:
                resp = await api_put(f"{base}/{time_entry_id}", json=data)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "update time entry")

        if action == "delete":
            if not time_entry_id:
                return {"error": "time_entry_id required for delete"}
            try:
                resp = await api_delete(f"{base}/{time_entry_id}")
                if resp.status_code == 204:
                    return {"success": True, "message": "Time entry deleted"}
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "delete time entry")

        return {"error": f"Unknown action '{action}'. Valid: create, view, list, update, delete"}

    # ------------------------------------------------------------------ #
    #  manage_change_approval                                             #
    # ------------------------------------------------------------------ #
    @mcp.tool()
    async def manage_change_approval(
        action: str,
        change_id: int,
        approval_id: Optional[int] = None,
        approval_group_id: Optional[int] = None,
        name: Optional[str] = None,
        approver_ids: Optional[List[int]] = None,
        approval_type: Optional[str] = None,
        approval_chain_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Manage approvals and approval groups for a change.

        Args:
            action: 'list_groups', 'create_group', 'update_group', 'cancel_group',
                    'list', 'view', 'remind', 'cancel', 'set_chain_rule'
            change_id: The change ID
            approval_id: Approval ID (view, remind, cancel)
            approval_group_id: Approval group ID (update_group, cancel_group)
            name: Group name (create_group, update_group)
            approver_ids: List of agent IDs (create_group, update_group)
            approval_type: 'everyone' or 'any' (create_group, update_group)
            approval_chain_type: 'parallel' or 'sequential' (set_chain_rule)
        """
        action = action.lower().strip()

        # -- approval groups --
        if action == "list_groups":
            try:
                resp = await api_get(f"changes/{change_id}/approval_groups")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "list approval groups")

        if action == "create_group":
            if not name or not approver_ids:
                return {"error": "name and approver_ids required for create_group"}
            data: Dict[str, Any] = {
                "name": name,
                "approver_ids": approver_ids,
                "approval_type": approval_type or "everyone",
            }
            try:
                resp = await api_post(f"changes/{change_id}/approval_groups", json=data)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "create approval group")

        if action == "update_group":
            if not approval_group_id:
                return {"error": "approval_group_id required for update_group"}
            data = {}
            if name is not None:
                data["name"] = name
            if approver_ids is not None:
                data["approver_ids"] = approver_ids
            if approval_type is not None:
                data["approval_type"] = approval_type
            try:
                resp = await api_put(f"changes/{change_id}/approval_groups/{approval_group_id}", json=data)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "update approval group")

        if action == "cancel_group":
            if not approval_group_id:
                return {"error": "approval_group_id required for cancel_group"}
            try:
                resp = await api_put(f"changes/{change_id}/approval_groups/{approval_group_id}/cancel")
                resp.raise_for_status()
                return {"success": True, "message": "Approval group cancelled"}
            except Exception as e:
                return handle_error(e, "cancel approval group")

        # -- individual approvals --
        if action == "list":
            try:
                resp = await api_get(f"changes/{change_id}/approvals")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "list approvals")

        if action == "view":
            if not approval_id:
                return {"error": "approval_id required for view"}
            try:
                resp = await api_get(f"changes/{change_id}/approvals/{approval_id}")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "view approval")

        if action == "remind":
            if not approval_id:
                return {"error": "approval_id required for remind"}
            try:
                resp = await api_put(f"changes/{change_id}/approvals/{approval_id}/resend_approval")
                resp.raise_for_status()
                return {"success": True, "message": "Reminder sent"}
            except Exception as e:
                return handle_error(e, "send approval reminder")

        if action == "cancel":
            if not approval_id:
                return {"error": "approval_id required for cancel"}
            try:
                resp = await api_put(f"changes/{change_id}/approvals/{approval_id}/cancel")
                resp.raise_for_status()
                return {"success": True, "message": "Approval cancelled"}
            except Exception as e:
                return handle_error(e, "cancel approval")

        # -- chain rule --
        if action == "set_chain_rule":
            if approval_chain_type not in ("parallel", "sequential"):
                return {"error": "approval_chain_type must be 'parallel' or 'sequential'"}
            try:
                resp = await api_put(f"changes/{change_id}/approval_chain", json={"approval_chain_type": approval_chain_type})
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "set chain rule")

        return {"error": f"Unknown action '{action}'. Valid: create_group, update_group, cancel_group, list_groups, list, view, remind, cancel, set_chain_rule"}
