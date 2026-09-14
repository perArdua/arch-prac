# -*- coding: utf-8 -*-
"""
memo_multiroom.py — 검색 메모의 **절벽**을 **방 여럿 · 한 프로세스** 부하에서 잰다. (LLM 0회 · `%TEMP%` DB · `run_all` 밖)

## 왜

`memory.py` 끝 절의 두 메모 — `_doc_grams`(검색이 τ를 통과한 행마다 부른다) · `_doc_heads`(게이트의 어휘 조립이
살아 있는 행마다 부른다) — 는 요약 문자열이 키인 `functools.lru_cache`이고, 상한 `MEMO_ROWS`는 **프로세스 전역** 몫이다.
`retrieve_memo.py` 3절은 방 **하나**에서 상한을 1,000으로 줄여 절벽(s0 적중 2.3 %)을 봤다. 방 여럿이 한 프로세스를 나눠
쓰면 상한에 먼저 닿는다 — 그 부하는 잰 적이 없다(docs/17 검B3의 딸린 🔓 ② · 엔진 결정의 «다시 열리는 경우» ② —
`docs/decisions/decisions-0911.md` §4). 이 파일은 **재기만 한다** — 상한을 올릴지 · 방 단위로 나눌지는 다음 결정이다.

## 방법

- **방** = eval3 레짐 하나의 살아 있는 색인(`retrieve_scaling.template_rows` — `soak.seed` + `soak.ingest` 무변경)의 앞 N행을
  **방마다 DB 파일 하나**에 복사한 것. 방 k의 요약 끝에 **꼬리표**(빈칸 + 비단어 문자 셋)를 붙여 방마다 다른 문자열 = 다른
  메모 키로 만든다. 꼬리표는 `bigrams`(낱말의 비단어 문자를 지운다)와 앞 2글자 정규식(한글 2자 이상) **둘 다에서 사라진다** —
  조각·점수·순위가 틀과 같고 **메모 키만** 갈린다(시작할 때 요약 전부에서 단언 · 깨지면 종료 1). 방 안 중복 구조(레짐의 성질)는 그대로다.
- **공유 비율 s** — 틀의 서로 다른 요약 중 s 몫(요약의 sha로 결정적으로 고른다)은 꼬리표 없이 모든 방이 같은 문자열을 쓴다.
  다른 사람의 기억이면 같은 요약 문자열이 거의 없다 → 주 조건은 s = 0.
- 방마다 DB를 따로 둔다 — 스키마에 `chat_id` 색인이 없어 한 DB에 방을 모으면 SQL이 R·N행을 훑는다(메모와 무관한 비용 ·
  검B3 ③). 이 파일은 **메모만** 가른다.
- **턴** = 게이트의 어휘 조립(`_recall_vocab_for`) → 검색(`retrieve`). 두 메모를 **모두** 부르는 턴이다. 게이트가 과거 참조
  정규식에서 먼저 돌아오는 턴은 `_doc_heads`를 안 부른다 — 그런 턴의 메모 압력은 이것보다 작다.
- 칸마다 **새** 메모 한 쌍(`functools.lru_cache(maxsize=C)`로 끝 절의 `_grams_raw`·`_heads_raw`를 감싼 것)을 끝 절 두 이름에
  잠시 꽂는다(G13 — `try/finally` 복원 · 객체 동일성 확인). ⚠️ `MEMO_ROWS`를 다시 묶는 것만으로는 상한이 **안 바뀐다** —
  `lru_cache`의 상한은 감쌀 때 고정된다(시작할 때 실측해 찍는다). 그래서 이름을 다시 묶는다.
- **지연** — 잰 턴마다 **짝 콜드 턴**(같은 방 · 같은 질의 · 빈 메모 한 쌍)을 순서를 섞어 잇달아 잰다. 콜드 대비 비는 같은 칸 ·
  같은 시간 창 안의 비다. 칸끼리의 절대 ms는 같은 실행 안에서도 시간 창이 다르다 — 비를 본다.
- **적중률은 LRU 흉내(sim)로도 센다** — 같은 `functools.lru_cache`에 요약 대신 정수 키를 흘린다(토큰화 0). 실측 칸마다 sim의
  (적중, 빗나감)이 실측과 **정수로 같아야** 한다(깨지면 종료 1). 같으면 조밀한 격자(R = 1…48 · 상한 여럿 · 공유 여럿)는 sim으로
  적는다 — **sim은 적중률만** 말한다. 지연은 실측 칸에서만.

## 실행 (G11)

    PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -B experiments/memo_multiroom.py --part real   # 실측 칸 + sim 대조
    PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -B experiments/memo_multiroom.py --part sim    # 조밀 격자(적중률만)
    PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -B experiments/memo_multiroom.py --part real --quick   # 자기 검사만 (심은 위반용)
    PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s experiments/tests -p "test_memo_multiroom.py" -v

종료 코드: 꼬리표 불변 · 접근 순서 재구성 · sim = 실측 · 복원 · 상한 고정 확인 중 하나라도 깨지면 1, 아니면 0.
사전 등록 조건의 참/거짓은 **값으로 찍을 뿐** 종료 코드를 바꾸지 않는다.
🔄 (w13cliff · 사후 정정) 절벽 판정은 옛 규칙(h ≤ 0.10)과 새 규칙(이득 g = h − d ≤ 0.10 · `CLIFF_GAIN`)을 나란히 찍는다.
   새 규칙의 sim d(`cold_sim`)가 실측 칸의 짝 콜드 d와 다르면 종료 1(자기 검사 하나 더).
⚠️ `eval3_probe.load`를 안 쓴다 — 그 모듈은 계측기 여럿을 함께 올린다. 경로 셋만 읽는다(`eval3/`는 읽기만).
"""
import argparse
import collections
import functools
import hashlib
import json
import os
import platform
import random
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
sys.stdout.reconfigure(encoding="utf-8")

import yaml                                                     # noqa: E402
import memory as M                                              # noqa: E402
import soak                                                     # noqa: E402
import retrieve_scaling as RS                                   # noqa: E402

W = 118
ORIGINAL = (M._doc_grams, M._doc_heads)     # 끝 절 두 메모 — 마감에 **객체**로 대조한다

