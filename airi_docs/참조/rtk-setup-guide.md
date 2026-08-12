# rtk 설치 가이드 — 클라우드 LLM 토큰 절감 (다른 PC 적용용)

> 작성: 2026-08-06 · 근거: [rtk-ai/rtk](https://github.com/rtk-ai/rtk) README/docs 실측 (v0.28+ 기준, 훅은 v0.37.2+ 네이티브)
> 갱신: 2026-08-06 — §4에 계측(벤치마크) 명령 보호 추가 (AIRI 프로젝트 대응, README 재검증 완료)
> 목적: 코딩 에이전트(Claude Code 등)가 읽는 셸 출력을 압축해 입력 토큰을 절감하는 rtk를 새 PC에 전역 설치한다.

---

## 0. 배경 — 토큰 절감 3축 스택 결론 요약

| 축 | 도구 | 상태 |
|---|---|---|
| ① 입력 압축 | **rtk** | ✅ **이 문서로 설치** — 유일한 실행 항목 |
| ② 호출 생략·라우팅 | LiteLLM 게이트웨이 | ⏸ 보류 — 자체 앱에 LLM API 호출이 생기는 시점에 도입 (구독형 Claude Code/Codex 트래픽에는 효과 없음) |
| ③ prompt caching | 프로바이더 내장 기능 | ✅ 설치 불필요 — Claude Code·Codex 모두 자동 적용 중 |

**rtk가 하는 일**: 에이전트가 실행하는 셸 명령을 훅으로 가로채(`git status` → `rtk git status` 자동 재작성), 진짜 명령을 그대로 실행한 뒤 **출력만** 규칙 기반 Rust 파서로 압축해 돌려준다. 명령의 실제 동작·결과물은 불변. 테스트/린트 출력 기준 60~90% 절감(청구서 전체 기준 아님 — §6 참고).

---

## 1. 설치 — Windows 네이티브 (권장)

```powershell
# 1) ripgrep 선행 설치 (일부 필터가 rg를 호출함 — 없으면 경고 발생)
winget install BurntSushi.ripgrep.MSVC

# 2) 최신 릴리스에서 Windows 바이너리 다운로드
#    https://github.com/rtk-ai/rtk/releases → rtk-x86_64-pc-windows-msvc.zip
# 3) 압축 해제 후 rtk.exe를 PATH 경로에 배치 (예: C:\Users\<사용자>\.local\bin)
#    PATH에 없으면 시스템 환경변수 Path에 해당 폴더 추가

# 4) 설치 확인 (반드시 터미널에서 — rtk.exe 더블클릭 금지, CLI라 바로 종료됨)
rtk --version   # 버전 출력 확인
rtk gain        # 절감 대시보드 출력 확인
```

- v0.37.2부터 훅이 **네이티브 바이너리**(`rtk hook claude`)로 동작 — bash/jq/Unix 셸 불필요, PowerShell·CMD에서 그대로 작동.
- cargo로 설치할 경우 crates.io의 동명 패키지(Rust Type Kit)와 충돌 주의 → `cargo install --git https://github.com/rtk-ai/rtk` 사용.

## 2. 설치 — macOS / Linux / WSL (참고)

```bash
brew install rtk                    # macOS (권장)
# 또는
curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh
# → ~/.local/bin 에 설치됨. PATH에 없으면 추가
```

## 3. Claude Code 전역 연동

```powershell
rtk init -g          # Claude Code / Copilot 전역 훅 설치 (기본값)
# 다른 도구: rtk init -g --gemini | --codex | --agent cursor | --agent windsurf 등
```

설치 후 **Claude Code를 재시작**해야 훅이 적용된다.

**동작 검증** (재시작 후 Claude Code 세션에서):
- 에이전트에게 `git status` 실행을 시키면 자동으로 `rtk git status`로 재작성되어 압축 출력이 나오는지 확인
- `rtk gain --history`로 명령이 기록되는지 확인

## 4. 보수적 초기 설정 (권장)

설정 파일: `~/.config/rtk/config.toml` (Windows는 `C:\Users\<사용자>\.config\rtk\config.toml` — 없으면 생성. macOS는 `~/Library/Application Support/rtk/config.toml`)

```toml
[hooks]
# 압축이 불안한 명령은 훅 재작성에서 제외 (도입 초기 권장 예시)
# 계측 명령 제외는 아래 "계측 명령 보호" 참고 — 프로젝트의 벤치 실행 명령에 맞춰 조정
exclude_commands = ["git diff", "python bench", "bench.py"]

[tee]
enabled = true
mode = "always"      # 도입 초기: 항상 원본 전체 보존 ("failures"가 기본값)
```

- **tee = 안전망**: 명령 실패 시(또는 always면 항상) 압축 전 원본 전체를 파일로 저장하고 경로를 출력 → 에이전트가 재실행 없이 원문 확인 가능.
- 신뢰가 쌓이면 `mode = "failures"`(기본값)로 되돌리고 exclude를 줄인다.

### 계측(벤치마크) 명령 보호 — AIRI 프로젝트 필수

AIRI 저지연 계획은 모든 채택 판정을 P50/P95 실측(TTS TTFA, STT 지연, 기억 검색 등)으로 내린다. rtk는 손실 압축이므로 **벤치 출력의 수치가 왜곡·생략되면 잘못된 측정값으로 Phase 판정이 이뤄질 위험**이 있다. 계측만큼은 압축을 태우지 않는다:

1. **벤치 실행 명령을 `exclude_commands`에 추가**한다 (위 예시). 일회성 실행은 `rtk proxy <명령>`으로 원본 통과(§6-4).
2. **벤치 스크립트는 "파일 저장 + 요약 출력" 패턴으로 작성**한다: 상세 결과(회차별 수치)는 JSONL/JSON 파일로 저장하고 stdout에는 요약 몇 줄만 출력. 에이전트는 상세 수치를 Read 도구로 파일에서 읽는데, **Read는 애초에 rtk 압축 대상이 아니므로**(§6-1) 이 패턴에서는 exclude로 잃는 절감이 사실상 0이다.
3. **예상 절감 손실은 무시 가능 수준**: 벤치 출력은 세션 bash 출력의 소수 비중(추정 5~15%)이고 밀도 높은 숫자라 압축 여지도 낮아, 청구서 기준 손실은 ~1%p 안팎으로 추정된다(§5의 실측으로 확정).

## 5. 절감 측정

```powershell
rtk gain             # 요약 통계 (Save% = 신뢰 가능한 비율)
rtk gain --graph     # 최근 30일 그래프
rtk gain --history   # 명령별 이력 (미지원 명령은 0%로 기록됨)
```

- **exclude 목록 검증**: 몇 세션 사용 후 `rtk gain --history`에서 벤치 명령의 실제 출력 비중을 확인하고, §4 계측 보호의 "손실 ~1%p" 추정을 실측으로 확정한다. 비중이 예상보다 크면 벤치 스크립트를 "파일 저장 + 요약 출력" 패턴으로 고치는 쪽을 우선하고(절감 회복 + 정확성 유지), exclude를 푸는 선택은 하지 않는다.

## 6. 한계·주의 (정직 고지)

1. **Bash 훅에만 적용** — Claude Code 내장 `Read`/`Grep`/`Glob` 도구는 압축되지 않음. 필요 시 `rtk read`/`rtk grep`/`rtk find`를 직접 사용.
2. **절감률은 bash 출력 기준** — bash 출력은 입력 토큰의 일부, 입력은 청구서의 일부. 체감 절감은 세션 성격에 따라 한 자릿수~40% 수준으로 희석됨. 테스트·빌드 헤비 세션일수록 상단.
3. **토큰 수치는 `bytes ÷ 4` 추정치** — 절대값은 청구서와 불일치, 비율(Save%)만 신뢰.
4. **손실 압축** — 파서 오판 리스크 0 아님. §4의 tee·exclude가 완화 장치. 수동 우회는 `rtk proxy <명령>`(원본 통과).
5. 압축과 무관하게 **명령 실행 자체와 결과물(커밋·파일·DB)은 불변**.

## 7. 제거

```powershell
rtk init -g --uninstall   # 훅·RTK.md·settings.json 항목 제거
# 이후 rtk.exe 삭제 (cargo면 cargo uninstall rtk, brew면 brew uninstall rtk)
```

## 참고 링크

- 레포: https://github.com/rtk-ai/rtk
- 공식 가이드(설치·지원 에이전트·설정·트러블슈팅): https://www.rtk-ai.app/guide
- 절감 원리 상세: `docs/guide/resources/savings-explained.md` (레포 내)
