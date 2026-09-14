# -*- coding: utf-8 -*-
"""
embed_model_sweep.py — 후속 9. 임베딩 지연을 TTFT 예산 안으로 넣을 모델이 있는가.

## 왜 — 그리고 🔴 **이 질문은 이제 철회됐다**

이 스크립트는 [ADR-015](../docs/adr/ADR-015-retrieval-modes.md) ⭐핵심 5의
*"bge-m3 웜 p50 **2,082 ms** = 예산의 5.2배"*에 대한 응답으로 태어났다.
**그 값은 틀렸다**(`.omc/plans/verifier-f38-overturn.md`). 2,082 ms의 **97.1%**가
기본 호스트 `localhost` 탓에 ollama에 닿지도 못한 **실패 connect**였고, 순 연산은
**34.2 ms**다. `127.0.0.1`로 재면 bge-m3는 **웜 p50 55 ms = 예산의 0.14배**로
**PASS**한다.

→ **모델 교체 질문은 근거가 사라졌다.** 게다가 아래 품질 열은 프로브 **10개**짜리라
   다섯 후보를 **구별하지 못한다**(bge-m3 대비 부호 검정 p = 0.500 / 0.250 /
   1.000 / 1.000 · 7/10의 95% Wilson CI [40%, 89%] · 품질 차이 전부가 **10개 중
   2개 프로브** 위에 서 있다). 그래서 결론은 **bge-m3 유지**다.

**이 스크립트를 지우지 않는 이유:** 다섯 모델이 전부 게이트를 통과한다는 것 자체가
기록이고, 다음 사람이 같은 질문을 다시 열 때 *"n=10으로는 못 고른다"*를 실측으로
보여주는 것이 이 표다. 그리고 0-연산 대조행(아래)이 F38 같은 사고를 다시 막는다.

## 🔴 지연만 재면 안 된다

빠른 모델을 골랐는데 한국어 순위가 무너지면 **게이트를 통과한 채로 검색이
망가진다.** 그래서 두 축을 같이 잰다:

  1. **지연** — F38의 절차 그대로: 콜드 1회를 떼고 개별 왕복 10회의 웜 p50/p95.
     🔴 **0-연산 대조(`GET /api/tags`)를 같은 표에 찍는다** — 모델을 안 돌리는
     호출이 같은 값을 내면 그 숫자는 모델에 대한 것이 아니다. F38이 그 경우였다.
  2. **품질** — `embed_vs_bigram.py`의 프로브 10개 × 확장 27문장에서
     1등·top-5·평균 순위·정답 근거 점수 하한 **+ 프로브별 순위 목록**.
     bge-m3의 `7/10 · 8/10 · 3.3 · 0.402`가 비교 대상이다.
     ⚠️ 순위 목록 없이는 **짝지은 비교가 불가능하다** — 평균 하나로는
     *"고르게 중간"*과 *"대부분 1등인데 두 개가 11·13등"*이 구분되지 않는다.

**둘 다 통과해야 후보다.** 판정은 이 스크립트가 하지 않는다 — 표를 찍고
"지연 PASS / 품질 ≥ bge-m3" 두 열을 병기할 뿐이고, 승격은 R2b 재개 라운드의 결정이다.

실행: python experiments/embed_model_sweep.py [--models a,b,c] [--skip-pull]
출력: 표 + `.omc/plans/baseline/after-r2a/embed-model-sweep.txt`로 저장 가능
"""
import argparse
import json
import os
import statistics as st
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "prototype"))

W = 78
# `localhost`가 아닌 이유는 `prototype/embedding.py:24`의 주석이 정본이다 —
# 이 기기는 거절된 connect에 ~2.02초를 쓰고, `localhost`는 ollama가 안 듣는 `::1`을
# 먼저 고른다. **이 파일의 2,09x ms 열이 전부 그 비용이었다.**
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_BIN = os.environ.get(
    "OLLAMA_BIN",
    os.path.join(os.path.expanduser("~"), r"AppData\Local\Programs\Ollama\ollama.exe"))

