"""대량 지식 배치의 사전 검증과 적재 후 회수율 실측.  네트워크·모델을 접촉하지 않는다.

`knowledge_ingest.py` 는 레코드 단위 스키마만 본다.  대량 적재에서 실제로 사고가 나는 지점은
그 바깥이다.

  lint  — 배치 상한(파일당 1,000건·2MB), 배치 간 title 중복, alias 품질, content 길이 분포,
          예상 청크 수를 본다.  content 를 길게 쓰면 청크가 쪼개져 서로 경쟁하고 top_k=4·
          max_chars=1600 예산에서 정작 필요한 조각이 밀린다.
  probe — 적재된 DB 에 실제 질의를 던져 회수 여부를 잰다.  적재 성공과 검색 성공은 다르다.
          2026-08-27 실측에서 지식 계층은 enabled=True 인데 documents=0 이었다.

출력에 본문을 넣지 않는다 — 제목·건수·판정만 낸다.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Sequence

from knowledge_store import (
    CHUNK_CHARS, KnowledgeInputError, KnowledgeStore, chunk_text, runtime_path, validate_record,
)
# 검색이 실제로 쓰는 토크나이저와 불용어를 그대로 빌린다.  다른 토크나이저로 후보를 뽑으면
# 적재한 제목이 회수 시 질의어와 어긋난다.
from knowledge_store import _QUERY_STOP_TERMS, _tokens  # noqa: E402

# knowledge_ingest.py 와 같은 상한.  두 곳이 어긋나면 lint 가 통과시킨 배치를 ingest 가 거부한다.
MAX_INPUT_BYTES = 2_000_000
MAX_RECORDS = 1_000
# retrieve() 기본값.  방송 지연은 적재량이 아니라 이 예산이 정한다.
DEFAULT_TOP_K = 4
DEFAULT_MAX_CHARS = 1600
# 한 레코드가 이보다 길면 청크가 쪼개져 서로 경쟁한다(계약 §4-1).
RECOMMENDED_CONTENT_CHARS = 3_000
MIN_ALIASES = 2


def load_lines(path: Path) -> list[dict]:
    records = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise KnowledgeInputError(f"{path.name}:{number} JSON 파싱 실패: {exc}") from exc
    return records


def lint_file(path: Path) -> dict:
    size = path.stat().st_size
    raw = load_lines(path)
    problems: list[str] = []
    if size > MAX_INPUT_BYTES:
        problems.append(f"파일 크기 {size:,}B 가 상한 {MAX_INPUT_BYTES:,}B 초과 — 배치를 쪼갤 것")
    if len(raw) > MAX_RECORDS:
        problems.append(f"레코드 {len(raw)}건이 상한 {MAX_RECORDS}건 초과 — 배치를 쪼갤 것")

    valid, titles, lengths, chunk_counts, thin_alias, long_content = [], Counter(), [], [], [], []
    for index, record in enumerate(raw, start=1):
        try:
            cleaned = validate_record(record)
        except KnowledgeInputError as exc:
            problems.append(f"레코드 {index}: {exc}")
            continue
        valid.append(cleaned)
        titles[cleaned["title"]] += 1
        lengths.append(len(cleaned["content"]))
        chunk_counts.append(len(chunk_text(cleaned["content"])))
        if len(cleaned["aliases"]) < MIN_ALIASES:
            thin_alias.append(cleaned["title"])
        if len(cleaned["content"]) > RECOMMENDED_CONTENT_CHARS:
            long_content.append(cleaned["title"])

    duplicates = sorted(title for title, count in titles.items() if count > 1)
    return {
        "path": path, "bytes": size, "records": len(raw), "valid": len(valid),
        "problems": problems, "duplicates": duplicates, "thin_alias": thin_alias,
        "long_content": long_content, "lengths": lengths, "chunk_counts": chunk_counts,
        "titles": set(titles),
    }


def check_ingest_reachable(paths: Sequence[Path], runtime_dir: str | None) -> list[str]:
    """ingest 가 거부할 경로를 미리 잡는다.

    `runtime_path()` 는 상대경로를 **CWD 기준**으로 푼다.  runtime-dir 밖으로 나가면
    ingest 가 "path must be inside the configured runtime directory" 로 거부하는데,
    실측에서 lint 통과 후 ingest 만 실패하는 착시를 만들었다.  그래서 lint 가 먼저 잡는다.
    """
    if runtime_dir is None:
        return []
    root = Path(runtime_dir).resolve()
    problems = []
    for path in paths:
        try:
            runtime_path(path.resolve(), root)
        except KnowledgeInputError:
            problems.append(f"{path.name}: runtime-dir({root}) 밖이라 ingest 가 거부한다 — "
                            f"파일을 runtime-dir 안으로 옮기고 --input 에 절대경로를 준다")
    return problems


def cmd_lint(args) -> int:
    paths = [Path(p) for p in args.input]
    reports = [lint_file(path) for path in paths]
    for problem in check_ingest_reachable(paths, args.runtime_dir):
        reports[0]["problems"].append(problem)
    seen: dict[str, str] = {}
    cross: list[str] = []
    for report in reports:
        for title in sorted(report["titles"]):
            if title in seen and seen[title] != report["path"].name:
                cross.append(f"{title!r}: {seen[title]} 와 {report['path'].name}")
            seen.setdefault(title, report["path"].name)

    failed = False
    for report in reports:
        lengths, chunks = report["lengths"], report["chunk_counts"]
        print(f"\n=== {report['path'].name} ===")
        print(f"  레코드 {report['records']}건 중 유효 {report['valid']}건 · {report['bytes']:,}B")
        if lengths:
            print(f"  content 길이  중앙 {statistics.median(lengths):,.0f}자 · "
                  f"최대 {max(lengths):,}자 · 총 {sum(lengths):,}자")
            print(f"  예상 청크     총 {sum(chunks):,}개 · 레코드당 최대 {max(chunks)}개 "
                  f"(청크 {CHUNK_CHARS}자 기준)")
        for label, items in (("제목 중복", report["duplicates"]),
                             ("alias 부족(2개 미만)", report["thin_alias"]),
                             (f"content 권장 초과({RECOMMENDED_CONTENT_CHARS:,}자)",
                              report["long_content"])):
            if items:
                shown = ", ".join(items[:5]) + (" …" if len(items) > 5 else "")
                print(f"  [경고] {label} {len(items)}건: {shown}")
        for problem in report["problems"]:
            print(f"  [실패] {problem}")
        failed = failed or bool(report["problems"])

    if cross:
        print(f"\n[경고] 배치 간 제목 중복 {len(cross)}건")
        for line in cross[:10]:
            print(f"  {line}")
    print(f"\n종합: 유효 {sum(r['valid'] for r in reports)}건 / "
          f"전체 {sum(r['records'] for r in reports)}건 → "
          f"{'적재 불가 — [실패] 를 먼저 고칠 것' if failed else '적재 가능'}")
    return 1 if failed else 0


def cmd_probe(args) -> int:
    queries = [line.strip() for line in Path(args.queries).read_text(encoding="utf-8").splitlines()
               if line.strip() and not line.startswith("#")]
    if not queries:
        raise KnowledgeInputError("질의 파일이 비어 있다")
    root = Path(args.runtime_dir).resolve()
    db_path = runtime_path(args.db if Path(args.db).is_absolute() else root / args.db, root)
    store = KnowledgeStore(db_path, runtime_dir=root)
    store.initialize()
    hit = 0
    print(f"{'질의':<24}{'히트':>5}  회수된 제목")
    print("-" * 78)
    for query in queries:
        try:
            hits = store.retrieve(query, top_k=args.top_k, max_chars=args.max_chars)
        except (KnowledgeInputError, ValueError) as exc:
            print(f"{query:<24}{'오류':>5}  {exc}")
            continue
        titles = list(dict.fromkeys(item.title for item in hits))
        hit += bool(hits)
        print(f"{query:<24}{len(hits):>5}  {', '.join(titles) if titles else '(회수 없음)'}")
    print("-" * 78)
    rate = hit / len(queries)
    print(f"회수율 {hit}/{len(queries)} ({rate:.0%})")
    if args.min_hit_rate is not None and rate < args.min_hit_rate:
        print(f"기준 {args.min_hit_rate:.0%} 미달 — title·aliases 설계를 고칠 것")
        return 1
    return 0


# 가명("v" + 16진수 8자)은 시청자 식별자다.  지식 후보가 아니고 저장소로 새어서도 안 된다.
_PSEUDONYM = re.compile(r"v[0-9a-f]{8}", re.I)
# "[YouTube] 둥하" 처럼 채널 프리픽스가 붙는다.  실측에서 youtube 가 297회로 후보 1위였다.
_SOURCE_PREFIX = re.compile(r"^\s*\[[^\]]{1,20}\]\s*")
# 검색용 불용어는 의도적으로 얇아서(조사·1자 위주) 일반 어휘가 그대로 후보로 올라온다.
# 지식 문서가 될 수 없는 말만 최소한으로 거른다.
_COMMON_TERMS = frozenset("""
그럼 그래 그래서 그러면 그런데 근데 우리 오늘 내일 어제 지금 누구 누가 뭐냐 뭐야 무슨 어디 언제
다른 다른가 저거 이거 그거 여기 저기 거기 이제 아직 진짜 완전 너무 조금 많이 다시 계속 그냥
보면 봤어 봐요 되나 되나요 아님 가능 하는 한다 했어 이런 저런 그런 이렇게 저렇게 그렇게
사람 생각 얘기 이야기 방송 채팅 시청자 자기 자신 정도 때문 이번 다음 처음 마지막
""".split())


def cmd_terms(args) -> int:
    """실제 시청자 발화에서 지식 후보 어휘를 뽑는다.

    867,024 문서를 다 적재할 수는 없다.  무관한 문서가 많을수록 BM25 회수 품질도 떨어진다.
    선별 기준은 추측이 아니라 **실제로 시청자가 친 말**이어야 한다.
    """
    counts: Counter[str] = Counter()
    turns = 0
    # 같은 고정 채팅을 여러 회차 리플레이하므로, 중복을 안 지우면 한 메시지가 회차 수만큼
    # 곱해져 빈도가 의미를 잃는다(실측: 14개 review 에서 count 가 14에 몰렸다).
    # 그래서 **서로 다른 시청자 메시지**를 한 번씩만 센다.
    seen: set[str] = set()
    for path in args.review:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            turns += 1
            # 두 형식을 모두 받는다: review JSONL 은 시청자 발화가 `user`, 가명화 채팅
            # JSONL(import_public_chat 산출)은 `text` 다.  한쪽만 보면 다른 쪽에서 조용히
            # 0건이 나온다(실측: 채팅 5,243건이 "서로 다른 메시지 1건" 으로 뭉개졌다).
            spoken_raw = record.get("user") or record.get("text") or ""
            key = record.get("user_hash") or spoken_raw
            if key in seen:
                continue
            seen.add(key)
            spoken = _SOURCE_PREFIX.sub("", spoken_raw)
            for term in _tokens(spoken):
                if len(term) < 2 or term in _QUERY_STOP_TERMS or term in _COMMON_TERMS:
                    continue
                if _PSEUDONYM.fullmatch(term):
                    continue
                counts[term] += 1

    # 토크나이저가 조사를 뗀 형태와 원형을 함께 낸다(검색에서는 의도된 동작).  후보 목록에서는
    # 같은 횟수로 붙어 나오는 접두 쌍이 중복이므로, 시청자가 실제로 친 긴 쪽만 남긴다.
    ordered = sorted(counts, key=len)
    redundant = {
        short for index, short in enumerate(ordered)
        for longer in ordered[index + 1:]
        if longer.startswith(short) and counts[longer] == counts[short]
    }
    ranked = [(term, count) for term, count in counts.most_common()
              if count >= args.min_count and term not in redundant]
    if args.output:
        Path(args.output).write_text("\n".join(term for term, _c in ranked) + "\n",
                                     encoding="utf-8")
    print(f"시청자 발화 {turns}턴 → 서로 다른 메시지 {len(seen)}건에서 "
          f"후보 어휘 {len(counts)}종 추출 (등장 {args.min_count}건 이상 {len(ranked)}종)")
    print("후보 목록은 큐레이션 전제다 — 지식 문서가 될 수 없는 말이 섞여 있다.")
    print(f"\n{'어휘':<20}{'메시지':>6}")
    for term, count in ranked[:args.top]:
        print(f"{term:<20}{count:>5}")
    if args.output:
        print(f"\n→ {args.output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="지식 배치 사전 검증과 회수율 실측.")
    sub = parser.add_subparsers(dest="command", required=True)

    lint = sub.add_parser("lint", help="적재 전 배치를 검증한다 (파일 여러 개 가능).")
    lint.add_argument("--input", nargs="+", required=True)
    lint.add_argument("--runtime-dir", default=None,
                      help="주면 ingest 가 그 경로를 받아줄지까지 미리 검사한다.")
    lint.set_defaults(func=cmd_lint)

    probe = sub.add_parser("probe", help="적재된 DB 에 질의를 던져 회수율을 잰다.")
    probe.add_argument("--queries", required=True, help="한 줄 한 질의. '#' 는 주석.")
    probe.add_argument("--runtime-dir", default=str(Path(__file__).resolve().parent / "runtime"))
    probe.add_argument("--db", default="airi-knowledge.sqlite3")
    probe.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    probe.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    probe.add_argument("--min-hit-rate", type=float, default=None,
                       help="이 회수율 미만이면 exit 1 (예: 0.9)")
    probe.set_defaults(func=cmd_probe)

    terms = sub.add_parser("terms", help="실제 시청자 발화에서 지식 후보 어휘를 뽑는다.")
    terms.add_argument("--review", nargs="+", required=True, help="review JSONL (저장소 밖).")
    terms.add_argument("--output", default=None, help="후보 어휘 목록 출력 경로.")
    terms.add_argument("--min-count", type=int, default=2, help="이 횟수 이상 등장한 어휘만.")
    terms.add_argument("--top", type=int, default=40, help="화면에 보여줄 상위 개수.")
    terms.set_defaults(func=cmd_terms)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KnowledgeInputError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
