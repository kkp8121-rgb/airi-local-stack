# AIRI 업그레이드 탐색 — 축별 원본 데이터 (2026-08-11)

본문은 `AIRI-UPGRADE-SCOUT-2026-08-11.md`입니다. 이 파일은 실측 3축 + 조사 6축이 제출한 후보 전량과 적대적 검증 판정을 축약 없이 담습니다.

판정 표기: `VIABLE`(타당) · `DOWNGRADE`(실재하나 이득 과장) · `UPGRADE`(이득 과소평가) · `UNVERIFIED`(검증 미실시). `BLOCKED`는 이미 제외돼 여기 없습니다.


---

## [측정] BUDGET
현재 지연 예산을 코드에서 분해한 결과, "이론상 최선"과 "실제"의 격차는 파이썬/JSON 오버헤드가 아니라 세 개의 구조적 버퍼링과 한 개의 O(N) 루프에 몰려 있습니다. (1) ollama_proxy 로컬 경로는 스트리밍이 아닙니다 — ollama_proxy.py:5931~6044 루프가 `boundary.feed()` 반환값을 버리고 실제 delta yield는 6376 한 곳뿐이라, LLM 문장이 완결될 때까지 클라이언트로 한 바이트도 안 나갑니다(클라우드 경로 5593~5610은 반대로 증분 yield). 측정치 "LLM 첫 content 427.3ms"는 본답변이 아니라 캐시된 '응!' ack입니다. (2) 클라이언트는 `res: ArrayBuffer` 전체를 받은 뒤 `decodeAudioData(res)`(patch:4189)를 호출하므로 서버의 streaming_mode=2·min_chunk_length=16 이득이 0이며, 실측 근거로 재생 시작이 TTS end 대비 +14ms입니다. (3) 기억 검색의 파이썬 cosine(airi_memory.py:183)은 제가 이 PC에서 직접 측정해 1024차원 2,000행에 379ms — 150ms 타임아웃을 이미 2.5배 초과해 기억이 조용히 폐기되고 있을 가능성이 큽니다(numpy 등가 0.24ms). (4) STT 이중 디코드(LAT-09)는 아직 그대로입니다 — openai_stt_server.py:832의 analyze_audio가 만든 배열을 버리고 833에서 같은 파일을 PyAV로 다시 디코드합니다. 반면 JSON 왕복 10회는 8,335B 페이로드 기준 총 1.8ms(측정: 1왕복 0.178ms), deepcopy 0.015ms로 최적화 가치가 없습니다 — 여기 손대지 마십시오. 업스트림 전송 이전 직렬 대기의 상한은 평가자 50ms + 기억 150ms + 지식 350ms = 최대 550ms이고 나머지는 모두 수 ms 이하입니다. 결론적으로 설정·파라미터만으로 줄일 수 있는 몫은 기능 축소 없이는 50~90ms, 기능을 끄는 것까지 허용해도 370~720ms인 반면 구조 변경이 필요한 몫은 약 1,000~2,000ms입니다 — P50 ≤2초 달성분의 80% 이상이 설정이 아니라 구조에 있습니다. TTS_LOCK은 max_sentences=1 정책 덕에 턴 내부 경합이 드물지만, acquire에 타임아웃이 없고 백엔드 타임아웃이 60초라 막힌 1건이 threadpool 전체를 막는 starvation 형태가 남아 있습니다.
판정:

