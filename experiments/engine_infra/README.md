# 엔진 라운드 인프라 — OpenSearch + nori · Postgres + pg_bigm

다음 파도(엔진 라운드)가 현행 검색(문자 bigram 덮기율)을 두 엔진과 요인별로 대조한다.
이 폴더는 그 두 엔진을 **다시 세우는 법**과 **실제로 한국어를 그렇게 처리하는지 보이는 검증기**를 둔다.
클라이언트는 `experiments/engine_clients.py`, 그 시험은 `experiments/tests/test_engine_clients.py`.

🔴 **`127.0.0.1`만 쓴다 — `localhost` 금지**(F38). 포트도 `127.0.0.1`에만 묶는다.
🔴 **기반 이미지는 다이제스트로만**(G11). 로컬의 `opensearchproject/opensearch:2.3.0`은 다른 이미지다(F21).

| | 파일 | 기반(다이제스트) | 더하는 것 |
|---|---|---|---|
| OpenSearch 2.19.6 · Lucene 9.12.3 | `Dockerfile.opensearch` | `opensearchproject/opensearch@sha256:8690b204…2b003f` | `analysis-nori 2.19.6` (공식 아티팩트) |
| Postgres 16.15 · Debian 13 | `Dockerfile.postgres` | `postgres@sha256:f1c3376c…df6f94` | `pg_bigm 1.2` (공식 저장소 태그 `v1.2-20250903` 소스 빌드) |

## 세우기 (저장소 루트에서)

```bash
# 1. 빌드 — 기반 이미지는 로컬에 있으면 다시 받지 않는다
docker build -f experiments/engine_infra/Dockerfile.opensearch -t memarch/opensearch-nori:2.19.6 experiments/engine_infra
docker build -f experiments/engine_infra/Dockerfile.postgres   -t memarch/postgres-bigm:16      experiments/engine_infra

# 2. 기동 — 포트는 127.0.0.1에만
docker run -d --name memarch-os -p 127.0.0.1:19200:9200 \
  -e discovery.type=single-node -e DISABLE_SECURITY_PLUGIN=true \
  -e DISABLE_INSTALL_DEMO_CONFIG=true -e OPENSEARCH_JAVA_OPTS="-Xms1g -Xmx1g" \
  memarch/opensearch-nori:2.19.6
docker run -d --name memarch-pg -p 127.0.0.1:15433:5432 \
  -e POSTGRES_PASSWORD=memarch -e POSTGRES_DB=memarch \
  memarch/postgres-bigm:16

# 3. 기다리기 (OpenSearch ≈12 s)
until curl -s -m 3 http://127.0.0.1:19200/_cluster/health | grep -qE '"status":"(green|yellow)"'; do sleep 3; done
until docker exec memarch-pg psql -U postgres -d memarch -Atc "select 1" >/dev/null 2>&1; do sleep 2; done

# 4. 검증 — 종료 코드 0 = 사전 등록 조건 전부 참 · 1 = 🔴 FAIL · 77 = 엔진 없음(SKIP, 통과 아님)
PYTHONIOENCODING=utf-8 python -B experiments/engine_infra/verify_engines.py
PYTHONIOENCODING=utf-8 python -B -m unittest discover -s experiments/tests -p "test_engine_clients.py" -v

# 멈춤/재개 (설정은 컨테이너에 남는다)
docker stop memarch-os memarch-pg
docker start memarch-os memarch-pg

# 정리 (이미지까지)
docker rm -f memarch-os memarch-pg
docker rmi memarch/opensearch-nori:2.19.6 memarch/postgres-bigm:16
```

⚠️ Windows Git Bash에서 `docker exec … /usr/...` 경로를 손으로 칠 때는 `MSYS_NO_PATHCONV=1`을 붙여라
(안 붙이면 `/usr/share/...`가 `C:/Program Files/Git/usr/share/...`로 바뀐다). 파이썬 클라이언트는 영향 없다.

## 2026-09-11에 세운 것

| 컨테이너 | 이미지 | 이미지 ID | 포트 |
|---|---|---|---|
| `memarch-os` | `memarch/opensearch-nori:2.19.6` | `sha256:6567c959be77192a541c4efb2ea5dad8a372415ccd3b13b3b17ef69279e42cd5` | `127.0.0.1:19200→9200` |
| `memarch-pg` | `memarch/postgres-bigm:16` | `sha256:30a75c69685e43ce04db5148768ea63e310c0a3cc7a807fac5d712a0f5609108` | `127.0.0.1:15433→5432` |

두 이미지 모두 **기반 이미지의 RootFS 층 전부 + 층 하나**다(`engine_clients.image_provenance`가 확인한다).
🔴 **그래서 이미지 ID는 기반 다이제스트와 다르다.** 이미지 ID를 기반 다이제스트와 곧바로 비교하는 검사
(`experiments/engine_arms.py`의 `probe_containers`)는 이 컨테이너를 «불일치»로 읽는다 — 층 접두사로 봐야 한다.

