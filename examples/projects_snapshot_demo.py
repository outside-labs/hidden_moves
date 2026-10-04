"""Offline Projects-to-Backpack fetch/store/reopen proof with typed DTOs."""

import sys
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from backpack_store import Backpack
from backpack_store.host import build_catalog
from hidden_moves_github_projects import ProjectsClient
from hidden_moves_github_projects.snapshots import (
    ProjectItemSnapshot,
    capture_project_item,
    register_snapshot_codec,
)

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
        / "packages/hidden-moves-github-projects/tests"
    ),
)
from replay import ReplayTransport


def main() -> None:
    client = ProjectsClient("fixture", transport=ReplayTransport())
    with TemporaryDirectory() as directory:
        path = Path(directory) / "snapshots.sqlite"
        with Backpack.open(path) as store:
            register_snapshot_codec(store)
            written = capture_project_item(
                client,
                store,
                "example",
                "organization",
                2,
                "ITEM_issue",
                max_pages=1,
                tags=["snapshot"],
            )
            expected = store.get_record(written.id)
        with Backpack.open(path) as store:
            register_snapshot_codec(store)
            record = store.get_record(written.id)
            assert record == expected and isinstance(record.value, ProjectItemSnapshot)
            assert record.id != record.value.item.id
            assert record.provenance.captured_at == record.value.captured_at
            catalog = build_catalog(store, ["backpack.records.get"])
            view = catalog.invoke("backpack.records.get", {"record_id": written.id})
            assert view.payload["item"] == asdict(record.value.item)
    print(
        "Fetched fixture item; reopened typed snapshot with capture time, source IDs and local UUID; selected catalog agrees."
    )


if __name__ == "__main__":
    main()
