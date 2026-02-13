"""Freshservice MCP — Tickets tools (consolidated).

Exposes 3 tools instead of the original 11:
  • manage_ticket          — CRUD + list + filter + get_fields
  • manage_ticket_conversation — reply, add_note, update, list
  • manage_service_catalog — list_items, get_requested_items, place_request
"""
import json
import urllib.parse
from typing import Any, Dict, List, Optional, Union

import httpx

from ..config import (
    FRESHSERVICE_DOMAIN,
    TicketPriority,
    TicketSource,
    TicketStatus,
)
from ..http_client import (
    api_delete,
    api_get,
    api_post,
    api_put,
    api_url,
    get_auth_headers,
    handle_error,
    parse_link_header,
)


# ── helpers ────────────────────────────────────────────────────────────────
def _validate_pagination(page: int, per_page: int) -> Optional[Dict[str, Any]]:
    if page < 1:
        return {"error": "Page number must be greater than 0"}
    if per_page < 1 or per_page > 100:
        return {"error": "Page size must be between 1 and 100"}
    return None


# ── registration ───────────────────────────────────────────────────────────
def register_tickets_tools(mcp) -> None:
    """Register ticket-related tools on *mcp*."""

    # ------------------------------------------------------------------ #
    #  manage_ticket                                                      #
    # ------------------------------------------------------------------ #
    @mcp.tool()
    async def manage_ticket(
        action: str,
        ticket_id: Optional[int] = None,
        # create / update fields
        subject: Optional[str] = None,
        description: Optional[str] = None,
        source: Optional[Union[int, str]] = None,
        priority: Optional[Union[int, str]] = None,
        status: Optional[Union[int, str]] = None,
        email: Optional[str] = None,
        requester_id: Optional[int] = None,
        custom_fields: Optional[Dict[str, Any]] = None,
        ticket_fields: Optional[Dict[str, Any]] = None,
        # filter / list
        query: Optional[str] = None,
        page: int = 1,
        per_page: int = 30,
        workspace_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Unified ticket operations.

        Args:
            action: One of 'create', 'update', 'delete', 'get', 'list', 'filter', 'get_fields'
            ticket_id: Required for get, update, delete
            subject: Ticket subject (create)
            description: Ticket body — HTML (create)
            source: Source enum (1=Email,2=Portal,3=Phone…) (create)
            priority: 1=Low,2=Medium,3=High,4=Urgent (create/update)
            status: 2=Open,3=Pending,4=Resolved,5=Closed (create/update)
            email: Requester email (create — required if no requester_id)
            requester_id: Requester ID (create — required if no email)
            custom_fields: Key-value custom field pairs
            ticket_fields: Dict of fields to update (update action)
            query: Filter query string, e.g. "priority:3 AND status:2" (filter)
            page: Page number (list/filter)
            per_page: Items per page 1-100 (list)
            workspace_id: Workspace filter (filter)
        """
        action = action.lower().strip()

        # ---------- get_fields ----------
        if action == "get_fields":
            try:
                resp = await api_get("ticket_form_fields")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "fetch ticket fields")

        # ---------- list ----------
        if action == "list":
            err = _validate_pagination(page, per_page)
            if err:
                return err
            try:
                resp = await api_get("tickets", params={"page": page, "per_page": per_page})
                resp.raise_for_status()
                pagination_info = parse_link_header(resp.headers.get("Link", ""))
                return {
                    "tickets": resp.json(),
                    "pagination": {
                        "current_page": page,
                        "next_page": pagination_info.get("next"),
                        "prev_page": pagination_info.get("prev"),
                        "per_page": per_page,
                    },
                }
            except Exception as e:
                return handle_error(e, "list tickets")

        # ---------- filter ----------
        if action == "filter":
            if not query:
                return {"error": "query is required for filter action"}
            encoded_query = urllib.parse.quote(f'"{query}"')
            url = f"tickets/filter?query={encoded_query}&page={page}"
            if workspace_id is not None:
                url += f"&workspace_id={workspace_id}"
            try:
                resp = await api_get(url)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "filter tickets")

        # ---------- get ----------
        if action == "get":
            if not ticket_id:
                return {"error": "ticket_id is required for get action"}
            try:
                resp = await api_get(f"tickets/{ticket_id}")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "get ticket")

        # ---------- create ----------
        if action == "create":
            if not subject or not description:
                return {"error": "subject and description are required for create action"}
            if not email and not requester_id:
                return {"error": "Either email or requester_id must be provided"}
            try:
                source_val = int(source) if source else TicketSource.PORTAL.value
                priority_val = int(priority) if priority else TicketPriority.LOW.value
                status_val = int(status) if status else TicketStatus.OPEN.value
            except ValueError:
                return {"error": "Invalid value for source, priority, or status"}

            data: Dict[str, Any] = {
                "subject": subject,
                "description": description,
                "source": source_val,
                "priority": priority_val,
                "status": status_val,
            }
            if email:
                data["email"] = email
            if requester_id:
                data["requester_id"] = requester_id
            if custom_fields:
                data["custom_fields"] = custom_fields

            try:
                resp = await api_post("tickets", json=data)
                resp.raise_for_status()
                return {"success": True, "ticket": resp.json()}
            except Exception as e:
                return handle_error(e, "create ticket")

        # ---------- update ----------
        if action == "update":
            if not ticket_id:
                return {"error": "ticket_id is required for update action"}
            fields = ticket_fields or {}
            if priority is not None:
                fields["priority"] = int(priority)
            if status is not None:
                fields["status"] = int(status)
            if subject is not None:
                fields["subject"] = subject
            if description is not None:
                fields["description"] = description
            if custom_fields:
                fields["custom_fields"] = custom_fields
            if not fields:
                return {"error": "No fields provided for update"}
            try:
                resp = await api_put(f"tickets/{ticket_id}", json=fields)
                resp.raise_for_status()
                return {"success": True, "ticket": resp.json()}
            except Exception as e:
                return handle_error(e, "update ticket")

        # ---------- delete ----------
        if action == "delete":
            if not ticket_id:
                return {"error": "ticket_id is required for delete action"}
            try:
                resp = await api_delete(f"tickets/{ticket_id}")
                if resp.status_code == 204:
                    return {"success": True, "message": "Ticket deleted successfully"}
                return {"error": f"Unexpected status {resp.status_code}"}
            except Exception as e:
                return handle_error(e, "delete ticket")

        return {"error": f"Unknown action '{action}'. Valid: create, update, delete, get, list, filter, get_fields"}

    # ------------------------------------------------------------------ #
    #  manage_ticket_conversation                                         #
    # ------------------------------------------------------------------ #
    @mcp.tool()
    async def manage_ticket_conversation(
        action: str,
        ticket_id: Optional[int] = None,
        conversation_id: Optional[int] = None,
        body: Optional[str] = None,
        from_email: Optional[str] = None,
        user_id: Optional[int] = None,
        cc_emails: Optional[List[str]] = None,
        bcc_emails: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Manage ticket conversations — replies, notes, updates.

        Args:
            action: 'reply', 'add_note', 'update', 'list'
            ticket_id: Required for reply, add_note, list
            conversation_id: Required for update
            body: HTML body content (reply, add_note, update)
            from_email: Sender email (reply)
            user_id: Agent user ID (reply)
            cc_emails: CC email list (reply)
            bcc_emails: BCC email list (reply)
        """
        action = action.lower().strip()

        if action == "list":
            if not ticket_id:
                return {"error": "ticket_id required"}
            try:
                resp = await api_get(f"tickets/{ticket_id}/conversations")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "list conversations")

        if action == "reply":
            if not ticket_id or not body:
                return {"error": "ticket_id and body required for reply"}
            payload: Dict[str, Any] = {
                "body": body.strip(),
                "from_email": from_email or f"helpdesk@{FRESHSERVICE_DOMAIN}",
            }
            if user_id is not None:
                payload["user_id"] = user_id
            if cc_emails:
                payload["cc_emails"] = cc_emails
            if bcc_emails:
                payload["bcc_emails"] = bcc_emails
            try:
                resp = await api_post(f"tickets/{ticket_id}/reply", json=payload)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "reply to ticket")

        if action == "add_note":
            if not ticket_id or not body:
                return {"error": "ticket_id and body required for add_note"}
            try:
                resp = await api_post(f"tickets/{ticket_id}/notes", json={"body": body})
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "add ticket note")

        if action == "update":
            if not conversation_id or not body:
                return {"error": "conversation_id and body required for update"}
            try:
                resp = await api_put(f"conversations/{conversation_id}", json={"body": body})
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "update conversation")

        return {"error": f"Unknown action '{action}'. Valid: reply, add_note, update, list"}

    # ------------------------------------------------------------------ #
    #  manage_service_catalog                                             #
    # ------------------------------------------------------------------ #
    @mcp.tool()
    async def manage_service_catalog(
        action: str,
        ticket_id: Optional[int] = None,
        display_id: Optional[int] = None,
        email: Optional[str] = None,
        requested_for: Optional[str] = None,
        quantity: int = 1,
        page: int = 1,
        per_page: int = 30,
    ) -> Dict[str, Any]:
        """Service catalog operations.

        Args:
            action: 'list_items', 'get_requested_items', 'place_request'
            ticket_id: Ticket ID (get_requested_items)
            display_id: Service item display ID (place_request)
            email: Requester email (place_request)
            requested_for: Email of person for whom request is placed (place_request)
            quantity: Number of items (place_request, default 1)
            page: Page number (list_items)
            per_page: Items per page (list_items)
        """
        action = action.lower().strip()

        if action == "list_items":
            err = _validate_pagination(page, per_page)
            if err:
                return err
            all_items: List[Any] = []
            current_page = page
            try:
                while True:
                    resp = await api_get("service_catalog/items", params={"page": current_page, "per_page": per_page})
                    resp.raise_for_status()
                    all_items.append(resp.json())
                    pagination_info = parse_link_header(resp.headers.get("Link", ""))
                    if not pagination_info.get("next"):
                        break
                    current_page = pagination_info["next"]
                return {"success": True, "items": all_items}
            except Exception as e:
                return handle_error(e, "list service items")

        if action == "get_requested_items":
            if not ticket_id:
                return {"error": "ticket_id required"}
            try:
                # verify it's a service request first
                ticket_resp = await api_get(f"tickets/{ticket_id}")
                ticket_resp.raise_for_status()
                if ticket_resp.json().get("ticket", {}).get("type") != "Service Request":
                    return {"error": "Requested items can only be fetched for service requests"}
                resp = await api_get(f"tickets/{ticket_id}/requested_items")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "get requested items")

        if action == "place_request":
            if not display_id or not email:
                return {"error": "display_id and email required for place_request"}
            payload = {"email": email, "quantity": quantity}
            if requested_for:
                payload["requested_for"] = requested_for
            try:
                resp = await api_post(f"service_catalog/items/{display_id}/place_request", json=payload)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "place service request")

        return {"error": f"Unknown action '{action}'. Valid: list_items, get_requested_items, place_request"}
