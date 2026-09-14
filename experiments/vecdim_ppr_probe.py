# -*- coding: utf-8 -*-
"""
vecdim_ppr_probe.py — [docs/17](../docs/17-gap-disposition.md) §6의 ❔1(벡터 «1024차원»)과
❔2(«PPR 축 태깅 없음»)를 코드와 실행으로 본다. (API 불필요 · ollama 0회 · LLM 0회)

## ❔1 — 1024는 누가 정하나

«모델 사양이다»와 «코드가 강제한다»는 다른 주장이다. 가르는 관측 셋:
  ① `prototype/`의 **코드 토큰**(주석·문자열 제외)에 `1024` 리터럴이나 차원 이름이 있나
  ② 차원이 다른 두 벡터를 `_cosine`에 넣으면 **멈추나** — 안 멈추면 코드는 차원을 모른다
     🔄 w6code(docs/17 축-2) — 이제 멈춘다(`DimMismatch`). ②″가 검색 경로의 강등을 함께 본다.
  ③ 저장소에 이미 있는 임베딩 캐시 파일의 벡터 길이 — 모델이 **실제로 낸** 값(읽기만)

## ❔2 — 축 태깅이 있나

docs/15 §4는 검색된 기억에 `(이해)`·`(인정)`·`(배려)`를 붙이라고 한다(§2 도식의 `(배려)`).
🔴 낱말 `이해`·`인정`·`축`으로 grep하면 **틀린 것을 문다** — `개인정보`에 `인정`이, `축출`에
`축`이 들어 있다. 그래서 grep 대상을 docs/15가 렌더하는 **괄호 꼴**로 정하고, 같은 grep이
docs/15에서는 발화하는지(대조)와, 검색이 실제로 돈 컨텍스트에서 그 꼴이 나오는지를 함께 본다.

    PYTHONIOENCODING=utf-8 python -B experiments/vecdim_ppr_probe.py
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
import tokenize
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "prototype"))
sys.stdout.reconfigure(encoding="utf-8")
W = 78

import yaml  # noqa: E402
import memory as M  # noqa: E402
import soak  # noqa: E402

PROTO = ROOT / "prototype"
DOC15 = ROOT / "docs" / "15-read-path-prompt.md"
CACHES = (ROOT / "experiments" / "data" / "EMBED_CACHE.json",
          ROOT / "experiments" / "data" / "EMBED_CACHE_SWEEP.json")
AXIS_TAG = re.compile(r"\((이해|인정|배려)\)")
DIM_NAME = re.compile(r"dim|차원", re.I)


def code_hits(src, number, name_re):
    """NUMBER·NAME 토큰만 본다 — 주석·문자열은 이 두 타입을 내지 않는다(`eval_controls_audit`와 같은 이유)."""
    nums, names = [], []
    for t in tokenize.generate_tokens(io.StringIO(src).readline):
        if t.type == tokenize.NUMBER and t.string == str(number):
            nums.append(t.start[0])
        if t.type == tokenize.NAME and name_re.search(t.string):
            names.append((t.start[0], t.string))
    return nums, names


def dim_report(proto_dir=PROTO):
    out = {}
    for p in sorted(Path(proto_dir).rglob("*.py")):
        src = p.read_text(encoding="utf-8")
        nums, names = code_hits(src, 1024, DIM_NAME)
        cmt = [i for i, ln in enumerate(src.splitlines(), 1) if "1024" in ln]
        out[p.name] = dict(nums=nums, names=names, all_1024=cmt)
    return out


# 🔄 첫 판은 «코드 토큰의 1024 = 0»을 판정 조건으로 박았는데 실행해 보니 6곳이었고,
#    전부 **바이트 단위**(`1 * 1024 * 1024` 캐시 상한 · `size/1024` KB 출력)였다. 그래서
#    줄마다 단위를 가르고 줄을 그대로 찍는다 — 읽는 사람이 분류를 다시 볼 수 있게.
BYTE_LINE = re.compile(r"BYTES|KB|size\s*/\s*1024|1024\s*\*\s*1024")


def classify_1024(proto_dir=PROTO):
    out = []
    for p in sorted(Path(proto_dir).rglob("*.py")):
        lines = p.read_text(encoding="utf-8").splitlines()
        for ln in sorted(set(dim_report(proto_dir)[p.name]["nums"])):
            text = lines[ln - 1].strip()
            out.append((p.name, ln, "바이트 단위" if BYTE_LINE.search(text) else "그 밖", text))
    return out


def vec_roundtrip():
    """3차원 벡터를 `embedding` 테이블에 넣고 다시 읽는다 — 거절하면 코드가 차원을 지킨다."""
    import embedding
    tmp = tempfile.mkdtemp(prefix="vecdim_")
    m = None
    try:
        m = M.Memory(os.path.join(tmp, "v.db"))
        try:
            embedding.db_put_vec(m.db, "chat-x", "차원 시험", [0.1, 0.2, 0.3])
            got = embedding.db_get_vec(m.db, "차원 시험")
            return True, None if got is None else len(got)
        except Exception as e:                               # noqa: BLE001
            return False, repr(e)
    finally:
        if m is not None:
            m.db.close()
        shutil.rmtree(tmp, ignore_errors=True)


def cosine_accepts_mismatch():
    """차원이 다른 두 벡터 — 예외가 나면 코드가 차원을 지키는 것이다."""
    try:
        return True, M._cosine([1.0, 0.0, 0.0], [1.0, 0.0])
    except Exception as e:                                   # noqa: BLE001
        return False, repr(e)


def retrieve_degrades_on_mismatch():
    """
    🆕 w6code — 임베딩 모드 검색에서 질의 3차원 × 문서 2차원이면 **예외 없이 강등**하나.
    `(예외 없음, 노트 종류 목록)` 또는 `(False, 예외 repr)`. 벡터 공급자는 가짜다(네트워크 0).
    """
    saved = (M.RETRIEVAL_MODE, M.EMBED_FN)
    m = M.Memory()
    try:
        m.db.execute("INSERT INTO event (chat_id, summary, occurred_at, emotional_weight,"
                     " importance, source_from_seq) VALUES (?,?,?,?,?,?)",
                     ("chat-x", "나비 사료를 새로 샀다", 1, 0.0, 0.8, 1))
        M.RETRIEVAL_MODE = "embed"
        M.EMBED_FN = lambda texts: [[1.0, 0.0, 0.0] if i == 0 else [1.0, 0.0]
                                    for i in range(len(texts))]
        try:
            m.retrieve("chat-x", "나비 사료", 10)
        except Exception as e:                           # noqa: BLE001
            return False, repr(e)
        return True, [k for k, _, _ in m._retrieval_notes]
    finally:
        M.RETRIEVAL_MODE, M.EMBED_FN = saved
        m.db.close()


def cache_lengths():
    c, files = Counter(), []
    for p in CACHES:
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        n = 0
        for v in d.values():
            if isinstance(v, list):
                c[len(v)] += 1; n += 1
            elif isinstance(v, dict):                        # 모델별로 묶인 꼴이면
                for vv in v.values():
                    if isinstance(vv, list):
                        c[len(vv)] += 1; n += 1
        files.append((p.name, n))
    return c, files


def axis_grep(paths):
    return {Path(p).name: [i for i, ln in enumerate(Path(p).read_text(encoding="utf-8")
                                                    .splitlines(), 1) if AXIS_TAG.search(ln)]
            for p in paths}


UTTER = (("부정 감정 → 배려", "나비 때문에 요즘 너무 힘들어"),
         ("성취 → 인정", "나 이직한 회사에서 첫 프로젝트 끝냈어"),
         ("질문 → 이해", "나비 응급실 갔던 게 언제였지?"))


def render_probe():
    with open(ROOT / "eval" / "corpus" / "corpus.jsonl", encoding="utf-8") as f:
        corpus = [json.loads(l) for l in f]
    with open(ROOT / "eval" / "fact-ledger.yaml", encoding="utf-8") as f:
        ledger = yaml.safe_load(f)
    tmp = tempfile.mkdtemp(prefix="pprprobe_")
    m = None
    try:
        m = M.Memory(os.path.join(tmp, "p.db"))
        soak.seed(m)
        soak.ingest(m, corpus, ledger, timed=False)
        last = corpus[-1]["seq"]
        rows = []
        for label, u in UTTER:
            ctx = m.build_context(soak.CHAT, u, last)
            text = ctx.render()
            names = [b.name for b in ctx.blocks]
            ret = next((b.text for b in ctx.blocks if b.name == "retrieved"), "")
            rows.append((label, u, len(ret.splitlines()) if ret else 0,
                         len(AXIS_TAG.findall(text)), names))
        return rows
    finally:
        if m is not None:
            m.db.close()
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print("=" * W)
    print("❔1 벡터 차원 · ❔2 PPR 축 태깅 — 코드와 실행으로 (ollama 0회)")
    print("=" * W)

    print("\n❔1 — «1024»는 코드가 강제하나")
    rep = dim_report()
    n_num = sum(len(r["nums"]) for r in rep.values())
    n_name = sum(len(r["names"]) for r in rep.values())
    print(f"  ① prototype/*.py {len(rep)}개 — 코드 토큰의 `1024` {n_num}곳 · 차원 이름(`dim|차원`) "
          f"{n_name}곳 {[(f, r['names']) for f, r in rep.items() if r['names']] or ''}")
    print("     글자 `1024`가 있는 줄(주석·문자열 포함): "
          + str({f: r["all_1024"] for f, r in rep.items() if r["all_1024"]}))
    cls = classify_1024()
    for f, ln, kind, text in cls:
        print(f"     코드 토큰 `1024` — {f}:{ln} [{kind}] {text[:60]}")
    ok, val = cosine_accepts_mismatch()
    print(f"  ② `_cosine([1,0,0], [1,0])` → {'예외 없이 ' + repr(val) if ok else '예외 ' + val}"
          f"  ({'차원을 안 본다 — `zip`이 짧은 쪽에서 조용히 끊는다' if ok else '차원을 본다'})")
    rt_ok, rt = vec_roundtrip()
    print(f"  ②′ `db_put_vec`에 3차원 벡터 → {'받아서 저장 · 다시 읽은 길이 ' + str(rt) if rt_ok else '거절 ' + rt}")
    deg_ok, deg = retrieve_degrades_on_mismatch()
    print(f"  ②″ 임베딩 검색 · 질의 3차원 × 문서 2차원 → "
          f"{'예외 없이 강등 · 노트 ' + str(deg) if deg_ok else '예외가 샌다 ' + deg}")
    c, files = cache_lengths()
    print(f"  ③ 캐시 파일 벡터 길이 {dict(c)} · 파일 {files}  (저장소에 이미 있는 모델 출력 — 읽기만)")
    dim_literal = [x for x in cls if x[2] != "바이트 단위"]
    # 🔄 w6code (docs/17 축-2) — ②의 기록 기대값이 뒤집혔다. 옛 판정은 `ok`(= 코사인이 길이가 다른
    #    벡터를 조용히 받는다)를 요구했고 옛 출력은 «② 예외 없이 1.0 → 모델 출력의 성질이다 — 코드는
    #    1024를 차원으로 적지도 검사하지도 않는다»였다. 이제 코사인은 던지고(②) 검색은 강등한다(②″).
    #    ②′(저장은 3차원도 받는다)는 그대로다 — 이 레인은 저장 경로를 안 고쳤다.
    deg_seen = deg_ok and deg.count("dim_mismatch") == 1 and deg.count("degraded") == 1
    verdict1 = ("모델 출력의 성질이다 — 코드는 1024를 차원으로 적지 않는다. 검사는 한다: 길이가 "
                "다르면 코사인이 던지고(②) 임베딩 검색은 예외 없이 강등한다(②″)"
                if not dim_literal and not ok and deg_seen and rt_ok and rt == 3
                and set(c) == {1024}
                else "기대와 다르다 — 위 칸을 볼 것")
    print(f"  → {verdict1}")

    print("\n❔2 — PPR 축 태깅이 있나 (grep 대상: 괄호 꼴 `(이해)|(인정)|(배려)`)")
    g_doc = axis_grep([DOC15])
    g_pro = axis_grep(sorted(PROTO.rglob("*.py")))
    hit_pro = {f: v for f, v in g_pro.items() if v}
    print(f"  대조 — docs/15: {sum(map(len, g_doc.values()))}줄 {g_doc}  (이 grep이 발화할 수 있다)")
    print(f"  prototype/*.py {len(g_pro)}개: {sum(map(len, g_pro.values()))}줄 {hit_pro or ''}")
    print("  실행 — 검색이 도는 발화 셋으로 `build_context`를 불러 렌더에서 같은 꼴을 센다:")
    rows = render_probe()
    for label, u, nret, ntag, names in rows:
        print(f"    {label:<12} «{u}» · 검색 블록 {nret}줄 · 축 표지 {ntag}개")
    print(f"    블록 이름(마지막 발화): {rows[-1][4]}")
    retrieved_any = any(r[2] > 0 for r in rows)
    verdict2 = ("없다 — docs/15에서는 발화하는 grep이 prototype에서 0이고, 검색이 돈 렌더에도 0"
                if not hit_pro and retrieved_any and all(r[3] == 0 for r in rows)
                else "판정 못 함 — 위 칸을 볼 것")
    print(f"  → {verdict2}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
