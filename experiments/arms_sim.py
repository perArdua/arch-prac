"""
메모리 arm 비교 — 동일 조건에서 검색 계층만 바꿔 측정한다.

docs/adr/ADR-009의 통제 baseline 5종 + 후보 arm들을 같은 코퍼스·같은 질문으로 돌린다.
LLM이 없으므로 "응답 품질"은 못 재고, 그 상한을 결정하는 것들을 잰다:
  evidence_recall  정답 근거가 컨텍스트에 들어왔는가   ← 못 찾으면 LLM도 못 답한다
  injected_tokens  컨텍스트 크기
  precision        주입된 것 중 관련 있는 비율
  cost_per_turn    실단가 기반

⚠️ 이 실험이 말할 수 없는 것: 응답 품질, 페르소나 유지, L3(활용) 실패.
   그건 API 키가 필요하다. 여기서 나오는 건 "품질의 상한"이다.

실행: python experiments/gen_corpus.py && python experiments/arms_sim.py
"""

import json
import random
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retrieval_sim import BM25, tok_bigram, importance_map, PROBES  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "eval" / "corpus" / "corpus.jsonl"
LEDGER = ROOT / "eval" / "fact-ledger.yaml"

PRICE_IN, PRICE_CACHED, PRICE_OUT = 0.75, 0.075, 3.75
OUTPUT_TOKENS = 400
CACHE_HIT = 0.79            # 실험 1에서 나온 최선값
BUDGET = 4000               # 전 arm 동일 (A0 제외) — docs/adr/ADR-009 통제 조건
FIXED_BLOCKS = 1370         # system+persona+speech+state+scene+digest (docs/06 §5)
SEED = 20260903


def ntok(text):
    """한국어 토큰 추정. 1글자 ≈ 1.5토큰 (docs/05 §2)."""
    return max(1, int(len(text) * 1.5))


def load():
    docs = [json.loads(l) for l in open(CORPUS, encoding="utf-8")]
    ledger = yaml.safe_load(open(LEDGER, encoding="utf-8"))
    return docs, ledger


# ── arm 정의 ────────────────────────────────────────────────────────────
def arm_full(docs, q, gold, ctx):
    return docs                                    # A0 전체 히스토리

def arm_oracle(docs, q, gold, ctx):
    return [d for d in docs if d["planted_id"] == gold]   # A1 정답만

def arm_window(docs, q, gold, ctx, n=15):
    return docs[-n:]                               # A2 최근 N턴

def arm_random(docs, q, gold, ctx, k=5):
    return ctx["rng"].sample(docs, k)              # A3 무작위 — 위생 검사

def arm_window_summary(docs, q, gold, ctx, n=15):
    # B1 최근 N턴 + 요약(사건 요약을 압축본으로 대용)
    summary = [d for d in docs if d["kind"] == "event"][:6]
    return docs[-n:] + summary

def arm_rag_session(docs, q, gold, ctx, k=3):
    # C1 세션 단위 청크 검색 — 덩어리가 커서 예산을 잡아먹는다
    return ctx["bm_sess"].topk(q, k=k) and [
        d for d, _ in ctx["bm_sess"].topk(q, k=k)]

def arm_rag_extracted(docs, q, gold, ctx, k=5):
    # C2 추출 항목 단위 검색 (라운드 granularity + 키 확장)
    return [d for d, _ in ctx["bm_ext"].topk(q, k=k)]

def arm_current_guess(docs, q, gold, ctx, k=5):
    # G1 현행 구조 재현(추정): 계층 메모리 + 전 턴 RAG + top-k, 임계 없음
    return docs[-10:] + [d for d, _ in ctx["bm_all"].topk(q, k=k)]

def arm_proposed(docs, q, gold, ctx, k=5, tau=0.2, theta=0.15):
    """
    F1 제안안: 상태는 항상 주입(고정 블록으로 계산) + 게이팅 + 하드 게이트 + 임계 컷.
    docs/adr/ADR-005(수정판) 4단계를 그대로 구현한다.
    """
    ext, imp = ctx["ext"], ctx["imp"]
    bm = ctx["bm_ext"]
    raw = bm.score(q)
    mx = max(raw) or 1.0
    cands = []
    for i, d in enumerate(ext):
        im = imp.get(d["planted_id"], 0.5)
        if im < tau:                       # 2단계 하드 게이트
            continue
        rel = raw[i] / mx
        score = 0.6 * rel + 0.4 * im       # 3단계 가중
        if score >= theta + 0.4 * im:      # 4단계 임계 컷 (relevance 기여 요구)
            cands.append((score, d))
    cands.sort(key=lambda x: -x[0])
    return [d for _, d in cands[:k]] + docs[-10:]


