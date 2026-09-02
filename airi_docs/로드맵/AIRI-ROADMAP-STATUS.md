# AIRI 로드맵 v4 — 실제 대화 사람 채점 중심 (2026-08-26 재개편; v3 2026-08-19)

> **2026-08-30 13:30 KST 저장공간 정리 완료 receipt:** 경로·참조·수량·바이트 불변식을
> 삭제 직전에 재검증한 뒤 3,992개 대상을 영구 삭제했고 실패는 0개다. 정리 명령이 직접 측정한
> 회수량은 C: **124.164 GiB**, D: **101.256 GiB**, 합계 **225.420 GiB**이며 최종 여유 공간은
> C: **170.950 GiB**, D: **327.343 GiB**다. 활성 `midm-airi:2.0-mini` manifest SHA와 네 blob,
> KURE-v1·STT·GPT-SoVITS·참조 음성·memory/knowledge DB, Mi:dm/Kanana 원본, venv, 실제 채팅·사람
> 평가·report/manifest는 보존했다. 지정한 미채택 weight·checkpoint·orphan·cache·log/tmp는 0개
> 남았다. work-continuity/dashboard와 주요 오프라인 회귀는 통과했다. 종합 checkpoint의 기존 독립
> 결함 세 종류(durability terminal timing, CI matrix 누락 3건, input-safety policy hash mismatch)는
> 이 저장공간 작업에서 수정하지 않았다. 서비스·운영 모델·DB·개인 데이터·commit/push 변경은 없다.

> **2026-08-30 13:02 KST 저장공간 정리 intent:** 사용자가 AIRI 관련 미사용 모델·캐시·임시
> 산출물의 영구 삭제를 요청했다. 실제 대조 결과 HEAD/local/origin은 `5f4bd8e`로 일치하고
> 사전 worktree는 clean이며 AIRI/Ollama 프로세스와 소유 포트 listener는 0개다. C: 여유 공간은
> 8.54 GiB로 부족하다. 기존 VOD storyline Goal은 재개하지 않고, 현재 설정이 참조하는 LLM·TTS·
> STT·GPT-SoVITS 자산과 DB·개인 오디오·원본 평가 데이터는 보존한다. 정확한 경로·용량·참조를
> 확인한 미사용 모델·캐시·tmp만 삭제하고, 삭제 전후 용량과 기본 검증을 receipt로 남긴다.

> **2026-08-28 16:10 KST — M8(스택·기술 한계 돌파) 개설, 전 실험 게이트 해제:**
> 사용자 결정 두 건을 반영했다: ①"모든 금지를 해제시키고 할 수 있는 건 다 해보자" —
> S5·모델 축·파인튜닝 승인 게이트 해제(단, 검토 PC는 CUDA 부재로 파인튜닝 물리 불가;
> 원문/키의 저장소 반입 금지와 push 매회 승인은 유지) ②"모델 변경은 가장 마지막" —
> Mi:dm 선정 사유에 한국어 능력 포함. 이에 따라 M8을 신설: Stage 1(추론 시점 — CRANE식
> 출력 격리 → 스토리 캐릭터 프레이밍 → 정제 예시 → depth injection, 하나씩 시험·조합 누적)
> → Stage 2(llama-server logit_bias·최소 GBNF) → Stage 3(Mi:dm 교정 파인튜닝, GPU PC) →
> Stage 4(모델 축 진단, 최후순위). 판정은 자동 바닥 지표 + 32턴 수동 7항목, 통과 시 재현
> 2회로 3연속 확정. 근거 문서 = 한계 실증·대안 기법 리서치 2종(진행중/). M7은 정상 11/15로
> 종결·직전 단계로 이동.

> **2026-08-28 15:30 KST 상태 — VOD storyline validator 튜닝 트랙 종료(사용자 결정):**
> 검토(Claude) PC가 인계를 재개해 지식 DB 0→`144/287` 적재(probe 6/6), 모델 digest·shell
> 차이를 규명한 뒤 run-81(`fictional-health-story-boundary`)과 run-82
> (`beat-verbatim-recitation-reject`)를 turn 1부터 완주했다. 겨눈 결함은 매번 닫혔지만
> (beat 낭독 10/96→**0/96**) 수동 검토는 두 회차 모두 실패했고, 자동 quality_pass 이력이
> **채점기 부풀림**(beat 어휘 일치 가점 ↔ 모델의 beat 복창) 위의 값이었음이 run-81→82
> 대조로 실증됐다. 사용자가 "지금 즉시 중단·정리"를 결정해 run-83
> (`out-of-story-voice-reject`)은 약 12/32에서 중단됐고 terminal report가 없어 무근거다.
> 유효 품질 통과는 **0/3**으로 종료. 결함 분류·한계 판단·남은 선택지 4종은
> `진행중/AIRI-VOD-STORYLINE-CEILING-EVIDENCE-2026-08-28.md`가 단일 근거 문서다.
> 다음은 사용자 방향 결정(결정 큐 24)이며, adoption false·운영 flag OFF·GPU/파인튜닝
> (2026-09-09까지)·replay/pickup/S5 금지는 유지된다. commit/push는 별도 승인 대기.

> **2026-08-28 10:21 KST 인계 상태:** VOD 8막 storyline 자가 테스트는 최신 유효 완주
> run-78까지 진행됐고, 유효 품질 통과 연속 횟수는 **0/3**이다. run-78은 32/32·8/8·1536
> slot 후보, 반복·고중복·무관 지식 표식 0이지만 자동 감정 다양성과 수동 품질 검토에서 실패했다.
> run-79는 slotwise 옵션 누락으로 무효, run-80은 인계 전환으로 19/32에서 중단되어 terminal
> report가 없다. 사용자 요청으로 Goal은 Claude PC 인계를 위해 paused로 전환한다. 새 단일 진입점은
> `진행중/AIRI-CLAUDE-HANDOFF-2026-08-28-VOD-STORYLINE.md`다. 구조 테스트 통과와 품질 통과를
> 분리하며, adoption false·운영 flag OFF·GPU/파인튜닝·replay·pickup·S5 금지를 유지한다. 게시 전
> 변경 검증은 storyline 8/8·proxy 411/411·broadcast rehearsal 85/85·broadcast_sim 105/105와
> 문서 계약·diff-check가 통과했다. 종합 checkpoint는 기준 HEAD부터 있던 CI workflow 누락 2건을
> 보고하고 실패했으며, 상세는 새 인계문에 보존했다.

> **2026-08-28 01:32 KST 최신 VOD storyline self-test receipt:** 지식 DB `documents=153, chunks=296`과 memory/knowledge ON·ready health를 유지한 채 run-15~20을 별도 외부 산출물로 보존했다. 모든 회차가 `32/32`, `8/8` 순서, 32명 staged audience, 금지 시그니처 0, 빈 응답/서비스 오류 0이었다. run-20은 repeat/high-overlap/source-claim/irrelevant-marker가 모두 0이었지만 새 사건·이전 단서/다음 고리·감정 변화의 전 장면 품질 조건과 내부 표식 비노출 조건을 충족하지 못했다. run-20 이후 동일 응답 형식 문제의 즉흥 수정은 중단하고, 추가 튜닝은 새 접근을 먼저 정한 뒤 재개한다. 이는 채택·게이트 판정이 아니며 `adoption_authorized=false`, 운영 flag OFF, GPU/파인튜닝 금지, push 별도 승인을 유지한다. 외부 결과 root는 `D:\AIRI-Models\airi-human-eval\20260828-vod-storyline-run-15`부터 `run-20`이다.

> **2026-08-28 00:25 KST 최신 receipt:** VOD 캡처의 저장된 31.64분 STT를 8막 줄거리로 구조화하고, 장면마다 맥락 연결형 시청자 모방 채팅 4개씩을 배치해 run-06 32턴을 완료했다. 8/8 장면·순서·금지 시그니처 0·빈 응답/서비스 오류 0으로 입력/전송 기준은 통과했지만, 품질 기준 `context_retention`은 사용자 직접 채점 전이며 formal adoption/gate 판정은 하지 않는다. 직접 검토 HTML: `D:\AIRI-Models\airi-human-eval\20260828-vod-storyline-run-06\vod-storyline-review.html`. 다음은 사용자 직접 32턴 채점이다.

> **2026-08-27 23:46 KST M7 VOD 시뮬레이션 설계 결함 receipt:** 이전 77턴 실행은 `츕츕` 변형 3건이 입력에 남았고, 고정 fixture의 generic beat와 pickup 직전 45초 STT만 사용해 VOD 시작부터 끝까지의 줄거리를 연출하지 못했다. 기술적 exit 0은 보존하지만 의도한 방송 연출 품질의 근거로 채택하지 않는다. 다음은 전체 STT 시간축에서 장면/줄거리를 구성하고, 장면별 정제 채팅과 AIRI 방송인 역할을 명시하는 설계 검토다. adoption_authorized=false·운영 flag OFF·GPU/파인튜닝 금지·push 별도 승인은 유지한다.

> **2026-08-27 22:34 KST Codex post-pull 상태 receipt:** 원격 `53befcb`로 fast-forward했고 저장소 내 권위 자산을 확인했다. 지식 배치 41/55/48건은 UTF-8 lint 144/144로 통과했으며 VOD 캡처는 chat 5,243·transcript 500·응답쌍 57행이다. 현재 runtime DB는 과거 상태 `documents=9, chunks=9`이고 새 배치는 아직 적재 전이다. 다음은 runtime 내부 절대경로 복사 → 세 배치 적재 → 고정 6종 probe이며, `goal_status=paused`·adoption_authorized=false·운영 flag OFF·GPU/파인튜닝 금지·push 별도 승인을 유지한다.

> **2026-08-27 22:40 KST 적재 경계:** 기존 runtime DB의 9건과 새 144건은 제목 중복이 없으므로 기존 DB는 보존하고 `ollama-proxy/runtime/airi-knowledge-m7-real-dialogue-20260827.sqlite3`에 평가 배치를 적재한다.

> **2026-08-27 22:41 KST 지식 적재 receipt:** 세 배치를 새 평가 DB에 `41+55+48`건 적용해 `documents=144, chunks=287`을 확인했고, 고정 6종 probe는 `6/6 (100%)`로 통과했다. 기존 9건 runtime DB는 보존했다.

> **2026-08-27 22:43 KST 사용자 정정·다음 intent:** 최종 적재 대상은 기존 runtime DB(`documents=9, chunks=9`)다. 세 배치를 순서대로 적용하며 각 `inserted/updated/duplicate`를 기록한다. 기대 상한은 153건이고 범위 밖이면 원인을 규명하기 전 중단한다. 완료 후 memory ON·knowledge ON 스택의 `/health` 문서 수가 DB와 일치하는지 확인하고, 채점 전 비채택·다음 회차 적용 선언을 기록한다.

> **2026-08-27 22:45 KST 지식 적재 receipt:** game `41/0/0`, meme `55/0/0`, culture `48/0/0` (`inserted/updated/duplicate`)을 기존 DB에 순서대로 적용했다. 최종 `documents=153, chunks=296`, 고정 probe `6/6 (100%)`로 기대 상한 153건 안이다. 다음은 memory ON·knowledge ON 스택 `/health` 대조다.

> **2026-08-27 22:47 KST 실제 대화 스택 intent:** 신규 외부 memory DB를 사용해 memory ON·knowledge ON 스택을 기동한다. `KnowledgeDbPath`는 기존 적재 DB로 고정하고 `/health` knowledge documents=153 일치 확인 전에는 1턴도 시작하지 않는다. 채점 전 비채택·다음 회차 적용 선언과 사용자 직접 채점 방식을 유지한다.

> **2026-08-27 19:xx KST 진척 — 지식 계층이 채워졌다.** 프로젝트 내내 `documents=0` 이던 자리가
> **`documents=145, chunks=289`** 이고 실측 실패 질의 6종이 전부 회수된다. 픽업 점수제 이식은 개선
> 없음으로 **트랙 종료**. 다음은 **계약 §1(b) 진짜 대화 세션 50턴+**. 상세 =
> `진행중/AIRI-CODEX-HANDOFF-2026-08-27.md`.
>
> ⚠️ **2026-08-27 판정 유효성 경고 — 아래 M7 수치를 채택 근거로 쓰기 전에 반드시 읽을 것.**
> **3축 ≥ 3.0 절대 판정은 현재 평가 입력에서 도달 불가능하다.** 사용자가 직접 채점한 198턴에서
> `context_retention` 평균 1.54·4점 이상 0건이고, 3.0 을 넘으려면 나머지 두 축이 평균 3.73
> (실측 1.98의 1.9배)이어야 한다. 입력에 스레드가 없고(99턴에 시청자 96명, 재발화 3%), 더
> 근본적으로 **채팅이 AIRI 에게 온 것이 아니다**(다른 스트리머 커뮤니티의 인사 의식·내부 농담이
> 픽업의 10~12%). 따라서 **S3 `[x]` 는 PASS 도 FAIL 도 아닌 측정 불가**, S2 `[F]`·기준선 1.7576 도
> 같은 한계다. **회차 간 비교는 유효하다** — 같은 입력이면 구조적 감점이 상수로 상쇄된다.
> 무효인 것은 절대 판정 하나다. 또한 s2-r2·s3-r2 는 사람 전수 채점이 아니라 **AI 채점 + 사용자
> 승인**이다(기준선 run 04·06b-r3 는 직접 채점). 상세·근거 =
> `진행중/AIRI-EVAL-INPUT-CONTEXT-AUDIT-2026-08-27.md`, 인계 = `진행중/AIRI-CODEX-HANDOFF-2026-08-27.md`.

## 사용자용 현재 진행 대시보드

> **2026-08-27 22:51 KST stack health receipt:** `/health` memory/knowledge enabled·ready, knowledge `documents=153, chunks=296`으로 DB와 일치, 신규 외부 memory `conversation_message=0`을 확인했다. proxy/latency/TTS가 listening 중이고 STT는 OFF다. 직접 대화 1턴 대기 상태다.

> 이 절이 현재 Goal의 권위 있는 사용자용 요약이다. 수치는 로그 문구 하나가 아니라 실제
> 산출물·PID·receipt를 대조해 갱신한다. 채택 게이트는 **실제 대화 사람 채점**
> (`진행중/AIRI-REAL-DIALOGUE-HUMAN-EVAL-CONTRACT-2026-08-26.md`) 하나뿐이며, 2026-08-26 타계책(`진행중/AIRI-BREAKTHROUGH-PLAN-2026-08-26.md`)에 따라
> 한 run에 한 변수만 바꾸고 복제로 노이즈를 잰다.

