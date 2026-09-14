# -*- coding: utf-8 -*-
"""
retrieve_scaling.py — `Memory.retrieve`의 지연을 **색인 크기 N의 함수**로 잰다. (API 불필요 · LLM 0회)

## 왜

[ADR-003](../docs/adr/ADR-003-storage-engine.md)의 «3,000개 0.13 ms»는 numpy 내적의 실측이다.
프로토타입의 `retrieve`는 SQL이 `chat_id`로만 거르고 τ를 통과한 **행마다 조각을 꺼낸다** —
메모 전에는 행마다 `set(bigrams(summary))`를 다시 만들었다(O(N·L)). 21행 색인에서는 계측에 안 잡혀서, 이 경로가 ADR-003의 재검토
트리거(`p95 > 20 ms`)에 **언제** 닿는지 아무도 몰랐다([docs/17](../docs/17-gap-disposition.md) 검§1-11 · 검B3). 🔄 (w8code · 2026-09-11) 지금은 요약 문자열이 키인 메모(`memory.py` 끝 절)가 조각을 받는다 — 이 스크립트의 틀은 요약 21종 되풀이라 워밍업 뒤 늘 웜이고, 곡선은 **웜 곡선**이다(ADR-003 줄 끝 w8 · `retrieve_memo.py`가 콜드·웜을 가른다 · 방 여럿이 상한을 나눠 쓰는 절벽은 `memo_multiroom.py`). 🔄 (w11a) 이 문단과 끝 출력 문구를 메모 뒤로 고쳤다

## 방법

- `eval` 대장을 `soak.seed` + `soak.ingest`로 적재한 색인(살아 있는 행)을 **틀**로 삼아, 그 행들을
  그대로 되풀이해 N행 색인을 `%TEMP%` DB에 만든다 — 길이 분포와 τ 탈락 비율이 원래 색인과 같다.
  두 번째 혼합은 importance를 τ 위로 올려 **모든 행이 조각·덮기율 계산을 타게** 한다(최악).
- 질의는 `eval` 문항 26개를 돌려 쓴다. N마다 **n = 130**(워밍업 5회 제외).
- 🔴 **라운드마다 N 순서를 섞어 번갈아 부른다** — 기계 부하가 시간에 따라 흘러도 모든 N이 같은
  몫을 받는다. N을 하나씩 차례로 재면 뒤쪽 N이 다른 부하 창을 받는다.
- **0-연산 대조:** 같은 SELECT만 따로 잰다(`SQL만`). `retrieve`와 같은 값이면 지연은 bigram
  루프가 아니라 SQL 몫이다.
- 곁가지로 `gate`(질의 게이트 — `_recall_vocab_for`가 매번 어휘를 다시 만든다)도 같은 방식으로 잰다.

⚠️ 지연은 기계·부하의 함수다. **이 표의 값은 같은 실행 안에서만 비교한다.** 다른 실행·다른
기계의 값과 나란히 놓지 말 것.

    PYTHONIOENCODING=utf-8 python -B experiments/retrieve_scaling.py
"""
import json
import os
import platform
import random
import shutil
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "prototype"))
sys.stdout.reconfigure(encoding="utf-8")
W = 78

import yaml  # noqa: E402
import memory as M  # noqa: E402
from memory import Memory  # noqa: E402
import soak  # noqa: E402

GRID = (21, 100, 500, 2000, 5000)        # 사전 등록한 격자
# 사전 등록 밖 — 1,500·3,000은 ADR-003 «우리 규모»의 양 끝(첫 실행에서 교차가 그 사이에 떨어져
# 내삽 대신 직접 재려고 넣었다) · 10,000·20,000은 선형인지 보려고
EXTEND = (1500, 3000, 10000, 20000)
N_CALLS = 130
WARMUP = 5
TRIGGER_MS = 20.0                        # ADR-003 재검토 트리거
SEED = 20260910


def pct(v, p):
    """`soak.py`의 백분위와 같은 식(최근접 순위) — 저장소 안에서 같은 자로 잰다."""
    v = sorted(v)
    return v[min(len(v) - 1, int(len(v) * p / 100))]


def load_eval():
    with open(ROOT / "eval" / "corpus" / "corpus.jsonl", encoding="utf-8") as f:
        corpus = [json.loads(l) for l in f]
    with open(ROOT / "eval" / "fact-ledger.yaml", encoding="utf-8") as f:
        ledger = yaml.safe_load(f)
    with open(ROOT / "eval" / "questions.yaml", encoding="utf-8") as f:
        qs = yaml.safe_load(f)["qa_questions"]
    return corpus, ledger, qs


