"""Explicit client configuration and selection for a local stdio application."""

from __future__ import annotations

import argparse
import asyncio
import subprocess
from collections.abc import Iterable
from typing import TYPE_CHECKING

from .client import ProjectsClient
from .errors import CredentialError

if TYPE_CHECKING:
	from hidden_moves.adapters import CapabilityCatalog


def resolve_gh_token() -> str:
	"""Explicitly read the existing GitHub CLI login; never print its captured token."""
	try:
		process = subprocess.run(
			["gh", "auth", "token", "--hostname", "github.com"],
			capture_output=True, text=True, check=False, timeout=10,
		)
	except (OSError, subprocess.SubprocessError):
		raise CredentialError("The existing GitHub CLI credential could not be read.") from None
	if process.returncode or not process.stdout.strip():
		raise CredentialError("The existing GitHub CLI credential is unavailable.")
	return process.stdout.strip()


def build_catalog(client: ProjectsClient, names: Iterable[str]) -> CapabilityCatalog:
	"""Bind the configured client before explicitly selecting installed capabilities."""
	from hidden_moves import Moves, discover_providers, load_provider
	from hidden_moves.adapters import CapabilityCatalog

	entries = [entry for entry in discover_providers() if entry.name == "github-projects"]
	if len(entries) != 1:
		raise ValueError("Install exactly one github-projects provider.")
	moves = Moves(target=client)
	load_provider(entries[0], moves.registry)
	return CapabilityCatalog(moves, names)


async def serve_client(client: ProjectsClient, names: Iterable[str]) -> None:
	"""Serve the configured, selected catalog through the existing MCP SDK adapter."""
	from hidden_moves_mcp import MCPAdapter, serve_stdio

	catalog = build_catalog(client, names)
	await serve_stdio(MCPAdapter(catalog).server("github-projects"))


def main() -> None:
	parser = argparse.ArgumentParser(description="Serve explicitly selected read-only GitHub Projects operations over local MCP stdio.")
	parser.add_argument("--move", action="append", required=True, help="Qualified read capability; repeat to select multiple operations.")
	parser.add_argument("--timeout", type=float, default=10.0, help="Finite GitHub socket timeout in seconds.")
	args = parser.parse_args()
	try:
		from hidden_moves_mcp import MCPAdapter, serve_stdio

		from hidden_moves import MoveError

		client = ProjectsClient(resolve_gh_token, timeout=args.timeout)
		catalog = build_catalog(client, args.move)
		server = MCPAdapter(catalog).server("github-projects")
	except ImportError:
		parser.error("Install the Projects package with its [host] extra.")
	except (MoveError, ValueError) as error:
		parser.error(str(error))
	asyncio.run(serve_stdio(server))