- 현재 목표: 스택·기술 한계 돌파 (M8) — 근거 기반 레버를 하나씩 시험하고 조합을 누적해, 고정 VOD 8막·32턴에서 수동 검토 포함 품질 3회 연속 통과를 달성한다.
- 현재 하는 일: M8 개설 직후 — Stage 1a(CRANE식 출력 격리) 구현·실행 준비. 사용자 결정으로 전 실험 게이트가 해제됐고, **모델 변경은 가장 마지막**(Mi:dm 한국어 능력 유지)이다.
- 왜 하는가: validator 튜닝 40회로 “겨눈 결함은 닫히고 다른 결함이 올라오는” 한계를 실증했다(M7 종료, 통과 0/3). 남은 길은 리서치로 확보한 근거 기반 레버들 — 출력 격리·프레이밍·예시·서빙 계층·교정 학습 — 을 순서대로 소진하는 것이다.
- 현재 진행: M8-0(한계 실증·리서치) 완료. 관측 프로토콜 확정: 자동은 바닥 지표만 필수, 판정은 32턴 수동 검토 7항목, 통과 시 재현 2회로 3연속 확정.
- 정지 사유: 없음 — Stage 1a 착수 대기.
- 완료 조건: 어느 Stage에서든 수동 7항목 통과 회차가 재현 포함 **3회 연속** 나오면 M8 성공 종료(채택·운영 반영은 별도 사용자 결정). Stage 1~3 소진 후에도 미달이면 Stage 4(모델 축)와 아키텍처 반전을 판정 재료로 보고한다.
- 다음 작업: M8-1 — story 모드(CRANE식) 구현·red/green·Mi:dm 32턴 fresh run·수동 검토.
- 다음 결정: M8-10 품질 게이트 재정의 승인(자동 지표 바닥 강등·수동 7항목 명문화), 그리고 각 Stage 전환 시점의 결과 확인.

> 현재 인계 불변식: `adoption_authorized=false`, 운영 flag OFF, GPU 학습·파인튜닝은
> 2026-09-09까지 금지이며 다음 PC의 commit/push도 별도 사용자 승인이 필요하다.
- M8 정상 완료율: **3/11 (27.3%)** — 신설 M8(스택·기술 한계 돌파) 11행의 `[x] / 활성 항목 전체`
- M8 처리 종료율: **8/11 (72.7%)** — `([x] + [F]) / 활성 항목 전체`
- M8 진행 지수: **8.5/11 (77.3%)** — `([x] + [F] + 0.5×[P] + 0.5×[~]) / 활성 항목 전체`
- 전체 로드맵 정상 완료율: **74/112 (66.1%)**
- 전체 로드맵 처리 종료율: **87/112 (77.7%)**
- 전체 로드맵 진행 지수: **91/112 (81.3%)** — 127개 행 중 `[S]` 12개와 `[N/A]` 3개를 분모에서 제외; 2026-09-02 11:45 KST 기준. 직전 M7 요약(정상 11/15·처리 13/15·진행 14/15)은 직전 단계 헤딩에 병기
- 마지막 실제 상태 대조: **2026-09-02 16:25 KST (GPU PC = Codex PC)** — local main `79ed8c43d8e228b12f742ce5070951d1f39aa610` = origin/main. Gemma 4 E2B 회차(exit 0, 32/32) 종료 후 shim·llama-server를 내리고 `ollama serve` 0.32.6 복구, 고아 llama-server 0, 11434/11500/11435 모두 free, 로드 모델 0, VRAM 1,158 MiB. 운영 태그 `midm-airi:2.0-mini`와 그 핀은 불변. dirty worktree는 spine-optional 러너·테스트·`reaction_kept` 투영 수정과 현행 문서 배치이며 commit/push 미수행. Gemma 태그 4개와 GGUF는 사용자 정리 결정 대기.

### 현재 주요 작업 단계(M8) 체크리스트

> **M8 = 스택·기술 한계 돌파.** 근거: `진행중/AIRI-VOD-STORYLINE-CEILING-EVIDENCE-2026-08-28.md`
> (한계 실증)와 `진행중/AIRI-METHOD-RESEARCH-2026-08-28.md`(대안 기법 리서치·링크).
> 실행 원칙(2026-08-28 사용자 결정 "전 게이트 해제·할 수 있는 건 다·모델 변경은 최후"):
> ①한 회차 한 레버 — 실패해도 결함 범주가 줄면 다음 레버를 **조합으로 누적**, 결함이
> 불변·악화면 그 레버는 폐기 ②**모델 변경은 가장 마지막**(Mi:dm 선정 사유에 한국어 능력이
> 포함 — 사용자 지시) ③자동 quality_pass는 채점기 부풀림 실증으로 판정자가 아니다 — 자동은
> 바닥 지표(32/32·8/8·금지 시그니처 0·오류 0·반복/고중복 0)만 필수, **판정은 32턴 수동 검토
> 7항목**(구체적 반응 / 새 사건+복선 회수 / 감정 대사 / 반복 0 / 내부 연출어·조언 0 /
> 경험 도용 0 / 무관 지식·시그니처 0) ④수동 통과가 나오면 같은 구성 재현 2회를 더해 **3회
> 연속으로 성공 확정**(비결정성 대비 — run-13 전례) ⑤검증기 적층 재개 금지(약한 verifier
> 반증: arXiv 2404.17140·2508.09074).

- [x] M8-0 한계 실증·대안 기법 리서치 — 두 근거 문서 작성·로드맵 반영 (2026-08-28)
- [F] M8-1 Stage 1a: CRANE식 출력 격리 — 구현·red/green 완료, run-84(환경 결함 발견: CPU에서 프록시 8초 첫 토큰 마감이 콜을 폴백 대체 → 30초 교정, run-81/82 draft 32/32 폴백이었음도 소급 확인)·run-85(구분자 미출력 58/64)·run-86(+형식 시연에도 61/64) — 사전 등록 기준 충족으로 **폐기**. 결정적 발견: 이 스택에서 단일 콜 다문장은 10개 회차 누적 실증으로 불가, 한 문장 콜만 모델의 결. 부산물(30초 교정·story 모드 코드)은 보존
- [x] M8-2 Stage 1b: 스토리 캐릭터 프레이밍(slotwise 캐리어) — run-87 완주·범주 대조 완료: 역할 전도 6→4~5(최악 T01 반전)·세계관 붕괴 1→0·동일내용 9→6~7 감소, 조언·질문 종결·모순 불변, **암묵 자기 경험 ~5턴 증가(감시)**. 규칙에 따라 **유지·조합** (2026-08-28, 수동 통과는 아직 0/3)
- [x] M8-3 Stage 1c: 슬롯별 정제 예시 — run-88(3종 예시)은 순악화(조언 2→7·존댓말 2→4)라 측정이 지목한 viewer_reaction 예시만 제거, run-89에서 **4개 축 전부 최선**(조언 2·존댓말 0·`그 사람` 10·질문 종결 4, 자동 new_event 최초 true). **유지**. 부작용: 예시 오염 2건(T11)
- [F] M8-4 Stage 1d: depth injection·anti-impersonation — run-90에서 순악화(예시 오염 2→7·`그 사람` 10→8·질문 종결 4→7·자동 new_event true→false). 지시 추가가 소형 모델의 표면 패턴 복사를 늘림. **폐기**, `SLOT_DEPTH_REMINDER=""`로 계약 명시(되돌리기 중 발견된 `base[:-0]` cue 전체 삭제 버그도 수리)
- [B] M8-5 Stage 1 최선 조합 재현 — 차단 원인: Stage 1 어느 회차도 수동 통과가 없어 재현할 통과 회차가 없음; 재개 조건: 어느 Stage에서든 수동 7항목 통과 회차 발생
- [F] M8-6 Stage 2: llama-server 평가 병행 — **프록시 무변경**으로 달성(신규 평가 전용 shim + Ollama 번들 llama-server + GGUF 어휘 덤프로 산출한 534토큰 차단). run-92에서 사전 등록한 보장은 지켜졌다: **`?` 11턴→0턴(구조적 제거)**. 그러나 수동 실패 — ①존댓말 미제거(1→1, `꾸셨`의 시/셨 어간이 차단 집합에 없었음) ②의문 **행위**는 생존해 종결부 없는 run-on과 말줄임(0→3턴)으로 변형 ③조언 2→4턴, T07은 위장 손상까지 지어냄 ④자기 경험·역할 전도·반복 불변. 결론: **서빙 계층을 완전히 통제해도 형식만 닫히고 의미는 안 닫힌다**
- [F] M8-7 Stage 3: Mi:dm 교정 파인튜닝 — GPU PC(=Codex PC, RTX 3060 Ti)에서 실행 완료. **정렬 축은 학습이 닫았다**: 조언 8→0턴, 존댓말 3→0, 질문 종결 20→0, 예시 오염 4 hits→0, 2인칭 1→0, 3인칭 주어 9→22. 홀드아웃 4턴(T06·T14·T22·T30)이 학습한 28턴과 동일하게 개선됐고 저작 타깃 184개 대비 문자 재현 exact 0·near 3이라 **암기가 아니라 전이**다. **능력 축은 못 닫았다**: 줄거리에 없는 사실 지어내기·beat 모순·주어 뒤집힘·동일 내용 반복 불변. 데이터 설계 2종(v1 단순 타깃 / v2 감정을 행동에 붙인 타깃)이 서로를 상쇄했고 — v1은 이해가 버티나 문체가 공식화, v2는 문체가 다양해지나 이해가 악화 — 이해가 더 나았던 v1(r2)에서도 ②는 이미 실패라 중간 설계도 통과선 아래다. dev loss는 두 회차 모두 epoch 1에서 최저 후 상승해 168행 코퍼스가 상한임을 실측했다. 수동 7항목 실패, 연속 통과 0/3 (2026-09-01)
- [F] M8-8 Stage 4: 모델 축 진단 — 재개 조건(Stage 1~3 소진·3연속 미달) 충족으로 착수, **연구·평가 전용**으로 3후보를 같은 스파인 하네스·32턴에 태웠다(변수는 모델 하나, 운영 태그 불변, 채택 없음). 라이선스 실측: qwen3 Apache-2.0(채택 논의 가능), kanana-nano CC-BY-NC(진단 전용), adelie 표기 모순(불명). 결과: **셋 다 Mi:dm+Stage 3(5/7)에 못 미침** — adelie-7B는 비일관·환각·한국어 파손으로 최악, qwen3-4b-instruct(thinking은 Instruct-2507 빌드로 해소)는 한국어 자연스러움 실패·입력 복창, kanana-nano-2.1b는 미정렬 Mi:dm 기준선과 같은 결함 계열 재현(크기 대조군 역할 완수). 크기가 도움이 안 됐고 잔여 결함은 "소형 모델이 저작 텍스트 옆에서 자유 문장 하나를 쓰는 대가"라는 구조적 성질로 확정. Mi:dm(MIT) 유지 근거가 선호에서 실측으로 바뀜 사용자 요청으로 4번째 후보 Gemma 4 E2B(Apache-2.0, 공식 text-only QAT q4_0 GGUF)를 추가 평가: Ollama 0.32.6이 gemma4 네이티브 렌더러로 thinking을 강제해 Modelfile로는 끌 수 없었고, Stage 2 shim + CUDA llama-server 경로(`--reasoning-budget 0`)로 no-think 확보. 바닥 전부 통과·한국어 문장 단위는 유창하나 **32턴 중 23턴이 시청자 채팅을 70% 이상 복창**(전 후보 최악, Mi:dm+r4는 0), 주체 전도·조언·비서체 되묻기로 ①③⑥⑧ 실패, **4/7**. 크기가 아니라 cue 아래 복창 성질이라 E4B 2차는 불필요 (2026-09-02)
- [P] M8-9 아키텍처 반전 — 설계에서 **실행까지 진행**. 신규 사이드카 `vod_storyline_20260827_spine.json`(32턴)이 줄거리 전진 두 슬롯을 말하고 모델은 `viewer_reaction` 한 문장만 생성한다(러너 `--rewrite-format spine`, 로더가 스파인도 각 beat 기준 `parse_slot_output`으로 fail-closed 검증). **수동 7항목 중 5개 통과 — 프로젝트 최고, 재현까지 확인**(②지어내기·beat 모순·주어 뒤집힘이 구조적으로 0). 부수 효과로 모델 호출 48→16회, 회차 9~12분→4분. cue 레버 3종(스파인 노출 / +낭독 거부 / 텍스트 없이 역할 축소)은 전부 폐기 — 노출은 완전 복사 9턴·최대 50자, 낭독 거부는 패러프레이즈로 이동, 지시만 주면 모순 2→4턴. **cue에 재료든 지시든 더하면 나빠진다는 3번째 재현**(M8-3·M8-4에 이어). 낭독 거부만 유지. 이어 r4 학습(`viewer_reaction` 타깃만 논평체로 재저작)이 **⑥경험 도용을 2→0으로 닫았으나** ④반복이 새 tic(`제일` 10/32턴)으로 재실패해 **총점은 5/7 그대로**. 잔여 2항목은 모델 문제가 아니라 32슬롯 코퍼스 크기와 저작 문제로 재분류 대기 (2026-09-01)
- [D] M8-10 품질 게이트 재정의 — 자동 지표는 바닥 전용으로 강등하고 수동 7항목을 명문화한 새 통과 계약(사용자 승인 필요)

### 상태 표준과 계산 기준

- `[x]` 검증까지 성공적으로 완료 · `[~]` 현재 실제 실행 중(현재 Goal에서 정확히 하나)
- `[Q]` 실행 준비 완료·순서 대기 · `[ ]` 미착수 · `[P]` 일부 완료·현재 비실행
- `[B]` 차단/보류(원인·재개 조건 필수) · `[D]` 사용자 결정/승인 필요
- `[F]` 실행됐지만 hard gate 실패 또는 no_winner로 종료 · `[S]` 후속 버전으로 대체
- `[N/A]` 선택되지 않은 조건 분기 · `[?]` 증거 대조 중 임시 상태(방치 금지)
- 활성 항목 전체는 `[S]`와 `[N/A]`를 제외한 행이다. `[F]`는 정상 완료에는 포함하지 않고
  처리 종료에는 포함한다. 직전 단계 요약 수치는 각 직전 단계 헤딩에 병기한다.
- 전체 로드맵의 과거 raw checkbox 55행을 코드·테스트·receipt·commit·사용자 결정과 대조했다.
  이 중 노후 상태 31개를 정정하고 복합 항목 분리로 12행을 추가했으며, M5 11행·M6 11행·
  M7 17행(종결)·M8 11행을 포함해 전체 127행이다. 2026-08-28 16:10 실제 파싱 기준 상태별
  개수는 `[x]` 72, `[~]` 0, `[Q]` 2, `[ ]` 5, `[P]` 7,
  `[B]` 12, `[D]` 6, `[F]` 8, `[S]` 12, `[N/A]` 3이며 `[?]`는 없다.

### 직전 단계(M7) 체크리스트 — 2026-08-28 validator 트랙 종료·전 게이트 해제로 M8 개설 (정상 11/15 · 처리 13/15 · 진행 14/15)

- [x] 저장소 VOD 자산·지식 배치 확인, runtime 지식 `153/296` 및 고정 probe `6/6` (Codex PC)
- [x] 고정 8막·32턴 장면 입력과 방송 사적 약속어 제거 계약
- [x] 외부 회차별 transcript/report/HTML 보존 및 구조·반복·맥락·감정·금지 지표 하네스
- [x] Claude PC 재개 — 검토 PC DB 0→`144/287` 적재·probe 6/6, digest(신형 Ollama manifest 직렬화 차이)·shell(pwsh7 Int64) 차이 규명 후 run-81/82를 turn 1부터 완주 (2026-08-28)
- [F] AIRI 반응 품질 자가 테스트(validator 튜닝 트랙) — run-81/82에서 겨눈 결함은 닫혔으나(beat 낭독 10/96→0/96) 수동 품질 통과 0/3, 2026-08-28 사용자 결정 "지금 즉시 중단·정리"로 종료. run-83은 약 12/32 중단·무근거. 근거 `진행중/AIRI-VOD-STORYLINE-CEILING-EVIDENCE-2026-08-28.md`
- [x] 다음 방향 결정 — 2026-08-28 16:0x 사용자 결정 완료: 전 실험 게이트 해제·"할 수 있는 건 다"·**모델 변경은 가장 마지막**(Mi:dm 한국어 능력). M8 단계 순서로 확정

