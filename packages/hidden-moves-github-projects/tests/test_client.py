"""Standalone reads, paging, normalization, transport bounds, and sanitized errors."""

import copy
import io
import json
import subprocess
import sys
import unittest
from dataclasses import asdict
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from hidden_moves_github_projects import (
	CredentialError,
	GraphQLError,
	HTTPResponse,
	HTTPStatusError,
	NotFoundError,
	PaginationLimitError,
	ProjectsClient,
	ProtocolError,
	TransportError,
)
from hidden_moves_github_projects.transport import _NoRedirect, http_transport
from replay import ReplayTransport


class ClientTests(unittest.TestCase):
	def setUp(self):
		self.transport = ReplayTransport()
		self.client = ProjectsClient("fixture-credential", transport=self.transport, timeout=3.0)

	def test_import_and_construction_are_independent_and_do_no_io(self):
		script = '''
import builtins
from unittest.mock import patch
original = builtins.__import__
def ordinary(name, *args, **kwargs):
    if name == "hidden_moves" or name.startswith("hidden_moves.") or name in ("mcp", "openai"):
        raise AssertionError("ordinary client imported an adapter")
    return original(name, *args, **kwargs)
with patch("builtins.__import__", side_effect=ordinary), patch("urllib.request.build_opener", side_effect=AssertionError("network")):
    from hidden_moves_github_projects import ProjectsClient
    client = ProjectsClient(lambda: (_ for _ in ()).throw(AssertionError("resolved credential")))
    assert repr(client) == "ProjectsClient()"
'''
		process = subprocess.run([sys.executable, "-B", "-c", script], capture_output=True, text=True, timeout=10, check=False)
		self.assertEqual(process.returncode, 0, process.stderr)
		self.assertEqual(process.stdout, "")

	def test_list_and_get_distinguish_user_and_organization_owners(self):
		for owner_kind, typename in (("user", "User"), ("organization", "Organization")):
			with self.subTest(kind=owner_kind):
				project = self.transport.responses["GetProject"]["data"]["owner"]["projectV2"]
				project["owner"]["__typename"] = typename
				self.transport.responses["ListProjects"]["data"]["owner"]["projectsV2"]["nodes"][0] = copy.deepcopy(project)
				self.assertEqual(self.client.get("example", owner_kind, 2).owner_kind, owner_kind)
				page = self.client.list("example", owner_kind, page_size=1, cursor="opaque")
				self.assertEqual(page.projects[0].owner_kind, owner_kind)
				payload, timeout, budget = self.transport.requests[-1]
				self.assertIn(f"owner: {owner_kind}(login:", payload["query"])
				self.assertEqual(payload["variables"], {"owner": "example", "first": 1, "cursor": "opaque"})
				self.assertEqual(timeout, 3.0)
				self.assertEqual(budget, 4_000_000)

	def test_fields_preserve_option_ids_and_completed_iterations(self):
		page = self.client.fields("PVT_demo")
		self.assertEqual(page.fields[1].options[0].id, "OPT_ready")
		self.assertEqual(page.fields[2].iterations[0].duration, 14)
		self.assertFalse(page.fields[2].iterations[0].completed)
		self.assertTrue(page.fields[2].iterations[1].completed)
		self.assertEqual(page.project_id, "PVT_demo")

	def test_items_preserve_distinct_identities_and_all_content_kinds(self):
		page = self.client.items("PVT_demo", page_size=5, field_page_size=7)
		self.assertEqual([item.content.kind for item in page.items], ["issue", "pull_request", "draft", "redacted"])
		issue = page.items[0]
		self.assertEqual((issue.project_id, issue.id, issue.content.id, issue.content.number), ("PVT_demo", "ITEM_issue", "ISSUE_node", 17))
		self.assertTrue(issue.field_values_complete)
		self.assertEqual(issue.field_values[0].option_id, "OPT_ready")
		self.assertEqual(issue.field_values[1].text, "Synthetic text")
		self.assertEqual(issue.field_values[2].number, 3.5)
		self.assertEqual(issue.field_values[3].date, "2026-10-04")
		self.assertEqual(issue.field_values[4].iteration.id, "ITER_current")
		self.assertTrue(page.items[1].archived)
		self.assertIsNone(page.items[2].content.number)
		self.assertEqual(page.diagnostics[0].code, "redacted_content")
		self.assertEqual(self.transport.requests[-1][0]["variables"]["fieldFirst"], 7)
		json.dumps(asdict(page), allow_nan=False)

	def test_nested_truncation_has_a_diagnostic_cursor_and_continuation_operation(self):
		connection = self.transport.responses["ProjectItems"]["data"]["node"]["items"]
		connection["nodes"][0]["fieldValues"]["pageInfo"] = {"hasNextPage": True, "endCursor": "nested-cursor"}
		page = self.client.items("PVT_demo")
		self.assertFalse(page.items[0].field_values_complete)
		self.assertEqual(page.items[0].field_values_page.end_cursor, "nested-cursor")
		self.assertIn("field_values_incomplete", [hint.code for hint in page.diagnostics])
		values = self.client.item_field_values("ITEM_issue", cursor="nested-cursor")
		self.assertFalse(values.page_info.has_next_page)
		self.assertEqual(self.transport.requests[-1][0]["variables"]["id"], "ITEM_issue")
		self.assertEqual(self.transport.requests[-1][0]["variables"]["cursor"], "nested-cursor")

	def test_unknown_types_and_null_nodes_are_reported_without_disappearing(self):
		fields = self.transport.responses["ProjectFields"]["data"]["node"]["fields"]["nodes"]
		fields.extend([{"__typename": "FutureField", "id": "future", "name": "Future", "dataType": "FUTURE"}, None])
		page = self.client.fields("PVT_demo")
		self.assertEqual(len(page.fields), 5)
		self.assertEqual([hint.code for hint in page.diagnostics], ["unsupported_field_type", "unavailable_field"])
		items = self.transport.responses["ProjectItems"]["data"]["node"]["items"]["nodes"]
		items[0]["fieldValues"]["nodes"].extend([{"__typename": "ProjectV2ItemFieldUserValue"}, None])
		items[1]["content"] = {"__typename": "FutureContent"}
		items.append(None)
		page = self.client.items("PVT_demo")
		self.assertEqual(len(page.items[0].field_values), 7)
		self.assertFalse(page.items[0].field_values_complete)
		self.assertEqual(page.items[1].content.kind, "unknown")
		self.assertIn("unavailable_item", [hint.code for hint in page.diagnostics])

	def test_outer_connections_retain_next_cursors(self):
		for operation, key, call in (("ListProjects", "projectsV2", lambda: self.client.list("example", "organization")), ("ProjectFields", "fields", lambda: self.client.fields("PVT_demo")), ("ProjectItems", "items", lambda: self.client.items("PVT_demo"))):
			with self.subTest(operation=operation):
				data = self.transport.responses[operation]["data"]
				parent = data["owner"] if operation == "ListProjects" else data["node"]
				parent[key]["pageInfo"] = {"hasNextPage": True, "endCursor": "next"}
				self.assertTrue(call().page_info.has_next_page)
				self.assertEqual(call().page_info.end_cursor, "next")

	def test_iterator_reports_budget_exhaustion_and_repeated_cursors(self):
		page = self.transport.responses["ProjectItems"]["data"]["node"]["items"]
		page["pageInfo"] = {"hasNextPage": True, "endCursor": "same"}
		with self.assertRaises(PaginationLimitError):
			list(self.client.iter_item_pages("PVT_demo", max_pages=1))
		with self.assertRaises(ProtocolError):
			list(self.client.iter_item_pages("PVT_demo", max_pages=3))

	def test_invalid_configuration_and_inputs_do_not_resolve_credentials(self):
		for timeout in (0, -1, float("nan"), float("inf"), True):
			with self.subTest(timeout=timeout), self.assertRaises(ValueError):
				ProjectsClient("fixture", timeout=timeout)
		for endpoint in ("http://example.test/graphql", "file:///tmp/data", "https://user:password@example.test/graphql", "https://example.test/graphql?q=secret"):
			with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
				ProjectsClient("fixture", endpoint=endpoint)
		with patch.object(self.client, "_token") as token:
			for operation in (lambda: self.client.get("example", "other", 2), lambda: self.client.get("example", "user", True), lambda: self.client.items("", page_size=1), lambda: self.client.items("id", page_size=101), lambda: self.client.items("id", field_page_size=0), lambda: self.client.fields("id", cursor="")):
				with self.assertRaises(ValueError):
					operation()
			token.assert_not_called()

	def test_missing_owners_projects_and_wrong_node_types_have_typed_errors(self):
		self.transport.responses["GetProject"] = {"data": {"owner": None}}
		with self.assertRaises(NotFoundError):
			self.client.get("example", "user", 2)
		self.transport.responses["ProjectFields"] = {"data": {"node": {"__typename": "Issue"}}}
		with self.assertRaises(NotFoundError):
			self.client.fields("ISSUE_node")

	def test_credentials_request_headers_and_exception_text_do_not_leak(self):
		credential = "synthetic-private-marker"
		seen = []
		def transport(request, **options):
			seen.append(request)
			raise RuntimeError(credential)
		client = ProjectsClient(credential, transport=transport)
		with self.assertRaises(TransportError) as caught:
			client.get("example", "user", 2)
		self.assertEqual(seen[0].get_header("Authorization"), "Bearer " + credential)
		self.assertNotIn(credential, seen[0].data.decode())
		self.assertNotIn(credential, repr(client))
		self.assertNotIn(credential, str(caught.exception))
		with self.assertRaises(CredentialError):
			ProjectsClient(lambda: (_ for _ in ()).throw(RuntimeError(credential))).get("example", "user", 2)

	def test_http_and_graphql_errors_never_return_partial_success_or_upstream_text(self):
		for status in (301, 401, 403, 429, 500):
			with self.subTest(status=status), self.assertRaises(HTTPStatusError) as caught:
				ProjectsClient("fixture", transport=lambda *args, status=status, **kwargs: HTTPResponse(status, b"private error text")).get("example", "user", 2)
			self.assertEqual(caught.exception.status, status)
		response = HTTPResponse(200, json.dumps({"data": {"owner": None}, "errors": [{"type": "FORBIDDEN", "message": "synthetic-private-marker"}, {"type": "private-unknown-code"}]}).encode())
		with self.assertRaises(GraphQLError) as caught:
			ProjectsClient("fixture", transport=lambda *args, **kwargs: response).get("example", "user", 2)
		self.assertEqual(caught.exception.codes, ("FORBIDDEN", "GRAPHQL_ERROR"))
		self.assertTrue(caught.exception.partial_data)
		self.assertNotIn("private", str(caught.exception))

	def test_oversized_invalid_nonfinite_and_malformed_responses_are_rejected(self):
		for body in (b"not-json", b"[]", b'{"data":null}', b'{"data":NaN}', b'{"data":{"owner":{"projectV2":false}}}'):
			with self.subTest(body=body), self.assertRaises(ProtocolError):
				ProjectsClient("fixture", transport=lambda *args, body=body, **kwargs: HTTPResponse(200, body)).get("example", "user", 2)
		with self.assertRaises(ProtocolError):
			ProjectsClient("fixture", max_response_bytes=2, transport=lambda *args, **kwargs: HTTPResponse(200, b"abc")).get("example", "user", 2)
		self.transport.responses["ProjectItems"]["data"]["node"]["items"]["pageInfo"] = {"hasNextPage": True, "endCursor": None}
		with self.assertRaises(ProtocolError):
			self.client.items("PVT_demo")

	def test_default_transport_bounds_reads_closes_responses_and_disables_redirects(self):
		response = io.BytesIO(b"123456789")
		response.status = 200
		with patch("hidden_moves_github_projects.transport.build_opener") as build:
			build.return_value.open.return_value = response
			result = http_transport(Request("https://example.test/graphql"), timeout=2, max_bytes=3)
			self.assertIsInstance(build.call_args.args[0], _NoRedirect)
			self.assertEqual(build.return_value.open.call_args.kwargs["timeout"], 2)
		self.assertEqual(result.body, b"1234")
		self.assertTrue(response.closed)
		self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, None, None, "https://other.test"))
		body = io.BytesIO(b"private-message")
		error = HTTPError("https://example.test/graphql", 403, "private-message", {}, body)
		with patch("hidden_moves_github_projects.transport.build_opener") as build:
			build.return_value.open.side_effect = error
			self.assertEqual(http_transport(Request("https://example.test/graphql"), timeout=2, max_bytes=3), HTTPResponse(403, b""))
		self.assertTrue(body.closed)
