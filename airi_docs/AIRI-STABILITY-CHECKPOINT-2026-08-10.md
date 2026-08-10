# AIRI 안정화 체크포인트 — 2026-08-10

## 오늘 고정한 범위

오늘은 선택지 A인 재현성·검증 안정화만 수행했다.

- B: 대화 자연스러움 및 grounding 정책 변경은 다음 체크포인트로 연기했다.
- C: 2초 지연 목표 및 corrective retry 정책 변경도 다음 체크포인트로 연기했다.
- 독립 검토 문서의 경로·개인정보 정리 작업은 사용자의 지시에 따라 수행하지 않았다.
- 모델, 서비스, 마이크, TTS, 운영 DB 및 ignored 런타임 산출물은 호출하거나 변경하지 않았다.

기준 브랜치는 `fix/code-audit-remediation-2026-08-07`, 시작 HEAD는 `9997145`였다.

## 확인된 기준선

저장소 루트에서 Python 3.12 격리 환경으로 다음 범위를 실행했다.

```powershell
python -m pytest -q ollama-proxy test_latency_trace.py test_start_airi_background.py latency-monitor stt
```

수정 전 결과는 `660 passed, 1 failed, 1 skipped, 365 subtests passed`였다.

유일한 실패는 `test_first_raw_watchdog_bounds_a_stream_that_never_starts`였다. 테스트가 지정한 10 ms는 Windows 단조 시계 해상도보다 짧아서 의도한 raw-body stall이 아니라 response-header timeout 경로를 검사했다. 또한 승인 지식 테스트는 이 PC에 남아 있던 ignored `runtime/` 파일 때문에 통과했을 뿐, 클린 체크아웃에서는 재현되지 않는 구조였다.

## 변경 사항

1. 승인된 공개 지식 9건의 테스트 입력을 `ollama-proxy/testdata/approved-knowledge-2026-08-09.json`으로 추적한다.
2. `test_knowledge_store.py`가 ignored 운영 경로가 아니라 추적되는 테스트 입력을 읽도록 변경했다.
3. first-raw watchdog 테스트의 watchdog/stall 간격을 각각 50 ms/200 ms로 분리해 Windows에서도 의도한 raw-body timeout 경로를 결정적으로 검증한다.
4. `.github/workflows/remediation-checkpoint.yml`에 별도 `python-core-tests` job을 추가했다.
   - Windows + Python 3.12
   - 모델 가중치나 `sentence-transformers` 전체 스택 대신 테스트에 필요한 직접 의존성만 설치
   - 루트 기준의 명시적 Python 테스트 범위를 실행

테스트 fixture는 운영 지식 DB를 자동으로 생성하거나 활성화하지 않는다. 운영 지식의 배포·활성화 정책은 별도 결정 사항이며 이번 안정화 범위에 포함하지 않았다.

## 검증 결과

- 전체 Python 범위: `661 passed, 1 skipped, 365 subtests passed`
- 기존 오프라인 체크포인트: PASS
- Node sender 계약: `26 passed`
- 패치 매니페스트/엔트리포인트: PASS
- 패치 적용성: 기존 계약대로 명시적 base checkout이 없어 SKIP
- 모델·서비스·마이크·TTS 호출: 0

## 다음 작업 경계

다음 세션은 먼저 이 체크포인트가 다른 PC의 클린 체크아웃에서도 재현되는지 독립 검증한다. 그 검증이 끝나기 전에는 B나 C를 시작하지 않는다.

검증 이후 사용자가 별도로 선택할 작업은 다음 두 가지다.

- B: 자연스러움 우선 — grounding의 반복·침묵·앵무새 응답 정책을 별도 acceptance 기준으로 다룬다.
- C: 지연시간 우선 — 2초 목표와 corrective retry의 비용·상한을 별도 acceptance 기준으로 다룬다.

두 정책을 한 변경에서 동시에 최적화하지 않는다.

## 다른 PC의 Claude 세션에 전달할 문구

아래 문구를 그대로 전달한다.

```text
저장소 branch fix/code-audit-remediation-2026-08-07을 git pull --ff-only로 갱신해 주세요.

이번 검토는 9997145 이후의 AIRI 안정화 체크포인트만 대상으로 합니다. 먼저 airi_docs/AIRI-STABILITY-CHECKPOINT-2026-08-10.md를 읽고, 구현 설명을 신뢰하지 말고 독립적으로 확인해 주세요.

검토 범위:
1. git status가 clean이고 원격 branch와 동기화됐는지 확인
2. git diff 9997145..HEAD로 실제 변경 파일과 범위를 확인
3. .\test-current-checkpoint.ps1 실행
4. 클린 Python 3.12 환경에서 다음 전체 범위를 실행
   python -m pytest -q ollama-proxy test_latency_trace.py test_start_airi_background.py latency-monitor stt
5. test_knowledge_store.py가 ignored runtime/ 파일 없이 tracked testdata fixture만으로 통과하는지 확인
6. first-raw watchdog 테스트가 response-header가 아니라 raw-body timeout 경로를 실제로 검증하는지 확인
7. .github/workflows/remediation-checkpoint.yml의 python-core-tests job이 클린 Windows runner에서 필요한 의존성을 모두 설치하고 위 범위를 실행하는지 정적 검토
8. 새 fixture에 비밀키, 개인 대화, 세션 ID, 로컬 절대 경로가 없는지 privacy-safe하게 검사

제약:
- 모델, Ollama, STT, TTS, 마이크, 운영 서비스, 운영 DB를 호출하거나 변경하지 마세요.
- B(자연스러움/grounding 정책)와 C(2초 지연/retry 정책)는 이번 검토 범위 밖입니다.
- 독립 검토 문서의 문구 수정이나 과거 patch artifact 정리는 하지 마세요.
- 발견 사항은 HIGH/MED만 우선 보고하고, 테스트 재현성 수정과 운영 지식 배포 정책을 구분해 주세요.
- 수정은 하지 말고 읽기 전용 검토 결과와 재현 명령/결과만 보고해 주세요.
```