### 직전 M7 실험 체크리스트

- [x] S0 복제 측정 — run 05 구성 3회 재생으로 시그니처 평균·SD, 픽업 결정성 확인, `summarize --baseline` (M7-1) — 2026-08-26 16:59
  `05r1..r3` exit 0: "?" 종결 78/71/15/84·"음" 48/56/1/89(SD ≈30/99, n=1 비교 무효), 픽업 99 id 동일, seed로도 생성 비재현; `f748cae` 3축 합성·`--baseline`
  (`진행중/AIRI-M7-S0-S1-RECEIPT-2026-08-26.md`)
- [x] S1 proxy 되먹임 고리 차단 flag 구현·복제 측정 (M7-2) — 2026-08-26 17:21 `098c887` `AIRI_FEEDBACK_HYGIENE` off/journal/on(기본 off byte 동일,
  테스트 10건, proxy 394 OK, health 노출); 복제 3회: 템플릿 고정("음... 뭐가 X인데?")은 on+브리핑 에코 차단에서 0/3(off 3/4)이지만
  문구 고정(최빈 응답 ≥20/99)은 2/3로 남음("응, 지금 채팅 보고 있어" 39턴 = 비트 큐 되풀이). 참고 채점 3축 1.59(기준선 1.76) —
  되먹임은 증폭기일 뿐 원인이 아니며, 입력(원 방송 화면 전제 채팅) 불일치가 드러남. 운영 기본값 off 유지, 켤 근거 없음
- [x] 사람 채점 — `06b-r3`(S1 최종 arm, 사전 등록 규칙) (M7-3) — 2026-08-26 17:51 사용자 99턴 채점: 방송다움 2.46·맥락 1.49·반응 1.75·말투 4.29·
  사실성 3.25, **3축 1.90(기준선 1.76, +0.14)**, filler 55.6%(+10.1%p), 치명 1.0%(23턴 루머 질문 "응" 시인) — 채택 기준(+0.2) 미달, S1 단독 기각;
  run 05 시트는 미채점(선택) (`진행중/AIRI-M7-S0-S1-RECEIPT-2026-08-26.md` §2-3)
- [x] S6 입력 정합 실행 — VOD 발화(로컬 STT 618세그먼트)를 픽업 직전 45초 assistant 턴으로 공급 (M7-9) — 2026-08-26 19:10 사용자 승인 "추천 방향",
  `5a5e225` `--replay-transcript`; run 07-r1..r3 exit 0: 최빈 응답 8/3/3·고유 77/93/96 — 전 복제 무붕괴(첫 arm), 화면 맥락 정답 최초 출현
  (`진행중/AIRI-M7-S0-S1-RECEIPT-2026-08-26.md` §5)
- [x] run 07-r2 사람 채점 (M7-11) — `ratings-codex-viewer.json` 99/99턴, run 04 대비 방송다움 +0.6465·맥락 +1.4848·반응 +0.9091이나 3축 합성 2.77<3.0, critical 1, filler 22.22%(기준 ≤5%)로 돌파·07 평가 기본 채택 실패; 다음 1변수는 사용자 결정
- [F] S2 오프너 중복 재샘플 — 초안 첫 2어절이 직전과 같고 둘 다 '?'면 seed+1·temperature 0.9로 1회 재샘플 (M7-4) — default-off 구현·`/v1/chat/completions`와 `/api/chat` stream/non-stream red/green 회귀 및 07 replay 3회 완료; r2 사람 채점 99/99턴에서 3축 2.2290·critical 0·filler 76.77%로 돌파 게이트 실패·평가 미채택
- [P] S3 예시 4쌍 — **2026-08-27 `[x]`→`[P]` 강등: 구현·회귀·회차 간 비교는 보존하지만 절대 채택 판정은 측정 불가**. 3축 3.0976 은 ①사람 전수 채점이 아니라 AI 채점 + 사용자 승인이고 ②그 값의 1/3 을 차지하는 맥락 유지 축이 입력 구조상 측정 불가이며 ③절대 기준선 3.0 자체가 이 입력에서 도달 불가능하다. `[~]`는 실제 실행 중에만 쓰므로 인계 정지 상태에서는 `[P]`가 맞다. 상세 = `진행중/AIRI-EVAL-INPUT-CONTEXT-AUDIT-2026-08-27.md` §10. 운영 기본값 OFF.
- [P] S4 픽업 스킵·배치 — 내용 토큰 임계와 합창 batched_chat (M7-6) — 구현·계약·07 replay r1..r3 완료, q_end 중앙값 대표 r2 사람 JSON 대기; 세 회차 `skipped=30`, `batched=0`, 자동 품질 판정 없음
- [S] S5 모델 축 1회 진단 — qwen3:8b, TTS 미기동·전량 GPU·think off·같은 샘플링·seed 2개, 채택 아님 (M7-7) — M8-8(모델 축 진단·최후순위)로 대체·확장
- [x] 민감 루머 질문 "응" 선행 시인 금지 가드 (M7-10) — 2026-08-26 19:10 사용자 승인, `f48b1ed` `deflect_leading_affirmation`(계층 마지막 단계,
  테스트 5건), run 07-r2 24턴 실전 발동 — 단, 이어진 문장이 반쯤 시인하는 한계 확인(후속은 사람 채점 뒤)
- [S] 파인튜닝 재진입 판정 (M7-8) — 2026-08-28 사용자 결정으로 기간 금지 해제, M8-7(Mi:dm 교정 파인튜닝 — Learnability Gap 반영)로 대체. 구 재개 조건의 "3축 < 3.0" 기준은 측정 불가 판정으로 이미 무효

### 직전 단계(M6) 체크리스트 — 2026-08-26 16:55 KST 타계책 확정으로 종결

- [x] 검증된 결정론 계층·grader 수리 commit (M6-1) — 2026-08-26 11:45 `a9583c3` (사용자 승인, push는 별도)
- [x] grounding 게이트 live-broadcast 평서문 침묵 수리 red/green (M6-2) — 2026-08-26 11:53 `cdbb6eb`: 방송 턴에서
  1~4문장·공유 앵커 1개 허용, 날조 가드 유지; HEAD worktree red(1 fail·6 error) → 수정 후 unittest 414 OK
- [x] 실제 대화 export·사람 채점 시트·요약 도구와 평가 계약 (M6-3) — 2026-08-26 11:53 `776b462`: `ollama-proxy/eval/
  human_review/` 3 CLI + 16 tests(CI evaluations shard 등록), 채점 HTML headless 렌더링 확인, 계약 `AIRI-REAL-DIALOGUE-HUMAN-EVAL-CONTRACT-2026-08-26.md`
- [x] 문서 다이어트 — WORKING 이력 아카이브, heartbeat 상한 60/15→120/30분, matrix 14→30분 (M6-4) — 2026-08-26 11:45
- [x] 로드맵 v4 재개편 — 사람 채점 게이트, 파인튜닝 트랙 보류, 체크리스트 정규화 (M6-5) — 2026-08-26 11:45
- [x] 실제 시청자 채팅 확보 — 공개 저챗 VOD 채팅 리플레이 수집·가명화·로컬 스택 재생 (M6-6) — 2026-08-26 12:35: 치지직 4편
  26,436건 수집·16,340건 가명화(저장소 밖), run 04로 99턴 응답 생성(`진행중/AIRI-REAL-CHAT-REPLAY-RUN04-2026-08-26.md`)
- [x] 사람 채점 실행·기준선 확정 (M6-7) — 2026-08-26 14:15 사용자 99턴 채점: 방송다움 1.87·맥락 1.58·반응 1.83·말투 3.60·
  사실성 2.75, 치명 7.1%, 무의미 대꾸 45.5%, 5축≥4 0% (`진행중/AIRI-REAL-CHAT-REPLAY-RUN04-2026-08-26.md` §2-1)
- [x] 기준선 뒤 첫 개선 후보 선택 (M6-8) — 2026-08-26 14:2x 사용자가 추천안 A+B 채택(C 보류)
- [S] A+B 구현·run 05 재생·사람 채점 비교 (M6-9, 사람 채점은 M7-3으로 이관) — 2026-08-26 15:35 구현 `beb0559`(계층 P5·재생 티어·되먹임 위생, 364 passed·
  proxy 414 OK), run 05 99턴 exit 0: 치명 0·축자 인용 0·"고마워." 0이지만 "음... 뭐가 X인데?" 되묻기 붕괴 37턴; Claude 참고
  채점 방송다움 1.70·맥락 1.65·반응 1.81·말투 4.22·사실성 3.94, 무의미 대꾸 81% (`진행중/AIRI-REAL-CHAT-REPLAY-RUN05-2026-08-26.md`). 사용자 채점 대기
- [x] 타계책 탐색 — 렌즈 4개·반박 검증 워크플로로 "코드 vs 파인튜닝" 이분법의 실제 병목 규명 (M6-10) — 2026-08-26 16:35
  `진행중/AIRI-BREAKTHROUGH-PLAN-2026-08-26.md`: 되먹임 고리(proxy `_short_direct_answer`·journal assistant 회수), 재료 수용 0/12, n=1 측정
- [S] 타계책 S0·S1 승인과 run 05 사람 채점 (M6-11, M7-1~3으로 이관) — 순서 S0→S1→S2→S3→S4→S5,
  한 run 한 변수, 돌파 정의 3축 합성 ≥3.0·critical 0·filler ≤25%; 파인튜닝 2주 금지

### 직전 단계(M5) 체크리스트 — 2026-08-26 11:29 KST 사용자 결정 C로 피벗 종결

- [x] d1v6 잔여 실패 축 원인 분리 진단 (M5-1) — 2026-08-26 10:45: polite 43행 = v6 opener
  저작 artefact, invented 5 = substring 충돌 2 + briefing author pool 불일치 3, transition
  miss 89 = grounding 침묵 폴백 72/모델 15/어느 2, probe miss 32 = P3 미발동 29/폴백 2/근거 부재 1
- [x] 최소 결정론 수리 red/green 구현 (M5-2) — 2026-08-26 11:20: 계층 6항목·proxy 1곳·harness
  grader pool; pre-fix worktree 새 테스트 FAIL → 수정 tree PASS
- [x] affected offline 회귀와 기존 실패 경계 분리 검증 (M5-3) — 2026-08-26 11:20: pinned pytest
  90/251/494 passed(알려진 behavior-v2 2건 분리), core suite 1140 passed, unittest 405 OK, 계약 PASS
- [S] 새로운 blind v7 fixture 3종 저작·봉인·commitment·synthetic comparator 확인 (M5-4) — 2026-08-26 11:29
  사용자 결정 C로 중단·대체(실태 파악). seal 도구 편집 되돌림, staging 미생성
- [S] 48회 평가 preflight 및 exact-once wrapper 시작·감시 (M5-5, d1v7 matrix) — 사용자 결정 C로 대체
- [S] 비교 결과 판정과 실패 축 진단 (M5-6) — 사용자 결정 C로 대체
- [S] winner일 때만 장시간 방송 campaign 실행 (M5-7) — 사용자 결정 C로 대체
- [S] 문서·전체 검증·정확한 commit/push 마감 (M5-8) — 사용자 결정 C로 대체(M5-10으로 재정의)
- [x] 공회전 실태 파악과 파인튜닝 검토 문서 작성 (M5-9) — 2026-08-26 11:29 `AIRI-REALITY-CHECK-AND-FINETUNE-REVIEW-2026-08-26.md`
- [x] 현행 문서 전면 갱신·계약 재검증 (M5-10) — 2026-08-26 11:29: WORKING/ROADMAP/LOG/NEXT/두 handoff/
  INDEX/D1 §10 동기화, patch·checkpoint·continuity·dashboard 계약 PASS
- [x] 실제 대화 데이터·사람 채점 평가, grounding 게이트 수리, step 2 코드 commit 결정 (M5-11) —
  2026-08-26 11:45 사용자가 4건 모두 승인(문서 다이어트 포함) → M6로 이관

### 직전 완료 단계(M4) 체크리스트 — 2026-08-26 10:10 KST 종결, 9/9 정상 완료

- [x] 방송 경로에 결정론 입력 계층 연결 (M4-1)
- [x] live 경로 통합 회귀 테스트 추가 및 red/green 입증 (M4-2)
- [x] 거부된 분기 인식 확장과 기존 v5 연속성 12/12 확인 (M4-3)
- [x] 새로운 blind v6 fixture·봉인·commitment·CI 계약 준비 (M4-4)
- [x] 48회 평가 preflight 및 exact-once wrapper 시작 (M4-5)
- [x] 비공개 48회 비교 평가 실행·감시 (M4-6, d1v6 matrix) — exit 0, 48/48, attestation·정리 검증
- [x] 비교 결과 판정과 실패 축 진단 (M4-7) — no_winner, failed gate 29개 P2~P5 귀책 기록
- [N/A] winner일 때만 장시간 방송 campaign 실행 (M4-8) — no_winner 분기가 선택되어 실행 대상 아님
- [x] 사용자용 로드맵 대시보드 공용 스킬 만들기 (M4-9) — 공통 계약·두 진입점·불변식 검증 PASS
- [x] 문서·전체 검증·정확한 commit/push 마감 (M4-10) — 사용자 승인, Claude handoff 포함
  final publication transaction과 post-push exact 검증으로 마감

### 짧은 용어집

- 주요 작업 단계(M): 이 대시보드에서 `M`은 Milestone이다. 현재 M7의 범위는 “타계책 실행 — 런타임 되먹임
  고리 차단과 1변수 실험”이며, 하단의 과거 M1~M6 분류는 전체 로드맵 감사 때 현재 상태 표준으로 재분류한다.
- 되먹임 고리: 런타임이 AIRI의 직전 응답(history·브리핑 echo·journal 회수)을 다음 프롬프트에 되돌려 넣는 경로.
  되돌린 문형이 다음 붕괴 모드가 된다(run 04 "고마워.", run 05 "음... 뭐가 X인데?").
- 3축 합성: 사람 채점 5축 중 방송다움·맥락 유지·반응 적절성의 평균. 돌파 기준 ≥ 3.0(기준선 1.76). 말투·사실성은
  하한만 둔다(filler 악화를 가리므로 5축 평균으로 판정하지 않는다).
- 복제: 같은 구성·같은 99턴 입력을 2회 이상 재생해 자동 시그니처의 노이즈를 재는 것. 사람은 그중 1회를 채점한다.
- 사람 채점: 실제 대화 50~100턴을 5축(방송다움·맥락·반응·말투·사실성) 1~5점과 플래그로 채점하는
  유일한 채택 게이트(2026-08-26~)
- blind 평가: 합성 fixture 봉인 평가 — 2026-08-26부터 채택 게이트가 아닌 결정론 계층·배관 회귀 도구
- matrix: 고정된 모델·fixture·seed 조합을 빠짐없이 실행하는 비교 평가 묶음
- verdict: 모든 고정 게이트를 적용해 winner 또는 no_winner 분기를 내리는 최종 판정
- campaign: winner 뒤에만 수행하는 3개 seed×500턴 장시간 방송 근사 검증
- P1 근거 풀 확장: 요청 history를 근거로 인정 · P2 과거 전용 토큰 가드: 현재 근거 없는
  과거 토큰을 안전한 지시어로 치환 · P3 결정 회수: 확정한 선택/사실을 근거에서 찾아 답변
