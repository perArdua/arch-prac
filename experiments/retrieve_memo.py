# -*- coding: utf-8 -*-
"""
retrieve_memo.py — 검색·게이트의 **내용 주소 메모**(w8code · docs/17 검B3)가 무엇을 바꾸고 무엇을 안 바꾸나. (LLM 0회 · `%TEMP%` DB)

## 왜

`retrieve`는 SQL이 `chat_id`만 거르고 **행마다** 요약을 다시 잘랐다(`set(bigrams(요약))`) — 색인 N행 × 요약 길이.
eval3 3,000행에서 p95 18.2~19.7 ms였고 SQL 몫은 ⅙ 안팎이었다(`.omc/handoff/NEXT.md` §3). 게이트의 어휘 조립
(`_recall_vocab_for`)도 행마다 정규식으로 같은 일을 했다. `memory.py` 끝 절이 두 자리를 **요약 문자열이 키인**
`functools.lru_cache`로 바꿨다(ADR-003 줄 끝 덧붙이기(w8)가 설계 비교의 정본). 이 파일은 그 교체를 잰다.

## 방법

- 코퍼스 다섯(`eval3_probe.CORPORA` — eval · eval2 · eval3 레짐 셋)을 `soak.seed` + `soak.ingest`로 무변경 적재(임시 DB).
- «전» = 끝 절의 두 이름을 **메모가 대신한 바로 그 두 표현**(`set(bigrams(s))` · 행마다 `re.findall`의 앞 2글자)으로
  잠시 되돌린 것(G13 — 되돌렸는지 객체 동일성으로 확인). 파일을 고치기 전의 코드와 같은 식이다.
- «후·콜드» = 메모를 비운 직후 한 턴 · «후·웜» = 바로 이어서 같은 턴 한 번 더. ⚠️ 콜드는 **메모만** 비운 것이다 —
  SQLite 페이지 캐시·파이썬 할당기는 따뜻하다. 프로세스를 새로 띄운 첫 턴은 이것보다 느릴 수 있다.
- 지연은 eval3 레짐 셋(각 3,000행)에서 `retrieve_scaling`의 절차를 따른다 — n = `RS.N_CALLS`(워밍업 `RS.WARMUP` 제외) ·
  라운드마다 DB 순서와 «전»/«콜드→웜» 순서를 섞음(seed `RS.SEED`). 턴 하나 = 게이트 → 검색(프로덕션 순서).
  게이트는 과거 참조 정규식·길이에서 먼저 돌아오면 어휘를 안 만든다 — 그래서 어휘 조립(`_recall_vocab_for`)을 따로도 잰다.
- 0-연산 대조: «전» 표본을 짝/홀 라운드로 갈라 p95 비를 찍는다(같은 식끼리의 흔들림).

⚠️ 지연은 기계·부하의 함수다 — **이 표의 값은 이 실행 안에서만** 비교한다. 그래서 `run_all`에 올리지 않는다
(`retrieve_scaling.py` · `eval3_probe.py`와 같은 이유).

## 실행 (G11)

    PYTHONIOENCODING=utf-8 python -B experiments/retrieve_memo.py
    PYTHONIOENCODING=utf-8 python -B experiments/retrieve_memo.py --identity-only   # 1절만 (심은 위반 하니스용)
    PYTHONIOENCODING=utf-8 python -B -m unittest discover -s prototype/tests -p "test_retrieve_memo.py" -v
    PYTHONIOENCODING=utf-8 python -B experiments/retrieve_memo.py --cliff-only      # 3절만 (1·2절 건너뜀 · 심은 위반 하니스용)
    PYTHONIOENCODING=utf-8 python -B -m unittest discover -s experiments/tests -p "test_retrieve_memo_cliff.py" -v

종료 코드: 동일성(C1)이나 복원이 깨지면 1, 아니면 0. 지연 판정(C2~C5)은 값으로 찍을 뿐 종료 코드를 바꾸지 않는다.
🔄 (w13cliff · 사후 정정) C5는 옛 규칙(h ≤ 0.10)과 새 규칙(g = h − d ≤ 0.10 · `CLIFF_GAIN`)을 나란히 찍는다 — d가 없는 칸은 «판정 불가».
"""
import functools
import hashlib
import json
import math
import os
import platform
import random
import re
import shutil
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "eval3"))
sys.stdout.reconfigure(encoding="utf-8")

