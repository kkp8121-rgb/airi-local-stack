import json
import io
import hashlib
from contextlib import redirect_stderr, redirect_stdout
import os
import sys
import types
import urllib.error
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark_memory_track as bench
from memory_stage_b import compile_decisions, decision_schema_for_count, decision_schema_for_items, format_stage_b_input, parse_stage_b_decisions
from memory_prompts import STAGE_A_CONVERSATION_SYSTEM_PROMPT, STAGE_A_SYSTEM_PROMPT, STAGE_B_DECISION_SYSTEM_PROMPT


class MemoryBenchmarkTests(unittest.TestCase):
    def test_ollama_request_disables_thinking(self):
        class Response:
            def read(self): return b'{"message":{"content":"{\\"extracted\\":[]}"}}'
            def __enter__(self): return self
            def __exit__(self, *_): return False

        with patch("urllib.request.urlopen", return_value=Response()) as urlopen:
            self.assertEqual(
                bench.ollama_chat("http://ollama/api/chat", "model", "system", "user", {"type": "object"}),
                '{"extracted":[]}',
            )
        request = urlopen.call_args.args[0]
        self.assertIs(json.loads(request.data.decode("utf-8"))["think"], False)

    def test_stage_a_contract_selection_and_active_prompt_hash(self):
        fixtures = {"extraction": [{"id": "x", "character": "speaker", "turns": "[turn 1] hi", "candidates": [], "expected_stage_a": [], "expected_stage_b": []}]}
        for contract, expected, comparison in (
            ("conversation-v2b", STAGE_A_CONVERSATION_SYSTEM_PROMPT, "v2.1_stage_a_legacy_to_conversation_v2b_same_options"),
            ("legacy", STAGE_A_SYSTEM_PROMPT, "v2_to_v2.1_same_options"),
        ):
            with self.subTest(contract=contract):
                args = bench.build_parser().parse_args(["--stage-a-contract", contract])
                seen = []
                def fake(*call):
                    seen.append(call[2])
                    return '{"extracted":[]}'
                result = bench.run_extraction(args, fixtures, fake)
                self.assertEqual(seen, [expected])
                self.assertEqual(result["stage_a_contract"], contract)
                self.assertEqual(result["comparison_contract"], comparison)
                self.assertEqual(bench.comparison_contract_for_stage_a(contract), comparison)
                metadata = bench.reproducibility_metadata(bench.FIXTURES, contract)
                self.assertEqual(metadata["stage_a_active_prompt_sha256"], hashlib.sha256(expected.encode("utf-8")).hexdigest())

    def test_item_aware_schema_scopes_indexes_and_candidate_kinds(self):
        extracted = [
            {"kind": "entity"},
            {"kind": "fact"},
        ]
        candidates = [{"alias": "e0", "kind": "entity"}, {"alias": "f0", "kind": "fact"}]
        schema = decision_schema_for_items(extracted, candidates)
        alternatives = schema["properties"]["decisions"]["items"]["oneOf"]
        fact_branches = [entry for entry in alternatives if entry["properties"]["sourceItemIndex"]["enum"] == [1]]
        self.assertEqual({entry["properties"]["action"]["const"] for entry in fact_branches}, {"add", "update", "noop", "supersede"})
        existing = [entry for entry in fact_branches if entry["properties"]["action"]["const"] != "add"]
        self.assertTrue(all(entry["properties"]["candidateAlias"]["enum"] == ["f0"] for entry in existing))
        self.assertNotIn("e0", repr(fact_branches))
        self.assertEqual(schema["properties"]["decisions"]["minItems"], 2)
        self.assertEqual(bench.schema_sha256(schema), bench.schema_sha256(decision_schema_for_items(extracted, candidates)))

    def test_item_aware_schema_without_same_kind_candidate_is_add_only(self):
        schema = decision_schema_for_items([{"kind": "relation"}], [{"alias": "e0", "kind": "entity"}])
        alternatives = schema["properties"]["decisions"]["items"]["oneOf"]
        self.assertEqual(len(alternatives), 1)
        self.assertEqual(alternatives[0]["properties"]["action"], {"const": "add"})
        empty = decision_schema_for_items([], [])
        self.assertEqual(empty["properties"]["decisions"]["items"], {})

    def test_item_aware_schema_is_bounded_and_grows_linearly(self):
        def encoded_size(count: int, candidate_count: int) -> int:
            extracted = [{"kind": ("entity", "fact", "relation")[index % 3]} for index in range(count)]
            candidates = [{"alias": f"{('e', 'f', 'r')[index % 3]}{index}", "kind": ("entity", "fact", "relation")[index % 3]}
                          for index in range(candidate_count)]
            schema = decision_schema_for_items(extracted, candidates)
            self.assertLessEqual(len(schema["properties"]["decisions"]["items"]["oneOf"]), 12)
            return len(json.dumps(schema, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        small = encoded_size(30, 90)
        large = encoded_size(60, 185)
        self.assertLess(large, 20_000)
        self.assertLess(large, small * 3)

    def test_decision_v2_dynamic_schema_is_exact_and_deterministic(self):
        schema = decision_schema_for_count(2)
        self.assertEqual(schema["properties"]["decisions"]["minItems"], 2)
        self.assertEqual(schema["properties"]["decisions"]["maxItems"], 2)
        actions = schema["properties"]["decisions"]["items"]["oneOf"]
        by_action = {entry["properties"]["action"]["const"]: entry for entry in actions}
        self.assertTrue(all(entry["properties"]["sourceItemIndex"]["maximum"] == 1 for entry in actions))
        self.assertEqual(by_action["add"]["properties"]["candidateAlias"], {"type": "null"})
        self.assertEqual(by_action["update"]["properties"]["reason"], {"type": "null"})
        self.assertEqual(by_action["noop"]["properties"]["reason"], {"type": "null"})
        self.assertEqual(by_action["supersede"]["properties"]["reason"]["maxLength"], 500)
        self.assertEqual(bench.schema_sha256(schema), bench.schema_sha256(decision_schema_for_count(2)))
        self.assertNotEqual(bench.schema_sha256(schema), bench.schema_sha256(decision_schema_for_count(3)))
        empty_index = decision_schema_for_count(0)["properties"]["decisions"]["items"]["oneOf"][0]["properties"]["sourceItemIndex"]
        self.assertNotIn("maximum", empty_index)
        for bad in (-1, True, "2"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError): decision_schema_for_count(bad)

    def test_decision_v1_compiler_copies_and_orders_dependencies(self):
        extracted=[
            {"turnNumber":1,"kind":"relation","subtype":"friend","sourceName":"Ada","targetName":"Bob","content":"friends"},
            {"turnNumber":1,"kind":"entity","subtype":"person","name":"Ada","content":"a"},
            {"turnNumber":1,"kind":"entity","subtype":"person","name":"Bob","content":"b"},
            {"turnNumber":1,"kind":"fact","subtype":"trait","subjectNames":["Ada"],"content":"brave","turnRange":[1,1]},
        ]
        decisions=parse_stage_b_decisions({"decisions":[{"sourceItemIndex":i,"action":"add","candidateAlias":None,"reason":None} for i in range(4)]})["decisions"]
        operations=compile_decisions(extracted,[],decisions)
        self.assertEqual([op["sourceItemIndex"] for op in operations],[1,2,3,0])
        self.assertEqual(operations[-1]["sourceAlias"],"e0")
        self.assertEqual(operations[2]["subjectAliases"],["e0"])
        with self.assertRaises(ValueError): parse_stage_b_decisions({"decisions":[{"sourceItemIndex":True,"action":"add","candidateAlias":None,"reason":None}]})

    def test_decision_formatter_is_compact_and_runtime_shaped(self):
        prompt=format_stage_b_input([{"turnNumber":1,"kind":"entity","subtype":"person","name":"Ada","content":"x"}], [{"alias":"e0","kind":"entity","name":"Ada","content":"x"*600}])
        self.assertNotIn("<extracted>",prompt)
        self.assertLessEqual(len(__import__('json').loads(prompt)["candidates"][0]["content"]),500)
    def test_decision_prompt_matches_null_action_contract(self):
        prompt=STAGE_B_DECISION_SYSTEM_PROMPT
        self.assertIn("candidateAlias=null; reason=null",prompt)
        self.assertIn("exact duplicate",prompt)
        self.assertNotIn("add requires candidateAlias",prompt)
        for action, alias, reason in (("add",None,None),("noop","e0",None),("update","e0",None),("supersede","e0","outdated")):
            parsed=parse_stage_b_decisions({"decisions":[{"sourceItemIndex":0,"action":action,"candidateAlias":alias,"reason":reason}]})
            self.assertEqual(parsed["decisions"][0]["action"],action)
    def test_stage_a_strict_schema(self):
        good = {"extracted":[{"turnNumber":1,"kind":"entity","subtype":"person","name":"{{user}}","content":"조수"}]}
        self.assertEqual(bench.parse_stage_a(json.dumps(good)), good)
        with self.assertRaises(bench.ValidationError):
            bench.parse_stage_a('{"extracted":[{"turnNumber":1,"kind":"person"}]}')
        with self.assertRaises(bench.ValidationError): bench.parse_stage_a("```json\n{}\n```")
        with self.assertRaises(bench.ValidationError): bench.parse_stage_a({"extracted":[{"turnNumber":True,"kind":"entity","subtype":"person","name":"Ada","content":"person"}]})
        with self.assertRaises(bench.ValidationError): bench.parse_stage_a({"extracted":[{"turnNumber":1,"kind":"fact","subtype":"trait","subjectNames":["Ada","Ada"],"content":"x","turnRange":[2,1]}]})

    def test_stage_b_alias_and_reason_validation(self):
        good = {"operations":[{"op":"ADD_ENTITY","sourceItemIndex":0,"sourceTurnNumber":1,"alias":"e10","subtype":"person","name":"{{user}}","content":"조수","turnRange":None,"reason":None}]}
        self.assertEqual(bench.parse_stage_b(good), good)
        bad = dict(good); bad["operations"]=[dict(good["operations"][0], alias="f10")]
        with self.assertRaises(bench.ValidationError): bench.parse_stage_b(bad)
        with self.assertRaises(bench.ValidationError): bench.parse_stage_b({"operations":[{"op":"SUPERSEDE_FACT","sourceItemIndex":0,"sourceTurnNumber":1,"alias":"f0","reason":""}]})
        supersede={"operations":[{"op":"SUPERSEDE_ENTITY","sourceItemIndex":0,"sourceTurnNumber":2,"alias":"e0","subtype":"person","name":"Ada","content":"new","turnRange":[2,2],"reason":"changed"}]}
        self.assertEqual(bench.parse_stage_b(supersede),supersede)
        with self.assertRaises(bench.ValidationError): bench.parse_stage_b({"operations":[{"op":"NOOP","sourceItemIndex":0,"sourceTurnNumber":True,"alias":"f0"}]})
        with self.assertRaises(bench.ValidationError): bench.parse_stage_b({"operations":[{"op":"ADD_FACT","sourceItemIndex":0,"sourceTurnNumber":1,"alias":"f1","subtype":"trait","content":"x","subjectAliases":["e0","e0"],"turnRange":[2,1],"reason":None}]})

    def test_scoring_and_percentiles(self):
        fixture=bench.load_fixtures()["extraction"][0]
        a={"extracted":[{"turnNumber":1,"kind":"entity","subtype":"person","name":"{{user}}","content":"x"},{"turnNumber":1,"kind":"entity","subtype":"organization","name":"달빛 길드","content":"x"},{"turnNumber":1,"kind":"relation","subtype":"소속","sourceName":"하린","targetName":"달빛 길드","content":"x"},{"turnNumber":1,"kind":"entity","subtype":"item","name":"별빛 나침반","content":"x"},{"turnNumber":1,"kind":"relation","subtype":"사용","sourceName":"{{user}}","targetName":"별빛 나침반","content":"x"}]}
        b={"operations":[{"op":"ADD_ENTITY","sourceItemIndex":0,"sourceTurnNumber":1,"alias":"e4","subtype":"person","name":"{{user}}","content":"x","turnRange":None,"reason":None}]}
        score=bench.score_extraction(a,b,fixture)
        self.assertEqual(score["critical_recall"], 1)
        self.assertTrue(score["placeholder_preserved"])
        self.assertEqual(bench.percentile([1,2,3,4], 50), 2.5)
        self.assertEqual(bench.percentile([], 95), None)

    def test_allowed_patterns_do_not_mask_hallucinations(self):
        fixture={"expected_stage_a":[{"kind":"entity","name":"하린"}], "expected_stage_b":[], "allowed":[{"kind":"fact","subtype":"trait"}]}
        accepted={"extracted":[{"kind":"entity","name":"하린"},{"kind":"fact","subtype":"trait"}]}
        self.assertEqual(bench.score_extraction(accepted, {"operations":[]}, fixture)["unexpected"], 0)
        bad={"extracted":[{"kind":"entity","name":"하린"},{"kind":"entity","name":"환각"}]}
        self.assertEqual(bench.score_extraction(bad, {"operations":[]}, fixture)["unexpected"], 1)

    def test_subject_matching_is_unordered_but_duplicate_extraction_fails_coverage(self):
        self.assertTrue(bench._matches({"subjectNames":["B","A"]},{"subjectNames":["A","B"]}))
        a={"extracted":[{"turnNumber":1,"kind":"entity","subtype":"person","name":"Ada","content":"person"},{"turnNumber":1,"kind":"entity","subtype":"person","name":"Ada","content":"person"}]}
        b={"operations":[
            {"op":"ADD_ENTITY","sourceItemIndex":0,"sourceTurnNumber":1,"alias":"e1","subtype":"person","name":"Ada","content":"person","turnRange":None,"reason":None},
            {"op":"ADD_ENTITY","sourceItemIndex":1,"sourceTurnNumber":1,"alias":"e2","subtype":"person","name":"Ada","content":"person","turnRange":None,"reason":None},
        ]}
        self.assertIn("duplicate_extracted_item",bench.stage_b_coverage_diagnostics(a,b,[]))

    def test_scoring_consumes_patterns_once(self):
        fixture={"expected_stage_a":[{"kind":"fact","subtype":"trait","subjectNames":["Ada"]}],"expected_stage_b":[],"allowed":[]}
        stage_a={"extracted":[
            {"kind":"fact","subtype":"trait","subjectNames":["Ada"],"content":"first"},
            {"kind":"fact","subtype":"trait","subjectNames":["Ada"],"content":"second"},
        ]}
        score=bench.score_extraction(stage_a,{"operations":[]},fixture)
        self.assertEqual(score["critical_found"],1)
        self.assertEqual(score["unexpected"],1)

    def test_graph_forward_reference_is_rejected(self):
        a={"extracted":[
            {"turnNumber":1,"kind":"relation","subtype":"friend","sourceName":"Ada","targetName":"Bob","content":"friends"},
            {"turnNumber":1,"kind":"entity","subtype":"person","name":"Ada","content":"person"},
            {"turnNumber":1,"kind":"entity","subtype":"person","name":"Bob","content":"person"},
        ]}
        b={"operations":[
            {"op":"ADD_RELATION","sourceItemIndex":0,"sourceTurnNumber":1,"alias":"r1","subtype":"friend","sourceAlias":"e1","targetAlias":"e2","content":"friends","reason":None},
            {"op":"ADD_ENTITY","sourceItemIndex":1,"sourceTurnNumber":1,"alias":"e1","subtype":"person","name":"Ada","content":"person","turnRange":None,"reason":None},
            {"op":"ADD_ENTITY","sourceItemIndex":2,"sourceTurnNumber":1,"alias":"e2","subtype":"person","name":"Bob","content":"person","turnRange":None,"reason":None},
        ]}
        self.assertIn("graph_forward_reference",bench.stage_b_coverage_diagnostics(a,b,[]))

    def test_connectivity_uses_existing_candidate_person(self):
        stage_a={"extracted":[
            {"kind":"entity","subtype":"organization","name":"Guild"},
            {"kind":"relation","sourceName":"Harin","targetName":"Guild"},
        ]}
        self.assertTrue(bench._connectivity(stage_a,[{"alias":"e0","name":"Harin"}]))

    def test_noop_requires_exact_candidate_identity(self):
        a={"extracted":[{"turnNumber":11,"kind":"fact","subtype":"trait","subjectNames":["Ada"],"content":"honest","turnRange":[11,11]}]}
        b={"operations":[{"op":"NOOP","sourceItemIndex":0,"sourceTurnNumber":11,"alias":"f0"}]}
        matching=[{"alias":"f0","subtype":"trait","content":"honest","subjectNames":["Ada"]}]
        self.assertTrue(bench.stage_b_coverage(a,b,matching))
        mismatch=[{"alias":"f0","subtype":"trait","content":"different","subjectNames":["Ada"]}]
        self.assertIn("noop_candidate_mismatch",bench.stage_b_coverage_diagnostics(a,b,mismatch))
        moment={"extracted":[{"turnNumber":2,"kind":"fact","subtype":"moment","subjectNames":["Ada"],"content":"arrived","turnRange":[2,2]}]}
        unknown={"operations":[{"op":"NOOP","sourceItemIndex":0,"sourceTurnNumber":2,"alias":"f404"}]}
        codes=bench.stage_b_coverage_diagnostics(moment,unknown,[])
        self.assertIn("unknown_existing_alias",codes)
        self.assertIn("noop_candidate_mismatch",codes)

    def test_stage_b_coverage_checks_exact_index_and_relation_direction(self):
        stage_a={"extracted":[
            {"turnNumber":1,"kind":"entity","subtype":"person","name":"Ada","content":"person"},
            {"turnNumber":1,"kind":"relation","subtype":"friend","sourceName":"Ada","targetName":"Bob","content":"friends"},
        ]}
        operations=[
            {"op":"ADD_ENTITY","sourceItemIndex":0,"sourceTurnNumber":1,"alias":"e2","subtype":"person","name":"Ada","content":"person","turnRange":None,"reason":None},
            {"op":"ADD_RELATION","sourceItemIndex":1,"sourceTurnNumber":1,"alias":"r2","subtype":"friend","sourceAlias":"e2","targetAlias":"e1","content":"friends","reason":None},
        ]
        candidates=[{"alias":"e1","name":"Bob"}]
        self.assertTrue(bench.stage_b_coverage(stage_a,{"operations":operations},candidates))
        reversed_ops=[dict(operation) for operation in operations]
        reversed_ops[1].update(sourceAlias="e1",targetAlias="e2")
        self.assertFalse(bench.stage_b_coverage(stage_a,{"operations":reversed_ops},candidates))
        duplicate=[dict(operation) for operation in operations]
        duplicate[1]["sourceItemIndex"]=0
        self.assertFalse(bench.stage_b_coverage(stage_a,{"operations":duplicate},candidates))

    def test_stage_b_diagnostics_are_structural_and_alias_safe(self):
        a={"extracted":[{"turnNumber":1,"kind":"entity","subtype":"person","name":"Ada","content":"person"}]}
        b={"operations":[{"op":"UPDATE_ENTITY","sourceItemIndex":0,"sourceTurnNumber":1,"alias":"e404","subtype":"person","name":"Ada","content":"person","turnRange":None,"reason":None}]}
        codes=bench.stage_b_coverage_diagnostics(a,b,[])
        self.assertEqual(codes,["unknown_existing_alias"])
        self.assertNotIn("e404",repr(codes))
        add={"operations":[{"op":"ADD_ENTITY","sourceItemIndex":0,"sourceTurnNumber":1,"alias":"e0","subtype":"person","name":"Ada","content":"person","turnRange":None,"reason":None}]}
        self.assertIn("add_alias_collision",bench.stage_b_coverage_diagnostics(a,add,[{"alias":"e0","name":"Other"}]))

    def test_num_ctx_and_stage_latency_reported(self):
        args=bench.build_parser().parse_args(["--num-ctx","8192"]); seen=[]
        def fake(*call):
            seen.append((call[-2],call[-1]))
            if "extract atomic" in call[2]:
                return '{"extracted":[]}'
            return '{"operations":[]}'
        result=bench.run_extraction(args, bench.load_fixtures(), fake)
        self.assertTrue(seen and all(x == (8192,0) for x in seen))
        self.assertEqual(set(result["latency"]), {"stage_a","stage_b","total"})
        self.assertIn("p50_ms", result["latency"]["stage_a"])
        self.assertTrue(all("content" not in row and "messages" not in row for row in result["fixtures"]))
        self.assertFalse(result["gate_pass"])
        row=result["fixtures"][0]
        self.assertIn("stage_a_count",row); self.assertIn("stage_b_count",row)
        self.assertEqual(row["failure_codes"],sorted(set(row["failure_codes"])))
        self.assertIn("failure_code_counts",result)
        self.assertNotIn("content",repr(result["failure_code_counts"]))

    def test_extraction_fail_fast_is_opt_in_and_reports_attempted_rows(self):
        def fixture(identifier, expected_stage_a):
            return {"id":identifier,"character":"c","turns":"t","candidates":[],
                    "expected_stage_a":expected_stage_a,"expected_stage_b":[]}
        bad = fixture("bad", [{"kind":"entity","name":"missing"}])
        later = fixture("later", [])

        default_calls=[]
        def default_chat(*_):
            default_calls.append(1)
            return '{"extracted":[]}'
        default = bench.run_extraction(bench.build_parser().parse_args([]), {"extraction":[bad,later]}, default_chat)
        self.assertEqual(len(default_calls), 2)
        self.assertEqual(default["attempted_fixture_ids"], ["bad","later"])
        self.assertEqual(default["attempted_row_count"], 2)
        self.assertFalse(default["fail_fast"])
        self.assertFalse(default["stopped_early"])
        self.assertIsNone(default["stop_reason"])

        transport_calls=[]
        def transport_chat(*_):
            transport_calls.append(1)
            raise urllib.error.URLError("offline")
        transport = bench.run_extraction(bench.build_parser().parse_args(["--fail-fast"]), {"extraction":[bad,later]}, transport_chat)
        self.assertEqual(len(transport_calls), 1)
        self.assertEqual(transport["attempted_row_count"], 1)
        self.assertEqual(transport["fixture_ids"], ["bad"])
        self.assertTrue(transport["stopped_early"])
        self.assertEqual(transport["stop_reason"], "stage_a_transport")

        quality = bench.run_extraction(bench.build_parser().parse_args(["--fail-fast"]), {"extraction":[bad,later]}, default_chat)
        self.assertEqual(quality["attempted_row_count"], 1)
        self.assertEqual(quality["attempted_fixture_ids"], ["bad"])
        self.assertEqual(quality["stop_reason"], "gate_row_failed")

        success_then_failure = bench.run_extraction(bench.build_parser().parse_args(["--fail-fast"]), {"extraction":[later,bad]}, default_chat)
        self.assertEqual(success_then_failure["attempted_row_count"], 2)
        self.assertEqual(success_then_failure["attempted_fixture_ids"], ["later","bad"])
        self.assertEqual(success_then_failure["fixture_ids"], ["bad","later"])
        self.assertEqual(success_then_failure["failure_code_counts"], {})

    def test_report_config_records_fail_fast(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(bench.main(["--mode","inventory","--fail-fast","--report",str(report)]), 0)
            config = json.loads(report.read_text(encoding="utf-8"))["config"]
            self.assertTrue(config["fail_fast"])
            self.assertIs(config["think"], False)

    def test_stage_b_failure_preserves_stage_a_diagnostics(self):
        args=bench.build_parser().parse_args([])
        fixtures={"extraction":[{"id":"x","character":"x","turns":"x","candidates":[],"expected_stage_a":[{"kind":"entity","name":"Ada"}],"expected_stage_b":[{"op":"ADD_ENTITY"}]}]}
        calls=[]
        def fake(*_):
            calls.append(1)
            return '{"extracted":[{"turnNumber":1,"kind":"entity","subtype":"person","name":"Ada","content":"person"}]}' if len(calls)==1 else '{"decisions":[{"sourceItemIndex":0,"action":"add","candidateAlias":"bad","reason":null}]}'
        result=bench.run_extraction(args,fixtures,fake); row=result["fixtures"][0]
        self.assertTrue(row["stage_a_schema_pass"]); self.assertFalse(row["stage_b_schema_pass"]); self.assertFalse(row["schema_pass"])
        self.assertEqual(row["error_stage"],"stage_b_parse"); self.assertEqual(row["stage_a_critical_recall"],1.0)
        self.assertEqual(result["stage_a_schema_pass_rate"],1.0); self.assertEqual(result["schema_pass_rate"],0.0); self.assertFalse(result["gate_pass"])

    def test_reproducibility_hashes_and_model_digest_validation(self):
        first=bench.reproducibility_metadata(bench.FIXTURES); second=bench.reproducibility_metadata(bench.FIXTURES)
        self.assertEqual(first,second); self.assertTrue(all(len(value)==64 for value in first.values()))
        self.assertNotIn("You extract",repr(first)); self.assertEqual(bench.model_digest("AB"*32),"ab"*32)
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit): bench.build_parser().parse_args(["--model-digest","bad"])

    def test_extraction_fixture_filter_is_bounded_and_rejects_unknown_id(self):
        args=bench.build_parser().parse_args(["--fixture-id","conversation_skip"])
        def fake(*call):
            return '{"extracted":[]}' if "extract atomic" in call[2] else '{"operations":[]}'
        result=bench.run_extraction(args,bench.load_fixtures(),fake)
        self.assertEqual(result["fixture_ids"],["conversation_skip"])
        self.assertTrue(result["gate_pass"])
        bad=bench.build_parser().parse_args(["--fixture-id","missing"])
        with self.assertRaises(ValueError):
            bench.run_extraction(bad,bench.load_fixtures(),fake)

    def test_fixture_coverage_has_all_stage_b_operation_categories(self):
        fixtures=bench.load_fixtures()["extraction"]
        self.assertGreaterEqual(len(fixtures), 6)
        ops={x["op"] for fixture in fixtures for x in fixture["expected_stage_b"]}
        for category in ("ADD_ENTITY", "ADD_FACT", "NOOP", "UPDATE_ENTITY", "SUPERSEDE_RELATION"):
            self.assertIn(category, ops)

    def test_cloud_is_opt_in_and_does_not_call_measurement(self):
        args=bench.build_parser().parse_args(["--mode","cloud"]); fixtures=bench.load_fixtures()
        called=False
        def fake(*_):
            nonlocal called; called=True; return 1
        result=bench.run_cloud(args, fixtures, fake)
        self.assertEqual(result["status"], "skipped"); self.assertFalse(called)

    def test_cloud_missing_key_skips_and_content_token_only(self):
        args=bench.build_parser().parse_args(["--allow-cloud","--cloud-provider","openai"])
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(bench.run_cloud(args, bench.load_fixtures())["status"], "skipped")
        self.assertFalse(bench._sse_content("openai", ": keepalive"))
        self.assertFalse(bench._sse_content("openai", "data: {}"))
        self.assertTrue(bench._sse_content("openai", 'data: {"choices":[{"delta":{"content":"x"}}]}'))
        self.assertTrue(bench._sse_content("anthropic", 'data: {"delta":{"text":"x"}}'))

    def test_inventory_never_uses_network(self):
        args=bench.build_parser().parse_args(["--mode","inventory"])
        result=bench.inventory(args, bench.load_fixtures())
        self.assertFalse(result["network_used"])

    def test_embedding_no_model_is_graceful_skip(self):
        args=bench.build_parser().parse_args(["--mode","embedding"])
        result=bench.run_embedding(args, bench.load_fixtures())
        self.assertEqual(result["status"], "skipped")

    def test_embedding_device_metrics_and_model_error_are_isolated(self):
        fake=types.ModuleType("sentence_transformers")
        class FakeModel:
            device="cpu"
            def __init__(self, path, device=None, local_files_only=True):
                self.requested_device=device
                if path == "bad": raise RuntimeError("CUDA out of memory")
            def encode(self, texts, batch_size, normalize_embeddings):
                # Stable, normalized-enough vectors; this test exercises result shape.
                return [[float(len(x) % 3), 1.0] for x in texts]
        fake.SentenceTransformer=FakeModel
        args=bench.build_parser().parse_args(["--embedding-model","good=.","--embedding-model","bad=bad","--embedding-device","auto","--no-local-files-only"])
        with patch.dict(sys.modules, {"sentence_transformers":fake}):
            result=bench.run_embedding(args, bench.load_fixtures())
        good, bad=result["models"]
        self.assertEqual(good["device"], "cpu")
        self.assertEqual(good["requested_device"], "auto")
        self.assertIn("corpus_batch_build_ms", good)
        self.assertIn("query_warm_latency", good)
        self.assertEqual(bad["status"], "error")

    def test_inventory_recommends_official_embedding_models_without_download(self):
        args=bench.build_parser().parse_args([])
        result=bench.inventory(args, bench.load_fixtures())
        self.assertEqual(result["recommended_models"], ["nlpai-lab/KURE-v1", "BAAI/bge-m3"])

    def test_retrieval_benchmark_is_local_bounded_and_reports_gates(self):
        args=bench.build_parser().parse_args(["--mode","retrieval","--retrieval-rows","100","--retrieval-runs","2"])
        result=bench.run_retrieval(args)
        self.assertFalse(result["network_used"])
        self.assertEqual((result["row_count"],result["runs"]),(100,2))
        self.assertEqual(set(result["modes"]),{"dynamic_conversation_cache_bypass","static_base_canon_semantic_warm"})
        dynamic=result["modes"]["dynamic_conversation_cache_bypass"]
        static=result["modes"]["static_base_canon_semantic_warm"]
        self.assertIn("p95_ms",dynamic["warm"]["wall_duration"])
        self.assertEqual((dynamic["db_row_count"],static["db_row_count"]),(100,100))
        self.assertGreaterEqual(static["semantic_entries"],1)
        self.assertEqual(dynamic["warm"]["cache_hits"],0)
        self.assertEqual(static["warm"]["cache_hits"],2)
        self.assertIn("pass",result["gate"])
        with self.assertRaises(ValueError):
            bench.run_retrieval(bench.build_parser().parse_args(["--mode","retrieval","--retrieval-rows","9"]))

if __name__ == "__main__": unittest.main()
