"""An ordinary read-only Projects client, independent of capability adapters."""

import json
import math
from collections.abc import Callable, Iterator
from urllib.parse import urlsplit
from urllib.request import Request

from . import _normalize as normalize
from . import _queries
from .errors import (
	CredentialError,
	GraphQLError,
	HTTPStatusError,
	NotFoundError,
	PaginationLimitError,
	ProtocolError,
	TransportError,
)
from .models import (
	Diagnostic,
	FieldPage,
	FieldValuePage,
	ItemPage,
	OwnerKind,
	Project,
	ProjectPage,
)
from .transport import HTTPResponse, Transport, http_transport

_ERROR_CODES = {
	"FORBIDDEN", "NOT_FOUND", "RATE_LIMITED", "UNAUTHORIZED", "UNPROCESSABLE",
	"MAX_NODE_LIMIT_EXCEEDED", "GRAPHQL_VALIDATION_FAILED", "INSUFFICIENT_SCOPES",
}


def _text(value: str, label: str) -> str:
	if not isinstance(value, str) or not value.strip():
		raise ValueError(f"{label} must be a nonempty string.")
	return value


def _count(value: int, label: str, maximum: int = 100) -> int:
	if type(value) is not int or not 1 <= value <= maximum:
		raise ValueError(f"{label} must be an integer between 1 and {maximum}.")
	return value


def _cursor(value: str | None) -> str | None:
	return None if value is None else _text(value, "cursor")