ARMS = {
    "A0 Full-context":        arm_full,
    "A1 Oracle":              arm_oracle,
    "A2 Window-only(15)":     arm_window,
    "A3 Random-K(5)":         arm_random,
    "B1 Window+요약":          arm_window_summary,
    "C1 세션단위 RAG":          arm_rag_session,
    "C2 추출단위 RAG":          arm_rag_extracted,
    "G1 현행 재현(추정)":        arm_current_guess,
    "F1 제안안":               arm_proposed,
}


def evaluate(name, fn, docs, ctx):
    recall = tokens = precision_num = precision_den = 0
    for q, gold in PROBES:
        sel = fn(docs, q, gold, ctx) or []
        ids = [d["planted_id"] for d in sel]
        if gold in ids:
            recall += 1
        tok = sum(ntok(d["text"]) for d in sel)
        # 최근 턴 이외의 '주입된 기억'만 정밀도 대상으로 본다
        injected = [d for d in sel if d["planted_id"]]
        precision_den += max(len(injected), 1)
        precision_num += sum(1 for d in injected if d["planted_id"] == gold)
        tokens += tok
    n = len(PROBES)
    return {
        "recall": recall / n,
        "tokens": tokens / n,
        "precision": precision_num / max(precision_den, 1),
    }


def cost_per_month(ctx_tokens):
    total = ctx_tokens + FIXED_BLOCKS
    unc = total * (1 - CACHE_HIT)
    cac = total * CACHE_HIT
    c_in = (unc * PRICE_IN + cac * PRICE_CACHED) / 1e6 * 10_000
    c_out = OUTPUT_TOKENS * PRICE_OUT / 1e6 * 10_000
    return c_in + c_out, c_in


def exp_depth(docs, ledger):
    """
    참조 깊이별 arm 성능.

    실험 3의 편향 교정: 질문을 항상 마지막 턴에서 물으면 전부 '깊은 참조'가 되어
    Window-only에 불공정하다. 같은 질문을 근거로부터 d턴 떨어진 시점에서 물어본다.

    깊이 가중치는 docs/08 D1의 추정: 15턴 이내 75% / 60턴 이내 20% / 그 이상 5%
    """
    print("\n" + "═" * 84)
    print("실험 4 — 참조 깊이별 arm 성능 (실험 3의 편향 교정)")
    print("═" * 84)

    seq_of = {d["planted_id"]: i for i, d in enumerate(docs) if d["planted_id"]}
    imp = importance_map(ledger)
    DEPTHS = [(5, "얕음 ≤15"), (30, "중간 ≤60"), (300, "깊음 60+")]
    WEIGHTS = {5: 0.75, 30: 0.20, 300: 0.05}   # docs/08 D1 추정

    subset = {
        "A1 Oracle": arm_oracle,
        "A2 Window-only(15)": arm_window,
        "A3 Random-K(5)": arm_random,
        "C2 추출단위 RAG": arm_rag_extracted,
        "G1 현행 재현(추정)": arm_current_guess,
        "F1 제안안": arm_proposed,
    }

    print(f"{'arm':<22}" + "".join(f"{lab:>12}" for _, lab in DEPTHS) +
          f"{'가중 평균':>12}")
    print("─" * 84)

    for name, fn in subset.items():
        cells, weighted = [], 0.0
        for d, _ in DEPTHS:
            hit = total = 0
            for q, gold in PROBES:
                g = seq_of.get(gold)
                if g is None or g + d >= len(docs):
                    continue
                visible = docs[:g + d + 1]
                ext_v = [x for x in visible if x["planted_id"]]
                ctx = {"rng": random.Random(SEED), "ext": ext_v, "imp": imp,
                       "bm_all": BM25(visible, tok_bigram),
                       "bm_ext": BM25(ext_v, tok_bigram),
                       "bm_sess": BM25(ext_v, tok_bigram)}
                sel = fn(visible, q, gold, ctx) or []
                total += 1
                if gold in [x["planted_id"] for x in sel]:
                    hit += 1
            r = hit / total if total else 0.0
            cells.append(r)
            weighted += WEIGHTS[d] * r
        print(f"{name:<22}" + "".join(f"{c:>11.0%}" for c in cells) +
              f"{weighted:>12.0%}")

    print("─" * 84)
    print("  실험 3의 표는 '깊음' 열만 본 것이다. 그건 실제 대화의 5%에 불과하다.")
    print("  얕은 참조에서는 Window-only만으로 충분하고, 검색은 오히려 노이즈를 넣는다.")
    print("  → 게이팅이 필요한 이유가 여기서 나온다 (docs/adr/ADR-006).")
    print("\n  ⚠️ 가중치(75/20/5)는 docs/08 D1의 추정이다. 실제 로그로 대체해야 한다.")


