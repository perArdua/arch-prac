"""
두 엔진이 **실제로 한국어를 그렇게 처리하는가**를 출력으로 보이고, 사전 등록한 조건으로 판정한다.

    PYTHONIOENCODING=utf-8 python -B experiments/engine_infra/verify_engines.py [--os-only|--pg-only]

종료 코드: 0 = 조건 전부 참 · 1 = 하나라도 거짓(🔴 FAIL) · 77 = 엔진이 없다(SKIP — 통과가 아니다, G1).
대상은 `MEMARCH_OS_URL` · `MEMARCH_OS_CONTAINER` · `MEMARCH_PG_CONTAINER`로 바꿀 수 있다
(순정 이미지에 대고 돌려 🔴 FAIL이 나는지 보는 것이 이 검증기의 심은 위반 시험이다 — README).

사전 등록 (값 보기 전에 적었다):
  T1 참 ⇔ `_cat/plugins`에 analysis-nori가 있고 그 버전이 `GET /`의 엔진 버전과 같으며,
          내장 `nori` 분석기가 `나비가`·`나비를`·`나비는` 셋 모두에서 정확히 `['나비']`를 낸다.
  T2 참 ⇔ `CREATE EXTENSION pg_bigm`이 성공하고, `show_bigm('나비가')`에 `나비`가 있고,
          `bigm_similarity('보류됐습니다','보류')`가 (0, 1] 안의 수이고, `gin_bigm_ops` GIN 색인이 만들어진다.
  보조(설정이 조용히 무시되지 않았는가 · 식이 무엇인가):
     T1b decompound_mode 셋이 합성어 대조 입력에서 서로 다른 출력을 적어도 둘 낸다.
     T1c 내장 `nori` == 읽어 낸 기본값으로 손수 조립한 사슬 (모든 입력에서).
     T2b `bigm_similarity` == |A∩B| / max(|A|,|B|) (A·B = `show_bigm` 집합) 모든 쌍에서, 그리고
         자카드 |A∩B| / |A∪B|와는 적어도 한 쌍에서 다르다(두 식을 가를 수 있는 입력이다).
"""

import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))                       # experiments/
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "prototype"))

import engine_clients as E                                        # noqa: E402

OS_CONTAINER = os.environ.get("MEMARCH_OS_CONTAINER", "memarch-os")

# 이 저장소가 실제로 깨졌던 자리.
INPUTS = ["나비가", "나비를", "나비는", "보류됐습니다", "보류",
          "사내 교육 정원은 40명입니다", "사내 교육 정원이 몇 명이었죠",
          "친구랑", "PR #391", "v2.4", "AWS"]
# decompound_mode가 실제로 먹는지 보는 대조 입력(Lucene nori 문서의 예). 캐릭터 이름이 아니다.
COMPOUND_CONTROL = "가거도항"
DECOMPOUND_MODES = ("none", "discard", "mixed")

PG_PAIRS = [("보류됐습니다", "보류"), ("나비가", "나비"), ("나비가", "나비를"),
            ("사내 교육 정원은 40명입니다", "사내 교육 정원이 몇 명이었죠"),
            ("친구랑", "친구"), ("AWS", "aws"),
            # pg_bigm 문서(docs/pg_bigm_en.md)의 예 — 값이 0.25 · 0 · 0.571429로 적혀 있다.
            ("ABC", "A"), ("ABC", "B"), ("full text search", "text similarity search")]

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"  {'✅ PASS' if ok else '🔴 FAIL'}  {name}" + (f" — {detail}" if detail else ""))


def hr(t):
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)


def current_tokenizers(t):
    """현행 분석기가 같은 입력에 내는 것 — `prototype/memory.py`를 **import만** 한다."""
    import memory as M
    return {"bigrams": M.bigrams(t), "tokens_fixed": M.tokens_fixed(t),
            "_stem(어절)": [M._stem(re.sub(r"[^\w가-힣]", "", w)) for w in t.split()],
            "게이트 [가-힣]{2,}": re.findall(r"[가-힣]{2,}", t)}


def javap_defaults():
    """nori jar에서 기본값을 **읽는다**(번들 JDK의 javap). 실패하면 None."""
    jar = "/usr/share/opensearch/plugins/analysis-nori/lucene-analysis-nori-9.12.3.jar"
    out = {}
    for cls, field in (("KoreanTokenizer", "DEFAULT_DECOMPOUND"),
                       ("KoreanPartOfSpeechStopFilter", "DEFAULT_STOP_TAGS")):
        p = subprocess.run(["docker", "exec", OS_CONTAINER, "/usr/share/opensearch/jdk/bin/javap",
                            "-cp", jar, "-c", "-p", "org.apache.lucene.analysis.ko." + cls],
                           capture_output=True)
        if p.returncode != 0:
            return None
        code = p.stdout.decode("utf-8", "replace").split("static {};", 1)[-1]
        vals = re.findall(r"(?:DecompoundMode|POS\$Tag)\.([A-Z]+):", code)
        out[field] = vals if field == "DEFAULT_STOP_TAGS" else (vals[:1] or [None])[0]
    return out


