# -*- coding: utf-8 -*-
"""
gate_saturation.py — 게이트가 자기 자신을 무력화하는가. (API 키 불필요 · ollama 불필요)

## 묻는 것

[ADR-006](../docs/adr/ADR-006-retrieval-gating-selection.md)의 게이트는 신호를
*"질문의 형태"*가 아니라 **"저장소와의 접점"**에서 찾는다 —
`prototype/memory.py`의 `Memory.gate`가 `_recall_vocab`(저장된 사건 요약의 앞
2글자 집합)과 겹치는 내용어가 있으면 검색을 연다.

그 설계에는 **자기 무력화의 씨앗**이 있다. 어휘는 **쓸수록 자란다.** 어휘가
코퍼스를 덮으면 «접점 없음»인 발화가 사라지고 게이트는 **길이 필터로 퇴화한다.**
같은 ADR이 *"검색 필요 턴 비율이 60%를 넘으면 게이팅의 이득이 작다"*를
**재검토 트리거로 이미 적어 뒀다** — 이 실험은 그 트리거가 **언제 열리는지**를
관측 가능한 양(`|_recall_vocab|`)으로 유도한다.

## 두 곡선, 그리고 🔴 **둘의 차이가 이 실험의 전부다**

  ① **순차 곡선** — 코퍼스를 순서대로 흘리며 그 시점의 어휘로 그 턴을 판정한다.
     **평평해진다.**
  ② **포화 극한** — «저장될 수 있는 접두 전체»에서 크기 k로 뽑아 436턴 전량을
     판정한다. **k와 함께 계속 오른다.**

①이 평평한 것이 **휴리스틱의 성질**이면 어휘가 자라도 발화율이 안 오른다는
뜻이고, **코퍼스/추출기의 성질**이면 «어휘가 안 자랐을 뿐»이다. 가르는 관측은
**어휘가 자라는 속도**다 — 새 접두가 코퍼스에서 얼마나 자주 오는가. 그것이
*"대화 종류가 다양해지면"*의 이 저장소 안 대리 지표다.

## 🔴 재는 것은 한쪽뿐이다

발화율은 **비용도 이득도 아니다.** 게이트가 열리면 회상이 오를 수 있고(이득)
검색 지연과 오주입도 오른다(비용). 이 실험은 **문이 얼마나 열리는가**만 재고
그 문 뒤의 교환비는 `prototype/gate_sweep.py`(실험 12)와
[실험 21](../docs/11-experiment-results.md)의 것이다. §H에 그렇게 적었다.

재현: `PYTHONIOENCODING=utf-8 python -B experiments/gate_saturation.py`
시험:  `PYTHONIOENCODING=utf-8 python -B -m unittest discover -s experiments/tests -p "test_gate_saturation.py" -v`
"""

import json
import os
import random
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "prototype"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import yaml                                            # noqa: E402
from memory import Memory                              # noqa: E402
import soak as S                                       # noqa: E402

W = 78

# ── 사전 등록 상수 ──────────────────────────────────────────────────────
#
# 🔴 **M은 이 실험이 고른 수가 아니다.** `ADR-006`의 재검토 트리거가
#    *"검색 필요 턴 비율이 60%를 넘으면 → 게이팅의 이득이 작다"*라고 이미 적어
#    뒀고, 이 실험은 그 문장의 **60**을 그대로 가져온다. 여기서 새 눈금을
#    발명하면 «결과를 보고 고른 임계»가 되고, 그것이 실험 21 §B가 사전등록으로
#    막은 것과 같은 실패다.
M_TRIGGER_PCT = 60.0

# 포화 극한의 표본 수. **중첩 표본**이라 seed마다 곡선이 단조 비감소다(A2).
N_SEEDS = 24
# N 유도용 미세 스윕 (k를 1칸씩 훑는다).
# 🔴 **여기가 24로는 모자랐다.** 평균이 M을 가로지르는 자리에서 이웃 k의 차이가
#    0.1%p 미만이라, 표본이 적으면 N이 seed 집합에 따라 흔들린다. 그래서 표본을
#    늘리고 **N 하나만 적지 않는다** — 아래 `derive_threshold`가 «평균이 넘는 곳」
#    「표본 전부가 넘는 곳」「표본 하나라도 넘는 곳」 셋을 함께 낸다.
N_SEEDS_FINE = 48
# 🔴 상한 130의 근거: `N_all`(표본 **전부**가 M을 넘는 곳)이 §D의 눈금에서
#    k=100(최소 57.1%)과 k=120(최소 67.4%) 사이에 있다. 110에서 끊었더니
#    `N_all`이 `None`으로 나왔고 **A5가 그것을 실제로 잡았다** — 훑은 구간이
#    답을 담지 못하면 «못 찾았다»를 조용히 «없다»로 적지 않는다.
FINE_LO, FINE_HI = 55, 130

# 표에 찍는 k 눈금. `TODAY` 자리는 실행 시점의 `|_recall_vocab|`로 채운다.
K_TABLE = [0, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 120, 140]

# 게이트가 내는 사유 문자열 — `Memory.gate`의 반환값 그대로다.
# 🔴 **여기 옮겨 적은 것이 아니라 §A의 앵커 대조가 실행 중에 확인한다.**
R_PAST = "과거 참조 표현"
R_CONTACT = "저장된 내용어와 접점"
R_SHORT = "너무 짧음 — 신호 없음"
R_RITUAL = "의례적 발화"
R_NONE = "과거 참조 신호도 내용어 접점도 없음"
FIRING = (R_PAST, R_CONTACT)


