import os
import tempfile
import threading
import unittest
import zlib
from pathlib import Path
from unittest import mock

from live_broadcast_runtime import BROADCAST_BRIEFING_HEADER, DONATION_CONTINUATION_CONTRACT
from word_chain_referee import (
    MAX_SHOWS,
    WORD_CHAIN_WORDS_ENV,
    WordChainReferee,
    chain_starts,
    load_words,
    parse_move,
    ro_particle,
    with_referee_lines,
    word_chain_segment,
)


def words_tsv(folder: str, words: list[str]) -> Path:
    """A tiny word list fixture; rank follows list order."""
    path = Path(folder) / "words.tsv"
    rows = "".join(f"{word}\t{index + 1}\tA\n" for index, word in enumerate(words))
    path.write_text("# fixture\nword\trank\tlevel\n" + rows, encoding="utf-8")
    return path


class ChainRuleTests(unittest.TestCase):
    def test_chain_starts_applies_the_initial_sound_rule(self) -> None:
        for word, expected in (
            ("노래", {"래", "내"}), ("능력", {"력", "역"}), ("수량", {"량", "양"}),
            ("어머니", {"니", "이"}), ("소녀", {"녀", "여"}), ("경로", {"로", "노"}),
            ("개나리", {"리", "이"}), ("기차", {"차"}), ("하나", {"나"}), ("알루미늄", {"늄", "윰"}),
        ):
            with self.subTest(word=word):
                self.assertEqual(chain_starts(word), expected)
        self.assertEqual(chain_starts(""), set())

    def test_ro_particle_follows_the_final_consonant(self) -> None:
        for syllable, particle in (("늄", "으로"), ("강", "으로"), ("범", "으로"), ("리", "로"), ("차", "로"), ("달", "로")):
            with self.subTest(syllable=syllable):
                self.assertEqual(ro_particle(syllable), particle)


