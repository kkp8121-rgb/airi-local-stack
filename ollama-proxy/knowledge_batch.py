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
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Sequence

from knowledge_store import (
    CHUNK_CHARS, KnowledgeInputError, KnowledgeStore, chunk_text, runtime_path, validate_record,
)

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