def run_t1():
    hr("T1 — OpenSearch + nori")
    info = E.os_request("/")
    print(f"  GET / → OpenSearch {info['version']['number']} · Lucene {info['version']['lucene_version']}")
    cat = E.os_request("/_cat/plugins?format=json")
    comps = sorted({(p["component"], p["version"]) for p in cat})
    print(f"  GET _cat/plugins → 플러그인 {len(comps)}종:")
    for c, v in comps:
        print(f"      {c} {v}")
    nori = [v for c, v in comps if c == "analysis-nori"]
    check("T1 analysis-nori가 목록에 있고 버전이 엔진과 같다",
          nori and nori[0] == info["version"]["number"],
          f"nori={nori[0] if nori else '없음'} · 엔진={info['version']['number']}")
    if not nori:
        return

    d = javap_defaults()
    print(f"\n  기본값(jar에서 javap로 읽음): {d}")
    print("  (OpenSearch NoriTokenizerFactory: discard_punctuation 기본 true · 사용자 사전 없음 ·"
          " 내장 `nori` = KoreanTokenizer → KoreanPartOfSpeechStopFilter → KoreanReadingFormFilter"
          " → LowerCaseFilter)")
    stoptags = (d or {}).get("DEFAULT_STOP_TAGS") or []
    chain = {"tokenizer": {"type": "nori_tokenizer", "decompound_mode": "discard"},
             "filter": [{"type": "nori_part_of_speech", "stoptags": stoptags},
                        "nori_readingform", "lowercase"]}

    print("\n  ── 입력별 `_analyze` 실출력 ──")
    same_chain = True
    for t in INPUTS:
        a = E.os_analyze(t)
        ex = E.os_request("/_analyze", {"tokenizer": "nori_tokenizer", "text": t, "explain": True,
                                        "attributes": ["leftPOS"]})
        pos = [(x["token"], (x.get("leftPOS") or "").split("(")[0])
               for x in ex["detail"]["tokenizer"]["tokens"]]
        modes = {m: E.os_analyze(t, tokenizer={"type": "nori_tokenizer", "decompound_mode": m},
                                 filter=["nori_part_of_speech", "nori_readingform", "lowercase"])
                 for m in DECOMPOUND_MODES}
        mine = E.os_analyze(t, **chain) if stoptags else None
        same_chain &= (mine == a)
        print(f"  «{t}»")
        print(f"      nori(내장)         {a}")
        print(f"      형태소·품사        {pos}")
        print(f"      decompound 셋      " + " · ".join(f"{m}={v}" for m, v in modes.items()))
        for k, v in current_tokenizers(t).items():
            print(f"      현행 {k:<16}{v}")
    stems = {t: E.os_analyze(t) for t in ("나비가", "나비를", "나비는")}
    check("T1 `나비가`·`나비를`·`나비는` → 셋 모두 정확히 ['나비']",
          all(v == ["나비"] for v in stems.values()), json.dumps(stems, ensure_ascii=False))

    comp = {m: E.os_analyze(COMPOUND_CONTROL,
                            tokenizer={"type": "nori_tokenizer", "decompound_mode": m})
            for m in DECOMPOUND_MODES}
    print(f"\n  합성어 대조 «{COMPOUND_CONTROL}» (필터 없이 토크나이저만): {comp}")
    check("T1b decompound_mode 셋이 서로 다른 출력을 적어도 둘 낸다",
          len({tuple(v) for v in comp.values()}) >= 2)
    check("T1c 내장 `nori` == 읽어 낸 기본값으로 조립한 사슬(모든 입력)",
          bool(stoptags) and d.get("DEFAULT_DECOMPOUND") == "DISCARD" and same_chain,
          f"DEFAULT_DECOMPOUND={(d or {}).get('DEFAULT_DECOMPOUND')} · stoptags {len(stoptags)}종")


def pg_array(s):
    """psql이 찍은 text[] 리터럴 `{" 나",나비,"비가"}`를 파이썬 목록으로."""
    return [q.replace('\\"', '"').replace("\\\\", "\\") if q or bare == "" else bare
            for q, bare in re.findall(r'"((?:[^"\\]|\\.)*)"|([^,]+)', s[1:-1])]


