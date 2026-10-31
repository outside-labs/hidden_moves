"""Bounded workspace context, usable without Hidden Moves or its adapters."""

from .client import Workspace
from .errors import ContentError, PathAccessError, StaleContentError, WorkspaceError
from .models import Excerpt, FilePage, SearchMatch, SearchPage, TextLine

__all__ = [
    "ContentError", "Excerpt", "FilePage", "PathAccessError", "SearchMatch",
    "SearchPage", "StaleContentError", "TextLine", "Workspace", "WorkspaceError",
]