import memory as M                                              # noqa: E402
import soak                                                     # noqa: E402
import retrieve_scaling as RS                                   # noqa: E402
import eval3_probe as E3P                                       # noqa: E402

W = 100
NAMES = E3P.NAMES
E3 = E3P.E3
SAMPLE_USERS = 300           # 동일성 절 — eval3의 user 턴(≈5,475)에서 고르게 뽑는 수. eval·eval2는 전량
DELETE_N = 3                 # 동일성 절 — 지운 뒤에도 같은가를 볼 삭제 수(살아 있는 행의 앞에서부터)
SMALL_CAP = 1000             # 절벽 절 — 세 레짐의 서로 다른 요약 수(1,289~2,899)보다 작은 상한
BAND = 0.10                  # 판정 띠 ±10 %
CLIFF_HIT = 0.10             # 절벽 판정 — 웜 적중률 ≤ 이 값
# 🔄 사후 정정(값을 본 뒤 · w13cliff · 2026-09-11) — 근거: 옛 규칙(위 문턱 · PREREG C5)은 적중률 h의 **수준만** 본다.
#    s1은 h 0.114로 «절벽 아님»이었지만 콜드 턴도 받는 방 안 중복 d가 ≈0.110이라 메모가 준 몫은 ≈0.004였다(docs/11 §C 🔄).
#    PREREG와 위 상수는 그대로 두고, 3절이 옛 판정과 새 판정을 **나란히** 찍는다. 새 판정은 아래 상수로만 한다.
CLIFF_GAIN = 0.10            # 새 절벽 판정 — 이득 g = h − d ≤ 이 값(d = 짝 콜드 턴의 적중 · 같은 상한의 빈 메모).
#    근거(옛 문턱과 같은 근거를 g에): 메모가 콜드 턴보다 더 아끼는 것은 토큰화 중 g 몫뿐이다 → 콜드 대비 절감 ≤ g × 콜드 턴 →
#    g ≤ 0.10이면 절감이 ±10 % 지연 띠 안이라 지연으로는 콜드와 가를 수 없다.


def old_grams(s):
    return set(M.bigrams(s))                                    # 메모 전 `retrieve`의 그 줄


def old_heads(s):
    return {w[:2] for w in re.findall(r"[가-힣]{2,}", s)}       # 메모 전 `_recall_vocab_for`의 그 두 줄


# ══════════════════════════════════════════════════════════════════════
# 사전 등록 — 값을 보기 전에 적었다. 첫 화면에 찍는다.
# ══════════════════════════════════════════════════════════════════════
PREREG = [
    # 🔄 첫 실행 뒤 고침(값과 무관한 계수 표기): «sha256 셋 · 30쌍»이라 적었는데 어휘를 방·전량 둘로 가르므로 sha가
    #    넷이고 쌍은 5 × 2 × 4 = 40이다. 판정 기준(«전부 같다»)은 한 글자도 안 바뀌었다.
    ("C1 동일성", "코퍼스 다섯 × {적재 직후, 앞 3행 삭제 뒤}마다 «전»과 «후» 사이 sha256 넷 — 검색 반환(점수 repr·"
     "행·요약·기각 사유) · 어휘(방) · 어휘(전량) · 게이트 판정",
     "참 ⇔ 40쌍 전부 같다", "거짓 ⇔ 한 쌍이라도 다르다 → 종료 1"),
    ("C2 웜 검색", "레짐마다 r = p95(후·웜) / p95(전) · p50도 나란히",
     f"r ≤ {1 - BAND:.2f} → «줄었다»", f"{1 - BAND:.2f} < r < {1 + BAND:.2f} → «구별 안 됨» · r ≥ {1 + BAND:.2f} → «늘었다»"),
    ("C3 콜드 검색", "레짐마다 r = p95(후·콜드) / p95(전)", "C2와 같은 세 칸", "(세 칸이 모든 관측을 나눈다)"),
    ("C4 어휘·게이트", "레짐마다 어휘 조립 p95 비 · 턴(게이트+검색) p95 비 — 웜·콜드 각각", "C2와 같은 세 칸", ""),
    ("C5 절벽", f"상한 {SMALL_CAP}(서로 다른 요약 수보다 작다)에서 웜 검색의 메모 적중률 h",
     f"h ≤ {CLIFF_HIT:.2f} → «절벽»(웜이 콜드가 된다)", f"h > {CLIFF_HIT:.2f} → «절벽 아님»"),
    ("C0 잡음", "«전» 표본을 짝/홀 라운드로 갈라 p95 비 q", f"|q − 1| < {BAND:.2f} → 이 실행의 ±10 % 띠를 믿는다",
     f"|q − 1| ≥ {BAND:.2f} → 그 레짐의 C2~C4 칸은 «잡음 안»으로 읽는다"),
    ("—  20 ms 자", "p95를 20 ms 옆에 찍기만 한다", "판정 아님", "자와의 차가 1 ms 안이면 만족 여부가 실행마다 갈린다(NEXT §3)"),
]


