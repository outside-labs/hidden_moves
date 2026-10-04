"""Public error categories; upstream messages and credentials are never copied."""


class ProjectsError(Exception):
	"""A sanitized failure reading GitHub Projects."""


class CredentialError(ProjectsError):
	"""Explicit credentials could not be resolved."""


class TransportError(ProjectsError):
	"""The configured HTTP transport failed."""


class HTTPStatusError(ProjectsError):
	def __init__(self, status: int) -> None:
		self.status = status
		super().__init__(f"GitHub returned HTTP status {status}.")


class GraphQLError(ProjectsError):
	def __init__(self, codes: tuple[str, ...], *, partial_data: bool) -> None:
		self.codes = codes
		self.partial_data = partial_data
		super().__init__("GitHub rejected the GraphQL read (" + ", ".join(codes) + ").")


class ProtocolError(ProjectsError):
	"""An invalid or oversized response cannot be normalized."""


class NotFoundError(ProjectsError):
	"""The requested resource is absent or not visible to this credential."""


class PaginationLimitError(ProjectsError):
	"""An explicit iterator budget ended before the connection did."""
