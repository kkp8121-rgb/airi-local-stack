"""Loopback-only, authenticated OpenAI-compatible evaluation gateway.

This deliberately small server is for local model evaluation, not a general
purpose proxy.  It accepts only the two pinned logical AIRI model names.
"""
from __future__ import annotations

import argparse
import hmac
import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

MIDM_MODEL = 'midm-airi:2.0-mini'
MOTIF_MODEL = 'motif-airi:2.6b-v1.1-lc-nf4'
MAX_BODY_BYTES = 64 * 1024
MAX_MESSAGES = 64
MAX_CONTENT_CHARS = 32 * 1024
Transport = Callable[[str, str, dict[str, Any]], dict[str, Any]]


class GatewayError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(message)


def _url(base: str, path: str) -> str:
    return base.rstrip('/') + path


def require_loopback_endpoint(endpoint: str) -> None:
    parsed = urllib.parse.urlsplit(endpoint)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port:
        raise ValueError('backend endpoints must be loopback http://127.0.0.1 with an explicit port')


def stdlib_transport(method: str, url: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = None if method == 'GET' else json.dumps(payload, separators=(',', ':')).encode('utf-8')
    headers = {'Content-Type': 'application/json'} if data is not None else {}
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode('utf-8'))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        raise GatewayError(503, 'backend unavailable') from exc


class Gateway:
    def __init__(self, token: str, midm_url: str, motif_url: str, midm_digest: str,
                 motif_digest: str, transport: Transport = stdlib_transport,
                 clock: Callable[[], float] = time.time,
                 id_factory: Callable[[], str] = lambda: uuid.uuid4().hex):
        if len(token.encode('utf-8')) < 32:
            raise ValueError('token must be at least 32 bytes')
        if not midm_digest or not motif_digest:
            raise ValueError('expected digests are required')
        require_loopback_endpoint(midm_url)
        require_loopback_endpoint(motif_url)
        self.token, self.midm_url, self.motif_url = token, midm_url, motif_url
        self.expected = {MIDM_MODEL: midm_digest, MOTIF_MODEL: motif_digest}
        self.transport, self.clock, self.id_factory = transport, clock, id_factory
        self.lock = threading.Lock()

    def startup_validate(self) -> None:
        for model, base in ((MIDM_MODEL, self.midm_url), (MOTIF_MODEL, self.motif_url)):
            response = self.transport('GET', _url(base, '/api/tags'), {})
            models = response.get('models')
            matching = [entry for entry in models if isinstance(entry, dict)
                        and entry.get('name') == model] if isinstance(models, list) else []
            if len(matching) != 1 or matching[0].get('digest') != self.expected[model]:
                raise GatewayError(503, 'backend model provenance mismatch')

    def authorized(self, header: str | None) -> bool:
        return bool(header and hmac.compare_digest(header, 'Bearer ' + self.token))

    def models(self) -> dict[str, Any]:
        return {'object': 'list', 'data': [
            {'id': MIDM_MODEL, 'object': 'model', 'owned_by': 'airi-local'},
            {'id': MOTIF_MODEL, 'object': 'model', 'owned_by': 'airi-local'},
        ]}

    def _validate_request(self, value: Any) -> tuple[str, list[dict[str, str]], int, int]:
        if not isinstance(value, dict):
            raise GatewayError(400, 'request must be an object')
        allowed = {'model', 'messages', 'stream', 'temperature', 'max_tokens', 'seed'}
        if set(value) - allowed:
            raise GatewayError(400, 'unsupported request option')
        model = value.get('model')
        if model not in self.expected:
            raise GatewayError(400, 'unsupported model')
        if value.get('stream', False) is not False:
            raise GatewayError(400, 'streaming is not supported')
        temperature = value.get('temperature', 0)
        if temperature != 0 or isinstance(temperature, bool):
            raise GatewayError(400, 'temperature must be zero')
        max_tokens = value.get('max_tokens', 128)
        seed = value.get('seed', 0)
        if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or not 1 <= max_tokens <= 128:
            raise GatewayError(400, 'max_tokens out of range')
        if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed <= 2 ** 31 - 1:
            raise GatewayError(400, 'seed out of range')
        messages = value.get('messages')
        if not isinstance(messages, list) or not messages or len(messages) > MAX_MESSAGES:
            raise GatewayError(400, 'invalid messages')
        total = 0
        clean: list[dict[str, str]] = []
        for message in messages:
            if not isinstance(message, dict) or set(message) != {'role', 'content'}:
                raise GatewayError(400, 'invalid message')
            role, content = message.get('role'), message.get('content')
            if role not in ('system', 'user', 'assistant') or not isinstance(content, str):
                raise GatewayError(400, 'invalid message')
            total += len(content)
            if total > MAX_CONTENT_CHARS:
                raise GatewayError(400, 'message content too large')
            clean.append({'role': role, 'content': content})
        return model, clean, max_tokens, seed

    def _unload_other(self, model: str) -> None:
        other, base = (MOTIF_MODEL, self.motif_url) if model == MIDM_MODEL else (MIDM_MODEL, self.midm_url)
        if model == MIDM_MODEL:
            self.transport('POST', _url(base, '/api/show'), {'name': other, 'keep_alive': 0})
        else:
            self.transport('POST', _url(base, '/api/generate'), {'model': other, 'keep_alive': 0})
        ps = self.transport('GET', _url(base, '/api/ps'), {})
        running = ps.get('models')
        if not isinstance(running, list):
            raise GatewayError(503, 'backend state unavailable')
        if model == MIDM_MODEL and running:
            raise GatewayError(503, 'other backend remains loaded')
        if model == MOTIF_MODEL and any(isinstance(x, dict) and x.get('name') == MIDM_MODEL for x in running):
            raise GatewayError(503, 'other backend remains loaded')

    def complete(self, request: Any) -> dict[str, Any]:
        model, messages, max_tokens, seed = self._validate_request(request)
        with self.lock:
            self._unload_other(model)
            base = self.midm_url if model == MIDM_MODEL else self.motif_url
            response = self.transport('POST', _url(base, '/api/chat'), {
                'model': model, 'messages': messages, 'stream': False,
                'options': {'temperature': 0, 'num_predict': max_tokens, 'seed': seed},
            })
        message = response.get('message')
        content = message.get('content') if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise GatewayError(503, 'invalid backend response')
        result = {'id': 'chatcmpl-' + self.id_factory(), 'object': 'chat.completion',
                'created': int(self.clock()), 'model': model,
                'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': content},
                             'finish_reason': 'stop'}]}
        prompt_tokens, completion_tokens = response.get('prompt_eval_count'), response.get('eval_count')
        if isinstance(prompt_tokens, int) and isinstance(completion_tokens, int):
            result['usage'] = {'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens,
                               'total_tokens': prompt_tokens + completion_tokens}
        return result


