# AIRI B0 자원 실측 (2026-08-12)

## 범위와 방법

dev PC(Ryzen 5 5600X, RTX 3060 Ti 8GB)에서 기본 Mi:dm·CUDA STT·
GPT-SoVITS·설치 AIRI를 유지했다. 각 구간은 `nvidia-smi`와 WMI CPU
LoadPercentage를 20회(약 40초) 수집했다. OBS 프로필은 측정 전후 SHA-256
`C8964C280074066F39FFCB36D562C6F3B6DD7EC2C0192F139A1A53E42661C3AE`로
동일함을 확인했다.

## B0-2 VRAM 3단계

| 단계 | VRAM 평균/최대 | 최소 여유 | GPU 평균 | 인코더 평균 |
|---|---:|---:|---:|---:|
| 스택 + 설치 AIRI | 6,084 / 6,084 MiB | 1,941 MiB | 22.2% | 0% |
| + OBS 미리보기 | 6,131 / 6,131 MiB | 1,894 MiB | 28.9% | 0% |
| + NVENC 녹화 | 6,289 / 6,289 MiB | 1,736 MiB | 25.2% | 73.4% |

OBS 미리보기 증분은 **+47MiB**, NVENC 증분은 **+158MiB**, 전체 증분은
**+205MiB**였다. NVENC는 H.264 1920×1080/60fps, CQP 23, p5,
look-ahead 8로 실제 동작했고 169.73초 MP4(10,186 프레임)를 정상 종료했다.
따라서 현 구성의 NVENC 자원 게이트는 PASS다. YouTube 네트워크 송출 자체는
B0-1/OAuth와 별도다.

## B0-3 x264 폴백

x264 `veryfast`, CRF 23, 1920×1080/30fps 녹화 중 설치 AIRI를 전면에 두고
실제 Electron→Mi:dm→TTS 턴을 발생시켰다. 20개 표본의 CPU는 평균
**44.8%**, 최대 **70%**로 최소 **30% headroom**을 남겼다. VRAM은 평균
6,041.8MiB, 최대 6,141MiB였고 Electron 턴은 2,982ms에 완료됐다.

OBS는 5,346프레임을 출력한 178.13초 H.264 MP4를 정상 마감했다. x264
encode 시간은 median 0.975ms, max 2.216ms로 33.3ms 프레임 예산보다
충분히 작았고 encoding-lag 경고가 없었다. 따라서 5600X의 1080p30 x264
폴백 자원 게이트도 PASS다. 이 결과는 로컬 녹화 부하 판정이며 비공개
YouTube 리허설의 채팅·네트워크·killswitch 검증을 대신하지 않는다.
