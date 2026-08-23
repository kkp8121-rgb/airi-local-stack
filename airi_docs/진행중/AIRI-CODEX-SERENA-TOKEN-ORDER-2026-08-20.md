# 폐기된 실험 기록 — Serena MCP 토큰 A/B (2026-08-20)

> **RETIRED — 실행 금지.** 2026-08-23 사용자 결정으로 Serena는 사용하거나
> 재도입하지 않는다. 아래 배경·수치·결과표는 과거 A/B와 롤백의 감사 기록이며,
> 설치·등록·인덱싱·사용 정책 지시로 해석하지 않는다. 현행 정책은 루트
> `AGENTS.md`의 built-in/`rg` 코드 탐색 정책이다. Caveman trial도 자동 진행하지 않는다.

## 0. 배경·근거 (클로드 PC 조사, 2026-08-20)

- Serena 공식 평가에 **정확히 우리 조건(Codex CLI + Java/대형 코드베이스)**
  결과가 있다: 타입 계층 grep 반복 체인→1회 호출, cross-file rename 수동
  5~20단계→원자 1회, 참조 검색 정밀도 향상. 실패 사례·레이턴시 문제 보고
  없음. (oraios.github.io/serena/04-evaluation/)
- **역효과 구간도 실측돼 있다**: 1줄 수정(tiny edit)은 built-in patch가
  더 저렴, 설정 파일·자유 텍스트 검색·쉘 작업은 built-in 우월. 공식
  결론 = "심볼 작업만 Serena, 나머지는 built-in".
- 절감률 공식 수치는 없다. 커뮤니티 "70~80%"는 비검증 일화. 클로드 종합
  추정 = **대형 레포·탐색/리팩토링 위주 세션에서 총 토큰 30~60%**
  (보장 아님 — §5 실측으로 확정한다). MCP 도구 정의 상주 오버헤드
  (수천 토큰)가 있어 **소형 단발 작업 세션에선 순손실 가능**.
- airi-local-stack은 Python 위주 대형 레포(테스트 1,200+)라 적용 적합.
  PowerShell 스크립트·ps1 패치는 Serena 비대상(built-in 유지).

## 1~4. 폐기된 설치·등록·인덱싱·사용 절차

2026-08-20 실험 당시 절차는 §7 결과표의 역사적 증거로만 남긴다. 설치, Codex MCP
등록, 프로젝트 인덱싱, `AGENTS.md` 사용 정책 추가를 실행하지 않는다. 심볼·참조·
cross-file 작업도 repository built-in 도구와 `rg`를 사용한다.

## 5. 검증·실측 의무 (완료 주장은 증거 동반 — 하우스 룰)

1. **연결 검증**: `/mcp` 연결 + 실작업 1회(예: `resolve_chat_model`
   심볼의 참조 조회)로 도구 호출 성공 로그 확보.
2. **A/B 실측 프로토콜** (분산이 크므로 단일 런 판정 금지 — 이 레포
   시뮬 실측의 기존 교훈과 동일):
   - 대표 작업 3종을 고정하고 §7에 기록: ①심볼형(예: ollama_proxy.py
     특정 심볼의 참조 전수 조회) ②리팩토링형(cross-file rename 1건,
     브랜치에서 수행 후 폐기) ③설정/문서형(대조군 — 이득 없어야 정상)
   - 각 작업 = **fresh Codex 세션**에서 동일 프롬프트로, serena
     ON/OFF(config.toml 블록 주석 토글) 각 3세션 = 총 18세션
   - 세션마다 종료 직전 `/status` 토큰 집계(입력·캐시·출력)를 기록하고,
     `~/.codex/sessions/`의 해당 세션 로그에서 usage 합산으로 교차 검증
     (로그 스키마는 코덱스가 자기 세션 파일을 직접 열어 확인 — 필드명
     추측 금지, 확인 불가면 `/status` 단독 기록으로 폴백하고 §7에 명시)
3. **판정 (수치 기준 — 제안값, 조정 시 §7에 사유 기록)**: ①②의
   arm 평균 입력 토큰 절감 **≥15% → 채택 유지**. **<10% → §6 롤백
   즉시 실행** (불필요한 상주 오버헤드이므로 걷어낸다). 10~15% → §4
   정책 준수 여부 점검 후 1회 재측정, 그래도 <15%면 롤백. 편집 오류·
   왕복 횟수가 ON에서 악화되면 절감과 무관하게 롤백.

