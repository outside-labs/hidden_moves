# Function-tool adapter

This separate distribution exports a selected `CapabilityCatalog` as OpenAI
Responses function tools and dispatches returned calls through that catalog.
It uses the standard library and the core package; an API SDK is optional in the
application that consumes it.

## Local setup

From the repository root, install both distributions in your chosen environment:

```sh
uv pip install --python .venv/bin/python -e . -e ./examples/text-plugin -e ./packages/hidden-moves-openai
```

Export and dispatch work offline:

```python
import asyncio
import json

from hidden_moves import Moves
from hidden_moves.adapters import CapabilityCatalog
from hidden_moves_example_text import repeat_text
from hidden_moves_openai import FunctionToolAdapter

moves = Moves()
moves.learn(repeat_text, name="repeat", namespace="example.text")
adapter = FunctionToolAdapter(CapabilityCatalog(moves, ["example.text.repeat"]))
print(json.dumps(adapter.tools(), indent=2))

output = asyncio.run(adapter.call_output(
	"local-call-1", "example__text__repeat", '{"value": "Hello World"}',
))
assert json.loads(output["output"]) == "Hello World Hello World"
```

In an existing asynchronous Responses application, pass `adapter.tools()` as
`tools`. For each returned `function_call` item, use
`await adapter.call_output(item.call_id, item.name, item.arguments)` to construct
its result item. The application keeps the response history, sends results to
the API, and decides whether to request another response. The adapter owns no
API client, credentials, model choice, retries, approvals, or event loop.

## Names and schemas

Dots become double underscores: `example.text.repeat` exports as `example__text__repeat`.
Names use 1-64 ASCII letters, digits, underscores, or hyphens. Invalid names and
collisions fail at construction; use `tool_names={"qualified.name": "alias"}`
for an explicit mapping. The original catalog retains its qualified names.

Tool dictionaries use the flat Responses format, with explicit `strict=False`
by default. This preserves omitted Python defaults. Schema dialect declarations,
defaults, and examples are omitted from the exported parameters. Property names
and neutral definitions remain unchanged. Behavioral hints and arbitrary metadata
stay in the catalog rather than becoming unsupported API fields.

`strict=True` accepts a conservative structural subset: each object is closed
and requires every property; arrays have typed items; unions use `anyOf` or a
nullable type pair. Scalar enums gain an inferred type when possible. Optional
properties, open mappings, untyped values, and mixed untyped enums fail exposure.
The adapter does not replace omitted arguments with `null` or invent required
defaults. Model-specific schema size limits remain the application's concern.

These choices follow the official [function calling guide](https://developers.openai.com/api/docs/guides/function-calling)
and [Structured Outputs requirements](https://developers.openai.com/api/docs/guides/structured-outputs),
checked October 3, 2026. Local tests validate export and dispatch. Live API
acceptance and a model conversation have not been tested.

## Invocation and errors

`call(name, arguments)` accepts a JSON string or mapping and returns JSON text.
`call_output` adds the supplied call ID in a `function_call_output` item.
Only selected aliases can dispatch, and validation happens before invocation.
Async functions and returned awaitables run in the caller's existing loop;
synchronous functions run inline. Results use the catalog's dataclass, enum,
TypedDict, and finite JSON conversions and output validation.

Invalid arguments raise `CapabilityArgumentError`; invalid results raise
`CapabilityResultError`; unselected names raise `UnknownMoveError`. Capability
exceptions and cancellation propagate to the application. The application must
choose its error reporting and invocation policy before returning failures to
a remote service.

Run the adapter tests in an environment with both local packages installed:

```sh
python -m unittest discover -s packages/hidden-moves-openai/tests -v
```
