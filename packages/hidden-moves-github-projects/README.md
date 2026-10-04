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
  .venv/bin/python -m unittest discover -s packages/hidden-moves-github-projects/tests
```

Tests use synthetic response fixtures, an injected transport, and blocked side
effects. CI builds and installs the actual wheel across the family platform matrix.
Live read access and capability-host interoperability are separate proofs.
