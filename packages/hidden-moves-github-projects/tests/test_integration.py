"""Installed provider inspection and equivalent catalog/MCP/function-tool results."""

import asyncio
import json
import subprocess
import sys
import unittest
from dataclasses import asdict
from importlib.metadata import EntryPoint
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner
from hidden_moves_github_projects import ProjectsClient
from hidden_moves_github_projects.host import build_catalog, resolve_gh_token
from hidden_moves_github_projects.integration import READ_CAPABILITIES, provide_moves
from hidden_moves_mcp import MCPAdapter
from hidden_moves_openai import FunctionToolAdapter
from mcp import Client, MCPError, StdioServerParameters
from replay import ReplayTransport

from hidden_moves import Moves, UnknownMoveError, discover_providers, load_provider
from hidden_moves.adapters import (
	CapabilityArgumentError,
	CapabilityCatalog,
	CapabilityExposureError,
)
from hidden_moves.cli import main

CAPABILITY = "github.projects.items"
ARGUMENTS = {"project_id": "PVT_demo", "page_size": 5, "field_page_size": 10}


class ProviderTests(unittest.TestCase):
	def test_discovery_and_unbound_inspection_need_no_credentials_or_requests(self):
		moves = Moves()
		entry, = [entry for entry in discover_providers() if entry.name == "github-projects"]
		with patch("hidden_moves_github_projects.host.resolve_gh_token", side_effect=AssertionError("credential access")):
			load_provider(entry, moves.registry)
			self.assertEqual({move.qualified_name for move in moves.moves()}, set(READ_CAPABILITIES))
			for name in READ_CAPABILITIES:
				definition = moves.describe(name)
				self.assertFalse(definition.available)
				self.assertEqual(definition.schema_errors, ())
				self.assertNotIn("client", definition.input_schema["properties"])
				self.assertTrue(definition.annotations.read_only)
				self.assertTrue(definition.annotations.external)
				self.assertFalse(definition.annotations.destructive)
			with self.assertRaises(CapabilityExposureError):
				CapabilityCatalog(moves, [CAPABILITY])

	def test_generic_cli_can_inspect_but_cannot_invent_account_binding(self):
		runner = CliRunner()
		result = runner.invoke(main, ["--plugin", "github-projects", "moves", "show", CAPABILITY])
		self.assertEqual(result.exit_code, 0, result.output)
		self.assertFalse(json.loads(result.output)["available"])
		result = runner.invoke(main, ["--plugin", "github-projects", "moves", "call", CAPABILITY, "--arguments", json.dumps(ARGUMENTS)])
		self.assertEqual(result.exit_code, 1)
		self.assertIn("requires Moves", result.output)

	def test_bound_catalog_keeps_credentials_private_and_selection_enforced(self):
		transport = ReplayTransport()
		client = ProjectsClient("synthetic-private-marker", transport=transport)
		catalog = build_catalog(client, [CAPABILITY])
		self.assertEqual(transport.requests, [])
		self.assertNotIn("synthetic-private-marker", json.dumps(catalog.describe(CAPABILITY).to_dict()))
		with self.assertRaises(UnknownMoveError):
			catalog.invoke("github.projects.get", {"owner": "example", "owner_kind": "organization", "number": 2})
		with self.assertRaises(CapabilityArgumentError):
			catalog.invoke(CAPABILITY, {"project_id": 1})
		self.assertEqual(transport.requests, [])
		self.assertEqual(catalog.serialize_result(CAPABILITY, catalog.invoke(CAPABILITY, ARGUMENTS)), asdict(client.items(**ARGUMENTS)))

	def test_every_read_wrapper_dispatches_with_supported_typed_results(self):
		client = ProjectsClient("fixture", transport=ReplayTransport())
		catalog = build_catalog(client, READ_CAPABILITIES)
		arguments = {
			"github.projects.list": {"owner": "example", "owner_kind": "organization"},
			"github.projects.get": {"owner": "example", "owner_kind": "organization", "number": 2},
			"github.projects.fields": {"project_id": "PVT_demo"},
			CAPABILITY: ARGUMENTS,
		}
		for name, values in arguments.items():
			with self.subTest(name=name):
				json.dumps(catalog.serialize_result(name, catalog.invoke(name, values)), allow_nan=False)

	def test_factory_is_zero_argument_and_host_requires_unique_provider(self):
		self.assertEqual(len(provide_moves()), 4)
		for entries in ((), (EntryPoint("github-projects", "a:factory", "hidden_moves.moves"), EntryPoint("github-projects", "b:factory", "hidden_moves.moves"))):
			with self.subTest(entries=entries), patch("hidden_moves.discover_providers", return_value=entries), self.assertRaises(ValueError):
				build_catalog(ProjectsClient("fixture"), [CAPABILITY])

	def test_credential_resolver_captures_login_without_echo_or_implicit_setup(self):
		with patch("hidden_moves_github_projects.host.subprocess.run") as run:
			run.return_value = subprocess.CompletedProcess(["gh"], 0, "fixture-token\n", "")
			self.assertEqual(resolve_gh_token(), "fixture-token")
			self.assertEqual(run.call_args.args[0], ["gh", "auth", "token", "--hostname", "github.com"])
			self.assertTrue(run.call_args.kwargs["capture_output"])
			self.assertEqual(run.call_args.kwargs["timeout"], 10)


class ConsumerTests(unittest.IsolatedAsyncioTestCase):
	async def test_python_catalog_mcp_and_function_tools_return_equivalent_fixture_data(self):
		client = ProjectsClient("fixture", transport=ReplayTransport())
		catalog = build_catalog(client, [CAPABILITY])
		expected = asdict(client.items(**ARGUMENTS))
		self.assertEqual(catalog.serialize_result(CAPABILITY, catalog.invoke(CAPABILITY, ARGUMENTS)), expected)
		async with Client(MCPAdapter(catalog).server()) as mcp:
			listing = await mcp.list_tools()
			self.assertEqual([tool.name for tool in listing.tools], [CAPABILITY])
			response = await mcp.call_tool(CAPABILITY, ARGUMENTS)
			self.assertFalse(response.is_error)
			self.assertEqual(response.structured_content, {"result": expected})
			with self.assertRaises(MCPError):
				await mcp.call_tool("github.projects.get", {})
		functions = FunctionToolAdapter(catalog)
		tool, = functions.tools()
		output = await functions.call_output("fixture-call-1", tool["name"], ARGUMENTS)
		self.assertEqual(json.loads(output["output"]), expected)
		with self.assertRaises(UnknownMoveError):
			await functions.call("github__projects__get", {})

	async def test_actual_stdio_host_initializes_lists_calls_and_rejects_unselected_operations(self):
		expected = asdict(ProjectsClient("fixture", transport=ReplayTransport()).items(**ARGUMENTS))
		process = StdioServerParameters(command=sys.executable, args=[str(Path(__file__).with_name("stdio_host.py"))])
		async with asyncio.timeout(20), Client(process, read_timeout_seconds=10) as client:
			listing = await client.list_tools()
			self.assertEqual([tool.name for tool in listing.tools], [CAPABILITY])
			result = await client.call_tool(CAPABILITY, ARGUMENTS)
			self.assertFalse(result.is_error)
			self.assertEqual(result.structured_content, {"result": expected})
			with self.assertRaises(MCPError):
				await client.call_tool("github.projects.get", {})
