"""
검색 실험 — 한국어 토큰화, evidence_recall@k, 빵 함정.

검증 대상:
  docs/03 FP-4   한국어 교착어 문제. 어절 단위 BM25가 왜 실패하는가
  docs/02 §0     "빵 유언" — 사소한 기억이 감정 어휘 때문에 끌려오는가
  docs/adr/ADR-005  importance 가중이 그걸 막는가
  docs/adr/ADR-006  임계 컷(0개 반환)의 효과

API 키 불필요. BM25는 어휘 통계이므로 로컬에서 완결된다.
※ dense 검색은 임베딩 모델이 필요해 여기 없다 — 하이브리드 비교는 다음 단계.

실행: python experiments/gen_corpus.py && python experiments/retrieval_sim.py
"""

import json
import math
import sys
from collections import Counter
from pathlib import Path

import yaml

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "eval" / "corpus" / "corpus.jsonl"
LEDGER = ROOT / "eval" / "fact-ledger.yaml"

K1, B = 1.5, 0.75


# ── 토큰화 ──────────────────────────────────────────────────────────────
def tok_eojeol(text):
    """어절(공백) 단위. 한국어는 교착어라 '나비가/나비를'이 다른 토큰이 된다."""
    return [w.strip(".,?!…~") for w in text.split() if w.strip(".,?!…~")]


def tok_bigram(text):
    """문자 bigram. 형태소 분석기가 없을 때의 실무적 대안(pg_bigm 등)."""
    s = "".join(text.split())
    return [s[i:i + 2] for i in range(len(s) - 1)] if len(s) > 1 else [s]


def tok_hybrid(text):
    return tok_eojeol(text) + tok_bigram(text)


TOKENIZERS = {
    "어절(공백)": tok_eojeol,
    "문자 bigram": tok_bigram,
    "어절+bigram": tok_hybrid,
}


# ── BM25 ────────────────────────────────────────────────────────────────
class BM25:
    def __init__(self, docs, tokenizer):
        self.tokenizer = tokenizer
        self.docs = docs
        self.toks = [tokenizer(d["text"]) for d in docs]
        self.lens = [len(t) for t in self.toks]
        self.avgdl = sum(self.lens) / max(len(self.lens), 1)
        self.tfs = [Counter(t) for t in self.toks]
        df = Counter()
        for t in self.toks:
            df.update(set(t))
        N = len(docs)
        self.idf = {w: math.log(1 + (N - n + 0.5) / (n + 0.5))
                    for w, n in df.items()}

    def score(self, query):
        q = self.tokenizer(query)
        out = []
        for i, tf in enumerate(self.tfs):
            s = 0.0
            dl = self.lens[i]
            for w in q:
                if w not in tf:
                    continue
                f = tf[w]
                s += self.idf.get(w, 0) * f * (K1 + 1) / (
                    f + K1 * (1 - B + B * dl / self.avgdl))
            out.append(s)
        return out

    def topk(self, query, k=5, weights=None):
        s = self.score(query)
        if weights:
            s = [x * weights[i] for i, x in enumerate(s)]
        order = sorted(range(len(s)), key=lambda i: -s[i])[:k]
        return [(self.docs[i], s[i]) for i in order if s[i] > 0]


def load():
    docs = [json.loads(l) for l in open(CORPUS, encoding="utf-8")]
    ledger = yaml.safe_load(open(LEDGER, encoding="utf-8"))
    return docs, ledger


# ── 실험 1: 토큰화별 evidence_recall@k ──────────────────────────────────
# 질문 → 정답 근거의 planted_id
PROBES = [
    ("우리 고양이 이름 뭐였지",           "F001"),
    ("나 지금 무슨 일 하지",               "F021"),
    ("나 커피 마셔도 되나",                "F003"),
    ("나 동생 있다고 했었나",              "F004"),
    ("나비 아팠던 거 기억나",              "E007"),
    ("우리 다퉜던 거",                     "E008"),
    ("이직 준비 시작한다고 했었지",        "E003"),
    ("최종 합격했다고 했잖아",             "E009"),
    ("그 카페 같이 가기로 했잖아",         "D001"),
    ("면접 결과 말해준다고 했었지",        "D002"),
]


