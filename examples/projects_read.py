"""Make a bounded, explicit live read and print only its paging/access summary."""

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime

from hidden_moves_github_projects import ProjectsClient, ProjectsError
from hidden_moves_github_projects.host import resolve_gh_token


def main() -> None:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("owner")
	parser.add_argument("owner_kind", choices=("user", "organization"))
	parser.add_argument("number", type=int)
	parser.add_argument("--page-size", type=int, default=2)
	parser.add_argument("--field-page-size", type=int, default=2)
	args = parser.parse_args()
	client = ProjectsClient(resolve_gh_token, timeout=10)
	try:
		project = client.get(args.owner, args.owner_kind, args.number)
		fields = client.fields(project.id, page_size=100)
		items = client.items(project.id, page_size=args.page_size, field_page_size=args.field_page_size)
	except (ProjectsError, ValueError) as error:
		parser.exit(1, f"{type(error).__name__}: {error}\n")
	print(json.dumps({
		"captured_at": datetime.now(UTC).isoformat(),
		"project_id": project.id, "source_url": project.url,
		"owner_kind": project.owner_kind, "project_number": project.number,
		"field_count_in_page": len(fields.fields), "fields_page": asdict(fields.page_info),
		"item_count_in_page": len(items.items), "items_page": asdict(items.page_info),
		"nested_values_complete": [item.field_values_complete for item in items.items],
		"diagnostic_codes": sorted({hint.code for hint in [*fields.diagnostics, *items.diagnostics]}),
	}, indent=2, allow_nan=False))


if __name__ == "__main__":
	main()
