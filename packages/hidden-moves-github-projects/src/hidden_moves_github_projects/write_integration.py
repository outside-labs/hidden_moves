"""A separate explicitly bound write provider; no model-supplied approval flag."""

from hidden_moves import MoveAnnotations, MoveSpec

from .writes import ProjectsWriter, WriteOutcomeUnknownError, WriteReceipt

WRITE_CAPABILITIES = ("github.projects.add_item", "github.projects.set_single_select")


def add_item(writer: ProjectsWriter, project_id: str, content_id: str) -> WriteReceipt:
    """Add an existing Issue/PR to an authorized Project and verify its identity."""
    try:
        return writer.add_item(project_id, content_id)
    except WriteOutcomeUnknownError as error:
        return error.receipt


def set_single_select(
    writer: ProjectsWriter,
    project_id: str,
    item_id: str,
    field_name: str,
    option_name: str,
    expected_option_id: str | None,
) -> WriteReceipt:
    """Set a resolved choice after an expected-value check and verify the write."""
    try:
        return writer.set_single_select(
            project_id, item_id, field_name, option_name, expected_option_id
        )
    except WriteOutcomeUnknownError as error:
        return error.receipt


def provide_write_moves() -> tuple[MoveSpec, ...]:
    """Advertise only two writes; the application must configure the bound writer."""
    annotations = MoveAnnotations(
        read_only=False, destructive=True, idempotent=False, external=True
    )
    return tuple(
        MoveSpec(
            name=name,
            namespace="github.projects",
            func=operation,
            bind_target=True,
            target_types=(ProjectsWriter,),
            annotations=annotations,
        )
        for name, operation in (
            ("add_item", add_item),
            ("set_single_select", set_single_select),
        )
    )
