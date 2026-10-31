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

The client never writes files, invokes commands, or accesses a network. Optional
provider and transport integration are developed separately from this client.

```sh
PYTHONPATH=packages/hidden-moves-workspace/src python -S -m unittest discover \
  -s packages/hidden-moves-workspace/tests -v
```
