# Selected capability catalogs

The registry describes Python capabilities. `hidden_moves.adapters.CapabilityCatalog`
is a consumer layer for exposing an explicit subset through structured interfaces.
It uses only the standard library and adds no transport, authorization, logging,
credential, or event-loop policy to the core.

```python
from hidden_moves import Moves
from hidden_moves.adapters import CapabilityCatalog
from hidden_moves_example_text import repeat_text

moves = Moves()
moves.learn(repeat_text, name="repeat", namespace="example.text")
catalog = CapabilityCatalog(moves, ["example.text.repeat"])

definition = catalog.describe("example.text.repeat")
result = catalog.invoke("example.text.repeat", {"value": "Hello World"})
assert catalog.serialize_result("example.text.repeat", result) == "Hello World Hello World"
```

Selection limits both discovery and invocation. There is no default selection;
an empty selection exposes nothing. Definitions are sorted and duplicate names
are deduplicated. Construction snapshots each definition and its bound callable,
so replacing a registry entry cannot change the operation behind an older catalog.
Create a new catalog to expose new registrations. Mutable targets and client
state retain their normal Python behavior.

Catalog construction rejects missing bindings, absent input schemas, unavailable
signatures, positional-only or `*args` parameters, and unsupported schema keywords.
An explicit schema may describe `**kwargs`; ordinary Python argument binding is
still checked. Direct registry usage remains available for rejected capabilities.

## Validation and conversion

The supported schema keywords are `$schema`, `title`, `description`, `default`,
`examples`, `type`, `enum`, `anyOf`, `properties`, `required`, `additionalProperties`,
and `items`. Unknown keywords are rejected when constructing a catalog. This is
a documented subset, not a general JSON Schema validator. Schemas with `$ref`,
model definitions, formats, or additional constraints need another consumer.
Inline schemas for non-recursive dataclasses and TypedDict models use the same
supported object keywords.

Arguments must be finite JSON-compatible objects. Required properties, nested
containers, allowed values, extra properties, and JSON types are checked before
execution. Booleans cannot satisfy integer/number inputs. Integral JSON numbers
such as `2.0` satisfy integer schemas and are restored to `int` for annotated
integer parameters. Enum values are restored to enum members, including inside
supported containers and unions. Other values retain their JSON forms. String
numbers are not converted. Omitted arguments use Python defaults; schema defaults
remain descriptive and are not injected.

Annotated dataclass inputs are constructed from their validated fields, using their
ordinary constructors and defaults. Nested dataclasses, supported containers, and
unions are restored recursively. TypedDict inputs remain dictionaries, with nested
annotated model values restored. Dataclass results serialize to their declared
fields; computed `init=False` fields appear in output and cannot be supplied as
automatically inferred inputs. Pydantic and recursive model adapters are deferred.

`invoke()` returns the ordinary Python result. Awaitable results pass through;
the consuming CLI or transport must await them before calling `serialize_result()`.
Serialization copies finite JSON data, uses enum values, and checks the declared
output schema when present. It never falls back to an arbitrary object's string
representation. Direct Python callers can keep the original result instead.

## Errors and policy

Selection and lookup failures use `UnknownMoveError`. Exposure failures use
`CapabilityExposureError`, invalid inputs use `CapabilityArgumentError`, and
structured result failures use `CapabilityResultError`. Exceptions raised by the
capability itself propagate unchanged, including cancellation. Consumers translate
these failures into their own protocol or terminal representation.

Behavioral annotations are descriptive hints. The application chooses which names
may be exposed and whether a call needs authorization. The catalog does not infer
permissions from `read_only` or silently expose installed providers.

## CLI consumer

`hidden-moves moves list --json` emits complete definitions without calling them.
`hidden-moves moves show NAME` describes one definition. Explicit JSON invocation
uses `hidden-moves moves call NAME --arguments '{"value": "Hello World"}'`.
The CLI selects that one name, checks input before execution, awaits results in
its own event loop when necessary, and prints validated JSON. The registry is
empty until an application or explicitly selected provider registers operations.
External providers must still be explicitly enabled with `--plugin NAME`.
