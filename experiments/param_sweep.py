"""
파라미터 스윕 — 내가 근거 없이 정한 값들을 실측으로 정당화하거나 고친다.

대상:
  τ  하드 게이트 임계 (importance < τ면 후보에서 제외)   ADR-005에서 0.2로 잡음
  k  주입 개수 상한                                      arm_proposed에서 5로 잡음
  N  최근 원문 윈도우 크기                                08 D1에서 10~15턴으로 잡음

전부 "그럴듯해 보여서" 고른 값이다. 스윕하면 정당화되거나 바뀐다.

측정:
  recall  참조 깊이 가중 (75/20/5) — 실험 4와 같은 방식
  noise   주입된 기억 중 정답이 아닌 것의 평균 개수 ← 낮을수록 좋다
          (precision을 쓰면 k가 커질수록 자동으로 떨어져 해석이 흐려진다)

실행: python experiments/gen_corpus.py && python experiments/param_sweep.py
"""

import json
import random
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retrieval_sim import BM25, tok_bigram, importance_map, PROBES  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "eval" / "corpus" / "corpus.jsonl"
LEDGER = ROOT / "eval" / "fact-ledger.yaml"

DEPTHS = [(5, 0.75), (30, 0.20), (300, 0.05)]   # (거리, 가중치) — docs/08 D1
SEED = 20260903


def retrieve(visible, q, imp, tau, k, theta):
    """ADR-005 수정판 4단계: 색인선별 → 하드게이트 → 가중정렬 → 임계컷."""
    ext = [d for d in visible if d["planted_id"]]
    if not ext:
        return []
    bm = BM25(ext, tok_bigram)
    raw = bm.score(q)
    mx = max(raw) or 1.0
    out = []
    for i, d in enumerate(ext):
        im = imp.get(d["planted_id"], 0.5)
        if im < tau:                          # 하드 게이트
            continue
        rel = raw[i] / mx
        s = 0.6 * rel + 0.4 * im              # 가중 정렬
        if rel < theta:                       # 임계 컷 (relevance 기여 요구)
            continue
        out.append((s, d))
    out.sort(key=lambda x: -x[0])
    return [d for _, d in out[:k]]


BUDGET = 4000          # docs/adr/ADR-009 통제 조건
FIXED_BLOCKS = 1370    # 페르소나·상태·요약 등 (docs/06 §5)


def ntok(t):
    return max(1, int(len(t) * 1.5))    # 한국어 ≈ 1.5토큰/글자


def evaluate(docs, imp, tau, k, theta, win):
    seq_of = {d["planted_id"]: i for i, d in enumerate(docs) if d["planted_id"]}
    w_recall = 0.0
    noise_tot = tok_tot = n_q = 0
    for dist, weight in DEPTHS:
        hit = tot = 0
        for q, gold in PROBES:
            g = seq_of.get(gold)
            if g is None or g + dist >= len(docs):
                continue
            visible = docs[:g + dist + 1]
            mem = retrieve(visible, q, imp, tau, k, theta)
            window = visible[-win:]
            ids = [d["planted_id"] for d in mem + window]
            tot += 1
            if gold in ids:
                hit += 1
            noise_tot += sum(1 for d in mem if d["planted_id"] != gold)
            tok_tot += sum(ntok(d["text"]) for d in mem + window)
            n_q += 1
        w_recall += weight * (hit / tot if tot else 0.0)
    n = max(n_q, 1)
    return w_recall, noise_tot / n, tok_tot / n


def sweep(docs, imp, name, values, build):
    print(f"\n{name}")
    print("─" * 76)
    print(f"{'값':<10}{'가중 recall':>13}{'노이즈/질의':>14}{'주입토큰':>11}{'예산':>8}")
    print("─" * 76)
    rows = []
    for v in values:
        r, nz, tk = evaluate(docs, imp, *build(v))
        ok = tk + FIXED_BLOCKS <= BUDGET
        rows.append((v, r, nz, tk, ok))
        print(f"{str(v):<10}{r:>12.0%}{nz:>14.2f}{tk:>11.0f}{'✅' if ok else '❌':>8}")
    print("─" * 76)
    return rows


def main():
    docs = [json.loads(l) for l in open(CORPUS, encoding="utf-8")]
    ledger = yaml.safe_load(open(LEDGER, encoding="utf-8"))
    imp = importance_map(ledger)

    BASE = dict(tau=0.2, k=5, theta=0.15, win=15)
    print("기준 구성: " + ", ".join(f"{a}={b}" for a, b in BASE.items()))
    r0, n0, t0 = evaluate(docs, imp, **BASE)
    print(f"기준 성능: 가중 recall {r0:.0%}, 노이즈 {n0:.2f}/질의, 주입 {t0:.0f}토큰")

    tau_rows = sweep(docs, imp, "τ — 하드 게이트 임계 (ADR-005에서 0.2로 잡음)",
                     [0.0, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5],
                     lambda v: (v, BASE["k"], BASE["theta"], BASE["win"]))

    k_rows = sweep(docs, imp, "k — 주입 개수 상한 (5로 잡음)",
                   [1, 2, 3, 5, 8, 12],
                   lambda v: (BASE["tau"], v, BASE["theta"], BASE["win"]))

    win_rows = sweep(docs, imp, "N — 최근 원문 윈도우 (10~15턴으로 잡음)",
                     [5, 10, 15, 25, 40],
                     lambda v: (BASE["tau"], BASE["k"], BASE["theta"], v))

    # ── 파레토 판정 ──────────────────────────────────────────────────
    print("\n" + "═" * 62)
    print("판정")

    def best(rows, label, unit=""):
        """예산을 지키면서, recall 손실 없이 노이즈가 가장 낮은 값."""
        feasible = [r for r in rows if r[4]] or rows
        top = max(r for _, r, _, _, _ in feasible)
        cand = [x for x in feasible if x[1] >= top - 0.005]
        v, r, n, t, ok = min(cand, key=lambda x: x[2])
        print(f"  {label:<24} {v}{unit:<3} (recall {r:.0%}, 노이즈 {n:.2f}, {t:.0f}토큰)")
        return v

    bt = best(tau_rows, "τ 하드 게이트 임계")
    bk = best(k_rows, "k 주입 개수")
    bw = best(win_rows, "N 윈도우 크기", "턴")

    print()
    for name, guess, found in (("τ", BASE["tau"], bt), ("k", BASE["k"], bk),
                               ("N", BASE["win"], bw)):
        mark = "✅ 추정 유지" if guess == found else f"🔄 {guess} → {found}"
        print(f"  {name}: {mark}")

    print("\n⚠️ 이 스윕을 신뢰하면 안 되는 지점")
    print("  · k: 질문마다 정답이 **정확히 1개**라 k=1이 자동으로 최적이 된다.")
    print("       평가 설계의 산물이지 발견이 아니다. 실제 대화는 여러 기억이 동시에 필요하다.")
    print("       → k는 이 실험으로 정할 수 없다. 품질 평가가 필요하다")
    print("  · τ: 0.15~0.4 구간이 사실상 평평하다(노이즈 1.12~1.23).")
    print("       '최적값'보다 '이 구간에서는 둔감하다'가 더 쓸모 있는 결론이다")
    print("  · N: 클수록 recall이 오르지만 토큰을 먹는다. 예산 제약이 실질 상한을 만든다")
    print("  · 표본이 작다 — 질문 10개, 추출 항목 27개")
    print("  · 깊이 가중치(75/20/5)가 추정이라, 바뀌면 최적 N이 크게 움직인다")


if __name__ == "__main__":
    main()
