# Hidden Moves MCP adapter

An optional adapter around explicitly selected capability catalogs. The MCP SDK
dependency belongs to this distribution; the core registry remains independent.

## Local installation

From the repository root:

```sh
uv venv /tmp/hidden-moves-mcp-env
uv pip install --python /tmp/hidden-moves-mcp-env/bin/python \
  . ./examples/text-plugin ./packages/hidden-moves-mcp
/tmp/hidden-moves-mcp-env/bin/python -m unittest discover \
  -s packages/hidden-moves-mcp/tests -v
```

The adapter uses the official Python SDK, `mcp>=2.3.0,<3`. The local proof was
verified with SDK 2.3.0 and protocol `2026-07-28`; legacy clients can negotiate
the SDK's supported `2025-11-25` handshake. See the official
[protocol-version documentation](https://py.sdk.modelcontextprotocol.io/protocol-versions/).

## Configure a local stdio host

A host starts the installed executable and owns the subprocess:

```json
{
  "command": "/tmp/hidden-moves-mcp-env/bin/hidden-moves-mcp",
  "args": [
    "--plugin", "example-text",
    "--move", "example.text.repeat"
  ]
}
```

The `--move` option is required and repeatable. Only those names are listed and
callable. Providers must be explicitly enabled with `--plugin`; installing one
does not activate it. The executable begins with an empty registry and supplies
no target binding. Configure a Python host for target-bound providers. It waits for protocol input on
stdin and exits when its host closes the connection. Output on stdout is the
protocol stream; application logging belongs on stderr.

This is an executable local proof, without a public service or configured account.
The temporary environment is suitable for testing; install into a durable location
before configuring a host for regular use.

## Python setup and binding

```python
import asyncio

from hidden_moves import Moves
from hidden_moves.adapters import CapabilityCatalog
from hidden_moves_example_text import repeat_text
from hidden_moves_mcp import MCPAdapter, serve_stdio

moves = Moves()
moves.learn(repeat_text, name="repeat", namespace="example.text")
catalog = CapabilityCatalog(moves, ["example.text.repeat"])
server = MCPAdapter(catalog).server()

if __name__ == "__main__":
    asyncio.run(serve_stdio(server))
```

Applications can configure clients or targets before building the catalog. The
adapter consumes those bound callables and does not infer credentials or context.
Synchronous functions execute in the request handler; awaitable results are awaited
there. Client resource setup and shutdown belong to the application.

## Export contract

MCP names retain qualified capability names when they satisfy the protocol's ASCII
name rules. Explicit `tool_names={qualified_name: alias}` mappings handle other
names; invalid or colliding aliases fail before server creation. Exported schemas
are independent copies of neutral definitions.

All successful results use `structuredContent: {"result": value}` with the matching
object output schema and an equivalent JSON text block. This includes object,
scalar, list, and null results. The catalog validates and serializes the underlying
value before wrapping it. Ordinary Python results remain unchanged outside this
adapter.

Behavioral hints map explicitly to MCP annotations, with unknown hints omitted.
They do not authorize calls. The host/application chooses exposure and approval
policy. Invalid arguments and invalid results are tool errors. Capability failures
are tool errors reporting the exception type, without exposing arbitrary exception
contents. Unknown/unexposed tool names are protocol errors. Cancellation propagates.

The [low-level SDK server](https://py.sdk.modelcontextprotocol.io/advanced/low-level-server/)
handles protocol discovery, legacy negotiation, wire types, and connection lifetime;
the adapter owns its list/call handlers and uses the catalog for validation.