def make_handler(gateway: Gateway):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'AiriEvalGateway/1'
        def log_message(self, _format: str, *_args: Any) -> None:
            return
        def _send(self, status: int, data: dict[str, Any]) -> None:
            body = json.dumps(data, separators=(',', ':')).encode('utf-8')
            self.send_response(status); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        def _auth(self) -> bool:
            if gateway.authorized(self.headers.get('Authorization')): return True
            self._send(401, {'error': {'message': 'unauthorized', 'type': 'authentication_error'}}); return False
        def do_GET(self) -> None:
            if not self._auth(): return
            if self.path == '/health': self._send(200, {'status': 'ok'})
            elif self.path == '/v1/models': self._send(200, gateway.models())
            else: self._send(404, {'error': {'message': 'not found'}})
        def do_POST(self) -> None:
            if not self._auth(): return
            if self.path != '/v1/chat/completions': self._send(404, {'error': {'message': 'not found'}}); return
            try:
                length = int(self.headers.get('Content-Length', '-1'))
                if length < 0 or length > MAX_BODY_BYTES: raise GatewayError(413, 'request too large')
                value = json.loads(self.rfile.read(length).decode('utf-8'))
                self._send(200, gateway.complete(value))
            except (ValueError, json.JSONDecodeError): self._send(400, {'error': {'message': 'invalid json'}})
            except GatewayError as exc: self._send(exc.status, {'error': {'message': exc.message}})
    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--token-file', required=True); parser.add_argument('--port', type=int, default=11888)
    parser.add_argument('--midm-url', default='http://127.0.0.1:11434'); parser.add_argument('--motif-url', default='http://127.0.0.1:11437')
    parser.add_argument('--midm-digest', required=True); parser.add_argument('--motif-digest', required=True)
    args = parser.parse_args()
    token = Path(args.token_file).read_text(encoding='utf-8').strip()
    gateway = Gateway(token, args.midm_url, args.motif_url, args.midm_digest, args.motif_digest)
    gateway.startup_validate()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(gateway))
    server.serve_forever()


if __name__ == '__main__': main()
