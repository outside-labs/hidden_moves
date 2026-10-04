"""Stateful synthetic GraphQL transport; never reaches a remote Project."""

import copy
import json
import re

from hidden_moves_github_projects import HTTPResponse


class WriteReplay:
    def __init__(self):
        self.requests = []
        self.added = False
        self.selected = None
        self.item_project = "PROJECT_allowed"
        self.content_kind = "Issue"
        self.fail_mutation = False
        self.malformed_mutation = False
        self.fail_verification = False
        self.ignore_set = False
        self.field_has_next = False
        self.fields = [
            {
                "__typename": "ProjectV2SingleSelectField",
                "id": "FIELD_dynamic",
                "name": "Workflow",
                "dataType": "SINGLE_SELECT",
                "options": [
                    {"id": "choice_A", "name": "Queued"},
                    {"id": "choice_B", "name": "Reviewed"},
                ],
            }
        ]

    @property
    def mutations(self):
        return [
            request
            for request in self.requests
            if request["query"].lstrip().startswith("mutation ")
        ]

    def __call__(self, request, *, timeout, max_bytes):
        body = json.loads(request.data)
        self.requests.append(body)
        operation = re.search(r"(?:query|mutation) (\w+)", body["query"]).group(1)
        variables = body["variables"]
        if self.fail_mutation and operation in ("AddProjectItem", "SetSingleSelect"):
            return HTTPResponse(
                200,
                json.dumps(
                    {
                        "errors": [
                            {"type": "FORBIDDEN", "message": "private-upstream-marker"}
                        ]
                    }
                ).encode(),
            )
        if (
            self.fail_verification
            and self.mutations
            and operation in ("ProjectItemMembership", "SingleSelectValue")
        ):
            raise OSError("private-transport-marker")
        if operation == "ProjectFields":
            data = {
                "node": {
                    "__typename": "ProjectV2",
                    "fields": {
                        "nodes": copy.deepcopy(self.fields),
                        "pageInfo": {
                            "hasNextPage": self.field_has_next,
                            "endCursor": "field-cursor",
                        },
                    },
                }
            }
        elif operation == "WritableContent":
            data = {"node": {"__typename": self.content_kind, "id": variables["id"]}}
        elif operation == "AddProjectItem":
            self.added = True
            data = {"addProjectV2ItemById": {"item": {"id": "ITEM_1"}}}
        elif operation == "ProjectItemMembership":
            data = {
                "node": {
                    "__typename": "ProjectV2Item",
                    "id": variables["id"],
                    "project": {"id": self.item_project},
                    "content": {"__typename": self.content_kind, "id": "CONTENT_issue"},
                }
            }
        elif operation == "SingleSelectValue":
            value = (
                None
                if self.selected is None
                else {
                    "__typename": "ProjectV2ItemFieldSingleSelectValue",
                    "optionId": self.selected,
                    "field": {"id": "FIELD_dynamic"},
                }
            )
            data = {
                "node": {
                    "__typename": "ProjectV2Item",
                    "id": variables["id"],
                    "project": {"id": self.item_project},
                    "fieldValueByName": value,
                }
            }
        elif operation == "SetSingleSelect":
            if not self.ignore_set:
                self.selected = variables["option"]
            data = {
                "updateProjectV2ItemFieldValue": {
                    "projectV2Item": {"id": variables["item"]}
                }
            }
        else:
            raise AssertionError("unexpected fixed operation")
        if self.malformed_mutation and operation in (
            "AddProjectItem",
            "SetSingleSelect",
        ):
            data = {}
        return HTTPResponse(200, json.dumps({"data": data}).encode())