# ══════════════════════════════════════════════════════════════════════
# 사전 등록 상수 — 적중률·지연 값을 보기 전에 박았다. 첫 화면에 찍는다.
# (레짐마다 D는 코퍼스의 성질이라 격자를 고르기 전에 셌다 — 1절이 다시 찍는다.)
# ══════════════════════════════════════════════════════════════════════
REGIMES = (("s0", "s0-flat"), ("s1", "s1-zipf"), ("s2", "s2-dominant"))
RG = tuple(r for r, _ in REGIMES)
CAP = M.MEMO_ROWS                 # 16384 — 오늘의 상한(읽기만 한다)
CAP_SCALED = CAP // 4             # 4096 — 경계가 상한에 비례하는지 보는 실측 한 줄
N_MEAS = 100                      # 칸당 잰 턴 (n ≥ 100)
CLIFF_HIT = 0.10                  # 절벽 — retrieve_memo C5와 같은 문턱 (근거는 PREREG «문턱»)
# 🔄 사후 정정(값을 본 뒤 · w13cliff · 2026-09-11) — 근거: 옛 문턱(위 상수 · PREREG «문턱»)은 h의 **수준만** 본다. 경계 너머
#    h = d(콜드 턴도 받는 방 안 중복)인 칸을 «절벽 아님»으로 적었다(w11a P2 · docs/11 §H). PREREG와 위 상수는 그대로 두고,
#    옛 판정(▼ · P2 · P3)과 새 판정을 **나란히** 찍는다. 새 판정은 아래 상수로만 한다(retrieve_memo `CLIFF_GAIN`과 같은 값).
CLIFF_GAIN = 0.10                 # 새 절벽 — 이득 g = h − d ≤ 이 값. 근거: 메모가 콜드 턴보다 더 아끼는 몫이 g라 절감 ≤ g × 콜드 턴 →
                                  # g ≤ 0.10이면 ±10 % 지연 띠 안 → 지연으로는 콜드와 가를 수 없다(옛 문턱과 같은 근거를 g에)
FULL_HIT = 0.90                   # 경계 안쪽 — «거의 다 맞는다»
BAND = 0.10                       # 지연 띠 ±10 % (retrieve_memo와 같다)
FLOOR_EPS = 0.01                  # «콜드와 같음» — h ≤ d + 0.01 (d = 콜드 턴도 받는 방 안 중복 적중)
HOT_P = 0.8                       # 한 방 몰림 — 턴의 80 %가 방 0, 나머지는 다른 방에 균등
SEED = 20260911
TAG_ALPHABET = "!#$%&*+-=~"       # 비단어 문자 10개 — 방 번호의 10진 세 자리
ORDERS = ("순환", "균등 무작위", "한 방 몰림")


def warmup(r):
    """잰 턴 앞의 턴 수 — 순환이면 모든 방을 두 번 돈 뒤부터 잰다."""
    return 2 * r + 5


# 실측 칸 — (레짐, 방당 N, 순서, 공유 s, 상한 C, R 격자). R 격자는 예측 경계 C/D 둘레다(D = 1절).
R_REAL = {3000: (1, 2, 4, 6, 8, 12, 16), 1000: (1, 8, 16, 24, 32, 40)}
REAL_CELLS = (
    [(rg, n, "순환", 0.0, CAP, R_REAL[n]) for rg in RG for n in (3000, 1000)]
    + [("s0", 3000, o, 0.0, CAP, R_REAL[3000]) for o in ("균등 무작위", "한 방 몰림")]
    + [("s0", 3000, "순환", 0.0, CAP_SCALED, (1, 2, 4))]
    + [("s0", 3000, "순환", 0.5, CAP, (8, 16))]
)
QUICK_CELLS = [("s0", 1000, "순환", 0.0, CAP_SCALED, (1, 8))]   # --quick: 자기 검사만 (심은 위반 하니스)

