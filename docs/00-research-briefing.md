# 리서치 브리핑 — LLM 장기기억(Long-term Memory) 도메인 지도

> 목적: 캐릭터 챗 장기기억 문제(“오래 대화해도 정확히 기억하면서 비용·지연을 최소화”)를 풀기 위한 사전 지식 정리.
> 이 문서는 **결론이 아니라 재료**입니다. 최종 산출물은 별도 ADR 세트.
> 작성 기준일: 2026-09-03

---

## 0. 30초 요약

- LLM은 **상태가 없다(stateless)**. “기억”은 모델 능력이 아니라, 매 턴 우리가 **프롬프트를 어떻게 조립하느냐**의 문제다.
- 전체 대화를 매 턴 넣으면 t번째 턴의 입력이 `O(t)`, N턴 누적 비용은 **`O(N²)`**. 수천~수만 턴에서는 산술적으로 불가능하다.
- 그래서 모든 해법은 결국 **“무엇을 버리고 무엇을 남길 것인가(write path)”** + **“지금 무엇을 꺼낼 것인가(read path)”** 두 갈래로 수렴한다.
- 업계 벤치마크상 선택적 검색 방식은 full-context 대비 **토큰 ~90%↓, p95 지연 ~91%↓**를 보고한다 ([Mem0 논문](https://arxiv.org/abs/2504.19413): 1.44s vs 17.12s, 1.8K vs 26K tokens).
- 다만 2026년 후속 연구([MemDelta](https://arxiv.org/pdf/2606.29914))는 **“정교한 메모리 시스템이 단순 baseline을 실제로는 못 이기는 경우가 많다”**고 지적한다. → **통제된 baseline 없이 낸 결론은 신뢰할 수 없다.** 이번 검토의 핵심 차별점이 여기 있다.
- 실무에서 비용을 가장 크게 좌우하는 건 알고리즘이 아니라 **프롬프트 캐시 적중률**이다. 캐시 히트는 입력가의 **0.1배**. 메모리 구조를 “캐시가 깨지지 않게” 설계하는 것이 알고리즘 개선보다 임팩트가 클 수 있다.

---

## 1. 문제를 정확히 정의하기

### 1.1 근본 제약

```
비용_턴t ≈ (입력토큰_t × 입력단가) + (출력토큰_t × 출력단가)
지연_턴t ≈ 검색지연 + 메모리조립지연 + TTFT(입력토큰_t에 비례) + 생성시간
```

전체 히스토리를 넣는 순진한 방식:

```
입력토큰_t = S + c·t        (S=시스템/페르소나, c=턴당 평균 토큰)
N턴 누적 입력토큰 = N·S + c·N(N+1)/2   →  O(N²)
```

턴당 평균 250토큰, 10,000턴 대화 하나를 끝까지 full-context로 굴리면 누적 입력만 **약 12.5억 토큰**. 어떤 단가로도 성립하지 않는다.

목표는 **입력토큰_t를 t와 무관한 상수 B로 묶는 것(bounded context)**. 즉 `O(N²) → O(N)`.
그 대가로 정보를 버려야 하고, **그 손실을 얼마나 작게 만드느냐**가 이 문제의 전부다.

### 1.2 서로 충돌하는 3축

| 축 | 개선 방향 | 다른 축에 주는 피해 |
|---|---|---|
| 기억 정확도 | 더 많이, 더 넓게 검색 | 토큰↑(비용) + TTFT↑(지연) |
| 비용 | 컨텍스트 축소, 캐시 활용 | 정확도↓ |
| 지연 | 검색/Selector 단계 축소 | 정확도↓ |

여기에 **운영 복잡도**와 **장애 지점(failure surface)** 축이 추가된다. 벡터DB, 그래프DB, 임베딩 서버, 비동기 워커가 늘어날수록 SLA가 나빠진다.

### 1.3 캐릭터 챗 도메인 특수성 (일반 챗봇과 다른 점)

이 문제를 일반적인 “agent memory” 문제로 풀면 안 된다. 캐릭터 롤플레이 챗은 성격이 다르다.

1. **정확한 사실 회상보다 “관계의 연속성”이 중요할 수 있다.** 사용자가 원하는 건 위키 검색이 아니라 “이 캐릭터가 나를 기억한다”는 감각이다.
2. **감정/사건/관계 상태**가 1급 데이터다. (호감도, 갈등, 약속, 별명, 금기)
3. **모순 처리가 치명적**이다. “너 남자친구 있다며?” 같은 stale fact 재생은 몰입을 깬다. → **knowledge update / invalidation**이 핵심 요구사항.
4. **턴이 짧고 빈도가 높다.** 턴당 20~80토큰짜리 대사가 초 단위로 오간다 → 턴당 오버헤드(추가 LLM 호출)가 매우 비싸다.
5. **무료 사용자 비중이 크다.** 턴당 원가가 곧 생존 문제. (참고: [Inworld — 컴패니언/롤플레이 앱 인프라](https://inworld.ai/resources/ai-infrastructure-for-companion-apps))
6. **체감 지연은 TTFT가 지배한다.** 스트리밍이라 첫 토큰까지가 전부.
7. **다국어(한국어)** — 임베딩 모델·토크나이저 선택이 영어 벤치마크와 다르게 움직인다.

> 이 5·6번 때문에 **“응답 경로에서 LLM 호출을 몇 번 하는가”**가 설계의 1차 변수가 된다. Selector가 별도 LLM 호출이라면 그것만으로 TTFT에 수백 ms~수 초가 붙는다.

---

## 2. 용어 지도 (이 판의 공용어)

### 2.1 메모리 종류 (인지과학에서 빌려온 분류, 거의 모든 논문이 이 틀을 씀)

| 종류 | 내용 | 캐릭터 챗 예시 |
|---|---|---|
| **Working / Short-term** | 최근 N턴 원문 | 직전 10턴 대사 |
| **Episodic** | 시점이 있는 사건 | “3주 전 사용자가 이직 실패를 말했다” |
| **Semantic** | 시점 없는 사실/프로필 | “고양이 이름은 나비”, “커피 못 마심” |
| **Procedural** | 방식/규칙/스타일 | “반말로 부른다”, “놀리면 삐진다” |
| **Persona / Core** | 캐릭터 설정 | 시스템 프롬프트 |

[ENGRAM](https://arxiv.org/abs/2511.12960)은 이 3종(episodic/semantic/procedural)만으로 단일 라우터+리트리버를 만들어 복잡한 그래프 시스템에 근접한 성능을 냈다고 보고한다. **단순한 게 강하다는 반례로 인용 가치가 높다.**

### 2.2 두 개의 경로 (설계는 항상 이 둘로 쪼갠다)

**Write path (비동기여야 함)**
```
원본 턴 → 추출(extraction) → 정규화 → 중복제거 → 모순해결(invalidation) → 저장 → (주기적) 통합/요약(consolidation) → 망각(eviction)
```

**Read path (동기, 지연 예산에 직결)**
```
쿼리 구성 → 후보 검색(retrieval) → 재정렬(rerank) → 선별(selection) → 컨텍스트 패킹(packing) → LLM 호출
```

> **Selector**는 read path의 “selection” 단계. 후보 M개 중 K개를 고르는 일. 구현 방식이 (a) 룰/스코어, (b) 크로스인코더 리랭커, (c) 작은 LLM 호출 중 무엇이냐에 따라 지연이 10ms ~ 2000ms로 100배 갈린다.

### 2.3 그 외 자주 나오는 단어

- **Bi-temporal**: 사건이 *일어난 시각*(valid time)과 *시스템에 들어온 시각*(ingestion time)을 분리 저장. 모순 해결과 “언제 그랬지?” 질문에 필수. ([Zep/Graphiti](https://arxiv.org/pdf/2501.13956)의 핵심)
- **Edge invalidation**: 새 사실이 옛 사실과 충돌하면 옛 것을 지우지 않고 `t_invalid`를 찍어 무효화. 삭제가 아니라 **버저닝**.
- **Compaction**: 컨텍스트가 한계에 근접하면 오래된 부분을 요약으로 접는 것. (Claude Code 방식)
- **Prompt caching**: 프롬프트 **접두사(prefix)**가 이전 요청과 동일하면 서버가 재사용. 접두사가 1토큰이라도 바뀌면 **전부 무효**.
- **Lost in the middle**: 긴 컨텍스트 중간에 놓인 정보를 모델이 잘 못 찾는 현상.
- **Abstention**: 근거가 없으면 “모른다”고 답하는 능력. 롤플레이에서는 **환각으로 없던 사건을 지어내지 않는 것**에 해당. LongMemEval의 5개 축 중 하나.

---

## 3. 흔히 쓰는 구조(현행 기준선) 해석 + 의심 지점

흔히 쓰는 구조: 계층적 메모리, RAG, Selector를 조합한다. 최근 대화와 장기 기억을 구분하고, 필요할 때 관련 기억을 검색·선별해 Context에 삽입한다.

추정 구조:
```
[system/persona] + [장기기억: 검색+선별된 K개] + [최근 N턴] + [현재 발화]
                          ↑
              벡터 검색 → Selector(LLM?) → 삽입
```

**이 검토에서 파고들 만한 의심 지점 (= 가설의 씨앗)**

| # | 의심 | 왜 중요한가 | 검증 방법 |
|---|---|---|---|
| H1 | 매 턴 삽입되는 장기기억이 **바뀌므로 프롬프트 캐시가 매번 깨진다** | 캐시 히트는 입력가의 0.1배. 이게 깨지면 비용이 10배 | 컨텍스트 레이아웃별 캐시 적중률/비용 실측 |
| H2 | **Selector가 응답 경로의 추가 LLM 호출**이라 TTFT를 지배한다 | 롤플레이는 TTFT가 체감 품질 | Selector 유/무, LLM Selector vs 리랭커 vs 룰 비교 |
| H3 | **매 턴 검색**하지만 실제로 장기기억이 필요한 턴은 소수다 | 불필요한 검색이 비용·지연·노이즈를 모두 유발 | “검색 필요 여부” 게이팅 도입 후 품질 델타 측정 |
| H4 | 기억을 **덮어쓰지 않고 누적**하면 모순된 사실이 함께 검색된다 | 몰입 파괴 1순위 | 모순 주입 시나리오 테스트(contradiction rate) |
| H5 | **단순 baseline(최근 N턴 + 롤링 요약)**이 이미 대부분을 커버한다 | MemDelta의 경고 | 통제된 baseline과 정면 비교 |

> **H5가 이 검토의 진짜 승부처다.** “더 복잡한 걸 만들었습니다”가 아니라 “복잡도가 실제로 값을 하는 지점은 여기까지입니다”를 데이터로 보이는 게 훨씬 강한 답변이다.

---

## 4. 대안 카탈로그 (실험 후보)

### A. Full context (상한선 baseline)
전체 히스토리를 매 턴 삽입. **품질 상한 측정용이지 후보가 아니다.**
- 반전: LongMemEval에서 **전체 히스토리를 넣으면 오히려 oracle 대비 정확도가 30~60% 하락**한다. 길수록 좋은 게 아니다. ([LongMemEval, ICLR 2025](https://arxiv.org/pdf/2410.10813))

### B. Sliding window + rolling summary (하한선 baseline) ⭐ 반드시 포함
최근 N턴 원문 + 그 앞의 모든 것을 누적 요약 1~2K토큰으로 압축.
- 장점: 구현 30줄, 외부 인프라 0, 검색 지연 0, **캐시 친화적(요약은 자주 안 바뀜)**
- 단점: 요약이 손실 압축이라 세부 사실이 사라짐, 요약의 요약으로 갈수록 열화(semantic drift)
- **이걸 이기지 못하는 대안은 채택하면 안 된다.**

### C. Vector RAG over conversation chunks
턴/세션을 청킹해 임베딩, 쿼리와 유사도 top-k 검색.
- 핵심 설계 변수(LongMemEval이 실측한 것들):
  - **granularity**: 세션 단위 vs 라운드(턴) 단위 → **라운드 단위가 고정 토큰예산에서 최대 6%p 우수**
  - **key expansion**: 원문 대신 “추출된 사실”을 임베딩 키로 사용 → +3~7%p
  - **query expansion**: 시간 표현 확장(“지난달” → 날짜 범위)
  - 이런 파이프라인 튜닝만으로 **누적 5~10%p** 회복 가능
- 단점: 벡터DB 운영, 임베딩 비용, 한국어 임베딩 품질 이슈

### D. Fact extraction + structured store (Mem0 계열)
대화에서 사실을 추출해 짧은 문장 단위로 저장, ADD/UPDATE/DELETE로 관리.
- [Mem0](https://arxiv.org/abs/2504.19413) 보고: LOCOMO에서 full-context 대비 **토큰 26K→1.8K, p95 17.12s→1.44s**, 정확도는 OpenAI 메모리 대비 +26% 상대개선
- 장점: 컨텍스트가 작고 캐시/지연에 유리, 사실 갱신이 명시적
- 단점: **추출 품질이 시스템 상한을 결정**. 추출 실패 = 영구 소실. write path에 LLM 비용 발생(단, 비동기 가능 → Batch API 50% 할인 대상)

### E. Temporal knowledge graph (Zep / Graphiti 계열)
엔티티-관계를 그래프로, 모든 엣지에 `(t_valid, t_invalid)` 유효구간 부여.
- [Zep 논문](https://arxiv.org/pdf/2501.13956): 벡터 + BM25 + 그래프 순회 하이브리드로 **sub-200ms** 검색, baseline 대비 정확도 +18.5% / 지연 -90% 주장
- 장점: 모순 해결·시간 추론이 구조적으로 해결됨 (H4에 직접 대응)
- 단점: **운영 복잡도 최상**. 그래프DB + 추출 파이프라인. 수만 유저 × 수만 턴에서 그래프 팽창 관리가 별도 문제

### F. Hierarchical summary tree (RAPTOR / MemWalker / H-MEM)
턴→세션→주차→분기 식으로 요약을 트리로 쌓고 top-down 탐색.
- [H-MEM](https://aclanthology.org/2026.eacl-long.15.pdf): Domain / Category / Memory Trace / Episode 4계층
- 장점: 다양한 시간 해상도의 질문(“요즘 어때?” vs “그때 그 얘기”)에 모두 대응
- 단점: 탐색이 다단계라 지연↑, 요약 재생성 비용, 상위 노드 갱신 전략이 까다로움

### G. Provider-native state + caching ⭐ 원래 질문이 명시적으로 언급한 축
- **[Gemini Interactions API](https://ai.google.dev/gemini-api/docs/interactions-overview)**: `previous_interaction_id`로 히스토리를 **서버가 보관**, 매 턴 새 메시지만 전송. 유료 티어 **55일 보관**(무료 1일). 암묵적 캐싱 활용도가 올라감.
  - ⚠️ **주의(중요)**: 현재 **beta**이며 공식 문서가 *프로덕션에는 `generateContent` 권장*이라고 명시. 또 **explicit caching은 Interactions API에서 미지원**. 그리고 서버가 히스토리를 “전부” 재구성하면 **`O(N²)` 문제는 그대로**다 — 전송량은 줄어도 과금 입력 토큰은 줄지 않을 수 있다. **이 지점을 실측으로 확인하는 것 자체가 좋은 실험 소재.**
- **[Context caching](https://ai.google.dev/gemini-api/docs/caching)**: Gemini 2.5+ 암묵적 캐싱 기본 활성. 최소 히트 토큰 임계(모델별 2,048~4,096). 캐시 토큰 단가는 입력의 **10%** 수준. 명시적 캐시는 **시간당 저장 요금** 발생.
- **Batch API**: 비동기 배치 처리에 **약 50% 할인**. → **write path(추출/요약/통합)를 전부 배치로 내리면 메모리 구축 비용이 반값**.
- 캐시·배치 할인은 **곱해진다**(예: batch×cache-read ≈ 정가의 5%).
- 👉 **이 축의 결론은 “어떤 API를 쓰느냐”가 아니라 “컨텍스트를 캐시가 깨지지 않는 순서로 배치하는가”다.**
  - 나쁜 배치: `[persona][매 턴 바뀌는 검색결과][최근 N턴]` → 접두사가 매번 달라져 캐시 전멸
  - 좋은 배치: `[persona][안정적 프로필/요약 = 캐시 대상][최근 N턴][이번 턴 검색결과]` → 앞부분 캐시 유지

### H. Memory-as-document (압축 문서 / 파일형) ⭐ 원래 질문이 언급한 “PDF” 아이디어의 정체
벡터DB 없이 **유저당 1개의 구조화 마크다운 문서**를 유지·갱신. Claude Code / [memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool) 계열 발상.
```
## 프로필     (거의 안 변함)   ← 캐시 친화
## 관계 상태   (천천히 변함)
## 진행 중 사건 (자주 변함)
## 최근 요약   (매 세션 변함)
```
- 장점: **인프라 0**, 검색 지연 0(문서를 통째로 넣음), 사람이 읽고 디버깅 가능, **캐시 적중률 최상**, 롤플레이의 “관계 연속성”에 개념적으로 딱 맞음
- 단점: 문서가 유계(예: 4K토큰)여야 하므로 **오래된 세부는 반드시 버려짐** → 정밀 회상 질문에 약함
- **하이브리드가 유력**: 문서(항상 삽입, 캐시됨) + 벡터검색(필요할 때만 게이팅해서 소량 추가). 이게 아마 최종 추천안의 뼈대가 될 것.

### 정성 비교표 (실측 전 가설)

| | 품질 | 기억 정확도 | 비용/턴 | TTFT | 구현 | 운영 | 수만 턴 확장성 |
|---|---|---|---|---|---|---|---|
| A Full context | 중(길면 저하) | 상 | ✗✗✗ | ✗✗✗ | ★ | ★ | ✗ 불가 |
| B Window+요약 | 중 | 하 | ★★★ | ★★★ | ★ | ★ | ○ |
| C Vector RAG | 중상 | 중상 | ★★ | ★★ | ★★ | ★★ | ○ |
| D Fact store | 중상 | 중상 | ★★★ | ★★★ | ★★ | ★★ | ◎ |
| E Temporal KG | 상 | 상 | ★★ | ★★ | ✗✗ | ✗✗ | △(그래프 팽창) |
| F 요약 트리 | 중상 | 중 | ★★ | ★ | ✗ | ✗ | ○ |
| G Provider state | ? | ? | ? | ★★ | ★★★ | ★★★ | **실측 필요** |
| H 문서형 | 중상 | 중 | ★★★ | ★★★ | ★★★ | ★★★ | ◎ |
| **D+H+C 하이브리드** | **상?** | **상?** | **★★★?** | **★★?** | ★★ | ★★ | ◎ |

---

## 5. 평가 방법론 — 여기가 이 검토의 진짜 승부처

원래 질문에 딸린 9개 물음은 결국 **평가를 어떻게 설계하느냐**로 모인다.

### 5.1 공개 벤치마크

| 벤치마크 | 규모 | 측정 축 | 한계 |
|---|---|---|---|
| [**LoCoMo**](https://arxiv.org/abs/2402.17753) ([데이터](https://github.com/snap-research/locomo)) | 10개 대화, 평균 ~600턴 / 최대 35세션 / ~16K토큰 | single-hop, multi-hop, temporal, open-domain, adversarial | **2026 기준 너무 짧다**(16K는 그냥 컨텍스트에 다 들어감) → 변별력 낮음 |
| [**LongMemEval**](https://github.com/xiaowu0162/longmemeval) ([데이터](https://huggingface.co/datasets/xiaowu0162/longmemeval)) | S: ~500문항 / 히스토리 ~115K토큰 / 40세션, M: ~500세션 | 정보추출, 다중세션추론, **시간추론**, **지식갱신**, **abstention** | 영어, 어시스턴트 톤(롤플레이 아님) |
| **BEAM** (ICLR 2026) | 100대화 / 최대 10M토큰 / 2,000문항 | 10개 능력(모순 해결 포함) | 최신이라 도구 지원 적음 |

⚠️ 원본 longmemeval은 deprecated, `longmemeval-cleaned` 사용 권장.

### 5.2 그러나 — 자체 데이터셋이 필요하다

캐릭터 챗은 **한국어 + 롤플레이 + 감정/관계** 도메인이다. 위 벤치마크는 전부 영어 어시스턴트 대화다. 그대로 쓴 결론은 설득력이 약하다.

**권장 접근 (하이브리드):**
1. **LongMemEval-S 서브셋**으로 방법론 신뢰성 확보 (재현 가능, 남들과 비교 가능)
2. **자체 한국어 롤플레이 더미 대화** 생성 (예: 1개 캐릭터 × 2,000턴 × 시나리오 30세션)
   - 생성 시 **정답 근거(ground truth)를 함께 심어둔다**: “12세션에서 사용자가 고양이 이름을 나비라고 말함” → 이후 “내 고양이 이름 뭐였지?” 질문
   - **모순 주입**: 30세션에서 “나비가 무지개다리를 건넜다” → 이후 시스템이 옛 사실을 재생하는지 측정
3. 평가 질문 세트를 **유형별로 균등 배치** (아래 5.3)

### 5.3 측정 지표 (반드시 이 5개 축 전부)

**① 응답 품질**
- LLM-as-judge (기준: 캐릭터 일관성, 자연스러움, 맥락 적합성) — 5점 척도, 심판 모델 고정, 순서 편향 방지 위해 A/B 위치 무작위화

**② 기억 정확도** (유형별 분해가 핵심)

| 유형 | 예시 질문 | 지표 |
|---|---|---|
| Single-hop 회상 | “내 고양이 이름 뭐였지?” | Accuracy |
| Multi-session 추론 | “내가 이직 준비 시작한 뒤로 몇 번 면접 봤지?” | Accuracy |
| Temporal | “우리 처음 만난 게 언제였지?” | Accuracy |
| **Knowledge update** | 옛 사실이 갱신된 뒤 재질문 | **Stale-fact rate (낮을수록 좋음)** |
| **Abstention** | 없던 사건 질문 | **Hallucination rate** |

> ④ Knowledge update와 ⑤ Abstention이 롤플레이에서 가장 중요한데 대부분의 비교글이 빼먹는다. **여기를 측정하면 차별화된다.**

**③ 비용** — 단순 “토큰 수”가 아니라 아래로 분해
```
턴당비용 = 입력_비캐시×단가_in + 입력_캐시히트×단가_in×0.1 + 출력×단가_out
         + (write path 비용 ÷ 상각 턴수)     ← 배치 할인 반영
         + 임베딩 비용 + 인프라 고정비(벡터/그래프DB) ÷ 턴수
```
→ **캐시 적중률을 반드시 함께 리포트.** 이게 없으면 비용 비교가 무의미하다.

**④ Latency** — p50 / p95 / **p99**, 그리고 **TTFT를 별도로**
```
TTFT = 게이팅판단 + 검색 + 리랭크/Selector + 패킹 + 모델 first-token
```
각 단계를 계측(instrumentation)해서 **스택 차트로** 보여주면 설득력이 크다.

**⑤ 구현/운영 복잡도** — 정성 평가지만 근거를 붙인다
- 새로 추가되는 인프라 수, 장애 지점 수
- write path 실패 시 degradation 양상 (조용히 기억을 잃는가?)
- 재구축(reindex/rebuild) 비용, 스키마 마이그레이션 난이도
- 디버깅 가능성 (“왜 이걸 기억 못 했나”를 추적할 수 있는가)

### 5.4 실험 통제 — MemDelta의 경고를 반영

[MemDelta](https://arxiv.org/pdf/2606.29914)는 기존 메모리 벤치마크가 **컨텍스트 길이, 검색 효율, 난이도 등을 통제하지 않아** 메모리 시스템의 성능을 부풀렸다고 지적한다. 통제 baseline(recency window, plain RAG)을 제대로 두면 **정교한 시스템이 단순 방식을 유의미하게 이기지 못하는 경우가 많다**는 것.

또한 벤치마크 점수 자체의 신뢰 문제도 있다 — Mem0는 Mem0의 점수를, Zep은 Zep 논문의 점수를 발표했고, Zep 팀은 Mem0 논문이 자사 시스템을 잘못 설정했다며 반박(LOCOMO 75.14%)했다. **자가 보고 점수를 그대로 인용하면 안 된다.**

**→ 이번 검토에서 지킬 규칙:**
1. **모든 방식에 동일한 토큰 예산**을 준다 (예: 컨텍스트 4K 고정). 예산이 다르면 비교가 아니다.
2. **동일 생성 모델·동일 온도·동일 시드**.
3. **통제 baseline 필수**: (a) 최근 N턴만, (b) 랜덤 K개 검색, (c) oracle 검색(상한선).
   - **랜덤 baseline**을 못 이기면 검색이 작동하지 않는 것이다.
   - **oracle**과의 격차가 개선 여지의 크기다.
4. **동일 평가 질문 세트**, 동일 심판 모델.
5. 반복 3회 이상, 분산 보고.

---

## 6. 아직 확인이 필요한 사실들 (⚠️ 실측/공식 문서 확인 대상)

| 항목 | 현재 정보 출처 | 상태 |
|---|---|---|
| Gemini 3.x 단가(입력/출력/캐시/캐시저장) | 가격 비교 블로그 | ⚠️ **공식 pricing 페이지로 재확인 필요** |
| Interactions API 사용 시 **과금 입력 토큰이 실제로 줄어드는지** | 문서에 명시 없음 | ⚠️ **직접 실측해야 함 — 이 검토의 핵심 실험 중 하나** |
| Interactions API 캐시 적중률 | “implicit caching 활용도 향상” 수준의 서술만 | ⚠️ `usage.total_cached_tokens` 필드로 실측 |
| Batch API가 write path에 실제 적용 가능한지 (지연 허용치) | 일반론 | ⚠️ 검증 |
| 한국어 임베딩 모델 성능 | 미조사 | ⚠️ **추가 리서치 필요** |

---

## 7. ADR 문서 구조 제안

“ADR = 짧아야 한다”가 원칙이다. 4,000단어짜리는 ADR이 아니라 설계문서다. 그래서 **1개의 거대 ADR이 아니라, 결정 단위로 쪼갠 ADR 세트 + 이를 묶는 실험 리포트** 구성을 제안한다.

```
docs/
├── 00-research-briefing.md      ← 이 문서 (배경지식)
├── 01-problem-and-hypotheses.md ← 문제정의 + 가설 H1~H5 + 실험설계
├── adr/
│   ├── ADR-000-template.md
│   ├── ADR-001-메모리-저장-형태.md          (문서형 vs 사실DB vs 그래프)
│   ├── ADR-002-무엇을-기억하고-버릴것인가.md  (write path / 압축·망각 정책)
│   ├── ADR-003-검색과-선별-전략.md          (RAG 게이팅, granularity, Selector 구현)
│   ├── ADR-004-컨텍스트-패킹과-캐시전략.md   (프롬프트 레이아웃 = 비용 결정)
│   ├── ADR-005-Provider-네이티브-상태-사용여부.md (Interactions API / Batch / 캐싱)
│   └── ADR-006-평가-하네스.md               (데이터셋·지표·통제)
├── 02-experiments.md            ← 실험 결과 (표 + 그래프)
└── 03-final-recommendation.md   ← "내가 처음부터 다시 설계한다면" 최종 결론
```

**각 ADR 본문(MADR 축약형):**
```markdown
# ADR-00X: <결정 제목>
- 상태: 제안됨 / 채택됨 / 폐기됨
- 일자: 2026-09-XX
- 관련: ADR-00Y

## 맥락 (Context)
무슨 문제이고 왜 지금 결정해야 하는가. 제약조건.

## 결정 동인 (Decision Drivers)
- 기억 정확도 / 비용 / TTFT / 운영 복잡도 / 확장성 (우선순위 명시)

## 고려한 선택지 (Considered Options)
1. ... 2. ... 3. ...

## 결정 (Decision)
"우리는 X를 선택한다. 왜냐하면 ..."

## 근거 — 실험 데이터
| 옵션 | 정확도 | Stale rate | 비용/턴 | TTFT p95 | 복잡도 |
(← 반드시 숫자를 붙인다. 이게 이 검토의 핵심)

## 결과 (Consequences)
- 좋아지는 것 / 나빠지는 것 / 감수하는 리스크
- 이 결정을 뒤집어야 할 신호(trigger)는 무엇인가
```

> 마지막 “뒤집어야 할 신호” 항목을 넣으면 **운영 관점을 아는 사람**으로 보인다. 예: “유저당 평균 턴이 5,000을 넘으면 ADR-001을 재검토한다.”

---

## 8. 첫 실행 계획 (제안)

| 일자 | 할 일 | 산출물 |
|---|---|---|
| **1일차** | 리서치 마감, 문제정의·가설 확정, 평가 하네스 스펙 확정, 더미 데이터 생성 | `01-problem-and-hypotheses.md`, 한국어 롤플레이 대화 2,000턴 + 질문 60문항(5유형 균등) |
| **2일차** | 하네스 구현 + baseline 3종(Full / Window+요약 / 랜덤) 측정 | 실행 가능한 실험 코드, baseline 수치 |
| **3일차** | 대안 구현·측정: Vector RAG(라운드 단위+키확장), 사실추출 저장소, 문서형, 하이브리드 | 대안 수치 |
| **4일차** | 캐시/비용 실험(패킹 레이아웃 A/B), Interactions API 실측, 결과 정리 | `02-experiments.md`, 그래프 |
| **5일차** | ADR 6편 작성 + 최종 추천 + 요약 1페이지 | 최종 문서 |

**스코프 방어선(중요):** 시간이 부족하면 아래 순서로 버린다.
1. Temporal KG(E) 구현 — 개념 비교만 하고 “왜 지금은 아닌가”로 처리
2. 요약 트리(F) 구현
3. BEAM 벤치마크
절대 버리면 안 되는 것: **통제 baseline, 5개 축 측정, 캐시/비용 분석.**

---

## 9. 예상 최종 결론의 형태 (가설 — 실험으로 뒤집힐 수 있음)

> **“유저당 유계 프로필 문서(항상 삽입, 캐시 고정) + 비동기 사실 추출 저장소 + 게이팅된 이벤트 검색”의 3층 구조.**
> 그래프DB도, 응답 경로의 LLM Selector도 두지 않는다.
> 이유: (1) 컨텍스트 접두사를 안정화해 캐시 적중률을 최대화하면 비용이 알고리즘 개선보다 크게 떨어지고, (2) 롤플레이에서 필요한 회상의 대부분은 유계 문서로 커버되며, (3) 정밀 회상이 필요한 소수 턴에만 검색을 켜면 평균 TTFT를 지킬 수 있기 때문.
> 무거운 write path(추출·통합)는 전부 비동기 배치로 내려 원가를 반으로 줄인다.

이 가설이 **틀리는 것도 좋은 결과**다. 중요한 건 숫자로 확인하는 과정.

---

## 10. 참고 자료

**벤치마크 / 데이터셋**
- [LoCoMo: Evaluating Very Long-Term Conversational Memory of LLM Agents (arXiv:2402.17753)](https://arxiv.org/abs/2402.17753) · [데이터](https://github.com/snap-research/locomo)
- [LongMemEval (ICLR 2025, arXiv:2410.10813)](https://arxiv.org/pdf/2410.10813) · [코드](https://github.com/xiaowu0162/longmemeval) · [데이터](https://huggingface.co/datasets/xiaowu0162/longmemeval)
- [AI Memory Benchmarks 2026: LoCoMo, LongMemEval & BEAM (Mem0)](https://mem0.ai/blog/ai-memory-benchmarks-in-2026)
- [MemDelta: Controlled Baselines and Hidden Confounds in Agent Memory Evaluation](https://arxiv.org/pdf/2606.29914) ⭐ 비판적 시각

**메모리 시스템**
- [Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory (arXiv:2504.19413)](https://arxiv.org/abs/2504.19413)
- [Zep: A Temporal Knowledge Graph Architecture for Agent Memory (arXiv:2501.13956)](https://arxiv.org/pdf/2501.13956) · [Graphiti 소개](https://neo4j.com/blog/developer/graphiti-knowledge-graph-memory/)
- [ENGRAM: Effective, Lightweight Memory Orchestration for Conversational Agents (arXiv:2511.12960)](https://arxiv.org/abs/2511.12960) ⭐ 단순함의 반례
- [H-MEM: Hierarchical Memory (EACL 2026)](https://aclanthology.org/2026.eacl-long.15.pdf)
- [Less Context, More Accuracy: A Bi-Temporal Memory Engine (arXiv:2606.09900)](https://arxiv.org/pdf/2606.09900)
- [Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging Frontiers (서베이)](https://arxiv.org/html/2603.07670v1)
- [Memory in the LLM Era: Modular Architectures and Strategies (서베이/벤치마크)](https://arxiv.org/html/2604.01707v1)
- [AI Agent Memory 2026 — Mem0/Zep/Graphiti/Letta/LangMem 비교](https://medium.com/@wasowski.jarek/i-compared-5-ai-agent-memory-systems-across-6-dimensions-none-wins-6a658335ed0a)

**API / 비용**
- [Gemini Interactions API 개요](https://ai.google.dev/gemini-api/docs/interactions-overview) · [원문 md](https://ai.google.dev/gemini-api/docs/interactions.md.txt)
- [Gemini Context caching](https://ai.google.dev/gemini-api/docs/caching)
- [Prompt Caching in 2026: OpenAI vs Claude vs Gemini](https://leanlm.ai/blog/prompt-caching) ⚠️ 2차 출처, 재확인 필요
- [Claude Memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool) · [Context engineering: memory, compaction, tool clearing](https://platform.claude.com/cookbook/tool-use-context-engineering-context-engineering-tools)

**도메인**
- [AI Infrastructure for Companion and Roleplay Apps in 2026 (Inworld)](https://inworld.ai/resources/ai-infrastructure-for-companion-apps)


**ADR**
- [MADR](https://adr.github.io/madr/) · [ADR 템플릿 모음](https://adr.github.io/adr-templates/) · [MADR 템플릿 해설](https://www.ozimmer.ch/practices/2022/11/22/MADRTemplatePrimer.html)