class MoveParsingTests(unittest.TestCase):
    # 분위기, 오늘, 시작 and 단어 are nouns of the real learner list too.
    NOUNS = frozenset(("기차", "차표", "사과", "노래", "내일", "분위기", "오늘", "시작", "단어", "이사", "나이"))

    def test_round_start_takes_the_last_list_noun_only_after_a_start_cue(self) -> None:
        for chat in (
            "[YouTube] 내가 먼저 한다 기차", "[YouTube] 기차로 시작", "[YouTube] 첫 단어는 기차",
            "[YouTube] 기차가 첫 단어", "[YouTube] 기차 ㄱ", "[YouTube] 기차 고고!", "[YouTube] 나 기차 할게요",
            "[2026-09-29 21:00] [YouTube] 사과 말고 기차 간다 ㅋㅋ",
        ):
            with self.subTest(chat=chat):
                self.assertEqual(parse_move(chat, "", self.NOUNS), "기차")
        for chat in ("[YouTube] 오늘 기차 탔어", "[YouTube] 기차 사과 ㅋㅋ", "[YouTube] 먼저 한다 대박"):
            with self.subTest(chat=chat):
                self.assertEqual(parse_move(chat, "", self.NOUNS), "")

    def test_round_start_takes_a_lone_token_even_off_the_list(self) -> None:
        self.assertEqual(parse_move("[YouTube] 우산ㅋㅋ!!", "", self.NOUNS), "우산")
        self.assertEqual(parse_move("[YouTube] 기차가!", "", self.NOUNS), "기차")
        self.assertEqual(parse_move("[YouTube] 이건 좀 대박", "", self.NOUNS), "")

    def test_a_lone_reaction_is_never_a_move(self) -> None:
        # Chat reacts with one word all the time; "대박" must not be judged 무효 or open a round.
        for chat in ("[YouTube] 대박ㅋㅋ!!", "[YouTube] 진짜", "[YouTube] 인정", "[YouTube] 미쳤다",
                     "[YouTube] 레알", "[YouTube] 실화냐", "[YouTube] 역시"):
            for previous in ("", "기차", "도시"):
                with self.subTest(chat=chat, previous=previous):
                    self.assertEqual(parse_move(chat, previous, self.NOUNS | {"진짜", "인정"}), "")

    def test_a_lone_cue_word_is_a_cue_unless_it_chains(self) -> None:
        for chat in ("[YouTube] 시작!", "[YouTube] 고고", "[YouTube] 먼저 ㄱㄱ"):
            with self.subTest(chat=chat):
                self.assertEqual(parse_move(chat, "", self.NOUNS), "")
                self.assertEqual(parse_move(chat, "기차", self.NOUNS), "")
        self.assertEqual(parse_move("[YouTube] 시작!", "도시", self.NOUNS), "시작")

    def test_mid_round_takes_the_last_chaining_noun_or_cued_token(self) -> None:
        chat = "[YouTube] 그럼 내가 한다 차표! 아이리 표로 시작하는 거"
        self.assertEqual(parse_move(chat, "기차", self.NOUNS), "차표")
        self.assertEqual(parse_move("[YouTube] 음 내일 어때", "노래", self.NOUNS), "내일")
        self.assertEqual(parse_move("[YouTube] 차표로 할게", "기차", self.NOUNS), "차표")
        self.assertEqual(parse_move("[YouTube] 이럼 정답", "차이", self.NOUNS), "이럼")
        self.assertEqual(parse_move("[YouTube] 이거 이사", "차이", self.NOUNS), "이사")
        self.assertEqual(parse_move("[YouTube] 나이야 받아라 아니 받아", "차이", self.NOUNS), "")
        self.assertEqual(parse_move("[YouTube] 받아 나이야", "차이", self.NOUNS), "")
        self.assertEqual(parse_move("[YouTube] 받아 나이야", "하나", self.NOUNS), "나이")

    def test_mid_round_chatter_is_no_move(self) -> None:
        for previous in ("기차", "차표", "차이"):
            with self.subTest(previous=previous):
                self.assertEqual(parse_move("[YouTube] ㅋㅋㅋ 분위기 왜 이럼", previous, self.NOUNS), "")
        self.assertEqual(parse_move("[YouTube] 이거 뭐야 ㅋㅋ", "차이", self.NOUNS), "")
        self.assertEqual(parse_move("[YouTube] 이럼 어쩌라고", "차이", self.NOUNS), "")

    def test_mid_round_lone_token_is_a_move_even_when_it_does_not_chain(self) -> None:
        self.assertEqual(parse_move("[YouTube] 사과!!", "기차", self.NOUNS), "사과")
        self.assertEqual(parse_move("[YouTube] 사과 먹고 싶다", "기차", self.NOUNS), "")

    def test_round_start_chatter_is_no_move_even_with_list_nouns(self) -> None:
        for chat in ("[YouTube] ㅋㅋㅋ 분위기 왜 이럼", "[YouTube] 안녕 아이리 오늘 뭐해"):
            with self.subTest(chat=chat):
                self.assertEqual(parse_move(chat, "", self.NOUNS), "")
        for chat in ("[YouTube] ㅋㅋㅋㅋ", "[YouTube] ?!", "", None, 3, "[YouTube] 차 차표로시작하는거"):
            with self.subTest(chat=chat):
                self.assertEqual(parse_move(chat, "기차", self.NOUNS), "")

    def test_one_trailing_particle_is_dropped_only_to_reach_a_list_noun(self) -> None:
        for chat, expected in (
            ("[YouTube] 기차로", "기차"), ("[YouTube] 기차요", "기차"), ("[YouTube] 기차임", "기차"),
            ("[YouTube] 분위기를", "분위기"), ("[YouTube] 나이야", "나이"), ("[YouTube] 이사이요", "이사"),
            ("[YouTube] 대박이야", "대박이야"), ("[YouTube] 차로", "차로"), ("[YouTube] 나이", "나이"),
        ):
            with self.subTest(chat=chat):
                self.assertEqual(parse_move(chat, "", self.NOUNS), expected)