def preregistration():
    print("\n사전 등록 — 조건 · 관측 · 참/거짓이 되는 관측")
    for name, obs, t, f in PREREG:
        print(f"  {name:<12} {obs}")
        print(f"  {'':<12}   {t}  |  {f}")
    print("  예측(판정 기준 아님): 웜 < 전 · 콜드 ≈ 전(메모에 넣는 몫만큼 조금 더) · 상한 1000은 s0·s1에서 절벽.")


# ══════════════════════════════════════════════════════════════════════
# 팔 — 끝 절의 두 이름을 잠시 바꾼다 (G13)
# ══════════════════════════════════════════════════════════════════════
class Arm:
    def __init__(self, grams, heads):
        self.new = {"_doc_grams": grams, "_doc_heads": heads}

    def __enter__(self):
        self.saved = {k: getattr(M, k) for k in self.new}
        for k, v in self.new.items():
            setattr(M, k, v)
        return self

    def __exit__(self, *a):
        for k, v in self.saved.items():
            setattr(M, k, v)
        for k, v in self.saved.items():                         # 값이 아니라 **객체**로 본다
            if getattr(M, k) is not v:
                raise SystemExit(f"복원 실패: {k}")


def before():
    return Arm(old_grams, old_heads)


def clear():
    M._doc_grams.cache_clear()
    M._doc_heads.cache_clear()


def sha(x):
    return hashlib.sha256(json.dumps(x, ensure_ascii=False).encode("utf-8")).hexdigest()


# ══════════════════════════════════════════════════════════════════════
# 1. 동일성
# ══════════════════════════════════════════════════════════════════════
def users_of(corpus, cap=None):
    u = [r["text"] for r in corpus if r["role"] == "user"]
    if cap is None or len(u) <= cap:
        return u
    k = math.ceil(len(u) / cap)
    return u[::k]


def prints(m, asks, users, last):
    ret = []
    for q in asks + users:
        h, rej = m.retrieve(soak.CHAT, q, last)
        ret.append([[repr(s), r["event_id"], r["summary"]] for s, r in h] + [list(map(list, rej))])
    return dict(retrieve=sha(ret), vocab_room=sha(sorted(m._recall_vocab_for(soak.CHAT))),
                vocab_all=sha(sorted(m._recall_vocab_for(None))),
                gate=sha([list(m.gate(u, soak.CHAT)) for u in users]),
                n_hits=sum(len(x) - 1 for x in ret), n_calls=len(ret),
                n_fire=sum(m.gate(u, soak.CHAT)[0] for u in users), n_users=len(users))