def exp1(docs):
    print("\n실험 1 — 한국어 토큰화별 evidence_recall@k (BM25, 720턴)")
    print("─" * 74)
    print(f"{'토큰화':<16}{'recall@1':>11}{'recall@5':>11}{'recall@10':>11}{'평균 순위':>12}")
    print("─" * 74)
    for name, tk in TOKENIZERS.items():
        bm = BM25(docs, tk)
        hits = {1: 0, 5: 0, 10: 0}
        ranks = []
        for q, gold in PROBES:
            s = bm.score(q)
            order = sorted(range(len(s)), key=lambda i: -s[i])
            rank = next((r + 1 for r, i in enumerate(order)
                         if docs[i]["planted_id"] == gold), None)
            if rank:
                ranks.append(rank)
                for k in hits:
                    if rank <= k:
                        hits[k] += 1
            else:
                ranks.append(len(docs))
        n = len(PROBES)
        avg = sum(ranks) / n
        print(f"{name:<16}{hits[1]/n:>10.0%}{hits[5]/n:>11.0%}"
              f"{hits[10]/n:>11.0%}{avg:>12.1f}")
    print("─" * 74)
    print("  어절 단위는 '이름은' vs '이름'이 매칭되지 않는다 — 교착어 문제(docs/03 FP-4).")
    print("  형태소 분석기(nori)가 없으면 문자 bigram이 실무적 대안이다.")


# ── 실험 2: 빵 함정 ────────────────────────────────────────────────────
def importance_map(ledger):
    imp = {}
    for f in ledger.get("facts", []):
        imp[f["id"]] = f.get("importance", 0.5)
    for e in ledger.get("events", []):
        imp[e["id"]] = e.get("emotional_weight", 0.5)
    for d in ledger.get("debts", []):
        imp[d["id"]] = d.get("emotional_stake", 0.5)
    return imp


def exp2(docs, ledger):
    """
    쓰기 정책이 색인 전에 무엇을 거르는가 (docs/adr/ADR-005).

    W1 전부 색인   : 원문 720턴 전부를 검색 대상으로
    W3 추출만 색인 : 사실·사건·부채로 추출된 것만 (20개)
    W3+importance  : 거기에 쓰기 시점 importance 가중까지
    """
    print("\n실험 2 — 쓰기 정책이 오주입에 미치는 영향 (docs/adr/ADR-005)")
    print("─" * 74)

    imp = importance_map(ledger)
    extracted = [d for d in docs if d["planted_id"]]
    w_ext = [imp.get(d["planted_id"], 0.5) for d in extracted]

    bm_all = BM25(docs, tok_bigram)
    bm_ext = BM25(extracted, tok_bigram)

    queries = [
        ("S19 나비 응급실", "나비가 아파서 너무 무섭고 아쉽고 마지막일까봐"),
        ("S24 엔딩",        "마지막이라 아쉬워 더 하고 싶었는데"),
        ("평범한 잡담",      "오늘 날씨 좋다 뭐하고 지내"),
    ]

    print(f"{'쿼리':<16}{'구성':<24}{'유효 주입':>10}{'트랩':>8}{'노이즈':>8}")
    print("─" * 74)
    for label, q in queries:
        configs = [
            ("W1 전부 색인", bm_all, None),
            ("W3 추출만 색인", bm_ext, None),
            ("W3 + importance", bm_ext, w_ext),
        ]
        for i, (name, bm, w) in enumerate(configs):
            hits = bm.topk(q, k=5, weights=w)
            trap = any(d["planted_id"] == "F007_TRAP" for d, _ in hits)
            noise = sum(1 for d, _ in hits if not d["planted_id"])
            useful = sum(1 for d, _ in hits if d["planted_id"]
                         and d["planted_id"] != "F007_TRAP")
            print(f"{label if i == 0 else '':<16}{name:<24}"
                  f"{useful}/5{'':>6}{'❌' if trap else '✅':>7}{noise}/5{'':>4}")
        print()
    print("─" * 74)
    print("  W1(전부 색인)은 top-5가 잡담으로 채워진다 — 검색기가 노이즈를 이길 수 없다.")
    print("  '저장은 예스, 색인은 선별' — 색인 안 한 것은 오주입될 수 없다 (docs/03 FP-8).")