# ── 후보 ──────────────────────────────────────────────────────────────
# 고르는 기준: **다국어 임베딩**. 영어 전용 모델은 넣지 않는다 — 이 코퍼스는 전부
# 한국어다. `all-minilm`(23M)은 빠르겠지만 한국어를 못 하므로 **빠른 쓰레기**가
# 되고, 그것을 표에 넣으면 지연 열만 보고 고르고 싶어진다. 후보에서 뺀 것도 기록이다.
#
# 🔴 **크기 주석 정정 (F38 정정).** 여기 있던 값은 카드 스펙에서 옮겨 적은 것이었고
#    `snowflake-arctic-embed2`가 **"305M"**으로 적혀 있었다. `/api/show`가 보고하는
#    실제 값은 **566.70M** — bge-m3와 **같은 크기**다(1.9배 틀렸다). 그래서 원래
#    적혀 있던 선정 기준 *"bge-m3보다 작다"*는 이 후보에 대해 **성립하지 않았다.**
#    아래 값은 전부 `/api/show`의 `general.parameter_count`다.
#
#    ⚠️ 그리고 *"파라미터 2.2배 폭"*은 **양 극단에서만** 성립한다:
#       277.45M → 595.78M = **2.15배**. 가운데 두 행은 서로 같은 크기다.
#       (이 폭이 중요한 이유: F38은 *"비용이 연산이다"*라고 적었는데, 연산이라면
#        2.15배 크기 차가 지연에 나타나야 한다. 나타나지 않았고 — 46.9~57.7 ms —
#        **그 자체가 F38의 자기 반증이었다.** 아무도 그렇게 읽지 않았을 뿐이다.)
CANDIDATES = [
    ("bge-m3",                     "566.70M · 현행 · 기준선"),
    ("snowflake-arctic-embed2",    "566.70M · 다국어 (bge-m3와 동급)"),
    ("granite-embedding:278m",     "277.45M · 다국어 (IBM)"),
    ("paraphrase-multilingual",    "277.45M · sentence-transformers 다국어"),
    ("qwen3-embedding:0.6b",       "595.78M · 다국어 (Qwen3)"),
]

# F38의 표본 정의를 그대로 쓴다 — 짧은 한국어 질의 10개, 개별 왕복.
LATENCY_PROBES = [
    "지우가 어제 뭐 했더라", "면접 몇 번 봤었지", "나비 요즘 괜찮아?",
    "우리 언제 처음 만났지", "그때 카페 이름이 뭐였어", "회사 일은 좀 나아졌어?",
    "동생 얘기 했었나", "고양이 병원 갔던 거", "새벽에 연락한 날", "요즘 고민 있어?",
]

TTFT_BUDGET_MS = 400        # docs/05 상한. 하한은 200
GATE_MS = TTFT_BUDGET_MS    # 후속 9의 조건: 웜 p50 ≤ 400 ms


def _post(path, payload, timeout=180):
    req = urllib.request.Request(
        f"{OLLAMA_HOST}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def embed_one(model, text, timeout=180):
    """한 텍스트 한 왕복. 실패는 None — 프로덕션 경로와 같은 규약."""
    try:
        r = _post("/api/embed", {"model": model, "input": [text]}, timeout)
        v = r.get("embeddings") or []
        return v[0] if v else None
    except Exception:
        return None


def tags_ms(timeout=180):
    """
    🔴 **0-연산 대조.** `GET /api/tags`는 모델을 한 번도 돌리지 않는다. 그래서
    이 호출에 남는 시간은 전부 클라이언트·연결·프로세스 경계 비용이다.

    이 표에 이 행이 없었기 때문에 2,09x ms 열 전체가 *"어떤 모델도 충분히 빠르지
    않다"*로 읽혔다. 실제로는 **계측기가 고장 나 있었다** — `/api/tags`도 같은
    2,06x ms를 내고 있었으므로 다섯 줄 · 10초면 잡혔을 일이다
    (`.omc/plans/verifier-f38-overturn.md` "The process lesson").
    """
    try:
        t0 = time.perf_counter()
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags",
                                    timeout=timeout) as r:
            r.read()
        return (time.perf_counter() - t0) * 1000
    except Exception:
        return None


def installed():
    try:
        out = subprocess.run([OLLAMA_BIN, "list"], capture_output=True,
                             text=True, encoding="utf-8", timeout=60).stdout
        return {ln.split()[0].split(":")[0] for ln in out.splitlines()[1:] if ln.strip()}
    except Exception:
        return set()


