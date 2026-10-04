"""Thin Click adapters for explicit capability inspection and invocation."""

import asyncio
import inspect
import json
from typing import Any

import click

from hidden_moves import MoveError, Moves, discover_providers
from hidden_moves.adapters import CapabilityCatalog


@click.group(name="moves")
def move_commands() -> None:
	"""Inspect registered capabilities."""


@move_commands.command(name="list")
@click.option("--json", "as_json", is_flag=True, help="Emit complete capability definitions as JSON.")
@click.pass_obj
def list_moves(moves: Moves, as_json: bool) -> None:
	if as_json:
		click.echo(json.dumps([moves.explain(spec.qualified_name) for spec in moves.moves()], indent=2))
		return
	for spec in moves.moves():
		click.echo(f"{spec.qualified_name}\t{spec.summary}")


@move_commands.command(name="show")
@click.argument("name")
@click.pass_obj
def show_move(moves: Moves, name: str) -> None:
	try:
		click.echo(json.dumps(moves.explain(name), indent=2))
	except MoveError as error:
		raise click.ClickException(str(error)) from error


async def _await_result(result: Any) -> Any:
	return await result


@move_commands.command(name="call")
@click.argument("name")
@click.option("--arguments", default="{}", help="Arguments as a JSON object.")
@click.pass_obj
def call_move(moves: Moves, name: str, arguments: str) -> None:
	"""Explicitly call one capability through its structured argument contract."""
	try:
		values = json.loads(arguments)
	except json.JSONDecodeError as error:
		raise click.BadParameter(str(error), param_hint="--arguments") from error
	if not isinstance(values, dict):
		raise click.BadParameter("Expected a JSON object.", param_hint="--arguments")
	try:
		catalog = CapabilityCatalog(moves, [name])
		result = catalog.invoke(name, values)
		if inspect.isawaitable(result):
			result = asyncio.run(_await_result(result))
		click.echo(json.dumps(catalog.serialize_result(name, result), indent=2, allow_nan=False))
	except MoveError as error:
		raise click.ClickException(str(error)) from error
	except Exception as error:
		raise click.ClickException(f"Capability {name!r} failed: {error}") from error


@click.group(name="plugins")
def plugin_commands() -> None:
	"""Inspect installed provider metadata."""


@plugin_commands.command(name="list")
def list_plugins() -> None:
	for entry in discover_providers():
		click.echo(f"{entry.name}\t{entry.value}")
