from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location("broadcast_continuity_v3", HERE / "synthesize_broadcast_continuity_v3.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = load()


def card(index: int) -> dict[str, str]:
    return {
        "local_id": f"c{index:03d}", "viewer_alias": f"시청자별명{index}", "other_alias": f"다른별명{index}",
        "topic": f"주제화면{index}", "fact_statement": f"나는 증거물{index}을 찾았어.",
        "evidence_clause": f"시청자별명{index}가 증거물{index} 찾은 건 기억나.", "evidence_token": f"증거물{index}",
        "fact_reaction": f"장면반응{index}이 충분해서 다음 판단도 달라졌겠다.", "next_move": f"다음 장면{index}부터 이어볼게.",
        "unrelated_statement": f"다른사람{index}은 금지명사{index}을 좋아해.", "unrelated_token": f"금지명사{index}",
        "update_statement": f"오늘은 증거물{index} 대신 새증거{index}로 바꿨어.",
        "updated_clause": f"새증거{index}로 바꾼 내용을 받았어.", "updated_token": f"새증거{index}",
        "recall_prompt": f"내 증거물{index} 기억해?", "related_prompt": f"다음 장면{index} 골라줘.",
        "unknown_prompt": f"내 금지명사{index} 기억해?", "topic_return_prompt": f"주제화면{index}으로 돌아가자.",
    }


def v2_row(index: int) -> dict[str, str]:
    categories = ("donation_content", "donation_ritual", "donation_burst", "selected_proposal")
    category = categories[index % len(categories)]
    target = f"후원자{index} 고마워. 본문내용{index}을 받아 장면선택{index}부터 정리할게. 화면흐름{index}으로 돌아가 다음순서{index}도 차분히 이어가자."
    return {
        "id": f"bbv2-{index:04d}", "source_local_id": f"v{index:03d}", "split": "train" if index < 188 else "dev" if index < 214 else "test",
        "category": category, "prompt": f"원본질문{index}", "target": target,
    }


class BroadcastContinuityV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards = [card(index) for index in range(120)]
        cls.v2 = [v2_row(index) for index in range(240)]
        cls.rows = builder.build_records(cls.cards, cls.v2)
        cls.chat = builder.export_chat(cls.rows)

    def test_count_categories_and_card_group_splits_are_fixed(self):
        self.assertEqual(len(self.rows), 1440)
        card_rows = [row for row in self.rows if row["source"] == "continuity-card-v3"]
        self.assertEqual(Counter(row["category"] for row in card_rows), Counter({category: 120 for category in builder.CATEGORIES}))
        self.assertEqual(Counter(row["split"] for row in card_rows), {"train": 960, "dev": 120, "test": 120})
        groups = defaultdict(set)
        for row in card_rows:
            groups[row["scenario_group"]].add(row["split"])
        self.assertTrue(all(len(value) == 1 for value in groups.values()))

    def test_chat_export_uses_runtime_shape_and_constants(self):
        self.assertEqual(len(self.chat), 1440)
        for source, chat in zip(self.rows, self.chat):
            messages = chat["messages"]
            self.assertEqual(messages[0], {"role": "system", "content": builder.production_system_content()})
            self.assertIn(builder.build_broadcast_contract_block(), messages[0]["content"])
            current_user = messages[-2]
            self.assertEqual(current_user["role"], "user")
            self.assertTrue(current_user["content"].startswith("[YouTube] "))
            self.assertEqual(messages[-1]["role"], "assistant")
            active = next(message for message in messages if message.get("role") == "system" and "[오늘 방송]" in message.get("content", ""))
            self.assertIn(builder.BRIEFING_HEADER, active["content"])
            local = messages[-3]
            self.assertEqual(local["role"], "system")
            self.assertNotIn("name", local)
            self.assertEqual(local["content"], builder.broadcast_style_contract())
            self.assertLessEqual(sum(message["role"] == "user" for message in messages[:-2]), 2)
            if source["source"] == "continuity-card-v3":
                aliases = (source["card"]["viewer_alias"], source["card"]["other_alias"])
                self.assertTrue(all(alias not in current_user["content"] and alias not in messages[-1]["content"] for alias in aliases))
            self.assertEqual(source["review"], builder.REVIEW)
            self.assertEqual(chat["review"], builder.REVIEW)

    def test_memory_evidence_is_not_copied_into_active_briefing(self):
        indexed_chat = {row["id"]: row for row in self.chat}
        for row in self.rows:
            if row["source"] != "continuity-card-v3" or row["category"] not in {"memory_immediate", "memory_delayed", "memory_update"}:
                continue
            messages = indexed_chat[row["id"]]["messages"]
            card_data = row["card"]
            active = next(message["content"] for message in messages if message.get("role") == "system" and "[오늘 방송]" in message.get("content", ""))
            memory = next(message["content"] for message in messages if message.get("content", "").startswith("[Character Memory]"))
            self.assertIn(card_data["evidence_token"], memory)
            if row["category"] in {"memory_immediate", "memory_delayed"}:
                self.assertNotIn(card_data["evidence_token"], active)
            if row["category"] == "memory_delayed":
                marker = next(index for index, message in enumerate(messages) if message.get("content", "").startswith("[Untrusted Journal Recall]"))
                self.assertEqual(messages[marker + 1]["role"], "user")
                self.assertIn(card_data["evidence_token"], messages[marker + 1]["content"])

    def test_skeleton_variants_are_bounded(self):
        skeletons = Counter(builder._skeleton(row) for row in self.rows if row["source"] == "continuity-card-v3")
        self.assertLessEqual(max(skeletons.values()), 15)
        self.assertGreaterEqual(len(skeletons), len(builder.CATEGORIES) * 8)
        for row in self.rows:
            self.assertIn(
                len(__import__("re").findall(r"[.!?](?:\s|$)", row["target"])),
                {2, 3, 4},
            )
            self.assertNotRegex(row["target"], r"기억해\s*둘게")

    def test_source_serialization_omits_full_card_and_keeps_review_provenance(self):
        serialized = [json.loads(line) for line in builder.render_jsonl(self.rows).splitlines()]
        self.assertEqual(len(serialized), 1440)
        self.assertTrue(all("card" not in row for row in serialized))
        self.assertTrue(all(row["review"] == builder.REVIEW for row in serialized))

    def test_evidence_updates_and_hard_negative_decoys_are_enforced(self):
        for row in self.rows:
            if row["source"] != "continuity-card-v3":
                continue
            card_data, target = row["card"], row["target"]
            if row["category"] != "hard_negative":
                self.assertIn(row["required_token"], target)
            if row["category"] == "memory_update":
                self.assertIn(card_data["updated_token"], target)
                if card_data["evidence_token"] not in card_data["updated_clause"]:
                    self.assertNotIn(card_data["evidence_token"], target)
            if row["category"] == "hard_negative":
                self.assertTrue(any(marker in target for marker in (
                    "모르겠어", "알 수 없어", "단정은 못 해", "답을 만들 순 없어",
                    "거짓말", "지어내진 않을게", "맞다고도 아니라고도 못 하겠어",
                )))
                self.assertNotIn(card_data["unrelated_token"], target)
                for token in builder.hard_negative_banned_tokens(card_data):
                    self.assertNotIn(token, target)

    def test_card_tokens_must_be_literal_in_both_evidence_surfaces(self):
        broken = copy.deepcopy(self.cards[0])
        broken["evidence_token"] = "없는토큰"
        with self.assertRaisesRegex(ValueError, "evidence_token must be literal"):
            builder.validate_card_tokens(broken, "fixture")

    def test_donation_v2_target_omits_renderer_owned_opener(self):
        by_id = {row["id"]: row for row in self.rows}
        for original in self.v2:
            row = by_id["v2-" + original["id"]]
            if original["category"] in builder.DONATION_CATEGORIES:
                self.assertNotIn("후원자", row["target"])
                active = next(message for message in next(item for item in self.chat if item["id"] == row["id"])["messages"] if message.get("role") == "system" and "[오늘 방송]" in message.get("content", ""))
                self.assertIn(builder.donation_continuation_contract(), active["content"])
            else:
                self.assertEqual(row["target"], original["target"])
            active = next(message for message in next(item for item in self.chat if item["id"] == row["id"])["messages"] if message.get("role") == "system" and "[오늘 방송]" in message.get("content", ""))
            self.assertIn(original.get("briefing", ""), active["content"])

    def test_duplicate_and_leak_mutations_fail_closed(self):
        duplicate = copy.deepcopy(self.rows)
        duplicate[-1]["target"] = duplicate[-2]["target"]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            builder.validate_records(duplicate)

        leaked = copy.deepcopy(self.rows)
        row = next(row for row in leaked if row["category"] == "hard_negative")
        row["target"] += " " + row["card"]["unrelated_statement"]
        with self.assertRaisesRegex(ValueError, "hard-negative"):
            builder.validate_records(leaked)


if __name__ == "__main__":
    unittest.main()
