# Hosting freshservice_mcp as a Remote MCP Server for Microsoft Foundry

**Date:** 2026-07-27
**Status:** Approved for planning
**Spec 2 of 2.** Executes after `2026-07-27-freshservice-solutions-read-tools-design.md`.

## Problem

The Freshservice knowledge base tools must be available to Foundry agents in the project
`lrsagenthub-dev-usw3`. Today `server.py` ends with:

```python
mcp.run(transport='stdio')
```

**Foundry Agent Service only accepts remote MCP server endpoints.** A stdio server cannot be
registered at all. Per Microsoft's documentation, a local MCP server must be self-hosted on Azure
Functions or Azure Container Apps to obtain an endpoint.

## Verified platform facts

Confirmed against Microsoft Learn on 2026-07-27.

### Foundry side

| Fact | Consequence |
|---|---|
| Agent Service accepts **remote endpoints only** | Hosting is mandatory, not optional |
| **Non-streaming MCP tool calls time out at 50 s** | The binding runtime limit — tighter than an HTTP-triggered Function's 230 s |
| **Max 128 tools registered per agent** | The server has 97; Spec 1 adds 7 → 104. Real headroom, but finite |
| `allowed_tools` filters which tools an agent sees | Lets an agent register only the KB subset instead of all 104 |
| `require_approval` defaults to **`always`** | Left at the default, every call stalls awaiting developer approval |
| **West US 3 supports the MCP tool** | `lrsagenthub-dev-usw3` is in a supported region. Verified in the tool-by-region matrix |
| Tool support requires **both** model and region support | The agent's model deployment must also support MCP |
| Credentials belong in a **project connection** | No secrets in agent definitions or prompts |

### Azure Functions side

Functions offers two hosting routes. The distinction matters, because one requires rewriting every
tool and the other does not:

| Route | What it means here |
|---|---|
| **Functions MCP extension** (`functions-bindings-mcp`) | Rebuild all 104 tools as Functions triggers. Endpoint `/runtime/webhooks/mcp`, secured by the `mcp_extension` system key. **Rejected** — a full rewrite for no benefit |
| **Self-hosted MCP server** (public preview) | Keep the MCP-SDK server as-is and add Functions artifacts. Microsoft: *"You don't need to make any code changes to the server to host it on Azure Functions."* **Chosen** |

Self-hosted preview requirements, all of which we must satisfy:

1. **Stateless servers using the `streamable-http` transport.**
2. Python, TypeScript, C#, or Java MCP SDKs. (This repo is the Python SDK — `mcp[cli]>=1.3.0`.)
3. **Must run on a Flex Consumption plan.**
4. App setting `AzureWebJobsFeatureFlags=EnableMcpCustomHandlerPreview`.
5. Python also requires `PYTHONPATH=/home/site/wwwroot/.python_packages/lib/site-packages`.
6. Local runs use `func start` (Core Tools ≥ 4.5.0). F5 debugging is not supported.
7. Creating the Entra app requires permission to do so in the subscription.

The official sample is `Azure-Samples/mcp-sdk-functions-hosting-python`, scaffolded with
`azd init --template mcp-sdk-functions-hosting-python`. Its `server.py` shows the one meaningful
code change:

```python
mcp = FastMCP("weather", stateless_http=True)
```

## Why Azure Functions over Container Apps

| | Azure Functions | Container Apps |
|---|---|---|
| Transport | `streamable-http` required | HTTP POST/GET |
| Auth | Built-in App Service auth (Entra, OAuth per MCP authorization spec), or keys | **Custom auth you implement** |
| OS-level deps | Not supported | Anything in the image |
| Containers | Not supported | Required |

Spec 1's dependencies (`pypdf`, `openpyxl`, `python-docx`) are pure Python with **no OS-level
dependencies**, so the single real Functions restriction does not bind. Container Apps would mean
building and maintaining custom authentication for no gain.

