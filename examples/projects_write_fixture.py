"""Run only against an explicitly authorized disposable Project fixture."""

import argparse
import json
from dataclasses import asdict

from hidden_moves_github_projects import ProjectsClient
from hidden_moves_github_projects.host import resolve_gh_token
from hidden_moves_github_projects.writes import ProjectsWriter


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify add-item and single-select writes on an authorized disposable Project."
    )
    parser.add_argument("--project-id", required=True)
    parser.add_argument(
        "--content-id", required=True, help="Existing disposable Issue/PR node ID."
    )
    parser.add_argument("--field-name", required=True)
    args = parser.parse_args()
    reader = ProjectsClient(resolve_gh_token)
    writer = ProjectsWriter(reader, allowed_projects=[args.project_id])
    added = writer.add_item(args.project_id, args.content_id)
    print(json.dumps(asdict(added)), flush=True)
    state = writer.inspect_single_select(
        args.project_id, added.item_id, args.field_name
    )
    options = [
        option for option in state.options if option.id != state.current_option_id
    ]
    if not options:
        raise ValueError("fixture must offer a different single-select choice")
    changed = writer.set_single_select(
        args.project_id,
        added.item_id,
        args.field_name,
        options[0].name,
        state.current_option_id,
    )
    print(json.dumps(asdict(changed)), flush=True)


if __name__ == "__main__":
    main()
