"""Synthetic stdio host with one authorized fixture Project and selected writes."""

import asyncio
import sys
from pathlib import Path

from hidden_moves_github_projects import ProjectsClient
from hidden_moves_github_projects.write_host import build_write_catalog
from hidden_moves_github_projects.write_integration import WRITE_CAPABILITIES
from hidden_moves_github_projects.writes import ProjectsWriter
from hidden_moves_mcp import MCPAdapter, serve_stdio

sys.path.insert(0, str(Path(__file__).parents[1] / "write_tests"))
from write_replay import WriteReplay

writer = ProjectsWriter(
    ProjectsClient("fixture", transport=WriteReplay()),
    allowed_projects=["PROJECT_allowed"],
)
asyncio.run(
    serve_stdio(
        MCPAdapter(build_write_catalog(writer, WRITE_CAPABILITIES)).server(
            "fixture-writes"
        )
    )
)
