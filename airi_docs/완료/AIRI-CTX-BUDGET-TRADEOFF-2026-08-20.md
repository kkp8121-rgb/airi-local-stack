# 히스토리 vs 브리핑 토큰 예산 실측 (2026-08-20, 클로드 PC, 급종료 재개)

> Task 3 — `--history-turns {4,8,12}` × 시드 `{11,22,33}` = 9런. 공통 구성은
> `--memory-arm seeded --briefing on --acts on --contract on`, 픽스처
> `first_broadcast_v1.json`, `num_ctx 4096`, 모델 `midm-airi:2.0-mini`, CPU.
> 목적: 히스토리 창을 줄이면(4쌍) 브리핑·계약 블록에 쓸 프롬프트 예산이
> 늘어나는데, 그게 §1(방송 지표)을 해치는지, 반대로 히스토리를 늘리면
> (12쌍) 득이 있는지를 실측으로 가른다.

## 0. 급종료·정체 재개 이력 (필수 1절)

이 배치는 **두 번 중단**됐다가 재개됐다.

1. **1차 중단(컴퓨터 급종료)**: 이전 워커가 9런 중 2런
   (`h4-seed11`, `h4-seed22`) 완료 후 컴퓨터가 급종료돼 중단됐다. 커밋
   상태는 무손실(`de4018c`)이었고, 재개 워커(이 문서 작성자)가 두 완성
   런의 내장 메타데이터(모델 태그·`num_ctx`·memory arm·history_turns·
   briefing/acts/contract/briefing_evidence·픽스처 SHA)를 재계산해 지정
   구성과 **바이트 단위 일치**를 확인한 뒤 재사용했다(§2).
2. **2차 정체(백그라운드 재개 체인 끊김)**: 재개 워커가 나머지 7런을
   순차 처리하던 중, `run_in_background` 완료 알림 이후 다음 런을 즉시
   잇지 못하고 대기 상태로 멈추는 일이 **세 차례** 발생했다
   (`h8-seed11` 완료 후 ~2.5시간 정체, 이후 재개 방식을 바꿨음에도
   `h8-seed22` 완료 후 재차 정체). 오케스트레이터가 감시망으로 이를
   실측 확인하고 개입해 구조를 바꿨다:
   - 잔여 4런(`h8-seed33`, `h12-seed11/22/33`)을 **단일 bash 스크립트**로
     묶어 순차 실행 + 런별 결과 검증(rows=48) + 실패 시 1회 재시도까지
     스크립트 내부에서 처리하도록 바꾸고, 이 스크립트 자체를 **하나의**
     백그라운드 작업으로 걸었다. 이후 `BATCH_DONE`까지 정체 없이 완주했다.
   - 이 과정에서 **CPU 전원 캡 70% + Ollama 프로세스 affinity 8/16코어**
     스로틀이 사용자 요청(팬 소음)으로 걸렸고, 이에 맞춰 프록시를
     `AIRI_UPSTREAM_FIRST_RAW_TIMEOUT_SECONDS=30 → 90`으로 재기동했다
     (§2-나). **주의 — 착수 당시엔 "품질 축은 스로틀과 무관, 지연축만
     영향받는다"고 가정했으나, 사후 분석(§5-가/나)에서 이 가정이 틀렸을
     가능성이 드러났다**: 스로틀 전/후(epoch A/B) 경계가 history_turns
     축과 완전히 겹쳐 있고, epoch만 고정해도 앵커·다양성·fact_usage가
     크게 갈리는 패턴이 나왔다. 즉 지연축뿐 아니라 콘텐츠 품질 축도
     epoch 변화의 교락 변수일 수 있다 — 상세는 §5-가/나.
3. 결과적으로 9런 전부 실패 0으로 완주했다(`transport_failures=0` 전
   런). 아래 지표는 이 두 번의 재개를 거쳐 만들어졌다는 것을 전제로
   읽는다.

### 0-가. 정정 추기 — "워치독 90초"는 실효 8초였다 (2026-08-20 사후)

