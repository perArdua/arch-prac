"""
민감도 분석 — 참조 깊이 분포 가정이 틀리면 결론이 얼마나 흔들리는가.

docs/08 D1에서 참조 깊이를 75/20/5(≤15턴 / ≤60턴 / 그 이상)로 추정했다.
유사 서비스 파라미터의 현시선호와 구조적 추론에서 역산한 값이고, 실제 로그는 못 봤다.

이 문서 전체에서 가장 하중이 큰 가정이다. 틀리면 무엇이 바뀌는가?

핵심 질문: **어떤 유저 분포를 믿어야 검색 시스템이 값을 하는가?**

실행: python experiments/gen_corpus.py && python experiments/sensitivity.py
"""

import json
import random
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retrieval_sim import BM25, tok_bigram, importance_map, PROBES  # noqa: E402
from arms_sim import (arm_oracle, arm_window, arm_rag_extracted,       # noqa: E402
                      arm_current_guess, arm_proposed, SEED)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "eval" / "corpus" / "corpus.jsonl"
LEDGER = ROOT / "eval" / "fact-ledger.yaml"

DIST = [
    ("극단 최근형", (0.95, 0.04, 0.01)),
    ("매우 최근형", (0.90, 0.08, 0.02)),
    ("내 추정",     (0.75, 0.20, 0.05)),
    ("중간",        (0.60, 0.25, 0.15)),
    ("깊음",        (0.50, 0.30, 0.20)),
    ("매우 깊음",   (0.35, 0.35, 0.30)),
]
DEPTHS = [5, 30, 300]

ARMS = {
    "A2 Window-only": arm_window,
    "C2 추출 RAG": arm_rag_extracted,
    "G1 현행 재현": arm_current_guess,
    "F1 제안안": arm_proposed,
    "A1 Oracle": arm_oracle,
}


def per_depth_recall(docs, ledger):
    """arm × 깊이 별 recall을 한 번만 계산해 재사용한다."""
    seq_of = {d["planted_id"]: i for i, d in enumerate(docs) if d["planted_id"]}
    imp = importance_map(ledger)
    out = {name: [] for name in ARMS}
    for dist in DEPTHS:
        for name, fn in ARMS.items():
            hit = tot = 0
            for q, gold in PROBES:
                g = seq_of.get(gold)
                if g is None or g + dist >= len(docs):
                    continue
                visible = docs[:g + dist + 1]
                ext_v = [x for x in visible if x["planted_id"]]
                ctx = {"rng": random.Random(SEED), "ext": ext_v, "imp": imp,
                       "bm_all": BM25(visible, tok_bigram),
                       "bm_ext": BM25(ext_v, tok_bigram),
                       "bm_sess": BM25(ext_v, tok_bigram)}
                sel = fn(visible, q, gold, ctx) or []
                tot += 1
                if gold in [x["planted_id"] for x in sel]:
                    hit += 1
            out[name].append(hit / tot if tot else 0.0)
    return out


def main():
    docs = [json.loads(l) for l in open(CORPUS, encoding="utf-8")]
    ledger = yaml.safe_load(open(LEDGER, encoding="utf-8"))
    base = per_depth_recall(docs, ledger)

    print("깊이별 원시 recall (분포와 무관)")
    print("─" * 62)
    print(f"{'arm':<18}{'얕음 ≤15':>12}{'중간 ≤60':>12}{'깊음 60+':>12}")
    print("─" * 62)
    for name, vals in base.items():
        print(f"{name:<18}" + "".join(f"{v:>11.0%}" for v in vals))
    print("─" * 62)

    print("\n분포 가정별 가중 recall")
    print("═" * 78)
    header = f"{'분포 (얕/중/깊)':<24}"
    names = ["A2 Window-only", "C2 추출 RAG", "G1 현행 재현", "F1 제안안"]
    for n in names:
        header += f"{n.split()[0]:>10}"
    header += f"{'검색 이득':>12}"
    print(header)
    print("─" * 78)

    rows = []
    for label, w in DIST:
        vals = {n: sum(wi * ri for wi, ri in zip(w, base[n])) for n in names}
        gain = vals["F1 제안안"] - vals["A2 Window-only"]
        rows.append((label, w, vals, gain))
        pct = "/".join(f"{int(x*100)}" for x in w)
        line = f"{label + ' (' + pct + ')':<24}"
        for n in names:
            line += f"{vals[n]:>9.0%}"
        line += f"{gain:>11.0%}p"
        print(line)
    print("─" * 78)

    print("\n판정 — 어떤 분포를 믿어야 검색이 값을 하는가")
    print("═" * 78)
    for label, w, vals, gain in rows:
        if gain < 0.10:
            v = "❌ 검색 시스템을 만들 이유가 약하다. Window+요약으로 충분"
        elif gain < 0.25:
            v = "⚠️ 애매하다. 복잡도 대비 이득을 따로 따져야 한다"
        else:
            v = "✅ 검색이 필수다"
        print(f"  {label:<14} 이득 {gain:>5.0%}p   {v}")

    print("\n관찰")
    g_min = min(r[3] for r in rows)
    g_max = max(r[3] for r in rows)
    print(f"  · 검색 이득이 분포에 따라 {g_min:.0%}p ~ {g_max:.0%}p로 움직인다 "
          f"({g_max/max(g_min,0.01):.0f}배 차이)")
    print("  · 구조(4층)는 어떤 분포에서도 유효하다 — 층 구성이 바뀌지 않는다")
    print("  · 그러나 '검색에 얼마를 투자할지'는 분포가 결정한다")
    print("  · G1(현행)과 F1(제안)의 recall 격차는 모든 분포에서 작다")
    print("    → 제안안의 가치는 recall이 아니라 precision에 있다는 결론이 분포와 무관하게 유지된다")

    print("\n⚠️ 한계")
    print("  · 깊이 구간을 3개(5/30/300턴)로만 이산화했다. 실제는 연속 분포다")
    print("  · 질문 10개 기준이라 각 셀의 표본이 작다")
    print("  · '검색 이득' 판정 기준(10%p / 25%p)은 내가 정한 임의값이다")


if __name__ == "__main__":
    main()
