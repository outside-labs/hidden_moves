"""Observable context, continuation, resource bounds, and path failures."""

import hashlib
import os
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from hidden_moves_workspace import (
    ContentError,
    PathAccessError,
    StaleContentError,
    Workspace,
)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "src").mkdir()
        self.text = "first\r\ncafé target target\r\nthird\r\ntarget last\r\n"
        (self.root / "src/demo.py").write_bytes(self.text.encode("utf-8"))
        (self.root / "empty.txt").write_bytes(b"")
        self.workspace = Workspace(self.root, ["src/demo.py", "empty.txt", "missing.txt"])

    def test_selection_is_sorted_deduplicated_and_paginated_without_content_reads(self):
        with patch("os.open", side_effect=AssertionError("content opened")):
            workspace = Workspace(self.root, ["src/demo.py", "empty.txt", "src/demo.py"])
            first = workspace.files(limit=1)
            second = workspace.files(offset=first.next_offset, limit=1)
        self.assertEqual(first.paths, ["empty.txt"])
        self.assertEqual(second.paths, ["src/demo.py"])
        self.assertIsNone(second.next_offset)
        self.assertEqual(self.workspace.files().paths, ["empty.txt", "missing.txt", "src/demo.py"])
        self.assertEqual(Workspace(self.root, []).files().paths, [])

    def test_numbered_excerpts_and_continuation_preserve_unicode_and_digest(self):
        first = self.workspace.read("src/demo.py", line_count=2)
        self.assertEqual(first.sha256, hashlib.sha256(self.text.encode()).hexdigest())
        self.assertEqual(first.total_lines, 4)
        self.assertEqual([asdict(line) for line in first.lines], [
            {"number": 1, "column": 1, "text": "first"},
            {"number": 2, "column": 1, "text": "café target target"},
        ])
        second = self.workspace.read(
            first.path, start_line=first.next_line, start_column=first.next_column,
            expected_sha256=first.sha256,
        )
        self.assertEqual([line.number for line in second.lines], [3, 4])
        self.assertIsNone(second.next_line)
        self.assertIsNone(second.next_column)
        self.assertEqual(self.workspace.read("empty.txt").lines, [])
        self.assertEqual(self.workspace.read("src/demo.py", start_line=5).lines, [])

    def test_long_lines_are_bounded_and_can_be_reassembled(self):
        text = "λ" * 40_000
        (self.root / "long.txt").write_bytes((text + "\nend").encode())
        workspace = Workspace(self.root, ["long.txt"])
        fragments = []
        page = workspace.read("long.txt", line_count=1)
        while True:
            self.assertLessEqual(sum(len(line.text) for line in page.lines), 16_384)
            fragments.extend(page.lines)
            if page.next_line is None:
                break
            page = workspace.read(
                "long.txt", page.next_line, 1, page.next_column, page.sha256,
            )
        self.assertEqual("".join(line.text for line in fragments if line.number == 1), text)
        self.assertEqual(fragments[-1].text, "end")
        self.assertEqual([line.column for line in fragments[:3]], [1, 16_385, 32_769])

    def test_line_limit_is_independent_of_character_limit(self):
        (self.root / "blank.txt").write_bytes(b"\n" * 401)
        workspace = Workspace(self.root, ["blank.txt"])
        page = workspace.read("blank.txt", line_count=200)
        self.assertEqual(len(page.lines), 200)
        self.assertEqual(page.next_line, 201)

    def test_literal_search_returns_first_match_per_line_and_exact_continuation(self):
        first = self.workspace.search("src/demo.py", "target", max_matches=1)
        self.assertEqual([match.line for match in first.matches], [2])
        self.assertEqual(first.matches[0].column, 6)
        self.assertEqual(first.next_line, 4)
        second = self.workspace.search(
            first.path, "target", start_line=first.next_line, expected_sha256=first.sha256,
        )
        self.assertEqual([match.line for match in second.matches], [4])
        self.assertIsNone(second.next_line)
        self.assertEqual(self.workspace.search(first.path, "TARGET").matches, [])
        self.assertEqual(self.workspace.search(first.path, ".*").matches, [])
        self.assertEqual(self.workspace.search("empty.txt", "x").matches, [])

    def test_search_previews_are_bounded_and_keep_the_match(self):
        query = "q" * 256
        (self.root / "large.txt").write_text("x" * 40_000 + query + "z" * 500, encoding="utf-8")
        result = Workspace(self.root, ["large.txt"]).search("large.txt", query)
        match, = result.matches
        self.assertLessEqual(len(match.preview), 320)
        self.assertIn(query, match.preview)
        self.assertEqual(match.column, 40_001)
        self.assertEqual(match.preview_column, 39_969)

    def test_changed_content_is_detected_on_both_continuation_paths(self):
        digest = self.workspace.read("src/demo.py").sha256
        (self.root / "src/demo.py").write_text("new content", encoding="utf-8")
        for operation in (
            lambda: self.workspace.read("src/demo.py", expected_sha256=digest),
            lambda: self.workspace.search("src/demo.py", "content", expected_sha256=digest),
        ):
            with self.subTest(operation=operation), self.assertRaises(StaleContentError):
                operation()
        self.assertNotEqual(digest, self.workspace.read("src/demo.py").sha256)

    def test_invalid_positions_queries_and_budgets_fail_before_reading(self):
        with patch("os.open", side_effect=AssertionError("content opened")):
            for arguments in ({"line_count": 201}, {"start_line": 0}, {"start_column": True}, {"line_count": 1.5}):
                with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                    self.workspace.read("src/demo.py", **arguments)
            for query in ("", "x" * 257, "a\nb", "\x00", 1):
                with self.subTest(query=query), self.assertRaises(ValueError):
                    self.workspace.search("src/demo.py", query)
            with self.assertRaises(ValueError):
                self.workspace.search("src/demo.py", "x", max_matches=101)
            with self.assertRaises(ValueError):
                self.workspace.read("src/demo.py", expected_sha256="invalid")
        for arguments in ({"start_line": 6}, {"start_line": 5, "start_column": 2}, {"start_column": 99}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                self.workspace.read("src/demo.py", **arguments)
        with self.assertRaises(ValueError):
            self.workspace.search("src/demo.py", "x", start_line=6)
        for arguments in ({"limit": 201}, {"offset": -1}, {"offset": 4}, {"limit": True}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                self.workspace.files(**arguments)

    def test_paths_must_be_selected_portable_relative_spellings(self):
        for path in ("../outside", "/etc/passwd", "src/../empty.txt", "src//demo.py", "./empty.txt", "C:/demo.py", "src\\demo.py", "bad\x00", "bad\nname", "empty.txt.", ""):
            with self.subTest(path=path), self.assertRaises(PathAccessError):
                Workspace(self.root, [path])
        for path in ("unselected.txt", "../outside", "missing.txt", None):
            with self.subTest(path=path), self.assertRaises(PathAccessError) as context:
                self.workspace.read(path)
            self.assertNotIn(str(self.root), str(context.exception))

    def test_symlink_files_and_directories_are_rejected_even_inside_the_root(self):
        try:
            (self.root / "alias.txt").symlink_to(self.root / "src/demo.py")
            (self.root / "alias-dir").symlink_to(self.root / "src", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks are unavailable for this account.")
        workspace = Workspace(self.root, ["alias.txt", "alias-dir/demo.py"])
        for path in workspace.files().paths:
            with self.subTest(path=path), self.assertRaises(PathAccessError):
                workspace.read(path)

    def test_a_file_replaced_by_an_outside_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / "private.txt"
            external.write_text("private-marker", encoding="utf-8")
            selected = self.root / "src/demo.py"
            selected.unlink()
            try:
                selected.symlink_to(external)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks are unavailable for this account.")
            with self.assertRaises(PathAccessError) as context:
                self.workspace.read("src/demo.py")
            self.assertNotIn("private-marker", str(context.exception))

    def test_directories_and_fifos_are_rejected_without_blocking(self):
        with self.assertRaises(PathAccessError):
            Workspace(self.root, ["src"]).read("src")
        if hasattr(os, "mkfifo"):
            os.mkfifo(self.root / "fifo")
            with self.assertRaises(PathAccessError):
                Workspace(self.root, ["fifo"]).read("fifo")

    def test_content_limits_encoding_and_nuls_are_explicit(self):
        for data in (b"\xff", b"a\x00b"):
            (self.root / "binary").write_bytes(data)
            with self.subTest(data=data), self.assertRaises(ContentError):
                Workspace(self.root, ["binary"]).read("binary")
        (self.root / "sized").write_bytes(b"12345")
        self.assertEqual(Workspace(self.root, ["sized"], max_file_bytes=5).read("sized").lines[0].text, "12345")
        with self.assertRaises(ContentError):
            Workspace(self.root, ["sized"], max_file_bytes=4).search("sized", "1")

    def test_configuration_errors_do_not_echo_host_paths(self):
        for root in (self.root / "absent", self.root / "empty.txt", None):
            with self.subTest(root=root), self.assertRaises(PathAccessError) as context:
                Workspace(root, [])
            self.assertNotIn(str(self.root), str(context.exception))
        for budget in (0, True, 1_048_577):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                Workspace(self.root, [], max_file_bytes=budget)
        with self.assertRaises(TypeError):
            Workspace(self.root, "empty.txt")
        with self.assertRaises(ValueError):
            Workspace(self.root, ["empty.txt"] * 513)
