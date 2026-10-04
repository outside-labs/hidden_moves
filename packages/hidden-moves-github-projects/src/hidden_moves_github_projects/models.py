"""Concrete, transport-neutral records for bounded Projects reads."""

from dataclasses import dataclass, field
from typing import Literal

OwnerKind = Literal["user", "organization"]


@dataclass(frozen=True)
class PageInfo:
	has_next_page: bool
	end_cursor: str | None


@dataclass(frozen=True)
class Diagnostic:
	code: str
	node_id: str | None = None
	graphql_type: str | None = None


@dataclass(frozen=True)
class Project:
	id: str
	number: int
	title: str
	url: str
	owner_login: str
	owner_kind: OwnerKind
	description: str | None
	public: bool
	closed: bool


@dataclass(frozen=True)
class ProjectPage:
	projects: list[Project]
	page_info: PageInfo
	diagnostics: list[Diagnostic] = field(default_factory=list)


@dataclass(frozen=True)
class SelectOption:
	id: str
	name: str


@dataclass(frozen=True)
class Iteration:
	id: str
	title: str
	start_date: str
	duration: int
	completed: bool = False


@dataclass(frozen=True)
class ProjectField:
	id: str | None
	name: str | None
	data_type: str | None
	graphql_type: str
	options: list[SelectOption] = field(default_factory=list)
	iterations: list[Iteration] = field(default_factory=list)


@dataclass(frozen=True)
class FieldPage:
	project_id: str
	fields: list[ProjectField]
	page_info: PageInfo
	diagnostics: list[Diagnostic] = field(default_factory=list)


@dataclass(frozen=True)
class Content:
	kind: str
	id: str | None = None
	title: str | None = None
	url: str | None = None
	number: int | None = None
	repository: str | None = None
	state: str | None = None
	body: str | None = None
	graphql_type: str | None = None


@dataclass(frozen=True)
class FieldValue:
	graphql_type: str
	id: str | None = None
	field_id: str | None = None
	field_name: str | None = None
	text: str | None = None
	number: float | None = None
	date: str | None = None
	option_id: str | None = None
	option_name: str | None = None
	iteration: Iteration | None = None


@dataclass(frozen=True)
class FieldValuePage:
	item_id: str
	values: list[FieldValue]
	page_info: PageInfo
	diagnostics: list[Diagnostic] = field(default_factory=list)


@dataclass(frozen=True)
class ProjectItem:
	id: str
	project_id: str
	item_type: str
	archived: bool
	created_at: str
	updated_at: str
	content: Content
	field_values: list[FieldValue]
	field_values_page: PageInfo
	field_values_complete: bool
	diagnostics: list[Diagnostic] = field(default_factory=list)


@dataclass(frozen=True)
class ItemPage:
	project_id: str
	items: list[ProjectItem]
	page_info: PageInfo
	diagnostics: list[Diagnostic] = field(default_factory=list)