> **이 절은 사후 정정이다. 아래 §2-나를 포함한 본문 원문은 당시 기록
> 그대로 두고, 사실 정정만 여기에 추기한다.**

위 2번과 §2-나에 적힌 재기동 env `AIRI_UPSTREAM_FIRST_RAW_TIMEOUT_SECONDS=90`
은 **실제로는 적용되지 않았다.** 프록시 코드의
`configured_upstream_first_raw_timeout`(`ollama-proxy/ollama_proxy.py`)은
유효 범위를 **1.0~30.0초**로 두고 범위 밖 값을 **경고 없이 기본값 8.0초로
클램프**한다:

```python
def configured_upstream_first_raw_timeout(value: object) -> float:
    """Bound a warm foreground request that never produces its first token."""
    default = 8.0
    ...
    return seconds if math.isfinite(seconds) and 1.0 <= seconds <= 30.0 else default
```

즉 5~9런(h8-seed22/33 · h12 전체)은 "워치독 90초"가 아니라 **실효 8초 워치독**
아래에서 실행됐다. 이 사실은 같은 날 다른 태스크(브리핑 근거 정의 좁히기)가
같은 env를 지정했다가 첫 3런이 거의 전 턴 8초 폴백으로 오염되는 것을
실측하면서 발견됐다(`완료/AIRI-BRIEFING-EVIDENCE-NARROW-2026-08-20.md` §6).

**실측 영향 판정: 미미하다.** 이 배치의 침묵 폴백(= 워치독 발동 건수)은
h4 2/144 · h8 2/144 · h12 0/144로, 8초 클램프가 걸린 epoch B 구간에서
오히려 0~2건에 그쳤다(전 런 `transport_failures=0`). 따라서 §4 표의 수치를
수정하지 않는다.

**단, epoch 해석에는 이 사실을 반드시 병기한다.** §5-가/나의 epoch A/B 구분은
"CPU 전원 캡 70% + affinity 8코어"만이 아니라 **워치독 실효값 30초(epoch A) vs
8초(epoch B)**의 차이도 포함한다. 두 변화가 같은 경계에서 동시에 일어났으므로,
epoch 교락의 내용물은 스로틀 단독이 아니라 "스로틀 + 워치독 단축"의 묶음이다.
§6이 권고하는 코덱스 GPU 단일조건 재실측에서는 **워치독을 유효 범위 안의 단일
값(예: 30)으로 고정**해 이 축까지 함께 제거해야 한다.

## 1. 재사용 검증 내역 — `h4-seed11`, `h4-seed22`

두 파일의 내장 메타데이터를 지정 구성과 대조했다(전부 일치, 재사용 확정):

| 필드 | 지정값 | h4-seed11 | h4-seed22 |
|---|---|---|---|
| `model` | `midm-airi:2.0-mini` | 일치 | 일치 |
| `memory_arm` | `seeded` | 일치 | 일치 |
| `briefing` | `on` | 일치 | 일치 |
| `acts` | `on` | 일치 | 일치 |
| `contract` / `contract_version` | `on` / `v3` | 일치 | 일치 |
| `briefing_evidence` | `off`(기본 유지) | 일치 | 일치 |
| `protocol` / `author_format` | `operational` / `runtime` | 일치 | 일치 |
| `history_turns` | 4 | 일치 | 일치 |
| `fixture_sha256` | 픽스처 정본 재계산값과 일치 | 일치 | 일치 |
| `rows` / `transport_failures` | 48 / 0 | 일치 | 일치 |

`fixture_sha256`은 파일 원문 바이트 해시가 아니라 `broadcast_sim.py`의
`sha256_of(canonical_bytes(fixture))`(정렬 키 JSON 직렬화) 값이다. 현재
저장소의 `first_broadcast_v1.json`을 같은 함수로 재계산한 결과
(`0d558c0c…`)가 두 파일의 기록값과 정확히 일치함을 확인했다 — 파일의
raw byte sha256(`e4dc404b…`, 줄바꿈·포맷 차이 포함)과는 다르지만, 이는
정규화 해시의 정의상 당연한 차이이지 픽스처 불일치가 아니다.