class BriefingPlacementTests(unittest.TestCase):
    NOTE = (
        "[오늘 방송]\n- 주제: 두 번째 방송\n- 지금 구간: 끝말잇기 1라운드\n- 상황: 대결 중.\n"
        "- 주제에서 벗어난 채팅에는 짧게 반응하고 현재 주제로 돌아와."
    )

    def test_only_the_segment_line_names_the_game(self) -> None:
        self.assertTrue(word_chain_segment(self.NOTE))
        for note in (
            "[오늘 방송]\n- 주제: 끝말잇기 대결\n- 지금 구간: 마무리",
            "[오늘 방송]\n- 주제: 첫 방송\n- 지금 구간: 오프닝\n- 상황: 끝말잇기 얘기가 나왔다.",
            "[오늘 방송]\n- 주제: 첫 방송\n- 지금 구간: 오프닝\n\n" + BROADCAST_BRIEFING_HEADER + "\n- 채팅 집계: 끝말잇기 하자 12",
            "", None,
        ):
            with self.subTest(note=note):
                self.assertFalse(word_chain_segment(note))

    def test_lines_go_under_the_briefing_header(self) -> None:
        lines = ("- 심판 판정: 기차 유효, AIRI 차례", "- AIRI 낼 단어: 차표")
        briefed = self.NOTE + "\n\n" + BROADCAST_BRIEFING_HEADER + "\n- 채팅 집계: 기차 5"
        self.assertEqual(with_referee_lines(briefed, lines), briefed + "\n" + "\n".join(lines))
        self.assertEqual(
            with_referee_lines(self.NOTE, lines),
            self.NOTE + "\n\n" + BROADCAST_BRIEFING_HEADER + "\n" + "\n".join(lines),
        )
        donation = briefed + "\n\n" + DONATION_CONTINUATION_CONTRACT
        self.assertEqual(
            with_referee_lines(donation, lines),
            briefed + "\n" + "\n".join(lines) + "\n\n" + DONATION_CONTINUATION_CONTRACT,
        )
        for note in (self.NOTE, briefed, donation):
            with self.subTest(note=note[-12:]):
                self.assertIs(with_referee_lines(note, ()), note)


