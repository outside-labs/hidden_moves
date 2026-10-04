# Usage and readiness

Hidden Moves registers ordinary Python capabilities, describes their effective
signatures and schemas, binds them to configured objects, and makes an explicit
selection available to consumers. The ordinary function or client remains the
source of behavior. The registry adds no workflow engine or application lifecycle.

## Packages and compatibility

| Distribution | Python import | Runtime dependencies | Purpose |
| --- | --- | --- | --- |
| `hidden-moves` | `hidden_moves` | Click for the CLI | Registry, binding, descriptions, schemas, selected catalog, and CLI |
| `hidden-moves-example-text` | `hidden_moves_example_text` | None for ordinary use | Independently usable example with an optional entry-point integration |
| `hidden-moves-mcp` | `hidden_moves_mcp` | Core package and `mcp>=2.3.0,<3` | Selected tools through the official MCP SDK |
| `hidden-moves-openai` | `hidden_moves_openai` | Core package | Responses function definitions and offline dispatch |

All distributions require Python 3.11 or newer. Registry, schema, and catalog
modules use the standard library. The optional distributions live in `packages/`
and are installed separately. Installing the core does not install an MCP or API
SDK. The ordinary example function can run without the core package.

The API and provider contract are experimental at version 0.1.0. Pull-request CI
builds and installs actual wheels and verifies behavior on Python 3.11 and 3.13
across Linux, macOS, and Windows. See the [compatibility policy](COMPATIBILITY.md).
The MCP tests exercise SDK 2.3.0's modern `2026-07-28` protocol and legacy
`2025-11-25` handshake, including a real local stdio subprocess. Function-tool
export and dispatch are tested offline; live model API acceptance is unverified.
No package has been published as part of this implementation.

## Run the complete local demonstration

From the repository root, create an isolated environment and install the local
distributions. These commands install declared dependencies but make no model
API calls:

```sh
uv venv /tmp/hidden-moves-demo-env
uv pip install --python /tmp/hidden-moves-demo-env/bin/python \
  . ./examples/text-plugin ./packages/hidden-moves-mcp ./packages/hidden-moves-openai
/tmp/hidden-moves-demo-env/bin/python examples/interop_demo.py
/tmp/hidden-moves-demo-env/bin/python -m unittest discover -s examples/tests -v
```

The [executable demonstration](../examples/interop_demo.py) calls the same example
function through ordinary Python, registry resolution, the installed CLI, a real
in-process MCP client, and function-tool dispatch. Every result is
`hello/hello/hello`. Its JSON output includes the neutral definition, both tool
exports, and a function-call result item. The provider is loaded once into the
in-process registry, and both adapters consume that same selected catalog.
The separate CLI process explicitly loads its own instance of the same provider.

## Ordinary Python and inspection

The example's ordinary interface has no registration requirement:

```python
from hidden_moves_example_text import repeat_text

assert repeat_text("hello", 3, separator="/") == "hello/hello/hello"
```

Metadata discovery identifies installed integrations without importing them.
Loading the chosen provider registers its definitions explicitly:

```python
from hidden_moves import Moves, discover_providers, load_provider
from hidden_moves.adapters import CapabilityCatalog

entries = [entry for entry in discover_providers() if entry.name == "example-text"]
if len(entries) != 1:
	raise RuntimeError("Install exactly one example-text provider.")

moves = Moves()
load_provider(entries[0], moves.registry)
definition = moves.describe("example.text.repeat")
assert definition.available
assert definition.input_schema["required"] == ("value",)
assert moves.example.text.repeat("hello", 3, separator="/") == "hello/hello/hello"

catalog = CapabilityCatalog(moves, ["example.text.repeat"])
```

The definition includes the source, documentation, effective signature, binding
availability, async status, behavioral hints, immutable JSON metadata, schemas,
and schema diagnostics. `definition.to_dict()` gives a fresh serializable view.
Target and context values are not included. Inspection does not call the function.
Annotation resolution assumes trusted Python provider code.

