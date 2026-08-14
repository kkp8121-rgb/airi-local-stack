# AIRI evaluations

## Privacy-preserving Korean live-chat replay

`chat_replay/` is the default-off, local-only intake and deterministic replay
boundary for authorized Korean livestream chat exports. Real captures and
redacted response review packets are ignored and require a current consent
sidecar plus its hash-bound local provenance artifact; normal reports are
content-free. A strict offline provider-safe envelope normalizer adds a
local-key HMAC channel/slot binding, drops donation wording and amount, and
rejects raw CHZZK/SOOP/YouTube payload shapes. Report v2 measures rolling flow,
pre-redaction source-text repeats, bounded lexical signals, and closed proxy
outcomes. A separate private-review scorer emits only confusion counts and
quality pass rates after binding the exact replay report and responses with a
local key. A strict campaign validator then requires three anonymous sources,
at least two phases per source, paired Mi:dm epistemic OFF/ON runs, completed
bounded human atmosphere/pattern labels, and a fresh operator attestation.
Its aggregate omits all source identities, paths, hashes, HMACs, and text and
never authorizes automatic gate adoption. The committed
fixture is independently authored synthetic text, not anonymized chat and not
training data. See `chat_replay/README.md` for the exact custody and CLI
contract. No provider scraping or network request occurs by default.

## Persona-jailbreak direct-model marker-contract gate

`run_airi_persona_jailbreak_gate.py` sends the frozen multilingual corpus
directly to a literal-loopback Ollama `/api/chat` endpoint. It uses
`think=false`, temperature 0, seed 42, and production-sized `num_ctx=2048`;
`--num-gpu` remains configurable. The corpus covers Korean, English, Japanese,
and Chinese benign requests, direct jailbreaks, indirect prompt injection,
profanity/targeted harassment, and explicit-sexual requests. Code-switch and
punctuation/zero-width variants are included.

```powershell
cd <repo>\ollama-proxy\eval
python -m unittest -v test_airi_persona_jailbreak_gate.py
python run_airi_persona_jailbreak_gate.py --model midm-airi:2.0-mini --expected-digest 92a9ba2ee8c79ba46c22907b50b15eb1ca55c94d04230eca73917936ef36485f --output airi-persona-jailbreak-report.json --fail-on-gate
```

The runner reads the fixture once before requests, verifies its exact 4×5
language/category matrix and prompt hashes, then requires an exact model tag,
digest, and `/api/show` provenance. The fixture contains test text and
per-prompt SHA-256 values. The report is deliberately content-free: it has case
IDs, language/category, boolean structural and marker-contract outcomes,
response character counts/hashes, timings, and bounded model provenance only.
The runner atomically writes the report. A custom fixture is nonauthoritative
unless its canonical bytes match the bundled corpus.

This is a **direct local-model marker-contract evaluation**, not a test of the
installed Electron client, AIRI proxy, or a semantic input classifier. It does
not claim semantic safety, nor does a passing marker contract prove production
input-screening coverage. `--fail-on-gate` applies only to structural and exact
standalone-marker contract checks.

## Production continuity/projection gate

`run_airi_production_context_gate.py` is distinct from the raw capacity gate:
it runs a frozen synthetic conversation through the current proxy projection,
continuity-ledger, snapshot memory assembler, language/mode injection and
native Ollama conversion. It does not start the proxy or access a memory
runtime, store, or session. The live CLI calls only a literal loopback
`/api/chat` endpoint by default; tests use a fake transport.

```powershell
cd <repo>\ollama-proxy\eval
python -m unittest -v test_airi_production_context_gate.py
python run_airi_production_context_gate.py --output airi-production-context-report.json --fail-on-gate
```

The raw capacity gate (`run_airi_context_gate.py`) measures model retention
against a direct synthetic prompt. This production continuity/projection gate
instead verifies that production shaping removes old pressure/holdout text,
preserves the deterministic tail, and strips private message names before the
native request. Three runs across pressures 0, 8, 20, and 48 are authoritative;
other `--runs` values are marked non-authoritative in the report.

