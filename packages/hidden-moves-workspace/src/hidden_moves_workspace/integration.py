"""Optional definitions around an application-configured workspace."""

from hidden_moves import MoveAnnotations, MoveSpec

from .client import Workspace
from .models import Excerpt, FilePage, SearchPage

READ_CAPABILITIES = ("workspace.files", "workspace.read", "workspace.search")


def list_files(workspace: Workspace, offset: int = 0, limit: int = 100) -> FilePage:
    """List one page of declared relative paths without scanning directories or reading content."""
    return workspace.files(offset, limit)


def read_file(
    workspace: Workspace, path: str, start_line: int = 1, line_count: int = 80,
    start_column: int = 1, expected_sha256: str | None = None,
) -> Excerpt:
    """Read a selected UTF-8 file with numbered fragments and a digest.

    At most 200 lines and 16,384 text characters; continue with next_line,
    next_column, and expected_sha256. Columns count Unicode characters from one.
    """
    return workspace.read(path, start_line, line_count, start_column, expected_sha256)


def search_file(
    workspace: Workspace, path: str, query: str, start_line: int = 1,
    max_matches: int = 20, expected_sha256: str | None = None,
) -> SearchPage:
    """Find case-sensitive literal text in one selected UTF-8 file.

    Return the first occurrence per matching line, at most 100 matches, with
    320-character previews. Continue with next_line and expected_sha256.
    """
    return workspace.search(path, query, start_line, max_matches, expected_sha256)


def provide_moves() -> tuple[MoveSpec, ...]:
    """Advertise definitions without constructing a workspace or opening files."""
    annotations = MoveAnnotations(read_only=True, destructive=False, idempotent=True, external=True)
    return tuple(
        MoveSpec(
            name=name, namespace="workspace", func=operation,
            bind_target=True, target_types=(Workspace,), annotations=annotations,
        )
        for name, operation in (("files", list_files), ("read", read_file), ("search", search_file))
    )