def identity(tmp):
    print("\n" + "=" * W)
    print("1. 동일성 (C1) — «전»(메모가 대신한 식) 대 «후»(끝 절 메모) · 적재 직후 / 앞 3행 삭제 뒤")
    print("=" * W)
    print(f"  {'코퍼스':<18}{'단계':<10}{'검색 호출':>9}{'꺼냄':>7}{'게이트 턴':>9}{'발화':>6}   "
          f"{'검색':<6}{'어휘(방)':<9}{'어휘(전량)':<10}{'게이트':<6}  sha(검색) 앞 12")
    bad = []
    for name in NAMES:
        corpus, ledger, qs = E3P.load(name)
        m = E3P.build(tmp, name, corpus, ledger)
        try:
            asks = [q["ask"] for q in qs]
            users = users_of(corpus, None if name not in E3 else SAMPLE_USERS)
            last = corpus[-1]["seq"]
            for stage in ("적재 직후", "삭제 3건 뒤"):
                if stage != "적재 직후":
                    ids = [r[0] for r in m.db.execute(
                        "SELECT event_id FROM event WHERE chat_id=? AND user_deleted=0 ORDER BY event_id LIMIT ?",
                        (soak.CHAT, DELETE_N))]
                    for i in ids:
                        m.delete_item(soak.CHAT, "event", i)
                clear()
                after = prints(m, asks, users, last)            # 콜드에서 시작해 웜으로 끝난다
                with before():
                    ref = prints(m, asks, users, last)
                eq = {k: after[k] == ref[k] for k in ("retrieve", "vocab_room", "vocab_all", "gate")}
                for k in ("n_hits", "n_calls", "n_fire", "n_users"):
                    eq[k] = after[k] == ref[k]
                ok = all(eq.values())
                if not ok:
                    bad.append((name, stage, [k for k, v in eq.items() if not v]))
                mk = lambda k: "같음" if eq[k] else "🔴다름"
                print(f"  {name:<18}{stage:<10}{ref['n_calls']:>9}{ref['n_hits']:>7}{ref['n_users']:>9}"
                      f"{ref['n_fire']:>6}   {mk('retrieve'):<6}{mk('vocab_room'):<9}{mk('vocab_all'):<10}"
                      f"{mk('gate'):<6}  {after['retrieve'][:12]}")
        finally:
            m.db.close()
    print(f"  → C1: {'참' if not bad else '거짓'} — 다른 쌍 {len(bad)}/{len(NAMES) * 2 * 4} {bad or ''}")
    print(f"  (eval3은 user 턴 {SAMPLE_USERS}개 안팎을 고르게 뽑는다 · eval·eval2는 전량 · 검색 호출 = 문항 + 그 턴들)")
    print("  ⚠️ «삭제 3건 뒤»에 eval3은 꺼냄·발화 **수**가 안 움직였고 sha(검색)는 바뀌었다 — 둘 다 «전»과 «후»가 같이 그랬다.")
    print("     (반환에 기각 목록이 들어 있다. 무엇이 바뀌었는지는 이 절이 재지 않는다 — 이 절이 재는 것은 전후 동일성뿐이다.)")
    return not bad


# ══════════════════════════════════════════════════════════════════════
# 2. 지연 — 같은 실행 안에서 전 / 후·콜드 / 후·웜
# ══════════════════════════════════════════════════════════════════════
def one_turn(m, q, last, cold=False):
    # 🔄 첫 실행 뒤 고침: 콜드 팔의 «어휘 조립» 칸이 게이트가 **방금 데운** 앞 2글자 메모를 쟀다(게이트가 과거 참조
    #    정규식에서 먼저 돌아온 턴만 콜드였다 — 두 모집단의 섞음). 콜드면 어휘를 재기 직전에 그 메모만 다시 비운다.
    #    게이트·검색·턴 칸은 그대로다(턴 = 게이트 → 검색, 프로덕션 순서).
    if cold:
        clear()
    t0 = time.perf_counter()
    m.gate(q, soak.CHAT)
    t1 = time.perf_counter()
    m.retrieve(soak.CHAT, q, last)
    t2 = time.perf_counter()
    if cold:
        M._doc_heads.cache_clear()
        t2 = time.perf_counter()
    m._recall_vocab_for(soak.CHAT)
    t3 = time.perf_counter()
    return (t1 - t0) * 1000, (t2 - t1) * 1000, (t3 - t2) * 1000


