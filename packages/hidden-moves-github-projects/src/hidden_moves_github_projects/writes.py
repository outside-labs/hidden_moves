"""Two fixed mutations, guarded by trusted local Project authorization."""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Literal

from . import _normalize as normalize
from .client import ProjectsClient, _count, _text
from .errors import CredentialError, PaginationLimitError, ProjectsError, ProtocolError
from .models import ProjectField, SelectOption

CONTENT_QUERY = """query WritableContent($id: ID!) {
  node(id: $id) { __typename id }
}"""
MEMBERSHIP_QUERY = """query ProjectItemMembership($id: ID!) {
  node(id: $id) { __typename ... on ProjectV2Item {
    id project { id } content { __typename ... on Issue { id } ... on PullRequest { id } }
  } }
}"""
SELECTION_QUERY = """query SingleSelectValue($id: ID!, $name: String!) {
  node(id: $id) { __typename ... on ProjectV2Item {
    id project { id } fieldValueByName(name: $name) {
      __typename ... on ProjectV2ItemFieldSingleSelectValue {
        optionId field { ... on ProjectV2SingleSelectField { id } }
      }
    }
  } }
}"""
ADD_MUTATION = """mutation AddProjectItem($project: ID!, $content: ID!) {
  addProjectV2ItemById(input: {projectId: $project, contentId: $content}) { item { id } }
}"""
SET_MUTATION = """mutation SetSingleSelect($project: ID!, $item: ID!, $field: ID!, $option: String!) {
  updateProjectV2ItemFieldValue(input: {projectId: $project, itemId: $item, fieldId: $field,
    value: {singleSelectOptionId: $option}}) { projectV2Item { id } }
}"""


class ProjectAuthorizationError(ProjectsError):
    """The configured allowlist, content type or item membership denies the write."""


class SelectionConflictError(ProjectsError):
    """The single-select value changed before the preflight check."""


@dataclass(frozen=True)
class WriteReceipt:
    operation: Literal["add_item", "set_single_select"]
    project_id: str
    item_id: str | None
    content_id: str | None
    field_id: str | None
    option_id: str | None
    verified: bool
    acknowledged: bool = False
    diagnostic: str | None = None


@dataclass(frozen=True)
class SingleSelectState:
    project_id: str
    item_id: str
    field_id: str
    current_option_id: str | None
    options: list[SelectOption]


class WriteOutcomeUnknownError(ProjectsError):
    """A submitted mutation may have taken effect; inspect before any retry."""

    def __init__(self, receipt: WriteReceipt, *, acknowledged: bool, cause_type: str):
        self.receipt = replace(
            receipt, acknowledged=acknowledged, diagnostic=cause_type
        )
        self.acknowledged = acknowledged
        self.cause_type = cause_type
        super().__init__(
            "mutation outcome is unverified; inspect the Project before retrying"
        )


class PostWriteVerificationError(WriteOutcomeUnknownError):
    """GitHub acknowledged the mutation but its post-write read did not verify it."""


def _opaque(value: str, label: str) -> str:
    value = _text(value, label)
    if len(value) > 1024 or any(char.isspace() for char in value):
        raise ValueError(f"{label} must be a bounded opaque ID")
    return value


