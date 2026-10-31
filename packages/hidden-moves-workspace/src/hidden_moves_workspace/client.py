"""Read-only context over an explicit, bounded file selection."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from collections.abc import Iterable
from pathlib import Path

from .errors import ContentError, PathAccessError, StaleContentError
from .models import Excerpt, FilePage, SearchMatch, SearchPage, TextLine

_EXCERPT_CHARS = 16_384
_PREVIEW_CHARS = 320


def _integer(value: int, minimum: int, maximum: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}.")


def _relative_path(value: str) -> str:
    # One portable spelling prevents traversal and platform-specific aliases.
    if (
        not isinstance(value, str) or not value or len(value) > 1024
        or any(char in value for char in ("\\", ":", "\x00"))
        or any(ord(char) < 32 for char in value)
        or any(part in ("", ".", "..") or part.endswith((" ", ".")) for part in value.split("/"))
    ):
        raise PathAccessError("Use a selected relative path with forward-slash separators.")
    return value


def _is_link(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


class Workspace:
    """Bind trusted configuration; read selected content only when called.

    Symlink checks reduce accidental escapes. This is not a filesystem sandbox
    against concurrent replacement of parent directories or other hostile edits.
    """

    def __init__(
        self, root: str | os.PathLike[str], files: Iterable[str], *, max_file_bytes: int = 262_144,
    ) -> None:
        _integer(max_file_bytes, 1, 1_048_576, "max_file_bytes")
        if isinstance(files, (str, bytes)):
            raise TypeError("files must be an iterable of relative paths.")
        selected: set[str] = set()
        for index, path in enumerate(files):
            if index >= 512:
                raise ValueError("Select at most 512 file paths.")
            selected.add(_relative_path(path))
        try:
            location = Path(root).resolve(strict=True)
            if not location.is_dir():
                raise ValueError
        except (OSError, RuntimeError, TypeError, ValueError):
            raise PathAccessError("The configured workspace root must be an existing directory.") from None
        self._root = location
        self._paths = tuple(sorted(selected))
        self._selected = frozenset(selected)
        self._max_file_bytes = max_file_bytes

    def files(self, offset: int = 0, limit: int = 100) -> FilePage:
        """List declared relative paths, not a live directory scan; no content is read."""
        _integer(offset, 0, len(self._paths), "offset")
        _integer(limit, 1, 200, "limit")
        end = min(offset + limit, len(self._paths))
        return FilePage(list(self._paths[offset:end]), end if end < len(self._paths) else None)

    def _read(self, path: str, expected_sha256: str | None) -> tuple[list[str], str]:
        path = _relative_path(path)
        if path not in self._selected:
            raise PathAccessError("The path is not selected in this workspace.")
        if expected_sha256 is not None and (
            not isinstance(expected_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
        ):
            raise ValueError("expected_sha256 must be a lowercase SHA-256 digest.")
        try:
            current = self._root
            for part in (None, *path.split("/")):
                if part is not None:
                    current = current / part
                info = current.lstat()
                if _is_link(info):
                    raise PathAccessError("Symlinks and reparse points are not supported.")
            current.resolve(strict=True).relative_to(self._root)
            if not stat.S_ISREG(info.st_mode):
                raise PathAccessError("Selected content must be a regular file.")
            flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
            with os.fdopen(os.open(current, flags), "rb") as stream:
                opened = os.fstat(stream.fileno())
                if not stat.S_ISREG(opened.st_mode):
                    raise PathAccessError("Selected content must be a regular file.")
                if opened.st_size > self._max_file_bytes:
                    raise ContentError("Selected content exceeds the configured byte limit.")
                data = stream.read(self._max_file_bytes + 1)
        except (OSError, RuntimeError, ValueError):
            raise PathAccessError("The selected file is unavailable within the configured workspace.") from None
        if len(data) > self._max_file_bytes:
            raise ContentError("Selected content exceeds the configured byte limit.")
        digest = hashlib.sha256(data).hexdigest()
        if expected_sha256 is not None and digest != expected_sha256:
            raise StaleContentError("Content changed; restart the read or search using the current file.")
        try:
            text = data.decode("utf-8")
        except UnicodeError:
            raise ContentError("Selected content must be UTF-8 text.") from None
        if "\x00" in text:
            raise ContentError("NUL-containing content is not supported text.")
        return text.splitlines(), digest

    def read(
        self, path: str, start_line: int = 1, line_count: int = 80,
        start_column: int = 1, expected_sha256: str | None = None,
    ) -> Excerpt:
        """Read numbered lines, bounded to 200 lines and 16,384 text characters.

        Continue with next_line/next_column and expected_sha256. Columns count
        Unicode characters from one, not UTF-8 bytes; newline characters are omitted.
        """
        _integer(start_line, 1, 1_048_577, "start_line")
        _integer(line_count, 1, 200, "line_count")
        _integer(start_column, 1, 1_048_577, "start_column")
        lines, digest = self._read(path, expected_sha256)
        if start_line > len(lines) + 1 or (start_line > len(lines) and start_column != 1):
            raise ValueError("The start position is beyond the end of the file.")
        result = []
        remaining = _EXCERPT_CHARS
        position = start_line - 1
        column = start_column - 1
        while position < len(lines) and len(result) < line_count:
            line = lines[position]
            if column > len(line):
                raise ValueError("start_column is beyond the end of the line.")
            fragment = line[column:column + remaining]
            result.append(TextLine(position + 1, column + 1, fragment))
            remaining -= len(fragment)
            column += len(fragment)
            if column < len(line):
                break
            position += 1
            column = 0
            if remaining == 0:
                break
        has_more = position < len(lines)
        return Excerpt(
            path, digest, len(lines), result,
            position + 1 if has_more else None, column + 1 if has_more else None,
        )

    def search(
        self, path: str, query: str, start_line: int = 1,
        max_matches: int = 20, expected_sha256: str | None = None,
    ) -> SearchPage:
        """Find the first case-sensitive literal occurrence on each matching line.

        Return at most 100 matches with 320-character previews. Continue using
        next_line and expected_sha256; a bounded page is not the whole file.
        """
        if not isinstance(query, str) or not 1 <= len(query) <= 256 or any(char in query for char in "\r\n\x00"):
            raise ValueError("query must contain 1-256 characters without CR, LF, or NUL.")
        _integer(start_line, 1, 1_048_577, "start_line")
        _integer(max_matches, 1, 100, "max_matches")
        lines, digest = self._read(path, expected_sha256)
        if start_line > len(lines) + 1:
            raise ValueError("start_line is beyond the end of the file.")
        matches = []
        next_line = None
        for position in range(start_line - 1, len(lines)):
            column = lines[position].find(query)
            if column == -1:
                continue
            if len(matches) == max_matches:
                next_line = position + 1
                break
            preview_start = max(0, column - 32)
            matches.append(SearchMatch(
                position + 1, column + 1, preview_start + 1,
                lines[position][preview_start:preview_start + _PREVIEW_CHARS],
            ))
        return SearchPage(path, digest, len(lines), matches, next_line)
