import httpx
from mcp.server.fastmcp import FastMCP
import logging
import os
import base64
from typing import Optional, Dict, Union, Any, List
from enum import IntEnum, Enum
import re   
from pydantic import BaseModel, Field
import json
import urllib.parse


from dotenv import load_dotenv
load_dotenv()

# Create MCP instance
mcp = FastMCP("freshservice_mcp")


# Fetch API credentials
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
    """
    Create a ticket in Freshservice.

    Accepted values for:
    
    - source (int or str):
        'email' (1), 'portal' (2), 'phone' (3), 'yammer' (6), 'chat' (7), 'aws_cloudwatch' (7),
        'pagerduty' (8), 'walk_up' (9), 'slack' (10), 'workplace' (12),
        'employee_onboarding' (13), 'alerts' (14), 'ms_teams' (15), 'employee_offboarding' (18)

    - priority (int or str):
        'low' (1), 'medium' (2), 'high' (3), 'urgent' (4)

    - status (int or str):
        'open' (2), 'pending' (3), 'resolved' (4), 'closed' (5)

    Either `email` or `requester_id` must be provided.
    """
    
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
            
# FILTER TICKET 
@mcp.tool()
async def filter_tickets(query: str, page: int = 1, workspace_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Filter tickets based on a query string.
    
    Notes:
    - Query must be properly URL encoded.
    - Logical operators AND, OR can be used.
    - String values must be enclosed in single quotes.
    - Date format: 'yyyy-mm-dd'.
    - Supported operators: =, :>, :<

    Example query (before encoding):
    "priority: 1 AND status: 2 OR urgency: 3"
    """
    encoded_query = urllib.parse.quote(query)
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
        
# DELETE TICKET.
@mcp.tool()
async def delete_ticket(ticket_id: int) -> str:
    """Delete a ticket in Freshdesk."""
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
    
# GET TICKET BY ID  
@mcp.tool()
async def get_ticket_by_id(ticket_id:int) -> str:
    """Get a specific ticket by its ID"""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/tickets/{ticket_id}"
    headers = get_auth_headers()

    async with httpx.AsyncClient() as client:
        response = await client.get(url,headers=headers)
        return response.json()
    
@mcp.tool()
async def list_service_items(page: Optional[int] = 1, per_page: Optional[int] = 30) -> Dict[str, Any]:
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
    """
    Place a service request in Freshservice.
    
    Args:
        display_id (int): The display ID of the service catalog item.
        email (str): Email of the requester.
        requested_for (Optional[str]): Email of the person the request is for.
        quantity (int): Number of items requested (must be a positive integer).
    
    Returns:
        dict: The response from the API.
    """
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
    Send a reply to a ticket in Freshservice.

    Required:
        - ticket_id (int): Must be >= 1
        - body (str): Message content

    Optional:
        - from_email (str): Sender's email
        - user_id (int): Agent user ID
        - cc_emails (list or str): List of emails to CC
        - bcc_emails (list or str): List of emails to BCC

    Note: Attachments are not supported in this version.
    """

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
        
@mcp.tool()
async def list_all_ticket_conversation(ticket_id: int)-> Dict[str, Any]:
    """List all conversation of a ticket in freshservice"""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/tickets/{ticket_id}/conversations"
    headers = get_auth_headers()
   
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        status_code = response.status_code
        if status_code == 200:
            return response.json()
        else:
            return f"Cannot fetch ticket conversations ${response.json()}"
        
#PRODUCTS 
#GET ALL PRODUCTS
@mcp.tool()
async def get_all_products(page: Optional[int] = 1, per_page: Optional[int] = 30) -> Dict[str, Any]:
    """
    Fetch one page of products from Freshservice with pagination support.
    Returns the page data and info about whether a next page exists.
    """
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
    """List all products of a ticket in freshservice"""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/products/{product_id}"
    headers = get_auth_headers()
   
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        status_code = response.status_code
        if status_code == 200:
            return response.json()
        else:
            return f"Cannot fetch products from the freshservice ${response.json()}"
        
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
    """
    Create a product in Freshservice with required and optional fields.
    Validates 'status' to be one of: 'In Production', 'In Pipeline', 'Retired' or corresponding integer values.
    """

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
    """
    Update a product in Freshservice. Requires 'id', 'name', and 'asset_type_id'.
    Optional fields: manufacturer, status, mode_of_procurement, depreciation_type_id, description, description_text.
    """

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
    """
    Creates a requester in Freshservice.
    'first_name' is required. Also requires at least one of: 'primary_email', 'work_phone_number', or 'mobile_phone_number'.
    """

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
    """Fetch requesters from Freshservice with pagination support."""
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
    """List all requester in Freshservice"""
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
    """List all requester in Freshservice"""
    url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/requester_fields"
    headers = get_auth_headers()
   
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        status_code = response.status_code
        if status_code == 200:
            return response.json()
        else:
            return f"Cannot fetch requester from the freshservice ${response.json()}"
        
#UPDATE REQUESTERS
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
    """Update a requester in Freshservice"""

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
    """
    Filter requesters based on requester attributes and custom fields.
    
    Notes:
    - Query must be URL encoded.
    - Logical operators AND, OR can be used.
    - To filter for empty fields, use `null`.
    - Use `~` for "starts with" text searches.
    - `include_agents=true` will include agents in the results (requires permissions).

    Example query (before encoding):
    "~name:'john' AND created_at:> '2024-01-01'"
    """
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

            
#Agents
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
    """Get agent by agent_id in Freshservice"""
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
    """Fetch agents from Freshservice with pagination support."""
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
                "error": f"Failed to create solution folder: {str(e)}",
                "status_code": e.response.status_code if e.response else None,
                "details": error_text
            }
            
#FILTER AGENTS
@mcp.tool()
async def filter_agents(query: str) -> List[Dict[str, Any]]:
    """
    Filter Freshservice agents based on a query.

    Args:
        query: The filter query in URL-encoded format (e.g., "department_id:123 AND created_at:>'2024-01-01'")

    Returns:
        A list of matching agent records.
    """
    base_url = f"https://{FRESHSERVICE_DOMAIN}/api/v2/agents"
    headers = get_auth_headers()
    all_agents = []
    page = 1

    async with httpx.AsyncClient() as client:
        while True:
            url = f"{base_url}?query={query}&page={page}"
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
    """Update the agent details in the Freshservice"""
    
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
    """Get all agent fields in  Freshservice"""
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
    """Get all agent groups in  Freshservice"""
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
    """Get agent groups by its group id in  Freshservice"""
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
    """
    Create a group in Freshservice using a plain dictionary.
    
    Required:
      - name: str
    Optional:
      - description: str
      - agent_ids: List[int]
      - auto_ticket_assign: bool
      - escalate_to: int
      - unassigned_for: str (e.g. "thirty_minutes")
    """
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
    """Update a group in Freshdesk."""
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
    """Get all requester groups in Freshservice with pagination support."""
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
    """Get requester groups by ID"""
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
    """Update an existing requester group in Freshservice."""
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
    """List canned response folder  Freshservice."""
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
    """Get list of solution folder by its ID in Freshservice."""
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
                "error": f"Failed to fetch list of solution folder: {str(e)}",
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
    """Get list of solution folder by its ID in Freshservice."""
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
    """Publish a solution article in Freshservice (status = 2)."""
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

# GET DEFAULT AUTH HEADERS
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