## 6. 경계·롤백

- AIRI 코드·운영 env·픽스처·`airi_docs/patches/` 무접촉 — 이 작업의
  변경 허용 범위는 ①`~/.codex/config.toml` ②`AGENTS.md` §4 블록
  ③전역 gitignore ④본 문서 §7 추기, 4가지뿐이다.
- **serena 완전 롤백 절차** (①~②로 즉시 무효화, ③~④는 청소):
  ① `~/.codex/config.toml`의 `[mcp_servers.serena]` 블록 제거
  ② `AGENTS.md`의 "Serena 사용 정책" 절 제거(커밋)
  ③ `uv tool uninstall serena-agent` ④ 레포의 `.serena/` 디렉토리 삭제
  (전역 gitignore의 `.serena/` 줄은 무해 — 잔류 가능)
- Serena 자체 셸 실행류 도구는 Codex 하네스에서 기본 비활성(공식
  문서) — 활성화하지 말 것.

## 7. 결과 보고 (코덱스 추기란)

> 코덱스는 완료 후 아래 표를 채우고 이 문서를 커밋, `로드맵/AIRI-ROADMAP-LOG.md`에
> 1줄 기록한다. (형식: 날짜 / 단계 / 증거 경로·수치)

| 항목 | 결과 | 증거 |
|---|---|---|
| §1~2 설치·연결 | 2026-08-20 설치·실연결 성공 후 판정에 따라 등록 롤백 | `Serena 1.7.0`; TUI `/mcp`에서 Serena 도구 24종 표시; 실제 `initial_instructions` → `find_symbol` → `find_referencing_symbols` 성공(thread `01a01f61-dbef-7b30-806b-d6d5a47d7f83`) |
| §3 인덱싱·온보딩 | Python 382파일 인덱싱, 온보딩 메모리 11개 인식, 전역 ignore 적용 | `.serena/project.yml`; `.serena/memories/`(전역 ignore); `serena memories check` → `✓ No referential integrity issues found.` |
| §4 AGENTS.md 배선 | 지시 블록 원문 그대로 추가 | 루트 `AGENTS.md`의 `Serena 사용 정책 (2026-08-20)` |
| §5 A/B 토큰 실측 (arm별 수치) | `gpt-5.6-luna`/low, 완료 3세션/arm. 총 토큰 ON=`130,673 / 233,882 / 252,156`(심볼/리팩터링/설정문서; 합 616,711, 평균 205,570), OFF=`86,433 / 78,094 / 96,148`(합 260,675, 평균 86,892). ON 평균 **+136.6% 순손실** | ON threads `01a01f61-dbef-7b30-806b-d6d5a47d7f83`, `01a01f64-5221-7031-86fe-f36bcb93e0fb`, `01a01f65-d107-7c30-b797-6eac1dd4732d`; OFF threads `01a01f62-f7fe-79e2-a107-a5c116b89e55`, `01a01f65-0c6a-70f0-b925-c9c51e205052`, `01a01f66-bd5a-74c0-ae30-682c858c63db`. ON 연결 미노출 실패 2회(각 57,657·56,079토큰)는 완료 표본에서 제외했으나 안정성 판정에 반영 |
| 채택/롤백 판정 | **롤백** — 세 유형 전부 순손실(ON 대비 OFF: +51.2% / +199.5% / +162.3%)이고 간헐적 MCP 미노출 2회. `~/.codex/config.toml` Serena 블록 제거 완료 | 롤백 후 `codex mcp list`에 Serena 없음; 설치물·인덱스·전역 ignore·정책 기록은 보존 |
| §8 caveman trial 실측 (세션 유형별) | | |
| §8 caveman 채택/부분 채택/기각 판정 | | |

## 8. Phase 2 — Caveman 프록시 (serena 적용 확인 2026-08-21, 클로드 검토 완료분)

