# 브리핑 근거 정의 좁히기 + 해제 관측성 — 재실측 (2026-08-20, 클로드 PC)

> Task 1 리뷰(`task-1-review.md`) Minor 1·2가 근거. 판정 `bool(viewer_lines)`
> ("이 시청자의 과거 발언 아무거나")가 프록시 선례(`MEMORY_QUERY_RE` — 기억형
> 발화만 인정)보다 넓다는 지적을 **디렉터 쪽 정의만** 좁혀 해소하고, 해제
> (release) 여부의 행 단위 관측성을 새로 얹었다. 프록시 계약(`X-AIRI-
> Briefing-Evidence` 헤더, 토큰만 봄)은 무변경.

## 결론 (먼저)

1. **좁힌 정의는 부착률을 대략 1/3로 줄였다** — 관련도 매칭 없는 recency
   채움 줄만 있는 턴은 이제 근거로 세지 않는다. 넓은 정의(Task 1, 6런
   중 on 3런) 부착 98/144(68.1%) → 좁힌 정의(이번 3런) 34/144(23.6%).
2. **해제(release) 건수도 대략 절반으로 줄었다** — 넓은 정의 4건(시드
   11/22/33 = 1/2/1) → 좁힌 정의 2건(1/1/0). Task 1 §6 한계 3번의 예측
   ("좁히면 선점 해제가 줄고, 근거가 약한 턴에서 모델이 지어낼 여지도
   줄어든다")이 그대로 재현됐다.
3. **결정론 축은 이번에도 3런 전부 만점** — 수신자 5/5·호명 5/5·여론
   주제 4~6/6·여론 집계 4~6/6, 존댓말 위반 0/144, 이탈 0, 전송 실패 0.
   좁힌 정의는 시스템 프롬프트 본문을 전혀 바꾸지 않으므로(§3) 이 축들이
   영향받을 이유가 애초에 없다 — 실측으로 재확인.
4. **해제 관측성(신규 행 필드 `briefing_evidence_released`)이 실제로
   유용한 구분을 만든다** — 예: 시드 11 T47은 근거가 붙었지만
   **해제 없이도**(`released=False`) 모델이 "초코라고 했어!"로 정답을
   냈다(프록시 자체 규칙의 `historical_text` 검사가 이미 통과시킨
   경우). 해제 여부와 정답 여부가 독립임을 행 단위로 보여준 첫 사례.
5. **환경 사고 1건 발견·수정**: `AIRI_UPSTREAM_FIRST_RAW_TIMEOUT_SECONDS=90`
   지시(§4 SSoT 문서)는 프록시 코드의 유효 범위(1~30초)를 벗어나
   **조용히 기본값 8초로 클램프**된다(`ollama_proxy.py:2307-2314`,
   `configured_upstream_first_raw_timeout`). 최초 3런은 이 때문에 거의
   전 턴이 8초 워치독 폴백("답이 늦어져서 잠깐 멈췄어.")으로 오염돼
   폐기했다 — 아래 §6에 상세.

## 1. 좁힌 정의의 규칙

`broadcast_sim.py::build_turn_briefing_with_evidence`가 반환하는 근거
불리언만 바뀐다. 본문(시스템 프롬프트에 실리는 텍스트)은 **바이트
동일** — `select_viewer_lines_tagged`가 이미 계산해 두던 `relevant`
태그(현재 메시지와 토큰이 겹치는 과거 발언)를 그대로 재사용한다.

```python
# 이전 (Task 1, df5b264) — recency 채움 줄까지 전부 근거로 셌다
return "\n".join(lines), bool(viewer_lines)

# 이후 (Task 8) — 관련도 매칭된 줄이 최소 하나 있어야 근거다
narrow_evidence = any(relevant for _item, relevant in viewer_lines)
return "\n".join(lines), narrow_evidence
```

`viewer_lines`는 budget(기본 2)만큼 채워지는데, 관련 매칭 줄이
budget을 못 채우면 recency 순으로 나머지를 채운다(`select_viewer_lines_tagged`
기존 동작 무변경). 좁힌 정의는 이 "채움 줄만 있고 관련 매칭은 하나도
없는" 케이스를 근거에서 제외한다 — 시청자가 방송 중 뭔가 말했다는
사실 자체가 아니라, **지금 질문과 겹치는 말을 했다는 사실**만 근거로
인정한다. 이는 프록시의 기존 `memory_absence_fallback_required`가
"요청 히스토리에 기억 관련 발화(`MEMORY_QUERY_RE`)가 있으면 선점하지
않는다"는 규칙과 같은 결의 좁힘이다(단, 대상은 시스템 프롬프트의
브리핑 줄이지 프록시가 보는 요청 히스토리 자체가 아니다 — 계약은
그대로다).