class RefereeTests(unittest.TestCase):
    def referee(self, words: list[str]) -> WordChainReferee:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        referee = WordChainReferee.from_path(words_tsv(folder.name, words))
        self.assertTrue(referee.enabled)
        return referee

    def test_accept_repeat_mismatch_and_loss_follow_the_round(self) -> None:
        referee = self.referee(["가수", "수가", "가구", "구수"])
        self.assertEqual(referee.judge("show-a", "[YouTube] 내가 먼저 한다 가수"),
                         ("- 심판 판정: 가수 유효, AIRI 차례", "- AIRI 낼 단어: 수가"))
        self.assertEqual(referee.judge("show-a", "[YouTube] 가구!"),
                         ("- 심판 판정: 가구 유효, AIRI 차례", "- AIRI 낼 단어: 구수"))
        self.assertEqual(referee.judge("show-a", "[YouTube] 수가"), ("- 심판 판정: 수가 무효(이미 나옴), 다시",))
        self.assertEqual(referee.judge("show-a", "[YouTube] 사과"),
                         ("- 심판 판정: 사과 무효(끝 글자와 안 이어짐), 다시",))
        self.assertEqual(referee.judge("show-a", "[YouTube] ㅋㅋㅋ 분위기 왜 이럼"), ())
        # 수가 is the only 수 word and it is used, so AIRI loses; a word off the list is still valid.
        self.assertEqual(referee.judge("show-a", "[YouTube] 수수"),
                         ("- 심판 판정: 수수 유효, AIRI 차례", "- 심판 판정: 수로 이을 단어 없음, AIRI 패"))
        # The round reset: no previous word and nothing used.
        self.assertEqual(referee.judge("show-a", "[YouTube] 가수"),
                         ("- 심판 판정: 가수 유효, AIRI 차례", "- AIRI 낼 단어: 수가"))
        self.assertEqual(referee.health(), {
            "enabled": True, "words": 4, "load_error": 0, "turns": 7,
            "accepted": 4, "rejected": 2, "airi_losses": 1,
        })

    def test_airi_answers_through_the_initial_sound_rule(self) -> None:
        referee = self.referee(["노래", "내일", "노력", "역사"])
        self.assertEqual(referee.judge("show-a", "[YouTube] 노래"),
                         ("- 심판 판정: 노래 유효, AIRI 차례", "- AIRI 낼 단어: 내일"))
        self.assertEqual(referee.judge("show-b", "[YouTube] 노력"),
                         ("- 심판 판정: 노력 유효, AIRI 차례", "- AIRI 낼 단어: 역사"))

    def test_loss_line_writes_the_particle(self) -> None:
        referee = self.referee(["알루미늄", "개나리", "기차"])
        self.assertEqual(referee.judge("show-a", "[YouTube] 알루미늄"),
                         ("- 심판 판정: 알루미늄 유효, AIRI 차례", "- 심판 판정: 늄으로 이을 단어 없음, AIRI 패"))
        self.assertEqual(referee.judge("show-a", "[YouTube] 개나리"),
                         ("- 심판 판정: 개나리 유효, AIRI 차례", "- 심판 판정: 리로 이을 단어 없음, AIRI 패"))

    def test_airi_never_repeats_the_viewer_word(self) -> None:
        referee = self.referee(["기기", "기차"])
        self.assertEqual(referee.judge("show-a", "[YouTube] 기기"),
                         ("- 심판 판정: 기기 유효, AIRI 차례", "- AIRI 낼 단어: 기차"))

    def test_airi_word_is_one_of_the_three_most_common_by_show_and_word(self) -> None:
        ranked = ["표현", "표정", "표시", "표지", "표본"]
        chosen = set()
        for index in range(12):
            show_id = f"show-{index}"
            expected = ranked[zlib.crc32((show_id + "차표").encode("utf-8")) % 3]
            first = self.referee(ranked + ["차표"]).judge(show_id, "[YouTube] 차표")
            again = self.referee(ranked + ["차표"]).judge(show_id, "[YouTube] 차표")
            with self.subTest(show_id=show_id):
                self.assertEqual(first, ("- 심판 판정: 차표 유효, AIRI 차례", f"- AIRI 낼 단어: {expected}"))
                self.assertEqual(again, first)
            chosen.add(expected)
        self.assertGreater(len(chosen), 1)

    def test_shows_keep_separate_rounds_and_close_clears_one(self) -> None:
        referee = self.referee(["기차", "차기"])
        accepted = ("- 심판 판정: 기차 유효, AIRI 차례", "- AIRI 낼 단어: 차기")
        repeated = ("- 심판 판정: 기차 무효(이미 나옴), 다시",)
        self.assertEqual(referee.judge("show-a", "[YouTube] 기차"), accepted)
        self.assertEqual(referee.judge("show-b", "[YouTube] 기차"), accepted)
        self.assertEqual(referee.judge("show-a", "[YouTube] 기차"), repeated)
        referee.close_show("show-a")
        self.assertEqual(referee.judge("show-a", "[YouTube] 기차"), accepted)
        self.assertEqual(referee.judge("show-b", "[YouTube] 기차"), repeated)
        referee.close_show("never-started")

    def test_state_is_capped_to_the_most_recent_shows(self) -> None:
        referee = self.referee(["기차", "차기"])
        accepted = ("- 심판 판정: 기차 유효, AIRI 차례", "- AIRI 낼 단어: 차기")
        for index in range(MAX_SHOWS + 1):
            self.assertEqual(referee.judge(f"show-{index}", "[YouTube] 기차"), accepted)
        self.assertEqual(referee.judge(f"show-{MAX_SHOWS}", "[YouTube] 기차"), ("- 심판 판정: 기차 무효(이미 나옴), 다시",))
        self.assertEqual(referee.judge("show-0", "[YouTube] 기차"), accepted)

    def test_judging_is_thread_safe(self) -> None:
        referee = self.referee(["기차", "차기"])
        results: list[tuple[str, ...]] = []
        threads = [threading.Thread(target=lambda: results.append(referee.judge("show-a", "[YouTube] 기차")))
                   for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(len(result) for result in results), [1] * 7 + [2])
        self.assertEqual(referee.health()["accepted"], 1)

    def test_no_line_ever_rejects_a_word_as_missing_from_the_dictionary(self) -> None:
        referee = self.referee(["기차", "차표"])
        lines = referee.judge("show-a", "[YouTube] 기차") + referee.judge("show-a", "[YouTube] 표범")
        self.assertEqual(lines[-2:], ("- 심판 판정: 표범 유효, AIRI 차례", "- 심판 판정: 범으로 이을 단어 없음, AIRI 패"))
        self.assertFalse(any("사전" in line for line in lines))


