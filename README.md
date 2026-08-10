# AIRI Korean Local Stack

Windows에서 AIRI 0.11.3을 로컬 LLM, 한국어 음성 합성, 로컬 음성 인식과 연결하기 위한 작업 저장소다.

현재 텍스트 대화, EXAONE 기반 로컬 LLM, GPT-SoVITS v2ProPlus 기반 TTS, CUDA faster-whisper STT, Codex 구독 기반 웹 검색과 Live2D 립싱크·표정 반응이 동작한다. 검색 요청은 즉시 캐시 음성으로 반응한 뒤 실제 검색 결과를 같은 답변에 이어 붙인다. **설치 AIRI 자동 재생 검증은 1.184초를 기록했지만 합성 STT 시각을 사용했으므로, 실제 사용자 마이크 연속 5회 검증 전에는 2초 목표 완료로 간주하면 안 된다.**

## 구성

| 구성 요소 | 경로/포트 | 상태 |
|---|---|---|
| Ollama | `127.0.0.1:11434` | 동작 |
| AIRI용 Ollama/검색 프록시 | `ollama-proxy/`, `127.0.0.1:11435` | 즉시 SSE + Codex 구독 live search 동작 |
| GPT-SoVITS v2ProPlus TTS | `gpt-sovits/`, API `127.0.0.1:9880`, 프록시 `127.0.0.1:8880` | 혼합 언어·선반응 WAV 캐시 동작. 동시 요청은 오디오 중첩 방지를 위해 의도적으로 직렬화(전역 락) — Phase 2+5 전까지 유지 |
| faster-whisper STT | `stt/`, `127.0.0.1:8890` | CUDA/float16, 고유명사 보정, 사용자 5회 검증 대기 |
| AIRI 데스크톱 | 별도 설치, 0.11.3 | 텍스트/LLM/TTS 재생/Live2D 동작 |

## 시작과 종료

```powershell
.\start-airi-local-stack.ps1
```

스택 종료:

```powershell
.\stop-airi-local-stack.ps1
```

AIRI 애플리케이션 자체는 Windows에 별도로 설치되어 있으며 위 스크립트와 별도로 실행한다.

## 다음 세션이 먼저 읽을 문서

1. `airi_docs/AIRI-CURRENT-DOCS-INDEX-2026-08-10.md` — **현재 문서 색인 및 최신 진입점**
2. `airi_docs/AIRI-SERVER-CHANNEL-PLAYBACK-CHECKPOINT-2026-08-10.md` — 현재 source/patch 인수인계
3. `airi_docs/AIRI-LOCAL-STACK-REVIEW-2026-08-07.md` — 코드 감사 보고서 (결함 근거·실측치)
4. `airi_docs/AIRI-CLOUD-SEARCH-REACTION-2026-08-07.md`
5. `NEXT-SESSION.md`

## Git에 포함하지 않는 항목

개인 음성 원본·추출 음원·생성 샘플, 다운로드 모델 가중치, Python 가상환경, 로그와 화면 캡처는 의도적으로 제외한다. 현재 PC의 로컬 파일은 삭제하지 않으며 실행에는 계속 사용할 수 있다. 새 PC에서 복원할 때는 모델과 개인 음성 참조 파일을 다시 준비해야 한다.

## 제3자 소스

이 저장소에는 작업 당시 사용한 세 프로젝트의 소스 스냅샷과 로컬 수정이 포함된다. 원본 저장소와 기준 커밋은 `THIRD-PARTY-SOURCES.md`에 기록했다. 각 프로젝트의 라이선스 파일을 유지한다.
> Current handoff: use `airi_docs/AIRI-CURRENT-DOCS-INDEX-2026-08-10.md` and `airi_docs/AIRI-SERVER-CHANNEL-PLAYBACK-CHECKPOINT-2026-08-10.md`. The older 2026-08-07 handoff documents are historical snapshots.
