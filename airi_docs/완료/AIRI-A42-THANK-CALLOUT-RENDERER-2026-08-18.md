# A4.2 thank 렌더러 — 호명 B안 반영 (2026-08-18, 클로드 PC)

> 사용자 결정(2026-08-18) **thank = B안** `{닉네임}, 고마워! {한마디}`
> + 초기 한마디 3종을 A4.2 결정론 렌더러에 구현한 결과 문서다.
> 근거 시트: `진행예정/AIRI-THANK-RENDERER-CANDIDATE-SHEET-2026-08-18.md`
> (선택 근거 = 계약 v3에서도 dn04·b18이 2/2 위반한 프롬프트 상한 실측,
> `완료/AIRI-B4C-ADDRESSEE-CONTRACT-V3-2026-08-18.md`).
> **운영 ON은 여전히 별도 승인 대상**이며, 이번 배치는 평가 계층
> (`ollama-proxy/eval/affect_broadcast/`) 안에서만 끝난다.

## 1. 무엇을 바꿨나

| 파일 | 변경 |
|---|---|
| `must_act_realization.py` | `thank` 전용 선택 파라미터 `callout_context` 신설 + 호명 템플릿·한마디 풀·닉네임 검증·역분해 함수 + 사이드카 오라클 검증기 |
| `must_act_thank_callout_v1.json` | **신규** — 호명 정책 사이드카 오라클(내용 없는 pin) |
| `test_must_act_realization.py` | 회귀 테스트 6종 추가(8 → **14 passed**) |
| `README.md` | 호명 경로의 실제 계약을 반영해 "identity-bearing 파라미터 없음" 서술 수정 |

핵심 상수(모듈 pin):

```
THANK_CALLOUT_TEMPLATE = "{nickname}, 고마워! {closer}"
THANK_CALLOUT_CLOSERS  = ("덕분에 오늘도 달린다!",
                          "이 힘으로 조금 더 해볼게!",
                          "사장님한테 자랑해야지!")
```

## 2. 하위 호환 — 기본은 v1 그대로

`render_must_act(candidate)`를 예전처럼 호출하면(= `callout_context`
생략) 산출물이 **바이트 단위로 종전과 같다**. 실측:

```
text        = "고마워. 함께해줘서 힘이 돼."
direction   = "fixed_korean_template"
postcondition = "exact_template_only"
```

즉 닉네임이 없으면 v1 문구로 떨어진다(사용자 지시 "하위 호환" 충족).
호명 변형은 호출자가 검증된 이름을 넘길 때만 활성화되는
**default-inert** 경로다. 기존 호출부(`run_guarded_delta_eval.py` 등)는
무수정이며 시그니처 변경 없이 동작한다.

## 3. 이름 발명 금지 — 어떻게 보장했나

렌더러는 이름을 **생성하지 않고, 픽스처에서 읽지도 않는다.** 슬롯 2개만
채우며 둘 다 출처가 고정이다.

- `{nickname}` = 호출자(B4b 어댑터)가 이미 검증한 표시 이름. 렌더러는
  이를 재검증만 한다 — 브로드캐스트 디렉터의 `BAD_TEXT` 계약
  (`broadcast-director/core.mjs:7,24`: 제어·양방향·서로게이트 문자 금지,
  NFC)과 동일 범위에 렌더러 고유 제약을 더한다: 길이 ≤32자, 호명 분해를
  흐리는 구두점(`,` `!` `{` `}` `<` `>` `|` `"` `'` `\` `` ` ``) 금지,
  U+0020 외 공백류·연속 공백·양끝 공백 금지.
- `{closer}` = 모듈에 pin된 3문구 중 **인덱스로만** 선택(디렉터가 순환
  선택). 자유 문자열 주입 경로가 없다.

닉네임에 `,`와 `!`가 들어올 수 없으므로 구분자 `", 고마워! "`는 렌더
결과에서 **정확히 1회**만 등장하고, `decompose_thank_callout()`이 역분해로
이를 증명한다(호명 정확히 1회 = B4a `donation_name_callout_request` 계약).

## 4. Fail-closed 실측

거부 확인 16종(전부 `MustActRealizationError`):

