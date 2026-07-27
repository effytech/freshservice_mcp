# Freshservice Solutions / Knowledge Base — Deep Read Tools

**Date:** 2026-07-27
**Status:** Approved for planning
**Spec 1 of 2.** Spec 2 (`2026-07-27-freshservice-mcp-foundry-hosting-design.md`) covers hosting the
server as a remote MCP endpoint for Microsoft Foundry. This spec is written to that target's
constraints but does not depend on it — every tool here is testable over stdio today.

## Problem

The MCP server has six solution tools (`get_all_solution_category`, `get_solution_category`,
`get_list_of_solution_folder`, `get_solution_folder`, `get_list_of_solution_article`,
`get_solution_article`). They cannot reach the knowledge base's deepest levels, and the levels they
do reach return payloads far too large to put in an agent's context.

Two concrete failures:

1. **Subfolders are unreachable.** `get_list_of_solution_folder` calls
   `solutions/folders?category_id=X`, which returns only top-level folders. Folders carry
   `has_subfolders` and `parent_id`, and the category `CX Rosemont FSO` (31000021923) contains
   **55 folders nested 3 levels deep**. Everything below level 0 is invisible.
2. **Every tool passes raw JSON through.** All six do `json.dumps(response.json())`. The article
   list endpoint embeds each article's full `description` HTML, so one folder page returns up to
   **1.9 MB**.

The goal: read the knowledge base down to article bodies and attachment contents, in payloads an
agent can actually consume.

## Verified API behaviour

Measured against `lrs.freshservice.com` on 2026-07-27. These numbers drive every design decision
below; they are not estimates.

| Observation | Evidence |
|---|---|
| Folders form a recursive tree | `solutions/folders?parent_id=<id>` returns children. Category 31000021923 → 55 folders, `max_depth=3` |
| Article bodies are enormous | One article's `description` = **461,674 bytes**; largest found = **1,280,210 bytes** |
| `description_text` is supplied by the API | Same article: 461,674 B HTML → **3,024 B** plain text. No HTML converter needed |
| List responses embed full bodies | `description` was **99%** of a 466 KB single-article response. Folder pages reached 1.9 MB |
| `per_page` / `page` work; no `Link` header | `per_page=15` over folder 31000033288 → 15, 15, 1. End of list = short page |
| Search works, unusably raw | `solutions/articles/search?search_term=price%20sheet` → 30 results = **4,009,746 bytes** |
| `attachments` shape differs by endpoint | **Detail:** list of objects (`id`, `name`, `content_type`, `size`, `attachment_url`, `canonical_url`, `has_access`). **List:** list of filename strings + parallel `attachment_urls` |
| Presigned URLs last 24 h | `Expires` − now = **86,400 s**. Tampered signature → 403 |
| Download by ID works in one call | `GET /api/v2/attachments/{id}` + `follow_redirects=True` → 200, 304,943 B, **0.70 s**. Forwarding the Basic auth header does not break S3. Bad ID → clean 404 |
| `content-length` precedes the body | Enables rejecting oversized files before buffering |
| `size: 0` attachments exist | 2 of 14 sampled returned HTTP 200 with **0 bytes**. A real data condition, not an error |
| Extraction works on real files | `openpyxl` → 123 rows from `HAULING 2-3-251.xlsx`. `pypdf` → 800–964 chars/page across 4 enrollment PDFs, text layer present |
| Rate limit | `x-ratelimit-total: 500` per minute |

## Goals

- Reach every folder level, including subfolders.
- Read article bodies with bounded, pageable output.
- List attachment metadata and extract attachment **text contents** (PDF, XLSX, DOCX, CSV, TXT).
- Search articles with lean output.
- Every tool returns in well under 50 s and in a size an agent can consume.

## Non-goals

