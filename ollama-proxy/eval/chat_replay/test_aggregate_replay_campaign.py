from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import hmac
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aggregate_replay_campaign as campaign
from chat_replay import _canonical


NOW = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
KEY = b"campaign-test-identity-key-at-least-32-bytes"


def _sign_report(report):
    report["run_binding_sha256"] = hashlib.sha256(_canonical({
        "source_structural_sha256": report["structural_sha256"],
        "source_evidence": report["source_evidence"],
        "runtime_profile": report["runtime_profile"],
        "response_rows": report["response_rows"],
        "response_sampling": report["response_sampling"],
    })).hexdigest()
    unsigned = dict(report)
    unsigned.pop("report_hmac_sha256", None)
    report["report_hmac_sha256"] = hmac.new(
        KEY,
        campaign.REPORT_HMAC_DOMAIN + _canonical(unsigned),
        hashlib.sha256,
    ).hexdigest()


def _sign_score(score):
    unsigned = dict(score)
    unsigned.pop("score_hmac_sha256", None)
    score["score_hmac_sha256"] = hmac.new(
        KEY,
        campaign.SCORE_HMAC_DOMAIN + _canonical(unsigned),
        hashlib.sha256,
    ).hexdigest()


def _source_label_hmac(source_structural_sha256):
    return hmac.new(
        KEY,
        campaign.SOURCE_LABEL_HMAC_DOMAIN + _canonical({
            "source_structural_sha256": source_structural_sha256,
            "labels": [
                {"seq": 1, "expected_action": "respond"},
                {"seq": 2, "expected_action": "ignore"},
            ],
        }),
        hashlib.sha256,
    ).hexdigest()