Note a documentation conflict worth knowing: the Foundry MCP page states Functions hosting is
"key-based only. OAuth needs API Management," while the Functions self-hosted page documents
**built-in App Service OAuth** implementing the MCP authorization spec (401 challenge, Protected
Resource Metadata) via Entra ID. The Functions page is more recent and specific. Auth is therefore
an implementation-time decision — see [Open question](#open-question-authentication-mode).

## Goals

- A deployed HTTPS `streamable-http` MCP endpoint reachable by Foundry.
- The 7 KB tools from Spec 1 callable by an agent in `lrsagenthub-dev-usw3`.
- Authenticated; no anonymous access to Freshservice data.
- The Freshservice API key held in Azure config, never in the repo or an agent definition.
- Existing stdio usage (Claude Code, `tests/test-fs-mcp.py`) keeps working unchanged.

## Non-goals

- **No new tools or tool-behaviour changes.** Spec 1 owns those.
- **No rewrite to the Functions MCP extension model.**
- **No API Management**, unless the auth decision forces it.
- **No production hardening** (VNet integration, private endpoints, APIM governance, autoscale
  tuning). This targets the `-dev-` project; production is a later concern.
- **No Azure API Center registration**, though it is the documented path for an org-wide private
  tool catalog and is worth revisiting once this proves out.

## Architecture

```
freshservice_mcp/
  src/freshservice_mcp/
    server.py          (edit)  stateless_http=True; transport selected by env var
    common.py          (Spec 1)
    solutions.py       (Spec 1)
  function_app.py      (new)   Functions entry point
  host.json            (new)   Functions host config
  requirements.txt     (new)   Functions deployment deps
  infra/               (new)   Bicep from the azd template
  azure.yaml           (new)   azd service definition
  .funcignore          (new)   excludes .venv, tests, docs from the package
```

### Dual transport

`main()` selects transport from an environment variable so one codebase serves both consumers:

```python
def main():
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)
```

Default `stdio` keeps Claude Code and the existing test file working with **no config change**. The
Function App sets `MCP_TRANSPORT=streamable-http`.

`FastMCP` is constructed with `stateless_http=True`, which the preview requires. This is safe for
stdio use and is the only change to how the server is instantiated.

### Configuration

| Setting | Value | Notes |
|---|---|---|
| `FRESHSERVICE_DOMAIN` | `lrs.freshservice.com` | App Setting |
| `FRESHSERVICE_APIKEY` | Key Vault reference | **Never** a literal App Setting |
| `MCP_TRANSPORT` | `streamable-http` | |
| `AzureWebJobsFeatureFlags` | `EnableMcpCustomHandlerPreview` | Required by the preview |
| `PYTHONPATH` | `/home/site/wwwroot/.python_packages/lib/site-packages` | Required for Python |

The Function App gets a system-assigned managed identity with a Key Vault `get` secret role
assignment. `load_dotenv()` in `server.py` is harmless in Azure (no `.env` present) and stays for
local development.

### Foundry wiring

In `lrsagenthub-dev-usw3`:

1. Create a project connection holding the endpoint credential.
2. Attach the MCP tool to the agent:

```python
MCPTool(
    server_label="freshservice_kb",
    server_url="https://<app>.azurewebsites.net/mcp",
    project_connection_id="<connection-id>",
    allowed_tools=[
        "list_solution_subfolders",
        "get_solution_folder_tree",
        "list_solution_articles_metadata",
        "get_solution_article_content",
        "list_solution_article_attachments",
        "read_solution_attachment",
        "search_solution_articles",
        "get_all_solution_category",
        "get_solution_category",
    ],
    require_approval="never",
)
```

Two settings carry most of the value:

- **`allowed_tools`** exposes 9 KB tools instead of all 104. Beyond staying clear of the 128-tool
  cap, this is the single biggest lever on tool-selection quality — Microsoft's own guidance is
  "register only required tools; prefer fewer, reusable tools." An agent shown 104 Freshservice
  tools will pick badly.
- **`require_approval="never"`** is safe *because* Spec 1's tools are strictly read-only. Had they
  included writes, the default `always` would be correct.

The exact `server_url` path suffix (`/mcp` vs the app root) is set by the azd template's routing;
confirm from the `azd up` output rather than assuming.

## Open question: authentication mode

Two viable modes, to be settled during implementation once the endpoint exists:

**A. Built-in App Service auth (Entra ID)** — the azd template's default, implementing the MCP
authorization spec. Strongest option, no shared secret, and it matches Foundry's recommendation to
prefer Entra when the server supports it. Requires permission to create an Entra app, and Foundry
must be configured with the matching audience.

**B. Function key** — simpler; the key lives in a Foundry project connection. Adequate for a dev
project, but a long-lived shared secret.

Recommendation: attempt A first, since the template scaffolds it. Fall back to B if Entra app
creation or the Foundry audience configuration blocks progress. Not a blocker either way — the work
below is identical.

## Implementation phases

**Phase 1 — Local streamable-http.** Add `stateless_http=True` and the `MCP_TRANSPORT` switch. Run
`mcp.run(transport="streamable-http")` locally and verify `tools/list` returns 104 tools and a KB
tool executes end to end. Confirm stdio still works.

**Phase 2 — Functions scaffold.** Scaffold the azd template into a scratch directory and port its
artifacts (`function_app.py`, `host.json`, `azure.yaml`, `infra/`, `.funcignore`). Generate
`requirements.txt` from `pyproject.toml`. Run `uv run func start` locally — the repo already uses
`uv`, so this fits existing tooling. Verify with MCP Inspector.

**Phase 3 — Deploy.** `azd up` into the LRS dev subscription on a Flex Consumption plan. Set the app
settings above, wire the Key Vault reference and managed identity, and confirm the endpoint responds
to an authenticated `tools/list`.

**Phase 4 — Foundry integration.** Create the project connection, attach the MCP tool with
`allowed_tools` and `require_approval="never"`, and run agent smoke tests:

- "What folders exist under CX Rosemont FSO?" → exercises the folder tree
- "What's in the Shields Township price sheet?" → exercises article content
- "What does the hauling garage spreadsheet say for Aledo?" → exercises attachment extraction
  end-to-end (attachment 31009362843; expected answer: garage `MONMOUTH`, rep `STEVE RAMOS`)

The third test is the real acceptance criterion: it proves an agent can read *inside* an attachment,
which is the goal that started this work.

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| **`requires-python = ">=3.13"` may exceed the Functions Python runtime.** `.python-version` pins 3.13 | **High** | Verify supported Flex Consumption Python versions in Phase 2 *before* deploying. If 3.13 is unsupported, relax to `>=3.11` — nothing in the codebase requires 3.13 |
| Self-hosted MCP hosting is **public preview** | Medium | Accepted for a dev project. The Functions MCP extension is the fallback, at the cost of a rewrite |
| **Flex Consumption plan required** — differs from LRS's existing App Service Plans | Medium | New dedicated plan; do not attach to a shared plan. See the `lrs-enterprise-apps` guidance on not disturbing shared plans |
| 50 s Foundry tool-call timeout | Medium | Already designed for in Spec 1 (bounded traversal, size caps, one attachment per call) |
| Cold start on Flex Consumption with `pypdf`/`openpyxl` | Low–Medium | All pure Python and small. Measure in Phase 3; consider an always-ready instance if it bites |
| 104 tools makes a large `tools/list` payload | Low | Under the 128 cap; `allowed_tools` narrows what the agent sees |
| Entra app creation may be blocked by tenant policy | Low | Auth mode B is the documented fallback |
| Transport change could regress the 97 existing tools | Low | Transport is orthogonal to tool logic; `stdio` remains the default so existing consumers are untouched |
| Preview feature flag `EnableMcpCustomHandlerPreview` may change | Low | Pinned in Bicep; revisit at GA |

## Success criteria

1. An authenticated `tools/list` against the deployed endpoint returns all 104 tools.
2. Both stdio and streamable-http work from one codebase with no code edits between them.
3. A Foundry agent in `lrsagenthub-dev-usw3` reads a KB article body.
4. That agent reads the contents of an XLSX attachment and answers a question from a specific row.
5. No credential appears in the repo, an App Setting literal, or an agent definition.