def prefixes(text):
    """
    `Memory.gate`·`_recall_vocab`이 쓰는 것과 **같은 규칙**의 앞 2글자 집합.

    🔴 정규식을 여기 한 번 더 적는 것이 F12(사본이 갈라진다)의 형태다. 그래서
       **§A가 이 함수를 쓰지 않는다** — 앵커는 실제 `Memory`의 `_recall_vocab`
       프로퍼티가 낸 집합과 대조하고, 다르면 종료 1이다.
    """
    return {w[:2] for w in re.findall(r"[가-힣]{2,}", text)}


class VocabProbe:
    """
    어휘 하나를 꽂고 **프로덕션 게이트 함수 그 자체**를 돌린다.

    🔴 `gate = Memory.gate`는 **사본이 아니라 같은 함수 객체**다. 게이트 논리를
       이 파일에 다시 적으면 `prototype/`을 고치는 날 두 벌이 갈라지고, 그것이
       이 저장소가 F12로 부르는 형태다. 바꿔 끼우는 것은 `_recall_vocab`
       **하나뿐**이고, 그것이 이 실험의 독립변수다.
    """
    gate = Memory.gate

    def __init__(self, vocab):
        self._recall_vocab = set(vocab)


def load_corpus():
    with open(ROOT / "eval/corpus/corpus.jsonl", encoding="utf-8") as f:
        corpus = [json.loads(l) for l in f]
    with open(ROOT / "eval/fact-ledger.yaml", encoding="utf-8") as f:
        ledger = yaml.safe_load(f)
    return corpus, ledger


def production_vocab(corpus, ledger):
    """
    **오늘 실제로 저장되는 어휘.** 임시 DB에 소크와 같은 경로로 ingest한 뒤
    `Memory._recall_vocab`을 그대로 읽는다 — 계산하지 않고 **묻는다.**

    DB는 `%TEMP%`에 만든다 (가드레일).
    """
    dbf = Path(tempfile.gettempdir()) / "gate_saturation.db"
    if dbf.exists():
        dbf.unlink()
    m = Memory(str(dbf))
    S.seed(m)
    S.ingest(m, corpus, ledger, timed=False)
    rows = m.db.execute(
        "SELECT COUNT(*) t, SUM(user_deleted=0) a FROM event WHERE chat_id=?",
        (S.CHAT,)).fetchone()
    sig = (rows["t"], rows["a"] or 0)
    vocab = set(m._recall_vocab)
    # 앵커 대조용으로 실제 인스턴스를 함께 돌려준다.
    return m, vocab, sig, dbf


def gate_counts(vocab, utterances):
    """사유별 계수. **분모는 언제나 `len(utterances)`다.**"""
    p = VocabProbe(vocab)
    return Counter(p.gate(u)[1] for u in utterances)


def fired(counts):
    return sum(counts[r] for r in FIRING)


# ── ① 순차 곡선 ────────────────────────────────────────────────────────
def sequential_curves(corpus, ledger):
    """
    두 팔을 **같은 코퍼스 순서**로 흘린다.

      A. 대장 추출 (오늘) — `eval/fact-ledger.yaml`의 22항목이 각자의 앵커
         턴(`at.session/turn`)을 지날 때 저장된다. `soak.ingest`가 event 색인에
         넣는 것과 **같은 22개**다.
      B. 이상 추출 (상한) — **모든 턴이 저장된다.** 추출기가 놓치는 것이 없다는
         가정이고, 그래서 어휘가 코퍼스를 따라 자란다.

    🔴 **두 팔의 차이는 게이트가 아니라 «무엇이 저장되는가»다.** 게이트 함수는
       한 글자도 다르지 않다.
    """
    seq_of = {(r["session"], r["turn"]): r["seq"] for r in corpus}
    arrivals = {}
    for item in list(ledger.get("events", [])) + list(ledger.get("facts", [])):
        at = item.get("at", {})
        s = seq_of.get((at.get("session"), at.get("turn")), 0)
        arrivals.setdefault(s, set()).update(prefixes(item["text"]))

    def walk(use_ledger, grow):
        """
        `grow(row) -> 이 행을 본 뒤 어휘에 더할 접두`.

        🔴 **팔 B는 `arrivals`를 쓰지 않는다.** 두 팔에 같은 대장 도착을 함께
           얹으면 팔 B가 «모든 턴 + 대장»이 되어 두 팔의 차이가 «저장 정책»
           하나가 아니게 된다. 팔을 가르는 변수는 **하나여야** 한다.

        반환의 마지막 원소 `last_growth`는 **어휘가 마지막으로 자란 자리**다 —
        «어디서 평평해지는가»가 그 값이다.
        """
        V = set(arrivals.get(0, set())) if use_ledger else set()
        n, f, trace, last_growth = 0, 0, [], (0, 0, len(V))
        for row in corpus:
            before = len(V)
            if use_ledger and row["seq"] in arrivals and row["seq"] != 0:
                V |= arrivals[row["seq"]]
            if row["role"] == "user":
                n += 1
                ok, _ = VocabProbe(V).gate(row["text"])
                f += bool(ok)
                trace.append((n, row["seq"], len(V), f))
            if grow is not None:
                V |= grow(row)
            if len(V) > before:
                last_growth = (n, row["seq"], len(V))
        return trace, last_growth

    a = walk(True, None)                              # 대장 추출 — arrivals만
    b = walk(False, lambda row: prefixes(row["text"]))  # 이상 추출 — 모든 턴
    return a, b


