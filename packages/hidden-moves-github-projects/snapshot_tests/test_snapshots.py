"""Offline bridge tests using the same normalized Projects transport fixtures."""

import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from dataclasses import asdict, replace
from pathlib import Path

from backpack_store import Backpack, StorageError
from backpack_store.host import build_catalog
from hidden_moves_github_projects import NotFoundError, ProjectsClient, TransportError
from hidden_moves_github_projects.snapshots import (
    SNAPSHOT_TYPE_KEY,
    ProjectItemSnapshot,
    SnapshotError,
    capture_project_item,
    fetch_project_item,
    register_snapshot_codec,
    store_snapshot,
)

sys.path.insert(0, str(Path(__file__).parents[1] / "tests"))
from replay import ReplayTransport


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "snapshots.sqlite"
        self.store = Backpack.open(self.path)
        self.addCleanup(self.store.close)
        register_snapshot_codec(self.store)
        self.transport = ReplayTransport()
        self.client = ProjectsClient(
            "synthetic-private-token", transport=self.transport
        )

    def test_fetch_store_reopen_preserves_normalized_dtos_and_source_identity(self):
        expected_project, expected_item = fetch_project_item(
            self.client, "example", "organization", 2, "ITEM_issue", max_pages=1
        )
        written = capture_project_item(
            self.client,
            self.store,
            "example",
            "organization",
            2,
            "ITEM_issue",
            max_pages=1,
            tags=["snapshot"],
        )
        before = self.store.get_record(written.id)
        self.assertNotEqual(written.id, expected_item.id)
        self.assertEqual(before.type_key, SNAPSHOT_TYPE_KEY)
        self.assertEqual(before.schema_version, 1)
        self.assertEqual(before.provenance.source_url, expected_project.url)
        self.assertEqual(before.provenance.source_id, expected_item.id)
        self.assertEqual(before.provenance.captured_at, before.value.captured_at)
        self.assertNotIn("synthetic-private-token", json.dumps(before.payload))
        self.assertTrue(
            all(
                request[0]["query"].lstrip().startswith("query ")
                for request in self.transport.requests
            )
        )
        self.store.close()
        with Backpack.open(self.path) as reopened:
            register_snapshot_codec(reopened)
            actual = reopened.get_record(written.id)
            self.assertEqual(actual, before)
            self.assertIs(type(actual.value), ProjectItemSnapshot)
            self.assertEqual(actual.value.project, expected_project)
            self.assertEqual(actual.value.item, expected_item)
            self.assertIs(type(actual.value.item.content), type(expected_item.content))
            catalog = build_catalog(reopened, ["backpack.records.get"])
            result = catalog.invoke("backpack.records.get", {"record_id": written.id})
            self.assertEqual(result.payload["item"], asdict(expected_item))
            self.assertEqual(
                reopened.find(ProjectItemSnapshot, tags=["snapshot"]).records, (actual,)
            )

    def test_separate_fetch_and_store_preserve_partial_and_redacted_diagnostics(self):
        project, item = fetch_project_item(
            self.client, "example", "organization", 2, "ITEM_redacted", max_pages=1
        )
        written = store_snapshot(
            self.store, project, item, captured_at="2026-10-04T00:00:00.000000Z"
        )
        snapshot = self.store.get(written.id)
        self.assertEqual(snapshot.item.content.kind, "redacted")
        self.assertEqual(snapshot.item.diagnostics, item.diagnostics)
        self.assertEqual(
            snapshot.item.field_values_complete, item.field_values_complete
        )
        self.assertEqual(snapshot.captured_at, "2026-10-04T00:00:00.000000Z")

    def test_failed_fetch_missing_item_and_mismatched_project_leave_no_record(self):
        with self.assertRaises(NotFoundError):
            capture_project_item(
                self.client,
                self.store,
                "example",
                "organization",
                2,
                "ITEM_missing",
                max_pages=1,
            )

        def fail_transport(*args, **kwargs):
            raise OSError("private credential marker")

        with self.assertRaises(TransportError):
            capture_project_item(
                ProjectsClient("fixture", transport=fail_transport),
                self.store,
                "example",
                "organization",
                2,
                "ITEM_issue",
            )
        project, item = fetch_project_item(
            self.client, "example", "organization", 2, "ITEM_issue", max_pages=1
        )
        with self.assertRaises(SnapshotError):
            store_snapshot(self.store, project, replace(item, project_id="PVT_other"))
        self.assertEqual(self.store.find(ProjectItemSnapshot).records, ())

    def test_failed_write_rolls_back_the_capture(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "CREATE TRIGGER fail_tag BEFORE INSERT ON tags BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END"
            )
        with self.assertRaises(StorageError):
            capture_project_item(
                self.client,
                self.store,
                "example",
                "organization",
                2,
                "ITEM_issue",
                max_pages=1,
                tags=["fail"],
            )
        self.assertEqual(self.store.find(ProjectItemSnapshot).records, ())


if __name__ == "__main__":
    unittest.main()
