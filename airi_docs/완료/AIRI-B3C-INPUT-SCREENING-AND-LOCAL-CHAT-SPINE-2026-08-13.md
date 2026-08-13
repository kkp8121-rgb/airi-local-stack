# AIRI B3-c 입력 프리필터 및 로컬 채팅 전달 경계

## 판정

소스·오프라인 계약과 loopback 정책 probe는 완료했다. 기능은 기본 OFF다.
이 문서는 다국어 semantic safety, 실제 YouTube 수신, 설치 UI/TTS 반응 또는
방송 안전 완료를 주장하지 않는다.

## 구현 경계

- 프록시는 model/state/memory/upstream보다 먼저 현재 입력과 재유입 가능한
  과거 user 입력을 검사한다. persona takeover, 욕설, 노골적 성적 요청,
  표적 괴롭힘, 개인정보를 결정론적으로 차단한다.
- OpenAI chat/completions, Ollama chat/generate와 legacy completions의 텍스트
  입력을 검사하고, 비텍스트·image 입력은 enabled 상태에서 fail closed한다.
- 정책·health boolean·정책 SHA 불일치 시 launcher가 기존 listener 재사용을
  거부한다. endpoint는 literal loopback이며 redirect를 따르지 않는다.
- B1 downstream spine은 screen → fixed AIRI event → retryable local sender 순서다.
  모델 입력은 `[YouTube] ${text}`이고 공개 displayName은 넣지 않는다.
  displayName은 별도 content-free viewer observation에만 남는다.
- 일본어·중국어와 검증되지 않은 Latin span은 `unsupported_language`로 hold한다.
  Korean 안에서 허용하는 Latin은 정책의 14개 고정 product/acronym token뿐이다.

이는 규칙 기반 프리필터다. 신조어·완곡 표현·교묘한 다국어 변형의 의미를
완전히 분류하지 못하므로 향후 실제 방송 가정 corpus/human rehearsal이 필요하다.

## fresh 증거

`airi_docs/evidence/AIRI-B3C-INPUT-SCREENING-LIVE-PROBE-2026-08-13.json`은
정책 SHA-256 `67739c9598532bbcfc44492f04d7891358d9790d68e618ba2f2ab10ea88b9d7a`를
사용한 두 번의 동일 loopback probe를 기록한다. 다섯 category는 각각 두 번
차단됐고 benign Korean YouTube envelope는 두 번 허용됐다(12 inspected,
2 allowed, 10 blocked). 당시 output moderation/extraction은 OFF, STT listener는
없었다. 설치 ASAR는 1,356,257,019 B, SHA-256
`1b68ae5ecb9db998002ac7268de707661ec0c81fc4bd90836f3c3e25719b88b0`로
변경되지 않았고 AIRI process는 7개였다.

설치 UI/TTS 재검증은 cleanup 후 sender SDK의 `@moeru/std`가 없어 연결 전에
중단됐다. model/TTS 요청은 발생하지 않았고 ASAR는 변경하지 않았다. 따라서
이 증거는 loopback 정책만 증명하며 B3-e를 닫지 않는다.

## 검증

- 독립 B3-c 최종 검토: PASS
- focused: input-only 19 PASS, chat-ingress 47 PASS, sender 32 PASS,
  combined Node 79 PASS
- Python 3.12 full: 911 passed, 1 skipped, 863 subtests, 7 warnings (53.13 s)
- `test-current-checkpoint.ps1`: PASS
- 두 launcher PowerShell parser와 diff checks: PASS

Actions는 billing 단계에서 차단되어 위 로컬 검증을 사용했다. 시험 종료 후
input screening/output moderation/extraction/STT는 모두 기본 OFF로 복원했다.

## 남은 gate

- provider-side streamList/OAuth/quota/live polling
- 설치 UI badge 및 TTS current-policy category별 반응(B3-e)
- 실제 방송 가정 자연스러움·간격·탈옥·욕설·성적·괴롭힘 human rehearsal
- 검증된 다국어 semantic classifier 또는 언어별 보수적 운영 정책