- P4 거부 선택 억제: “A 말고 B”에서 거부된 A를 응답에서 제거 · P5 후원 이어말하기 보강:
  후원 본문 공유 토큰과 감사 표현이 없을 때 보수적인 인용 감사 문장을 추가

> **이 문서가 프로젝트 최상위 SSoT다.** 부속 문서(GROWTH-STRATEGY·
> MODEL-CUSTOMIZATION-PLAN·NEUROSAMA-LOW-LATENCY-PLAN)와 충돌하면
> 이 문서가 우선한다. 갱신 로그는 `AIRI-ROADMAP-LOG.md`로 분리했다 —
> **매 배치(커밋)마다 로그 파일에 기록**하고, 이 문서는 상태가 실제로
> 변할 때만 고친다. v2 원문(트랙 상세 이력 포함)은
> `아카이브/AIRI-ROADMAP-STATUS-v2-SNAPSHOT-2026-08-19.md`에 동결 보존.

> **2026-08-26 11:29 KST M5 피벗 — 사용자 결정 C(공회전 중단):** 사용자가 5라운드 blind 대화를 HTML 뷰어로
> 확인한 뒤 "방송 같지 않다"고 판단해 v7 저작·매트릭스·campaign을 중단시켰다. 실태 파악 결과는
> `진행중/AIRI-REALITY-CHECK-AND-FINETUNE-REVIEW-2026-08-26.md`: 08-19 이후 commit 156, GPU 후보 4(채택 0), blind 6라운드
> 216 report 전부 no_winner(원인 대부분 계측·저작 결함), 운영 모델 stock Mi:dm 2.0 Mini Q4, 실제
> 시청자 데이터 0, 사람 검수 0. 파인튜닝은 중단 권고. 합성 blind 매트릭스는 채택 게이트에서
> 회귀 도구로 격하한다. step 1~3의 진단·수리·검증은 유효(로컬, 미커밋). adoption=false.

> **2026-08-26 10:40 KST M5 활성화 — d1v6 잔여 게이트 분리 진단 시작:** 사용자가 POST-M4
> handoff의 Goal 명령을 Claude에 제출해 M5가 활성화됐다. 시작 대조는 HEAD/local/origin/remote
> `d7c6283` exact·clean, d1v6 terminal 48/48·exit 0·no_winner(29 gate)·listener 0이다. step 1에서
> 채점된 report만 read-only로 써서 공통 polite 43행이 전부 `opinion`/`wave_opener` 행임을, invented
> handle 5행 중 baseline 2행은 roster handle `모아`와 동사 활용의 substring 충돌임을 확인했다.
> P3 probe/required miss와 e2-c2 3행 귀책은 대조 중이다. matrix·campaign·GPU·adoption은 0이다.

> **2026-08-25 22:55 KST M4 §3.1~§3.4 완료 — d1v6 preflight·precommit PASS:** live 결정론 계층이
> 주입된 브리핑·후원 note를 받도록 배선했고 pre-fix 2 FAIL → 수정 후 2 PASS, P3 v5 arc
> 12/12를 확인했다. 새 blind v6는 v1~v5와 topic 불일치, handle-topic collision 0을 독립
> 감사한 뒤 정확히 한 번 봉인했고(manifest `18a1987f...1c2e`), commitment/launcher/verifier/
> CI 및 실제 comparator synthetic 48-report를 PASS했다. fresh external root의 실제
> `-PreflightOnly`도 48/48 unique run, num_ctx 4096으로 PASS했다. flag OFF exact와 P3 predicate
> P1 수리 후 proxy/runtime 403 OK, affected 435 passed/3 skipped/276 subtests, 독립 P0/P1/P2 0이다.
> 다음은 exact 20-path repo commit/push
> 뒤 exact-once matrix다. matrix·campaign·GPU 학습·adoption은 아직 0.

> **2026-08-25 21:22 KST M3 — d1v5 재측정 `no_winner`, 결정론 계층 배선 결함 확정:** blind v5로
> 4-arm 48-report를 재실행해 계측이 실제로 작동함을 확인했다(`service_error` 0, memory_probe
> 36/40, `unknown_identity_safe` 학습 arm 1.0, 점수 0.34~0.37 — D1 0.11의 3배). 그러나
> `winner=null`: **live-broadcast 경로에서 결정론 계층(P3/P4/P5)이 주입 전 메시지만 받아 브리핑·
> 후원 note를 보지 못한다**(P3 폴백 62~65/80, P5 미발동). 그 밖에 P3 정규식 공백(1글자 토큰),
> v5 handle의 주제 명사 충돌(채점 artefact), 부정 교정문 decoy. comparator의 v4 하드코딩
> verifier도 v5까지 받도록 수정. 병렬 branch(legacy F5/F6·게이트 evidence 바인딩·P2-4b·P3-T4
> 설계) 병합. **다음 라운드(계층 입력 배선 수정 + live 경로 통합 테스트 + blind v6)는 사용자
> 결정.** adoption=false.

> **2026-08-25 17:05 KST M2 완료 — greybox 평가 기준선 박제:** lm-eval(kobest·haerae)로
> 일반 능력이 stock→v3→e2c2 순 단조 하락(kobest −0.90%p, haerae −1.92%p, 제안 게이트 ≤2%p
> 안·경계)임을, llama.cpp perplexity로 v3 Q4_K_M 손실이 비율 1.0181(≤1.05)임을 처음 계측했다.
> 증거 `완료/AIRI-M2-GREYBOX-EVAL-2026-08-25.md`. 남은 사용자 결정: 새 blind v5로 4-arm 재측정,
> 일반 능력 게이트 강제, native_baseline 픽스처 핀 수리. adoption=false 유지.

> **2026-08-25 16:24 KST M2 배치 A — 계측 근본 원인 수리·F7 게이트·검토 문서 편입:**
> 프록시 400 `exceed_context_size_error`의 고정비는 GGUF 내장 KT 프리앰블 ≈514토큰(Ollama가
> Modelfile TEMPLATE를 무시, GPU PC 패키징 태그 재검증: user 1건 `prompt_eval_count` 514)이라
> `num_ctx` 기본값을 2048→**4096**으로 올렸다(프록시 `NUM_CTX` + 세 런처, 태그 재패키징 0,
> `/health`에 `context_exceeded_observations` 추가). campaign 런처에 blind comparator 승자
> exact tag/digest 게이트(R2 F7)를 넣어 `no_winner`·digest 불일치를 서비스 기동 전에 거부한다.
> 검토 PC 문서 2건을 `참조/`에 시점 고정으로 편입했다. 다음은 lm-eval·llama.cpp perplexity
> greybox 기준선. 재측정용 새 blind와 adoption은 별도 승인.

> **2026-08-25 13:05 KST D1 종결 — 48-report matrix 완주, `winner=null`, campaign 미실행:**
> exact-once detached matrix가 12:38:14 KST에 exit 0으로 끝났다(reports/health/
> run-contract/packets/runtime 48/48, 두 런타임 플래그 48/48 attest, comparator
> `airi.d1-blind-comparison.v1` `status=pass`). **`winner=null`(45 게이트 실패)이라 goal의
> `no_winner` 경로대로 3×500 campaign을 실행하지 않았고 자동 후속 라운드도 없다.**
> score baseline 0.1058 / e2 0.1093 / e2-c1 0.1170 / e2-c2 0.1089.
>
> 채점 후 원문 열람으로 확인한 실패 원인은 **모델도 임계값도 아니라 계측 결함 2건**이다.
> ① 프록시 `LOCAL_ERROR_DIALOGUE`가 전 arm 턴의 33.9~35.3%를 차지한다 — D1 고유가
> 아니라 E2-C1 30.3~31.6%, E2-C2 37.2~38.6%로 **세 blind 라운드 공통**이며
> `summary.fallback`이 세지 않아 지금까지 보고된 적이 없다. ② **P3
> `answer_recall_question` 과발동(D1 신규 회귀)** 이 `continuity_callback` 320행 중
> 176행(55%)을 회수 폴백으로 대체해 `long_callback`·`complete_show_arc`를 정확히 0.0으로
> 만들었다. `unknown_identity_safe`는 분모 12행이 전 arm 전부 차단이라 측정 자체가
> 불가능했다. `invented_handle`은 5/4/8/6으로 v2(28/40/53)·v3(14/27/33) 대비 85% 감소하고
> 학습 단조 악화도 사라졌으나, 감소분 일부는 발화 부재의 산술 효과라 가드 공로로
> 승격하지 않는다. 프록시 오류의 근본 원인은 프록시 stdout 미보존으로 **미확정**이다.
> 실패 root 보존, blind v4 소비·재사용 금지, hard gate 완화 0, adoption=false 유지.
> **다음 방향은 사용자 결정 사항이다.** 상세: `진행중/AIRI-D1-DETERMINISTIC-LAYER-CONTRACT-2026-08-25.md` §6.

> **2026-08-25 10:27 KST D1 matrix 실행 유지, 감독 Claude 이관:** exact-once detached
> wrapper PID 7832는 live이고 reports/health 15/48, stdout 75,211 B, stderr 0 B,
> exit receipt absent다. Codex monitor subagent만 종료했으며 matrix launcher·wrapper·
> 서비스에는 제어 0이다. blind v4는 소비됐고 재실행·재사용 금지다. Claude는
> `진행중/AIRI-D1-CODEX-HANDOFF-2026-08-25.md`를 단일 진입점으로 read-only 감시를
> 이어받아 48/48 후 D1 comparator verdict 분기만 수행한다. Codex는 더 이상 감시·
> verdict·campaign을 수행하지 않는다. adoption=false 유지.

> **2026-08-25 09:26 KST D1 launcher SHIPPED + preflight PASS — matrix intent 대기:** `d1`
> 4-arm/48-run, guard+deterministic layer ON/복원, 두 `/health` attest, D1 comparator
> 배선을 구현·검증해 `9e6b1f4`+receipt `a510004`로 origin/main push했다. 기존
> t3/e2c1/e2c2 3-arm/36 동작은 계약 테스트로 유지된다. model manifest SHA
> `050ae10f...e330`, `-PreflightOnly` 48/48 unique key와 v4 binding PASS, OutputDir와
> 응답 생성 0이다. 다음은 detached wrapper 고정 → 별도 intent 뒤 matrix 정확히 1회다.
> adoption=false 유지.

> **2026-08-25 07:10 KST D1(결정론 계층) 진행 중 — 3/5 단계, 코덱스 인계:** 두 학습
> 후보의 실패를 받아 로드맵 v3 원칙(프롬프트/학습보다 결정론 계층)대로 **GPU 학습 없이**
> 게이트를 코드로 닫는 라운드다. 계층 구현(P1~P5, 기본 off)·blind v4 봉인·D1
> commitment/policy/verifier·4-arm comparator·CI 등록까지 push(`a3f2f39`). 남은 것은
> launcher `d1` 프로파일(4 arm/48, 가드+계층 ON 강제) → 48-report matrix → winner면
> 3×500 campaign / no_winner면 진단 후 대기. threshold 완화 0, adoption=false 유지.
> 인계 문서: `진행중/AIRI-D1-CODEX-HANDOFF-2026-08-25.md`.
>
> **2026-08-25 02:40 KST E2-C2 no_winner 종결:** 언더트레이닝 교정 후보 E2-C2(1536/96,
> LR 2e-5, 3 epochs — dev loss 2.24→1.61)를 새 blind v3(가드 신호 ON 측정)에서 36-report로
> 평가한 결과 **winner=null이며 후보 score(0.1875)가 E2(0.2019)보다 낮았다**(첫 역전).
> invented_handle은 가드 신호 ON에도 14/27/33으로 학습 단조 악화. 진단: dev 개선과 blind
> 후퇴의 절연(좁은 교정 도메인에 6× 선량 → 표면 과적합), 전 arm이 절대 최소선 2-4× 미달 —
> 선량/LR 조정으로 닫힐 격차가 아니라는 것이 두 후보(E2-C1/E2-C2)로 실증됐다. campaign/
> adoption 금지 유지, 실패 root 보존, blind v1/v2/v3 전부 소비됨. **다음 방향은 사용자
> 결정 사항**(자동 E2-C3 금지). 상세: `진행중/AIRI-E2-C2-FROZEN-CONTRACT-2026-08-24.md` §7.

> **2026-08-24 16:33 KST 진단 완료 + 핸들 grounding 가드/채점기 신호 SHIPPED:**
> no_winner 원인은 e2-c1 자체가 아니라 채점기 사각지대였다 — invented_handle 53건 중
> 47건(89%)이 실제 memory 회수였고, 그중 vocative(-님) 형태는 7건(13%)뿐, 46건(87%)은
> 일반 명사 사용이었다(forensic 재검토로 확정, 프로덕션은 roster가 없어 문법 신호
> 외에 handle을 식별 못 함). 사용자 "1과 2함께" 승인으로 신규
> `handle_grounding_guard.py`(기본 off)가 이번 턴 실제 근거 풀을 한 번 계산해 -님
> vocative만 좁게 가드하고, 그 계산의 memory/journal 부분을 기존 in-band SSE 신호로
> 항상 노출 — 시뮬레이터가 roster 부분일치로 `fact_tokens`에 합쳐 게이트 정의는
> 그대로 두고 판정 입력 범위만 넓힌다. 구현 중 실제 버그 1건 + 이중 flag 위험 1건을
> 잡아 회귀 테스트로 고정. 신규 16 + 프록시 373 + 시뮬레이터/코드체인 88+85 + blind
> commitment 6 전부 pass, `test-current-checkpoint.ps1`/work-continuity PASS. commit
> `a0020dd`(fix)+docs 3개로 `59d1836`까지 push. E2-C1 학습 계약(§frozen 1-10)은
> 불변 — 다음은 이 근거로 학습량/LR을 재검토한 **E2-C2**를 새 blind로 설계하는 것.
> 상세는 frozen contract §12·handoff §-7.
>
> **2026-08-24 15:14 KST E2-C1 36-report blind matrix 결과 — no_winner:** 한국어로 재봉인한
> blind v2로 baseline/e2/e2-c1 36 reports를 완주했다. score는 e2-c1 0.244(최고)지만
> `invented_handle` 위반이 28→40→**53**으로 학습할수록 악화해 13개 hard/legacy/perfect-rate
> 게이트가 전부 실패, `winner=null`이다. `adoption_authorized=false`·campaign 금지 유지.
> 사용자 승인 순서: e2-c1 invented_handle 원문 진단 → roster 밖 한국어 인명을 거르는
> 결정론 런타임 가드 설계 → 남는 축은 학습량 재검토한 E2-C2를 새 blind로 재도전(같은
> data로 epoch만 늘리는 E3는 아님). 상세는 frozen contract §11·handoff §-6.
>
> **2026-08-24 09:47 KST 사용자 `/goal` — GPU 제한 없음:** E2-C1 bounded smoke → durable 본 학습
> step 0 → merge/package → baseline/E2/E2-C1 36 reports → gate 판정이 연속 허가됐다. winner면
> 3×500 campaign을 즉시, no_winner면 실패 축 분석·새 blind 봉인·E2-C2까지 재확인 없이 진행한다.
> T3 invented-handle read-only 진단과 T-05 126번 A/B 샘플은 병행한다. 금지는 blind 확인 뒤
> 계약 변경·blind 재사용·hard gate 완화, 운영 모델/태그 변경·외부 provider/extraction/greybox
> ON·126번 승격뿐이며 adoption은 별도 승인이다. 감독은 Claude Fable 세션, 워커는
> `.claude/agents/` implementer(opus)/worker(sonnet)/scout(haiku)다.
>
> **2026-08-24 E2-C1 adapter-init offline PASS / published:** 사용자는 E2 adapter
> weight를 검증된 초기값으로 사용하고 optimizer/scheduler/RNG/cursor는 새로 시작하는
> 교정 후보 `E2-C1`을 승인했다. correction 480 + 검증된 v4 replay 200 + mixture 680과
> 새 retained blind 3종·4 seeds·baseline/E2/E2-C1 36-report 평가 계약을 GPU보다 먼저
> 동결했다. final 한국어 감사에서 확인한 `으로/로` target 오류 exact 5건과 validator
> 공백은 최소 helper/template/verifier/mutation 수리로 닫았고, current bytes의 full unit,
> blind commitment, generator byte check, repository/external verifier, independent semantic/
> grammar/split/replay/collision 감사와 diff/security가 PASS했다. milestone `2e61842`와 receipt
> `3dba3ca`는 origin/main에 push됐고 직후 HEAD/local·remote exact, clean, PID 0이다. 따라서
> `freeze_status=pass`, E2-C1 0/0, 관련 AIRI PID 0이다. trainer/builder/runner/verifier의 E2
> weights-only init, fresh optimizer/scheduler/RNG/cursor/progress, v2/v3 provenance와 closed-
> inventory fault 회귀는 pinned pycompile, focused 27/2·50/2·67/1, combined 144 passed/
> 5 skipped, continuity/full current-checkpoint/diff-check와 actual E2 helper를 PASS했다.
> implementation `6dd2412`와 receipt `3c4b1a9`는 origin/main에 push됐고 HEAD/local·remote
> exact, clean, PID 0을 확인했다. 다음 gate는 review PC의 mandatory reconciliation 뒤 별도
> intent를 쓰는 bounded GPU smoke이며 이 인계 배치에서는 `gpu_authorized=false`다. 계약은
> `진행중/AIRI-E2-C1-FROZEN-CONTRACT-2026-08-24.md`를 따른다. 운영 채택과 기본 모델·태그
> 변경 금지는 유지한다.