def _artifacts():
    manifest = {
        "schema_version": campaign.MANIFEST_SCHEMA,
        "local_only": True,
        "campaign_id": "study",
        "operator_attestation": {
            "permission_scope_verified": True,
            "privacy_review_completed": True,
            "retention_and_revocation_checked": True,
            "exclusive_local_model_session": True,
            "reviewed_at": "2026-01-01T11:00:00Z",
            "valid_until": "2026-01-01T13:00:00Z",
            "reviewer_role": "operator",
        },
        "runs": [],
    }
    files = {"manifest.json": manifest}
    for slot_index, slot in enumerate(campaign.SLOTS):
        for phase_index, phase in enumerate(("opening", "middle")):
            pair_id = f"p{slot_index}{phase_index}"
            source_identity = f"{slot_index + 1:x}" * 64
            exact_capture = hashlib.sha256(f"{slot}:{phase}".encode()).hexdigest()
            source_hash = hashlib.sha256(f"source:{slot}:{phase}".encode()).hexdigest()
            for gate in campaign.GATES:
                name = f"{pair_id}-{gate}"
                runtime = {
                    **campaign.EXPECTED_RUNTIME,
                    "epistemic_confidence_enabled": gate == "on",
                }
                evidence = {
                    "provider": "chzzk" if slot != "channel_c" else "soop",
                    "source_identity_hmac": source_identity,
                    "exact_capture_hmac": exact_capture,
                }
                response = "epistemic_reference" if gate == "on" else "normal"
                response_hmac = hmac.new(
                    KEY,
                    b"airi.chat-replay-response.v1\0" + b"1\0response",
                    hashlib.sha256,
                ).hexdigest()
                report = {
                    "schema_version": campaign.REPLAY_SCHEMA,
                    "event_count": 300,
                    "event_kinds": {"chat": 300},
                    "timing_buckets": {"under_1s": 1, "5s_to_15s": 299},
                    "duplicate_count": 299,
                    "noise_count": 0,
                    "delivered_count": 1,
                    "response_count": 1,
                    "response_rows": [{
                        "seq": 1,
                        "outcome": response,
                        "response_char_count": 8,
                        "response_hmac_sha256": response_hmac,
                    }],
                    "response_sampling": {
                        "policy_id": "offline_fixed_5s_response_sampler_v1",
                        "fixed_window_ms": 5000,
                        "fixed_5s_batch_count": 300,
                        "candidate_batch_count": 1,
                        "no_reply_batch_count": 0,
                        "baseline_eligible_count": 1,
                        "selected_event_count": 1,
                        "eligible_not_selected_count": 0,
                        "per_batch_limit": 1,
                        "selection_rate": 1.0,
                        "reason_counts": {"question": 1},
                    },
                    "response_outcome_counts": {response: 1},
                    "outcome_by_surface_signal": {"question_mark": {response: 1}},
                    "surface_signal_counts": {
                        "question_mark": 300,
                        "source_text_repeat": 299,
                    },
                    "adjacent_event_count": 299,
                    "adjacent_signal_pair_counts": {
                        "question_mark->question_mark": 299,
                        "question_mark->source_text_repeat": 299,
                        "source_text_repeat->question_mark": 298,
                        "source_text_repeat->source_text_repeat": 298,
                    },
                    "max_events_in_rolling_5s": 1,
                    "capture_profile": {"source_slot": slot, "phase": phase},
                    "flow": {
                        "duration_ms": 1_800_000,
                        "gap_p50_ms": 6_020,
                        "gap_p95_ms": 6_021,
                        "gap_max_ms": 6_021,
                        "interarrival_rate_per_minute": 9.966667,
                        "active_fixed_5s_bins": 300,
                        "rolling_5s_burst_threshold": 5,
                        "rolling_5s_burst_start_count": 0,
                        "duplicate_rate": 0.996667,
                        "noise_rate": 0.0,
                        "eligible_rate": 0.003333,
                        "repeat_cluster_count": 1,
                        "max_repeat_cluster_size": 300,
                    },
                    "structural_sha256": source_hash,
                    "runtime_profile": runtime,
                    "source_evidence": evidence,
                }
                _sign_report(report)
                observation = {
                    "atmosphere": "calm",
                    "pace": "steady",
                    "context_pressure": "low",
                    "dominant_patterns": ["question_wave"],
                }
                quality = {
                    field: {"pass_count": 1, "pass_rate": 1.0}
                    for field in campaign.QUALITY_FIELDS
                }
                score = {
                    "schema_version": campaign.SCORE_SCHEMA,
                    "capture_profile": report["capture_profile"],
                    "source_observation": observation,
                    "runtime_profile": runtime,
                    "source_evidence": evidence,
                    "run_binding_sha256": report["run_binding_sha256"],
                    "row_count": 300,
                    "reviewed_response_count": 1,
                    "replay_selector": {
                        "tp": 1, "fp": 0, "fn": 0, "tn": 299,
                        "precision": 1.0, "recall": 1.0, "f1": 1.0,
                        "noise_delivery_count": 0,
                        "source_repeat_delivery_count": 0,
                    },
                    "response_quality": quality,
                    "critical_failure_count": 0,
                    "critical_failure_counts": {
                        **{field: 0 for field in campaign.CRITICAL_FIELDS},
                        "total_critical_rows": 0,
                    },
                    "source_label_hmac_sha256": _source_label_hmac(source_hash),
                    "source_structural_sha256": source_hash,
                    "structural_sha256": hashlib.sha256(f"score:{name}".encode()).hexdigest(),
                }
                _sign_score(score)
                report_name = f"{name}.json"
                score_name = f"{name}-score.json"
                manifest["runs"].append({
                    "pair_id": pair_id,
                    "gate": gate,
                    "replay_report": report_name,
                    "human_score_report": score_name,
                })
                files[report_name] = report
                files[score_name] = score
    return files


def _resign_pair(files, report_name):
    _sign_report(files[report_name])
    score_name = report_name.removesuffix(".json") + "-score.json"
    score = files[score_name]
    report = files[report_name]
    score["capture_profile"] = report["capture_profile"]
    score["runtime_profile"] = report["runtime_profile"]
    score["source_evidence"] = report["source_evidence"]
    score["run_binding_sha256"] = report["run_binding_sha256"]
    score["source_structural_sha256"] = report["structural_sha256"]
    _sign_score(score)


