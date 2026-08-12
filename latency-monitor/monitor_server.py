"""메모리 전용 음성 파이프라인 지연 계측 대시보드."""
import ctypes
from ctypes import wintypes
import json
import math
import os
import subprocess
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST, PORT = "127.0.0.1", 8892
MAX_BODY = 16384
SOURCES = {"stt", "memory", "llm", "tts", "playback"}
LOCAL_BROADCAST_SOURCE = "local-proactive-broadcast"
LOCAL_BROADCAST_PHASE = "playback-completed"
LOCAL_BROADCAST_FAILURE_CODES = {
    "invalid-proactive-speech",
    "audio-context-unavailable",
    "speech-provider-unavailable",
    "local-rest-speech-required",
    "speech-model-or-voice-unavailable",
    "speech-provider-initialization-failed",
    "local-speech-endpoint-required",
    "audio-context-resume-failed",
    "speech-stage-unavailable",
    "candidate-rejected",
    "candidate-too-long",
    "candidate-content-rejected",
    "candidate-empty-or-cancelled",
    "playback-rejected",
    "playback-interrupted",
    "intent-cancelled",
    "proactive-speech-timeout",
    "pipeline-incomplete",
}
PHASES = {
    "start",
    "first",
    "raw_content",
    "content",
    "end",
    "error",
    "retrieve_start",
    "retrieve_end",
    "extract_start",
    "extract_end",
}


def now_ms():
    return int(time.time() * 1000)


