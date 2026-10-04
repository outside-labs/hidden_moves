"""Normalize only queried fields and retain diagnostics for unavailable data."""

import math
from typing import Any

from .errors import NotFoundError, ProtocolError
from .models import (
	Content,
	Diagnostic,
	FieldValue,
	FieldValuePage,
	Iteration,
	PageInfo,
	Project,
	ProjectField,
	ProjectItem,
	SelectOption,
)


def obj(value: Any) -> dict:
	if not isinstance(value, dict):
		raise ProtocolError("GitHub returned an invalid object.")
	return value


def text(value: Any, *, nullable: bool = False) -> str | None:
	if nullable and value is None:
		return None
	if not isinstance(value, str):
		raise ProtocolError("GitHub returned an invalid text field.")
	return value


def integer(value: Any) -> int:
	if type(value) is not int:
		raise ProtocolError("GitHub returned an invalid integer field.")
	return value


def boolean(value: Any) -> bool:
	if type(value) is not bool:
		raise ProtocolError("GitHub returned an invalid boolean field.")
	return value


def identity(value: Any) -> str:
	value = text(value)
	if not value:
		raise ProtocolError("GitHub returned an invalid node identity.")
	return value


def sequence(value: Any) -> list:
	if not isinstance(value, list):
		raise ProtocolError("GitHub returned an invalid list.")
	return value


def connection(value: Any) -> tuple[list, PageInfo]:
	value = obj(value)
	page = obj(value.get("pageInfo"))
	info = PageInfo(boolean(page.get("hasNextPage")), text(page.get("endCursor"), nullable=True))
	if info.has_next_page and not info.end_cursor:
		raise ProtocolError("GitHub omitted the next-page cursor.")
	return sequence(value.get("nodes")), info


def node(data: dict, expected: str) -> dict:
	value = data.get("node")
	if value is None:
		raise NotFoundError("The requested node is absent or inaccessible.")
	value = obj(value)
	if value.get("__typename") != expected:
		raise NotFoundError("The requested node has a different resource type.")
	return value


def project(value: dict) -> Project:
	value = obj(value)
	owner = obj(value.get("owner"))
	kinds = {"User": "user", "Organization": "organization"}
	kind = kinds.get(owner.get("__typename"))
	if kind is None:
		raise ProtocolError("GitHub returned an unsupported project owner.")
	return Project(
		identity(value.get("id")), integer(value.get("number")), text(value.get("title")),
		text(value.get("url")), identity(owner.get("login")), kind,
		text(value.get("shortDescription"), nullable=True), boolean(value.get("public")),
		boolean(value.get("closed")),
	)


def iteration(value: dict, *, completed: bool = False) -> Iteration:
	value = obj(value)
	return Iteration(
		identity(value.get("id")), text(value.get("title")), text(value.get("startDate")),
		integer(value.get("duration")), completed,
	)


def project_field(value: dict | None) -> tuple[ProjectField, list[Diagnostic]]:
	if value is None:
		return ProjectField(None, None, None, "Unavailable"), [Diagnostic("unavailable_field")]
	value = obj(value)
	typename = text(value.get("__typename"))
	field = ProjectField(
		text(value.get("id"), nullable=True), text(value.get("name"), nullable=True),
		text(value.get("dataType"), nullable=True), typename,
	)
	if typename not in {"ProjectV2Field", "ProjectV2SingleSelectField", "ProjectV2IterationField"}:
		return field, [Diagnostic("unsupported_field_type", field.id, typename)]
	identity(field.id)
	text(field.name)
	text(field.data_type)
	if typename == "ProjectV2SingleSelectField":
		field.options.extend(SelectOption(identity(obj(option).get("id")), text(option.get("name"))) for option in sequence(value.get("options")))
	if typename == "ProjectV2IterationField":
		config = obj(value.get("configuration"))
		field.iterations.extend(iteration(item) for item in sequence(config.get("iterations")))
		field.iterations.extend(iteration(item, completed=True) for item in sequence(config.get("completedIterations")))
	return field, []


