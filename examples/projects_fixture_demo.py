"""Prove typed Projects equivalence through four consumers without account access."""

import asyncio
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

from hidden_moves_github_projects import HTTPResponse, ProjectsClient
from hidden_moves_github_projects.host import build_catalog
from hidden_moves_openai import FunctionToolAdapter
from mcp import Client, StdioServerParameters

CAPABILITY = "github.projects.items"
ARGUMENTS = {"project_id": "PVT_demo", "page_size": 5, "field_page_size": 10}
TEST_APPLICATION = Path(__file__).resolve().parents[1] / "packages/hidden-moves-github-projects/tests"


async def demonstrate() -> dict:
	fixture = json.loads((TEST_APPLICATION / "fixtures/projects.json").read_text(encoding="utf-8"))
	def replay(request, *, timeout, max_bytes):
		query = json.loads(request.data)["query"]
		operation = re.search(r"query (\w+)", query).group(1)
		return HTTPResponse(200, json.dumps(fixture[operation], allow_nan=False).encode())
	client = ProjectsClient("fixture-only", transport=replay)
	catalog = build_catalog(client, [CAPABILITY])
	results = {
		"python": asdict(client.items(**ARGUMENTS)),
		"catalog": catalog.serialize_result(CAPABILITY, catalog.invoke(CAPABILITY, ARGUMENTS)),
	}
	process = StdioServerParameters(command=sys.executable, args=[str(TEST_APPLICATION / "stdio_host.py")])
	async with asyncio.timeout(20), Client(process, read_timeout_seconds=10) as mcp:
		listing = await mcp.list_tools()
		if [tool.name for tool in listing.tools] != [CAPABILITY]:
			raise RuntimeError("The stdio host exposed an unexpected selection.")
		result = await mcp.call_tool(CAPABILITY, ARGUMENTS)
		if result.is_error:
			raise RuntimeError("The fixture stdio call failed.")
		results["stdio_mcp"] = result.structured_content["result"]
	functions = FunctionToolAdapter(catalog)
	tool, = functions.tools()
	output = await functions.call_output("fixture-call-1", tool["name"], ARGUMENTS)
	results["function_tools"] = json.loads(output["output"])
	if any(value != results["python"] for value in results.values()):
		raise RuntimeError("Projects results differ across consumers.")
	return {
		"verified_consumers": list(results), "equivalent": True,
		"item_count": len(results["python"]["items"]),
		"content_kinds": [item["content"]["kind"] for item in results["python"]["items"]],
		"fixture": "packages/hidden-moves-github-projects/tests/fixtures/projects.json",
	}


if __name__ == "__main__":
	print(json.dumps(asyncio.run(demonstrate()), indent=2, allow_nan=False))
