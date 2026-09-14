# -*- coding: utf-8 -*-
"""
scoring.py — 생존 채점의 **단일 정본**. (단계 0-b)

## 왜 이 파일이 생겼나

"요약에 대장 항목이 살아남았는가"를 재는 함수가 **두 벌** 있었다
(`drift_probe.py:62`와 `summary_local.py:90`). 같은 규칙을 두 곳에 적어두면
한쪽만 고쳐지고, 그러면 실험 19(Gemini)와 실험 20(로컬)의 숫자가 조용히
비교 불가능해진다. 그래서 여기로 모은다.

## 왜 함수가 **둘**인가

`survived_frozen`은 **옛 구현 그대로**다. 바꾸면 실험 19/20의 기존 측정이
재현되지 않는다 — 그 둘을 비교하는 것이 실험 20의 존재 이유다. **동결한다.**

`survived_v2`는 그 구현의 **위양성 3건**을 잡는다. 프로브
`"지우는 요즘 고민이 있음. 회사 일이 크게 늘었다."`에 대해 옛 구현은
`지우는 마케팅 회사 대리` / `지우에게 여동생이 한 명 있음` /
`지우가 회사에서 크게 깨지고 새벽에 연락함` 셋을 "살아남았다"고 판정한다.
셋 다 요약이 실제로 담고 있지 않다. 겹친 어근이 **화자 이름 `지우`**와
**길이 1짜리 파편(`있`·`크`)**뿐이라서 벌어진 일이다.

## 🔴 왜 함수가 **셋**이 됐나 — 그리고 `survived_v2`도 안 고친다

실험 26(`scorer_eval.py`)이 v2의 오답 셋을 **이름으로** 찍었다: `P12`·`P14`·`P15`.
전부 위양성이고 **전부 같은 지문** — 면접 사건을 **다른 회차의** 면접 요약에 붙였다.
겹친 어근이 `{면접, 번째}`이고 회차를 가르는 `첫`·`두`·`세`가 사라진다.

`survived_v3`이 그것을 고친다. 🔴 **v2를 제자리에서 고치지 않는 이유는 P1과 같다:**
`digest_budget.py` 3절의 M2 상한 대조군과 [docs/11 실험 26]의 표가 **`survived_v2`라는
이름으로 기록된 값**을 갖고 있다. 그 이름 아래의 숫자를 바꾸면 «모양만 같고 다른 집합»이
되고, 그것이 S16이 실측으로 배운 실패 모드 ②다. **v2는 기록으로 얼리고, v3을 옆에 둔다.**
실험 26은 둘을 **같은 실행에서 나란히** 찍는다 — 라운드를 건너 화살표를 그리지 않는다.

**모든 표는 `frozen` / `v2` 두 열을 찍는다. 실험 26의 표는 `v2` / `v3` 두 열을 더 찍는다.**
"""
import os
import re
import sys
from typing import NamedTuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "prototype"))
from memory import Memory                                  # noqa: E402

# 화자 이름이라 **대장 항목 11개 중 10개에 나온다.** 어근 겹침 채점에서
# 편재 어근은 신호가 아니라 배경이다 — 이것 하나로 분자가 채워지면
# "요약이 이 항목을 남겼다"가 아니라 "요약이 지우 얘기다"를 잰 것이다.
# 집합으로 두는 이유: 다른 코퍼스에는 다른 이름이 편재한다.
UBIQUITOUS = {"지우"}

