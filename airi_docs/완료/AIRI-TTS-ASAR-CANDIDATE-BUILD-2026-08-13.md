# AIRI TTS source ASAR candidate build — 2026-08-13

## 판정

고정 3층 source tree `bf173f2` / `ff71039c`에서 설치 후보 `app.asar`를
생성하고, SHA-256·ASAR 구조·핵심 payload·unpacked 호환성을 검증했다. 후보는
`1,131,077,260` bytes, SHA-256
`6767625E9B5C0A01625A6ADA59544480EA4FE4235AAA117A16471A1718C9BCED`이며
`ai.moeru.airi` 0.11.3, 28,167 entries다. 이 결과는 **설치 가능한 ASAR
후보의 검증 완료**이지, 설치 또는 runtime TTS 검증 완료가 아니다.

## 재현성과 호환성 근거

- layer 1/2/3의 bytes·SHA와 최종 source commit/tree를 sidecar JSON에 고정했다.
- repository full ASAR validator가 package, main, preload, renderer payload와
  bounds를 통과했다. packed main/preload/renderer index와 pages bundle은 fresh
  `out` 파일과 byte-for-byte 일치한다.
- 후보와 설치본 `app.asar.unpacked`는 각각 135 files / 240,017,777 bytes이며,
  모든 relative path·size·file SHA가 일치한다. canonical manifest SHA-256은
  양쪽 모두 `21CA46DC...14079D`다.
- 후보와 설치 `airi.exe`의 fuse 상태는 동일하고
  `EnableEmbeddedAsarIntegrityValidation`과 `OnlyLoadAppFromAsar`는 모두
  disabled다. ASAR-only 교체의 정적 호환성 근거이며 runtime 증명은 아니다.
- PCM resampler, bounded unsupported fallback, worklet ACK/write-tail 및 기존
  moderation badge marker가 후보 archive에 존재한다.

기계 판독 원본과 정규화된 경로·정확한 해시·도구 버전은
`airi_docs/evidence/AIRI-TTS-ASAR-CANDIDATE-BUILD-2026-08-13.json`에 있다
(5,774 bytes, SHA-256
`5A5960A52E1337E0F4F4EFE3C6F9C5BE5787D353B7908CE002A90552F87A3813`).

## 패키징 경계와 다음 게이트

`electron-vite` source build는 PASS했다. `electron-builder --dir`은 후보 ASAR와
integrity resource를 만든 뒤, `winCodeSign-2.6.0.7z`의 macOS dylib symlink를
Windows 권한 없이 만들지 못해 최종 실패했다. 따라서 full portable
`win-unpacked` PASS를 주장하지 않으며, 누락된 Godot `extraResources`도 portable
배포 범위에서 별도 해결해야 한다. 이 실패는 이미 생성된 ASAR의 내용 검증과는
분리했다. 정확한 console transcript는 별도 보존하지 않았으므로, terminal 결과와
생성 파일·timestamp·hash·validator를 provenance 근거로 사용한다.

현재 설치 archive는 read-only 재확인 후에도 `1,356,257,019` bytes,
SHA-256 `1B68AE5E...19B88B0`로 변하지 않았다. 설치·백업·AIRI 종료·실행은 하지
않았다. [GitHub issue #2](https://github.com/kkp8121-rgb/airi-local-stack/issues/2)에서
설치본 변경 권한이 명시적으로 주어지면, 고정 artifact/current 해시로 안전
installer를 실행하고 32 kHz fixture duration/pitch 및 text→render 회귀를 별도
증거로 남긴다. STT와 마이크는 계속 OFF/deferred다.

후속 read-only preflight는 이 sidecar와 실제 후보·설치 baseline·unpacked
트리·patch layer를 다시 묶어 검사한다. 현재 실경로 호출은 설치 AIRI 프로세스
7개를 감지해 의도대로 거부했으며 앱 종료나 설치 파일 변경은 없었다. 이는
설치 승인이나 live PASS가 아니다. 상세:
`AIRI-SOURCE-ASAR-PREFLIGHT-2026-08-13.md`.