Serena가 "적게 읽기"라면 caveman 프록시(github.com/JuliusBrussee/caveman,
99.7k★, 2026-08-21 검토)는 "그래도 흐르는 것 압축"이다 — 로컬 프록시가
provider 호출 직전 tool 출력을 유형별 압축(테스트 출력 27.8%·로그
50.2%·JSON 리포트 26.4% — 공식 벤치 실측)하고 원본은 디스크에 byte-exact
보존한다. **주의: 공식 33.2%(CI 14.6~48.5%)는 Claude Code 측정이고 Codex
벤치는 없다.** 클로드 추정 = 코덱스 워크로드(테스트·시뮬·학습 로그 위주)
기준 입력 15~30%, 코드 편집 세션은 0~순손실 위험(`code` 압축기가 함수
본문을 생략 → patch 컨텍스트 불일치 재시도 가능). serena와 절감 축이
겹치므로 합산 기대 금지 — 그래서 trial 실측이 의무다.

1. **설치** (프록시만 — **스킬(`npx skills add`)은 설치 금지**, 출력 축소는
   보고 품질 훼손 + 순손실 가능이라 기각됨):
   ```powershell
   npm install -g @caveman-ai/cli
   caveman setup --install
   caveman telemetry off     # 필수 — 익명 텔레메트리 기본 ON
   ```
2. **실측**: 내장 A/B 하네스 사용 — `caveman trial -- codex`로 실세션
   기록 후 `caveman trial report`. **세션 유형 2종을 반드시 분리 측정**:
   ①실행형(pytest·시뮬·벤치 돌리고 결과 읽기 — 추정 상한 지형)
   ②코드 편집형(patch 실패율·재시도 횟수를 함께 기록).
3. **판정**: ①에서 유의 절감 + ②에서 patch 실패율 무악화 → 전면 채택
   (`caveman codex`로 상시 wrap). ②만 악화 → **부분 채택**(실행형
   세션에만 wrap). 전 유형 무이득 → 제거(`npm uninstall -g` — 가역).
4. **경계**: 엔진은 BSL-1.1(자가 사용 무료 — 우리 용도 허용), ChatGPT
   구독 로그인은 ephemeral CODEX_HOME 방식으로 자격증명이 로컬 프록시를
   경유함을 인지할 것. 레포 무접촉 원칙은 §6과 동일. loopback upstream은
   차단돼 있어(이슈 #841) 로컬 릴레이엔 못 물린다 — AIRI의 127.0.0.1
   프록시와는 무관(그건 Codex provider 트래픽이 아님).
5. **caveman 완전 롤백**: wrap 사용 중지 → `npm uninstall -g
   @caveman-ai/cli` → `~/.caveman-cloud/` 삭제. 스킬은 애초에 미설치라
   걷을 것 없음.

## 9. 코덱스 실행 프롬프트 (사용자가 Codex CLI에 그대로 붙여넣기)

```text
airi_docs/진행중/AIRI-CODEX-SERENA-TOKEN-ORDER-2026-08-20.md 를 정독하고 순서대로 실행하라.

1) Phase 1(serena)은 이미 적용돼 있다 — §1~§4 상태를 실측 점검만 하고
   (미비点 있으면 §대로 보완), §5 A/B 프로토콜을 그대로 수행하라:
   작업 3종 고정 → fresh 세션 × ON/OFF × 3회 = 18세션, /status + 세션
   로그 교차 검증. 필드명·경로는 추측하지 말고 자기 세션 파일을 열어
   확인하라.
2) §5-3 수치 판정을 적용하라: ≥15% 유지 / <10% 즉시 §6 롤백(걷어내기)
   / 10~15% 재측정 1회. 판정과 근거 수치를 §7 표에 추기하라.
3) serena 판정이 끝난 뒤에만 §8 Phase 2(caveman 프록시)를 진행하라:
   스킬 설치 금지, telemetry off, trial 2유형 분리 실측, §8-3 판정
   (전면/부분/기각 — 기각이면 §8-5 롤백으로 걷어내라).
4) 모든 결과(수치·판정·롤백 여부)를 §7 표에 추기하고, 이 문서와
   AGENTS.md 변경만 커밋·push하라. 레포 코드·운영 설정은 무접촉이다.
5) 완료·성공 주장은 반드시 직전 실측 증거(세션 로그 경로·수치)를
   동반하라. 증거 없는 완료 선언 금지.
```
