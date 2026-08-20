import json
import unittest
from pathlib import Path

from memory_prompts import STAGE_A_SCHEMA
from memory_taxonomy import (
    AliasResolver, TAXONOMY_PATH, USER_PLACEHOLDER,
    apply_taxonomy_gate, load_tables, normalize_key, taxonomy_slot,
)

HERE = Path(__file__).resolve().parent
SEED = HERE / "training" / "seed" / "airi_extraction_seed_pending.jsonl"


def entity(name, subtype="person", content="설명"):
    return {"turnNumber": 1, "kind": "entity", "subtype": subtype, "name": name, "content": content}


def fact(subjects, subtype="moment"):
    return {"turnNumber": 1, "kind": "fact", "subtype": subtype, "subjectNames": list(subjects),
            "content": "내용", "turnRange": [1, 1]}


def relation(subtype, source="세라", target="은빛 상단"):
    return {"turnNumber": 1, "kind": "relation", "subtype": subtype,
            "sourceName": source, "targetName": target, "content": "내용"}


class TaxonomyTableTests(unittest.TestCase):
    """고정 택소노미 표는 데이터 파일 하나가 SSoT여야 한다."""

    def test_entity_and_fact_slots_match_the_stage_a_schema_enums(self):
        # 스키마와 표가 갈라지면 게이트가 정상 항목을 떨군다. 드리프트를 여기서 잡는다.
        tables = load_tables()
        branches = STAGE_A_SCHEMA["properties"]["extracted"]["items"]["oneOf"]
        schema_enums = {
            branch["properties"]["kind"]["const"]: branch["properties"]["subtype"].get("enum")
            for branch in branches
        }
        self.assertEqual(set(tables.slot_ids["entity"]), set(schema_enums["entity"]))
        self.assertEqual(set(tables.slot_ids["fact"]), set(schema_enums["fact"]))
        # relation 은 스키마상 자유 문자열이므로 표가 유일한 제약이다.
        self.assertIsNone(schema_enums["relation"])
        self.assertTrue(tables.slot_ids["relation"])

    def test_registered_surfaces_map_onto_one_relation_slot(self):
        for surface in ("친구", "friend", "friendship", " 친구 ", "우정"):
            self.assertEqual(taxonomy_slot("relation", surface), "friendship")
        self.assertEqual(taxonomy_slot("relation", "소속"), "affiliation")
        self.assertEqual(taxonomy_slot("relation", "사용"), "uses")

    def test_free_form_subtype_has_no_slot(self):
        self.assertIsNone(taxonomy_slot("relation", "그 날 밤에 느낀 애매한 감정"))
        self.assertIsNone(taxonomy_slot("relation", ""))
        self.assertIsNone(taxonomy_slot("entity", "person-ish"))
        self.assertIsNone(taxonomy_slot("moment", "trait"))

    def test_taxonomy_file_is_shipped_and_versioned(self):
        payload = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], 1)


class TaxonomyGateTests(unittest.TestCase):
    def test_gate_keeps_registered_items_and_drops_free_form_ones(self):
        items = [entity("세라"), fact(["세라"]), relation("소속"), relation("그냥 아무 말")]
        kept, dropped = apply_taxonomy_gate(items)
        self.assertEqual(dropped, 1)
        self.assertEqual([item["subtype"] for item in kept], ["person", "moment", "소속"])

    def test_gate_never_rewrites_a_surviving_item(self):
        # 게이트는 통과/차단만 한다 — 기존 행과의 subtype 표기 분열을 만들지 않는다.
        items = [relation("friendship")]
        kept, dropped = apply_taxonomy_gate(items)
        self.assertEqual((kept, dropped), (items, 0))
        self.assertIsNot(kept[0], items[0])

    def test_gate_drops_a_structurally_broken_item_instead_of_raising(self):
        kept, dropped = apply_taxonomy_gate([{"kind": "relation"}, "not-a-dict"])
        self.assertEqual((kept, dropped), ([], 2))


