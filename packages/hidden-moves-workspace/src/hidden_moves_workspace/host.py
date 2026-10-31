"""Explicit configuration and selection for JSON CLI and local stdio MCP."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Iterable
from typing import TYPE_CHECKING

from .client import Workspace
from .errors import WorkspaceError

if TYPE_CHECKING:
    from hidden_moves.adapters import CapabilityCatalog


def build_catalog(workspace: Workspace, names: Iterable[str]) -> CapabilityCatalog:
    """Bind the configured workspace before selecting installed capabilities."""
    from hidden_moves import Moves, discover_providers, load_provider
    from hidden_moves.adapters import CapabilityCatalog

    entries = [entry for entry in discover_providers() if entry.name == "workspace"]
    if len(entries) != 1:
        raise ValueError("Install exactly one workspace provider.")
    moves = Moves(target=workspace)
    load_provider(entries[0], moves.registry)
    return CapabilityCatalog(moves, names)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Read explicitly selected workspace text through JSON CLI or local MCP stdio.")
    parser.add_argument("--root", required=True, help="Explicit workspace root; no default or directory scan.")
    parser.add_argument("--file", action="append", required=True, help="Exact relative path; repeat to select files.")
    parser.add_argument("--move", action="append", required=True, help="Qualified capability; repeat to select operations.")
    parser.add_argument("--max-file-bytes", type=int, default=262_144, help="Per-file byte ceiling, at most 1,048,576.")
    commands = parser.add_subparsers(dest="command", required=True)
    call = commands.add_parser("call", help="Invoke one selected operation and print validated JSON.")
    call.add_argument("name")
    call.add_argument("--arguments", default="{}", help="JSON object; follows the selected move's schema.")
    commands.add_parser("serve", help="Serve only the selected operations over local MCP stdio.")
    args = parser.parse_args(argv)
    try:
        from hidden_moves import MoveError
    except ImportError:
        parser.error("Install the workspace package with its [moves] or [host] extra.")
    try:
        workspace = Workspace(args.root, args.file, max_file_bytes=args.max_file_bytes)
        catalog = build_catalog(workspace, args.move)
        if args.command == "call":
            try:
                arguments = json.loads(args.arguments)
            except (ValueError, RecursionError):
                parser.error("arguments must be a finite JSON object.")
            value = catalog.invoke(args.name, arguments)
            print(json.dumps(catalog.serialize_result(args.name, value), allow_nan=False))
            return
        try:
            from hidden_moves_mcp import MCPAdapter, serve_stdio
        except ImportError:
            parser.error("Install the workspace package with its [host] extra.")
        server = MCPAdapter(catalog, offload_sync=True).server("workspace")
    except (WorkspaceError, MoveError, ValueError, TypeError) as error:
        parser.error(str(error))
    asyncio.run(serve_stdio(server))
