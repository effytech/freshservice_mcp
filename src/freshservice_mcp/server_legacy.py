import os
import re   
import httpx
import logging
import base64
import json
import urllib.parse
from typing import Optional, Dict, Union, Any, List
from mcp.server.fastmcp import FastMCP 
from enum import IntEnum, Enum
from pydantic import BaseModel, Field 


from dotenv import load_dotenv 
load_dotenv()


# Set up logging
logging.basicConfig(level=logging.INFO)


# Create MCP INSTANCE
mcp = FastMCP("freshservice_mcp")


# API CREDENTIALS
FRESHSERVICE_DOMAIN = os.getenv("FRESHSERVICE_DOMAIN")
FRESHSERVICE_APIKEY = os.getenv("FRESHSERVICE_APIKEY")


class TicketSource(IntEnum):
    PHONE = 3
    EMAIL = 1
    PORTAL = 2
    CHAT = 7
    YAMMER = 6
    PAGERDUTY = 8
    AWS_CLOUDWATCH = 7
    WALK_UP = 9
    SLACK=10
    WORKPLACE = 12
    EMPLOYEE_ONBOARDING = 13
    ALERTS = 14
    MS_TEAMS = 15
    EMPLOYEE_OFFBOARDING = 18
    
class TicketStatus(IntEnum):
    OPEN = 2
    PENDING = 3
    RESOLVED = 4
    CLOSED = 5