class ProjectsClient:
	"""Resolve explicit credentials and perform one bounded GraphQL read per call."""

	def __init__(
		self, token: str | Callable[[], str], *, transport: Transport = http_transport,
		timeout: float = 10.0, max_response_bytes: int = 4_000_000,
		endpoint: str = "https://api.github.com/graphql",
	) -> None:
		if type(timeout) not in (float, int) or not math.isfinite(timeout) or timeout <= 0:
			raise ValueError("timeout must be a finite positive number.")
		_count(max_response_bytes, "max_response_bytes", 16_000_000)
		parsed = urlsplit(endpoint)
		if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
			raise ValueError("endpoint must be an HTTPS URL without credentials, query, or fragment.")
		if not callable(token) and not isinstance(token, str):
			raise TypeError("token must be a string or an explicit resolver.")
		if not callable(transport):
			raise TypeError("transport must be callable.")
		self._token = token
		self._transport = transport
		self._timeout = float(timeout)
		self._max_response_bytes = max_response_bytes
		self._endpoint = endpoint

	def __repr__(self) -> str:
		return "ProjectsClient()"

	def _read(self, query: str, variables: dict) -> dict:
		try:
			token = self._token() if callable(self._token) else self._token
		except Exception:  # noqa: BLE001 - Resolver failures may contain credentials.
			raise CredentialError("The configured credential resolver failed.") from None
		if not isinstance(token, str) or not token.strip() or any(char.isspace() for char in token):
			raise CredentialError("The configured credential is empty or invalid.")
		request = Request(
			self._endpoint, data=json.dumps({"query": query, "variables": variables}, allow_nan=False).encode(),
			headers={"Authorization": "Bearer " + token, "Accept": "application/json", "Content-Type": "application/json", "User-Agent": "hidden-moves-github-projects/0.1.0"},
			method="POST",
		)
		try:
			response = self._transport(request, timeout=self._timeout, max_bytes=self._max_response_bytes)
		except Exception:  # noqa: BLE001 - Transport failures may echo request credentials.
			raise TransportError("The configured GitHub transport failed.") from None
		if not isinstance(response, HTTPResponse) or type(response.status) is not int or not 100 <= response.status <= 599 or not isinstance(response.body, bytes):
			raise ProtocolError("The transport returned an invalid response.")
		if response.status != 200:
			raise HTTPStatusError(response.status)
		if len(response.body) > self._max_response_bytes:
			raise ProtocolError("The GitHub response exceeded the configured byte budget.")
		try:
			def reject_constant(value):
				raise ValueError("non-finite JSON")
			result = json.loads(response.body, parse_constant=reject_constant)
		except (ValueError, UnicodeError, RecursionError):
			raise ProtocolError("GitHub returned invalid JSON.") from None
		result = normalize.obj(result)
		errors = result.get("errors")
		if errors is not None and not isinstance(errors, list):
			raise ProtocolError("GitHub returned an invalid GraphQL error response.")
		if errors:
			codes = []
			for error in errors:
				code = error.get("type") if isinstance(error, dict) else None
				codes.append(code if isinstance(code, str) and code in _ERROR_CODES else "GRAPHQL_ERROR")
			raise GraphQLError(tuple(codes), partial_data=result.get("data") is not None)
		return normalize.obj(result.get("data"))

	def list(self, owner: str, owner_kind: OwnerKind, *, cursor: str | None = None, page_size: int = 50) -> ProjectPage:
		"""Read one page of a user's or organization's Projects, retaining its cursor."""
		if owner_kind not in ("user", "organization"):
			raise ValueError("owner_kind must be user or organization.")
		data = self._read(_queries.owner_query(owner_kind, listing=True), {
			"owner": _text(owner, "owner"), "first": _count(page_size, "page_size"), "cursor": _cursor(cursor),
		})
		if data.get("owner") is None:
			raise NotFoundError("The requested owner is absent or inaccessible.")
		nodes, page = normalize.connection(normalize.obj(data["owner"]).get("projectsV2"))
		diagnostics = [Diagnostic("unavailable_project") for entry in nodes if entry is None]
		return ProjectPage([normalize.project(entry) for entry in nodes if entry is not None], page, diagnostics)

	def get(self, owner: str, owner_kind: OwnerKind, number: int) -> Project:
		"""Read a Project by its owner kind, login, and Project number."""
		if owner_kind not in ("user", "organization"):
			raise ValueError("owner_kind must be user or organization.")
		data = self._read(_queries.owner_query(owner_kind, listing=False), {
			"owner": _text(owner, "owner"), "number": _count(number, "number", 2_147_483_647),
		})
		owner_data = data.get("owner")
		if owner_data is None or normalize.obj(owner_data).get("projectV2") is None:
			raise NotFoundError("The requested Project is absent or inaccessible.")
		return normalize.project(owner_data["projectV2"])

	def fields(self, project_id: str, *, cursor: str | None = None, page_size: int = 50) -> FieldPage:
		"""Read one field-definition page, including select options and iteration metadata."""
		data = self._read(_queries.FIELD_QUERY, {"id": _text(project_id, "project_id"), "first": _count(page_size, "page_size"), "cursor": _cursor(cursor)})
		nodes, page = normalize.connection(normalize.node(data, "ProjectV2").get("fields"))
		fields, diagnostics = [], []
		for value in nodes:
			field, hints = normalize.project_field(value)
			fields.append(field)
			diagnostics.extend(hints)
		return FieldPage(project_id, fields, page, diagnostics)

	def items(self, project_id: str, *, cursor: str | None = None, page_size: int = 50, field_page_size: int = 50) -> ItemPage:
		"""Read a bounded item page; incomplete nested values retain their own cursors."""
		data = self._read(_queries.ITEM_QUERY, {
			"id": _text(project_id, "project_id"), "first": _count(page_size, "page_size"),
			"cursor": _cursor(cursor), "fieldFirst": _count(field_page_size, "field_page_size"),
		})
		nodes, page = normalize.connection(normalize.node(data, "ProjectV2").get("items"))
		items = [normalize.item(value, project_id) for value in nodes if value is not None]
		diagnostics = [Diagnostic("unavailable_item", project_id) for value in nodes if value is None]
		diagnostics.extend(hint for value in items for hint in value.diagnostics)
		return ItemPage(project_id, items, page, diagnostics)

	def item_field_values(self, item_id: str, *, cursor: str | None = None, page_size: int = 50) -> FieldValuePage:
		"""Continue a nested field-values connection using the item's distinct node ID."""
		data = self._read(_queries.VALUE_QUERY, {"id": _text(item_id, "item_id"), "first": _count(page_size, "page_size"), "cursor": _cursor(cursor)})
		return normalize.field_values(item_id, normalize.node(data, "ProjectV2Item").get("fieldValues"))

	def iter_item_pages(self, project_id: str, *, page_size: int = 50, field_page_size: int = 50, max_pages: int = 10) -> Iterator[ItemPage]:
		"""Yield pages with diagnostics; exceeding the explicit budget reports truncation."""
		_count(max_pages, "max_pages", 1000)
		cursor = None
		seen = set()
		for _ in range(max_pages):
			page = self.items(project_id, cursor=cursor, page_size=page_size, field_page_size=field_page_size)
			yield page
			if not page.page_info.has_next_page:
				return
			cursor = page.page_info.end_cursor
			if cursor in seen:
				raise ProtocolError("GitHub repeated an item-page cursor.")
			seen.add(cursor)
		raise PaginationLimitError("The item-page budget ended before the connection did.")
