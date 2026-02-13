"""Freshservice MCP — Configuration and constants."""
import os
import logging
from enum import IntEnum, Enum

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("freshservice_mcp")

# ---------------------------------------------------------------------------
# API credentials
# ---------------------------------------------------------------------------
FRESHSERVICE_DOMAIN = os.getenv("FRESHSERVICE_DOMAIN")
FRESHSERVICE_APIKEY = os.getenv("FRESHSERVICE_APIKEY")

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TicketSource(IntEnum):
    EMAIL = 1
    PORTAL = 2
    PHONE = 3
    YAMMER = 6
    CHAT = 7
    AWS_CLOUDWATCH = 7
    PAGERDUTY = 8
    WALK_UP = 9
    SLACK = 10
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

# All available scopes for --scope flag
AVAILABLE_SCOPES = [
    "tickets",
    "changes",
    "assets",
    "agents",
    "requesters",
    "groups",
    "solutions",
    "products",
    "service_catalog",
    "canned_responses",
    "workspaces",
    "discovery",
]