class ProjectsWriter:
    """Trusted configuration authorizes Projects; tool input cannot add permission."""

    def __init__(
        self,
        reader: ProjectsClient,
        *,
        allowed_projects: Iterable[str],
        max_field_pages: int = 5,
    ):
        if not isinstance(reader, ProjectsClient):
            raise TypeError("reader must be an explicitly configured ProjectsClient")
        if isinstance(allowed_projects, (str, bytes)):
            raise ValueError("allowed_projects must be an explicit collection of IDs")
        projects = set()
        for index, project_id in enumerate(allowed_projects):
            if index >= 64:
                raise ValueError("authorize at most 64 Projects per local writer")
            projects.add(_opaque(project_id, "project_id"))
        if not projects:
            raise ValueError("authorize at least one explicit Project")
        self._reader = reader
        self._allowed_projects = frozenset(projects)
        self._max_field_pages = _count(max_field_pages, "max_field_pages", 100)

    def __repr__(self) -> str:
        return "ProjectsWriter()"

    def _authorize(self, project_id: str) -> None:
        _opaque(project_id, "project_id")
        if project_id not in self._allowed_projects:
            raise ProjectAuthorizationError(
                "Project is outside the configured write allowlist"
            )

    def _member(self, node: dict, project_id: str, item_id: str) -> None:
        if (
            normalize.text(node.get("id")) != item_id
            or normalize.text(normalize.obj(node.get("project")).get("id"))
            != project_id
        ):
            raise ProjectAuthorizationError(
                "item does not belong to the authorized Project"
            )

    def _field(self, project_id: str, name: str) -> ProjectField:
        _text(name, "field_name")
        found, cursor, seen = [], None, set()
        for _ in range(self._max_field_pages):
            page = self._reader.fields(project_id, cursor=cursor, page_size=100)
            found.extend(field for field in page.fields if field.name == name)
            if not page.page_info.has_next_page:
                break
            cursor = page.page_info.end_cursor
            if cursor in seen:
                raise ProtocolError("GitHub repeated a field-definition cursor")
            seen.add(cursor)
        else:
            raise PaginationLimitError(
                "field-definition budget ended before the connection"
            )
        if (
            len(found) != 1
            or found[0].graphql_type != "ProjectV2SingleSelectField"
            or found[0].id is None
        ):
            raise ValueError(
                "field_name must identify one accessible single-select field"
            )
        _opaque(found[0].id, "field_id")
        return found[0]

    def _selection(
        self, project_id: str, item_id: str, field: ProjectField
    ) -> str | None:
        data = self._reader._execute(
            SELECTION_QUERY, {"id": item_id, "name": field.name}
        )
        node = normalize.node(data, "ProjectV2Item")
        self._member(node, project_id, item_id)
        value = node.get("fieldValueByName")
        if value is None:
            return None
        value = normalize.obj(value)
        if (
            value.get("__typename") != "ProjectV2ItemFieldSingleSelectValue"
            or normalize.obj(value.get("field")).get("id") != field.id
        ):
            raise ProtocolError(
                "single-select lookup returned a different field or value type"
            )
        return _opaque(normalize.text(value.get("optionId")), "option_id")

    def inspect_single_select(
        self, project_id: str, item_id: str, field_name: str
    ) -> SingleSelectState:
        """Read the authorized item value and dynamically resolved choices."""
        self._authorize(project_id)
        _opaque(item_id, "item_id")
        field = self._field(project_id, field_name)
        return SingleSelectState(
            project_id,
            item_id,
            field.id,
            self._selection(project_id, item_id, field),
            field.options,
        )

    def _mutate(self, query: str, variables: dict, receipt: WriteReceipt) -> dict:
        try:
            return self._reader._execute(query, variables)
        except CredentialError:
            raise
        except ProjectsError as error:
            # Never retry automatically: transport/GraphQL errors can follow a completed effect.
            raise WriteOutcomeUnknownError(
                receipt, acknowledged=False, cause_type=type(error).__name__
            ) from None

    def add_item(self, project_id: str, content_id: str) -> WriteReceipt:
        """Add one existing Issue/PR and verify returned identity and membership."""
        self._authorize(project_id)
        _opaque(content_id, "content_id")
        self._reader.fields(
            project_id, page_size=1
        )  # also verifies Project read access/type
        content = normalize.obj(
            self._reader._execute(CONTENT_QUERY, {"id": content_id}).get("node")
        )
        if (
            content.get("__typename") not in ("Issue", "PullRequest")
            or content.get("id") != content_id
        ):
            raise ProjectAuthorizationError(
                "content must be an accessible existing Issue or PullRequest"
            )
        receipt = WriteReceipt(
            "add_item", project_id, None, content_id, None, None, False
        )
        data = self._mutate(
            ADD_MUTATION, {"project": project_id, "content": content_id}, receipt
        )
        try:
            item_id = _opaque(
                normalize.text(
                    normalize.obj(
                        normalize.obj(data.get("addProjectV2ItemById")).get("item")
                    ).get("id")
                ),
                "item_id",
            )
        except (ProjectsError, ValueError) as error:
            raise WriteOutcomeUnknownError(
                receipt, acknowledged=False, cause_type=type(error).__name__
            ) from None
        receipt = replace(receipt, item_id=item_id, acknowledged=True)
        try:
            node = normalize.node(
                self._reader._execute(MEMBERSHIP_QUERY, {"id": item_id}),
                "ProjectV2Item",
            )
            self._member(node, project_id, item_id)
            if normalize.obj(node.get("content")).get("id") != content_id:
                raise ProtocolError(
                    "added item content did not match the supplied identity"
                )
        except (ProjectsError, ValueError) as error:
            raise PostWriteVerificationError(
                receipt, acknowledged=True, cause_type=type(error).__name__
            ) from None
        return replace(receipt, verified=True, acknowledged=True)

    def set_single_select(
        self,
        project_id: str,
        item_id: str,
        field_name: str,
        option_name: str,
        expected_option_id: str | None,
    ) -> WriteReceipt:
        """Check the expected value, set a dynamically resolved option, then verify."""
        self._authorize(project_id)
        _opaque(item_id, "item_id")
        _text(option_name, "option_name")
        if expected_option_id is not None:
            _opaque(expected_option_id, "expected_option_id")
        field = self._field(project_id, field_name)
        options = [option for option in field.options if option.name == option_name]
        if len(options) != 1:
            raise ValueError(
                "option_name must identify one choice on the resolved field"
            )
        option_id = _opaque(options[0].id, "option_id")
        if self._selection(project_id, item_id, field) != expected_option_id:
            raise SelectionConflictError(
                "single-select value differs from the caller's expected option"
            )
        receipt = WriteReceipt(
            "set_single_select", project_id, item_id, None, field.id, option_id, False
        )
        data = self._mutate(
            SET_MUTATION,
            {
                "project": project_id,
                "item": item_id,
                "field": field.id,
                "option": option_id,
            },
            receipt,
        )
        try:
            returned = normalize.obj(
                normalize.obj(data.get("updateProjectV2ItemFieldValue")).get(
                    "projectV2Item"
                )
            )
            if returned.get("id") != item_id:
                raise ProtocolError(
                    "mutation response did not identify the requested item"
                )
        except (ProjectsError, ValueError) as error:
            raise WriteOutcomeUnknownError(
                receipt, acknowledged=False, cause_type=type(error).__name__
            ) from None
        receipt = replace(receipt, acknowledged=True)
        try:
            if self._selection(project_id, item_id, field) != option_id:
                raise ProtocolError(
                    "single-select post-write value did not match the requested choice"
                )
        except (ProjectsError, ValueError) as error:
            raise PostWriteVerificationError(
                receipt, acknowledged=True, cause_type=type(error).__name__
            ) from None
        return replace(receipt, verified=True, acknowledged=True)
