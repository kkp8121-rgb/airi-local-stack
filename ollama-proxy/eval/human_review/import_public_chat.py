"""공개 라이브 스트림 채팅 리플레이를 가명화된 시청자 메시지 JSONL 로 변환하는 오프라인 도구.

원본 캡처와 출력은 저장소 밖에 둔다. 닉네임/원본 유저 id/채널 id 는 절대 남기지 않고
HMAC-SHA256 으로 가명화한 값만 남긴다. 표준 라이브러리만 쓰고, 다른 eval 모듈을 import 하지 않는다.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[3]

CHZZK_KEEP_TYPE_CODES = (1, 10)
CHZZK_DONATION_TYPE_CODE = 10

NICKNAME_STYLES = ("hash", "korean")
# `--nickname-style korean` 전용 가명 단어 풀. 평가지에서 사람이 시청자를 구분해
# 읽기 좋으라고만 쓴다 — 실제 닉네임과는 아무 관계가 없고, 고르는 값은 전부
# HMAC 다이제스트에서 나온다.
KOREAN_NICKNAME_WORDS = (
    "하늘", "별빛", "물결", "감자", "초코", "구름", "바람", "노을", "새벽", "달빛",
    "봄비", "여울", "가람", "미르", "솔잎", "이슬", "단비", "누리", "아침", "저녁",
    "모래", "은하", "우주", "토끼", "고래", "수달", "참새", "딸기", "포도", "사과",
    "호박", "당근", "버섯", "만두", "국수", "라면", "김밥", "떡국", "팥죽", "보름",
    "파도", "안개", "서리", "눈꽃",
)

EMOTE_TOKEN_RE = re.compile(r"\{:[^{}:]*:\}")
WHITESPACE_RE = re.compile(r"\s+")
URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
HANGUL_RE = re.compile(r"[가-힣]")


@dataclass
class RawMessage:
    """형식에 상관없이 정규화 이전 단계에서 다루는 공통 채팅 레코드."""

    video_id_raw: str
    user_id_raw: str
    offset_ms: int
    kind: str  # "chat" | "donation"
    text: str
    amount_label: str


def is_inside_repo(path: Path) -> bool:
    """출력 경로가 저장소 트리 안인지 판정한다(존재하지 않는 경로도 허용)."""
    resolved = Path(path).resolve()
    return resolved == REPO_ROOT or REPO_ROOT in resolved.parents


def clean_text(text: str) -> str:
    """이모트 토큰(`{:name:}`)을 제거하고 공백을 정리한다."""
    without_emotes = EMOTE_TOKEN_RE.sub(" ", text)
    return WHITESPACE_RE.sub(" ", without_emotes).strip()


def hash_video_ref(video_id_raw: str) -> str:
    """영상 식별자를 되돌릴 수 없는 짧은 참조값으로 바꾼다(키 없이 평문 sha256)."""
    return hashlib.sha256(video_id_raw.encode("utf-8")).hexdigest()[:12]


def korean_nickname(digest: str) -> str:
    """같은 다이제스트면 항상 같은, 2음절 두 단어 + 2자리 접미사 가명 닉네임(≤ 8자).

    원본 닉네임에서 오는 값은 하나도 없다 — HMAC 다이제스트에서만 고른다.
    """
    pool = KOREAN_NICKNAME_WORDS
    value = int(digest[:12], 16)
    first = pool[value % len(pool)]
    second = pool[(value // len(pool)) % len(pool)]
    suffix = (value // (len(pool) ** 2)) % 100
    return f"{first}{second}{suffix:02d}"


def hash_author(hmac_key: bytes, source: str, user_id_raw: str, style: str = "hash") -> str:
    """(source, 원본 유저 id)를 HMAC-SHA256 으로 가명화한다. 원문 id 는 절대 저장하지 않는다."""
    if style not in NICKNAME_STYLES:
        raise ValueError(f"unknown nickname style: {style!r}")
    message = f"{source}:{user_id_raw}".encode("utf-8")
    digest = hmac.new(hmac_key, message, hashlib.sha256).hexdigest()
    if style == "korean":
        return korean_nickname(digest)
    return "v" + digest[:8]


def load_or_create_hmac_key(key_path: Path) -> bytes:
    """키 파일이 있으면 그대로 읽고, 없으면 32바이트 난수로 새로 만든다. 키 값은 절대 출력하지 않는다."""
    if key_path.is_file():
        data = key_path.read_bytes()
        if not data:
            raise ValueError(f"empty HMAC key file: {key_path}")
        return data
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    key_path.write_bytes(key)
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass  # Windows 는 POSIX 권한 비트를 완전히 지원하지 않는다: 최선 노력으로만 제한한다.
    return key


# ---------------------------------------------------------------------------
# Chzzk VOD 채팅
# ---------------------------------------------------------------------------

def _chzzk_user_id(chat: dict) -> str:
    profile_raw = chat.get("profile")
    if isinstance(profile_raw, str) and profile_raw:
        try:
            profile = json.loads(profile_raw)
        except json.JSONDecodeError:
            profile = {}
        user_id = profile.get("userIdHash") if isinstance(profile, dict) else None
        if user_id:
            return str(user_id)
    return str(chat.get("userIdHash", ""))


def _chzzk_amount_label(chat: dict) -> str:
    extras_raw = chat.get("extras")
    if isinstance(extras_raw, str) and extras_raw:
        try:
            extras = json.loads(extras_raw)
        except json.JSONDecodeError:
            extras = {}
        pay_amount = extras.get("payAmount") if isinstance(extras, dict) else None
        if pay_amount is not None:
            return str(pay_amount)
    return ""


def parse_chzzk(
    raw: dict, video_id_override: str | None = None
) -> tuple[list[RawMessage], dict[str, int]]:
    """Chzzk VOD 채팅 원본을 공통 레코드로 바꾼다. system/notice 타입은 여기서 걸러낸다."""
    video_id_raw = video_id_override if video_id_override else str(raw.get("videoNo", ""))
    records: list[RawMessage] = []
    stats = {"system_type": 0}
    for chat in raw.get("videoChats") or []:
        try:
            type_code = int(chat.get("messageTypeCode"))
        except (TypeError, ValueError):
            stats["system_type"] += 1
            continue
        if type_code not in CHZZK_KEEP_TYPE_CODES:
            stats["system_type"] += 1
            continue
        kind = "donation" if type_code == CHZZK_DONATION_TYPE_CODE else "chat"
        try:
            offset_ms = int(chat.get("playerMessageTime"))
        except (TypeError, ValueError):
            offset_ms = 0
        records.append(
            RawMessage(
                video_id_raw=video_id_raw,
                user_id_raw=_chzzk_user_id(chat),
                offset_ms=offset_ms,
                kind=kind,
                text=str(chat.get("content", "")),
                amount_label=_chzzk_amount_label(chat) if kind == "donation" else "",
            )
        )
    return records, stats


def _http_fetch_chzzk_page(video_no: int, cursor: int) -> dict:
    """Chzzk VOD 채팅 API 를 실제로 호출한다. 테스트는 이 함수만 갈아 끼운다(네트워크 금지)."""
    url = f"https://api.chzzk.naver.com/service/v1/videos/{video_no}/chats?playerMessageTime={cursor}"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_chzzk_chats(
    video_no: int,
    max_pages: int,
    sleep_seconds: float,
    fetch_page=None,
) -> dict:
    """Chzzk VOD 채팅을 끝까지(또는 max_pages 까지) 페이지네이션해 원본 JSON 형태로 모은다."""
    if fetch_page is None:
        fetch_page = _http_fetch_chzzk_page
    chats: list[dict] = []
    cursor = 0
    for page_index in range(max_pages):
        response = fetch_page(video_no, cursor)
        content = (response or {}).get("content") or {}
        page_chats = content.get("videoChats") or []
        if not page_chats:
            break
        chats.extend(page_chats)
        next_cursor = content.get("nextPlayerMessageTime")
        if next_cursor is None or next_cursor <= cursor:
            break
        cursor = next_cursor
        if sleep_seconds and page_index + 1 < max_pages:
            time.sleep(sleep_seconds)
    return {"videoNo": video_no, "videoChats": chats}


# ---------------------------------------------------------------------------
# Chzzk VOD 오디오 (스트리머 발화 STT 용)
# ---------------------------------------------------------------------------

CHZZK_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://chzzk.naver.com/"}
AUDIO_MIME = "audio/mp4"


def _http_get_json(url: str) -> dict:
    """테스트는 이 함수만 갈아 끼운다(네트워크 금지)."""
    request = Request(url, headers=CHZZK_HEADERS)
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def resolve_chzzk_audio_url(video_no: int, fetch_json=None) -> tuple[str, float]:
    """VOD 의 오디오 전용 트랙 URL 과 길이(초)를 낸다.

    yt-dlp 의 chzzk:video 추출기는 2026-08-27 기준 이 매니페스트에서
    ``KeyError('sourceURL')`` 로 깨진다 — 오디오 representation 의
    ``segmentList.initialization.sourceURL`` 이 null 이기 때문이다. 실제 주소는
    ``otherAttributes.m3u`` 에 서명 토큰과 함께 들어 있고, CMAF 구조라 모든 세그먼트가
    **같은 .m4a 파일의 바이트 범위**다. 그래서 플레이리스트를 따라갈 필요 없이 그 파일
    하나만 받으면 된다. (세그먼트 상대경로에는 토큰이 붙지 않아 ffmpeg 이 400 을 받는다.)
    """
    if fetch_json is None:
        fetch_json = _http_get_json
    meta = fetch_json(f"https://api.chzzk.naver.com/service/v2/videos/{int(video_no)}")
    content = (meta or {}).get("content") or {}
    video_id, in_key = content.get("videoId"), content.get("inKey")
    if not video_id or not in_key:
        raise ValueError("videoId/inKey 를 얻지 못했다(비공개이거나 성인 인증이 필요한 VOD)")
    playback = fetch_json(
        f"https://apis.naver.com/neonplayer/vodplay/v2/playback/{video_id}?key={in_key}")
    for period in (playback or {}).get("period") or []:
        for adaptation in period.get("adaptationSet") or []:
            if adaptation.get("mimeType") != AUDIO_MIME:
                continue
            for representation in adaptation.get("representation") or []:
                playlist = (representation.get("otherAttributes") or {}).get("m3u")
                if not playlist:
                    continue
                head, _, query = playlist.partition("?")
                directory = head.rsplit("/", 1)[0]
                name = f"{representation.get('id')}.m4a"
                url = f"{directory}/{name}" + (f"?{query}" if query else "")
                return url, float(content.get("duration") or 0)
    raise ValueError("오디오 전용 트랙을 찾지 못했다")


def download_chzzk_audio(video_no: int, destination: Path, fetch_json=None, opener=None) -> int:
    """오디오 트랙을 통째로 내려받는다. 반환값은 바이트 수."""
    url, _duration = resolve_chzzk_audio_url(video_no, fetch_json=fetch_json)
    if opener is None:
        def opener(target):  # pragma: no cover - 네트워크 경로
            return urlopen(Request(target, headers=CHZZK_HEADERS), timeout=900)
    written = 0
    with opener(url) as response, destination.open("wb") as handle:
        while True:
            block = response.read(1 << 20)
            if not block:
                break
            handle.write(block)
            written += len(block)
    return written


# ---------------------------------------------------------------------------
# yt-dlp YouTube 라이브 채팅 리플레이
# ---------------------------------------------------------------------------

def _youtube_message_text(message: dict | None) -> str:
    if not isinstance(message, dict):
        return ""
    parts = [
        str(run["text"])
        for run in message.get("runs") or []
        if isinstance(run, dict) and "text" in run
    ]
    return "".join(parts)


def _youtube_offset_ms(
    video_offset_raw: str | int | None,
    timestamp_usec: str | int | None,
    first_timestamp_usec: int | None,
) -> int | None:
    if video_offset_raw is not None:
        try:
            return int(video_offset_raw)
        except (TypeError, ValueError):
            pass
    if timestamp_usec is not None and first_timestamp_usec is not None:
        try:
            return (int(timestamp_usec) - first_timestamp_usec) // 1000
        except (TypeError, ValueError):
            return None
    return None


def parse_youtube(
    lines: Sequence[str], video_id_override: str
) -> tuple[list[RawMessage], dict[str, int]]:
    """yt-dlp 라이브 채팅 리플레이(JSON Lines)를 공통 레코드로 바꾼다."""
    records: list[RawMessage] = []
    stats = {"not_message": 0, "no_offset": 0}
    first_timestamp_usec: int | None = None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            envelope = json.loads(line)
        except json.JSONDecodeError:
            stats["not_message"] += 1
            continue

        video_offset_raw = envelope.get("videoOffsetTimeMsec")
        actions = (envelope.get("replayChatItemAction") or {}).get("actions") or []
        for action in actions:
            item = (action.get("addChatItemAction") or {}).get("item")
            if not isinstance(item, dict):
                continue

            if "liveChatTextMessageRenderer" in item:
                renderer, kind = item["liveChatTextMessageRenderer"], "chat"
            elif "liveChatPaidMessageRenderer" in item:
                renderer, kind = item["liveChatPaidMessageRenderer"], "donation"
            else:
                stats["not_message"] += 1
                continue

            timestamp_usec = renderer.get("timestampUsec")
            if first_timestamp_usec is None and timestamp_usec is not None:
                try:
                    first_timestamp_usec = int(timestamp_usec)
                except (TypeError, ValueError):
                    first_timestamp_usec = None

            offset_ms = _youtube_offset_ms(video_offset_raw, timestamp_usec, first_timestamp_usec)
            if offset_ms is None:
                stats["no_offset"] += 1
                continue

            author_name = (renderer.get("authorName") or {}).get("simpleText", "")
            user_id_raw = renderer.get("authorExternalChannelId") or author_name
            amount_label = ""
            if kind == "donation":
                amount_label = (renderer.get("purchaseAmountText") or {}).get("simpleText", "")

            records.append(
                RawMessage(
                    video_id_raw=video_id_override,
                    user_id_raw=str(user_id_raw),
                    offset_ms=offset_ms,
                    kind=kind,
                    text=_youtube_message_text(renderer.get("message")),
                    amount_label=amount_label,
                )
            )
    return records, stats


# ---------------------------------------------------------------------------
# 공통 정제/가명화
# ---------------------------------------------------------------------------

def normalize_messages(
    records: Sequence[RawMessage],
    *,
    source: str,
    hmac_key: bytes,
    min_chars: int,
    max_chars: int,
    drop_links: bool,
    dedupe_window: int,
    nickname_style: str = "hash",
) -> tuple[list[dict], dict[str, int]]:
    """정제·필터링·가명화를 거쳐 최종 행을 만든다. 대화 원문/원본 id 는 로그에 남기지 않는다."""
    stats = {"empty": 0, "length": 0, "link": 0, "no_hangul": 0, "duplicate": 0}
    rows: list[dict] = []
    seen: deque[tuple[str, str]] = deque(maxlen=max(dedupe_window, 1))

    for record in records:
        text = clean_text(record.text)
        if not text:
            stats["empty"] += 1
            continue
        if len(text) < min_chars or len(text) > max_chars:
            stats["length"] += 1
            continue
        if drop_links and URL_RE.search(text):
            stats["link"] += 1
            continue
        if not HANGUL_RE.search(text):
            stats["no_hangul"] += 1
            continue

        author = hash_author(hmac_key, source, record.user_id_raw, style=nickname_style)
        dedupe_key = (author, text)
        if dedupe_key in seen:
            stats["duplicate"] += 1
            continue
        seen.append(dedupe_key)

        rows.append(
            {
                "source": source,
                "video_ref": hash_video_ref(record.video_id_raw),
                "offset_ms": record.offset_ms,
                "author": author,
                "kind": record.kind,
                "text": text,
                "amount_label": record.amount_label,
            }
        )
    return rows, stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="공개 라이브 스트림 채팅 리플레이를 가명화된 시청자 메시지 JSONL 로 바꾼다.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    normalize_parser = subparsers.add_parser(
        "normalize", help="원본 채팅을 가명화 JSONL 로 변환한다."
    )
    normalize_parser.add_argument("--format", required=True, choices=["chzzk", "youtube"])
    normalize_parser.add_argument("--input", required=True, help="원본 채팅 파일 경로.")
    normalize_parser.add_argument("--output", required=True, help="가명화 JSONL 출력 경로(저장소 밖).")
    normalize_parser.add_argument(
        "--hmac-key-file",
        required=True,
        help="가명화용 HMAC 키 파일 경로(저장소 밖, 없으면 새로 만든다).",
    )
    normalize_parser.add_argument(
        "--video-id",
        default=None,
        help="video_ref 계산에 쓸 영상 식별자. --format youtube 는 필수, chzzk 는 원본 videoNo 를 덮어쓴다.",
    )
    normalize_parser.add_argument(
        "--nickname-style",
        choices=list(NICKNAME_STYLES),
        default="hash",
        help="author 가명 표기. hash=v+16진수 8자리(기본), korean=평가자가 읽기 쉬운 한국어 가명.",
    )
    normalize_parser.add_argument("--min-chars", type=int, default=2)
    normalize_parser.add_argument("--max-chars", type=int, default=160)
    normalize_parser.add_argument(
        "--drop-links", dest="drop_links", action="store_true", default=True
    )
    normalize_parser.add_argument(
        "--keep-links",
        dest="drop_links",
        action="store_false",
        help="URL 이 있는 메시지도 지우지 않는다.",
    )
    normalize_parser.add_argument("--dedupe-window", type=int, default=20)
    normalize_parser.add_argument("--stats-output", default=None, help="요약 통계를 쓸 JSON 경로(선택).")
    normalize_parser.add_argument(
        "--allow-repo-path",
        action="store_true",
        help="저장소 트리 안으로 쓰는 것을 명시적으로 허용한다(권장하지 않음).",
    )

    fetch_parser = subparsers.add_parser(
        "chzzk-fetch", help="Chzzk VOD 채팅을 페이지네이션으로 받아 원본 JSON 으로 저장한다."
    )
    fetch_parser.add_argument("--video-no", type=int, required=True)
    fetch_parser.add_argument("--output", required=True, help="원본 JSON 출력 경로(저장소 밖).")
    fetch_parser.add_argument("--max-pages", type=int, default=60)
    fetch_parser.add_argument("--sleep", type=float, default=0.4, help="페이지 사이 대기 시간(초).")
    fetch_parser.add_argument(
        "--allow-repo-path",
        action="store_true",
        help="저장소 트리 안으로 쓰는 것을 명시적으로 허용한다(권장하지 않음).",
    )

    audio_parser = subparsers.add_parser(
        "chzzk-audio",
        help="Chzzk VOD 오디오 트랙을 받는다(스트리머 발화 STT 용). yt-dlp 우회 경로.",
    )
    audio_parser.add_argument("--video-no", type=int, required=True)
    audio_parser.add_argument("--output", required=True, help="오디오 출력 경로(저장소 밖).")
    audio_parser.add_argument(
        "--allow-repo-path",
        action="store_true",
        help="저장소 트리 안으로 쓰는 것을 명시적으로 허용한다(권장하지 않음).",
    )

    return parser


def _refuse_if_inside_repo(path: Path, allow_repo_path: bool, what: str) -> bool:
    if is_inside_repo(path) and not allow_repo_path:
        print(
            f"error: refusing to write {what} inside the repository tree; "
            "choose a path outside the repo or pass --allow-repo-path",
            file=sys.stderr,
        )
        return True
    return False


def _run_chzzk_fetch(args: argparse.Namespace) -> int:
    output_path = Path(args.output)
    if _refuse_if_inside_repo(output_path, args.allow_repo_path, "a raw chat capture"):
        return 1

    raw = fetch_chzzk_chats(args.video_no, args.max_pages, args.sleep)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(raw, handle, ensure_ascii=False)

    print(f"video_no={args.video_no} chats={len(raw['videoChats'])} output={output_path}")
    return 0


def _run_chzzk_audio(args: argparse.Namespace) -> int:
    output_path = Path(args.output)
    if _refuse_if_inside_repo(output_path, args.allow_repo_path, "a raw audio capture"):
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        written = download_chzzk_audio(args.video_no, output_path)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"video_no={args.video_no} bytes={written} output={output_path}")
    return 0


def _run_normalize(args: argparse.Namespace) -> int:
    if args.format == "youtube" and not args.video_id:
        print("error: --video-id is required for --format youtube", file=sys.stderr)
        return 1

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"error: input not found: {input_path}", file=sys.stderr)
        return 1

    output_path = Path(args.output)
    if _refuse_if_inside_repo(output_path, args.allow_repo_path, "pseudonymized chat"):
        return 1
    key_path = Path(args.hmac_key_file)
    if _refuse_if_inside_repo(key_path, args.allow_repo_path, "the HMAC key"):
        return 1
    stats_path = Path(args.stats_output) if args.stats_output else None
    if stats_path is not None and _refuse_if_inside_repo(stats_path, args.allow_repo_path, "stats output"):
        return 1

    hmac_key = load_or_create_hmac_key(key_path)

    if args.format == "chzzk":
        raw = json.loads(input_path.read_text(encoding="utf-8"))
        records, parse_stats = parse_chzzk(raw, video_id_override=args.video_id)
    else:
        lines = input_path.read_text(encoding="utf-8").splitlines()
        records, parse_stats = parse_youtube(lines, video_id_override=args.video_id)

    rows, filter_stats = normalize_messages(
        records,
        source=args.format,
        hmac_key=hmac_key,
        min_chars=args.min_chars,
        max_chars=args.max_chars,
        drop_links=args.drop_links,
        dedupe_window=args.dedupe_window,
        nickname_style=args.nickname_style,
    )
    rows.sort(key=lambda row: row["offset_ms"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    authors = {row["author"] for row in rows}
    duration_ms = (rows[-1]["offset_ms"] - rows[0]["offset_ms"]) if rows else 0
    stats = {
        "in": len(records),
        "out": len(rows),
        **parse_stats,
        **filter_stats,
        "unique_authors": len(authors),
        "duration_ms": duration_ms,
    }

    if stats_path is not None:
        stats_path.parent.mkdir(parents=True, exist_ok=True)
        with stats_path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(stats, handle, ensure_ascii=False, indent=2)

    ordered_keys = (
        ["in", "out"]
        + sorted(k for k in stats if k not in {"in", "out", "unique_authors", "duration_ms"})
        + ["unique_authors", "duration_ms"]
    )
    print(" ".join(f"{key}={stats[key]}" for key in ordered_keys) + f" output={output_path}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "chzzk-fetch":
        return _run_chzzk_fetch(args)
    if args.command == "chzzk-audio":
        return _run_chzzk_audio(args)
    return _run_normalize(args)


if __name__ == "__main__":
    raise SystemExit(main())
