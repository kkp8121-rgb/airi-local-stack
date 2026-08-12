# AIRI 설치 Electron matched 모델 render A/B (2026-08-12)

## 범위와 통제 조건

동일한 설치 AIRI(`app.asar` SHA-256
`1B68AE5ECB9DB998002AC7268DE707661EC0C81FC4BD90836F3C3E25719B88B0`)와
동일 proxy 정책·GPT-SoVITS warm cache 7/7에서 `midm-airi:2.0-mini`와
`exaone-airi:2.4b`를 비교했다. 출력 모더레이션은 off였다. 고정된 합성 한국어
한 문장 요청 5개를 모델당 두 번씩 사용해 모델별 n=10을 만들었다. 블록 순서는
Mi:dm→EXAONE→Mi:dm→EXAONE이며 두 번째 블록은 prompt 순서를 뒤집었다.

각 블록 전 이전 runner를 `keep_alive=0`으로 내리고 해당 모델로 stack을
재기동했다. `/health`의 실제 chat model과 `ollama ps`의 단일 foreground
runner를 확인한 뒤 측정했다. `measure-airi-text-to-speech.ps1`의
`-Threshold 0.003`을 사용해 text send→assistant completion과 고정 ACK 뒤
첫 실질 Windows 기본 render 신호를 기록했다. STT·마이크·물리 음압은 이
측정에 포함되지 않는다. 측정 보고서에는 prompt·응답 본문, session/trace ID,
raw audio를 보존하지 않았다. 합성 턴의 정상 local journal 기록은 삭제하지
않았으므로 이 timing 보고서와 운영 journal의 수명주기는 별개다.

## 결과

| 모델·지표 | n | P50 | P95 | 평균 | 범위 |
|---|---:|---:|---:|---:|---:|
| Mi:dm completion | 10 | 655ms | 1,086.3ms | 734.0ms | 555–1,336ms |
| EXAONE completion | 10 | 732.5ms | 972.3ms | 752.7ms | 581–1,002ms |
| Mi:dm first substantive render | 10 | **1,501.5ms** | **2,597.2ms** | 1,845.6ms | 1,473–2,608ms |
| EXAONE first substantive render | 10 | 1,752.5ms | 3,233.0ms | 2,020.5ms | 1,296–3,476ms |

Mi:dm의 render P50은 EXAONE보다 251ms, P95는 635.8ms 낮았다. completion
P50도 77.5ms 낮았지만 P95는 114ms 높았다. 모델별 n=10이고 같은 prompt도
TTS·render 분산이 컸으므로 이 결과는 현 설치 구성의 지연 gate를 닫는
matched 실측이지, 일반 성능 우위나 응답 품질 우위를 증명하지 않는다.

원시 completion(ms)은 Mi:dm
`[781,774,555,623,593,1336,663,647,755,613]`, EXAONE
`[798,751,719,581,1002,936,695,667,746,632]`다. 원시 first substantive
render(ms)은 Mi:dm
`[2608,1497,1501,1502,1501,1925,2382,2584,1473,1483]`, EXAONE
`[1363,1296,1368,1861,2936,1613,2238,1644,3476,2410]`다.

## 판정과 복구

같은 설치 Electron·warm TTS에서 요구한 교차 matched text→render A/B는
완료됐다. Mi:dm 기본 후보 유지에 모순되는 지연 증거는 없지만, 인간 검수
100건과 실제 마이크 전체 체인은 별도 gate다. 측정 후 기본 Mi:dm digest
pin/verified stack으로 복구하고 EXAONE runner를 내렸다. 최종 상태는 Mi:dm
단일 foreground runner, 출력 모더레이션 기본 off, 설치 AIRI background다.
