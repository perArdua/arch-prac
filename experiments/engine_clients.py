"""
엔진 라운드가 쓸 얇은 클라이언트 — OpenSearch(+nori) · Postgres(+pg_bigm).

엔진마다 세 가지만 한다: 색인 만들기 / 문서 넣기 / 질의해서 `(doc_id, score)` 목록 받기.
컨테이너를 세우는 법은 `experiments/engine_infra/README.md`에 있다.

🔴 **엔진이 없으면 빈 목록을 돌려주지 않고 `EngineUnavailable`을 던진다.** 조용한 빈 결과는
   «차이 없음»으로 읽힌다 — 이 모듈이 막으려는 것이 그것이다. 호출자는 이 예외를 잡아
   `EXIT_SKIP`(77)으로 번역하고, SKIP은 통과가 아니다(G1).
🔴 **`127.0.0.1`만 쓴다.** `localhost`는 거부한다(F38: `localhost`의 느린 TCP 거절이
   «지연 FAIL»이라는 거짓 판정을 만들었다).

새 pip 의존성은 없다. OpenSearch는 표준 라이브러리 `urllib`로, Postgres는 `psycopg`가 없으므로
컨테이너 안의 `psql`을 `docker exec`로 부른다(`PG_BACKEND`). ⚠️ 이 경로는 호출마다 프로세스를
하나 띄우므로 **벽시계 지연에 그 시작 비용이 섞인다** — 지연을 잴 때는 서버 시간(`\\timing`)을
따로 읽거나 `pg_search_many`로 한 세션에 묶어라.
"""

import importlib.util
import json
import os
import subprocess
import urllib.error
import urllib.request

OS_URL = os.environ.get("MEMARCH_OS_URL", "http://127.0.0.1:19200")
PG_CONTAINER = os.environ.get("MEMARCH_PG_CONTAINER", "memarch-pg")
PG_DB, PG_USER = "memarch", "postgres"
EXIT_SKIP = 77

# `psycopg`가 깔려 있으면 쓸 수 있지만 이 저장소에는 없다 — 그래서 경로는 하나다.
PSYCOPG_INSTALLED = importlib.util.find_spec("psycopg") is not None
PG_BACKEND = "docker-exec-psql"


# 사전 등록 기반 이미지. 컨테이너 이미지는 이 위에 플러그인/확장 층을 더 쌓은 것이라
# **이미지 ID는 다르다** — 같은지는 `image_provenance`가 RootFS 층 접두사로 본다.
BASE_IMAGES = {
    "memarch-os": ("opensearchproject/opensearch@sha256:8690b204fe914c60ca76d451ac73bc04"
                    "81e034d32d3779944c8caca56a2b003f"),
    "memarch-pg": "postgres@sha256:f1c3376c26f2609ab9f29f71f824103fe2fcd8ee0346485cb6122a4f93df6f94",
}


class EngineUnavailable(RuntimeError):
    """엔진(컨테이너·플러그인·확장)이 없다. **결과가 아니다** — 호출자는 SKIP으로 번역한다."""


class EngineError(RuntimeError):
    """엔진은 떠 있는데 요청이 실패했다(SQL 오류 · bulk 오류 · 개수 불일치)."""


def _docker_json(args):
    try:
        p = subprocess.run(["docker", *args], capture_output=True, timeout=60)
    except FileNotFoundError as e:
        raise EngineUnavailable("`docker` 실행 파일이 없다") from e
    if p.returncode != 0:
        raise EngineUnavailable(p.stderr.decode("utf-8", "replace").strip()[:300])
    return json.loads(p.stdout.decode("utf-8"))


def image_provenance(container, base=None):
    """
    컨테이너 이미지가 사전 등록 기반 이미지 **위에** 쌓였는가. 이미지 ID 비교로는 못 본다
    (플러그인 층이 더해져 ID가 바뀐다) — 기반 이미지의 RootFS 층 전부가 컨테이너 이미지 층의
    **앞부분**과 같은지를 본다. 🔴 로컬의 `opensearchproject/opensearch:2.3.0`은 다른 이미지다(F21).
    """
    base = base or BASE_IMAGES[container]
    image_id = _docker_json(["inspect", "--format", "{{json .Image}}", container])
    mine = _docker_json(["image", "inspect", "--format", "{{json .RootFS.Layers}}", image_id])
    theirs = _docker_json(["image", "inspect", "--format", "{{json .RootFS.Layers}}", base])
    on_base = len(mine) >= len(theirs) and mine[:len(theirs)] == theirs
    return {"image": image_id, "base": base, "on_base": on_base,
            "extra_layers": len(mine) - len(theirs) if on_base else None}


def _check_host(url):
    if "localhost" in url.lower():
        raise ValueError(f"`localhost` 금지 — 127.0.0.1을 써라 (F38): {url}")
    return url.rstrip("/")


# ══════════════════════════════════════════════════════════════════════
# OpenSearch
# ══════════════════════════════════════════════════════════════════════

