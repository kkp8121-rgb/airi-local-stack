import asyncio
import json
import math
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

import memory_embed
import memory_extract
import memory_layer
import memory_retrieve
import memory_store
import ollama_proxy


def run(coroutine):
    return asyncio.run(coroutine)


STAGE_A_RESPONSE = json.dumps(
    {
        "extracted": [
            {
                "turnNumber": 1,
                "kind": "entity",
                "subtype": "person",
                "name": "{{user}}",
                "content": "아이리와 매일 대화하는 사용자.",
            },
            {
                "turnNumber": 1,
                "kind": "entity",
                "subtype": "person",
                "name": "보리",
                "content": "{{user}}가 키우는 골든리트리버.",
            },
            {
                "turnNumber": 1,
                "kind": "fact",
                "subtype": "trait",
                "subjectNames": ["{{user}}"],
                "content": "강아지 보리를 키운다.",
                "turnRange": [1, 1],
            },
            {
                "turnNumber": 2,
                "kind": "fact",
                "subtype": "moment",
                "subjectNames": ["보리"],
                "content": "보리가 아파서 병원에 다녀왔다.",
                "turnRange": [2, 2],
            },
            {
                "turnNumber": 2,
                "kind": "relation",
                "subtype": "반려동물",
                "sourceName": "{{user}}",
                "targetName": "보리",
                "content": "보리는 {{user}}의 반려견.",
            },
        ]
    },
    ensure_ascii=False,
)


class _ScriptedExtractor:
    """Mock extraction LLM: answers Stage A and Stage B from canned strings."""

    def __init__(self, stage_a: str = STAGE_A_RESPONSE, stage_b: str | None = None) -> None:
        self.stage_a = stage_a
        self.stage_b = stage_b
        self.calls: list[tuple[str, str]] = []

    async def __call__(self, system_prompt: str, user_message: str) -> str:
        stage = "A" if system_prompt is memory_extract.STAGE_A_SYSTEM_PROMPT else "B"
        self.calls.append((stage, user_message))
        if stage == "A":
            if isinstance(self.stage_a, BaseException):
                raise self.stage_a
            return self.stage_a
        if self.stage_b is None:
            raise RuntimeError("no stage B response scripted")
        if isinstance(self.stage_b, BaseException):
            raise self.stage_b
        return self.stage_b


class _FakeBackend:
    """Minimal dialogue adapter so the speech path can run without a provider."""

    def __init__(self, deltas=("응! 알겠어.",)) -> None:
        self.deltas = deltas
        self.memory_block = ""

    async def stream_completion(self, system_prompt, messages, *, memory_block=""):
        self.memory_block = memory_block
        for delta in self.deltas:
            yield delta