## 2. 사용 env 전문

### 2-가. 1~4런 (h4 전 시드 + h8-seed11) — 스로틀 전

```
cd ollama-proxy
AIRI_UPSTREAM_FIRST_RAW_TIMEOUT_SECONDS=30 \
AIRI_IMMEDIATE_ACK=marker \
AIRI_BROADCAST_CONTRACT=on \
AIRI_SILENCE_FALLBACK_POOL=on \
AIRI_MEMORY_CLAIM_GUARD=on \
python ollama_proxy.py --num-ctx 4096 --num-gpu 0
```

`AIRI_MEMORY_ENABLED`는 설정하지 않았다(프록시 기본값 OFF, `/health`의
`memory.enabled: false`로 실측 확인). 이래도 되는 근거는 추측이 아니라
`run_broadcast_sim.py`의 `run_arm()` 코드를 직접 읽어 확인했다:

- `history`는 러너 프로세스 안의 **평범한 파이썬 리스트**다(`run_arm()`
  지역 변수). 매 턴 `kept = history[-history_turns:] if history_turns > 0
  else []`로 최근 N쌍만 잘라 요청 `messages`에 실제 `user`/`assistant`
  턴으로 명시 포함한다 — 프록시가 대화를 기억하는 게 아니라 **러너가
  매번 전체 맥락을 재구성해서 보낸다**. 그래서 `--history-turns`는
  프록시 상태가 아니라 이 슬라이싱 길이 하나만 바꾼다.
- `--memory-arm seeded`가 켜는 유일한 동작은 `pre_session_seeds=True`
  분기다(`args.memory_arm == "seeded"`) — 방송 루프 시작 전에 프로브가
  심을 사실 3건을 실제 이전 세션 발화처럼 한 번 주고받는다. `off`/`on`
  arm은 이 분기 외에 `run_arm()` 안에서 코드 경로가 갈라지지 않는다.
- `briefing == "on"`일 때 매 턴 `sim.build_turn_briefing_with_evidence(
  fixture, stream, pick, echo_safe)`가 시스템 프롬프트 뒤에 붙일 지시문을
  조립하는데, 이 함수의 입력은 **고정 픽스처 + 시드로 생성한 스트림 +
  이번 런에서 이미 답한 pick 목록**뿐이다 — 프록시의 영속 저널이나
  `AIRI_MEMORY_ENABLED` 상태를 전혀 참조하지 않는다.

즉 이번 실측의 "memory_arm"·"briefing" 두 축은 전부 **러너가 결정론으로
관리하는 시뮬레이션 계층**이고, 프록시의 실제 기억 서브시스템(임베더·
추출·저널 회수)은 개입하지 않는다. Task 1의 동일 배치 실측
(`완료/AIRI-BRIEFING-EVIDENCE-SIGNAL-2026-08-20.md` §4)도 같은 env로
`--memory-arm seeded --briefing on --acts on --contract on`을 돌렸다 —
이 문서의 근거와 같은 전제다.

러너 커맨드(런마다 `--history-turns`/`--seed`/`--session-id`/`--report`만
바뀜):

```
python run_broadcast_sim.py \
  --memory-arm seeded --briefing on --acts on --contract on \
  --history-turns {4|8|12} --seed {11|22|33} \
  --session-id broadcast-sim-ctxbudget-h{N}-seed{S} \
  --report ../results/broadcast-sim-ctxbudget-h{N}-seed{S}-local-2026-08-20.json
```

### 2-나. 5~9런 (h8-seed22/33, h12 전 시드) — 스로틀 후

사용자 요청(팬 소음)으로 CPU 전원 캡 70% + Ollama 프로세스 affinity
8/16코어가 걸렸다. 이 조건에서 기존 30초 워치독을 유지하면 TTFT 지연이
늘어 스퓨리어스 침묵 폴백이 섞여 측정이 오염될 위험이 있어, **프록시를
재기동**하고 워치독만 90초로 올렸다(그 외 env·인자 전부 동일):

