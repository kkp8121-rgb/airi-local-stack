# T-05 한국어 화자 후보 샘플 (2026-08-12)

## 후보와 라이선스

공식 [OpenSLR SLR40](https://www.openslr.org/40/) Zeroth-Korean 코퍼스의
서로 다른 익명 화자 3명을 사용했다. 코퍼스는 **CC BY 4.0**이며 원 출처는
Zeroth Project(Lucas Jo, Wonkyum Lee)다. 다운로드는 동일 코퍼스를
pyarrow로 재배포한 `kresnik/zeroth_korean` mirror revision
`1fe937899f828af822293d05e086200946088bdf`를 사용했다.

화자 식별을 시도하지 않았고 공개 speaker ID만 보존했다. 이 샘플은 사용자
청취 비교용이며 아직 운영 화자로 승인되지 않았다. attribution 의무와
음성 유사성 사용의 별도 인격권 리스크 때문에, 라이선스만으로 운영 승격을
자동 승인하지 않는다.

## 산출물

dev PC의 local-only `tts-samples/t05-zeroth-ko-2026-08-12/`에 speaker 105,
126, 132의 참조 WAV, 원시 합성 WAV, 청취용 WAV가 있다. WAV는 프로젝트의
`*.wav` 정책에 따라 gitignored이며 이 커밋에 포함되지 않는다. 세 참조는
16 kHz mono, 6.6~7.0초이며 정확한 전사·SHA-256·attribution은 커밋되는
`provenance.json`에 기록했다. 다른 checkout은 provenance를 사용해 승인된
원본과 동일한 로컬 합성 절차로 산출물을 다시 만들어야 한다.

동일 문장 `Hello 아이리, 음성 연결 테스트야.`를 GPT-SoVITS v2ProPlus로
합성했다. 세 원시 출력 모두 기존 self-test 음량 기준보다 작아서 청취용
파일에만 동일한 FFmpeg `loudnorm` 조건을 적용했다. 청취 파일은 32 kHz
mono, 3.08~4.12초이며 RMS 0.099~0.115다. 이는 음색 비교를 위한 후처리일
뿐 운영 readiness PASS를 의미하지 않는다.

## 판정

이 dev PC의 local-only 샘플 생성은 완료했다. 사용자가 현재 worktree의 세
`*-listen.wav`를 1회 비교해 후보를 선택해야 한다. fresh checkout에는 WAV가
없다. 모두 부적합하면 인수인계 계약대로 현재 일본어 참조 교차클로닝을
유지한다. 검증 종료 후 서비스는 기존 일본어 참조와 TTS cache 7/7 상태로
복구했다.