> **2026-08-23 E1/E2 사용자 검토:** baseline/E1/E2는 모두 같은 Mi:dm 계열의 기존
> broadcast v3/continuity-v4 1 epoch/2 epoch 후보다. 1,248턴씩에서 E2는 E1 대비 topic
> 572→586, fact 180→193, memory 8→11, invented handle 46→37, callback 6→8,
> complete arc 1→5로 상대 우세하고 dev loss도 epoch 1 `2.893371758116589`에서 epoch 2
> `2.735453106217887`로 낮아졌다. 그러나 final blind invented handle은 E1 26→E2 34로
> 악화했고 long memory는 양쪽 0/12, E2 donation은 55/56이다. 따라서 E2는 교정 학습의
> 검토상 우세한 출발점일 뿐 T3 승자·운영 채택 모델이 아니다. same-data 3 epoch 반복은
> 승인·권고하지 않으며 새 교정 데이터·비오염 blind·후보 범위를 별도 사용자 intent로
> 고정하기 전에는 학습/T3/campaign을 실행하지 않는다. response-bearing 24 reports는
> external T3 root에만 보존한다.

> **2026-08-23 authoritative T3 terminal FAIL:** controlled GPU와 E2 1,600/1,600,
> E1/E2 merge·BF16/Q4_K_M package는 완료·미채택이다. external root에서 baseline/E1/E2
> 각 12, 총 36 reports와 두 comparator를 실행했으나 양쪽 comparison이 모두 schema v1,
> `status=fail`, adoption false, paired reports 0, reason `polite violation or invented handle`로
> 종료했고 launcher exit 1, `summary.json` absent다. 전 arm transport failure는 0이나 invented
> handle baseline/E1/E2 30/46/37, memory 5/36·8/36·11/36, fact
> 173/752·180/752·193/752, donation 56/56·56/56·55/56이다. comparison 두 파일은 각
> 196 bytes SHA `5f2b4213...3afa`; report/packet/evidence/runtime/comparison inventory SHA는
> `e5241341...16b4`/`00b90c95...859a`/`7cb97aea...3dee`/
> `0417f814...4e8a`/`5a4793b9...d75`다. 관련 PID/listener 0, winner 0이므로 campaign과
> adoption을 금지한다. blind가 공개된 같은 matrix를 반복하거나 hard gate를 낮추지 않는다.
> terminal failure 다섯 SSoT commit `d3724b1`은 `90a436e..d3724b1 main -> main`으로
> origin/main push됐고 HEAD/local·remote exact, 관련 PID/listener 0을 확인했다.

> **2026-08-23 T3 journal blocker 최소 수정·실서비스 smoke PASS:** E2는
> 1,600/1,600 microsteps·100/100 optimizer steps, selected epoch 2 dev loss
> `2.735453106217887`로 완료됐고 E1/E2 merge·BF16/Q4_K_M package와 exact model
> manifest도 완료·미채택이다. T3 `journal_pending`의 원인은 OpenAI SSE 오류 경로가
> public fallback과 terminal을 정상 전달하면서 같은 trace journal을 예약하지 않은
> false-success였다. exact public fallback을 terminal 전에 durable 예약하도록 최소 수정했고
> targeted 2, 영향 113, proxy 370, simulator 63, continuity/current-checkpoint gate가 모두
> PASS했다. baseline/첫 승인 fixture/seed 11 실제 1-turn smoke는
> `transport_failures=0`, `live_receipt_bound=true`; report SHA는
> `6193fb80...26886`이다. authoritative T3 36 `summary.json`과 campaign은 아직 0이며,
> 수정 commit/push·clean 뒤 새 외부 root에서 T3 36을 실행한다. GPU 학습은 없고 baseline
> Ollama 추론 모델만 로드돼 있다. `adoption_authorized=false`를 유지한다.
> fix/test+필수 SSoT commit `80160a1`은 `9724833..80160a1 main -> main`으로 push됐고
> 직후 HEAD/local/remote exact·worktree clean이었다. push receipt 문서 commit 뒤
> authoritative T3 36으로 이동한다.

> **2026-08-23 controlled GPU P0-B PASS receipt:** Goal status는 `active`다. 첫 K=5
> baseline은 480/30 계산 뒤 actual checkpoint interval max `705.902827`초와 final-evidence
> 결속 실패로 FAIL해 보존했고 같은 K=5를 반복하지 않았다. final-evidence SHA 의미 혼동을
> exact internal manifest receipt row에 결속해 pinned Python `146 passed, 5 skipped`,
> actual-process PowerShell durability와 final offline gate로 최소 수리했다. fresh K=3 root의
> 무중단 baseline과 실제 `SAFE_TO_POWER_OFF` pause/checkpoint/resume arm은 모두 terminal
> 480/30이다. 권위 equivalence receipt SHA `d913992e...e84b9`는 `pass=true`, adoption false,
> 672 tensors exact/max abs·rel 0, normal interval 10개/max `551.5176357`초다. Windows
> producer/verifier의 `README.md` 순서 false reject는 platform `Path` 순서 한 줄과 targeted
> 회귀로 최소 수정했고 suite 62 passed/1 skipped, actual GPU verifier와 final offline gate도
> PASS했다. verifier/test+five SSoT commit `87dfabd`와 commit receipt `29080be`는
> `0454ca8..29080be main -> main`으로 origin/main push됐다. actual push receipt five-doc의
> final commit/push 및 clean 확인 뒤에만 authoritative E2를 step 0부터 시작한다.
> `goal_status=active`; E2 microstep 0, 운영 채택과 기본 모델 변경 금지는 유지한다.
>
> **이전 권한 이력 — 2026-08-22 goal resume:** 사용자 `/goal` 명령으로 당시 AIRI 본 goal은 `active`였다.
> 저장소 구현·GPU 학습·모델 병합/패키징·로컬 서비스·T3·장시간 캠페인과
> 검증된 milestone commit/push가 승인됐다. 운영 채택과 기본 모델 변경은 별도
> 사용자 승인 전까지 금지한다. E1 adapter/report만 존재하고 E2·후속 산출물은 0이며,
> P0-A offline 구현·fault 실증과 독립 P0/P1 0 감사는 완료되어 `6f0c1358`로
> origin/main push됐다. P0-B checkpoint timing/exact-equivalence evidence gate와
> external expected-run 결속도 offline 회귀·독립 P0/P1 0 감사를 거쳐
> `e970cf7`·`8cd69b5`로 origin/main push됐으며, E2보다 먼저
> safe-pause의 exactly-one verified active-run 자동 탐지도 0/1/multiple/spoof/
> corrupt-current actual-process 회귀와 독립 P0/P1 0을 통과했다. 이어서
> P0-B controlled GPU 동등성·실제 속도 10분 checkpoint 상한을 실증한다.
> 현재 `goal_status=active`; pause 인계 이력은 `goal_status=paused-user-session-handoff`;
> `adoption_authorized=false`;
> `execution_order=P0_A>P0_B>E2_LAUNCH>E2_PROVENANCE>PACKAGE>T3_36>CAMPAIGN_3X500>USER_DECISION`

> **장기 작업 지속성:** 세션 시작·goal resume·재부팅·compact 직후에는
> `진행중/AIRI-WORKING-STATE.md`를 먼저 전체 읽고 실제 goal status·HEAD·PID·
> 산출물과 대조한다. active goal은 최대 60분 heartbeat 및 단계 전후
> intent/receipt checkpoint를 남긴다.

- 표기: `[x]` 완료(일자) / `[~]` 진행중·부분 / `[ ]` 미착수 /
  `(보류: 재개 조건)`. 완료 표시는 근거 문서·커밋 필수.

## 0-1. v4 재개편 (2026-08-26, 사용자 결정 C)

v3 개편 뒤 7일 동안 GPU 학습 후보 4개와 합성 fixture blind 매트릭스 6라운드(216 report, 전부
no_winner)를 돌렸지만, 실패 원인의 대부분은 계측·저작 결함이었고 대화는 방송과 닮지 않았다.
운영 모델은 stock Mi:dm 2.0 Mini Q4 그대로이고 실제 시청자 데이터·사람 검수는 0이었다
(`진행중/AIRI-REALITY-CHECK-AND-FINETUNE-REVIEW-2026-08-26.md`). v4 원칙:

1. **채택 게이트는 실제 대화 사람 채점 하나다**(`진행중/AIRI-REAL-DIALOGUE-HUMAN-EVAL-CONTRACT-2026-08-26.md`).
   합성 시뮬레이션·정규식 게이트는 결정론 계층과 배관의 회귀 가드로만 쓴다.
2. **파인튜닝은 2026-09-09까지 금지**한다. 재진입 조건(전부): S1~S5 뒤에도 3축 합성 < 3.0, S5에서 큰 모델이
   +0.6 이상(용량 병목 실측), 실제 채팅 입력 + 사람 4점 이상 검증 답변 ≥ 300턴. 학습 데이터의 유일한 출처는
   사람 채점 루프다(합성 템플릿 금지). 기존 어댑터는 보관·채택 금지.
3. 실제 방송에서 바로 드러나는 배관 결함(grounding 침묵 등)을 먼저 고친다.
4. 절차 비용을 실질 아래로 내린다(heartbeat 120/30분, live state 아카이브).
5. **(타계책, 2026-08-26) 런타임이 모델에게 되돌려 보여주는 자기 출력은 통제 변수다.** history·브리핑 echo·journal
   회수는 모델을 재기 전에 먼저 고정한다(`진행중/AIRI-BREAKTHROUGH-PLAN-2026-08-26.md`).
6. **한 run에 한 변수**({모델, 프롬프트, 결정론 계층, history/재료, 픽업} 중 하나), 사전 예측 등록, 복제 ≥ 2,
   사람 채점 1회. 정규식 시그니처는 채점자에게 표시만 하고 판정·kill에 쓰지 않는다.
7. 규칙 문장 추가·문형별 땜질·메모형 브리핑 줄 추가·저널 시청자 행 주입은 하지 않는다(반박 검증에서 기각).

## 0. 왜 갈아엎었나 (v3 개편 배경 — 사용자 진단 2026-08-19)

v2 체제의 사이클은 "평가 → 결함 발견 → 가드 추가 → 위반률↓"였고,
**빼기 지표가 전부 0에 도달**(존댓말 위반 0/144턴·이탈 0·오변환 0)한
뒤에도 같은 루프를 돌아 공회전했다. 100인 방송 시뮬레이션
(`완료/AIRI-BROADCAST-SIM-3ARM-2026-08-18.md`)이 그 결과를 보여줬다:
틀리지는 않지만 응답 중앙값 8~16자, "응!" 연발, 집계·호명·기억 활용 부재.

**진단**: 병목은 하드웨어도 Mi:dm도 아니라 **모델을 굶기는 구조**다.
같은 모델·같은 하드웨어에서 컨텍스트에 재료만 넣어준 arm(seeded)이
전 지표 개선(단답 10→3건·주제 적중 27→50%)을 실측으로 증명했다.
프롬프트 지시의 상한도 2회 실증됐다(dn04·gr01 — 명시 금지 예시조차
위반). 따라서 v3의 원칙:

1. **모든 배치는 §1 더하기 지표 중 하나를 올려야 한다.** 빼기 지표는
   회귀 가드로만 유지한다(§2).
2. **프롬프트 지시보다 결정론 계층 우선.** 모델에게 시키지 말고,
   재료를 주거나(P1) 코드가 만든다(P2).
3. **모델 교체·하드웨어 논의는 P1·P2 소진 후**(P3 게이트 조건 참조).

## 1. 주 지표 — 발화 실질 (더하기)

기준선 = 2026-08-18 100인 시뮬레이션(48턴, CPU, 계약+게이트 ON).
목표치는 **제안값**이며 사용자 확정 전까지 잠정이다.

| 지표 | 기준선 (off / on / seeded) | 제안 목표 | 측정 수단 |
|---|---|---|---|
| 단답률 (5자 이하) | 10 / 14 / **3** /48 | ≤3/48 상시 | broadcast_sim |
| 주제 앵커 적중 | 27% / 38% / **50%** | ≥60% | broadcast_sim |
| 응답 다양성 (고유율) | 60% / 67% / **75%** | ≥80% | broadcast_sim |
| 기억 콜백 사용 | 0 / **1** / **1** /3 | 3/3 | broadcast_sim 프로브 |
| 시청자 사실 활용 | **7% (2/29)** — 2026-08-19 신설 | ≥40% (제안) | broadcast_sim fact_usage |
| 여론 집계 발화 | 0/6 전 arm | ≥4/6 | broadcast_sim 웨이브 |
| 후원 호명 정확 | 0/5 전 arm (named 변형도 0/5) | 5/5 | P2 렌더러 + sim |
| 후원 수신자 정합 | 1~2/5 | 5/5 | sim addressee 검사 |

> 2026-08-26 v4: 위 broadcast_sim 지표는 회귀 가드로만 유지한다. 주 지표는 아래 사람 채점 표다.

