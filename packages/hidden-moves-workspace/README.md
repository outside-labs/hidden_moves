# Workspace context

Bounded context over an exact selection of local UTF-8 text files. The ordinary
Python client uses only the standard library and does not import Hidden Moves.
This package is experimental and source-only; no package publication is implied.

```python
from hidden_moves_workspace import Workspace

workspace = Workspace("/path/to/project", ["README.md", "src/example.py"])
paths = workspace.files(limit=20)
page = workspace.search("src/example.py", "def ", max_matches=5)
excerpt = workspace.read("src/example.py", start_line=1, line_count=30)
```

Configuration fixes the canonical root, exact relative-file selection, and
`max_file_bytes` (262,144 by default; at most 1,048,576). At most 512 path entries
are accepted. Paths use forward slashes. No globbing, recursive directory scan,
or implicit hidden-file selection occurs. `files` lists the declared selection,
including files that may currently be missing; it does not inspect content.
Construction resolves the root but does not open selected files.

`read` returns the path, SHA-256 of the raw bytes read, total line count, numbered
text fragments, and `next_line`/`next_column`. Each call returns at most 200 lines
and 16,384 text characters. A long physical line continues at the reported
column. Line and column numbers start at one; columns count Unicode characters.
Python `str.splitlines()` defines lines; line-ending characters are omitted.
An empty file returns no lines. Starting one line beyond EOF returns an empty
completed excerpt; positions beyond that are rejected.

`search` is case-sensitive literal search within one selected file, with one
match per matching line. It returns at most 100 matches, 320-character previews,
and an explicit `next_line` when further matches exist. Follow that position
rather than assuming a page contains all matches. An empty result with no next
position means no matches remain in that file from the requested start.

For either operation, pass the prior `sha256` as `expected_sha256` on continuation
to reject content changes with `StaleContentError`. Digests describe the bytes
actually read, not a transactional snapshot across files or concurrent edits.

Absolute paths, traversal, unselected paths, symlink/reparse components,
non-regular files, invalid UTF-8, NUL content, oversized files, and invalid bounds
are rejected. Exceptions do not echo absolute host paths or file content.
Explicit selection is trusted configuration: it can intentionally include
sensitive files, so configure it only with content appropriate for the consumer.
These checks reduce accidental escapes; this local library is not an OS sandbox
against hostile concurrent filesystem replacement, hard links, or mount changes.

The client never writes files, invokes commands, or accesses a network. Importing
`hidden_moves_workspace` does not import Hidden Moves or a protocol adapter.

## Install and inspect the provider

From the repository checkout, install the local packages into your environment:

```sh
uv pip install . ./packages/hidden-moves-mcp ./packages/hidden-moves-openai \
  './packages/hidden-moves-workspace[host]'
hidden-moves plugins list
hidden-moves --plugin workspace moves show workspace.read
```

The ordinary package has no mandatory dependencies. The `[moves]` extra enables
the provider and configured JSON CLI; `[host]` also enables local MCP. The
function-tool adapter is installed separately. Discovery and unbound inspection
do not open selected files, and the generic CLI cannot infer a workspace target.

The installed `workspace` provider advertises `workspace.files`, `workspace.read`,
and `workspace.search`. They are target-bound wrappers, annotated read-only,
non-destructive, and idempotent. Their external-system hint reflects the mutable
local filesystem, not network access. Hints do not authorize exposure.

## Configured CLI and local MCP

Run a useful read-only context workflow from a checkout:

```sh
hidden-moves-workspace --root . --file README.md --file src/hidden_moves/core/moves.py \
  --move workspace.files call workspace.files
hidden-moves-workspace --root . --file src/hidden_moves/core/moves.py \
  --move workspace.search call workspace.search \
  --arguments '{"path":"src/hidden_moves/core/moves.py","query":"def learn","max_matches":3}'
hidden-moves-workspace --root . --file src/hidden_moves/core/moves.py \
  --move workspace.read call workspace.read \
  --arguments '{"path":"src/hidden_moves/core/moves.py","start_line":1,"line_count":12}'
```

`--root`, repeated `--file`, and repeated `--move` are required; no root, file,
or capability is selected by default. `--max-file-bytes` can lower the content
ceiling. Only selected moves can dispatch. The CLI prints validated finite JSON;
input and domain errors exit with status 2 and omit host paths/content.

For a local MCP client, launch the same executable with `serve`:

```sh
hidden-moves-workspace --root /absolute/project --file README.md \
  --move workspace.files --move workspace.read --move workspace.search serve
```

Use these tokens as the client's executable/argument array. Configuration belongs
to the local host, outside tool arguments. The server serves the selected catalog
over stdio and offloads synchronous reads from its event loop. Startup emits no
application output to stdout. MCP failures identify the exception type without
leaking file content; `StaleContentError` means restart from current content.

This is a Python entry-point plugin and local MCP host. It does not create a
hosted marketplace package, remote identity service, or public endpoint.

## Python composition and offline function tools

```python
import asyncio
import json

from hidden_moves_openai import FunctionToolAdapter
from hidden_moves_workspace import Workspace
from hidden_moves_workspace.host import build_catalog

workspace = Workspace("/path/to/project", ["README.md"])
catalog = build_catalog(workspace, ["workspace.read"])
arguments = {"path": "README.md", "line_count": 12}
value = catalog.serialize_result("workspace.read", catalog.invoke("workspace.read", arguments))
functions = FunctionToolAdapter(catalog)
assert json.loads(asyncio.run(functions.call("workspace__read", arguments))) == value
```

`functions.tools()` exports tool definitions. Offline dispatch makes no model API
call. Defaults retain ordinary Python omission semantics; the adapter's default
`strict=False` preserves these optional arguments. For MCP in an application,
pass the same catalog to `MCPAdapter` from `hidden_moves_mcp`.

## Verification

```sh
PYTHONPATH=packages/hidden-moves-workspace/src python -S -m unittest discover \
  -s packages/hidden-moves-workspace/tests -v
python -m unittest discover -s packages/hidden-moves-workspace/integration_tests -v
```

Integration tests use synthetic temporary files and compare Python, catalog,
MCP, and function-tool results. Actual stdio tests start the installed module,
initialize a client, list/call tools, continue pages, and reject unselected moves.
