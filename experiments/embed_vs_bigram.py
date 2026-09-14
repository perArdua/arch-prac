# -*- coding: utf-8 -*-
"""
embed_vs_bigram.py — 글자 겹침 검색 vs 임베딩 검색. (로컬 ollama, LLM 불필요)

## 왜

처음 정리한 문서에 한계로 이렇게 적었다.

    임베딩을 안 쓰고 글자 두 개씩 잘라 겹치는 정도로 검색함
    특히 말이 겹치지 않고 뜻만 통하는 경우를 놓침. **이쪽이 불리하게 나왔을 것임**

무료 티어를 응답 품질에 쓰려고 미뤄둔 것이었는데, 로컬 임베딩이 생겼으니 이제 잰다.
**편향의 방향까지 적어뒀으므로 이 실험은 내 결론에 불리하게 나올 수 있다.**

## 무엇을 재나

같은 프로브 10개, 같은 후보 집합에 검색 방식만 바꾼다.

    현재    어절을 붙여 bigram, 덮기율로 점수
    고침    어절별 bigram + 조사 제거, 자카드
    임베딩  bge-m3 코사인 유사도

교착어 문제의 정체가 여기서 갈린다.
    "아팠던"과 "아파서"는 글자로는 안 겹치지만 뜻은 같다.
    글자 방식이 이걸 놓친다면 임베딩이 이겨야 한다. 안 이기면 내 한계 서술이 과장이었던 것이다.
"""
import json
import math
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "prototype"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import memory as M                                    # noqa: E402
import embedding as EMB                               # noqa: E402
from retrieval_sim import PROBES                      # noqa: E402

# 🆕 라이브 재계산 모드 (단계 1 작업 7-a — rev6 E4 마감).
#
# 0-f의 결론은 **전부 캐시에서 나왔다.** ollama를 죽은 포트로 돌려도 출력이
# 바이트 단위로 같았다 — 즉 "캐시가 만들어진 시점의 모델"로 낸 숫자다.
# 계획 rev6 E4가 요구한 것은 그 캐시를 **한 번 라이브로 대조**하는 것이다.
# `--live`는 37개를 전부 다시 계산해 캐시와 비교하고, **`EMBED_CACHE.json`에는
# 쓰지 않는다.** 플래그가 없으면 이 파일의 출력은 이전과 바이트 단위로 같다.
LIVE = ("--live" in sys.argv) or os.environ.get("EMBED_LIVE") == "1"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# `localhost`가 아닌 이유는 `prototype/embedding.py:24`의 주석이 정본이다 —
# 이 기기는 거절된 connect에 ~2.02초를 쓰고, `localhost`는 `::1`을 먼저 고른다.
HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
EMB_MODEL = "bge-m3"
CK = f"{ROOT}/experiments/data/EMBED_CACHE.json"
W = 74

# 하이브리드 가중치 — `α·어휘 + (1−α)·코사인`. 두 점수 다 [0,1]이라 그대로 섞인다.
# 0.5는 **탐색의 출발점**이지 튜닝 결과가 아니다. 격자는 단계 4가 돌린다.
ALPHA_HYBRID = 0.5

# `rel` 분포의 표본 정의. 스크립트가 이 문자열을 **직접 찍는다** —
# 세션 중 임시 측정으로 나온 n(220/100)이 저장소 구조와 안 맞았고,
# 어느 부분집합이었는지 알 수 없어 **재현하지 않고 새로 잰다**(G11).
THETA_UNDER_TEST = M.THETA_RELEVANCE

# 🔵 **정본 승격 (라운드 2 단계 3).** 여기 있던 `stem2`/`bigrams2` 지역 사본을
#    `prototype/memory.py`로 올리고 이름만 남긴다 — `lexical_fixed` 척도는 이제
#    프로덕션 코드가 들고 있고, 이 실험과 `rel_dist.py`가 **같은 것을 읽는다.**
#    사본이 둘이면 한쪽만 고쳐진다(F12·F9). 이름을 남기는 이유는 `rel_dist.py:55`가
#    `bigrams2`로 import하고 이 파일이 `:183`에서 쓰기 때문이다.
#    ⚠️ 승격은 **이름의 이동이지 식의 변경이 아니다** — 이 파일의 출력이 승격 전후로
#       바이트 동일임이 그 확인이고, 그것이 단계 3의 수용 기준에 들어 있다.
stem2 = M._fixed_word
bigrams2 = M.tokens_fixed


