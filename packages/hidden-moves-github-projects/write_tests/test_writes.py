import copy
import unittest

from hidden_moves_github_projects import (
    PaginationLimitError,
    ProjectsClient,
    ProtocolError,
)
from hidden_moves_github_projects.writes import (
    PostWriteVerificationError,
    ProjectAuthorizationError,
    ProjectsWriter,
    SelectionConflictError,
    WriteOutcomeUnknownError,
)
from write_replay import WriteReplay


class WriteTests(unittest.TestCase):
    def setUp(self):
        self.transport = WriteReplay()
        self.reader = ProjectsClient("private-token-marker", transport=self.transport)
        self.writer = ProjectsWriter(self.reader, allowed_projects=["PROJECT_allowed"])

    def test_add_existing_issue_or_pr_and_verify_remote_identities(self):
        for kind in ("Issue", "PullRequest"):
            with self.subTest(kind=kind):
                self.transport.content_kind = kind
                receipt = self.writer.add_item("PROJECT_allowed", "CONTENT_issue")
                self.assertTrue(receipt.verified)
                self.assertEqual(receipt.item_id, "ITEM_1")
                self.assertEqual(receipt.content_id, "CONTENT_issue")
                self.assertEqual(receipt.project_id, "PROJECT_allowed")
        self.assertEqual(len(self.transport.mutations), 2)

    def test_allowlist_denial_happens_before_credentials_or_requests(self):
        for operation in (
            lambda: self.writer.add_item("PROJECT_other", "CONTENT_issue"),
            lambda: self.writer.set_single_select(
                "PROJECT_other", "ITEM_1", "Workflow", "Reviewed", None
            ),
        ):
            with self.assertRaises(ProjectAuthorizationError):
                operation()
        self.assertEqual(self.transport.requests, [])
        for projects in ([], "PROJECT_allowed", [" "]):
            with self.assertRaises(ValueError):
                ProjectsWriter(self.reader, allowed_projects=projects)
        self.assertNotIn("private-token-marker", repr(self.writer))

    def test_only_existing_issue_pr_content_can_be_added(self):
        for kind in ("DraftIssue", "User", "UnknownContent"):
            self.transport.content_kind = kind
            with self.assertRaises(ProjectAuthorizationError):
                self.writer.add_item("PROJECT_allowed", "CONTENT_issue")
        self.assertEqual(self.transport.mutations, [])

    def test_dynamic_field_option_lookup_and_expected_value(self):
        state = self.writer.inspect_single_select(
            "PROJECT_allowed", "ITEM_1", "Workflow"
        )
        self.assertEqual(state.current_option_id, None)
        self.assertEqual(
            [option.id for option in state.options], ["choice_A", "choice_B"]
        )
        receipt = self.writer.set_single_select(
            "PROJECT_allowed", "ITEM_1", "Workflow", "Reviewed", None
        )
        self.assertTrue(receipt.verified)
        self.assertEqual(
            (receipt.field_id, receipt.option_id), ("FIELD_dynamic", "choice_B")
        )
        self.assertEqual(
            self.transport.mutations[0]["variables"],
            {
                "project": "PROJECT_allowed",
                "item": "ITEM_1",
                "field": "FIELD_dynamic",
                "option": "choice_B",
            },
        )
        updated = self.writer.set_single_select(
            "PROJECT_allowed", "ITEM_1", "Workflow", "Queued", "choice_B"
        )
        self.assertEqual(updated.option_id, "choice_A")

    def test_membership_stale_value_and_invalid_choices_prevent_mutations(self):
        self.transport.item_project = "PROJECT_other"
        with self.assertRaises(ProjectAuthorizationError):
            self.writer.set_single_select(
                "PROJECT_allowed", "ITEM_1", "Workflow", "Reviewed", None
            )
        self.transport.item_project = "PROJECT_allowed"
        self.transport.selected = "choice_A"
        with self.assertRaises(SelectionConflictError):
            self.writer.set_single_select(
                "PROJECT_allowed", "ITEM_1", "Workflow", "Reviewed", None
            )
        for field, option in (("Absent", "Reviewed"), ("Workflow", "Absent")):
            with self.assertRaises(ValueError):
                self.writer.set_single_select(
                    "PROJECT_allowed", "ITEM_1", field, option, "choice_A"
                )
        self.assertEqual(self.transport.mutations, [])

    def test_ambiguous_fields_and_options_are_not_guessed(self):
        self.transport.fields.append(copy.deepcopy(self.transport.fields[0]))
        with self.assertRaises(ValueError):
            self.writer.set_single_select(
                "PROJECT_allowed", "ITEM_1", "Workflow", "Reviewed", None
            )
        self.transport.fields.pop()
        self.transport.fields[0]["options"].append(
            {"id": "choice_C", "name": "Reviewed"}
        )
        with self.assertRaises(ValueError):
            self.writer.set_single_select(
                "PROJECT_allowed", "ITEM_1", "Workflow", "Reviewed", None
            )
        self.assertEqual(self.transport.mutations, [])

    def test_field_lookup_budget_and_repeated_cursors_are_errors(self):
        self.transport.field_has_next = True
        short = ProjectsWriter(
            self.reader, allowed_projects=["PROJECT_allowed"], max_field_pages=1
        )
        with self.assertRaises(PaginationLimitError):
            short.set_single_select(
                "PROJECT_allowed", "ITEM_1", "Workflow", "Reviewed", None
            )
        with self.assertRaises(ProtocolError):
            self.writer.set_single_select(
                "PROJECT_allowed", "ITEM_1", "Workflow", "Reviewed", None
            )
        self.assertEqual(self.transport.mutations, [])

    def test_post_write_failure_carries_acknowledged_receipt_without_retry(self):
        self.transport.fail_verification = True
        with self.assertRaises(PostWriteVerificationError) as error:
            self.writer.add_item("PROJECT_allowed", "CONTENT_issue")
        self.assertTrue(self.transport.added)
        self.assertTrue(error.exception.acknowledged)
        self.assertEqual(error.exception.receipt.item_id, "ITEM_1")
        self.assertFalse(error.exception.receipt.verified)
        self.assertEqual(len(self.transport.mutations), 1)
        self.assertNotIn("private-transport-marker", str(error.exception))

    def test_unverified_set_and_uncertain_graphql_response_are_typed(self):
        self.transport.ignore_set = True
        with self.assertRaises(PostWriteVerificationError) as error:
            self.writer.set_single_select(
                "PROJECT_allowed", "ITEM_1", "Workflow", "Reviewed", None
            )
        self.assertEqual(error.exception.receipt.option_id, "choice_B")
        self.assertEqual(len(self.transport.mutations), 1)
        self.transport.ignore_set = False
        self.transport.fail_mutation = True
        with self.assertRaises(WriteOutcomeUnknownError) as error:
            self.writer.add_item("PROJECT_allowed", "CONTENT_issue")
        self.assertFalse(error.exception.acknowledged)
        self.assertEqual(error.exception.cause_type, "GraphQLError")
        self.assertNotIn("private-upstream-marker", str(error.exception))
        self.assertNotIn("private-token-marker", str(error.exception))

    def test_malformed_success_response_does_not_claim_acknowledgement(self):
        self.transport.malformed_mutation = True
        with self.assertRaises(WriteOutcomeUnknownError) as error:
            self.writer.add_item("PROJECT_allowed", "CONTENT_issue")
        self.assertTrue(self.transport.added)
        self.assertFalse(error.exception.acknowledged)
        self.assertIsNone(error.exception.receipt.item_id)
        self.assertFalse(error.exception.receipt.verified)
        self.assertEqual(len(self.transport.mutations), 1)

    def test_add_then_set_can_partially_complete_and_is_not_rolled_back(self):
        added = self.writer.add_item("PROJECT_allowed", "CONTENT_issue")
        self.transport.selected = "choice_A"
        with self.assertRaises(SelectionConflictError):
            self.writer.set_single_select(
                "PROJECT_allowed", added.item_id, "Workflow", "Reviewed", None
            )
        self.assertTrue(added.verified)
        self.assertTrue(self.transport.added)
        self.assertEqual(len(self.transport.mutations), 1)


if __name__ == "__main__":
    unittest.main()
