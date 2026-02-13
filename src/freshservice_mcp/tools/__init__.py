"""Freshservice MCP — tools package.

Each sub-module exposes a ``register_*_tools(mcp)`` function.
"""

from .agents import register_agents_tools
from .assets import register_assets_tools
from .changes import register_changes_tools
from .misc import register_misc_tools
from .products import register_products_tools
from .requesters import register_requesters_tools
from .solutions import register_solutions_tools
from .tickets import register_tickets_tools

# Mapping from scope name → registration function.
# Used by server.py to selectively load tool modules.
SCOPE_REGISTRY: dict[str, callable] = {
    "tickets": register_tickets_tools,
    "changes": register_changes_tools,
    "assets": register_assets_tools,
    "agents": register_agents_tools,
    "requesters": register_requesters_tools,
    "solutions": register_solutions_tools,
    "products": register_products_tools,
    "misc": register_misc_tools,
}

__all__ = [
    "SCOPE_REGISTRY",
    "register_agents_tools",
    "register_assets_tools",
    "register_changes_tools",
    "register_misc_tools",
    "register_products_tools",
    "register_requesters_tools",
    "register_solutions_tools",
    "register_tickets_tools",
]
