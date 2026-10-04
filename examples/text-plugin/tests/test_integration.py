"""An installed example exercises real package metadata and ordinary imports."""

import json
import subprocess
import sys
import unittest

from click.testing import CliRunner
from hidden_moves_example_text import prefix_text, repeat_text

from hidden_moves import Moves, ProviderLoadError, discover_providers, load_provider
from hidden_moves.adapters import CapabilityCatalog
from hidden_moves.cli import main


class ExampleProviderTests(unittest.TestCase):
	def entry(self):
		return next(entry for entry in discover_providers() if entry.name == "example-text")

	def test_ordinary_import_does_not_require_or_import_the_registry(self):
		script = '''
import builtins
import sys
original = builtins.__import__
def independent(name, *args, **kwargs):
    if name == "hidden_moves" or name.startswith("hidden_moves."):
        raise AssertionError("ordinary helper imported the registry")
    return original(name, *args, **kwargs)
builtins.__import__ = independent
from hidden_moves_example_text import prefix_text, repeat_text
assert repeat_text("hello", 2, separator="/") == "hello/hello"
assert prefix_text("demo: ", "hello") == "demo: hello"
assert "hidden_moves" not in sys.modules
'''
		result = subprocess.run([sys.executable, "-I", "-B", "-c", script], capture_output=True, text=True, check=False)
		self.assertEqual(result.returncode, 0, result.stderr)

	def test_real_metadata_discovery_does_not_import_the_integration(self):
		script = '''
import sys
from hidden_moves import discover_providers
assert any(entry.name == "example-text" for entry in discover_providers())
assert "hidden_moves_example_text.integration" not in sys.modules
'''
		result = subprocess.run([sys.executable, "-I", "-B", "-c", script], capture_output=True, text=True, check=False)
		self.assertEqual(result.returncode, 0, result.stderr)

	def test_explicit_loading_and_catalog_agree_with_the_independent_function(self):
		moves = Moves()
		self.assertFalse(moves.knows("example.text.repeat"))
		load_provider(self.entry(), moves.registry)
		catalog = CapabilityCatalog(moves, ["example.text.repeat"])
		for count in (0, 1, 3):
			arguments = {"value": "héllo", "count": count, "separator": "/"}
			self.assertEqual(catalog.invoke("example.text.repeat", arguments), repeat_text(**arguments))
		self.assertEqual(catalog.describe("example.text.repeat").source, self.entry().value)
		with self.assertRaises(ProviderLoadError):
			load_provider(self.entry(), moves.registry)
		self.assertEqual(len(moves.moves()), 2)
		self.assertEqual(moves.example.text.repeat("hello"), "hello hello")

	def test_real_provider_cli_activation_is_scoped_to_one_invocation(self):
		runner = CliRunner()
		result = runner.invoke(main, ["--plugin", "example-text", "moves", "call", "example.text.repeat", "--arguments", '{"value": "hello", "count": 3}'])
		self.assertEqual(result.exit_code, 0, result.output)
		self.assertEqual(json.loads(result.output), "hello hello hello")
		unloaded = runner.invoke(main, ["moves", "show", "example.text.repeat"])
		self.assertNotEqual(unloaded.exit_code, 0)

	def test_installed_provider_binds_independent_targets_without_exposing_them(self):
		unbound = Moves()
		load_provider(self.entry(), unbound.registry)
		definition = unbound.describe("example.text.prefix")
		self.assertFalse(definition.available)
		self.assertEqual(definition.input_schema["required"], ("value",))
		for prefix in ("first: ", "second: "):
			moves = Moves(prefix, registry=unbound.registry)
			catalog = CapabilityCatalog(moves, ["example.text.prefix"])
			self.assertEqual(catalog.invoke("example.text.prefix", {"value": "hello"}), prefix_text(prefix, "hello"))
			self.assertNotIn(prefix, json.dumps(catalog.describe("example.text.prefix").to_dict()))