def main():
    docs, ledger = load()
    rng = random.Random(SEED)
    ext = [d for d in docs if d["planted_id"]]

    # 세션 단위 청크
    sessions = {}
    for d in docs:
        sessions.setdefault(d["session"], []).append(d["text"])
    sess_docs = [{"text": " ".join(v), "planted_id": None,
                  "kind": "session", "session": k}
                 for k, v in sessions.items()]

    ctx = {
        "rng": rng,
        "ext": ext,
        "imp": importance_map(ledger),
        "bm_all": BM25(docs, tok_bigram),
        "bm_ext": BM25(ext, tok_bigram),
        "bm_sess": BM25(sess_docs, tok_bigram),
    }

    print(f"코퍼스 720턴 · 질문 {len(PROBES)}개 · 예산 {BUDGET}토큰 통제 "
          f"· 캐시 적중 {CACHE_HIT:.0%} 가정\n")
    print("─" * 88)
    print(f"{'arm':<22}{'evidence':>10}{'precision':>11}{'주입토큰':>10}"
          f"{'예산초과':>10}{'$/월':>9}{'입력$':>9}")
    print("─" * 88)

    results = {}
    for name, fn in ARMS.items():
        r = evaluate(name, fn, docs, ctx)
        over = "❌" if r["tokens"] + FIXED_BLOCKS > BUDGET else "✅"
        total, c_in = cost_per_month(r["tokens"])
        results[name] = (r, total)
        print(f"{name:<22}{r['recall']:>9.0%}{r['precision']:>11.0%}"
              f"{r['tokens']:>10.0f}{over:>9}{total:>9.2f}{c_in:>9.2f}")
    print("─" * 88)

    print("\n읽는 법")
    print("  evidence  정답 근거가 컨텍스트에 들어왔는가. 이게 응답 품질의 상한이다")
    print("  precision 주입된 기억 중 정답 근거의 비율. 낮으면 노이즈를 함께 넣은 것")
    print("  예산초과   ❌면 4,000토큰 통제를 못 지킨 것 — 공정 비교에서 탈락")

    print("\n관찰")
    a3 = results["A3 Random-K(5)"][0]["recall"]
    for name in ("C2 추출단위 RAG", "F1 제안안", "G1 현행 재현(추정)"):
        r = results[name][0]["recall"]
        verdict = "✅ 통과" if r > a3 else "❌ 위생검사 실패"
        print(f"  {name:<22} recall {r:.0%} vs Random-K {a3:.0%}  → {verdict}")
    print("\n  A0(Full-context)는 evidence 100%지만 예산을 30배 초과한다.")
    print("  A1(Oracle)은 이론적 상한 — 실제 arm과의 격차가 개선 여지다.")
    print("  A3(Random-K)를 못 이기는 arm은 검색이 작동하지 않는 것이다.")

    exp_depth(docs, ledger)

    print("\n⚠️ 이 실험이 말할 수 없는 것")
    print("  응답 품질 · 페르소나 유지 · L3(활용) 실패 — 전부 API 키가 필요하다.")
    print("  여기서 나오는 건 '품질의 상한'이지 품질이 아니다.")


if __name__ == "__main__":
    main()