class TicketPriority(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4

class ChangeStatus(IntEnum):
    OPEN = 1
    PLANNING = 2
    AWAITING_APPROVAL = 3
    PENDING_RELEASE = 4
    PENDING_REVIEW = 5
    CLOSED = 6

class ChangePriority(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4

class ChangeImpact(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3

class ChangeType(IntEnum):
    MINOR = 1
    STANDARD = 2
    MAJOR = 3
    EMERGENCY = 4

class ChangeRisk(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    VERY_HIGH = 4
    
class UnassignedForOptions(str, Enum):
    THIRTY_MIN = "30m"
    ONE_HOUR = "1h"
    TWO_HOURS = "2h"
    FOUR_HOURS = "4h"
    EIGHT_HOURS = "8h"
    TWELVE_HOURS = "12h"
    ONE_DAY = "1d"
    TWO_DAYS = "2d"
    THREE_DAYS = "3d"
    
class FilterRequestersSchema(BaseModel):
    query: str = Field(..., description="Main query string to filter requesters (e.g., first_name:'Vijay')")
    custom_fields: Optional[Dict[str, str]] = Field(default=None, description="Custom fields to filter (key-value pairs)")
    include_agents: Optional[bool] = Field(default=False, description="Include agents in the response")
    page: Optional[int] = Field(default=1, description="Page number for pagination (default is 1)")
    
class AgentInput(BaseModel):
    first_name: str = Field(..., description="First name of the agent")
    last_name: Optional[str] = Field(None, description="Last name of the agent")
    occasional: Optional[bool] = Field(False, description="True if the agent is an occasional agent")
    job_title: Optional[str] = Field(None, description="Job title of the agent")
    email:  Optional[str]= Field(..., description="Email address of the agent")
    work_phone_number: Optional[int] = Field(None, description="Work phone number of the agent")
    mobile_phone_number: Optional[int] = Field(None, description="Mobile phone number of the agent")
    
class GroupCreate(BaseModel):
    name: str = Field(..., description="Name of the group")
    description: Optional[str] = Field(None, description="Description of the group")
    agent_ids: Optional[List[int]] = Field(
        default=None,
        description="Array of agent user ids"
    )
    auto_ticket_assign: Optional[bool] = Field(
        default=False,
        description="Whether tickets are automatically assigned (true or false)"
    )
    escalate_to: Optional[int] = Field(
        None,
        description="User ID to whom escalation email is sent if ticket is unassigned"
    )
    unassigned_for: Optional[UnassignedForOptions] = Field(
        default=UnassignedForOptions.THIRTY_MIN,
        description="Time after which escalation email will be sent"
    )
    
def parse_link_header(link_header: str) -> Dict[str, Optional[int]]:
    """Parse the Link header to extract pagination information.
    
    Args:
        link_header: The Link header string from the response
        
    Returns:
        Dictionary containing next and prev page numbers
    """
    pagination = {
        "next": None,
        "prev": None
    }
    
    if not link_header:
        return pagination

   
    links = link_header.split(',')
    
    for link in links:
        match = re.search(r'<(.+?)>;\s*rel="(.+?)"', link)
        if match:
            url, rel = match.groups()
            page_match = re.search(r'page=(\d+)', url)
            if page_match:
                page_num = int(page_match.group(1))
                pagination[rel] = page_num

    return pagination

#GET TICKET FIELDS
@mcp.tool()
async def get_ticket_fields() -> Dict[str, Any]:
    """Get ticket fields from Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/ticket_form_fields"
    headers = get_auth_headers()
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        return response.json()
    
#GET TICKETS
@mcp.tool()
async def get_tickets(page: Optional[int] = 1, per_page: Optional[int] = 30) -> Dict[str, Any]:
    """Get tickets from Freshservice with pagination support."""
    
    if page < 1:
        return {"error": "Page number must be greater than 0"}
    
    if per_page < 1 or per_page > 100:
        return {"error": "Page size must be between 1 and 100"}

    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/tickets"
    
    params = {
        "page": page,
        "per_page": per_page
    }
    
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            link_header = response.headers.get('Link', '')
            pagination_info = parse_link_header(link_header)
            
            tickets = response.json()
            
            return {
                "tickets": tickets,
                "pagination": {
                    "current_page": page,
                    "next_page": pagination_info.get("next"),
                    "prev_page": pagination_info.get("prev"),
                    "per_page": per_page
                }
            }
            
        except httpx.HTTPStatusError as e:
            return {"error": f"Failed to fetch tickets: {str(e)}"}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}

#CREATE TICKET 
@mcp.tool()
async def create_ticket(
    subject: str,
    description: str,
    source: Union[int, str],
    priority: Union[int, str],
    status: Union[int, str],
    email: Optional[str] = None,
    requester_id: Optional[int] = None,
    custom_fields: Optional[Dict[str, Any]] = None
) -> str:
    """Create a ticket in Freshservice."""
    
    if not email and not requester_id:
        return "Error: Either email or requester_id must be provided"

    try:
        source_val = int(source)
        priority_val = int(priority)
        status_val = int(status)
    except ValueError:
        return "Error: Invalid value for source, priority, or status"

    if (source_val not in [e.value for e in TicketSource] or
        priority_val not in [e.value for e in TicketPriority] or
        status_val not in [e.value for e in TicketStatus]):
        return "Error: Invalid value for source, priority, or status"

    data = {
        "subject": subject,
        "description": description,
        "source": source_val,
        "priority": priority_val,
        "status": status_val
    }

    if email:
        data["email"] = email
    if requester_id:
        data["requester_id"] = requester_id

    if custom_fields:
        data["custom_fields"] = custom_fields

    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/tickets"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=data)
            response.raise_for_status()

            response_data = response.json()
            return f"Ticket created successfully: {response_data}"

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                error_data = e.response.json()
                if "errors" in error_data:
                    return f"Validation Error: {error_data['errors']}"
            return f"Error: Failed to create ticket - {str(e)}"
        except Exception as e:
            return f"Error: An unexpected error occurred - {str(e)}"

#UPDATE TICKET
@mcp.tool()
async def update_ticket(ticket_id: int, ticket_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Update a ticket in Freshservice."""
    if not ticket_fields:
        return {"error": "No fields provided for update"}

    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/tickets/{ticket_id}"
    headers = get_auth_headers()

    custom_fields = ticket_fields.pop('custom_fields', {})
    
    update_data = {}
    
    for field, value in ticket_fields.items():
        update_data[field] = value
    
    if custom_fields:
        update_data['custom_fields'] = custom_fields

    async with httpx.AsyncClient() as client:
        try:
            response = await client.put(url, headers=headers, json=update_data)
            response.raise_for_status()
            
            return {
                "success": True,
                "message": "Ticket updated successfully",
                "ticket": response.json()
            }
            
        except httpx.HTTPStatusError as e:
            error_message = f"Failed to update ticket: {str(e)}"
            try:
                error_details = e.response.json()
                if "errors" in error_details:
                    error_message = f"Validation errors: {error_details['errors']}"
            except Exception:
                pass
            return {
                "success": False,
                "error": error_message
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"An unexpected error occurred: {str(e)}"
            }
            
#FILTER TICKET 
@mcp.tool()
async def filter_tickets(query: str, page: int = 1, workspace_id: Optional[int] = None) -> Dict[str, Any]:
    """Filter the tickets in Freshservice.

    Args:
        query: Filter query string (e.g., "status:2 AND priority:1")
               Note: Some Freshservice endpoints may require queries to be wrapped in double quotes.
               If you get 500 errors, try wrapping your query in double quotes: "your_query_here"
        page: Page number (default: 1)
        workspace_id: Optional workspace ID filter
    """
    # Freshservice API requires the query to be wrapped in double quotes
    encoded_query = urllib.parse.quote(f'"{query}"')
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/tickets/filter?query={encoded_query}&page={page}"
    
    if workspace_id is not None:
        url += f"&workspace_id={workspace_id}"

    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}
        
#DELETE TICKET.
@mcp.tool()
async def delete_ticket(ticket_id: int) -> str:
    """Delete a ticket in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/tickets/{ticket_id}"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        response = await client.delete(url, headers=headers)

        if response.status_code == 204:
            # No content returned on successful deletion
            return "Ticket deleted successfully"
        elif response.status_code == 404:
            return "Error: Ticket not found"
        else:
            try:
                response_data = response.json()
                return f"Error: {response_data.get('error', 'Failed to delete ticket')}"
            except ValueError:
                return "Error: Unexpected response format"
    
#GET TICKET BY ID  
@mcp.tool()
async def get_ticket_by_id(ticket_id:int) -> Dict[str, Any]:
    """Get a ticket in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/tickets/{ticket_id}"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        response = await client.get(url,headers=headers)
        return response.json()
    
#GET ALL CHANGES
@mcp.tool()
async def get_changes(
    page: Optional[int] = 1, 
    per_page: Optional[int] = 30,
    query: Optional[str] = None,
    view: Optional[str] = None,
    sort: Optional[str] = None,
    order_by: Optional[str] = None,
    updated_since: Optional[str] = None,
    workspace_id: Optional[int] = None
) -> Dict[str, Any]:
    """Get all changes from Freshservice with pagination and filtering support.
    
    Args:
        page: Page number (default: 1)
        per_page: Number of items per page (1-100, default: 30)
        query: Filter query string (e.g., "priority:4 OR priority:3", "status:2 AND priority:1")
               **IMPORTANT**: Query must be wrapped in double quotes for filtering to work!
               Examples: "status:3", "approval_status:1 AND status:<6", "planned_start_date:>'2025-07-14'"
        view: Accepts the name or ID of views (e.g., 'my_open', 'unassigned')
        sort: Field to sort by (e.g., 'priority', 'created_at')
        order_by: Sort order ('asc' or 'desc', default: 'desc')
        updated_since: Changes updated since date (ISO format: '2024-10-19T02:00:00Z')
        workspace_id: Filter by workspace ID (0 for all workspaces)
        
    Query examples:
        - "priority:4 OR priority:3" - Urgent and High priority changes
        - "priority:>3 AND group_id:11 AND status:1" - High priority open changes for group 11
        - "status:2" - Open changes
        - "status:<6" - Not closed changes (statuses 1-5)
        - "approval_status:1" - Approved changes
        - "planned_end_date:<'2025-01-14'" - Changes with end date before specified date
        
    Note: Query and view parameters cannot be used together
    """
    
    if page < 1:
        return {"error": "Page number must be greater than 0"}
    
    if per_page < 1 or per_page > 100:
        return {"error": "Page size must be between 1 and 100"}

    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes"
    
    params = {
        "page": page,
        "per_page": per_page
    }
    
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
    
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            link_header = response.headers.get('Link', '')
            pagination_info = parse_link_header(link_header)
            
            changes = response.json()
            
            return {
                "changes": changes,
                "pagination": {
                    "current_page": page,
                    "next_page": pagination_info.get("next"),
                    "prev_page": pagination_info.get("prev"),
                    "per_page": per_page
                }
            }
            
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}

#GET CHANGE BY ID
@mcp.tool()
async def get_change_by_id(change_id: int) -> Dict[str, Any]:
    """Get a specific change by ID in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Failed to fetch change: {str(e)}"}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}

#CREATE CHANGE
@mcp.tool()
async def create_change(
    requester_id: int,
    subject: str,
    description: str,
    priority: Union[int, str],
    impact: Union[int, str],
    status: Union[int, str],
    risk: Union[int, str],
    change_type: Union[int, str],
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
    assets: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Create a new change in Freshservice.
    
    Args:
        requester_id: Unique identifier of the initiator of the change (MANDATORY)
        subject: Change subject (MANDATORY)
        description: HTML content of the change (MANDATORY)
        priority: Priority (1=Low, 2=Medium, 3=High, 4=Urgent) (MANDATORY)
        impact: Impact (1=Low, 2=Medium, 3=High) (MANDATORY)
        status: Status (1=Open, 2=Planning, 3=Awaiting Approval, 4=Pending Release, 5=Pending Review, 6=Closed) (MANDATORY)
        risk: Risk (1=Low, 2=Medium, 3=High, 4=Very High) (MANDATORY)
        change_type: Type (1=Minor, 2=Standard, 3=Major, 4=Emergency) (MANDATORY)
        group_id: Agent group ID
        agent_id: Agent ID
        department_id: Department ID
        category: Category of the change
        sub_category: Sub-category of the change
        item_category: Item category of the change
        planned_start_date: Planned start date (ISO format)
        planned_end_date: Planned end date (ISO format)
        reason_for_change: Planning field - Reason for change (text/HTML)
        change_impact: Planning field - Impact analysis (text/HTML)
        rollout_plan: Planning field - Rollout plan (text/HTML)
        backout_plan: Planning field - Backout plan (text/HTML)
        custom_fields: Custom fields key-value pairs
        assets: List of assets to associate, e.g. [{"display_id": 1}, {"display_id": 2}]
    """
    
    try:
        priority_val = int(priority)
        impact_val = int(impact)
        status_val = int(status)
        risk_val = int(risk)
        change_type_val = int(change_type)
    except ValueError:
        return {"error": "Invalid value for priority, impact, status, risk, or change_type"}

    if (priority_val not in [e.value for e in ChangePriority] or
        impact_val not in [e.value for e in ChangeImpact] or
        status_val not in [e.value for e in ChangeStatus] or
        risk_val not in [e.value for e in ChangeRisk] or
        change_type_val not in [e.value for e in ChangeType]):
        return {"error": "Invalid value for priority, impact, status, risk, or change_type"}

    data = {
        "requester_id": requester_id,
        "subject": subject,
        "description": description,
        "priority": priority_val,
        "impact": impact_val,
        "status": status_val,
        "risk": risk_val,
        "change_type": change_type_val
    }

    if group_id:
        data["group_id"] = group_id
    if agent_id:
        data["agent_id"] = agent_id
    if department_id:
        data["department_id"] = department_id
    if category:
        data["category"] = category
    if sub_category:
        data["sub_category"] = sub_category
    if item_category:
        data["item_category"] = item_category
    if planned_start_date:
        data["planned_start_date"] = planned_start_date
    if planned_end_date:
        data["planned_end_date"] = planned_end_date

    # Handle planning fields
    planning_fields = {}
    if reason_for_change:
        planning_fields["reason_for_change"] = {
            "description": reason_for_change
        }
    if change_impact:
        planning_fields["change_impact"] = {
            "description": change_impact
        }
    if rollout_plan:
        planning_fields["rollout_plan"] = {
            "description": rollout_plan
        }
    if backout_plan:
        planning_fields["backout_plan"] = {
            "description": backout_plan
        }
    
    if planning_fields:
        data["planning_fields"] = planning_fields

    if custom_fields:
        data["custom_fields"] = custom_fields

    if assets:
        data["assets"] = assets

    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                error_data = e.response.json()
                if "errors" in error_data:
                    return {"error": f"Validation Error: {error_data['errors']}"}
            return {"error": f"Failed to create change - {str(e)}"}
        except Exception as e:
            return {"error": f"An unexpected error occurred - {str(e)}"}

#UPDATE CHANGE
@mcp.tool()
async def update_change(
    change_id: int,
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
    assets: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Update an existing change in Freshservice.
    
    Args:
        change_id: The ID of the change to update
        subject: Change subject
        description: HTML content of the change
        priority: Priority (1=Low, 2=Medium, 3=High, 4=Urgent)
        impact: Impact (1=Low, 2=Medium, 3=High)
        status: Status (1=Open, 2=Planning, 3=Awaiting Approval, 4=Pending Release, 5=Pending Review, 6=Closed)
        risk: Risk (1=Low, 2=Medium, 3=High, 4=Very High)
        change_type: Type (1=Minor, 2=Standard, 3=Major, 4=Emergency)
        group_id: Agent group ID
        agent_id: Agent ID
        department_id: Department ID
        category: Category of the change
        sub_category: Sub-category of the change
        item_category: Item category of the change
        planned_start_date: Planned start date (ISO format)
        planned_end_date: Planned end date (ISO format)
        reason_for_change: Planning field - Reason for change (text/HTML)
        change_impact: Planning field - Impact analysis (text/HTML)
        rollout_plan: Planning field - Rollout plan (text/HTML)
        backout_plan: Planning field - Backout plan (text/HTML)
        custom_fields: Custom fields key-value pairs
        assets: List of assets to associate, e.g. [{"display_id": 1}, {"display_id": 2}]
    """
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}"
    headers = get_auth_headers()

    update_data = {}
    
    # Add regular fields if provided
    if subject is not None:
        update_data["subject"] = subject
    if description is not None:
        update_data["description"] = description
    if group_id is not None:
        update_data["group_id"] = group_id
    if agent_id is not None:
        update_data["agent_id"] = agent_id
    if department_id is not None:
        update_data["department_id"] = department_id
    if category is not None:
        update_data["category"] = category
    if sub_category is not None:
        update_data["sub_category"] = sub_category
    if item_category is not None:
        update_data["item_category"] = item_category
    if planned_start_date is not None:
        update_data["planned_start_date"] = planned_start_date
    if planned_end_date is not None:
        update_data["planned_end_date"] = planned_end_date
    
    # Handle enum fields with validation
    if priority is not None:
        try:
            update_data["priority"] = int(priority)
        except ValueError:
            return {"error": f"Invalid priority value: {priority}"}
    if impact is not None:
        try:
            update_data["impact"] = int(impact)
        except ValueError:
            return {"error": f"Invalid impact value: {impact}"}
    if status is not None:
        try:
            update_data["status"] = int(status)
        except ValueError:
            return {"error": f"Invalid status value: {status}"}
    if risk is not None:
        try:
            update_data["risk"] = int(risk)
        except ValueError:
            return {"error": f"Invalid risk value: {risk}"}
    if change_type is not None:
        try:
            update_data["change_type"] = int(change_type)
        except ValueError:
            return {"error": f"Invalid change_type value: {change_type}"}
    
    # Add custom fields if present
    if custom_fields:
        update_data["custom_fields"] = custom_fields
    
    # Add assets if present
    if assets:
        update_data["assets"] = assets
    
    # Handle planning fields
    planning_fields = {}
    if reason_for_change is not None:
        planning_fields["reason_for_change"] = {"description": reason_for_change}
    if change_impact is not None:
        planning_fields["change_impact"] = {"description": change_impact}
    if rollout_plan is not None:
        planning_fields["rollout_plan"] = {"description": rollout_plan}
    if backout_plan is not None:
        planning_fields["backout_plan"] = {"description": backout_plan}
    
    if planning_fields:
        update_data["planning_fields"] = planning_fields

    if not update_data:
        return {"error": "No fields provided for update"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.put(url, headers=headers, json=update_data)
            response.raise_for_status()
            
            return {
                "success": True,
                "message": "Change updated successfully",
                "change": response.json()
            }
            
        except httpx.HTTPStatusError as e:
            error_message = f"Failed to update change: {str(e)}"
            try:
                error_details = e.response.json()
                if "errors" in error_details:
                    error_message = f"Validation errors: {error_details['errors']}"
            except Exception:
                pass
            return {
                "success": False,
                "error": error_message
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"An unexpected error occurred: {str(e)}"
            }

#CLOSE CHANGE WITH RESULT
@mcp.tool()
async def close_change(
    change_id: int,
    change_result_explanation: str,
    custom_fields: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Close a change and provide the result explanation.
    This is a convenience function that updates status to Closed and sets the result explanation."""
    
    merged_custom_fields = {
        "change_result_explanation": change_result_explanation
    }
    
    # Merge additional custom fields if provided
    if custom_fields:
        merged_custom_fields.update(custom_fields)
    
    return await update_change(
        change_id=change_id,
        status=ChangeStatus.CLOSED.value,
        custom_fields=merged_custom_fields
    )

#DELETE CHANGE
@mcp.tool()
async def delete_change(change_id: int) -> str:
    """Delete a change in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        response = await client.delete(url, headers=headers)

        if response.status_code == 204:
            return "Change deleted successfully"
        elif response.status_code == 404:
            return "Error: Change not found"
        else:
            try:
                response_data = response.json()
                return f"Error: {response_data.get('error', 'Failed to delete change')}"
            except ValueError:
                return "Error: Unexpected response format"


# FILTER CHANGES
@mcp.tool()
async def filter_changes(
    query: str,
    page: int = 1,
    per_page: int = 30,
    sort: Optional[str] = None,
    order_by: Optional[str] = None,
    workspace_id: Optional[int] = None
) -> Dict[str, Any]:
    """Filter changes in Freshservice based on a query.
    
    Args:
        query: Filter query string (e.g., "status:2 AND priority:1" or "approval_status:1 AND planned_end_date:<'2025-01-14' AND status:<6")
               **CRITICAL**: Query must be wrapped in double quotes for filtering to work!
               Without quotes: status:3 → 500 Internal Server Error
               With quotes: "status:3" → Works perfectly
        page: Page number (default: 1)
        per_page: Number of items per page (1-100, default: 30)
        sort: Field to sort by
        order_by: Sort order ('asc' or 'desc')
        workspace_id: Optional workspace ID filter
        
    Common query examples:
        - "status:2" - Open changes
        - "status:<6" - Not closed changes (statuses 1-5)
        - "approval_status:1" - Approved changes
        - "planned_end_date:<'2025-01-14'" - Changes with end date before specified date
        - "priority:1 AND status:2" - High priority open changes
        - "approval_status:1 AND status:3" - Approved changes awaiting implementation
    """
    # Use the main get_changes function with query parameter
    # This is the correct approach since /api/v2/changes/filter doesn't exist
    return await get_changes(
        page=page,
        per_page=per_page,
        query=query,
        sort=sort,
        order_by=order_by,
        workspace_id=workspace_id
    )

#GET CHANGE TASKS
@mcp.tool()
async def get_change_tasks(change_id: int) -> Dict[str, Any]:
    """Get all tasks associated with a change."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}/tasks"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Failed to fetch change tasks: {str(e)}"}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}

#CREATE CHANGE NOTE
@mcp.tool()
async def create_change_note(change_id: int, body: str) -> Dict[str, Any]:
    """Create a note for a change in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}/notes"
    headers = get_auth_headers()
    data = {
        "body": body
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Failed to create change note: {str(e)}"}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}

# CHANGES APPROVAL ENDPOINTS

#CREATE CHANGE APPROVAL GROUP
@mcp.tool()
async def create_change_approval_group(
    change_id: int,
    name: str,
    approver_ids: List[int],
    approval_type: str = "everyone"
) -> Dict[str, Any]:
    """Create an approval group for a change.
    
    Args:
        change_id: The ID of the change
        name: Name of the approval group
        approver_ids: List of agent IDs who can approve
        approval_type: 'everyone' or 'any' (default: 'everyone')
    """
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}/approval_groups"
    headers = get_auth_headers()
    data = {
        "name": name,
        "approver_ids": approver_ids,
        "approval_type": approval_type
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}

#UPDATE CHANGE APPROVAL GROUP
@mcp.tool()
async def update_change_approval_group(
    change_id: int,
    group_id: int,
    name: Optional[str] = None,
    approver_ids: Optional[List[int]] = None,
    approval_type: Optional[str] = None
) -> Dict[str, Any]:
    """Update a change approval group."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}/approval_groups/{group_id}"
    headers = get_auth_headers()
    
    data = {}
    if name is not None:
        data["name"] = name
    if approver_ids is not None:
        data["approver_ids"] = approver_ids
    if approval_type is not None:
        data["approval_type"] = approval_type
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.put(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}

#CANCEL CHANGE APPROVAL GROUP
@mcp.tool()
async def cancel_change_approval_group(change_id: int, group_id: int) -> Dict[str, Any]:
    """Cancel a change approval group."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}/approval_groups/{group_id}/cancel"
    headers = get_auth_headers()
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.put(url, headers=headers)
            response.raise_for_status()
            return {"success": True, "message": "Approval group cancelled successfully"}
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}

#UPDATE APPROVAL CHAIN RULE FOR CHANGE
@mcp.tool()
async def update_approval_chain_rule_change(
    change_id: int,
    approval_chain_type: str = "parallel"
) -> Dict[str, Any]:
    """Update approval chain rule for a change.
    
    Args:
        change_id: The ID of the change
        approval_chain_type: Type of approval chain ('parallel' or 'sequential')
    """
    if approval_chain_type not in ["parallel", "sequential"]:
        return {"error": "approval_chain_type must be 'parallel' or 'sequential'"}
    
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}/approval_chain"
    headers = get_auth_headers()
    data = {"approval_chain_type": approval_chain_type}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.put(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}

#LIST CHANGE APPROVAL GROUPS
@mcp.tool()
async def list_change_approval_groups(change_id: int) -> Dict[str, Any]:
    """List all approval groups within a change."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}/approval_groups"
    headers = get_auth_headers()
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}

#VIEW CHANGE APPROVAL
@mcp.tool()
async def view_change_approval(change_id: int, approval_id: int) -> Dict[str, Any]:
    """View a specific change approval."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}/approvals/{approval_id}"
    headers = get_auth_headers()
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}

#LIST CHANGE APPROVALS
@mcp.tool()
async def list_change_approvals(change_id: int) -> Dict[str, Any]:
    """List all change approvals."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}/approvals"
    headers = get_auth_headers()
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}

#SEND CHANGE APPROVAL REMINDER
@mcp.tool()
async def send_change_approval_reminder(change_id: int, approval_id: int) -> Dict[str, Any]:
    """Send reminder for a change approval."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}/approvals/{approval_id}/resend_approval"
    headers = get_auth_headers()
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.put(url, headers=headers)
            response.raise_for_status()
            return {"success": True, "message": "Reminder sent successfully"}
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}

#CANCEL CHANGE APPROVAL
@mcp.tool()
async def cancel_change_approval(change_id: int, approval_id: int) -> Dict[str, Any]:
    """Cancel a change approval."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}/approvals/{approval_id}/cancel"
    headers = get_auth_headers()
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.put(url, headers=headers)
            response.raise_for_status()
            return {"success": True, "message": "Approval cancelled successfully"}
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}

