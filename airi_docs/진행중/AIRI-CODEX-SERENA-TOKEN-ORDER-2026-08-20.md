# 코덱스(GPU dev PC) 작업 명령 — Serena MCP 도입으로 Codex 토큰 절감 (2026-08-20, 클로드 PC 발신)

> 목적: 코덱스 PC의 Codex CLI에 Serena MCP(시맨틱 코드 검색·편집,
> github.com/oraios/serena, 28.3k★)를 붙여 **파일 통짜 read·grep 반복
> 체인을 심볼 단위 조회로 대체**해 토큰 소비를 줄인다. 본 문서는
> 자기완결형이며, 절차 §1~§5를 순서대로 실행하고 §7에 결과를 추기한다.
> 이 작업은 **코덱스 PC의 에이전트 환경 변경**이다 — AIRI 레포 코드·운영
> 설정은 건드리지 않는다 (§6 경계).

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

## 1. 설치 (1회)

```powershell
# uv가 없으면 (유일한 선행 조건):
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# 새 셸에서:
uv tool install -p 3.13 serena-agent
serena --version   # 성공 확인 (PATH에 없으면 새 터미널 또는 uv tool update-shell)
```

주의: MCP 마켓플레이스 경유 설치 금지(공식 README가 outdated 명령이라고
명시). 위 명령이 유일한 공식 경로다.

## 2. Codex 등록 (공식 스니펫 그대로)

`~/.codex/config.toml`에 추가:

```toml
[mcp_servers.serena]
startup_timeout_sec = 15
command = "serena"
args = ["start-mcp-server", "--project-from-cwd", "--context=codex"]
```

Codex 세션에서 `/mcp` 실행 → serena 연결 확인. `--project-from-cwd`라
**Codex를 반드시 airi-local-stack 루트에서 기동**해야 프로젝트가 잡힌다.

## 3. 프로젝트 준비 (1회)

1. **인덱싱**: 레포 루트에서 `serena project index` — 언어 서버 심볼을
   선캐시해 첫 호출 지연을 없앤다. 이후는 자동 갱신.
2. **온보딩 토큰 선소비 주의**: 최초 세션에서 Serena가 온보딩(파일
   다수 read + 메모리 생성)을 자동 수행한다 — **저부담 세션 하나를
   온보딩 전용으로 소모**하고 본 작업은 다음 세션부터.
3. **레포 오염 금지**: Serena가 레포에 `.serena/`(project.yml·메모리)를
   생성한다. **커밋 금지·레포 .gitignore 수정도 금지** — 전역 제외로
   처리한다 (클로드 PC의 `.gstack/` 오염 사고와 같은 유형 예방):
   ```powershell
   git config --global core.excludesFile "$HOME/.gitignore_global"
   Add-Content "$HOME/.gitignore_global" ".serena/"
   git status --short   # .serena/ 미표시 확인
   ```

## 4. 사용 정책 — AGENTS.md에 아래 절을 그대로 추가

레포 루트 `AGENTS.md` 말미에 추가(코덱스 에이전트가 매 세션 준수하도록
배선하는 것이 목적):

```markdown
## Serena 사용 정책 (2026-08-20)

- Serena로 할 것: 심볼 검색·참조 조회·타입 계층·cross-file rename/move·
  메서드 본문 단위 read/edit. 파일 전체 read 전에 반드시 심볼 조회 먼저.
- built-in으로 할 것: 1~2줄 수정, 자유 텍스트/문자열 검색, 설정·JSON·
  픽스처·ps1·md 파일, 쉘·git·테스트 실행.
- 판단 기준 한 줄: "IDE라면 go-to-definition을 쓸 작업인가?" — 그렇다면 Serena.
```

## 5. 검증·실측 의무 (완료 주장은 증거 동반 — 하우스 룰)

1. **연결 검증**: `/mcp` 연결 + 실작업 1회(예: `resolve_chat_model`
   심볼의 참조 조회)로 도구 호출 성공 로그 확보.
2. **A/B 실측**: 대표 작업 3종(심볼 탐색형·리팩토링형·설정/문서형)을
   Serena ON/OFF 각각 수행하고 세션당 토큰 집계(Codex `/status` 또는
   세션 로그)를 기록. 최소 3세션/arm. GPU 큐 작업(인계문 2026-08-19
   §2)을 그대로 A/B 소재로 써도 된다.
3. **판정**: 심볼·리팩토링형에서 유의한 절감이면 유지, 전 유형 순손실
   이면 §6 롤백. 중간 결과(심볼형만 이득)면 §4 정책 준수 강화로 대응.

## 6. 경계·롤백

- AIRI 코드·운영 env·픽스처·`airi_docs/patches/` 무접촉 — 이 작업의
  변경 허용 범위는 ①`~/.codex/config.toml` ②`AGENTS.md` §4 블록
  ③전역 gitignore ④본 문서 §7 추기, 4가지뿐이다.
- 롤백 = config.toml의 `[mcp_servers.serena]` 블록 제거(완전 가역).
- Serena 자체 셸 실행류 도구는 Codex 하네스에서 기본 비활성(공식
  문서) — 활성화하지 말 것.

## 7. 결과 보고 (코덱스 추기란)

> 코덱스는 완료 후 아래 표를 채우고 이 문서를 커밋, `로드맵/AIRI-ROADMAP-LOG.md`에
> 1줄 기록한다. (형식: 날짜 / 단계 / 증거 경로·수치)

| 항목 | 결과 | 증거 |
|---|---|---|
| §1~2 설치·연결 | | |
| §3 인덱싱·온보딩 | | |
| §4 AGENTS.md 배선 | | |
| §5 A/B 토큰 실측 (arm별 수치) | | |
| 채택/롤백 판정 | | |