| 분류 | 입력 |
|---|---|
| act 오용 | `thank` 아닌 act에 `callout_context`, deescalate와 동시 사용 |
| 컨텍스트 형식 | 키 누락·여분 키(`amount`)·dict 아님·리스트·빈 dict |
| 인덱스 | `True`(bool), `"0"`(str), `3`(범위 밖), `-1` |
| 닉네임 | 빈 문자열, 33자, `별, 빛`, `별빛!`, 개행, U+202E, NBSP, 양끝 공백, 연속 공백, NFD(`가`), 정수, `None` |

산출물 위조 거부 4종: v1 라벨에 호명 텍스트, 풀 밖 한마디,
호명 2회 삽입, 라벨 혼합(direction/postcondition 불일치).

바이트 상한: 최악 입력(32자 닉네임 + 최장 한마디) 정규 JSON
**333 / 512 바이트**로 여유 확인.

## 5. 오라클 — v1 무수정 + 사이드카 신설 (greybox)

`must_act_realization_v1.json`은 **바이트·SHA 전부 그대로 뒀다**
(`ORACLE_SHA256 = cec3f9b8…`). 호명 정책은 형제 파일
`must_act_thank_callout_v1.json`(SHA `f3509ef8…`)로 분리했다.

사이드카는 내용이 없다 — 이름·금액·텍스트 필드가 없고, thank 턴 3개
(`callback-04`·`callback-11`·`callback-20`)에 대해 `callout_available:
false`만 기록한다. **합성 코퍼스의 후원 턴에는 검증된 표시 이름이 아예
없기 때문**이다(픽스처 실측: 세 턴 모두 익명/이름 정보 없는 후원,
`prior_airi`가 "이름이나 금액 정보 없이 온다"고 명시). 따라서 합성
데이터에서 기대되는 산출물은 계속 v1 고정 템플릿이고, 사이드카가 그
사실을 pin한다. 검증기는 사이드카의 turn_id 순서가 realization 오라클의
thank 순서와 일치하는지, 라벨이 `callout_available`과 정합한지까지 본다.

## 6. 검증 증거

```
ollama-proxy/eval/affect_broadcast/test_must_act_realization.py  14 passed
ollama-proxy/eval/affect_broadcast/ (디렉터리 전체)  121 passed, 2 skipped,
                                                     188 subtests passed
node test-affect-evaluator-runtime-fence.mjs         11 tests, 0 fail
                                                     (2 skip = symlink 불가)
```

런타임 펜스가 통과했다는 것은 이 모듈이 여전히 **프로덕션 경로에서
참조되지 않음**을 뜻한다(운영 배선 금지 조건 충족). CI 자체는 billing
차단 상태라 로컬 실행이 대체 증거다(`ollama-proxy-api`/`evaluations`
샤드에 이 테스트 파일은 이미 등록돼 있어 워크플로 수정 불요 —
`.github/workflows/remediation-checkpoint.yml:144`).

## 7. 남은 것

1. **B4b 어댑터 배선** — 디렉터의 `donation_name_callout_request`
   (`{eventId, displayName}`)를 `callout_context`로 옮기고, 한마디
   인덱스 순환을 디렉터 측에서 결정. (미착수)
2. **비공개 리허설에서 실제 1회 호명 증명** — 어댑터 배선 후.
3. **운영 ON 승인** — 사용자 결정 대기. 렌더러 존재만으로는 아무것도
   켜지지 않는다.
4. 한마디 풀 확장·문구 교체는 별도 승인 경유(현행 3종은 승인 원안).

## 8. 한계

- 렌더러는 **후원 이벤트에만** 반응한다. 후원 문구의 의미(생일·응원
  등)는 읽지 않으며, 문맥 반영형 응답은 이번 범위 밖이다(시트 §3).
- 닉네임 32자 상한은 디렉터 계약(80자)보다 엄격하다. 초과 이름은
  예외로 실패하므로 어댑터가 잡아 v1 문구로 폴백해야 한다.
- 합성 코퍼스에 검증된 이름이 없어, 호명 경로의 **실데이터 리허설
  증거는 아직 없다**(§7-2가 그 공백을 메운다).

관련: `진행예정/AIRI-THANK-RENDERER-CANDIDATE-SHEET-2026-08-18.md`(후보·결정),
`완료/AIRI-G1A-MUST-ACT-REALIZATION-FOUNDATION-2026-08-17.md`(A4.2 기반),
`완료/AIRI-B4A-BROADCAST-DIRECTOR-FOUNDATION-2026-08-13.md`(호명 요청 계약).
