# AIRI dev PC 모델 SSoT 실기 검증 (2026-08-12)

## 범위와 환경

- 검증 기준: `feat/upgrade-scout-full-2026-08-11` commit `3bb61ff`
- GPU: NVIDIA GeForce RTX 3060 Ti 8 GiB
- 설치 AIRI `app.asar` SHA-256:
  `A81C52811BCD6F5290A5C0D498357742F26D61CE33F8FEBDB767CC8AD388BC00`
- 모델: `midm-airi:2.0-mini`, 롤백 `exaone-airi:2.4b`
- 실제 설치 Electron 서버 채널을 `send-airi-local-text.mjs`로 구동했다.
  직접 11435 요청으로 대체하지 않았다.

Git에서 제외되는 참조 WAV와 STT Python/CUDA runtime은 기존 dev worktree의
승인된 로컬 자산을 환경 변수로 지정했다. 대상 worktree에 자산이 없을 때
첫 기동은 TTS cache readiness와 CUDA preflight에서 의도대로 차단됐다.

## 결과

| 항목 | 실측 결과 | 판정 |
|---|---|---|
| 기본 warmup | `midm-airi:2.0-mini`, HTTP 200 | PASS |
| Electron 정규화 | `normalized_requests=1`, `last_requested_model=exaone-airi:2.4b` | PASS |
| foreground | Mi:dm runner 1개, 100% GPU, context 2048 | PASS |
| evaluator | 실제 Electron 턴 뒤 `last_status=ok` | PASS |
| eval provenance | `model`과 `model_version` 모두 Mi:dm | PASS |
| EXAONE 롤백 | warmup 200, Electron 턴 완료, `matching_requests=2` | PASS |
| 롤백 evaluator/provenance | evaluator `ok`, 두 provenance 필드 모두 EXAONE | PASS |
| digest 관측 | Mi:dm `92a9ba2ee8c79ba46c22907b50b15eb1ca55c94d04230eca73917936ef36485f` | PASS |
| 일치 pin | health/log `pinned=true`, `verified=true`, `status=pinned` | PASS |
| 불일치 pin | 1자 변경 digest가 proxy 기동 전 차단, 11435 미수신 | PASS |

임시 provenance 레코드는 생성·승인·export 확인 후 삭제했다. Electron 턴은
합성 검증 문장만 사용했으며 원문 대화나 식별자를 증거에 남기지 않았다.

## 운영 반영과 주의

기본 Mi:dm 실측 digest를 root 운영 런처의 기본 pin으로 고정한다. 명시적
`-ChatModelDigest` 또는 `AIRI_CHAT_MODEL_DIGEST`는 이를 override한다.
`-ChatModel exaone-airi:2.4b` 롤백은 별도 digest가 없으면 기존처럼 unpinned
관측 모드이며, 승인 digest를 함께 주면 pin할 수 있다.

모델 전환 직후에는 Ollama의 30분 keep-alive 때문에 이전 runner가 잠시
함께 남았다. 검증에서는 이전 모델에 `keep_alive=0`을 보내 언로드한 뒤
단일 runner를 확인했다. 이는 모델 삭제·재생성이 아니며, 운영 전환 시에도
VRAM 실측 전에 이전 runner를 명시적으로 언로드해야 한다.