| 사람 채점 지표 (같은 99턴, run 04 기준선) | 기준선 | 돌파 목표(타계책) |
|---|---:|---:|
| 3축 합성(방송다움·맥락 유지·반응 적절성 평균) | 1.76 | **≥ 3.0** |
| critical_failure | 7.1% | 0 |
| silence_or_filler | 45.5% | ≤ 25% |
| 말투 규칙 | 3.60 | ≥ 3.5(하한) |
| 사실성 | 2.75 | ≥ 2.75(하한) |
| 복제 | n=1 | 후보당 ≥ 2회, 사람 채점 1회 |

## 2. 회귀 가드 — 유지만 한다 (빼기, 완결된 축)

새 작업 금지. 배치마다 깨지지 않았는지만 확인한다.

- 존댓말: 게이트+치환표+주체높임 가드+폴백 정규화 — 위반 0/144턴 유지
- 이탈(drift) 0 · 오변환 0 · addressee 검사(사이드카 28케이스)
- 방송 발화 계약 v3(`ec7a4209…`) + 스타일 게이트 이중 배선
- 안전(B3 모더레이션·입력 스크리닝) · 모델 SSoT 게이트(digest pin 등)
- 지연 예산: §12 원문 목표 유지(결정 5) — 코덱스 GPU 실측 축

## 3. 돌파 3축 (P1 → P2 → P3 순서, P1·P2는 병행 가능)

### P1. 쇼 러너 브리핑 — 모델에게 재료를 공급한다

디렉터가 매 턴 **브리핑을 자동 조립**해 컨텍스트에 넣는다(LLM 추가
호출 0, 방송 중 사람 개입 0): 이 시청자에 대해 아는 것(viewer_memory
I2a 기존 기반) · 방송 구간/경과 · 최근 화제 · 여론 현황 · 후원 이벤트.
근거: seeded arm 실측 + 뉴로사마 구조(작은 모델 + 두꺼운 자동화 계층).

- [x] P1-1a 턴 브리핑 조립기·프록시 근거 신호 — 2026-08-19~20 시뮬레이션 배선·실측 완료
  (`완료/AIRI-P1P2-BRIEFING-DETERMINISTIC-ACTS-2026-08-19.md`).
  **2026-08-20 추가**: 브리핑 근거를 프록시에 알리는 신호 계약
  `X-AIRI-Briefing-Evidence: memory`(정확 일치·루프백 전용) 구현·라이브
  확정 — 헤더 없이 218 ms 결정론 폴백 vs 헤더 있으면 11,299 ms 모델 응답,
  6런에서 선점 4건 해제(`absence_bypasses=4`)·결정론 축 만점 유지,
  단 **기억 프로브 2/9 불변**(선점 해소 ≠ 모델 활용)
  (`완료/AIRI-BRIEFING-EVIDENCE-SIGNAL-2026-08-20.md`, `f6a4167`+`df5b264`).
  이어서 근거 정의를 "관련도 매칭된 줄 존재"로 좁혀 부착률 68.1%→23.6%·
  해제 4→2(결정론적 감소)로 확정하고 행 단위 해제 관측성
  (`briefing_evidence_released`)을 신설
  (`완료/AIRI-BRIEFING-EVIDENCE-NARROW-2026-08-20.md`, `a5abc2c`+`6889d1e`).
- [P] P1-1b 운영 디렉터(B4a) 브리핑 이식 — 구현 근거는 완료됐으나 현재 실행 중이 아니며,
  이식 시 ①근거 판정은 좁힌 정의를 쓰고
  ②프록시 계약·루프백 제약은 그대로 두며 ③원격 디렉터가 되면 루프백
  제약 전체가 재검토 대상이고 ④해제 관측은 `/health` 누계 대조 대신
  프록시가 요청-응답 상관을 직접 남기는 텔레메트리로 승격을 검토한다
  (`/health` 대조는 전용 프로세스·순차 실행 전제에서만 안전)
- [x] P1-2 브리핑 지렛대 소진 — 2026-08-19 관련도 매칭·에코 필터
  (`363c6a7`)+지시형 문구·고정 문구 차단(`40298e2`). 에코 차단은 유효
  (앵커 17→35%·다양성 52→71%), 지시형은 무효(사실 활용 7% 동결) —
  P3 게이트 판정 근거. I2a 실데이터 주입은 B1b 이후
- [x] P3-T1b 추출 판단 학습쌍 — 2026-08-19, 102건(주체 선택·{{user}}·
  과추출 억제 장면), 전 타깃 스팬 파서 무손실 통과 강제, 게이트 어휘
  분리 테스트. 2차 학습 후보(1차=행동 SFT)
- [x] P1-3 "시청자 사실 활용" 지표 신설·재실측 — 2026-08-19. **기준선
  7%(2/29)** — 재료를 줘도 안 쓰는 비율이 수치화됨(P3 게이트 1차 증거,
  단 P1 지렛대 소진 전이라 게이트는 계속 잠김)
- [x] P1-4 **C안: ACK marker 모드** — 2026-08-19 구현 완료(`3ead135`).
  env `AIRI_IMMEDIATE_ACK`(audible 기본=바이트 동일) + 런처 기본 marker.
  실측: control 런에서 marker 자체는 모델 입력 불변 확인
- (연계) 히스토리 8쌍 + num_ctx 예산 재배분 — 브리핑이 차지할 토큰과
  트레이드오프 실측 필요

### P2. 결정론 발화 계층 — 코드가 만드는 발화

모델이 프롬프트로는 못 하는 것(2회 실증)을 결정론으로 생산한다.

- [x] P2-1a thank 렌더러와 시뮬레이션 배선 — 2026-08-19 5/5 실증(생일 반사 소멸),
  렌더러 자체는 2026-08-18 default-inert·테스트 14로 완료.
- [P] P2-1b 운영 B4b 어댑터·reaction 슬롯·비공개 리허설 — 원계획은 B4b 어댑터 →
  `callout_context`이며 운영 ON은 사용자 승인 경유.
  근거: 생일 후원 반사 4/4 arm + 호명 0/5(닉네임 줘도 0).
  **2026-08-20 추가 실측**: 운영 후원은 액션 3종
  (`donation_name_callout_request`/`donation_read_request`/
  `donation_reaction_request` — `broadcast-director/core.mjs:106,121`)인데
  현행 렌더러는 **1번만 덮는다**. 시뮬 5/5는 후원 턴 전체를 렌더러가
  대체한 값이라 reaction 슬롯은 미검증 — dn04류 반사가 운영에서 재발할
  지점이다(P2-4 조사에서 P2-1 귀속 판정)
- [x] P2-2a 여론 집계 발화 — 승인 3종(2026-08-19) 시뮬레이션 6/6 실증
- [P] P2-2b 여론 집계 발화 운영 디렉터 이식 — 구현은 완료됐으나 운영 배선·실측 잔여
- [x] P2-3 "기억나?" 가드 — 2026-08-19 프록시 방출 경계 배선 완료
  (`363c6a7`, env 기본 OFF·런처 ON). 기존 absence 폴백(증거 0)의
  잔여 구멍(증거 있는데 무내용 단정) 전용 보완
- [x] P2-4a 결정론 발화 시뮬레이션 격리 — **범위 재정의 2026-08-20**. 조사 결과
  "이관할 렌더러가 더 있다"는 전제는 실측과 어긋났다(**이관 후보 0건**).
  사이드카 28케이스의 최종 실패 4건(2026-08-18 게이트) 중 dn04·b18은
  후원 이벤트류=렌더러 소관(시뮬 5/5×12런, 단 addressee 분모가 후원
  5턴뿐이라 구조적 보장값), gr01·sp01은 답의 내용이 자기 상태·상대
  발언에 의존해 이관 불가(C2 자기 상태 주입·P1-2 소관 — v3 문서 §4-2
  판정 유지). 실질 잔여는 **이관한 발화의 격리**였다 — 후원 렌더러가
  부른 이름이 히스토리·브리핑 "방금 흐름"으로 되먹여져 이후 모델 턴이
  재호명(08-20 시뮬 15런 19턴, 그중 16건이 직전 후원 렌더러 이름 —
  B4a "이름 발명 금지" 계약 위반). **시뮬 격리 수리 완료(2026-08-20,
  `4046d75`)**: 러너 `run_arm()`에서 `deterministic_act` 턴의 히스토리·
  에코 사본만 이름 없는 A4.2 v1 문구로 치환(+4/−2줄, 채점·transcript는
  실제 발화 유지). 같은 시드 전/후 대조 `invented_handle_turns` 2→0,
  addressee·호명 5/5·존댓말 0/48·전송실패 0 무훼손, 테스트 52건 통과.
- [P] P2-4b 결정론 발화 운영 격리·사이드카 재측정 — 운영 디렉터(B4a/B4b) 이식 + 28케이스 재측정
  (마지막 측정 2026-08-18 게이트 런 — 렌더러가 시뮬 러너에만 배선돼
  `run_broadcast_chat_ab.py`·`run_broadcast_rehearsal.py`에는 acts 경로가
  없어 A4.2·P2 배선 이후 미재측정. v3 문서 §4-5의 회귀 자산 의무 미이행)
- [P] P2-4c cheer/sincere 수신 오프너 — default-off 선택기·검증은 `9de8f7a`로 완료됐으나
  운영 배선·실측·ON 승인은 남았다. 디렉터 분류는 `priority-policy.mjs`의
  CHEER_CUES/SINCERE_CUES를 사용한다.
- [x] P2-5a affect→표현 선택 계약·GPU probe 구현(평가 전용, 2026-08-21) — 기존 13상태를
  closed expression 계약으로 바꾸는 순수 선택기와 frozen fixture 3-arm
  GPU probe를 추가했다.
- [F] P2-5b affect 표현 품질 승격 — 5상태×3시드 15쌍에서 표현 arm은 문자열을 12/15
  바꿨지만 위트 0/3·pleased 반응 불변 3/3·competitive 문맥 이탈 3/3,
  safety 안내 약화 2/3이어서 **품질 승격 실패**. 이는 런타임 선택 구조보다
  모델의 표현 팔레트가 선행 병목임을 보여준다. 별도 affect 행동 pending 120건과
  queue-SHA 결속 검수 폼까지 준비했으나, **2026-08-21 사용자 내용 검수에서 반려**됐다.
  기존 행동 181건 중앙값 13자·affect 120건 중앙값 14자로 짧고, 후원/선택 채팅의
  이벤트 맥락·감사 의례·메시지별 반응·주제 확장·복귀 beat가 없는 챗봇형 Q→A다.
  두 큐와 폼은 실패 재현용으로만 보존하며 검수 회신·QLoRA에 쓰지 않는다. 이벤트
  ingress 배선·운영 ON은 별도 사용자 승인 전 금지하며 현재 기본/실행 모두 OFF
- [x] **P2-6a 한국 인터넷 방송 반응 메타 재관찰·행동 데이터 재설계
  (2026-08-21)** — 탬탬버린 공식 다시보기/클립과 아리사 공식 영상의 확인 가능한
  입력→반응 장면을 비식별 코딩했다. 공통 단위는 `인지/감사 → 메시지별 반응 →
  의견·에피소드 확장 → 복귀·다음 훅`이며, 길이와 존댓말/반말은 전역 규칙이 아니라
  이벤트·beat별 계약이어야 한다. 실제 방송인의 고유 문체를 복제하지 않고 AIRI
  고유 합성 target을 새 큐로 저작한다. **2026-08-22 현행 데이터:** 공식 1차
  출처 30건·11명과 결속된 원문·PII 없는 observation-only event/beat 30행을 별도
  출처 원장으로 분리했고, 수 시간 연속성 arc 7건은 독립 데이터로 유지한다. 사용자
  지정 진행자 가설 선언 장면도 `OBS-S01` partial-evidence로 포함한다. 출처 식별자는
  비공개 원장에만 둔다.
  AIRI 원본 파일럿 24건도 train/dev/test 16/4/4,
  single/burst 15/9, compact/standard/expanded 4/10/10으로 작성했으며 target
  길이 중앙값 98자·입력보다 짧은 답 0건·전건 training-ineligible이다.
  24건 묶음 총평은 후속 v2→v3→v4 재설계에 반영됐다. 아리사 추가 공식 사례는
  자막 접근이 복구될 때만 확정 표본으로 승격한다.
  근거: `참조/AIRI-KR-BROADCAST-REGISTER-REFERENCE-2026-08-21.md`,
  `진행예정/AIRI-KR-BROADCAST-RESPONSE-PILOT-2026-08-21.md`

- [F] **P2-6b 총평 반영 학습·품질 트랙:** 사용자가 파일럿의 길이·후원
  의례·한국 방송식 주제 확장·RAG 연속성 방향을 묶음 단위로 승인했다.
  이 총평을 반영한 broadcast v2 240행 선행 학습은 T3에서 두 방송 사실 활용
  기준을 소폭 밑돌아 채택하지 않았다. 현행 v3는 120 card×10 연속성 변형+
  v2 240으로 **1,440행**이며, group split 1,148/146/146, 한국어 전수 감사
  blocker 0건·quality gate PASS였다. v3 QLoRA 실행은 현행 v4 트랙으로 대체됐고,
  현재 학습 프로세스는 0이다. T3+사용자 승인 전에는 어떤 어댑터·양자화 모델도
  운영 채택하지 않는다.
- [B] P2-6c 후속 행동 데이터·학습 라운드 — 차단 원인: 타계책에 따라 2026-09-09까지 파인튜닝 금지; 재개 조건: M7-8과 동일
  (S1~S5 뒤 3축 < 3.0, S5 +0.6 용량 병목 실측, 실제 채팅 사람 검증 ≥ 300턴)

### P3. 생성 상한 재검토 — **게이트 열림 (2026-08-19 실측 판정)**

게이트 조건("P1+P2 반영 후 재실측에서도 §1 목표 미달") 충족 —
프롬프트 지렛대 소진(지시형 브리핑까지 사실 활용 7% 동결, 명시 지시
불응 3회째), 독립 증거 4계열
(`완료/AIRI-P1-LEVER-EXHAUSTION-P3-GATE-2026-08-19.md`).
**실행은 코덱스 GPU 몫** — 시뮬레이션 하네스를 그대로 GPU에서 돌려
지연-품질을 한 표로 비교한다. 원 게이트 조건:
근거: 8B 게이트 실측 — 크기는 recall을 못 올렸다(0.43~0.50 정체),
"크면 해결" 반증 (`완료/AIRI-QWEN3-8B-EXTRACTION-GATE-2026-08-18.md`).

**주 경로 = 학습 트랙 (사용자 방향 확정 2026-08-19: "모델을 학습시키는
방향으로")**. 근거: 실패의 정체가 지식이 아니라 행동 패턴(사실 활용
7%·지시 불응 3회)이고, 크기 확대는 반증됐으며(8B recall 정체),
LightMem 실증(작은 모델+좁은 LoRA > 큰 모델)과 정합. 기존
`training/` QLoRA 스캐폴드·governance(합성→pending→**인간 검수**→
승인→로컬 학습)를 그대로 따른다.

- [x] **P3-T1 행동 SFT 데이터 합성** — 2026-08-19 완료. 4행동 181건
  (fact 126·addressee 15·register 10·substance 30), 운영 브리핑 포맷
  그대로, 전 정답 방송 채점기 통과, pending·eligible:false
  (`완료/AIRI-P3T1-BEHAVIOR-SFT-SYNTHESIS-2026-08-19.md`)
