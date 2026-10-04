"""Explicit bounded live read followed by one local snapshot insertion."""

import argparse
import json

from backpack_store import Backpack
from hidden_moves_github_projects import ProjectsClient
from hidden_moves_github_projects.host import resolve_gh_token
from hidden_moves_github_projects.snapshots import (
    capture_project_item,
    register_snapshot_codec,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture one explicitly selected Project item into a local Backpack store."
    )
    parser.add_argument("--database", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--owner-kind", choices=("user", "organization"), required=True)
    parser.add_argument("--number", type=int, required=True)
    parser.add_argument("--item-id", required=True)
    parser.add_argument("--max-pages", type=int, default=2)
    args = parser.parse_args()
    client = ProjectsClient(resolve_gh_token)
    with Backpack.open(args.database) as store:
        register_snapshot_codec(store)
        written = capture_project_item(
            client,
            store,
            args.owner,
            args.owner_kind,
            args.number,
            args.item_id,
            max_pages=args.max_pages,
            tags=["github", "snapshot"],
        )
    with Backpack.open(args.database) as store:
        register_snapshot_codec(store)
        record = store.get_record(written.id)
        print(
            json.dumps(
                {
                    "local_id": record.id,
                    "type_key": record.type_key,
                    "schema_version": record.schema_version,
                    "source_url": record.provenance.source_url,
                    "project_id": record.value.project.id,
                    "item_id": record.value.item.id,
                    "captured_at": record.value.captured_at,
                    "field_values_complete": record.value.item.field_values_complete,
                    "diagnostics": [d.code for d in record.value.item.diagnostics],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
