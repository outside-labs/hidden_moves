"""Optional target-bound definitions; the factory never resolves an account."""

from hidden_moves import MoveAnnotations, MoveSpec

from .client import ProjectsClient
from .models import FieldPage, ItemPage, OwnerKind, Project, ProjectPage

READ_CAPABILITIES = (
	"github.projects.list", "github.projects.get", "github.projects.fields", "github.projects.items",
)


def list_projects(client: ProjectsClient, owner: str, owner_kind: OwnerKind, cursor: str | None = None, page_size: int = 50) -> ProjectPage:
	"""Read one bounded Project page for an explicit user or organization owner."""
	return client.list(owner, owner_kind, cursor=cursor, page_size=page_size)


def get_project(client: ProjectsClient, owner: str, owner_kind: OwnerKind, number: int) -> Project:
	"""Read one Project by owner identity and Project number."""
	return client.get(owner, owner_kind, number)


def project_fields(client: ProjectsClient, project_id: str, cursor: str | None = None, page_size: int = 50) -> FieldPage:
	"""Read one field-definition page with select options and iteration metadata."""
	return client.fields(project_id, cursor=cursor, page_size=page_size)


def project_items(client: ProjectsClient, project_id: str, cursor: str | None = None, page_size: int = 50, field_page_size: int = 50) -> ItemPage:
	"""Read one item page with nested completeness diagnostics and cursor state."""
	return client.items(project_id, cursor=cursor, page_size=page_size, field_page_size=field_page_size)


def provide_moves() -> tuple[MoveSpec, ...]:
	"""Advertise read operations around an application-configured ProjectsClient."""
	annotations = MoveAnnotations(read_only=True, destructive=False, idempotent=True, external=True)
	return tuple(
		MoveSpec(name=name, namespace="github.projects", func=operation,
			bind_target=True, target_types=(ProjectsClient,), annotations=annotations)
		for name, operation in (
			("list", list_projects), ("get", get_project),
			("fields", project_fields), ("items", project_items),
		)
	)
