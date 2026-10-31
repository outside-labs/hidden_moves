---
name: hidden-moves
description: Use or extend Hidden Moves typed Python capabilities through explicit providers, selected catalogs, local MCP hosts, and function tools. Use for capability discovery, binding, structured invocation, or implementing a reusable Hidden Moves plugin.
---

# Hidden Moves

Use ordinary typed Python as the implementation. Register it once and expose a
small, explicitly selected catalog for the current task. Hidden Moves supplies
definitions, binding, schemas, and dispatch; the application supplies resources,
authorization, and the execution environment.

## Find and inspect

In a checkout, start with `uv sync --locked`. List installed provider metadata
with `uv run hidden-moves plugins list`; this does not activate providers. Load
only the provider needed for the task:

```sh
hidden-moves --plugin PROVIDER moves list --json
hidden-moves --plugin PROVIDER moves show QUALIFIED_NAME
```

Inspect `available`, `input_schema`, `output_schema`, `schema_errors`, binding
requirements, and behavioral annotations before choosing an operation.
`available` describes target binding, not credentials or service health. An
unbound definition is inspectable but cannot enter a selected catalog.
Provider loading executes trusted Python; providers are not sandboxed.

## Bind and select

Keep configuration in an ordinary client or target, outside move metadata and
tool arguments. Use an explicit provider entry point and explicit capability
names; neither installation nor registration authorizes exposing everything.

```python
from hidden_moves import Moves, discover_providers, load_provider
from hidden_moves.adapters import CapabilityCatalog

# target is an explicitly configured ordinary Python object.
entry, = [p for p in discover_providers() if p.name == provider_name]
moves = Moves(target)
load_provider(entry, moves.registry)
catalog = CapabilityCatalog(moves, selected_names)
value = catalog.invoke(selected_names[0], arguments)
payload = catalog.serialize_result(selected_names[0], value)
```

Await awaitable results before serialization. A catalog snapshots definitions
and callables, while the bound object's mutable state remains live. Create a new
catalog after changing registrations.

## Choose the consumer

- Use direct Python for local composition and typed results.
- Use the generic JSON CLI for unbound ordinary functions. Target-bound clients
  need their configured domain host; the generic CLI does not infer a target.
- Use `hidden_moves_mcp.MCPAdapter(catalog)` for MCP tools, then the existing
  `serve_stdio(adapter.server())` inside an application-owned event loop.
- Use `hidden_moves_openai.FunctionToolAdapter(catalog)` to export function tools
  and dispatch calls offline. Exporting tools does not make a model API call.

For agent context over local files, the implementation track is a workspace
provider with an exact file selection, bounded numbered excerpts, digests, and
literal search. See the [implementation plan](../../IMPLEMENTATION_PLAN.md).
Prefer a narrow excerpt or search result over loading an entire workspace.

## Add a useful plugin

Implement and test the ordinary function or client first. Keep its module usable
without importing Hidden Moves. Put optional registration in an integration
module: a zero-argument `provide_moves()` returns `MoveSpec` definitions, and the
package advertises it in the `hidden_moves.moves` entry-point group.

Use `bind_target=True` with explicit `target_types` for configured clients; omit
the injected receiver from public tool arguments. Prefer supported dataclasses
or TypedDicts for structured results. Supply accurate behavior hints; they do
not enforce authorization. Keep imports and provider construction free of
content reads, credential resolution, network requests, and writes.

Verify the useful operation through direct Python and a selected catalog, then
through actual stdio MCP and offline function-tool dispatch when those surfaces
are part of the task. Check invalid inputs and rejection of unselected names.
Keep fixture output finite and JSON-compatible; preserve completeness and
continuation information when returning bounded results.

Read the [plugin contract](../../docs/PLUGIN_API.md) for provider and binding
details, [catalog guide](../../docs/CAPABILITY_CATALOG.md) for supported schemas
and validation, and [usage guide](../../docs/USAGE.md) for existing adapters.
A Python entry-point provider and local MCP host are separate from a hosted
marketplace plugin. Hosted authorization and packaging follow their own tasks.