- [x] P3-T2a 인간 검수·익스포트·QLoRA trainer 계약 구현 — 2026-08-19~21 완료
- [S] P3-T2b 기존 행동 181건·affect 120건 큐 — 사용자 내용 검수에서 반려되어 후속 v2~v4로 대체
- [x] P3-T2c runtime-shaped continuity v4 E1/E2 QLoRA 실행 — durable receipt와 provenance 검증 완료
- [B] P3-T2d 추가 인간 검수·학습 라운드 — 차단 원인: 타계책에 따라 2026-09-09까지 파인튜닝 금지; 재개 조건: M7-8과 동일
  (합성 템플릿 데이터 금지, 사람 채점 루프의 검증 턴만)

**P3-T2 상세 근거:** 트레이너 준비 완료 2026-08-19
  (`train_airi_behavior_lora.py` — sha 핀·로컬 전용·assistant 마스킹,
  CPU 스모크로 루프 검증). **2026-08-20 추가**: 2차(추출) 학습의 검수·
  익스포트 경로를 행동 SFT와 대칭으로 신설(`a473eb1`+`df31dc6`) — 폼→
  적용기(스팬 스키마 게이트, 한 건 실패 시 회신 전체 거부)→익스포터
  (벤치마크 Stage A 조립 import 재사용, 바이트 동일 테스트 고정).
  이어 **추출 검수 폼 v2**(`eb9f46a`): rewrite 브라우저 사전 검증
  (evidence ⊂ turns·이름 ⊂ evidence) + target 파싱 실패 배지 분리 +
  **회신-큐 sha256 결속 필수화** — 큐가 바뀌면 **구 폼 회신은 거부되고
  최신 폼을 안내**한다. **검수 직전 보강 완료(2026-08-20 코덱스)**:
  추출 익스포터가 split 도메인·빈 id·중복 id를 fail-closed로 거부하고,
  queue SHA를 LF 정규화해 Windows CRLF 체크아웃에서도 폼/적용기 결속이
  `2988a82bd738`으로 일치한다. **2026-08-21 보강**: 행동 폼도 LF-normalized
  queue SHA 결속과 duplicate/overlap fail-closed를 갖췄고, affect 행동 120건을
  별도 큐·폼으로 추가했다. 현행 SHA는 기존 행동 181건 `eab7f6b76c06`, affect
  행동 120건 `96d0d2d3c69d`, 추출 102건 `2988a82bd738`. 행동 exporter는 검수된
  두 행동 큐를 한 번에 합치되 affect만 운영 request-local 4-message 형태로 조립하고,
  trainer는 기존 3-message/affect 4-message 두 정확한 계약만 허용한다. training
  스위트 **136 passed, 3 skipped**. **2026-08-21 순서 변경:** 기존 행동 181·affect
  행동 120은 사용자 총평으로 반려되어 회신 적용·CUDA 행동 1차를 금지한다. P2-6의
  새 AIRI 고유 방송 반응 24건 파일럿 총평 반영과 별도 전량 검수 계약 뒤에만 행동 학습
  큐를 다시 연다. 추출 102건은
  기술적으로 별도이나 현 배치에서는 행동 재설계와 혼동하지 않도록 검수·2차 학습 보류
  **2026-08-21 현행 대체 트랙:** 반려된 181/120 큐를 재사용하지 않고,
  사용자 묶음 총평을 반영한 broadcast v2 240행→T3 실패 분석→continuity v3
  1,440행→**runtime-shaped continuity v4 1,000행**으로 재설계했다. v4는
  train/dev/test 800/100/100, chat SHA `96cc223ca591`, source SHA
  `43f9c1ed1abf`로 고정됐다. seq2048 E1 QLoRA(800 microsteps/50 optimizer
  updates)는 train first3 3.3845→last3 2.9151, dev loss 2.8938로 완료했지만
  `adoption_authorized=false`, `t3_status=pending`이다. E2는 사용량 한계에 따른
  사용자 요청으로 중단해 산출물 없이 다음 세션 재실행으로 넘겼다. 정확한 명령과
  해시는 `진행중/AIRI-CODEX-HANDOFF-2026-08-21.md`에 고정했다. **2026-08-22
  재감사:** 재부팅 후 세 번째 시작도 pause 요청 직후 checkpoint 전에 종료했으며,
  trainer 0, E2 adapter/report 0, 시작 로그 2개는 각각 0 bytes다. 계산 이력은 있으나
  재개 가능한 상태가 아니므로 P0 내구성 실증 뒤 동일 seed의 step 0부터 다시 실행한다.
- [x] **P3-T2b E1/E2 병합·GGUF 패키징** — P0 실증과 E2 provenance 검증 뒤
  E1/E2 각각 HF safe-merge → BF16 GGUF → Q4_K_M 순서로 완료했다. 후보별
  artifact manifest, SHA, `package-evidence.json`의 최종 tag/digest가 완료 증거다.
  패키징은 후보 생성일 뿐 운영 채택이 아니다.
- [x] P3-T3a isolated T3 launcher·comparator·증적 계약 구현 및 검증 완료
- [F] P3-T3b 전/후 게이트 실측 — production T3와 E2-C1 blind matrix 모두 no_winner

**P3-T3 상세 근거 — authoritative FAIL:** 시뮬 하네스 그대로. **캘리브레이션 완료
  (2026-08-19 4-시드)**: 사실 활용은 12% 노이즈 천장 상회 필수, 결정론
  축 만점·존댓말 0 유지, 앵커·다양성은 3시드 평균 비교
  (`완료/AIRI-SPAN-CONTRACT-AND-VARIANCE-2026-08-19.md`). **held-out 2차
  방송 기준선 확보(2026-08-19)** — 과적합 검출용, 1차+2차 양쪽 측정 의무
  (`완료/AIRI-HELDOUT-AND-EXTRACTION-SFT-2026-08-19.md`). 미통과 어댑터 폐기
  **2026-08-21 실측 계약 보강:** baseline/candidate 모두 인증된
  `--live-broadcast-context on`으로만 새로 측정한다. proxy가 신원/규칙을 한 번만
  만들고 server-owned `[오늘 방송]`·브리핑·affect·request-local 문체 순으로
  모델에 전달한다. 호출자 system은 capability claim 후 전량 제거하고,
  사전 기억 seed도 trace-bound durable journal receipt 완료 후 본 방송을 시작한다.
  show-arc callback_hit/miss와 TTS·RAG·저널·지연 전 체인은 T3 통과 후
  3-seed×500-turn 장시간 캠페인이 별도로 소유한다. **v4 게이트는** baseline/E1/E2
  각각 first+second 4-seed와 final-blind 180분 4-seed, 총 36 reports로 수행한다.
  **전용 isolated T3 launcher 구현·감사 완료(실측 대기):**
  `run-airi-broadcast-t3-matrix.ps1`이 exact 3-model manifest, 승인 fixture raw/canonical
  pin, 공통 `seeded` 설정, run별 fresh DB/capability, 실행 전후 pinned health,
  immutable stream-plan 전체 turn 집합, 모든 row의 durable live receipt, 두 12-pair
  comparator와 전체 증적 hash inventory를 fail-closed로 강제한다. GPT-SoVITS cache
  wrapper/stream mode 2/min chunk 16과 identity-only partial cleanup·환경 복원도 고정했다.
  오프라인 launcher 8 tests, 시뮬/비교기 75 tests(1 skip), 독립 최종 감사 P0/P1 0.
  2026-08-23 production 36/36 reports와 두 comparator를 terminal까지 실행했으나 invented
  handle/polite hard gate에서 양쪽 모두 FAIL, PASS summary와 winner는 0이다. T3 knowledge
  DB는 fresh empty 상태를 attest했고 campaign RAG fixture를 섞지 않았다. 실패 root를
  보존하며 같은 공개 blind matrix를 반복하지 않는다. **2026-08-24 E2-C1 후속:** 새 한국어
  blind v2(3 fixture×4 seed)로 baseline/e2/e2-c1 36-report를 별도 실행 — e2-c1 score
  최고(0.244)나 `invented_handle` 위반 53건(학습할수록 악화)으로 13개 게이트 전부 FAIL,
  winner 0. 다음은 원문 진단+결정론 가드+재검토된 E2-C2다.
- [x] P3-T4a 하드코딩 축소 설계 — `5774fcd`로 설계와 offline handoff 완료
- [B] P3-T4b 하드코딩 축소 구현 — 차단 원인: T3 통과 행동이 없어 축소 대상 미확정;
  재개 조건: 후속 gate 통과와 사용자 실행 승인
  T3 통과 행동부터 결정론 계층 걷어냄
  (집계 오프너·폴백 후보). **thank 렌더러는 유지** — 후원 호명 오류
  비용이 커서 고정이 정석

보조 경로 (T3 게이트 실패 시 재평가):
- [D] P3-M1 코덱스 GPU 재실측에 4B급 공존 옵션 포함 — 사용자 방향 결정 필요 — v4: 사람 채점 기준선(M6-7) 확정 뒤에만 검토; 4B급 태그는 현재 이 PC에 없음
- [D] P3-M2 챗 모델 체급 A/B — 기존 하네스 재실행 여부를 사용자 결정 — v4: 사람 채점 기준선(M6-7) 확정 뒤에만 검토 → 타계책 S5(M7-7): qwen3:8b 1회 진단(채택 아님, TTS와 공존 불가)
- [D] P3-M3 클라우드 하이브리드 재평가 — 외부 provider·비용·결정 2 승인 필요 — v4: 사람 채점 기준선(M6-7) 확정 뒤에만 검토
- [D] P3-M4 GPU 증설 — 최후 수단이며 사용자 구매 결정 필요 — v4: 사람 채점 기준선(M6-7) 확정 뒤에만 검토

## 4. 기존 트랙 → v3 매핑 (미완 항목 전수 이관)

| v2 트랙 | v3 처지 | 잔여 항목 |
|---|---|---|
| G1 캐릭터 루프 | 유지보수 | evaluator 재활성(보류: G1a validator 합류) |
| G1a 감정·연속성 | **P2에 흡수** | A4.2 배선=P2-1, 잔여 A류는 P2-4 |
| G2 장기 기억 | **P1 공급원** | Stage A 스팬 계약 실측 완료(2026-08-19 — 날조 차단 실증, 판단 축은 미돌파: 추출 판단도 학습 후보 + 코덱스 8B+span 1회 실측 권고). **MEM-04 락 경합 실측 완료(2026-08-20) — 판정: `busy_timeout` 5000 ms 현행 유지가 적정.** 실제 PRAGMA·`append_turn`/`latest_turn` 경로를 임시 DB에 재현: 방송 운영 근사(writer 2·reader 6, 각 2000 ops)·8-writer 동일 세션 최악 케이스 양쪽 모두 busy/locked 실패 0건, 최악 max 대기 2,099 ms=예산의 42%(500 ms로 되돌리면 최악 p99 780.6 ms조차 초과). 근거 `.superpowers/sdd/task-12-report.md` + LOG 2026-08-20. 런타임 계약 수렴분(v2b→v3-span opt-in `00482ec`)·결정론 alias/고정 택소노미 greybox(`9034428`)는 §3 P3·인계문 참조. I2=P1-2 |
| G3 평가 플라이휠 | 지표 교체 | 측정 체계를 §1로 전환. 인간 검수 100건(코덱스)·16케이스 게이트·replay(외부 권한 대기) 유지 |
| G4 / C1~C5 파인튜닝 | 장기 보류 | (보류: 인간 검수 데이터 축적 — 변동 없음) |
| G5 방송 디렉터 | **P1·P2의 몸통** | B4a partial → 브리핑·집계로 확장 |
| G6 화면·게임 | 보류 | (G5=P1·P2 이후) |
| B4c 발화 계약 | §2 가드로 완결 | 파라미터 확정(결정 큐 4)·운영 ON만 잔여 |
| 지연 플랜 v2.1 | 코덱스 트랙 §5 | 본답변 지연·마이크 체인 실측 |
| M1~M5 방송 실행 | 유지 (교차 게이트) | 아래 별도 |
| 모델 SSoT 게이트 | §2 가드 | 완결 유지 |

**M1~M5 잔여** (방송 실행 게이트 — P축과 교차):
- [B] 과거 방송 실행 M1: B0-1 streamList 쿼터 실측 — 차단 원인: 외부 자격증명 없음;
  재개 조건: 사용자가 자격증명 사용을 승인하고 제공
- [B] 과거 방송 실행 M2: B1b 라이브 어댑터/OAuth/실주입 — 차단 원인: 외부 자격증명·운영 승인 없음;
  재개 조건: 사용자가 OAuth·운영 실주입을 승인
  I2 시청자 기억 → P1-2로 이동
- [B] 과거 방송 실행 M3: B3-e 실기·B3-f replay·B2 송출 — 차단 원인: 외부 권한과 결정 2 미완료;
  재개 조건: replay 권한과 송출 결정을 사용자에게 승인받음
- [S] 과거 방송 실행 M4 분류(B4 확장=P1·P2) — 현재 M4 handoff 단계 체계로 대체
- [B] 과거 방송 실행 M5: 비공개 리허설→데뷔 — 차단 원인: 선행 방송 gate·결정 4 미완료;
  재개 조건: 선행 gate 통과 뒤 사용자가 리허설·데뷔 실행 승인

## 5. 코덱스(GPU) 대기열

### v4 active fail-closed 체크리스트 (2026-08-23 resume)

- [x] live working-state와 60분/장기작업 15분 heartbeat·intent/receipt·재독/대조
  프로토콜 도입 — `e822f9f` origin/main push(2026-08-22), 독립 P0/P1 0
- [x] 공식 방송 event reference 30건·continuity arc 7건과 v4 1,000행 SHA 고정
- [x] E1 QLoRA 및 adapter/report provenance 검증
- [x] 사용자 `/goal`로 명시적 resume, Goal status `active`, Git/PID/SHA/산출물 재대조;
  운영 채택·기본 모델 변경 금지선 유지
- [x] **P0-A (2026-08-22 offline 완료):** checkpoint를 E2보다 먼저 구현: 전체 학습/RNG/순서/loss/provenance 상태, 같은 볼륨
  원자 승격·latest/previous 회전·깨진 checkpoint 격리 구현 및 회귀 —
  `6f0c1358d2acd18b828ebc0ae8482a348712c461` origin/main push
- [x] **P0-B (controlled GPU 완료, 2026-08-23):** exact-pin CPU 중단/재개 동등성, durable runner/run-state, safe pause,
  PID/command/checkpoint SHA 재부팅 복구의 offline 실증은 완료. checkpoint별 durable
  timing event, deterministic pin, 허용오차 0 full-state comparator, 600초/최소 4구간
  gate와 fault 회귀는 `e970cf7`, external input/config/seed/batch/accumulation/first-pause
  expected 결속은 `8cd69b5`로 origin/main push됐다. RunDir 생략 safe-pause는 exact
  command/state/source/process identity가 일치하는 active run 정확히 1개만 선택하고
  0개·복수·spoof·명시적 empty를 거부하도록 offline 검증됐다. controlled GPU 동등성과 실제
  E2 속도 손실 상한 10분 이하 실측이 남음. 2026-08-23 로컬 후속 배치는 no-follow
  input lock/manifest, authenticated run-state recovery, producer evidence/index/event,
  trainer-bound launcher와 anchor-bound pause를 구현했다. 한 차례 감사 P0=0/P1=4의
  네 원래 P1만 최소 수정하고 targeted+최종 Python `145 passed, 5 skipped`+actual-process
  PowerShell+전체 offline+diff/security gate로 잔여 로컬 P0/P1 0을 확인했다. 새 감사
  라운드는 추가하지 않는다. 검증 완료 commit `911d082`과 receipt docs `a898ff8`은
  origin/main에 durable하다. 첫 K=5 controlled baseline은 480/30 계산 뒤 interval max
  705.902827초와 final-root adapter SHA 의미 혼동으로 FAIL했다. runner/pause 두 P0를 exact
  internal manifest receipt row에 결속해 pinned Python 146/5, actual PowerShell, final offline,
  diff/security PASS로 수리했고 `18d0bc6`으로 origin/main push했다. fresh K=3 baseline과
  실제 `SAFE_TO_POWER_OFF` safe arm은 terminal 480/30, paired receipt SHA
  `d913992e...e84b9`, 672 tensors exact, normal interval max 551.5176357초로 PASS했다.
  Windows verifier receipt-order 한 줄과 회귀는 `87dfabd`/`29080be`로 origin/main push됐다.
  actual push receipt five-doc finalization과 clean 확인 뒤 E2로 이동한다.
  이미 완료된 P0-A를 다시 넓게 감사하며 공회전하지 않는다.