def pull(model):
    """없으면 받는다. 실패는 치명적이지 않다 — 그 모델만 SKIP."""
    print(f"    받는 중 {model} …", end=" ", flush=True)
    t0 = time.perf_counter()
    r = subprocess.run([OLLAMA_BIN, "pull", model], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=3600)
    dt = time.perf_counter() - t0
    if r.returncode == 0:
        print(f"✅ {dt:.0f}초")
        return True
    print(f"❌ ({(r.stderr or '').strip()[:80]})")
    return False


def latency(model):
    """
    F38의 절차 그대로. **콜드 1회를 떼고** 개별 왕복 10회의 웜 p50/p95.
    콜드를 버리는 것이 이 게이트에 **가장 유리한 읽기**다.

    🔴 함께 재는 것: **0-연산 대조**(`tags_ms`). 웜 p50에서 그 값을 빼면
       `순 연산`이 나온다 — 그 뺄셈이 없으면 클라이언트 비용이 모델 비용으로
       읽힌다(F38: 2,082 ms 중 **2,047 ms가 실패한 connect**였다).
    """
    cold_t0 = time.perf_counter()
    v = embed_one(model, LATENCY_PROBES[0])
    cold = (time.perf_counter() - cold_t0) * 1000
    if v is None:
        return None
    dim = len(v)
    lat = []
    for t in LATENCY_PROBES:
        s = time.perf_counter()
        if embed_one(model, t) is None:
            return None
        lat.append((time.perf_counter() - s) * 1000)
    lat.sort()
    # 0-연산 대조는 임베딩 직후에 **같은 조건에서** 잰다. 중앙값 5회.
    tags = sorted(t for t in (tags_ms() for _ in range(5)) if t is not None)
    tags_p50 = tags[len(tags) // 2] if tags else None
    return {"cold": cold, "p50": st.median(lat), "p95": lat[int(len(lat) * .95) - 1],
            "min": lat[0], "max": lat[-1], "dim": dim, "n": len(lat),
            "tags": tags_p50,
            "net": (st.median(lat) - tags_p50) if tags_p50 is not None else None}


def quality(model):
    """
    `embed_vs_bigram.py`의 프로브·확장 집합을 **그대로** 빌려 쓴다.
    같은 모집단이라야 bge-m3의 `7/10 · 8/10 · 3.3 · 0.402`와 비교 가능하다.
    """
    import embed_vs_bigram as EV
    # `main()` 안에서 만들던 후보 집합을 여기서 같은 규칙으로 다시 만든다.
    # ⚠️ 규칙을 복사하지 말고 **같은 파일에서 읽는다** — `planted_id`가 있는 턴만이
    #    후보다(`embed_vs_bigram.py:103`). 규칙이 갈라지면 두 실험의 수치가
    #    비교 불가능해지고, 그것이 이 저장소가 F12에서 겪은 일이다.
    docs = [json.loads(l) for l in
            open(ROOT / "eval/corpus/corpus.jsonl", encoding="utf-8")]
    ext = [d["text"] for d in docs if d["planted_id"]]
    gold_of = {d["text"]: d["planted_id"] for d in docs if d["planted_id"]}
    probes = EV.PROBES                    # [(질의, 정답 id), ...]

    vecs = {}
    for t in ext + [q for q, _ in probes]:
        v = embed_one(model, t)
        if v is None:
            return None
        vecs[t] = v

    def cos(a, b):
        num = sum(x * y for x, y in zip(a, EV.M._same_dim(a, b)))  # 길이가 다르면 던진다 — `EV.M`은 `memory` 모듈 그 자체다(사본 아님 · F12 · w12close)
        na = sum(x * x for x in a) ** .5 or 1.0
        nb = sum(x * x for x in b) ** .5 or 1.0
        return num / (na * nb)

    first = top5 = 0
    ranks, floors = [], []
    for q, gold_id in probes:
        scored = sorted(((cos(vecs[q], vecs[e]), e) for e in ext),
                        key=lambda x: -x[0])
        r = next((i + 1 for i, (_, e) in enumerate(scored)
                  if gold_of[e] == gold_id), len(scored))
        ranks.append(r)
        first += r == 1
        top5 += r <= 5
        # 🔴 **`min()`이다** — `embed_vs_bigram.py:136`과 같은 규약.
        #    여기 있던 `next(...)`는 **내림차순으로 정렬된** `scored`에서 첫 정답을
        #    집으므로 사실상 `max()`였다. 오늘의 코퍼스는 1:1(27문서 / 27개 서로
        #    다른 `planted_id` · 중복 텍스트 0)이라 두 식이 같은 값을 내지만,
        #    **한 gold id에 문서가 둘 이상 붙는 순간 조용히 갈라진다** — 그리고
        #    이 열의 뜻(*"정답이 받은 점수 중 **최악**"*)은 `min` 쪽이다.
        gold_scores = [s for s, e in scored if gold_of[e] == gold_id]
        floors.append(min(gold_scores) if gold_scores else 0.0)
    return {"first": first, "top5": top5, "n": len(probes),
            "mean_rank": sum(ranks) / len(ranks), "floor": min(floors), "ranks": ranks}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="")
    ap.add_argument("--skip-pull", action="store_true")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    cands = ([(m.strip(), "지정") for m in a.models.split(",") if m.strip()]
             if a.models else CANDIDATES)

    print("=" * W)
    print("후속 9 — 임베딩 지연을 TTFT 예산 안으로 넣을 모델이 있는가")
    print("=" * W)
    print(f"\n게이트: **웜 p50 ≤ {GATE_MS} ms** (docs/05 TTFT 예산 200~400 ms)")
    print(f"측정 호스트: {OLLAMA_HOST}"
          f"{'  (OLLAMA_HOST로 덮어씀)' if os.environ.get('OLLAMA_HOST') else ''}"
          "   ← G15. `localhost`로 재면 이 기기에서 전 행이 2,09x ms가 된다")
    print("표본: 짧은 한국어 질의 10개 · 개별 왕복 · 콜드 1회 제외 — F38과 같은 절차")
    print("품질: embed_vs_bigram의 프로브 10개 × 확장 27문장. 기준 bge-m3 = 7/10 · 8/10 · 3.3 · 0.402")
    print("\n🔴 **지연만 보고 고르면 안 된다** — 빠른데 한국어 순위가 무너지면")
    print("   게이트를 통과한 채로 검색이 망가진다. 두 열을 함께 읽는다.")
    print("🔴 **그리고 지연 열을 0-연산 대조행과 함께 읽는다** — 모델을 안 돌리는")
    print("   호출이 같은 값을 내면 그 열은 모델에 대한 것이 아니다 (F38이 그랬다).\n")

    have = installed()
    rows = []
    for model, note in cands:
        base = model.split(":")[0]
        print(f"  ▶ {model:<28} {note}")
        if base not in have and not a.skip_pull:
            if not pull(model):
                rows.append((model, note, None, None, "받기 실패"))
                continue
        elif base not in have:
            rows.append((model, note, None, None, "미설치 (--skip-pull)"))
            continue
        lat = latency(model)
        if lat is None:
            rows.append((model, note, None, None, "임베딩 실패"))
            continue
        print(f"    지연 웜 p50 {lat['p50']:>7.0f} ms · p95 {lat['p95']:>7.0f} · "
              f"콜드 {lat['cold']:>7.0f} · dim {lat['dim']}")
        if lat["tags"] is not None:
            print(f"    0-연산 {lat['tags']:>7.0f} ms (GET /api/tags) → "
                  f"순 연산 {lat['net']:>7.0f} ms")
        q = quality(model)
        if q:
            print(f"    품질 1등 {q['first']}/{q['n']} · top5 {q['top5']}/{q['n']} · "
                  f"평균순위 {q['mean_rank']:.1f} · 하한 {q['floor']:.3f}")
        rows.append((model, note, lat, q, ""))

    print("\n" + "=" * W)
    print(f"{'모델':<26}{'웜 p50':>9}{'p95':>8}{'게이트':>8}  {'1등':>5}{'top5':>6}{'평균순위':>8}{'하한':>7}")
    print("-" * W)
    for model, note, lat, q, err in rows:
        if lat is None:
            print(f"{model:<26}{'—':>9}{'—':>8}{'SKIP':>8}  {err}")
            continue
        gate = "✅ PASS" if lat["p50"] <= GATE_MS else f"❌ {lat['p50']/GATE_MS:.1f}배"
        if q:
            print(f"{model:<26}{lat['p50']:>9.0f}{lat['p95']:>8.0f}{gate:>8}  "
                  f"{q['first']:>3}/{q['n']}{q['top5']:>4}/{q['n']}{q['mean_rank']:>8.1f}{q['floor']:>7.3f}")
        else:
            print(f"{model:<26}{lat['p50']:>9.0f}{lat['p95']:>8.0f}{gate:>8}  (품질 측정 실패)")

    # 🔴 **0-연산 대조행.** 모델 행과 **같은 표 안에** 있어야 눈이 비교한다.
    #    이 행이 모델 행과 같은 자릿수면 위의 지연 열은 모델을 재고 있지 않다.
    tvals = sorted(r[2]["tags"] for r in rows if r[2] and r[2]["tags"] is not None)
    if tvals:
        tmid = tvals[len(tvals) // 2]
        print(f"{'(0-연산 대조) GET /api/tags':<26}{tmid:>9.0f}{'—':>8}{'—':>8}"
              f"  모델을 한 번도 안 돌리는 호출")
        worst = max(r[2]["tags"] / r[2]["p50"] for r in rows
                    if r[2] and r[2]["tags"] is not None and r[2]["p50"])
        print(f"{'':<26}{'':>9}{'':>8}{'':>8}  "
              f"웜 p50의 최대 {worst:.0%} — "
              f"{'🔴 계측기를 먼저 본다' if worst >= .5 else '🟢 지배적이지 않다'}")

    # 🔴 **프로브별 순위 목록.** 이것이 없으면 짝지은 비교가 불가능하다 —
    #    `quality()`는 여태 `ranks`를 계산하고 **찍지 않았다.** n=10에서 평균
    #    3.3과 1.6의 차이가 *"두 프로브가 11→3, 13→4로 움직인 것"*인지
    #    *"열 개가 고르게 좋아진 것"*인지는 이 줄만 말할 수 있다.
    qrows = [(m, q) for m, _n, _l, q, _e in rows if q]
    if qrows:
        print("-" * W)
        npr = qrows[0][1]["n"]
        print(f"{'프로브별 정답 순위 (1이 최선)':<26}"
              + "".join(f"{i+1:>4}" for i in range(npr)))
        for m, q in qrows:
            print(f"{m:<26}" + "".join(f"{r:>4}" for r in q["ranks"]))
        print("  프로브 번호는 embed_vs_bigram.PROBES(= retrieval_sim.PROBES) 순서다.")
        print("  ⚠️ **n=10이다.** 이 열들이 갈리는 곳이 두 칸뿐이면 그 두 칸이")
        print("     평균 순위 열 전체를 만든 것이고, 그것은 모델의 차이가 아니다.")

    passed = [r for r in rows if r[2] and r[2]["p50"] <= GATE_MS]
    print("-" * W)
    if not passed:
        print(f"🔴 지연 게이트({GATE_MS} ms)를 통과한 모델 **없음.**")
        print("   → 이 결과가 나오면 **먼저 0-연산 대조행을 본다.** 그 행이 모델")
        print("      행과 같은 자릿수면 재고 있는 것은 모델이 아니라 클라이언트다")
        print("      (F38이 정확히 그 경우였고, 그때 이 행이 없었다).")
    else:
        print(f"🟢 지연 게이트 통과 **{len(passed)}종.**")
        print("   🔴 그러나 이 표는 **모델을 고르지 못한다.** 품질 열의 차이가 프로브")
        print("      10개 위에 서 있고, bge-m3 대비 부호 검정이 p = 0.500 / 0.250 /")
        print("      1.000 / 1.000이다 — 하나도 유의하지 않다. 7/10의 95% Wilson CI는")
        print("      [40%, 89%]로 거의 전부 겹친다.")
        print("   → **정직한 진술은 *\"품질 붕괴가 없다\"*까지다.** 순위를 매기려면")
        print("      프로브가 10개보다 많아야 한다. 현행 유지(bge-m3)가 결론이다.")
    print("⚠️ 이 표는 **이 기기 한 대**의 값이다. 다른 기기에서는 다시 재야 한다.")
    print("=" * W)

    if a.out:
        Path(a.out).write_text("(위 출력을 리다이렉트로 저장한다)\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
