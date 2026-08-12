# AIRI Upgrade Scout 적용·실측 — 2026-08-11

## 범위와 안전 경계

- `AIRI-UPGRADE-SCOUT-2026-08-11.md`에서 채택한 T0~T3 항목을 별도 기능 브랜치에 적용했다.
- 모델 호출은 로컬 loopback만 사용했다. 마이크, 운영 서비스, 운영 DB, 외부 채팅·검색은 사용하지 않았다.
- 기억 계측은 이 worktree의 격리 runtime DB 또는 생성 fixture만 사용했다. 승인 지식 fixture의 재현성과 운영 지식 배포는 계속 별개다.
- T-05 한국어 레퍼런스 교체는 화자 변경 승인이 없어 수행하지 않았다. 기존 승인 음성은 경로만 재사용했고 복사·변경하지 않았다.

## 구현 상태

- T0/T1: PX-00, evaluator 기본 off, TTS 15초 상한, grounding A/B, KURE fp16, num_ctx/num_gpu SSoT, KM-01, ARCH-08, STT SSoT/beam 1/이중 decode 제거, ARCH-06, T-02 cache-ready gate, UP-05/STT-05 실험 gate를 구현했다.
- T2: KM-02/03/04/05/08, PX-01/02/06(a), T-01 AudioWorklet PCM 재생, ARCH-01/03/04 barge-in 묶음, v0.11.3 runtime patch를 구현했다.
- T3: Mi:dm 2.0 Mini Q4_K_M 기본 모델, 조건부 AEC3 모드, STT-06 loopback streaming STT를 구현했다.
- UP-01은 `origin/main` 기준 별도 포팅 브랜치로 재배치했다. source build와 타입검사 및 집중 회귀를 통과했다.
- 문서에서 기각·BLOCKED로 분류한 엔진 교체, speculative decoding, STT-03, PX-03/04/08 등은 적용하지 않았다.

## 실측 결과

### VRAM과 기억

| 항목 | 결과 |
|---|---|
| KURE fp32 | CUDA allocated 2,165.938MiB, reserved 2,186MiB |
| KURE fp16 | CUDA allocated 1,083.032MiB, reserved 1,090MiB |
| 회수량 | allocated 1,082.906MiB, reserved 1,096MiB |
| fp32/fp16 검색 품질 | 양쪽 MRR·Recall@1·Recall@3 모두 1.0 |
| fp32 query | P50 24.387ms, P95 38.354ms |
| fp16 query | P50 26.774ms, P95 55.481ms |
| 10k×1024 memory benchmark | dynamic P50 110ms, static P50 78ms; 150ms gate 통과 |

동시 상주 단계는 TTS+STT 4,888MiB, KURE fp16 추가 6,137MiB, Mi:dm 전량 GPU 추가 7,324MiB였다. 합성→전사 1회 뒤 관측 peak는 7,350/8,192MiB였다. `ollama ps`는 Mi:dm 100% GPU, context 2,048을 보고했다. 이번 구성에서는 자동 부분 offload가 재현되지 않았고 peak 기준 약 842MiB가 남았다.

### Mi:dm과 EXAONE

| 항목 | EXAONE 3.5 2.4B | Mi:dm 2.0 Mini |
|---|---:|---:|
| 고정 raw 품질 gate | 3/16 | 9/16 |
| isolated warm 생성 | 약 123.4 tok/s | 약 116.1 tok/s |
| isolated GPU 증분 | 약 1,792MiB | 약 1,946MiB |
| full-stack 동일 TTS 문장 첫 byte P50, n=6 | 777.1ms | 1,078.5ms |
| full-stack 동일 TTS 문장 완료 P50, n=6 | 2,029.4ms | 2,182.7ms |

Mi:dm은 품질 gate와 MIT 라이선스 목적은 충족했지만, 이 작은 순차 표본에서는 TTS 첫 byte가 약 301ms 느렸다. TTS 자체가 비결정적이고 A/B 순서도 완전 무작위화하지 않았으므로 인과 확정값은 아니다. 기본 전환은 코드에 유지하되 installed Electron의 실제 first-audible P50을 통과하기 전에는 배포 승인으로 해석하지 않는다.

