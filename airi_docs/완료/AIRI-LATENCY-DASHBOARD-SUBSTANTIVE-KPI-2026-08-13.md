# AIRI 지연 대시보드 substantive KPI 정합성 — 2026-08-13

## 판정

상단 대시보드의 기존 계산은 raw `playback.start`를 사용해 heuristic/mixed
상관 turn도 셀 수 있어, 상단은 통과로 보이는 반면 per-turn 행은 heuristic
포함 및 substantive KPI 보류를 정확히 표시하는 모순이 가능했다. 새
`latency-monitor/dashboard-metrics.mjs`는 상단 표본을 substantive playback
KPI로 한정한다. raw stage scalar는 진단용으로만 남는다.

## 수집 계약

표본은 non-synthetic STT, cloud-search LLM, 명시적 STT·LLM·playback 상관을
모두 요구한다. `vadEndWaitMs`는 유한하고 0 이상이어야 하며,
`stt.start <= llm.content <= kpi.substantive_playback_start`와 유한한
nonnegative 결과를 엄격히 요구한다. 상단의 newest-five, P50, P95, worst,
pass/fail은 이 substantive KPI 표본만 사용한다.

`/dashboard-metrics.mjs`는 고정 경로로 제공되며, 대시보드는 이 모듈의
`summarizeAcceptance`를 import한다.

## 검증과 운영 경계

- Node dashboard metrics: **5/5 PASS**
- latency Python: **32 passed + 15 subtests PASS**
- checkpoint: **PASS**; independent review: **PASS**
- 별도 전체 Python 3.12 실행: `python -m pytest -q ollama-proxy
  test_latency_trace.py test_start_airi_background.py latency-monitor stt` —
  **875 passed, 1 skipped, 738 subtests, 7 warnings (49.88s)**

이는 라이브 마이크/런타임 측정이 아니다. STT는 user-deferred/OFF 상태이며,
설치 AIRI·서비스·모델은 변경하지 않았다. 물리적 5-turn gate도 닫지 않는다.