class Correlator:
    """Half-duplex 이벤트를 최근 20개 turn으로 결합한다. 디스크 기록은 하지 않는다."""
    def __init__(self, limit=20, reorder_ttl_ms=1000, pending_request_limit=32,
                 pending_event_limit=128, pending_per_request_limit=8, clock=None):
        capacities = (limit, pending_request_limit, pending_event_limit,
                      pending_per_request_limit)
        if any(isinstance(value, bool) or not isinstance(value, int)
               or value <= 0 or value > 100_000 for value in capacities):
            raise ValueError("correlator capacity limits must be integers from 1 to 100000")
        if isinstance(reorder_ttl_ms, bool) or not isinstance(reorder_ttl_ms, (int, float)) \
                or (isinstance(reorder_ttl_ms, float) and not math.isfinite(reorder_ttl_ms)) \
                or reorder_ttl_ms <= 0 or reorder_ttl_ms > 60_000:
            raise ValueError("reorder TTL must be a finite number from 1 to 60000 ms")
        if clock is not None and not callable(clock):
            raise ValueError("clock must be callable")
        self.turns = deque(maxlen=limit)
        self.by_request = {}
        self.request_correlation = {}
        self.reorder_ttl_ms = reorder_ttl_ms
        self.pending_request_limit = pending_request_limit
        self.pending_event_limit = pending_event_limit
        self.pending_per_request_limit = pending_per_request_limit
        self.clock = clock or time.monotonic
        self.pending_audio = {}
        self.pending_event_count = 0
        self.pending_sequence = 0
        self.last_clock = None
        self.lock = threading.Lock()

    def _read_clock(self):
        value = self.clock()
        if isinstance(value, bool) or not isinstance(value, (int, float)) \
                or (isinstance(value, float) and not math.isfinite(value)):
            raise ValueError("clock must return a finite number")
        if self.last_clock is not None and value < self.last_clock:
            raise ValueError("clock must be monotonic")
        self.last_clock = value
        return value

    @staticmethod
    def _clean_meta(meta):
        if not isinstance(meta, dict):
            return {}
        # 텍스트·오디오 원문을 보관하지 않는다. 숫자/불리언 값만 제한적으로 허용한다.
        # Completed Ollama rows are emitted after the fixed grounding fields,
        # so retain these content-free measurements even when an older caller
        # fills the ordinary bounded metadata budget first.
        required_ollama_metrics = {
            "ollama_prompt_eval_count",
            "ollama_prompt_eval_ms",
            "ollama_eval_count",
            "ollama_eval_ms",
        }
        cleaned = {}
        for key, value in meta.items():
            clean_key = str(key)[:48]
            if not isinstance(value, (int, float, bool)) or isinstance(value, str):
                continue
            if len(cleaned) < 24 or clean_key in required_ollama_metrics:
                cleaned[clean_key] = value
        return cleaned

    def _new_turn(self, event):
        if len(self.turns) == self.turns.maxlen:
            expired = self.turns[0]
            for request_id, mapped in list(self.by_request.items()):
                if mapped is expired:
                    del self.by_request[request_id]
                    self.request_correlation.pop(request_id, None)
        turn = {"turn_id": event["request_id"], "created_ms": event["timestamp_ms"],
                "stt": {}, "memory": {}, "llm": {}, "tts": {"segments": 0},
                "playback": {}, "kpi": {}, "correlation": {},
                "_kpi_events": {"tts": [], "playback": []}, "_kpi_overflow": []}
        self.turns.append(turn)
        self.by_request[event["request_id"]] = turn
        self.request_correlation[event["request_id"]] = "explicit"
        return turn

    def _latest(self, key, unassigned=False):
        for turn in reversed(self.turns):
            if key in turn and (not unassigned or not turn[key]):
                return turn
        return None

    def _apply(self, event):
            source, request_id = event["source"], event["request_id"]
            turn = self.by_request.get(request_id)
            correlation = self.request_correlation.get(request_id, "unmatched") if turn else "unmatched"
            if source == "stt" and event["phase"] == "start":
                turn = self._new_turn(event)
                correlation = "explicit"
            elif not turn:
                if source == "memory":
                    turn = self._latest("memory", True) or self._latest("llm") or self._latest("stt")
                elif source == "llm":
                    # Join only a turn that has not received any LLM event.
                    # Falling back to an arbitrary latest STT stage merges a
                    # new text-only request into the previous completed turn.
                    turn = self._latest("llm", True)
                elif source == "tts":
                    turn = self._latest("tts", True) or self._latest("llm")
                elif source == "playback":
                    turn = self._latest("playback", True) or self._latest("tts")
                else:
                    turn = self._latest("stt")
                if not turn and source == "llm" and event["phase"] == "start":
                    # Text/API turns have no STT start event. The proxy's
                    # loopback request ID is still an explicit correlation
                    # boundary, so retain the same content-free waterfall.
                    turn = self._new_turn(event)
                    correlation = "explicit"
                if turn:
                    self.by_request[request_id] = turn
                    if request_id not in self.request_correlation:
                        self.request_correlation[request_id] = "heuristic"
                        correlation = "heuristic"
            if not turn:
                return False
            stage = turn[source]
            phase = event["phase"]
            stamp = event["timestamp_ms"]
            first_content = source == "llm" and phase == "content" and "content" not in stage
            # TTS start는 새 세그먼트/요청 수를 의미한다.
            if source == "tts" and phase == "start":
                stage["segments"] = stage.get("segments", 0) + 1
                stage.setdefault("start", stamp)
            elif source == "tts" and phase == "first":
                stage.setdefault("first", stamp)
            elif source == "playback" and phase == "start":
                stage.setdefault("start", stamp)
            elif source == "llm" and phase == "content":
                # `content` is the first boundary-visible substantive delta.
                # Preserve it as TTFS-like evidence and retain the latest
                # content event separately if an older producer emits more
                # than once.
                stage.setdefault("content", stamp)
                stage["content_last"] = stamp
            elif source == "llm" and phase == "raw_content":
                stage.setdefault("raw_content", stamp)
            else:
                stage[phase] = stamp
            if event.get("duration_ms") is not None:
                stage["duration_ms"] = event["duration_ms"]
            clean = self._clean_meta(event.get("meta", {}))
            if clean:
                stage.setdefault("meta", {}).update(clean)
            # Keep a small numeric-only event trail so a real test can still
            # be reconstructed on one clock when renderer/TTS request IDs do
            # not match the LLM ID.  Such entries remain explicitly marked as
            # heuristic and never become acceptance KPIs.
            if source in {"tts", "playback"} and phase in {"start", "first", "end", "error"}:
                timeline = stage.setdefault("timeline", [])
                timeline.append({
                    "phase": phase,
                    "timestamp_ms": stamp,
                    "correlation": correlation,
                })
                if len(timeline) > 64:
                    del timeline[:-64]
            # A different request ID can only be joined by the legacy
            # half-duplex heuristic.  Preserve it for the waterfall, but do
            # not let it create substantive-content KPIs: overlapping turns
            # would otherwise be silently attributed to the wrong response.
            prior_correlation = turn["correlation"].get(source)
            if prior_correlation is None or prior_correlation == correlation:
                turn["correlation"][source] = correlation
            else:
                turn["correlation"][source] = "mixed"
            if first_content:
                self._recompute_audio_kpis(turn)
            elif source in {"tts", "playback"}:
                self._record_audio_kpi(turn, source, phase, stamp, correlation)
            return True

    @staticmethod
    def _record_audio_kpi(turn, source, phase, stamp, correlation):
        if correlation != "explicit":
            return
        if source == "tts" and phase == "first":
            ack_key, substantive_key = "ack_tts_first", "substantive_tts_first"
        elif source == "playback" and phase == "start":
            ack_key, substantive_key = "ack_playback_start", "substantive_playback_start"
        else:
            return
        if source in turn["_kpi_overflow"]:
            return
        candidates = turn["_kpi_events"][source]
        if len(candidates) >= 64:
            candidates.clear()
            turn["_kpi_overflow"].append(source)
            turn["kpi"].pop(ack_key, None)
            turn["kpi"].pop(substantive_key, None)
            return
        candidates.append(stamp)
        content_at = turn["llm"].get("content")
        key = substantive_key if content_at is not None and stamp >= content_at else ack_key
        turn["kpi"][key] = min(stamp, turn["kpi"].get(key, stamp))

    @staticmethod
    def _recompute_audio_kpis(turn):
        """Classify exact audio from timestamps, independent of arrival order."""
        content_at = turn["llm"].get("content")
        for stage_name, phase, ack_key, substantive_key in (
            ("tts", "first", "ack_tts_first", "substantive_tts_first"),
            ("playback", "start", "ack_playback_start", "substantive_playback_start"),
        ):
            turn["kpi"].pop(ack_key, None)
            turn["kpi"].pop(substantive_key, None)
            if stage_name in turn["_kpi_overflow"]:
                continue
            stamps = list(turn["_kpi_events"][stage_name])
            if not stamps:
                continue
            if content_at is None:
                turn["kpi"][ack_key] = min(stamps)
                continue
            before = [stamp for stamp in stamps if stamp < content_at]
            after = [stamp for stamp in stamps if stamp >= content_at]
            if before:
                turn["kpi"][ack_key] = min(before)
            if after:
                turn["kpi"][substantive_key] = min(after)

    def _copy_pending_event(self, event):
        """Retain only fixed-shape numeric fields while audio is reordered."""
        saved = {
            "source": event["source"], "phase": event["phase"],
            "request_id": event["request_id"], "timestamp_ms": event["timestamp_ms"],
        }
        if event.get("duration_ms") is not None:
            saved["duration_ms"] = event["duration_ms"]
        return saved

    def _drop_pending(self, request_id):
        bucket = self.pending_audio.pop(request_id, None)
        if bucket:
            self.pending_event_count -= len(bucket["events"])
        return bucket

    def _expire_pending(self, ingested_at):
        if not any(
                ingested_at - bucket["received_at"] >= self.reorder_ttl_ms / 1000
                for bucket in self.pending_audio.values()):
            return
        expired = []
        # Once the oldest reorder window closes, flush the whole bounded set.
        # This can shorten a later bucket's window, but never reorders events.
        for request_id in list(self.pending_audio):
            expired.extend(self._drop_pending(request_id)["events"])
        # No matching LLM boundary arrived in time: preserve the old
        # half-duplex behavior and the original cross-request arrival order.
        for pending in sorted(expired, key=lambda item: item["sequence"]):
            request_id = pending["event"]["request_id"]
            mapped = self.by_request.get(request_id)
            if mapped and self.request_correlation.get(request_id) == "explicit" \
                    and ({"end", "error"} & mapped["llm"].keys()):
                # A reused completed ID has no safe legacy target. If no new
                # explicit anchor arrived within the window, discard it.
                continue
            self._apply(pending["event"])

    def _buffer_audio(self, event, ingested_at):
        request_id = event["request_id"]
        bucket = self.pending_audio.get(request_id)
        if bucket is None:
            while len(self.pending_audio) >= self.pending_request_limit:
                self._drop_pending(next(iter(self.pending_audio)))
            bucket = {"received_at": ingested_at, "events": []}
            self.pending_audio[request_id] = bucket
        if len(bucket["events"]) >= self.pending_per_request_limit:
            return
        while self.pending_event_count >= self.pending_event_limit and self.pending_audio:
            self._drop_pending(next(iter(self.pending_audio)))
            bucket = self.pending_audio.get(request_id)
            if bucket is None:
                bucket = {"received_at": ingested_at, "events": []}
                self.pending_audio[request_id] = bucket
        self.pending_sequence += 1
        bucket["events"].append({
            "sequence": self.pending_sequence,
            "event": self._copy_pending_event(event),
        })
        self.pending_event_count += 1

    def add(self, event):
        with self.lock:
            ingested_at = self._read_clock()
            self._expire_pending(ingested_at)
            source, request_id = event["source"], event["request_id"]
            mapped = self.by_request.get(request_id)
            if source in {"tts", "playback"} and mapped is None:
                self._buffer_audio(event, ingested_at)
                return True
            if source == "llm" and event["phase"] == "start":
                bucket = self._drop_pending(request_id)
                existing = self.by_request.get(request_id)
                completed_reuse = bool(
                    existing and self.request_correlation.get(request_id) == "explicit"
                    and ({"end", "error"} & existing["llm"].keys())
                )
                if bucket and existing and not completed_reuse:
                    # Cross-process delivery can put audio ahead of the LLM
                    # event even after the same-ID STT anchor has arrived.
                    # Complete that voice turn instead of creating a text row.
                    self._apply(event)
                    for pending in sorted(bucket["events"], key=lambda item: item["sequence"]):
                        self._apply(pending["event"])
                    return True
                if bucket or completed_reuse:
                    # A same-ID LLM start is an explicit text-only boundary;
                    # do not mutate the preceding completed turn.
                    self._new_turn(event)
                    self._apply(event)
                    for pending in sorted(
                            bucket["events"] if bucket else [],
                            key=lambda item: item["sequence"]):
                        self._apply(pending["event"])
                    return True
            return self._apply(event)

    def snapshot(self):
        with self.lock:
            self._expire_pending(self._read_clock())
            # JSON roundtrip is a compact deep-copy; no user raw content exists in this structure.
            turns = json.loads(json.dumps(list(reversed(self.turns))))
            for turn in turns:
                turn.pop("_kpi_events", None)
                turn.pop("_kpi_overflow", None)
            return turns


