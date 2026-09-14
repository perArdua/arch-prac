"""
하이브리드 검색 실험 — BM25 vs Dense vs 결합.

검증 대상: docs/03 FP-4
  주장: "임베딩은 분포 의미론으로 학습되므로 고유명사의 지시체를 못 담는다.
        특정 문자열에 특정 지시체를 묶는 유일한 방법은 어휘적 정확 매칭이다.
        그리고 롤플레이는 고유명사 밀도가 비정상적으로 높다.
        → 하이브리드는 일반론이 아니라 도메인적으로 강제된다."

이 주장을 제대로 검증하려면 프로브를 두 종류로 나눠야 한다:
  lexical    고유명사·정확 문자열을 쓰는 질의   → BM25가 이겨야 함
  paraphrase 같은 뜻을 다른 말로 쓰는 질의      → Dense가 이겨야 함
한 종류만 보면 어느 쪽으로든 원하는 결론이 나온다.

⚠️ 모델: intfloat/multilingual-e5-small (~470MB).
   docs/04 §3.3이 권한 KURE(BGE-M3 기반, ~2.2GB)가 아니다.
   한국어 특화 모델이면 dense 성능이 더 좋을 수 있다 — 이 결과는 하한으로 읽어야 한다.

실행: python experiments/gen_corpus.py && python experiments/hybrid_sim.py
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retrieval_sim import BM25, tok_bigram  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "eval" / "corpus" / "corpus.jsonl"
MODEL = "intfloat/multilingual-e5-small"

# ── 프로브: 어휘형 vs 의역형 ────────────────────────────────────────────
# 어휘형 — 고유명사·정확 문자열이 질의에 그대로 등장한다
LEXICAL = [
    ("나비",                         "F001"),
    ("나비 아팠던 거",                "E007"),
    ("크로와상",                      "F007_TRAP"),
    ("스타트업 이직",                 "F021"),
    ("카페인",                        "F003"),
]
# 의역형 — 같은 뜻을 다른 어휘로. 표면 일치가 거의 없다
PARAPHRASE = [
    ("우리 집 반려묘 이름이 뭐였지",    "F001"),
    ("우리 애가 병원 갔던 날",         "E007"),
    ("새 직장으로 옮긴 거",            "F021"),
    ("나 각성 음료 못 마시잖아",       "F003"),
    ("우리 크게 말다툼했던 거",        "E008"),
]


def rrf(rank_lists, k=60):
    """Reciprocal Rank Fusion. 점수 스케일이 다른 검색기를 결합하는 표준 방법."""
    scores = {}
    for ranks in rank_lists:
        for r, idx in enumerate(ranks):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + r + 1)
    return sorted(scores, key=lambda i: -scores[i])


def rank_of(order, docs, gold):
    for r, i in enumerate(order):
        if docs[i]["planted_id"] == gold:
            return r + 1
    return len(docs)


def main():
    from sentence_transformers import SentenceTransformer

    docs = [json.loads(l) for l in open(CORPUS, encoding="utf-8")]
    ext = [d for d in docs if d["planted_id"]]
    print(f"검색 대상: 추출 항목 {len(ext)}개 (docs/06 §3.1의 카디널리티 가정)")

    print(f"모델 로딩: {MODEL}")
    model = SentenceTransformer(MODEL)

    # e5 계열은 prefix가 필요하다
    emb = model.encode([f"passage: {d['text']}" for d in ext],
                       normalize_embeddings=True, show_progress_bar=False)
    bm = BM25(ext, tok_bigram)

    def dense_order(q):
        qv = model.encode([f"query: {q}"], normalize_embeddings=True)[0]
        sims = emb @ qv
        return list(np.argsort(-sims))

    def bm25_order(q):
        s = bm.score(q)
        return sorted(range(len(ext)), key=lambda i: -s[i])

    for label, probes in (("어휘형 (고유명사·정확 문자열)", LEXICAL),
                          ("의역형 (같은 뜻, 다른 어휘)", PARAPHRASE)):
        print(f"\n{label}")
        print("─" * 76)
        print(f"{'질의':<26}{'BM25':>10}{'Dense':>10}{'Hybrid':>10}{'승자':>14}")
        print("─" * 76)
        agg = {"BM25": [], "Dense": [], "Hybrid": []}
        for q, gold in probes:
            bo, do = bm25_order(q), dense_order(q)
            ho = rrf([bo, do])
            rb, rd, rh = (rank_of(bo, ext, gold), rank_of(do, ext, gold),
                          rank_of(ho, ext, gold))
            agg["BM25"].append(rb)
            agg["Dense"].append(rd)
            agg["Hybrid"].append(rh)
            win = "BM25" if rb < rd else ("Dense" if rd < rb else "동률")
            print(f"{q:<26}{rb:>10}{rd:>10}{rh:>10}{win:>14}")
        print("─" * 76)
        line = "  평균 순위".ljust(26)
        for k in ("BM25", "Dense", "Hybrid"):
            line += f"{np.mean(agg[k]):>10.1f}"
        print(line)
        for k in ("BM25", "Dense", "Hybrid"):
            top3 = sum(1 for r in agg[k] if r <= 3) / len(probes)
            print(f"  {k:<10} recall@3 = {top3:.0%}")

    print("\n" + "═" * 76)
    print("판정 기준 (docs/03 FP-4)")
    print("  주장이 참이면: 어휘형에서 BM25 우세, 의역형에서 Dense 우세,")
    print("                 그리고 Hybrid가 양쪽에서 안정적이어야 한다.")
    print("  주장이 거짓이면: 한쪽이 양쪽 다 이긴다 → 하이브리드가 불필요하다.")
    print("\n⚠️ 한계: 경량 다국어 모델(e5-small)이다. 한국어 특화 KURE면 dense가 더 셀 수 있다.")
    print("  추출 항목이 22개뿐이라 순위 변별력도 약하다. 방향성만 읽어야 한다.")


if __name__ == "__main__":
    main()
