# AIRI 로컬 개발 자산 통합 및 정리 기록

날짜: 2026-08-14
상태: 완료 기준 기록
대상: 분산 worktree·검증 clone·로컬 LLM 평가 자산·Codex 세션 인덱스

## 결론

- 운영 LLM은 사용자 확정값인 `midm-airi:2.0-mini`로 단일화했다.
- Ollama에는 운영 태그와 그 원본 Q4 태그만 남겼다.
  - `midm-airi:2.0-mini` — digest `92a9ba2ee8c7`
  - `hf.co/DevQuasar/K-intelligence.Midm-2.0-Mini-Instruct-GGUF:Q4_K_M`
- Motif, Ministral, Qwen, Phi, Granite, EXAONE, Kanana, Gemma의 로컬 가중치와
  재다운로드 가능한 평가용 snapshot·가상환경·로그는 제거했다.
- 후보를 지운 것은 연구 결론을 지운 것이 아니다. 고정 revision, artifact hash,
  모델별 사용법, 실측 결과, 대화 검토, 실패 원인과 채택 판단은 Git 문서와 로컬
  content-safe 결과 보관소에 남겼다.
- 설치 ASAR, 최종 Mi:dm blob, STT 최종 모델, GPT-SoVITS 자산, 개인 음성 및
  기존 `airi_docs/patches/` 파일은 변경하지 않았다.

## 보존한 연구·기술 판단 자산

### Git 추적 자산

- `airi_docs/evidence/AIRI-CODEX-SESSION-INVENTORY-2026-08-14.json`
  - AIRI 작업을 만든 root session 13개, subagent session 503개, 총 516개의
    content-free 인덱스다.
  - prompt, response, credential은 복사하지 않았다. raw rollout은 기존
    `%CODEX_HOME%/sessions`에 그대로 남아 있다.
- `airi_docs/evidence/source-archives/AIRI-SOURCE-ARCHIVE-MANIFEST-2026-08-14.json`
  - unpublished upstream source port 두 계열의 thin Git bundle과 prerequisite
    commit을 고정한다.
  - TTS resampler의 서로 다른 중간 patch 6개를 byte-for-byte 보존한다.
  - 최종 런타임에는 채택하지 않은 authenticated loopback/Tailscale 원격 모델
    리허설 코드와 테스트를 `archived_not_deployed` 상태로 보존한다.
  - P0 Hugging Face metadata 수집 결과를 보존하되 weights·prompt·output은
    포함하지 않는다.
- 기존 로드맵, 후보 manifest, A/B 결과, 대화 검토와 native clean rerun 문서는
  과거 판단 근거이므로 삭제하지 않았다.
- canonical runtime patch 3계층은 기존 경로와 바이트를 유지했다. source
  branch를 현재 local-stack Git 역사에 직접 merge하지 않은 이유는 서로 다른
  upstream object history이고, 같은 기술이 이미 manifest-pinned patch layer로
  보존·검증되기 때문이다.

### Git에 넣지 않은 로컬 연구 자산

- 전체 A/B 결과의 scout-only 119개 파일을 main worktree의 ignored
  `ollama-proxy/eval/results/`에 덮어쓰기 없이 합쳤다. 같은 경로 26개는 SHA-256
  동일했고 충돌은 0개였다.
- TTS sample의 scout-only 9개 파일을 main worktree의 ignored `tts-samples/`에
  덮어쓰기 없이 합쳤다. 같은 경로 1개는 SHA-256 동일했고 충돌은 0개였다.
- review key, raw dialogue와 음성 파일은 공개 commit 대상이 아니므로 계속
  ignored 로컬 자산으로만 보존한다.
- scout STT cache 8개는 main의 동일 상대 경로·동일 SHA-256 사본으로 전부
  확인했으므로 별도 복사하지 않았다.

## 제거한 재생성 가능 자산

### 로컬 LLM

- Ollama 비최종 태그 11개:
  `granite3.3:2b`, `phi4-mini:3.8b-q4_K_M`,
  `ministral-3:3b-instruct-2512-q4_K_M`, `granite4:3b`, Kanana Q8,
  `gemma3:4b`, `qwen3.5:4b-q4_K_M`, `qwen3:4b`,
  `exaone-airi-runtime:2.4b`, `exaone-airi:2.4b`, `exaone3.5:2.4b`.
- `%TEMP%`의 Mi:dm/Motif native snapshot, Motif HF cache, 평가 전용 Python
  환경, `airi-llm-ab`, 원격 도구 다운로드 사본과 Motif 로그.
- 삭제된 디렉터리의 논리 파일 크기 합계는 hardlink 중복을 포함하므로 실제
  회수 용량과 같지 않다. 특히 Mi:dm과 Motif의 원본/snapshot weight는 각각
  hardlink를 공유했다.

### 비최종 TTS 실험 환경

- 최종 기술 스펙은 GPT-SoVITS이므로 Chatterbox와 Qwen3-TTS 두 구현의
  재생성 가능한 `.venv` 3개와 Hugging Face model cache 3개, 서버 로그를
  제거했다.
- source snapshot과 음성·비교 sample은 연구 자산이므로 유지했다.
- BGE-M3, KURE, STT, GPT-SoVITS cache와 자산은 현행 stack 또는 로드맵에
  필요하므로 제거하지 않았다.

### 분산 개발 디렉터리

- 검증 clone 두 개는 84개 leaf 파일이 서로 byte-identical이고 모든 기술이
  staging `bf173f2` 또는 canonical patch layer에 보존됨을 확인한 뒤 제거했다.
- client/main source port와 staging commit은 source archive manifest의 bundle로
  보존한 뒤 등록 worktree 순서에 맞춰 제거했다.
- Python 3.12 audit venv는 최종 회귀 실행 후 재생성 가능 환경으로 제거했다.
- `airi-git-metadata-backup-20260805`는 약 22 MiB의 작은 provenance 자산이라
  유지한다.

## 복구·재현 경계

- 삭제한 후보 weight는 각 model usage manifest의 exact revision과 SHA-256으로
  다시 받을 수 있다. evaluation 결과와 판단 문서는 weight 없이 재검토할 수 있다.
- thin bundle은 manifest에 적힌 공개 upstream prerequisite commit이 필요하다.
- ignored 결과, review key, raw dialogue, 음성은 GitHub 복구 대상이 아니다.
  main 로컬 worktree에 합친 사본이 유일한 보존 경계다.
- raw Codex rollout은 `%CODEX_HOME%/sessions`가 보존 경계다. 이번 정리에서
  해당 저장소를 이동하거나 삭제하지 않았다.

## 검증

- `test-current-checkpoint.ps1`: PASS
- Python 3.12 core suite: `1061 passed, 2 skipped, 916 subtests passed`
- source bundles: prerequisite를 가진 upstream 저장소에서 `git bundle verify` PASS
- archive JSON parse: PASS
- `git diff --check -- . ':(exclude)airi_docs/patches/*.patch'`: PASS
- main push commit: `26b0a935fdd231f00e21479c2f8b857ac37f67d9`
- Actions run `31807207795`: 13개 job 전부 steps 0으로 종료. 테스트 실패가
  아니라 기존 runner allocation/결제 차단 상태이므로 위 로컬 전체 suite와
  checkpoint를 검증 근거로 사용한다.

최종 확인에서 로컬 project root의 AIRI 관련 항목은 main repository와 작은 Git metadata
backup만 남았다. main 단일 worktree, 최종 Mi:dm 두 태그, Tailscale 비활성,
임시 모델 service/listener 없음도 확인했다.