# CHANGES NOTES ENDPOINTS

#VIEW CHANGE NOTE
@mcp.tool()
async def view_change_note(change_id: int, note_id: int) -> Dict[str, Any]:
    """View a specific note for a change."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}/notes/{note_id}"
    headers = get_auth_headers()
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}

#LIST CHANGE NOTES
@mcp.tool()
async def list_change_notes(change_id: int) -> Dict[str, Any]:
    """List all notes for a change."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}/notes"
    headers = get_auth_headers()
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}

#UPDATE CHANGE NOTE
@mcp.tool()
async def update_change_note(change_id: int, note_id: int, body: str) -> Dict[str, Any]:
    """Update a note for a change."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}/notes/{note_id}"
    headers = get_auth_headers()
    data = {"body": body}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.put(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}

#DELETE CHANGE NOTE
@mcp.tool()
async def delete_change_note(change_id: int, note_id: int) -> Dict[str, Any]:
    """Delete a note for a change."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}/notes/{note_id}"
    headers = get_auth_headers()
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.delete(url, headers=headers)
            if response.status_code == 204:
                return {"success": True, "message": "Note deleted successfully"}
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}

# CHANGES TASKS ENDPOINTS

#CREATE CHANGE TASK
@mcp.tool()
async def create_change_task(
    change_id: int,
    title: str,
    description: str,
    status: int = 1,
    priority: int = 1,
    assigned_to_id: Optional[int] = None,
    group_id: Optional[int] = None,
    due_date: Optional[str] = None
) -> Dict[str, Any]:
    """Create a task for a change."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}/tasks"
    headers = get_auth_headers()
    
    data = {
        "title": title,
        "description": description,
        "status": status,
        "priority": priority
    }
    
    if assigned_to_id:
        data["assigned_to_id"] = assigned_to_id
    if group_id:
        data["group_id"] = group_id
    if due_date:
        data["due_date"] = due_date
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}

#VIEW CHANGE TASK
@mcp.tool()
async def view_change_task(change_id: int, task_id: int) -> Dict[str, Any]:
    """View a specific task for a change."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}/tasks/{task_id}"
    headers = get_auth_headers()
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}

#UPDATE CHANGE TASK
@mcp.tool()
async def update_change_task(
    change_id: int,
    task_id: int,
    task_fields: Dict[str, Any]
) -> Dict[str, Any]:
    """Update a task for a change."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}/tasks/{task_id}"
    headers = get_auth_headers()
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.put(url, headers=headers, json=task_fields)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}

#DELETE CHANGE TASK
@mcp.tool()
async def delete_change_task(change_id: int, task_id: int) -> Dict[str, Any]:
    """Delete a task for a change."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}/tasks/{task_id}"
    headers = get_auth_headers()
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.delete(url, headers=headers)
            if response.status_code == 204:
                return {"success": True, "message": "Task deleted successfully"}
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}

# CHANGES TIME ENTRIES ENDPOINTS

#CREATE CHANGE TIME ENTRY
@mcp.tool()
async def create_change_time_entry(
    change_id: int,
    time_spent: str,
    note: str,
    agent_id: int,
    executed_at: Optional[str] = None
) -> Dict[str, Any]:
    """Create a time entry for a change.
    
    Args:
        change_id: The ID of the change
        time_spent: Time spent in format "hh:mm" (e.g., "02:30")
        note: Description of the work done
        agent_id: ID of the agent who performed the work
        executed_at: When the work was done (ISO format)
    """
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}/time_entries"
    headers = get_auth_headers()
    
    data = {
        "time_spent": time_spent,
        "note": note,
        "agent_id": agent_id
    }
    
    if executed_at:
        data["executed_at"] = executed_at
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}

#VIEW CHANGE TIME ENTRY
@mcp.tool()
async def view_change_time_entry(change_id: int, time_entry_id: int) -> Dict[str, Any]:
    """View a specific time entry for a change."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}/time_entries/{time_entry_id}"
    headers = get_auth_headers()
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}

#LIST CHANGE TIME ENTRIES
@mcp.tool()
async def list_change_time_entries(change_id: int) -> Dict[str, Any]:
    """List all time entries for a change."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}/time_entries"
    headers = get_auth_headers()
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}

#UPDATE CHANGE TIME ENTRY
@mcp.tool()
async def update_change_time_entry(
    change_id: int,
    time_entry_id: int,
    time_spent: Optional[str] = None,
    note: Optional[str] = None
) -> Dict[str, Any]:
    """Update a time entry for a change."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}/time_entries/{time_entry_id}"
    headers = get_auth_headers()
    
    data = {}
    if time_spent is not None:
        data["time_spent"] = time_spent
    if note is not None:
        data["note"] = note
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.put(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}

#DELETE CHANGE TIME ENTRY
@mcp.tool()
async def delete_change_time_entry(change_id: int, time_entry_id: int) -> Dict[str, Any]:
    """Delete a time entry for a change."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}/time_entries/{time_entry_id}"
    headers = get_auth_headers()
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.delete(url, headers=headers)
            if response.status_code == 204:
                return {"success": True, "message": "Time entry deleted successfully"}
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}

# OTHER CHANGES ENDPOINTS

#MOVE CHANGE
@mcp.tool()
async def move_change(change_id: int, workspace_id: int) -> Dict[str, Any]:
    """Move a change to another workspace."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/changes/{change_id}/move_workspace"
    headers = get_auth_headers()
    data = {"workspace_id": workspace_id}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.put(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}

#LIST CHANGE FIELDS
@mcp.tool()
async def list_change_fields() -> Dict[str, Any]:
    """List all change fields."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/change_form_fields"
    headers = get_auth_headers()
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}

#GET SERVICE ITEMS
@mcp.tool()
async def list_service_items(page: Optional[int] = 1, per_page: Optional[int] = 30) -> Dict[str, Any]:
    """Get list of service items from Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/service_catalog/items"

    if page < 1:
        return {"error": "Page number must be greater than 0"}
    if per_page < 1 or per_page > 100:
        return {"error": "Page size must be between 1 and 100"}

    headers = get_auth_headers()
    all_items: List[Dict[str, Any]] = []
    current_page = page

    async with httpx.AsyncClient() as client:
        while True:
            params = {
                "page": current_page,
                "per_page": per_page
            }

            try:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()

                data = response.json()
                all_items.append(data)  # Store the entire response for each page

                link_header = response.headers.get("Link", "")
                pagination_info = parse_link_header(link_header)

                if not pagination_info.get("next"):
                    break

                current_page = pagination_info["next"]

            except httpx.HTTPStatusError as e:
                return {"error": f"HTTP error occurred: {str(e)}"}
            except Exception as e:
                return {"error": f"Unexpected error: {str(e)}"}

    return {
        "success": True,
        "items": all_items,
        "pagination": {
            "starting_page": page,
            "per_page": per_page,
            "last_fetched_page": current_page
        }
    }
       
#GET REQUESTED ITEMS 
@mcp.tool()
async def get_requested_items(ticket_id: int) -> dict:
    """Fetch requested items for a specific ticket if the ticket is a service request."""
    
    async def get_ticket(ticket_id: int) -> dict:
        """Fetch ticket details by ticket ID to check the ticket type."""
        url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/tickets/{ticket_id}"
        headers = get_auth_headers()  

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()  
                ticket_data = response.json()
                
                # Check if the ticket type is a service request
                if ticket_data.get("ticket", {}).get("type") != "Service Request":
                    return {"success": False, "error": "Requested items can only be fetched for service requests"}
                
                # If ticket is a service request, proceed to fetch the requested items
                return {"success": True, "ticket_type": "Service Request"}
            
            except httpx.HTTPStatusError as e:
                return {"success": False, "error": f"HTTP error occurred: {str(e)}"}
            except Exception as e:
                return {"success": False, "error": f"An unexpected error occurred: {str(e)}"}

    # Step 1: Check if the ticket is a service request
    ticket_check = await get_ticket(ticket_id)
    
    if not ticket_check.get("success", False):
        return ticket_check  # If ticket fetching or type check failed, return the error message
    
    # Step 2: If the ticket is a service request, fetch the requested items
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/tickets/{ticket_id}/requested_items"
    headers = get_auth_headers()  # Use your existing method to get the headers

    async with httpx.AsyncClient() as client:
        try:
            # Send GET request to fetch requested items
            response = await client.get(url, headers=headers)
            response.raise_for_status()  # Will raise HTTPError for bad responses

            # If the response contains requested items, return them
            if response.status_code == 200:
                return response.json()

        except httpx.HTTPStatusError as e:
            # If a 400 error occurs, return a message saying no service items exist
            if e.response.status_code == 400:
                return {"success": False, "error": "There are no service items for this ticket"}
            return {"success": False, "error": f"HTTP error occurred: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"An unexpected error occurred: {str(e)}"}

#CREATE SERVICE REQUEST
@mcp.tool()
async def create_service_request(
    display_id: int,
    email: str,
    requested_for: Optional[str] = None,
    quantity: int = 1
) -> dict:
    """Create a service request in Freshservice."""
    if not isinstance(quantity, int) or quantity <= 0:
        return {"success": False, "error": "Quantity must be a positive integer."}

    if requested_for and "@" not in requested_for:
        return {"success": False, "error": "requested_for must be a valid email address."}

    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/service_catalog/items/{display_id}/place_request"

    payload = {
        "email": email,
        "quantity": quantity
    }

    if requested_for:
        payload["requested_for"] = requested_for

    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            error_message = f"Failed to place request: {str(e)}"
            try:
                error_details = e.response.json()
                return {"success": False, "error": error_details}
            except Exception:
                return {"success": False, "error": error_message}
        except Exception as e:
            return {"success": False, "error": str(e)}

#SEND TICKET REPLY
@mcp.tool()
async def send_ticket_reply(
    ticket_id: int,
    body: str,
    from_email: Optional[str] = None,
    user_id: Optional[int] = None,
    cc_emails: Optional[Union[str, List[str]]] = None,
    bcc_emails: Optional[Union[str, List[str]]] = None
) -> dict:
    """
    Send reply to a ticket in Freshservice."""

    # Validation
    if not ticket_id or not isinstance(ticket_id, int) or ticket_id < 1:
        return {"success": False, "error": "Invalid ticket_id: Must be an integer >= 1"}

    if not body or not isinstance(body, str) or not body.strip():
        return {"success": False, "error": "Missing or empty body: Reply content is required"}

    def parse_emails(value):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return []  # Invalid JSON format
        return value or []

    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/tickets/{ticket_id}/reply"

    payload = {
        "body": body.strip(),
        "from_email": from_email or f"helpdesk@{FRESHSERVICE_DOMAIN}",
    }

    if user_id is not None:
        payload["user_id"] = user_id

    parsed_cc = parse_emails(cc_emails)
    if parsed_cc:
        payload["cc_emails"] = parsed_cc

    parsed_bcc = parse_emails(bcc_emails)
    if parsed_bcc:
        payload["bcc_emails"] = parsed_bcc

    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"success": False, "error": f"HTTP error occurred: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"An unexpected error occurred: {str(e)}"}

#CREATE A Note
@mcp.tool()
async def create_ticket_note(ticket_id: int,body: str)-> Dict[str, Any]:
    """Create a note for a ticket in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/tickets/{ticket_id}/notes"
    headers = get_auth_headers()
    data = {
        "body": body
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=data)
        return response.json()
    
 #UPDATE A CONVERSATION

