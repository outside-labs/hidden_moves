"""Select and verify exactly one distribution for a published release tag."""

import argparse
import tarfile
import tomllib
from email.parser import BytesParser
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = {
    "hidden-moves": (".", "", "pypi"),
    "hidden-moves-mcp": ("packages/hidden-moves-mcp", "-mcp", "pypi-mcp"),
    "hidden-moves-openai": ("packages/hidden-moves-openai", "-openai", "pypi-openai"),
}


def select_release(tag: str) -> dict[str, str]:
    for name, (directory, suffix, environment) in PACKAGES.items():
        project = tomllib.loads((ROOT / directory / "pyproject.toml").read_text())["project"]
        if project["name"] != name:
            raise ValueError(f"Unexpected project name in {directory}.")
        if tag == "v" + project["version"] + suffix:
            return {
                "package": name,
                "package_directory": directory,
                "version": project["version"],
                "environment": environment,
            }
    raise ValueError("Release tag must match a configured package version and suffix.")


def check_distributions(directory: Path, tag: str) -> None:
    release = select_release(tag)
    stem = release["package"].replace("-", "_") + "-" + release["version"]
    expected = {stem + "-py3-none-any.whl", stem + ".tar.gz"}
    if {path.name for path in directory.iterdir() if path.name != ".gitignore"} != expected:
        raise ValueError("Release artifacts must contain only the selected wheel and source distribution.")
    with ZipFile(directory / (stem + "-py3-none-any.whl")) as wheel:
        metadata_path, = [name for name in wheel.namelist() if name.endswith(".dist-info/METADATA")]
        wheel_metadata = wheel.read(metadata_path)
    with tarfile.open(directory / (stem + ".tar.gz")) as source:
        metadata_file = source.extractfile(stem + "/PKG-INFO")
        if metadata_file is None:
            raise ValueError("Source distribution metadata is missing.")
        with metadata_file:
            source_metadata = metadata_file.read()
    for content in (wheel_metadata, source_metadata):
        metadata = BytesParser().parsebytes(content)
        if metadata["Name"].replace("_", "-").lower() != release["package"]:
            raise ValueError("Distribution name does not match the release.")
        if metadata["Version"] != release["version"]:
            raise ValueError("Distribution version does not match the release.")
        if metadata["Requires-Python"] != ">=3.11" or metadata["License-Expression"] != "MIT":
            raise ValueError("Distribution Python or license metadata does not match the release contract.")
    print(f"Verified wheel and source distribution for {release['package']} {release['version']}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output", type=Path, help="Append package selection to a GitHub Actions output file.")
    parser.add_argument("--check", type=Path, help="Verify the selected release artifact directory.")
    args = parser.parse_args()
    release = select_release(args.tag)
    output = "".join(f"{key}={value}\n" for key, value in release.items())
    if args.output:
        with args.output.open("a", encoding="utf-8") as destination:
            destination.write(output)
    print(output, end="")
    if args.check:
        check_distributions(args.check, args.tag)


if __name__ == "__main__":
    main()
