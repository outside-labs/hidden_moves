# Independent text provider example

This small distribution demonstrates an ordinary Python library with an optional
Hidden Moves integration. Its helper module has no runtime dependencies and never
imports the registry. Only `integration.py` imports Hidden Moves.

From the repository root, install the host and this example locally:

```sh
uv sync --locked
uv pip install ./examples/text-plugin
.venv/bin/hidden-moves plugins list
.venv/bin/hidden-moves --plugin example-text moves show example.text.repeat
.venv/bin/hm --plugin example-text moves call example.text.repeat \
  --arguments '{"value": "hello", "count": 3}'
.venv/bin/python -m unittest discover -s examples/text-plugin/tests -v
```

Ordinary use is independent:

```python
from hidden_moves_example_text import repeat_text

assert repeat_text("hello", 2, separator="/") == "hello/hello"
```

The provider advertises the `hidden_moves.moves` entry point `example-text`.
Installed metadata is visible without importing the integration. Explicit loading
returns one `MoveSpec` for `example.text.repeat`, with typed schemas, provenance,
behavioral hints, and example metadata. Loading a conflicting definition fails
without changing existing registrations. This example is a local integration
proof and has not been published as a package.

## Target binding

The ordinary `prefix_text(prefix, value)` helper also has an explicit target-bound
provider definition, `example.text.prefix`. A host binds a configured string:

```python
from hidden_moves import Moves, discover_providers, load_provider
from hidden_moves.adapters import CapabilityCatalog

moves = Moves("demo: ")
entry, = [entry for entry in discover_providers() if entry.name == "example-text"]
load_provider(entry, moves.registry)
catalog = CapabilityCatalog(moves, ["example.text.prefix"])
assert catalog.invoke("example.text.prefix", {"value": "hello"}) == "demo: hello"
```

Generic CLI inspection can describe the unbound operation. The executable does
not infer a target; a configured application host owns binding and exposure.