```
AIRI_UPSTREAM_FIRST_RAW_TIMEOUT_SECONDS=90 \
AIRI_IMMEDIATE_ACK=marker \
AIRI_BROADCAST_CONTRACT=on \
AIRI_SILENCE_FALLBACK_POOL=on \
AIRI_MEMORY_CLAIM_GUARD=on \
python ollama_proxy.py --num-ctx 4096 --num-gpu 0
```

모델 디지스트 프리플라이트는 두 세션 모두
`106cfaacc185aec489ccbddd82894d6558aac745444b844a73cef4ea450e9f6c`
(`midm-airi:2.0-mini`)로 동일하게 관측됐다(핀 고정은 미설정,
`AIRI_CHAT_MODEL_DIGEST` 없음 — 관측 기록만).

## 3. 9런 결과 — 3-시드 평균 (history_turns 축)

턴 48건/런 전부 성공(`transport_failures=0`, 9런 합계 0). 결정론 축은
9런 전부 만점이라 평균 없이 합계로 표기한다.

### 3-가. 다양성(응답 다양성) 산출 절차 — 재현 가능

이 지표는 **어림값이 아니라 커밋된 결과 JSON에서 그대로 재현된다**.
`rows` 배열에는 응답 원문이 없지만(채점 플래그만 있음), 같은 파일의
형제 배열 **`transcript`**에 턴별 원문이 들어 있다 —
`stage == "turn"`인 항목의 `"airi"` 필드가 그 턴의 최종 응답 텍스트다
(결정론 액트가 붙는 후원 턴은 렌더러 출력, 그 외는 모델 생성문).

계산식: `distinct(len(set(airi 텍스트들))) / len(턴 수)`, 48턴 전부
분모. 재현 커맨드(9개 파일 전부에 대해 이 문서의 수치와 바이트 단위로
재현됨을 확인했다):

```python
import json
d = json.load(open("broadcast-sim-ctxbudget-h{N}-seed{S}-local-2026-08-20.json", encoding="utf-8"))
bodies = [e["airi"] for e in d["transcript"] if e.get("stage") == "turn"]
distinct, total = len(set(bodies)), len(bodies)
print(distinct, "/", total, "=", round(100 * distinct / total, 1), "%")
```

런별 고유 응답 수(재현 확인 완료):

| 런 | 고유 응답 수 / 전체 | 비율 |
|---|---:|---:|
| h4-seed11 | 23/48 | 47.9% |
| h4-seed22 | 37/48 | 77.1% |
| h4-seed33 | 29/48 | 60.4% |
| h8-seed11 | 39/48 | 81.2% |
| h8-seed22 | 13/48 | 27.1% |
| h8-seed33 | 14/48 | 29.2% |
| h12-seed11 | 11/48 | 22.9% |
| h12-seed22 | 13/48 | 27.1% |
| h12-seed33 | 14/48 | 29.2% |

(§5-가에서 이 지표가 history_turns 축과 CPU epoch 축에 동시에
걸려 있다는 것을 별도로 다룬다 — 재현 가능하다는 것과 원인 귀속이
가능하다는 것은 별개다.)

> **읽기 전 주의**: 아래 앵커·다양성·fact_usage·프로브 4개 행은
> history_turns 축과 CPU epoch 축(§5-가)이 완전히 교락돼 있다 — 이
> 표만 보고 "히스토리가 줄수록 좋다"로 읽지 말 것. §5-나·§6에서
> epoch를 통제한 재판정을 다룬다.