- **No writes.** Read-only. Existing create/update/publish tools are untouched.
- **No transport or hosting changes.** Spec 2.
- **No OCR.** Scanned PDFs with no text layer are reported as such, not processed.
- **No caching or indexing.** Every call is stateless and self-contained (a hosting requirement).
- **No changes to the six existing solution tools.** Back-compat is absolute; `tests/test-fs-mcp.py`
  imports them by name.

## Constraints inherited from Spec 2

Recorded here because they shape the tool signatures, and honouring them now is free:

1. **50 s timeout** on non-streaming MCP tool calls in Foundry Agent Service. The binding limit —
   tighter than an HTTP-triggered Function's 230 s. No unbounded traversal, no multi-attachment
   extraction per call.
2. **128 tools per agent.** The server already has 97. Adding 7 → 104.
3. **Stateless only.** No local disk, no cross-call state. A returned file path would be a dead
   reference to the client, which is why attachment text is extracted server-side rather than
   downloaded and pointed at.
4. **Pure-Python dependencies only.** Azure Functions does not support OS-level dependencies.

## Architecture

`server.py` is 3,520 lines / 131 KB. Appending 7 tools makes a bad file worse, so:

```
src/freshservice_mcp/
  common.py      (new)  shared config, auth headers, error envelope, small helpers
  solutions.py   (new)  the 7 tools + pure transform helpers; exposes register(mcp)
  server.py      (edit) imports from common; calls solutions.register(mcp)
```

**`common.py`** holds what both modules need, moved verbatim out of `server.py`:
`FRESHSERVICE_DOMAIN`, `FRESHSERVICE_APIKEY`, `get_auth_headers()`,
`get_auth_headers_multipart()`, `_coerce_to_list()`, plus a new `error_envelope()` factoring the
`except httpx.HTTPStatusError` block, which is currently copy-pasted **94 times** in `server.py`.

`server.py` replaces its local definitions with `from .common import ...`. Because the names stay
resident in `server.py`'s namespace, **all 97 existing call sites and every test import keep
working unchanged.** This is the only edit to existing code.

**`solutions.py`** defines `register(mcp)`, called from `server.py` after the `mcp` instance is
created. This avoids a circular import without restructuring how `mcp` is created.

