import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reliefqueue.assignment import suggest_assignments
from reliefqueue.cli import build_cases
from reliefqueue.intake import load_json, load_jsonl
from reliefqueue.live_integrations import (
    _redis_entries,
    logistics_profile_catalog,
    logistics_profile_names,
    run_live_integration_command,
    _volunteer_drill_config,
    stateful_mutation_profile_catalog,
    stateful_mutation_profile_names,
)
from reliefqueue.reports import write_outputs


ROOT = Path(__file__).resolve().parents[1]


class RedisResponseParserTests(unittest.TestCase):
    def test_redis_entries_parser_supports_xclaim_direct_response(self) -> None:
        claimed = _redis_entries([["1783231977960-0", ["purpose", "simulate_dispatch_worker_crash", "team_id", "rescue-alpha"]]])
        self.assertEqual(claimed, [("1783231977960-0", {"purpose": "simulate_dispatch_worker_crash", "team_id": "rescue-alpha"})])

        grouped = _redis_entries(
            [[
                "reliefqueue.intake.v1.logistics_asset.test",
                [["1783231977960-0", ["purpose", "simulate_dispatch_worker_crash"]]],
            ]]
        )
        self.assertEqual(grouped, [("1783231977960-0", {"purpose": "simulate_dispatch_worker_crash"})])


class LiveIntegrationPhaseCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT / "fixtures", self.root / "fixtures")
        self.report_dir = self.root / "reports" / "latest"
        reports = load_jsonl(self.root / "fixtures" / "reliefqueue_seed_reports.jsonl")
        zones = load_json(self.root / "fixtures" / "operation_zones.json")
        workers = load_json(self.root / "fixtures" / "field_workers.json")
        cases = build_cases(reports, zones)
        suggestions = suggest_assignments(cases, workers)
        write_outputs(self.report_dir, cases, suggestions, "# validation\n", zones)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_makefile_contains_all_phase_targets(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        for target in [
            "postgis-live-smoke",
            "queue-live-smoke",
            "live-stateful-mutation-drill",
            "live-stateful-mutation-drill-verbose",
            "live-stateful-mutation-drill-profile",
            "live-stateful-mutation-drill-profiles",
            "live-logistics-asset-drill",
            "live-logistics-asset-drill-profile",
            "live-logistics-asset-profiles",
            "live-volunteer-surge-drill",
            "live-volunteer-surge-drill-profile",
            "live-volunteer-surge-profiles",
            "vllm-live-status",
            "observability-live-smoke",
            "odk-live-smoke",
            "rapidpro-live-smoke",
            "channel-live-status",
            "masked-contact-provider-smoke",
            "live-pilot-drill",
        ]:
            self.assertIn(f"{target}", makefile)

    def test_phase_smokes_write_checkpoints_without_live_env(self) -> None:
        commands = [
            "postgis-live-smoke",
            "queue-live-smoke",
            "amd-live-report",
            "observability-live-smoke",
            "odk-live-smoke",
            "rapidpro-live-smoke",
            "channel-live-status",
            "masked-contact-cancel-dry-run",
            "live-pilot-drill",
            "live-pilot-reviewer-pack",
            "live-pilot-status",
        ]
        with patch.dict("os.environ", {"AI_MODE": "mock"}, clear=True):
            for command in commands:
                self.assertEqual(run_live_integration_command(command, self.root, self.report_dir), 0, command)

        checkpoint_dir = self.report_dir / "live_integration_checkpoints"
        expected = [
            "geospatial-store.json",
            "operations-queue.json",
            "ai-model-endpoint.json",
            "system-health.json",
            "field-forms.json",
            "messaging-channel.json",
            "communication-channels.json",
            "masked-contact.json",
            "pilot-drill.json",
        ]
        for name in expected:
            self.assertTrue((checkpoint_dir / name).exists(), name)
            payload = json.loads((checkpoint_dir / name).read_text(encoding="utf-8"))
            self.assertIn(payload["implementation_status"], {"PASS", "SKIP"})
            self.assertFalse("secret" in json.dumps(payload).lower() and "value" in json.dumps(payload).lower())



    def test_live_phase_commands_auto_resolve_local_stack_endpoints_and_ignore_stale_empty_port_env(self) -> None:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        (self.report_dir / "live_stack_status.json").write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "services": [
                        {"name": "postgis", "status": "PASS", "detail": "running (healthy)", "endpoint": "127.0.0.1:54329"},
                        {"name": "redis", "status": "PASS", "detail": "running (healthy)", "endpoint": "127.0.0.1:63799"},
                        {"name": "nats", "status": "PASS", "detail": "running (healthy)", "endpoint": "127.0.0.1:42299"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        seen: dict[str, str] = {}

        def fake_postgres_execute(dsn: str, statements: list[str], timeout: float) -> None:
            del statements, timeout
            seen["postgres_dsn"] = dsn

        def fake_redis_command(url: str, args: list[str], timeout: float = 5.0) -> str:
            del args, timeout
            seen["redis_url"] = url
            return "PONG"

        with (
            patch.dict(
                "os.environ",
                {
                    "RELIEFQUEUE_POSTGIS_DSN": "postgresql://reliefqueue:reliefqueue@127.0.0.1:/reliefqueue",
                    "RELIEFQUEUE_REDIS_URL": "redis://127.0.0.1:/0",
                    "RELIEFQUEUE_QUEUE_BACKEND": "redis",
                },
                clear=True,
            ),
            patch("reliefqueue.live_integrations._postgres_execute", side_effect=fake_postgres_execute),
            patch("reliefqueue.live_integrations._redis_command", side_effect=fake_redis_command),
            patch("reliefqueue.live_integrations._redis_xgroup_create", return_value="created"),
        ):
            self.assertEqual(run_live_integration_command("postgis-live-init", self.root, self.report_dir), 0)
            self.assertEqual(run_live_integration_command("queue-live-init", self.root, self.report_dir), 0)

        self.assertEqual(seen["postgres_dsn"], "postgresql://reliefqueue:reliefqueue@127.0.0.1:54329/reliefqueue")
        self.assertEqual(seen["redis_url"], "redis://127.0.0.1:63799/0")
        postgis_payload = json.loads(
            (self.report_dir / "live_integrations" / "geospatial-store" / "postgis_live_init.json").read_text(encoding="utf-8")
        )
        queue_payload = json.loads(
            (self.report_dir / "live_integrations" / "operations-queue" / "queue_live_init.json").read_text(encoding="utf-8")
        )
        self.assertEqual(postgis_payload["postgis_backend"], "local_live_stack")
        self.assertEqual(queue_payload["redis_source"], "local_live_stack")



    def test_stateful_mutation_profile_library_covers_recent_disaster_patterns(self) -> None:
        names = stateful_mutation_profile_names()
        self.assertGreaterEqual(len(names), 20)
        for expected in [
            "urban_flood",
            "riverine_flood",
            "flash_flood_landslide",
            "earthquake_urban",
            "tsunami_coastal",
            "wildfire_evacuation",
            "drought_food_security",
            "cholera_wash_outbreak",
            "conflict_displacement_camp",
            "winter_storm_cold_wave",
            "volcanic_ashfall",
            "industrial_chemical_release",
            "power_outage_urban",
            "crowd_event_mass_casualty",
        ]:
            self.assertIn(expected, names)
        for item in stateful_mutation_profile_catalog():
            self.assertIn("coordinator_owns", item)
            self.assertIn("command_center_owns", item)
            self.assertGreaterEqual(item["coordinator_owns"]["relief_hub_radius_meters"], 100)
            self.assertGreaterEqual(item["command_center_owns"]["redis_burst_size"], 4)
            self.assertEqual(item["command_center_owns"]["replay_mode"], "review_first")


    def test_logistics_profile_library_matches_disaster_profiles_and_role_split(self) -> None:
        names = logistics_profile_names()
        self.assertEqual(names, stateful_mutation_profile_names())
        self.assertGreaterEqual(len(names), 20)
        catalog = logistics_profile_catalog()
        self.assertEqual(len(catalog), len(names))
        for item in catalog:
            self.assertIn("coordinator_owns", item)
            self.assertIn("command_center_owns", item)
            self.assertGreaterEqual(len(item["coordinator_owns"]["field_teams"]), 4)
            self.assertGreaterEqual(len(item["coordinator_owns"]["planned_asset_types"]), 4)
            self.assertGreaterEqual(item["command_center_owns"]["reservation_burst_size"], 4)
            self.assertEqual(item["command_center_owns"]["replay_mode"], "review_first")

    def test_logistics_asset_drill_skips_without_live_endpoints(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(run_live_integration_command("live-logistics-asset-drill", self.root, self.report_dir), 0)

        out_dir = self.report_dir / "live_integrations" / "logistics-assets"
        payload = json.loads((out_dir / "live_logistics_asset_drill.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "SKIP")
        self.assertEqual(payload["postgis"]["status"], "SKIP")
        self.assertEqual(payload["redis"]["status"], "SKIP")

    def test_volunteer_surge_drill_skips_without_live_endpoints_and_keeps_polling_gated(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(run_live_integration_command("live-volunteer-surge-drill", self.root, self.report_dir), 0)

        out_dir = self.report_dir / "live_integrations" / "volunteer-surge"
        payload = json.loads((out_dir / "live_volunteer_surge_drill.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "SKIP")
        self.assertEqual(payload["postgis"]["status"], "SKIP")
        self.assertEqual(payload["redis"]["status"], "SKIP")
        self.assertFalse(payload["privacy_and_safety_boundary"]["real_messages_sent"])
        self.assertFalse(payload["privacy_and_safety_boundary"]["presence_polling_enabled"])

    def test_volunteer_config_separates_roles_and_safety_boundary(self) -> None:
        with patch.dict("os.environ", {"RELIEFQUEUE_VOLUNTEER_PROFILE": "urban_flood"}, clear=True):
            config = _volunteer_drill_config()

        self.assertEqual(config["coordinator_config"]["volunteer_intake_policy"]["field_worker_can_register_walkup_volunteer"], True)
        self.assertIn("outreach_burst_size", config["command_center_config"])
        self.assertFalse(config["privacy_and_safety_boundary"]["raw_phone_numbers_stored"])
        self.assertIn("telecom/provider integration", " ".join(config["privacy_and_safety_boundary"]["requires_before_live_polling"]))
        self.assertEqual(config["selected_profile"]["name"], "urban_flood")
        self.assertIn("field_teams", config["coordinator_config"])
        self.assertIn("local_coordinator", config["role_contract"])
        self.assertIn("field_worker", config["role_contract"])
        self.assertIn("command_center_operator", config["role_contract"])
        self.assertFalse(config["secret_values_printed"])

    def test_logistics_asset_drill_aggregates_live_evidence_and_checkpoint(self) -> None:
        postgis = {
            "status": "PASS",
            "cleanup_verified": True,
            "nearest_asset_decision": {"asset_id": "asset-1"},
            "reallocation_result": {"status": "reallocation_review"},
        }
        redis = {
            "status": "PASS",
            "cleanup_verified": True,
            "reservation_lock": {"race_prevented": True},
            "atomic_dedup": {"duplicate_suppressed": True},
            "replayed": 1,
        }
        with (
            patch.dict("os.environ", {"RELIEFQUEUE_LOGISTICS_PROFILE": "earthquake_urban"}, clear=True),
            patch("reliefqueue.live_integrations._postgis_logistics_asset_drill", return_value=postgis),
            patch("reliefqueue.live_integrations._redis_logistics_asset_drill", return_value=redis),
        ):
            self.assertEqual(run_live_integration_command("live-logistics-asset-drill", self.root, self.report_dir), 0)

        out_dir = self.report_dir / "live_integrations" / "logistics-assets"
        payload = json.loads((out_dir / "live_logistics_asset_drill.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["selected_profile"]["name"], "earthquake_urban")
        self.assertTrue(payload["cleanup_verified"])
        checkpoint = json.loads(
            (self.report_dir / "live_integration_checkpoints" / "logistics-assets.json").read_text(encoding="utf-8")
        )
        self.assertEqual(checkpoint["implementation_status"], "PASS")
        self.assertIn("live-logistics-asset-drill", checkpoint["commands_added"])

    def test_logistics_asset_verbose_mode_prints_operator_evidence(self) -> None:
        postgis = {
            "status": "PASS",
            "postgis_backend": "local_live_stack",
            "scenario": "mission_logistics_inventory_reservation_dispatch_return_and_reallocation",
            "case_for_postgis": ["nearest available asset or hub by destination point"],
            "tables": {"hubs": "reliefqueue_live.reliefqueue_live_logistics_hubs"},
            "tables_found": ["reliefqueue_live.reliefqueue_live_logistics_hubs"],
            "spatial_indexes_found": ["reliefqueue_live_inventory_assets_point_gix"],
            "hubs_inserted": [{"hub_id": "hub-1"}],
            "inventory_assets_inserted": [{"asset_id": "asset-1", "asset_type": "rescue_boat"}],
            "logistics_requests_created": [{"request_id": "req-1", "team_role": "water_rescue"}],
            "nearest_asset_decision": {"asset_id": "asset-1", "distance_meters": 750},
            "reservation_result": {"request_id": "req-1", "asset_id": "asset-1"},
            "distribution_result": {"quantity_decremented": 20},
            "overdue_return_assets": [{"asset_id": "asset-1", "minutes_overdue": 10}],
            "reallocation_result": {"request_id": "req-2", "status": "reallocation_review"},
            "final_inventory_before_cleanup": [{"asset_id": "asset-1", "status": "reallocated"}],
            "final_requests_before_cleanup": [{"request_id": "req-2", "status": "reallocation_review"}],
            "cleanup_remaining_requests": 0,
            "cleanup_remaining_assets": 0,
            "cleanup_remaining_hubs": 0,
            "cleanup_verified": True,
        }
        redis = {
            "status": "PASS",
            "redis_source": "local_live_stack",
            "scenario": "logistics_request_reservation_dispatch_return_reallocation_and_replay",
            "case_for_redis": ["bursty team logistics requests"],
            "stream": "reliefqueue.intake.v1.logistics_asset.test",
            "dead_letter_stream": "reliefqueue.intake.v1.logistics_asset.test.dead_letter",
            "replay_review_stream": "reliefqueue.intake.v1.logistics_asset.test.replay_review",
            "timeline_stream": "reliefqueue.intake.v1.logistics_asset.test.timeline",
            "jobs_prepared": 6,
            "queue_depth_after_enqueue": 6,
            "reservation_lock": {"race_prevented": True},
            "atomic_dedup": {"duplicate_suppressed": True},
            "simulated_worker_crash_message_id": "1-0",
            "recovered_message_id": "1-0",
            "recovery_consumer": "logistics-recovery-worker",
            "retry_message_id": "2-0",
            "dead_letter_message_id": "3-0",
            "replayed": 1,
            "timeline_events_written": 6,
            "final_state_before_cleanup": {"stream_length": 7, "replay_review_length": 1},
            "final_state_after_cleanup": {"stream_exists": 0, "dlq_exists": 0, "replay_review_exists": 0, "timeline_exists": 0},
            "cleanup_verified": True,
        }

        def render_with_verbose(verbose_value: str) -> str:
            with (
                patch.dict(
                    "os.environ",
                    {"RELIEFQUEUE_LIVE_LOGISTICS_VERBOSE": verbose_value, "RELIEFQUEUE_LOGISTICS_PROFILE": "cyclone_coastal"},
                    clear=True,
                ),
                patch("reliefqueue.live_integrations._postgis_logistics_asset_drill", return_value=postgis),
                patch("reliefqueue.live_integrations._redis_logistics_asset_drill", return_value=redis),
            ):
                import io
                from contextlib import redirect_stdout

                out = io.StringIO()
                with redirect_stdout(out):
                    self.assertEqual(run_live_integration_command("live-logistics-asset-drill", self.root, self.report_dir), 0)
                return out.getvalue()

        compact = render_with_verbose("1")
        self.assertIn("Logistics asset evidence (-v)", compact)
        self.assertIn("- profile: cyclone_coastal", compact)
        self.assertIn("PostGIS: PASS", compact)
        self.assertIn("Redis: PASS", compact)
        self.assertIn("Full report:", compact)
        self.assertNotIn("Coordinator logistics scenario", compact)
        self.assertNotIn("Redis logistics evidence", compact)

        rendered = render_with_verbose("2")
        self.assertIn("Logistics asset evidence (-vv)", rendered)
        self.assertIn("Scenario profile: cyclone_coastal", rendered)
        self.assertIn("Coordinator logistics scenario", rendered)
        self.assertIn("Command center logistics controls", rendered)
        self.assertIn("PostGIS logistics evidence", rendered)
        self.assertIn("nearest available asset decision", rendered)
        self.assertIn("overdue return assets", rendered)
        self.assertIn("reallocation result", rendered)
        self.assertIn("Redis logistics evidence", rendered)
        self.assertIn("reservation lock", rendered)
        self.assertIn("atomic duplicate suppression", rendered)
        self.assertIn("timeline events written", rendered)
        self.assertIn("cleanup remaining assets: 0", rendered)

    def test_stateful_mutation_drill_skips_without_live_endpoints(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(run_live_integration_command("live-stateful-mutation-drill", self.root, self.report_dir), 0)

        out_dir = self.report_dir / "live_integrations" / "stateful-mutation"
        payload = json.loads((out_dir / "live_stateful_mutation_drill.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "SKIP")
        self.assertEqual(payload["postgis"]["status"], "SKIP")
        self.assertEqual(payload["redis"]["status"], "SKIP")
        self.assertEqual(payload["nats"]["status"], "SKIP")
        self.assertEqual(payload["selected_profile"]["name"], "urban_flood")
        self.assertEqual(payload["postgis"]["selected_profile"]["name"], "urban_flood")
        self.assertEqual(payload["redis"]["selected_profile"]["name"], "urban_flood")
        self.assertIn("local_coordinator", payload["role_contract"])
        self.assertIn("command_center_operator", payload["role_contract"])
        self.assertFalse(payload["private_payload_written"])
        self.assertFalse(payload["secret_values_printed"])
        for name in ["postgis_mutation_evidence.json", "redis_mutation_evidence.json", "nats_guidance_proof.json"]:
            self.assertTrue((out_dir / name).exists(), name)

    def test_stateful_mutation_profiles_separate_coordinator_and_command_center_config(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "RELIEFQUEUE_MUTATION_PROFILE": "cyclone_coastal",
                "RELIEFQUEUE_COORDINATOR_RELIEF_HUB_RADIUS_METERS": "3200",
                "RELIEFQUEUE_COMMAND_CENTER_REDIS_BURST_SIZE": "12",
                "RELIEFQUEUE_COMMAND_CENTER_DEDUP_TTL_SECONDS": "900",
                "RELIEFQUEUE_COMMAND_CENTER_DLQ_AFTER_ATTEMPTS": "4",
            },
            clear=True,
        ):
            self.assertEqual(run_live_integration_command("live-stateful-mutation-drill", self.root, self.report_dir), 0)

        out_dir = self.report_dir / "live_integrations" / "stateful-mutation"
        payload = json.loads((out_dir / "live_stateful_mutation_drill.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["selected_profile"]["name"], "cyclone_coastal")
        self.assertEqual(payload["coordinator_config"]["relief_hub_radius_meters"], 3200)
        self.assertEqual(payload["command_center_config"]["redis_burst_size"], 12)
        self.assertEqual(payload["command_center_config"]["dedup_ttl_seconds"], 900)
        self.assertEqual(payload["command_center_config"]["dlq_after_attempts"], 4)
        self.assertEqual(payload["postgis"]["functional_config"]["relief_hub_radius_meters"], 3200)
        self.assertEqual(payload["redis"]["runtime_config"]["redis_burst_size"], 12)
        self.assertEqual(payload["redis"]["runtime_config"]["dedup_ttl_seconds"], 900)

    def test_stateful_mutation_drill_aggregates_live_evidence_and_checkpoint(self) -> None:
        postgis = {"status": "PASS", "cleanup_verified": True, "operations": ["insert_demo_case", "verify_cleanup"]}
        redis = {"status": "PASS", "cleanup_verified": True, "operations": ["enqueue_test_jobs", "replay_dlq_safely"]}
        nats = {"status": "PASS", "jetstream_queue_mutation_attempted": False, "role": "connectivity_proof_only"}
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("reliefqueue.live_integrations._postgis_stateful_mutation_drill", return_value=postgis),
            patch("reliefqueue.live_integrations._redis_stateful_mutation_drill", return_value=redis),
            patch("reliefqueue.live_integrations._nats_guidance_proof", return_value=nats),
        ):
            self.assertEqual(run_live_integration_command("live-stateful-mutation-drill", self.root, self.report_dir), 0)

        out_dir = self.report_dir / "live_integrations" / "stateful-mutation"
        payload = json.loads((out_dir / "live_stateful_mutation_drill.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "PASS")
        self.assertTrue(payload["cleanup_verified"])
        self.assertFalse(payload["nats"]["jetstream_queue_mutation_attempted"])
        checkpoint = json.loads(
            (self.report_dir / "live_integration_checkpoints" / "stateful-mutation.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(checkpoint["implementation_status"], "PASS")
        self.assertIn("live-stateful-mutation-drill", checkpoint["commands_added"])

    def test_stateful_mutation_verbose_mode_prints_operator_evidence(self) -> None:
        postgis = {
            "status": "PASS",
            "postgis_backend": "local_live_stack",
            "table": '"reliefqueue_live".reliefqueue_live_cases',
            "case_id": "stateful-mutation-test",
            "operation_zone_id": "zone-a",
            "scenario": "spatial_zone_assignment_nearest_case_and_cleanup",
            "why_postgis_matters": ["stores true geometry"],
            "case_table": '"reliefqueue_live".reliefqueue_live_cases',
            "zone_table": '"reliefqueue_live".reliefqueue_live_operation_zones',
            "tables_found": ["reliefqueue_live.reliefqueue_live_cases", "reliefqueue_live.reliefqueue_live_operation_zones"],
            "spatial_indexes_found": ["reliefqueue_live_cases_point_gix"],
            "inserted_zone_public": {"zone_polygon_wkt": "POLYGON((0 0,1 0,1 1,0 1,0 0))"},
            "inserted_public_row": {"case_id": "stateful-mutation-test", "urgency": "REVIEW", "longitude": 73.1, "latitude": 22.1},
            "read_back_row": {"case_id": "stateful-mutation-test", "urgency": "HIGH", "inside_zone_polygon": True},
            "spatial_assignment_verified": True,
            "update_verified": True,
            "inside_zone_count_after_insert": 2,
            "outside_case_excluded_by_polygon": True,
            "nearest_cases_to_relief_hub": [{"case_id": "stateful-mutation-test", "distance_meters": 850}],
            "deleted_case_ids": ["stateful-mutation-test"],
            "deleted_operation_zone_id": "zone-a",
            "cleanup_remaining_rows": 0,
            "cleanup_remaining_zones": 0,
            "cleanup_verified": True,
            "coordinator_config": {"relief_hub_radius_meters": 1500, "operation_zone_id": "zone-a"},
        }
        redis = {
            "status": "PASS",
            "redis_source": "local_live_stack",
            "stream": "reliefqueue.intake.v1.stateful_mutation.test",
            "dead_letter_stream": "reliefqueue.intake.v1.stateful_mutation.test.dead_letter",
            "replay_review_stream": "reliefqueue.intake.v1.stateful_mutation.test.replay_review",
            "scenario": "bursty_intake_worker_crash_retry_dlq_replay_and_dedup",
            "why_redis_matters": ["consumer groups expose pending jobs"],
            "jobs_prepared": 4,
            "prepared_jobs_public_fields": [{"job_id": "job-1", "purpose": "process_once"}],
            "enqueued": 4,
            "claimed": 4,
            "processed": 1,
            "queue_depth_after_enqueue": 4,
            "simulated_worker_crash_message_id": "1-0",
            "pending_after_worker_crash": [1, "1-0", "1-0", [["drill-worker-once", "1"]]],
            "recovered_message_id": "1-0",
            "recovery_consumer": "drill-recovery-worker",
            "pending_after_recovery": [0, None, None, None],
            "retry_message_id": "2-0",
            "dead_letter_message_id": "3-0",
            "replayed": 1,
            "atomic_dedup": {"first_event_result": "OK", "duplicate_event_result": None, "duplicate_suppressed": True},
            "final_state_before_cleanup": {"stream_length": 5, "dlq_length": 0, "replay_review_length": 1},
            "final_state_after_cleanup": {"stream_exists": 0, "dlq_exists": 0, "replay_review_exists": 0, "dedup_key_exists": 0},
            "cleanup_verified": True,
            "command_center_config": {"redis_burst_size": 4, "dedup_ttl_seconds": 300, "dlq_after_attempts": 3, "replay_mode": "review_first"},
            "pending_breakdown_after_worker_crash": {"total_pending": 1, "simulated_crash_job_pending": True, "other_core_drill_jobs_pending": 0, "unclaimed_burst_buffer_jobs": 0},
            "pending_breakdown_after_recovery": {"total_pending": 0, "recovered_crash_job_pending": False, "other_core_drill_jobs_pending": 0, "unclaimed_burst_buffer_jobs": 0},
        }
        nats = {"status": "PASS", "role": "connectivity_proof_only", "jetstream_queue_mutation_attempted": False}

        def render_with_verbose(verbose_value: str) -> str:
            with (
                patch.dict(
                    "os.environ",
                    {"RELIEFQUEUE_LIVE_MUTATION_VERBOSE": verbose_value, "RELIEFQUEUE_MUTATION_PROFILE": "heatwave_urban"},
                    clear=True,
                ),
                patch("reliefqueue.live_integrations._postgis_stateful_mutation_drill", return_value=postgis),
                patch("reliefqueue.live_integrations._redis_stateful_mutation_drill", return_value=redis),
                patch("reliefqueue.live_integrations._nats_guidance_proof", return_value=nats),
            ):
                import io
                from contextlib import redirect_stdout

                out = io.StringIO()
                with redirect_stdout(out):
                    self.assertEqual(run_live_integration_command("live-stateful-mutation-drill", self.root, self.report_dir), 0)
                return out.getvalue()

        compact = render_with_verbose("1")
        self.assertIn("Stateful mutation evidence (-v)", compact)
        self.assertIn("- profile: heatwave_urban", compact)
        self.assertIn("PostGIS: PASS", compact)
        self.assertIn("Redis: PASS", compact)
        self.assertIn("Full report:", compact)
        self.assertNotIn("Role ownership", compact)
        self.assertNotIn("Redis resilience scenario", compact)

        rendered = render_with_verbose("2")
        self.assertIn("Stateful mutation evidence (-vv)", rendered)
        self.assertIn("Scenario profile: heatwave_urban", rendered)
        self.assertIn("Role ownership", rendered)
        self.assertIn("Coordinator field scenario", rendered)
        self.assertIn("PostGIS GIS scenario", rendered)
        self.assertIn('case table: "reliefqueue_live".reliefqueue_live_cases', rendered)
        self.assertIn("operation zone polygon inserted", rendered)
        self.assertIn("spatial assignment verified: True", rendered)
        self.assertIn("case_id inserted: stateful-mutation-test", rendered)
        self.assertIn("Command center runtime scenario", rendered)
        self.assertIn("Redis resilience scenario", rendered)
        self.assertIn("pending breakdown after worker crash", rendered)
        self.assertIn("simulated crashed worker message id", rendered)
        self.assertIn("atomic duplicate suppression", rendered)
        self.assertIn("dead letter stream", rendered)
        self.assertIn("cleanup remaining rows: 0", rendered)

    def test_masked_contact_create_dry_run_returns_success_with_draft_session(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(run_live_integration_command("masked-contact-create-dry-run", self.root, self.report_dir), 0)

        result_path = self.report_dir / "live_integrations" / "masked-contact" / "masked_contact_create_dry_run.json"
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["session_status"], "draft")
        self.assertEqual(payload["session"]["status"], "draft")
        self.assertFalse(payload["provider_mutation_attempted"])
        self.assertFalse(payload["live_call_attempted"])


    def test_configured_vllm_bad_endpoint_fails_negative_control(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "AI_MODE": "openai_compatible",
                "OPENAI_COMPAT_BASE_URL": "http://127.0.0.1:9/v1",
                "OPENAI_COMPAT_API_KEY": "test-key",
                "OPENAI_COMPAT_MODEL": "test-model",
                "AI_SEND_PRIVATE_TEXT": "false",
                "AI_TIMEOUT_SECONDS": "1",
                "AI_MAX_RETRIES": "0",
                "AI_HTTP_USER_AGENT": "ReliefQueueAI/0.1 OpenAICompatibleClient",
                "AI_RESPONSE_FORMAT": "json_object",
            },
            clear=True,
        ):
            self.assertEqual(run_live_integration_command("vllm-live-smoke", self.root, self.report_dir), 1)
        payload = json.loads(
            (
                self.report_dir
                / "live_integrations"
                / "ai-model-endpoint"
                / "vllm_live_smoke.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(payload["status"], "FAIL")
        self.assertTrue(payload["provider_call_attempted"])
        self.assertFalse(payload["private_text_sent"])
        self.assertTrue(payload["human_review_required"])
        self.assertFalse(payload["secret_values_printed"])
        self.assertNotIn("test-key", json.dumps(payload))


    def test_amd_live_report_separates_openai_smoke_from_benchmark_claims(self) -> None:
        out_dir = self.report_dir / "live_integrations" / "ai-model-endpoint"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "vllm_live_status.json").write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "ai_mode": "openai_compatible",
                    "redacted_endpoint": "https://api.fireworks.ai/inference/v1",
                    "secret_values_printed": False,
                }
            ),
            encoding="utf-8",
        )
        (out_dir / "vllm_live_smoke.json").write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "ai_mode": "openai_compatible",
                    "redacted_endpoint": "https://api.fireworks.ai/inference/v1",
                    "provider_call_attempted": True,
                    "private_text_sent": False,
                    "sampled_cases": 1,
                    "successful_enrichments": 1,
                    "human_review_required": True,
                    "secret_values_printed": False,
                }
            ),
            encoding="utf-8",
        )
        (out_dir / "amd_live_benchmark_500.json").write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "requested_count": 500,
                    "sampled_for_endpoint": 50,
                    "health_status": "success",
                    "provider_call_attempted": True,
                    "private_text_sent": False,
                }
            ),
            encoding="utf-8",
        )

        self.assertEqual(run_live_integration_command("amd-live-report", self.root, self.report_dir), 0)

        payload = json.loads((out_dir / "amd_live_report.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "PASS")
        self.assertTrue(payload["smoke_found"])
        self.assertEqual(payload["smoke_status"], "PASS")
        self.assertEqual(payload["provider_family"], "openai_compatible")
        self.assertEqual(payload["sampled_cases"], 1)
        self.assertEqual(payload["successful_enrichments"], 1)
        self.assertFalse(payload["private_text_sent"])
        self.assertTrue(payload["human_review_required"])
        self.assertFalse(payload["amd_cloud_verified"])
        self.assertEqual(payload["benchmark_type"], "smoke_not_benchmark")

        markdown = (out_dir / "amd_live_report.md").read_text(encoding="utf-8")
        self.assertIn("## Endpoint smoke evidence", markdown)
        self.assertIn("provider_family: openai_compatible", markdown)
        self.assertIn("benchmark_type: smoke_not_benchmark", markdown)
        self.assertIn("amd_cloud_verified: false", markdown)
        self.assertIn("private_text_sent: false", markdown)
        self.assertIn("requested_count: 500", markdown)
        self.assertIn("adapter boundary only", markdown)
        self.assertNotIn("Synthetic benchmark evidence only", markdown)

    def test_amd_live_report_fails_when_existing_smoke_failed(self) -> None:
        out_dir = self.report_dir / "live_integrations" / "ai-model-endpoint"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "vllm_live_smoke.json").write_text(
            json.dumps(
                {
                    "status": "FAIL",
                    "ai_mode": "openai_compatible",
                    "redacted_endpoint": "https://api.fireworks.ai/inference/v1",
                    "provider_call_attempted": True,
                    "private_text_sent": False,
                    "sampled_cases": 1,
                    "successful_enrichments": 0,
                    "human_review_required": True,
                    "secret_values_printed": False,
                }
            ),
            encoding="utf-8",
        )

        self.assertEqual(run_live_integration_command("amd-live-report", self.root, self.report_dir), 1)
        payload = json.loads((out_dir / "amd_live_report.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "FAIL")
        self.assertTrue(payload["smoke_failed"])
        self.assertFalse(payload["private_text_sent"])
        self.assertFalse(payload["amd_cloud_verified"])

    def test_phase_contract_env_names_and_confirmation_flags_are_preserved(self) -> None:
        source = (ROOT / "src" / "reliefqueue" / "live_integrations.py").read_text(encoding="utf-8")
        for expected in [
            "RELIEFQUEUE_POSTGIS_DSN",
            "RELIEFQUEUE_REDIS_URL",
            "RELIEFQUEUE_NATS_URL",
            "ODK_CENTRAL_BASE_URL",
            "RAPIDPRO_BASE_URL",
            "WHATSAPP_VERIFY_TOKEN",
            "TWILIO_MESSAGING_SERVICE_SID",
            "MASKED_CONTACT_LIVE_CONFIRM",
            "I_UNDERSTAND_REAL_CONTACT_PROVIDER_ACTION",
            "QUEUE_REPLAY_CONFIRM",
            "I_UNDERSTAND_REPLAY",
        ]:
            self.assertIn(expected, source)
        self.assertNotIn("RELIEFQUEUE_CONFIRM_MASKED_CONTACT_MUTATION", source)

    def test_required_phase_output_paths_are_written(self) -> None:
        with patch.dict("os.environ", {"AI_MODE": "mock"}, clear=True):
            self.assertEqual(run_live_integration_command("channel-normalize-smoke", self.root, self.report_dir), 0)
            self.assertEqual(run_live_integration_command("live-pilot-drill", self.root, self.report_dir), 0)
            self.assertEqual(run_live_integration_command("live-pilot-reviewer-pack", self.root, self.report_dir), 0)
        self.assertTrue((self.report_dir / "channel_ingress" / "normalized_messages.jsonl").exists())
        self.assertTrue((self.report_dir / "live_pilot_drill" / "status.json").exists())
        self.assertTrue((self.report_dir / "live_pilot_drill" / "timeline.jsonl").exists())
        self.assertTrue((self.report_dir / "live_pilot_reviewer_pack" / "reviewer_feedback_template.json").exists())

    def test_queue_replay_requires_exact_confirmation(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(run_live_integration_command("queue-live-enqueue-demo", self.root, self.report_dir), 0)
            self.assertEqual(run_live_integration_command("queue-live-worker-once", self.root, self.report_dir), 0)
            self.assertEqual(run_live_integration_command("queue-live-dlq-report", self.root, self.report_dir), 0)
            self.assertEqual(run_live_integration_command("queue-live-replay-dlq", self.root, self.report_dir), 0)
        payload = json.loads((self.report_dir / "live_integrations" / "operations-queue" / "queue_live_replay_dlq.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "SKIP")
        self.assertFalse(payload["replay_attempted"])

    def test_configured_postgis_bad_dsn_fails_negative_control(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "RELIEFQUEUE_POSTGIS_DSN": "postgresql://reliefqueue:reliefqueue@127.0.0.1:1/reliefqueue",
                "RELIEFQUEUE_POSTGIS_SCHEMA": "reliefqueue_live",
                "RELIEFQUEUE_POSTGIS_CONNECT_TIMEOUT_SECONDS": "1",
            },
            clear=True,
        ):
            self.assertEqual(run_live_integration_command("postgis-live-query", self.root, self.report_dir), 1)
        payload = json.loads(
            (
                self.report_dir
                / "live_integrations"
                / "geospatial-store"
                / "postgis_live_query.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(payload["status"], "FAIL")
        self.assertTrue(payload["query_attempted"])
        self.assertFalse(payload["secret_values_printed"])

    def test_configured_redis_bad_url_fails_negative_control(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "RELIEFQUEUE_REDIS_URL": "redis://127.0.0.1:1/0",
                "RELIEFQUEUE_QUEUE_BACKEND": "redis",
                "RELIEFQUEUE_QUEUE_NAME": "reliefqueue-live-intake-negative-control",
            },
            clear=True,
        ):
            self.assertEqual(run_live_integration_command("queue-live-worker-once", self.root, self.report_dir), 1)
        payload = json.loads(
            (
                self.report_dir
                / "live_integrations"
                / "operations-queue"
                / "queue_live_worker_once.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(payload["status"], "FAIL")
        self.assertEqual(payload["worker_mode"], "once_redis")
        self.assertFalse(payload["secret_values_printed"])

    def test_live_health_fails_for_bad_configured_local_services(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "RELIEFQUEUE_POSTGIS_DSN": "postgresql://reliefqueue:reliefqueue@127.0.0.1:1/reliefqueue",
                "RELIEFQUEUE_REDIS_URL": "redis://127.0.0.1:1/0",
                "RELIEFQUEUE_QUEUE_BACKEND": "redis",
            },
            clear=True,
        ):
            self.assertEqual(run_live_integration_command("live-health", self.root, self.report_dir), 1)
        payload = json.loads(
            (
                self.report_dir
                / "live_integrations"
                / "system-health"
                / "live_health.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(payload["status"], "FAIL")
        self.assertEqual(payload["checks"]["postgis"]["status"], "FAIL")
        self.assertEqual(payload["checks"]["queue"]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
