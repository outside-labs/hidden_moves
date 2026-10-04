"""Explicit local write host, separate from the default read-only host."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Iterable
from typing import TYPE_CHECKING

from .client import ProjectsClient
from .host import resolve_gh_token
from .writes import ProjectsWriter

if TYPE_CHECKING:
    from hidden_moves.adapters import CapabilityCatalog


def build_write_catalog(
    writer: ProjectsWriter, names: Iterable[str]
) -> CapabilityCatalog:
    from hidden_moves import Moves, discover_providers, load_provider
    from hidden_moves.adapters import CapabilityCatalog

    names = tuple(names)
    if not names:
        raise ValueError("Select at least one explicit Project write capability.")
    entries = [
        entry for entry in discover_providers() if entry.name == "github-projects-write"
    ]
    if len(entries) != 1:
        raise ValueError("Install exactly one github-projects-write provider.")
    moves = Moves(target=writer)
    load_provider(entries[0], moves.registry)
    return CapabilityCatalog(moves, names)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Serve explicitly authorized bounded Project writes over local MCP stdio."
    )
    parser.add_argument(
        "--allow-project",
        action="append",
        required=True,
        help="Authorized Project node ID; repeat for each allowed Project.",
    )
    parser.add_argument(
        "--move",
        action="append",
        required=True,
        help="Qualified write capability; repeat to select operations.",
    )
    args = parser.parse_args()
    try:
        from hidden_moves_mcp import MCPAdapter, serve_stdio

        from hidden_moves import MoveError

        writer = ProjectsWriter(
            ProjectsClient(resolve_gh_token), allowed_projects=args.allow_project
        )
        server = MCPAdapter(build_write_catalog(writer, args.move)).server(
            "github-projects-write"
        )
    except ImportError:
        parser.error("Install the Projects package with its [host] extra.")
    except (MoveError, ValueError) as error:
        parser.error(str(error))
    asyncio.run(serve_stdio(server))