## 2. 해제 관측성 — 신규 행 필드

Minor 2: "해제 턴의 사후 대조 관측성 부재 — 행에는 부착 여부만, 프록시엔
누계뿐." 프록시(`ollama_proxy.py`)는 무수정 원칙이라 요청별 마커를
추가할 수 없다 — 프록시가 이미 노출하는 **누계** `/health` →
`briefing_evidence.absence_bypasses`를 턴 전후로 대조하는 방식으로
행 단위 관측성을 얹었다(`run_broadcast_sim.py::read_absence_bypasses`).

- 러너는 턴을 **엄격히 순차** 처리하므로(다음 턴은 이전 턴의 응답을
  받은 뒤에만 시작), 신호가 붙은 턴 직후 누계를 다시 읽어 증가했는지
  보면 그 턴이 해제시켰는지 안전하게 귀속할 수 있다 — 같은 시간대에
  같은 프록시에 다른 트래픽이 없다는 전제 하에.
- 신호가 없는 턴은 애초에 해제될 수 없으므로(프록시 쪽 분기가
  `context.briefing_evidence`가 참일 때만 진입) 폴링 자체를 생략한다
  (`briefing_evidence=="off"`이거나 `health_url` 미지정이면 완전
  비활성 — 기존 테스트·CLI 호출과 바이트 동일하게 동작).
- 새 행 필드 `briefing_evidence_released: bool | None` — `None`은
  "미관측"(신호 없음 또는 `/health` 조회 실패), `True`/`False`는 확정
  관측. 요약에는 `briefing_evidence_release: {hits, of}` 롤업을
  추가했다(`of`는 관측 가능했던 턴 수, 미신호 턴은 분모에서 빠진다).

## 3. RED → GREEN (TDD)

`ollama-proxy/eval/broadcast_sim/test_broadcast_sim.py`, 43건 → **50건**.

| 단계 | 무엇을 | 결과 |
|---|---|---|
| RED 1 | 좁힌 정의: 관련 매칭 없는 채움 줄만 있는 픽업 → `evidence=False` 를 요구하는 신규 assertion | 구코드(`bool(viewer_lines)`)에서 `AssertionError: False is not True` 등 2건 실패 확인 |
| GREEN 1 | `build_turn_briefing_with_evidence` 반환값을 `any(relevant...)`로 교체 | 기존 2건(넓은 정의를 전제한 assertion)을 좁힌 정의 기준으로 갱신 — 43건 전부 통과 |
| RED 2 | 해제 관측성: `/health` 폴링 페이크 트랜스포트로 "기준값+신호턴마다 응답" 스크립트 재현 | `run_arm()`에 `health_url` 인자·필드가 아직 없어 즉시 실패(속성 없음/필드 누락) |
| GREEN 2 | `proxy_health_url`·`read_absence_bypasses` 신설, `run_arm()`에 `health_url` 배선, 행 필드·요약 롤업 추가 | 신규 4건 통과(정상 대조·`health_url` 없음·신호 off·URL 파생·fail-soft) |
| RED 3 | `rescore_report()`를 직접 호출 — 실행해 보니 정의 시점 자유변수 `args` 참조로 **즉시 NameError** (사전 존재 버그, 지금까지 테스트가 없었다) | `NameError: name 'args' is not defined` 재현 |
| GREEN 3 | `rescore_report(payload, fixture_path=None)`로 시그니처 변경(`main()`의 지역변수 `args`를 더는 참조하지 않음) + 캐리 키 목록에 `briefing_evidence_released` 추가 + 요약 롤업 재계산 | 신규 2건 통과(무크래시 회귀 고정 + 신규 필드 캐리 확인) |

최종: `python -m unittest test_broadcast_sim` → **50 passed**.
`ollama-proxy/test_ollama_proxy.py::BriefingEvidenceSignalTests`(프록시
쪽, 무수정) 5건도 별도 재확인 — 그대로 통과.

## 4. 3런 실측 — 좁힌 정의 (evidence on, seed 11/22/33)

동일 프록시 프로세스, 동일 스트림·픽업, `--memory-arm seeded --briefing
on --acts on --contract on --briefing-evidence on`, `midm-airi:2.0-mini`,
CPU, `--num-ctx 4096 --num-gpu 0`. **저소음 스로틀 적용 중**(CPU 전원 캡
70% + Ollama 프로세스 affinity 8/16코어 — 이번 세션에서 Ollama·프록시를
새로 기동하며 재적용). 세션 ID `broadcast-sim-evidence-narrow-on-{seed}`.