| 지표 | h4 (평균) | h8 (평균) | h12 (평균) |
|---|---:|---:|---:|
| 주제 앵커 적중 (epoch 교락, §5-가) | 29.9% | 20.8% | 13.2% |
| 응답 다양성(서로 다른 응답, epoch 교락, §5-가) | 61.8% | 45.8% | 26.4% |
| 5자 이하 단답 (epoch와 무관하게 h4만 이탈 — §6 근거) | 6.9% | 0.0% | 0.0% |
| fact_usage (epoch 교락, §5-가) | 3.4% | 4.8% | 0.0% |
| 응답 길이 p50 / p95 | 15.7자 / 35.3자 | 16.0자 / 30.7자 | 15.0자 / 30.3자 |
| 수신자(후원 검사) | 15/15 | 15/15 | 15/15 |
| 후원 호명 정확 | 15/15 | 15/15 | 15/15 |
| 여론 응답 | 16/16 | 16/16 | 16/16 |
| 여론 집계 표현 | 16/16 | 16/16 | 16/16 |
| 존댓말 위반 | 0/144 | 0/144 | 0/144 |
| 이탈(drift) | 0 | 0 | 0 |
| 침묵 폴백(워치독) | 2/144 | 2/144 | 0/144 |
| 이름 발명 | 5 | 7 | 0 |
| 전송 실패 | 0/144 | 0/144 | 0/144 |

**기억 프로브(런별 병기 — 표본 3/런이라 평균 대신 원값)**:

| | seed11 | seed22 | seed33 |
|---|---:|---:|---:|
| h4 | 1/3 | 1/3 | 0/3 |
| h8 | **3/3** | 0/3 | 0/3 |
| h12 | 0/3 | 0/3 | 0/3 |

h8-seed11의 3/3은 이 표에서 유일한 이상값이다 — 표본 3건짜리 지표라
단일 시드 급등을 "h8이 더 낫다"는 근거로 쓰지 않는다(§6 한계).

### 런별 상세

| 런 | 앵커 | 다양성 | 단답 | fact | probe | chars p50/p95 | 발명 | 폴백 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| h4-seed11 | 29.2% | 47.9% | 2.1% | 2/28 | 1/3 | 10/26 | 0 | 1/48 |
| h4-seed22 | 31.2% | 77.1% | 6.2% | 1/33 | 1/3 | 17/26 | 0 | 1/48 |
| h4-seed33 | 29.2% | 60.4% | 12.5% | 0/29 | 0/3 | 20/54 | 5 | 0/48 |
| h8-seed11 | 31.2% | 81.2% | 0.0% | 4/28 | 3/3 | 18/32 | 7 | 2/48 |
| h8-seed22 | 12.5% | 27.1% | 0.0% | 0/33 | 0/3 | 15/30 | 0 | 0/48 |
| h8-seed33 | 18.8% | 29.2% | 0.0% | 0/29 | 0/3 | 15/30 | 0 | 0/48 |
| h12-seed11 | 8.3% | 22.9% | 0.0% | 0/28 | 0/3 | 15/30 | 0 | 0/48 |
| h12-seed22 | 12.5% | 27.1% | 0.0% | 0/33 | 0/3 | 15/30 | 0 | 0/48 |
| h12-seed33 | 18.8% | 29.2% | 0.0% | 0/29 | 0/3 | 15/31 | 0 | 0/48 |

## 4. num_ctx 거절·워치독 발동 기록

- **num_ctx 거절(400) 0건** — 9런 전부 `transport_failures=0`이고 개별
  턴의 `failure` 필드도 전부 `null`(추출 확인). `history_turns=12`가
  프롬프트를 가장 길게 만드는 조건인데도 `--num-ctx 4096`에서 거절이
  나오지 않았다 — 고정 주제 블록 + 캐릭터 카드(~2,250토큰) +
  브리핑·계약 블록 + 히스토리 12쌍을 더해도 4096 한도 안에 들어간다는
  뜻이다.
- **워치독(침묵 폴백) 발동**: h4 2/144, h8 2/144, h12 0/144. 전부
  `AIRI_UPSTREAM_FIRST_RAW_TIMEOUT_SECONDS` 임계 이내였고, 오히려
  스로틀 이후(90초 워치독 구간)에 0건으로 떨어졌다 — 워치독을 90초로
  올린 조치가 CPU 저속화를 "모델이 답을 못 냈다"로 오분류하는 것을
  성공적으로 막았다는 뜻이다.

