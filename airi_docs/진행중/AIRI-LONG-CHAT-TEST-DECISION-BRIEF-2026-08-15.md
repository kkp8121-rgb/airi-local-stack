# AIRI 장시간 방송 채팅 테스트 판단서 — 2026-08-15

## 한눈에 보는 결론

현재 배치는 **장시간 채팅 평가 기반과 Mi:dm 출력 경계 준비 완료**로는 조건부
승인할 수 있다. 자동 회귀, ACK 분리, 비스트리밍 빈 응답 방지, 로컬 Mi:dm 합성
1턴 연결은 통과했다.

그러나 사용자가 요청한 **실제 장시간 방송 채팅에서 AIRI가 무엇을 골라 어떻게
대응하는지에 대한 실증은 아직 0%**다. 승인된 실제 캡처와 동일 입력 OFF/ON 비교,
사람 검수 결과가 하나도 없으므로 장시간 캠페인 완료, epistemic gate 운영 ON,
B4c 방송 계약 운영 ON을 승인할 근거는 아직 없다.

권고 판단은 다음과 같다.

| 판단 대상 | 권고 | 이유 |
|---|---|---|
| 장시간 replay 기반 구현 | **조건부 승인** | 최신 로컬 회귀와 체크포인트 통과 |
| Mi:dm 출력 경계 수정 | **승인** | stream ACK 분리와 non-stream nonempty 재확인 |
| 실제 장시간 채팅 성능 | **판단 보류** | 승인 실제 캡처 0건 |
| epistemic-confidence 운영 ON | **채택 금지 유지** | OFF/ON 실제 비교와 사람 검수 없음 |
| B4c 방송 계약 운영 ON | **채택 금지 유지** | 기존 원격 실측은 raw 경로이며 운영 proxy 종단 증거가 아님 |
| B1b 공개 방송/TTS 종단 완료 | **미완료** | 실제 screened event 주입과 공개 wire/TTS 증거 없음 |

## 1. 이번에 다시 실행한 로컬 검증

기준 커밋은 `8192828 fix: preserve replay output boundaries`이다. 2026-08-15에
현재 작업 트리에서 아래 검증을 다시 실행했다. CI는 billing 차단 중이므로 모두
dev PC 로컬 결과다.

| 검증 | 결과 | 해석 |
|---|---:|---|
| 장시간 채팅 replay unittest discovery | **73/73 PASS** | 승인·정규화·sampler·HMAC·campaign 계약 회귀 통과 |
| conversation-soak/ACK 경계 | **12/12 PASS** | audible ACK 분리, 본응답 scoring/history, fallback 판정 통과 |
| `test-current-checkpoint.ps1` | **PASS** | patch/source manifest, entrypoint, ASAR, Node 계약 통과 |
| 체크포인트 내 Node 계약 | **108/108 PASS** | sender 32, chat-ingress 47, director 24, latency 5 |

실행 명령:

```powershell
python -m unittest discover -s ollama-proxy/eval/chat_replay -p 'test_*.py'
python -m unittest discover -s ollama-proxy/eval -p 'test_*conversation_soak*.py'
.\test-current-checkpoint.ps1
```

첫 unittest 출력에 나타나는 `capture receipt must stay inside ...` 사용법 문구는
잘못된 경로를 의도적으로 거부하는 negative test의 stderr다. 전체 프로세스는
exit code 0이고 73개 테스트가 모두 통과했다.

## 2. 실제 로컬 Mi:dm 연결 확인

임시 loopback-only 11435 proxy에서 `midm-airi:2.0-mini`, 고정 digest
`92a9ba2ee8c79ba46c22907b50b15eb1ca55c94d04230eca73917936ef36485f`,
`num_ctx=2048`을 확인했다. memory, knowledge, evaluation, moderation, input
screening, epistemic confidence는 모두 OFF였다.

합성 greeting 1턴 결과:

| 항목 | 결과 |
|---|---:|
| 완료 여부 | PASS |
| transport error | 0 |
| audible ACK | `local`, 1회 |
| ACK 제거 후 control 잔존 | 없음 |
| 실질 응답 판정 | PASS |
| 스트리밍 완료 지연 | 594.1 ms |
| 비스트리밍 응답 | nonempty, control-free |
| 사람 검수 | PENDING |

이는 출력 경계 readiness smoke다. 장시간 채팅 품질, 실제 시청자 맥락 추적,
B1b/TTS 종단 또는 운영 gate 채택 증거로 확대 해석하면 안 된다. 검증 뒤 소유한
임시 11435 proxy는 종료했다.

## 3. 알려진 예외

별도로 실행한 전체 `test_ollama_proxy.py`는 Python 3.14 환경에서 **296/297**였다.
변경 경로 집중 테스트 4개는 모두 통과했다. 남은 1건은 기존의 타이밍 민감
watchdog metadata 테스트
`test_first_raw_watchdog_closes_response_when_send_already_completed`이며, 이번
ACK/non-stream 수정 경로의 기능 실패로 분류하지 않았다.

다만 완전한 green으로 과장하지 않는다. CI 기준 Python은 3.12지만 현재 활성
Python 3.14 환경에는 pytest가 없어 이번 배치에서 core pytest 전체를 다시 실행하지
못했다. GitHub Actions도 billing 차단 때문에 실행 근거로 사용할 수 없다.

## 4. 이전 B4c 원격 실측 — 별도 참고 근거

