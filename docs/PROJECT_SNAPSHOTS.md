# Local Projects snapshots

The optional Projects-to-Backpack bridge persists dated normalized DTOs in an
explicit SQLite store. GitHub remains authoritative for current board state.
Reading a snapshot never refreshes it or edits a board.

Install the Projects package with its `backpack` extra when the distributions are
available from an index, or install the actual Projects and Backpack wheels from
their source checkouts. Both libraries retain zero mandatory runtime dependencies.
For catalog/MCP consumers, install the existing capability-family wheels separately.
CI uses a reviewed pinned Backpack revision and synthetic transport data.

```python
from backpack_store import Backpack
from hidden_moves_github_projects import ProjectsClient
from hidden_moves_github_projects.snapshots import (
    capture_project_item, register_snapshot_codec,
)

# Supply the application's explicit credential resolver; it is never persisted.
client = ProjectsClient(resolve_token)
with Backpack.open("snapshots.sqlite") as store:
    register_snapshot_codec(store)
    written = capture_project_item(
        client, store, "example", "organization", 2, "PROJECT_ITEM_ID",
        max_pages=2, tags=["github", "snapshot"],
    )

with Backpack.open("snapshots.sqlite") as store:
    register_snapshot_codec(store)
    record = store.get_record(written.id)
    snapshot = record.value
    print(snapshot.captured_at, snapshot.project.id, snapshot.item.id)
```

`resolve_token` is application configuration, not a tool argument. The application
selects the database path and registers the trusted snapshot codec explicitly.
There is no default database, dynamic model import or automatic synchronization.

`ProjectItemSnapshot` contains the full normalized `Project` and `ProjectItem`
plus a UTC capture time. The record has a distinct local UUID, stable type key
`github.project_item_snapshot`, payload schema version 1 and Backpack revision.
Provenance retains the source Project URL, `github-projects` system, remote item
ID and capture time. Remote content IDs and issue/PR numbers remain named inside
the normalized item DTO; they never become the local UUID.

`fetch_project_item` and `store_snapshot` expose the two effects separately.
`capture_project_item` composes them: complete the bounded fetch first, then insert
one atomic local record. A failed fetch inserts nothing; failed persistence rolls
back the record. Fetching follows at most `max_pages` (default 10) item pages and
retains the client's nested field-value limits. Missing items or exhausted budgets
raise typed errors. It preserves redaction, unsupported-field diagnostics and
`field_values_complete`; a captured page does not imply a complete board snapshot.

The standard Backpack read provider can expose the stored snapshot as a concrete
JSON record view. It cannot update GitHub. Run
`python examples/projects_snapshot_demo.py` for the complete offline fetch/store/
reopen/catalog proof. The synthetic bridge suite is separate from the standalone
Projects client tests:

```sh
python -m unittest discover -s packages/hidden-moves-github-projects/snapshot_tests -v
```

For an explicit live read with the existing GitHub CLI login:

```sh
python examples/projects_capture.py --database snapshots.sqlite \
  --owner OWNER --owner-kind organization --number PROJECT_NUMBER \
  --item-id PROJECT_ITEM_ID --max-pages 2
```

The script captures the token internally, performs bounded reads, writes one local
record and reopens it. Its output includes IDs, source URL, capture time and
completeness diagnostics without printing credentials, titles or content bodies.

## Verified live capture

On October 4, 2026 at `22:00:29.043023Z`, one explicitly selected item from
[Outside Labs Project 2](https://github.com/orgs/outside-labs/projects/2) was fetched
using the existing CLI login and stored in a temporary local database. Reopening
recovered the typed Project/item, separate local UUID, schema identity and source
provenance. `field_values_complete` remained false with an
`unsupported_field_value` diagnostic. The proof performed no GitHub mutations,
model API calls or deployment; CI uses fixtures instead of account credentials.