def latency(mems, asks, last):
    rng = random.Random(RS.SEED)
    keys = list(mems)
    arms = ("전", "후·콜드", "후·웜")
    t = {(k, a, w): [] for k in keys for a in arms for w in ("gate", "ret", "vocab", "turn")}
    parity = {k: ([], []) for k in keys}
    sql = {k: [] for k in keys}
    for rnd in range(RS.WARMUP + RS.N_CALLS):
        rng.shuffle(keys)
        q = asks[rnd % len(asks)]
        for k in keys:
            m = mems[k]
            order = ["전", "콜드→웜"]
            rng.shuffle(order)
            got = {}
            for o in order:
                if o == "전":
                    with before():
                        got["전"] = one_turn(m, q, last)
                else:
                    got["후·콜드"] = one_turn(m, q, last, cold=True)
                    got["후·웜"] = one_turn(m, q, last)
            s0 = time.perf_counter()
            m.db.execute(RS.SQL_ONLY, (soak.CHAT,)).fetchall()
            s1 = time.perf_counter()
            if rnd < RS.WARMUP:
                continue
            sql[k].append((s1 - s0) * 1000)
            for a, (g, r, v) in got.items():
                t[(k, a, "gate")].append(g)
                t[(k, a, "ret")].append(r)
                t[(k, a, "vocab")].append(v)
                t[(k, a, "turn")].append(g + r)
            parity[k][rnd % 2].append(got["전"][1])
    return t, parity, sql


def cls(r):
    return "줄었다" if r <= 1 - BAND else ("늘었다" if r >= 1 + BAND else "구별 안 됨")


def show_latency(t, parity, sql, rows):
    pct = RS.pct
    print("\n" + "=" * W)
    print(f"2. 지연 (C2~C4 · C0) — eval3 레짐 셋 · n={RS.N_CALLS}/칸 (워밍업 {RS.WARMUP} 제외) · ms · 이 실행 안에서만 비교")
    print("=" * W)
    print(f"  기계: {platform.platform()} · 논리 CPU {os.cpu_count()} · Python {platform.python_version()} · "
          f"{time.strftime('%Y-%m-%d %H:%M:%S')} · 모드 {M.RETRIEVAL_MODE}")
    verdict = {}
    for k in E3:
        q = pct(parity[k][0], 95) / pct(parity[k][1], 95)
        noisy = abs(q - 1) >= BAND
        print(f"\n── {k}  (살아 있는 {rows[k][0]}행 · 서로 다른 요약 {rows[k][1]}종)  "
              f"SQL만 p50 {pct(sql[k], 50):.3f} · p95 {pct(sql[k], 95):.3f}  · C0 잡음 q = {q:.3f}"
              f"{' 🔴 ±10 % 띠 밖 — 이 레짐의 판정은 «잡음 안»' if noisy else ''}")
        print(f"  {'':<14}{'전 p50':>9}{'p95':>9} │{'후·콜드 p50':>11}{'p95':>9}{'비(p95)':>9}  {'칸':<10}│"
              f"{'후·웜 p50':>10}{'p95':>9}{'비(p95)':>9}  {'칸':<10}")
        for w, lab in (("ret", "검색"), ("vocab", "어휘 조립"), ("gate", "게이트"), ("turn", "턴(게이트+검색)")):
            b, c, h = (t[(k, a, w)] for a in ("전", "후·콜드", "후·웜"))
            rc, rw = pct(c, 95) / pct(b, 95), pct(h, 95) / pct(b, 95)
            verdict[(k, w)] = (rc, rw, noisy)
            flag = lambda x: f"{x:>7.3f}" + (" 🔸" if x > RS.TRIGGER_MS else "  ")
            print(f"  {lab:<14}{pct(b, 50):>9.3f}{flag(pct(b, 95))}│{pct(c, 50):>11.3f}{flag(pct(c, 95))}"
                  f"{rc:>7.3f}  {cls(rc):<10}│{pct(h, 50):>10.3f}{flag(pct(h, 95))}{rw:>7.3f}  {cls(rw):<10}")
    print(f"\n  🔸 = p95 > {RS.TRIGGER_MS:g} ms (ADR-003 재검토 자) — **판정 아님**. 자와 1 ms 안이면 실행마다 갈린다.")
    print("  → C2 웜 검색: " + " · ".join(f"{k} {cls(verdict[(k, 'ret')][1])}(×{verdict[(k, 'ret')][1]:.2f})" for k in E3))
    print("  → C3 콜드 검색: " + " · ".join(f"{k} {cls(verdict[(k, 'ret')][0])}(×{verdict[(k, 'ret')][0]:.2f})" for k in E3))
    print("  → C4 턴 웜/콜드: " + " · ".join(
        f"{k} {cls(verdict[(k, 'turn')][1])}/{cls(verdict[(k, 'turn')][0])}" for k in E3))
    return verdict


