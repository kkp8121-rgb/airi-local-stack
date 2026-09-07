# AIRI Korean Local Stack

Windows에서 공개된 AIRI 연동 작업을 로컬 LLM, 한국어 음성 합성, 로컬 음성 인식과 연결하는 작업 저장소입니다. AIRI 앱 자체를 포크해 배포하는 저장소가 아니라, 프록시·런처·검증 코드와 제3자 소스 스냅샷을 함께 보관한 공개 미러입니다.

## AI 검토자를 위한 안내

먼저 공개 트리의 코드와 문서 링크를 읽고, 파일에 있는 사실·과거 실행 기록·작성자의 자기보고를 구분해 주세요. 공개 스냅샷에 없는 최신 로컬 기억 구현이나 PC 환경은 공개 코드의 근거가 아닙니다. 사람은 연결 목표와 검증 기준을 정하고 결과를 판단했으며, AI는 코드 작성·수정과 검증 보조에 활용되었습니다.

## 공개본 읽는 순서

1. [현재 문서 색인](https://github.com/kkp8121-rgb/airi-local-stack/blob/main/airi_docs/AIRI-CURRENT-DOCS-INDEX-2026-08-10.md)에서 문서 상태와 공개 범위를 확인합니다.
2. [로컬 스택 런처](https://github.com/kkp8121-rgb/airi-local-stack/blob/main/start-airi-local-stack.ps1)에서 기본값과 선택 기능을 읽습니다.
3. [ollama-proxy](https://github.com/kkp8121-rgb/airi-local-stack/tree/main/ollama-proxy), [GPT-SoVITS 연결](https://github.com/kkp8121-rgb/airi-local-stack/tree/main/gpt-sovits), [STT 코드](https://github.com/kkp8121-rgb/airi-local-stack/tree/main/stt)의 실제 진입점을 확인합니다.
4. [THIRD-PARTY-SOURCES.md](https://github.com/kkp8121-rgb/airi-local-stack/blob/main/THIRD-PARTY-SOURCES.md)에서 원본 저장소와 기준 커밋을 대조합니다.

## 공개 트리의 구성

| 경로 | 공개 역할 |
|---|---|
| `ollama-proxy/` | 로컬 모델 프록시, 기억·지식·대화·평가 코드 |
| `gpt-sovits/` | 한국어 TTS 실행·프록시·검증 스크립트 |
| `stt/` | faster-whisper 기반 음성 인식 코드와 벤치마크 |
| `chat-ingress/`, `broadcast-director/` | 입력 경계와 방송 제어 실험 코드 |
| `airi_docs/` | 상태, 설계, 실험과 인계 문서 |
| `start-airi-local-stack.ps1` | 로컬 서비스 시작 옵션과 기본값 |

모델 가중치, 개인 음성 자료, 가상환경, 런타임 DB와 로그는 공개 파일에 포함하지 않습니다. AIRI 데스크톱 앱은 별도 설치 대상입니다. 외부 채팅·검색과 일부 평가 기능은 런처 옵션에서 명시적으로 켜야 합니다.

## 확인할 공개 코드

- [ollama-proxy/airi_memory.py](https://github.com/kkp8121-rgb/airi-local-stack/blob/main/ollama-proxy/airi_memory.py): 프록시에서 사용하는 기억 처리 코드
- [ollama-proxy/requirements.txt](https://github.com/kkp8121-rgb/airi-local-stack/blob/main/ollama-proxy/requirements.txt): 프록시 Python 의존성 목록
- [gpt-sovits/](https://github.com/kkp8121-rgb/airi-local-stack/tree/main/gpt-sovits): TTS 실행·프록시·계약 테스트 진입점
- [stt/](https://github.com/kkp8121-rgb/airi-local-stack/tree/main/stt): 음성 인식 코드와 벤치마크
- [NEXT-SESSION.md](https://github.com/kkp8121-rgb/airi-local-stack/blob/main/NEXT-SESSION.md): 공개된 다음 작업 인계 문서

각 경로는 공개 트리에 있는 파일 또는 디렉터리의 존재를 가리킵니다. 파일에 적힌 실험 결과는 작성 시점과 조건을 함께 읽고, 현재 동작을 주장할 때는 같은 조건으로 재실행해야 합니다.

## 실행과 검증

Windows에서 필요한 모델과 제3자 런타임을 준비한 뒤 다음 런처를 사용합니다.

```powershell
.\start-airi-local-stack.ps1
.\stop-airi-local-stack.ps1
```

공개 트리에는 `ollama-proxy`·`stt`·TTS 하위의 테스트와 평가 스크립트가 있지만, 이 README 갱신에서 전체 스택을 실행하거나 마이크 연속 대화를 재현하지 않았습니다. 따라서 파일 존재와 과거 기록을 실제 실행 성공으로 확장해 설명하지 마십시오. 최신 로컬 진행 기록과 공개본의 차이는 문서 색인과 커밋 트리를 기준으로 다시 확인해야 합니다.

공개 스냅샷의 문서에는 여러 실험 단계와 계획이 함께 남아 있을 수 있습니다. `진행중/`, `진행예정/`, `완료/`, `아카이브/`의 의미는 문서 색인에서 확인하고, 계획 문서를 구현 완료 증거로 읽지 마십시오.

## 원본과 라이선스 범위

공개 트리에는 `chatterbox/LICENSE`, `faster-qwen3-tts/LICENSE`, `Qwen3-TTS-Openai-Fastapi/LICENSE`가 각 하위 소스에 있습니다. 원본 저장소·기준 커밋은 [THIRD-PARTY-SOURCES.md](https://github.com/kkp8121-rgb/airi-local-stack/blob/main/THIRD-PARTY-SOURCES.md)에 기록되어 있습니다.

## 기여와 AI 활용

저는 HTML 테스트 화면의 결과를 확인하고 문제를 지적하며 수정 방향과 다음 검증 항목을 정했습니다. AI는 코드 작성과 수정에 활용했습니다. 공개 저장소에는 이 연결 작업과 검증 문서의 결과를 정리했습니다.

이 README의 공개 범위는 AIRI 원본의 전체 기능이나 설치 패키지의 완성도를 대신 설명하지 않습니다. 원본 AIRI는 [공식 문서](https://airi.moeru.ai/docs/en/)와 [원본 저장소](https://github.com/moeru-ai/airi)에서 확인하고, 이 저장소의 연결·패치·평가 코드와 구분해 읽어 주세요.
