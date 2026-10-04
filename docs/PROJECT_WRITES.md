# Explicit bounded Project writes

The default Projects client, provider and stdio host retain their read-only
selection. A separate `ProjectsWriter`, `github-projects-write` provider and local
host expose only `github.projects.add_item` and `.set_single_select`.

```python
from hidden_moves_github_projects import ProjectsClient
from hidden_moves_github_projects.writes import ProjectsWriter

reader = ProjectsClient(resolve_token)
writer = ProjectsWriter(reader, allowed_projects=["AUTHORIZED_PROJECT_ID"])
added = writer.add_item("AUTHORIZED_PROJECT_ID", "EXISTING_ISSUE_OR_PR_ID")
current = writer.inspect_single_select("AUTHORIZED_PROJECT_ID", added.item_id, "Workflow")
changed = writer.set_single_select(
    "AUTHORIZED_PROJECT_ID", added.item_id, "Workflow", "Desired choice",
    expected_option_id=current.current_option_id,
)
assert changed.verified
```

The application supplies `resolve_token` and the allowed Project IDs. Construction
resolves no credentials and submits no requests. Authorization is trusted host
configuration; a model cannot grant it through tool arguments or a confirmation
boolean. Writes outside that allowlist fail before credential access. GitHub also
enforces the configured credential's permissions; read access alone does not prove
write permission. Hosted per-user authorization remains a separate feature.

`add_item` accepts only an accessible existing Issue or PullRequest, verifies
Project read access, submits one fixed mutation and reads back the returned item
to check Project membership and content identity. It creates no issue or draft.
`set_single_select` scans at most five field-definition pages by default (100
fields/page), resolves exact field/option names to their current IDs, verifies item
membership and checks the expected current option. Empty expected values are
explicit `None`. Missing/ambiguous fields or options fail instead of guessing.

The preflight check is not atomic compare-and-swap: a concurrent GitHub edit can
occur before the mutation. A post-write read verifies the observed choice. Adding
and setting are separate effects; adding can succeed while the following field
change fails. There is no implicit rollback, batch mutation or automatic retry.

## Outcome contract

Successful Python calls return a `WriteReceipt` with `verified=True` and
`acknowledged=True`. Credentials and untrusted upstream messages are absent from
receipts and exception text. A submitted mutation with an uncertain/invalid reply
raises `WriteOutcomeUnknownError`; an acknowledged mutation whose post-write read
fails raises `PostWriteVerificationError`. Both carry the known receipt, an
acknowledgement flag and sanitized failure type. `SelectionConflictError` occurs
before submission when the expected value differs.

Tool wrappers return these uncertain receipts as structured outcomes, preserving
known item/field IDs, `verified=False`, acknowledgement and diagnostic type. Always
check `verified`; transport-level success is not proof of a verified mutation.
An unacknowledged reply does not prove that GitHub made no change. Inspect the
Project before deciding whether to retry.

## Explicit local exposure

```python
from hidden_moves_github_projects.write_host import build_write_catalog

catalog = build_write_catalog(writer, ["github.projects.add_item"])
```

The write provider is loaded and bound separately. Unselected operations remain
unavailable, and the existing read catalog cannot expose these writes. The local
stdio executable also requires both configuration and selection:

```sh
hidden-moves-github-projects-write --allow-project AUTHORIZED_PROJECT_ID \
  --move github.projects.add_item --move github.projects.set_single_select
```

Annotations conservatively declare external, destructive and non-idempotent
effects. Application permissions and caller approval policy enforce access;
annotations do not grant it. There are no deletion, archive, draft, bulk,
iteration-edit or field-definition tools.

## Verification

Synthetic installed-wheel tests cover authorization, Issue/PR types, dynamic
choices, stale values, membership, pagination budgets, partial completion,
uncertain replies, post-write verification and receipts through catalog/MCP/
function consumers. Real stdio checks exercise both writes against synthetic
transport. The actual content, membership and field-value preflight queries and
mutation input/payload schema were checked through bounded read-only GitHub calls.

An explicitly authorized live proof completed on 2026-10-04 at
22:58:43 UTC against the private
[Projects write verification fixture](https://github.com/orgs/outside-labs/projects/4).
The installed wheel added the existing closed
[Backpack setup issue](https://github.com/outside-labs/backpack/issues/1) and
verified its Project membership and content identity. A separate write dynamically
resolved the `Status` field and changed its observed `Done` choice to `Todo`;
the post-write read verified the new option. Both receipts reported
`acknowledged=True` and `verified=True`.

The first field attempt encountered a concurrent status change and raised
`SelectionConflictError` before submission. After inspecting the current value,
only the field change was submitted again; the successful add was not repeated.
The private fixture remains available for review.

`examples/projects_write_fixture.py` demonstrates these two independent operations
on a supplied authorized fixture. A conflict or uncertain outcome requires
inspection before deciding what to submit next. CI uses synthetic transport and
never mutates a GitHub account.