## 5. CPU 환경 제약 (운영 대표성 없음 — 지연 수치 비대표) — 및 스로틀 epoch 교락

이 배치는 두 개의 서로 다른 CPU 조건("epoch")에서 실행됐고, **이
epoch 경계가 history_turns 축과 완전히 겹친다.** 지연 수치가
비대표라는 것과는 별개로, 이는 §6 판정에 직접 영향을 주는 문제라
별도 절로 다룬다.

### 5-가. 런별 epoch 매핑 (완전 교락 — 반드시 읽을 것)

| 런 | epoch | 워치독 | CPU 조건 |
|---|---|---|---|
| h4-seed11 | **A (스로틀 전)** | 30초 | 정상 |
| h4-seed22 | **A** | 30초 | 정상 |
| h4-seed33 | **A** | 30초 | 정상 |
| h8-seed11 | **A** | 30초 | 정상 |
| h8-seed22 | **B (스로틀 후)** | 90초 | 전원 캡 70%+affinity 8코어 |
| h8-seed33 | **B** | 90초 | 전원 캡 70%+affinity 8코어(+사용자 웹스크레이퍼 3개 동시 실행) |
| h12-seed11 | **B** | 90초 | 상동 |
| h12-seed22 | **B** | 90초 | 상동 |
| h12-seed33 | **B** | 90초 | 상동 |

**h4 3런은 전부 epoch A, h12 3런은 전부 epoch B다 — 표본이 완벽하게
분리된다.** h8만 seed11(A)·seed22/33(B)로 양쪽에 걸쳐, epoch 내부
비교가 가능한 유일한 history_turns 값이다. **즉 h4→h12 추세(§3)는
history_turns와 CPU epoch가 완전히 교락(confounded)돼 있다 — 이
9런만으로는 두 원인을 분리할 수 없다.**

### 5-나. epoch별 평균 — h8의 내부 분할이 주는 증거

| 지표 | epoch A 평균 (n=4: h4×3+h8-seed11) | epoch B 평균 (n=5: h8-seed22/33+h12×3) |
|---|---:|---:|
| 주제 앵커 | **30.2%** | 14.2% |
| 응답 다양성 | **66.7%** | 27.1% |
| fact_usage | **6.1%** | 0.0% |
| 기억 프로브 | **5/12(41.7%)** | 0/15(0%) |

이 표가 §3의 h4>h8>h12 추세보다 **더 급격하고 더 깨끗하게 갈린다.**
결정적 대조점 두 가지:

1. **epoch A 안에서는 history_turns를 4→8로 올려도 지표가 떨어지지
   않는다.** h4(3시드 평균, epoch A) 앵커 29.9%/다양성 61.8%인데,
   같은 epoch A의 h8-seed11 **단독값은 31.2%/81.2%로 오히려 더
   높다.** history_turns가 늘었는데 지표가 오른 것이다 — §3의
   "history_turns가 늘수록 나빠진다"는 방향과 **정반대**다.
2. **epoch B 안에서는 history_turns를 8→12로 올려도 차이가 거의
   없다.** epoch B만 놓고 h8(seed22/33 평균) 앵커 15.65%/다양성
   28.15% vs h12(3시드 평균) 앵커 13.2%/다양성 26.4% — 차이 2~3pp로
   시드 잡음 범위 안이다.

즉 **epoch를 고정하면 history_turns의 효과가 거의 사라지고, epoch를
바꾸면(A→B) 앵커·다양성·fact_usage·프로브가 전부 큰 폭으로 떨어진다.**
이는 이번 9런에서 관측된 "히스토리가 늘수록 나빠진다"는 표면적 추세의
대부분이 실제로는 **CPU epoch(전원 캡·affinity·워치독) 변화와 연동된
현상일 가능성**을 시사한다. 메커니즘은 확인하지 못했다 — 가설로만
기록한다: CPU 전원 캡·코어 affinity 축소가 추론 스레드풀의 연산 순서를
바꿔 부동소수점 축적 순서·샘플링 결과에 영향을 줬을 수 있다(temperature
0.45이므로 모델 샘플링 자체가 결정론적이지 않다는 점도 별도 잡음원 —
`--seed`는 시뮬레이션 스트림 생성만 고정하고 모델 토큰 샘플링은
고정하지 않는다). 두 가설(epoch 아티팩트 vs 순수 샘플링 잡음) 중 어느
쪽인지도 이 배치만으로는 가르지 못한다.