#UPDATE TICKET CONVERSATION
@mcp.tool()
async def update_ticket_conversation(conversation_id: int,body: str)-> Dict[str, Any]:
    """Update a conversation for a ticket in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/conversations/{conversation_id}"
    headers = get_auth_headers()
    data = {
        "body": body
    }
    async with httpx.AsyncClient() as client:
        response = await client.put(url, headers=headers, json=data)
        status_code = response.status_code
        if status_code == 200:
            return response.json()
        else:
            return f"Cannot update conversation ${response.json()}"
        
#GET ALL TICKET CONVERSATION
@mcp.tool()
async def list_all_ticket_conversation(ticket_id: int)-> Dict[str, Any]:
    """List all conversation of a ticket in freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/tickets/{ticket_id}/conversations"
    headers = get_auth_headers()
   
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        status_code = response.status_code
        if status_code == 200:
            return response.json()
        else:
            return f"Cannot fetch ticket conversations ${response.json()}"
        
#GET ALL PRODUCTS
@mcp.tool()
async def get_all_products(page: Optional[int] = 1, per_page: Optional[int] = 30) -> Dict[str, Any]:
    """List all the products from Freshservice."""
    if page < 1:
        return {"error": "Page number must be greater than 0"}
    
    if per_page < 1 or per_page > 100:
        return {"error": "Page size must be between 1 and 100"}

    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/products"
    headers = get_auth_headers()

    params = {
        "page": page,
        "per_page": per_page
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()

            data = response.json()
            products = data.get("products", [])

            link_header = response.headers.get("Link", "")
            pagination_info = parse_link_header(link_header)
            next_page = pagination_info.get("next")

            return {
                "success": True,
                "products": products,
                "pagination": {
                    "current_page": page,
                    "next_page": next_page,
                    "has_next": bool(next_page),
                    "per_page": per_page
                }
            }

        except httpx.HTTPStatusError as e:
            return {"success": False, "error": f"HTTP error occurred: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error occurred: {str(e)}"}
        
#GET PRODUCT BY ID
@mcp.tool()
async def get_products_by_id(product_id:int)-> Dict[str, Any]:
    """Get product by product ID in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/products/{product_id}"
    headers = get_auth_headers()
   
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        status_code = response.status_code
        if status_code == 200:
            return response.json()
        else:
            return f"Cannot fetch products from the freshservice ${response.json()}"
        
#CREATE PRODUCT
@mcp.tool()
async def create_product(
    name: str,
    asset_type_id: int,
    manufacturer: Optional[str] = None,
    status: Optional[Union[str, int]] = None,
    mode_of_procurement: Optional[str] = None,
    depreciation_type_id: Optional[int] = None,
    description: Optional[str] = None,
    description_text: Optional[str] = None
) -> Dict[str, Any]:
    """Create a product in Freshservice."""

    # Allowed statuses mapping
    allowed_statuses = {
        "In Production": "In Production",
        "In Pipeline": "In Pipeline",
        "Retired": "Retired",
        1: "In Production",
        2: "In Pipeline",
        3: "Retired"
    }

    # Validate status
    if status is not None:
        if status not in allowed_statuses:
            return {
                "success": False,
                "error": (
                    "Invalid 'status'. It should be one of: "
                    "[\"In Production\", 1], [\"In Pipeline\", 2], [\"Retired\", 3]"
                )
            }
        status = allowed_statuses[status]

    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/products"
    headers = get_auth_headers()

    payload = {
        "name": name,
        "asset_type_id": asset_type_id
    }

    if manufacturer:
        payload["manufacturer"] = manufacturer
    if status:
        payload["status"] = status
    if mode_of_procurement:
        payload["mode_of_procurement"] = mode_of_procurement
    if depreciation_type_id:
        payload["depreciation_type_id"] = depreciation_type_id
    if description:
        payload["description"] = description
    if description_text:
        payload["description_text"] = description_text

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return {"success": True, "data": response.json()}
        except httpx.HTTPStatusError as http_err:
            return {
                "success": False,
                "status_code": response.status_code,
                "error": f"HTTP error occurred: {http_err}",
                "response": response.json()
            }
        except Exception as err:
            return {
                "success": False,
                "error": f"An unexpected error occurred: {err}"
            }

#UPDATE PRODUCT 
@mcp.tool()
async def update_product(
    id: int,
    name: str,
    asset_type_id: int,
    manufacturer: Optional[str] = None,
    status: Optional[Union[str, int]] = None,
    mode_of_procurement: Optional[str] = None,
    depreciation_type_id: Optional[int] = None,
    description: Optional[str] = None,
    description_text: Optional[str] = None
) -> Dict[str, Any]:
    """Update a product in Freshservice."""

    allowed_statuses = {
        "In Production": "In Production",
        "In Pipeline": "In Pipeline",
        "Retired": "Retired",
        1: "In Production",
        2: "In Pipeline",
        3: "Retired"
    }

    if status is not None:
        if status not in allowed_statuses:
            return {
                "success": False,
                "error": (
                    "Invalid 'status'. It should be one of: "
                    "[\"In Production\", 1], [\"In Pipeline\", 2], [\"Retired\", 3]"
                )
            }
        status = allowed_statuses[status]

    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/products/{id}"
    headers = get_auth_headers()

    payload = {
        "name": name,
        "asset_type_id": asset_type_id
    }

    # Optional updates
    if manufacturer:
        payload["manufacturer"] = manufacturer
    if status:
        payload["status"] = status
    if mode_of_procurement:
        payload["mode_of_procurement"] = mode_of_procurement
    if depreciation_type_id:
        payload["depreciation_type_id"] = depreciation_type_id
    if description:
        payload["description"] = description
    if description_text:
        payload["description_text"] = description_text

    async with httpx.AsyncClient() as client:
        try:
            response = await client.put(url, headers=headers, json=payload)
            response.raise_for_status()
            return {"success": True, "data": response.json()}
        except httpx.HTTPStatusError as http_err:
            return {
                "success": False,
                "status_code": response.status_code,
                "error": f"HTTP error occurred: {http_err}",
                "response": response.json()
            }
        except Exception as err:
            return {
                "success": False,
                "error": f"Unexpected error occurred: {err}"
            }
        
#CREATE REQUESTER
@mcp.tool()
async def create_requester(
    first_name: str,
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
    time_format: Optional[str] = None,  # "12h" or "24h"
    language: Optional[str] = None,
    location_id: Optional[int] = None,
    background_information: Optional[str] = None,
    custom_fields: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Creates a requester in Freshservice."""

    if not isinstance(first_name, str) or not first_name.strip():
        return {"success": False, "error": "'first_name' must be a non-empty string."}

    if not (primary_email or work_phone_number or mobile_phone_number):
        return {
            "success": False,
            "error": "At least one of 'primary_email', 'work_phone_number', or 'mobile_phone_number' is required."
        }

    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/requesters"
    headers = get_auth_headers()

    payload: Dict[str, Any] = {
        "first_name": first_name.strip()
    }

    # Add optional fields if provided
    optional_fields = {
        "last_name": last_name,
        "job_title": job_title,
        "primary_email": primary_email,
        "secondary_emails": secondary_emails,
        "work_phone_number": work_phone_number,
        "mobile_phone_number": mobile_phone_number,
        "department_ids": department_ids,
        "can_see_all_tickets_from_associated_departments": can_see_all_tickets_from_associated_departments,
        "reporting_manager_id": reporting_manager_id,
        "address": address,
        "time_zone": time_zone,
        "time_format": time_format,
        "language": language,
        "location_id": location_id,
        "background_information": background_information,
        "custom_fields": custom_fields
    }

    payload.update({k: v for k, v in optional_fields.items() if v is not None})

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return {"success": True, "data": response.json()}

        except httpx.HTTPStatusError as http_err:
            return {
                "success": False,
                "status_code": response.status_code,
                "error": f"HTTP error: {http_err}",
                "response": response.json()
            }
        except Exception as err:
            return {
                "success": False,
                "error": f"Unexpected error: {err}"
            }
            
#GET ALL REQUESTER
@mcp.tool()
async def get_all_requesters(page: int = 1, per_page: int = 30) -> Dict[str, Any]:
    """Fetch all requesters from Freshservice."""
    if page < 1:
        return {"success": False, "error": "Page number must be greater than 0"}
    
    if per_page < 1 or per_page > 100:
        return {"success": False, "error": "Page size must be between 1 and 100"}

    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/requesters"
    headers = get_auth_headers()
    params = {"page": page, "per_page": per_page}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()

            data = response.json()
            requesters = data.get("requesters", [])

            link_header = response.headers.get("Link", "")
            pagination_info = parse_link_header(link_header)

            return {
                "success": True,
                "requesters": requesters,
                "pagination": {
                    "current_page": page,
                    "per_page": per_page,
                    "next_page": pagination_info.get("next"),
                    "prev_page": pagination_info.get("prev"),
                    "has_more": pagination_info.get("next") is not None
                }
            }
        except httpx.HTTPStatusError as e:
            return {"success": False, "error": f"HTTP error: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {str(e)}"}

#GET REQUESTERS BY ID
@mcp.tool()
async def get_requester_id(requester_id:int)-> Dict[str, Any]:
    """Get requester by ID in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/requesters/{requester_id}"
    headers = get_auth_headers()
   
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        status_code = response.status_code
        if status_code == 200:
            return response.json()
        else:
            return f"Cannot fetch requester from the freshservice ${response.json()}"

#LIST ALL REQUESTER FIELDS
@mcp.tool()
async def list_all_requester_fields()-> Dict[str, Any]:
    """List all requester fields in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/requester_fields"
    headers = get_auth_headers()
   
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        status_code = response.status_code
        if status_code == 200:
            return response.json()
        else:
            return f"Cannot fetch requester from the freshservice ${response.json()}"
        
#UPDATE REQUESTER
@mcp.tool()
async def update_requester(
    requester_id: int,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    job_title: Optional[str] = None,
    primary_email: Optional[str] = None,
    secondary_emails: Optional[List[str]] = None,
    work_phone_number: Optional[int] = None,
    mobile_phone_number: Optional[int] = None,
    department_ids: Optional[List[int]] = None,
    can_see_all_tickets_from_associated_departments: Optional[bool] = False,
    reporting_manager_id: Optional[int] = None,
    address: Optional[str] = None,
    time_zone: Optional[str] = None,
    time_format: Optional[str] = None,
    language: Optional[str] = None,
    location_id: Optional[int] = None,
    background_information: Optional[str] = None,
    custom_fields: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Update a requester in Freshservice."""

    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/requesters/{requester_id}"
    headers = get_auth_headers()

    payload = {
        "first_name": first_name,
        "last_name": last_name,
        "job_title": job_title,
        "primary_email": primary_email,
        "secondary_emails": secondary_emails,
        "work_phone_number": work_phone_number,
        "mobile_phone_number": mobile_phone_number,
        "department_ids": department_ids,
        "can_see_all_tickets_from_associated_departments": can_see_all_tickets_from_associated_departments,
        "reporting_manager_id": reporting_manager_id,
        "address": address,
        "time_zone": time_zone,
        "time_format": time_format,
        "language": language,
        "location_id": location_id,
        "background_information": background_information,
        "custom_fields": custom_fields
    }

    data = {k: v for k, v in payload.items() if v is not None}

    async with httpx.AsyncClient() as client:
        response = await client.put(url, headers=headers, json=data)
        if response.status_code == 200:
            return response.json()
        else:
            return {"success": False, "error": response.text, "status_code": response.status_code}   
        
#FILTER REQUESTERS
@mcp.tool()
async def filter_requesters(query: str,include_agents: bool = False) -> Dict[str, Any]:
    """Filter requesters in Freshservice."""
    encoded_query = urllib.parse.quote(query)
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/requesters?query={encoded_query}"
    
    if include_agents:
        url += "&include_agents=true"

    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            return {
                "error": f"Failed to filter requesters: {response.status_code}",
                "details": response.text
            }

#CREATE AN AGENT
@mcp.tool()
async def create_agent(
    first_name: str,
    email: str = None,
    last_name: Optional[str] = None,
    occasional: Optional[bool] = False,
    job_title: Optional[str] = None,
    work_phone_number: Optional[int] = None,
    mobile_phone_number: Optional[int] = None,
) -> Dict[str, Any]:
    """Create a new agent in Freshservice."""
    
    data = AgentInput(
        first_name=first_name,
        last_name=last_name,
        occasional=occasional,
        job_title=job_title,
        email=email,
        work_phone_number=work_phone_number,
        mobile_phone_number=mobile_phone_number
    ).dict(exclude_none=True)

    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/agents"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=data)
        if response.status_code == 200 or response.status_code == 201:
            return response.json()
        else:
            return {
                "error": f"Failed to create agent",
                "status_code": response.status_code,
                "details": response.json()
            }

#GET AN AGENT
@mcp.tool()
async def get_agent(agent_id:int)-> Dict[str, Any]:
    """Get agent by id in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/agents/{agent_id}"
    headers = get_auth_headers()
   
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        status_code = response.status_code
        if status_code == 200:
            return response.json()
        else:
            return f"Cannot fetch requester from the freshservice ${response.json()}"
            
#GET ALL AGENTS
@mcp.tool()
async def get_all_agents(page: int = 1, per_page: int = 30) -> Dict[str, Any]:
    """Fetch agents from Freshservice."""
    if page < 1:
        return {"success": False, "error": "Page number must be greater than 0"}

    if per_page < 1 or per_page > 100:
        return {"success": False, "error": "Page size must be between 1 and 100"}

    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/agents"
    headers = get_auth_headers()
    params = {"page": page, "per_page": per_page}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()

            data = response.json()
            agents = data.get("agents", [])

            # Parse pagination info from Link header
            link_header = response.headers.get("Link", "")
            pagination_info = parse_link_header(link_header)

            return {
                "success": True,
                "agents": agents,
                "pagination": {
                    "current_page": page,
                    "per_page": per_page,
                    "next_page": pagination_info.get("next"),
                    "prev_page": pagination_info.get("prev"),
                    "has_more": pagination_info.get("next") is not None
                }
            }
        except httpx.HTTPStatusError as e:
            error_text = None
            try:
                error_text = e.response.json() if e.response else None
            except Exception:
                error_text = e.response.text if e.response else None

            return {
                "error": f"Failed to get all agents: {str(e)}",
                "status_code": e.response.status_code if e.response else None,
                "details": error_text
            }
            
#FILTER AGENTS
@mcp.tool()
async def filter_agents(query: str) -> List[Dict[str, Any]]:
    """Filter Freshservice agents based on a query."""
    base_url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/agents"
    headers = get_auth_headers()
    all_agents = []
    page = 1
    # Freshservice API requires the query to be wrapped in double quotes
    encoded_query = urllib.parse.quote(f'"{query}"')

    async with httpx.AsyncClient() as client:
        while True:
            url = f"{base_url}?query={encoded_query}&page={page}"
            response = await client.get(url, headers=headers)
            response.raise_for_status()

            data = response.json()
            all_agents.extend(data.get("agents", []))

            link_header = response.headers.get("link")
            pagination = parse_link_header(link_header)

            if not pagination.get("next"):
                break
            page = pagination["next"]

    return all_agents

#UPDATE AGENT
@mcp.tool()
async def update_agent(agent_id, occasional=None, email=None, department_ids=None, 
                 can_see_all_tickets_from_associated_departments=None, reporting_manager_id=None, 
                 address=None, time_zone=None, time_format=None, language=None, 
                 location_id=None, background_information=None, scoreboard_level_id=None):
    """Update the agent details in the Freshservice."""
    
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/agents/{agent_id}"
    headers = get_auth_headers()
    
    payload = {
        "occasional": occasional,
        "email": email,
        "department_ids": department_ids,
        "can_see_all_tickets_from_associated_departments": can_see_all_tickets_from_associated_departments,
        "reporting_manager_id": reporting_manager_id,
        "address": address,
        "time_zone": time_zone,
        "time_format": time_format,
        "language": language,
        "location_id": location_id,
        "background_information": background_information,
        "scoreboard_level_id": scoreboard_level_id
    }
    
    payload = {k: v for k, v in payload.items() if v is not None}
    
    async with httpx.AsyncClient() as client:
        response = await client.put(url, headers=headers,json=payload)
        status_code = response.status_code
        if status_code == 200:
            return response.json()
        else:
            return f"Cannot fetch agents from the freshservice ${response.json()}"
                      
#GET AGENT FIELDS
@mcp.tool()
async def get_agent_fields()-> Dict[str, Any]:
    """Get all agent fields in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/agent_fields"
    headers = get_auth_headers()
   
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        status_code = response.status_code
        if status_code == 200:
            return response.json()
        else:
            return f"Cannot fetch agents from the freshservice ${response.json()}"
        
#GET ALL AGENT GROUPS
@mcp.tool()
async def get_all_agent_groups()-> Dict[str, Any]:
    """Get all agent groups in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/groups"
    headers = get_auth_headers()
   
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        status_code = response.status_code
        if status_code == 200:
            return response.json()
        else:
            return f"Cannot fetch agents from the freshservice ${response.json()}"
        
#GET AGENT GROUP BY ID
@mcp.tool()
async def getAgentGroupById(group_id:int)-> Dict[str, Any]:
    """Get agent groups by its group id in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/groups/{group_id}"
    headers = get_auth_headers()
   
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        status_code = response.status_code
        if status_code == 200:
            return response.json()
        else:
            return f"Cannot fetch agents from the freshservice ${response.json()}"
        
#ADD REQUESTER TO GROUP
@mcp.tool()
async def add_requester_to_group(
    group_id: int,
    requester_id: int
) -> Dict[str, Any]:
    """Add a requester to a manual requester group in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/requester_groups/{group_id}/members/{requester_id}"
    headers = get_auth_headers()  

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers)
            response.raise_for_status() 

            return {"success": f"Requester {requester_id} added to group {group_id}."}

        except httpx.HTTPStatusError as e:
            error_text = None
            try:
                error_text = e.response.json() if e.response else None
            except Exception:
                error_text = e.response.text if e.response else None

            return {
                "error": f"Failed to add requester to group: {str(e)}",
                "status_code": e.response.status_code if e.response else None,
                "details": error_text
            }
        
#CREATE GROUP
@mcp.tool()
async def create_group(group_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a group in Freshservice."""
    if "name" not in group_data:
        return {"error": "Field 'name' is required to create a group."}

    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/groups"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=group_data)
            response.raise_for_status()
            return response.json()
        
        except httpx.HTTPStatusError as e:
            error_text = None
            try:
                error_text = e.response.json() if e.response else None
            except Exception:
                error_text = e.response.text if e.response else None

            return {
                "error": f"Failed to create group: {str(e)}",
                "status_code": e.response.status_code if e.response else None,
                "details": error_text
            }
        
#UPDATE GROUP
@mcp.tool()
async def update_group(group_id: int, group_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Update a group in Freshservice."""
    try:
        validated_fields = GroupCreate(**group_fields)
        group_data = validated_fields.model_dump(exclude_none=True)
    except Exception as e:
        return {"error": f"Validation error: {str(e)}"}
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/groups/{group_id}"
    headers = get_auth_headers()
    async with httpx.AsyncClient() as client:
        try:
            response = await client.put(url, headers=headers, json=group_data)
            response.raise_for_status()
            return response.json()
        
        except httpx.HTTPStatusError as e:
            error_text = None
            try:
                error_text = e.response.json() if e.response else None
            except Exception:
                error_text = e.response.text if e.response else None

            return {
                "error": f"Failed to update group: {str(e)}",
                "status_code": e.response.status_code if e.response else None,
                "details": error_text
            }
            
#GET ALL REQUETER GROUPS 
@mcp.tool()
async def get_all_requester_groups(page: Optional[int] = 1, per_page: Optional[int] = 30) -> Dict[str, Any]:
    """Get all requester groups in Freshservice."""
    if page < 1:
        return {"error": "Page number must be greater than 0"}
    
    if per_page < 1 or per_page > 100:
        return {"error": "Page size must be between 1 and 100"}

    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/requester_groups"
    headers = get_auth_headers()

    params = {
        "page": page,
        "per_page": per_page
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()

            # Parse the Link header for pagination info
            link_header = response.headers.get('Link', '')
            pagination_info = parse_link_header(link_header)

            data = response.json()

            return {
                "success": True,
                "requester_groups": data,
                "pagination": {
                    "current_page": page,
                    "next_page": pagination_info.get("next"),
                    "prev_page": pagination_info.get("prev"),
                    "per_page": per_page
                }
            }

        except httpx.HTTPStatusError as e:
            return {"error": f"Failed to fetch all requester groups: {str(e)}"}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}
        
#GET REQUETER GROUPS BY ID
@mcp.tool()
async def get_requester_groups_by_id(requester_group_id:int)-> Dict[str, Any]:
    """Get requester groups in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/requester_groups/{requester_group_id}"
    headers = get_auth_headers()
   
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        status_code = response.status_code
        if status_code == 200:
            return response.json()
        else:
            return f"Cannot fetch requester group from the freshservice ${response.json()}"
        
#CREATE REQUESTER GROUP
@mcp.tool()
async def create_requester_group(
    name: str,
    description: Optional[str] = None
) -> Dict[str, Any]:
    """Create a requester group in Freshservice."""
    group_data = {"name": name}
    if description:
        group_data["description"] = description

    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/requester_groups"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=group_data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            error_text = None
            try:
                error_text = e.response.json() if e.response else None
            except Exception:
                error_text = e.response.text if e.response else None

            return {
                "error": f"Failed to create requester group: {str(e)}",
                "status_code": e.response.status_code if e.response else None,
                "details": error_text
            }

        except Exception as e:
            return {
                "error": f"Unexpected error occurred: {str(e)}"
            }
            
#UPDATE REQUESTER GROUP
@mcp.tool()
async def update_requester_group(id: int,name: Optional[str] = None,description: Optional[str] = None) -> Dict[str, Any]:
    """Update an requester group in Freshservice."""
    group_data = {}
    if name:
        group_data["name"] = name
    if description:
        group_data["description"] = description

    if not group_data:
        return {"error": "At least one field (name or description) must be provided to update."}

    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/requester_groups/{id}"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.put(url, headers=headers, json=group_data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            error_text = None
            try:
                error_text = e.response.json() if e.response else None
            except Exception:
                error_text = e.response.text if e.response else None

            return {
                "error": f"Failed to update requester group: {str(e)}",
                "status_code": e.response.status_code if e.response else None,
                "details": error_text
            }
            
#GET LIST OF REQUESTER GROUP MEMBERS
@mcp.tool()
async def list_requester_group_members(
    group_id: int
) -> Dict[str, Any]:
    """List all members of a requester group in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/requester_groups/{group_id}/members"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status() 

            return response.json()

        except httpx.HTTPStatusError as e:
            error_text = None
            try:
                error_text = e.response.json() if e.response else None
            except Exception:
                error_text = e.response.text if e.response else None

            return {
                "error": f"Failed to fetch list of requester group memebers: {str(e)}",
                "status_code": e.response.status_code if e.response else None,
                "details": error_text
            }

        except Exception as e:
            return {
                "error": f"Unexpected error occurred: {str(e)}"
            }
            
#GET ALL CANNED RESPONSES
@mcp.tool()
async def get_all_canned_response() -> Dict[str, Any]:
    """List all canned response in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/canned_responses"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()  # Will raise an exception for 4xx/5xx responses

            # Return the response JSON (list of members)
            return response.json()

        except httpx.HTTPStatusError as e:
            error_text = None
            try:
                error_text = e.response.json() if e.response else None
            except Exception:
                error_text = e.response.text if e.response else None

            return {
                "error": f"Failed to get all canned response folder: {str(e)}",
                "status_code": e.response.status_code if e.response else None,
                "details": error_text
            }

        except Exception as e:
            return {
                "error": f"Unexpected error occurred: {str(e)}"
            }

#GET CANNED RESPONSE BY ID
@mcp.tool()
async def get_canned_response(
    id: int
) -> Dict[str, Any]:
    """Get a canned response in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/canned_responses/{id}"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()  # Will raise HTTPStatusError for 4xx/5xx responses

            # Only parse JSON if the response is not empty
            if response.content:
                return response.json()
            else:
                return {"error": "No content returned for the requested canned response."}

        except httpx.HTTPStatusError as e:
            # Handle specific HTTP errors like 404, 403, etc.
            if e.response.status_code == 404:
                return {"error": "Canned response not found (404)"}
            else:
                return {
                    "error": f"Failed to retrieve canned response: {str(e)}",
                    "details": e.response.json() if e.response else None
                }

        except Exception as e:
            return {"error": f"Unexpected error: {str(e)}"}

#LIST ALL CANNED RESPONSE FOLDER            
@mcp.tool()
async def list_all_canned_response_folder() -> Dict[str, Any]:
    """List all canned response of a folder in Freshservice."""
    
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/canned_response_folders"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()  

            return response.json()

        except httpx.HTTPStatusError as e:
            error_text = None
            try:
                error_text = e.response.json() if e.response else None
            except Exception:
                error_text = e.response.text if e.response else None

            return {
                "error": f"Failed to list all canned response folder: {str(e)}",
                "status_code": e.response.status_code if e.response else None,
                "details": error_text
            }

        except Exception as e:
            return {
                "error": f"Unexpected error occurred: {str(e)}"
            }
            
#LIST CANNED RESPONSE FOLDER
@mcp.tool()
async def list_canned_response_folder(
    id: int
) -> Dict[str, Any]:
    """List canned response folder in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/canned_response_folders/{id}"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status() 

            return response.json()

        except httpx.HTTPStatusError as e:
            error_text = None
            try:
                error_text = e.response.json() if e.response else None
            except Exception:
                error_text = e.response.text if e.response else None

            return {
                "error": f"Failed to list canned response folder: {str(e)}",
                "status_code": e.response.status_code if e.response else None,
                "details": error_text
            }

        except Exception as e:
            return {
                "error": f"Unexpected error occurred: {str(e)}"
            }
            
#GET ALL WORKSPACES
@mcp.tool()
async def list_all_workspaces() -> Dict[str, Any]:
    """List all workspaces in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/workspaces"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()  

            return response.json()

        except httpx.HTTPStatusError as e:
            error_text = None
            try:
                error_text = e.response.json() if e.response else None
            except Exception:
                error_text = e.response.text if e.response else None

            return {
                "error": f"Failed to fetch list of solution workspaces: {str(e)}",
                "status_code": e.response.status_code if e.response else None,
                "details": error_text
            }

        except Exception as e:
            return {
                "error": f"Unexpected error occurred: {str(e)}"
            }

#GET WORKSPACE
@mcp.tool()
async def get_workspace(id: int) -> Dict[str, Any]:
    """Get a workspace by its ID in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/workspaces/{id}"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()  

            return response.json()

        except httpx.HTTPStatusError as e:
            error_text = None
            try:
                error_text = e.response.json() if e.response else None
            except Exception:
                error_text = e.response.text if e.response else None

            return {
                "error": f"Failed to fetch workspace: {str(e)}",
                "status_code": e.response.status_code if e.response else None,
                "details": error_text
            }

        except Exception as e:
            return {
                "error": f"Unexpected error occurred: {str(e)}"
            }
            
#GET ALL SOLUTION CATEGORY
@mcp.tool()
async def get_all_solution_category() -> Dict[str, Any]:
    """Get all solution category in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/solutions/categories"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()  

            return response.json()

        except httpx.HTTPStatusError as e:
            error_text = None
            try:
                error_text = e.response.json() if e.response else None
            except Exception:
                error_text = e.response.text if e.response else None

            return {
                "error": f"Failed to get all solution category: {str(e)}",
                "status_code": e.response.status_code if e.response else None,
                "details": error_text
            }

        except Exception as e:
            return {
                "error": f"Unexpected error occurred: {str(e)}"
            }
            
#GET SOLUTION CATEGORY
@mcp.tool()
async def get_solution_category(id: int) -> Dict[str, Any]:
    """Get solution category by its ID in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/solutions/categories/{id}"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()  

            return response.json()

        except httpx.HTTPStatusError as e:
            error_text = None
            try:
                error_text = e.response.json() if e.response else None
            except Exception:
                error_text = e.response.text if e.response else None

            return {
                "error": f"Failed to get solution category: {str(e)}",
                "status_code": e.response.status_code if e.response else None,
                "details": error_text
            }

        except Exception as e:
            return {
                "error": f"Unexpected error occurred: {str(e)}"
            }
            
#CREATE SOLUTION CATEGORY
@mcp.tool()
async def create_solution_category(
    name: str,
    description: str = None,
    workspace_id: int = None,
) -> Dict[str, Any]:
    """Create a new solution category in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/solutions/categories"
    headers = get_auth_headers()

    category_data = {
        "name": name,
        "description": description,
        "workspace_id": workspace_id,
    }

    category_data = {key: value for key, value in category_data.items() if value is not None}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=category_data)
            response.raise_for_status() 

            return response.json() 
        except httpx.HTTPStatusError as e:
            error_text = None
            try:
                error_text = e.response.json() if e.response else None
            except Exception:
                error_text = e.response.text if e.response else None

            return {
                "error": f"Failed to create solution category: {str(e)}",
                "status_code": e.response.status_code if e.response else None,
                "details": error_text
            }

        except Exception as e:
            return {
                "error": f"Unexpected error occurred: {str(e)}"
            }
            
#UPDATE SOLUTION CATEGORY
@mcp.tool()
async def update_solution_category(
    category_id: int,
    name: str,
    description: str = None,
    workspace_id: int = None,
    default_category: bool = None,
) -> Dict[str, Any]:
    """Update a solution category in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/solutions/categories/{category_id}"
    headers = get_auth_headers()

   
    category_data = {
        "name": name,
        "description": description,
        "workspace_id": workspace_id,
        "default_category": default_category,
    }

   
    category_data = {key: value for key, value in category_data.items() if value is not None}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.put(url, headers=headers, json=category_data)
            response.raise_for_status()  

            return response.json()  
        except httpx.HTTPStatusError as e:
            error_text = None
            try:
                error_text = e.response.json() if e.response else None
            except Exception:
                error_text = e.response.text if e.response else None

            return {
                "error": f"Failed to update solution category: {str(e)}",
                "status_code": e.response.status_code if e.response else None,
                "details": error_text
            }

        except Exception as e:
            return {
                "error": f"Unexpected error occurred: {str(e)}"
            }

#GET LIST OF SOLUTION FOLDER
@mcp.tool()
async def get_list_of_solution_folder(id:int) -> Dict[str, Any]:
    """Get list of solution folder by its ID in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/solutions/folders?category_id={id}"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()  

            return response.json()

        except httpx.HTTPStatusError as e:
            error_text = None
            try:
                error_text = e.response.json() if e.response else None
            except Exception:
                error_text = e.response.text if e.response else None

            return {
                "error": f"Failed to fetch list of solution folder: {str(e)}",
                "status_code": e.response.status_code if e.response else None,
                "details": error_text
            }

        except Exception as e:
            return {
                "error": f"Unexpected error occurred: {str(e)}"
            }
            
#GET SOLUTION FOLDER
@mcp.tool()
async def get_solution_folder(id: int) -> Dict[str, Any]:
    """Get solution folder by its ID in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/solutions/folders/{id}"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()  

            return response.json()

        except httpx.HTTPStatusError as e:
            error_text = None
            try:
                error_text = e.response.json() if e.response else None
            except Exception:
                error_text = e.response.text if e.response else None

            return {
                "error": f"Failed to fetch solution folder: {str(e)}",
                "status_code": e.response.status_code if e.response else None,
                "details": error_text
            }

        except Exception as e:
            return {
                "error": f"Unexpected error occurred: {str(e)}"
            }
            
#GET LIST OF SOLUTION ARTICLE
@mcp.tool()
async def get_list_of_solution_article(id:int) -> Dict[str, Any]:
    """Get list of solution article in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/solutions/articles?folder_id={id}"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status() 

            return response.json()

        except httpx.HTTPStatusError as e:
            error_text = None
            try:
                error_text = e.response.json() if e.response else None
            except Exception:
                error_text = e.response.text if e.response else None

            return {
                "error": f"Failed to fetch list of solution article: {str(e)}",
                "status_code": e.response.status_code if e.response else None,
                "details": error_text
            }

        except Exception as e:
            return {
                "error": f"Unexpected error occurred: {str(e)}"
            }
            
#GET SOLUTION ARTICLE
@mcp.tool()
async def get_solution_article(id:int) -> Dict[str, Any]:
    """Get solution article by id in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/solutions/articles/{id}"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()  
            return response.json()

        except httpx.HTTPStatusError as e:
            error_text = None
            try:
                error_text = e.response.json() if e.response else None
            except Exception:
                error_text = e.response.text if e.response else None

            return {
                "error": f"Failed to fetch solution article: {str(e)}",
                "status_code": e.response.status_code if e.response else None,
                "details": error_text
            }

        except Exception as e:
            return {
                "error": f"Unexpected error occurred: {str(e)}"
            }

#CREATE SOLUTION ARTICLE
@mcp.tool()
async def create_solution_article(
    title: str,
    description: str,
    folder_id: int,
    article_type: Optional[int] = 1,  # 1 - permanent, 2 - workaround
    status: Optional[int] = 1,        # 1 - draft, 2 - published
    tags: Optional[List[str]] = None,
    keywords: Optional[List[str]] = None,
    review_date: Optional[str] = None  # Format: YYYY-MM-DD
) -> Dict[str, Any]:
    """Create a new solution article in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/solutions/articles"
    headers = get_auth_headers()

    article_data = {
        "title": title,
        "description": description,
        "folder_id": folder_id,
        "article_type": article_type,
        "status": status,
        "tags": tags,
        "keywords": keywords,
        "review_date": review_date
    }

    article_data = {key: value for key, value in article_data.items() if value is not None}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=article_data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            error_text = None
            try:
                error_text = e.response.json() if e.response else None
            except Exception:
                error_text = e.response.text if e.response else None

            return {
                "error": f"Failed to create solution article: {str(e)}",
                "status_code": e.response.status_code if e.response else None,
                "details": error_text
            }

        except Exception as e:
            return {
                "error": f"Unexpected error occurred: {str(e)}"
            }
            
#UPDATE SOLUTION ARTICLE
@mcp.tool()  
async def update_solution_article(
    article_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    folder_id: Optional[int] = None,
    article_type: Optional[int] = None,     # 1 - permanent, 2 - workaround
    status: Optional[int] = None,           # 1 - draft, 2 - published
    tags: Optional[List[str]] = None,
    keywords: Optional[List[str]] = None,
    review_date: Optional[str] = None       # Format: YYYY-MM-DD
) -> Dict[str, Any]:
    """Update a solution article in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/solutions/articles/{article_id}"
    headers = get_auth_headers()

    update_data = {
        "title": title,
        "description": description,
        "folder_id": folder_id,
        "article_type": article_type,
        "status": status,
        "tags": tags,
        "keywords": keywords,
        "review_date": review_date
    }

    update_data = {key: value for key, value in update_data.items() if value is not None}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.put(url, headers=headers, json=update_data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            error_text = None
            try:
                error_text = e.response.json() if e.response else None
            except Exception:
                error_text = e.response.text if e.response else None

            return {
                "error": f"Failed to update solution article: {str(e)}",
                "status_code": e.response.status_code if e.response else None,
                "details": error_text
            }

        except Exception as e:
            return {
                "error": f"Unexpected error occurred: {str(e)}"
            }
            
#CREATE SOLUTION FOLDER
@mcp.tool()
async def create_solution_folder(
    name: str,
    category_id: int,
    department_ids: List[int], 
    visibility: int = 4,  
    description: Optional[str] = None
) -> Dict[str, Any]:
    """Create a new folder under a solution category in Freshservice."""
    
    if not department_ids:  
        return {"error": "department_ids must be provided and cannot be empty."}
    
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/solutions/folders"
    headers = get_auth_headers()

    payload = {
        "name": name,
        "category_id": category_id,
        "visibility": visibility,  # Allowed values: 1, 2, 3, 4, 5, 6, 7
        "description": description,
        "department_ids": department_ids
    }

    payload = {k: v for k, v in payload.items() if v is not None}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            error_text = None
            try:
                error_text = e.response.json() if e.response else None
            except Exception:
                error_text = e.response.text if e.response else None

            return {
                "error": f"Failed to create solution folder: {str(e)}",
                "status_code": e.response.status_code if e.response else None,
                "details": error_text
            }

        except Exception as e:
            return {
                "error": f"Unexpected error occurred: {str(e)}"
            }

#UPDATE SOLUTION FOLDER
@mcp.tool()
async def update_solution_folder(
    id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    visibility: Optional[int] = None  # Allowed values: 1, 2, 3, 4, 5, 6, 7
) -> Dict[str, Any]:
    """Update an existing solution folder's details in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/solutions/folders/{id}"
    headers = get_auth_headers()

    payload = {
        "name": name,
        "description": description,
        "visibility": visibility
    }

    payload = {k: v for k, v in payload.items() if v is not None}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.put(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        
        except httpx.HTTPStatusError as e:
            error_text = None
            try:
                error_text = e.response.json() if e.response else None
            except Exception:
                error_text = e.response.text if e.response else None

            return {
                "error": f"Failed to update solution folder: {str(e)}",
                "status_code": e.response.status_code if e.response else None,
                "details": error_text
            }

        except Exception as e:
            return {
                "error": f"Unexpected error occurred: {str(e)}"
            }
                    
#PUBLISH SOLUTION ARTICLE   
@mcp.tool()
async def publish_solution_article(article_id: int) -> Dict[str, Any]:
    """Publish a solution article in Freshservice."""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/solutions/articles/{article_id}"
    headers = get_auth_headers()

    payload = {"status": 2}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.put(url, headers=headers,json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            error_text = None
            try:
                error_text = e.response.json() if e.response else None
            except Exception:
                error_text = e.response.text if e.response else None

            return {
                "error": f"Failed to publish solution article: {str(e)}",
                "status_code": e.response.status_code if e.response else None,
                "details": error_text
            }

        except Exception as e:
            return {
                "error": f"Unexpected error occurred: {str(e)}"
            }


# ============================================================================
# ASSETS / CMDB MANAGEMENT
# ============================================================================

#GET ASSETS
@mcp.tool()
async def get_assets(
    page: Optional[int] = 1,
    per_page: Optional[int] = 30,
    include: Optional[str] = None,
    order_by: Optional[str] = None,
    order_type: Optional[str] = None,
    trashed: Optional[bool] = False,
    workspace_id: Optional[int] = None
) -> Dict[str, Any]:
    """Get all assets from Freshservice with pagination support.

    Args:
        page: Page number (default: 1)
        per_page: Number of items per page (1-100, default: 30)
        include: Embed additional details. Use 'type_fields' to get asset type specific fields (costs 1 extra API credit)
        order_by: Sort field: 'id', 'created_at', or 'updated_at' (default: created_at)
        order_type: Sort order: 'asc' or 'desc' (default: desc)
        trashed: If True, return only trashed assets (default: False)
        workspace_id: Filter by workspace ID. Use 0 for all workspaces. If not provided, returns assets from primary workspace only.
    """
    if page < 1:
        return {"error": "Page number must be greater than 0"}

    if per_page < 1 or per_page > 100:
        return {"error": "Page size must be between 1 and 100"}

    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/assets"

    params = {
        "page": page,
        "per_page": per_page
    }

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

    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()

            link_header = response.headers.get('Link', '')
            pagination_info = parse_link_header(link_header)

            assets = response.json()

            return {
                "assets": assets,
                "pagination": {
                    "current_page": page,
                    "next_page": pagination_info.get("next"),
                    "prev_page": pagination_info.get("prev"),
                    "per_page": per_page
                }
            }

        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}


#GET ASSET BY ID
@mcp.tool()
async def get_asset_by_id(
    display_id: int,
    include: Optional[str] = None
) -> Dict[str, Any]:
    """Get a specific asset by its display ID in Freshservice.

    Args:
        display_id: The display ID of the asset to retrieve
        include: Embed additional details. Use 'type_fields' to get asset type specific fields (costs 1 extra API credit)
    """
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/assets/{display_id}"

    params = {}
    if include:
        params["include"] = include

    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": f"Failed to fetch asset: {str(e)}", "details": e.response.json()}
            except Exception:
                return {"error": f"Failed to fetch asset: {str(e)}"}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}


#CREATE ASSET
@mcp.tool()
async def create_asset(
    name: str,
    asset_type_id: int,
    asset_tag: Optional[str] = None,
    impact: Optional[str] = "low",
    usage_type: Optional[str] = "permanent",
    description: Optional[str] = None,
    user_id: Optional[int] = None,
    location_id: Optional[int] = None,
    department_id: Optional[int] = None,
    agent_id: Optional[int] = None,
    group_id: Optional[int] = None,
    assigned_on: Optional[str] = None,
    workspace_id: Optional[int] = None,
    type_fields: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create a new asset in Freshservice.

    Args:
        name: Name of the asset (MANDATORY)
        asset_type_id: ID of the asset type (MANDATORY)
        asset_tag: Asset tag (e.g., 'ASSET-9')
        impact: Impact level: 'low', 'medium', or 'high' (default: 'low')
        usage_type: Usage type: 'permanent' or 'loaner' (default: 'permanent')
        description: Description of the asset
        user_id: ID of the user the asset is assigned to (Used By)
        location_id: ID of the associated location
        department_id: ID of the associated department
        agent_id: ID of the agent managing the asset (Managed By)
        group_id: ID of the agent group managing the asset (Managed By Group)
        assigned_on: Date when asset was assigned (ISO format)
        workspace_id: Workspace ID (applicable only to accounts with workspaces)
        type_fields: Asset type specific fields (e.g., product_id, vendor_id, serial_number, cost, etc.)
    """
    if impact and impact not in ("low", "medium", "high"):
        return {"error": "Invalid impact value. Must be 'low', 'medium', or 'high'"}

    if usage_type and usage_type not in ("permanent", "loaner"):
        return {"error": "Invalid usage_type value. Must be 'permanent' or 'loaner'"}

    data: Dict[str, Any] = {
        "name": name,
        "asset_type_id": asset_type_id
    }

    if asset_tag:
        data["asset_tag"] = asset_tag
    if impact:
        data["impact"] = impact
    if usage_type:
        data["usage_type"] = usage_type
    if description:
        data["description"] = description
    if user_id is not None:
        data["user_id"] = user_id
    if location_id is not None:
        data["location_id"] = location_id
    if department_id is not None:
        data["department_id"] = department_id
    if agent_id is not None:
        data["agent_id"] = agent_id
    if group_id is not None:
        data["group_id"] = group_id
    if assigned_on:
        data["assigned_on"] = assigned_on
    if workspace_id is not None:
        data["workspace_id"] = workspace_id
    if type_fields:
        data["type_fields"] = type_fields

    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/assets"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=data)
            response.raise_for_status()
            return {
                "success": True,
                "message": "Asset created successfully",
                "asset": response.json()
            }
        except httpx.HTTPStatusError as e:
            error_message = f"Failed to create asset: {str(e)}"
            try:
                error_details = e.response.json()
                if "errors" in error_details:
                    error_message = f"Validation errors: {error_details['errors']}"
            except Exception:
                pass
            return {"success": False, "error": error_message}
        except Exception as e:
            return {"success": False, "error": f"An unexpected error occurred: {str(e)}"}


#UPDATE ASSET
@mcp.tool()
async def update_asset(
    display_id: int,
    asset_fields: Dict[str, Any]
) -> Dict[str, Any]:
    """Update an existing asset in Freshservice.

    Args:
        display_id: The display ID of the asset to update
        asset_fields: Dictionary of fields to update. Supported fields include:
            - name: Name of the asset
            - asset_type_id: ID of the asset type
            - asset_tag: Asset tag
            - impact: 'low', 'medium', or 'high'
            - usage_type: 'permanent' or 'loaner'
            - description: Description
            - user_id: User ID (Used By)
            - location_id: Location ID
            - department_id: Department ID
            - agent_id: Agent ID (Managed By)
            - group_id: Agent group ID (Managed By Group)
            - assigned_on: Assignment date (ISO format)
            - type_fields: Asset type specific fields dict

    Note: workspace_id cannot be updated here. Use move_asset instead.
    """
    if not asset_fields:
        return {"error": "No fields provided for update"}

    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/assets/{display_id}"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.put(url, headers=headers, json=asset_fields)
            response.raise_for_status()
            return {
                "success": True,
                "message": "Asset updated successfully",
                "asset": response.json()
            }
        except httpx.HTTPStatusError as e:
            error_message = f"Failed to update asset: {str(e)}"
            try:
                error_details = e.response.json()
                if "errors" in error_details:
                    error_message = f"Validation errors: {error_details['errors']}"
            except Exception:
                pass
            return {"success": False, "error": error_message}
        except Exception as e:
            return {"success": False, "error": f"An unexpected error occurred: {str(e)}"}


#DELETE ASSET (move to trash)
@mcp.tool()
async def delete_asset(display_id: int) -> str:
    """Delete an asset in Freshservice (moves it to trash).

    Args:
        display_id: The display ID of the asset to delete
    """
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/assets/{display_id}"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        response = await client.delete(url, headers=headers)

        if response.status_code == 204:
            return "Asset deleted successfully (moved to trash)"
        elif response.status_code == 404:
            return "Error: Asset not found"
        else:
            try:
                response_data = response.json()
                return f"Error: {response_data.get('error', 'Failed to delete asset')}"
            except ValueError:
                return "Error: Unexpected response format"


#DELETE ASSET PERMANENTLY
@mcp.tool()
async def delete_asset_permanently(display_id: int) -> str:
    """Permanently delete an asset from Freshservice. This action cannot be undone.

    Args:
        display_id: The display ID of the trashed asset to permanently delete
    """
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/assets/{display_id}/delete_forever"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        response = await client.put(url, headers=headers)

        if response.status_code == 204:
            return "Asset permanently deleted"
        elif response.status_code == 404:
            return "Error: Asset not found"
        else:
            try:
                response_data = response.json()
                return f"Error: {response_data.get('error', 'Failed to permanently delete asset')}"
            except ValueError:
                return "Error: Unexpected response format"


#RESTORE ASSET
@mcp.tool()
async def restore_asset(display_id: int) -> str:
    """Restore a previously deleted (trashed) asset in Freshservice.

    Args:
        display_id: The display ID of the trashed asset to restore
    """
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/assets/{display_id}/restore"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        response = await client.put(url, headers=headers)

        if response.status_code == 204:
            return "Asset restored successfully"
        elif response.status_code == 404:
            return "Error: Asset not found in trash"
        else:
            try:
                response_data = response.json()
                return f"Error: {response_data.get('error', 'Failed to restore asset')}"
            except ValueError:
                return "Error: Unexpected response format"


#SEARCH ASSETS
@mcp.tool()
async def search_assets(
    search_query: str,
    page: Optional[int] = 1,
    trashed: Optional[bool] = False
) -> Dict[str, Any]:
    """Search assets in Freshservice using asset attributes.

    Args:
        search_query: Search query string using asset fields.
            Supported fields: name, asset_tag, serial_number, mac_addresses, ip_addresses, uuid, item_id, imei_number.
            Examples: "name:'dell'", "serial_number:'HSN123'", "asset_tag:'ASSET-65'"
            Note: The query will be automatically URL-encoded and wrapped in double quotes.
        page: Page number (default: 1). 30 results per page.
        trashed: If True, search in trashed assets (default: False)
    """
    encoded_search = urllib.parse.quote(f'"{search_query}"')
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/assets?search={encoded_search}&page={page}"

    if trashed:
        url += "&trashed=true"

    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()

            link_header = response.headers.get('Link', '')
            pagination_info = parse_link_header(link_header)
            total_count = response.headers.get('X-Total-Count', None)

            result = response.json()
            result["pagination"] = {
                "current_page": page,
                "next_page": pagination_info.get("next"),
                "prev_page": pagination_info.get("prev"),
            }
            if total_count:
                result["total_count"] = int(total_count)
            return result

        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}


#FILTER ASSETS
@mcp.tool()
async def filter_assets(
    filter_query: str,
    page: Optional[int] = 1,
    include: Optional[str] = None
) -> Dict[str, Any]:
    """Filter assets in Freshservice using asset attributes.

    Args:
        filter_query: Filter query string using asset fields.
            Supported fields: workspace_id, asset_type_id, department_id, location_id,
            asset_state, user_id, agent_id, name, asset_tag, created_at, updated_at,
            serial_number, mac_addresses, ip_addresses, uuid, item_id, imei_number, device42_id.
            Operators: AND, OR, parentheses (), :> (>=), :< (<=)
            Examples:
                "asset_state:'IN USE'"
                "asset_state:'IN STOCK' AND created_at:>'2023-01-01'"
                "department_id:5 AND location_id:3"
                "asset_type_id:25 AND agent_id:null"
            Note: The query will be automatically URL-encoded and wrapped in double quotes.
        page: Page number (default: 1). 30 results per page, max 40 pages.
        include: Embed additional details. Use 'type_fields' for asset type specific fields.
    """
    encoded_filter = urllib.parse.quote(f'"{filter_query}"')
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/assets?filter={encoded_filter}&page={page}"

    if include:
        url += f"&include={include}"

    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()

            link_header = response.headers.get('Link', '')
            pagination_info = parse_link_header(link_header)
            total_count = response.headers.get('X-Total-Count', None)

            result = response.json()
            result["pagination"] = {
                "current_page": page,
                "next_page": pagination_info.get("next"),
                "prev_page": pagination_info.get("prev"),
            }
            if total_count:
                result["total_count"] = int(total_count)
            return result

        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}


#MOVE ASSET TO WORKSPACE
@mcp.tool()
async def move_asset(
    display_id: int,
    workspace_id: int,
    agent_id: Optional[int] = None,
    group_id: Optional[int] = None
) -> Dict[str, Any]:
    """Move an asset to a different workspace in Freshservice.

    Note: This endpoint is applicable only to accounts with workspaces.

    Args:
        display_id: The display ID of the asset to move
        workspace_id: The target workspace ID
        agent_id: Optional new agent ID for the asset
        group_id: Optional new group ID for the asset
    """
    data: Dict[str, Any] = {"workspace_id": workspace_id}
    if agent_id is not None:
        data["agent_id"] = agent_id
    if group_id is not None:
        data["group_id"] = group_id

    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/assets/{display_id}/move_workspace"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.put(url, headers=headers, json=data)
            response.raise_for_status()
            return {
                "success": True,
                "message": "Asset moved successfully",
                "asset": response.json()
            }
        except httpx.HTTPStatusError as e:
            try:
                return {"error": f"Failed to move asset: {str(e)}", "details": e.response.json()}
            except Exception:
                return {"error": f"Failed to move asset: {str(e)}"}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}


#GET ASSET COMPONENTS
@mcp.tool()
async def get_asset_components(display_id: int) -> Dict[str, Any]:
    """Get all components of an asset in Freshservice (e.g., Processor, Memory, Disk, etc.).

    Args:
        display_id: The display ID of the asset
    """
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/assets/{display_id}/components"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": f"Failed to fetch asset components: {str(e)}", "details": e.response.json()}
            except Exception:
                return {"error": f"Failed to fetch asset components: {str(e)}"}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}


#GET ASSET ASSIGNMENT HISTORY
@mcp.tool()
async def get_asset_assignment_history(display_id: int) -> Dict[str, Any]:
    """Get the user assignment history for a specific asset in Freshservice.

    Args:
        display_id: The display ID of the asset
    """
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/assets/{display_id}/assignment-history"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": f"Failed to fetch assignment history: {str(e)}", "details": e.response.json()}
            except Exception:
                return {"error": f"Failed to fetch assignment history: {str(e)}"}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}


#GET ASSET REQUESTS
@mcp.tool()
async def get_asset_requests(display_id: int) -> Dict[str, Any]:
    """List all associated requests (tickets) for a specific asset in Freshservice.

    Args:
        display_id: The display ID of the asset
    """
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/assets/{display_id}/requests"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": f"Failed to fetch asset requests: {str(e)}", "details": e.response.json()}
            except Exception:
                return {"error": f"Failed to fetch asset requests: {str(e)}"}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}


#GET ASSET CONTRACTS
@mcp.tool()
async def get_asset_contracts(display_id: int) -> Dict[str, Any]:
    """List all associated contracts for a specific asset in Freshservice.

    Args:
        display_id: The display ID of the asset
    """
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/assets/{display_id}/contracts"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": f"Failed to fetch asset contracts: {str(e)}", "details": e.response.json()}
            except Exception:
                return {"error": f"Failed to fetch asset contracts: {str(e)}"}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}


# ============================================================================
# ASSET RELATIONSHIPS
# ============================================================================

#GET ASSET RELATIONSHIPS
@mcp.tool()
async def get_asset_relationships(display_id: int) -> Dict[str, Any]:
    """List all relationships for a specific asset in Freshservice.

    Args:
        display_id: The display ID of the asset
    """
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/assets/{display_id}/relationships"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": f"Failed to fetch asset relationships: {str(e)}", "details": e.response.json()}
            except Exception:
                return {"error": f"Failed to fetch asset relationships: {str(e)}"}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}


#GET ALL RELATIONSHIPS
@mcp.tool()
async def get_all_relationships(page: Optional[int] = 1, per_page: Optional[int] = 30) -> Dict[str, Any]:
    """List all asset relationships in the Freshservice account.

    Args:
        page: Page number (default: 1)
        per_page: Number of items per page (1-100, default: 30)
    """
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/relationships"
    params = {"page": page, "per_page": per_page}
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()

            link_header = response.headers.get('Link', '')
            pagination_info = parse_link_header(link_header)

            return {
                "relationships": response.json(),
                "pagination": {
                    "current_page": page,
                    "next_page": pagination_info.get("next"),
                    "prev_page": pagination_info.get("prev"),
                    "per_page": per_page
                }
            }
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}


#GET RELATIONSHIP BY ID
@mcp.tool()
async def get_relationship_by_id(relationship_id: int) -> Dict[str, Any]:
    """View a specific relationship by its ID in Freshservice.

    Args:
        relationship_id: The ID of the relationship
    """
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/relationships/{relationship_id}"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": f"Failed to fetch relationship: {str(e)}", "details": e.response.json()}
            except Exception:
                return {"error": f"Failed to fetch relationship: {str(e)}"}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}


#CREATE RELATIONSHIPS IN BULK
@mcp.tool()
async def create_asset_relationships(
    relationships: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Create asset relationships in bulk in Freshservice.

    This is an asynchronous operation performed via background jobs.
    The response contains a job_id which can be used with get_job_status() to track progress.
    Supported primary_type/secondary_type values: 'asset', 'requester', 'agent', 'department', 'software'.

    Args:
        relationships: List of relationship objects. Each object should contain:
            - relationship_type_id: ID of the relationship type (MANDATORY)
            - primary_id: ID of the primary entity (MANDATORY)
            - primary_type: Type of the primary entity: 'asset', 'requester', 'agent', 'department', 'software' (MANDATORY)
            - secondary_id: ID of the secondary entity (MANDATORY)
            - secondary_type: Type of the secondary entity: 'asset', 'requester', 'agent', 'department', 'software' (MANDATORY)
    """
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/relationships/bulk-create"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json={"relationships": relationships})
            response.raise_for_status()
            result = response.json()
            return {
                "success": True,
                "message": "Bulk relationship creation job submitted. Use get_job_status() with the job_id to track progress.",
                "job_id": result.get("job_id"),
                "href": result.get("href"),
                "data": result
            }
        except httpx.HTTPStatusError as e:
            try:
                return {"error": f"Failed to create relationships: {str(e)}", "details": e.response.json()}
            except Exception:
                return {"error": f"Failed to create relationships: {str(e)}"}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}


#DELETE RELATIONSHIPS IN BULK
@mcp.tool()
async def delete_asset_relationships(
    relationship_ids: List[int]
) -> str:
    """Delete asset relationships in bulk in Freshservice.

    Args:
        relationship_ids: List of relationship IDs to delete
    """
    ids_param = ",".join(str(rid) for rid in relationship_ids)
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/relationships?ids={ids_param}"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.delete(url, headers=headers)

            if response.status_code == 204:
                return "Relationships deleted successfully"
            else:
                try:
                    return f"Error: {response.json()}"
                except Exception:
                    return f"Error: Unexpected response (status {response.status_code})"
        except Exception as e:
            return f"Error: An unexpected error occurred: {str(e)}"


#GET BACKGROUND JOB STATUS
@mcp.tool()
async def get_job_status(job_id: str) -> Dict[str, Any]:
    """Get the status of a background job in Freshservice.

    Use this to track the progress of async operations like bulk relationship creation.
    Possible status values: 'queued', 'in progress', 'partial', 'success', 'failed'.
    - queued: Job is queued and ready to be executed
    - in progress: Job execution started
    - partial: Job completed with some successes and some failures
    - success: All operations completed successfully
    - failed: No operations succeeded

    Note: The job status URL is valid for one hour after creation.

    Args:
        job_id: The job ID returned by a bulk operation (e.g., create_asset_relationships)
    """
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/jobs/{job_id}"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": f"Failed to fetch job status: {str(e)}", "details": e.response.json()}
            except Exception:
                return {"error": f"Failed to fetch job status: {str(e)}"}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}