def template_rows(tmp, corpus, ledger):
    """`eval` 적재 후 살아 있는 색인 행 — 이것을 되풀이해 N행을 만든다."""
    m = Memory(os.path.join(tmp, "tpl.db"))
    try:
        soak.seed(m)
        soak.ingest(m, corpus, ledger, timed=False)
        rows = [dict(r) for r in m.db.execute(
            "SELECT summary, occurred_at, emotional_weight, importance, narrative_role,"
            " source_from_seq FROM event WHERE chat_id=? AND user_deleted=0 ORDER BY event_id",
            (soak.CHAT,)).fetchall()]
    finally:
        m.db.close()
    return rows


def build_db(tmp, tag, n, tpl, all_pass):
    m = Memory(os.path.join(tmp, f"{tag}_{n}.db"))
    soak.seed(m)
    floor = M.TAU_IMPORTANCE + 0.3
    vals = []
    for i in range(n):
        r = tpl[i % len(tpl)]
        imp = r["importance"]
        if all_pass:
            imp = max(imp or 0, floor)
        vals.append((soak.CHAT, r["summary"], r["occurred_at"], r["emotional_weight"], imp,
                     r["narrative_role"], r["source_from_seq"]))
    m.db.executemany(
        "INSERT INTO event (chat_id, summary, occurred_at, emotional_weight, importance,"
        " narrative_role, source_from_seq) VALUES (?,?,?,?,?,?,?)", vals)
    m.db.commit()
    live = m.db.execute("SELECT COUNT(*) c FROM event WHERE chat_id=? AND user_deleted=0",
                        (soak.CHAT,)).fetchone()["c"]
    assert live == n, f"색인 {live}행 ≠ {n}"
    return m


SQL_ONLY = ("SELECT event_id, summary, importance, emotional_weight, surfaced_count"
            " FROM event WHERE chat_id=? AND user_deleted=0")


def run(grid, mixes=(("eval 분포", False), ("전부 τ 통과", True))):
    corpus, ledger, qs = load_eval()
    asks = [q["ask"] for q in qs]
    last = corpus[-1]["seq"]
    tmp = tempfile.mkdtemp(prefix="retscale_")
    mems = {}
    try:
        tpl = template_rows(tmp, corpus, ledger)
        for tag, all_pass in mixes:
            for n in grid:
                mems[(tag, n)] = build_db(tmp, "p" if all_pass else "e", n, tpl, all_pass)
        rng = random.Random(SEED)
        keys = list(mems)
        t = {(k, what): [] for k in keys for what in ("retrieve", "sql", "gate")}
        hits = {k: 0 for k in keys}
        for rnd in range(WARMUP + N_CALLS):
            rng.shuffle(keys)
            q = asks[rnd % len(asks)]
            for k in keys:
                m = mems[k]
                t0 = time.perf_counter()
                got, _ = m.retrieve(soak.CHAT, q, last)
                t1 = time.perf_counter()
                m.db.execute(SQL_ONLY, (soak.CHAT,)).fetchall()
                t2 = time.perf_counter()
                m.gate(q, soak.CHAT)
                t3 = time.perf_counter()
                if rnd >= WARMUP:
                    t[(k, "retrieve")].append((t1 - t0) * 1000)
                    t[(k, "sql")].append((t2 - t1) * 1000)
                    t[(k, "gate")].append((t3 - t2) * 1000)
                    hits[k] += len(got)
        return tpl, t, hits
    finally:
        for m in mems.values():
            m.db.close()
        shutil.rmtree(tmp, ignore_errors=True)


def crossing(ns, vals, thr):
    """
    첫 교차 N과 교차 추정. 교차가 격자 안이면 **그 N과 바로 앞 N 사이의 직선**(내삽),
    끝까지 안 넘으면 가장 큰 두 N의 직선(외삽). 🔄 첫 판은 늘 가장 큰 두 N을 써서
    10,000·20,000에서 2,000대로 **거꾸로 외삽**하고 «내삽»이라 적었다.
    """
    pts = sorted(zip(ns, vals))
    i = next((k for k, (_, v) in enumerate(pts) if v > thr), None)
    if i == 0:
        return pts[0][0], None, None, "격자 첫 N부터 넘음"
    (n1, v1), (n2, v2) = (pts[i - 1], pts[i]) if i is not None else (pts[-2], pts[-1])
    slope = (v2 - v1) / (n2 - n1)
    est = None if slope <= 0 else n1 + (thr - v1) / slope
    kind = f"내삽 {n1:,}–{n2:,}" if i is not None else f"외삽 {n1:,}·{n2:,}에서"
    return (pts[i][0] if i is not None else None), est, slope, kind


