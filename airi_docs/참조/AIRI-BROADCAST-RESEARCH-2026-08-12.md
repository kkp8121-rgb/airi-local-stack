# 저스트챗 방송·기술 파이프라인 리서치 — 2026-08-12

`진행예정/AIRI-BROADCAST-CHARACTER-PLAN-2026-08-12.md`의 근거 자료.
콘텐츠 구조(A부)와 기술 파이프라인(B부) 두 병렬 조사의 핵심 발견을 출처와
함께 보존한다. 근거 등급: [A] 학술·1차 / [B] 위키·언론 / [C] 실무 가이드.

---

## A부. 저스트챗 방송의 실제 구조

### A-1. 시간 구조 — 저챗은 즉흥이 아니라 설계다 [C]

한국형 2시간 표준: 오프닝 10~15분(근황→질문형 마무리) → 메인 60~80분
(**주제당 20~30분 × 2~3개**, 25분 타이머로 리듬) → 클로징 15~20분(자유
Q&A + 다음 방송 예고). 주제 준비량은 방송 시간의 1.5배.
일본형은 20분 블록(도입 5 → 전개 10: **질문 → 3~5초 침묵 → 자문자답** →
결론 5)이 기본 단위. 침묵을 "시청자 참여 시간"으로 재정의하는 것이 설계 핵심.

→ **AI에게는 2시간 대본이 아니라 20분 블록 상태기계가 적합하다.**

### A-2. 채팅 읽기 메커니즘 [C]

- 질문 후 **10~15초 대기**(채팅 딜레이 감안)가 표준.
- **소규모(하꼬)는 전 채팅 낭독이 원칙** — "못 읽는 것과 안 읽는 것은
  다르다". 중·대규모는 선별로 전환.
- 읽히는 채팅의 우선순위(시청자 측 역산): 질문형 > 화제 확장형 > 진심
  리액션 > 응원 > 긍정 톤. 짧고 의도가 명확하며 현재 화제와 관련될 것.
- 침묵 대처 사다리: 나레이션(What-How-Why) → 백업 주제(3~5개 상시) →
  양자택일 질문("짜장면 vs 짬뽕"). 라커(lurker) 개별 지목은 이탈 유발 —
  집합 호명만.
- 후원 프로토콜: ① 즉시 닉네임 호명 → ② 흐름 접합부에서 메시지 낭독 →
  ③ 1~2문장 리액션. 토크 방송은 화제 전환 시점에 밀린 후원을 몰아 읽는다.
  금액 무관 성의, TTS 1.0~1.2배속, 최소 1,000~2,000원.
- 단골 관리 실무: 1등급 10~20명(이름·관심사·근황), 2등급 30~50명(닉·특징),
  3등급(첫 방문 환영). 콜백 형태 = "지난번에 말씀하신 그 게임 드디어
  시작했어요". 닉네임 호명 최소 3회/방송.

### A-3. 뉴로사마 벤치마크 [A/B]

- 방송 2~3시간(지루함 방지를 위해 24/7에서 의도적으로 축소). 게임·리액션·
  가라오케·저챗·**Dev Stream**(개발 과정 자체가 콘텐츠).
- **Vedal과의 티키타카가 주력 콘텐츠** — AI–인간 상호작용이 전체 게시물의
  18~23%로 최대 매력 요인 (arXiv:2509.20817).
- 채팅은 필터링·우선순위 로직으로 선별. 금지 발화는 무음이 아니라
  **"filtered." 화면 표시** — 필터가 콘텐츠가 됨. 팬덤은 필터를 "진짜
  성격을 가두는 감옥"으로 의인화.
- 학습 루프: 방송 → 트랜스크립트 수집 → **수동 큐레이션** → 오프라인
  파인튜닝 → 재배포. 추론 중 온라인 학습 없음. 크로스세션 영속 기억은
  미확인("지속 과제") — **트랙 M 보유가 추월 가능한 갭**.
- 2023-01 Twitch 2주 정지(홀로코스트 부정 발언) → 필터 강화의 선례.
- 침묵 처리는 1차 문서 부재 — 인간 파트너 + 병행 액티비티로 구조적
  회피하는 것으로 추정.

### A-4. 팬덤 학술 실측 (arXiv:2509.10427 — 팬 334명 설문) [A]

| 항목 | 수치 |
|---|---:|
| 알고리즘 추천으로 발견 | 96% |
| 커뮤니티–AI 상호작용이 중요 | 92% |
| 예측 불가·놀라움이 중요 | 90% |
| **일관된 성격을 인지** | **83%** |
| 슈퍼챗 중 능동형(새 질문·지시) | 85% (인간 버튜버는 반응형 50%+) |
| 결제 전환율 | 1.59% (인간 비교군 1.18%/0.83%) |

