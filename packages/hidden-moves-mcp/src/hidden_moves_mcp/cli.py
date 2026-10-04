"""Explicit provider activation and capability selection for a local stdio host."""

import argparse
import asyncio

from hidden_moves import MoveError, Moves, Registry, discover_providers, load_provider
from hidden_moves.adapters import CapabilityCatalog

from .server import MCPAdapter, serve_stdio


def main() -> None:
	parser = argparse.ArgumentParser(description="Serve explicitly selected Hidden Moves capabilities over MCP stdio.")
	parser.add_argument("--move", dest="moves", action="append", required=True, help="Qualified capability to expose; repeat for multiple names.")
	parser.add_argument("--plugin", action="append", default=[], help="Installed provider to explicitly activate.")
	parser.add_argument("--name", default="hidden-moves", help="Server identity.")
	arguments = parser.parse_args()
	registry = Registry()
	try:
		if arguments.plugin:
			entries = discover_providers()
			for name in arguments.plugin:
				matches = [entry for entry in entries if entry.name == name]
				if len(matches) != 1:
					parser.error(f"Provider {name!r} must be installed and unambiguous.")
				load_provider(matches[0], registry)
		catalog = CapabilityCatalog(Moves(registry=registry), arguments.moves)
		server = MCPAdapter(catalog).server(arguments.name)
	except (MoveError, ValueError) as error:
		parser.error(str(error))
	asyncio.run(serve_stdio(server))
