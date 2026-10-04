import asyncio
import json
import sys
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from hidden_moves_github_projects import ProjectsClient
from hidden_moves_github_projects.host import build_catalog
from hidden_moves_github_projects.write_host import build_write_catalog
from hidden_moves_github_projects.write_integration import WRITE_CAPABILITIES
from hidden_moves_github_projects.writes import ProjectsWriter
from hidden_moves_mcp import MCPAdapter
from hidden_moves_openai import FunctionToolAdapter
from mcp import Client, MCPError, StdioServerParameters

from hidden_moves import Moves, UnknownMoveError, discover_providers, load_provider
from hidden_moves.adapters import CapabilityCatalog, CapabilityExposureError

sys.path.insert(0, str(Path(__file__).parents[1] / "write_tests"))
from write_replay import WriteReplay


class WriteProviderTests(unittest.TestCase):
    def test_installed_write_provider_requires_separate_explicit_binding(self):
        (entry,) = [
            entry
            for entry in discover_providers()
            if entry.name == "github-projects-write"
        ]
        with patch(
            "hidden_moves_github_projects.host.resolve_gh_token",
            side_effect=AssertionError("credential access"),
        ):
            moves = Moves()
            load_provider(entry, moves.registry)
            for name in WRITE_CAPABILITIES:
                definition = moves.describe(name)
                self.assertFalse(definition.available)
                self.assertEqual(definition.schema_errors, ())
                self.assertFalse(definition.annotations.read_only)
                self.assertTrue(definition.annotations.destructive)
                self.assertTrue(definition.annotations.external)
                self.assertNotIn("writer", definition.input_schema["properties"])
                self.assertNotIn("confirm", definition.input_schema["properties"])
            with self.assertRaises(CapabilityExposureError):
                CapabilityCatalog(moves, WRITE_CAPABILITIES)
        with self.assertRaises(UnknownMoveError):
            build_catalog(ProjectsClient("fixture"), WRITE_CAPABILITIES)


class WriteConsumerTests(unittest.IsolatedAsyncioTestCase):
    async def test_unverified_write_receipt_is_visible_to_tool_consumers(self):
        transport = WriteReplay()
        transport.ignore_set = True
        writer = ProjectsWriter(
            ProjectsClient("fixture", transport=transport),
            allowed_projects=["PROJECT_allowed"],
        )
        catalog = build_write_catalog(writer, [WRITE_CAPABILITIES[1]])
        arguments = {
            "project_id": "PROJECT_allowed",
            "item_id": "ITEM_1",
            "field_name": "Workflow",
            "option_name": "Reviewed",
            "expected_option_id": None,
        }
        async with Client(MCPAdapter(catalog).server()) as client:
            result = await client.call_tool(WRITE_CAPABILITIES[1], arguments)
            self.assertFalse(result.is_error)
            receipt = result.structured_content["result"]
            self.assertFalse(receipt["verified"])
            self.assertTrue(receipt["acknowledged"])
            self.assertEqual(receipt["diagnostic"], "ProtocolError")
            self.assertEqual(receipt["item_id"], "ITEM_1")
            self.assertEqual(receipt["field_id"], "FIELD_dynamic")

    async def test_real_stdio_write_profile_verifies_add_and_set_and_denies_other_projects(
        self,
    ):
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).with_name("write_stdio_host.py"))],
        )
        async with (
            asyncio.timeout(20),
            Client(parameters, read_timeout_seconds=10) as client,
        ):
            listing = await client.list_tools()
            self.assertEqual(
                {tool.name for tool in listing.tools}, set(WRITE_CAPABILITIES)
            )
            added = await client.call_tool(
                WRITE_CAPABILITIES[0],
                {"project_id": "PROJECT_allowed", "content_id": "CONTENT_issue"},
            )
            self.assertTrue(added.structured_content["result"]["verified"])
            changed = await client.call_tool(
                WRITE_CAPABILITIES[1],
                {
                    "project_id": "PROJECT_allowed",
                    "item_id": "ITEM_1",
                    "field_name": "Workflow",
                    "option_name": "Reviewed",
                    "expected_option_id": None,
                },
            )
            self.assertTrue(changed.structured_content["result"]["verified"])
            denied = await client.call_tool(
                WRITE_CAPABILITIES[0],
                {"project_id": "PROJECT_other", "content_id": "CONTENT_issue"},
            )
            self.assertTrue(denied.is_error)

    async def test_mcp_function_and_python_writes_agree_and_selection_is_enforced(self):
        arguments = {"project_id": "PROJECT_allowed", "content_id": "CONTENT_issue"}
        expected = asdict(
            ProjectsWriter(
                ProjectsClient("fixture", transport=WriteReplay()),
                allowed_projects=["PROJECT_allowed"],
            ).add_item(**arguments)
        )
        catalog = build_write_catalog(
            ProjectsWriter(
                ProjectsClient("private-marker", transport=WriteReplay()),
                allowed_projects=["PROJECT_allowed"],
            ),
            [WRITE_CAPABILITIES[0]],
        )
        self.assertNotIn(
            "private-marker",
            json.dumps(catalog.describe(WRITE_CAPABILITIES[0]).to_dict()),
        )
        async with Client(MCPAdapter(catalog).server()) as client:
            listing = await client.list_tools()
            self.assertEqual(
                [tool.name for tool in listing.tools], [WRITE_CAPABILITIES[0]]
            )
            result = await client.call_tool(WRITE_CAPABILITIES[0], arguments)
            self.assertFalse(result.is_error)
            self.assertEqual(result.structured_content, {"result": expected})
            with self.assertRaises(MCPError):
                await client.call_tool(WRITE_CAPABILITIES[1], {})
        adapter = FunctionToolAdapter(catalog)
        (tool,) = adapter.tools()
        result = await adapter.call_output("fixture-write", tool["name"], arguments)
        self.assertEqual(json.loads(result["output"]), expected)