#GET RELATIONSHIP TYPES
@mcp.tool()
async def get_relationship_types() -> Dict[str, Any]:
    """List all relationship types available in Freshservice.
    These define the kind of relationships between assets (e.g., 'Used By', 'Depends On', etc.).
    """
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/relationship_types"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": f"Failed to fetch relationship types: {str(e)}", "details": e.response.json()}
            except Exception:
                return {"error": f"Failed to fetch relationship types: {str(e)}"}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}


# ============================================================================
# ASSET TYPES
# ============================================================================

#GET ASSET TYPES
@mcp.tool()
async def get_asset_types(page: Optional[int] = 1, per_page: Optional[int] = 30) -> Dict[str, Any]:
    """List all asset types in Freshservice (e.g., Hardware, Software, etc.).

    Args:
        page: Page number (default: 1)
        per_page: Number of items per page (1-100, default: 30)
    """
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/asset_types"
    params = {"page": page, "per_page": per_page}
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()

            link_header = response.headers.get('Link', '')
            pagination_info = parse_link_header(link_header)

            return {
                "asset_types": response.json(),
                "pagination": {
                    "current_page": page,
                    "next_page": pagination_info.get("next"),
                    "prev_page": pagination_info.get("prev"),
                    "per_page": per_page
                }
            }
        except httpx.HTTPStatusError as e:
            try:
                return {"error": str(e), "details": e.response.json()}
            except Exception:
                return {"error": str(e), "raw_response": e.response.text}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}


#GET ASSET TYPE BY ID
@mcp.tool()
async def get_asset_type_by_id(asset_type_id: int) -> Dict[str, Any]:
    """Get a specific asset type by ID in Freshservice.

    Args:
        asset_type_id: The ID of the asset type
    """
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/asset_types/{asset_type_id}"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                return {"error": f"Failed to fetch asset type: {str(e)}", "details": e.response.json()}
            except Exception:
                return {"error": f"Failed to fetch asset type: {str(e)}"}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}


# GET AUTH HEADERS
def get_auth_headers():
    return {
        "Authorization": f"Basic {base64.b64encode(f'{FRESHSERVICE_APIKEY}:X'.encode()).decode()}",
        "Content-Type": "application/json"
    }

def main():
    logging.info("Starting Freshservice MCP server")
    mcp.run(transport='stdio')

if __name__ == "__main__":
    main()
