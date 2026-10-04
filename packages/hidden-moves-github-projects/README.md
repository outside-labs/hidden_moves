# GitHub Projects client

An experimental read-only GraphQL client with concrete typed records. The ordinary
Python library uses only the standard library and does not import Hidden Moves,
MCP, or an API SDK. Capability integration is an optional extra.

## Ordinary Python

```python
from hidden_moves_github_projects import ProjectsClient

# The application supplies its credential resolver; construction performs no I/O.
client = ProjectsClient(resolve_token, timeout=10)
project = client.get("example", "organization", 2)
fields = client.fields(project.id)
page = client.items(project.id, page_size=20, field_page_size=50)
```

`resolve_token` is an application-owned callable returning an authorized token.
Keep credentials outside source control and tool arguments. A successful Project
query verifies access; repository access alone does not establish Projects access.
Classic-token scopes and GitHub App permissions differ. See the
[GitHub Projects API guide](https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-api-to-manage-projects).

## Operations and identities

- `list(owner, owner_kind, cursor=None, page_size=50)` returns a Project page.
- `get(owner, owner_kind, number)` returns a Project record.
- `fields(project_id, cursor=None, page_size=50)` returns a field-definition page.
- `items(project_id, cursor=None, page_size=50, field_page_size=50)` returns an item page.
- `item_field_values(item_id, cursor=None, page_size=50)` continues nested values.
- `iter_item_pages(project_id, ..., max_pages=10)` explicitly iterates bounded pages.

Owner kind is `user` or `organization`. Node IDs are opaque strings. Project number,
Project node ID, item node ID, content node ID, and issue/PR number are separate
identities. Item content distinguishes issues, PRs, drafts, redaction, and unknown
types. Select options retain IDs/names; iteration definitions retain active and
completed iteration metadata.

## Paging and completeness

Each requested connection returns `page_info.has_next_page` and `end_cursor`.
Every page contains at most the requested 1–100 entries. A last page with an input
cursor still represents only that page. Nested item field values have independent
page information and `field_values_complete`; continue them with the item ID and
their own cursor. An iterator that reaches its page budget raises
`PaginationLimitError` instead of silently claiming to have read the board.

Text, number, date, single-select, and iteration values are normalized. Unsupported
value types remain visible as typed placeholders and diagnostics; their omitted
payloads make `field_values_complete=False`. Unknown field/content types and null
nodes also produce diagnostics. Issue assignees, labels, linked PRs, and repository
connections are not queried. No unbounded nested connection is silently returned.

## Transport and errors

The default transport makes one HTTPS POST per explicit read, uses a finite socket
timeout, reads at most a configured byte budget, closes the response, and refuses
redirects carrying credentials. An explicit HTTPS endpoint supports application-
configured enterprise API URLs. Inject a `Transport` for synthetic or custom HTTP
behavior; it receives a `urllib.request.Request` and the timeout/byte budget and
returns `HTTPResponse(status, body)`.

HTTP failures, GraphQL errors (including HTTP 200 with partial data), malformed or
oversized responses, unavailable resources, and iterator limits have separate error
types. Upstream error text and resolver/transport exception messages are sanitized.
Requests are not retried automatically. Clients do not resolve local login state
unless the application explicitly supplies such a resolver.

## Verification

```sh
PYTHONPATH=packages/hidden-moves-github-projects/src \
  .venv/bin/python -m unittest discover -s packages/hidden-moves-github-projects/tests -p test_client.py
```

Tests use synthetic response fixtures, an injected transport, and blocked side
effects. CI builds and installs the actual wheel across the family platform matrix.
Live read access and capability-host interoperability are separate proofs.

## Optional provider and local host

Install `[moves]` for the optional provider or `[host]` for the MCP executable.
For local development install the family packages together:

```sh
uv pip install --python .venv/bin/python . ./packages/hidden-moves-mcp \
  ./packages/hidden-moves-openai ./packages/hidden-moves-github-projects
hidden-moves --plugin github-projects moves show github.projects.items
```

The zero-argument `github-projects` entry-point factory never resolves credentials
or makes a request. It advertises target-bound `github.projects.list/get/fields/items`
with read-only, non-destructive, external annotations. Generic framework inspection
needs no token; account invocation needs an application-bound `ProjectsClient`.

```python
from hidden_moves_github_projects import ProjectsClient
from hidden_moves_github_projects.host import build_catalog, resolve_gh_token
from hidden_moves_mcp import MCPAdapter
from hidden_moves_openai import FunctionToolAdapter

client = ProjectsClient(resolve_gh_token, timeout=10)
catalog = build_catalog(client, ["github.projects.items"])
mcp = MCPAdapter(catalog)
functions = FunctionToolAdapter(catalog)
```

`resolve_gh_token` explicitly captures the existing `github.com` login from `gh`
when a read executes. It neither prints the token nor changes login/scopes. A
local MCP host can launch the installed executable:

```json
{
  "command": "/absolute/path/to/environment/bin/hidden-moves-github-projects",
  "args": ["--move", "github.projects.items", "--timeout", "10"]
}
```

Only selected capabilities list or dispatch. The host supplies no arbitrary query,
shell, or Project-editing tool. The SDK owns stdio protocol and process cleanup.
This configured local application uses one local identity; a remote host requires
request-scoped authorization and credentials. Sync HTTP executes inline here;
concurrent remote hosting must provide its own offloading and resource strategy.

The consumer tests use a synthetic transport and compare ordinary Python, the
selected catalog, actual stdio MCP initialize/list/call, and offline function-tool
dispatch. Install the local family and run:

```sh
python -m unittest discover -s packages/hidden-moves-github-projects/tests
```

Inspection, fixture tests, and offline function tools require no model API call.
# Optional local snapshots

The `backpack` extra enables an explicit Projects-to-Backpack bridge. Store dated
normalized Project/item DTOs with a local UUID and source provenance, then reopen
them without GitHub access. Fetch and persistence can be invoked separately; no
snapshot read updates a board or claims to be live. See the
[snapshot guide](../../docs/PROJECT_SNAPSHOTS.md) and run
`python examples/projects_snapshot_demo.py` from the repository for the offline
proof. Backpack remains an independent package with no mandatory runtime
dependencies.
# Optional bounded writes

The separate `ProjectsWriter` and `github-projects-write` provider support adding
an existing Issue/PR and setting a dynamically resolved single-select choice.
The host authorizes explicit Project IDs and selects writes separately from the
default read profile. See the [write guide](../../docs/PROJECT_WRITES.md) for
expected-value checks, verified/unverified receipts and the remaining disposable
fixture gate. There are no bulk, deletion or archive tools.
