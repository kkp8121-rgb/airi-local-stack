"""메모리 전용 음성 파이프라인 지연 계측 대시보드."""
import ctypes
from ctypes import wintypes
import json
import os
import subprocess
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST, PORT = "127.0.0.1", 8892
MAX_BODY = 16384
SOURCES = {"stt", "llm", "tts", "playback"}
PHASES = {"start", "first", "end", "error"}


def now_ms():
    return int(time.time() * 1000)


class Correlator:
    """Half-duplex 이벤트를 최근 20개 turn으로 결합한다. 디스크 기록은 하지 않는다."""
    def __init__(self, limit=20):
        self.turns = deque(maxlen=limit)
        self.by_request = {}
        self.lock = threading.Lock()

    @staticmethod
    def _clean_meta(meta):
        if not isinstance(meta, dict):
            return {}
        # 텍스트·오디오 원문을 보관하지 않는다. 숫자/불리언 값만 제한적으로 허용한다.
        return {str(k)[:48]: v for k, v in list(meta.items())[:24]
                if isinstance(v, (int, float, bool)) and not isinstance(v, str)}

    def _new_turn(self, event):
        if len(self.turns) == self.turns.maxlen:
            expired = self.turns[0]
            for request_id, mapped in list(self.by_request.items()):
                if mapped is expired:
                    del self.by_request[request_id]
        turn = {"turn_id": event["request_id"], "created_ms": event["timestamp_ms"],
                "stt": {}, "llm": {}, "tts": {"segments": 0}, "playback": {}, "meta": {}}
        self.turns.append(turn)
        self.by_request[event["request_id"]] = turn
        return turn

    def _latest(self, key, unassigned=False):
        for turn in reversed(self.turns):
            if key in turn and (not unassigned or not turn[key]):
                return turn
        return None

    def add(self, event):
        with self.lock:
            source, request_id = event["source"], event["request_id"]
            turn = self.by_request.get(request_id)
            if source == "stt" and event["phase"] == "start":
                turn = self._new_turn(event)
            elif not turn:
                if source == "llm":
                    turn = self._latest("llm", True) or self._latest("stt")
                elif source == "tts":
                    turn = self._latest("tts", True) or self._latest("llm")
                elif source == "playback":
                    turn = self._latest("playback", True) or self._latest("tts")
                else:
                    turn = self._latest("stt")
                if turn:
                    self.by_request[request_id] = turn
            if not turn:
                return False
            stage = turn[source]
            phase = event["phase"]
            stamp = event["timestamp_ms"]
            # TTS start는 새 세그먼트/요청 수를 의미한다.
            if source == "tts" and phase == "start":
                stage["segments"] = stage.get("segments", 0) + 1
                stage.setdefault("start", stamp)
            elif source == "tts" and phase == "first":
                stage.setdefault("first", stamp)
            elif source == "playback" and phase == "start":
                stage.setdefault("start", stamp)
            else:
                stage[phase] = stamp
            if event.get("duration_ms") is not None:
                stage["duration_ms"] = event["duration_ms"]
            clean = self._clean_meta(event.get("meta", {}))
            if clean:
                stage.setdefault("meta", {}).update(clean)
            return True

    def snapshot(self):
        with self.lock:
            # JSON roundtrip is a compact deep-copy; no user raw content exists in this structure.
            return json.loads(json.dumps(list(reversed(self.turns))))


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


CORRELATOR, RESOURCES = Correlator(), Resources()


def validate(payload):
    if not isinstance(payload, dict) or set(("source", "phase", "request_id")) - payload.keys(): return None
    if set(payload) - {"source", "phase", "request_id", "timestamp_ms", "duration_ms", "meta"}: return None
    if payload["source"] not in SOURCES or payload["phase"] not in PHASES or not isinstance(payload["request_id"], str) or not payload["request_id"] or len(payload["request_id"]) > 128: return None
    if "timestamp_ms" in payload and (not isinstance(payload["timestamp_ms"], (int, float)) or isinstance(payload["timestamp_ms"], bool)): return None
    if "duration_ms" in payload and (not isinstance(payload["duration_ms"], (int, float)) or isinstance(payload["duration_ms"], bool)): return None
    if "meta" in payload and not isinstance(payload["meta"], dict): return None
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
        if self.path == "/health": return self.send_json(200, {"status": "ok"})
        if self.path == "/api/snapshot": return self.send_json(200, {"now_ms": now_ms(), "turns": CORRELATOR.snapshot(), "resources": RESOURCES.snapshot()})
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
            event = validate(payload)
            if not event: raise ValueError()
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError): return self.send_json(400, {"error": "유효하지 않은 계측 이벤트"})
        if not CORRELATOR.add(event): return self.send_json(409, {"error": "연결할 STT/LLM turn이 없습니다"})
        self.send_json(202, {"accepted": True})


if __name__ == "__main__":
    print(f"Latency monitor: http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