class LocalBroadcastProofs:
    """Content-free, process-local proof that renderer WebAudio drained naturally."""

    def __init__(self, limit=64):
        self.events = deque(maxlen=limit)
        self.incomplete = deque(maxlen=limit)
        self.lock = threading.Lock()

    def add(self, proof):
        with self.lock:
            if proof["phase"] == "playback-incomplete":
                self.incomplete.append({
                    "received_ms": now_ms(),
                    "attempt_count": proof["attempt_count"],
                    "failure_code": proof["failure_code"],
                    "tts_requests": proof["tts_requests"],
                    "successful_tts_results": proof["successful_tts_results"],
                    "natural_playback_ends": proof["natural_playback_ends"],
                })
                return
            self.events.append({
                "received_ms": now_ms(),
                "completion_count": proof["completion_count"],
            })

    def snapshot(self):
        with self.lock:
            events = list(self.events)
            incomplete = list(self.incomplete)
            return {
                "accepted_events": len(events),
                "latest_completion_count": events[-1]["completion_count"] if events else 0,
                "events": list(reversed(events)),
                "incomplete_events": len(incomplete),
                "latest_incomplete": incomplete[-1] if incomplete else None,
            }


class Resources:
    def __init__(self):
        self.last_times = None
        self.gpu_at = 0
        self.gpu = None
        self.lock = threading.Lock()

    def cpu_ram(self):
        cpu = None
        if os.name == "nt":
            class FILETIME(ctypes.Structure):
                _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]
            idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
            if ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
                def q(v): return (v.dwHighDateTime << 32) + v.dwLowDateTime
                current = (q(idle), q(kernel), q(user))
                if self.last_times:
                    total = (current[1] - self.last_times[1]) + (current[2] - self.last_times[2])
                    cpu = round(100 * (1 - (current[0] - self.last_times[0]) / total), 1) if total else None
                self.last_times = current
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            mem = MEMORYSTATUSEX(); mem.dwLength = ctypes.sizeof(mem)
            ram = {"used_percent": mem.dwMemoryLoad, "total_mb": round(mem.ullTotalPhys / 1048576),
                   "used_mb": round((mem.ullTotalPhys - mem.ullAvailPhys) / 1048576)} if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)) else None
        else:
            ram = None
        return cpu, ram

    def gpu_snapshot(self):
        with self.lock:
            if time.monotonic() - self.gpu_at < 2:
                return self.gpu
            self.gpu_at = time.monotonic()
            try:
                out = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=1.5, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
                rows = []
                for line in out.splitlines():
                    vals = [x.strip() for x in line.split(",")]
                    if len(vals) == 4: rows.append({"utilization_percent": float(vals[0]), "vram_used_mb": float(vals[1]), "vram_total_mb": float(vals[2]), "temperature_c": float(vals[3])})
                self.gpu = rows or None
            except (OSError, subprocess.SubprocessError, ValueError):
                self.gpu = None
            return self.gpu

    def snapshot(self):
        cpu, ram = self.cpu_ram()
        return {"cpu_percent": cpu, "ram": ram, "gpus": self.gpu_snapshot()}