Transform logic (projection, truncation, tree bounding, extraction dispatch) lives in module-level
pure functions, separate from the `@mcp.tool()` coroutines that do I/O. That split is what makes
the logic testable without network access — see [Testing](#testing).

## Shared contracts

**Truncation.** Every tool returning text emits the same four fields, so an agent can page
deterministically without guessing:

```json
{ "total_chars": 461674, "returned_chars": 20000, "truncated": true, "next_offset": 20000 }
```

When `truncated` is `false`, `next_offset` is `null`.

**Pagination.** Tools take `page` (1-based) and `per_page`. Since the API sends no `Link` header,
responses include `"has_more": <bool>`, derived from whether the page came back full.

**Error envelope.** Matches the existing style so behaviour is consistent across the server:

```json
{ "error": "<message>", "status_code": <int|null>, "details": <parsed body|text|null> }
```

**Defaults**, chosen from the measurements above:

| Parameter | Default | Rationale |
|---|---|---|
| `max_chars` | 20,000 | ~5k tokens. The 1.28 MB article pages in ~64 slices |
| `max_bytes` | 20,971,520 (20 MB) | Rejected via `content-length` before buffering. Largest attachment seen: 1.16 MB |
| `max_depth` | 3 | Matches the deepest observed nesting |
| `max_nodes` | 300 | The 55-folder category walks in ~10 HTTP calls; this bounds pathological categories |
| `per_page` | 30 | The API default |
| `max_rows` (XLSX) | 500 | `HAULING 2-3-251.xlsx` has 123 |

**Concurrency.** Tree traversal issues sibling requests concurrently through an
`asyncio.Semaphore(5)`. Sequential walking risks the 50 s budget; unbounded concurrency risks the
500-req/min rate limit.

## Tools

### 1. `list_solution_subfolders`

```python
async def list_solution_subfolders(
    parent_folder_id: int, page: int = 1, per_page: int = 30
) -> str
```

`GET solutions/folders?parent_id={parent_folder_id}`. The capability that does not exist today.

Per folder, projects: `id`, `name`, `description`, `parent_id`, `category_id`, `has_subfolders`,
`visibility`, `position`, `updated_at`. Drops the portal/department/group plumbing
(`manage_by_group_ids`, `portal_ids`, `portal_access_mode`, `approval_settings`,
`folder_department_ids`, …), which an agent reading the KB has no use for.

Returns `{ "folders": [...], "count": n, "has_more": bool }`.

### 2. `get_solution_folder_tree`

```python
async def get_solution_folder_tree(
    category_id: int, max_depth: int = 3, max_nodes: int = 300
) -> str
```

Bounded breadth-first walk. Starts at `solutions/folders?category_id={category_id}`, then recurses
into any folder with `has_subfolders: true` until `max_depth` or `max_nodes` is hit.

Returns a nested tree of `{id, name, depth, has_subfolders, article_count: null, children: [...]}`
plus a `limits` block:

```json
{ "limits": { "max_depth": 3, "max_nodes": 300, "nodes_returned": 55,
              "truncated": false, "depth_reached": 3, "elapsed_ms": 3120 } }
```

`truncated: true` means a bound was hit and the agent should drill in with
`list_solution_subfolders` rather than assume it has the whole tree. `article_count` is `null`
because obtaining it would require one article call per folder — far past the 50 s budget.

### 3. `list_solution_articles_metadata`

```python
async def list_solution_articles_metadata(
    folder_id: int, page: int = 1, per_page: int = 30,
    include_preview: bool = False, preview_chars: int = 300
) -> str
```

`GET solutions/articles?folder_id={folder_id}&page&per_page`, then **discards `description` and
`description_text`** — the transformation that turns a 1.9 MB response into roughly 2 KB.

Per article, projects: `id`, `title`, `status`, `article_type`, `folder_id`, `category_id`,
`views`, `thumbs_up`, `thumbs_down`, `created_at`, `updated_at`, `review_date`, `keywords`,
plus derived `attachment_count` (length of the `attachments` array) and `body_chars`
(`len(description_text)`, so an agent can judge cost before fetching).

With `include_preview=True`, adds `preview`: the first `preview_chars` of `description_text`.
Off by default — 30 articles × 300 chars is another 9 KB.

Returns `{ "articles": [...], "count": n, "has_more": bool }`.

### 4. `get_solution_article_content`

```python
async def get_solution_article_content(
    article_id: int, format: str = "text", offset: int = 0, max_chars: int = 20000
) -> str
```

`GET solutions/articles/{article_id}`. The primary "read what's inside" tool.

- `format="text"` (default) → the API's own `description_text`.
- `format="html"` → raw `description`. Same truncation applies. For agents this is 150× more
  expensive for the same information, so the docstring must say so explicitly.
- Any other value → error naming the two valid options.

Returns `title`, `status`, `article_type`, `folder_id`, `category_id`, `tags`, `keywords`,
`updated_at`, `attachment_count`, `content`, and the four truncation fields.

If `description_text` is empty but `description` is not (an article whose body is entirely images
or tables), returns `content: ""` with `"note": "No plain-text body; retry with format='html'"`
rather than a bare empty string.

`offset` beyond `total_chars` returns empty content with `truncated: false`, not an error.

### 5. `list_solution_article_attachments`

```python
async def list_solution_article_attachments(article_id: int) -> str
```

`GET solutions/articles/{article_id}` — the **detail** endpoint specifically, because it returns
attachment objects where the list endpoint returns bare filename strings.

Per attachment, projects `id`, `name`, `content_type`, `size`, `created_at`, `canonical_url`,
`attachment_url`, `has_access`, plus two derived flags:

- `is_empty` — `size == 0`. Verified real: 2 of 14 sampled. Surfaced as data, not an error, so the
  agent knows not to bother calling `read_solution_attachment`.
- `extractable` — whether `content_type` maps to a supported extractor.

Both URLs are included deliberately: `attachment_url` is presigned and valid **24 h**, so a client
that needs the actual binary (to open a spreadsheet, or fill in an enrollment form) can fetch it
directly. Extraction serves reading; the URL serves fetching.

Also returns `cloud_files` verbatim (observed `null`/`[]`; no sample available to design against).

### 6. `read_solution_attachment`

```python
async def read_solution_attachment(
    attachment_id: int, offset: int = 0, max_chars: int = 20000,
    max_bytes: int = 20971520, page_range: Optional[str] = None,
    sheet: Optional[str] = None, max_rows: int = 500
) -> str
```

Takes an `attachment_id` from tool 5 and needs nothing else — verified that
`GET /api/v2/attachments/{id}` with `follow_redirects=True` returns the file in one 0.70 s call.

**Parameter ordering is significant.** `page_range`, `sheet`, and `max_rows` select *what gets
extracted*; `offset` and `max_chars` then page through the resulting text. So `page_range="1-5"`
with `offset=0, max_chars=20000` returns the first 20,000 characters **of pages 1–5 only**, and
`total_chars` reports the length of that selection, not of the whole document. The docstring must
state this, or an agent will misread `total_chars` as the document size.

Sequence:

1. Open a streaming request. Read `content-length`; if it exceeds `max_bytes`, abort **before
   buffering** and return an error carrying the declared size so the agent can decide.
2. Stream into memory with a running cap (defence for a missing `content-length`).
3. If 0 bytes → `{"is_empty": true, "text": "", ...}`, not an error.
4. Dispatch on `content-type`, falling back to the filename extension.
5. Truncate via the shared contract.

| Type | Library | Notes |
|---|---|---|
| `application/pdf` | `pypdf` | Optional `page_range` (`"1-5"`, `"3"`). Per-page text joined with `\n\n`. Returns `page_count`. If total extracted text is empty across pages, returns `text_layer: false` and a note that the PDF is likely scanned — no OCR |
| `…spreadsheetml.sheet` (XLSX) | `openpyxl` | `read_only=True, data_only=True`. Optional `sheet` name; default all, capped at `max_rows` per sheet. Rows joined with tab, sheets prefixed `## <name>`. Returns `sheet_names`. **Caveat:** `data_only=True` returns cached values, so formula cells never calculated by Excel read as `None` |
| `…wordprocessingml.document` (DOCX) | `python-docx` | Paragraphs, then tables as tab-joined rows |
| `text/csv`, `text/plain`, `application/json` | stdlib | Decode UTF-8, fall back to latin-1 (never raises) |
| Anything else (images, legacy `.xls`/`.doc`, ZIP) | — | `extractable: false` + metadata + `attachment_url`. Not an error: the correct outcome is telling the agent to hand the URL to a human |

Extraction runs inside `asyncio.to_thread` so a large PDF parse does not block the event loop.

A malformed file that defeats its parser returns an error envelope naming the library and
exception rather than propagating a traceback.

### 7. `search_solution_articles`

```python
async def search_solution_articles(
    search_term: str, page: int = 1, per_page: int = 30, preview_chars: int = 300
) -> str
```

`GET solutions/articles/search?search_term={term}`, with the same projection as tool 3 — the
transformation that turns the measured 4,009,746-byte response into a few KB.

`search_term` is URL-encoded via `urllib.parse.quote` (already imported in `server.py`). Includes
a `preview` per hit by default — unlike tool 3, because a search result is worthless without a
snippet showing why it matched.

Returns `{ "articles": [...], "count": n, "has_more": bool, "search_term": "..." }`.

## Dependencies

Added to `pyproject.toml`:

```toml
"pypdf>=5.1.0",
"openpyxl>=3.1.5",
"python-docx>=1.1.2",
```

All three are pure Python with no OS-level dependencies — the property that keeps Azure Functions
viable in Spec 2. **`pandas` is explicitly excluded**: tens of MB, slow cold start, and `openpyxl`
already does the job.

## Testing

The existing `tests/test-fs-mcp.py` is print-based scripts against the live API with no assertions
and no test runner; the project has no test dependency. This spec does not rewrite it, but new work
gets real tests.

Add `pytest`, `pytest-asyncio`, and `respx` (an httpx mock transport) as dev dependencies, and
`tests/test_solutions.py`:

**Pure transform tests** — no network, the bulk of the value:

- Article projection drops `description`/`description_text` and derives `attachment_count` /
  `body_chars`. Asserted against a **captured real fixture**, so the 99%-of-payload reduction is
  proven rather than assumed.
- Truncation: `offset`/`max_chars` slicing; `next_offset` arithmetic; `offset` past the end;
  `truncated` false on exact-fit; last page sets `next_offset: null`.
- Tree bounding: `max_depth` stops recursion; `max_nodes` sets `truncated: true`; a folder claiming
  `has_subfolders: true` that returns none does not loop or crash.
- Attachment flags: `size == 0` → `is_empty`; content-type → `extractable` mapping, including an
  unknown type and extension fallback.
- Extraction dispatch by content type, with unknown types returning `extractable: false`.

**Mocked HTTP tests** via `respx`: 404 on a bad ID yields the error envelope; a 401 does too;
`content-length` over `max_bytes` aborts without reading the body; the 302 → presigned redirect is
followed.

**Extraction tests** against small committed fixtures — a 2-page PDF, a 2-sheet XLSX, a DOCX, a
latin-1 CSV — plus a zero-byte file and a truncated/corrupt PDF asserting a clean error envelope.

Live-API checks stay manual and follow the existing file's convention, exercising each tool against
category 31000021923 (55 folders, depth 3), article 31000459933 (461 KB body), article 31000098068
(11 attachments), and attachment 31009362843 (the 304 KB XLSX).

## Risks

| Risk | Mitigation |
|---|---|
| A category far larger than the one sampled blows the 50 s budget in `get_solution_folder_tree` | `max_depth` / `max_nodes` / `Semaphore(5)`, and `elapsed_ms` + `truncated` reported so the agent can tell it got a partial tree |
| `description_text` quality varies; may be empty for image-only articles | Detected and reported with a note pointing at `format="html"` |
| Scanned PDFs yield no text | `text_layer: false` and an explicit note. OCR is out of scope |
| XLSX formula cells read as `None` under `data_only=True` | Documented in the tool docstring; the alternative (`data_only=False`) returns formula strings, which are less useful to an agent |
| Presigned URLs expire after 24 h, so a URL handed to a user can go stale | `canonical_url` is also returned as the durable handle; `read_solution_attachment` always fetches fresh by ID |
| 500 req/min rate limit | Bounded concurrency; a 429 surfaces through the standard error envelope |
| Extracting a 20 MB PDF could approach the 50 s ceiling | Default `max_bytes` is 20 MB against a largest-observed 1.16 MB; extraction runs in a worker thread; `page_range` lets an agent take a slice |
| Splitting helpers into `common.py` touches a file with 97 working tools | Names are re-imported into `server.py`'s namespace, so call sites and test imports are unchanged. Verified by importing every name `tests/test-fs-mcp.py` imports |

## Foundry readiness

Deliberately satisfied here so Spec 2 is purely an infrastructure change:

- Every tool returns in well under 50 s; no tool loops unboundedly.
- No local-disk or cross-call state; attachment text crosses the wire.
- Pure-Python dependencies only.
- 7 tools → 104 total, under the 128-per-agent cap.
- Tool names all carry `solution`, so Foundry's `allowed_tools` can select the KB subset by prefix
  and agents are not shown all 104.
- All 7 are read-only, so `require_approval: "never"` is safe — Foundry defaults to `always`, which
  would otherwise stall every call awaiting developer approval.