def main():
    tpl0 = None
    print("=" * W)
    print("retrieve 지연 곡선 — 색인 N행 × (p50 · p95) · 같은 실행 안에서만 비교")
    print("=" * W)
    print(f"기계: {platform.platform()} · {platform.processor() or '?'} · 논리 CPU "
          f"{os.cpu_count()} · Python {platform.python_version()} · "
          f"{time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"모드 {M.RETRIEVAL_MODE} · τ {M.TAU_IMPORTANCE} · TOP_K {M.TOP_K} · 호출 n={N_CALLS}"
          f"/N (워밍업 {WARMUP} 제외) · 라운드마다 N 순서를 섞음(seed {SEED})")

    grid = GRID + EXTEND
    tpl, t, hits = run(grid)
    tpl0 = tpl
    print(f"틀: eval 색인 살아 있는 {len(tpl0)}행 · 평균 요약 {sum(len(r['summary']) for r in tpl0)/len(tpl0):.1f}자"
          f" · τ 미만 {sum(1 for r in tpl0 if max(r['importance'] or 0, r['emotional_weight'] or 0) < M.TAU_IMPORTANCE)}행")
    for tag in ("eval 분포", "전부 τ 통과"):
        print(f"\n── 혼합: {tag} " + "─" * (W - len(tag) - 10))
        print(f"  {'N':>6} {'retrieve p50':>13} {'p95':>8} {'max':>8} │ {'SQL만 p50':>10} {'p95':>7}"
              f" │ {'gate p50':>9} {'p95':>7} │ {'gate+retrieve p95':>17} │ {'µs/행(p50)':>10}"
              f" {'꺼냄/회':>7}")
        p50s, p95s, sums, ns = [], [], [], []
        for n in sorted(grid):
            r = t[((tag, n), "retrieve")]
            s = t[((tag, n), "sql")]
            g = t[((tag, n), "gate")]
            both = [x + y for x, y in zip(r, g)]    # 같은 라운드에 잇달아 잰 한 턴의 두 몫
            a, b = pct(r, 50), pct(r, 95)
            p50s.append(a); p95s.append(b); sums.append(pct(both, 95)); ns.append(n)
            mark = " ⚠️사전등록 밖" if n in EXTEND else ""
            flag = " 🔴>20" if b > TRIGGER_MS else ""
            print(f"  {n:>6} {a:>11.3f}ms {b:>6.3f}ms {max(r):>6.2f}ms │ {pct(s,50):>8.3f}ms"
                  f" {pct(s,95):>5.3f}ms │ {pct(g,50):>7.3f}ms {pct(g,95):>5.3f}ms │"
                  f" {pct(both,95):>15.3f}ms │ {a/n*1000:>10.2f} {hits[(tag, n)]/N_CALLS:>7.2f}"
                  f"{flag}{mark}")
        pre = [i for i, n in enumerate(ns) if n in GRID]
        f_pre = crossing([ns[i] for i in pre], [p95s[i] for i in pre], TRIGGER_MS)
        f_all = crossing(ns, p95s, TRIGGER_MS)
        f_sum = crossing(ns, sums, TRIGGER_MS)
        for label, (first, est, slope, kind) in (
                ("retrieve · 사전 등록 격자", f_pre), ("retrieve · 확장 포함", f_all),
                ("gate+retrieve · 확장 포함", f_sum)):
            e = f"추정 N ≈ {est:,.0f} ({kind} · 기울기 {slope*1000:.2f} µs/행)" if est else kind
            print(f"  → p95 > {TRIGGER_MS:g} ms — {label}: 첫 N {first or '없음'} · {e}")
        lin = [p50s[i] / ns[i] for i in range(len(ns)) if ns[i] >= 500]
        print(f"  → N ≥ 500에서 p50/N의 최대/최소 {max(lin)/min(lin):.2f}배 (1에 가까우면 선형)")
    print("\n⚠️ 틀을 되풀이한 합성 색인이다 — 요약 문자열이 21종뿐이라 어휘가 늘지 않는다. "
          "지연(워밍업 뒤 웜 메모 — 콜드는 retrieve_memo · 상한 절벽은 memo_multiroom)은 행 수와 길이의 함수라 이 방식으로 잴 수 있지만, "  # 🔄 (w11a) 출력 문구 고침 — 메모 전 판은 «행마다 bigram 재계산»(run_all 밖 · RESULTS.txt 무관)
          "**꺼낸 수·순위는 규모 코퍼스의 값이 아니다.**")
    return 0


if __name__ == "__main__":
    sys.exit(main())
