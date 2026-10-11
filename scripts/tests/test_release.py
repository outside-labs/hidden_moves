"""Release routing and artifact isolation prevent accidental package uploads."""

import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_release import PACKAGES, check_distributions, select_release


class ReleaseTests(unittest.TestCase):
    def test_core_tag_keeps_its_existing_environment(self):
        self.assertEqual(select_release("v0.1.0"), {
            "package": "hidden-moves", "package_directory": ".",
            "version": "0.1.0", "environment": "pypi",
        })

    def test_each_package_has_an_exact_version_and_environment(self):
        for name, (directory, suffix, environment) in PACKAGES.items():
            with self.subTest(name=name):
                release = select_release("v0.1.0" + suffix)
                self.assertEqual(release["package"], name)
                self.assertEqual(release["package_directory"], directory)
                self.assertEqual(release["environment"], environment)

    def test_function_tool_tag_uses_its_own_publisher(self):
        release = select_release("v0.1.0-openai")
        self.assertEqual(release["package"], "hidden-moves-openai")
        self.assertEqual(release["environment"], "pypi-openai")

    def test_projects_tag_uses_its_own_publisher(self):
        release = select_release("v0.1.0-github-projects")
        self.assertEqual(release["package"], "hidden-moves-github-projects")
        self.assertEqual(release["environment"], "pypi-github-projects")

    def test_unknown_malformed_and_mismatched_tags_are_rejected(self):
        for tag in ("0.1.0", "v0.1.1", "v0.1.0-unknown", "v0.1.0-mcp-extra", "v0.1.0-mcp\n", "v0.1.0/../mcp"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                select_release(tag)

    def artifacts(self, directory, *, wheel_name="hidden-moves-mcp", source_version="0.1.0"):
        stem = "hidden_moves_mcp-0.1.0"

        def metadata(name, version):
            return f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\nRequires-Python: >=3.11\nLicense-Expression: MIT\n\n".encode()

        with ZipFile(directory / (stem + "-py3-none-any.whl"), "w") as wheel:
            wheel.writestr("hidden_moves_mcp-0.1.0.dist-info/METADATA", metadata(wheel_name, "0.1.0"))
        with tarfile.open(directory / (stem + ".tar.gz"), "w:gz") as source:
            content = metadata("hidden-moves-mcp", source_version)
            member = tarfile.TarInfo(stem + "/PKG-INFO")
            member.size = len(content)
            source.addfile(member, io.BytesIO(content))

    def test_matching_wheel_and_source_distribution_are_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            self.artifacts(directory)
            (directory / ".gitignore").write_text("*\n")
            check_distributions(directory, "v0.1.0-mcp")

    def test_an_extra_or_missing_distribution_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            self.artifacts(directory)
            extra = directory / "hidden_moves-0.1.0-py3-none-any.whl"
            extra.touch()
            with self.assertRaisesRegex(ValueError, "only the selected"):
                check_distributions(directory, "v0.1.0-mcp")
            extra.unlink()
            (directory / "hidden_moves_mcp-0.1.0.tar.gz").unlink()
            with self.assertRaisesRegex(ValueError, "only the selected"):
                check_distributions(directory, "v0.1.0-mcp")

    def test_wheel_metadata_cannot_claim_another_package(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            self.artifacts(directory, wheel_name="hidden-moves")
            with self.assertRaisesRegex(ValueError, "name"):
                check_distributions(directory, "v0.1.0-mcp")

    def test_source_metadata_must_match_the_wheel_version(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            self.artifacts(directory, source_version="0.1.1")
            with self.assertRaisesRegex(ValueError, "version"):
                check_distributions(directory, "v0.1.0-mcp")


if __name__ == "__main__":
    unittest.main()
