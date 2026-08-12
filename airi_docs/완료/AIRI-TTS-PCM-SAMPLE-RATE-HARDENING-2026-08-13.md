# AIRI TTS PCM sample-rate hardening — 2026-08-13

## 판정

GPT-SoVITS의 progressive WAV 재생은 이미 동작했지만, 32 kHz source PCM을
Web Audio의 일반적인 48 kHz 출력에 1:1로 공급해 재생 속도와 pitch가 변할 수
있었다. 지원되는 AIRI 3층 source patch에 chunk-safe resampler를 추가해 source
rate를 실제 `AudioContext.sampleRate`로 변환한다. 이 배치는 **source 구현·빌드
검증 완료**이며 설치 AIRI는 교체하지 않았다.

## 구현 계약

- mono/stereo frame 경계와 보간 phase를 임의 network chunk 사이에서 보존한다.
- 동일 sample rate는 sample-exact identity 경로를 쓴다.
- AudioWorklet 큐는 bounded 상태를 유지하되, 큰 chunk를 분할하고 공간을
  비동기로 기다려 PCM을 버리지 않는다. abort는 대기자를 해제한다.
- node 연결은 pre-roll 충족 뒤 수행하고, 짧은 응답은 terminal flush에서 한 번
  시작한다.
- streaming WAV로 판정한 뒤에는 전체 HTTP body를 보관하지 않는다. 판정 전
  prefix만 512 KiB로 제한하며 unsupported 응답의 full-buffer fallback은 한 번만
  수행한다.

## 고정 산출물과 검증

- layer-3 patch: `130,974` bytes
- SHA-256: `CC172A16281E56DC03E6A6F261B5531367711C0393D57E171C932EA8544C5E3E`
- verified source commit/tree: `bf173f2de870e3f779db02548d691c7b51bb290f` /
  `ff71039caa507c5676c2cee31125374c5cc37d35`
- focused Stage UI: 6 files, 28 tests PASS
- Stage UI·Stage Tamagotchi typecheck PASS
- Stage Tamagotchi `electron-vite` production build PASS (outer
  `electron-builder` packaging은 이 source 구현 배치의 PASS 주장에 포함하지 않음)
- clean `dbf8124` base에서 layer 1→2→3 apply/reverse PASS, 최종 tree 재계산 일치
- patch manifest와 checkpoint contract PASS

## 운영 경계

현재 설치 `app.asar` SHA-256
`1B68AE5ECB9DB998002AC7268DE707661EC0C81FC4BD90836F3C3E25719B88B0`는
변경하지 않았다. 후속 배치에서 이 source tree의 ASAR 후보를 생성·정적 검증했지만
설치본의 sample-rate 보정, 실제 음성 duration/pitch, text→render 지연은 아직
증명되지 않았다. 상세 후보 provenance는
`AIRI-TTS-ASAR-CANDIDATE-BUILD-2026-08-13.md`에 있다. 다음 운영 단계는 명시적
설치 권한 뒤 AIRI를 정지하고 안전 백업·교체한 다음 32 kHz fixture duration과
text-only 실기 회귀를 확인하는 것이다. STT·마이크·참조 음성 선택은 이 배치
범위가 아니다.
