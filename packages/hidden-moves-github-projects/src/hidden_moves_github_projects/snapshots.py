"""Optional explicit Projects-to-Backpack snapshots; no synchronization or writes."""

from collections.abc import Iterable
from dataclasses import dataclass

from backpack_store import Backpack, DataclassCodec, Provenance, WriteResult
from backpack_store.records import utc_now, validate_timestamp

from .client import ProjectsClient
from .errors import NotFoundError, ProjectsError
from .models import OwnerKind, Project, ProjectItem

SNAPSHOT_TYPE_KEY = "github.project_item_snapshot"
SNAPSHOT_SCHEMA_VERSION = 1


class SnapshotError(ProjectsError):
    """A supplied snapshot does not match its source Project identity."""


@dataclass(frozen=True)
class ProjectItemSnapshot:
    project: Project
    item: ProjectItem
    captured_at: str

    def __post_init__(self) -> None:
        if type(self.project) is not Project or type(self.item) is not ProjectItem:
            raise SnapshotError(
                "snapshots require normalized Project and ProjectItem DTOs"
            )
        if self.item.project_id != self.project.id:
            raise SnapshotError("the item must belong to the supplied Project")
        validate_timestamp(self.captured_at)


def register_snapshot_codec(store: Backpack) -> None:
    """Register the trusted current DTO codec; choose the database separately."""
    store.register(
        DataclassCodec(
            ProjectItemSnapshot,
            type_key=SNAPSHOT_TYPE_KEY,
            schema_version=SNAPSHOT_SCHEMA_VERSION,
        )
    )


def fetch_project_item(
    client: ProjectsClient,
    owner: str,
    owner_kind: OwnerKind,
    number: int,
    item_id: str,
    *,
    page_size: int = 50,
    field_page_size: int = 50,
    max_pages: int = 10,
) -> tuple[Project, ProjectItem]:
    """Find one explicit item through bounded read pages, preserving diagnostics."""
    if not isinstance(item_id, str) or not item_id or len(item_id) > 256:
        raise ValueError("item_id must be an explicit opaque Project item ID")
    project = client.get(owner, owner_kind, number)
    for page in client.iter_item_pages(
        project.id,
        page_size=page_size,
        field_page_size=field_page_size,
        max_pages=max_pages,
    ):
        for item in page.items:
            if item.id == item_id:
                return project, item
    raise NotFoundError(
        "the requested item is not available in the bounded Project connection"
    )


def store_snapshot(
    store: Backpack,
    project: Project,
    item: ProjectItem,
    *,
    captured_at: str | None = None,
    tags: Iterable[str] = (),
) -> WriteResult:
    """Persist one dated DTO after the application registers its snapshot codec."""
    snapshot = ProjectItemSnapshot(
        project, item, utc_now() if captured_at is None else captured_at
    )
    provenance = Provenance(
        source_url=project.url,
        source_system="github-projects",
        source_id=item.id,
        captured_at=snapshot.captured_at,
    )
    return store.put(snapshot, tags=tags, provenance=provenance)


def capture_project_item(
    client: ProjectsClient,
    store: Backpack,
    owner: str,
    owner_kind: OwnerKind,
    number: int,
    item_id: str,
    *,
    page_size: int = 50,
    field_page_size: int = 50,
    max_pages: int = 10,
    tags: Iterable[str] = (),
) -> WriteResult:
    """Fetch first, then atomically persist; a fetch failure creates no record."""
    project, item = fetch_project_item(
        client,
        owner,
        owner_kind,
        number,
        item_id,
        page_size=page_size,
        field_page_size=field_page_size,
        max_pages=max_pages,
    )
    return store_snapshot(store, project, item, tags=tags)