# ── 실험 3: 임계 컷 (0개 반환) ─────────────────────────────────────────
def exp2b(docs, ledger):
    """
    importance를 relevance와 어떻게 결합할 것인가.

    docs/adr/ADR-005는 곱셈(score = rel × imp)을 전제했다.
    Generative Agents 원논문은 덧셈(α_rel·rel + α_imp·imp)이다.
    셋째 선택지는 하드 필터(imp < τ면 후보에서 제외).
    """
    print("\n실험 2b — importance 결합 방식 (docs/adr/ADR-005 수식 검증)")
    print("─" * 74)

    imp = importance_map(ledger)
    ext = [d for d in docs if d["planted_id"]]
    bm = BM25(ext, tok_bigram)
    q = "마지막이라 아쉬워 더 하고 싶었는데"
    raw = bm.score(q)
    mx = max(raw) or 1.0
    norm = [r / mx for r in raw]                       # 0~1 정규화
    imps = [imp.get(d["planted_id"], 0.5) for d in ext]

    modes = {
        "곱셈  rel × imp":        [n * i for n, i in zip(norm, imps)],
        "덧셈  rel + imp":        [n + i for n, i in zip(norm, imps)],
        "하드필터 imp<0.2 제외":   [n if i >= 0.2 else -1 for n, i in zip(norm, imps)],
    }

    print(f'  쿼리: "{q}"')
    print(f'  트랩(F007_TRAP)의 정규화 relevance: '
          f'{norm[[d["planted_id"] for d in ext].index("F007_TRAP")]:.2f}, '
          f'importance: 0.05')
    print()
    print(f"{'결합 방식':<26}{'트랩 순위':>12}{'top-3 항목':>34}")
    print("─" * 74)
    for name, s in modes.items():
        order = sorted(range(len(s)), key=lambda i: -s[i])
        rank = next(r + 1 for r, i in enumerate(order)
                    if ext[i]["planted_id"] == "F007_TRAP")
        top3 = ", ".join(ext[i]["planted_id"] for i in order[:3] if s[i] > 0)
        mark = "❌" if rank <= 5 else "✅"
        print(f"{name:<26}{mark} {rank:>2}위{'':>5}{top3:>34}")
    print("─" * 74)
    print("  곱셈은 relevance가 압도적이면 importance 0.05를 곱해도 살아남는다.")
    print("  → ADR-005의 가중합 수식을 '곱셈'이 아니라 '덧셈 + 하드 필터'로 고쳐야 한다.")


def exp3(docs):
    print("\n실험 3 — 임계 컷의 효과 (docs/adr/ADR-006 '0개 반환 허용')")
    print("─" * 74)
    bm = BM25(docs, tok_bigram)

    # 장기기억이 필요 없는 평범한 턴 — 여기서 뭔가 나오면 오주입이다
    idle = ["오늘 날씨 좋다", "밥 먹었어?", "뭐해", "피곤하다", "잘 자"]
    # 장기기억이 필요한 턴
    need = [q for q, _ in PROBES]

    print(f"{'임계값':<10}{'평범한 턴 주입률':>18}{'필요한 턴 회수율':>18}")
    print("─" * 74)
    for th in (0.0, 2.0, 4.0, 6.0, 8.0):
        idle_inj = sum(1 for q in idle if bm.topk(q, 5) and
                       bm.topk(q, 5)[0][1] > th) / len(idle)
        need_hit = sum(1 for q in need if bm.topk(q, 5) and
                       bm.topk(q, 5)[0][1] > th) / len(need)
        print(f"{th:<10.1f}{idle_inj:>17.0%}{need_hit:>18.0%}")
    print("─" * 74)
    print("  top-k는 관련 없어도 항상 k개를 준다 — 그게 '빵을 유언으로' 만든다.")
    print("  임계 컷은 평범한 턴에서 0개를 반환할 수 있게 한다.")


def main():
    docs, ledger = load()
    print(f"코퍼스: {len(docs)}턴 "
          f"(심은 항목 {sum(1 for d in docs if d['planted_id'])}개)")
    exp1(docs)
    exp2(docs, ledger)
    exp2b(docs, ledger)
    exp3(docs)
    print("\n※ 한계: dense 검색이 없어 하이브리드 비교가 빠져 있다.")
    print("  로컬 임베딩(KURE) 도입 시 FP-4의 '고유명사는 BM25, 의역은 dense' 주장을 검증할 수 있다.")


if __name__ == "__main__":
    main()
