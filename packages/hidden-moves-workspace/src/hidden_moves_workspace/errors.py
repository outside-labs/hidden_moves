"""Errors omit host paths and file content."""


class WorkspaceError(Exception):
    """A configured workspace operation failed."""


class PathAccessError(WorkspaceError):
    """A path is invalid, unselected, unavailable, or not a regular file."""


class ContentError(WorkspaceError):
    """Selected content exceeds its budget or is not supported UTF-8 text."""


class StaleContentError(WorkspaceError):
    """The content no longer matches an explicitly expected digest."""
