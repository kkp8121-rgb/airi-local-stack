# AIRI STT OFF 방송 프로파일 — 결정 및 실기 증거 (2026-08-12)

## 결정

기본 방송 프로파일은 **채팅/텍스트 입력, STT OFF**다. 실제 마이크와 STT 개발은
사용자가 재개를 명시할 때까지 보류하며, Electron 마이크 토글도 OFF로 둔다.

`start-airi-local-stack.ps1`의 검증된 기본값은 `-Stt off`다. 명시적으로
`-Stt on` 또는 `AIRI_STT=on`을 주면 켤 수 있다. OFF 모드에서는 Python 실행
파일·저장소의 정확한 서버 경로·loopback host·port 인자가 모두 일치하는 STT
프로세스만 종료한다. 그 뒤 local port `8890` listener가 하나라도 남으면 계속
기동하지 않고 거부한다.

## 실기 증거

- repo stop 스크립트가 정확히 경로가 일치한 STT PID `16220`, `26220`을 종료했다.
- 직후 기본 런처 재실행은 변수 충돌 수정 후 성공했다: `STTMode=off`,
  `STT=disabled`, STT model/device는 빈 값. `8880`, `11434`, `11435` listener는
  존재했고 `8890`은 없었다. proxy `/health`는 `ok`, memory extraction disabled,
  moderation disabled였다. extraction은 failed gate 때문에 OFF 유지이고,
  moderation 기본 OFF는 의도된 운영 선택이다.
- GPU 총 메모리 paired sample(동시의 무관 GPU 작업 존재): STT 전
  `7790, 7782, 7786, 7787, 7787 MiB` (평균 `7786.4 MiB`), STT 후
  `6741, 6741, 6741, 6741, 6748 MiB` (평균 `6742.4 MiB`), 관측 차이
  `1044 MiB`.

이 GPU 수치는 동시 무관 작업이 있는 paired observation일 뿐이며, 공식적인 깨끗한
B0 capacity proof가 아니다. 기존 B0 측정 사실은 변경하지 않는다.

## 검증

- root launcher/background `unittest`: `21 passed`
- extraction-gate launcher regression `unittest`: `21 passed`
- `start-airi-local-stack.ps1` PowerShell parser: `PASS`
- 잘못된 `AIRI_STT` 환경값의 서비스 기동 전 fail-closed: `PASS`
- STT 내부 테스트는 시스템 Python에 선택 의존성 `av`가 없어 수집되지 않았다.
  STT OFF 런처 및 실제 기본 방송 기동 검증 결과에는 영향이 없다.

## 재개 조건

사용자가 **STT/마이크 개발 재개**를 요청한 경우에만 `-Stt on`으로 시작하고,
보류한 실제 마이크 20+20, AEC, barge-in 시험을 수행한다. TTS 참조 음성 관련
경고는 이 STT 결정의 일부가 아니다.