CORRELATOR, RESOURCES, LOCAL_BROADCAST_PROOFS = Correlator(), Resources(), LocalBroadcastProofs()


def validate_local_broadcast_proof(payload):
    if not isinstance(payload, dict):
        return None
    completed = {"schema_version", "source", "phase", "completion_count"}
    incomplete = {
        "schema_version", "source", "phase", "attempt_count", "tts_requests",
        "successful_tts_results", "natural_playback_ends", "failure_code",
    }
    required = completed if payload.get("phase") == LOCAL_BROADCAST_PHASE else incomplete
    if set(payload) != required:
        return None
    if payload["schema_version"] != 1 or isinstance(payload["schema_version"], bool):
        return None
    if payload["source"] != LOCAL_BROADCAST_SOURCE or payload["phase"] not in {LOCAL_BROADCAST_PHASE, "playback-incomplete"}:
        return None
    if payload.get("phase") == "playback-incomplete" and payload.get("failure_code") not in LOCAL_BROADCAST_FAILURE_CODES:
        return None
    numeric_keys = required - {"schema_version", "source", "phase", "failure_code"}
    for key in numeric_keys:
        value = payload[key]
        minimum = 1 if key in {"completion_count", "attempt_count"} else 0
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum or value > 1_000_000_000:
            return None
    return {key: payload[key] for key in sorted(required)}