class WordListLoadTests(unittest.TestCase):
    def test_env_unset_or_empty_is_off_without_an_error(self) -> None:
        for value in (None, "", "   "):
            with self.subTest(value=value), mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop(WORD_CHAIN_WORDS_ENV, None)
                if value is not None:
                    os.environ[WORD_CHAIN_WORDS_ENV] = value
                referee = WordChainReferee.from_env()
                self.assertFalse(referee.enabled)
                self.assertEqual(referee.judge("show-a", "[YouTube] 기차"), ())
                self.assertEqual(referee.health(), {
                    "enabled": False, "words": 0, "load_error": 0, "turns": 0,
                    "accepted": 0, "rejected": 0, "airi_losses": 0,
                })

    def test_env_path_loads_comments_bom_and_blank_lines(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "words.tsv"
            path.write_bytes(
                "﻿# source\r\n# license\r\nword\trank\tlevel\r\n기차\t7\tA\r\n\r\n차표\t3\tC\r\n".encode("utf-8")
            )
            self.assertEqual(load_words(path), {"기차": 7, "차표": 3})
            with mock.patch.dict(os.environ, {WORD_CHAIN_WORDS_ENV: str(path)}):
                referee = WordChainReferee.from_env()
            self.assertTrue(referee.enabled)
            self.assertEqual(referee.health()["words"], 2)

    def test_unreadable_or_malformed_list_is_off_and_counted(self) -> None:
        header = "word\trank\tlevel\n"
        with tempfile.TemporaryDirectory() as folder:
            cases = {
                "no-header": "기차\t1\tA\n",
                "wrong-header": "word\trank\n기차\t1\n",
                "header-only": "# comment\n" + header,
                "short-row": header + "기차\t1\n",
                "bad-rank": header + "기차\t하나\tA\n",
                "not-hangul": header + "train\t1\tA\n",
                "one-syllable": header + "차\t1\tA\n",
            }
            paths = {}
            for name, text in cases.items():
                paths[name] = Path(folder) / f"{name}.tsv"
                paths[name].write_text(text, encoding="utf-8")
            paths["not-utf8"] = Path(folder) / "not-utf8.tsv"
            paths["not-utf8"].write_bytes(header.encode("utf-8") + "기차\t1\tA\n".encode("cp949"))
            paths["missing"] = Path(folder) / "missing.tsv"
            paths["directory"] = Path(folder)
            for name, path in paths.items():
                with self.subTest(case=name), mock.patch.dict(os.environ, {WORD_CHAIN_WORDS_ENV: str(path)}):
                    referee = WordChainReferee.from_env()
                    self.assertFalse(referee.enabled)
                    self.assertEqual(referee.judge("show-a", "[YouTube] 기차"), ())
                    health = referee.health()
                    self.assertEqual((health["words"], health["load_error"], health["turns"]), (0, 1, 0))


if __name__ == "__main__":
    unittest.main()