class CampaignAggregationTests(unittest.TestCase):
    def run_campaign(self, files):
        def read(path, _parent):
            return deepcopy(files[path.name])

        with (
            patch.object(campaign, "_read", side_effect=read),
            patch.object(campaign, "_secure_inside", return_value=True),
            patch.object(campaign, "read_identity_key", return_value=KEY),
            patch.object(campaign, "write_atomic_json") as write,
        ):
            result = campaign.aggregate_campaign(
                campaign.HERE / "private-replays" / "manifest.json",
                campaign.HERE / "reports" / "out.json",
                campaign.HERE / "local-replay-intake" / "identity.key",
                now=NOW,
            )
        return result, write

    def assert_invalid(self, files):
        with self.assertRaises(campaign.CampaignFormatError):
            self.run_campaign(files)

    def test_happy_campaign_is_content_free_and_deterministic(self):
        result, write = self.run_campaign(_artifacts())
        again, _ = self.run_campaign(_artifacts())
        self.assertEqual(result, again)
        self.assertEqual(result["coverage"], {
            "pair_count": 6,
            "run_count": 12,
            "anonymous_slot_phase_sets": {
                "slot_1": ["middle", "opening"],
                "slot_2": ["middle", "opening"],
                "slot_3": ["middle", "opening"],
            },
        })
        self.assertEqual(result["source_pattern_aggregates"]["capture_count"], 6)
        self.assertEqual(result["source_pattern_aggregates"]["event_count"], 1800)
        self.assertEqual(result["on_minus_off"]["epistemic_outcome_rate_delta"], 1.0)
        self.assertEqual(result["campaign_critical_gate"], "pass")
        self.assertIn("donation_callout", campaign.EVENT_KINDS)
        self.assertFalse(result["automatic_adoption"])
        self.assertTrue(result["user_confirmation_required"])
        serialized = str(result)
        for forbidden in ("chzzk", "soop", "p00", ".json", "a" * 64, "92a9ba2e"):
            self.assertNotIn(forbidden, serialized)
        write.assert_called_once()

    def test_missing_coverage_and_pairing_fail_closed(self):
        for mode in (
            "slot", "phase", "arm", "duplicate_path", "duplicate_path_case_alias",
            "output_overwrite", "output_overwrite_case_alias",
        ):
            with self.subTest(mode=mode):
                files = _artifacts()
                manifest = files["manifest.json"]
                if mode == "slot":
                    manifest["runs"] = [run for run in manifest["runs"] if not run["pair_id"].startswith("p2")]
                elif mode == "phase":
                    for gate in campaign.GATES:
                        report_name = f"p01-{gate}.json"
                        files[report_name]["capture_profile"]["phase"] = "opening"
                        _resign_pair(files, report_name)
                elif mode == "arm":
                    manifest["runs"].append(deepcopy(manifest["runs"][0]))
                elif mode == "duplicate_path":
                    manifest["runs"][1]["human_score_report"] = manifest["runs"][0]["human_score_report"]
                elif mode == "duplicate_path_case_alias":
                    manifest["runs"][1]["human_score_report"] = manifest["runs"][0]["human_score_report"].upper()
                elif mode == "output_overwrite":
                    files["out.json"] = files[manifest["runs"][0]["replay_report"]]
                    manifest["runs"][0]["replay_report"] = "out.json"
                else:
                    files["OUT.JSON"] = files[manifest["runs"][0]["replay_report"]]
                    manifest["runs"][0]["replay_report"] = "OUT.JSON"
                self.assert_invalid(files)

    def test_source_runtime_gate_and_score_mismatches_fail_closed(self):
        for mode in ("identity", "shared_identity", "capture_reuse", "runtime", "gate", "score", "observation", "source_labels", "sampling"):
            with self.subTest(mode=mode):
                files = _artifacts()
                if mode == "identity":
                    report = files["p00-on.json"]
                    report["source_evidence"]["source_identity_hmac"] = "e" * 64
                    _resign_pair(files, "p00-on.json")
                elif mode == "shared_identity":
                    identity = files["p00-off.json"]["source_evidence"]["source_identity_hmac"]
                    for phase in (0, 1):
                        for gate in campaign.GATES:
                            name = f"p1{phase}-{gate}.json"
                            files[name]["source_evidence"]["source_identity_hmac"] = identity
                            _resign_pair(files, name)
                elif mode == "capture_reuse":
                    exact = files["p00-off.json"]["source_evidence"]["exact_capture_hmac"]
                    for gate in campaign.GATES:
                        name = f"p01-{gate}.json"
                        files[name]["source_evidence"]["exact_capture_hmac"] = exact
                        _resign_pair(files, name)
                elif mode == "runtime":
                    files["p00-on.json"]["runtime_profile"]["history_turns"] = 9
                    _resign_pair(files, "p00-on.json")
                elif mode == "gate":
                    files["p00-on.json"]["runtime_profile"]["epistemic_confidence_enabled"] = False
                    _resign_pair(files, "p00-on.json")
                elif mode == "score":
                    files["p00-on-score.json"]["run_binding_sha256"] = "e" * 64
                    _sign_score(files["p00-on-score.json"])
                elif mode == "observation":
                    files["p00-on-score.json"]["source_observation"]["atmosphere"] = "tense"
                    _sign_score(files["p00-on-score.json"])
                elif mode == "source_labels":
                    files["p00-on-score.json"]["source_label_hmac_sha256"] = "e" * 64
                    _sign_score(files["p00-on-score.json"])
                else:
                    files["p00-on.json"]["response_sampling"]["reason_counts"] = {"donation_callout": 1}
                    _resign_pair(files, "p00-on.json")
                self.assert_invalid(files)

    def test_runtime_profile_requires_exact_json_types(self):
        for name, value in (
            ("temperature", False),
            ("history_turns", 8.0),
            ("max_model_calls", 1441.0),
            ("request_byte_limit", 12288.0),
        ):
            with self.subTest(name=name):
                files = _artifacts()
                for gate in campaign.GATES:
                    report = files[f"p00-{gate}.json"]
                    report["runtime_profile"][name] = value
                    _resign_pair(files, f"p00-{gate}.json")
                    score = files[f"p00-{gate}-score.json"]
                    score["runtime_profile"][name] = value
                    score["run_binding_sha256"] = report["run_binding_sha256"]
                    _sign_score(score)
                self.assert_invalid(files)

    def test_tampering_and_stale_attestation_fail_closed(self):
        for mode in ("report_hmac", "score_hmac", "attestation", "stale", "reviews", "leak_key", "critical_union"):
            with self.subTest(mode=mode):
                files = _artifacts()
                if mode == "report_hmac":
                    files["p00-off.json"]["noise_count"] = 1
                elif mode == "score_hmac":
                    files["p00-off-score.json"]["source_observation"]["pace"] = "bursty"
                elif mode == "attestation":
                    files["manifest.json"]["operator_attestation"]["permission_scope_verified"] = False
                elif mode == "stale":
                    files["manifest.json"]["operator_attestation"]["valid_until"] = "2026-01-01T12:00:00Z"
                elif mode == "reviews":
                    score = files["p00-off-score.json"]
                    score["reviewed_response_count"] = 0
                    _sign_score(score)
                elif mode == "leak_key":
                    report = files["p00-off.json"]
                    report["event_kinds"]["creator identity"] = 0
                    _resign_pair(files, "p00-off.json")
                else:
                    score = files["p00-off-score.json"]
                    score["critical_failure_counts"]["privacy_ok"] = 1
                    score["critical_failure_counts"]["total_critical_rows"] = 0
                    score["critical_failure_count"] = 0
                    _sign_score(score)
                self.assert_invalid(files)

    def test_critical_failure_is_a_valid_failed_campaign(self):
        files = _artifacts()
        score = files["p00-on-score.json"]
        score["response_quality"]["privacy_ok"] = {
            "pass_count": 0, "pass_rate": 0.0,
        }
        score["critical_failure_counts"]["privacy_ok"] = 1
        score["critical_failure_counts"]["total_critical_rows"] = 1
        score["critical_failure_count"] = 1
        _sign_score(score)
        result, _ = self.run_campaign(files)
        self.assertEqual(result["campaign_critical_gate"], "fail")
        self.assertEqual(result["arms"]["on"]["critical_failure_count"], 1)

    def test_long_stream_duration_and_event_count_boundaries_fail_closed(self):
        files = _artifacts()
        for gate in campaign.GATES:
            files[f"p00-{gate}.json"]["flow"]["duration_ms"] = 7_200_000
            files[f"p00-{gate}.json"]["flow"]["interarrival_rate_per_minute"] = 2.491667
            files[f"p00-{gate}.json"]["flow"]["gap_p50_ms"] = 24_080
            files[f"p00-{gate}.json"]["flow"]["gap_p95_ms"] = 24_081
            files[f"p00-{gate}.json"]["flow"]["gap_max_ms"] = 24_081
            files[f"p00-{gate}.json"]["timing_buckets"] = {
                "under_1s": 1, "15s_plus": 299,
            }
            _resign_pair(files, f"p00-{gate}.json")
        self.run_campaign(files)
        for duration in (1_799_999, 7_200_001):
            with self.subTest(duration=duration):
                invalid = _artifacts()
                for gate in campaign.GATES:
                    invalid[f"p00-{gate}.json"]["flow"]["duration_ms"] = duration
                    invalid[f"p00-{gate}.json"]["flow"]["interarrival_rate_per_minute"] = round(299 * 60_000 / duration, 6)
                    _resign_pair(invalid, f"p00-{gate}.json")
                self.assert_invalid(invalid)
        invalid = _artifacts()
        for gate in campaign.GATES:
            report = invalid[f"p00-{gate}.json"]
            report["event_count"] = 299
            report["event_kinds"] = {"chat": 299}
            report["timing_buckets"] = {"under_1s": 299}
            report["adjacent_event_count"] = 298
            _resign_pair(invalid, f"p00-{gate}.json")
        self.assert_invalid(invalid)

    def test_paired_swapped_response_sequence_is_rejected(self):
        files = _artifacts()
        report = files["p00-on.json"]
        report["response_rows"][0]["seq"] = 2
        _resign_pair(files, "p00-on.json")
        self.assert_invalid(files)

    def test_signed_impossible_flow_summaries_are_rejected(self):
        for field, value in (("eligible_rate", 0.5), ("active_fixed_5s_bins", 999)):
            with self.subTest(field=field):
                files = _artifacts()
                for gate in campaign.GATES:
                    files[f"p00-{gate}.json"]["flow"][field] = value
                    _resign_pair(files, f"p00-{gate}.json")
                self.assert_invalid(files)

        files = _artifacts()
        for gate in campaign.GATES:
            report = files[f"p00-{gate}.json"]
            report["duplicate_count"] = 0
            report["surface_signal_counts"].pop("source_text_repeat")
            report["flow"]["duplicate_rate"] = 0.0
            _resign_pair(files, f"p00-{gate}.json")
        self.assert_invalid(files)

        files = _artifacts()
        for gate in campaign.GATES:
            report = files[f"p00-{gate}.json"]
            report["flow"]["gap_max_ms"] = 1
            report["flow"]["gap_p95_ms"] = 1
            report["flow"]["gap_p50_ms"] = 1
            _resign_pair(files, f"p00-{gate}.json")
        self.assert_invalid(files)

    def test_module_has_no_network_imports(self):
        source = (campaign.HERE / "aggregate_replay_campaign.py").read_text(encoding="utf-8")
        for forbidden in ("urllib", "requests", "socket"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
