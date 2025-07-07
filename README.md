[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/effytech-freshservice-mcp-badge.png)](https://mseep.ai/app/effytech-freshservice-mcp)

# Freshservice MCP Server

[![smithery badge](https://smithery.ai/badge/@effytech/freshservice_mcp)](https://smithery.ai/server/@effytech/freshservice_mcp)

## Overview

A powerful MCP (Model Control Protocol) server implementation that seamlessly integrates with Freshservice, enabling AI models to interact with Freshservice modules and perform various IT service management operations. This integration bridge empowers your AI assistants to manage and resolve IT service tickets, streamlining your support workflow.

## Key Features

- **Enterprise-Grade Freshservice Integration**: Direct, secure communication with Freshservice API endpoints
- **AI Model Compatibility**: Enables Claude and other AI models to execute service desk operations through Freshservice
- **Automated ITSM Management**: Efficiently handle ticket creation, updates, responses, and asset management
- **Workflow Acceleration**: Reduce manual intervention in routine IT service tasks

## Supported Freshservice Modules

**This MCP server currently supports operations across a wide range of Freshservice modules**:

-  Tickets
-  Conversations
-  Products
-  Requesters
-  Agents
-  Agent Groups
-  Requester Groups
-  Canned Responses
-  Canned Response Folders
-  Workspaces
-  Solution Categories
-  Solution Folders
-  Solution Articles

## Components & Tools

The server provides a comprehensive toolkit for Freshservice operations:

### Ticket Management

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `create_ticket` | Create new service tickets | `subject`, `description`, `source`, `priority`, `status`, `email` |
| `update_ticket` | Update existing tickets | `ticket_id`, `updates` |
| `delete_ticket` | Remove tickets | `ticket_id` |
| `search_tickets` | Find tickets matching criteria | `query` |
| `get_ticket_fields` | Retrieve ticket field definitions | None |
| `get_tickets` | List all tickets with pagination | `page`, `per_page` |
| `get_ticket` | Retrieve single ticket details | `ticket_id` |

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

- "Create a new incident ticket with subject 'Network connectivity issue in Marketing department' and description 'Users unable to connect to Wi-Fi in Marketing area', set priority to high"
- "Update the status of change request #45678 to 'Approved'"
- "List all critical incidents reported in the last 24 hours"
- "Show asset details for laptop with asset tag 'LT-2023-087'"
- "Create a change request for scheduled server maintenance next Tuesday at 2 AM"

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