# 🆕 🔴 **유도 이력.** 실험 30이 이 값을 유도했는데 그 근거가 코드에 안 남았다.
#   여기가 그 자리다 — `THETA_BY_MODE`(`memory.py:224`)가 θ에 대해 하는 것과 같은 형태다.
#
# ⚠️ **왜 값 안이 아니라 값 옆인가.** `THETA_BY_MODE`는 유도 이력을 값 자체에
#   튜플로 넣는다(`(theta, f, n, population_sig)`). 여기서는 그럴 수 없다 —
#   `UBIQUITOUS`는 `survived_v2`의 **닫힌 해시 안**에 있어서
#   (`test_scoring.TestFrozenClosureIsFrozen.REACH`에 이름으로 적혀 있다)
#   값의 모양을 바꾸면 얼린 것이 움직인다. 그래서 **동결 함수가 읽지 않는 별도
#   객체**로 옆에 두고, 대조는 **별도 함수**(`stale_ubiquitous`)가 한다.
#   `stale_theta`도 값이 아니라 `retrieve()`가 대조한다 — 같은 분업이다.
#
# 🔴 **집합이 아니라 정렬된 튜플로 든다.** `repr(set)`의 순서는 `PYTHONHASHSEED`의
#   함수라, 집합으로 두면 이 이력을 찍거나 해시하는 순간 «오늘 운이 나빠서» 갈린다.
UBIQUITOUS_PROVENANCE = {
    "basis": "대장-22 — `eval/fact-ledger.yaml`의 facts + events 전량",
    "rule": "문서빈도 DF >= tau",
    "tau": 0.50,
    "n": 22,                    # 기저 문서 수 (분모 · G15)
    # 🔴 답은 **점이 아니라 구간**이다. 컷이 `>=`라 유도 집합은 반개구간
    #   `(band_lo, band_hi]` 위에서 상수다. 폭이 «유도됐다»의 근거이고,
    #   좁으면 «맞춘 것»이다 — 여기서는 5/22 ~ 12/22, 즉 **31.8%p**.
    #   비율을 반올림해 적지 않는다: 분수로 두어야 재유도와 글자 그대로 만난다.
    "band": (5 / 22, 12 / 22),
    "derived": ("지우",),       # 유도값. **현행 `UBIQUITOUS`와 같아야 한다**
    # `(facts 행 수, events 행 수)` — `stale_theta`의 `population_sig`와 같은 뜻이다.
    # 기저가 이만큼에서 움직이면 위의 DF도 구간도 다시 유도해야 한다.
    "population_sig": (12, 10),
    "source": "experiments/hardcoding_audit.py 절 2 (실험 30 §C)",
}

# 어근이 이만큼은 남아야 겹침 비율이 뜻을 갖는다. 1개짜리 분모는
# 한 번만 맞아도 100%가 되어 판정이 동전 던지기가 된다.
MIN_ROOTS = 2


class V2Result(NamedTuple):
    """
    `survived`와 `unscorable`을 **함께** 돌려준다.

    판정 불가를 리스트에서 조용히 빼면 그것이 '비생존'과 섞여 분모를 오염시킨다
    (`썸` 같은 항목이 소리 없이 0으로 세어지던 문제). 1급 필드로 올려서
    호출부가 **따로 보고하도록 강제한다.**
    """
    survived: list
    unscorable: list


def survived_frozen(text, items):
    """대장 항목 중 요약에 살아남은 것. 어근 겹침으로 본다(교착어).

    ⚠️ **동결.** `drift_probe.py:62`의 옛 구현과 논리가 같아야 한다 —
    실험 19/20의 기존 숫자를 재현하는 것이 유일한 용도다. 고치지 말 것.
    """
    tr = Memory._roots(text)
    out = []
    for it in items:
        ir = Memory._roots(it)
        if ir and len(tr & ir) / len(ir) >= 0.5:
            out.append(it)
    return out


def _clean_roots(text):
    """길이 1 어근과 편재 어근을 걷어낸 어근 집합 — v2의 전처리."""
    return {r for r in Memory._roots(text)
            if len(r) > 1 and r not in UBIQUITOUS}


def survived_v2(text, items):
    """
    위양성을 잡는 생존 채점. 규칙 셋 다 F13의 실측에서 나왔다.

      1. 길이 1인 어근 제거      — `있`·`크` 같은 파편은 어근이 아니라 잔해다
      2. 편재 어근 제외          — `UBIQUITOUS` (화자 이름)
      3. 남은 어근이 2개 미만이면 **판정 불가** — 생존도 비생존도 아니다
    """
    tr = _clean_roots(text)
    survived, unscorable = [], []
    for it in items:
        ir = _clean_roots(it)
        if len(ir) < MIN_ROOTS:
            unscorable.append(it)
            continue
        if len(tr & ir) / len(ir) >= 0.5:
            survived.append(it)
    return V2Result(survived, unscorable)


