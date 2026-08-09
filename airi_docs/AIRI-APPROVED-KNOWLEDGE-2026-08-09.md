# AIRI 승인 일반 지식 시드 — 2026-08-09

이 문서는 `ollama-proxy/runtime/approved-knowledge-2026-08-09.json`에 포함한 공개 일반 지식의 승인 근거다. 각 레코드는 한국어 요약이며, 원문을 대체하지 않는다. `published_at`은 이 승인 요약의 발행 시각, `expires_at`은 재검토 기한이다. 원문 게시·갱신일은 원문이 명시할 때에만 별도로 신뢰한다.

## 적용 범위와 검토 원칙

- 공식 운영자 또는 공공기관의 1차 페이지를 근거로 삼았다.
- 게임·콘텐츠 서비스는 기능과 이용 시 주의만 서술했고, 패치 수치·메타·가격·지역별 제공 여부 같은 변동 정보는 고정 지식으로 넣지 않았다.
- 과학은 NASA, 식량·농식품 무역은 FAO의 설명을 요약했다. 시장 전망·가격·정책 평가는 최신 원문을 다시 확인해야 한다.
- 모든 JSON 레코드는 `approved: true`, 출처 URL, 제목, 버전, 발행·만료 시각, provenance 및 콘텐츠 SHA-256을 가진다. SHA-256은 UTF-8 콘텐츠 문자열을 대상으로 산출했다.
- `answer_summary`는 같은 승인 본문에서 추린 40~53자의 발화용 핵심 사실이다. 본문 해시와 분리해 검토하며, 검색·대화에서는 긴 본문보다 우선하되 출처 라벨 자체를 읽지는 않는다.

## 승인 출처

| 주제 | 공식 1차 출처 | 요약 근거 |
| --- | --- | --- |
| Minecraft | https://www.minecraft.net/en-us/article/what-minecraft | 샌드박스 성격과 크리에이티브·서바이벌 모드 |
| Eternal Return | https://playeternalreturn.com/main?hl=en-US | 루미아 섬, 제작·팀 생존 아레나의 공식 소개 |
| MANGA Plus | https://mangaplus.shueisha.co.jp/faq/eng/ | 집영사가 운영하는 공식 서비스, 작품·지역·화수의 제한 |
| MapleStory 게임 | https://maplestory.nexon.com/Home/Main | 넥슨 코리아의 공식 서비스 안내 |
| MapleStory 직업 | https://maplestory.nexon.com/Guide/Job | 공식 직업 안내 경로 |
| 태양계 | https://science.nasa.gov/solar-system/solar-system-facts/ | 구성과 형성에 관한 NASA 설명 |
| 은하 | https://science.nasa.gov/universe/galaxies/ | 은하의 구성·형태·우리은하에 관한 NASA 설명 |
| 농식품 시장 | https://www.fao.org/markets-and-trade/en/ | FAO의 시장 정보·조기경보·무역 분석 역할 |
| 식량안보와 무역 | https://www.fao.org/markets-and-trade/areas-of-work/trade-policy-and-partnerships/trade-food-security-and-sustainable-development/3/ | 무역의 기여와 한계, 균형 정책의 필요성 |

## 운영 메모

입력 파일은 오프라인 importer의 2 MB·1,000건 제한 아래에 유지한다. 적용 전에는 `knowledge_ingest.py`의 dry-run만 수행하며, 이 승인 묶음은 자동 수집이나 외부 연결을 수행하지 않는다.
