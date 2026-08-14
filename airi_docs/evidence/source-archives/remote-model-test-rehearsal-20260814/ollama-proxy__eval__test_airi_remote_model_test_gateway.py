import importlib.util
import threading
import time
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name('run_airi_remote_model_test_gateway.py')
SPEC = importlib.util.spec_from_file_location('gateway_module', MODULE_PATH)
gateway_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(gateway_module)
Gateway = gateway_module.Gateway
GatewayError = gateway_module.GatewayError
MIDM_MODEL = gateway_module.MIDM_MODEL
MOTIF_MODEL = gateway_module.MOTIF_MODEL


class RecordingTransport:
    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()
        self.active = 0
        self.maximum_active = 0

    def __call__(self, method, url, payload):
        with self.lock:
            self.calls.append((method, url, payload))
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
        try:
            if url.endswith('/api/ps'):
                return {'models': []}
            if url.endswith('/api/chat'):
                time.sleep(.02)
                return {'message': {'content': 'safe answer'}, 'prompt_eval_count': 2, 'eval_count': 3}
            if url.endswith('/api/tags'):
                if '11434' in url:
                    return {'models': [{'name': MIDM_MODEL, 'digest': 'd-mid'}]}
                return {'models': [{'name': MOTIF_MODEL, 'digest': 'd-motif'}]}
            if url.endswith('/api/show'):
                model = payload['name']
                return {'name': model, 'digest': 'd-mid' if model == MIDM_MODEL else 'd-motif'}
            return {}
        finally:
            with self.lock:
                self.active -= 1


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.transport = RecordingTransport()
        self.gateway = Gateway('x' * 32, 'http://127.0.0.1:11434', 'http://127.0.0.1:11437',
                               'd-mid', 'd-motif', self.transport, lambda: 7, lambda: 'fixed')

    def request(self, model=MIDM_MODEL):
        return {'model': model, 'messages': [{'role': 'user', 'content': 'private prompt'}],
                'temperature': 0, 'max_tokens': 4, 'seed': 1, 'stream': False}

    def test_token_and_startup_provenance(self):
        with self.assertRaises(ValueError):
            Gateway('short', 'a', 'b', 'x', 'y')
        with self.assertRaisesRegex(ValueError, 'loopback'):
            Gateway('x' * 32, 'http://localhost:11434', 'http://127.0.0.1:11437', 'x', 'y')
        self.gateway.startup_validate()
        bad = Gateway('x' * 32, 'http://127.0.0.1:11434', 'http://127.0.0.1:11437', 'wrong', 'd-motif', self.transport)
        with self.assertRaisesRegex(GatewayError, 'provenance'):
            bad.startup_validate()

    def test_auth_and_model_listing(self):
        self.assertTrue(self.gateway.authorized('Bearer ' + 'x' * 32))
        self.assertFalse(self.gateway.authorized('Bearer bad'))
        self.assertEqual([m['id'] for m in self.gateway.models()['data']], [MIDM_MODEL, MOTIF_MODEL])

    def test_exact_mapping_and_midm_unload_order(self):
        result = self.gateway.complete(self.request())
        self.assertEqual(result['id'], 'chatcmpl-fixed')
        self.assertEqual(result['choices'][0]['message']['content'], 'safe answer')
        self.assertEqual(result['usage'], {'prompt_tokens': 2, 'completion_tokens': 3, 'total_tokens': 5})
        paths = [item[1] for item in self.transport.calls]
        self.assertEqual(paths, ['http://127.0.0.1:11437/api/show', 'http://127.0.0.1:11437/api/ps',
                                 'http://127.0.0.1:11434/api/chat'])
        chat = self.transport.calls[-1][2]
        self.assertEqual(chat['options'], {'temperature': 0, 'num_predict': 4, 'seed': 1})
        self.assertEqual(chat['messages'][0]['content'], 'private prompt')

    def test_motif_unloads_midm_with_generate(self):
        self.gateway.complete(self.request(MOTIF_MODEL))
        self.assertEqual(self.transport.calls[0][1], 'http://127.0.0.1:11434/api/generate')
        self.assertEqual(self.transport.calls[0][2], {'model': MIDM_MODEL, 'keep_alive': 0})

    def test_tags_provenance_does_not_depend_on_show_digest(self):
        # /api/show is allowed to omit digest (as live Ollama does); startup uses tags.
        self.gateway.startup_validate()
        self.assertTrue(all('/api/tags' in call[1] for call in self.transport.calls))
        class BadTags(RecordingTransport):
            def __call__(self, method, url, payload):
                if url.endswith('/api/tags'):
                    return {'models': [{'name': MIDM_MODEL, 'digest': 'd-mid'},
                                       {'name': MIDM_MODEL, 'digest': 'd-mid'}]}
                return super().__call__(method, url, payload)
        bad = Gateway('x' * 32, 'http://127.0.0.1:11434', 'http://127.0.0.1:11437',
                      'd-mid', 'd-motif', BadTags())
        with self.assertRaisesRegex(GatewayError, 'provenance'):
            bad.startup_validate()

    def test_limits_and_unsupported_data_do_not_echo_content(self):
        bad = self.request(); bad['tools'] = [{'type': 'function'}]
        with self.assertRaisesRegex(GatewayError, 'unsupported'):
            self.gateway.complete(bad)
        bad = self.request(); bad['messages'] = [{'role': 'user', 'content': ['image']}]
        with self.assertRaises(GatewayError) as caught:
            self.gateway.complete(bad)
        self.assertNotIn('image', caught.exception.message)
        bad = self.request(); bad['messages'] = [{'role': 'user', 'content': 'x' * 32769}]
        with self.assertRaisesRegex(GatewayError, 'too large'):
            self.gateway.complete(bad)
        bad = self.request(); bad['stream'] = True
        with self.assertRaisesRegex(GatewayError, 'streaming'):
            self.gateway.complete(bad)

    def test_calls_are_serialized(self):
        failures = []
        def run():
            try: self.gateway.complete(self.request())
            except Exception as error: failures.append(error)
        threads = [threading.Thread(target=run) for _ in range(3)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(failures, [])
        # All backend work, including unload checks, belongs under the global lock.
        self.assertEqual(self.transport.maximum_active, 1)


if __name__ == '__main__':
    unittest.main()