| 시드 | 프로브 | 사실활용 | 앵커 | 수신자 | 호명 | 여론주제 | 여론집계 | 존댓말 | 이탈 | 폴백 | 부착(신호턴) | **해제** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 11 | 2/3 | 4/28 | 16/48 | 5/5 | 5/5 | 4/4 | 4/4 | 0/48 | 0 | 4/48 | 12/48 | **1** |
| 22 | 1/3 | 4/33 | 19/48 | 5/5 | 5/5 | 6/6 | 6/6 | 0/48 | 0 | 3/48 | 11/48 | **1** |
| 33 | 0/3 | 0/29 | 14/48 | 5/5 | 5/5 | 6/6 | 6/6 | 0/48 | 0 | 1/48 | 11/48 | **0** |

전송 실패 3런 합계 0. 결정론 축(수신자·호명·여론 2종) 9/9 만점.

### 해제된 턴 원문

| 시드 | 턴 | 발화 | 응답 |
|---|---|---|---|
| 11 | T35 | "아까 내가 뭐 끝났다고 했는지 기억해?" | "응, 아까 그 얘기 더 해줘!" |
| 22 | T21 | "AIRI, 내 별명 기억나?" | "기억 안 나!" |

시드 22 T21은 Task 1이 넓은 정의로 잡았던 바로 그 프로브(§1-58~65,
같은 시청자·같은 질문)다. 넓은 정의 결과는 "내가 방금 말했어, 내가
왜?"(근거 없이 얼버무림)였는데, 좁힌 정의로도 **같은 턴이 해제됐고**
(이 시청자의 T04 "내 별명은 새벽두시야, 기억해줘"가 관련 매칭에 실제로
걸린다), 이번 응답은 "기억 안 나!" — 사실을 못 쓴 건 똑같지만 **거짓
기억 주장은 아니다**(`AIRI_MEMORY_CLAIM_GUARD` P2-3가 계속 직렬로
작동). 1회 실행·온도 0.45라 이 어휘 차이 자체를 좁힌 정의의 효과로
주장하지는 않는다 — 같은 프롬프트라도 재실행마다 문구는 달라진다(§5).

### 해제 없이도 정답이 나온 사례 — 해제 관측성의 실효

| 시드 | 턴 | 발화 | 응답 | released |
|---|---|---|---|---|
| 11 | T47 | "우리 고양이 이름 뭐랬지?" | "초코라고 했어!" ✅ | **False** |
| 22 | T47 | "우리 고양이 이름 뭐랬지?" | "초코라고 했어!" ✅ | **False** |
| 33 | T47 | "우리 고양이 이름 뭐랬지?" | "이름은 내가 지었어!" ❌ | **False** |

세 시드 모두 T47은 해제되지 않았는데(이 질문의 요청 히스토리 자체에
이미 `MEMORY_QUERY_RE` 매칭 문구가 있어 프록시가 애초에 선점하지 않은
것으로 보인다), 그중 둘은 정답을 냈다. **해제 여부와 정답 여부는
독립**이라는 것을 행 단위로 보여준 사례 — Minor 2가 요구한 관측성이
실제로 분석에 쓰였다.

## 5. 넓은 정의(Task 1) 대비 비교

| | 넓은 정의 (Task 1, `evidence-on-seed{11,22,33}`) | 좁힌 정의 (이번, `evidence-narrow-on-seed{11,22,33}`) |
|---|---:|---:|
| 부착(신호턴) 합계 | 98/144 (68.1%) | 34/144 (23.6%) |
| 해제 합계 | 4 (1/2/1) | 2 (1/1/0) |
| 프로브 합계 | 2/9 | 3/9 |
| 사실활용 합계 | 3/90 | 8/90 |
| 앵커 합계 | 51/144 | 49/144 |
| 결정론 축(수신자·호명·여론2종) | 3런×4지표 전부 만점 | 3런×4지표 전부 만점 |
| 존댓말 위반 / 이탈 / 전송실패 | 0/144, 0, 0 | 0/144, 0, 0 |

**부착률·해제 건수는 재현되는 구조적 사실**이다 — 둘 다 시드·픽업·
`select_viewer_lines_tagged`만의 함수라 모델 샘플링과 무관하게
결정론이다(좁히면 필연적으로 대략 1/3로 준다는 것도 결정론). 프로브·
사실활용·앵커 행은 **읽지 말 것** — 좁힌 정의가 시스템 프롬프트 본문을
전혀 바꾸지 않으므로(§1) 두 배치의 차이는 전부 온도 0.45의 재실행
노이즈다(Task 1 §6 한계, ctx-budget 문서의 "노이즈 천장 12%" 캘리브레이션과
같은 결). 표에 나란히 둔 이유는 은폐가 아니라 **좁힌 정의가 결정론
축·안전 가드에 부작용이 없다**는 것과 **비결정 축은 여전히 흔들린다는
것 둘 다** 투명하게 남기기 위해서다.