def os_request(path, body=None, method=None, url=None, timeout=30, ndjson=None):
    """JSON 요청 하나. 연결이 안 되면 `EngineUnavailable`, HTTP 오류는 그대로 올린다."""
    base = _check_host(url or OS_URL)
    if ndjson is not None:
        data, ctype = ndjson.encode("utf-8"), "application/x-ndjson"
    elif body is not None:
        data, ctype = json.dumps(body, ensure_ascii=False).encode("utf-8"), "application/json"
    else:
        data, ctype = None, "application/json"
    req = urllib.request.Request(base + path, data=data, headers={"Content-Type": ctype},
                                 method=method or ("POST" if data is not None else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError:
        raise
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
        raise EngineUnavailable(f"OpenSearch 응답 없음 ({base}): {e!r}") from e


def os_require_nori(url=None):
    """엔진 버전과 nori 플러그인 버전을 돌려준다. nori가 없으면 `EngineUnavailable`."""
    info = os_request("/", url=url)
    plugs = os_request("/_cat/plugins?format=json", url=url)
    nori = [p for p in plugs if p.get("component") == "analysis-nori"]
    if not nori:
        raise EngineUnavailable("`analysis-nori`가 없다 — nori는 기본 탑재가 아니다 "
                                "(experiments/engine_infra/Dockerfile.opensearch)")
    return {"opensearch": info["version"]["number"],
            "lucene": info["version"]["lucene_version"],
            "analysis-nori": nori[0]["version"]}


def os_analyze(text, analyzer="nori", url=None, **spec):
    """`_analyze`가 **실제로 돌려준** 토큰 목록. `spec`으로 tokenizer/filter를 직접 줄 수 있다."""
    body = dict(spec) if spec else {"analyzer": analyzer}
    body["text"] = text
    return [t["token"] for t in os_request("/_analyze", body, url=url)["tokens"]]


def os_create_index(index, analyzer_body=None, k1=1.2, b=0.75, url=None):
    """
    색인을 **지우고 새로** 만든다. 기본 분석기는 내장 `nori`(사용자 사전 없음).
    🔴 샤드 1개 — 여럿이면 IDF가 샤드마다 계산된다(선언하지 않은 요인이 하나 는다).
    """
    os_delete_index(index, url=url)
    analyzer = analyzer_body or {"type": "nori"}
    body = {
        "settings": {
            "index": {"number_of_shards": 1, "number_of_replicas": 0,
                      "similarity": {"default": {"type": "BM25", "k1": k1, "b": b}}},
            "analysis": {"analyzer": {"memarch_an": analyzer}},
        },
        "mappings": {"properties": {"body": {"type": "text", "analyzer": "memarch_an"}}},
    }
    return os_request("/" + index, body, method="PUT", url=url)


def os_delete_index(index, url=None):
    try:
        os_request("/" + index, method="DELETE", url=url)
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise


def os_index_docs(index, docs, url=None):
    """`docs`: `{doc_id: text}` 또는 `[(doc_id, text), …]`. 넣은 뒤 개수를 확인한다."""
    items = list(docs.items()) if isinstance(docs, dict) else list(docs)
    lines = []
    for doc_id, text in items:
        lines.append(json.dumps({"index": {"_id": str(doc_id)}}))
        lines.append(json.dumps({"body": text}, ensure_ascii=False))
    res = os_request("/" + index + "/_bulk", ndjson="\n".join(lines) + "\n", url=url, timeout=120)
    if res.get("errors"):
        raise EngineError(f"bulk 색인 실패: {json.dumps(res, ensure_ascii=False)[:500]}")
    os_request("/" + index + "/_refresh", method="POST", url=url)
    n = os_request("/" + index + "/_count", url=url)["count"]
    if n != len(items):
        raise EngineError(f"색인 개수가 안 맞는다: {n} vs {len(items)}")
    return n


def os_search(index, query, size=100, url=None):
    """`match` 질의 → `[(doc_id, score), …]` 점수 내림차순. 안 맞은 문서는 목록에 없다."""
    r = os_request("/" + index + "/_search",
                   {"query": {"match": {"body": query}}, "size": size, "_source": False},
                   url=url)
    return [(h["_id"], float(h["_score"])) for h in r["hits"]["hits"]]


# ══════════════════════════════════════════════════════════════════════
# Postgres (docker exec psql)
# ══════════════════════════════════════════════════════════════════════

_UNAVAILABLE_MARKS = ("No such container", "is not running", "error during connect",
                      "Cannot connect to the Docker daemon", "the database system is starting up")


def psql(sql, container=None, timeout=120):
    """
    컨테이너 안 psql에 UTF-8로 먹이고 `-A -t -F<TAB>` 행을 `[[필드, …], …]`로 돌려준다.
    컨테이너·서버가 없으면 `EngineUnavailable`, SQL 오류는 `EngineError`.
    """
    cmd = ["docker", "exec", "-i", "-e", "PGCLIENTENCODING=UTF8", container or PG_CONTAINER,
           "psql", "-X", "-q", "-U", PG_USER, "-d", PG_DB, "-v", "ON_ERROR_STOP=1",
           "-A", "-t", "-F", "\t"]
    try:
        p = subprocess.run(cmd, input=sql.encode("utf-8"), capture_output=True, timeout=timeout)
    except FileNotFoundError as e:
        raise EngineUnavailable("`docker` 실행 파일이 없다") from e
    out = p.stdout.decode("utf-8", "replace")
    err = p.stderr.decode("utf-8", "replace")
    if p.returncode != 0:
        # psql 종료 코드: 2 = 서버 연결 실패, 3 = 스크립트 오류(ON_ERROR_STOP). docker 쪽은 1·125~127.
        if p.returncode == 2 or any(m in err for m in _UNAVAILABLE_MARKS):
            raise EngineUnavailable(f"Postgres 컨테이너 «{container or PG_CONTAINER}» 없음/미기동: "
                                    f"{err.strip()[:300]}")
        raise EngineError(f"psql 실패(rc={p.returncode}): {err.strip()[:500]}")
    return [line.split("\t") for line in out.replace("\r", "").split("\n") if line != ""]


def lit(s):
    """SQL 문자열 리터럴(standard_conforming_strings=on). 작은따옴표만 이스케이프한다."""
    return "'" + str(s).replace("'", "''") + "'"


def pg_require_bigm(container=None):
    """`CREATE EXTENSION IF NOT EXISTS pg_bigm` 뒤 버전을 돌려준다. 확장이 없으면 `EngineUnavailable`."""
    avail = psql("SELECT count(*) FROM pg_available_extensions WHERE name='pg_bigm';",
                 container=container)
    if avail != [["1"]]:
        raise EngineUnavailable("`pg_bigm` 확장이 이 서버에 없다 "
                                "(experiments/engine_infra/Dockerfile.postgres)")
    rows = psql("CREATE EXTENSION IF NOT EXISTS pg_bigm;\n"
                "SELECT extversion FROM pg_extension WHERE extname='pg_bigm';\n"
                "SELECT current_setting('server_version');", container=container)
    return {"pg_bigm": rows[0][0], "postgres": rows[1][0]}


def pg_create_index(table, container=None):
    """표를 **지우고 새로** 만든다: `(id text primary key, body text)` + `gin_bigm_ops` GIN 색인."""
    pg_require_bigm(container)
    psql(f"DROP TABLE IF EXISTS {table};\n"
         f"CREATE TABLE {table} (id text PRIMARY KEY, body text NOT NULL);\n"
         f"CREATE INDEX {table}_bigm ON {table} USING gin (body gin_bigm_ops);\n",
         container=container)


def pg_index_docs(table, docs, container=None):
    """`docs`: `{doc_id: text}` 또는 `[(doc_id, text), …]`. 넣은 뒤 개수를 확인한다."""
    items = list(docs.items()) if isinstance(docs, dict) else list(docs)
    for doc_id, _ in items:
        if any(c in str(doc_id) for c in "\t\r\n"):
            raise ValueError(f"doc_id에 탭·줄바꿈 금지: {doc_id!r}")
    values = ",\n".join(f"({lit(i)}, {lit(t)})" for i, t in items)
    rows = psql(f"INSERT INTO {table} VALUES\n{values};\nANALYZE {table};\n"
                f"SELECT count(*) FROM {table};", container=container)
    n = int(rows[-1][0])
    if n != len(items):
        raise EngineError(f"색인 개수가 안 맞는다: {n} vs {len(items)}")
    return n


def _search_sql(table, query, size):
    lim = f" LIMIT {int(size)}" if size else ""
    return (f"SELECT id, bigm_similarity(body, {lit(query)}) AS s FROM {table} "
            f"WHERE bigm_similarity(body, {lit(query)}) > 0 ORDER BY s DESC, id{lim};")


def pg_search_many(table, queries, size=None, container=None):
    """
    한 psql 세션에 질의를 전부 먹인다 → `{query: [(doc_id, score), …]}`.
    점수는 `bigm_similarity(body, query)` — **BM25가 아니다**(README의 식 참고).
    """
    marks = [f"__q{i}__" for i in range(len(queries))]
    sql = "\n".join(f"SELECT {lit(m)};\n" + _search_sql(table, q, size)
                    for m, q in zip(marks, queries))
    rows = psql(sql, container=container)
    out, cur = {}, None
    for r in rows:
        if len(r) == 1 and r[0] in marks:
            cur = queries[marks.index(r[0])]
            out[cur] = []
        elif cur is not None and len(r) == 2:
            out[cur].append((r[0], float(r[1])))
        else:
            raise EngineError(f"psql 출력 형식이 안 맞는다: {r!r}")
    if len(out) != len(set(queries)):
        raise EngineError(f"응답 질의 수가 안 맞는다: {len(out)} vs {len(set(queries))}")
    return out


def pg_search(table, query, size=None, container=None):
    """`[(doc_id, score), …]` 점수 내림차순. 겹치는 bigram이 없는 문서는 목록에 없다."""
    return pg_search_many(table, [query], size=size, container=container)[query]


def pg_drop(table, container=None):
    psql(f"DROP TABLE IF EXISTS {table};", container=container)
