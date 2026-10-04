"""Fixed read-only queries; account identities and cursors are variables."""

PROJECT = """
id number title url shortDescription public closed
owner { __typename ... on User { login } ... on Organization { login } }
"""
PAGE = "pageInfo { hasNextPage endCursor }"
FIELDS = """
__typename
... on ProjectV2FieldCommon { id name dataType }
... on ProjectV2SingleSelectField { options { id name } }
... on ProjectV2IterationField {
  configuration {
    iterations { id title startDate duration }
    completedIterations { id title startDate duration }
  }
}
"""
VALUES = """
__typename
... on ProjectV2ItemFieldValueCommon {
  id field { ... on ProjectV2FieldCommon { id name } }
}
... on ProjectV2ItemFieldTextValue { text }
... on ProjectV2ItemFieldNumberValue { number }
... on ProjectV2ItemFieldDateValue { date }
... on ProjectV2ItemFieldSingleSelectValue { optionId name }
... on ProjectV2ItemFieldIterationValue { iterationId title startDate duration }
"""
CONTENT = """
__typename
... on Issue { id number title url state repository { nameWithOwner } }
... on PullRequest { id number title url state repository { nameWithOwner } }
... on DraftIssue { id title body }
"""


def owner_query(kind: str, *, listing: bool) -> str:
	if listing:
		return f"""query ListProjects($owner: String!, $first: Int!, $cursor: String) {{
  owner: {kind}(login: $owner) {{ projectsV2(first: $first, after: $cursor) {{
    nodes {{ {PROJECT} }} {PAGE}
  }} }}
}}"""
	return f"""query GetProject($owner: String!, $number: Int!) {{
  owner: {kind}(login: $owner) {{ projectV2(number: $number) {{ {PROJECT} }} }}
}}"""


FIELD_QUERY = f"""query ProjectFields($id: ID!, $first: Int!, $cursor: String) {{
  node(id: $id) {{ __typename ... on ProjectV2 {{
    fields(first: $first, after: $cursor) {{ nodes {{ {FIELDS} }} {PAGE} }}
  }} }}
}}"""
ITEM_QUERY = f"""query ProjectItems($id: ID!, $first: Int!, $cursor: String, $fieldFirst: Int!) {{
  node(id: $id) {{ __typename ... on ProjectV2 {{
    items(first: $first, after: $cursor) {{
      nodes {{ id type isArchived createdAt updatedAt
        content {{ {CONTENT} }}
        fieldValues(first: $fieldFirst) {{ nodes {{ {VALUES} }} {PAGE} }}
      }} {PAGE}
    }}
  }} }}
}}"""
VALUE_QUERY = f"""query ItemFieldValues($id: ID!, $first: Int!, $cursor: String) {{
  node(id: $id) {{ __typename ... on ProjectV2Item {{
    fieldValues(first: $first, after: $cursor) {{ nodes {{ {VALUES} }} {PAGE} }}
  }} }}
}}"""