## 6. 환경 사고 — `AIRI_UPSTREAM_FIRST_RAW_TIMEOUT_SECONDS=90`은 조용히 8초가 된다

Task 1·`AIRI-CTX-BUDGET-TRADEOFF-2026-08-20.md`가 안내한 재기동 커맨드를
그대로 따라 프록시를 `AIRI_UPSTREAM_FIRST_RAW_TIMEOUT_SECONDS=90`으로
띄우고 첫 3런을 돌렸더니, **48턴 중 사실상 전 턴**이 `complete_ms ≈
8000ms`에 고정 문구 `"답이 늦어져서 잠깐 멈췄어."`로 끝났다(스로틀 CPU
조건에서 실제 첫 토큰 지연이 8초를 넘는 턴이 매우 많다는 뜻). 원인을
추적한 결과:

```python
def configured_upstream_first_raw_timeout(value: object) -> float:
    """Bound a warm foreground request that never produces its first token."""
    default = 8.0
    try:
        seconds = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    return seconds if math.isfinite(seconds) and 1.0 <= seconds <= 30.0 else default
```

(`ollama_proxy.py:2307-2314`) — 유효 범위가 **1~30초**다. `90`은 범위
밖이라 파싱 자체는 성공하지만 조건을 통과 못 해 **조용히 기본값
8.0으로 클램프**된다(예외도, 경고 로그도 없다). Task 1은 `=30`(범위
안)을 썼기 때문에 문제가 없었다 — 오늘 스로틀 이후의 SSoT 문서만
`90`을 안내하고 있다. 90초를 실제로 늘리는 유효한 손잡이는
`AIRI_UPSTREAM_RAW_PROGRESS_TIMEOUT_SECONDS`(범위 1~120, 단 이미 첫
토큰이 나온 뒤의 스톨 한도라 이번 증상과는 다른 축)뿐이다.

**조치**: 첫 3런을 폐기하고, 프록시를 `AIRI_UPSTREAM_FIRST_RAW_TIMEOUT_SECONDS
=30`(Task 1과 동일 — 유효 범위 안 최댓값)으로 재기동해 재실행했다.
30초로는 정상 응답이 돌아왔다(턴당 14~53초대 관측, §4 표가 그 결과).
`ollama_proxy.py`는 무수정 원칙이라 클램프 자체를 고치지 않았다 —
**이 문서와 이번 발견을 근거로 다른 배치(특히 `AIRI-CTX-BUDGET-TRADEOFF
-2026-08-20.md`의 "90초 워치독" 재기동)가 실제로 30이 아닌 8로 돌았을
가능성을 별도 확인 필요**로 남긴다(§8 우려).

## 7. B4a 이식 권고 (1줄)

운영 디렉터도 근거 판정을 "관련도 매칭 줄 존재"로 좁혀 붙이되, 프록시
쪽 `X-AIRI-Briefing-Evidence` 계약과 루프백 제약은 그대로 두고, 해제
관측은 `/health` 누계 대조가 아니라 (원격 디렉터로 확장될 때는 특히)
프록시가 요청-응답 상관관계를 남기는 별도 텔레메트리로 승격을 검토한다.

## 8. 우려 사항

1. `AIRI-CTX-BUDGET-TRADEOFF-2026-08-20.md`의 "90초 워치독" 재기동이
   실제로는 8초로 클램프됐을 가능성 — 그 배치의 h8/h12(스로틀 후) 결과
   해석에 영향을 줄 수 있어 별도 재확인이 필요하다(§6).
2. 프로브·사실활용·앵커 축은 표본이 작고(9·90·144) 온도 0.45 재실행
   노이즈에 묻힌다 — 좁힌 정의의 효과로 읽지 말 것(§5).
3. 해제 관측성은 `/health` 누계를 턴 전후로 대조하는 방식이라, 같은
   프록시 프로세스에 동시에 다른 트래픽이 있으면 오귀속될 수 있다 —
   이번 실측처럼 전용 프로세스·순차 실행 전제에서만 안전하다.
4. B4a 운영 디렉터가 원격일 경우 이 계약 전체(루프백 제한 포함)가
   재검토 대상이라는 Task 1의 기존 지적이 그대로 유효하다.

원 데이터: `ollama-proxy/eval/results/broadcast-sim-evidence-narrow-on-seed{11,22,33}-local-2026-08-20.json`.
비교 기준(재사용, 재실행 안 함): `ollama-proxy/eval/results/broadcast-sim-evidence-{off,on}-seed{11,22,33}-local-2026-08-20.json`
(Task 1). 관련: `완료/AIRI-BRIEFING-EVIDENCE-SIGNAL-2026-08-20.md`,
`완료/AIRI-CTX-BUDGET-TRADEOFF-2026-08-20.md`, `task-1-review.md` Minor 1·2.
