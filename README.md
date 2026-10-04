# Hidden Moves

Describe, discover, bind, and expose typed Python capabilities. Ordinary functions
and clients own their behavior; Hidden Moves supplies a small registry, schemas,
per-object binding, and explicitly selected consumer interfaces.

The API and provider contract are experimental. See the [plugin contract](docs/PLUGIN_API.md),
[catalog guide](docs/CAPABILITY_CATALOG.md), and [usage guide](docs/USAGE.md).

## Installation and CLI

Python 3.11 or newer is required. Click is the core distribution's only runtime
dependency. Registry, schema, and catalog modules use the standard library.

```sh
uv sync
uv run hidden-moves --help
uv run hidden-moves plugins list
uv run hidden-moves moves list --json
```

The registry starts empty. Installing a provider advertises it; loading it is an
explicit choice. Install the source-only text example to try the generic CLI:

```sh
uv pip install --python .venv/bin/python ./examples/text-plugin
uv run hidden-moves --plugin example-text moves show example.text.repeat
uv run hm --plugin example-text moves call example.text.repeat \
  --arguments '{"value": "hello", "count": 3}'
```

`hm` aliases `hidden-moves`. The shipped command groups are `plugins list` and
`moves list/show/call`. An unconfigured CLI can inspect target-bound definitions;
an application host must bind their target before structured invocation.

## Ordinary functions

Your functions remain directly usable without registration:

```python
from hidden_moves import Moves
from hidden_moves.adapters import CapabilityCatalog

def repeat(value: str, count: int = 2) -> str:
    return " ".join([value] * count)

moves = Moves()
moves.learn(repeat, namespace="text")
assert moves.text.repeat("hello", 3) == repeat("hello", 3)

catalog = CapabilityCatalog(moves, ["text.repeat"])
assert catalog.invoke("text.repeat", {"value": "hello"}) == "hello hello"
```

The catalog validates structured arguments before execution and serializes
supported finite JSON results. Non-recursive dataclasses and TypedDicts retain
typed Python behavior through supported model conversion.

## Per-object binding

`bind_target=True` supplies the container's target as the first positional argument.
Definitions can be shared while each container retains its own target:

```python
from hidden_moves import Moves, Registry, MoveSpec

def prefix(target: str, value: str) -> str:
    return target + value

registry = Registry()
registry.register(MoveSpec("prefix", prefix, namespace="text", bind_target=True))
first = Moves("first: ", registry=registry)
second = Moves("second: ", registry=registry)
assert first.text.prefix("hello") == "first: hello"
assert second.text.prefix("hello") == "second: hello"
```

Existing bound client methods can be learned without additional target injection.
Applications configure clients, credentials, timeouts, and resources. Inspection
does not invoke capabilities or include target/context values.

## Consumers and inspection

- `moves.moves()` lists definitions; `knows(name)` checks registration.
- `resolve(name)` supplies the callable; `describe(name)` and `explain(name)` inspect it.
- Async results remain awaitable; consuming applications own their event loop.
- Metadata is copied deeply and kept immutable; behavioral annotations are hints.
- Discovery reads installed entry-point metadata; provider activation is explicit.

The optional [MCP adapter](packages/hidden-moves-mcp/README.md) serves a selected
catalog through a local stdio host. The separate [function-tool adapter](packages/hidden-moves-openai/README.md)
exports Responses function tools and supports offline dispatch. Both use the same
structured contract. Applications own authorization, transport, concurrency, and
resource cleanup.

The [GitHub Projects consumer](docs/GITHUB_PROJECTS.md) provides a standalone typed
read-only client and optional configured provider/host. Its fixture proof returns
equivalent data through Python, catalog, actual stdio MCP, and function tools; a
separate bounded live read verifies existing GitHub authorization.

The [installed text provider](examples/text-plugin/README.md) demonstrates ordinary
imports, explicit activation, and target binding. The [interoperability example](examples/interop_demo.py)
proves equivalent behavior through Python, CLI, MCP, and function tools.

## Verification

```sh
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
uvx ruff check src tests
```

CI builds, inspects, and installs wheels and the example provider, checks both
executables and module execution, and runs the complete behavior suites on Linux,
macOS, and Windows with Python 3.11/3.13. See the [compatibility policy](docs/COMPATIBILITY.md).
MCP tests include an actual stdio handshake/list/call. Network clients use synthetic
fixtures and function-tool checks make no model API call.

## Experimental import changes

The framework no longer ships prototype `kit`, `notes`, `logs`, `palette`, `presets`,
or `connectors` namespaces, automatic built-in assembly, `CommandSet`, or specialized
text/JSON/shell commands. Applications register their ordinary typed functions or
load explicit providers instead. Historical implementations remain recoverable
from Git. See [migration notes](docs/MIGRATIONS.md).
