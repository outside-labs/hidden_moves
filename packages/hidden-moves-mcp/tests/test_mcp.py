"""Actual SDK clients exercise catalog tools in-process and over stdio."""

import asyncio
import json
import subprocess
import sys
import unittest
from dataclasses import dataclass

from mcp import Client, MCPError, StdioServerParameters
from mcp.types import CallToolRequestParams, INVALID_PARAMS

from hidden_moves import MoveAnnotations, Moves
from hidden_moves.adapters import CapabilityCatalog
from hidden_moves_mcp import MCPAdapter


def echo(value: str) -> str:
	return value


@dataclass
class Record:
	name: str
	count: int = 1


class MCPTests(unittest.IsolatedAsyncioTestCase):
	def adapter(self, func=echo, **options):
		moves = Moves()
		moves.learn(func, name="operation", namespace="example", **options)
		return MCPAdapter(CapabilityCatalog(moves, ["example.operation"]))

	async def test_real_discovery_listing_annotations_schemas_and_call(self):
		adapter = self.adapter(annotations=MoveAnnotations(read_only=True, destructive=False, external=False))
		async with Client(adapter.server()) as client:
			self.assertEqual(client.protocol_version, "2026-07-28")
			listing = await client.list_tools()
			self.assertEqual([tool.name for tool in listing.tools], ["example.operation"])
			tool = listing.tools[0]
			self.assertEqual(tool.input_schema["required"], ["value"])
			self.assertTrue(tool.annotations.read_only_hint)
			self.assertFalse(tool.annotations.destructive_hint)
			self.assertIsNone(tool.annotations.idempotent_hint)
			result = await client.call_tool(tool.name, {"value": "Héllo World"})
			self.assertFalse(result.is_error)
			self.assertEqual(result.structured_content, {"result": "Héllo World"})
			self.assertEqual(json.loads(result.content[0].text), result.structured_content)

	async def test_legacy_client_handshake_also_works(self):
		async with Client(self.adapter().server(), mode="legacy") as client:
			self.assertEqual(client.protocol_version, "2025-11-25")
			result = await client.call_tool("example.operation", {"value": "Hello World"})
			self.assertEqual(result.structured_content["result"], "Hello World")

	async def test_bad_inputs_and_unknown_tools_cannot_execute(self):
		calls = []

		def operation(value: int) -> int:
			calls.append(value)
			return value

		async with Client(self.adapter(operation).server()) as client:
			for arguments in ({}, {"value": True}, {"value": "1"}, {"value": 1, "extra": 2}):
				result = await client.call_tool("example.operation", arguments)
				self.assertTrue(result.is_error)
			with self.assertRaises(MCPError) as caught:
				await client.call_tool("unselected.operation", {"value": 1})
			self.assertEqual(caught.exception.code, INVALID_PARAMS)
		self.assertEqual(calls, [])

	async def test_async_and_structured_model_results(self):
		async def operation(record: Record) -> Record:
			self.assertIsInstance(record, Record)
			await asyncio.sleep(0)
			return record

		async with Client(self.adapter(operation).server()) as client:
			result = await client.call_tool("example.operation", {"record": {"name": "hello"}})
			self.assertEqual(result.structured_content, {"result": {"name": "hello", "count": 1}})

	async def test_capability_and_non_json_result_failures_are_tool_errors(self):
		def failure() -> str:
			raise RuntimeError("private-client-value")

		def bad_result():
			return object()

		for operation in (failure, bad_result):
			async with Client(self.adapter(operation).server()) as client:
				result = await client.call_tool("example.operation", {})
				self.assertTrue(result.is_error)
				self.assertIsNone(result.structured_content)
				self.assertNotIn("private-client-value", result.content[0].text)

	async def test_cancellation_is_not_swallowed(self):
		async def operation() -> None:
			raise asyncio.CancelledError

		adapter = self.adapter(operation)
		with self.assertRaises(asyncio.CancelledError):
			await adapter._call_tool(None, CallToolRequestParams(name="example.operation", arguments={}))

	async def test_actual_stdio_subprocess_lists_and_calls_the_installed_provider(self):
		process = StdioServerParameters(
			command=sys.executable,
			args=["-m", "hidden_moves_mcp", "--plugin", "example-text", "--move", "example.text.repeat"],
		)
		async with asyncio.timeout(20):
			async with Client(process, read_timeout_seconds=10) as client:
				listing = await client.list_tools()
				self.assertEqual([tool.name for tool in listing.tools], ["example.text.repeat"])
				result = await client.call_tool("example.text.repeat", {"value": "hello", "count": 3})
				self.assertEqual(result.structured_content, {"result": "hello hello hello"})


class ExportTests(unittest.TestCase):
	def test_name_aliases_are_validated_and_collision_checked(self):
		moves = Moves()
		moves.learn(echo, name="café")
		moves.learn(echo, name="second")
		catalog = CapabilityCatalog(moves, ["café", "second"])
		with self.assertRaises(ValueError):
			MCPAdapter(catalog)
		with self.assertRaises(ValueError):
			MCPAdapter(catalog, tool_names={"café": "same", "second": "same"})
		adapter = MCPAdapter(catalog, tool_names={"café": "cafe"})
		self.assertEqual([tool.name for tool in adapter.tools()], ["cafe", "second"])

	def test_unknown_hints_are_omitted_and_exported_views_are_independent(self):
		moves = Moves()
		moves.learn(echo)
		adapter = MCPAdapter(CapabilityCatalog(moves, ["echo"]))
		first = adapter.tools()[0]
		self.assertIsNone(first.annotations)
		first.input_schema["required"].clear()
		self.assertEqual(adapter.tools()[0].input_schema["required"], ["value"])

	def test_cli_requires_explicit_selection_before_starting(self):
		result = subprocess.run([sys.executable, "-m", "hidden_moves_mcp"], capture_output=True, text=True)
		self.assertEqual(result.returncode, 2)
		self.assertEqual(result.stdout, "")
		self.assertIn("--move", result.stderr)

	def test_cli_does_not_supply_implicit_utilities_or_bindings(self):
		for arguments in (["--move", "text.slugify"], ["--plugin", "example-text", "--move", "example.text.prefix"]):
			with self.subTest(arguments=arguments):
				result = subprocess.run([sys.executable, "-m", "hidden_moves_mcp", *arguments], capture_output=True, text=True, timeout=10)
				self.assertEqual(result.returncode, 2)
				self.assertEqual(result.stdout, "")