# sim 격자 — 적중률만. R = 1…48 전부.
R_SIM = tuple(range(1, 49))
SIM_ROWS = (
    [(rg, n, "순환", 0.0, CAP) for rg in RG for n in (500, 1000, 2000, 3000)]
    + [(rg, n, o, 0.0, CAP) for rg in RG for n in (1000, 3000) for o in ("균등 무작위", "한 방 몰림")]
    + [(rg, 3000, "순환", s, CAP) for rg in ("s0", "s1") for s in (0.25, 0.5, 0.75, 1.0)]
    + [(rg, 3000, "순환", 0.0, c) for rg in RG for c in (CAP // 4, CAP // 2, CAP * 2)]
)

PREREG = [
    ("부하", "방 R개(실측 R 격자 · sim 1…48) × 방당 N행(실측 1,000 · 3,000 · sim 500~3,000) · 방마다 DB 하나 · 프로세스 하나 · "
     f"상한 C = {CAP}(오늘) · {CAP_SCALED} · sim은 {CAP // 4}~{CAP * 2}",
     "(조건 아님 — 부하의 정의)", ""),
    ("공유 s", "방 사이 같은 요약 문자열의 몫 — 주 조건 0(다른 사람의 기억) · sim 0.25~1.0 · 실측 0.5 두 칸",
     "(축)", ""),
    ("순서", f"순환(0,1,…,R−1 되풀이 — LRU에 가장 나쁜 꼴) · 균등 무작위 · 한 방 몰림(방 0이 {HOT_P:.0%})",
     "(축)", ""),
    ("지표", "h = 메모 적중 / 메모 호출(검색 = τ 통과 행 · 어휘 = 살아 있는 행) · 턴 p50/p95 · 짝 콜드 p95 대비 비 r95 · "
     "d = 짝 콜드 턴의 적중(방 안 중복 — 콜드도 받는다) · 몫 q = (공유 키 + R × 방 고유 키) / C",
     "(관측의 정의)", ""),
    ("문턱", f"h ≤ {CLIFF_HIT:.2f} → «절벽»(retrieve_memo C5와 같은 값 — 두 파일의 «절벽»이 같은 뜻이 되게). 근거: 턴 = SQL + "
     "토큰화 + 나머지이고 메모가 아끼는 것은 토큰화 중 h 몫뿐이다 → 콜드 대비 절감 ≤ h × 콜드 턴. h ≤ 0.10이면 절감 ≤ 10 % = "
     f"지연 띠 ±{BAND:.0%} 안 → 지연으로는 콜드와 가를 수 없다",
     "⚠️ 문턱은 수준만 본다 — 하락은 «첫 h < 0.90»으로, 콜드와의 같음은 «h ≤ d + 0.01»로 곁에 찍는다", ""),
    ("P1 경계 = 몫 1", "순환 · s = 0 · 메모마다 · 상한마다: 칸의 q와 h",
     f"참 ⇔ q ≤ 1인 칸 전부 h ≥ {FULL_HIT:.2f} 이고 q > 1인 칸 전부 h ≤ d + {FLOOR_EPS:.2f}",
     "거짓 ⇔ 어긋나는 칸이 하나라도 있다(그 칸을 찍는다)"),
    ("P2 절벽이 온다", "레짐 · N · 순서 · 메모마다 격자 안의 첫 h ≤ 0.10",
     "참 ⇔ 그런 R이 격자 안에 있다 → 그 R · R·N · 몫을 찍는다", "거짓 ⇔ 없다 → 격자의 가장 낮은 h를 찍는다"),
    ("P3 순서", "균등 무작위 · 한 방 몰림 대 순환 (같은 레짐 · N · C · s = 0)",
     "«무작위의 하락이 순환과 같은 R에서 시작» 참 ⇔ 첫 h < 0.90의 R이 같다 · «몰림엔 절벽 없음» 참 ⇔ 격자 전부 h > 0.10",
     "각각 그 관측이 아니면 거짓"),
    ("P4 지연", "실측 순환 칸(R ≥ 2): 두 메모의 몫(q검색 · q어휘)과 r95 = p95(턴) / p95(짝 콜드)",
     f"참 ⇔ 두 몫 다 ≤ 1인 칸 전부 r95 ≤ {1 - BAND:.2f}(줄었다) 이고 두 몫 다 > 1인 칸 전부 r95 > {1 - BAND:.2f}"
     "(콜드와 구별 안 됨 · 또는 더 느림) · 한 몫만 넘은 칸은 값만 찍는다(기대 없음)",
     "거짓 ⇔ 한 칸이라도 어긋남 · C0 잡음 |q₀−1| ≥ 0.10인 칸은 «잡음 안»으로 따로 적는다"),
    ("P5 상한 비례", f"P1을 상한 {CAP // 4} · {CAP // 2} · {CAP} · {CAP * 2}(sim)와 {CAP_SCALED}(실측)에서",
     "참 ⇔ 모든 상한에서 P1이 참", "거짓 ⇔ 한 상한에서라도 P1이 거짓"),
    ("P6 공유", "순환 · s > 0: q_s = (D·s′ + R·D·(1−s′)) / C (s′ = 그 메모 키 중 실제 공유 몫)",
     f"참 ⇔ q_s ≤ 1 칸 전부 h ≥ {FULL_HIT:.2f} 이고 q_s > 1 칸 전부 h < {FULL_HIT:.2f}", "거짓 ⇔ 한 칸이라도 어긋남"),
    ("S sim = 실측", "실측 칸마다 (적중, 빗나감) 두 메모", "참 ⇔ 정수로 같다", "거짓 ⇔ 한 칸이라도 다르다 → 종료 1"),
    ("C0 잡음", "짝 콜드 표본을 짝/홀 턴으로 갈라 p95 비 q₀", f"|q₀ − 1| < {BAND:.2f} → 그 칸의 띠를 믿는다",
     f"|q₀ − 1| ≥ {BAND:.2f} → 그 칸의 P4는 «잡음 안»"),
]


def preregistration():
    print("\n사전 등록 — 상수 · 관측 · 참/거짓이 되는 관측 (값을 보기 전에 박았다)")
    for name, obs, t, f in PREREG:
        print(f"  {name:<14} {obs}")
        if t or f:
            print(f"  {'':<14}   {t}{'  |  ' + f if f else ''}")
    print("  예측(판정 기준 아님): 순환이면 경계는 몫 q = 1(R·D = C)에서 계단 — 넘으면 방 사이 적중이 0이 되고 h는 d로 떨어진다 ·"
          " 무작위는 같은 자리에서 비탈 · 몰림은 방 0이 버틴다 · 어휘 메모(D가 크다)가 검색 메모보다 먼저 닿는다.")
    print("  🔄 (본 격자 값 전 · 시험이 잡음) d는 바닥의 **아래 끝**이다 — 한 훑기에 두 번 나오는 키는 **마지막** 출현부터 재므로"
          " 경계 너머에서도 방 사이 적중을 받을 수 있다. P1의 기준은 바꾸지 않았다.")
    print(f"  🔄 사후 정정(값을 본 뒤 · w13cliff) — 근거: 옛 문턱은 h의 수준만 본다. 새 규칙: 이득 g = h − d ≤ {CLIFF_GAIN:.2f} → "
          f"«절벽»(d = 짝 콜드 턴의 적중 · sim은 같은 상한의 빈 LRU에 방 하나를 흘린 적중). 옛 판정은 그대로 찍고 새 판정을 곁에 찍는다"
          " — 위 사전 등록 문장은 안 바꿨다.")


# ══════════════════════════════════════════════════════════════════════
# 방 — 꼬리표 · 공유 · 접근 순서
# ══════════════════════════════════════════════════════════════════════
def tag(k):
    """방 k의 꼬리표 — 빈칸 + 비단어 문자 셋. 두 토크나이저 모두에서 사라진다(`tag_invariant`)."""
    a = TAG_ALPHABET
    return " " + a[k // 100 % 10] + a[k // 10 % 10] + a[k % 10]


def tag_invariant(summaries, ks=(0, 7, 42, 999)):
    """꼬리표를 붙여도 조각·앞 2글자가 같은가 — 어긋난 요약 목록(비면 참)."""
    bad = []
    for s in summaries:
        g, h = M.bigrams(s), M._heads_raw(s)
        for k in ks:
            if M.bigrams(s + tag(k)) != g or M._heads_raw(s + tag(k)) != h:
                bad.append((s, k))
                break
    return bad


def shared_set(distinct, s):
    """틀의 서로 다른 요약 중 s 몫 — 요약 sha 순으로 앞에서부터(결정적 · PYTHONHASHSEED 무관)."""
    distinct = sorted(set(distinct))
    if s <= 0:
        return frozenset()
    ranked = sorted(distinct, key=lambda x: hashlib.sha256(f"{SEED}|{x}".encode("utf-8")).hexdigest())
    return frozenset(ranked[:round(s * len(ranked))])


def room_order(order, r, turns, key):
    """칸의 방 접근 순서 — 실측과 sim이 **같은 목록**을 쓴다(문자열 시드 = sha512 · 결정적)."""
    rng = random.Random(f"{SEED}|{key}")
    if order == "순환":
        return [i % r for i in range(turns)]
    if order == "균등 무작위":
        return [rng.randrange(r) for _ in range(turns)]
    if order == "한 방 몰림":
        return [0 if r == 1 or rng.random() < HOT_P else 1 + rng.randrange(r - 1) for _ in range(turns)]
    raise ValueError(order)


def passes_tau(r):
    return max(r["importance"] or 0, r["emotional_weight"] or 0) >= M.TAU_IMPORTANCE   # retrieve 2단계와 같은 식


class RoomSet:
    """한 (틀, N, 공유 s) — 방 k의 요약 = 틀 요약 + 꼬리표(k), 공유 요약은 꼬리표 없이 그대로."""

    def __init__(self, tpl, n, share):
        rows = tpl[:n]
        if len(rows) != n:
            raise ValueError(f"틀이 {len(rows)}행 < N {n}")
        self.rows, self.n, self.share = rows, n, share
        self.base = {"h": [r["summary"] for r in rows],                     # 어휘 조립 — 살아 있는 행 전부
                     "g": [r["summary"] for r in rows if passes_tau(r)]}    # 검색 — τ 통과 행만
        self.shared = shared_set(self.base["h"], share)
        sid = {s: i for i, s in enumerate(sorted(set(self.base["h"])))}
        self._ids = {w: [(sid[s], s in self.shared) for s in self.base[w]] for w in "gh"}
        self._cache = {}

    def key(self, s, k):
        return s if s in self.shared else s + tag(k)

    def strings(self, w, k):
        return [self.key(s, k) for s in self.base[w]]

    def seq(self, w, k):
        """sim 전용 정수 키 — 공유 요약은 방과 무관한 키, 아니면 방마다 다른 키."""
        ck = (w, k)
        if ck not in self._cache:
            self._cache[ck] = [i * 1000 if sh else i * 1000 + k + 1 for i, sh in self._ids[w]]
        return self._cache[ck]

    def forget(self):
        self._cache.clear()

    def stats(self, w):
        """(호출 수, 서로 다른 키 D, 그중 공유 키, d = 콜드 턴의 방 안 중복 적중)."""
        b = self.base[w]
        d = len(set(b))
        return len(b), d, len(set(b) & self.shared), 1 - d / len(b)

    def q(self, w, r, cap):
        _, d, ds, _ = self.stats(w)
        return (ds + r * (d - ds)) / cap


def build_room(path, rs, k):
    """방 k의 DB — `retrieve_scaling.build_db`와 같은 열 · `soak.seed` 무변경."""
    m = M.Memory(path)
    soak.seed(m)
    m.db.executemany(
        "INSERT INTO event (chat_id, summary, occurred_at, emotional_weight, importance,"
        " narrative_role, source_from_seq) VALUES (?,?,?,?,?,?,?)",
        [(soak.CHAT, rs.key(r["summary"], k), r["occurred_at"], r["emotional_weight"], r["importance"],
          r["narrative_role"], r["source_from_seq"]) for r in rs.rows])
    m.db.commit()
    live = m.db.execute("SELECT COUNT(*) c FROM event WHERE chat_id=? AND user_deleted=0", (soak.CHAT,)).fetchone()["c"]
    if live != rs.n:
        raise RuntimeError(f"방 {k}: 살아 있는 {live}행 ≠ {rs.n}")
    return m


# ══════════════════════════════════════════════════════════════════════
# 끝 절 두 이름 바꾸기 (G13)
# ══════════════════════════════════════════════════════════════════════
class RestoreError(RuntimeError):
    pass


class Swap:
    """끝 절의 `_doc_grams`·`_doc_heads`를 잠시 바꾼다 — 나올 때 **객체**로 복원을 확인한다(예외가 나도)."""

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
        for k, v in self.saved.items():
            if getattr(M, k) is not v:
                raise RestoreError(f"복원 실패: {k}")


def memo_pair(cap):
    return (functools.lru_cache(maxsize=cap)(M._grams_raw), functools.lru_cache(maxsize=cap)(M._heads_raw))


def cap_is_fixed():
    """`MEMO_ROWS`를 다시 묶어도 끝 절 메모의 상한이 안 바뀌는가 — (전, 다시 묶은 뒤, 새로 감싼 상한 7, 복원)."""
    before = M._doc_grams.cache_info().maxsize
    saved = M.MEMO_ROWS
    try:
        M.MEMO_ROWS = 7
        during = M._doc_grams.cache_info().maxsize, M._doc_heads.cache_info().maxsize
    finally:
        M.MEMO_ROWS = saved
    fresh = functools.lru_cache(maxsize=7)(M._grams_raw).cache_info().maxsize
    return before, during, fresh, M.MEMO_ROWS == saved


def record(m, q, last):
    """이 방에서 한 턴이 메모에 흘리는 키 순서 — 실제 코드 경로를 기록한다(메모 없이)."""
    g, h = [], []
    with Swap(lambda s: (g.append(s), M._grams_raw(s))[1], lambda s: (h.append(s), M._heads_raw(s))[1]):
        m._recall_vocab_for(soak.CHAT)
        m.retrieve(soak.CHAT, q, last)
    return g, h


# ══════════════════════════════════════════════════════════════════════
# 칸 — 실측 / sim
# ══════════════════════════════════════════════════════════════════════
def timed_turn(m, q, last):
    t0 = time.perf_counter()
    m._recall_vocab_for(soak.CHAT)
    t1 = time.perf_counter()
    m.retrieve(soak.CHAT, q, last)
    t2 = time.perf_counter()
    return (t2 - t0) * 1000, (t2 - t1) * 1000


def cold_turn(m, q, last, cap):
    cg, ch = memo_pair(cap)
    with Swap(cg, ch):
        t = timed_turn(m, q, last)
    return t, cg.cache_info(), ch.cache_info()


def real_cell(rooms, order, n_warm, cap, asks, last, rng):
    """칸 하나 — 새 메모 한 쌍으로 잰다. 잰 턴마다 짝 콜드 턴(빈 메모)을 섞은 순서로."""
    g, h = memo_pair(cap)
    lat = {k: [] for k in ("turn", "ret", "cold", "cold_ret")}
    cold = {"g": [0, 0], "h": [0, 0]}
    with Swap(g, h):
        for i, r in enumerate(order):
            m, q = rooms[r], asks[i % len(asks)]
            if i == n_warm:
                g0, h0 = g.cache_info(), h.cache_info()
            if i < n_warm:
                timed_turn(m, q, last)
                continue
            first = rng.random() < 0.5
            if first:
                c = cold_turn(m, q, last, cap)
            t = timed_turn(m, q, last)
            if not first:
                c = cold_turn(m, q, last, cap)
            lat["turn"].append(t[0])
            lat["ret"].append(t[1])
            lat["cold"].append(c[0][0])
            lat["cold_ret"].append(c[0][1])
            for w, info in (("g", c[1]), ("h", c[2])):
                cold[w][0] += info.hits
                cold[w][1] += info.hits + info.misses
    g1, h1 = g.cache_info(), h.cache_info()
    hm = {"g": (g1.hits - g0.hits, g1.misses - g0.misses), "h": (h1.hits - h0.hits, h1.misses - h0.misses)}
    return hm, lat, {w: cold[w][0] / max(cold[w][1], 1) for w in "gh"}


def _nothing(k):
    return None


def sim_cell(rs, order, n_warm, cap):
    """같은 `functools.lru_cache`에 정수 키를 흘린다 — (적중, 빗나감)을 잰 턴에서만 센다."""
    out = {}
    for w in "gh":
        f = functools.lru_cache(maxsize=cap)(_nothing)
        i0 = None
        for i, r in enumerate(order):
            if i == n_warm:
                i0 = f.cache_info()
            collections.deque(map(f, rs.seq(w, r)), maxlen=0)
        i1 = f.cache_info()
        out[w] = (i1.hits - i0.hits, i1.misses - i0.misses)
    return out


def rate(hm):
    return hm[0] / max(hm[0] + hm[1], 1)


def cliff_word(h):
    return "절벽" if h <= CLIFF_HIT else "—"


def cliff_gain_word(h, d):
    """새 규칙(사후 정정) — 이득 g = h − d. d가 없으면 판정하지 않는다."""
    if d is None:
        return "판정 불가"
    return "절벽" if h - d <= CLIFF_GAIN else "—"


def first_cliffs(h, d, rgrid=R_SIM):
    """(옛 첫 절벽 R · 새 첫 절벽 R) — 옛 = 첫 h ≤ CLIFF_HIT · 새 = 첫 g = h − d ≤ CLIFF_GAIN. 없으면 None."""
    return (next((r for r in rgrid if cliff_word(h[r]) == "절벽"), None),
            next((r for r in rgrid if cliff_gain_word(h[r], d) == "절벽"), None))


def cold_sim(rs, w, cap):
    """짝 콜드 턴의 sim — 같은 상한의 **빈** LRU에 방 하나(방 0)의 키를 한 번 흘린 적중률(방 안 중복 · 상한 안에서만 맞는다)."""
    f = functools.lru_cache(maxsize=cap)(_nothing)
    collections.deque(map(f, rs.seq(w, 0)), maxlen=0)
    i = f.cache_info()
    return rate((i.hits, i.misses))


# ══════════════════════════════════════════════════════════════════════
# 틀 · 방 적재
# ══════════════════════════════════════════════════════════════════════
def load_regime(d):
    base = ROOT / "eval3" / "regimes" / d
    with open(base / "corpus" / "corpus.jsonl", encoding="utf-8") as f:
        corpus = [json.loads(line) for line in f]
    with open(base / "fact-ledger.yaml", encoding="utf-8") as f:
        ledger = yaml.safe_load(f)
    with open(ROOT / "eval3" / "questions.yaml", encoding="utf-8") as f:
        asks = [q["ask"] for q in yaml.safe_load(f)["qa_questions"]]
    return corpus, ledger, asks


def templates(tmp):
    out = {}
    for rg, d in REGIMES:
        corpus, ledger, asks = load_regime(d)
        sub = os.path.join(tmp, "tpl_" + rg)
        os.makedirs(sub)
        out[rg] = dict(tpl=RS.template_rows(sub, corpus, ledger), asks=asks, last=corpus[-1]["seq"])
    return out


def check_rooms(rs, rooms, asks, last, all_asks=False):
    """방마다 실제 코드가 흘리는 키 순서 = 구성(`RoomSet.strings`)인가 — 어긋난 (방, 메모) 목록."""
    bad = []
    for k, m in rooms.items():
        for q in (asks if all_asks and k == 0 else asks[:1]):
            g, h = record(m, q, last)
            if g != rs.strings("g", k):
                bad.append((k, "검색", q[:12]))
            if h != rs.strings("h", k):
                bad.append((k, "어휘", q[:12]))
    return bad


def rooms_table(sets):
    print(f"\n  {'레짐':<10}{'N':>6}{'s':>6} │{'검색 호출':>9}{'D_τ':>7}{'공유':>6}{'d':>7} │{'어휘 호출':>9}{'D':>7}{'공유':>6}{'d':>7}"
          f" │ 예측 경계 R(순환 · C={CAP}): 검색 C/D_τ · 어휘 C/D")
    for (rg, n, s), rs in sets.items():
        ng, dg, sg, fg = rs.stats("g")
        nh, dh, sh, fh = rs.stats("h")
        print(f"  eval3·{rg:<4}{n:>6}{s:>6.2f} │{ng:>9}{dg:>7}{sg:>6}{fg:>7.3f} │{nh:>9}{dh:>7}{sh:>6}{fh:>7.3f}"
              f" │ {CAP / dg:>6.2f} · {CAP / dh:>6.2f}" + ("" if s == 0 else "  (s > 0 — q_s로 본다)"))


# ══════════════════════════════════════════════════════════════════════
# 1부 — 실측 칸
# ══════════════════════════════════════════════════════════════════════
def part_real(quick):
    cells = QUICK_CELLS if quick else REAL_CELLS
    tmp = tempfile.mkdtemp(prefix="w11a_memo_")
    all_rooms = []
    fail = []
    try:
        tpls = templates(tmp)
        need = {}
        for rg, n, _, s, _, rgrid in cells:
            need[(rg, n, s)] = max(need.get((rg, n, s), 0), max(rgrid))
        sets, rooms = {}, {}
        bad_tag = []
        for (rg, n, s), rmax in sorted(need.items()):
            rs = sets[(rg, n, s)] = RoomSet(tpls[rg]["tpl"], n, s)
            bad_tag += tag_invariant(sorted(set(rs.base["h"])))
            rooms[(rg, n, s)] = {k: build_room(os.path.join(tmp, f"{rg}_{n}_{s}_{k}.db"), rs, k) for k in range(rmax)}
            all_rooms += rooms[(rg, n, s)].values()
        print("\n" + "=" * W)
        print("1. 방 — 틀 · 꼬리표 · 접근 순서 재구성")
        print("=" * W)
        rooms_table(sets)
        print(f"\n  꼬리표 불변(조각 · 앞 2글자가 틀과 같다 · 방 번호 0·7·42·999): 어긋난 요약 {len(bad_tag)}"
              f"{' 🔴' if bad_tag else ''}")
        if bad_tag:
            fail.append(f"꼬리표 불변 {len(bad_tag)}")
        nbad = 0
        for key, rs in sets.items():
            asks, last = tpls[key[0]]["asks"], tpls[key[0]]["last"]
            b = check_rooms(rs, rooms[key], asks, last, all_asks=(key[1] == 3000 and key[2] == 0 and not quick))
            nbad += len(b)
            if b:
                print(f"  🔴 {key}: 키 순서 어긋남 {b[:4]}")
        scope = "" if quick else f" · N=3,000 · s=0 방 0은 질의 {len(tpls[RG[0]]['asks'])}개 전부"
        print(f"  접근 순서 재구성(방마다 실제 코드가 흘린 키 = 구성 · 질의 1개{scope}): 어긋남 {nbad}{' 🔴' if nbad else ''}")
        if nbad:
            fail.append(f"키 순서 {nbad}")

        print("\n" + "=" * W)
        print(f"2. 실측 칸 — 턴 = 어휘 조립 + 검색 · n={N_MEAS}/칸(워밍업 2R+5 제외) · 짝 콜드 · ms · 이 실행 안에서만")
        print("=" * W)
        print(f"  기계: {platform.platform()} · 논리 CPU {os.cpu_count()} · Python {platform.python_version()} · "
              f"{time.strftime('%Y-%m-%d %H:%M:%S')} · 모드 {M.RETRIEVAL_MODE}")
        jobs = [(c, r) for c in cells for r in c[5]]
        random.Random(SEED).shuffle(jobs)                     # 칸 순서를 섞는다 — 부하 흐름이 R과 겹치지 않게
        res = {}
        t_start = time.perf_counter()
        for (rg, n, o, s, cap, _), r in jobs:
            key = f"{rg}|{n}|{o}|{s}|{cap}|{r}"
            order = room_order(o, r, warmup(r) + N_MEAS, key)
            rs = sets[(rg, n, s)]
            hm, lat, hc = real_cell(rooms[(rg, n, s)], order, warmup(r), cap, tpls[rg]["asks"], tpls[rg]["last"],
                                    random.Random(key))
            sm = sim_cell(rs, order, warmup(r), cap)
            rs.forget()
            res[(rg, n, o, s, cap, r)] = (hm, lat, hc, sm)
        el = time.perf_counter() - t_start
        pct = RS.pct
        print(f"  {'레짐':<9}{'N':>5} {'순서':<7}{'s':>5}{'C':>6}{'R':>4}{'R·N':>8} │{'q검색':>6}{'h':>6}{'d':>6}   │"
              f"{'q어휘':>6}{'h':>6}{'d':>6}   │{'턴 p50':>7}{'p95':>7} │{'콜드 p50':>8}{'p95':>7} │{'r95':>6}{'r50':>6}{'q₀':>6}"
              f" │ sim")
        s_bad = []
        c_bad = []                                            # 🔄 (w13cliff) 짝 콜드 d = sim 콜드 d — 새 규칙의 sim 판정이 기대는 곳
        marks = {"옛": [0, 0], "새": [0, 0]}
        rows_out = []
        for c in cells:
            for r in c[5]:
                rg, n, o, s, cap, _ = c
                hm, lat, hc, sm = res[(rg, n, o, s, cap, r)]
                rs = sets[(rg, n, s)]
                ok = sm == hm
                if not ok:
                    s_bad.append((rg, n, o, s, cap, r, hm, sm))
                hg, hh = rate(hm["g"]), rate(hm["h"])
                qg, qh = rs.q("g", r, cap), rs.q("h", r, cap)
                p50, p95 = pct(lat["turn"], 50), pct(lat["turn"], 95)
                c50, c95 = pct(lat["cold"], 50), pct(lat["cold"], 95)
                ev, od = lat["cold"][0::2], lat["cold"][1::2]
                q0 = pct(ev, 95) / pct(od, 95)
                rows_out.append(dict(rg=rg, n=n, o=o, s=s, cap=cap, r=r, qg=qg, qh=qh, hg=hg, hh=hh,
                                     r95=p95 / c95, q0=q0))
                for w in "gh":
                    if cold_sim(rs, w, cap) != hc[w]:
                        c_bad.append((rg, n, o, s, cap, r, w, hc[w]))
                    hw = rate(hm[w])
                    marks["옛"][0] += cliff_word(hw) == "절벽"
                    marks["새"][0] += cliff_gain_word(hw, hc[w]) == "절벽"
                    marks["옛"][1] += 1
                    marks["새"][1] += 1
                gain = lambda h, d: "◆" if cliff_gain_word(h, d) == "절벽" else " "
                print(f"  eval3·{rg:<3}{n:>5} {o:<7}{s:>5.2f}{cap:>6}{r:>4}{r * n:>8,} │{qg:>6.2f}{hg:>6.3f}{hc['g']:>6.3f}"
                      f"{'▼' if hg <= CLIFF_HIT else ' ':>2}{gain(hg, hc['g'])}│{qh:>6.2f}{hh:>6.3f}{hc['h']:>6.3f}"
                      f"{'▼' if hh <= CLIFF_HIT else ' ':>2}{gain(hh, hc['h'])}│"
                      f"{p50:>7.2f}{p95:>7.2f} │{c50:>8.2f}{c95:>7.2f} │{p95 / c95:>6.2f}{p50 / c50:>6.2f}{q0:>6.2f}"
                      f"{' ⚠' if abs(q0 - 1) >= BAND else '  '}│ {'=' if ok else '🔴≠'}")
        print(f"  ▼ = h ≤ {CLIFF_HIT:.2f}(절벽) · d = 짝 콜드 턴의 적중(방 안 중복) · r95 = p95(턴)/p95(짝 콜드) · "
              f"q₀ = 짝 콜드 짝/홀 턴 p95 비(⚠ = ±10 % 밖) · 칸 순서는 섞었다 · 잰 시간 {el:.0f} s")
        print(f"  ◆ = 🔄 새 규칙 g = h − d ≤ {CLIFF_GAIN:.2f}(사후 정정 · 값을 본 뒤 — 근거: ▼는 수준만 본다) · 칸×메모 "
              f"옛 ▼ {marks['옛'][0]}/{marks['옛'][1]} · 새 ◆ {marks['새'][0]}/{marks['새'][1]}")
        print(f"  S sim = 실측: {'참' if not s_bad else '거짓'} — 다른 칸 {len(s_bad)}/{len(rows_out)}"
              f"{' 🔴 ' + str(s_bad[:2]) if s_bad else ''}")
        if s_bad:
            fail.append(f"sim ≠ 실측 {len(s_bad)}")
        print(f"  🔄 짝 콜드 d = sim 콜드 d(새 규칙의 sim 판정이 기대는 곳 · 칸×메모): {'같다' if not c_bad else '🔴 다르다'} — "
              f"다른 칸 {len(c_bad)}/{2 * len(rows_out)}{' ' + str(c_bad[:2]) if c_bad else ''}")
        if c_bad:
            fail.append(f"콜드 sim ≠ 짝 콜드 {len(c_bad)}")
        if not quick:
            verdict_p4(rows_out)
            verdict_p1_rows(rows_out, sets, "실측")
            entry_bytes(rooms[("s0", 3000, 0.0)][0], tpls["s0"])
    finally:
        for m in all_rooms:
            m.db.close()
        shutil.rmtree(tmp, ignore_errors=True)
    return fail


def verdict_p4(rows):
    bad, noisy, mixed, n = [], [], [], 0
    for x in rows:
        if x["o"] != "순환" or x["r"] < 2:
            continue
        cell = (x["rg"], x["n"], x["s"], x["cap"], x["r"], round(x["qg"], 2), round(x["qh"], 2), round(x["r95"], 2))
        if abs(x["q0"] - 1) >= BAND:
            noisy.append(cell[:5])
        if (x["qg"] <= 1) != (x["qh"] <= 1):                 # 한 몫만 넘었다 — 기대 없음, 값만
            mixed.append(cell)
            continue
        n += 1
        ok = (x["r95"] <= 1 - BAND) if x["qg"] <= 1 else (x["r95"] > 1 - BAND)
        if not ok:
            bad.append(cell)
    print(f"  → P4 지연(순환 · R ≥ 2 · 기대가 있는 {n}칸 — 두 몫 다 ≤ 1 → r95 ≤ {1 - BAND:.2f} · 두 몫 다 > 1 → r95 > "
          f"{1 - BAND:.2f}): {'참' if not bad else '거짓'} — 어긋난 칸 {len(bad)} {bad or ''}")
    print(f"     한 몫만 넘은 칸(값만 · (레짐, N, s, C, R, q검색, q어휘, r95)) {len(mixed)} {mixed or ''}")
    print(f"     C0 잡음 칸(|q₀−1| ≥ 0.10) {len(noisy)} {noisy or ''}")


def verdict_p1_rows(rows, sets, label):
    bad, n = [], 0
    for x in rows:
        if x["o"] != "순환" or x["s"] != 0:
            continue
        rs = sets[(x["rg"], x["n"], x["s"])]
        for w in "gh":
            n += 1
            q, h, d = x["q" + w], x["h" + w], rs.stats(w)[3]
            ok = h >= FULL_HIT if q <= 1 else h <= d + FLOOR_EPS
            if not ok:
                bad.append((x["rg"], x["n"], x["cap"], x["r"], "검색" if w == "g" else "어휘", round(q, 2), round(h, 3)))
    print(f"  → P1({label} · 순환 · s = 0 · {n}칸×메모): {'참' if not bad else '거짓'} — 어긋남 {len(bad)} {bad or ''}")


def entry_bytes(room, t):
    g, h = memo_pair(CAP)
    tracemalloc.start()
    with Swap(g, h):
        timed_turn(room, t["asks"][0], t["last"])
    cur, _ = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    k = g.cache_info().currsize + h.cache_info().currsize
    print(f"  메모 크기(eval3·s0 N=3,000 방 하나 한 턴): 두 메모 {k}항목 · tracemalloc 현재 {cur / 1024:.0f} KiB = 항목당 "
          f"{cur / max(k, 1):.0f} B → 상한 C 둘이 다 차면 ≈ {cur / max(k, 1) * CAP * 2 / 2 ** 20:.0f} MiB(C={CAP})")


# ══════════════════════════════════════════════════════════════════════
# 2부 — sim 조밀 격자 (적중률만)
# ══════════════════════════════════════════════════════════════════════
SHOW_R = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 16, 18, 20, 24, 28, 32, 36, 40, 48)


def part_sim():
    tmp = tempfile.mkdtemp(prefix="w11a_sim_")
    fail = []
    try:
        tpls = templates(tmp)
        sets = {}
        for rg, n, _, s, _ in SIM_ROWS:
            if (rg, n, s) not in sets:
                sets[(rg, n, s)] = RoomSet(tpls[rg]["tpl"], n, s)
        print("\n" + "=" * W)
        print("1. 방 — 틀 · 접근 순서 재구성(방 0 · 방 1 DB에서 실제 코드가 흘린 키 = 구성)")
        print("=" * W)
        rooms_table(sets)
        nbad = 0
        for (rg, n, s), rs in sets.items():
            rooms = {k: build_room(os.path.join(tmp, f"{rg}_{n}_{s}_{k}.db"), rs, k) for k in (0, 1)}
            try:
                nbad += len(check_rooms(rs, rooms, tpls[rg]["asks"], tpls[rg]["last"]))
            finally:
                for m in rooms.values():
                    m.db.close()
        print(f"  접근 순서 재구성: 어긋남 {nbad}{' 🔴' if nbad else ''}")
        if nbad:
            fail.append(f"키 순서 {nbad}")
        print("\n" + "=" * W)
        print(f"2. sim — R = 1…48 · 칸마다 잰 턴 {N_MEAS}(워밍업 2R+5 제외) · 적중률만 (지연은 1부 실측에서만)")
        print("=" * W)
        t0 = time.perf_counter()
        out = {}
        for row in SIM_ROWS:
            rg, n, o, s, cap = row
            rs = sets[(rg, n, s)]
            for r in R_SIM:
                order = room_order(o, r, warmup(r) + N_MEAS, f"{rg}|{n}|{o}|{s}|{cap}|{r}")
                sm = sim_cell(rs, order, warmup(r), cap)
                out[row + (r,)] = (rate(sm["g"]), rate(sm["h"]))
            rs.forget()
        print(f"  (sim {len(SIM_ROWS)}줄 × {len(R_SIM)} R · {time.perf_counter() - t0:.0f} s)")
        show_sim(out, sets)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return fail


def first(rgrid, pred):
    return next((r for r in rgrid if pred(r)), None)


def show_sim(out, sets):
    print(f"\n  줄마다: 메모 · D(방당 서로 다른 키) · d · 첫 h < {FULL_HIT:.2f}의 R(그 R의 R·N · 몫 q) · 첫 h ≤ {CLIFF_HIT:.2f}의 R "
          f"(R·N · q) · 격자 최저 h")
    p1_bad = {}
    p1_side = []
    p6_bad = []
    starts = {}
    for row in SIM_ROWS:
        rg, n, o, s, cap = row
        rs = sets[(rg, n, s)]
        print(f"\n  ── eval3·{rg} · N={n} · {o} · s={s:.2f} · C={cap}")
        for i, w in enumerate("gh"):
            _, dd, _, d = rs.stats(w)
            h = {r: out[row + (r,)][i] for r in R_SIM}
            r0 = first(R_SIM, lambda r: h[r] < FULL_HIT)
            r1 = first(R_SIM, lambda r: h[r] <= CLIFF_HIT)
            dc = cold_sim(rs, w, cap)                         # 🔄 (w13cliff) 새 규칙의 d — 같은 상한의 빈 LRU
            r1g = first_cliffs(h, dc)[1]
            starts[(rg, n, o, s, cap, w)] = (r0, r1, min(h.values()), r1g, min(h[r] - dc for r in R_SIM))
            fmt = lambda r: "없음" if r is None else f"R={r} (R·N {r * n:,} · q {rs.q(w, r, cap):.2f})"
            print(f"    {'검색' if w == 'g' else '어휘'}  D {dd:>5} · d {d:.3f} · 첫 h<{FULL_HIT:.2f} {fmt(r0):<30} · "
                  f"첫 절벽 {fmt(r1):<30} · 최저 h {min(h.values()):.3f}")
            print(f"          🔄 새(g = h − d ≤ {CLIFF_GAIN:.2f} · 사후 · 콜드 d {dc:.3f}): 첫 절벽 {fmt(r1g):<30} · "
                  f"최저 g {starts[(rg, n, o, s, cap, w)][4]:.3f}")
            print("          h: " + " ".join(f"{r}:{h[r]:.2f}" for r in SHOW_R))
            if o == "순환":
                r_over = first(R_SIM, lambda r: rs.q(w, r, cap) > 1)
                for r in R_SIM:
                    q = rs.q(w, r, cap)
                    if s == 0:
                        ok = h[r] >= FULL_HIT if q <= 1 else h[r] <= d + FLOOR_EPS
                        if not ok:
                            p1_bad.setdefault(cap, []).append((rg, n, w, r, round(q, 3), round(h[r], 3)))
                            p1_side.append((q <= 1, r == r_over, h[r] - d))
                    else:
                        ok = h[r] >= FULL_HIT if q <= 1 else h[r] < FULL_HIT
                        if not ok:
                            p6_bad.append((rg, s, w, r, round(q, 3), round(h[r], 3)))
    print("\n" + "=" * W)
    print("3. 사전 등록 조건")
    print("=" * W)
    caps = sorted({row[4] for row in SIM_ROWS if row[2] == "순환" and row[3] == 0})
    for cap in caps:
        b = p1_bad.get(cap, [])
        print(f"  P1(순환 · s = 0 · C={cap}): {'참' if not b else '거짓'} — 어긋남 {len(b)} {b[:6] or ''}")
    over = [x for x in p1_side if not x[0]]
    if p1_side:
        spread = f" · h − d {min(x[2] for x in over):.3f}~{max(x[2] for x in over):.3f}" if over else ""
        print(f"    └ 사후(값을 본 뒤 더함 · 판정 아님): P1 어긋남 {len(p1_side)}칸 — q ≤ 1 쪽 {len(p1_side) - len(over)} · "
              f"q > 1 쪽 {len(over)}(그중 몫이 1을 처음 넘는 R {sum(x[1] for x in over)}){spread}")
    print(f"  P5(상한 비례 — 위 {len(caps)}개 상한에서 P1 전부 참): {'참' if not any(p1_bad.values()) else '거짓'}"
          " (실측 C=4096 줄은 1부)")
    print(f"  P6(공유 — q_s ≤ 1 ⇔ h ≥ 0.90): {'참' if not p6_bad else '거짓'} — 어긋남 {len(p6_bad)} {p6_bad[:6] or ''}")
    print(f"  P2(절벽이 온다 · C={CAP} · s = 0):")
    for rg in RG:
        for n in (500, 1000, 2000, 3000):
            for o in ORDERS:
                for w in "gh":
                    k = (rg, n, o, 0.0, CAP, w)
                    if k not in starts:
                        continue
                    r0, r1, lo, r1g, log = starts[k]
                    rs = sets[(rg, n, 0.0)]
                    txt = (f"참 — R={r1} · R·N {r1 * n:,} · q {rs.q(w, r1, CAP):.2f}" if r1
                           else f"거짓 — 격자 최저 h {lo:.3f}")
                    new = (f"참 — R={r1g} · R·N {r1g * n:,} · q {rs.q(w, r1g, CAP):.2f}" if r1g
                           else f"거짓 — 격자 최저 g {log:.3f}")
                    print(f"    eval3·{rg} N={n:<5} {o:<7} {'검색' if w == 'g' else '어휘'}: {txt:<34} │ 🔄 새(g · 사후): {new}")
    print("  P3(순서 · C={} · s = 0):".format(CAP))
    for rg in RG:
        for n in (1000, 3000):
            for w in "gh":
                if any((rg, n, o, 0.0, CAP, w) not in starts for o in ORDERS):
                    continue
                rr = starts[(rg, n, "순환", 0.0, CAP, w)]
                un = starts[(rg, n, "균등 무작위", 0.0, CAP, w)]
                hot = starts[(rg, n, "한 방 몰림", 0.0, CAP, w)]
                print(f"    eval3·{rg} N={n:<5} {'검색' if w == 'g' else '어휘'}: 첫 h<0.90 순환 R={rr[0]} · 무작위 R={un[0]} → "
                      f"«같은 R» {'참' if rr[0] == un[0] else '거짓'} · 몰림 최저 h {hot[2]:.3f} → «몰림엔 절벽 없음» "
                      f"{'참' if hot[2] > CLIFF_HIT else '거짓'} │ 🔄 새(g · 사후): 몰림 최저 g {hot[4]:.3f} → "
                      f"{'참' if hot[3] is None else '거짓'}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=("real", "sim", "both"), default="both")
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args(argv)
    print("=" * W)
    print("memo_multiroom — 검색 메모의 절벽 · 방 여럿 × 한 프로세스 (LLM 0회 · 임시 DB · 같은 실행 안)")
    print("=" * W)
    preregistration()
    before, during, fresh, restored = cap_is_fixed()
    fixed_ok = before == CAP and during == (CAP, CAP) and fresh == 7 and restored
    print(f"\n  상한 고정 확인: 끝 절 메모 상한 {before} → `MEMO_ROWS`를 7로 다시 묶은 동안 {during} → 새로 감싼 메모 {fresh}"
          f" · 복원 {restored} ⇒ {'다시 묶기로는 안 바뀐다 — 칸마다 새 메모를 이름에 꽂는다' if fixed_ok else '🔴 예상과 다름'}")
    fail = [] if fixed_ok else ["상한 고정 확인"]
    t0 = time.perf_counter()
    try:
        if a.part in ("real", "both"):
            fail += part_real(a.quick)
        if a.part in ("sim", "both"):
            fail += part_sim()
    except RestoreError as e:
        fail.append(str(e))
    if (M._doc_grams, M._doc_heads) != ORIGINAL or M.MEMO_ROWS != CAP:
        fail.append("끝 절 메모가 원래 객체가 아니다")
    print(f"\n  (소요 {time.perf_counter() - t0:.0f} s) · 자기 검사: {'통과' if not fail else '🔴 ' + ' · '.join(fail)}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
