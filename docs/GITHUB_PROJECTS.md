# Read-only GitHub Projects consumer

The separate `hidden-moves-github-projects` distribution provides an ordinary typed
GraphQL client, optional provider, and configured local MCP host. Its
[package guide](../packages/hidden-moves-github-projects/README.md) covers the API,
identities, paging, credentials, transport, and errors.

## Synthetic consumer proof

```sh
uv venv /tmp/projects-demo-env
uv pip install --python /tmp/projects-demo-env/bin/python . ./examples/text-plugin \
  ./packages/hidden-moves-mcp ./packages/hidden-moves-openai \
  ./packages/hidden-moves-github-projects
/tmp/projects-demo-env/bin/python examples/projects_fixture_demo.py
```

The demonstration compares the full normalized `ItemPage` through ordinary Python,
a selected catalog, an actual stdio MCP subprocess, and offline function tools.
It fails if payloads differ or the MCP host exposes an unexpected selection.
Synthetic records include issues, PRs, drafts, redaction, distinct identities, and
typed field values. No account credential or model API call is involved.

The Projects tests also reject unselected calls, verify credential-free discovery,
unbound inspection, and all four wrappers. The ordinary wheel runs independently
with no third-party packages.

## Bounded live read

Use an existing authorized `github.com` login in `gh`. The explicit resolver
captures its credential only when a read executes, without printing it or changing
login configuration. Classic-token `read:project`/`project` scopes and GitHub App
permissions differ; private content may need repository access. An actual query
confirms access. See [GitHub's Projects API guide](https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-api-to-manage-projects).

```sh
/tmp/projects-demo-env/bin/python examples/projects_read.py \
  outside-labs organization 2 --page-size 2 --field-page-size 2
```

Replace the owner identity and number with an allowed Project. The script makes
three fixed reads: Project metadata, one field page, and one item page. It prints
capture time, source URL, counts, cursors, and diagnostics, without dumping item
titles/bodies or credentials.

Verified October 4, 2026 at 21:04 UTC against the
[Hidden Moves Project](https://github.com/orgs/outside-labs/projects/2): `get`
returned Project 2 with node ID `PVT_kwDOE0y-h84BltEV`; the field page contained
13 definitions and no next page; the two-item page reported a next cursor.
Both items reported incomplete nested values at the deliberately small field-page
size, with `field_values_incomplete` and `unsupported_field_value` diagnostics.

This establishes read access at capture time. It does not represent a complete
board or current data indefinitely. Live authorization and fixture consumer
equivalence are separate proofs. No Project mutation was part of the access proof.

## Exposure and limitations

The optional host requires explicit repeated `--move` selections. Generic CLI
inspection needs no account; invocation requires a bound client. Text, number,
date, single-select, and iteration values are supported. Other values remain
typed placeholders with diagnostics. Continue outer connections with their own
cursors; nested continuation uses the item ID and nested cursor through the
ordinary client. The four initial tools report nested incompleteness explicitly.

The local host uses one configured identity, finite socket/response budgets, and
SDK stdio cleanup. Remote hosting requires request-scoped user authorization,
credentials, and synchronous-work offloading. Function tools dispatch offline;
applications own any later model request. Package upload and a public plugin
remain separate release decisions.
# Dated local snapshots

The optional [snapshot bridge](PROJECT_SNAPSHOTS.md) now stores a normalized
Project item in an explicitly configured Backpack file and recovers its typed DTO
after reopening. Capture time and completeness diagnostics are visible; GitHub
continues to own current board state.