class MemoryTestCase(unittest.TestCase):
    """Every test gets its own database file and the dependency-free embedder."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "nested" / "memory.db"

    def build_layer(self, **overrides) -> memory_layer.MemoryLayer:
        memory_section = {
            "db_path": str(self.db_path),
            "embed_mode": "fake",
            "extraction_batch_turns": 6,
            **overrides,
        }
        extractor = memory_section.pop("extraction_caller", None)
        layer = memory_layer.MemoryLayer(
            {"memory": memory_section, "modes": {}}, extraction_caller=extractor
        )
        layer.start()
        self.addCleanup(lambda: run(layer.aclose()))
        return layer

    def seed(self, layer, **kwargs) -> int:
        defaults = {
            "session_id": layer.session_id,
            "source": "conversation",
            "kind": memory_store.KIND_FACT,
            "subtype": "trait",
            "content": "테스트 기억",
        }
        defaults.update(kwargs)
        text = f"{defaults.get('name') or ''} {defaults['content']}".strip()
        defaults.setdefault("vector", memory_embed.pack_vector(memory_embed.fake_vector(text)))
        row_id, _inserted = layer.store.insert_memory(**defaults)
        return row_id


# --------------------------------------------------------------- (1) schema


class SchemaTests(MemoryTestCase):
    def test_schema_creation_is_idempotent(self) -> None:
        layer = self.build_layer()
        layer.store.ensure_schema()
        layer.store.ensure_schema()

        tables = {
            row["name"]
            for row in layer.store.connect().execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        self.assertLessEqual(
            {"memory", "fact_subject", "extraction_job", "conversation_turn"}, tables
        )

    def test_reference_columns_are_all_present(self) -> None:
        layer = self.build_layer()
        columns = {
            row["name"] for row in layer.store.connect().execute("PRAGMA table_info(memory)")
        }
        self.assertLessEqual(
            {
                "session_id", "source", "kind", "subtype", "name", "content",
                "source_id", "target_id", "confidence", "heard_from",
                "turn_range_start", "turn_range_end", "story_day", "time_of_day",
                "status", "superseded_by", "content_hash", "vector",
            },
            columns,
        )

    def test_migration_upgrades_a_database_written_before_the_added_columns(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        legacy = sqlite3.connect(self.db_path)
        legacy.execute(
            "CREATE TABLE memory (id INTEGER PRIMARY KEY, session_id TEXT, source TEXT, "
            "kind TEXT, subtype TEXT, name TEXT, content TEXT NOT NULL, content_hash TEXT, "
            "status TEXT DEFAULT 'active', vector BLOB)"
        )
        legacy.execute(
            "INSERT INTO memory (content, kind, subtype, status) VALUES ('옛 기억', 'fact', 'trait', 'active')"
        )
        legacy.commit()
        legacy.close()

        layer = self.build_layer()
        columns = {
            row["name"] for row in layer.store.connect().execute("PRAGMA table_info(memory)")
        }
        self.assertIn("is_true", columns)
        self.assertIn("created_at", columns)
        # The pre-existing row survives and stays visible (COALESCE default).
        rows = layer.store.active_rows(layer.session_id, kind="fact", subtypes=("trait",))
        self.assertEqual([row["content"] for row in rows], ["옛 기억"])

    def test_wal_mode_is_enabled(self) -> None:
        layer = self.build_layer()
        mode = layer.store.connect().execute("PRAGMA journal_mode").fetchone()[0]
        self.assertEqual(str(mode).lower(), "wal")


# ------------------------------------------------------- (2) stage A parsing


class StageAParsingTests(MemoryTestCase):
    def test_parses_the_documented_output_shape(self) -> None:
        items = memory_extract.parse_stage_a(STAGE_A_RESPONSE)
        kinds = [item["kind"] for item in items]
        self.assertEqual(kinds.count("entity"), 2)
        self.assertEqual(kinds.count("fact"), 2)
        self.assertEqual(kinds.count("relation"), 1)
        self.assertEqual(items[0]["name"], "{{user}}")

    def test_strips_code_fences_and_surrounding_prose(self) -> None:
        wrapped = "여기 결과야:\n```json\n" + STAGE_A_RESPONSE + "\n```\n"
        self.assertEqual(len(memory_extract.parse_stage_a(wrapped)), 5)

    def test_repairs_the_subtype_in_kind_failure_mode(self) -> None:
        # The prompt calls this out as the #1 violation; a small model will do
        # it, and throwing the batch away would lose real memories.
        raw = json.dumps(
            {"extracted": [{"kind": "location", "subtype": "location", "name": "집", "content": "사용자의 집."}]}
        )
        items = memory_extract.parse_stage_a(raw)
        self.assertEqual(items[0]["kind"], "entity")
        self.assertEqual(items[0]["subtype"], "location")

    def test_malformed_json_raises_so_the_batch_can_be_held(self) -> None:
        with self.assertRaises(ValueError):
            memory_extract.parse_stage_a("죄송해요, JSON을 못 만들겠어요")
        with self.assertRaises(ValueError):
            memory_extract.parse_stage_a('{"items": []}')

    def test_items_are_inserted_and_a_duplicate_hash_is_skipped(self) -> None:
        layer = self.build_layer()
        items = memory_extract.parse_stage_a(STAGE_A_RESPONSE)
        applier = memory_extract.ExtractionApplier(
            layer.store, layer._ensure_embedder(), session_id=layer.session_id, turn_ids=[11, 12]
        )
        first = applier.apply_items(items)
        self.assertEqual(first["added"], 5)

        again = memory_extract.ExtractionApplier(
            layer.store, layer._ensure_embedder(), session_id=layer.session_id, turn_ids=[11, 12]
        )
        second = again.apply_items(items)
        self.assertEqual(second["added"], 0)
        self.assertEqual(second["noop"], 5)
        self.assertEqual(len(layer.store.active_rows(layer.session_id)), 5)

    def test_turn_ranges_are_mapped_onto_global_turn_ids(self) -> None:
        layer = self.build_layer()
        items = memory_extract.parse_stage_a(STAGE_A_RESPONSE)
        applier = memory_extract.ExtractionApplier(
            layer.store, layer._ensure_embedder(), session_id=layer.session_id, turn_ids=[41, 42]
        )
        applier.apply_items(items)
        moment = layer.store.active_rows(layer.session_id, kind="fact", subtypes=("moment",))[0]
        self.assertEqual((moment["turn_range_start"], moment["turn_range_end"]), (42, 42))
        trait = layer.store.active_rows(layer.session_id, kind="fact", subtypes=("trait",))[0]
        # Traits are canon: no turn range, therefore no decay.
        self.assertIsNone(trait["turn_range_end"])

    def test_relations_link_the_entities_they_name(self) -> None:
        layer = self.build_layer()
        items = memory_extract.parse_stage_a(STAGE_A_RESPONSE)
        memory_extract.ExtractionApplier(
            layer.store, layer._ensure_embedder(), session_id=layer.session_id, turn_ids=[1, 2]
        ).apply_items(items)
        relation = layer.store.active_rows(layer.session_id, kind="relation")[0]
        source = layer.store.find_entity(layer.session_id, "{{user}}")
        target = layer.store.find_entity(layer.session_id, "보리")
        self.assertEqual(relation["source_id"], source["id"])
        self.assertEqual(relation["target_id"], target["id"])


# --------------------------------------------------------- (3) stage B ops


class StageBOperationTests(MemoryTestCase):
    def _applier(self, layer):
        return memory_extract.ExtractionApplier(
            layer.store, layer._ensure_embedder(), session_id=layer.session_id, turn_ids=[7]
        )

    def test_add_ops_create_rows_and_resolve_new_aliases(self) -> None:
        layer = self.build_layer()
        items = [
            memory_extract.normalize_item(
                {"kind": "entity", "subtype": "person", "name": "라임", "content": "동네 친구."}
            ),
            memory_extract.normalize_item(
                {"kind": "fact", "subtype": "trait", "subjectNames": ["라임"], "content": "커피를 좋아한다."}
            ),
            memory_extract.normalize_item(
                {
                    "kind": "relation", "subtype": "친구",
                    "sourceName": "라임", "targetName": "{{user}}", "content": "오래된 친구.",
                }
            ),
        ]
        operations = [
            {"op": "ADD_ENTITY", "alias": "e10", "subtype": "person", "name": "라임", "content": "동네 친구."},
            {"op": "ADD_FACT", "alias": "f11", "subtype": "trait", "content": "커피를 좋아한다.", "subjectAliases": ["e10"]},
            {"op": "ADD_RELATION", "alias": "r12", "subtype": "친구", "sourceAlias": "e10", "targetAlias": "f11", "content": "오래된 친구."},
        ]
        summary = self._applier(layer).apply_operations(operations, items, [])
        self.assertGreaterEqual(summary["added"], 3)
        contents = {row["content"] for row in layer.store.active_rows(layer.session_id)}
        self.assertIn("커피를 좋아한다.", contents)
        fact = layer.store.active_rows(layer.session_id, kind="fact", subtypes=("trait",))[0]
        subjects = list(
            layer.store.connect().execute(
                "SELECT entity_id FROM fact_subject WHERE fact_id = ?", (fact["id"],)
            )
        )
        self.assertTrue(subjects, "ADD_FACT must materialize its subjectAliases")

    def test_update_op_rewrites_the_candidate_in_place(self) -> None:
        layer = self.build_layer()
        row_id = self.seed(layer, content="커피를 좋아한다.")
        candidates = [
            {"alias": "f0", "id": row_id, "kind": "fact", "subtype": "trait", "name": None, "content": "커피를 좋아한다."}
        ]
        items = [memory_extract.normalize_item({"kind": "fact", "subtype": "trait", "content": "디카페인 커피를 좋아한다."})]
        summary = self._applier(layer).apply_operations(
            [{"op": "UPDATE_FACT", "alias": "f0", "subtype": "trait", "content": "디카페인 커피를 좋아한다."}],
            items,
            candidates,
        )
        self.assertEqual(summary["updated"], 1)
        rows = layer.store.active_rows(layer.session_id, kind="fact", subtypes=("trait",))
        self.assertEqual([row["content"] for row in rows], ["디카페인 커피를 좋아한다."])
        self.assertEqual(rows[0]["id"], row_id)

    def test_supersede_chains_the_old_row_to_its_replacement(self) -> None:
        layer = self.build_layer()
        old_id = self.seed(layer, content="고양이를 키운다.")
        candidates = [
            {"alias": "f0", "id": old_id, "kind": "fact", "subtype": "trait", "name": None, "content": "고양이를 키운다."}
        ]
        items = [memory_extract.normalize_item({"kind": "fact", "subtype": "trait", "content": "이제 강아지를 키운다."})]
        summary = self._applier(layer).apply_operations(
            [{"op": "SUPERSEDE_FACT", "alias": "f0", "reason": "반려동물이 바뀜"}], items, candidates
        )
        self.assertEqual(summary["superseded"], 1)

        old = layer.store.connect().execute("SELECT * FROM memory WHERE id = ?", (old_id,)).fetchone()
        self.assertEqual(old["status"], memory_store.STATUS_SUPERSEDED)
        self.assertIsNotNone(old["superseded_by"])
        # History is preserved, not deleted, and the chain points forward.
        replacement = layer.store.connect().execute(
            "SELECT * FROM memory WHERE id = ?", (old["superseded_by"],)
        ).fetchone()
        self.assertEqual(replacement["content"], "이제 강아지를 키운다.")
        active = layer.store.active_rows(layer.session_id, kind="fact", subtypes=("trait",))
        self.assertEqual([row["content"] for row in active], ["이제 강아지를 키운다."])

    def test_noop_changes_nothing(self) -> None:
        layer = self.build_layer()
        row_id = self.seed(layer, content="커피를 좋아한다.")
        candidates = [
            {"alias": "f0", "id": row_id, "kind": "fact", "subtype": "trait", "name": None, "content": "커피를 좋아한다."}
        ]
        items = [memory_extract.normalize_item({"kind": "fact", "subtype": "trait", "content": "커피를 좋아한다."})]
        summary = self._applier(layer).apply_operations(
            [{"op": "NOOP", "alias": "f0"}], items, candidates
        )
        self.assertEqual(summary["noop"], 1)
        self.assertEqual(summary["added"], 0)
        self.assertEqual(len(layer.store.active_rows(layer.session_id)), 1)

    def test_an_invented_alias_degrades_to_an_add(self) -> None:
        layer = self.build_layer()
        items = [memory_extract.normalize_item({"kind": "fact", "subtype": "moment", "content": "우산을 잃어버렸다."})]
        summary = self._applier(layer).apply_operations(
            [{"op": "UPDATE_FACT", "alias": "f99", "content": "우산을 잃어버렸다."}], items, []
        )
        self.assertEqual(summary["added"], 1)

    def test_candidates_are_aliased_by_kind_prefix(self) -> None:
        layer = self.build_layer()
        self.seed(layer, kind="entity", subtype="person", name="라임", content="동네 친구.")
        self.seed(layer, content="커피를 좋아한다.")
        items = [memory_extract.normalize_item({"kind": "fact", "subtype": "trait", "content": "커피를 좋아한다."})]
        candidates = memory_extract.select_candidates(
            layer.store, layer._ensure_embedder(), layer.session_id, items
        )
        self.assertTrue(candidates)
        self.assertTrue(all(candidate["alias"][0] in "efr" for candidate in candidates))


# ------------------------------------------------------- (4) retrieval math


class RetrievalScoringTests(MemoryTestCase):
    def test_decay_formula_matches_the_reference(self) -> None:
        caps = memory_retrieve.RetrievalCaps()
        self.assertEqual(memory_retrieve.decay_for({"turn_range_end": None}, 100, caps.decay_lambda), 1.0)
        self.assertAlmostEqual(
            memory_retrieve.decay_for({"turn_range_end": 5}, 15, caps.decay_lambda),
            math.exp(-0.05 * 10),
        )
        # A memory from the future (clock skew) must not amplify the score.
        self.assertEqual(memory_retrieve.decay_for({"turn_range_end": 20}, 10, caps.decay_lambda), 1.0)

    def test_score_is_alpha_cosine_plus_beta_decay(self) -> None:
        caps = memory_retrieve.RetrievalCaps()
        self.assertAlmostEqual(memory_retrieve.score_row(0.5, 0.6, caps), 0.7 * 0.5 + 0.3 * 0.6)
        self.assertAlmostEqual(memory_retrieve.score_row(1.0, 1.0, caps), 1.0)

    def test_ranking_follows_the_computed_scores(self) -> None:
        layer = self.build_layer()
        current = 100
        self.seed(layer, subtype="moment", content="어제 강아지 산책을 했다.", turn_range=(90, 90))
        self.seed(layer, subtype="moment", content="지난달 이사를 했다.", turn_range=(2, 2))
        rows = layer.store.active_rows(layer.session_id, kind="fact", subtypes=("moment",))
        query = layer._ensure_embedder().embed_one("강아지 산책 얘기해줘")
        cosines = memory_embed.cosine_many(query, [row["vector"] for row in rows])
        expected = sorted(
            (
                memory_retrieve.score_row(
                    cosines[index],
                    memory_retrieve.decay_for(row, current, layer.caps.decay_lambda),
                    layer.caps,
                ),
                row["content"],
            )
            for index, row in enumerate(rows)
        )
        result = memory_retrieve.retrieve(
            layer.store,
            layer._ensure_embedder(),
            layer.caps,
            session_id=layer.session_id,
            question="강아지 산책 얘기해줘",
            current_turn=current,
        )
        self.assertEqual(
            [row["content"] for row in result.moments],
            [content for _score, content in reversed(expected)],
        )

    def test_caps_cut_each_bucket(self) -> None:
        layer = self.build_layer()
        for index in range(12):
            self.seed(layer, subtype="trait", content=f"성향 {index}")
        for index in range(9):
            self.seed(layer, subtype="moment", content=f"사건 {index}", turn_range=(index, index))
        result = memory_retrieve.retrieve(
            layer.store,
            layer._ensure_embedder(),
            layer.caps,
            session_id=layer.session_id,
            question="어떤 일이 있었는지 전부 설명해줘",
            current_turn=20,
        )
        self.assertEqual(len(result.traits), layer.caps.traits)
        self.assertEqual(len(result.moments), layer.caps.moments)

    def test_scene_bucket_respects_the_over_fetch_then_final_cap(self) -> None:
        layer = self.build_layer(caps={"scene_facts_raw": 20, "scene_facts_final": 8})
        for index in range(25):
            self.seed(layer, kind="entity", subtype="person", name=f"사람{index}", content=f"인물 {index}")
        result = memory_retrieve.retrieve(
            layer.store,
            layer._ensure_embedder(),
            layer.caps,
            session_id=layer.session_id,
            question="그 인물에 대해 설명해줘",
            current_turn=5,
        )
        self.assertEqual(len(result.context), 8)

    def test_superseded_and_untrue_rows_are_excluded_at_query_level(self) -> None:
        layer = self.build_layer()
        kept = self.seed(layer, content="사용자는 커피를 좋아한다.")
        dropped = self.seed(layer, content="사용자는 홍차를 좋아한다.")
        layer.store.supersede(dropped, kept)
        self.seed(layer, content="사용자는 사실 로봇이다.", is_true=False)

        result = memory_retrieve.retrieve(
            layer.store,
            layer._ensure_embedder(),
            layer.caps,
            session_id=layer.session_id,
            question="사용자가 어떤 사람인지 설명해줘",
            current_turn=10,
        )
        contents = [row["content"] for row in result.traits]
        self.assertEqual(contents, ["사용자는 커피를 좋아한다."])

    def test_one_hop_expansion_only_fires_on_a_name_match(self) -> None:
        layer = self.build_layer()
        entity_id = self.seed(layer, kind="entity", subtype="person", name="보리", content="골든리트리버.")
        other_id = self.seed(layer, kind="entity", subtype="person", name="라임", content="동네 친구.")
        self.seed(
            layer,
            kind="relation",
            subtype="반려동물",
            content="보리는 사용자의 반려견.",
            source_ref=other_id,
            target_ref=entity_id,
        )
        hit = memory_retrieve.retrieve(
            layer.store, layer._ensure_embedder(), layer.caps,
            session_id=layer.session_id, question="보리 어떻게 지내?", current_turn=3,
        )
        self.assertEqual(hit.matched_names, ["보리"])
        self.assertEqual([row["content"] for row in hit.relations], ["보리는 사용자의 반려견."])

        miss = memory_retrieve.retrieve(
            layer.store, layer._ensure_embedder(), layer.caps,
            session_id=layer.session_id, question="오늘 날씨는 어떤가?", current_turn=3,
        )
        self.assertEqual(miss.relations, [])

    def test_a_row_without_a_vector_still_scores_instead_of_crashing(self) -> None:
        layer = self.build_layer()
        self.seed(layer, content="임베딩이 실패한 기억.", vector=None)
        result = memory_retrieve.retrieve(
            layer.store, layer._ensure_embedder(), layer.caps,
            session_id=layer.session_id, question="어떤 기억이 있는지 알려줘", current_turn=1,
        )
        self.assertEqual([row["content"] for row in result.traits], ["임베딩이 실패한 기억."])


# --------------------------------------------------------------- (5) gate


class RetrievalGateTests(unittest.TestCase):
    def test_short_utterances_skip_retrieval(self) -> None:
        for text in ("ㅇㅇ", "안녕", "ㅋㅋ", "   "):
            with self.subTest(text=text):
                self.assertFalse(memory_retrieve.needs_retrieval(text, []))

    def test_information_signals_always_retrieve(self) -> None:
        for text in ("그때 무슨 일이 있었어", "이유가 뭐야", "그거 설명해줘", "기억나?"):
            with self.subTest(text=text):
                self.assertTrue(memory_retrieve.needs_retrieval(text, []))

    def test_naming_an_absent_person_retrieves(self) -> None:
        self.assertTrue(memory_retrieve.needs_retrieval("보리 잘 있지", ["보리", "라임"]))
        self.assertFalse(
            memory_retrieve.needs_retrieval("보리 잘 있지", ["보리", "라임"], attendees=["보리"])
        )

    def test_long_questions_retrieve_even_without_a_signal(self) -> None:
        self.assertTrue(memory_retrieve.needs_retrieval("ㄱ" * 25, []))
        self.assertFalse(memory_retrieve.needs_retrieval("ㄱ" * 24, []))

    def test_name_scanner_drops_a_name_swallowed_by_a_longer_one(self) -> None:
        scanner = memory_retrieve.NameScanner()
        self.assertEqual(scanner.scan("김보리랑 놀았어", ["보리", "김보리"]), ["김보리"])


# ------------------------------------------------------ (6) block format


class MemoryBlockFormatTests(MemoryTestCase):
    def test_block_matches_the_reference_serialization(self) -> None:
        layer = self.build_layer()
        self.seed(layer, subtype="trait", content="강아지 보리를 키운다.")
        self.seed(
            layer, subtype="moment", content="보리가 병원에 다녀왔다.",
            turn_range=(4, 4), story_day=3, time_of_day="저녁",
        )
        entity_id = self.seed(layer, kind="entity", subtype="person", name="보리", content="골든리트리버.")
        self.seed(
            layer, kind="relation", subtype="반려동물", content="보리는 {{user}}의 반려견.",
            source_ref=entity_id, target_ref=entity_id,
        )
        result = memory_retrieve.retrieve(
            layer.store, layer._ensure_embedder(), layer.caps,
            session_id=layer.session_id, question="보리에 대해 설명해줘", current_turn=5,
        )
        block = memory_retrieve.format_memory_block(result)
        lines = block.splitlines()
        self.assertEqual(lines[0], "[Character Memory]")
        self.assertIn("Traits:", lines)
        self.assertIn("Recent Events:", lines)
        self.assertIn("Relevant Context:", lines)
        self.assertIn("Relations:", lines)
        self.assertIn("- 강아지 보리를 키운다.", lines)
        self.assertIn("- (Day 3 저녁) 보리가 병원에 다녀왔다.", lines)
        # An entity carries its identity in the name, so the line keeps it.
        self.assertIn("- 보리: 골든리트리버.", lines)
        # Placeholders are stored verbatim and only rendered at the block.
        self.assertIn("- 보리는 사용자의 반려견.", lines)
        self.assertNotIn("{{user}}", block)

    def test_an_empty_result_serializes_to_an_empty_string(self) -> None:
        empty = memory_retrieve.RetrievalResult([], [], [], [], [])
        self.assertEqual(memory_retrieve.format_memory_block(empty), "")

    def test_sections_are_omitted_when_they_have_no_rows(self) -> None:
        layer = self.build_layer()
        self.seed(layer, subtype="trait", content="조용한 곳을 좋아한다.")
        result = memory_retrieve.retrieve(
            layer.store, layer._ensure_embedder(), layer.caps,
            session_id=layer.session_id, question="어떤 성격인지 설명해줘", current_turn=1,
        )
        block = memory_retrieve.format_memory_block(result)
        self.assertIn("Traits:", block)
        self.assertNotIn("Recent Events:", block)
        self.assertNotIn("Relations:", block)


# ------------------------------------------------------------ (7) fail-soft


class FailSoftTests(MemoryTestCase):
    def test_a_locked_database_yields_an_empty_block(self) -> None:
        layer = self.build_layer()
        with mock.patch.object(
            layer.store, "entity_names", side_effect=sqlite3.OperationalError("database is locked")
        ):
            self.assertEqual(run(layer.memory_block("무슨 일이 있었는지 알려줘")), "")

    def test_exceeding_the_timebox_yields_an_empty_block(self) -> None:
        layer = self.build_layer(retrieval_timebox_ms=10)

        def slow(_text: str) -> str:
            import time as _time

            _time.sleep(0.3)
            return "[Character Memory]\nTraits:\n- 늦게 도착한 기억"

        with mock.patch.object(layer, "memory_block_sync", side_effect=slow):
            self.assertEqual(run(layer.memory_block("무슨 일이 있었는지 알려줘")), "")

    def test_a_retrieval_crash_yields_an_empty_block(self) -> None:
        layer = self.build_layer()
        with mock.patch.object(layer, "memory_block_sync", side_effect=RuntimeError("boom")):
            self.assertEqual(run(layer.memory_block("무슨 일이 있었는지 알려줘")), "")

    def test_a_broken_embedder_does_not_stop_the_write(self) -> None:
        layer = self.build_layer()
        applier = memory_extract.ExtractionApplier(
            layer.store, layer._ensure_embedder(), session_id=layer.session_id
        )
        with mock.patch.object(layer._ensure_embedder(), "embed_one", side_effect=RuntimeError("no gpu")):
            applier.apply_items(
                [memory_extract.normalize_item({"kind": "fact", "subtype": "trait", "content": "기억 하나."})]
            )
        rows = layer.store.active_rows(layer.session_id, kind="fact", subtypes=("trait",))
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["vector"])

    def test_start_failure_disables_the_layer_instead_of_raising(self) -> None:
        blocked = Path(self._tmp.name) / "blocked"
        blocked.mkdir()
        layer = memory_layer.MemoryLayer({"memory": {"db_path": str(blocked)}, "modes": {}})
        layer.start()
        self.assertFalse(layer.enabled)
        self.assertEqual(run(layer.memory_block("무슨 일이 있었는지 알려줘")), "")
        self.assertEqual(layer.health()["rows"], 0)

    def test_the_speech_path_survives_a_failing_memory_layer(self) -> None:
        layer = self.build_layer()
        backend = _FakeBackend(["응! 잘 지냈어."])
        with mock.patch.object(layer, "memory_block_sync", side_effect=RuntimeError("boom")), \
                mock.patch.object(ollama_proxy, "MEMORY", layer), \
                mock.patch.object(ollama_proxy, "LLM_MODE", "cloud"), \
                mock.patch.object(ollama_proxy, "build_backend", lambda config, http: backend), \
                mock.patch.object(ollama_proxy, "client", object()):
            response = TestClient(ollama_proxy.app).post(
                "/v1/chat/completions",
                json={
                    "model": "exaone-airi:2.4b",
                    "stream": True,
                    "messages": [{"role": "user", "content": "그동안 무슨 일이 있었는지 알려줘"}],
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("잘 지냈어.", response.text)
        self.assertEqual(backend.memory_block, "")


# ------------------------------------------------------------ (8) watermark


class WatermarkTests(MemoryTestCase):
    def _record(self, layer, count: int) -> None:
        for index in range(count):
            layer.record_turn_sync(f"{index}번째 질문이야", f"{index}번째 대답이야")

    def test_a_batch_under_the_threshold_waits(self) -> None:
        layer = self.build_layer(extraction_caller=_ScriptedExtractor())
        self._record(layer, 3)
        outcome = run(layer.run_extraction_once())
        self.assertEqual(outcome["status"], "waiting")
        self.assertEqual(layer.store.watermark(layer.session_id), 0)

    def test_a_full_batch_advances_the_watermark(self) -> None:
        extractor = _ScriptedExtractor()
        layer = self.build_layer(extraction_caller=extractor)
        self._record(layer, 6)
        outcome = run(layer.run_extraction_once())
        self.assertEqual(outcome["status"], "ok")
        self.assertEqual(layer.store.watermark(layer.session_id), 6)
        self.assertEqual(layer.store.pending_turns(layer.session_id), [])
        self.assertEqual(extractor.calls[0][0], "A")
        self.assertIn("<character>", extractor.calls[0][1])
        self.assertIn("[turn 6]", extractor.calls[0][1])

    def test_a_parse_failure_holds_the_batch_for_the_next_trigger(self) -> None:
        layer = self.build_layer(extraction_caller=_ScriptedExtractor(stage_a="설명은 못 하겠어"))
        self._record(layer, 6)
        outcome = run(layer.run_extraction_once())
        self.assertEqual(outcome["status"], "held")
        self.assertEqual(layer.store.watermark(layer.session_id), 0)
        self.assertEqual(len(layer.store.pending_turns(layer.session_id)), 6)
        self.assertEqual(layer.store.job(layer.session_id)["fail_count"], 1)

    def test_a_retry_after_a_failure_succeeds_on_the_same_turns(self) -> None:
        extractor = _ScriptedExtractor(stage_a="깨진 응답")
        layer = self.build_layer(extraction_caller=extractor)
        self._record(layer, 6)
        run(layer.run_extraction_once())
        extractor.stage_a = STAGE_A_RESPONSE
        outcome = run(layer.run_extraction_once())
        self.assertEqual(outcome["status"], "ok")
        self.assertEqual(layer.store.watermark(layer.session_id), 6)
        self.assertEqual(layer.store.job(layer.session_id)["fail_count"], 0)

    def test_repeated_failures_dead_letter_the_batch(self) -> None:
        layer = self.build_layer(
            extraction_caller=_ScriptedExtractor(stage_a="깨진 응답"), extraction_max_failures=3
        )
        self._record(layer, 6)
        statuses = [run(layer.run_extraction_once())["status"] for _ in range(3)]
        self.assertEqual(statuses, ["held", "held", "skipped"])
        self.assertEqual(layer.store.watermark(layer.session_id), 6)

    def test_a_provider_error_also_holds_the_batch(self) -> None:
        layer = self.build_layer(
            extraction_caller=_ScriptedExtractor(stage_a=RuntimeError("codex is down"))
        )
        self._record(layer, 6)
        self.assertEqual(run(layer.run_extraction_once())["status"], "held")
        self.assertEqual(layer.store.watermark(layer.session_id), 0)

    def test_stage_b_runs_once_candidates_exist_and_degrades_when_it_breaks(self) -> None:
        extractor = _ScriptedExtractor()
        layer = self.build_layer(extraction_caller=extractor)
        self._record(layer, 6)
        run(layer.run_extraction_once())  # first batch: no candidates -> stage A only
        self.assertEqual([call[0] for call in extractor.calls], ["A"])

        self._record(layer, 6)
        extractor.stage_b = "JSON이 아니야"
        outcome = run(layer.run_extraction_once())
        self.assertEqual([call[0] for call in extractor.calls], ["A", "A", "B"])
        self.assertFalse(outcome["stage_b"])
        # The identical Stage A payload is deduped by content_hash either way.
        self.assertEqual(len(layer.store.active_rows(layer.session_id)), 5)

    def test_stage_b_operations_are_applied_when_they_parse(self) -> None:
        extractor = _ScriptedExtractor()
        layer = self.build_layer(extraction_caller=extractor)
        self._record(layer, 6)
        run(layer.run_extraction_once())

        self._record(layer, 6)
        extractor.stage_a = json.dumps(
            {"extracted": [{"turnNumber": 1, "kind": "fact", "subtype": "trait",
                            "subjectNames": ["{{user}}"], "content": "이제 고양이도 키운다."}]},
            ensure_ascii=False,
        )
        extractor.stage_b = json.dumps(
            {"operations": [{"op": "ADD_FACT", "alias": "f30", "subtype": "trait",
                             "content": "이제 고양이도 키운다.", "subjectAliases": []}]},
            ensure_ascii=False,
        )
        outcome = run(layer.run_extraction_once())
        self.assertTrue(outcome["stage_b"])
        self.assertIn("<extracted>", extractor.calls[-1][1])
        self.assertIn("<candidates>", extractor.calls[-1][1])
        contents = {row["content"] for row in layer.store.active_rows(layer.session_id)}
        self.assertIn("이제 고양이도 키운다.", contents)


# ---------------------------------------------------------- (9) end to end


class EndToEndTests(MemoryTestCase):
    def test_six_turns_survive_a_restart_and_come_back_in_the_block(self) -> None:
        extractor = _ScriptedExtractor()
        layer = self.build_layer(extraction_caller=extractor)
        conversation = [
            ("나 강아지 키워. 이름은 보리야.", "보리! 이름 예쁘다."),
            ("보리가 아파서 병원 다녀왔어.", "많이 걱정됐겠다."),
            ("그래도 지금은 괜찮아졌어.", "다행이야!"),
            ("오늘 산책도 했어.", "좋았겠다."),
            ("보리는 골든리트리버야.", "큰 아이구나."),
            ("내일도 산책 갈 거야.", "재밌겠다!"),
        ]
        for user_text, assistant_text in conversation:
            layer.record_turn_sync(user_text, assistant_text)

        outcome = run(layer.run_extraction_once())
        self.assertEqual(outcome["status"], "ok")
        run(layer.aclose())

        # Restart: a brand new layer on the same file, nothing carried over.
        restarted = memory_layer.MemoryLayer(
            {"memory": {"db_path": str(self.db_path), "embed_mode": "fake"}, "modes": {}}
        )
        restarted.start()
        self.addCleanup(lambda: run(restarted.aclose()))

        block = run(restarted.memory_block("보리 어떻게 지내는지 기억나?"))
        self.assertTrue(block.startswith("[Character Memory]"), block)
        self.assertIn("보리", block)
        self.assertIn("강아지 보리를 키운다.", block)
        self.assertNotIn("{{user}}", block)

        health = restarted.health()
        self.assertEqual(health["embed_mode"], "fake")
        self.assertGreaterEqual(health["rows"], 5)
        self.assertEqual(health["pending_jobs"], 0)
        self.assertIsNotNone(health["last_extraction_ts"])

    def test_a_chat_turn_injects_the_block_and_queues_the_turn(self) -> None:
        layer = self.build_layer()
        self.seed(layer, subtype="trait", content="강아지 보리를 키운다.")
        backend = _FakeBackend(["응! 보리 잘 지내."])
        with mock.patch.object(ollama_proxy, "MEMORY", layer), \
                mock.patch.object(ollama_proxy, "LLM_MODE", "cloud"), \
                mock.patch.object(ollama_proxy, "build_backend", lambda config, http: backend), \
                mock.patch.object(ollama_proxy, "client", object()):
            response = TestClient(ollama_proxy.app).post(
                "/v1/chat/completions",
                json={
                    "model": "exaone-airi:2.4b",
                    "stream": True,
                    "messages": [{"role": "user", "content": "보리 어떻게 지내는지 기억나?"}],
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("[Character Memory]", backend.memory_block)
        self.assertIn("강아지 보리를 키운다.", backend.memory_block)
        run(layer.aclose())
        self.assertEqual(
            [row["user_text"] for row in layer.store.pending_turns(layer.session_id)],
            ["보리 어떻게 지내는지 기억나?"],
        )

    def test_health_exposes_the_memory_summary(self) -> None:
        layer = self.build_layer()
        with mock.patch.object(ollama_proxy, "MEMORY", layer):
            payload = TestClient(ollama_proxy.app).get("/health").json()
        self.assertLessEqual(
            {"rows", "pending_jobs", "last_extraction_ts", "embed_mode"},
            set(payload["memory"]),
        )


# ------------------------------------------------- config / embedding / wiring


class ConfigAndEmbeddingTests(MemoryTestCase):
    def test_caps_come_from_config_not_from_code(self) -> None:
        layer = self.build_layer(caps={"traits": 2, "alpha": 0.9, "beta": 0.1, "lambda": 0.2})
        self.assertEqual(layer.caps.traits, 2)
        self.assertEqual(layer.caps.alpha, 0.9)
        self.assertEqual(layer.caps.decay_lambda, 0.2)
        # Unspecified caps keep the reference defaults.
        self.assertEqual(layer.caps.moments, 5)
        self.assertEqual(layer.caps.scene_facts_raw, 20)

    def test_shipped_config_carries_the_reference_constants(self) -> None:
        config = memory_layer.memory_config(ollama_proxy.LLM_CONFIG)
        caps = memory_retrieve.RetrievalCaps.from_config(config["caps"])
        self.assertEqual(
            (caps.traits, caps.moments, caps.scene_facts_raw, caps.scene_facts_final),
            (8, 5, 20, 8),
        )
        self.assertEqual((caps.one_hop_relations, caps.one_hop_facts), (5, 3))
        self.assertEqual((caps.alpha, caps.beta, caps.decay_lambda), (0.7, 0.3, 0.05))
        self.assertEqual(config["extraction_provider"], "codex-cli")

    def test_environment_overrides_win_over_the_config_file(self) -> None:
        with mock.patch.dict(
            "os.environ", {"AIRI_EMBED_MODE": "local", "AIRI_MEMORY_ENABLED": "0"}, clear=False
        ):
            config = memory_layer.memory_config({})
        self.assertEqual(config["embed_mode"], "local")
        self.assertFalse(config["enabled"])

    def test_fake_embeddings_are_deterministic_and_normalized(self) -> None:
        first = memory_embed.fake_vector("강아지 보리를 키운다.")
        second = memory_embed.fake_vector("강아지 보리를 키운다.")
        self.assertEqual(first, second)
        self.assertEqual(len(first), memory_embed.FAKE_DIM)
        self.assertAlmostEqual(sum(value * value for value in first), 1.0, places=5)

    def test_fake_embeddings_still_rank_related_text_higher(self) -> None:
        query = memory_embed.fake_vector("강아지 보리 산책")
        related = memory_embed.fake_vector("보리랑 산책을 다녀왔다")
        unrelated = memory_embed.fake_vector("양자컴퓨터 원리 설명")
        self.assertGreater(
            memory_embed.cosine(query, related), memory_embed.cosine(query, unrelated)
        )

    def test_local_mode_falls_back_to_fake_when_the_library_is_missing(self) -> None:
        with mock.patch.dict("sys.modules", {"sentence_transformers": None}):
            embedder = memory_embed.build_embedder("local", "nlpai-lab/KURE-v1")
        self.assertEqual(embedder.mode, "fake")

    def test_vectors_survive_a_pack_unpack_round_trip(self) -> None:
        vector = memory_embed.fake_vector("왕복 검사")
        restored = memory_embed.unpack_vector(memory_embed.pack_vector(vector))
        for original, value in zip(vector, restored):
            self.assertAlmostEqual(original, value, places=6)
        self.assertIsNone(memory_embed.unpack_vector(None))

    def test_extraction_mode_resolves_by_mode_name_or_provider(self) -> None:
        config = ollama_proxy.LLM_CONFIG
        by_provider = memory_layer.resolve_extraction_mode(config, "codex-cli")
        self.assertEqual(by_provider["provider"], "codex-cli")
        by_name = memory_layer.resolve_extraction_mode(config, "local")
        self.assertEqual(by_name["provider"], "ollama")
        self.assertIsNone(memory_layer.resolve_extraction_mode(config, "nope"))

    def test_codex_extraction_drops_the_dialogue_prompt_header(self) -> None:
        import llm_backends

        dialogue = llm_backends.CodexBackend({"model": "gpt-5.6-sol"})
        self.assertIn(
            llm_backends.CODEX_PROMPT_HEADER, dialogue.build_prompt("페르소나", [{"role": "user", "content": "안녕"}], "")
        )
        extraction = llm_backends.CodexBackend({"model": "gpt-5.6-sol", "codex_prompt_header": ""})
        self.assertNotIn(
            llm_backends.CODEX_PROMPT_HEADER,
            extraction.build_prompt("추출 지시문", [{"role": "user", "content": "<turns>...</turns>"}], ""),
        )

    def test_the_local_system_prompt_constant_is_never_mutated(self) -> None:
        before = ollama_proxy.AIRI_SYSTEM_PROMPT
        body = json.dumps(
            {"messages": [{"role": "system", "content": ollama_proxy.AIRI_SYSTEM_PROMPT},
                          {"role": "user", "content": "안녕"}]},
            ensure_ascii=False,
        ).encode("utf-8")
        patched = json.loads(ollama_proxy.apply_memory_block(body, "[Character Memory]\nTraits:\n- 기억"))
        self.assertEqual(ollama_proxy.AIRI_SYSTEM_PROMPT, before)
        self.assertTrue(patched["messages"][0]["content"].startswith(before))
        self.assertIn("[Character Memory]", patched["messages"][0]["content"])

    def test_an_empty_block_leaves_the_body_untouched(self) -> None:
        body = b'{"messages": [{"role": "system", "content": "x"}]}'
        self.assertIs(ollama_proxy.apply_memory_block(body, ""), body)
        self.assertIs(ollama_proxy.apply_memory_block(b"not json", "block"), b"not json")


if __name__ == "__main__":
    unittest.main()