def embed(texts, cache):
    """ollama 임베딩. 캐시가 있으면 호출하지 않는다."""
    need = [t for t in texts if t not in cache]
    for i, t in enumerate(need):
        body = json.dumps({"model": EMB_MODEL, "input": t}).encode()
        req = urllib.request.Request(f"{HOST}/api/embed", body,
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            cache[t] = json.loads(r.read())["embeddings"][0]
        if (i + 1) % 20 == 0:
            print(f"    {i+1}/{len(need)}", end="\r", flush=True)
    if need:
        json.dump(cache, open(CK, "w", encoding="utf-8"))
    return [cache[t] for t in texts]


def cos(a, b):
    d = sum(x * y for x, y in zip(a, M._same_dim(a, b)))  # 길이가 다르면 던진다 — `memory._cosine`의 검사를 부른다(사본 아님 · F12 · w12close)
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return d / (na * nb)


def main():
    docs = [json.loads(l) for l in open(f"{ROOT}/eval/corpus/corpus.jsonl", encoding="utf-8")]
    ext = [d for d in docs if d["planted_id"]]
    cache = json.load(open(CK, encoding="utf-8")) if os.path.exists(CK) else {}

    print("=" * W)
    print("검색 방식 비교 — 글자 겹침 vs 임베딩")
    print("=" * W)
    print(f"\n후보 {len(ext)}개 · 프로브 {len(PROBES)}개 · 임베딩 {EMB_MODEL}\n")

    print("  임베딩 만드는 중...", flush=True)
    texts = [d["text"] for d in ext] + [q for q, _ in PROBES]
    embed(texts, cache)
    print("  완료" + " " * 20)

    cov = lambda q, d: len(q & d) / max(len(q), 1)
    jac = lambda q, d: len(q & d) / max(len(q | d), 1)

    def run(scorer):
        """
        (적중@1, 적중@5, 평균 순위, 프로브별 순위, **정답 근거 점수 하한**)

        `scorer(q, doc_text)` 하나로 어휘·임베딩·하이브리드를 같은 틀에 넣는다.
        점수 하한 = 프로브 10개의 **정답 항목 점수 중 최솟값**. 이게 θ보다 낮으면
        임계 컷이 정답을 깔고 앉는다 — 무엇이 걸러지는지는 순위가 아니라 이 값이 말한다.
        """
        h1 = h5 = 0
        ranks, gold_scores = [], []
        for q, gold in PROBES:
            scored = [(scorer(q, d["text"]), d["planted_id"]) for d in ext]
            rows_ = sorted(scored, key=lambda x: -x[0])
            ids = [g for _, g in rows_]
            r = ids.index(gold) + 1 if gold in ids else len(ids)
            ranks.append(r)
            gs = [s for s, g in scored if g == gold]
            gold_scores.append(min(gs) if gs else 0.0)
            h1 += r == 1
            h5 += r <= 5
        return h1, h5, sum(ranks) / len(ranks), ranks, min(gold_scores)

    def lex(bg, score):
        return lambda q, t: score(set(bg(q)), set(bg(t)))

    s_cur = lex(M.bigrams, cov)          # memory.py:1175의 rel(`coverage`)과 **같은 식**
    s_fix = lex(bigrams2, jac)
    s_emb = lambda q, t: cos(cache[q], cache[t])
    # α·어휘 + (1−α)·코사인. 어휘 쪽은 현행 `rel`을 쓴다 — 섞는 대상이
    # "고친 것"이면 하이브리드의 이득이 어디서 왔는지 갈리지 않는다.
    s_hyb = lambda q, t: (ALPHA_HYBRID * s_cur(q, t)
                          + (1 - ALPHA_HYBRID) * s_emb(q, t))

    rows = [
        ("현재  어절 붙임 + 덮기율", *run(s_cur)),
        ("고침  어절별 + 자카드", *run(s_fix)),
        ("임베딩 bge-m3", *run(s_emb)),
        (f"하이브리드 α={ALPHA_HYBRID} (어휘·코사인)", *run(s_hyb)),
    ]

    print(f"{'방식':<28}{'1등':>6}{'top-5':>8}{'평균 순위':>10}{'정답 근거 점수 하한':>20}")
    print("-" * W)
    for name, h1, h5, mr, _ranks, lo in rows:
        print(f"{name:<28}{h1:>4}/10{h5:>6}/10{mr:>10.1f}{lo:>16.3f}")
    print("-" * W)
    print(f"  정답 근거 점수 하한 = 프로브 10개의 정답 항목 점수 중 최솟값 "
          f"(현행 θ={THETA_UNDER_TEST})")

    # ── 프로브별 순위 목록 ──────────────────────────────────────────────
    # 평균 순위 하나로는 "고르게 중간"과 "대부분 1등인데 하나가 27등"이 구분되지 않는다.
    print("\n프로브별 정답 순위 (1이 최선 · 후보 {}개 중)".format(len(ext)))
    print("-" * W)
    print(f"  {'방식':<28}" + "".join(f"{i+1:>4}" for i in range(len(PROBES))))
    for name, _h1, _h5, _mr, ranks, _lo in rows:
        print(f"  {name:<28}" + "".join(f"{r:>4}" for r in ranks))
    print(f"  {'프로브 번호는 retrieval_sim.PROBES 순서다':<28}")

    # 교착어가 실제로 갈리는 문항만 따로 본다
    print("\n글자로는 안 겹치는데 뜻이 통하는 문항")
    print("-" * W)
    for q, gold in PROBES:
        g = next((d for d in ext if d["planted_id"] == gold), None)
        if not g:
            continue
        ov = len(set(bigrams2(q)) & set(bigrams2(g["text"])))
        if ov <= 1:
            e = cos(cache[q], cache[g["text"]])
            print(f"  질문 {q}")
            print(f"  근거 {g['text'][:40]}")
            print(f"       겹치는 조각 {ov}개 · 임베딩 유사도 {e:.2f}\n")

    # ── rel 분포 — θ가 어디에 놓여 있는가 ────────────────────────────────
    #
    # 순위표는 "누가 이기나"만 말한다. **θ가 무엇을 자르나**는 점수의 분포가 말한다.
    # 어휘 점수가 대부분 θ 아래에 깔려 있으면 θ는 정답을 자르는 칼이고,
    # 코사인이 전부 θ 위에 있으면 코사인에서는 **θ가 아무것도 안 자른다**(소멸).
    # 그러면 지배항이 rel에서 importance로 넘어간다 — 그게 §0.4의 주장이다.
    sample_def = f"ext {len(ext)} x PROBES {len(PROBES)} = {len(ext) * len(PROBES)}쌍"
    dists = [
        ("어휘 (덮기율)", [s_cur(q, d["text"]) for q, _ in PROBES for d in ext]),
        (f"{EMB_MODEL} 코사인", [s_emb(q, d["text"]) for q, _ in PROBES for d in ext]),
    ]

    def q_at(v, p):
        v = sorted(v)
        return v[min(len(v) - 1, int(len(v) * p / 100))]

    print("\n\nrel 분포 — 모든 (프로브, 후보) 쌍")
    print("-" * W)
    print(f"  {'':<18}{'표본 정의':<26}{'n':>6}{'중앙값':>9}{'최솟값':>9}"
          f"{'p25':>8}{'p75':>8}")
    stat = {}
    for name, v in dists:
        stat[name] = v
        print(f"  {name:<18}{sample_def:<26}{len(v):>6}{q_at(v,50):>9.3f}"
              f"{min(v):>9.3f}{q_at(v,25):>8.3f}{q_at(v,75):>8.3f}")

    # 판정에 필요한 것은 두 부등식뿐이다.
    lex_med = q_at(stat["어휘 (덮기율)"], 50)
    emb_min = min(stat[f"{EMB_MODEL} 코사인"])
    t = THETA_UNDER_TEST
    ok1, ok2 = lex_med < t, emb_min > t
    print(f"\n  {'판정':<40}{'결과':>10}")
    print("  " + "-" * (W - 2))
    print(f"  median(어휘) = {lex_med:.3f} < θ = {t}"
          f"{'':<10}{'PASS' if ok1 else 'FAIL':>10}")
    print(f"  min(코사인)  = {emb_min:.3f} > θ = {t}"
          f"{'':<10}{'PASS' if ok2 else 'FAIL':>10}")
    if ok1 and ok2:
        print("\n  → 둘 다 성립한다. **어휘에서 θ는 중앙값 위에 있어 후보 절반 이상을 자르고,**")
        print("     **코사인에서는 θ 아래가 하나도 없어 아무것도 안 자른다(θ 소멸).**")
        print("     검색 방식을 바꾸면 θ는 같은 숫자여도 **다른 일을 한다** — 지배항 역전.")
    else:
        print("\n  🔴 부등식이 깨졌다. §0.4의 결론(θ 소멸 · 지배항 역전)과 부검 시나리오 1을")
        print("     **다시 써야 한다.** 이 출력을 근거로 계획을 고칠 것.")

    print("\n⚠️ 프로브 10개다. 순위 하나가 10%p를 움직인다")
    print("⚠️ 하이브리드 α=0.5는 **탐색의 출발점**이다. 격자는 단계 4가 돌린다")

    # 🔄 단계 2 이월 (단계 1 검증자 지적 3) — `live_check`의 77을 버리지 않는다.
    #    `--live`에서 ollama가 죽어 있으면 라이브 대조를 **못 한** 것이지 통과가
    #    아니다. SKIP 규약(run_all.py `SKIP_CODE`)이 이 저장소에서 유일하게
    #    적혀만 있고 배선되지 않은 자리였다. 기본 실행(`--live` 없음)은 불변 — 0.
    if LIVE:
        return live_check(texts, ext, cache, stat, lex_med, t)
    return 0


def live_check(texts, ext, cache, stat, lex_med, t):
    """
    🆕 작업 7-a — 캐시 대 라이브 대조. `EMBED_CACHE.json`에 **쓰지 않는다.**

    묻는 것은 하나다: *"위의 숫자를 만든 캐시가 지금 모델과 같은 것인가?"*
    같으면 `max |Δcos|`가 0에 가깝고 두 부등식의 판정이 그대로다.
    다르면 위 결론(θ 소멸·지배항 역전)은 **지금 모델의 것이 아니다**.
    """
    info = EMB.checkpoint_info()
    print("\n\n" + "=" * W)
    print("🆕 라이브 재계산 대조 (--live) — rev6 E4")
    print("=" * W)
    print(f"  ollama {info['ollama']} · {info['model']} "
          f"digest {(info['digest'] or '?')[:16]}")
    print(f"  텍스트 {len(texts)}개를 캐시 없이 다시 계산한다 "
          f"(EMBED_CACHE.json에는 쓰지 않는다)")

    vecs = EMB.embed(texts, use_cache=False, save=False)
    if vecs is None:
        print("\n  ⚠️ ollama가 응답하지 않는다 — 라이브 대조를 **하지 못했다.**")
        print("     캐시 기반 위 숫자는 그대로 유효하지만 rev6 E4는 열린 채다.")
        return 77
    live = dict(zip(texts, vecs))

    # 코사인만 보면 "캐시를 그냥 읽은 것"과 구별되지 않는다. 성분 자체를 대조한다.
    comp = max((abs(a - b) for t_ in texts
                for a, b in zip(cache[t_], live[t_])), default=0.0)
    same = sum(cache[t_] == live[t_] for t_ in texts)

    dmax, dsum, n = 0.0, 0.0, 0
    live_pairs = []
    for q, _ in PROBES:
        for d in ext:
            a = cos(cache[q], cache[d["text"]])
            b = cos(live[q], live[d["text"]])
            live_pairs.append(b)
            dmax = max(dmax, abs(a - b))
            dsum += abs(a - b)
            n += 1

    emb_min_live = min(live_pairs)
    emb_min_cached = min(stat[f"{EMB_MODEL} 코사인"])
    ok1, ok2 = lex_med < t, emb_min_live > t
    print(f"\n  {'대조 항목':<44}{'값':>12}")
    print("  " + "-" * (W - 2))
    print(f"  {'쌍 수 (캐시 vs 라이브 코사인)':<44}{n:>12}")
    print(f"  {'max |Δcos|':<44}{dmax:>12.3e}")
    print(f"  {'mean |Δcos|':<44}{dsum / n:>12.3e}")
    print(f"  {'벡터 성분 최대차 (1024차원 x 37개)':<44}{comp:>12.3e}")
    print(f"  {'캐시와 완전히 같은 벡터':<44}{f'{same}/{len(texts)}':>12}")
    print(f"  {'min(코사인) 캐시':<44}{emb_min_cached:>12.3f}")
    print(f"  {'min(코사인) 라이브':<44}{emb_min_live:>12.3f}")
    print(f"\n  {'부등식 (라이브 값으로 다시 판정)':<44}{'결과':>12}")
    print("  " + "-" * (W - 2))
    print(f"  median(어휘) = {lex_med:.3f} < θ = {t}"
          f"{'':<10}{'PASS' if ok1 else 'FAIL':>12}")
    print(f"  min(코사인)  = {emb_min_live:.3f} > θ = {t}"
          f"{'':<10}{'PASS' if ok2 else 'FAIL':>12}")
    if ok1 and ok2:
        print("\n  → 라이브에서도 두 부등식이 성립한다. 위 결론은 캐시의 산물이 아니다.")
    else:
        print("\n  🔴 라이브에서 부등식이 깨졌다. 캐시로 낸 위 결론은 **지금 모델의 것이"
              " 아니다.** §0.4와 부검 시나리오 1을 다시 쓸 것.")
    print("=" * W)
    return 0


if __name__ == "__main__":
    sys.exit(main())
