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
The stdio adapter defaults to invoking synchronous functions in the request
handler and awaiting awaitable results there. `MCPAdapter` also accepts explicit
`offload_sync=True` and a finite `call_timeout` for hosts that need them. Client
resource setup and shutdown belong to the application.

## Local Streamable HTTP

```python
from hidden_moves_mcp import create_http_app, serve_http

async def authorize(request):
    # Check the application's local request grant without consuming the body.
    return await local_access_policy(request.headers)

app = create_http_app(catalog, authorize=authorize)
asyncio.run(serve_http(app, port=8000))
```

The application supplies an async authorizer that returns exactly `True` for each
allowed request. Missing grants, rejected grants and authorizer exceptions return
401 before protocol dispatch. It chooses credentials, request identity and the
selected catalog; no installed provider or account is activated implicitly.

`serve_http` binds only `127.0.0.1`. The
[SDK's ASGI app](https://py.sdk.modelcontextprotocol.io/run/asgi/) handles
Streamable HTTP, initialization, protocol negotiation and lifespan cleanup at
`/mcp`, with its default localhost Host/Origin protection. Responses are JSON and
HTTP is stateless. The same adapter supplies schemas, annotations and
`structuredContent: {"result": value}` over HTTP and stdio. Unselected names remain
protocol errors. Mounting the returned app inside another application requires
the host to run its lifespan, as described in the SDK guide.

Defaults are a 10-second call deadline, 30-second request deadline, 16 concurrent
requests and a 1 MiB request body. Limits must be finite; excess concurrency returns
503, an expired request returns 504, and the SDK rejects oversized bodies with 413.
Timed-out tools return sanitized tool errors. Access logging is disabled by the
local serving helper, and forwarded identity headers are not trusted.

HTTP offloads synchronous capabilities by default so blocking I/O does not stop
other requests. Async capabilities execute on the event loop. Configure the
underlying clients with their own finite I/O timeouts: cancellation cannot stop a
running Python worker thread, and a timed-out write may still complete. Inspect
its outcome before submitting another write. Thread-affine resources need an
application-owned execution strategy; `offload_sync=False` is available for fast
event-loop-safe callables, whose deadlines depend on cooperative yielding. The
host owns resource cleanup and concurrency safety.

`examples/mcp_http.py` serves only `example.text.repeat` using an explicitly
configured `HIDDEN_MOVES_LOCAL_HTTP_TOKEN` of 32–512 printable ASCII characters.
It demonstrates a local request grant; hosted OAuth, delegated GitHub credentials
and per-user catalog isolation require their separate authentication work.

Installed-wheel tests run real loopback initialize/list/call clients in modern
and legacy modes, compare Python/HTTP DTOs, check authorization and request limits,
exercise cancellation and worker offloading, then shut down the SDK lifespan and
listener. The existing real stdio subprocess checks still run in the same suite.

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