# ── v3: 회차(서수) 불일치 ────────────────────────────────────────────────
#
# 🔴 이 상수가 `_clean_roots`가 아니라 **원문**을 다시 읽는 이유.
#   `첫`·`두`·`세`는 `_clean_roots`의 «길이 1 어근 제거»가 버리는 것이 **아니다.**
#   그 앞에서 `Memory._roots`가 **토큰 단계에서** 버린다(`len(w) < 2` → `continue`).
#   즉 `_clean_roots`는 그 글자들을 **본 적이 없고**, 거기서 길이 조건을 풀어도
#   서수는 돌아오지 않는다. 원문을 다시 읽는 것 말고 다른 자리가 없다.
_ORDINALS = frozenset(
    "첫 두 세 네 한 둘 셋 넷 다섯 여섯 일곱 여덟 아홉 열".split())

# 🔴 «서수가 **뒤 낱말**에 붙는» 유일한 표지. 한국어에서 수량 분류사(`차례`·`번`·
#   `개`)는 앞 낱말을 세지만 `번째`는 **뒤 낱말의 회차**를 매긴다 — `세 번째 면접`.
#   이 하나만 투명하게 통과시키는 이유는 아래 `_ordinal_heads`의 주석에 있다.
_ORDINAL_MARKER = "번째"


def _head_root(tok):
    """토큰 하나를 `Memory._roots`와 **같은 정규화**로 깎는다 (`면접을` → `면접`).

    정규화를 새로 쓰지 않는 것이 요점이다 — 서수 묶음이 두 텍스트에서 **같은
    모양으로** 나와야 비교가 뜻을 갖는데, 정규화가 둘이면 그것부터 갈라진다.
    """
    r = Memory._roots(tok)
    return next(iter(r)) if len(r) == 1 else None


def _ordinal_heads(text):
    """`{머리 낱말: {붙은 서수, …}}`. `세 번째 면접` → `{번째: {세}, 면접: {세}}`.

    🔴 **서수를 집합으로 따로 모으지 않는 이유.** S16은 *"두 번째 면접과 회의
    **세 차례**"*라, 서수만 모으면 `{두, 세}`가 되고 «세 번째 면접»이 그 `세`로
    통과한다. **`세 차례`의 `세`와 `세 번째`의 `세`는 다른 것을 센다.**
    서수를 **무엇에 붙었는지와 함께** 들고 있어야 그 둘이 갈린다.

    🔴 **`번째`를 투명하게 통과시키는 이유.** `첫 번째 면접`과 `첫 면접`은 같은
    회차이고, 머리를 `번째`로만 잡으면 그 둘이 안 만나 **없는 불일치가 생긴다**
    (실측: 그 판이 `E004`×`S14` — 같은 면접인 쌍 — 을 죽였다). 그래서
    `번째` 뒤의 낱말에도 같은 서수를 매단다. 투명한 것은 이 하나뿐이다 —
    `차례`·`번`·`개`는 **앞** 낱말을 세므로 뒤로 넘기면 그것이 오발화가 된다.

    ⚠️ **마크다운 목록 번호는 뺀다.** `1. 사용자는 …`의 `1.`은 회차가 아니라
    글머리다. 안 빼면 요약 스물넷 중 열여덟이 `{사용자: {1}}` 같은 가짜 머리를
    들고 다니고, 그것이 언젠가 진짜 서수와 부딪친다.
    ⚠️ 붙여 쓴 `첫번째`는 **못 잡는다** — `세`+`션` 같은 우연한 접두 일치가 가짜
    머리를 만들기 때문이다. 재현율을 버리고 정확도를 골랐다.
    """
    raw = text.split()
    toks = [re.sub(r"[^\w가-힣]", "", w) for w in raw]
    out = {}

    def put(head, ordinal):
        if head:
            out.setdefault(head, set()).add(ordinal)

    for i, a in enumerate(toks):
        is_ord = a in _ORDINALS or (
            a.isdigit() and not re.fullmatch(r"\d+\.", raw[i]))
        if not is_ord or i + 1 >= len(toks):
            continue
        b = _head_root(toks[i + 1])
        put(b, a)
        if b == _ORDINAL_MARKER and i + 2 < len(toks):
            put(_head_root(toks[i + 2]), a)
    return out


def _ordinal_conflict(item_heads, text_heads):
    """**같은 머리 낱말**에 붙은 서수가 서로 완전히 어긋나는가.

    🔴 «양쪽에 서수가 있는데 안 겹친다»가 아니라 «**같은 것**을 세는데 수가
    다르다»를 본다. 앞의 것은 `세 차례`와 `첫 번째`를 부딪치게 만든다.
    """
    return any(text_heads.get(h) and not (o & text_heads[h])
               for h, o in item_heads.items())