# ══════════════════════════════════════════════════════════════════════
# 3. 절벽 — 상한이 서로 다른 요약 수보다 작으면
# ══════════════════════════════════════════════════════════════════════
def c5_old(h):
    """옛 규칙(PREREG C5 · 값 전) — 적중률 h의 수준만 본다."""
    return "«절벽»" if h <= CLIFF_HIT else "«절벽 아님»"


def c5_new(h, d):
    """새 규칙(사후 정정 · 값을 본 뒤) — 이득 g = h − d. d가 없으면 판정하지 않는다(숫자를 만들지 않는다)."""
    if d is None:
        return "판정 불가(d 없음)"
    return "«절벽»" if h - d <= CLIFF_GAIN else "«절벽 아님»"


def c5_row(k, wh, wn, ch, cn, cold95, d_tau, n_tau):
    """3절 새 표의 한 줄 — 옛 판정과 새 판정을 **나란히**(옛 칸을 지우지 않는다). 콜드 호출 0 → d 없음(만들지 않는다)."""
    hs = wh / max(wn, 1)
    d = ch / cn if cn else None
    coef = 1 - d_tau / n_tau if n_tau else float("nan")
    gtxt = f"{hs - d:>9.3f}" if d is not None else f"{'—':>9}"
    dtxt = f"{d:>7.3f}" if d is not None else f"{'—':>7}"
    return (f"  {k:<18}{f'{wh}/{wn}':>18}{hs:>7.3f} │{f'{ch}/{cn}':>18}{dtxt}{cold95:>9.3f} │"
            f"{coef:>8.3f} │{gtxt}  {c5_old(hs):<12}{c5_new(hs, d):<14}")


def cold_turn(m, q, last, cap):
    """짝 콜드 턴 — **새** 빈 메모 한 쌍(상한 cap)을 끝 절 이름에 꽂고 검색 한 번. (ms, 적중, 호출).
    웜 팔의 메모 객체는 건드리지 않는다(옛 칸의 적중 수는 이 턴과 무관하다)."""
    cg = functools.lru_cache(maxsize=cap)(M._grams_raw)
    with Arm(cg, functools.lru_cache(maxsize=cap)(M._heads_raw)):
        t0 = time.perf_counter()
        m.retrieve(soak.CHAT, q, last)
        t1 = time.perf_counter()
    i = cg.cache_info()
    return (t1 - t0) * 1000, i.hits, i.hits + i.misses