핵심 개념: **투명한 파라소셜**(인공물임을 알면서 애착), **진정성 = 일관성**
(인간다움이 아니라), 결제 = 전개 중인 공연에 대한 영향력 구매.
설계 권고: "일관성 + 전략적 예측불가능성"의 병행, 결함의 콘텐츠화
("10+9=21"이 사랑받는 밈, arXiv:2509.20817).

### A-5. 한국 씬 [B]

- 한국 AI 버튜버 계보: 모나루(2023, 종료)·라디안(2023~2026, 개발자 이직으로
  중단)·냥아지(콘텐츠 고갈로 중단)·Se:RIN(스마일게이트, 졸업)·코마리
  치이타(2025-10 치지직 데뷔)·제페토 나미(2026-01, 첫 방송 3,000명·채팅
  5,000건). **흥행형은 "기존 버튜버 클론 + 본인 합방"뿐, 단독형은 대부분
  수개월 내 중단.**
- 관례: 팬덤명 이중 구조(그룹+개인), 고정 시그니처 인사(이세계아이돌 "셋
  차원을 넘어!"는 시청자 공동 제작으로 정착), 신비주의.
- 금기: 정치·종교·특정인 비방·과도한 사생활. 무통보 휴방·지각 금지.
- 역설적 리스크: "반응이 너무 빨라 사람이 조작하는 것 아니냐"는 의심
  사례 존재 — 저지연 자체가 진위 의심을 부를 수 있음.

### A-6. 최소 성립 조건 (생략 불가 9)

① 오디오 공백 금지(침묵 사다리 정의) ② 응답 지연(1초 초과 단절감, 1.5초
초과 이탈) ③ 닉네임 호명 ④ 후원 즉시 인지 ⑤ 캐릭터 일관성 ⑥ 필터·
모더레이션("filtered" 표시 방식) ⑦ 고정 인사·클로징 ⑧ 오늘의 주제 선언
⑨ **인간 파트너 또는 그에 준하는 관계 축**.

생략 가능: 무결점 응답(결함=밈), 인간처럼 보이기, 中の人 비밀 관리,
고품질 3D(Live2D로 충분), 편집 채널.
소규모에서 필수 승격: 전 채팅 낭독, 단골 개별 기억, **콜백**, 고정 스케줄.

---

## B부. 기술 파이프라인

### B-1. 유튜브 채팅 수신

- **`liveChatMessages.streamList`** (gRPC server-streaming push, 문서 갱신
  2025-10-31) — 컷오프 이후 추가된 공식 저지연 경로. **쿼터 과금 방식이
  문서에 없음 → 착수 전 실측 1순위.**
- 폴링(`list`) 쿼터 산술: 기본 10,000 units/일, 비용 5 units/call(커뮤니티
  검증치) 가정 시 **2초 폴링으로 하루 약 1.1시간, 5초 폴링으로 2.8시간**.
  1 unit이면 5배. 쿼터 증액은 1인 프로젝트 승인 가능성 낮음.
- 슈퍼챗·스티커·멤버십은 동일 스트림의 `snippet.type`
  (`superChatEvent` 등)으로 수신 — 별도 호출 불필요.
- 비공식 라이브러리는 전멸: pytchat(2022 archived)·masterchat(2022)·
  youtube-chat(2023) — 단독 의존 금지.
- 폴백: **Social Stream Ninja** (GPL-3.0, 활발) — SSE
  `https://io.socialstream.ninja/sse/{APIKEY}`. 별도 프로세스 + SSE 소비로
  GPL 전파 회피.
- **`@aituber-onair/comment-intelligence`** (MIT, 2026-08 활발) — 프롬프트
  인젝션·스팸·반복 위반자 차단 + 시청자 안전 메모리. 전송 계층 비의존.
  **그대로 채택 권고.**
- AIRI 주입 지점은 기존 `input:text`(`ws://127.0.0.1:6121/ws`) — 타입
  union에 `'youtube'` 추가 1곳이 유일한 수정
  (`packages/plugin-protocol/src/types/events.ts:600`).

### B-2. 송출

- **권고: Electron 창 캡처 대신 `apps/stage-web`을 OBS Browser Source로
  직접 렌더** — 순수 Vite 앱 + `@proj-airi/server-sdk` 확인됨. 투명 배경
  네이티브, WGC·크로마키·Spout 문제 소멸.
- 오디오: **OBS 28+ 내장 Application Audio Capture**(WASAPI process
  loopback)로 AIRI 프로세스만 분리 — 가상 케이블 불필요. (AIRI에
  `setSinkId` 없음 확인)
- 자막: 프록시 TTS 문장 분기 → obs-websocket 5.x `SetInputSettings` →
  Text(GDI+). CEF 브라우저 소스 최소화.
- **VRAM 판정: 여유 842MiB로 NVENC 상주 불가** — 인코더 surface pool만
  195~340MiB 실측(OBS #13656, look-ahead 설정 의존). 해법 사다리:
  ① 방송 중 클라우드 LLM 전환(Mi:dm ~1.9GB 반납) — 현행 스위치는
  `AIRI_CHAT_PROVIDER=openai|anthropic` + `AIRI_ALLOW_EXTERNAL_CHAT=1`
  (과거 표기 `AIRI_LLM_MODE`는 옛 프로토타입 브랜치의 스위치로 현행
  코드에 없음. 그 프로토타입의 hybrid 반사 응답·모드 벤치는
  `archive/llm-backend-modes-2026-08-07` 태그에 보존 — 반사 1.36s 수치는
  exaone/CPU 기준이라 현행 모델로 재측정 필요) ② x264 CPU 인코딩(5600X
  여유 실측 필요) ③ 720p 다운스케일 + look-ahead OFF + 미리보기 비활성.
- 측정 프로토콜: `nvidia-smi` 3단계 델타(스택만 / +OBS / +방송).

### B-3. 안전장치

- **지연 버퍼 30~60초 = RAM 30~60MB, VRAM 0** (obs-output-delay.c 소스로
  확정 — 인코딩된 패킷을 RAM deque에 보관). 가장 값싼 안전 마진.
  RTMPS + 지연 버퍼 조합 권고(ultra-low-latency 포기).
- Killswitch 3중: L1 obs-websocket 대기씬 전환+뮤트(즉시) / L2 프록시 취소
  경로 재사용(ASGI finally 실측 검증됨) / L3 `liveBroadcasts.transition
  (complete)`.
- **한국어 출력 모더레이션 기성품 전무 확정**: Llama Guard 3(한국어 미지원,
  지원 8개 언어 목록 확인)·ShieldGemma(영어만)·Detoxify(7개 언어, 한국어
  없음). → 금칙어 사전 + 정규식 자체 구축이 유일한 경로. 삽입 지점은
  문장 단위 TTS 게이트.
- 입력 방어: comment-intelligence + `liveChatBans.insert` API.

### B-4. 정책 (2026-08 현재)

- 유튜브 AI 공시 의무: **photorealistic 대상 — 애니메이션 아바타는 면제
  범주** (답변 14328491 원문 확인).
- 수익화: 2025-07-15 "inauthentic content" 개정에서 **"AI로 창작자 고유
  캐릭터·내러티브 시각화"가 허용 예시로 명시** — AI 버튜버 수익화 가능
  범주.
- **한국 AI 기본법(2026-01-22 시행)**: 생성형 AI 산출물 표시 의무(문구
  또는 메타데이터·워터마크). 실시간 방송 적용 세부는 law.go.kr 원문 확인
  필요.
- 라이브 Content ID는 재방송 탐지 중심이나 BGM은 클리어된 것만 사용.

### B-5. 기존 오픈소스 판정

유튜브 채팅 수신 + OBS 송출을 모두 제대로 구현한 공개 프로젝트는 **없음**
(Ikaros-521/AI-Vtuber는 GPL+pytchat, Open-LLM-VTuber는 Bilibili만,
kimjammer/Neuro는 Twitch만). comment-intelligence(MIT)만 그대로 채택,
나머지는 패턴 참고만.

---

## 확인 필요 (미해결)

1. `streamList` 쿼터 과금 방식 — **착수 전 실측 1순위**
2. `liveChatMessages.list`의 공식 쿼터 비용(5 vs 1 units) 및
   `pollingIntervalMillis` 실측값
3. 5600X x264 1080p30 CPU 여유 실측
4. WGC 창 캡처의 알파 전달 여부 (Browser Source 경로 채택 시 무관)
5. 한국 AI 기본법의 실시간 방송·합성 음성 조항 원문
6. 뉴로사마 침묵 처리·크로스세션 기억의 1차 근거
7. 12시간 초과 방송 VOD 미보관 여부

## 주요 출처

학술: arXiv:2509.10427 (My Favorite Streamer is an LLM) ·
arXiv:2509.20817 (Even More Kawaii than Real-Person-Driven VTubers?) ·
Penn Annenberg (What Makes an AI Livestreamer Seem Real) ·
Wikipedia Neuro-sama
기술 1차: developers.google.com/youtube/v3/live/docs/liveChatMessages/streamList ·
determine_quota_cost · life-of-a-broadcast · OBS #13656 · OBS 28.0.0 릴리스
노트 · obs-output-delay.c · obs-websocket protocol ·
support.google.com/youtube/answer/14328491 · answer/1311392
실무: psdetector.co.kr 토크 방송·후원·단골 관리 시리즈 · 하꼬애호가 33가지
가이드(DCinside) · note.com 잡담 방송 구성 시리즈 · HoloStats 채팅 밀도
랭킹 · namu.wiki (Neuro-sama·인공지능 버츄얼 유튜버·스텔라이브)
오픈소스: github.com/shinshin86/aituber-onair ·
github.com/steveseguin/social_stream · github.com/obsproject/obs-studio