def field_values(item_id: str, value: dict) -> FieldValuePage:
	nodes, page = connection(value)
	values, diagnostics = [], []
	supported = {
		"ProjectV2ItemFieldTextValue", "ProjectV2ItemFieldNumberValue", "ProjectV2ItemFieldDateValue",
		"ProjectV2ItemFieldSingleSelectValue", "ProjectV2ItemFieldIterationValue",
	}
	for entry in nodes:
		if entry is None:
			values.append(FieldValue("Unavailable"))
			diagnostics.append(Diagnostic("unavailable_field_value", item_id))
			continue
		entry = obj(entry)
		typename = text(entry.get("__typename"))
		field = obj(entry.get("field", {}))
		kwargs = {
			"graphql_type": typename,
			"id": text(entry.get("id"), nullable=True),
			"field_id": text(field.get("id"), nullable=True),
			"field_name": text(field.get("name"), nullable=True),
		}
		if typename not in supported:
			diagnostics.append(Diagnostic("unsupported_field_value", item_id, typename))
		else:
			identity(kwargs["id"])
			identity(kwargs["field_id"])
			text(kwargs["field_name"])
			if typename.endswith("TextValue"):
				kwargs["text"] = text(entry.get("text"), nullable=True)
			elif typename.endswith("NumberValue"):
				number = entry.get("number")
				if number is not None:
					if type(number) not in (float, int) or not math.isfinite(number):
						raise ProtocolError("GitHub returned an invalid numeric field value.")
					kwargs["number"] = float(number)
			elif typename.endswith("DateValue"):
				kwargs["date"] = text(entry.get("date"), nullable=True)
			elif typename.endswith("SingleSelectValue"):
				kwargs["option_id"] = text(entry.get("optionId"), nullable=True)
				kwargs["option_name"] = text(entry.get("name"), nullable=True)
			else:
				kwargs["iteration"] = iteration({**entry, "id": entry.get("iterationId")})
		values.append(FieldValue(**kwargs))
	if page.has_next_page:
		diagnostics.append(Diagnostic("field_values_incomplete", item_id))
	return FieldValuePage(item_id, values, page, diagnostics)


def content(value: dict | None, item_type: str, item_id: str) -> tuple[Content, list[Diagnostic]]:
	if value is None:
		kind = "redacted" if item_type == "REDACTED" else "unavailable"
		return Content(kind), [Diagnostic(kind + "_content", item_id)]
	value = obj(value)
	typename = text(value.get("__typename"))
	kinds = {"Issue": "issue", "PullRequest": "pull_request", "DraftIssue": "draft"}
	if typename not in kinds:
		return Content("unknown", graphql_type=typename), [Diagnostic("unsupported_content_type", item_id, typename)]
	result = Content(
		kind=kinds[typename], id=identity(value.get("id")), title=text(value.get("title")),
		url=text(value.get("url"), nullable=True),
		number=None if typename == "DraftIssue" else integer(value.get("number")),
		repository=None if typename == "DraftIssue" else text(obj(value.get("repository")).get("nameWithOwner")),
		state=text(value.get("state"), nullable=True), body=text(value.get("body"), nullable=True),
		graphql_type=typename,
	)
	return result, []


def item(value: dict, project_id: str) -> ProjectItem:
	value = obj(value)
	item_id = identity(value.get("id"))
	item_type = text(value.get("type"))
	linked, diagnostics = content(value.get("content"), item_type, item_id)
	fields = field_values(item_id, value.get("fieldValues"))
	diagnostics.extend(fields.diagnostics)
	return ProjectItem(
		item_id, project_id, item_type, boolean(value.get("isArchived")),
		text(value.get("createdAt")), text(value.get("updatedAt")), linked,
		fields.values, fields.page_info, not fields.diagnostics, diagnostics,
	)