def cliff(mems, asks, last, rows):
    small_g = functools.lru_cache(maxsize=SMALL_CAP)(M._grams_raw)
    small_h = functools.lru_cache(maxsize=SMALL_CAP)(M._heads_raw)
    rng = random.Random(RS.SEED + 1)
    keys = list(mems)
    t = {(k, a): [] for k in keys for a in ("기본", "작음", "작음·콜드")}
    hit = {(k, a): [0, 0] for k in keys for a in ("기본", "작음", "작음·콜드")}
    for rnd in range(RS.WARMUP + RS.N_CALLS):
        rng.shuffle(keys)
        q = asks[rnd % len(asks)]
        for k in keys:
            order = ["기본", "작음"]
            rng.shuffle(order)
            for a in order:
                if a == "작음":                                 # 🔄 (w13cliff) 짝 콜드 — rng를 안 부른다(옛 칸의 순서 흐름 그대로)
                    c = cold_turn(mems[k], q, last, SMALL_CAP)
                arm = Arm(small_g, small_h) if a == "작음" else Arm(M._doc_grams, M._doc_heads)
                with arm:
                    g = M._doc_grams
                    mems[k].retrieve(soak.CHAT, q, last)       # 웜으로 만든다
                    i0 = g.cache_info()
                    t0 = time.perf_counter()
                    mems[k].retrieve(soak.CHAT, q, last)
                    t1 = time.perf_counter()
                    i1 = g.cache_info()
                if rnd >= RS.WARMUP:
                    t[(k, a)].append((t1 - t0) * 1000)
                    hit[(k, a)][0] += i1.hits - i0.hits
                    hit[(k, a)][1] += (i1.hits - i0.hits) + (i1.misses - i0.misses)
                    if a == "작음":
                        t[(k, "작음·콜드")].append(c[0])
                        hit[(k, "작음·콜드")][0] += c[1]
                        hit[(k, "작음·콜드")][1] += c[2]
    print("\n" + "=" * W)
    print(f"3. 절벽 (C5) — 메모 상한 {SMALL_CAP} 대 기본 {M.MEMO_ROWS} · 웜 검색 · n={RS.N_CALLS}/칸 · 이 실행 안")
    print("=" * W)
    print(f"  {'레짐':<18}{'서로 다른 요약':>12}{'τ 통과 행':>10} │{'기본 적중률':>10}{'p95':>9} │{'작음 적중률':>10}{'p95':>9}"
          f"{'비':>7}  C5")
    out = {}
    for k in E3:
        hb, hs = (hit[(k, a)][0] / max(hit[(k, a)][1], 1) for a in ("기본", "작음"))
        pb, ps = RS.pct(t[(k, "기본")], 95), RS.pct(t[(k, "작음")], 95)
        out[k] = hs
        print(f"  {k:<18}{rows[k][1]:>12}{rows[k][3]:>10} │{hb:>10.3f}{pb:>9.3f} │{hs:>10.3f}{ps:>9.3f}{ps / pb:>7.2f}  "
              f"{c5_old(hs)}")
    print("  ⚠️ 적중률의 분모는 **τ를 통과해 조각을 잰 행**이다(τ 미만은 메모를 안 부른다). 같은 요약이 한 번의 훑기 안에서")
    print("     상한보다 가까이 다시 나오면 작은 상한에서도 맞는다 — 소수 지배 레짐(서로 다른 요약이 적다)이 그 자리다.")
    print(f"\n  🔄 C5 옛 규칙 / 새 규칙 나란히 — 새 규칙은 **사후 정정(값을 본 뒤)** · 근거: 옛 규칙은 수준만 본다"
          f"(콜드 턴도 받는 방 안 중복 d를 안 뺀다). 새: 이득 g = h − d ≤ {CLIFF_GAIN:.2f} → «절벽»(±10 % 지연 띠 안)")
    print(f"  {'레짐':<18}{'작음 웜 적중/호출':>18}{'h':>7} │{'짝 콜드 적중/호출':>18}{'d':>7}{'콜드 p95':>9} │"
          f"{'1−D_τ/n':>8} │{'g = h − d':>9}  {'옛 C5(h)':<12}{'새(g · 사후)':<14}")
    for k in E3:
        (wh, wn), (ch, cn) = hit[(k, "작음")], hit[(k, "작음·콜드")]
        print(c5_row(k, wh, wn, ch, cn, RS.pct(t[(k, "작음·콜드")], 95), rows[k][4], rows[k][3]))
    print(f"  d = 짝 콜드 턴(같은 라운드 · 같은 질의 · 새 빈 메모 · 상한 {SMALL_CAP})의 적중 — 옛 칸(웜)의 메모는 안 건드린다."
          " 1−D_τ/n = 방 안 중복 계수(τ 통과 행 중 서로 다른 요약 D_τ · 상한이 없을 때의 콜드 적중 — 대조용, 판정에 안 쓴다).")
    return out