- [x] controlled GPU preflight: 입력 code/data clean, trainer 0, corpus/base/E1 SHA exact,
  fresh root와 E2 산출물 부재를 확인했다. E2 직전에는 현재 commit/push·clean과 같은 입력/
  PID/E2 부재를 fresh timestamped run root 기준으로 다시 확인한다.
- [x] **E2-LAUNCH:** authoritative durable runner seed 42·1,600 microsteps terminal,
  report/SHA/manifest 검증 완료
- [x] E1/E2 각각 safe-merge → BF16 GGUF → Q4_K_M 패키징 완료·미채택
- [x] exact baseline/E1/E2 tag+digest manifest 작성·SHA 결속 완료
- [F] isolated 36-report T3와 두 comparator는 terminal 실행 완료이나 양쪽 hard-gate FAIL,
  PASS summary/winner 0
- [x] E1/E2 각 12개 원본 report 위치와 1,248-turn aggregate, 실제 응답 대표 사례를
  사용자 검토용으로 제출했다. E2는 상대 우세하나 T3 PASS/winner로 승격하지 않았다.
- [x] **E2-C1 교정 iteration 설계·데이터·평가 계약:** 사용자 승인·동결·milestone push 완료. same-data E3가
  아니라 E2 weight-only init + fresh optimizer/scheduler/RNG/cursor다. correction/replay/
  mixture와 retained blind commitment/policy, exact dataset SHA, split/seed/step/LR/scheduler/
  checkpoint/metric 계약은 current bytes에서 full freeze validation PASS다. `으로/로` 5건과
  validator 공백도 mutation regression으로 닫혔다. frozen-contract milestone commit/push와
  HEAD=origin/main clean/PID 0이 남았으며, 그전에는 GPU 학습을 시작하지 않는다.
- [x] **E2-C1 GPU 실행 완료:** smoke PASS(K=1 80/5 두 arm+resume) → 본 학습 512/32 terminal
  exit 0(mixture dev loss 2.235104) → safe merge(target l2 0.0865, non-target 무변경) →
  BF16/Q4_K_M 패키징(tag `midm-airi:e2c1-broadcast-v4-20260824-08df7ecf...`) — 전부 미채택
- [F] **E2-C1 blind v2 36-report matrix — no_winner:** 한국어 재봉인 blind(v1은 영어 문구라
  실행 불능이던 결함 수리 후) 36/36 완주. score e2-c1 0.244(최고)·e2 0.225·baseline 0.218,
  additive 4/5 축 방향 개선하나 전부 절대 최소선 미달. `invented_handle` 위반 28/40/53으로
  후보가 최악 — hard/legacy/perfect-rate 13개 게이트 전부 실패. `adoption_authorized=false`
- [x] invented_handle 53건 원문 진단 완료: 순수 날조 0, 재호명(실제 memory 회수) 47건
  (89%), 그중 -님 vocative 7건(13%)·일반 명사 사용 46건(87%), 렌더러 되먹임 0
- [x] **핸들 grounding 가드 + 채점기 신호 구현·SHIPPED (2026-08-24 16:33,
  commit `a0020dd`+docs → `59d1836`):** roster가 없는 프로덕션에서는 문법
  신호(-님 vocative)만 좁게 가드하고, 실제 no_winner 원인이던 87%(일반 명사 사용)는
  채점기 쪽에 memory/journal 근거를 노출해 `fact_tokens`로 합치는 방식으로 처리 —
  게이트 정의는 불변, 판정 입력 범위만 확장. 프록시 flag 기본 off, 신규 16 + 프록시
  373 + 시뮬레이터 88+85 전부 pass
- [F] 가드+채점기 신호 뒤 E2-C2 재설계·학습·새 blind v3 36-report 재도전 — 36/36 exit 0이나
  `winner=null`, e2-c2 score 0.187536으로 e2 0.201901보다 낮고 13 gate 실패
- [N/A] T3(v4)·E2-C1·E2-C2 winner 조건부 3 seed × 500 turn campaign — 모든 verdict가
  no_winner라 실행 대상 아님
- [x] T3 terminal 실패 aggregate·receipt·hash와 E1/E2 원본 제출 완료
- [N/A] 실제 승자 응답·지연·TTS/RAG campaign 묶음 — winner 0이라 생성 대상 아님
- [D] 운영 채택 판단 — `adoption_authorized=false`; 사용자 별도 승인 필요

각 단계의 fail-closed 완료 증거와 정확한 명령은
`진행중/AIRI-CODEX-HANDOFF-2026-08-21.md` §8을 따른다.

### 기존 GPU 대기열

GPU 재실측의 완료·잔여 상태는 아래 분리 행을 권위로 삼는다. ctx/narrow/Qwen3-8B span은
2026-08-20 실행 완료.
  marker 실제 render TTFT A/B는 외부 GPT-SoVITS venv 불완전으로 보류,
  게이트 경로 폴백률 reps 확대·치환표 중기 조치 ①② 판단은 잔여
- [x] **ctx 예산 GPU 단일조건 재실측 (2026-08-20 완료)** —
  `--history-turns {4,8,12}` 효과가 CPU 스로틀 epoch와 완전히 교락돼
  앵커·다양성·fact_usage·프로브의 우열을 확정하지 못했다. 스로틀·워치독
  변경 없이 **단일 조건**으로 9런을 재실측해 history_turns 효과를 epoch
  효과와 분리할 것. 확정된 것은 결정론 축 무영향·`num_ctx 4096`이
  history_turns=12까지 수용한다는 두 가지뿐이다
  (`완료/AIRI-CTX-BUDGET-TRADEOFF-2026-08-20.md`). GPU 고정조건 9런은
  전송 실패 0, h4/h8/h12 앵커 41/48/46 of 144, 사실 5/7/5 of 90,
  프로브 4/4/3 of 9, 오프너 다양성 평균 78.5/81.3/84.0%였다.
  CPU의 h4 우위는 재현되지 않았고 시드 분산 때문에 단일 설정을 승격하지 않는다.
  주의: `AIRI_UPSTREAM_FIRST_RAW_TIMEOUT_SECONDS`의 유효 범위는 **1~30초**이며
  벗어나면 경고 없이 8초로 클램프된다
- [x] **narrow evidence GPU 확인 (2026-08-20 완료)** — 좁힌 근거 정의
  (부착 23.6%·해제 2건)와 행 단위 해제 관측성이 GPU에서도 같은 값인지
  확인하고, 프로브·사실활용·앵커가 CPU 노이즈에 묻혀 판정 불가였던 축을
  다중 시드로 다시 쟀다. 부착 34/144·해제 2/34는 CPU와 정확히 같고,
  프로브 2/9·사실 4/90·앵커 49/144였다
  (`완료/AIRI-BRIEFING-EVIDENCE-NARROW-2026-08-20.md`)
- [x] **Qwen3-8B + `conversation-v3-span` GPU 1회** — 구조 schema 3종은
  1.0이나 connectivity/B coverage 0.857, recall 0.262, op-alias 0.143,
  failure code 1건으로 balanced gate FAIL. 운영 승인·span 활성화 근거 아님
- [B] TTS 재검증(v2ProPlus 스트리밍 계약) — proxy 계약 23 passed. 차단 원인: 외부
  GPT-SoVITS venv 선언 의존성 누락; 재개 조건: 의존성 환경 복구 뒤 live 7문장 gate 재실행
- [B] B1b 라이브 어댑터 — 차단 원인: 외부 자격증명·운영 승인 없음;
  재개 조건: 사용자가 자격증명 사용과 live adapter 실행을 승인
- [S] 인간 검수 100건 수집 — 2026-08-26 M6-6/M6-7(실제 세션 50~100턴 사람 채점)로 대체
- [Q] 실제 마이크 음성 체인 P50/P95 — 사용자 요청 시 실행 준비

## 6. 사용자 결정 큐 (2026-08-19 정리)

| # | 항목 | 상태 |
|---|---|---|
| 0 | ACK 제거 C안 | **완료** — marker 채택·구현(2026-08-19) |
| 1 | thank 렌더러 운영 배선 (P2-1) | **승인** — 시뮬 실증 완료, 운영 이식 진행 |
| 2 | 여론 집계 발화 문구 (P2-2) | **승인** — 3종 원안, 시뮬 6/6 |
| 3 | "기억나?" 가드 (P2-3) | **승인** — 도입, 회피 문구 원안 |
| 4 | B4c 파라미터 9행 | **승인** — 원안 전체(2026-08-19) |
| 5 | 침묵 폴백 풀 운영 ON | **완료** — 런처 기본 ON(`3ead135`) |
| 6 | 계약 v3+게이트 운영 ON | **완료** — 런처 기본 ON(`3ead135`) |
| 7 | 팬덤명 | 유보 지속 |
| 8 | T-05 목소리 샘플 | **샘플 요청** — 2026-08-24 결정 폼 회신 `t05=샘플요청`. 126번을 감정이 드러나는 대화체 문장으로 재합성해 현행 일본어 참조와 A/B 청취 샘플을 준비한다(포지). 운영 승격 아님·현행 음성 유지 |
| 9 | DeepL 키 (talkain) | **보류** — 2026-08-24 회신 `deepl=보류(위험 인지)`. 08-19 "종결" 표기를 대체하며 회전 시점은 사용자 몫 |
| 10 | §1 목표치 확정 | **승인** — 제안값 확정, 실측 후 조정 가능 |
| 11 | (2026-08-26) 합성 blind 루프 중단·피벗 | **결정 C** — v7 저작·matrix·campaign 중단, 실태 파악 |
| 12 | (2026-08-26) 실제 대화 사람 채점을 유일한 채택 게이트로 | **승인** — 계약 `AIRI-REAL-DIALOGUE-HUMAN-EVAL-CONTRACT-2026-08-26.md` |
| 13 | (2026-08-26) grounding 게이트 평서문 침묵 수리(production) | **승인** — M6-2 |
| 14 | (2026-08-26) step 2 수리 코드 commit | **승인** — `a9583c3`(push 별도) |
| 15 | (2026-08-26) 문서 다이어트·heartbeat 완화 | **승인** — M6-4 |
| 16 | (2026-08-26) 파인튜닝 중단 권고 | **수용** — 재개 조건은 실태 문서 §4.2 |
| 17 | (2026-08-26) 타계책 채택 — 되먹임 고리 통제·1변수·복제, 파인튜닝 2주 금지 | **문서 반영** — `AIRI-BREAKTHROUGH-PLAN-2026-08-26.md`, M7 |
| 18 | (2026-08-26) S0 복제 측정·S1 proxy 되먹임 flag·run 05 사람 채점·push | **승인·실행** — 16:5x "1 2 3 4 모두 진행", push `e6e745a` |
| 19 | (2026-08-26) 운영 `AIRI_FEEDBACK_HYGIENE=on` 채택 | **기각** — 사람 채점 3축 1.90(+0.14 < +0.2), filler +10.1%p; flag는 기본 off로 유지 |
| 21 | (2026-08-26) M7-10 민감 루머 질문 "응" 시인 가드 | **승인·구현** — `f48b1ed`, run 07 실전 발동(한계 §5) |
| 22 | (2026-08-26) 업스트림 v0.12.0-beta.1 점검(사용자 요청) | **해당 없음** — 라이브 채팅·기억·응답 품질 변경 없음, 병목은 proxy 쪽 |
| 20 | (2026-08-26) S6 입력 정합(자기완결 구간 선별 vs 스트리머 STT 발화 정렬 공급)을 다음 변수로 | **사용자 결정 필요** — M7-9 |
| 23 | (2026-08-28) VOD storyline validator 튜닝 트랙 중단 | **결정** — "지금 즉시 중단·정리". run-83 중단(무근거), 결함 목록을 `진행중/AIRI-VOD-STORYLINE-CEILING-EVIDENCE-2026-08-28.md`로 고정 |
| 24 | (2026-08-28) 다음 방향 — A 단기 콤보 / B llama-server 병행 / C S5 모델 축 / D 교정 파인튜닝 | **결정** — 16:0x "모든 금지 해제·할 수 있는 건 다" + "모델 변경은 가장 마지막"(Mi:dm 한국어). M8 Stage 1→2→3→4 순서로 확정 |
| 25 | (2026-08-28) 전 실험 게이트 해제 + M8 개설 | **승인·반영** — S5·모델 축·파인튜닝 승인 게이트 해제(검토 PC는 CUDA 부재로 파인튜닝 물리 불가). 원문/키 저장소 반입 금지·push 매회 승인·운영 채택 별도 결정은 유지. M8 체크리스트와 관측 프로토콜 참조 |

2026-08-24 사용자가 `AIRI-DECISION-FORM-2026-08-19.html` 정식 회신 텍스트를 제출했다:
`ack=marker · targets=승인 · thank=배선진행 · wave=원안승인 · memguard=도입 ·
b4c 9행 전부 승인 · pool=ON · contract=ON · fandom=유보 · t05=샘플요청 · deepl=보류`.
0~7·10은 08-19 일괄 승인 기록과 동일하고 8·9만 위 표대로 갱신했다. 회신은 문서
결정이며 코드·런처 기본값·운영 채택은 바뀌지 않았다.

확정된 과거 결정(1~7, 2026-08-12·14·18)의 전문은 v2 스냅샷 §사용자 결정
참조 — 요지: 관계 축=AI 단독형+사장님 메타 서사, 로컬 LLM=Mi:dm,
지연 목표=§12 원문, 헌법 v2 7행+통과선 8지표+thank B안+장시간 채팅 A,
raw 경로 검토 근거 불인정(11435 게이트 경유 의무).

## 7. 문서 위계 (2026-08-19 정리 후)

- 최상위: 이 문서 → 로그: `AIRI-ROADMAP-LOG.md`
- 부속 계획(참조용, 이 문서가 우선): `AIRI-GROWTH-STRATEGY.md` ·
  `AIRI-MODEL-CUSTOMIZATION-PLAN.md` · `AIRI-NEUROSAMA-LOW-LATENCY-PLAN.md`
- 현행 스펙: `진행중/AIRI-LOCAL-TECH-SPECS.md`
- 문서 지도: `AIRI-CURRENT-DOCS-INDEX-2026-08-10.md` (파일명 불변 규칙)
- `아카이브/`의 문서는 **현재 상태 검증에 사용 금지** (역사 기록 전용)