class SeedTaxonomyCrossCheckTests(unittest.TestCase):
    """추출 학습쌍 102건이 고정 택소노미를 전건 통과해야 한다."""

    def test_every_seed_pair_passes_the_taxonomy(self):
        if not SEED.exists():  # 학습 데이터는 다른 스트림 소유 — 없으면 대조를 건너뛴다.
            self.skipTest("extraction seed is not present")
        records = [json.loads(line) for line in SEED.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(records), 102)
        offenders = []
        total = 0
        for record in records:
            items = json.loads(record["target"])["extracted"]
            total += len(items)
            kept, dropped = apply_taxonomy_gate(items)
            if dropped:
                offenders.append((record["id"], [item.get("subtype") for item in items]))
        self.assertEqual(offenders, [])
        self.assertTrue(total)


class AliasResolutionTests(unittest.TestCase):
    def test_vocative_and_particle_forms_resolve_onto_a_known_name(self):
        resolver = AliasResolver(["세라", "은빛 상단"])
        for mention in ("세라야", "세라는", "세라님", "  세라  ", "세라!"):
            self.assertEqual(resolver.resolve(mention), "세라")
        self.assertEqual(resolver.resolve("은빛상단"), "은빛 상단")

    def test_registered_alias_resolves_onto_its_canonical_name(self):
        resolver = AliasResolver([])
        self.assertEqual(resolver.resolve("AIRI"), "아이리")

    def test_resolution_never_invents_an_unknown_name(self):
        resolver = AliasResolver(["세라"])
        self.assertEqual(resolver.resolve("하린"), "하린")
        self.assertEqual(resolver.resolve("하린아"), "하린아")

    def test_ambiguous_known_names_are_left_untouched(self):
        # 가드는 충돌하는 두 표기가 **이미 색인에 있을 때만** 발동한다.
        resolver = AliasResolver(["미나", "미나야"])
        self.assertEqual(resolver.resolve("미나는"), "미나는")

    def test_known_limitation_unknown_names_collapse_inside_one_batch(self):
        """알려진 한계 — 미지 인물끼리 접미가 충돌하면 병합된다.

        첫 등장 이름이 배치를 훑는 도중 색인에 편입되므로, 뒤에 오는 다른
        인물이 그 stem과 겹치면 ambiguity 가드가 발동하기 전에 흡수된다.
        아래는 고칠 목표가 아니라 **현재 동작의 상한**을 고정한 것이다.
        활성화 전 해결 조건: 라이브 오병합률 실측 후 (a) 접미 목록 축소 또는
        (b) 엔티티 name 재작성을 기지 표기 한정으로 좁히는 결정.
        """
        resolver = AliasResolver([])
        resolved, counts = resolver.apply([entity("하린"), entity("하린이")])
        self.assertEqual([item["name"] for item in resolved], ["하린", "하린"])
        self.assertEqual(counts["alias_entity_renamed"], 1)

    def test_user_placeholder_stays_literal(self):
        resolver = AliasResolver(["{{user}}", "세라"])
        self.assertEqual(resolver.resolve(USER_PLACEHOLDER), USER_PLACEHOLDER)

    def test_apply_counts_entity_renames_apart_from_reference_binding(self):
        resolver = AliasResolver(["세라"])
        items = [entity("세라야"), fact(["세라"]), relation("소속", source="세라는", target="은빛 상단")]
        resolved, counts = resolver.apply(items)
        self.assertEqual(resolved[0]["name"], "세라")
        self.assertEqual(resolved[1]["subjectNames"], ["세라"])
        self.assertEqual(resolved[2]["sourceName"], "세라")
        self.assertEqual(resolved[2]["targetName"], "은빛 상단")
        # 위험 축(엔티티 재작성) 1건과 안전 축(참조 결속) 1건이 분리돼야 한다.
        self.assertEqual(counts, {"alias_entity_renamed": 1, "alias_reference_bound": 1})
        self.assertEqual(items[0]["name"], "세라야")

    def test_apply_binds_references_to_a_first_seen_batch_entity(self):
        resolver = AliasResolver([])
        items = [entity("하린"), fact(["하린이"]), relation("친구", source="하린아", target="하린")]
        resolved, counts = resolver.apply(items)
        self.assertEqual(resolved[1]["subjectNames"], ["하린"])
        self.assertEqual(resolved[2]["sourceName"], "하린")
        self.assertEqual(counts, {"alias_entity_renamed": 0, "alias_reference_bound": 2})


if __name__ == "__main__":
    unittest.main()
