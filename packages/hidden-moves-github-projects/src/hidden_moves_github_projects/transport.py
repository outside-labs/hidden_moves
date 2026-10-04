"""Bounded HTTP POST transport with credential-bearing redirects disabled."""

from dataclasses import dataclass, field
from typing import Protocol
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener


@dataclass(frozen=True)
class HTTPResponse:
	status: int
	body: bytes = field(repr=False)


class Transport(Protocol):
	def __call__(self, request: Request, *, timeout: float, max_bytes: int) -> HTTPResponse: ...


class _NoRedirect(HTTPRedirectHandler):
	def redirect_request(self, req, fp, code, msg, headers, newurl):
		return None


def http_transport(request: Request, *, timeout: float, max_bytes: int) -> HTTPResponse:
	"""Make one explicit request, reading at most the budget plus one sentinel byte."""
	try:
		with build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
			return HTTPResponse(response.status, response.read(max_bytes + 1))
	except HTTPError as error:
		status = error.code
		error.close()
		return HTTPResponse(status, b"")
