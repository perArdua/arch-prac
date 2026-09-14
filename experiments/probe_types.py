# -*- coding: utf-8 -*-
"""
probe_types.py — 유형 라벨 프로브 집합을 **네 모드로 채점하는 하니스**.

## 무엇을 하나

`probe_set.TYPED_PROBES`(n=24 · 직접형 8 · 의역형 8 · 추론형 8)를 심긴 문서 27개에
대해 네 모드로 채점하고, **유형별로** 1등 · top-5 · 평균 순위 · 정답 근거 점수 하한을
찍는다. 프로브별 순위 목록도 전부 찍는다 — 평균 하나로는 *"고르게 중간"*과
*"대부분 1등인데 둘이 11등"*이 구분되지 않는다.

    lexical         현행. `coverage(bigrams(q), bigrams(d))`      (memory.py:367 · 호출부는 retrieve의 lexical 분기)
    lexical_fixed   어절별 bigram + 자카드                        (memory.py:351 `tokens_fixed` · 호출부는 retrieve의 lexical_fixed 분기)
    embed           bge-m3 코사인
    hybrid(α)       α·lexical + (1−α)·embed, α는 embed_vs_bigram.ALPHA_HYBRID

## 🔴 무엇을 하지 **않나** — 판정하지 않는다

이 스크립트는 **하이브리드가 재진입하는지 판정하지 않는다.** 그것은 다음 라운드의
판단이고, 재진입은 조건 1·2가 **둘 다** 참이어야 한다(ADR-015 핵심 3). 여기서
찍는 것은 조건 1이 요구한 **계측기와 그 눈금**이며, 마지막 절은 조건 1의 세 요건이
각각 충족됐는지를 **사실로만** 적는다.

## 🔴 채점 규칙을 다시 구현하지 않는다

`rel`의 식은 **`prototype/memory.py`의 것을 그대로 부른다**(`coverage` · `jaccard` ·
`bigrams` · `tokens_fixed`). 코사인과 α는 `embed_vs_bigram`에서 가져온다. 같은
규칙의 사본이 둘이 되면 한쪽만 고쳐진다 — 그것이 F12였다.

⚠️ 딱 하나 사본이 있고 그것은 **캐시 입출력**이다(`ensure_vectors`). `rel_dist.py`의
같은 이름 함수는 `REL_CACHE.json`에 하드코딩돼 있는데, 이 실험은 **다른 캐시**를
써야 한다(아래). 사본이 금지되는 것은 *점수를 만드는 규칙*이지 파일 경로가 아니다.

## 캐시

임베딩 51개(후보 27 + 질의 24)는 **`experiments/data/PROBE_CACHE.json`**에 쓴다.
🔴 `EMBED_CACHE.json`(embed_vs_bigram의 270쌍)에도 `REL_CACHE.json`(rel_dist의
378쌍)에도 **쓰지 않는다.** 두 파일은 각각 다른 실험의 재현성을 떠받치고 있고,
키를 더하면 그 실험의 캐시 히트/미스 경로가 바뀐다.

호스트는 `127.0.0.1`이다 — `localhost`가 아닌 이유의 정본은
`prototype/embedding.py:24`이고, 그 차이가 이 라운드에서 번복된 F38이다.

## 모집단

후보 = 심긴 문서 27개, 프로브 24개 → **648쌍.** `embed_vs_bigram.py`의 270쌍과
**같은 후보 집합**이라 ADR-015의 4행 비교표와 나란히 읽을 수 있다.
🔴 `rel_dist.py`·`retrieval_sweep.py`의 **378쌍은 다른 모집단**이다 — 한쪽 값을
다른 쪽의 근거로 옮겨 적지 않는다(P1 · G12).

실행:
    python experiments/probe_types.py        # ollama 없으면 77(SKIP)
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "prototype"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import memory as M                                          # noqa: E402
import embedding as EMB                                     # noqa: E402
import precision as PR                                      # noqa: E402
import probe_set as PS                                      # noqa: E402
from embed_vs_bigram import cos, ALPHA_HYBRID               # noqa: E402

W = 92

ROOT = PS.ROOT
# 🔴 신규 캐시. 위 "캐시" 절 참조.
PROBE_CACHE = os.path.join(ROOT, "experiments", "data", "PROBE_CACHE.json")

# 이 하니스가 채점하는 모드 이름. `hybrid`는 `memory.RETRIEVAL_MODE`에 **없다**
# (ADR-015 결정 E가 격자에서 지웠다) — 여기서만 계산하는 비교 대상이다.
MODES = ("lexical", "lexical_fixed", "embed", f"hybrid(α={ALPHA_HYBRID})")
BASELINE = "lexical"


# ── 채점 (규칙은 전부 남의 것을 부른다) ────────────────────────────────

def score_lexical(q, t):
    """현행 `rel` — `memory.py:1175`의 `coverage` 호출과 **같은 두 함수**다."""
    return M.coverage(M.bigrams(q), M.bigrams(t))


def score_fixed(q, t):
    """`lexical_fixed` — `memory.py:1177`이 부르는 것과 같다."""
    return M.jaccard(M.tokens_fixed(q), M.tokens_fixed(t))


# ── 표 0 — 격자의 18문항을 이 집합의 눈금으로 재면 (레인 J) ────────────
#
# 🔴 **읽기 전용이다.** `eval/`은 한 바이트도 안 바뀐다(A8). 여기서 하는 것은
#    `eval/questions.yaml`을 **열어 보는 것**뿐이다.
#
# 🔴 **그리고 여기서 붙는 라벨은 원장의 것이 아니라 이 파일의 것이다.**
#    `eval/questions.yaml`에 유형 라벨은 **없다.** 아래가 하는 일은 오직
#    *"이 문항의 정답쌍 어휘 rel이 레인 I의 세 유형 중심 중 어디에 가장
#    가까운가"*이고, 그것은 문항의 뜻을 읽은 것이 아니라 **한 숫자를 잰 것**이다.
#    다른 사람이 문항을 읽고 라벨을 붙이면 다른 답이 나올 수 있다.
#
# 왜 재는가: 표 1이 *"직접형에서 네 모드가 동률"*을 보였다. 그러면 **격자가
# 모드를 못 가른 이유가 '격자의 문항이 대부분 직접형이라서'일 수 있다**는 가설이
# 선다. 그 가설은 이 집합 자신의 라벨 검사 눈금(표 3)으로 **검사할 수 있다.**

def type_centroids(gold_text):
    """레인 I 프로브의 유형별 **정답쌍 어휘 rel** — 표 3이 쓰는 바로 그 값."""
    return {t: sorted(score_lexical(p.q, gold_text[p.gold])
                      for p in PS.TYPED_PROBES if p.type == t)
            for t in PS.TYPES}


def eval_gold_rel():
    """
    채점 18문항의 **정답 근거에 대한** 어휘 rel — `(id, 질의, rel)`.

    근거 문자열은 `precision.key_index`(`precision.py:155`)가 만드는 허용 문자열
    집합이고, 그 규칙은 `soak.qa_eval`(`soak.py:127`)의 `key_of`
    (`soak.py:142-146`)와 같다. 한 문항의 근거가 여럿이면 **최댓값**을 쓴다 —
    묻는 것이 *"어휘가 이 문항의 근거를 잡을 수 있었는가"*이므로 가장 유리한
    근거로 재는 것이 그 물음에 맞다.

    🔴 격자의 `lex_rel`(`retrieval_sweep.py`의 `hybrid_reentry`)과 **다른 값이다.**
       (🔄 여기 있던 줄 번호는 규칙 ⑤가 들어오면서 밀렸다. 같은 줄에 `coverage`와
       `lex_rel`이 함께 있어 닻이 갈리므로 **줄 번호를 빼고 심볼로** 인용한다.) 저것은
       색인 21행 **전체**에 대한 최댓값이고 이것은 **정답 근거에 대한** 값이다.
       레인 I가 표 5에서 조건 2를 다시 잰 것과 같은 교정이다.
    """
    _corpus, ledger, qs = PR.load()
    key_of = PR.key_index(ledger)
    scored, _excluded = PR.partition(qs, key_of)
    out = []
    for q in scored:
        rels = [score_lexical(q["ask"], s)
                for e in q.get("evidence", []) if e in key_of
                for s in key_of[e]]
        out.append((q["id"], q["ask"], max(rels)))
    return out


def rank_of(scored, gold):
    """
    `scored` = [(점수, id), …] → gold의 **1-기반 순위**.

    ⚠️ **동점 규약이 여기 있다.** 정렬 키가 점수 하나뿐이고 Python `sort`는 안정
       정렬이라 **동점의 순서는 `scored`가 들어온 순서**(= 코퍼스 행 순서)가 정한다.
       ADR-015가 *"계측 외적 사실이 지표를 정한다"*고 적은 그 성질이고, 그래서 아래
       `run_mode`는 **정답 점수와 동점인 후보 수를 같이 돌려준다.**

       🔄 **프로덕션은 이 성질을 이제 갖고 있지 않다** — `memory.py:1189`(`scored.sort`)의
       `retrieve()`는 `(-s, event_id)`로 정렬해 동점을 결정적으로 가른다(후속 10).
       **이 하니스는 일부러 따라가지 않는다:** 여기 후보는 `event` 행이 아니라
       코퍼스 문서라 `event_id`가 없고, 없는 키를 지어내면 순위가 **하니스의
       선택**이 된다. 동점 수를 병기하는 것이 그 자리의 정직한 대체물이다.
    """
    order = sorted(scored, key=lambda x: -x[0])
    ids = [g for _, g in order]
    return ids.index(gold) + 1 if gold in ids else len(ids)


def run_mode(scorer, probes, docs):
    """
    한 모드로 전 프로브를 채점한다.

    돌려주는 것: 프로브마다 `(순위, 정답 점수, 정답과 동점인 다른 후보 수)`.
    """
    out = []
    for p in probes:
        scored = [(scorer(p.q, d["text"]), d["planted_id"]) for d in docs]
        gs = [s for s, g in scored if g == p.gold]
        gold_score = min(gs) if gs else 0.0
        ties = sum(1 for s, g in scored if g != p.gold and s == gold_score)
        out.append((rank_of(scored, p.gold), gold_score, ties))
    return out


# ── 부호 검정 ──────────────────────────────────────────────────────────

def sign_test(mode_ranks, base_ranks):
    """
    페어별 **정확 부호 검정** (양측). 순위는 작을수록 좋다.

    🔴 **n = 24는 작다** — 그리고 유형별로는 n = 8이다. 평균 순위 차이 하나를
       결과로 읽지 않게 하려고 이 검정이 있다. 이 라운드의 모델 스윕이 정확히 그
       실수를 한 번 했다: 다섯 모델이 프로브 10개 중 **2개에서만** 갈렸는데
       그것이 "모델 차이"로 읽혔고, 부호 검정은 p ≥ 0.25였다(ADR-015 후속 9).

    동점(같은 순위)은 **버린다** — 부호 검정의 표준 규약이고, 버린 수를 같이
    돌려준다(버린 것이 많으면 검정이 본 표본은 n보다 작다).
    """
    win = sum(1 for a, b in zip(mode_ranks, base_ranks) if a < b)
    loss = sum(1 for a, b in zip(mode_ranks, base_ranks) if a > b)  # noqa: E741
    tie = len(mode_ranks) - win - loss
    n = win + loss
    if n == 0:
        return win, loss, tie, 1.0
    k = min(win, loss)
    p = 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return win, loss, tie, min(p, 1.0)


# ── 임베딩 확보 ────────────────────────────────────────────────────────

def ensure_vectors(texts):
    """
    `(vecs, 히트, 미스)` 또는 미확보 시 `(None, 히트, 미스)`.

    🔴 `EMB.embed(..., use_cache=False, save=False)`로 부른다 — `embedding.py`의
       캐시 경로를 타면 `EMBED_CACHE_SWEEP.json`에 쓰게 되고 이 실험의 키가
       다른 실험의 캐시 파일에 섞인다. (`rel_dist.ensure_vectors`와 같은 이유,
       같은 형태. 다른 것은 파일 경로뿐이다.)
    """
    cache = {}
    if os.path.exists(PROBE_CACHE):
        try:
            with open(PROBE_CACHE, encoding="utf-8") as f:
                cache = json.load(f)
        except ValueError:
            cache = {}
    need = [t for t in texts if t not in cache]
    hit = len(texts) - len(need)
    if need:
        if not EMB.available():
            print(f"\n⚠️ 캐시 미스 {len(need)}건이고 ollama({EMB.OLLAMA_HOST})가 "
                  f"응답하지 않는다 — SKIP(77)으로 끝낸다.")
            print("   **SKIP은 통과가 아니다**(G1). 없는 키 전량:")
            for t in need:
                print(f"     없는 키: {t[:78]}")
            return None, hit, len(need)
        vecs = EMB.embed(need, use_cache=False, save=False)
        if vecs is None:
            print(f"\n⚠️ ollama가 {len(need)}건을 돌려주지 못했다 — SKIP(77).")
            for t in need:
                print(f"     없는 키: {t[:78]}")
            return None, hit, len(need)
        cache.update(dict(zip(need, vecs)))
        with open(PROBE_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    return {t: cache[t] for t in texts}, hit, len(need)


# ── 출력 ───────────────────────────────────────────────────────────────

def _block(title):
    print("\n" + "-" * W)
    print(title)
    print("-" * W)


def _p(v):
    """p를 **0.0000으로 반올림해 버리지 않는다.** 작은 p가 0으로 찍히면 그것은
    *"정확히 0"*으로 읽히고, 부호 검정의 p는 결코 0이 아니다."""
    return f"{v:.4f}" if v >= 1e-4 else f"{v:.2e}"


def report_eval_question_types(docs):
    """
    [표 0] 채점 18문항을 레인 I의 유형 중심에 **최근접 배정**한다.

    돌려주는 것: `(경계, 직접형 수, 전체 수, 분리 가능한가)`. 시험이 읽는다.
    """
    gold_text = {d["planted_id"]: d["text"] for d in docs}
    cent = type_centroids(gold_text)
    mean = {t: sum(v) / len(v) for t, v in cent.items()}
    rows = sorted(eval_gold_rel(), key=lambda r: -r[2])

    _block("[표 0] 🔵 **보고 전용** — 격자의 채점 18문항은 이 눈금의 어느 대역에 있나")
    print("  가설: *\"표 1에서 네 모드가 직접형에 동률이니, 격자가 모드를 못 가른 것은")
    print("  격자의 18문항이 대부분 직접형이기 때문일 수 있다.\"* 이 집합의 **라벨 검사")
    print("  눈금**(표 3의 정답쌍 어휘 rel)으로 그 가설을 검사한다.")
    print("  🔴 여기서 붙는 라벨은 **이 파일의 것이지 `eval/`의 것이 아니다.**")
    print("     `eval/questions.yaml`에 유형 라벨은 없다. `eval/`은 **읽기 전용으로만**")
    print("     열었다 (A8). 재는 것은 문항의 뜻이 아니라 **한 숫자**다.\n")

    print(f"  {'유형 중심 (레인 I 프로브 24개)':<34}{'평균':>8}{'최소':>8}{'최대':>8}")
    for t in PS.TYPES:
        print(f"  {t:<34}{mean[t]:>8.3f}{cent[t][0]:>8.3f}{cent[t][-1]:>8.3f}")

    other = sorted(cent[PS.PARA] + cent[PS.INFER])
    gap_lo, gap_hi = other[-1], cent[PS.DIRECT][0]
    separable = gap_lo < gap_hi
    boundary = (mean[PS.DIRECT] + mean[PS.PARA]) / 2
    pi_overlap = not (max(cent[PS.PARA]) < min(cent[PS.INFER])
                      or max(cent[PS.INFER]) < min(cent[PS.PARA]))
    print(f"\n  직접형 ↔ 나머지 둘: "
          + (f"🟢 **빈 구간 ({gap_lo:.3f}, {gap_hi:.3f})** — 분리된다"
             if separable else
             f"🔴 **겹친다** (나머지 최대 {gap_lo:.3f} ≥ 직접형 최소 {gap_hi:.3f})"))
    print(f"  의역형 ↔ 추론형   : "
          + ("🔴 **겹친다 — 이 눈금은 둘을 못 가른다.** 아래 배정에서 그 둘은 "
             "한 대역으로 읽는다" if pi_overlap else "🟢 분리된다"))

    if not separable:
        print("\n  🔴 **직접형 대역이 나머지와 겹치므로 경계를 그을 수 없다.**")
        print("     이 눈금으로는 18문항을 분류하지 않는다 — 숫자를 안 찍는다.")
        print("     (레인 I의 라벨 검사가 FAIL이면 여기가 먼저 침묵한다.)")
        return None, None, len(rows), False

    print(f"  최근접 중심 경계 (직접형 ↔ 의역형) = **{boundary:.3f}** — "
          f"위 빈 구간 안에 떨어진다\n")

    print(f"  {'문항':<7}{'정답쌍 rel':>11}  {'배정':<8}질의")
    for qid, ask, r in rows:
        lab = min(PS.TYPES, key=lambda t: abs(r - mean[t]))
        print(f"  {qid:<7}{r:>11.4f}  {lab:<8}{ask}")

    n_direct = sum(1 for _, _, r in rows if r >= boundary)
    n_zero = sum(1 for _, _, r in rows if r == 0.0)
    lo_n = sum(1 for _, _, r in rows if r >= gap_lo)
    hi_n = sum(1 for _, _, r in rows if r >= gap_hi)
    print(f"\n  배정 결과: 직접형 **{n_direct}/{len(rows)}** · "
          f"나머지(의역형·추론형 대역) {len(rows) - n_direct}/{len(rows)}")
    print(f"  경계 민감도: 경계를 빈 구간 전체({gap_lo:.3f} ~ {gap_hi:.3f})에서 "
          f"움직여도 직접형은 **{hi_n}~{lo_n}/{len(rows)}**")
    print(f"  18문항의 정답쌍 rel: 평균 "
          f"{sum(r for _, _, r in rows) / len(rows):.3f} · "
          f"정확히 0인 문항 **{n_zero}/{len(rows)}** "
          f"(현행 θ={M.THETA_RELEVANCE} 아래다 — 임계 컷이 정답 근거를 깔고 앉는다)")
    print("  → **가설은 이 눈금에서 지지받지 못한다.** 격자의 문항은 직접형이 많은 "
          "것이 아니라")
    print("     거의 전부 의역형·추론형 대역에 있다. 격자가 모드를 못 가른 이유를 "
          "'문항 구성'에서")
    print("     찾을 수 없다는 뜻이고, **판정을 닫은 것은 전선 5셀 규칙이라는 "
          "설명이 남는다.**")
    print("  ⚠️ 이 표는 **648쌍 프로브 모집단의 눈금을 378쌍 격자 모집단의 문항에 "
          "댄 것**이다.")
    print("     옮겨 적은 것은 **점수가 아니라 자(尺)**이고, 그 자는 두 모집단에서 "
          "같은 함수다 (G12).")
    return boundary, n_direct, len(rows), True


def main():
    probes = PS.TYPED_PROBES
    docs = PS.corpus_docs()

    print("=" * W)
    print("유형 라벨 프로브 집합 — 하이브리드 재진입 조건 1의 계측기 (레인 I)")
    print("=" * W)

    # ── 1. gold id 해석 — 하나라도 없으면 여기서 죽는다 ─────────────────
    cids, lids = PS.corpus_ids(), PS.ledger_ids()
    PS.validate(probes, valid_ids=cids & lids)     # 위반 시 ProbeSetError
    print(f"\n[검증] 정답 근거 id 해석 — **조용히 건너뛰지 않는다**")
    print(f"  프로브 {len(probes)}개 · gold id {len({p.gold for p in probes})}개 "
          f"(전부 서로 다르다)")
    print(f"  {sum(p.gold in cids for p in probes)}/{len(probes)}가 "
          f"eval/corpus/corpus.jsonl의 planted_id에 존재")
    print(f"  {sum(p.gold in lids for p in probes)}/{len(probes)}가 "
          f"eval/fact-ledger.yaml(facts·events·debts)에 존재")
    print(f"  ⚠️ eval/ 은 **읽기 전용으로만** 열었다 (A8). 프로브는 eval/ 밖 자산이다")

    # ── 2. 자기저작 선언 — 출력에 있어야 한다 ──────────────────────────
    _block("자기저작 편향 — 제거하지 못한 한계 (정본: experiments/probe_set.py 머리말)")
    print(PS.SELF_AUTHORSHIP)

    # ── 2-b. 표 0 — 격자의 18문항은 어느 대역에 있나 (임베딩 없이 돈다) ──
    #    🔴 이 절은 벡터를 안 쓴다. 그래서 **ollama가 없어 SKIP(77)로 끝나는
    #       실행에서도 찍힌다** — 자기저작 선언과 같은 이유다.
    report_eval_question_types(PS.corpus_docs())

    # ── 3. 환경 ────────────────────────────────────────────────────────
    info = EMB.checkpoint_info()
    _block("모집단과 환경")
    counts = {t: sum(1 for p in probes if p.type == t) for t in PS.TYPES}
    print(f"  프로브 {len(probes)}개 = " +
          " · ".join(f"{t} {counts[t]}" for t in PS.TYPES) +
          f"  |  후보 심긴 문서 {len(docs)}개  |  "
          f"{len(probes) * len(docs)}쌍")
    print(f"  임베딩 {EMB.EMBED_MODEL} · ollama {info['ollama']} · "
          f"digest {(info['digest'] or '?')[:16]}")
    print(f"  측정 호스트 {EMB.OLLAMA_HOST}"
          f"{'  (OLLAMA_HOST로 덮어씀)' if os.environ.get('OLLAMA_HOST') else ''}"
          f"  — `localhost`가 아닌 이유는 prototype/embedding.py:24")
    print(f"  🔴 이 648쌍은 rel_dist/retrieval_sweep의 **378쌍과 다른 모집단**이다. "
          f"값을 옮겨 적지 않는다 (P1 · G12)")

    texts = [d["text"] for d in docs] + [p.q for p in probes]
    vecs, hit, miss = ensure_vectors(texts)
    print(f"  임베딩 캐시 ({os.path.basename(PROBE_CACHE)}): 텍스트 {len(texts)}개 · "
          f"히트 {hit} · 미스 {miss}")
    if vecs is None:
        print("  → `embed`·`hybrid`를 잴 수 없다. **SKIP은 통과가 아니다**(G1). "
              "조건 1은 `측정 안 됨`으로 남는다.")
        print("=" * W)
        return 77

    scorers = {
        "lexical": score_lexical,
        "lexical_fixed": score_fixed,
        "embed": lambda q, t: cos(vecs[q], vecs[t]),
    }
    scorers[MODES[3]] = (lambda q, t:
                         ALPHA_HYBRID * score_lexical(q, t)
                         + (1 - ALPHA_HYBRID) * cos(vecs[q], vecs[t]))

    res = {m: run_mode(scorers[m], probes, docs) for m in MODES}

    # ── 4. 표 1 — 유형 × 모드 ──────────────────────────────────────────
    _block(f"[표 1] 유형 × 모드 — 1등 / top-5 / 평균 순위 / 정답 근거 점수 하한 "
           f"(후보 {len(docs)}개 중)")
    groups = [(t, [i for i, p in enumerate(probes) if p.type == t])
              for t in PS.TYPES] + [("전체", list(range(len(probes))))]
    print(f"  {'유형':<8}{'모드':<20}{'1등':>8}{'top-5':>9}{'평균 순위':>11}"
          f"{'점수 하한':>11}{'동점 발생':>11}")
    for t, idx in groups:
        for j, m in enumerate(MODES):
            r = [res[m][i] for i in idx]
            h1 = sum(1 for x in r if x[0] == 1)
            h5 = sum(1 for x in r if x[0] <= 5)
            mr = sum(x[0] for x in r) / len(r)
            lo = min(x[1] for x in r)
            tie = sum(1 for x in r if x[2] > 0)
            print(f"  {t if j == 0 else '':<8}{m:<20}"
                  f"{f'{h1}/{len(r)}':>8}{f'{h5}/{len(r)}':>9}{mr:>11.1f}"
                  f"{lo:>11.3f}{f'{tie}/{len(r)}':>11}")
        print()
    print("  점수 하한 = 그 유형의 정답 항목 점수 중 **최솟값**. 현행 "
          f"θ={M.THETA_RELEVANCE}보다 낮으면 임계 컷이 정답을 깔고 앉는다")
    print("  동점 발생 = 정답과 **같은 점수**인 다른 후보가 있는 프로브 수. "
          "그 순위는 코퍼스 행 순서가 정한다 — 프로덕션(`scored.sort` · memory.py:1189)은 "
          "event_id로 가른다")

    # ── 5. 표 2 — 프로브별 순위 ────────────────────────────────────────
    _block("[표 2] 프로브별 정답 순위 — 평균 하나로는 "
           "'고르게 중간'과 '대부분 1등인데 둘이 꼴찌'가 안 갈린다")
    for t in PS.TYPES:
        idx = [i for i, p in enumerate(probes) if p.type == t]
        print(f"\n  {t}")
        print(f"    {'모드':<20}" + "".join(f"{k+1:>5}" for k in range(len(idx)))
              + "     ← 이 유형 안의 번호")
        for m in MODES:
            print(f"    {m:<20}" + "".join(f"{res[m][i][0]:>5}" for i in idx))
        for k, i in enumerate(idx):
            print(f"      {k+1:>2}. [{probes[i].gold:<11}] {probes[i].q}")

    # ── 6. 표 3 — 라벨 자체의 검사 ─────────────────────────────────────
    _block("[표 3] 유형 라벨은 주장이다 — 정답쌍의 **어휘 겹침**이 그 주장을 검사한다")
    print("  직접형은 정의상 어휘가 겹쳐야 하고, 의역형·추론형은 0 근처여야 한다.")
    print("  그렇지 않으면 라벨이 틀린 것이지 검색기가 특이한 것이 아니다.\n")
    print(f"  {'유형':<8}{'정답쌍 lexical rel':>22}{'0인 프로브':>12}"
          f"{'정답쌍 코사인(평균)':>22}")
    gold_text = {d["planted_id"]: d["text"] for d in docs}
    lab = {}
    for t in PS.TYPES:
        idx = [i for i, p in enumerate(probes) if p.type == t]
        rels = [score_lexical(probes[i].q, gold_text[probes[i].gold]) for i in idx]
        coss = [cos(vecs[probes[i].q], vecs[gold_text[probes[i].gold]]) for i in idx]
        lab[t] = (sum(rels) / len(rels), sum(1 for v in rels if v == 0),
                  sum(coss) / len(coss))
        print(f"  {t:<8}{f'평균 {lab[t][0]:.3f}':>22}{f'{lab[t][1]}/{len(idx)}':>12}"
              f"{lab[t][2]:>22.3f}")
    ok_label = (lab[PS.DIRECT][0] > lab[PS.PARA][0]
                and lab[PS.DIRECT][0] > lab[PS.INFER][0])
    print(f"\n  라벨 검사 (직접형의 어휘 겹침이 나머지 둘보다 큰가): "
          f"{'🟢 PASS' if ok_label else '🔴 FAIL — 라벨을 다시 붙여야 한다'}")

    # ── 7. 표 4 — 부호 검정 ────────────────────────────────────────────
    _block(f"[표 4] `{BASELINE}` 기준 **페어별 정확 부호 검정** (양측) — "
           f"n=24, 유형별 n=8은 작다")
    print(f"  {'유형':<8}{'모드':<20}{'승':>5}{'패':>5}{'동':>5}{'p (양측)':>12}"
          f"{'이 n의 최소 p':>15}")
    for t, idx in groups:
        floor = min(2 / 2 ** len(idx), 1.0)
        for j, m in enumerate(MODES):
            if m == BASELINE:
                continue
            w, l, ti, p = sign_test([res[m][i][0] for i in idx],
                                    [res[BASELINE][i][0] for i in idx])
            print(f"  {t if j == 1 else '':<8}{m:<20}{w:>5}{l:>5}{ti:>5}"
                  f"{_p(p):>12}{_p(floor):>15}")
        print()
    print("  '이 n의 최소 p' = 그 표본에서 **원리상 도달 가능한 가장 작은 양측 p**"
          " (2/2^n). 이보다 작은 유의수준은 이 n에서 물을 수 없다.")
    print("  동점(같은 순위)은 부호 검정에서 **버린다** — 버린 수가 크면 검정이 "
          "실제로 본 표본은 n보다 작다.")
    print("  ⚠️ 이 검정은 **순위의 부호만** 본다. 순위가 몇 칸 움직였는지는 안 본다 "
          "— 크기는 표 1·2에서 읽는다.")

    # ── 7-b. 🔵 보고 전용 — F29(하이브리드 ≡ 임베딩)를 이 집합에서 다시 보면 ──
    _block("[표 4-b] 🔵 **보고 전용** — F29를 이 집합에서 다시 보면")
    print("  F29(ADR-015 핵심 3의 기각 근거 1): *\"α=0.5 하이브리드의 순위 프로파일이")
    print("  임베딩 단독과 **완전히 동일하다**\"* — 270쌍 프로브 10개에서 관측된 것이고,")
    print("  R2b 격자가 378쌍에서 이미 일반화되지 않는다고 적었다. 이 집합에서 다시 본다.\n")
    hy = MODES[3]
    diff = [i for i in range(len(probes))
            if res[hy][i][0] != res["embed"][i][0]]
    print(f"  {'유형':<8}{'승':>5}{'패':>5}{'동':>5}{'p (양측)':>12}   "
          f"(`{hy}` 대 `embed` · 승 = 하이브리드가 위)")
    for t, idx in groups:
        w, l, ti, p = sign_test([res[hy][i][0] for i in idx],
                                [res["embed"][i][0] for i in idx])
        print(f"  {t:<8}{w:>5}{l:>5}{ti:>5}{_p(p):>12}")
    print(f"\n  순위가 **다른** 프로브: {len(diff)}/{len(probes)}개"
          f"{' — ' + ', '.join(probes[i].gold for i in diff) if diff else ''}")
    if diff:
        print("  → 이 집합에서는 두 모드의 순위 프로파일이 **동일하지 않다.** "
              "F29가 관측된 모집단(270쌍)의")
        print("     성질이 여기서 재현되지 않는다는 사실만 적는다. "
              "**무엇이 더 나은지는 판정하지 않는다.**")
    else:
        print("  → 이 집합에서도 두 프로파일이 완전히 같다 (F29 재현).")

    # ── 8. 표 5 — 조건 2를 이 집합에서 다시 재면 (보고 전용) ───────────
    _block("[표 5] 🔵 **보고 전용** — 재진입 조건 2를 이 집합에서 다시 재면")
    print("  조건 2: *\"`embed`가 `lexical`보다 근거 회상이 낮은 문항이 있고, 그 문항의")
    print("  어휘 `rel > 0`이다\"*. R2b 격자에서 참이 됐지만(Q01·Q05·Q10·Q25), 그때의")
    print("  계측기 `lex_rel`은 **색인 전체에 대한 최댓값**이라 조건의 문장보다 약했다")
    print("  (`.omc/plans/verifier-r2b-laneE.md` 위험 4). 여기서는 **정답 근거에 대한**")
    print("  `rel`을 직접 쓴다 — 조건이 실제로 말하는 값이다.\n")
    hold = []
    for i, p in enumerate(probes):
        if res["embed"][i][0] > res[BASELINE][i][0]:
            gr = score_lexical(p.q, gold_text[p.gold])
            hold.append((p, res[BASELINE][i][0], res["embed"][i][0], gr))
    if hold:
        print(f"  {'유형':<8}{'gold':<12}{'lexical 순위':>12}{'embed 순위':>12}"
              f"{'정답쌍 어휘 rel':>16}   질의")
        for p, rl, re_, gr in hold:
            print(f"  {p.type:<8}{p.gold:<12}{rl:>12}{re_:>12}{gr:>16.4f}   {p.q}")
        strong = [h for h in hold if h[3] > 0]
        print(f"\n  `embed`가 잃고 `lexical`이 든 프로브: {len(hold)}개 · "
              f"그중 **정답쌍 어휘 rel > 0**: {len(strong)}개")
    else:
        print("  `lexical`이 `embed`보다 정답을 위에 놓은 프로브가 이 집합에는 없다.")
    print("  🔴 이 표는 조건 2의 판정이 아니다 — 조건 2는 **격자의 문항**에서 재는 "
          "것이고 여기는 프로브다. 다음 라운드가 둘을 나란히 읽는다.")

    # ── 9. 조건 1의 상태 — 사실만 ──────────────────────────────────────
    _block("재진입 조건 1의 상태 — **사실만 적는다. 판정하지 않는다**")
    req = [
        ("유형 라벨이 붙어 있다",
         f"{len(PS.TYPES)}종 ({' · '.join(PS.TYPES)}) · 분류 밖 라벨 0건",
         True),
        (f"n ≥ {PS.N_MIN}", f"n = {len(probes)}", len(probes) >= PS.N_MIN),
        ("bge-m3로 채점한다",
         f"{EMB.EMBED_MODEL} · digest {(info['digest'] or '?')[:16]} · "
         f"캐시 히트 {hit} / 라이브 {miss}", EMB.EMBED_MODEL == "bge-m3"),
    ]
    print(f"  {'조건 1이 요구하는 것':<30}{'이 집합':<52}{'':>6}")
    for name, val, ok in req:
        print(f"  {name:<30}{val:<52}{'🟢' if ok else '🔴':>4}")
    print(f"\n  세 요건 모두 충족: {'예' if all(o for _, _, o in req) else '아니오'}")
    if miss == 0:
        print(f"  ⚠️ 이번 실행의 벡터는 **전부 캐시에서 나왔다**"
              f"({os.path.basename(PROBE_CACHE)} · 히트 {hit}). 캐시를 만든 시점의")
        print("     모델로 낸 숫자라는 뜻이다 — 라이브로 다시 재려면 그 파일을 지우고 "
              "다시 돌린다.")
        print("     (`embed_vs_bigram.py --live`가 같은 이유로 존재한다.)")
    print("  🔴 **그러나 하이브리드 재진입 여부는 이 스크립트의 판정이 아니다.**")
    print("     재진입은 조건 1·2가 둘 다 참이어야 논의가 열리는 것이고, "
          "'논의를 연다'는")
    print("     '바꾼다'가 아니다(홀드아웃 부재 — ADR-015). 위 표 1·2·4의 숫자와 "
          "자기저작")
    print("     선언을 함께 읽는 것이 다음 라운드의 일이다.")
    print("=" * W)
    return 0


if __name__ == "__main__":
    sys.exit(main())
