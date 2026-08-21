"""Pure offline B3-d regression evaluator for the input rule prefilter."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

SUITE_ID = "airi_ko_input_safety_b3d"
SCHEMA_VERSION = 2
RUNNER_VERSION = "2"
POLICY_SHA256 = "64a7d9bdb152aeb458bfa2a5a43b31c2d25d5e085c5e070d6b8ebc28dfe9525d"
CANONICAL_FIXTURE_SHA256 = "8d535bd52833d34eb268da92d2fc156cebedf7ab3c0adbce00cd3c161a6e3dad"
MAX_FIXTURE_BYTES = 256 * 1024
FIXTURE_PATH = Path(__file__).with_name("airi_ko_input_safety_corpus.json")

CATEGORIES = (
    "persona_takeover", "profanity", "sexual_explicit", "targeted_harassment", "privacy",
    "unsupported_language",
)
LANGUAGES = frozenset(("ko", "mixed", "en", "fr", "es", "ja", "zh"))
TRANSFORMATIONS = frozenset((
    "plain", "spacing", "punctuation", "zero_width", "nfkc", "casefold", "code_switch",
    "contextual", "euphemistic",
))
SEMANTIC_FAMILIES = frozenset((
    "contextual_quote", "euphemism", "indirect_persona", "coded_harassment", "ambiguous_privacy",
))
FAMILIES = frozenset(("benign", *CATEGORIES, *SEMANTIC_FAMILIES))


class EvalError(RuntimeError):
    """Sanitized failure for an invalid fixture, policy, or report write."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _has_hangul(text: str) -> bool:
    return any("\uac00" <= character <= "\ud7a3" for character in text)


def _language_matches(label: str, text: str) -> bool:
    normalized = unicodedata.normalize("NFKC", text)
    has_hangul = _has_hangul(normalized)
    has_latin = any("a" <= character.casefold() <= "z" for character in normalized)
    has_kana = any(0x3040 <= ord(character) <= 0x30FF for character in normalized)
    has_cjk = any(0x3400 <= ord(character) <= 0x9FFF for character in normalized)
    if label == "ko":
        return has_hangul
    if label == "mixed":
        return has_hangul and has_latin
    if label in {"en", "fr", "es"}:
        return has_latin and not has_hangul and not has_kana and not has_cjk
    if label == "ja":
        return has_kana
    if label == "zh":
        return has_cjk and not has_kana
    return False


def _valid_text(text: object, transformation: object) -> bool:
    if not isinstance(text, str) or not text or len(text) > 1_100:
        return False
    try:
        encoded = text.encode("utf-8", "strict")
    except UnicodeError:
        return False
    if len(encoded) > 4_400 or unicodedata.normalize("NFC", text) != text:
        return False
    zero_width = 0
    for character in text:
        category = unicodedata.category(character)
        if category in {"Cc", "Cs"} or "\u202a" <= character <= "\u202e" or "\u2066" <= character <= "\u2069":
            return False
        if category == "Cf":
            if transformation != "zero_width" or character != "\u200b":
                return False
            zero_width += 1
    return zero_width <= 2


def validate_fixture(fixture: object) -> None:
    if not isinstance(fixture, dict) or set(fixture) != {"suite_id", "schema_version", "policy_sha256", "cases"}:
        raise EvalError("fixture schema mismatch")
    if (
        fixture["suite_id"] != SUITE_ID
        or type(fixture["schema_version"]) is not int
        or fixture["schema_version"] != SCHEMA_VERSION
    ):
        raise EvalError("fixture suite mismatch")
    if fixture["policy_sha256"] != POLICY_SHA256 or not isinstance(fixture["cases"], list):
        raise EvalError("fixture policy mismatch")
    cases = fixture["cases"]
    if len(cases) != 120:
        raise EvalError("fixture case count mismatch")
    required = {
        "id", "partition", "language", "family", "transformation", "text",
        "text_sha256", "expected_allowed", "expected_category", "expected_rule",
        "review_status",
    }
    partitions = Counter()
    contract_buckets = Counter()
    languages = Counter()
    ids = set()
    texts = set()
    contract_hangul = 0
    for position, case in enumerate(cases, 1):
        if (
            not isinstance(case, dict)
            or set(case) != required
            or case["id"] != f"b3d_{position:03d}"
            or case["id"] in ids
        ):
            raise EvalError("fixture case schema mismatch")
        if (
            case["language"] not in LANGUAGES
            or case["family"] not in FAMILIES
            or case["transformation"] not in TRANSFORMATIONS
        ):
            raise EvalError("fixture enum mismatch")
        if not _valid_text(case["text"], case["transformation"]) or case["text"] in texts:
            raise EvalError("fixture text mismatch")
        if not _language_matches(case["language"], case["text"]):
            raise EvalError("fixture language mismatch")
        if (
            not isinstance(case["text_sha256"], str)
            or case["text_sha256"] != sha256(case["text"].encode("utf-8"))
        ):
            raise EvalError("fixture text hash mismatch")
        ids.add(case["id"])
        texts.add(case["text"])
        partitions[case["partition"]] += 1
        languages[case["language"]] += 1
        if case["partition"] == "semantic_gap":
            semantic_contract = (
                case["expected_allowed"], case["expected_category"],
                case["expected_rule"], case["review_status"],
            )
            if (
                case["family"] not in SEMANTIC_FAMILIES
                or semantic_contract != (None, None, None, "human_review_only")
            ):
                raise EvalError("semantic case mismatch")
            continue
        if (
            case["partition"] not in {"policy_bound", "adversarial_transform"}
            or type(case["expected_allowed"]) is not bool
            or case["review_status"] != "policy_contract"
        ):
            raise EvalError("contract case mismatch")
        if case["expected_allowed"]:
            if (case["family"], case["expected_category"], case["expected_rule"]) != ("benign", "", ""):
                raise EvalError("allowed case mismatch")
            bucket = "allowed"
        else:
            if (
                case["family"] not in CATEGORIES
                or case["expected_category"] != case["family"]
                or case["expected_rule"] not in {"term", "pattern"}
            ):
                raise EvalError("blocked case mismatch")
            bucket = case["family"]
        contract_buckets[(case["partition"], bucket)] += 1
        contract_hangul += _has_hangul(case["text"])
    if partitions != Counter(policy_bound=70, adversarial_transform=30, semantic_gap=20):
        raise EvalError("fixture partition mismatch")
    if any(
        contract_buckets[("policy_bound", bucket)] != 10
        for bucket in ("allowed", *CATEGORIES)
    ):
        raise EvalError("policy bucket mismatch")
    if (
        any(
            contract_buckets[("adversarial_transform", category)] != 5
            for category in CATEGORIES
        )
        or contract_hangul < 70
        or languages["ko"] < 80
    ):
        raise EvalError("fixture diversity mismatch")


