# Agent capability implementation plan

Prepared: October 31, 2026

## Useful first workflow

Let an agent inspect a deliberately selected set of workspace text files,
retrieve bounded numbered excerpts, and locate literal evidence. Return typed
results with relative paths, content digests, and explicit continuation so the
same operation is useful in Python, a selected catalog, local MCP, and function
tools. Keep the capability registry and existing adapters unchanged.

The existing foundation already implements typed definitions, provider discovery,
target binding, schemas, selected catalogs, MCP, function tools, GitHub Projects,
and optional Backpack snapshots. The remaining hosted tasks
[PLG-02](https://github.com/outside-labs/hidden_moves/issues/11),
[PLG-03](https://github.com/outside-labs/hidden_moves/issues/12), and
[PLG-04](https://github.com/outside-labs/hidden_moves/issues/13) retain their
identity/service decisions and publication boundaries. This local track does
not depend on hosted identity.

## Rolling batch

Each row is one focused branch/PR. Build dependent work on the preceding branch,
start CI as each PR becomes ready, then squash merge in dependency order.
The [Hidden Moves Project](https://github.com/orgs/outside-labs/projects/2) and
linked issues own current task status.

| Task | Scope | Acceptance |
| --- | --- | --- |
| [AGT-01](https://github.com/outside-labs/hidden_moves/issues/31) | Portable skill and workflow plan | Describe actual discovery, binding, selection, invocation, and verification; validate the skill against the current APIs |
| [AGT-02](https://github.com/outside-labs/hidden_moves/issues/32) | Standalone workspace client | Explicit root and exact file selection; bounded listing, excerpts, and literal search; typed completeness/digests; path and resource-limit tests; standard library only |
| [AGT-03](https://github.com/outside-labs/hidden_moves/issues/33) | Provider, configured host, and interoperability | Explicit file and capability selection; JSON CLI and stdio MCP; equivalent Python/catalog/MCP/function results; wheel and CI coverage; exercise the skill on real repository files |

## Implementation choices

- Add one independently usable package, `packages/hidden-moves-workspace`, rather
  than new domain modules in the core. Optional integration reuses the existing
  Hidden Moves, MCP, and function-tool adapters.
- Bind a workspace object configured with an exact relative-file selection and
  a finite per-file byte ceiling. Do not infer a root, recursively crawl a tree,
  or implicitly include hidden/configuration files.
- Expose selected-path listing, numbered line excerpts, and literal search.
  Report a next position when results are bounded. Digests identify the content
  actually read; they do not establish a transactional filesystem snapshot.
- Reject traversal, absolute/non-selected paths, symlink components, special
  files, oversized files, and unsupported text. Bound both input work and output.
  The local host is for trusted workspaces, not adversarial filesystem isolation.
- Keep imports, discovery, and descriptions free of content reads. Calls never
  write files, invoke a shell, execute source, or fetch network data.
- A portable skill lives at [skills/hidden-moves/SKILL.md](skills/hidden-moves/SKILL.md).
  Revise it after exercising the implementation. Keep conditional detail in the
  maintained provider documentation instead of duplicating APIs in the skill.

## Verification and next decisions

Use synthetic temporary files for path handling, Unicode, long lines, byte
limits, continuation, and changes between calls. Run the client tests without
Hidden Moves installed, then exercise installed provider discovery, selection,
invalid inputs, all three adapters, and a real stdio handshake/list/call.
Extend the existing wheel inspection and platform CI; use focused local checks
for changed behavior and a short final-main smoke.

After this batch, choose the next plugin from an observed repeated workflow.
Potential candidates are structured JSON extraction, patch preparation with
stale-content checks, or typed task-queue summaries. File writes, arbitrary code
execution, remote hosting, and new external services need their own concrete
contracts. No dependency version changes or package publication belong to this
batch.
