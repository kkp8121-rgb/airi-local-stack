# AIRI B3 Electron 모더레이션 실기 검증 (2026-08-12)

## 소스·빌드 계약

v0.11.3 `dbf8124`의 깨끗한 checkout에 canonical → sanitizer → Upgrade
Scout 세 레이어를 순서대로 적용했다. 최종 임시 commit은 `dcf9396`, 실제
tree는 `d40b4a3`이며 패치 SHA-256은
`13417A7464C35B2A8C2E8FDC54F37E629C32F031F9F7DA5EB6073B995E1F63DA`다.
패치 manifest와 apply/reverse 계약이 통과했다.

- moderation stream/store 집중 테스트: 21 PASS
- Stage UI, Stage Tamagotchi typecheck: PASS
- Electron main/preload/renderer production build: PASS

설치 ASAR는 `A81C5281…`에서
`1B68AE5ECB9DB998002AC7268DE707661EC0C81FC4BD90836F3C3E25719B88B0`로
교체했다. 후보의 native 파일 18개는 설치본 대응 파일과 모두 해시가
같았고 기존 `app.asar.unpacked` 135개는 변경하지 않았다. 원본 ASAR와
unpacked 전체는
`%LOCALAPPDATA%\AIRI-Codex-Backups\20260812-1955-before-moderation-badge`에
보존했다.

## 실제 차단 턴

일시 정책의 단일 정규식 `(?s).`으로 모든 비어 있지 않은 생성 문장을
차단했다. 설치 AIRI를 loopback CDP로 관찰하면서 실제 server-channel 턴을
보낸 결과는 다음과 같다.

- sender 완료 768ms, 원문 대신 운영 폴백 대사만 반환
- `/health.output_moderation`: inspected 0→2, blocked 0→2
- 메인 renderer DOM: exact text `필터당함`, visible `DIV`, 80×28px
- 배지 스크린샷(dev PC local-only, `runtime/` gitignore로 커밋되지 않음):
  `ollama-proxy/runtime/electron-moderation-badge-20260812.png`, SHA-256
  `63AC5688B38B57A1028ADD6C2BF12D7FA5442B1C3E503137CDC8DD9A65C2879B`

따라서 xsAI SSE 보존 → core event → loopback-only store → Stage 배지의
전 구간이 실제 설치본에서 증명됐다. 검증 후 임시 정책은 삭제했고 CDP도
닫았다. 운영은 출력 모더레이션 기본값 **off**, Mi:dm digest pinned/verified,
기존 일본어 참조, TTS cache 7/7, 설치 AIRI background 상태로 복구했다.