def memory_cost(mems, asks, last):
    clear()
    tracemalloc.start()
    for k, m in mems.items():
        m.retrieve(soak.CHAT, asks[0], last)
        m._recall_vocab_for(soak.CHAT)
    cur, _ = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    ng, nh = M._doc_grams.cache_info().currsize, M._doc_heads.cache_info().currsize
    print(f"\n  메모 크기(세 레짐을 한 번씩 훑은 뒤): 조각 {ng}항목 · 앞 2글자 {nh}항목 · tracemalloc 현재 {cur / 1024:.0f} KiB "
          f"= 항목당 {cur / max(ng + nh, 1):.0f} B (두 메모 합) · 상한 {M.MEMO_ROWS}×2까지 차면 ≈ "
          f"{cur / max(ng + nh, 1) * M.MEMO_ROWS * 2 / 2**20:.0f} MiB")


def main():
    t_start = time.perf_counter()
    print("=" * W)
    print("retrieve_memo — 검색·게이트의 내용 주소 메모 (LLM 0회 · 임시 DB · 같은 실행 안의 전후)")
    print("=" * W)
    preregistration()
    tmp = tempfile.mkdtemp(prefix="w8memo_")
    mems = {}
    try:
        cliff_only = "--cliff-only" in sys.argv                 # 🔄 (w13cliff) 3절만 — 1절(C1)을 안 보므로 종료 코드는 복원만 본다
        ok = True if cliff_only else identity(tmp)
        if "--identity-only" in sys.argv:
            return 0 if ok else _fail()
        rows, asks, last = {}, None, None
        for name in E3:
            corpus, ledger, qs = E3P.load(name)
            mems[name] = _build_lat(tmp, name, corpus, ledger)
            live = [r[0] for r in mems[name].db.execute(
                "SELECT summary FROM event WHERE chat_id=? AND user_deleted=0 ORDER BY event_id", (soak.CHAT,))]
            npass = mems[name].db.execute(
                "SELECT COUNT(*) FROM event WHERE chat_id=? AND user_deleted=0 AND"
                " MAX(COALESCE(importance,0), COALESCE(emotional_weight,0)) >= ?",
                (soak.CHAT, M.TAU_IMPORTANCE)).fetchone()[0]
            dpass = mems[name].db.execute(                      # 🔄 (w13cliff) τ 통과 행 중 서로 다른 요약 — 3절 대조 열
                "SELECT COUNT(DISTINCT summary) FROM event WHERE chat_id=? AND user_deleted=0 AND"
                " MAX(COALESCE(importance,0), COALESCE(emotional_weight,0)) >= ?",
                (soak.CHAT, M.TAU_IMPORTANCE)).fetchone()[0]
            rows[name] = (len(live), len(set(live)), live[0], npass, dpass)
            asks = [q["ask"] for q in qs]
            last = corpus[-1]["seq"]
        if not cliff_only:
            t, parity, sql = latency(mems, asks, last)
            show_latency(t, parity, sql, rows)
        cliff(mems, asks, last, rows)
        memory_cost(mems, asks, last)
    finally:
        for m in mems.values():
            m.db.close()
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n  (소요 {time.perf_counter() - t_start:.0f} s)")
    return 0 if ok else _fail()


def _fail():
    print("🔴 C1 거짓 — 종료 1")
    return 1


def _build_lat(tmp, name, corpus, ledger):
    """지연용 DB — 동일성 절의 DB와 파일이 겹치지 않게 이름만 다르다(`soak.seed` + `soak.ingest` 무변경)."""
    m = M.Memory(os.path.join(tmp, f"lat_{E3P.NAMES.index(name)}.db"))
    soak.seed(m)
    soak.ingest(m, corpus, ledger, timed=False)
    return m


if __name__ == "__main__":
    sys.exit(main())