### LLM streaming, grounding, prefix

- full-stack Mi:dm quality probe: HTTP header 37.2ms, 첫 raw delta 94.5ms, 첫 안전한 본문 561.5ms, 완료 565.4ms.
- 같은 턴 terminal meta: prompt 1,091 tokens / 246.135ms, eval 11 tokens / 112.6ms, Ollama total 515.419ms.
- 별도 공개 SSE 표본은 ACK 20.9ms, 안전 본문 283.7ms였다. PX-01은 native terminal까지 기다리는 약 100ms를 해당 표본에서 제거했다.
- prefix 반복 실험의 prompt-eval은 첫 235.647ms, 동일 prompt 두 번째 12.702ms, 다른 tail 두 건 28.160/25.382ms였다. PX-02의 안정 prefix 이동은 실제 cache reuse 근거가 있다.
- 고정 seed 8문장 A/B에서 grounding off 중앙값 약 270.7ms, balanced 약 639.5ms, balanced retry 5/8이었다. off는 새 사실·약속을 만들었고 balanced는 더 안전하지만 느렸다.
- 공유 anchor 새 actor, 생략 주어 화자 역전, 수량·장소·전언, 지원하지 않는 `-ㄹ게` 약속을 balanced 최초 draft에서도 차단하도록 보강했다.

### TTS와 STT

| 항목 | 결과 |
|---|---|
| TTS cold cache-ready | 약 34.3초, ready 2/2 |
| cache ACK warm | 첫 byte P50 약 2.3ms(첫 연결 표본 제외) |
| isolated 일반 TTS, n=3 | 첫 byte P50 742.8ms, 완료 P50 2,013.5ms |
| full-stack 합성→POST STT | STT 610.7ms, 합성 문장 정확히 복원 |
| STT WebSocket, 3.3초 합성 음성 burst | 첫 partial 504.0ms, final 2,447.4ms |

WebSocket partial은 중간에 단어가 수정됐고 final은 문장 의미를 보존했지만 마침표를 물음표로 바꿨다. partial을 caption-only로 제한한 설계는 타당하다. 다만 실제 마이크 20+20 표본이 없으므로 STT-05 300ms 승격, STT-06 품질, P50 ≤2.0초는 아직 통과 판정이 아니다.

## 검증

- 통합 Python: 716 passed, 1 skipped, 463 subtests.
- proxy: 253 tests passed.
- memory: 211 tests 및 9 subtests passed.
- STT: 52 tests 및 35 subtests passed.
- TTS proxy: 21 tests passed; cache-ready launcher contract passed.
- `test-current-checkpoint.ps1`: PASS, sender 26/26.
- Python CI는 10분 상한의 11개 독립 shard와 cold-cache용 lean requirements로
  구성했다. 로컬 전체 suite는 45.52초였지만, 원격 GitHub clean Windows
  runner의 cold-cache 실행은 아직 관측하지 않았으므로 10분 gate의 최종
  통과 판정은 첫 원격 run에 남긴다.
- v0.11.3 client: Stage UI/Tamagotchi typecheck와 production renderer build 통과; focused 42 tests passed.
- 최신 `main` 포팅: 25/25 build tasks, Stage UI·Tamagotchi typecheck, focused 168 tests passed.

## 판정

- 코드·fixture·정적 회귀 기준으로 Wave A/B와 조건부 T3 구현은 통합 가능 상태다.
- 아직 운영 채택으로 승격하면 안 되는 항목은 Mi:dm의 installed-app first-audible, T-01 실제 playback/lip-sync/fallback, real-mic VAD 20+20, speaker AEC, barge-in 200~500ms, STT-06 실제 마이크 품질이다.
- Python CI cold-cache 10분 상한도 첫 원격 Windows run 전에는 조건부다.
- T-05는 사용자 화자 승인 전까지 보류한다.
- 승인 지식 fixture는 테스트 재현성만 보장한다. 운영 지식 자동 배포는 별도 승인·배포 과제로 남긴다.