def survived_v3(text, items):
    """
    v2 + **회차 불일치**. 실험 26이 이름으로 찍은 위양성 셋을 잡는다.

      4. 항목과 본문이 **같은 낱말을 세는데 회차가 어긋나면**
         겹침 비율과 무관하게 **비생존**

    🔴 **머리가 안 겹치면 발화하지 않는다.** 본문이 회차를 안 말하는 것은 «다른
    회차다»가 아니라 «회차를 안 말한다»이고, 거기서 비생존을 찍으면 서수를 가진
    항목이 서수 없는 요약에 대해 영구히 죽는다. 보수적인 쪽을 골랐고, 그래서 이
    규칙은 **v2가 생존이라 한 것만 뺄 수 있다** — `v3.survived ⊆ v2.survived`이고
    `unscorable`은 **v2와 항상 같다.** 분모가 갈라지지 않는 것이 이 설계의 값이다.
    """
    th = _ordinal_heads(text)
    tr = _clean_roots(text)
    survived, unscorable = [], []
    for it in items:
        ir = _clean_roots(it)
        if len(ir) < MIN_ROOTS:
            unscorable.append(it)      # v2와 **같은 분모**를 쓴다 — 여기서 안 가른다
            continue
        if _ordinal_conflict(_ordinal_heads(it), th):
            continue                   # 회차가 어긋난다 — 겹침 비율을 보지 않는다
        if len(tr & ir) / len(ir) >= 0.5:
            survived.append(it)
    return V2Result(survived, unscorable)


# ══════════════════════════════════════════════════════════════════════════
# 🆕 유도 이력의 **대조** — 동결 경계 **밖**이다
# ══════════════════════════════════════════════════════════════════════════
#
# 🔴 **위 어느 동결 함수도 아래를 부르지 않는다.** 부르는 순간 `co_names`를 타고
#   닫힌 해시 안으로 들어오고, 그러면 유도 이력을 손볼 때마다 «얼린 것»이
#   움직인다. `stale_theta`가 `THETA_BY_MODE`의 값을 바꾸지 않는 것과 같은 분업이다.
#
# 🔴 **유도 규칙을 여기 한 벌만 둔다** (F12 · 사본 금지). `hardcoding_audit.py`가
#   같은 규칙의 지역 사본을 들고 있었다 — 사본이 둘이면 «유도값이 현행값과 같다»가
#   어느 규칙에 대한 말인지 알 수 없어진다. 그 파일은 이제 여기를 import한다.


def doc_freq(docs):
    """`{어근: 등장 문서 수}`. `Memory._roots`를 **그대로** 쓴다 (사본 금지 · F12)."""
    df = {}
    for t in docs:
        for r in Memory._roots(t):
            df[r] = df.get(r, 0) + 1
    return df


def derive_ubiquitous(docs, tau):
    """문서빈도 비율이 `tau` 이상인 어근 — 이것이 «유도된 `UBIQUITOUS`»다.

    **정렬된 튜플**로 돌려준다. 집합으로 돌려주면 호출부가 그것을 찍거나 해시하는
    순간 `PYTHONHASHSEED`에 따라 순서가 갈리고, 그러면 대조가 «내용이 다르다»가
    아니라 «오늘 운이 나빴다»로 빨개진다.
    """
    n = len(docs) or 1
    return tuple(sorted(r for r, c in doc_freq(docs).items() if c / n >= tau))


def stable_band(docs, target):
    """`target`과 **정확히 같은** 집합을 주는 tau 반개구간 `(하한, 상한]`. 없으면 None.

    🔴 컷이 `>=`라 유도 집합은 `(rs[i-1], rs[i]]` 위에서 상수다. 눈금 하나를 답으로
       찍으면 «0.545에서만 나온다»처럼 읽혀 폭이 0으로 보인다. 폭이 근거다.
    """
    n = len(docs) or 1
    df = doc_freq(docs)
    rs = sorted({c / n for c in df.values()})
    lo = hi = None
    want = tuple(sorted(target))
    for i, r in enumerate(rs):
        if tuple(sorted(x for x, c in df.items() if c / n >= r)) == want:
            if lo is None:
                lo = rs[i - 1] if i else 0.0
            hi = r
    return None if lo is None else (lo, hi)