**지연 수치(턴당 완료 시간)는 두 구간 간에도, 08-18/08-19 기준
실측과도 비교 불가능하다** — CPU 배치·부하가 다르기 때문이다.
워치독 발동(침묵 폴백)은 스로틀 이후 오히려 0건으로 감소했다(§4) —
이는 "워치독을 90초로 올린 조치가 CPU 저속화를 폴백으로 오분류하는
것은 막았다"는 뜻일 뿐, 콘텐츠 품질 축(앵커·다양성·fact_usage)이
epoch와 무관하다는 뜻은 아니다 — 오히려 5-나가 보여주듯 정반대다.
이 두 주장을 혼동하지 않는다.

## 6. 판정 (§5-가/나의 epoch 교락을 반영해 재판정 — 원 판정에서 하향 수정)

**교락되지 않는 것부터**: 결정론 축(수신자·호명·여론·존댓말·이탈)은
9런 전부 만점이고, history_turns·epoch 어느 쪽으로도 갈리지 않는다 —
이 축에 한해서는 history_turns 4/8/12 모두 안전하다는 결론은 그대로
유지된다.

**앵커·다양성·fact_usage·프로브만으로 재판정(§5-가/나 반영)**: 이
네 지표는 전부 history_turns 축과 CPU epoch 축에 동시에 걸려 있다
(h4=전부 epoch A, h12=전부 epoch B, h8만 양쪽). §5-나에서 본 대로
epoch를 고정하면(epoch A 내부에서 h4 vs h8-seed11, epoch B 내부에서
h8-seed22/33 vs h12) history_turns의 효과는 사실상 사라지거나
방향이 뒤집힌다 — epoch A에서는 h8-seed11이 h4 평균보다 오히려 더
높은 앵커·다양성을 냈다. **따라서 앵커 추세(29.9%>20.8%>13.2%)만
따로 떼어봐도, 그 추세가 history_turns 때문인지 epoch 때문인지 이
데이터로는 분리되지 않는다 — "히스토리 4가 앵커·다양성에서 가장
좋다"는 원 판정을 확증된 결론으로 유지할 수 없다.**

이 배치가 실제로 뒷받침하는 것은 다음 세 가지뿐이다:

1. **결정론 축(P2)은 history_turns 4/8/12 어느 값에서도 무영향** —
   확증됨(epoch와도 무관, 9런 전부 만점).
2. **num_ctx 4096은 history_turns 12까지도 거절 없이 수용한다** —
   확증됨(§4).
3. **5자 이하 단답 비율은 epoch와 무관하게 h4에서만 관측된다**
   (h4 세 런 6.9% 평균 vs h8-seed11 0.0%·epoch B 전 런 0.0%) — 이
   지표는 epoch A/B에 걸쳐 h4만 유일하게 다른 값을 보여 **epoch
   교락에서 상대적으로 자유로운, 그나마 history_turns 자체의 신호에
   가까운 유일한 항목**이다. 그리고 이 신호는 **h4에 불리한
   방향**이다(단답이 더 많음 = §1이 원하는 방향의 반대).

**히스토리 12가 이득이 없다는 결론은 여전히 유지된다** — 다만 근거가
바뀐다. epoch B 안에서 h8(seed22/33)과 h12을 비교하면(§5-나) 차이가
2~3pp로 잡음 수준이었다 — 즉 "h12가 h8보다 나쁘다"가 아니라 **"h8과
h12 사이에는 history_turns로 설명되는 유의미한 차이가 없다"**가 더
정확한 문장이다. fact_usage·프로브가 epoch B에서 전부 0인 것도
h8-seed22/33과 h12 공통이라 history_turns=12 고유의 결함이 아니다.