For an application-owned function, use `moves.learn(function, namespace="domain")`.
An existing bound client method needs no target injection. `bind_target=True`
instead supplies the container's target as the first argument. Configure clients,
credentials, and resources before selecting them for exposure; the registry does
not infer that configuration.

## Installed CLI

Use the environment created above:

```sh
/tmp/hidden-moves-demo-env/bin/hidden-moves plugins list
/tmp/hidden-moves-demo-env/bin/hidden-moves --plugin example-text moves show example.text.repeat
/tmp/hidden-moves-demo-env/bin/hidden-moves --plugin example-text moves list --json
/tmp/hidden-moves-demo-env/bin/hm --plugin example-text moves call example.text.repeat \
  --arguments '{"value": "hello", "count": 3, "separator": "/"}'
```

The `hm` executable aliases `hidden-moves`. Installing a provider does not activate
it; `--plugin` chooses it for that invocation. Generic calls select one capability,
validate the JSON object, await results when necessary, and print JSON. Invalid
structured input is rejected before the function runs. Both CLIs begin with an
empty registry; domain operations require explicit provider activation. Target-bound
operations require an application host that configures the target before selection.

## MCP consumer

Use the catalog above with a local SDK client:

```python
from mcp import Client
from hidden_moves_mcp import MCPAdapter

adapter = MCPAdapter(catalog)

async def check_mcp():
	async with Client(adapter.server()) as client:
		tools = await client.list_tools()
		assert [tool.name for tool in tools.tools] == ["example.text.repeat"]
		result = await client.call_tool("example.text.repeat", {
			"value": "hello", "count": 3, "separator": "/",
		})
		assert result.structured_content == {"result": "hello/hello/hello"}
```

The adapter preserves supported qualified names, maps known behavioral hints,
and wraps successful values in `{"result": value}` with a matching output schema.
Only selected tools list or dispatch. Async results are awaited by the consumer.
The [MCP adapter guide](../packages/hidden-moves-mcp/README.md) covers error channels,
aliases, configured clients, and a stdio command suitable for a local host.

## Responses function consumer

The same catalog exports a different format without changing the definition:

```python
import json
from hidden_moves_openai import FunctionToolAdapter

adapter = FunctionToolAdapter(catalog)
tools = adapter.tools()
assert tools[0]["name"] == "example__text__repeat"
assert tools[0]["strict"] is False

async def check_function():
	output = await adapter.call_output("local-call-1", tools[0]["name"], {
		"value": "hello", "count": 3, "separator": "/",
	})
	assert json.loads(output["output"]) == "hello/hello/hello"
```

The application owns API requests, response history, and the model loop. The
adapter exports flat Responses definitions and returns `function_call_output`
items, using the same local argument and result validation as MCP. Explicit
`strict=False` preserves Python defaults; strict mode accepts compatible schemas
without turning omitted defaults into nullable required parameters. See the
[function-tool guide](../packages/hidden-moves-openai/README.md) for naming,
schema adjustments, supported strict structure, and propagated errors.

## Boundaries and next integration step

Supported structured types include primitives, nullable unions, lists, string-keyed
mappings, literals, enums, non-recursive dataclasses, and TypedDict models.
Unsupported signatures can remain ordinary Python capabilities with explicit
schema diagnostics. The selected catalog validates a documented schema subset;
recursive models, `$ref`, formats, arbitrary constraints, and Pydantic require
another integration. See the [plugin contract](PLUGIN_API.md) and
[catalog contract](CAPABILITY_CATALOG.md).

Behavioral annotations are hints, and unknown behavior remains unknown. The
application owns exposure, call approval, authentication, error disclosure,
concurrency, timeouts, retries, and resource cleanup. Synchronous functions execute
inline in these adapters. Ordinary result types remain available to direct Python
callers; structured consumers require supported finite JSON results.

The local implementation is ready for a chosen consumer. A durable MCP setup
requires selecting the host and capabilities, installing the adapter in a stable
environment, and adding the host's subprocess configuration. A Responses setup
requires an application-owned API client, model selection, credentials outside
source control, and a conversation loop. Neither has been configured for an
external account. Package publication, a public server, hosted authentication,
and deployment are separate next steps.
