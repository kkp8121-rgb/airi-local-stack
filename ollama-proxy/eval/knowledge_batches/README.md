# knowledge_batches — 적재용 지식 배치 (저장소 내 보관)

`knowledge_ingest.py` 로 적재할 지식 레코드 배치다. 생성 계약은
`airi_docs/진행중/AIRI-KNOWLEDGE-INGEST-CONTRACT-2026-08-27.md`.

## 왜 저장소 안인가

계약 §1 이 저장소 밖으로 밀어내는 것은 **실제 시청자 식별 정보와 대화 원문**이다. 지식 레코드는
둘 다 아니다 — 게임·밈·생활 문화에 대한 사실 서술이고, 시청자 발화도 가명도 담지 않는다.
반입 전 실측(2026-08-27, 144건 대상): 가명(`v`+8자·한글 가명) **0건**, 실제 채팅 문장(8자 이상
2,092건과 대조) 인용 **0건**, 총 368KB.

그리고 **저장소에 있어야 두 PC 가 같은 코퍼스를 쓴다.** 각자 재생성하면 지식 베이스가 갈라지고
그 위에서 잰 측정끼리 비교가 성립하지 않는다. 재생성은 토큰도 크게 쓴다.

> 초기 계약 문구는 "산출물은 전부 저장소 밖" 이었다. 평가 산출물과의 유비로 쓴 것이고, 지식
> 레코드에는 과한 조항이었다. 이 디렉터리가 그 정정이다. **채점 결과·export JSONL·SQLite 는
> 여전히 저장소 밖이다.**

## 적재

경로는 **반드시 절대경로**로, runtime 디렉터리 안에 두고 준다. `runtime_path()` 는 상대경로를
CWD 기준으로 풀기 때문에 runtime-dir 밖으로 나가면 `KnowledgeInputError` 로 거부된다.

```powershell
# 0) 사전 검증 (ingest 가 거부할 경로까지 함께 본다)
python ollama-proxy\knowledge_batch.py lint `
    --input ollama-proxy\eval\knowledge_batches\*.jsonl --runtime-dir ollama-proxy\runtime
# 1) 적재
python ollama-proxy\knowledge_ingest.py --input <절대경로>\kb-game-001.jsonl --apply
# 2) 회수율 확인 — 적재 성공과 검색 성공은 다르다
python ollama-proxy\knowledge_batch.py probe `
    --queries ollama-proxy\eval\knowledge_probe_queries.txt --min-hit-rate 0.9
```

## 현재 배치 (2026-08-27 1차)

| 파일 | 건수 | content 중앙 | 청크 |
|---|---|---|---|
| `kb-game-001.jsonl` | 41 | 742자 | 81 |
| `kb-meme-001.jsonl` | 55 | 747자 | 110 |
| `kb-culture-001.jsonl` | 48 | 768자 | 96 |

적재 결과 `documents=145, chunks=289`, 고정 질의 회수율 **6/6**(`--min-hit-rate 0.9` 통과).
적재 전 실측은 `documents=0` 이었다 — 프로젝트 내내 지식 계층이 비어 있었다.

## 배치를 추가할 때

- 파일명 `kb-<범위>-<번호>.jsonl`. 파일당 **≤1,000 레코드 AND ≤2MB**(`knowledge_ingest` 상한).
- `title` 중복은 배치 간에도 피한다 — `lint` 가 여러 파일을 한 번에 받아 잡는다.
- `aliases` 중복 판정은 **`casefold()` 기준**이다. `저스트채팅(Just Chatting)` 처럼 대소문자만
  다른 별칭이 실제로 거부됐다.
- 생성기가 아직 쓰고 있는 파일을 적재하지 않는다. 레코드 수가 같아도 본문이 덜 차 있을 수 있다
  (실측: 중앙 450자 → 747자). `lint` 가 최근 수정 시각을 경고한다.
