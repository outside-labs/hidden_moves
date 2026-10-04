"""Inspect built wheels and smoke-test their installed public interfaces."""

import argparse
import importlib
import json
import subprocess
import sys
import sysconfig
from email.parser import BytesParser
from pathlib import Path
from zipfile import ZipFile

PUBLIC = {
	"hidden-moves": "hidden_moves",
	"hidden-moves-mcp": "hidden_moves_mcp",
	"hidden-moves-openai": "hidden_moves_openai",
	"hidden-moves-github-projects": "hidden_moves_github_projects",
}
EXAMPLE = "hidden-moves-example-text"


def check_wheels(directory: Path) -> None:
	seen = set()
	for path in sorted(directory.glob("*.whl")):
		with ZipFile(path) as wheel:
			names = wheel.namelist()
			metadata_path, = [name for name in names if name.endswith(".dist-info/METADATA")]
			metadata = BytesParser().parsebytes(wheel.read(metadata_path))
			name = metadata["Name"].replace("_", "-").lower()
			if name in seen:
				raise ValueError(f"Duplicate wheel for {name}.")
			seen.add(name)
			if any(name.endswith((".pyc", ".log", ".txt")) and ".dist-info/" not in name for name in names):
				raise ValueError(f"Unexpected generated/log artifact in {path.name}.")
			if name == EXAMPLE:
				continue
			if name not in PUBLIC:
				raise ValueError(f"Unexpected distribution {name}.")
			if metadata["Version"] != "0.1.0" or metadata["Requires-Python"] != ">=3.11":
				raise ValueError(f"Unexpected version/runtime metadata for {name}.")
			if metadata["License-Expression"] != "MIT" or metadata.get_all("License-File") != ["LICENSE"]:
				raise ValueError(f"Missing MIT license metadata for {name}.")
			license_path, = [item for item in names if item.endswith(".dist-info/licenses/LICENSE")]
			if wheel.read(license_path) != Path("LICENSE").read_bytes():
				raise ValueError(f"License notice mismatch for {name}.")
			if metadata["Description-Content-Type"] != "text/markdown" or not metadata.get_payload().strip():
				raise ValueError(f"Missing Markdown README for {name}.")
			if "Development Status :: 3 - Alpha" not in metadata.get_all("Classifier", []):
				raise ValueError(f"Missing experimental classifier for {name}.")
			if not any("https://github.com/outside-labs/hidden_moves" in url for url in metadata.get_all("Project-URL", [])):
				raise ValueError(f"Missing repository URL for {name}.")
			if f"{PUBLIC[name]}/__init__.py" not in names:
				raise ValueError(f"Missing import package for {name}.")
			requirements = metadata.get_all("Requires-Dist", [])
			if name in {"hidden-moves-mcp", "hidden-moves-openai"} and not any(
				requirement.replace(" ", "").startswith("hidden-moves")
				and ">=0.1" in requirement and "<0.2" in requirement
				for requirement in requirements
			):
				raise ValueError(f"Missing tested core minor range for {name}.")
			if name == "hidden-moves-github-projects" and any(";" not in requirement for requirement in requirements):
				raise ValueError("The ordinary Projects client must have no mandatory dependencies.")
			if name == "hidden-moves":
				allowed = {"core", "adapters", "commands", "__init__.py", "__main__.py", "cli.py"}
				for item in names:
					if item.startswith("hidden_moves/") and not item.endswith("/") and item.split("/")[1] not in allowed:
						raise ValueError(f"Domain/prototype module shipped in core: {item}.")
	if seen != set(PUBLIC) | {EXAMPLE}:
		raise ValueError(f"Incomplete wheel set: {sorted(seen)}.")
	print("All intended wheels contain the expected imports, metadata, and licenses.")


def smoke_installed() -> None:
	for package in PUBLIC.values():
		importlib.import_module(package)
	from hidden_moves_example_text import prefix_text
	from hidden_moves_mcp import MCPAdapter
	from hidden_moves_openai import FunctionToolAdapter

	from hidden_moves import Moves, discover_providers, load_provider
	from hidden_moves.adapters import CapabilityCatalog

	entry, = [entry for entry in discover_providers() if entry.name == "example-text"]
	moves = Moves("wheel: ")
	load_provider(entry, moves.registry)
	catalog = CapabilityCatalog(moves, ["example.text.prefix"])
	if catalog.invoke("example.text.prefix", {"value": "hello"}) != prefix_text("wheel: ", "hello"):
		raise ValueError("Installed target binding failed.")
	if not MCPAdapter(catalog).tools() or not FunctionToolAdapter(catalog).tools():
		raise ValueError("Installed adapter export failed.")
	scripts = Path(sysconfig.get_path("scripts"))
	suffix = ".exe" if sys.platform == "win32" else ""
	for command in ([str(scripts / ("hidden-moves" + suffix))], [str(scripts / ("hm" + suffix))], [sys.executable, "-m", "hidden_moves"]):
		process = subprocess.run([*command, "moves", "list", "--json"], capture_output=True, text=True, check=True, timeout=10)
		if json.loads(process.stdout) != []:
			raise ValueError("Installed CLI did not start with an empty registry.")
	process = subprocess.run(
		[sys.executable, "-m", "hidden_moves", "--plugin", "example-text", "moves", "call", "example.text.repeat", "--arguments", '{"value":"hello","count":3}'],
		capture_output=True, text=True, check=True, timeout=10,
	)
	if json.loads(process.stdout) != "hello hello hello":
		raise ValueError("Installed provider CLI invocation failed.")
	process = subprocess.run([str(scripts / ("hidden-moves-mcp" + suffix)), "--help"], capture_output=True, text=True, check=True, timeout=10)
	if "--move" not in process.stdout:
		raise ValueError("Installed MCP entry point failed.")
	print("Installed imports, aliases, provider binding, and adapter exports passed.")


def main() -> None:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("directory", type=Path)
	parser.add_argument("--installed", action="store_true")
	args = parser.parse_args()
	check_wheels(args.directory)
	if args.installed:
		smoke_installed()


if __name__ == "__main__":
	main()