def load_fixture(path: Path = FIXTURE_PATH) -> tuple[dict, bytes]:
    try:
        size = path.stat().st_size
        if size < 1 or size > MAX_FIXTURE_BYTES:
            raise EvalError("fixture size mismatch")
        raw = path.read_bytes()
    except OSError as exc:
        raise EvalError("fixture unreadable") from exc
    if len(raw) != size:
        raise EvalError("fixture size mismatch")
    if CANONICAL_FIXTURE_SHA256 and sha256(raw) != CANONICAL_FIXTURE_SHA256:
        raise EvalError("fixture hash mismatch")
    try:
        fixture = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvalError("fixture invalid") from exc
    validate_fixture(fixture)
    return fixture, raw


def _runtime():
    proxy_dir = str(Path(__file__).resolve().parents[2])
    added = proxy_dir not in sys.path
    if added:
        sys.path.insert(0, proxy_dir)
    try:
        from input_screening import InputScreeningRuntime, load_input_screening_policy
        policy = load_input_screening_policy()
        if policy.sha256 != POLICY_SHA256:
            raise EvalError("policy hash mismatch")
        return InputScreeningRuntime(enabled=True, policy=policy), policy
    finally:
        if added:
            sys.path.remove(proxy_dir)


def evaluate(fixture_path: Path = FIXTURE_PATH) -> dict:
    fixture, raw = load_fixture(fixture_path)
    runtime, policy = _runtime()
    partitions = Counter()
    buckets = Counter()
    languages = Counter()
    semantic = Counter()
    transforms = defaultdict(Counter)
    exact = 0
    allow_false_positive = 0
    block_false_negative = 0
    category_mismatch = 0
    rule_mismatch = 0
    rows = []
    for case in fixture["cases"]:
        verdict = runtime.inspect(case["text"])
        actual = {
            "allowed": verdict.allowed,
            "category": verdict.category,
            "rule": verdict.rule,
        }
        expected = {
            "allowed": case["expected_allowed"],
            "category": case["expected_category"],
            "rule": case["expected_rule"],
        }
        row = {
            "id": case["id"],
            "partition": case["partition"],
            "family": case["family"],
            "transformation": case["transformation"],
            "expected": expected,
            "actual": actual,
            "exact": None,
        }
        partitions[case["partition"]] += 1
        buckets[case["family"]] += 1
        languages[case["language"]] += 1
        if case["partition"] == "semantic_gap":
            semantic[
                (verdict.allowed, verdict.category, verdict.rule, case["family"])
            ] += 1
        else:
            row["exact"] = actual == expected
            exact += row["exact"]
            if case["partition"] == "adversarial_transform":
                key = (case["transformation"], case["family"])
                transforms[key]["exact" if row["exact"] else "mismatch"] += 1
            if not row["exact"]:
                if case["expected_allowed"] and not verdict.allowed:
                    allow_false_positive += 1
                elif not case["expected_allowed"] and verdict.allowed:
                    block_false_negative += 1
                elif verdict.category != case["expected_category"]:
                    category_mismatch += 1
                else:
                    rule_mismatch += 1
        rows.append(row)
    return {
        "schema_version": SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "suite_id": SUITE_ID,
        "fixture_sha256": sha256(raw),
        "evaluator_sha256": sha256(Path(__file__).read_bytes()),
        "policy_sha256": policy.sha256,
        "counts": {
            "partition": dict(partitions),
            "bucket": dict(buckets),
            "language": dict(languages),
            "contract_total": 100,
            "contract_exact": exact,
            "allow_false_positive": allow_false_positive,
            "block_false_negative": block_false_negative,
            "category_mismatch": category_mismatch,
            "rule_mismatch": rule_mismatch,
        },
        "transform_metrics": {
            f"{transformation}/{family}": dict(value)
            for (transformation, family), value in sorted(transforms.items())
        },
        "semantic_histogram": {
            f"allowed={allowed},category={category},rule={rule},family={family}": count
            for (allowed, category, rule, family), count in sorted(semantic.items())
        },
        "cases": rows,
        "policy_contract_gate": "PASS" if exact == 100 else "FAIL",
        "semantic_safety_claim": False,
        "installed_airi_claim": False,
        "runtime_changed": False,
        "b3d_overall": "FAIL",
        "operational_gate": "OFF",
    }


def write_report(report: dict, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".b3d-", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        os.replace(temporary, destination)
    except OSError as exc:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise EvalError("report write failed") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="offline B3-d input safety evaluator")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    try:
        report = evaluate()
        if arguments.output:
            write_report(report, arguments.output)
    except EvalError:
        return 2
    return 0 if report["policy_contract_gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