**권고(1줄, 채택은 사용자/코덱스 몫)**: 이 CPU 배치의 데이터로는
`--history-turns` 4/8/12 중 앵커·다양성·fact_usage 기준의 우열을
확정할 수 없다(epoch와 완전 교락) — **코덱스(GPU PC)에서 CPU
스로틀·워치독 변경 없이 단일 조건으로 9런(또는 최소 h4/h12 6런)을
재실측해 history_turns 효과를 epoch 효과와 분리하는 것을 다음 단계로
제안한다.** 그 전까지는 결정론 축 무영향·num_ctx 4096 수용 확인이라는
확실한 결과만 근거로 운영 기본값을 결정해야 하며, 앵커·다양성 수치를
`--history-turns 4` 채택의 근거로 인용하지 않는다.

## 7. 한계·이상 징후

- **표본 크기**: history_turns당 3시드, 기억 프로브는 런당 3건(9건
  총). h8-seed11의 프로브 3/3은 유일한 이상값이며 단독으로 "h8이
  우월하다"를 뒷받침하지 않는다. 08-19 분산 캘리브레이션 문서가 이미
  경고했듯("주제 앵커 21~48%, ±13pp — 단일 런 판정 금지"), 이번 h4→h12
  하락폭(29.9%→13.2%, 약 17pp)의 노이즈 대비 크기 자체는 확인되지만,
  아래 CPU epoch 교락 때문에 이 하락폭을 history_turns 효과로
  귀속시킬 수 없다(§5-가/나, §6).
- **CPU epoch 완전 교락(가장 중요한 한계 — §5-가/나 참조)**: h4
  3런은 전부 스로틀 전(epoch A), h12 3런은 전부 스로틀 후(epoch B)라
  history_turns 축과 CPU epoch 축이 겹친다. 워치독 발동(침묵 폴백)은
  스로틀 이후 오히려 줄었지만(§4), 이는 지연축 얘기일 뿐 **콘텐츠
  품질 축(앵커·다양성·fact_usage·프로브)도 epoch 사이에 크게
  갈렸다**(epoch A 30.2%/66.7% vs epoch B 14.2%/27.1% 앵커/다양성,
  §5-나). epoch를 고정한 내부 비교(epoch A 안 h4 vs h8-seed11, epoch
  B 안 h8 vs h12)에서는 history_turns의 효과가 사실상 사라지거나
  방향이 뒤집힌다 — 즉 배치 간 왜곡 근거는 **약하지 않고, 오히려
  주된 설명변수일 가능성이 있다.** 원인(전원 캡·affinity로 인한
  추론 스레드풀 변화 vs 단순 샘플링 잡음)은 확정하지 못했다 — 코덱스
  GPU 단일조건 재실측이 필요하다(§6).
- **재개 이력 자체가 잡음원**: 이 배치는 급종료 1회 + 백그라운드
  재개 정체 3회를 거쳤다(§0). 각 재개 지점에서 프록시를 재기동했으나
  (PID 1300→1399 최초, 이후 28632로 교체), 매 재기동마다 모델
  디지스트 프리플라이트로 동일 아티팩트(`106cfaac…`)를 재확인했다.
- **invented_handle_turns**: h4-seed33(5건), h8-seed11(7건)에서만
  발생하고 나머지 런은 0건 — history_turns과 뚜렷한 상관은 안 보이고
  시드별 잡음으로 보인다.

## 8. 변경 파일

- 신규: `airi_docs/완료/AIRI-CTX-BUDGET-TRADEOFF-2026-08-20.md` (이 문서)
- 신규(force-add, 9종): `ollama-proxy/eval/results/broadcast-sim-ctxbudget-h{4,8,12}-seed{11,22,33}-local-2026-08-20.json`
  (`h4-seed11`·`h4-seed22`는 급종료 이전 워커 산출물을 검증 후 재사용,
  나머지 7종은 이번 재개 세션에서 신규 생성)
- 코드·픽스처 무수정(요구사항대로 `--history-turns` 기존 플래그만 사용)