2026-08-14 원격 실측은 단발 76턴과 멀티턴 96턴, 합계 172턴에서 transport 실패가
0이었다. B4c 계약 ON은 단발 자동 마커에서 방송통과 0%→50%, 반말 8%→66%,
길이규격 55%→84%로 개선됐다.

하지만 다음 한계가 확인됐다.

- raw 원격 서버 직접 호출이라 운영 11435 proxy 스타일 게이트가 없었다.
- 멀티턴에서 첫 턴 앵커 고정 현상이 재현돼 prompt 계약만으로 불충분했다.
- 후원 호명은 ON에서도 0/2였다.
- 비스트리밍 완료 시간만 측정했고 실제 TTFT/TTS는 측정하지 않았다.

따라서 이 결과는 B4c prompt 효과의 근거이지 현재 요청한 장시간 실제 채팅
campaign이나 운영 ON 채택 근거가 아니다.

## 5. 실제 장시간 캠페인 현황

사용자가 요청한 평가 단위는 단발 3문장이 아니라 연속 30~120분 방송 채팅이다.
현재 캠페인 요구량과 확보량은 다음과 같다.

| 필수 증거 | 최소 요구 | 현재 확보 |
|---|---:|---:|
| 익명 source | 3개 | 0개 |
| source별 서로 다른 방송 국면 | 각 2개 이상 | 0개 |
| 연속 30~120분·300~20,000 event 캡처 | 총 6개 이상 | 0개 |
| 동일 redacted sequence Mi:dm OFF/ON | 총 12개 이상 | 0개 |
| private 사람 검수 | 모든 전달·응답 대상 | packet 없음, 0% |
| content-free campaign aggregate | 1개 | 없음 |
| B1b→11435→style gate→public wire/TTS | 종단 증거 1세트 이상 | 없음 |

현재 저장소에 있는 장시간 관련 결과는 합성 fixture와 준비도 회귀다. 실제 방송
채팅 원문, 승인된 real capture, actual OFF/ON campaign 결과로 간주할 수 없다.

## 6. 실제 실증을 시작하기 위한 조건

첫 실측 수집기는 종료된 YouTube 다시보기 화면을 scrape하지 않고 **현재 LIVE의
공식 API**만 사용한다. 시작 전 아래 입력이 모두 필요하다.

1. 방송인·플랫폼의 서면 허가 또는 사용자가 권리를 보유한 방송
2. 허가가 특정 video/channel, 30~120분 구간, 평가 목적, 삭제 기한을 포함한다는
   운영자 확인
3. 권한 있는 현재 YouTube LIVE와 API key
4. 캡처별 익명 `channel_a`~`channel_c` 및 서로 다른 phase 지정
5. 자동 삭제 뒤 사람 privacy 검수
6. 동일 캡처를 gate OFF와 ON으로 각각 재생할 운영자 결정
7. 모든 대응을 private packet에서 사람이 검수할 시간

공개 VOD에 Chat Replay UI가 보인다는 사실만으로는 수집·저장·모델 평가 허가가
성립하지 않는다. 치지직과 SOOP도 공식 OAuth/SDK 및 해당 방송 권한 없이는 실제
캡처 source로 승격하지 않는다.

## 7. 사용자 판단 선택지

### 선택 A — 현재 배치를 기반 완료로 승인 — **사용자 선택 2026-08-18**

추천한다. 의미는 “장시간 실증을 안전하게 실행할 수 있는 코드와 출력 경계가
준비됐다”까지다. 실제 성능 완료나 운영 gate ON은 승인하지 않는다.

### 선택 B — 실제 장시간 캠페인 착수 승인 — **미선택 (2026-08-18)**

권한 있는 방송/API key/provenance가 준비된 뒤 실행한다. 한 source만 먼저 실행한
결과는 pilot이며, 3 source×2 phase×OFF/ON을 모두 채우기 전 최종 campaign으로
판정하지 않는다.

### 선택 C — 운영 gate ON 채택 — **미선택 (2026-08-18, 채택 금지 유지)**

현재는 권고하지 않는다. 실제 paired campaign과 사람 검수에서 critical failure가
0임을 확인한 뒤 별도로 판단해야 한다. runner와 campaign aggregator도 스스로
운영 설정을 승격하지 않는다.

## 최종 권고

**A는 승인, B는 외부 입력이 준비되는 즉시 착수, C는 보류**가 현재 증거에 맞는
판단이다. 로드맵 상태는 G3/B3-f의 기반 작업은 진전됐지만 실제 장시간 실증이
남은 `[~]`로 유지한다.

**사용자 결정(2026-08-18): `long_chat=A`.** 기반 완료만 승인됐고 B 캠페인 착수와
C 운영 gate ON은 선택되지 않았다. 로드맵 `[~]` 유지도 그대로다.

## 근거 문서

- `완료/AIRI-MIDM-REPLAY-OUTPUT-BOUNDARY-2026-08-15.md`
- `진행예정/AIRI-KOREAN-LIVE-CHAT-REPLAY-PLAN-2026-08-15.md`
- `완료/AIRI-AUTHORIZED-CHAT-REPLAY-CAMPAIGN-CONTROL-2026-08-15.md`
- `완료/AIRI-YOUTUBE-LIVE-CHAT-CAPTURE-FOUNDATION-2026-08-15.md`
- `완료/AIRI-YOUTUBE-LIVE-CAPTURE-PREPARATION-2026-08-15.md`
- `완료/AIRI-B4C-CONTRACT-AB-2026-08-14.md`
- `로드맵/AIRI-ROADMAP-STATUS.md`