- `BUDGET-C1` [high/S] [설정] 캐릭터 평가자 비활성 — 턴마다 고정 50ms 대기 + GPU 러너 경합 제거
  이득: 턴당 고정 0~50ms 제거. 추가로 평가자 호출이 러너를 잡고 있던 턴에서는 간헐적으로 수백 ms(평가자 max_tokens=320, timeout 15s) 회수. 기능 축소 폭 대비 가장 확실한 설정 이득입니다.
  비용: 런처 인자 1개. 재기동만 필요. 코드 변경 0줄.
  근거: ollama-proxy/ollama_proxy.py:5096 (await interrupt_for_chat), ollama-proxy/character_state_evaluator.py:327-343 (asyncio.wait timeout=0.05), ollama-proxy/start-local-ollama-proxy.ps1:229-236 (AIRI_CHARACTER_EVALUATOR_NUM_GPU=$NumGpu=999, 동일 11434 업스트림), start-airi-local-stack.ps1:25 (EnableCharacter

- `BUDGET-C2` [high/S] [설정] 지식 RAG 비활성 — 업스트림 직전 최대 350ms 상한 제거
  이득: 지식 게이트를 통과하는 사실질문 턴에서 0~350ms. 게이트 통과율은 /health에 이미 노출된 retrievals / retrievals_with_hit 카운터로 즉시 실측 가능합니다.
  비용: 런처 인자 1개.
  근거: ollama-proxy/ollama_proxy.py:4087-4091 (prepare_knowledge_body), ollama-proxy/ollama_proxy.py:420-429 (KnowledgeRuntime.retrieve, timeout=0.35), ollama-proxy/ollama_proxy.py:4081 (prepare_memory_body가 기억 검색 뒤에 순차 호출), ollama-proxy/ollama_proxy.py:399-403 (allow_semantic 기본 False 주석), :364-385 (shoul

- `BUDGET-C3` [high/S] [설정] 기억 임베더 비활성 또는 CPU 이전 — 파이썬 cosine 379ms 제거 + KURE-v1 fp32 약 2.4GB VRAM 회수
  이득: 본 검토 PC에서 직접 측정 — 1024차원 2,000행 기준: 전체 파이썬 cosine 경로 379ms → 임베더 없을 때 57.5ms(unpack만 잔존). 약 320ms 회수. 추가로 CUDA 인코드 1회(포그라운드 LLM과 GPU 경합)가 사라지고 VRAM 약 2,400MB 회수. `-MemoryEmbedDevice cpu`만 적용하면 VRAM만 회수하고 cosine 비용은 그대로 남습니다.
  비용: 런처 인자 1개. 저장된 벡터는 보존되므로 재활성 시 다시 쓰입니다.
  근거: ollama-proxy/airi_memory.py:183-188 (순수 파이썬 cosine, 빈 qvec 즉시 0.0 반환), :1697-1705 (sorted key=score가 엔티티 전수에 cosine 호출), :1732-1737 (relations도 동일), ollama-proxy/memory_runtime.py:156-174 (fp16 변환 없이 SentenceTransformer 로드), ollama-proxy/start-local-ollama-proxy.ps1:20-22 (KURE-v1 / cuda 기본값), https

- `BUDGET-C4` [medium/S] [설정] AIRI_MEMORY_RETRIEVE_TIMEOUT_MS 하향 (150→70) — 낭비되는 대기 절반 삭감
  이득: 기억 검색이 타임아웃으로 끝나는 턴에서 약 70~80ms. 성공하는 턴(행 수가 적을 때)에서는 이득 0이며 오히려 성공률이 떨어집니다.
  비용: 환경변수 1개. start-local-ollama-proxy.ps1의 $memoryEnvironment 해시에 추가.
  근거: ollama-proxy/memory_runtime.py:82 (retrieve_timeout_ms 기본 150), :129 (_positive('AIRI_MEMORY_RETRIEVE_TIMEOUT_MS', 150)), :390-399 (asyncio.wait_for 상한, 초과 시 빈 RetrievalResult 반환)

- `BUDGET-C5` [high/S] [설정] GPT_SOVITS_BACKEND_TIMEOUT 60→15 — 막힌 1건이 전체 TTS를 60초 막는 starvation 완화
  이득: 지연 자체를 줄이진 않습니다. 최악 대기를 60초→15초로 줄이는 가용성 개선입니다. 정상 warm 합성이 1.2초대라 15초는 충분한 여유입니다.
  비용: 환경변수 1개.
  근거: gpt-sovits/openai_compatible_proxy.py:44 (BACKEND_TIMEOUT_SECONDS, env 조정 가능), :55 (TTS_LOCK = threading.Lock()), :223-231 (타임아웃 없는 acquire), :206-213 (본문 소진까지 락 유지), :333 (sync def speech → threadpool), :367-376 (캐시 히트는 락 이전 반환), :259-268 및 :315-320 (끼어들기 시 GeneratorExit·응답 finally에서 락 해제). 수치: air

- `BUDGET-C6` [high/S] [설정·주의] TTS 스트리밍 파라미터는 지금 건드리지 마십시오 — 클라이언트 완성 버퍼링 때문에 이득이 0입니다
  이득: 0ms. 다만 BUDGET-S2(클라이언트 청크 재생)를 먼저 하면 이 파라미터가 비로소 살아나며, 그때 min_chunk_length 16→8로 첫 음절을 더 앞당길 수 있습니다(추정, 확인 필요).
  비용: 0. 오히려 잘못 조정하면 청크가 잘게 쪼개져 총 합성 시간이 늘고 클라이언트는 여전히 전체를 기다려 순손실입니다.
  근거: gpt-sovits/openai_compatible_proxy.py:40-41 (STREAMING_MODE=2, MIN_CHUNK_LENGTH=16), :117 (parallel_infer False 하드코딩), airi_docs/patches/AIRI-v0.11.3-local-runtime-source.patch:4189 (decodeAudioData(res)), airi_docs/AIRI-PLAYBACK-TRACE-CHECKPOINT-2026-08-10.md ('TTS duration: 1,965.8 ms' / 'playback

- `BUDGET-S1` [high/L] [구조] ollama_proxy 로컬 경로가 전혀 스트리밍하지 않습니다 — 문장 완결까지 클라이언트 무음
  이득: 첫 토큰 이후 문장 완결까지의 생성 시간 전체. max_sentences=1·preferred_chars=60·max_chars=96 제약이라 한 문장은 대략 30~50토큰 — EXAONE 2.4B Q4_K_M/3060 Ti에서 약 300~800ms로 추정합니다(정확값 확인 필요 — latency-monitor의 llm raw_content 대 llm content 타임스탬프 차로 즉시 실측 가능하며 둘 다 이미 방출됩니다). grounding 재시도가 발동하면 2회차 생성이 통째로 더해집니다(상한 5.0s).
  비용: L. 단순 yield 추가로는 안 됩니다 — grounding_candidate_fabricates 계열 검증이 전체 문장을 봐야 성립하도록 설계돼 있습니다. 게이트를 '첫 절 통과 후 잔여 스트리밍'으로 재설계하거나 boundary가 안전하다고 커밋한 절 단위로 조기 방출하는 구조가 필요합니다.
  근거: ollama-proxy/ollama_proxy.py:5931-6044 (루프에서 clean 폐기, yield 없음), :6331 (boundary.finish), :6373-6376 (유일한 최종 delta), :5593-5610 (클라우드 경로는 증분 yield — 대조군), :5671-5676 (ack delta), :1594-1597 (LOCAL_IMMEDIATE_ACK='응!'), gpt-sovits/openai_compatible_proxy.py:58 (IMMEDIATE_RESPONSE_TEXTS 캐시 일치), ollama

- `BUDGET-S2` [high/XL] [구조] 클라이언트 완성 버퍼링 — 실측 근거 있는 최대 단일 삭감분(약 580~1,350ms)
  이득: 실측 두 건 — (a) acceptance 문서 warm: total 1,192.9ms − first byte 613.3ms = 약 580ms. (b) 2026-08-10 라이브 턴: TTS 1,965.8ms, 재생은 TTS end +14ms → first byte 대비 약 1,350ms. 턴당 580~1,350ms이며 이 축에서 가장 크고 가장 확실한 단일 삭감분입니다.
  비용: L~XL. WAV 컨테이너는 MediaSource가 지원하지 않으므로 서버가 raw PCM 또는 MSE 지원 컨테이너를 내보내도록 바꾸거나, 클라이언트에서 WAV 헤더(44B)를 파싱해 PCM을 AudioWorklet 링버퍼로 밀어 넣어야 합니다. 라운드 취소(activeSpeechRoundId)와 wLipSync 그래프 연결이 AudioBufferSourceNode 전제로 짜여 있어 재배선 범위가 넓습니다.
  근거: airi_docs/patches/AIRI-v0.11.3-local-runtime-source.patch:4014 (+++ b/packages/stage-ui/src/components/scenes/Stage.vue), 같은 파일 patch:4165 (let res: ArrayBuffer | undefined), patch:4173 (res = await generateSpeech({...})), patch:4187 (!res || res.byteLength === 0 검사), patch:4189 (const audioBuffer =

- `BUDGET-S3` [high/M] [구조] 파이썬 cosine → numpy 벡터화 — 측정 379ms를 0.24ms로 (약 1,580배)
  이득: 본 검토 PC 실측 — 1024차원 2,000행: 현재 경로 379ms → numpy 등가 0.24ms. 약 380ms 회수. 더 중요한 건, 이 값이 AIRI_MEMORY_RETRIEVE_TIMEOUT_MS=150 상한을 이미 2.5배 초과한다는 점입니다. 즉 지금 기억 검색은 '느린 것' 이전에 '조용히 안 되고 있을' 가능성이 큽니다 — 150ms를 버리고 빈 결과를 반환하는 구조. 벡터화하면 지연 삭감과 기능 복구가 동시에 일어납니다.
  비용: M. 저장 포맷(BLOB)은 그대로 두고 로드 시 numpy로 변환하는 캐시 레이어만 추가하면 됩니다. 기존 cosine() 시그니처는 단위 테스트(test_airi_memory.py)가 쓰고 있으니 유지하고 핫 경로만 교체.
  근거: ollama-proxy/airi_memory.py:177-188 (unpack_vector / cosine), :1697-1705 (sorted key=score, 엔티티 전수), :1732-1737 (relations 전수), :1687-1690 (의미 캐시 조회에서도 cosine 선형 스캔), ollama-proxy/memory_runtime.py:390-399 (150ms 상한, 초과 시 빈 결과), :174 (normalize_embeddings=True). 측정(본 검토 PC, Python 3.12): cosine+unpa

- `BUDGET-S4` [high/S] [구조] STT 이중 디코드(LAT-09) 아직 존재 — 같은 파일을 PyAV로 두 번 디코드
  이득: 분석 단계의 정확히 절반. 3초 webm/opus 발화 기준 약 25~60ms 추정, 10초면 80~200ms 추정 — 정확값은 확인 필요하나 이미 계측돼 있습니다: 서버가 감사 이벤트에 analysis_ms(838행 계산, 933행 방출)를 내보내며 이 값이 두 디코드를 모두 포함합니다. 추측하지 말고 이 값을 먼저 보십시오 — 이득은 그 절반입니다.
  비용: S. 함수 2개 시그니처 변경과 호출부 1곳. 기존 테스트(test_transcription_filter.py)는 파일 경로 인터페이스를 거의 안 쓰는 순수 함수 위주라 영향이 적을 것으로 보이나 확인 필요.
  근거: stt/openai_stt_server.py:832 (await to_thread(analyze_audio, temp_path)), :833-837 (await to_thread(prepare_audio_for_whisper, temp_path, ...)), :371-391 (analyze_audio가 decoded 배열 생성 후 폐기), :394-406 (load_audio_samples — 동일 디코드 반복), :463-471 (prepare_audio_for_whisper가 load_audio_samples 호출), :838/

## [측정] VRAM
레포에 남은 VRAM 실측은 4건뿐이며 **전부 Ollama num_gpu=0 또는 12에서 측정된 값**입니다: GPT-SoVITS 단독 5,092/8,192MiB → +Ollama(num_gpu=12) 5,975MiB → 실제 마이크 세션(num_gpu=0, STT CUDA, AIRI 실행) **7,586/8,192MiB(여유 606MiB)** → KURE-v1 CUDA 상주 후 **여유 약 1.16GB**. 반면 현재 기본 런타임은 num_gpu=999인데(start-airi-local-stack.ps1:7), 이 구성의 VRAM 실측은 레포 어디에도 없습니다(AIRI-WORK-CHECKPOINT-2026-08-10.md:163은 num_gpu=999만 기록하고 수치는 없음) — 이것이 이 축의 최대 갭입니다. 산술 판정: KURE 포함 num_gpu=0 상태 사용량 ≈7,030MiB에 EXAONE 전량 GPU분(가중치 1.6GB + KV + compute buffer ≈1,900~2,100MiB 추정)을 더하면 **8,930~9,130MiB로 8,192MiB를 약 740~940MiB 초과**합니다. 즉 남는 VRAM은 0이 아니라 음수이며, Ollama는 로드 시점 가용량에 맞춰 레이어를 자동 하향하므로 **num_gpu=999는 명목값에 그치고 실제 오프로드 층수가 실행마다 달라져 TTFT·tok/s가 재현되지 않습니다**. num_gpu=12 vs 999 "불일치"는 프로덕션 경로에서는 999가 이깁니다(start-local-ollama-proxy.ps1:251이 `--num-gpu`를 넘기고 ollama_proxy.py:7279가 :108의 12를 덮어씀) — 다만 12가 Modelfile.exaone-airi:3에 살아 있어 옵션 없는 요청이 오면 러너 언로드→재로드(수 초 stall)를 유발하고, 12로 굳어지면 생성 속도가 실측 CPU 17.82 tok/s와 GPU 추정 70~110 tok/s 사이인 약 25~30 tok/s로 떨어져 60자 응답 기준 **+1.2~1.5초**가 붙어 P50 ≤2초 목표를 이것 하나로 파괴합니다. 단일 최대 절감 항목은 **KURE-v1이 fp32(2.27GB)로 GPU에 상주하는 것**이며(memory_runtime.py:166-167에 dtype 미지정, 기본 device='cuda'), fp16 한 줄로 약 1.1GB를 회수해야 비로소 num_gpu=999가 산술적으로 성립합니다. 결론적으로 **KURE 예산을 줄이기 전에는 어떤 신규 GPU 상주 제안도 불가**이며, 다른 축 제안은 아래 vram-hard-blocks 목록으로 걸러야 합니다.
판정: **부분적으로 뒤처졌습니다 — 다만 정확한 답은 "판정할 데이터가 지금 없다"입니다.** ① STT(faster-whisper large-v3-turbo, int8_float16, CUDA)와 TTS(GPT-SoVITS v2ProPlus, is_half:true — tts-infer-v2proplus.yaml:4-5)는 각 계층에서 8GB 예산 대비 여전히 최선이며 교체 이유가 없습니다. ② **KURE-v1의 fp32 GPU 상주는 명백히 열등한 현 선택입니다** — memory_runtime.py:166-167에 dtype이 지정돼 있지 않아 2.27GB를 그대로 쓰고 있고, fp16 한 줄로 약 1.1GB를 회수할 수 있습니다. 이 하나가 예산 초과분(추정 740~940MiB) 전체보다 큽니다. ③ **num_gpu=999는 "선택"이라기보다 "요청"입니다** — 산술적으로 8,192MiB에 들어가지 않는 요청이라 Ollama가 로드 시점에 자동 하향하며, 그 결과 실제 오프로드 층수가 비결정적입니다. 의도(전량 GPU)와 결과(불명)가 분리돼 있어 현재 상태로는 최선인지 열등한지조차 말할 수 없습니다. ④ 12/999/0 세 값이 Modelfile.exaone-airi:3, ollama_proxy.py:108, 런처 기본값, 문서 2종에 흩어져 SSoT가 없는 것은 그 자체로 결함입니다(단 프로덕션 경로에서는 999가 이기므로 "12로 돌고 있다"는 우려는 사실이 아닙니다 — start-local-ollama-proxy.ps1:251 → ollama_proxy.py:7279). ⑤ 결정적으로 **현 구성의 VRAM 실측이 2026-08-08(num_gpu=0 시점) 이후 없습니다**. 따라서 권고 순서는 고정입니다: vram-measure-now(실측) → kure-fp16(예산 확보) → num-gpu-ssot + ollama-num-parallel(결정론) → startup-order(배분). 이 순서를 건너뛴 어떤 VRAM 제안도 추측 위에 쌓는 것입니다.

- `vram-measure-now` [high/S] [선행 필수] num_gpu=999 현행 구성의 단계별 VRAM 실측
  이득: 이 축의 모든 추정(EXAONE 999분 1,900~2,100MiB, GPT-SoVITS 2.0~2.5GB, STT 1.5~1.6GB, KURE 2.4~2.7GB)을 실측으로 대체한다. 특히 '999를 요청했지만 실제로 몇 층이 올라갔는가'가 확정되어, LLM 생성 속도가 100 tok/s대인지 30 tok/s대인지가 판정된다. 다른 리서처 제안의 채택/기각 기준선이 여기서 나온다.
  비용: S. PowerShell 스크립트 1개 + GPU PC에서 10분. 서비스 재기동 1회 외 코드 변경 없음.
  근거: C:/Projects/airi-local-stack/start-airi-local-stack.ps1:97,102,185,186,200-221 (기동 순서) · latency-monitor/monitor_server.py:274 · latency-monitor/dashboard.html:116 · airi_docs/AIRI-WORK-CHECKPOINT-2026-08-10.md:163,167 (num_gpu=999 기록, VRAM 수치 없음)

- `kure-fp16` [medium/S] KURE-v1을 fp16으로 로드 — 단일 최대 VRAM 회수
  이득: model.safetensors 2.27GB → 약 1.14GB. 활성화/워크스페이스 포함 **약 1,100~1,200MiB 회수(추정)**. 이 회수만으로 위 산술 초과분(740~940MiB)이 해소되어 EXAONE num_gpu=999가 비로소 성립한다. 질문 임베딩이 TTFT 직렬 경로에 있으므로 GPU 상주를 유지한 채 절감한다는 점이 핵심 — CPU 이전과 달리 지연 리스크가 없다.
  비용: S. 1~2줄. 임베딩 fingerprint는 모델명 기준이라(memory_runtime.py:169 `f"{model_name}@{Path(resolved_model).name}"`) 계약 재협상이나 재색인이 유발되지 않는다.
  근거: C:/Projects/airi-local-stack/ollama-proxy/memory_runtime.py:156-171 (dtype 미지정) · :169 (fingerprint) · ollama-proxy/start-local-ollama-proxy.ps1:20,22 · ollama-proxy/ollama_proxy.py:412 (embedder 공유) · https://huggingface.co/nlpai-lab/KURE-v1/tree/main (model.safetensors 2.27GB, 2026-08-11 확인) · htt

- `num-gpu-ssot` [high/S] num_gpu 단일 소스화 + 실제 오프로드 층수 기동 게이트
  이득: ① 서로 다른 num_gpu 요청이 섞일 때 Ollama가 러너를 언로드→재로드하며 발생하는 수 초 stall을 제거. ② 부분 오프로드를 조용히 겪는 대신 즉시 알게 된다 — 12/31로 굳으면 생성 속도가 약 25~30 tok/s로 떨어져(실측 CPU 17.82 tok/s와 GPU 추정 70~110 tok/s의 roofline 혼합), preferred 60자/max 96자 ≈ 30~55토큰 기준 생성이 0.5~0.8초 → 1.8~2.2초, 즉 **+1.2~1.5초**가 종단에 순증한다.
  비용: S. Modelfile 1줄, 상수 1줄, 기동 스크립트에 파싱 1블록.
  근거: C:/Projects/airi-local-stack/ollama-proxy/Modelfile.exaone-airi:3 · ollama-proxy/ollama_proxy.py:108,4618,4771,7274,7279 · ollama-proxy/start-local-ollama-proxy.ps1:8,251 · start-airi-local-stack.ps1:7,207 · airi_docs/AIRI-INDEPENDENT-REVIEW-DATA-2026-08-10.md:697 (num_gpu=0 baseline 17.82 tok/s 실측)

- `vram-hard-blocks` [high/S] [판정] 8GB 예산상 애초에 불가능한 업그레이드 목록 — 타 축 제안 필터
  이득: 다른 리서처가 올릴 제안 중 GPU 상주를 요구하는 항목을 즉시 기각할 수 있다. 특히 ⑥은 이 프로젝트가 이미 실제로 부딪힌 사례 — qwen3:4b(2.5GB)를 검토할 때 여유가 1.8GB뿐이라 별도 11436 Ollama를 num_gpu=0(CPU)으로 격리해야 했다.
  비용: 없음 (판정).
  근거: C:/Projects/airi-local-stack/airi_docs/AIRI-TRACK-M-HANDOFF-2026-08-08.md:137 ("KURE 상주 후 GPU 여유 약 1.16 GB. 추가 GPU 모델 동시 적재 금지.") · :523-524 (여유 1.8GB → qwen3:4b를 11436 num_gpu=0으로 격리) · airi_docs/AIRI-CODE-AUDIT-2026-08-06.md:130 ("여유가 약 2.2GB뿐이므로 다른 GPU 작업을 함께 시작하면 OOM 위험") · airi_docs/AIRI-FIX-HA

- `kure-cpu-onnx` [medium/L] KURE를 CPU ONNX int8로 이전 — 최대 회수, 지연 리스크 동반
  이득: 약 2,400~2,700MiB 회수(추정) — 단일 항목 최대. GPT-SoVITS·STT·EXAONE 999가 모두 여유롭게 들어가고, 소형 reranker 추가 여지까지 생긴다.
  비용: M~L. sentence-transformers backend 교체 또는 별도 ONNX 런타임 배선 + 벡터 차원/정규화 계약 재검증. 임베더 교체 시 전체 재색인(memory DB 37,666 messages 규모 — AIRI-TRACK-M-HANDOFF-2026-08-08.md:131).
  근거: C:/Projects/airi-local-stack/ollama-proxy/start-local-ollama-proxy.ps1:20,22 · ollama-proxy/memory_runtime.py:102-105,156-171 · ollama-proxy/benchmark_memory_track.py:465-476 (임베딩 device별 벤치 하네스 이미 존재, --embedding-device cpu/cuda 지원) · airi_docs/AIRI-INDEPENDENT-REVIEW-DATA-2026-08-10.md:1556 · airi

- `ollama-num-parallel` [medium/S] foreground Ollama의 OLLAMA_NUM_PARALLEL 명시 고정
  이득: KV 캐시 크기가 결정론화되어 VRAM 변동 폭이 줄고(추정 수백 MB), num_gpu 오프로드 층수 결정도 안정된다. num-gpu-ssot와 짝으로 TTFT 재현성을 만든다.
  비용: S. start-local-ollama-proxy.ps1에 환경변수 1줄. 단 Ollama 서비스 자체의 환경변수이므로 프록시가 아니라 Ollama 프로세스에 걸어야 한다 — 현재 런처가 Ollama를 직접 띄우지 않으면(11434는 기존 서비스 재사용) 적용 지점이 다를 수 있어 확인 필요.
  근거: C:/Projects/airi-local-stack/ollama-proxy/start-memory-extractor.ps1:94-96 (격리 인스턴스만 NUM_PARALLEL=1/MAX_LOADED=1) · ollama-proxy/start-local-ollama-proxy.ps1:214-217 (foreground는 AIRI_* 변수만, OLLAMA_NUM_PARALLEL 없음) · ollama-proxy/character_state_evaluator.py:77,81,83,88-89 · https://eastondev.com/bl

- `startup-order` [high/S] 기동 순서 재배치 — LLM을 먼저 pin (예산 확보 이후에만)
  이득: LLM 오프로드 층수가 매 기동 동일해져 TTFT/tok/s가 재현된다. 부분 오프로드로 인한 +1.2~1.5초 리스크가 LLM에서 제거된다.
  비용: S. start-airi-local-stack.ps1의 블록 순서 변경 + Wait-LocalHealth 순서 조정.
  근거: C:/Projects/airi-local-stack/start-airi-local-stack.ps1:97,102,185,186,200-221 · gpt-sovits/start-local-stack.ps1:86,92,110-126 (GPT-SoVITS는 9880 기동 후 자체 warmup으로 GPU 워크스페이스까지 선점) · ollama-proxy/memory_runtime.py:235-237 (proxy startup에서 embedder 로드)

## [측정] MEMSCALE
기억·지식 계층의 코드 실체는 `C:\Projects\airi-local-stack\ollama-proxy\`에 있습니다(작업 디렉터리 `C:\Projects\airi`는 문서 전용). 검색 경로는 `airi_memory.py:183 cosine()` — 순수 파이썬 스칼라 루프이며, `retrieve()`가 `active_rows()`로 활성 행 전체를 `SELECT *`(벡터 BLOB 포함)로 올린 뒤 `score()`(1697-1699)에서 행마다 `unpack_vector`+`cosine`을 새로 계산합니다. 이 검토 PC(Ryzen 7 8700G, GPU 미사용 — 개발 PC 5600X는 Zen3라 약 1.2~1.4배 더 느릴 것으로 추정)에서 KURE-v1 실제 차원인 1024dim 실측 결과 unpack+cosine = 126.1µs/행이며, 500행 63ms / 1,000행 126ms / 2,000행 252ms / 5,000행 630ms / 10,000행 1,261ms입니다. 여기에 `SELECT *` 행 구성 비용(10,000행 74.3ms)이 더해져 `retrieve_timeout_ms=150` 예산은 **약 1,000~1,200행**(개발 PC 기준 약 800~900행)에서 무너집니다. 그런데 기존 게이트(`benchmark_memory_track.py:595` p50≤150ms PASS)는 `_RetrievalEmbedder`(526-528)가 **2차원** 벡터를 쓰기 때문에 10,000행이 21ms로 나옵니다 — 실운영 대비 약 60배 낙관이며, 게이트가 스케일 한계를 전혀 감지하지 못합니다. 지식 계층은 더 나쁩니다: `KnowledgeStore.retrieve()`가 매 쿼리 `initialize()`(393)를 호출하고 그 안의 백필 anti-join(254-256)이 FTS5 `chunk_id UNINDEXED` 때문에 **O(N²)**(EXPLAIN: `SCAN c` × `SCAN f VIRTUAL TABLE`)입니다 — 실측 200청크 5.9ms, 1,000청크 105.7ms, 3,000청크 2,560.6ms로, 반환 행이 0건이어도 전액을 지불하고 350ms 타임아웃(`ollama_proxy.py:428`)을 약 1,800청크에서 초과합니다. **기억이 조용히 사라지는 조건은 명확합니다**: 150ms 초과 시 `memory_runtime.py:399`가 빈 `RetrievalResult()`를 반환하는데, 478행은 그 빈 결과를 그대로 `extraction_watermark`와 함께 `assemble_context`(`airi_memory.py:1798`)에 넘겨 **이미 추출된 과거 턴을 히스토리에서 제거**합니다 — 기억 블록도 없고 원본 턴도 없는 완전 기억상실이 되며, 사용자에게는 아무 오류도 표시되지 않습니다. 반면 바깥 `except`(481-482)는 원본 전체 히스토리를 반환하므로 **예외가 타임아웃보다 안전한 비대칭**이 존재합니다. 게다가 `MEMORY_QUERY_RE` 매칭 질문이면 "기억에 없으면 만들지 말고 모른다고 짧게 말해"가 주입(`ollama_proxy.py:4038-4041`)되어, 타임아웃 시 AI가 **실제로 저장된 사실까지 "모른다"고 단언**합니다. 정리·보존기간 코드는 전수 확인 결과 **존재하지 않습니다** — `DELETE FROM`은 `session_turn_tail`(60턴 유지, 445), `fact_subject` 링크 정리, knowledge 청크 교체, 평가 레코드 개별 삭제뿐이며 `memory`(superseded 포함)와 `conversation_message`는 영구 증가하고 VACUUM·TTL·WAL 설정이 전무합니다. 해법의 1순위는 새 의존성이 필요 없는 numpy 벡터화(numpy 2.5.1이 sentence-transformers 의존으로 이미 설치됨 — 10,000×1024 matmul 1.203ms, 약 1,048배)와 knowledge_store의 O(N²) 제거이며, sqlite-vec은 Windows 휠이 실존하나(0.1.9) 여전히 pre-1.0 알파에 ANN 미구현(brute force)이라 numpy 대비 추가 이득이 거의 없습니다.
판정: 현 선택(파이썬 O(N) 코사인 + 150ms fail-soft + 정리 코드 없음)은 **명백히 뒤처졌습니다**. 근거는 세 가지입니다. ① 스케일 한계가 실제로는 약 1,000행(개발 PC 800~900행)인데, 이는 대화 몇 주 분량이면 도달하는 수치입니다 — 계획서의 "장기 기억" 전제 자체가 성립하지 않습니다. ② fail-soft가 안전하지 않습니다. 타임아웃은 기억 블록만 비우는 게 아니라 워터마크 프루닝을 그대로 적용해 과거 턴까지 제거하고, 여기에 "모른다고 답하라" 주입이 겹쳐 **저장된 사실을 능동적으로 부정**하게 만듭니다. 실패 확률이 DB 크기와 단조 증가하므로 "기억이 쌓일수록 기억을 잃는" 역행 구조입니다. ③ 이 한계를 지켜야 할 게이트가 2차원 임베더로 측정되어 실제 대비 60배 낙관 PASS를 내고 있어, 회귀를 영영 잡지 못합니다. 다만 아키텍처 자체(SQLite 단일 파일 + 로컬 임베딩 + 127.0.0.1)는 유지가 옳습니다 — 교체 대상은 저장소가 아니라 **스코어링 루프와 실패 계약**입니다. KM-01(지식 O(N²) 제거)·KM-02(fail-soft 계약)·KM-03(numpy)·KM-04(벤치마크 차원)를 묶어 처리하면 새 의존성 0개로 스케일 상한이 약 1,000행에서 10만 행대로 이동하며, 그 이후에야 sqlite-vec 검토 가치가 생깁니다.

- `KM-01` [high/S] knowledge_store.retrieve()의 매 쿼리 initialize() O(N²) 백필 제거
  이득: 실측(8700G, in-memory DB): 백필 anti-join 200청크 5.9ms -> 1,000청크 105.7ms -> 3,000청크 2,560.6ms. 반환 0행이어도 전액 지불. 제거 시 지식 검색 경로에서 이 비용이 통째로 사라지며(3,000청크 기준 -2.56초), 350ms 타임아웃 상한이 약 1,800청크에서 사실상 무제한으로 이동합니다.
  비용: knowledge_store.py 2줄 제거 + 스키마 마이그레이션(인덱스 1개 또는 컬럼 1개) + startup 배선 확인. 기존 테스트(test_knowledge_store.py의 v1 DB 백필 케이스 157/182행)가 initialize()를 직접 호출하므로 그쪽은 그대로 통과합니다.
  근거: knowledge_store.py:393(retrieve가 매번 initialize), knowledge_store.py:254-256(백필 anti-join), knowledge_store.py:239-241(chunk_id UNINDEXED), ollama_proxy.py:428(timeout=0.35), EXPLAIN QUERY PLAN 실측 = ('SCAN c'),('CORRELATED SCALAR SUBQUERY 1'),('SCAN f VIRTUAL TABLE INDEX 0:'); 실측 스크립트 C:\Users\ovenco

- `KM-02` [high/S] fail-soft 계약 수정 — 타임아웃 시 워터마크 프루닝을 동반 포기 + 협조적 취소
  이득: 현재는 150ms 초과 한 번이 '기억 블록 소실 + 과거 턴 소실 + 모른다고 답하라 강제'의 3중 실패로 증폭됩니다. ①만으로 과거 턴 소실이 사라지고(모델이 최소한 원본 히스토리는 봄), ②로 '저장된 사실을 부정하는' 최악의 관측 증상이 사라집니다. ③은 5,000행에서 630ms 스캔이 타임아웃 후에도 약 480ms 더 GIL을 점유하며 SSE 스트리밍/TTS 큐와 경쟁하는 문제를 제거합니다(asyncio.to_thread는 취소 불가).
  비용: memory_runtime.py 소폭 수정 + RetrievalResult 필드 1개 추가 + airi_memory.retrieve()에 deadline 파라미터 배선. 기존 test_memory_runtime.py:154(test_retrieval_timeout_is_empty_and_meta_safe)는 gate=False만 검증하므로 계약 변경에 대응하는 새 테스트가 필요합니다.
  근거: memory_runtime.py:390-399(wait_for -> except -> RetrievalResult()), memory_runtime.py:478(실패해도 extraction_watermark 적용), airi_memory.py:1798(recent = id > extracted_up_to_msg 필터), memory_runtime.py:481-482(except는 원본 payload 반환 = 비대칭), ollama_proxy.py:4026-4041(absence guard 주입문), airi_memory.py:234

- `KM-03` [high/M] numpy 벡터화 — 세션별 float32 행렬 캐시 + 단일 matmul (신규 의존성 0)
  이득: 실측(8700G, dim=1024): 파이썬 unpack+cosine 126.1µs/행 -> numpy matmul 10,000행 1.203ms(약 1,048배), 5,000행 0.517ms, 2,000행 0.162ms, 1,000행 0.134ms. 스케일 상한이 약 1,000행에서 10만 행대로 이동합니다(50,000행 6.695ms). semantic 캐시 프로브도 512엔트리 x 113µs = 최대 58ms에서 0.1ms 미만으로 떨어집니다. 메모리는 10,000행 x 1024 x 4B = 39.1MiB 시스템 RAM, VRAM 0.
  비용: numpy는 sentence-transformers(requirements.txt:4) 의존으로 **이미 설치되어 있음**(이 PC 실측 numpy 2.5.1) — 신규 설치 0. 작업은 airi_memory.py의 score()/retrieve() 스코어링 경로 재작성 + 행렬 캐시 무효화 배선 + LRU 상한. active_rows의 SELECT *도 스코어링용에는 (id, vector)만 뽑도록 좁히면 10,000행 74.3ms 구성 비용도 크게 줄어듭니다.
  근거: airi_memory.py:172-188(pack/unpack/cosine), airi_memory.py:1697-1699(score의 행별 unpack+cosine), airi_memory.py:1768(scene 전체 cosine), airi_memory.py:1688-1690(semantic 캐시 프로브), airi_memory.py:428(캐시 512 상한), requirements.txt:4(sentence-transformers=numpy 전이 의존), 실측 스크립트 C:\Users\ovencode\AppData\Loca

- `KM-04` [high/S] 검색 게이트 벤치마크의 임베딩 차원을 2 -> 1024로 교정
  이득: 현재 게이트(595행 p50<=150ms PASS)는 10,000행에서 dim=2 기준 21.0ms로 여유롭게 통과하지만, 실제 1024차원에서는 1,261ms로 8.4배 초과입니다 — 약 60배 낙관. 차원만 교정해도 스케일 한계가 게이트에 즉시 드러나고, KM-03 적용 후에는 진짜 회귀 감지기로 기능합니다.
  비용: benchmark_memory_track.py 3~4곳 수정. 시드 비용이 커지므로(10,000행 x 4KB = 39MB 쓰기) 기본 --retrieval-rows를 낮추거나 시드 시간을 리포트에서 분리해야 합니다.
  근거: benchmark_memory_track.py:523-528(_RetrievalEmbedder가 2차원), benchmark_memory_track.py:545,552(픽스처 2차원 pack_vector), benchmark_memory_track.py:594-595(p50<=150ms 게이트), https://huggingface.co/nlpai-lab/KURE-v1 (bge-m3 파인튜닝, 1024차원 / 검색 2026-08-11)

- `KM-05` [high/M] 보존기간·정리(pruning) 도입 — superseded GC + 저널 TTL + WAL + VACUUM
  이득: 스캔 대상 행 수를 유계로 만들어 KM-03 적용 후에도 상한이 무한히 밀리지 않게 합니다. WAL은 백그라운드 추출 커밋이 foreground retrieve를 블로킹해 150ms를 넘기는 경로를 제거합니다(현재 journal_mode=delete 기본, sqlite3.connect 기본 busy timeout 5초 — 락 대기가 곧 기억 소실). ensure_embedding_contract(397)가 시작 시 superseded 포함 전 행을 SELECT+SHA256하므로, GC는 기동 시간도 줄입니다.
  비용: M. 삭제 정책 결정(보존 일수)이 기획 판단을 요구하고, 매직넘버가 아니라 설정 테이블/환경변수로 빼야 합니다. WAL 전환은 _connect(airi_memory.py:261-265)에 PRAGMA 2줄. VACUUM은 유지보수 잡 1개.
  근거: DELETE FROM 전수 결과: airi_memory.py:445(session_turn_tail 60턴만), airi_memory.py:633,772,805(fact_subject 링크), knowledge_store.py:298,307-309(청크 교체), evaluation_store.py:248(평가 레코드) — memory/conversation_message 삭제 코드 없음. VACUUM/retention/TTL 문자열 매치 0건. airi_memory.py:261-265(_connect에 journal_mode/bus

- `KM-06` [medium/M] sqlite-vec 도입 (vec0 가상 테이블) — Windows 설치 가능성 확인 완료
  이득: C/SIMD 수준 brute force로 파이썬 대비 수백 배. 행렬을 프로세스 메모리에 들고 있을 필요가 없어 KM-03의 캐시 일관성 문제가 사라지고, 추출이 행을 추가해도 즉시 반영됩니다. 저장 공간도 float32 그대로라 증가 없음.
  비용: M. pip install sqlite-vec(win_amd64 휠 실존) + 스키마 추가 + 이중 쓰기(memory 테이블과 vec0 동기화) + 마이그레이션. **ANN이 없으므로 KM-03 numpy 대비 실측 이득은 크지 않을 가능성이 높습니다** — 두 방식 모두 O(N) brute force이고 상수만 다릅니다.
  근거: https://pypi.org/project/sqlite-vec/#files — sqlite_vec-0.1.9-py3-none-win_amd64.whl (292.8kB, 2026-03-31 업로드), 프리릴리스 0.1.10a4(2026-05-18) / 검색·페치 2026-08-11. https://github.com/asg017/sqlite-vec/issues/25 (ANN 인덱스 tracking issue, 미해결 = brute force only). 로컬 실측: python 3.12.10 / sqlite 3.49.1 / enab

- `KM-07` [medium/L] faiss-cpu / hnswlib — 검토 결과 비권장
  이득: 수백만 벡터 규모에서만 numpy brute force를 유의미하게 앞섭니다. 이 프로젝트의 현실적 상한(KM-05 적용 시 수만 행)에서는 numpy matmul이 10,000행 1.203ms / 50,000행 6.695ms로 이미 예산의 1~4%에 불과해 ANN의 이득이 측정 한계에 묻힙니다.
  비용: faiss-cpu는 설치는 쉽습니다(1.15.0 / 2026-08-03, win_amd64 휠 제공, Python 3.10~3.14). 그러나 인덱스 파일 별도 관리 + 삭제/갱신 시 재빌드 + SQLite와의 정합성 유지라는 상시 유지보수가 붙습니다. hnswlib은 PyPI에 Windows 휠이 없어 pip install 시 MSVC 빌드가 필요하며, 'Microsoft Visual C++ 14.0 or greater is required', "cannot open include file: 'crtdbg.h'" 류 실패가 다수 보고됩니다 — 1인 운영 환경에 부적합합니다.
  근거: https://pypi.org/project/faiss-cpu/ (1.15.0, 2026-08-03, win_amd64 휠 제공, Python 3.10-3.14 / 페치 2026-08-11). https://github.com/nmslib/hnswlib/issues/469 및 /issues/479 (Windows MSVC 빌드 실패 — crtdbg.h, VC++ 14.0 요구). numpy 실측 비교는 KM-03 근거 참조. 주의: 인용된 faiss/hnswlib 벤치마크는 3060 Ti 8GB 환경 측정이 아니며, 두 라이브러리

- `KM-08` [high/M] journal_recall의 O(N) 파이썬 재토큰화를 FTS5로 대체
  이득: 실측(8700G): _journal_tokens = 0.060ms/메시지(352자 한국어 기준). 미추출 100건 6.0ms / 500건 30.2ms / 1,000건 60.4ms / 4,096건 247.4ms — 코사인과 **같은 150ms 예산을 공유**하므로 미추출 저널이 약 2,500건 쌓이면 코사인이 0이어도 단독으로 타임아웃합니다. FTS5 전환 시 후보 수십 건으로 축소되어 사실상 상수 시간이 됩니다.
  비용: S~M. conversation_message용 FTS5 외부 콘텐츠 테이블 + 트리거 또는 명시적 동기화. 한국어는 FTS5 기본 토크나이저가 CJK를 온전히 분절하지 못하므로, knowledge_store가 이미 쓰는 방식(_tokens로 정규화한 search_text 컬럼을 별도 인덱싱, knowledge_store.py:64-67)을 그대로 재사용하면 됩니다 — 검증된 한국어 패턴이 사내에 이미 있습니다.
  근거: airi_memory.py:27(JOURNAL_RECALL_WINDOW_MESSAGES=4096), airi_memory.py:940-958(윈도 4096건 SELECT), airi_memory.py:970-977(행마다 _journal_tokens 재계산), airi_memory.py:915-931(_journal_tokens 정규식), knowledge_store.py:44-67(재사용 가능한 한국어 정규화 패턴). 실측 스크립트 C:\Users\ovencode\AppData\Local\Temp\claude\C--Projects

- `KM-09` [high/S] knowledge_store의 embedding_json(TEXT) -> float32 BLOB + 벡터화
  이득: 실측(8700G, dim=1024): 현재 코드 형태(json.loads + 행별 쿼리 norm 재계산) 546.4µs/청크 -> 500청크 273ms / 1,000청크 546ms / 5,000청크 2,732ms. 350ms 타임아웃은 약 640청크에서 붕괴합니다. json.loads만도 354.0µs/청크로 struct.unpack(13.0µs) 대비 27배. 저장 공간도 청크당 20,771B -> 4,096B(5.1배 감소). numpy 전환 시 KM-03과 동일한 밀리초 단위로 내려갑니다.
  비용: S~M. 스키마 컬럼 추가 + 마이그레이션(기존 JSON 재파싱 1회) + reindex_missing(487-500) 경로 수정. numpy는 이미 설치되어 있어 신규 의존성 0.
  근거: knowledge_store.py:236(embedding_json TEXT), knowledge_store.py:452-461(전체 스캔 + json.loads + 파이썬 코사인), knowledge_store.py:456(쿼리 norm 행별 재계산), knowledge_store.py:449(렉시컬 히트 시 스킵), ollama_proxy.py:396,403(allow_semantic 기본 False + '스레드 타임아웃은 CUDA encode를 취소 못한다' 주석 399-402). 실측 스크립트 bench_mem.py

- `KM-10` [low/S] 쿼리 임베딩(KURE-v1 encode)을 150ms 예산 밖으로 분리
  이득: 현재 150ms 예산에는 (a) 쿼리 임베딩 + (b) O(N) 코사인 + (c) journal_recall이 모두 들어 있어, 어느 하나만 튀어도 전체가 실패하고 KM-02의 3중 소실로 이어집니다. 분리하면 실패 원인이 구분되고 각 구간에 맞는 예산을 줄 수 있습니다. GPU 경합 관점에서는 KURE-v1(bge-m3 = XLM-R large, 568M 파라미터)이 fp16 기준 약 1.1~1.2GB의 가중치를 8GB VRAM 예산에서 STT/LLM/TTS와 나눠 써야 하므로, CPU 고정 시 VRAM을 그만큼 되돌려 받습니다.
  비용: S. memory_runtime/airi_memory 시그니처 변경 + _query_cache(airi_memory.py:1658-1667) 이동. CPU 고정 시 인코딩 지연이 늘어나므로 실측 후 결정해야 합니다.
  근거: airi_memory.py:1657-1668(retrieve 내부에서 쿼리 encode), memory_runtime.py:390-393(그 전체가 150ms wait_for 안), memory_runtime.py:156-174(SentenceTransformerEmbedder, device 옵션), memory_runtime.py:103-105(AIRI_MEMORY_EMBED_DEVICE), ollama_proxy.py:399-402(지식 경로에서는 같은 위험 때문에 semantic을 기본 off로 했다는 주석 — 기억 경로는 미


## [조사] TTS (BLOCKED 2건 제외)
결론부터 말씀드리면, **이 축의 병목은 TTS 엔진이 아니라 재생 계약과 기동 계약입니다.** warm first byte 613.3ms는 8GB 예산에서 이미 경쟁력 있는 값이고, 2026년 8월 현재 후보를 전수 조사해도 한국어+제로샷 클로닝+3060 Ti 8GB 동시 상주 조건을 모두 만족하면서 613ms를 유의미하게 깎아줄 대체재는 없습니다. cold 6,897ms의 정체를 코드로 추적한 결과 두 개의 구조적 원인을 특정했습니다 — (1) `GPT_SoVITS/text/cleaner.py:36`이 언어 모듈을 **첫 요청 시점에 lazy import**하고 `GPT_SoVITS/text/korean.py:289`의 `_g2p = G2p()`(g2pk2+MeCab 사전)가 그 import 시점에 실행되어 첫 한국어 요청이 사전 로드를 전액 부담하며, (2) 프록시가 `@app.on_event("startup")`에서 워밍업을 **백그라운드 스레드**로 돌리는데(openai_compatible_proxy.py:177) uvicorn은 포트를 즉시 열기 때문에, 워밍업이 `_fetch_wav_from_backend`에서 TTS_LOCK을 잡고 있는 동안 도착한 첫 실사용 요청이 락 뒤에 줄을 섭니다. 즉 6.9초의 상당 부분은 모델 로드가 아니라 **자기 워밍업과의 경합일 가능성이 높고, 이를 판별할 `lock_wait_ms` 텔레메트리가 이미 :254에 배선되어 있습니다** — 엔진 교체 전에 이 한 숫자를 먼저 읽으십시오. 클라이언트 쪽은 명확합니다: api_v2.py:422-429가 첫 청크에 WAV 헤더를 흘린 뒤 **raw int16 PCM @ 32kHz**(TTS.py:361)로 전환해 정직하게 스트리밍하는데, 클라이언트가 `decodeAudioData(전체 ArrayBuffer)`(patch:4189)로 받아 이득을 전량 폐기합니다. 여기서 MediaSource는 함정입니다 — Chromium MSE는 raw PCM/WAV/ogg를 재생하지 못하므로 **AudioWorklet + 링 버퍼가 유일한 정답 경로**이며, `media_type="raw"`가 이미 서버에 구현돼 있어(api_v2.py:276) 서버 변경 없이 전환 가능합니다. `prompt_lang="ja"`는 흔한 오해와 달리 **버그가 아닙니다** — api_v2.py:31이 prompt_lang을 "레퍼런스 오디오의 언어"로 정의하므로 일본어 레퍼런스에는 "ja"가 정답이고, 대신 지불하는 비용은 속도가 아니라 교차언어 클로닝에서 오는 한국어 억양·운율 열화입니다. 마지막으로 TTS_LOCK은 GPT-SoVITS가 `self.prompt_cache`(TTS.py:452)를 단일 인스턴스에 공유 변경하는 구조라 **제거가 아니라 유지가 옳으며**, 빠진 것은 acquire 타임아웃뿐입니다(:224 무기한 acquire).
판정: **현 선택(GPT-SoVITS v2ProPlus 유지)은 여전히 최선입니다. 다만 그것을 감싼 두 개의 계약이 명백히 뒤처졌습니다.** ① 엔진 판정: 2026년 8월 기준 한국어+제로샷 클로닝+8GB 동시 상주를 모두 만족하는 대체재는 Chatterbox Multilingual V3와 Fun-CosyVoice 3.0 둘뿐이며, 어느 쪽도 3060 Ti 8GB 실측 근거가 없고 VRAM 축 판정상 현재 예산은 이미 적자라 도입 자체가 불가합니다. warm 613.3ms를 이기지 못할 교체에 XL 비용을 쓰는 것은 손해입니다. ② **재생 계약은 명백히 뒤처졌습니다** — 서버는 api_v2.py:422-429에서 정직하게 청크를 흘리는데 클라이언트가 patch:4189에서 전량 버퍼링해 이득을 0으로 만듭니다. 이것이 남은 최대 단일 레버(약 -580ms, 문장 길이에 비례 증가)이며 엔진을 무엇으로 바꾸든 고쳐지지 않습니다. ③ **기동 계약도 뒤처졌습니다** — cold 6,897ms는 '모델이 느려서'가 아니라 lazy G2P import(cleaner.py:36 → korean.py:289)와 백그라운드 워밍업과의 락 경합(:177 spawn, :138 락 보유, :224 무기한 acquire)이라는 자기 유발 원인이 유력하며, S 등급 작업으로 최대 -6.3초입니다. ④ `prompt_lang="ja"`에 대한 통념은 **정정이 필요합니다** — api_v2.py:31 정의상 올바른 설정이며 속도 손해도 없습니다(레퍼런스 특징은 캐시됨). 지불 중인 비용은 교차언어 클로닝의 한국어 억양 열화뿐이고, 해법은 설정 변경이 아니라 한국어 레퍼런스 확보(T-05)입니다. ⑤ TTS_LOCK은 **해체 대상이 아닙니다** — TTS.py:452의 공유 prompt_cache 때문에 락은 정당하며, 결함은 타임아웃 부재 하나뿐입니다. **권고 실행 순서는 고정입니다: T-02(cold, S) → T-03(락 타임아웃, S) → T-01(스트리밍 재생, L) → T-05(한국어 레퍼런스, M).** 엔진 교체(T-06/T-07)는 이 넷을 끝내고 KURE fp16으로 VRAM을 확보한 뒤에야 검토 가치가 생깁니다. 착수 전 단 하나의 실측을 권합니다 — openai_compatible_proxy.py:254가 이미 남기는 `lock_wait_ms`를 cold 샘플에서 읽으십시오. 이 숫자가 T-02의 절감폭을 확정합니다.

- `T-01` [VIABLE] 클라이언트 재생 계약 교체 — raw PCM + AudioWorklet 링 버퍼 (conf=high, eff=L, vram=0 (클라이언트·직렬화 계층 변경, GPU 영향 없음), ko=yes)
  변경: 프록시가 백엔드에 `media_type="raw"`를 요청하고(현재 "wav", openai_compatible_proxy.py:118), 클라이언트는 `decodeAudioData(전체 ArrayBuffer)`(patch:4189) 대신 fetch ReadableStream을 읽어 Int16→Float32 변환 후 AudioWorklet 링 버퍼에 밀어넣습니다. 32kHz 모노 고정이므로 AudioContext sampleRate와 불일치 시
  이득: warm 턴에서 첫 음절이 TTS 완료(1,192.9ms) 대신 첫 청크(613.3ms 부근)에 나므로 약 -580ms. 문장이 길어질수록 이득이 선형 증가하며, 계획서 P50 ≤2초 달성분 중 단일 최대 레버입니다. 추가로 barge-in 시 링 버퍼 flush만으로 즉시 중단이 가능해져 200~500ms 목표의 전제 조건이 됩니다.
  근거: api_v2.py:422-429 (첫 청크 wave_header_chunk 후 media_type을 raw로 전환), api_v2.py:276 pack_raw, GPT_SoVITS/TTS_infer_pack/TTS.py:361 sampling_rate=32000, airi_docs/patches/AIRI-v0.11.3-local-runtime-source.patch:4189 decodeAudioData, 동 patch grep 결과 AudioW
  검증: 핵심 주장은 코드로 확인됩니다. ① 백엔드는 이미 진짜 스트리밍입니다 — C:\Projects\airi\external\GPT-SoVITS\api_v2.py:422-429에서 첫 청크에 wave_header_chunk를 내보낸 뒤 media_type을 raw로 전환하므로, 프록시가 받는 첫 바이트(warm 613.3ms, airi_docs/AIRI-LATENCY-ACCEPTANCE-2026-08-09.md:12)는 실제 오디오 생성 시점입니다.

- `T-02` [DOWNGRADE] cold start 제거 — 워밍업 완료 전 요청 admission 차단 + 한국어 모듈 선(先)import (conf=high, eff=S, vram=0, ko=yes)
  변경: ① 런처의 준비 완료 판정을 `Wait-Port 8880`(start-local-stack.ps1:103)에서 `/health`의 `immediate_response_cache.ready == total` 폴링으로 교체합니다. ② 프록시 워밍업이 끝나기 전 도착한 합성 요청은 락 뒤에 줄세우지 말고 503 또는 대기 이벤트로 명시 처리합니다. ③ 백엔드 기동 스크립트에서 `from text import korean`을 미리 import해 g2p
  이득: 첫 턴에서 최대 약 -6,300ms(6,897.5ms → warm 613.3ms 수준). 실제 음성 턴 기준 본답변 재생 시작 +8,968ms의 가장 큰 단일 기여분을 제거합니다. 이후 턴에는 영향 없음(프로세스 상주 중 재-cold 없음).
  근거: gpt-sovits/openai_compatible_proxy.py:174-180 (startup 워밍업을 daemon 스레드로 spawn), :138 `_fetch_wav_from_backend`가 TTS_LOCK 보유, :58 워밍 대상 2문구, :224 무기한 acquire, :254 lock_wait_ms 이미 emit / gpt-sovits/start-local-stack.ps1:103-104 포트만 확인 후 통과, :106 `$sta
  검증: 진단한 갭 자체는 실재합니다 — 프록시 워밍업이 daemon 스레드로 spawn되고(gpt-sovits/openai_compatible_proxy.py:174-180) 그 워밍업이 TTS_LOCK을 보유하며(:138), 런처는 포트만 확인하고 통과합니다(gpt-sovits/start-local-stack.ps1:103-104). korean 모듈 lazy import(GPT_SoVITS/text/cleaner.py:37 → text/korean

- `T-03` [DOWNGRADE] TTS_LOCK starvation 제거 — acquire 타임아웃 + 큐 깊이 제한 (락 자체는 유지) (conf=high, eff=S, vram=0, ko=yes)
  변경: `TTS_LOCK.acquire()`(openai_compatible_proxy.py:224)를 `acquire(timeout=N)`으로 바꾸고 초과 시 503을 반환하며, 대기 큐 깊이를 제한합니다. 락을 없애지는 않습니다.
  이득: 막힌 1건이 uvicorn threadpool 전체를 60초(BACKEND_TIMEOUT_SECONDS, :44) 동안 잠그는 starvation을 제거합니다. 지연 중앙값 개선이 아니라 P95 꼬리와 행(hang) 복구가 목적입니다.
  근거: gpt-sovits/openai_compatible_proxy.py:55 TTS_LOCK, :224 타임아웃 없는 acquire, :44 BACKEND_TIMEOUT_SECONDS=60, :186-231 _BackendStream / GPT_SoVITS/TTS_infer_pack/TTS.py:452 self.prompt_cache, :1132·1157 요청별 mutate
  검증: 코드 사실은 맞습니다(gpt-sovits/openai_compatible_proxy.py:55 TTS_LOCK, :224 타임아웃 없는 acquire, :44 BACKEND_TIMEOUT_SECONDS=60). 그러나 '막힌 1건이 uvicorn threadpool 전체를 60초 잠근다'는 틀렸습니다. :330 `def speech(...)`는 async가 아니라 sync이므로 Starlette가 anyio threadpool(기본 40 토큰)

- `T-04` [VIABLE] 엔진 유지 판정 — GPT-SoVITS v2ProPlus가 2026년 8월 현재도 이 제약에서 최선 (conf=high, eff=S, vram=현행 유지 — GPT-SoVITS 단독 5,092MiB(VRAM 축 실측 인용), ko=yes)
  변경: 엔진을 교체하지 않고 T-01~T-03에 자원을 집중합니다. v2ProPlus는 GitHub 릴리스 기준 2025-06-06 `20250606v2pro` 이후 신규 릴리스가 없고, 로컬 클론은 2026-07-22 커밋으로 이미 최신 계열입니다.
  이득: 교체 리스크 0. 한국어 음질·persona 음성 동일성·이미 구축된 Windows MeCab/g2pk2 어댑터·레퍼런스 캐시가 모두 보존됩니다. warm 613.3ms는 후보군 대비 열세가 아닙니다.
  근거: https://api.github.com/repos/RVC-Boss/GPT-SoVITS/releases (2026-08-11 조회 — 최신 릴리스 20250606v2pro, 2025-06-06) / 로컬 클론 `git log -1` = d523079 2026-07-22 / external/GPT-SoVITS/README.md:354-361 V2Pro Release Notes("surpassing v4's performance, with v2's
  검증: 인용을 전수 재확인했고 모두 실재합니다. GitHub 릴리스 API 조회(2026-08-11) 결과 최신 태그는 20250606v2pro(2025-06-06)이며 그 위로 신규 릴리스가 없습니다(https://api.github.com/repos/RVC-Boss/GPT-SoVITS/releases). 로컬 클론 `git log -1` = d523079, 2026-07-22 확인. README 인용도 원문 일치 — C:\Projects\airi\

- `T-05` [VIABLE] 한국어 레퍼런스 음성으로 교체 — prompt_lang="ja"는 버그가 아니라 교차언어 비용 (conf=high, eff=M, vram=0, ko=yes)
  변경: 현재 `prompt_lang="ja"` + 일본어 prompt_text(openai_compatible_proxy.py:35-39)는 **올바른 설정**입니다. api_v2.py:31이 prompt_lang을 "레퍼런스 오디오의 언어"로 정의하기 때문입니다. 개선안은 설정 변경이 아니라 동일 화자 톤의 **한국어 레퍼런스 클립을 새로 확보**해 ref_audio+prompt_text+prompt_lang을 ko로 정렬하는 것입니다.
  이득: 속도 이득은 사실상 없습니다(레퍼런스 특징은 TTS.py:1132·1157에서 캐시되어 warm 경로에 미포함). 이득은 전량 **품질** — 교차언어 클로닝에서 오는 일본어 억양·운율 전이 제거. Resemble의 Chatterbox 문서도 같은 현상을 명시적으로 경고합니다("reference clip must match the language tag, otherwise outputs inherit the reference language's
  근거: external/GPT-SoVITS/api_v2.py:31 `"prompt_lang": "" # str.(required) language of the prompt text for the reference audio` / gpt-sovits/openai_compatible_proxy.py:35-39 PROMPT_LANG="ja"+일본어 prompt_text, :111-113 text_lang="ko" / GPT_SoVITS/TTS_infer_p
  검증: '버그가 아니다'라는 진단은 레포 자체 기록으로 확증됩니다. api_v2.py:31 `"prompt_lang": "" # str.(required) language of the prompt text for the reference audio` 원문 일치이고, 더 결정적으로 airi_docs/AIRI-HANDOFF-2026-08-06.md:30이 '참조 음성 airi-reference.wav는 한국어가 아니라 일본어다 ... 기존 prompt_l

- `T-08` [DOWNGRADE] 보조 후보 — Supertonic을 CPU ONNX ack 합성기로 병행 (VRAM 0) (conf=medium, eff=M, vram=0 (CPU ONNX). 단 CPU는 STT/LLM과 경합, ko=yes)
  변경: Supertone(한국 기업)의 온디바이스 TTS. 31개 언어에 Korean 포함, 99M 파라미터, ONNX Runtime, GPU 불필요. 메인 엔진 교체가 아니라 '응!'·'바로 찾아볼게' 같은 즉답 ack와 워밍업 중 폴백을 **CPU에서** 담당시키는 용도입니다.
  이득: VRAM을 1MiB도 쓰지 않으면서 첫 반응 P50 ≤1.5초 목표에 기여할 수 있고, GPT-SoVITS 워밍업/락 대기 구간의 무음을 메웁니다. ONNX 세션은 상호 독립이라 TTS_LOCK 경합에서 자유롭습니다.
  근거: https://github.com/supertone-inc/supertonic 및 raw README (2026-08-11 조회 — 31개 언어에 Korean(ko), 약 99M ONNX, 코드 MIT·가중치 OpenRAIL-M, 프리셋 6종, 공개 클로닝 파이프라인 없음, 스트리밍 언급 없음, RTF 0.3x는 Onyx Boox Go 6 측정) / gpt-sovits/openai_compatible_proxy.py:58-61·122-127 기
  검증: 제약 통과 여부는 대체로 깨끗합니다 — https://raw.githubusercontent.com/supertone-inc/supertonic/main/README.md (2026-08-11 조회): 31개 언어에 Korean(ko) 포함, 약 99M ONNX, 코드 MIT·가중치 OpenRAIL-M(상업 사용 허용, 사용 기반 제한 부가), CPU 전용이므로 VRAM 0, Windows ONNX Runtime 정상. 문제는 이득이 사실상 0

- `T-09` [VIABLE] 탈락 — Fish Audio S2 Pro (라이선스 + 하드웨어 격차) (conf=medium, eff=S, vram=해당 없음 (도입 비권고), ko=partial)
  변경: fish-speech 계열의 2026년 최신 모델. 80개 이상 언어(한국어 Tier 2), 스트리밍 성능 우수(Continuous Batching, Paged KV Cache, CUDA Graph, RadixAttention prefix caching).
  이득: 기술적으로는 가장 앞선 스트리밍 스택이며 TTFA 약 100ms, RTF 0.195를 주장합니다.
  근거: https://github.com/fishaudio/fish-speech (2026-08-11 조회 — 최신 Fish Audio S2 Pro, 80+ 언어·Korean은 Tier 2, RTF 0.195·TTFA 약 100ms는 단일 H200 기준, FISH AUDIO RESEARCH LICENSE)
  검증: '도입 비권고'라는 결론이 정확하며, 근거를 원문으로 확인했습니다. 라이선스가 결정적입니다 — https://raw.githubusercontent.com/fishaudio/fish-speech/main/LICENSE 실측: 허용 범위가 'use, reproduce, distribute, and create Derivative Works of ... the Fish Audio Materials for any Research or Non-Comm

- `T-10` [VIABLE] 탈락군 정리 — Kokoro / MeloTTS / MOSS-TTS-Nano / Qwen3-TTS (conf=high, eff=S, vram=해당 없음, ko=no)
  변경: 조사 대상 중 명확히 탈락한 후보들을 사유와 함께 고정해, 다음 세션이 같은 조사를 반복하지 않게 합니다.
  이득: 재조사 비용 제거. 특히 Kokoro·Qwen3-TTS는 매력적인 벤치마크 때문에 반복적으로 재검토 대상에 오릅니다.
  근거: **Kokoro-82M — 한국어 미지원으로 탈락**: https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md (2026-08-11 조회 — 지원 9종은 미국/영국 영어·일본어·중국어·스페인어·프랑스어·힌디어·이탈리아어·브라질 포르투갈어이며 Korean 없음). **MeloTTS — 한국어 O·MIT·CPU 실시간이나 음성 클로닝 부재로 persona 불가**: https://github.
  검증: 4건 모두 인용대로 실재하며 탈락 사유가 성립합니다. ① Kokoro-82M: https://huggingface.co/hexgrad/Kokoro-82M/raw/main/VOICES.md (2026-08-11 조회) 지원 목록이 American English·British English·Japanese·Mandarin Chinese·Spanish·French·Hindi·Italian·Brazilian Portuguese 9종이고 Korean이


## [조사] STT (BLOCKED 2건 제외)
결론부터 말씀드리면, 이 축의 996.5ms는 "faster-whisper가 느려서"가 아니라 **측정 없이 내려진 두 개의 설정 결정 + 발화 길이와 무관하게 고정된 30초 인코더 창** 때문입니다. 레포 자체 기록이 이를 증명합니다 — 기준선은 `small`/CUDA/float16/beam1에서 warm 291ms였고(airi_docs/AIRI-LOCAL-STACK-REVIEW-2026-08-07.md:27), 이후 모델을 large-v3-turbo로, beam을 1→3으로 올린 뒤 996.5ms가 됐습니다(`git show 1d8a720:stt/openai_stt_server.py` 101행 `BEAM_SIZE = 1` → 현재 stt/openai_stt_server.py:115 `BEAM_SIZE = 3`). beam 상향의 근거는 airi_docs/AIRI-LATENCY-ACCEPTANCE-2026-08-09.md:19 "실제 발화 한 건에서 짧은 의미 변경 오인식이 확인된 뒤"가 전부이며, 정확도 개선폭 수치는 존재하지 않습니다. 다만 기존 독립 리뷰(ALIGN-08)가 회수분 700ms를 beam에 귀속시킨 것은 **정정이 필요합니다** — faster-whisper 1.2.1 소스 실측 결과 temperature=0에서 `best_of`는 무시되고 beam은 4층 디코더에만 3배로 걸리는 반면(transcribe.py:1431-1443), large-v3-turbo의 인코더는 large-v3와 동일한 32층·635M이고 whisper는 **항상 30초 멜로 패딩**하므로(feature_extractor.py:15-17, transcribe.py:916) 2~4초 발화에서도 인코더 비용을 전액 지불합니다. 즉 지배적 항목은 beam이 아니라 인코더이며, 이 때문에 최대 단일 레버는 `transcribe(chunk_length=...)`로 창을 발화 길이에 맞춰 줄이는 것입니다(faster-whisper 1.2.1이 시퀀셜 경로에서 정식 지원 — transcribe.py:785, 916 / feature_extractor.py:203-205). 2026년 8월 기준 대안 조사 결과 **한국어 지원이라는 1차 필터에서 대부분이 탈락**했습니다 — NVIDIA Parakeet-TDT-0.6b-v3와 Canary-1b-v2는 25개 유럽어만 지원해 한국어가 아예 없고, Moonshine·Distil-Whisper·Kyutai STT도 한국어가 없습니다. 한국어를 공식 지원하는 실질 후보는 Voxtral-Mini-4B-Realtime-2602(2026-02, 네이티브 스트리밍 80ms~2.4s이나 BF16에서 16GB VRAM 요구 → 8GB 예산에서 탈락), SenseVoice-Small(ko 지원·비자기회귀·초고속이나 한국어 벤치마크가 공개돼 있지 않음), sherpa-onnx 한국어 스트리밍 zipformer(KsponSpeech CER 9.91/10.72% — 최종 전사로 쓰기엔 과다) 셋뿐입니다. 따라서 **모델을 바꾸는 게 아니라 현 스택의 설정·창·VAD를 고치는 것이 정답**이며, 이것만으로 996.5ms → 350~550ms가 산술적으로 도달 가능합니다. 추가로, 목표에 잡히지 않은 숨은 비용이 있습니다 — 클라이언트 종료 감지 450ms(패치된 상수, packages/stage-ui/src/stores/ai/models/vad.ts:23이 스톡 1200ms)는 996.5ms 바깥이라 실제 T0→STT확정은 약 1,450ms입니다. 마지막으로 이중 디코드(LAT-09)는 실존이 확인되나(openai_stt_server.py:371-391 analyze_audio가 만든 `decoded`를 버리고 :394-406 load_audio_samples가 같은 파일을 재디코드) 제가 이 검토 PC(Ryzen 7 8700G, PyAV 18.0.0)에서 직접 측정한 비용은 3초 WAV 7.5ms / 3초 webm-opus 9.5ms로 **약 10ms에 불과**합니다 — 무위험이라 고치는 게 맞지만 여기에 기대를 걸면 안 됩니다.
판정: **절반은 최선, 절반은 뒤처졌습니다 — 그리고 뒤처진 쪽이 지연의 대부분을 차지합니다.**

① **엔진 선택(faster-whisper/CTranslate2 + CUDA + Windows 네이티브)은 2026년 8월 기준 여전히 최선입니다.** 한국어라는 1차 필터가 대안을 거의 전멸시켰습니다 — NVIDIA Parakeet-TDT-0.6b-v3와 Canary-1b-v2는 25개 유럽어뿐이라 한국어가 없고, Moonshine·Distil-Whisper·Kyutai STT도 없습니다. 한국어를 공식 지원하는 유일한 상급 대안 Voxtral-Mini-4B-Realtime-2602(2026-02)는 BF16 16GB를 요구해 8GB 예산에서 탈락합니다. 교체할 곳이 없습니다.

② **설정은 명백히 뒤처졌습니다.** `BEAM_SIZE = 3`(stt/openai_stt_server.py:115)은 실제 발화 **1건**의 오인식을 근거로 올렸고(AIRI-LATENCY-ACCEPTANCE-2026-08-09.md:19), 개선폭 수치가 존재하지 않으며, 같은 문서가 "실제 마이크 재검증은 새 입력이 필요하다"고 스스로 미완결을 기록합니다. 기준선 `BEAM_SIZE = 1`은 `git show 1d8a720`로 확인됩니다.

③ **가장 큰 낭비는 아무도 지적하지 않은 곳에 있습니다 — 30초 고정 인코더 창.** large-v3-turbo는 디코더만 32→4층으로 줄인 모델이고 인코더는 large-v3와 동일한 32층입니다. whisper는 발화가 2초든 30초든 항상 3000 멜 프레임을 인코딩하므로, 2~4초 대화 턴에서 인코더 비용의 85~90%가 무음 패딩에 지출됩니다. faster-whisper 1.2.1은 `chunk_length`로 이 창을 줄이는 것을 시퀀셜 경로에서 정식 지원합니다(transcribe.py:785,916 / feature_extractor.py:203-205).

④ **기존 독립 리뷰 ALIGN-08의 "beam 되돌림 −700ms"는 정정이 필요합니다.** 291ms(small/beam1) → 996.5ms(turbo/beam3)의 증가분 705ms는 beam과 모델 두 변경의 합인데, faster-whisper 소스상 beam은 4층 디코더에만 작용하고(temperature=0에서 best_of는 무시, transcribe.py:1431-1443) 인코더는 불변이므로 **지배분은 small→large 인코더 교체(약 7배 FLOPs)**입니다. beam 1로 되돌려도 −700ms는 나오지 않습니다. 이 오귀속을 그대로 두면 beam만 되돌린 뒤 "목표 미달"로 잘못 결론 내리게 됩니다.

⑤ **예산 정의 자체에 구멍이 있습니다.** 996.5ms는 HTTP `/v1/audio/transcriptions` 구간이고, 실제 사용자가 체감하는 발화 종료 감지 450ms(클라이언트 Silero VAD, 스톡 1200ms를 바이너리 패치)는 이 숫자 바깥입니다. 실제 T0→STT확정은 약 1,450ms이며, 이것만으로 P50 2초 예산의 72%를 소진합니다.

⑥ **이중 디코드(LAT-09)는 실존하나 크기가 과대평가돼 있었습니다.** 제가 이 검토 PC에서 직접 측정한 결과 3초 WAV 7.5ms / webm-opus 9.5ms — 996.5ms의 1%입니다. 무위험이므로 고치되, 병목으로 취급하면 안 됩니다.

**권고 순서(고정)**: STT-00(4-way 계측) → STT-01(chunk_length) + STT-02(beam 1) + STT-03(without_timestamps) 일괄 → STT-05(VAD 450→300) → STT-07(SSoT) → STT-04(이중 디코드). 여기까지가 전부 S~M이고 새 의존성 0개이며, 산술적으로 996.5ms → 350~550ms + 종단 추가 −150ms가 도달 가능 범위입니다. **STT-06(스트리밍)과 STT-08(SenseVoice)은 위 조합이 목표에 미달할 때만 착수하십시오** — 각각 XL 비용과 한국어 미검증 리스크를 안고 있으며, 지금 착수하면 1인 운영 유지보수가 감당 범위를 넘습니다.

**미해결 — 확인 필요**: (a) 996.5ms의 인코더/디코더/VAD 분해(서버가 analysis_ms·inference_ms를 이미 응답에 싣는데 로그가 남아 있지 않음), (b) 3060 Ti에서 large-v3-turbo int8_float16의 실제 VRAM(레포에 수치 없음 — small 회귀 시 −700~1,000MB 추정은 검증되지 않았습니다), (c) chunk_length 축소가 한국어 CER에 미치는 영향, (d) SenseVoice-Small의 한국어 CER(공개 벤치마크 부재).

- `STT-00` [VIABLE] 먼저 계측: 4-way A/B 하네스 (모델 × beam × chunk_length) (conf=high, eff=S, vram=변화 없음, ko=yes)
  변경: stt/ 아래에 읽기전용 벤치 스크립트를 두고, 표준 한국어 문장 7종(계획서 §9)에 대해 ①small/beam1 ②turbo/beam1 ③turbo/beam3(현행) ④turbo/beam1+chunk_length=10 의 P50/P95 지연과 CER을 1회 측정해 표로 남깁니다. 서버가 이미 analysis_ms·inference_ms를 응답에 싣고 있으므로(openai_stt_server.py:933-934) 인코더/디코더 분해도 함께 기
  이득: 절감치는 아니지만 이 축의 모든 후속 판단 전제. 현재 996.5ms의 인코더/디코더/VAD 분해가 레포 어디에도 없습니다(stt-server.out.log 부재 확인).
  근거: airi_docs/AIRI-LATENCY-ACCEPTANCE-2026-08-09.md:19 (beam 상향 사유가 일화 1건), airi_docs/AIRI-INDEPENDENT-REVIEW-2026-08-10.md:400,592-610 (ALIGN-08 CONFIRMED), stt/openai_stt_server.py:933-934
  검증: 전제 3개 모두 실측 확인. (1) STT 벤치 하네스 부재 — `find` 결과 benchmark 스크립트는 gpt-sovits/·faster-qwen3-tts/·ollama-proxy/에만 있고 stt/에는 0건, stt/*.log도 부재. (2) 계측 훅 존재 — stt/openai_stt_server.py:933-934 `analysis_ms`/`inference_ms`가 latency 이벤트에 실림. (3) ALIGN-08 CONFIR

- `STT-02` [DOWNGRADE] beam 3 → 1 되돌리기 (고유명사는 이미 hotwords + 사후 정규화가 담당) (conf=high, eff=S, vram=무시 가능(빔 상태 메모리 소폭 감소), ko=yes)
  변경: stt/openai_stt_server.py:115 `BEAM_SIZE = 3` → 1. beam으로 지키려던 고유명사는 이미 두 겹으로 방어됩니다 — (a) build_hotwords()(:150-155)가 proper_nouns.json의 canonical+context를 매 디코드 프롬프트에 주입하고(faster_whisper/transcribe.py:1542-1550에서 sot_prev 뒤에 실제로 삽입됨을 소스로 확인), (b) nor
  이득: −50~150ms 추정. beam은 4층 디코더에만 3배로 걸리고 인코더는 불변이므로 ALIGN-08이 말한 −700ms보다 **작을 것**입니다(그 700ms의 상당 부분은 small→turbo 모델 교체분).
  근거: stt/openai_stt_server.py:115-116,150-155,250-,561,566,860-894 / proper_nouns.json:1-31 / faster_whisper/transcribe.py:1431-1443(temperature=0이면 best_of 미사용),1542-1550(hotwords 실제 삽입) / airi_docs/AIRI-LATENCY-ACCEPTANCE-2026-08-09.md:19
  검증: 코드 사실관계는 대부분 맞습니다 — stt/openai_stt_server.py:115-116 `BEAM_SIZE = 3`/`RECOVERY_BEAM_SIZE = 3`, :561,565-566에서 `beam_size`/`best_of`로 전달, temperature=0이라 best_of는 무시됨(faster-whisper transcribe.py 확인: temperature>0일 때만 num_hypotheses=best_of 사용), hotwo

- `STT-03` [DOWNGRADE] without_timestamps=True — 디코딩 토큰 절반 (conf=medium, eff=S, vram=변화 없음, ko=yes)
  변경: transcription_options에 `without_timestamps: True` 추가. 현재 시퀀셜 transcribe의 기본값은 False라(faster_whisper/transcribe.py:776) 세그먼트마다 타임스탬프 토큰이 텍스트와 번갈아 생성돼 디코드 토큰 수가 약 2배입니다.
  이득: 디코더 구간 −30~50% 추정. STT-02와 곱셈이 아니라 덧셈으로 작용합니다. 절대값은 STT-00 필요.
  근거: faster_whisper/transcribe.py:776(sequential 기본 False) vs :283(batched 기본 True) / stt/openai_stt_server.py:562-576,620,627-631
  검증: API 사실은 맞습니다 — 시퀀셜 `WhisperModel.transcribe`의 `without_timestamps` 기본값은 False(v1.2.0 :1010), batched는 True(:213)이고, 현재 서버의 transcription_options(:562-576)에 이 키가 없음을 grep으로 확인했습니다. **그러나 이득 산정 근거가 틀렸습니다.** Whisper의 타임스탬프 토큰은 '텍스트와 번갈아' 나오지 않고 세그먼트를 **

- `STT-04` [VIABLE] 동일 오디오 이중 PyAV 디코드 제거 (LAT-09) — 실측 약 10ms (conf=high, eff=S, vram=변화 없음, ko=yes)
  변경: analyze_audio()가 내부에서 이미 완전한 float32 mono/16kHz 배열 `decoded`를 만들고 버립니다(openai_stt_server.py:387). 이를 반환해 prepare_audio_for_whisper()가 재사용하도록 바꾸면 :833의 두 번째 av.open+decode가 사라집니다.
  이득: **제가 이 검토 PC(Ryzen 7 8700G, PyAV 18.0.0, 단일 스레드)에서 직접 측정: 3초 WAV 7.545ms, 3초 webm/opus 9.485ms.** 개발 PC(5600X, Zen3)에서는 약 9~12ms 예상. 즉 −10ms 안팎.
  근거: stt/openai_stt_server.py:371-391(analyze_audio, :387 decoded 생성 후 폐기), :394-406(load_audio_samples 재디코드), :463-466, :832-837 / 측정 스크립트는 스크래치패드에서 실행, 재현 가능
  검증: 중복 디코드 확인. stt/openai_stt_server.py:371-391의 analyze_audio가 av.open→resample로 완전한 float32 mono/16kHz 배열을 만들고 :387에서 `decoded`로 합친 뒤 **반환하지 않고 버립니다**(반환값은 통계 dict). 이어서 :463-471 prepare_audio_for_whisper → :394-406 load_audio_samples가 **동일한 resampler

- `STT-05` [DOWNGRADE] 발화 종료 감지 450ms 축소 — 예산 바깥에 숨은 최대 항목 (conf=high, eff=M, vram=변화 없음(브라우저 WASM/CPU), ko=yes)
  변경: 현재 클라이언트 VAD는 transformers.js로 `onnx-community/silero-vad`(Silero v5 계열)를 512샘플=32ms 프레임으로 돌리고(packages/stage-ui/src/workers/vad/vad.ts:34,52 / process.worklet.ts:7), minSilenceDurationMs는 스톡 1200ms를 바이너리 패치로 450ms까지 내린 상태입니다. 두 갈래가 있습니다 — (a) 즉시: 같은
  이득: 450→300ms면 종단 −150ms가 **무조건** 붙습니다(모델 연산과 무관). TEN VAD는 개발사가 'Silero는 speech→silence 전이에서 수백 ms 지연'이라 명시하며 10/16ms hop을 제공하므로 추가 −100~200ms 여지.
  근거: packages/stage-ui/src/stores/ai/models/vad.ts:22-25,36-40 / packages/stage-ui/src/workers/vad/vad.ts:34,52 / process.worklet.ts:7 / airi-local-stack/patch-airi-reaction-latency.ps1:9-10,17-20,250-280 / https://github.com/TEN-framework/ten-vad (Apache
  검증: 코드 근거는 정확합니다 — packages/stage-ui/src/stores/ai/models/vad.ts:23 `DEFAULT_VAD_MIN_SILENCE_DURATION_MS = 1200`, :37 `exitThreshold: resolvedThreshold * 0.3`(0.52×0.3=0.156), workers/vad/vad.ts:52 `AutoModel.from_pretrained('onnx-community/silero-vad')`

- `STT-06` [DOWNGRADE] 스트리밍 부분 전사 — 서버 롤링 윈도우 + AIRI 로컬 provider 배선 (conf=medium, eff=XL, vram=증가(상시 GPU 점유). 정량치 확인 필요, ko=yes)
  변경: AIRI 업스트림에 클라이언트→서버 PCM16 스트리밍 + SSE transcript delta 경로가 이미 존재하나 **Aliyun NLS(중국 클라우드) 전용으로 하드코딩**돼 있습니다. 확장점은 명확합니다 — packages/stage-ui/src/stores/modules/hearing.ts:229-238의 `STREAM_TRANSCRIPTION_EXECUTORS` 레지스트리에 로컬 executor를 등록하면 됩니다(@xsai/strea
  이득: 발화 종료 이전에 전사가 진행되므로 STT 확정이 '잔여 구간 재디코드'만 남습니다 — 계획서 목표 300~500ms의 유일한 구조적 도달 경로. STT-01~03을 다 해도 남는 인코더 하한을 넘는 방법은 이것뿐입니다.
  근거: apps/server/src/routes/audio-transcription-stream/route.ts:13,15-25,47-55(aliyun-nls 하드코딩), session.ts:23,51,162,169(16kHz PCM 청크·SSE delta) / packages/stage-ui/src/stores/modules/hearing.ts:229-238 / AIRI-NEUROSAMA-LOW-LATENCY-PLAN.md:19,260,266 / h
  검증: 확장점 존재는 사실입니다 — packages/stage-ui/src/stores/modules/hearing.ts:230-234 `STREAM_TRANSCRIPTION_EXECUTORS`에 aliyun만 등록, :236 resolveStreamTranscriptionExecutor, :412에서 실제 사용, 소비처는 packages/stage-layouts/src/composables/use-transcriptions.ts:22,178. 서버측

- `STT-07` [VIABLE] 모델·컴퓨트타입 SSoT 정렬 — 두 진입점 기본값 불일치 (conf=high, eff=S, vram=구성에 따라 ±700~1,000MB(small↔turbo 추정, 확인 필요), ko=yes)
  변경: start-airi-local-stack.ps1:2-3은 large-v3-turbo/int8_float16을 넘기지만(:186-188로 실제 전달) stt/start-local-stt.ps1:2-4의 기본값은 여전히 `small`/`float16`이고, openai_stt_server.py:76,81도 `small`/`float16`입니다. 세 곳이 갈라져 있어 어떤 경로로 띄웠는지에 따라 지연이 3배 차이 납니다.
  이득: 지연 절감은 0이지만 **재현성 회복**. 지금은 '996.5ms'가 어느 구성의 값인지 실행마다 달라질 수 있습니다.
  근거: start-airi-local-stack.ps1:2-3,186-188 / stt/start-local-stt.ps1:2-4 / stt/openai_stt_server.py:76,81,999-1002 / airi_docs/AIRI-INDEPENDENT-REVIEW-2026-08-10.md:598,610
  검증: 세 지점 불일치 전부 실측 확인. (1) airi-local-stack/start-airi-local-stack.ps1:2-3 `$SttModel = 'mobiuslabsgmbh/faster-whisper-large-v3-turbo'`, `$SttComputeType = 'int8_float16'` → :186-188 `& (Join-Path $PSScriptRoot 'stt\start-local-stt.ps1') -Model $SttModel

- `STT-09` [VIABLE] 기각 목록 — 조사했으나 이 프로젝트에 쓸 수 없는 후보들 (conf=high, eff=S, vram=해당 없음, ko=no)
  변경: 조사 결과를 남겨 재조사를 막습니다. ①NVIDIA Parakeet-TDT-0.6b-v3 / Canary-1b-v2 — 25개 유럽어 전용, **한국어 없음**(RTFx 3332/749로 매력적이나 무가치). ②Voxtral-Mini-4B-Realtime-2602(2026-02-03) — 한국어 공식 지원 + 네이티브 스트리밍 80ms~2.4s로 기술적 최적해지만 BF16 기준 **16GB VRAM 요구**, 8GB 예산에서 TTS+LLM과 공
  이득: 없음(기각). 다만 ⑤는 '선행 가설 생성기'로만, ②는 VRAM 예산이 바뀌는 후보 D(LLM 클라우드 이전) 채택 시 **재검토 가치가 생깁니다** — 그때는 STT에 4~5GB를 쓸 수 있습니다.
  근거: https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3 (25개 유럽어, 한국어 불포함, 2025-08-14) / https://huggingface.co/nvidia/canary-1b-v2 (동일 25개어, 한국어 불포함) / https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602 (2026-02-03, 13개어에 ko 포함, ≥16GB VRAM, A
  검증: 기각 근거를 URL로 전수 재확인했고 모두 실재합니다. ① nvidia/parakeet-tdt-0.6b-v3 — 25개 유럽어(bg,hr,cs,da,nl,en,et,fi,fr,de,el,hu,it,lv,lt,mt,pl,pt,ro,sk,sl,es,sv,ru,uk) 명시, **한국어 없음**, CC-BY-4.0, RTFx 3,332.74. ② mistralai/Voxtral-Mini-4B-Realtime-2602 — 실재하며 13개어에 ko 포함,


## [조사] LLM (BLOCKED 2건 제외)
이 축의 결론은 세 가지입니다. ① **EXAONE의 NC 봉쇄는 2026-08 현재 풀리지 않았습니다** — 최신 EXAONE 4.5(33B, arXiv 2604.08644)조차 "EXAONE AI Model License Agreement 1.2 - NC"이고, 4.5 계열에는 8GB에 들어갈 소형 모델 자체가 없습니다(33B 단일, 그 위 K-EXAONE 2.0은 750B-A37B MoE). 즉 "후속 모델로 갈아타면 라이선스가 풀린다"는 경로는 존재하지 않습니다. ② **대체 후보 판도가 2주 전에 바뀌었습니다** — Kakao가 2026-07말 Kanana 2 SLM(1.3B/3B)을 공개했고, 결정적으로 `kanana-2-3b-instruct`의 아키텍처가 `Qwen3ForCausalLM`이라 **llama.cpp가 오늘 바로 변환 가능**합니다(GGUF는 레포에 없어 직접 제작 필요). 한국어 지식 격차가 압도적입니다 — KoSimpleQA에서 Kanana-2-3B 22.29% vs Qwen3.5-2B 3.21%로 약 7배이며, "Apache 2.0이니 Qwen3.5-2B로 가자"는 직관적 선택은 한국어 버튜버 용도에서 실패합니다. 형제 모델 1.3B는 `Kanana2TinyForCausalLM`(하이브리드 SWA)이라 llama.cpp 미지원이니 **3B만** 선택지입니다. ③ **가속 축의 진짜 이득은 speculative decoding이 아니라 KV 프리픽스 재사용입니다** — `airi_memory.py:1795-1809`가 매 턴 변하는 `memory_block`을 시스템 프롬프트 **직후**에 삽입해 그 뒤 히스토리 전체를 매 턴 재-prefill시킵니다. 947자 시스템 프롬프트는 안정 프리픽스라 오히려 공짜에 가깝고, 문제는 프롬프트 길이가 아니라 **순서**입니다 — 질문의 전제가 뒤집힙니다. 반대로 speculative decoding은 이 프로젝트에서 적극 비추천입니다(타깃이 이미 2.4B, temp 0.45 샘플링이 수용률을 깎음, draft VRAM 여유 없음, Ollama는 Apple MLX 한정). 권고 순서는 **L7(프롬프트 순서) → L8(num_ctx·num_gpu SSoT) → L2/L3(라이선스 즉시 해소) → L1(Kanana-2-3B, VRAM축 kure-fp16 선행 필수) → L6(llama.cpp 직접)** 이며 L9는 하지 마십시오.
판정: **뒤처졌습니다 — 단, 지연(latency)이 아니라 라이선스·프롬프트 순서 축에서입니다.** 나눠 판정합니다. ① **품질 면에서 EXAONE 3.5 2.4B는 여전히 강력합니다** — KoMT-Bench 7.24 / LogicKor 8.51로, 대체 후보 Kanana-2-3B-Instruct의 KoMT-Bench 6.92, Kanana-1.5-2.1B의 6.54보다 오히려 높습니다. "더 좋은 한국어 소형 모델이 나와서 뒤처졌다"는 아닙니다. (단, KoMT-Bench는 카드마다 판정 모델·버전이 달라 교차 인용에 주의 — 동일 조건 재측정 확인 필요.) ② **그러나 라이선스 축에서는 명백한 막다른 길입니다.** 3.5 2.4B는 1.1-NC, 4.5는 1.2-NC이며 4.5에 소형이 없습니다. 공개 방송·수익화 시점에 반드시 교체해야 하는데, 지금 후보가 존재하고(Mi:dm 2.0 Mini = MIT, Kanana 1.5 2.1B = Apache-2.0, Kanana 2 3B = Kanana Open License) 그중 둘은 VRAM 중립이라 **미룰 이유가 사라졌습니다.** 늦출수록 프롬프트·평가자·캐릭터 계약이 EXAONE 출력 습성에 고착돼 이전 비용이 커집니다. ③ **가속 설정은 뒤처진 정도가 아니라 자기모순 상태입니다.** num_ctx가 2048로 3곳에 하드코딩돼 있는데 이는 Ollama 자체 기본값 4k(<24GiB VRAM)보다도 낮고, 947자 시스템 프롬프트가 창의 상당분을 먹은 상태에서 최근 60턴을 담으려 하므로 조용한 truncation이 상시 발생할 조건입니다. truncation은 KV 프리픽스 재사용을 파괴하므로 지연과 품질이 동시에 나빠집니다. num_gpu 12/999 불일치도 같은 SSoT 결함입니다. ④ **가장 큰 미실현 이득은 L7(memory_block 위치 이동)이며 새 모델·새 런타임 없이 순서 한 줄로 얻습니다.** 반대로 speculative decoding(L9)은 이 하드웨어·모델 크기·샘플링 설정에서 **적극적으로 하지 말아야 할 항목**이며, "가속=spec decoding"이라는 통념을 따르면 VRAM만 잃습니다. ⑤ 단, L7의 이득 존재 여부 자체를 먼저 실측하십시오 — Ollama의 KV 재사용은 공식 문서 어디에도 명시가 없습니다(확인 필요).

- `L7` [DOWNGRADE] 프롬프트 순서 재배치 — 휘발성 memory_block을 뒤로 이동해 KV 프리픽스 재사용 확보 (conf=medium, eff=S, vram=0 (증가 없음), ko=yes)
  변경: airi_memory.py:1795-1809 `assemble_context()`는 [system_intro, static_prompt, memory_block, journal, recent...] 순으로 조립합니다. 매 턴 내용·길이가 바뀌는 `memory_block`이 앞쪽 3번째에 있어 그 뒤의 journal+recent 전체가 매 턴 KV 캐시 무효화 대상입니다. [static_prompt, system_intro, journal, re
  이득: 매 턴 재-prefill 대상이 '시스템+전체 히스토리'에서 '기억블록+마지막 턴'으로 축소. num_ctx=2048 기준 수백~1,500 토큰 규모 절감이며, 절감 ms는 Ollama가 반환하는 prompt_eval_duration으로 즉시 A/B 측정 가능(ollama_proxy.py:68-100에 수집기가 이미 있음). 모델·런타임 교체 없이 얻는 유일한 구조적 이득이며, LLM 축 권고 1순위입니다.
  근거: C:\Projects\airi-local-stack\ollama-proxy\airi_memory.py:1795-1809 (assemble_context 조립 순서 — output.append 순서가 system_intro → static_prompt → memory_block → journal → recent), memory_runtime.py:410-412 ("AIRI's static identity therefore always preced
  검증: 실현 가능하나 **제안된 순서 그대로는 이득이 거의 0입니다**. ① 인용 오류: 현재 런타임 순서는 [system_intro, static_prompt, ...]가 아니라 [static_prompt, system_intro, ...]입니다 — memory_runtime.py:412가 `assemble_context(static_prompt, system_intro, ...)`로 인자를 뒤바꿔 넘기고, 제안이 인용한 :410-412 주석이 바로

- `L8` [UPGRADE] num_ctx / num_gpu SSoT 통합 — 2048 고정과 12/999 불일치 제거 (conf=high, eff=S, vram=num_ctx 2048→4096 시 EXAONE 2.4B 기준 약 +100~200MiB 추정(확인 필요). kure-fp16 선행 필수, ko=yes)
  변경: num_ctx가 2048로 3곳에 하드코딩(ollama_proxy.py:107, Modelfile.exaone-airi:2, start-local-ollama-proxy.ps1:3)돼 있고, num_gpu는 12(ollama_proxy.py:108, Modelfile.exaone-airi:3)와 999(start-local-ollama-proxy.ps1:8)로 갈립니다. 값을 단일 테이블/환경변수로 올리고, num_ctx는 실측 기반으로 재설정
  이득: ① 조용한 truncation 제거 — truncation은 KV 프리픽스를 통째로 깨뜨리므로 L7 이득을 보전하는 전제 조건입니다. ② num_gpu가 실행마다 갈리는 비결정성 제거 → TTFT 재현성 확보(VRAM축이 지적한 '오프로드 층수 비결정성'과 같은 뿌리). 절감 ms는 truncation 발생 빈도에 비례하므로 로그 기반 확인 필요.
  근거: C:\Projects\airi-local-stack\ollama-proxy\ollama_proxy.py:107-108 (NUM_CTX=2048, NUM_GPU=12), Modelfile.exaone-airi:2-3 (PARAMETER num_ctx 2048 / num_gpu 12), start-local-ollama-proxy.ps1:3,8,251 (NumCtx=2048, NumGpu=999, --num-ctx/--num-gpu 전달), oll
  검증: 코드 실측으로 제안보다 문제가 더 큽니다. ① 하드코딩 지점이 3곳이 아니라 최소 5곳: ollama_proxy.py:107-108, :4617-4618, :4732-4733, :4770-4771, 그리고 제안이 누락한 **:3616-3617에 num_ctx=1024** (dialogue director, 같은 `model` 변수 대상). Ollama는 동일 모델에 다른 num_ctx가 오면 러너를 재적재하므로 이 director 호출이 매 턴

- `L2` [UPGRADE] KT Mi:dm 2.0 Mini Instruct 2.3B (MIT) — 라이선스 리스크를 0으로 만드는 최소비용 교체 (conf=high, eff=M, vram=Q4_K_M 약 1.4~1.6GB 추정(2.3B×~4.8bit). 현 EXAONE Q4_K_M 1.6GB 대비 중립~소폭 절감, ko=yes)
  변경: exaone-airi:2.4b를 Mi:dm 2.0 Mini Instruct 2.3B로 교체합니다. MIT 라이선스라 상업 사용·재배포·API 제공·귀속 표기 의무가 전부 없습니다 — 조사한 후보 중 유일하게 조건이 하나도 없습니다. 아키텍처가 LlamaForCausalLM(hidden 1792, 48층, vocab 131,392, ctx 32,768)이라 llama.cpp 완전 호환이고 커뮤니티 Q4_K_M GGUF가 이미 다수 존재해 `oll
  이득: 라이선스 블록커 완전 해소(NC → MIT). 2.3B로 EXAONE 2.4B보다 작아 **VRAM 중립 또는 소폭 절감**이라 8GB 예산에 신규 압력을 주지 않습니다. 지연 개선은 기대하지 마십시오 — 동급 크기라 tok/s는 비슷할 것으로 추정됩니다(확인 필요).
  근거: https://huggingface.co/K-intelligence/Midm-2.0-Mini-Instruct — "Mi:dm 2.0 is licensed under the MIT License", 2.3B dense, pruning+distillation 파생 (2026-08-11 확인). config: https://huggingface.co/K-intelligence/Midm-2.0-Mini-Instruct/raw/main/config.js
  검증: 제안이 스스로를 과소평가했습니다. ① 라이선스 MIT 확인 — 의무 조항 0건 (https://huggingface.co/K-intelligence/Midm-2.0-Mini-Instruct, 2026-08-11). ② VRAM은 추정보다 좋습니다: DevQuasar GGUF 실측 Q4_K_M = 1,426,272,672B = **1.33GiB**, 현행 EXAONE q4_K_M 1.6GB(=1.49GiB) 대비 약 160MiB 절감 (https

- `L3` [DOWNGRADE] Kanana 1.5 2.1B Instruct (Apache-2.0) — 가장 리스크 낮은 즉시 폴백 (conf=high, eff=S, vram=Q4_K_M 약 1.3~1.4GB 추정 — 현행 대비 약 200~300MiB 회수, ko=yes)
  변경: exaone-airi:2.4b를 kanana-1.5-2.1b-instruct-2505로 교체합니다. Apache-2.0라 상업 조건이 없고, GGUF가 공식 파트너(DevQuasar)로 이미 배포되며 Ollama 라이브러리에도 커뮤니티 태그가 다수 존재해 사실상 `ollama pull` 한 번으로 검증 가능합니다. 즉 '오늘 저녁에 A/B 돌려볼 수 있는' 유일한 후보입니다.
  이득: 라이선스 블록커 해소 + 2.1B로 가장 작아 VRAM 절감(Q4_K_M 약 1.3~1.4GB 추정, 현재 1.6GB 대비 약 200~300MiB 회수). 8GB 초과 상태에서 이 회수분은 그 자체로 의미가 있습니다. 32K native / YaRN 128K 컨텍스트.
  근거: https://huggingface.co/kakaocorp/kanana-1.5-2.1b-instruct-2505 — license apache-2.0, KoMT-Bench 6.54, KMMLU 32.93(0-shot CoT), HAE-RAE 77.46(base), "up to 32K tokens length natively and up to 128K tokens using YaRN" (2026-08-11 확인). GGUF: kakaocorp.k
  검증: 라이선스 해소는 사실이나 두 가지 핵심 주장이 실측과 어긋납니다. ① Apache-2.0 확인, Q4_K_M GGUF 다수 실재(DevQuasar 등 15+ 레포) → '오늘 저녁 A/B 가능'은 맞습니다 (https://huggingface.co/kakaocorp/kanana-1.5-2.1b-instruct-2505, 2026-08-11). ② **VRAM 주장 3~4배 과장**: DevQuasar GGUF 실측 Q4_K_M = 1,522,7

- `L1` [DOWNGRADE] Kanana 2 3B Instruct — 한국어 지식 최강 후보, 단 GGUF 자체 제작 + VRAM 선행 조치 필수 (conf=high, eff=L, vram=Q4_K_M 약 2.1~2.3GB 추정(3.5B×~4.8bit). 현행 대비 +500~700MiB → **VRAM축 kure-fp16 선행 필수**, ko=yes)
  변경: 2026-07말 공개된 kakaocorp/kanana-2-3b-instruct로 교체합니다. 핵심은 아키텍처입니다 — HF API 확인 결과 architectures=["Qwen3ForCausalLM"], model_type="qwen3"이고 llama.cpp LLM_ARCH_NAMES에 `qwen3`가 등록돼 있어 **convert_hf_to_gguf.py로 오늘 바로 GGUF 변환이 가능**합니다(레포에 GGUF 파일은 없으므로 직접 제작)
  이득: 한국어 지식·사실성에서 다른 후보를 압도합니다. KoSimpleQA 22.29%(Qwen3.5-2B는 3.21%로 약 7배 차), KMMLU-CoT 43.32%, HAE-RAE 80.66%(base), KoMT-Bench 6.92, MT-Bench 7.15, MBPP 70.63. 토크나이저가 이전 세대 대비 한국어 토큰 효율 30%+ 개선이라 **같은 한국어 문장을 더 적은 토큰으로 표현** → prefill·decode 양쪽에서 지연이 줄어드
  근거: https://huggingface.co/api/models/kakaocorp/kanana-2-3b-instruct → config.architectures=["Qwen3ForCausalLM"], config.model_type="qwen3", license tag "kanana-open-license", siblings에 GGUF 없음 (2026-08-11 확인). https://huggingface.co/kakaocorp/kanana-2-3
  검증: '한국어 지식 최강'과 '라이선스 해소' 양쪽 다 근거가 약합니다. ① **라이선스가 리스크 0이 아닙니다**: kanana-open-license §4.1은 'API·클라우드·기타 원격 접속 서비스를 통해 제3자에게 Kanana Materials 접근을 제공/재판매'하는 경우 **별도 상업 라이선스**를 요구합니다. §3.1(v)는 웹사이트·인터페이스·문서에 'Powered by Kanana' 표시 의무와 파생 모델명 'Kanana' 접두 의

- `L6` [DOWNGRADE] llama.cpp llama-server 직접 구동 — Windows CUDA 사전빌드로 KV 캐시 제어권 확보 (conf=medium, eff=L, vram=모델 동일 시 중립. --n-gpu-layers 고정으로 오히려 예측 가능해짐, ko=yes)
  변경: Ollama를 llama-server로 교체하거나 병행합니다. Windows CUDA 사전빌드 zip이 매 빌드마다 배포되므로(b10358 기준 cuda-12.4 / cuda-13.3 x64) **Visual Studio 빌드 없이 압축 해제만으로 도입 가능**합니다(문서 build.md는 소스 빌드만 안내하지만 릴리스 자산에는 존재). 핵심 이득은 Ollama가 노출하지 않는 캐시 플래그입니다: --cache-prompt(기본 활성), --c
  이득: L7의 프리픽스 재사용을 '문서화된 동작'으로 확정합니다. Ollama는 KV 재사용을 공식 문서 어디에도 명시하지 않아 블랙박스인 반면, llama-server는 --cache-reuse로 **중간이 바뀐 프롬프트에서도** shifting 재사용을 명시적으로 켤 수 있습니다 — 정확히 memory_block이 중간에서 변하는 이 프로젝트의 형태와 맞습니다. --n-gpu-layers로 오프로드 층수를 결정론적으로 고정해 VRAM축의 '비결정적
  근거: Windows CUDA 사전빌드 자산: https://github.com/ggml-org/llama.cpp/releases/tag/b10358 → llama-b10358-bin-win-cuda-12.4-x64.zip, llama-b10358-bin-win-cuda-13.3-x64.zip (+cudart, 2026-08-11 릴리스). 서버 플래그: https://github.com/ggml-org/llama.cpp/blob/master/tool
  검증: 인용은 전부 실재하나 **핵심 전제가 무너집니다**. ① 사실 확인된 것: Windows CUDA 사전빌드 자산 실재(llama-b10358-bin-win-cuda-12.4-x64.zip, cuda-13.3-x64.zip, 2026-08-11 릴리스), --cache-reuse 기본 0, 설명 원문 'min chunk size to attempt reusing from the cache via KV shifting', --cache-prompt

- `L10` [DOWNGRADE] 한국어 imatrix 양자화 — 같은 비트수에서 한국어 품질만 회수 (conf=medium, eff=M, vram=Q4_K_M 유지 시 중립. IQ4_XS 전환 시 약 100~200MiB 절감 추정(확인 필요), ko=yes)
  변경: 현재 Q4_K_M은 범용(영어 중심) 캘리브레이션 기반입니다. llama-imatrix로 **한국어 코퍼스만으로 importance matrix를 생성**한 뒤 Q4_K_M 또는 IQ4_XS로 재양자화합니다. 파일 크기·VRAM·속도는 그대로 두고 한국어 손실만 줄이는 접근입니다.
  이득: llama.cpp 실측 근거가 있습니다 — 프랑스어 C4 평가에서 프랑스어 전용 imatrix 5.8036 PPL vs 영어 wiki.train imatrix 6.0314 PPL로 약 0.23 PPL(약 3.8%) 개선이었고, 영불 혼합(5.8405)보다도 단일 언어 전용이 더 좋았습니다. 원저자 결론은 "if a specific language is the primary use case it may be best to create the im
  근거: https://github.com/ggml-org/llama.cpp/discussions/5263 — ikawrakow: "The PPL for the French C4 dataset drops to 5.8036 if I use only French imatrix calibration, so if a specific language is the primary use case it may be best to create the imatrix us
  검증: 인용 자체는 실재 확인(ikawrakow, French C4 PPL 5.8036 French-only / 5.8405 EN-FR mixed / 6.0314 wiki.train, 결론 문장 원문 일치 — https://github.com/ggml-org/llama.cpp/discussions/5263). **그러나 그 실험은 Mistral-7B-Instruct-v0.2 + IQ2_XS(약 2.06bpw)입니다**. imatrix의 효과는 비트수가

- `L4` [VIABLE] [탈락군] Qwen3.5-2B · Gemma 4 · HyperCLOVA X SEED · Trillion · Motif · SKT A.X — 전부 비추천 (conf=high, eff=S, vram=해당 없음 (전부 탈락) — 참고로 Qwen3.5-2B만 Q4_K_M 약 1.3~1.5GB 추정으로 VRAM은 문제 없음, ko=partial)
  변경: 임무가 명시한 나머지 후보들의 탈락 근거를 한 항목으로 묶어 남깁니다. 다음 세션이 같은 조사를 반복하지 않게 하기 위한 항목이며, 재검토 트리거도 함께 적습니다.
  이득: 조사 재실행 비용 절감. 특히 Qwen3.5-2B는 Apache-2.0·Ollama 공식 태그(17.3M pulls, 0.8B/2B/4B/9B/27B/35B/122B)·llama.cpp qwen35 아키텍처 지원으로 도입 마찰이 최저라 **다음 세션이 가장 고르기 쉬운 함정**이므로 명시적 경고가 필요합니다.
  근거: Qwen3.5-2B: https://huggingface.co/Qwen/Qwen3.5-2B (Apache 2.0, 201 languages, 262,144 ctx, 24층/hidden 2048/vocab 248,320, Qwen3_5ForConditionalGeneration dense) + KoSimpleQA 3.21 vs 22.29는 https://huggingface.co/kakaocorp/kanana-2-3b-instruct/raw/ma
  검증: 기록 항목으로 유효하고 결론도 대체로 옳으나 세 곳을 보정합니다. ① Qwen3.5-2B: HF API 확인 결과 architectures=Qwen3_5ForConditionalGeneration, model_type=qwen3_5, 총 2.27B이며 **image-text-to-text 멀티모달**입니다(제안의 'dense' 서술 보정 필요). llama.cpp LLM_ARCH_NAMES에 "qwen35" 존재는 확인. 탈락 근거로 든 KoS


## [조사] ARCH (BLOCKED 3건 제외)
barge-in을 막는 것은 "에코 문제가 어렵기 때문"이 아니라 **트리거 지점과 캡처 생존**이라는 두 개의 구조 결정입니다. 중단 자체는 이미 즉시입니다 — `playFunction`의 `stopPlayback()`이 `source.stop()`을 동기 호출하고(C:/Projects/airi/external/airi/packages/stage-ui/src/components/scenes/Stage.vue:295-299), 취소 전파도 3계층이 이미 완성돼 있습니다(LLM abortSignal — round-cancel.patch:736 / 라운드 스코프 재생 드롭 — round-cancel.patch:1290-1292 / GPT-SoVITS ClientDisconnect 시 백엔드 절단 — C:/Projects/airi-local-stack/gpt-sovits/openai_compatible_proxy.py:260-267). 그런데 현재 barge-in 상당물의 트리거는 `stt_final → ingest(supersedeActive) → onBeforeMessageComposed → playbackManager.stopAll('new-message')`(Stage.vue:770)이라 **VAD 무음 판정 450ms + STT 약 1,000ms를 다 지불한 뒤에야** 재생이 멈춥니다 — 200~500ms 목표와 자릿수가 다릅니다. 반면 VAD `speech-start`는 512샘플(16kHz 기준 32ms) 프레임 하나가 임계를 넘는 즉시 발생하므로(packages/stage-ui/src/workers/vad/vad.ts:145-148), 트리거만 옮기면 목표는 이론상 사정권입니다. 그러나 그 앞을 두 겹이 막습니다: ① `watch(nowSpeaking)`가 재생 시작 시 `voiceInputInteractionLifecycle.stop()`으로 **VAD·레코더 스택 전체를 teardown**하고 800ms 쿨다운 후 재기동합니다(apps/stage-tamagotchi/src/renderer/pages/index.vue:589-603, voice-input-suppression.ts:1) — 단순 boolean 게이트가 아니라 물리적 청취 종료입니다. ② AEC가 상시 off인데, 그 사유는 문서에 남아 있습니다 — "Disables Chromium's microphone DSP (AGC / echo cancellation / noise suppression) **so the STT provider receives raw capture**"(C:/Projects/airi-local-stack/patch-airi-audio-constraints.ps1:5-8). 이 사유는 NS/AGC에는 타당하지만 AEC에는 적용되지 않으며, MDN 기준 세 제약은 **독립 설정 가능**합니다 — 즉 셋을 묶어 끈 것은 과잉이었고 그 대가로 Phase 6 1안이 소스+테스트로 봉인됐습니다(local-runtime-source.patch:4539-4551 및 :4505-4525 계약 테스트). 마지막으로 취소에 실체 갭이 하나 남습니다: `speech-pipeline.ts:25/211`이 tts 콜백에 `AbortSignal`을 넘기는데 `Stage.vue:476`의 `generateSpeech(...)`가 그것을 fetch로 전달하지 않아, barge-in 후에도 진행 중 합성이 완주하며 `TTS_LOCK`(openai_compatible_proxy.py:55)을 계속 점유합니다 — 서버 쪽 취소 코드는 이미 있는데 클라이언트가 방아쇠를 안 당기는 상태입니다. 2026년 전이중 speech-to-speech 모델 경로는 8GB에서 기각입니다(ARCH-10). 뉴로사마 항목은 정직하게 말씀드리면 **공개 아키텍처가 없습니다** — 계획서 자신도 "첫 구절 우선·병렬 합성·이전 발화 취소는 이미 구현됨"이라 기록하고 남은 차별점을 ①턴 전환 ②끼어들기 ③짧은 답변으로 좁혀 놨으므로(AIRI-NEUROSAMA-LOW-LATENCY-PLAN.md:109-113), 여기서 새로 이식할 "비법"은 없고 ②를 푸는 것이 곧 그 항목입니다. ※ 이번 세션은 WebSearch 예산(200/200)이 소진되어 검색을 수행하지 못했고 WebFetch 5건만 사용했습니다 — 전이중 모델 지형 전수 조사는 **확인 필요**로 남깁니다.
판정: **명백히 뒤처졌습니다 — 단, 교체 대상은 아키텍처가 아니라 세 개의 국소 결정입니다.** ① `echoCancellation:false`는 근거가 무효화된 선택입니다. 패치 사유는 "STT가 raw capture를 받게 한다"였는데(patch-airi-audio-constraints.ps1:5-8), raw capture를 훼손하는 것은 NS(스펙트럼 감쇠)와 AGC(동적 레인지 변형)이지 AEC가 아니며, MDN 기준 세 제약은 독립 설정 가능합니다. 셋을 하나로 묶은 결과 barge-in의 유일한 저비용 해법이 선제 차단됐고, 이제는 계약 테스트(local-runtime-source.patch:4505-4525)까지 얹혀 되돌리는 비용이 커졌습니다. ② half-duplex 억제가 "게이트"가 아니라 "teardown"인 것은 barge-in과 무관하게도 손해입니다 — 매 턴 VAD·마이크 재기동 비용을 지불하며(index.vue:589-596 + 800ms 쿨다운), 이 비용은 지연 예산에 계상조차 돼 있지 않습니다. ③ barge-in 트리거가 `stt_final`에 걸려 있는 것은 목표(200~500ms)와 산술적으로 양립 불가입니다. 반대로 **유지가 옳은 것**도 분명합니다: 로컬 STT+LLM+TTS 파이프라인 구성 자체, 라운드 상관·취소 설계(round-cancel.patch), GPT-SoVITS의 disconnect 취소 처리, `SpeechOutputStopReason`·`playbackManager.stopByIntent` 같은 확장 지점 — 이것들은 barge-in을 얹기에 이미 잘 맞는 형태입니다. 권고 순서는 고정입니다: **ARCH-05(취소 실체화, 1줄) → ARCH-03(억제를 게이트로 강등) → ARCH-01(헤드폰 모드로 지표 측정 개시) → ARCH-04(트리거 이동) → ARCH-06 → ARCH-02(스피커 사용 시 AEC) → ARCH-08 → (필요 시) ARCH-07/09**. ARCH-01 이전에는 "끼어들기→중단" 수치가 **측정 자체가 불가능**하므로, 그 앞 단계에서 AEC 알고리즘을 고르는 논의는 데이터 없이 하는 선택입니다. ARCH-10(전이중 S2S 모델)은 8GB 예산에서 현 시점 기각이며, 재검토 조건은 "한국어 음성 입출력을 지원하면서 int4로 6GB 이하에 상주하는 전이중 모델의 등장"으로 명시해 두십시오.

- `ARCH-01` [DOWNGRADE] 헤드폰 전제 full-duplex 모드 (억제 우회 토글) — 지표 측정 개시용 (conf=high, eff=S, vram=0MB (GPU 미사용), ko=yes)
  변경: 설정에 `fullDuplexMode` 토글을 추가해 켜졌을 때 `isVoiceInputSuppressed()`가 항상 false를 반환하고, `watch(nowSpeaking)`의 `voiceInputInteractionLifecycle.stop()` 호출을 건너뛰게 합니다. AEC·상관·화자인증 없이 '스피커를 안 쓴다'는 물리적 전제로 에코를 0으로 만듭니다. 계획서 Phase 6의 3안입니다.
  이득: 계획서 2대 핵심 지표 중 하나인 '끼어든 시점→음성 정지'가 **최초로 측정 가능**해집니다. 중단 자체는 이미 즉시(`source.stop()` 동기 호출)이므로 예상 실측은 VAD 프레임 32ms + 확정창 + Vue watcher 1틱 ≈ 100~350ms로 목표 200~500ms를 첫 시도에 충족할 가능성이 높습니다. 부수 효과로 턴당 VAD·마이크 재기동(800ms 쿨다운 포함)이 사라집니다.
  근거: C:/Projects/airi/external/airi/apps/stage-tamagotchi/src/renderer/pages/index.vue:307,320,345,386,449,462,475,499 / :589-603 (nowSpeaking watcher가 lifecycle.stop 호출) ; C:/Projects/airi/external/airi/apps/stage-tamagotchi/src/renderer/utils/voice-inpu
  검증: **변경 자체는 가능하나 이득주장의 핵심 수치가 틀렸습니다.** 근거 확인 — `apps/stage-tamagotchi/src/renderer/pages/index.vue:307-312`(isVoiceInputSuppressed), `:589-603`(nowSpeaking watcher가 `voiceInputInteractionLifecycle.stop({flushTranscript:false})` 호출), `utils/voice-input-s

- `ARCH-02` [DOWNGRADE] Chromium AEC3 재활성화 — echoCancellation만 true, NS/AGC는 false 유지 (conf=medium, eff=M, vram=0MB (CPU DSP), ko=yes)
  변경: `audio-device.ts:62-75`의 정적 constraints를 동적으로 바꿔 `echoCancellation: true`만 복원하고 `noiseSuppression`·`autoGainControl`은 false로 둡니다. Electron에 내장된 WebRTC AEC3를 그대로 씁니다(신규 설치물 0). 계획서 Phase 6의 1안.
  이득: 스피커 환경에서도 full-duplex가 성립합니다. AEC3는 Chromium이 렌더 스트림을 참조 신호로 잡으므로 AIRI 자신의 Web Audio 출력이 취소 대상에 들어갑니다 — 별도 루프백 배선·프로세스 추가가 필요 없습니다. 성공 시 ARCH-07(상관 게이트)·ARCH-09(화자 인증)가 통째로 불필요해집니다.
  근거: C:/Projects/airi/external/airi/packages/stage-ui/src/composables/audio/audio-device.ts:62-75 (업스트림 원본은 세 값 모두 true) ; C:/Projects/airi-local-stack/airi_docs/patches/AIRI-v0.11.3-local-runtime-source.patch:4539-4551 (false 치환), :4505-4525 (계약 테스트) ; C
  검증: **핵심 인과 주장이 인용 URL로 뒷받침되지 않습니다.** https://developer.mozilla.org/en-US/docs/Web/API/MediaTrackConstraints/echoCancellation fetch(2026-08-11) 결과: 세 제약이 독립 설정 가능하다는 점 ✓, `true`는 '브라우저가 결정하며 **최소 remote-only 수준**은 취소'라는 점 ✓ 확인됩니다. 그런데 `remote-only`는 **RT

- `ARCH-03` [DOWNGRADE] 억제를 teardown에서 '캡처 유지 + 전송 게이트'로 강등 (conf=high, eff=M, vram=0MB, ko=yes)
  변경: `watch(nowSpeaking)`가 호출하는 `voiceInputInteractionLifecycle.stop({flushTranscript:false})`를 제거하고, 마이크 스트림·VAD 워크릿은 살려둔 채 `inspectVoiceInputProviderRequestGate`/`inspectVoiceInputStreamingRequestGate`의 '전송 차단'만 유지합니다. 즉 '듣기는 계속, 보내기는 안 함'으로 계약을 바꿉니다.
  이득: barge-in의 물리적 전제(재생 중 VAD 생존)를 확보합니다. 동시에 턴마다 발생하던 VAD·getUserMedia 재기동과 800ms 쿨다운이 사라져, AIRI 발화 직후 첫 사용자 턴의 지연이 줄어듭니다(현재 지연 예산에 미계상 항목 — 절감폭 실측 필요).
  근거: C:/Projects/airi/external/airi/apps/stage-tamagotchi/src/renderer/pages/index.vue:589-603 (재생 시작 시 lifecycle.stop, 종료 시 쿨다운 예약), :364-390 (scheduleAssistantSpeechResume), :317-352 (전송 게이트 2종) ; C:/Projects/airi-local-stack/airi_docs/AIRI-CODE-AUDIT-2
  검증: **근거는 유효하나 접점이 후보 기술보다 훨씬 많고, 단독으로는 barge-in이 성립하지 않습니다.** 확인된 근거 — `index.vue:589-603`(재생 시작 시 lifecycle.stop, 종료 시 쿨다운 예약), `:357-391`(clearAssistantSpeechResumeTimer/scheduleAssistantSpeechResume), `:317-352`(전송 게이트 2종), `AIRI-CODE-AUDIT-2026-08-0

- `ARCH-04` [DOWNGRADE] barge-in 트리거를 stt_final → VAD speech-start로 이동 (+확정창 250~300ms) (conf=high, eff=M, vram=0MB, ko=yes)
  변경: 현재 재생 중단은 STT 확정 후 `ingest(supersedeActive:true)` → `onBeforeMessageComposed` → `playbackManager.stopAll('new-message')` 경로로만 발생합니다. 이를 VAD `speech-start` 직결로 바꿉니다: `SpeechOutputStopReason`에 `'barge-in'`을 추가하고(현재 유일값이 `'manual-chat'`), `useVoiceInput
  이득: barge-in 지연이 'VAD 무음판정 450ms + STT ≈1,000ms + LLM 진입'에서 '32ms 프레임 + 확정창 250~300ms'로 이동합니다 — 산술상 약 1,200ms 절감이며 목표 200~500ms 대역에 들어옵니다. 중단 경로 자체는 재작성이 아니라 재배선입니다(stopSpeechOutput이 이미 세션 취소·파이프라인·재생을 한 번에 정리).
  근거: C:/Projects/airi/external/airi/packages/stage-ui/src/stores/speech-output-control.ts:4 (`SpeechOutputStopReason = 'manual-chat'` 단일 값), :32-37 ; C:/Projects/airi/external/airi/packages/stage-ui/src/components/scenes/Stage.vue:651-656 (stopSpeechOutpu
  검증: **선행 의존성이 누락되어 단독 적용 시 효과가 0입니다.** 근거 확인 — `packages/stage-ui/src/stores/speech-output-control.ts:4`의 `SpeechOutputStopReason = 'manual-chat'` 단일값 ✓(이 파일은 combined patch·round-cancel patch 어디에도 없어 패치 후에도 동일), `:32-37` ✓, `Stage.vue:651-657`(stopSpeec

- `ARCH-06` [VIABLE] barge-in 중단 시 8~15ms 게인 램프 — 클릭·팝 제거 (conf=high, eff=S, vram=0MB, ko=yes)
  변경: `playFunction`의 `stopPlayback()`이 `source.stop()`을 즉시 호출해 파형을 임의 위치에서 잘라냅니다. `source → GainNode → destination` 사이에 GainNode를 넣고 abort 시 `linearRampToValueAtTime(0, now+0.010)` 후 `stop(now+0.012)`로 바꿉니다.
  이득: 끼어들기가 잦아질수록 매번 발생하던 클릭 노이즈가 사라집니다. 방송 품질 요소이며, 스피커 환경에서는 클릭 자체가 VAD를 재트리거하는 2차 오작동 원인이 될 수 있어 self-interrupt 감소에도 기여합니다.
  근거: C:/Projects/airi/external/airi/packages/stage-ui/src/components/scenes/Stage.vue:294-303 (stopPlayback: source.stop() 즉시), :275-284 (source → destination/analyser/lipSyncNode 직결)
  검증: **제약 4종을 모두 통과하며 근거도 패치 후 소스에서 재확인됩니다.** `Stage.vue:295-304`의 `stopPlayback`이 `source.stop(); source.disconnect()`를 즉시 호출하고, `:276-284`가 source→destination/analyser/lipSyncNode 직결임을 확인했습니다. combined patch의 Stage.vue hunk `@@ -292,7 +317,10 @@`는 시그니처를

- `ARCH-07` [DOWNGRADE] 재생 참조 신호 상관 게이트 (AudioWorklet 내 정규화 상호상관) (conf=low, eff=L, vram=0MB (CPU 워크릿), ko=yes)
  변경: 재생 직전 클라이언트가 이미 보유한 `item.audio`(AudioBuffer) PCM을 16kHz로 다운샘플해 지연 라인 링버퍼에 넣고, VAD용 별도 AudioContext(16kHz)의 워크릿에서 마이크 프레임과 정규화 상호상관을 계산해 임계 초과 시 speech 판정을 무효화합니다. AEC가 아니라 '에코 판별기'입니다 — 신호를 제거하지 않고 트리거만 억제합니다.
  이득: AEC3가 Electron에서 기대대로 동작하지 않는 경우(ARCH-02 실패 시)의 대안이며, 스피커 환경에서 self-interrupt를 억제합니다. 필터 수렴이 필요 없어 AEC보다 구현 실패 모드가 단순하고, 취소가 아니라 게이팅이라 STT 입력 음질을 훼손하지 않습니다.
  근거: C:/Projects/airi/external/airi/packages/stage-ui/src/libs/audio/vad.ts:66-72 (VAD 전용 AudioContext, sampleRate 16000) ; C:/Projects/airi/external/airi/packages/stage-ui/src/stores/ai/models/vad.ts:126 (minChunkSize 512) ; C:/Projects/airi/external/air
  검증: **'AEC보다 실패 모드가 단순'하다는 핵심 주장이 성립하지 않습니다.** 근거 자체는 확인됩니다 — `packages/stage-ui/src/stores/ai/models/vad.ts:124-133`(VAD 전용 AudioContext `sampleRate: 16000`, `minChunkSize: 512` = 32ms), `libs/audio/vad.ts:59-73`(audioContextOptions 기본 16kHz/interactive

- `ARCH-08` [UPGRADE] 텍스트 레벨 self-echo 가드 — 직전 TTS 텍스트 n-gram 대조 (2차 방어선) (conf=high, eff=S, vram=0MB, ko=partial)
  변경: 최근 N초 동안 TTS로 내보낸 문장들을 링버퍼에 보관하고, STT 결과가 도착하면 NFKC 정규화·공백/조사 정리 후 문자 n-gram 유사도를 계산해 임계 초과 시 그 전사를 폐기하고 라운드에 넣지 않습니다.
  이득: 음향 대책이 무엇이든(헤드폰·AEC·상관) 새어 들어온 자기 발화가 **대화 히스토리와 기억 DB를 오염시키는 것**을 막습니다. 에코가 사용자 발화로 저장되면 이후 모든 턴이 오염되므로 손해가 누적형입니다. 비용이 극히 낮아 다른 어떤 안을 채택하든 함께 넣을 가치가 있습니다.
  근거: C:/Projects/airi/external/airi/apps/stage-tamagotchi/src/renderer/pages/index.vue:472-480 (onTranscriptionResult가 무조건 push — 내용 기반 필터 없음), :447-458 (스트리밍 경로도 동일) ; C:/Projects/airi-local-stack/airi_docs/patches/AIRI-v0.11.3-round-cancel.patch:731-733
  검증: **이득이 과소평가됐고 한국어 표기도 하향 오기입니다.** 신규성 확인 — `AIRI-v0.11.3-local-runtime-source.patch`(84파일/5,799삽입) 전수에서 `self-echo|selfEcho|echo guard|n-gram|ngram|similarity` grep 0건이므로 운영 소스에도 내용 기반 필터가 전혀 없습니다. `index.vue:479-483`의 `onTranscriptionResult`가 무조건 `vo


## [조사] UPSTREAM (BLOCKED 0건 제외)
이 축의 결론은 한 문장으로 요약됩니다 — 이 포크는 업스트림이 이미 소스에 가지고 있는 것을 바이너리 패치로 우회하느라 못 쓰고 있습니다. 첫째, 포크의 근본 제약은 AIRI 업스트림이 아니라 설치본 `app.asar`를 동일 길이 in-place 바이트 치환으로 패치하는 방식입니다(`airi-local-stack/patch-airi-audio-constraints.ps1:174-175`이 `true`를 `!1  ` 패딩으로 뒤집습니다). 이 방식에서는 코드를 추가할 수 없으므로 Phase 5(스트리밍 재생)·Phase 6(barge-in) 진입이 원리적으로 불가능하며, 이것이 블로커 #2·#3의 실제 원인입니다. 둘째, 블로커 #2의 대부분은 업스트림 v0.11.3에 이미 구현돼 있습니다 — `Stage.vue:476-487`의 `tts()`는 전체 응답이 아니라 세그먼트(문장) 단위 콜백이고, `speech-pipeline.ts:27`의 `ttsMaxConcurrent` 기본값 4로 문장 N을 재생하는 동안 N+1을 합성하며, `playback-manager.ts`는 `stopByIntent`/`interrupt`/`onInterrupt` + `steal-oldest` 정책까지 갖춘 완성된 barge-in 하부구조입니다. 셋째, 블로커 #3의 `echoCancellation:false`는 업스트림 결함이 아니라 포크가 스스로 뒤집은 것입니다 — 업스트림 `audio-device.ts:66-73`의 기본값은 `true`입니다. 넷째, 900ms 볼륨 폴백 PR 기여는 이미 가치가 소멸했습니다 — 업스트림이 2026-07-26 커밋 `bcf7742`(#2095)로 먼저, 그리고 포크의 하드코딩 2700ms보다 나은 방식(`requiredSilenceMs = vad ? vadMinSilence + 900 : 900`)으로 고쳤습니다. 오히려 포크가 업스트림 방식을 역채택해야 합니다. 다섯째, 인접 OSS 중 파이프라인을 통째로 대체할 만한 것은 없습니다 — Open-LLM-VTuber는 동일 스택(faster-whisper + GPT-SoVITS + Ollama)에 MIT·한국어 README까지 갖췄지만 2026-05-15 이후 정체 상태이고 Live2D 프런트가 별도 레포라 이관 비용이 이득을 넘습니다. 다만 그 프로젝트의 interrupt 메시지에 `heard_response`를 실어 LLM 컨텍스트를 "사용자가 실제로 들은 지점"까지 절단하는 설계는 AIRI 업스트림에도 포크에도 없는 것으로, 개념만 차용할 가치가 있습니다. 권고 순서는 고정입니다: UP-02(소스 빌드 전환) → UP-01(main 리베이스) → UP-03(세그멘터 채택) → UP-04(AEC 복원). UP-02를 건너뛰면 나머지는 전부 실행 불가입니다.
판정: **명백히 뒤처졌습니다 — 단 뒤처진 대상은 "업스트림 버전"이 아니라 "업스트림을 소비하는 방식"입니다.** ① 포크는 v0.11.3 태그에 고정돼 있고 업스트림 main은 126커밋 앞서 있으나, 릴리스는 아직 v0.11.3(2026-07-18)이 최신이므로 "버전이 낡았다"는 판정은 과합니다. ② 진짜 결함은 설치본 asar 바이너리 패치 전략입니다 — 동일 길이 치환 제약 때문에 코드 추가가 불가능하고, 그 결과 업스트림이 이미 소스로 제공하는 세그멘터 재생·PlaybackManager barge-in 하부구조를 전혀 쓰지 못한 채 "클라이언트 완성 버퍼링"을 미해결 블로커로 안고 있습니다. 계획서가 블로커 #2·#3을 업스트림 한계로 기술한 것은 사실과 다릅니다. ③ `echoCancellation:false` 고착은 자해입니다 — 업스트림 기본값은 `true`이며, 포크의 `patch-airi-audio-constraints.ps1`이 이를 뒤집었습니다. ④ 900ms 업스트림 기여 계획은 철회해야 합니다 — 업스트림이 2026-07-26에 더 나은 방식으로 선행 수정했고, 포크의 하드코딩 2700ms가 오히려 열등합니다. ⑤ 인접 OSS 대체 검토 결과, 재발명 중인 것은 오케스트레이션 프레임워크가 아니라 AIRI 업스트림 자기 자신의 `pipelines-audio` 패키지입니다. pipecat/LiveKit은 `ollama_proxy.py`를 대체할 뿐 블로커의 소재지인 Electron 클라이언트를 대체하지 못하므로 부적합합니다. ⑥ 단 한 가지 확인 필요 사항이 남습니다 — AEC를 켰을 때 STT 품질이 실제로 어떻게 변하는지는 이 레포에 A/B 실측이 없습니다(`AIRI-LOCAL-STACK-REVIEW-2026-08-07.md:112`가 이미 미측정을 지적). UP-04는 실측 후 확정하십시오.

- `UP-02` [VIABLE] asar 바이너리 패치 → 소스 빌드 전환 (이 축의 최우선·전제조건) (conf=high, eff=L, vram=변화 없음 (클라이언트 빌드 방식 변경, GPU 미사용), ko=yes)
  변경: 설치본 `app.asar`를 동일 길이 in-place 바이트 치환하는 현행 패치 7종을 폐기하고, moeru-ai/airi를 소스에서 클론해 `pnpm -F @proj-airi/stage-tamagotchi app:build`로 직접 빌드한 뒤 포크 변경을 정상 소스 diff로 유지합니다. 현행 방식은 치환 문자열이 원본과 같은 바이트 길이여야 해서(예: `true` → `!1  ` 공백 패딩) 코드를 단 한 줄도 추가할 수 없습니다.
  이득: 블로커 #2·#3의 실행 경로가 열립니다. 현 방식에서는 Phase 5(스트리밍 재생)·Phase 6(barge-in) 진입이 원리적으로 불가능 — 두 기능 모두 코드 추가를 요구하기 때문입니다. 부수적으로 1.05GiB pristine 백업 계약과 `test-patch-applicability.ps1`/`test-patch-manifest.ps1` 등 패치 검증 하네스 전체가 불필요해집니다. 지연 자체의 직접 절감은 0ms이나, 다른 모든 U
  근거: C:/Projects/airi-local-stack/patch-airi-audio-constraints.ps1:174-175 (`$enabledBlock`/`$disabledBlock` 동일 길이 패딩), C:/Projects/airi-local-stack/patch-airi-playback-latency.ps1:1-17 ("replacement is shorter than the region and is padded with spaces, s
  검증: 근거 전부 실측 확인. (1) 바이트 길이 제약 실재 — patch-airi-audio-constraints.ps1:174-175 `$enabledBlock`/`$disabledBlock`이 `true`→`!1  ` 공백 패딩 동일 길이, patch-airi-playback-latency.ps1:9-11 "replacement is shorter ... padded with spaces, so the asar is never repacked".

- `UP-03` [DOWNGRADE] 업스트림 pipelines-audio 세그멘터·PlaybackManager 채택 — 블로커 #2·#3 재발명 중단 (conf=high, eff=M, vram=변화 없음 (클라이언트측 스케줄링), ko=yes)
  변경: 자체 재생 로직 대신 업스트림 v0.11.3에 이미 있는 `@proj-airi/pipelines-audio`의 speech-pipeline(문장 세그멘터 + 동시 합성)과 PlaybackManager(intent 단위 중단)를 그대로 사용합니다. 포크가 "미착수 Phase 5·6"으로 분류한 기능이 base에 이미 구현돼 있습니다.
  이득: 블로커 #2 대부분 해소 — `Stage.vue`의 `tts()` 콜백은 전체 응답이 아니라 **세그먼트 단위**이고, `ttsMaxConcurrent` 기본 4로 문장 1을 재생하는 동안 문장 2~4를 병렬 합성합니다. TTS warm first byte 613ms가 첫 문장에만 적용되고 이후 문장은 재생 뒤로 숨습니다. 블로커 #3의 하부구조도 완비 — `stopByIntent`/`stopAll`/`stopByOwner`/`interrupt
  근거: C:/Projects/airi/external/airi/packages/stage-ui/src/components/scenes/Stage.vue:460-487 (세그먼트 단위 tts 콜백, 485 decodeAudioData는 세그먼트 1개), C:/Projects/airi/external/airi/packages/pipelines-audio/src/speech-pipeline.ts:27 (ttsMaxConcurrent @default 4),
  검증: 코드 근거는 전부 정확하나 이득 주장 3건 중 2건이 성립하지 않습니다. 확인된 사실: packages/stage-ui/src/components/scenes/Stage.vue:13(`createSpeechPipeline` import)·:364(파이프라인 생성)·:376-378("per-segment callback" 주석)·:485(`decodeAudioData(res)` — 세그먼트 1개), pipelines-audio/src/speech

- `UP-01` [DOWNGRADE] 업스트림 main으로 리베이스 (v0.11.3 → main, 126커밋) (conf=high, eff=M, vram=변화 없음, ko=yes)
  변경: 포크 base를 v0.11.3 태그에서 업스트림 main(조회 시점 `28dec4b`)으로 올립니다. 릴리스는 아직 v0.11.3이 최신이므로 태그 추종이 아니라 main 추종 판단이 필요합니다.
  이득: 확인된 직접 이득 4건 — (1) 900ms 볼륨 폴백 선점 결함 수정(`bcf7742`, #2095, 2026-07-26)으로 포크 자체 패치 1종 폐기, (2) `chore(deps): use prebuilt node-pty, bump isolated-vm to 7.0 (#2112)`로 Windows 소스 빌드 난이도 하락 → UP-02 직접 지원, (3) `fix(stage-ui): fail fast on Whisper worker err
  근거: https://api.github.com/repos/moeru-ai/airi/compare/v0.11.3...main (2026-08-11 조회: total_commits 126), https://api.github.com/repos/moeru-ai/airi/releases (2026-08-11 조회: 최신 v0.11.3, published 2026-07-18), git ls-remote --heads origin main → 28dec4bc5
  검증: 인용 사실은 대부분 실재 확인. https://api.github.com/repos/moeru-ai/airi/compare/v0.11.3...main (2026-08-11 조회) → status=ahead, total_commits=126, behind_by=0. 커밋 목록에 `fix(stage-ui): fail fast on Whisper worker errors (#1803)`, `fix(stage-ui): preserve Kokoro wo

- `UP-05` [VIABLE] 900ms 볼륨 폴백 업스트림 PR 기여 — **철회 권고**, 대신 업스트림 수정을 역채택 (conf=high, eff=S, vram=변화 없음, ko=yes)
  변경: 계획된 moeru-ai/airi 이슈·PR 기여를 취소하고, 반대로 업스트림의 수정 방식을 포크에 가져옵니다. 포크는 하드코딩 2700ms로, 업스트림은 VAD 설정에서 파생되는 동적 값으로 같은 버그를 고쳤습니다.
  이득: 불필요한 업스트림 기여 작업(재현 테스트 작성 + PR 리뷰 대응) 제거. 동시에 포크 패치 품질 개선 — 업스트림 방식 `requiredSilenceMs = (trigger === 'vad') ? vadMinSilenceDurationMs + 900 : 900`은 VAD의 min_silence(현재 300ms)를 바꿔도 자동 추종하지만, 포크의 고정 2700ms는 VAD 설정 변경 시 다시 어긋납니다. 저지연 튜닝 과정에서 min_silenc
  근거: 버그 실재(v0.11.3): C:/Projects/airi/external/airi/packages/stage-ui/src/composables/audio/voice-input-session.ts:78 (`DEFAULT_VOLUME_FALLBACK_STOP_DELAY_MS = 900`) 및 :499 (`else if (activeRecordingTrigger.value === 'volume' || activeRecordingTrigger.val
  검증: 양쪽 근거 모두 실측 확인. 포크가 안고 있는 버그: external/airi/packages/stage-ui/src/composables/audio/voice-input-session.ts:78 `DEFAULT_VOLUME_FALLBACK_STOP_DELAY_MS = 900`, :499 `else if (activeRecordingTrigger.value === 'volume' || activeRecordingTrigger.value ===

- `UP-04` [DOWNGRADE] echoCancellation 재활성화 — 블로커 #3은 업스트림 한계가 아니라 자체 패치 (conf=high, eff=S, vram=변화 없음, ko=yes)
  변경: `patch-airi-audio-constraints.ps1`을 폐기해 업스트림 기본값(AEC/AGC/NS 모두 on)으로 되돌립니다. 계획서가 "`echoCancellation:false` 하드코딩이 소스+테스트로 고착"이라 기술한 것은 사실과 다릅니다 — 업스트림 소스의 기본값은 `true`이고, 포크가 minify된 `true`를 `!1  `로 치환한 결과입니다.
  이득: 블로커 #3의 절반(AEC 상시 off)이 패치 1종 삭제로 사라집니다. AEC가 켜지면 재생 중 마이크를 억제하는 half-duplex 강제가 완화되어 barge-in 지표를 **측정할 수 있게** 됩니다 — 현재는 측정조차 불가한 상태이므로 이것만으로도 목표(끼어들기 200~500ms) 검증 경로가 열립니다. Open-LLM-VTuber도 서버측 AEC 없이 프런트 `getUserMedia` AEC에 전적으로 의존하므로, 업계 표준 접근과
  근거: 업스트림 기본값: C:/Projects/airi/external/airi/packages/stage-ui/src/composables/audio/audio-device.ts:66-73 (`autoGainControl: true, echoCancellation: true, noiseSuppression: true` ×2블록). 포크의 역전: C:/Projects/airi-local-stack/patch-airi-audio-constraints.p
  검증: 사실 정정 부분은 맞으나 **핵심 이득 주장("barge-in 지표를 측정할 수 있게 된다")이 틀렸습니다**. ▶정확한 부분: 업스트림 기본값은 packages/stage-ui/src/composables/audio/audio-device.ts:62-73에서 `autoGainControl: true, echoCancellation: true, noiseSuppression: true` ×2블록으로 확인되며, 포크가 patch-airi-audi

- `UP-06` [VIABLE] Open-LLM-VTuber — 전면 대체는 부결, `heard_response` 설계만 차용 (conf=high, eff=S, vram=차용 시 변화 없음 (전면 대체는 부결이므로 해당 없음), ko=yes)
  변경: 동일 스택(faster-whisper + GPT-SoVITS + Ollama)의 로컬 AI 버튜버 스택입니다. 파이프라인 전면 대체 여부를 판정하고, 대체하지 않더라도 이식 가치가 있는 설계 요소를 추출합니다.
  이득: **차용 1건이 실질적입니다** — interrupt 메시지가 `heard_response = data.get("text", "")`를 실어 나르고, `handle_individual_interrupt(client_uid, current_conversation_tasks, heard_response, ...)`가 LLM 대화 이력을 "사용자가 실제로 들은 지점까지"로 절단합니다. AIRI 업스트림과 이 포크 모두 이 개념이 없습니다 — barg
  근거: https://api.github.com/repos/Open-LLM-VTuber/Open-LLM-VTuber (2026-08-11 조회: 13,183 stars, pushed_at 2026-05-15, MIT, topics에 neuro-sama/ollama/live2d), https://raw.githubusercontent.com/Open-LLM-VTuber/Open-LLM-VTuber/main/README.md (2026-08-11 조회:
  검증: 핵심 근거 4건 모두 실측 확인. (1) heard_response 설계 실재 — https://raw.githubusercontent.com/Open-LLM-VTuber/Open-LLM-VTuber/main/src/open_llm_vtuber/websocket_handler.py (2026-08-11 조회): `heard_response = data.get("text", "")` 및 `await handle_individual_interrup

- `UP-07` [VIABLE] pipecat / LiveKit Agents로 파이프라인 오케스트레이션 대체 — 부결 (conf=medium, eff=XL, vram=확인 필요 — 로컬 전용 구성의 8GB 동시 상주 실적 미확인, ko=unknown)
  변경: 실시간 음성 에이전트 프레임워크로 `ollama_proxy.py`(6,500줄)를 대체하는 안을 판정합니다. 과제의 핵심 질문 "파이프라인 오케스트레이션을 통째로 대체할 만한 것이 있는가"에 대한 직접 답입니다.
  이득: 이론적으로는 자체 프록시 6,500줄의 유지보수 부담과 SSE·문장 경계·인터럽트 처리 재발명을 덜 수 있습니다. pipecat은 BSD-2로 라이선스가 매우 관대하고 유지보수도 활발합니다(pushed_at 2026-08-11, 14,049 stars).
  근거: https://api.github.com/repos/pipecat-ai/pipecat (2026-08-11 조회: 14,049 stars, BSD-2-Clause, pushed_at 2026-08-11, archived false). 블로커 소재지가 클라이언트임의 근거: C:/Projects/airi/external/airi/packages/stage-ui/src/components/scenes/Stage.vue:485 (재생 경로), C:/P
  검증: 부결 판단이 옳습니다(제안의 결론에 동의). 근거 확인: https://api.github.com/repos/pipecat-ai/pipecat (2026-08-11 조회) stars 14,049 / BSD-2-Clause / pushed_at 2026-08-11 / archived false — 인용 수치는 정확합니다. 그러나 대체 논거는 성립하지 않습니다. ▶(a) 블로커 소재지가 서버가 아닙니다 — 실제 병목은 클라이언트 Electron에

- `UP-09` [DOWNGRADE] 업스트림 streaming-pipeline.ts 로컬 이식 — 중기 옵션, 지금은 보류 (conf=medium, eff=L, vram=변화 없음, ko=yes)
  변경: 업스트림 v0.11.3에 이미 있는 양방향 WebSocket 스트리밍 TTS 파이프라인을, GPT-SoVITS에 WS 엔드포인트를 붙여 로컬로 재사용하는 안입니다. `tts-session.ts`의 어댑터 경계가 provider id에 의존하지 않아 이론상 꽂을 수 있습니다.
  이득: 세그먼트 경계마저 없애 진정한 바이트 단위 스트리밍이 가능해집니다 — GPT-SoVITS의 `streaming_mode=2`·`min_chunk_length=16` 설정이 처음으로 실효를 갖습니다. 현재 이 설정들의 이득은 0입니다. 첫 음절까지의 시간이 문장 합성 완료가 아니라 첫 청크 도착 시점으로 당겨지므로 TTS warm 613ms에서 추가 절감 여지가 생깁니다(정확한 폭은 확인 필요).
  근거: C:/Projects/airi/external/airi/packages/stage-ui/src/libs/speech/streaming-pipeline.ts:113-130 (createStreamingTtsPipeline — token 필수, wsUrl 고정), :43 (model 예시 volcengine/seed-tts-2.0), :207 (per-sentence decodeAudioData), C:/Projects/airi/external/a
  검증: 보류 판단 자체는 옳으나 **핵심 이득 주장이 코드와 정면 배치**되므로 기대값을 더 낮춰야 합니다. ▶결정적 반증: packages/stage-ui/src/libs/speech/streaming-pipeline.ts:180-209 `flushAccumulatedAsSentence()`가 청크를 `merged`로 이어붙인 뒤 `await options.audioContext.decodeAudioData(merged.buffer.slice(0))

- `UP-08` [VIABLE] Amica — 탈락 (유지보수 중단 수준) (conf=high, eff=S, vram=해당 없음, ko=unknown)
  변경: 3D 캐릭터 음성 대화 오픈소스(TypeScript, MIT). 인접 후보로 검토했습니다.
  이득: 없음. 검토 결과 채택 가치가 확인되지 않았습니다.
  근거: https://api.github.com/repos/semperai/amica (2026-08-11 조회: 1,582 stars, pushed_at 2025-07-23, MIT, archived false)
  검증: 탈락 판단이 옳습니다. https://api.github.com/repos/semperai/amica (2026-08-11 조회): stars 1,582, license MIT, archived false — 인용 수치 정확. 결정적 근거는 pushed_at=**2025-07-23**으로 조회 시점 기준 약 13개월 커밋 정체이며, open_issues 22가 방치돼 있습니다(updated_at 2026-08-11은 스타·워치 등 메타 갱신이라


## [조사] PROXY (BLOCKED 1건 제외)
6,500줄(실측 7,284줄) 단일 파일의 실제 hot path는 **1턴당 905~1,342줄(12.4~18.4%)**로 실측됐고, 2,260줄짜리 `proxy()` 함수(ollama_proxy.py:5006-7265) 중 실행되는 것은 306~436줄(14~19%)뿐입니다 — 이 파일의 문제는 "느린 코드"가 아니라 "한 함수에 8배의 죽은 분기가 얹혀 있는 변경 위험"입니다. 실제로 grounding 로직 1,205줄 전체의 CPU 비용은 `grounding_rejection_flags` 0.139ms·`needs_grounding_retry` 0.0038ms로 밀리초 레벨에서 무의미합니다. 지연은 세 곳에 있습니다. ① **로컬 경로가 store-and-forward** — 증분 yield는 클라우드 경로(5596-5610)에만 있고 로컬은 6376 단 한 곳에서 완성된 1문장을 통째로 내보냅니다. 클라이언트는 `STREAMING_UI_FLUSH_CHUNK_SIZE = 6`으로 6자마다 flush하도록 이미 튜닝돼 있어 이 이득이 100% 버려집니다. ② **프롬프트 prefix가 매 턴 깨집니다** — `inject_character_state`(3761)가 매 턴 변하는 `silence_ms`/`last_user_at`/`version`(character_state.py:227-228)을 첫 system 메시지에 append하고, memory_block도 히스토리 앞(airi_memory.py:1803)에 들어갑니다. llama.cpp 서버는 `--cache-prompt` 기본 on으로 "공통 prefix는 재처리하지 않고 다른 suffix만" 처리하므로, 이 배치는 매 턴 전체 프롬프트(system_chars 949 + 히스토리, num_ctx 2048 상한)를 통째로 re-prefill시킵니다. ③ **기억→지식이 함수 안에 중첩 직렬**(4081) — 150ms + 350ms(428) = 최대 500ms. 다만 `asyncio.gather` 병렬화는 제가 직접 측정한 결과 **GIL 때문에 1.09~1.40배에 그칩니다**(순수 파이썬 2개 동시 = 0.96배로 오히려 손해). ALIGN-11의 "선기동 복원"은 원문 지적대로 **원형 그대로는 불가능**합니다 — 대신 prefix를 안정화한 뒤 `num_predict=0` 프리필 워밍을 검색과 겹치는 형태가 유일하게 성립하는 등가물입니다. FastAPI/uvicorn 튜닝은 실측상 **손댈 가치가 없습니다**(BaseHTTPMiddleware 첫 청크 +0.1ms/청크당 13.3µs, json 왕복 0.034ms, to_thread 106µs). 업계 표준(LiveKit preemptive generation, Pipecat BaseTextAggregator/InterruptionFrame)과 대조하면 이 프록시는 텍스트→TTS aggregation을 재발명 중이고, 낙관적 생성·인터럽션 계약·"재생된 것만 커밋"은 아예 빠져 있습니다.
판정:

- `PX-00` [UPGRADE] 먼저 측정: 이미 존재하는 ollama_prompt_eval_count / raw_chars_16_ms 텔레메트리 판독 (conf=high, eff=S, vram=0, ko=yes)
  변경: 코드 변경 0줄. 실제 음성 턴 5~10건에서 llm/end 이벤트의 `ollama_prompt_eval_count`·`ollama_prompt_eval_ms`·`ollama_eval_count`·`ollama_eval_ms`·`raw_chars_16_ms`·`raw_content_last_ms`를 읽습니다. prompt_eval_count가 매 턴 수백~2,048이면 PX-02(prefix 무효화)가 확정되고, 작으면 기각됩니다. (raw_c
  이득: 절감 0ms — 대신 PX-01/PX-02의 예상 ms를 추정에서 실측으로 바꿉니다. 이 축의 나머지 제안은 전부 이 수치 없이는 추정입니다.
  근거: ollama_proxy.py:68-77 (prompt_eval_duration/prompt_eval_count 이미 수집), ollama_proxy.py:5975-5981 (raw_chars_8/16/24_ms 기록), ollama_proxy.py:6404-6412 (end_meta 방출), ollama_proxy.py:1650-1668 (GROUNDING_MODE off = A/B 레버)
  검증: 인용 근거 전량 실측 확인. `OLLAMA_COUNT_METRIC_FIELDS`(prompt_eval_count/eval_count)는 C:\Projects\airi-local-stack\ollama-proxy\ollama_proxy.py:68-77, raw_chars_8/16/24_ms 기록은 같은 파일 5975-5981 구간, end_meta 방출은 6400-6412 구간에 실재합니다. `AIRI_GROUNDING_MODE` env는 oll

- `PX-01` [DOWNGRADE] 로컬 경로 증분 SSE 복원 — 절(clause) 단위 방출 + prefix-doom 검사 (conf=medium, eff=L, vram=0, ko=partial)
  변경: 현재 로컬 스트리밍은 6376의 단 한 번 delta로 완성 1문장을 내보냅니다(store-and-forward). 클라우드 경로(5596-5610)는 이미 `boundary.feed()` 반환값을 증분 yield합니다 — 로컬 루프는 6013에서 같은 반환값을 버립니다. 단, `max_sentences=1`·`preferred_chars=60`(1256-1258)이라 '문장 단위'는 사실상 답변 전체이므로 이득이 0입니다(본 세션 실측: 구둠
  이득: 첫 절이 보통 15~25자에서 완성되고 GPT-SoVITS `min_chunk_length=16`과 정확히 맞습니다. 45~60자 답변에서 20~40자(약 12~25토큰) 분량의 생성 시간을 앞당깁니다 — GPU 70~110 tok/s 가정 시 **약 170~360ms**, 부분 오프로드(25~30 tok/s)면 **400~1,000ms**. 독립 검토도 같은 구간을 300~800ms로 산정했습니다. 클라이언트는 이미 6자 flush로 준비돼
  근거: ollama_proxy.py:6376 (로컬 단일 delta), ollama_proxy.py:6013 `clean = boundary.feed(content)` 반환값 폐기, ollama_proxy.py:5596-5610 (클라우드 증분 yield — 참조 구현), ollama_proxy.py:1256-1258 (preferred_chars=60/max_chars=96/max_sentences=1), airi_docs/patches/AIRI-v
  검증: 기계적 사실은 전부 확인됐습니다: 로컬 루프의 `clean = boundary.feed(content)`는 ollama_proxy.py:6008에서 write-only이고(전 파일 `clean` 참조 전수 확인 — 이 스코프에서 재사용 없음), 본문 delta는 6376의 단 1회이며, 클라우드 경로 5594-5610은 같은 반환값을 증분 yield합니다. 경계 상수도 실측 일치(ollama_proxy.py:1256-1258 preferred_

- `PX-02` [VIABLE] 프롬프트 prefix 안정화 — 매 턴 변하는 블록을 head에서 tail로 이동 (KV 캐시 재사용 복원) (conf=medium, eff=M, vram=0, ko=yes)
  변경: `inject_character_state`(3748-3770)가 **첫 system 메시지에** 캐릭터 상태 JSON을 append합니다(3761). 그 JSON에는 `silence_ms`·`silence_before_turn_ms`·`last_user_at`·`last_assistant_at`·`version`이 들어 있어(character_state.py:227-228) **매 턴 반드시 달라집니다**. memory_block도 히스토리
  이득: PX-00 측정 전이므로 범위로만: 재프리필 대상이 수백~2,048토큰에서 tail 100~200토큰으로 축소. 3060 Ti의 2.4B Q4 prefill 속도는 **이 하드웨어 실측이 없어 확인 필요**이나 1,500~3,000 tok/s 범위를 가정하면 **약 150~700ms** 절감이며, 부분 오프로드 상태면 더 큽니다. grounding 재시도 턴은 이 절감을 두 번 받습니다(재시도는 이미 tail 노트만 교체 — 6094-6103)
  근거: ollama_proxy.py:3761 `message["content"] = f"{content}\n\n{block}"` (첫 system에 append), character_state.py:220-230 prompt_block(silence_ms/last_user_at/version 포함), airi_memory.py:1801-1803 (memory_block이 히스토리 앞), ollama_proxy.py:3196-3204·3222-3242
  검증: 근거가 라인 단위로 정확합니다. ollama_proxy.py:3761 `message["content"] = f"{content}\n\n{block}"`가 **첫 system 메시지**에 append하는 것, character_state.py:220-230 `prompt_block`이 `silence_ms`·`last_user_at`·`last_assistant_at`·`version`을 포함해 매 턴 반드시 달라지는 것, airi_memory

- `PX-03` [DOWNGRADE] ALIGN-11 판정 + 성립 가능한 유일한 대안: num_predict=0 선(先)프리필 (conf=low, eff=M, vram=0 (신규 상주 없음). 단 OLLAMA_NUM_PARALLEL>1이면 슬롯당 KV가 별도 할당돼 8GB 예산 위반 — PX-05로 1 고정 필수, ko=yes)
  변경: **판정: 원형 복원 불가**입니다. 현재 `send_task`는 5811-5822에서 memory/knowledge/native 변환이 모두 끝난 뒤에야 생성되며(5831 `await asyncio.wait_for(send_task, ...)`), 본문에 기억·지식 블록이 들어가야 하므로 순서를 되돌릴 방법이 없습니다(ALIGN-11 원문의 수정안도 동일 결론). 성립하는 대안은 하나뿐입니다: PX-02로 prefix를 안정화한 뒤, 기억·지
  이득: min(프리필 시간, 검색 시간)만큼 겹칩니다 — 오늘 기준 검색 150~500ms·프리필 150~700ms이므로 **약 150~400ms**. PX-02 없이는 이득 0(캐시가 어차피 무효), MEMSCALE의 numpy/O(N²) 수정 후에는 검색이 ~10ms로 줄어 이득이 다시 0에 수렴합니다 — **PX-02 완료 시점 & MEMSCALE 미완료 구간에서만 가치가 있는 과도기 최적화**입니다.
  근거: ollama_proxy.py:5811-5822·5831 (send_task가 prepare_memory_body 이후 생성), ollama_proxy.py:4081 (지식이 기억 안에 중첩), airi_docs/AIRI-INDEPENDENT-REVIEW-DATA-2026-08-10.md:1236-1240 (ALIGN-11 원문 및 "client.send를 먼저 띄울 수는 없습니다"), https://docs.livekit.io/agents/bu
  검증: 코드 근거는 정확합니다(ollama_proxy.py:5815-5825 `send_task = asyncio.create_task(client.send(...))`가 prepare_memory_body 이후 생성, 5830 `await asyncio.wait_for(send_task, ...)`, 4081 지식이 기억 안에 중첩). LiveKit 인용도 원문 확인 완료(https://docs.livekit.io/agents/build/audio/

- `PX-04` [DOWNGRADE] asyncio.gather(기억, 지식) 병렬화 — 실측 결과 권고하지 않음 (conf=high, eff=S, vram=0, ko=yes)
  변경: `prepare_memory_body`(4047)가 내부 4081에서 `prepare_knowledge_body`를 호출해 기억 150ms(memory_runtime.py:82) → 지식 350ms(ollama_proxy.py:428)가 완전 직렬입니다. 두 검색 모두 `question`에만 의존하므로 retrieve만 떼어내 gather로 겹치는 것이 이론상 가능합니다. 질문 2번에 대한 답은 '기회는 있으나 측정해 보니 거의 없다'입니다.
  이득: **이 검토 PC(Ryzen 7 8700G, Python 3.12.10, ProactorEventLoop)에서 직접 측정한 결과 이득이 거의 없습니다**: 순수 파이썬 CPU 작업 2개 동시 = **0.96배**(GIL로 오히려 손해), 순수 C sqlite 스캔 2개 = 1.40배, 실제 형태(파이썬 코사인 + sqlite) = **1.23배**. 500ms 직렬이 약 380~400ms가 되어 **약 100~120ms** 절감에 그칩니다. M
  근거: ollama_proxy.py:4047-4083 (중첩 직렬), ollama_proxy.py:4081, ollama_proxy.py:428 timeout=0.35, memory_runtime.py:82 retrieve_timeout_ms=150 · memory_runtime.py:393, 본 세션 실측(Ryzen 7 8700G, py3.12.10, ProactorEventLoop): pure-python gather2 0.96x / sqlite
  검증: 제안자 스스로 '권고하지 않음'으로 내렸고 그 방향은 옳습니다. 코드 근거 확인: ollama_proxy.py:4047-4083에서 `memory_runtime.prepare_payload_context` 완료 후 4081 `await prepare_knowledge_body(...)` 직렬, 지식 상한은 ollama_proxy.py:428 `timeout=0.35`, 기억 상한은 memory_runtime.py:82 `retrieve_time

- `PX-05` [DOWNGRADE] 단일 Ollama 슬롯의 다중 테넌트 정리 — NUM_PARALLEL 고정 + dialogue director의 직렬 삽입 제거 (conf=high, eff=S, vram=슬롯 1개 고정 시 KV = num_ctx 2048분 1회. NUM_PARALLEL이 2·4로 자동 선택되면 그 배수만큼 초과 — 정확한 MiB는 확인 필요, ko=yes)
  변경: 두 가지가 같은 자원(단일 Ollama 슬롯)을 건드립니다. **(a)** `OLLAMA_NUM_PARALLEL='1'`·`OLLAMA_MAX_LOADED_MODELS='1'`은 기본 OFF인 메모리 추출기 런처(start-memory-extractor.ps1:94-95)에만 있고 프로덕션 런처(start-local-ollama-proxy.ps1:249-256)에는 없어 Ollama 자동 결정에 맡겨져 있습니다 — 슬롯이 나뉘면 prefix 재
  이득: (a)는 직접 절감보다 **결정론 확보** — PX-02·PX-03의 전제 조건이며 KV VRAM이 예측 가능해집니다. (b)는 해당 턴에서 director 프리필+128토큰 생성 + 본답변 재프리필을 제거해 보수적으로 **+800~2,500ms**를 도로 가져옵니다. 최소 개입으로 5202의 빈 delta만 LOCAL_IMMEDIATE_ACK로 바꿔도 그 구간의 침묵은 즉시 가려집니다.
  근거: ollama-proxy/start-memory-extractor.ps1:94-96 (여기에만 존재), ollama-proxy/start-local-ollama-proxy.ps1:249-256 (프로덕션 런처 — 해당 변수 없음), ollama_proxy.py:4617-4618 (매 요청 num_ctx/num_gpu 강제), ollama_proxy.py:5188·5202·5213, ollama_proxy.py:3524-3687 + `"num_pr
  검증: (a)와 (b) 모두 실측으로 크게 약화됩니다.

**(a) 전제가 사실과 다르고, 제안한 수정은 무효타입니다.** Ollama 공식 FAQ(https://github.com/ollama/ollama/blob/main/docs/faq.mdx, 2026-08-11 페치)는 `OLLAMA_NUM_PARALLEL` 기본값을 **1**로 명시합니다 — "Ollama 자동 결정에 맡겨져 슬롯이 2·4로 나뉜다"는 전제가 현행 문서와 어긋납니다(구버전 a

- `PX-06` [VIABLE] 2,260줄 proxy() 분해 — 지연이 아니라 변경 위험 대책 (질문 1의 답) (conf=high, eff=L, vram=0, ko=yes)
  변경: 단일 함수 `proxy()`(5006-7265)가 라우팅·ACK·검색·클라우드·프로액티브·로컬 스트리밍·grounding 재시도·비스트리밍 3종을 모두 담습니다(await 51개). 책임 분포 실측: proxy() 2,260줄 / grounding 1,205줄(43 defs) / lang·dialogue 566 / IncrementalAiriOutputBoundary 369 / LeadingControlSanitizer 215 / TopicBo
  이득: **지연 절감 0ms** — 실측상 grounding 전체 CPU가 `grounding_rejection_flags` 0.139ms·`needs_grounding_retry` 0.0038ms·`sanitize_assistant_content` 0.056ms·boundary 문자단위 feed 0.055ms로 무의미합니다. 이득은 전부 유지보수 쪽: PX-01·PX-02·PX-07이 전부 이 함수 한복판을 건드리므로 분해 없이는 세 변경이 같은 2
  근거: 본 세션 sys.settrace+threading.settrace 실측: 로컬 스트리밍 1턴 905/7,284줄(12.4%)·proxy() 316/2,260(14.0%) / grounded 일반턴 991줄(13.6%)·proxy() 306·grounding 117 / grounding 재시도턴 1,269~1,342줄(17.4~18.4%)·proxy() 409~436·grounding 292~307. ollama_proxy.py:5006-7265
  검증: 수치가 검증 가능한 범위에서 전부 정확합니다. `@app.api_route` 핸들러 `proxy`는 ollama_proxy.py:5006에서 시작해 다음 최상위 정의 `def main()`(7266) 직전인 7265에서 끝나 정확히 2,260줄이고, 그 구간의 `await ` 출현 수를 세면 **51**로 주장과 일치합니다(파일 총 7,284줄). 로컬 스트리밍 제너레이터는 ollama_proxy.py:5656 `async def stream_

- `PX-08` [VIABLE] FastAPI/Starlette/uvicorn 튜닝 — 실측으로 기각. 손대지 마십시오 (질문 5의 답) (conf=high, eff=S, vram=0, ko=yes)
  변경: 현재: `uvicorn.run(app, host, port)` 전 기본값(7280), httptools·uvloop·winloop 전부 미설치, ProactorEventLoop, `@app.middleware("http")`(917) = BaseHTTPMiddleware 1개, httpx.AsyncClient 기본 limits(4455). 이 축을 전부 직접 벤치마크했습니다.
  이득: **전부 합쳐 1ms 미만입니다.** 동 PC 실측(인프로세스 ASGI 구동): BaseHTTPMiddleware 없음 = 첫 청크 0.029ms·청크당 0.9µs / 1개 = 0.133ms·13.3µs / 2개 = 0.284ms·23.8µs. 즉 미들웨어 1개의 순비용은 첫 청크 +0.104ms입니다. `anyio.create_memory_object_stream()`은 버퍼 0이라 전체 바디를 쌓아두지 않으므로 SSE 버퍼링 위험도 없습니다
  근거: ollama_proxy.py:7280 `uvicorn.run(app, host=args.host, port=args.port)`, ollama_proxy.py:917, ollama_proxy.py:4455, 설치 실측: httptools/uvloop/winloop/orjson MISSING · uvicorn 0.52.1 · starlette 1.4.1 · httpx 0.28.1 · numpy 2.5.1 · py3.12.10, uvicorn/lo
  검증: 이 검토 PC에서 독립적으로 재확인했고 전부 일치합니다. `python -m pip list`: fastapi 0.141.1 / starlette 1.4.1 / uvicorn 0.52.1 / httpx 0.28.1 / numpy 2.5.1, Python 3.12.10 (MSC v.1943 64bit), **httptools·uvloop·winloop·orjson 모두 미설치**. `uvicorn.run(app, host=args.host, po

- `PX-09` [VIABLE] 재발명 목록 — 업계 표준 대비 이 프록시가 직접 만든 것 (질문 6의 답) (conf=medium, eff=S, vram=0, ko=yes)
  변경: LiveKit Agents / Pipecat와 대조해 세 층으로 나눕니다. **(A) 재발명했으나 정당함**: 한국어 문체·반말 계약, grounding 사실성 게이트, AIRI 제어 봉투(ACT/CALL/DELAY) 파싱 — 프레임워크에 등가물이 없는 프로젝트 고유 자산입니다. **(B) 재발명했고 표준이 더 낫다**: 텍스트→TTS aggregation. Pipecat은 `BaseTextAggregator`로 sentence/word/tok
  이득: 직접 ms 0. PX-01·PX-03·PX-07의 설계 근거를 검증된 선례로 고정해 잘못된 방향의 재작업을 방지합니다.
  근거: https://docs.livekit.io/agents/build/audio/ (2026-08-11 페치: preemptive generation, `preemptive_tts: True`, max_speech_duration, max_retries — "provides no specific latency measurements"), https://docs.livekit.io/agents/build/turns/ (2026-08-11 페치: tu
  검증: 웹 근거 4건을 전부 원문 페치로 대조했고 인용이 정확합니다. Pipecat `BaseTextAggregator`는 실재하며 추상 메서드 `text`/`aggregate`/`flush`/`handle_interruption`/`reset`와 `AggregationType.SENTENCE|TOKEN|WORD` 전략, 그리고 인터럽션 시 폐기 docstring을 갖습니다(https://raw.githubusercontent.com/pipecat-a
