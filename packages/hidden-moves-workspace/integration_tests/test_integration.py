"""Installed discovery, configured CLI, and equivalent structured consumers."""

import asyncio
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import asdict
from importlib.metadata import EntryPoint
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner
from hidden_moves_mcp import MCPAdapter
from hidden_moves_openai import FunctionToolAdapter
from hidden_moves_workspace import Workspace
from hidden_moves_workspace.host import build_catalog, main
from hidden_moves_workspace.integration import READ_CAPABILITIES, provide_moves
from mcp import Client, MCPError, StdioServerParameters

from hidden_moves import Moves, UnknownMoveError, discover_providers, load_provider
from hidden_moves.adapters import (
    CapabilityArgumentError,
    CapabilityCatalog,
    CapabilityExposureError,
)
from hidden_moves.cli import main as generic_cli


class WorkspaceFixture:
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "demo.txt").write_bytes("alpha\nβ target\nlast target\n".encode())
        self.workspace = Workspace(self.root, ["demo.txt"])

    def command(self, *moves):
        result = ["--root", str(self.root), "--file", "demo.txt"]
        for name in moves:
            result.extend(["--move", name])
        return result


class ProviderTests(WorkspaceFixture, unittest.TestCase):
    def test_installed_discovery_and_unbound_inspection_read_no_content(self):
        with patch.object(Workspace, "_read", side_effect=AssertionError("content read")):
            entry, = [entry for entry in discover_providers() if entry.name == "workspace"]
            moves = Moves()
            load_provider(entry, moves.registry)
            self.assertEqual({move.qualified_name for move in moves.moves()}, set(READ_CAPABILITIES))
            for name in READ_CAPABILITIES:
                definition = moves.describe(name)
                self.assertFalse(definition.available)
                self.assertEqual(definition.schema_errors, ())
                self.assertNotIn("workspace", definition.input_schema["properties"])
                self.assertTrue(definition.annotations.read_only)
                self.assertTrue(definition.annotations.idempotent)
                self.assertFalse(definition.annotations.destructive)
            with self.assertRaises(CapabilityExposureError):
                CapabilityCatalog(moves, ["workspace.read"])
            self.assertEqual(len(provide_moves()), 3)

    def test_generic_cli_can_inspect_but_cannot_infer_a_workspace(self):
        runner = CliRunner()
        result = runner.invoke(generic_cli, ["--plugin", "workspace", "moves", "show", "workspace.read"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertFalse(json.loads(result.output)["available"])
        result = runner.invoke(generic_cli, ["--plugin", "workspace", "moves", "call", "workspace.read", "--arguments", '{"path":"demo.txt"}'])
        self.assertNotEqual(result.exit_code, 0)

    def test_bound_catalog_keeps_root_private_and_rejects_unselected_names(self):
        with patch.object(Workspace, "_read", side_effect=AssertionError("content read")):
            catalog = build_catalog(self.workspace, ["workspace.files"])
            self.assertNotIn(str(self.root), json.dumps(catalog.describe("workspace.files").to_dict()))
            self.assertEqual(catalog.serialize_result("workspace.files", catalog.invoke("workspace.files", {})), {"paths": ["demo.txt"], "next_offset": None})
            with self.assertRaises(UnknownMoveError):
                catalog.invoke("workspace.read", {"path": "demo.txt"})
        self.assertEqual(build_catalog(self.workspace, []).definitions(), ())

    def test_all_wrappers_dispatch_with_equivalent_typed_results(self):
        catalog = build_catalog(self.workspace, READ_CAPABILITIES)
        for name, arguments, expected in (
            ("workspace.files", {"limit": 1}, self.workspace.files(limit=1)),
            ("workspace.read", {"path": "demo.txt", "line_count": 2}, self.workspace.read("demo.txt", line_count=2)),
            ("workspace.search", {"path": "demo.txt", "query": "target", "max_matches": 1}, self.workspace.search("demo.txt", "target", max_matches=1)),
        ):
            with self.subTest(name=name):
                self.assertEqual(catalog.serialize_result(name, catalog.invoke(name, arguments)), asdict(expected))

    def test_invalid_structured_arguments_cannot_read_content(self):
        catalog = build_catalog(self.workspace, ["workspace.read"])
        with patch.object(Workspace, "_read", side_effect=AssertionError("content read")):
            for arguments in ({}, {"path": 1}, {"path": "demo.txt", "extra": True}, {"path": "demo.txt", "line_count": True}, {"path": "demo.txt", "line_count": float("nan")}, []):
                with self.subTest(arguments=arguments), self.assertRaises(CapabilityArgumentError):
                    catalog.invoke("workspace.read", arguments)

    def test_missing_or_ambiguous_providers_fail_without_reading(self):
        entry = EntryPoint("workspace", "a:factory", "hidden_moves.moves")
        for entries in ((), (entry, entry)):
            with self.subTest(entries=entries), patch("hidden_moves.discover_providers", return_value=entries), self.assertRaises(ValueError):
                build_catalog(self.workspace, ["workspace.read"])

    def test_configured_module_cli_prints_valid_json(self):
        process = subprocess.run(
            [sys.executable, "-m", "hidden_moves_workspace", *self.command("workspace.read"), "call", "workspace.read", "--arguments", '{"path":"demo.txt","line_count":2}'],
            capture_output=True, text=True, check=True, timeout=10,
        )
        self.assertEqual(json.loads(process.stdout), asdict(self.workspace.read("demo.txt", line_count=2)))

    def test_cli_requires_configuration_and_does_not_read_invalid_or_unselected_calls(self):
        for arguments in (
            ["call", "workspace.read"],
            [*self.command("workspace.files"), "call", "workspace.read", "--arguments", '{"path":"demo.txt"}'],
            [*self.command("workspace.read"), "call", "workspace.read", "--arguments", '{"path":1}'],
            [*self.command("workspace.read"), "call", "workspace.read", "--arguments", "invalid"],
            [*self.command("workspace.read"), "call", "workspace.read", "--arguments", '{"path":"demo.txt","line_count":NaN}'],
        ):
            with self.subTest(arguments=arguments), patch.object(Workspace, "_read", side_effect=AssertionError("content read")), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as context:
                main(arguments)
            self.assertEqual(context.exception.code, 2)


class ConsumerTests(WorkspaceFixture, unittest.IsolatedAsyncioTestCase):
    async def test_catalog_mcp_and_function_tools_equal_python_for_every_operation(self):
        catalog = build_catalog(self.workspace, READ_CAPABILITIES)
        functions = FunctionToolAdapter(catalog)
        async with Client(MCPAdapter(catalog).server()) as mcp:
            for name, arguments, expected in (
                ("workspace.files", {}, self.workspace.files()),
                ("workspace.read", {"path": "demo.txt", "line_count": 2}, self.workspace.read("demo.txt", line_count=2)),
                ("workspace.search", {"path": "demo.txt", "query": "target", "max_matches": 1}, self.workspace.search("demo.txt", "target", max_matches=1)),
            ):
                with self.subTest(name=name):
                    expected = asdict(expected)
                    self.assertEqual(catalog.serialize_result(name, catalog.invoke(name, arguments)), expected)
                    result = await mcp.call_tool(name, arguments)
                    self.assertFalse(result.is_error)
                    self.assertEqual(result.structured_content, {"result": expected})
                    output = await functions.call_output("offline-call", name.replace(".", "__"), arguments)
                    self.assertEqual(json.loads(output["output"]), expected)

    async def test_actual_stdio_host_lists_only_selected_moves_and_supports_continuation(self):
        process = StdioServerParameters(
            command=sys.executable,
            args=["-m", "hidden_moves_workspace", *self.command("workspace.read"), "serve"],
        )
        async with asyncio.timeout(20), Client(process, read_timeout_seconds=10) as client:
            listing = await client.list_tools()
            self.assertEqual([tool.name for tool in listing.tools], ["workspace.read"])
            first = await client.call_tool("workspace.read", {"path": "demo.txt", "line_count": 1})
            self.assertFalse(first.is_error)
            page = first.structured_content["result"]
            expected = asdict(self.workspace.read("demo.txt", line_count=1))
            self.assertEqual(page, expected)
            second = await client.call_tool("workspace.read", {
                "path": "demo.txt", "start_line": page["next_line"],
                "start_column": page["next_column"], "expected_sha256": page["sha256"],
            })
            self.assertFalse(second.is_error)
            self.assertIsNone(second.structured_content["result"]["next_line"])
            with self.assertRaises(MCPError):
                await client.call_tool("workspace.search", {"path": "demo.txt", "query": "target"})
            (self.root / "demo.txt").write_bytes(b"new content")
            stale = await client.call_tool("workspace.read", {"path": "demo.txt", "expected_sha256": page["sha256"]})
            self.assertTrue(stale.is_error)
            self.assertIn("StaleContentError", stale.content[0].text)
            self.assertNotIn(str(self.root), stale.content[0].text)
            forbidden = await client.call_tool("workspace.read", {"path": "../outside"})
            self.assertTrue(forbidden.is_error)
            invalid = await client.call_tool("workspace.read", {"path": 1})
            self.assertTrue(invalid.is_error)

    async def test_unselected_function_tool_is_unavailable(self):
        functions = FunctionToolAdapter(build_catalog(self.workspace, ["workspace.files"]))
        with self.assertRaises(UnknownMoveError):
            await functions.call("workspace__read", {"path": "demo.txt"})

    async def test_actual_stdio_listing_and_search_equal_direct_python(self):
        process = StdioServerParameters(
            command=sys.executable,
            args=["-m", "hidden_moves_workspace", *self.command("workspace.files", "workspace.search"), "serve"],
        )
        async with asyncio.timeout(20), Client(process, read_timeout_seconds=10) as client:
            listing = await client.list_tools()
            self.assertEqual([tool.name for tool in listing.tools], ["workspace.files", "workspace.search"])
            for name, arguments, expected in (
                ("workspace.files", {}, self.workspace.files()),
                ("workspace.search", {"path": "demo.txt", "query": "target", "max_matches": 1}, self.workspace.search("demo.txt", "target", max_matches=1)),
            ):
                with self.subTest(name=name):
                    result = await client.call_tool(name, arguments)
                    self.assertFalse(result.is_error)
                    self.assertEqual(result.structured_content, {"result": asdict(expected)})
            with self.assertRaises(MCPError):
                await client.call_tool("workspace.read", {"path": "demo.txt"})
