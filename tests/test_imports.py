"""Import the changed surfaces in a fresh process with side effects blocked."""

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class ImportTests(unittest.TestCase):
	def test_imports_do_not_write_change_cwd_run_programs_or_open_network(self):
		source = Path(__file__).resolve().parents[1] / "src"
		script = textwrap.dedent("""\
			import builtins
			import importlib
			import sys
			from unittest.mock import patch

			original_open = builtins.open
			def read_only_open(file, mode="r", *args, **kwargs):
				if any(flag in mode for flag in ("w", "a", "x", "+")):
					raise AssertionError("import attempted a file write")
				return original_open(file, mode, *args, **kwargs)

			with (
				patch("builtins.open", side_effect=read_only_open),
				patch("pathlib.Path.write_text", side_effect=AssertionError("file write")),
				patch("os.chdir", side_effect=AssertionError("changed cwd")),
				patch("subprocess.run", side_effect=AssertionError("ran a program")),
				patch("urllib.request.urlopen", side_effect=AssertionError("opened network")),
			):
				import hidden_moves
				assert "click" not in sys.modules, "core imported Click"
				assert "mcp" not in sys.modules, "core imported an optional adapter SDK"
				for module in (
					"hidden_moves.adapters",
					"hidden_moves.cli",
					"hidden_moves.__main__",
				):
					importlib.import_module(module)
		""")
		with tempfile.TemporaryDirectory() as temporary:
			result = subprocess.run(
				[sys.executable, "-B", "-c", script],
				cwd=temporary,
				env={**os.environ, "PYTHONPATH": str(source)},
				capture_output=True,
				text=True,
				check=False,
			)
		self.assertEqual(result.returncode, 0, result.stderr)
		self.assertEqual(result.stdout, "")
