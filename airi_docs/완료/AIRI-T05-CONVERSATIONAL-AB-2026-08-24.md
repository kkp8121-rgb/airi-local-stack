# T-05 대화체 A/B 청취 샘플 — 126번 vs 현행 일본어 참조 (2026-08-24)

2026-08-24 결정 폼 회신 `t05=샘플요청`의 산출물이다. 2026-08-12 판정("126번은 낭독조 —
감정 있는 대화체 문장으로 재합성해 A/B할 때 우선 사용")을 이행했다. **청취 비교용일 뿐
운영 승격·음성 변경이 아니며**, 현행 운영 음성은 그대로다.

## 무엇을 합성했나

파일럿 24건(`airi_broadcast_response_pilot_pending.jsonl`)에서 감정·이벤트 맥락이 있는
AIRI target 4문장을 골라, 동일 문장을 두 참조 음성으로 각각 합성했다.

| ID | 이벤트 | 길이 |
|---|---|---|
| `brpilot-donation-ritual` | 의례 후원 감사 | 52자 |
| `brpilot-selected-playful-tease` | 장난 채팅 받아치기 | 135자 |
| `brpilot-donation-anonymous` | 익명 후원 반응 | 74자 |
| `brpilot-greeting-opening` | 오프닝 인사 | 74자 |

| arm | 참조 | prompt_lang | 비고 |
|---|---|---|---|
| `ja-current` | `chatterbox/voices/airi-reference.wav` | ja | 현행 운영 프록시 기본값과 동일 payload(비스트리밍만 다름) |
| `ko-126` | `tts-samples/t05-zeroth-ko-2026-08-12/reference-126-126_003_2800.wav` | ko | 참조 SHA `2e1552fc…7521`을 합성 전 재검증 |

엔진: GPT-SoVITS v2ProPlus `api_v2.py`(127.0.0.1:9880, 이 작업 전용으로 기동 후 종료).
청취본은 2026-08-12 배치와 동일한 `loudnorm=I=-20:LRA=7:TP=-1.5`, mono 32 kHz.

## 산출물 (WAV는 gitignored — 이 PC 로컬 전용)

`tts-samples/t05-conversational-20260824/` — `<id>--<arm>-raw.wav` + `-listen.wav` 8쌍과
`provenance.json`(요청 payload·참조 SHA·파일별 bytes/seconds/RMS/peak/SHA-256·ffmpeg 명령).
청취는 `-listen.wav`를 사용한다. 길이 9.0~22초, RMS 0.08~0.12 범위.

## 실행 receipt

- backend 기동 → HTTP ready 6초 → 8/8 합성 exit 0 → backend 종료, `api_v2` PID 0·9880 미청취
- 스크립트는 참조 SHA 불일치·비RIFF 응답·HTTP 오류에서 fail-closed, 기존 출력 디렉터리 거부
- 운영 프록시(8880)·Ollama·설치 AIRI는 미접촉, 서비스 설정 변경 0

## 사용자 청취 안내

각 문장을 `ja-current` → `ko-126` 순으로 듣고 다음 축으로 판정해 주시면 된다.

1. 대화체에서도 126번이 여전히 낭독조인가, 감정이 붙는가
2. 한국어 발음 명료도 (현행 일본어 참조는 "일본어 화자의 한국어" 느낌이 남는 것이 기존 평가)
3. 후원 감사~장난 받아치기의 톤 변화가 자연스러운 쪽
4. 방송 개성: 어느 쪽이 "AIRI답게" 들리는가

판정 선택지: **126 승격 검토 진행 / 현행 유지 확정 / 다른 문장·조건으로 재합성**.
어느 쪽이든 운영 반영은 별도 승인 절차를 거친다.
