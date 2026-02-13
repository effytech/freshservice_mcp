# Freshservice MCP Server

[![smithery badge](https://smithery.ai/badge/@effytech/freshservice_mcp)](https://smithery.ai/server/@effytech/freshservice_mcp)

## Overview

A powerful MCP (Model Context Protocol) server implementation that seamlessly integrates with Freshservice, enabling AI models to interact with Freshservice modules and perform various IT service management operations. This integration bridge empowers your AI assistants to manage and resolve IT service tickets, streamlining your support workflow.

## Key Features

- **Enterprise-Grade Freshservice Integration**: Direct, secure communication with Freshservice API endpoints
- **AI Model Compatibility**: Enables Claude and other AI models to execute service desk operations through Freshservice
- **Automated ITSM Management**: Efficiently handle ticket creation, updates, responses, and asset management
- **Workflow Acceleration**: Reduce manual intervention in routine IT service tasks

## Supported Freshservice Modules

**This MCP server currently supports operations across a wide range of Freshservice modules**:

- Tickets
- Changes
- Conversations
- Products
- Requesters
- Agents
- Agent Groups
- Requester Groups
- Canned Responses
- Canned Response Folders
- Workspaces
- Solution Categories
- Solution Folders
- Solution Articles
- Assets / CMDB
- Asset Relationships
- Asset Types

## Components & Tools

The server provides a comprehensive toolkit for Freshservice operations:

### Ticket Management

| Tool | Description | Key Parameters |
| ---- | ----------- | -------------- |
| `create_ticket` | Create new service tickets | `subject`, `description`, `source`, `priority`, `status`, `email` |
| `update_ticket` | Update existing tickets | `ticket_id`, `updates` |
| `delete_ticket` | Remove tickets | `ticket_id` |
| `filter_tickets` | Find tickets matching criteria | `query` |
| `get_ticket_fields` | Retrieve ticket field definitions | None |
| `get_tickets` | List all tickets with pagination | `page`, `per_page` |
| `get_ticket_by_id` | Retrieve single ticket details | `ticket_id` |

### Change Management

| Tool | Description | Key Parameters |
| ---- | ----------- | -------------- |
| `get_changes` | List all changes with pagination | `page`, `per_page`, `query` |
| `filter_changes` | Filter changes with advanced queries | `query`, `page`, `per_page` |
| `get_change_by_id` | Retrieve single change details | `change_id` |
| `create_change` | Create new change request | `requester_id`, `subject`, `description`, `priority`, `impact`, `status`, `risk`, `change_type` |
| `update_change` | Update existing change | `change_id`, `change_fields` |
| `close_change` | Close change with result explanation | `change_id`, `change_result_explanation` |
| `delete_change` | Remove change | `change_id` |
| `get_change_tasks` | Get tasks for a change | `change_id` |
| `create_change_note` | Add note to change | `change_id`, `body` |

#### 🚨 Important: Query Syntax for Filtering

When using `get_changes` or `filter_changes` with the `query` parameter, **the query string must be wrapped in double quotes** for the Freshservice API to work correctly:

✅ **CORRECT**: `"status:3"`, `"approval_status:1 AND status:<6"`
❌ **WRONG**: `status:3` (will cause 500 Internal Server Error)

**Common Query Examples:**

- `"status:3"` - Changes awaiting approval
- `"approval_status:1"` - Approved changes
- `"approval_status:1 AND status:<6"` - Approved changes that are not closed
- `"planned_start_date:>'2025-07-14'"` - Changes starting after specific date
- `"status:3 AND priority:1"` - High priority changes awaiting approval

### Asset / CMDB Management

| Tool | Description | Key Parameters |
| ---- | ----------- | -------------- |
| `get_assets` | List all assets with pagination | `page`, `per_page`, `include`, `order_by`, `order_type`, `trashed`, `workspace_id` |
| `get_asset_by_id` | Retrieve single asset details | `display_id`, `include` |
| `create_asset` | Create a new asset | `name`, `asset_type_id`, `impact`, `usage_type`, `description`, `type_fields` |
| `update_asset` | Update an existing asset | `display_id`, `asset_fields` |
| `delete_asset` | Delete (trash) an asset | `display_id` |
| `delete_asset_permanently` | Permanently delete a trashed asset | `display_id` |
| `restore_asset` | Restore a trashed asset | `display_id` |
| `search_assets` | Search assets by attributes | `search_query`, `page`, `trashed` |
| `filter_assets` | Filter assets with advanced queries | `filter_query`, `page`, `include` |
| `move_asset` | Move asset to another workspace | `display_id`, `workspace_id`, `agent_id`, `group_id` |
| `get_asset_components` | List hardware components | `display_id` |
| `get_asset_assignment_history` | View user assignment history | `display_id` |
| `get_asset_requests` | List associated tickets | `display_id` |
| `get_asset_contracts` | List associated contracts | `display_id` |

### Asset Relationships

| Tool | Description | Key Parameters |
| ---- | ----------- | -------------- |
| `get_asset_relationships` | List relationships for an asset | `display_id` |
| `get_all_relationships` | List all relationships | `page`, `per_page` |
| `get_relationship_by_id` | View a specific relationship | `relationship_id` |
| `create_asset_relationships` | Create relationships in bulk | `relationships` |
| `delete_asset_relationships` | Delete relationships in bulk | `relationship_ids` |
| `get_relationship_types` | List available relationship types | None |

### Asset Types

| Tool | Description | Key Parameters |
| ---- | ----------- | -------------- |
| `get_asset_types` | List all asset types | `page`, `per_page` |
| `get_asset_type_by_id` | View a specific asset type | `asset_type_id` |

## Getting Started

### Installing via Smithery

To install freshservice_mcp automatically via Smithery:

```bash
npx -y @smithery/cli install @effytech/freshservice_mcp --client claude
```

### Prerequisites

- A Freshservice account (sign up at [freshservice.com](https://www.freshservice.com))
- Freshservice API key
- `uvx` installed (`pip install uv` or `brew install uv`)

### Configuration

1. Generate your Freshservice API key from the admin panel:
   - Navigate to Profile Settings → API Settings
   - Copy your API key for configuration

2. Set up your domain and authentication details as shown below

### Usage with Claude Desktop

1. Install Claude Desktop from the [official website](https://claude.ai/desktop)
2. Add the following configuration to your `claude_desktop_config.json`:

```json
"mcpServers": {
  "freshservice-mcp": {
    "command": "uvx",
    "args": [
        "freshservice-mcp"
    ],
    "env": {
      "FRESHSERVICE_APIKEY": "<YOUR_FRESHSERVICE_APIKEY>",
      "FRESHSERVICE_DOMAIN": "<YOUR_FRESHSERVICE_DOMAIN>"
    }
  }
}
```

**Important**: Replace `<YOUR_FRESHSERVICE_APIKEY>` with your actual API key and `<YOUR_FRESHSERVICE_DOMAIN>` with your domain (e.g., `yourcompany.freshservice.com`)

## Example Operations

Once configured, you can ask Claude to perform operations like:

**Tickets:**

- "Create a new incident ticket with subject 'Network connectivity issue in Marketing department' and description 'Users unable to connect to Wi-Fi in Marketing area', set priority to high"
- "List all critical incidents reported in the last 24 hours"
- "Update ticket #12345 status to resolved"

**Changes:**

- "Create a change request for scheduled server maintenance next Tuesday at 2 AM"
- "Update the status of change request #45678 to 'Approved'"
- "Close change #5092 with result explanation 'Successfully deployed to production. All tests passed.'"
- "List all pending changes"

**Other Operations:**

- "Show asset details for laptop with asset tag 'LT-2023-087'"
- "Create a solution article about password reset procedures"

**Assets / CMDB:**

- "List all assets in the CMDB"
- "Create a new hardware asset named 'Dell Latitude 5540' with asset type 'Laptop'"
- "Search assets with serial number 'HSN12345'"
- "Filter assets by state 'IN USE' in department 5"
- "Show all components of asset #42 (CPU, memory, disk, etc.)"
- "Show the assignment history for asset #115"
- "List all relationships for asset #42"
- "Move asset #99 to workspace 3"

## Testing

For testing purposes, you can start the server manually:

```bash
uvx freshservice-mcp --env FRESHSERVICE_APIKEY=<your_api_key> --env FRESHSERVICE_DOMAIN=<your_domain>
```

## Troubleshooting

- Verify your Freshservice API key and domain are correct
- Ensure proper network connectivity to Freshservice servers
- Check API rate limits and quotas
- Verify the `uvx` command is available in your PATH

## License

This MCP server is licensed under the MIT License. See the LICENSE file in the project repository for full details.

## Additional Resources

- [Freshservice API Documentation](https://api.freshservice.com/)
- [Claude Desktop Integration Guide](https://docs.anthropic.com/claude/docs/claude-desktop)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)

---

<p align="center">Built with ❤️ by effy</p>
