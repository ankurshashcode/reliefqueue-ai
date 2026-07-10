import unittest
from unittest.mock import patch
import base64
import tempfile
from pathlib import Path

from reliefqueue import product_api


class ProductApiFacadeTests(unittest.TestCase):
    def test_concurrent_assignment_conflict_is_reported(self) -> None:
        with (
            patch("reliefqueue.product_api._claim_idempotency", return_value=True),
            patch("reliefqueue.product_api._postgres_query", return_value=[]),
        ):
            with self.assertRaises(product_api.ProductApiError) as raised:
                product_api.assign_case("case-1", "worker-alpha-boat", "operator-a", "assign-a")
        self.assertEqual(raised.exception.status, 409)

    def test_duplicate_mobile_status_retry_does_not_insert_again(self) -> None:
        with (
            patch("reliefqueue.product_api._claim_idempotency", return_value=False),
            patch("reliefqueue.product_api.get_case", return_value={"case_id": "case-1", "status": "in_progress"}),
        ):
            result = product_api.update_status("case-1", "complete", "worker-alpha-boat", "retry", "status-1")
        self.assertEqual(result["status"], "duplicate")
        self.assertEqual(result["case"]["status"], "in_progress")

    def test_duplicate_message_send_returns_existing_message_id(self) -> None:
        with (
            patch("reliefqueue.product_api._claim_idempotency", return_value=False),
            patch("reliefqueue.product_api._postgres_query", return_value=[["42"]]),
        ):
            result = product_api.send_message("case-1", "sms", "duplicate", "message-1")
        self.assertEqual(result["status"], "duplicate")
        self.assertEqual(result["message_id"], "42")
        self.assertEqual(result["paid_integration_state"], "disabled_demo_local_only")

    def test_offline_sync_replays_status_and_evidence(self) -> None:
        with (
            patch("reliefqueue.product_api.update_status", return_value={"status": "updated"}) as status,
            patch("reliefqueue.product_api.add_evidence", return_value={"status": "metadata_recorded"}) as evidence,
            patch("reliefqueue.product_api._redis_command", return_value=0),
            patch("reliefqueue.product_api.field_my_cases", return_value={"cases": []}),
        ):
            result = product_api.sync_field(
                "worker-alpha-boat",
                [
                    {"case_id": "case-1", "status": "acknowledged", "idempotency_key": "sync-status"},
                    {"case_id": "case-1", "action": "evidence", "metadata": {}, "idempotency_key": "sync-evidence"},
                ],
            )
        self.assertEqual(result["status"], "synced")
        self.assertEqual(status.call_count, 1)
        self.assertEqual(evidence.call_count, 1)

    def test_ai_advisory_retry_returns_latest_review_required_result(self) -> None:
        with (
            patch("reliefqueue.product_api._claim_idempotency", return_value=False),
            patch(
                "reliefqueue.product_api.latest_ai_advisory",
                return_value={"job_id": "ai-1", "human_review_required": True},
            ),
        ):
            result = product_api.request_ai_advisory("case-1", "ai-key")
        self.assertEqual(result["status"], "duplicate")
        self.assertTrue(result["human_review_required"])

    def test_evidence_upload_rejects_metadata_only_and_stores_file_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_store = product_api.EVIDENCE_STORE
            product_api.EVIDENCE_STORE = Path(tmp)
            try:
                with self.assertRaises(product_api.ProductApiError) as raised:
                    product_api.add_evidence("RQ-1042", "worker-alpha-boat", {"file_name": "note.txt"}, "metadata-only")
                self.assertEqual(raised.exception.status, 400)
                payload = base64.b64encode(b"actual evidence bytes").decode()
                result = product_api.add_evidence(
                    "RQ-1042",
                    "worker-alpha-boat",
                    {"file_name": "note.txt", "media_type": "text/plain", "file_base64": payload},
                    "evidence-bytes",
                )
                self.assertEqual(result["status"], "stored")
                record = result["evidence"]
                self.assertEqual(record["size"], len(b"actual evidence bytes"))
                self.assertEqual(record["actor"]["role"], "field_worker")
                self.assertEqual(product_api.retrieve_evidence("RQ-1042", record["sha256"]), b"actual evidence bytes")
            finally:
                product_api.EVIDENCE_STORE = old_store

    def test_role_denial_blocks_field_worker_assignment(self) -> None:
        with self.assertRaises(product_api.ProductApiError) as raised:
            product_api.assign_case("RQ-1042", "worker-alpha-boat", "worker-alpha-boat", "denied-assignment")
        self.assertEqual(raised.exception.status, 403)

    def test_stale_replay_conflicts_without_clobbering_server_state(self) -> None:
        case = product_api._local_get_case("RQ-1042")
        original_status = case["status"]
        original_revision = int(case.get("revision") or 1)
        product_api.update_status("RQ-1042", "in_progress", "worker-alpha-boat", "newer server update", "newer-server")
        result = product_api.sync_field(
            "worker-alpha-boat",
            [{"case_id": "RQ-1042", "status": "complete", "expected_revision": original_revision, "idempotency_key": "stale-replay"}],
        )
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(product_api._local_get_case("RQ-1042")["status"], "in_progress")
        self.assertEqual(result["conflicts"][0]["attempted"]["status"], "complete")
        self.assertIn("refresh", result["conflicts"][0]["safe_actions"])
        case["status"] = original_status
        case["revision"] = original_revision

    def test_webhook_normalization_and_dlq_replay(self) -> None:
        rapidpro = product_api.normalize_inbound_webhook(
            "rapidpro",
            {"contact": {"urn": "tel:+15550000000"}, "text": "Need water", "message_id": "rp-1"},
        )
        twilio = product_api.normalize_inbound_webhook("twilio_sms", {"From": "+15550000001", "Body": "Need food", "MessageSid": "SM1"})
        whatsapp = product_api.normalize_inbound_webhook("whatsapp", {"From": "whatsapp:+15550000002", "Body": "Need shelter", "MessageSid": "WA1"})
        self.assertEqual(rapidpro["provider"], "rapidpro")
        self.assertEqual(twilio["text"], "Need food")
        self.assertEqual(whatsapp["external_id"], "WA1")
        product_api._LOCAL_DLQ.append({"type": "test", "context": {"error": "retry me"}})
        replay = product_api.replay_dlq("command-operator")
        self.assertGreaterEqual(replay["replayed"], 1)

    def test_monitoring_distinguishes_local_mock_provider_state(self) -> None:
        status = product_api.monitoring_status()
        self.assertIn(status["live_stack_state"], {"local/mock", "configured-live"})
        self.assertIn("dlq_count", status["queue_pressure"])
        self.assertIn("local_mock", status["provider_status"])


if __name__ == "__main__":
    unittest.main()