## pg_bigm 설치 경로 — 시도한 것

1. 이미지 안 `apt-get update && apt-cache search bigm` → `golang-filippo-bigmod-dev`·`r-cran-bigmemory`·
   `r-cran-bigmemory.sri`뿐. **PGDG(trixie-pgdg)에 pg_bigm 패키지가 없다.** (`apt-cache policy postgresql-16-pg-bigm`도 빈 결과.)
2. 공식 저장소 릴리스 확인 → 최신 `v1.2-20250903`(2025-09-02). RPM(el8/el9)만 있고 deb는 없다.
3. 태그 소스 타르볼(36,292 바이트, sha256 `4d4fb481…77b3142`) + `postgresql-server-dev-16`
   (`16.15-1.pgdg13+2`, 이미지와 같은 판) + `build-essential`로 빌드 → **첫 시도 실패**:
   `pg_locale.h:24: fatal error: unicode/ucol.h: No such file or directory` (`--no-install-recommends`라 ICU 헤더가 빠짐).
4. `libicu-dev` 추가 → 빌드 성공(경고 0). 다단 빌드라 최종 이미지에는 `.so`·`.control`·`.sql`만 들어간다.

## `bigm_similarity`의 식 — BM25가 아니다

pg_bigm `v1.2-20250903`의 `bigm_op.c` `cnt_sml_bigm()`:

```c
#ifdef DIVUNION
	return ((float4) count) / ((float4) (len1 + len2 - count));
#else
	return ((float4) count) / ((float4) ((len1 > len2) ? len1 : len2));
#endif
```

`DIVUNION`은 이 판의 `Makefile`·`bigm.h` 어디에도 정의돼 있지 않다 → **`|A∩B| / max(|A|,|B|)`**.
`A`·`B`는 **중복을 없앤** bigram 집합(`generate_bigm`이 정렬 뒤 `unique_array`)이고, 어절마다 앞뒤에 공백 하나를
붙여 자른다(`LPADDING`·`RPADDING` = 1). bigram은 바이트 그대로 저장된다(`char str[8]` — 해시 아님, 충돌 없음).
검증기가 이 식을 실측으로도 확인한다(T2b: 아홉 쌍 모두 `∩/max`와 일치, 자카드와는 갈림).
대조: `pg_trgm.similarity`는 **자카드**(∩/∪)이고 다바이트 trigram을 해시한다(`show_trgm('나비가')` → `0xdf06e4,…`).

## nori 기본값 — jar에서 읽었다

| 항목 | 값 | 어디서 |
|---|---|---|
| `decompound_mode` 기본 | `DISCARD` | `KoreanTokenizer.DEFAULT_DECOMPOUND` (javap) · OpenSearch `NoriTokenizerFactory`가 이 값을 기본으로 쓴다 |
| 품사 필터 기본(18종) | `E IC J MAG MAJ MM SP SSC SSO SC SE XPN XSA XSN XSV UNA NA VSV` | `KoreanPartOfSpeechStopFilter.DEFAULT_STOP_TAGS` (javap) |
| `discard_punctuation` 기본 | `true` | `NoriTokenizerFactory` (javap) |
| 내장 `nori` 분석기 | 토크나이저 → 품사 필터 → `KoreanReadingFormFilter` → `LowerCaseFilter` | `KoreanAnalyzer.createComponents` (javap) |
| 사용자 사전 | **없음** — 넣지 않았다 | 캐릭터 이름을 넣으면 답을 넣는 것이다 |

사용자 사전을 넣은 설정이 필요하면 **다른 이름의 색인 설정**으로 만들어라(`os_create_index(index, analyzer_body=…)`).

## 내려받은 것

| 무엇 | 어디서 | 크기 | 최종 이미지에 |
|---|---|---|---|
| `analysis-nori-2.19.6.zip` | `artifacts.opensearch.org/releases/plugins/analysis-nori/2.19.6/` | 7,759,782 B (sha512 `4946e5d1…ce54497`) | 들어감 |
| pg_bigm 소스 `v1.2-20250903.tar.gz` | `github.com/pgbigm/pg_bigm` (태그 아카이브) | 36,292 B | 빌드 산출물만 |
| apt 색인(Debian trixie · trixie-pgdg) | `deb.debian.org` · `apt.postgresql.org` | 11.3 MB × 3회 | 아니오 |
| 빌드 도구 패키지(`build-essential`·`postgresql-server-dev-16`·`libicu-dev`·`curl` 등) | 같은 두 곳 | 177 MB(1차, 실패) + 188 MB(2차) | 아니오(다단 빌드) |

기반 이미지 둘은 이미 로컬에 있어 받지 않았다. 코퍼스는 **로컬 컨테이너에만** 넣는다.