def run_t2():
    hr("T2 — Postgres + pg_bigm")
    avail = E.psql("SELECT name, default_version FROM pg_available_extensions "
                   "WHERE name IN ('pg_bigm','pg_trgm') ORDER BY name;")
    print(f"  pg_available_extensions → {avail}")
    try:
        v = E.pg_require_bigm()
        ok = True
    except E.EngineUnavailable as e:
        v, ok = str(e), False
    check("T2 CREATE EXTENSION pg_bigm 성공", ok, str(v))
    if not ok:
        return
    rows = E.psql("SELECT extname, extversion FROM pg_extension ORDER BY extname;")
    print(f"  pg_extension → {rows}")

    print("\n  ── show_bigm ──")
    words = sorted({w for p in PG_PAIRS for w in p})
    arr = {}
    for w in words:
        r = E.psql(f"SELECT show_bigm({E.lit(w)});")
        arr[w] = pg_array(r[0][0])
        print(f"      show_bigm({w!r:34}) = {r[0][0]}")
    check("T2 show_bigm('나비가')에 '나비'가 있다", "나비" in arr.get("나비가", []),
          str(arr.get("나비가")))

    print("\n  ── bigm_similarity vs 두 식 (A·B = show_bigm 집합) ──")
    print(f"      {'쌍':<58}{'bigm_sim':>10}{'∩/max':>10}{'∩/∪':>10}")
    agree_max, differs_jac, borja = True, False, None
    for a, b in PG_PAIRS:
        s = float(E.psql(f"SELECT bigm_similarity({E.lit(a)}, {E.lit(b)});")[0][0])
        A, B = set(arr[a]), set(arr[b])
        f_max = len(A & B) / max(len(A), len(B)) if A and B else 0.0
        f_jac = len(A & B) / len(A | B) if A and B else 0.0
        agree_max &= abs(s - f_max) < 1e-6
        differs_jac |= abs(s - f_jac) > 1e-6
        if (a, b) == ("보류됐습니다", "보류"):
            borja = s
        print(f"      {a + ' ↔ ' + b:<58}{s:>10.6f}{f_max:>10.6f}{f_jac:>10.6f}")
    check("T2 bigm_similarity('보류됐습니다','보류') ∈ (0, 1]",
          borja is not None and 0 < borja <= 1, str(borja))
    check("T2b bigm_similarity == |A∩B|/max(|A|,|B|) (모든 쌍) · 자카드와는 다르다",
          agree_max and differs_jac, f"∩/max 일치={agree_max} · 자카드와 갈린 쌍 있음={differs_jac}")

    print("\n  ── GIN 색인(gin_bigm_ops) ──")
    E.psql("DROP TABLE IF EXISTS memarch_verify;\n"
           "CREATE TABLE memarch_verify (id text PRIMARY KEY, body text);\n"
           "INSERT INTO memarch_verify SELECT 'n'||g, '잡음 문장 '||g FROM generate_series(1,2000) g;\n"
           "INSERT INTO memarch_verify VALUES ('hit', '첫 번째 PG사 미팅은 수수료 이견으로 보류됐습니다');\n"
           "CREATE INDEX memarch_verify_bigm ON memarch_verify USING gin (body gin_bigm_ops);\n"
           "ANALYZE memarch_verify;")
    idx = E.psql("SELECT indexdef FROM pg_indexes WHERE indexname='memarch_verify_bigm';")
    print(f"      pg_indexes → {idx}")
    plan = E.psql("SET enable_seqscan = off;\n"
                  "EXPLAIN SELECT id FROM memarch_verify WHERE body LIKE likequery('보류');")
    for r in plan:
        print(f"      {r[0]}")
    hit = E.psql("SELECT id FROM memarch_verify WHERE body LIKE likequery('보류');")
    print(f"      LIKE likequery('보류') → {hit}")
    check("T2 gin_bigm_ops GIN 색인이 만들어지고 계획이 그것을 쓴다",
          idx and "gin_bigm_ops" in idx[0][0]
          and any("memarch_verify_bigm" in r[0] for r in plan) and hit == [["hit"]])
    E.psql("DROP TABLE memarch_verify;")

    print("\n  ── (선택) 같은 입력에서 pg_trgm · tsvector(simple) ──")
    E.psql("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    for a, b in PG_PAIRS[:6]:
        r = E.psql(f"SELECT similarity({E.lit(a)}, {E.lit(b)}), "
                   f"to_tsvector('simple', {E.lit(a)}) @@ plainto_tsquery('simple', {E.lit(b)}), "
                   f"to_tsvector('simple', {E.lit(a)})::text;")[0]
        print(f"      {a + ' ↔ ' + b:<58} trgm={float(r[0]):.6f}  simple@@={r[1]}  tsv={r[2]}")
    for w in ("나비가", "보류"):
        print(f"      show_trgm({w!r}) = {E.psql(f'SELECT show_trgm({E.lit(w)});')[0][0]}")


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    for c in (OS_CONTAINER, E.PG_CONTAINER):
        try:
            p = E.image_provenance(c, base=E.BASE_IMAGES.get(c.replace("-stock", "")))
            print(f"  출처 «{c}» 이미지 {p['image'][:19]}… · 기반 {p['base']} 위인가={p['on_base']}"
                  f" · 더한 층 {p['extra_layers']}")
        except (E.EngineUnavailable, KeyError) as e:
            print(f"  출처 «{c}» 확인 불가: {e}")
    try:
        if only != "--pg-only":
            run_t1()
        if only != "--os-only":
            run_t2()
    except E.EngineUnavailable as e:
        print(f"\n⛔ SKIP(77) — 엔진이 없다: {e}\n   SKIP은 통과가 아니다(G1).")
        return E.EXIT_SKIP
    fails = [n for n, ok in RESULTS if not ok]
    print(f"\n판정: 조건 {len(RESULTS)}개 중 PASS {len(RESULTS) - len(fails)} · FAIL {len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