# AIRI C0 baseline evaluation

## Synthetic context gate

The context gate is a synthetic-only, non-streaming raw Ollama `/api/chat` comparison at production `num_ctx=2048`. It records retention of an active card, early user/assistant facts, a late correction/negation, and a tail memory block. It does not exercise the Electron app, human quality, or production-proxy retry behavior.

```powershell
python -m unittest -v ollama-proxy/eval/test_airi_context_gate.py
python ollama-proxy/eval/run_airi_context_gate.py --model exaone-airi:2.4b --output airi-context-exaone.json
python ollama-proxy/eval/run_airi_context_gate.py --model midm-airi:2.0-mini --output airi-context-midm.json
```

Reports contain only public fixture canaries and local Ollama metadata; remote hosts require `--allow-host`.

이 디렉터리는 **합성 텍스트 fixture만** 사용하는 로컬 Ollama baseline harness다. 학습 코드가 아니며, 실제 사용자 대화·음성·전사·API 키·환경 비밀을 읽거나 저장하지 않는다. 현재 v0.3 fixture는 16개이며, 성인 간 비노골적 관계 대화의 과잉 거부, 노골적·미성년 경계, active character-card 정체성, character-card보다 우선하는 도구 진실성 계약을 함께 평가한다.

기본값은 `http://127.0.0.1:11434/api/chat`, `exaone-airi:2.4b`, `num_ctx=2048`, `num_gpu=0`, `temperature=0`, `seed=42`, `runs=1`이다. `--runs`는 1~10회 실제 반복 측정을 수행하고, 표의 시간은 중앙값이다. 외부 host는 `--allow-host` 없이는 거부된다.

```powershell
cd <repo>\ollama-proxy\eval
python -m unittest -v test_airi_baseline.py
python run_airi_baseline.py --output airi-baseline-report.json --markdown-output airi-baseline-report.md
# 행동 gate 실패도 종료 코드로 반영하려면:
python run_airi_baseline.py --fail-on-gate
```

JSON은 fixture/system-prompt hash, 안전하게 축약한 model metadata, runtime 설정, 각 반복의 합성 output/check/TTFT/총 시간/tok/s와 케이스별 중앙값을 기록한다. Markdown 표는 같은 report에서 결정적으로 생성된다. 정상 `done:true` 없이 잘린 스트림과 전송·schema 오류는 항상 nonzero이며, 행동 check 실패는 report의 `aggregate.gate=FAIL`로 남고 `--fail-on-gate`에서만 nonzero가 된다.

현재 fixture SHA-256은 `95309E101E30009EC12A9EDB4D047E69A46AEC42C2F46DF0A8B70962225DC3BE`다. `results/`의 기존 10-case report는 v0.2 기준 역사적 baseline이며 현재 16-case gate의 결과로 재사용하지 않는다. AIRI session-header patch와 새 proxy가 실제로 올라온 뒤 v0.3을 한 번 실행해 runtime 결과를 고정한다. failing baseline도 비교 기준으로 유효하므로, PASS 수를 높이기 위한 prompt·fixture 미세조정은 하지 않는다.

C0에는 아직 human rating, 실제 음성 평가, T0 first-audio 측정이 포함되지 않는다. `human_review` 필드는 후속 사람이 합성 응답의 톤·정확성·안전성을 검토할 수 있도록 남겨 둔 기준이다. “Gear”라는 별도 모델·카드·상태 계약은 현재 저장소와 AIRI v0.11.3 snapshot에서 확인되지 않았으므로, character-card 적용과 동일하다고 추측하지 않는다. 실제 UI/설정에서 그 이름의 소유자와 입력 경로를 확인한 뒤 별도 integration case를 추가한다.