def vocab_growth(corpus, block=100):
    """
    **어휘가 자라는 속도** — 새 접두가 코퍼스에서 얼마나 자주 오는가.

    이것이 *"대화 종류가 다양해지면"*의 대리 지표다. 구간마다 «처음 보는 접두»의
    수를 세고, **마지막 새 접두가 몇 번째 턴에 왔는가**를 함께 찍는다. 끝까지
    0이 아니면 이 코퍼스는 **어휘적으로 소진되지 않았다**는 뜻이고, 그러면
    순차 곡선의 평평함을 «코퍼스가 반복적이라서»로 설명할 수 없다.
    """
    V, per_block, last_new, total = set(), Counter(), 0, corpus[-1]["seq"]
    for row in corpus:
        new = prefixes(row["text"]) - V
        if new:
            last_new = row["seq"]
            per_block[(row["seq"] - 1) // block] += len(new)
        V |= new
    return per_block, last_new, total, len(V)


# ── ② 포화 극한 ────────────────────────────────────────────────────────
def saturation_curve(pool, utterances, ks, seeds):
    """
    «저장될 수 있는 접두 전체»(`pool`)에서 크기 k를 뽑아 **436턴 전량**을 판정한다.

    🔴 **중첩 표본이다.** seed마다 pool을 한 번 섞고 앞에서부터 k개를 자른다 —
       k가 커질 때 어휘가 **부분집합 관계**로 늘어나므로 같은 seed 안에서
       발화율은 **단조 비감소**여야 한다(A2가 그것을 검사한다). 독립 표본을
       쓰면 그 불변식이 사라지고, 검사할 것이 «평균이 대충 오른다»뿐이 된다.

    ⚠️ 무작위 추출은 *"화제가 고르게 다양해진다"*를 가정한다 — §H에 적었다.
    """
    pool = sorted(pool)
    out = {k: [] for k in ks}
    for s in range(seeds):
        order = list(pool)
        random.Random(20260910 + s).shuffle(order)
        for k in ks:
            out[k].append(fired(gate_counts(order[:k], utterances)) / len(utterances))
    return out


def derive_threshold(pool, utterances, m_pct, lo, hi, seeds):
    """
    **열리는 조건의 N을 유도한다** — 리터럴을 박지 않고 `lo..hi`를 1칸씩 훑는다.

    🔴 **N을 하나만 적지 않는다.** 평균이 M을 가로지르는 자리에서 이웃 k의 차이가
       0.1%p 미만이라, 「평균이 넘는 최소 k」 하나만 적으면 그 수는 표본 집합의
       함수가 되고 **재현되지 않는 숫자를 문서에 박는 것**(G11)이 된다. 그래서
       셋을 함께 낸다:

         N_any   표본 **하나라도** M을 넘는 최소 k — 낙관적 경계
         N_mean  표본 **평균**이 M을 넘는 최소 k
         N_all   표본 **전부**가 M을 넘는 최소 k — 보수적 경계

       세 수 사이가 «열리는 구간»이고, 그 폭이 곧 이 유도의 불확실성이다.
    """
    ks = list(range(lo, hi + 1))
    curve = saturation_curve(pool, utterances, ks, seeds)
    means = {k: sum(v) / len(v) * 100 for k, v in curve.items()}
    mins = {k: min(v) * 100 for k, v in curve.items()}
    maxs = {k: max(v) * 100 for k, v in curve.items()}
    pick = lambda d: next((k for k in ks if d[k] >= m_pct), None)  # noqa: E731
    return dict(N_any=pick(maxs), N_mean=pick(means), N_all=pick(mins),
                means=means, mins=mins, maxs=maxs, ks=ks)


# ── 검사 5종 — 심을 위반이 붙는 자리 ────────────────────────────────────
#
# 🔴 **검사는 «계산»이 아니라 «데이터»를 받는다.** 그래야 시험이 위반을 심을 수
#    있다 — 계산 안에 숨은 assert는 밖에서 흔들 수 없고, 흔들 수 없는 검사는
#    이 저장소가 «발화할 수 없는 검사»라 부르는 것이다.

def check_anchor(st):
    """A1 — shim의 게이트가 프로덕션 `Memory.gate`와 **판정도 사유도** 같은가."""
    d = st["anchor_disagreements"]
    return ("A1 앵커 (shim ≡ 프로덕션 게이트)", d == 0,
            f"불일치 {d}/{st['n_utt']}건")


def check_monotone(st):
    """A2 — 중첩 표본이므로 seed마다 k에 대해 발화율이 단조 비감소여야 한다."""
    bad = []
    for k_prev, k in zip(st["ks"], st["ks"][1:]):
        for i, (a, b) in enumerate(zip(st["curve"][k_prev], st["curve"][k])):
            if b < a - 1e-12:
                bad.append((i, k_prev, k, a, b))
    return ("A2 단조성 (중첩 표본)", not bad,
            "위반 0건" if not bad else
            f"위반 {len(bad)}건 — 예: seed{bad[0][0]} k{bad[0][1]}→{bad[0][2]} "
            f"{bad[0][3]*100:.1f}%→{bad[0][4]*100:.1f}%")


def check_floor_invariant(st):
    """
    A3 — **정규식 팔은 어휘와 무관하다.** `과거 참조 표현`으로 발화한 수가 어휘
    크기에 따라 움직이면 «바닥값»이라는 말 자체가 성립하지 않는다.
    """
    vals = sorted(set(st["past_by_k"].values()))
    return ("A3 정규식 바닥 불변", len(vals) == 1,
            f"바닥 {vals[0]}/{st['n_utt']}건 · k 전 구간 동일" if len(vals) == 1
            else f"어휘에 따라 움직인다: {vals}")


def check_denominator(st):
    """
    A4 — 모든 사유 계수의 합이 분모와 같은가. 게이트는 **전 판정 분할**이므로
    합이 분모와 다르면 어떤 턴이 두 번 세어졌거나 빠진 것이다 (G15).
    """
    bad = {k: t for k, t in st["totals_by_k"].items() if t != st["n_utt"]}
    return ("A4 분모 고정", not bad,
            f"모든 k에서 사유 합 = {st['n_utt']}" if not bad
            else f"분모가 어긋난 k: {bad}")


def check_real_point(st):
    """
    A6 — **오늘의 «실제» 어휘를 무작위 곡선과 같은 칸에 적지 않는다.**

    🔴 이 검사가 있는 이유가 이 라운드의 사고다. §D의 `k = 62` 행에 `← 오늘`을
       붙였는데 그 행의 값은 **크기만 62인 무작위 표본의 평균**이었다. 실제
       `_recall_vocab`은 같은 62개인데 **발화가 2.4배 적다** — 옳은 숫자에 틀린
       이름을 붙인 것이고, 이 저장소가 F21로 부르는 형태다.

    기계적으로 지킬 수 있는 불변식은 둘이다:
      ① 실제 어휘가 pool의 **부분집합**이다. 아니면 무작위 곡선은 실제가 사는
         공간을 표본하지 않는 것이고, 두 수를 나란히 놓는 것 자체가 무의미하다.
      ② 실제 점의 발화율이 `production_vocab`이 낸 어휘로 **따로 계산**됐다
         (곡선에서 읽어 오지 않았다) — 크기가 실제 어휘와 같은지로 확인한다.
    """
    V, pool = st["today_vocab"], st["pool"]
    outside = V - pool
    bad = []
    if outside:
        bad.append(f"실제 어휘 {len(outside)}개가 pool 밖에 있다: {sorted(outside)[:5]}")
    if st["today_counts_n"] != len(V):
        bad.append(f"실제 점이 |V|={len(V)}가 아닌 어휘로 계산됐다"
                   f"(={st['today_counts_n']})")
    band = st["curve"].get(len(V))
    where = ""
    if band:
        lo, hi = min(band) * 100, max(band) * 100
        r = st["today_rate"] * 100
        where = (f" · 같은 크기 무작위 표본 구간 {lo:.1f}–{hi:.1f}% "
                 f"{'밖' if not (lo <= r <= hi) else '안'}")
    return ("A6 실제 어휘 점 (무작위와 분리)", not bad,
            f"실제 {st['today_fired']}/{st['n_utt']} = {st['today_rate']*100:.1f}%"
            + where if not bad else " · ".join(bad))


def check_threshold(st):
    """
    A5 — N 셋이 **유도됐고** 경계와 순서가 맞는가.

      ① 셋 다 훑은 구간 안에서 찾혔다 (`None`이 없다)
      ② 각각 `rate(N) ≥ M > rate(N-1)`
      ③ `N_any ≤ N_mean ≤ N_all` — 정의상 강제되는 순서다. 깨지면 곡선이
        중첩 표본이 아니거나 min/mean/max가 뒤섞인 것이다.
    """
    d, m = st["thr"], st["M"]
    names = ("N_any", "N_mean", "N_all")
    keys = {"N_any": "maxs", "N_mean": "means", "N_all": "mins"}
    missing = [x for x in names if d[x] is None]
    if missing:
        return ("A5 열리는 조건 유도", False,
                f"{', '.join(missing)}이 훑은 구간 {d['ks'][0]}..{d['ks'][-1]}에서 "
                f"{m:.0f}%에 닿지 않는다")
    bad = []
    for x in names:
        s, n = d[keys[x]], d[x]
        if not (s[n] >= m and (n - 1 not in s or s[n - 1] < m)):
            bad.append(f"{x}={n} 경계 어긋남")
    trio = [d[x] for x in names]
    if trio != sorted(trio):
        bad.append(f"순서 어긋남 {trio}")
    return ("A5 열리는 조건 유도", not bad,
            f"N_any={d['N_any']} ≤ N_mean={d['N_mean']} ≤ N_all={d['N_all']} · "
            f"평균 {d['means'][d['N_mean']]:.2f}% ≥ {m:.0f}% > "
            f"{d['means'][d['N_mean'] - 1]:.2f}%"
            if not bad else " · ".join(bad))


CHECKS = [check_anchor, check_monotone, check_floor_invariant,
          check_denominator, check_real_point, check_threshold]


def run_checks(st):
    """(이름, 통과, 상세) 목록. **호출부가 종료 코드를 정한다.**"""
    return [c(st) for c in CHECKS]


# ── 본체 ────────────────────────────────────────────────────────────────
def measure():
    corpus, ledger = load_corpus()
    users = [r["text"] for r in corpus if r["role"] == "user"]
    m, today_vocab, sig, dbf = production_vocab(corpus, ledger)

    # §A 앵커 — 실제 인스턴스 vs shim. **판정과 사유를 둘 다** 본다.
    dis = sum(1 for u in users if m.gate(u) != VocabProbe(today_vocab).gate(u))
    m.db.close()
    if dbf.exists():
        dbf.unlink()

    pool = set()
    for r in corpus:
        pool |= prefixes(r["text"])

    (a_trace, a_last), (b_trace, b_last) = sequential_curves(corpus, ledger)
    growth, last_new, last_seq, pool_from_growth = vocab_growth(corpus)

    ks = sorted(set(K_TABLE + [len(today_vocab), len(pool)]))
    curve = saturation_curve(pool, users, ks, N_SEEDS)

    # 사유별 분해 — k마다 전량. 바닥값·분모 검사가 이 표를 읽는다.
    order = sorted(pool)
    random.Random(20260910).shuffle(order)
    counts_by_k = {k: gate_counts(order[:k], users) for k in ks}
    past_by_k = {k: c[R_PAST] for k, c in counts_by_k.items()}
    totals_by_k = {k: sum(c.values()) for k, c in counts_by_k.items()}

    # 🔴 **오늘의 «실제» 어휘 점 — 무작위 곡선에서 읽어 오지 않고 따로 잰다.**
    #    같은 크기라도 실제 어휘는 화제가 몰려 있어 덮는 턴이 겹친다(A6).
    today_counts = gate_counts(today_vocab, users)
    today_fired = fired(today_counts)

    thr = derive_threshold(pool, users, M_TRIGGER_PCT,
                           FINE_LO, min(len(pool), FINE_HI), N_SEEDS_FINE)

    return dict(
        corpus=corpus, users=users, n_utt=len(users),
        today_vocab=today_vocab, pop_sig=sig, pool=pool,
        anchor_disagreements=dis,
        a_trace=a_trace, b_trace=b_trace, a_last=a_last, b_last=b_last,
        growth=growth, last_new=last_new, last_seq=last_seq,
        pool_from_growth=pool_from_growth,
        ks=ks, curve=curve, counts_by_k=counts_by_k,
        past_by_k=past_by_k, totals_by_k=totals_by_k,
        today_counts=today_counts, today_fired=today_fired,
        today_counts_n=len(today_vocab),
        today_rate=today_fired / len(users),
        thr=thr, M=M_TRIGGER_PCT)


def report(st):
    n = st["n_utt"]
    p = print
    p("=" * W)
    p("실험 29 — 게이트 포화: 어휘가 자라면 게이트는 자기 자신을 무력화하는가")
    p("=" * W)
    p("\n재현: PYTHONIOENCODING=utf-8 python -B experiments/gate_saturation.py")
    p(f"모집단: user 발화 **{n}건**(분모 · 전 표에서 같다) · "
      f"event 색인 서명 {st['pop_sig']} · 코퍼스 접두 전체 {len(st['pool'])}개")
    p(f"오늘의 어휘: |_recall_vocab| = **{len(st['today_vocab'])}** "
      f"(`eval/fact-ledger.yaml` 22항목이 event 색인에 들어간 결과)")

    p("\n" + "-" * W)
    p("§A. 앵커 — 이 실험이 프로덕션 게이트를 돌리고 있는가")
    p("-" * W)
    p(f"  `VocabProbe.gate is Memory.gate` = {VocabProbe.gate is Memory.gate}")
    p(f"  실제 `Memory` 인스턴스와 판정·사유 불일치: "
      f"**{st['anchor_disagreements']}/{n}건**")
    p("  → 아래 모든 수는 `prototype/memory.py`의 `Memory.gate` **그 함수**가 낸 것이다.")

    p("\n" + "-" * W)
    p("§B. ① 순차 곡선 — 코퍼스를 순서대로 흘린다 (분모: 그 시점까지의 user턴)")
    p("-" * W)
    p("  팔 A = 대장 추출(오늘 저장되는 22항목) · 팔 B = 이상 추출(모든 턴이 저장된다)")
    p(f"\n  {'user턴':>7}{'A |V|':>7}{'A 누적발화':>12}{'B |V|':>7}{'B 누적발화':>12}")
    p("  " + "-" * 45)
    marks = list(range(0, n, 50)) + [n - 1]
    for i in marks:
        a, b = st["a_trace"][i], st["b_trace"][i]
        p(f"  {a[0]:>7}{a[2]:>7}{a[3]:>7}/{a[0]:<4}"
          f"{b[2]:>7}{b[3]:>7}/{b[0]:<4}")
    ae, be = st["a_trace"][-1], st["b_trace"][-1]
    p(f"\n  끝: A |V|={ae[2]} · 발화 {ae[3]}/{n} = {ae[3]/n*100:.1f}%"
      f"   |   B |V|={be[2]} · 발화 {be[3]}/{n} = {be[3]/n*100:.1f}%")
    p(f"  🔴 **어디서 평평해지는가** — 어휘가 마지막으로 자란 자리:")
    p(f"     A: user턴 {st['a_last'][0]}/{n} (seq {st['a_last'][1]}) 에서 "
      f"|V|={st['a_last'][2]}, 이후 **끝까지 한 개도 안 는다**")
    p(f"     B: user턴 {st['b_last'][0]}/{n} (seq {st['b_last'][1]}) 에서 "
      f"|V|={st['b_last'][2]}")
    delta = st["a_last"][2] - len(st["today_vocab"])
    p(f"  ⚠️ A의 끝 |V|={ae[2]}는 오늘의 `|_recall_vocab|`={len(st['today_vocab'])}보다 "
      f"**{delta}개 많다.**")
    p(f"     `_recall_vocab`은 `user_deleted=0`만 세는데(색인 서명 {st['pop_sig']} — "
      f"22행 중 21행 생존),")
    p("     이 순차 팔은 **저장 시점**만 보고 나중의 무효화를 되돌리지 않는다. "
      "무효화를 세면 어휘는 줄 수도 있다.")
    # 구간 발화율 — 누적은 초기값을 오래 끌고 다닌다.
    B = 50
    p(f"\n  구간 발화율 (누적이 아니라 그 구간 안에서 · 분모는 열에 함께 찍는다)")
    p(f"  {'구간':>12}{'A 발화/분모':>14}{'B 발화/분모':>14}")
    for i in range(0, n, B):
        j = min(i + B, n)
        a0 = st["a_trace"][i - 1][3] if i else 0
        b0 = st["b_trace"][i - 1][3] if i else 0
        a1, b1 = st["a_trace"][j - 1][3], st["b_trace"][j - 1][3]
        d = j - i
        p(f"  {i+1:>5}-{j:<6}{a1-a0:>9}/{d:<5}{b1-b0:>9}/{d:<5}")

    p("\n" + "-" * W)
    p("§C. 어휘가 자라는 속도 — «다양해지면»의 대리 지표")
    p("-" * W)
    p(f"  코퍼스 720턴에서 처음 보는 접두의 도착 수 (100 seq 구간별, 합 "
      f"{sum(st['growth'].values())} = 접두 전체 {st['pool_from_growth']})")
    for b in sorted(st["growth"]):
        lo, hi = b * 100 + 1, (b + 1) * 100
        p(f"    seq {lo:>4}-{hi:<4} {'▮' * max(1, st['growth'][b] // 3)} "
          f"{st['growth'][b]}")
    p(f"\n  🔴 마지막 새 접두가 온 자리: **seq {st['last_new']} / {st['last_seq']}** "
      f"({st['last_new']/st['last_seq']*100:.0f}% 지점)")
    p("  → 도착이 줄기는 해도 **0이 되지 않는다.** 이 코퍼스는 어휘적으로 소진되지 않았다.")

    p("\n" + "-" * W)
    p("§D. ② 포화 극한 — 어휘를 «저장될 수 있는 접두 전체»에서 뽑는다")
    p("-" * W)
    p(f"  pool = 코퍼스 접두 전체 {len(st['pool'])}개 · 중첩 표본 {N_SEEDS}개 · "
      f"분모 **{n}** (전량, 고정)")
    p(f"\n  {'|V|':>5}{'발화율 평균':>12}{'최소':>8}{'최대':>8}{'발화/분모(평균)':>18}")
    p("  " + "-" * 51)
    today_k = len(st["today_vocab"])
    for k in st["ks"]:
        v = st["curve"][k]
        mean = sum(v) / len(v)
        # 🔴 **`← 오늘`을 여기 붙이지 않는다.** 이 행은 «크기만 오늘과 같은
        #    무작위 표본»이고 오늘의 실제 어휘가 아니다 — 붙였다가 A6이 잡았다.
        tag = "  ← 오늘과 **같은 크기**(같은 어휘 아님)" if k == today_k else (
              "  ← 극한 (pool 전량)" if k == len(st["pool"]) else "")
        p(f"  {k:>5}{mean*100:>11.1f}%{min(v)*100:>7.1f}%{max(v)*100:>7.1f}%"
          f"{mean*n:>12.0f}/{n:<5}{tag}")

    band = st["curve"][today_k]
    p(f"\n  🔴 **오늘의 «실제» 어휘는 이 곡선 위에 있지 않다.**")
    p(f"     실제 `_recall_vocab`({today_k}개) → 발화 **{st['today_fired']}/{n} = "
      f"{st['today_rate']*100:.1f}%**")
    p(f"     같은 크기 무작위 표본 {N_SEEDS}개 → 평균 "
      f"{sum(band)/len(band)*100:.1f}% · 최소 {min(band)*100:.1f}% · "
      f"최대 {max(band)*100:.1f}%")
    p(f"     → 실제가 무작위 평균의 **{sum(band)/len(band)/st['today_rate']:.1f}분의 1**이고 "
      f"**표본 최소보다도 낮다.**")
    p("     실제 어휘는 대장 22항목이 다루는 **몇 개 화제에 몰려 있어** 덮는 턴이")
    p("     겹친다. 무작위 추출이 가정하는 «화제가 고르게 다양해진다»가 이 코퍼스에서")
    p("     **얼마나 틀리는지**가 이 두 수의 비다.")
    p(f"  🔴 **그래서 아래 §F의 N은 낙관적 경계다** — 실제 어휘 궤적으로 재면 "
      f"트리거는 더 늦게 열린다.")
    p(f"     ⚠️ 얼마나 늦는지는 **이 실험이 유도하지 못한다**: 실제 궤적이 하나뿐이라 "
      f"곡선이 안 나온다.")

    p("\n" + "-" * W)
    p("§E. 발화 이유별 분해 — 정규식 바닥값은 얼마인가")
    p("-" * W)
    p("  게이트는 **첫 일치 규칙**으로 사유를 붙인다 — `과거 참조 표현`이 먼저다.")
    p("  ⚠️ 그래서 이 표는 «각 규칙이 혼자 할 수 있는 일»이 아니라 «누가 먼저")
    p("     잡았나»의 분해다. 어휘가 커져도 `과거참조` 열이 안 움직이는 것이")
    p("     그 규칙이 **어휘와 무관하다**는 증거이고, 그것이 바닥값의 정의다.")
    p(f"  (단일 중첩 궤적 — seed 20260910 하나를 앞에서부터 k개 자른 것)")
    p(f"\n  {'|V|':>5}{'과거참조':>10}{'접점':>10}{'너무짧음':>10}"
      f"{'의례적':>8}{'접점없음':>10}{'합':>7}")
    p("  " + "-" * 60)
    for k in st["ks"]:
        c = st["counts_by_k"][k]
        p(f"  {k:>5}{c[R_PAST]:>10}{c[R_CONTACT]:>10}{c[R_SHORT]:>10}"
          f"{c[R_RITUAL]:>8}{c[R_NONE]:>10}{sum(c.values()):>7}")
    tc = st["today_counts"]
    p("  " + "-" * 60)
    p(f"  {'실제':>5}{tc[R_PAST]:>10}{tc[R_CONTACT]:>10}{tc[R_SHORT]:>10}"
      f"{tc[R_RITUAL]:>8}{tc[R_NONE]:>10}{sum(tc.values()):>7}"
      f"  ← 오늘의 `_recall_vocab` ({len(st['today_vocab'])}개)")
    p(f"     같은 크기의 무작위 궤적은 접점 {st['counts_by_k'][len(st['today_vocab'])][R_CONTACT]}건인데 "
      f"실제는 {tc[R_CONTACT]}건이다 — **접점 팔은 어휘의 크기가 아니라 «어디에 몰려 있는가»에 반응한다.**")
    floor = st["past_by_k"][st["ks"][0]]
    top = st["counts_by_k"][len(st["pool"])]
    p(f"\n  🔴 **정규식 바닥값 = {floor}/{n} = {floor/n*100:.1f}%** — 어휘가 0이든 "
      f"{len(st['pool'])}든 움직이지 않는다.")
    p(f"  🔴 극한에서 안 열리는 {n - fired(top)}건은 **전부 «{R_SHORT}»**"
      f" (`접점없음` {top[R_NONE]}건).")
    p("     → 어휘가 코퍼스를 덮으면 게이트는 **길이 필터로 퇴화한다.**")
    p(f"  ⚠️ «{R_RITUAL}» 가지는 {n}턴에서 {sum(st['counts_by_k'][k][R_RITUAL] for k in st['ks'])}번 탔다 — "
      f"길이 검사가 먼저 잡기 때문이다(의례 낱말은 전부 8자 미만).")

    p("\n" + "-" * W)
    p("§F. 열리는 조건 — N·M을 어떻게 유도했나")
    p("-" * W)
    d = st["thr"]
    p(f"  M = **{st['M']:.0f}%** — 이 실험이 고른 값이 **아니다.** "
      f"`ADR-006`의 재검토 트리거")
    p(f"       *\"검색 필요 턴 비율이 60%를 넘으면 → 게이팅의 이득이 작다\"*의 그 60이다.")
    p(f"  N — pool {len(st['pool'])}개에서 중첩 표본 {N_SEEDS_FINE}개로 "
      f"k를 {d['ks'][0]}부터 {d['ks'][-1]}까지 **1칸씩** 훑어 유도했다. "
      f"**하나가 아니라 셋이다:**")
    today = len(st["today_vocab"])
    tag_of = {}
    for nm in ("N_any", "N_mean", "N_all"):
        if d[nm] is not None:
            tag_of.setdefault(d[nm], []).append(nm)
    tag_of.setdefault(today, []).append("오늘")
    show = sorted({k for anchor in list(tag_of) for k in (anchor - 1, anchor)
                   if k in d["means"]})
    p(f"\n  {'k':>5}{'표본 최소':>11}{'평균':>10}{'표본 최대':>11}"
      f"{'평균 발화/분모':>16}")
    p("  " + "-" * 53)
    prev = None
    for k in show:
        if prev is not None and k > prev + 1:
            p(f"  {'⋮':>5}")
        tags = tag_of.get(k, [])
        p(f"  {k:>5}{d['mins'][k]:>10.2f}%{d['means'][k]:>9.2f}%"
          f"{d['maxs'][k]:>10.2f}%{d['means'][k]/100*n:>11.0f}/{n:<4}"
          f"{'  ← ' + ', '.join(tags) if tags else ''}")
        prev = k
    p(f"\n  · **N_any = {d['N_any']}** — 운 좋은 표본 **하나가** M을 넘기 시작하는 곳")
    p(f"  · **N_mean = {d['N_mean']}** — **평균**이 M을 넘는 곳", end="")
    p(f" ({d['means'][d['N_mean']]:.2f}% ≥ {st['M']:.0f}% > "
      f"{d['means'][d['N_mean']-1]:.2f}%)" if d["N_mean"] else "")
    p(f"  · **N_all = {d['N_all']}** — {N_SEEDS_FINE}개 표본이 **전부** M을 넘는 곳")
    p(f"\n  🔴 **관측 가능한 형태로 적으면:**")
    p(f"     «`|_recall_vocab|`가 **{d['N_mean']}**을 넘으면 게이트 발화율이 "
      f"**{st['M']:.0f}%**를 넘고, 그때")
    p(f"      ADR-006의 재검토 트리거(*\"60%를 넘으면 게이팅의 이득이 작다\"*)가 "
      f"열린다.»")
    p(f"     분모 **{n}** user턴 · 이 코퍼스 · 중첩 표본 {N_SEEDS_FINE}개 · "
      f"**불확실 구간 {d['N_any']}–{d['N_all']}**")
    p(f"  ⚠️ **구간의 폭이 이 유도의 정직한 크기다.** 표본 12개로 잡으면 N_mean이 "
      f"72로 나왔다 —")
    p(f"     이웃 k의 평균 차이가 0.1%p 미만이라 **표본이 적으면 N이 seed 집합의 "
      f"함수가 된다.**")
    p(f"  🔴 **그리고 이 N은 낙관적 경계다** — 무작위 어휘로 유도했는데, 실제 어휘는 "
      f"같은 크기에서")
    p(f"     발화가 {sum(st['curve'][today])/len(st['curve'][today])/st['today_rate']:.1f}배 "
      f"적다(§D). 실제 궤적의 N은 이보다 **크다.** 얼마나 큰지는 못 잰다.")
    if d["N_mean"] and d["N_all"]:
        p(f"\n  오늘 |_recall_vocab| = **{today}** → N_mean까지 어휘 "
          f"**{d['N_mean'] - today}개**({d['N_mean']/today:.2f}배), "
          f"보수적 경계 N_all까지 **{d['N_all'] - today}개**"
          f"({d['N_all']/today:.2f}배).")
        rows = st["pop_sig"][1]
        p(f"  ⚠️ 이 여유는 **어휘 개수**로 잰 것이지 시간이 아니다. 색인 {rows}행이 "
          f"어휘 {today}개를 만들었으니 같은 밀도라면")
        p(f"     **+{(d['N_mean'] - today) * rows / today:.0f}행**에서 N_mean, "
          f"**+{(d['N_all'] - today) * rows / today:.0f}행**에서 N_all이다 "
          f"(조잡한 외삽 — 새 행의 낱말은 겹칠수록 어휘를 덜 늘린다).")

    p("\n" + "-" * W)
    p("§G. 🔴 평평함은 무엇의 성질인가 — 이 실험의 판정")
    p("-" * W)
    p(f"  ① 순차 곡선(팔 A)은 평평하다: |V| {ae[2]}에서 멈추고 발화 "
      f"{ae[3]}/{n} = {ae[3]/n*100:.1f}%.")
    p(f"  ② 같은 코퍼스·같은 게이트인데 팔 B는 |V| {be[2]}까지 자라고 "
      f"{be[3]}/{n} = {be[3]/n*100:.1f}%에 닿는다.")
    p(f"  ③ 코퍼스는 **어휘적으로 소진되지 않았다** — 마지막 새 접두가 "
      f"seq {st['last_new']}/{st['last_seq']}에 온다.")
    p("\n  → **평평함은 휴리스틱의 성질이 아니다.** 어휘가 자라면 발화율은 "
      "실제로 계속 오른다(②·§D).")
    p("  → **코퍼스의 어휘적 반복성도 아니다.** 새 화제가 끝까지 도착한다(③).")
    p(f"  → 평평하게 만든 것은 **«무엇이 저장되는가»**다 — 대장 22항목이 "
      f"어휘를 {ae[2]}에서 묶어 둔다.")
    p("     즉 **게이트를 지키고 있는 것은 게이트가 아니라 추출기의 인색함이고,**")
    p("     그것은 이 저장소가 고칠 계획을 이미 가진 부분이다(추출 커버리지).")

    p("\n" + "-" * W)
    p("§H. ⚠️ 이 실험이 말할 수 없는 것")
    p("-" * W)
    p("  · **코퍼스가 하나다.** «다양해지면»은 이 720턴 안에서 **모사**한 것이지")
    p("    실제 화제 다양성이 아니다. 다른 코퍼스에서 N도 극한도 다를 수 있다.")
    p("  · 🔴 **무작위 추출은 «화제가 고르게 다양해진다»를 가정하고, 그 가정이 이")
    p("    코퍼스에서 얼마나 틀리는지는 §D가 실제로 쟀다** — 같은 크기 62개에서")
    p(f"    실제 {st['today_rate']*100:.1f}% vs 무작위 평균 "
      f"{sum(st['curve'][len(st['today_vocab'])])/N_SEEDS*100:.1f}%. 그래서 §D·§F의")
    p("    곡선과 N은 **낙관적 경계**로만 읽는다. ⚠️ 다만 실제 궤적이 하나뿐이라")
    p("    «진짜 곡선»은 이 실험이 못 그린다 — 경계가 있고 그 안쪽이 비어 있다.")
    p("  · **팔 B의 «모든 턴이 저장된다»는 상한이지 계획이 아니다.** 실제 추출기가")
    p("    어디까지 저장할지는 이 실험이 모른다 — 팔 A와 팔 B 사이 어딘가다.")
    p("  · 🔴 **게이트가 참을 많이 내는 것 자체는 결함이 아니다.** 발화율은 비용")
    p("    (검색 지연·오주입)과 이득(회상)의 교환에서 **한쪽 축일 뿐**이고, 이")
    p("    실험은 **문이 얼마나 열리는가만** 잰다. 그 문 뒤의 교환비는")
    p("    `prototype/gate_sweep.py`(실험 12)와 실험 21의 격자가 잰다.")
    p("  · **접두 2글자 규칙 자체는 흔들지 않았다.** 3글자였다면 pool도 발화율도")
    p("    다르다 — 이 실험은 **오늘의 규칙 안에서** 포화를 잰다.")

    p("\n" + "-" * W)
    p("§I. 검사 — 심을 위반이 붙는 자리")
    p("-" * W)
    results = run_checks(st)
    for name, ok, detail in results:
        p(f"  {'✅' if ok else '🔴'} {name:<28} {detail}")
    bad = [r for r in results if not r[1]]
    p("\n" + "=" * W)
    return 1 if bad else 0


def main():
    return report(measure())


if __name__ == "__main__":
    sys.exit(main())
