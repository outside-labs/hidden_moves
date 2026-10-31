"""Finite result models shared by ordinary Python and structured consumers."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FilePage:
    paths: list[str]
    next_offset: int | None


@dataclass(frozen=True)
class TextLine:
    number: int
    column: int
    text: str


@dataclass(frozen=True)
class Excerpt:
    path: str
    sha256: str
    total_lines: int
    lines: list[TextLine]
    next_line: int | None
    next_column: int | None


@dataclass(frozen=True)
class SearchMatch:
    line: int
    column: int
    preview_column: int
    preview: str


@dataclass(frozen=True)
class SearchPage:
    path: str
    sha256: str
    total_lines: int
    matches: list[SearchMatch]
    next_line: int | None