def validate(payload):
    if not isinstance(payload, dict) or set(("source", "phase", "request_id")) - payload.keys(): return None
    if set(payload) - {"source", "phase", "request_id", "timestamp_ms", "duration_ms", "meta"}: return None
    if payload["source"] not in SOURCES or payload["phase"] not in PHASES or not isinstance(payload["request_id"], str) or not payload["request_id"] or len(payload["request_id"]) > 128: return None
    if payload["phase"] == "content" and payload["source"] != "llm": return None
    if "timestamp_ms" in payload and (not isinstance(payload["timestamp_ms"], (int, float)) or isinstance(payload["timestamp_ms"], bool) or (isinstance(payload["timestamp_ms"], float) and not math.isfinite(payload["timestamp_ms"]))): return None
    if "duration_ms" in payload and (not isinstance(payload["duration_ms"], (int, float)) or isinstance(payload["duration_ms"], bool) or (isinstance(payload["duration_ms"], float) and not math.isfinite(payload["duration_ms"]))): return None
    if "meta" in payload and not isinstance(payload["meta"], dict): return None
    if "meta" in payload and any(isinstance(value, float) and not math.isfinite(value) for value in payload["meta"].values()): return None
    # Whitelist fields only. 텍스트/audio 등의 어떤 추가 원문 필드도 수용하지 않는다.
    event = {k: payload[k] for k in ("source", "phase", "request_id", "duration_ms", "meta") if k in payload}
    event["timestamp_ms"] = int(payload.get("timestamp_ms", now_ms()))
    return event


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        super().end_headers()
    def send_json(self, status, value):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path == "/health": return self.send_json(200, {"status": "ok", "local_broadcast": LOCAL_BROADCAST_PROOFS.snapshot()})
        if self.path == "/api/snapshot": return self.send_json(200, {"now_ms": now_ms(), "turns": CORRELATOR.snapshot(), "resources": RESOURCES.snapshot(), "local_broadcast": LOCAL_BROADCAST_PROOFS.snapshot()})
        if self.path == "/dashboard-metrics.mjs":
            try:
                with open(os.path.join(os.path.dirname(__file__), "dashboard-metrics.mjs"), "rb") as f: body = f.read()
                self.send_response(200); self.send_header("Content-Type", "application/javascript; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            except OSError: self.send_error(404)
            return
        if self.path in ("/", "/dashboard.html"):
            try:
                with open(os.path.join(os.path.dirname(__file__), "dashboard.html"), "rb") as f: body = f.read()
                self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            except OSError: self.send_error(404)
            return
        self.send_error(404)
    def do_OPTIONS(self):
        self.send_response(204); self.end_headers()
    def do_POST(self):
        if self.path != "/api/event": return self.send_error(404)
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > MAX_BODY: raise ValueError()
            payload = json.loads(self.rfile.read(size).decode("utf-8"))
            proof = validate_local_broadcast_proof(payload)
            if proof:
                LOCAL_BROADCAST_PROOFS.add(proof)
                return self.send_json(202, {"accepted": True})
            event = validate(payload)
            if not event: raise ValueError()
        except (ValueError, OverflowError, UnicodeDecodeError, json.JSONDecodeError): return self.send_json(400, {"error": "유효하지 않은 계측 이벤트"})
        if not CORRELATOR.add(event): return self.send_json(409, {"error": "연결할 STT/LLM turn이 없습니다"})
        self.send_json(202, {"accepted": True})


if __name__ == "__main__":
    print(f"Latency monitor: http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