def ledger_docs(root=None):
    """유도 기저 «대장-22» — `eval/fact-ledger.yaml`의 facts + events. **읽기만** 한다 (A8).

    지연 로딩이다: import 시점에 읽으면 `scoring`을 쓰는 **모든** 스크립트가 대장
    파일에 매인다. 대조할 때만 읽는다.
    돌려주는 것: `(문서 리스트, (facts 행 수, events 행 수))`.
    """
    import yaml
    root = root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "eval", "fact-ledger.yaml"), encoding="utf-8") as f:
        led = yaml.safe_load(f)
    return ([f["text"] for f in led["facts"]] + [e["text"] for e in led["events"]],
            (len(led["facts"]), len(led["events"])))


def stale_ubiquitous(docs=None, sig=None):
    """
    🆕 `UBIQUITOUS_PROVENANCE`가 **지금 기저에서도 참인가.** `stale_theta`와 같은 계약:
    **값을 바꾸지도, 예외를 던지지도 않는다** — 어긋난 것을 사유 목록으로 돌려줄 뿐이다 (P5).

    돌려주는 것: `[(사유, 기록값, 지금값), …]`. 빈 리스트 = 이력이 아직 참이다.

    🔴 **구간을 두 방향으로 건다.** 실험 30 §H가 적은 실패가 정확히 여기다 — 처음
    쓴 구간 시험은 «폭이 넓은가»만 보고 «그 구간 **안에서** 그 집합이 나오는가»를
    안 봤고, 그래서 발화하지 못했다. 안(구간 안 눈금이 기록된 집합을 준다)과
    밖(구간 **밖** 눈금은 다른 집합을 준다)을 다 걸어야 운다.
    """
    P = UBIQUITOUS_PROVENANCE
    if docs is None:
        docs, sig = ledger_docs()
    out = []

    if sig is not None and tuple(sig) != tuple(P["population_sig"]):
        out.append(("기저 모집단이 유도 시점과 다르다",
                    tuple(P["population_sig"]), tuple(sig)))
    if len(docs) != P["n"]:
        out.append(("기저 문서 수(분모)가 다르다", P["n"], len(docs)))

    got = derive_ubiquitous(docs, P["tau"])
    if got != tuple(P["derived"]):
        out.append((f"DF >= {P['tau']}에서 유도되는 집합이 다르다",
                    tuple(P["derived"]), got))
    # 🔴 유도값과 **현행값**이 갈리는 것이 이 대조의 요점이다 — 이력만 맞고 상수가
    #   딴 값이면 그 이력은 «누군가 예전에 잰 것»이지 이 값의 근거가 아니다.
    if tuple(P["derived"]) != tuple(sorted(UBIQUITOUS)):
        out.append(("유도값과 현행 `UBIQUITOUS`가 다르다",
                    tuple(P["derived"]), tuple(sorted(UBIQUITOUS))))

    lo, hi = P["band"]
    band = stable_band(docs, P["derived"])
    if band is None:
        out.append(("어떤 tau에서도 기록된 집합이 나오지 않는다", (lo, hi), None))
    elif abs(band[0] - lo) > 1e-9 or abs(band[1] - hi) > 1e-9:
        out.append(("구간이 움직였다", (lo, hi), band))
    if not lo < P["tau"] <= hi:
        out.append(("고른 tau가 기록된 구간 밖이다", (lo, hi), P["tau"]))
    # 안 — 구간 안쪽 두 눈금에서 기록된 집합이 나오는가
    for tau in (P["tau"], hi):
        if derive_ubiquitous(docs, tau) != tuple(P["derived"]):
            out.append((f"구간 **안** tau={tau}에서 기록된 집합이 안 나온다",
                        tuple(P["derived"]), derive_ubiquitous(docs, tau)))
    # 밖 — 구간 밖에서는 **달라야** 한다. 이쪽이 없으면 «전부 통과»도 통과한다.
    for tau, where in ((lo, "하한"), (hi + 1e-9, "상한 위")):
        if derive_ubiquitous(docs, tau) == tuple(P["derived"]):
            out.append((f"구간 **밖**({where} tau={tau:.6f})에서도 같은 집합이"
                        " 나온다 — 구간이 경계가 아니다",
                        tuple(P["derived"]), "같다"))
    return out
