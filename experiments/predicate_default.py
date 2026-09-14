# -*- coding: utf-8 -*-
"""
predicate_default.py — **표 밖 술어의 기본값** 후보를 값으로 잰다. (LLM 0회 · `%TEMP%` DB · docs/17 밖E10)

## 왜

`predicate_vocab_cost.py`가 보인 것: 표를 25종으로 넓혀도 Δ 0 — 대장 술어가 코드 표와 docs/14 표 **모두**의 밖이다
(eval2 12/12종). 그래서 결정할 것은 표가 아니라 «세 표 어디에도 없는 술어를 어떤 기본값으로 둘 것인가»다.
`memory.py` 끝 절에 스위치 `UNKNOWN_PREDICATE_POLICY`를 넣었다 — **기본값 `"legacy"`는 오늘의 동작이다**(G16).
이 파일은 후보마다 무엇이 고쳐지고 무엇을 잃는지를 코퍼스 열마다 찍는다. **켤지는 제품 결정이다.**

## 무엇을 재나 — 정의는 새로 쓰지 않는다

- ⓐ 대장 «갱신» 쌍 중 병존 등(≠superseded)으로 끝남 · ⓑ 유효 사실 중 상시 블록에 안 실림 · ⓒ `superseded_by` 채워진 행 ·
  «대장이 무효화한 옛 값이 런타임에서 아직 유효» — 전부 **`predicate_vocab_cost.measure`를 그대로 부른다**(무변경).
  eval3 열은 그 함수의 로더(`load`)만 `eval3_probe.load`로 잠시 바꿔 끼운다(G13 — 객체 동일성으로 복원 확인).
- 잃는 것 — 이 파일이 따로 잰다(`measure`가 안 돌려주는 것): 대장상 유효한(무효화 표시 없는) 사실 중 런타임에서
  `valid_until`이 채워진 것 = **덮인 사실**. 덮은 쪽의 대장 주어가 같은가로 가른다 — ⚠️ `soak.ingest`는 모든 사실의 주어를
  «지우»로 넣으므로(그 하니스의 성질), 주어가 다른 두 사실이 한 술어를 공유하면 단일값 정책에서 서로를 덮는다.
  그래서 **«대장 주어 복원»** 변형(적재 중 `upsert_fact`의 주어 인자만 대장의 주어로 바꾼다 — 인스턴스 메서드 감싸기)을 함께 잰다.
  그 덮인 사실의 색인 복사본은 `_invalidate_derived`가 빼므로 **검색에서도 사라진다** → 근거를 잃은 문항 수를 센다.
- 상시 블록의 크기(줄 · `ntok`) · 함정 사실(대장 `tests`에 `misinjection`)이 상시 블록에 실린 수.
- 색인에 살아 있는 무효 사실 — `eval3_probe.stale_alive`를 그대로 부른다(전체 · CARD 밖).

## 후보 — 값 보기 전에 적었다 (PREREG)

`memory.UNKNOWN_PREDICATE_DEFAULTS`의 넷 + 이름 규칙 셋(호출 가능 정책 — **프로덕션 코드에 넣지 않는다**).
⚠️ eval2의 대장 술어는 Claude가 지었고 eval3 생성기도 Claude가 썼다 — 이름 규칙이 그 이름들에 맞춰지면 순환이다.
그래서 규칙마다 **유도한 곳을 한 군데로 적고, 나머지 열을 «확인»으로** 가른다. 유도한 열의 값은 증거가 아니라 적합도다.

## 실행 (G11)

    PYTHONIOENCODING=utf-8 python -B experiments/predicate_default.py
    PYTHONIOENCODING=utf-8 python -B experiments/predicate_default.py --corpora eval,eval2   # 빠른 두 열 (심은 위반 하니스용)
    PYTHONIOENCODING=utf-8 python -B -m unittest discover -s prototype/tests -p "test_predicate_policy.py" -v

종료 코드: G16(시작·끝 정책이 `"legacy"`) 또는 복원이 깨지면 1 · `legacy` 팔이 스위치 이전 기본값(L0)과 다르면 1 · 아니면 0.
"""
import os
import re
import shutil
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "eval3"))
sys.stdout.reconfigure(encoding="utf-8")

import memory as M                                              # noqa: E402
from memory import Memory                                       # noqa: E402
import soak                                                     # noqa: E402
import predicate_vocab_cost as PV                               # noqa: E402
import eval3_probe as E3P                                       # noqa: E402

W = 118
CW = 17


def known(p):
    """세 표 중 하나라도 있으면 «표 안» — `memory._unknown_pred`와 같은 경계."""
    return (p in Memory.PREDICATE_CARDINALITY or p in Memory.PREDICATE_MUTABILITY
            or p in Memory.PREDICATE_STANDING)


# ══════════════════════════════════════════════════════════════════════
# 이름 규칙 — 유도한 곳을 한 군데로. 규칙은 «카디널리티»만 정한다(가변성 mid · 상시성은 규칙마다 적음).
# ══════════════════════════════════════════════════════════════════════
# R-e3 — eval3 대장(세 레짐 공통 술어)에서 유도. 표 밖 16종 중 대장이 갱신 쌍을 준 6종(단일값) · 같은 주어에 유효 사실
#        ≥ 2인 7종(다중값)을 가르는 가장 짧은 접두·접미. `취미`는 이름으로 못 가른다 — 규칙에 이름을 **통째로 적지 않았다**
#        (적으면 그것은 규칙이 아니라 표 확장이고, 표 확장은 Δ 0이었다).
RE3_ONE_PREFIX = ("다니는_", "쓰는_")
RE3_ONE_SUFFIX = ("_기종", "_수단")
# R-e2 — eval2 대장에서 유도. 표 밖 12종 중 갱신 쌍이 있는 것은 `운영_버전` 하나 · 나머지 11종은 사실이 1행씩이라 가를 수 없다.
RE2_ONE_SUFFIX = ("_버전",)
# R-code — 코드 표 자신에서 유도. 표 안에서 **상시가 아닌** 유일한 술어가 `일상_사소`(many/high) → «`_사소`로 끝나면 상시 아님, 나머지는
#        상시». ⚠️ eval2의 `_사소` 셋(비품·요청·일정)도 같은 저자가 같은 모양으로 지었다 — **eval2 열은 확인이 아니다**(순환).
RCODE_TRIVIA_SUFFIX = ("_사소",)


def rule_e3(p):
    one = p.startswith(RE3_ONE_PREFIX) or p.endswith(RE3_ONE_SUFFIX)
    return ("one" if one else "many", "mid", False)


def rule_e2(p):
    return ("one" if p.endswith(RE2_ONE_SUFFIX) else "many", "mid", False)


def rule_code(p):
    trivia = p.endswith(RCODE_TRIVIA_SUFFIX)
    return ("many", "high" if trivia else "mid", not trivia)


POLICIES = [   # (이름, 정책 값, 유도한 열 — None이면 이름 규칙이 아니다)
    ("legacy (현행)", "legacy", None),
    ("one (모르면 단일값)", "one", None),
    ("standing (모르면 상시)", "standing", None),
    ("one+standing", "one+standing", None),
    ("R-e3 이름 규칙", rule_e3, "eval3"),
    ("R-e2 이름 규칙", rule_e2, "eval2"),
    ("R-code 상시·사소 예외", rule_code, "코드 표"),
]

PREREG = [
    ("G16", "시작·끝에 `UNKNOWN_PREDICATE_POLICY == \"legacy\"` · 매 팔 뒤 정책·로더가 **같은 객체**로 복원",
     "참 ⇔ 전부 그렇다", "거짓 → 종료 1"),
    ("L0 legacy = 스위치 없음", "legacy 팔의 `measure` 결과(동작·ⓐⓑⓒ·블록) == 표 밖 기본값을 스위치 이전 글자 그대로"
     "(`\"many\"`·`\"mid\"`·상시 아님) 꽂은 참조의 결과",
     "참 ⇔ 돈 열 전부 같다", "거짓 → 종료 1"),
    ("D 지배", "열·후보마다: ⓐ ≤ legacy · ⓑ ≤ legacy · 덮인 사실(하니스 그대로) = 0 · 함정 실림 = 0",
     "참 ⇔ 넷 다 → «이 열에서 legacy를 지배»", "거짓 ⇔ 하나라도 어긋남 → «대가 있음»(어느 것인지 찍는다)"),
    ("T 규칙 전이", "이름 규칙마다 «확인» 열(유도한 곳이 아닌 열)에서: ⓐ < legacy 이고 덮인 사실 = 0",
     "참 ⇔ 한 열이라도 → «옮겨 간다»", "거짓 ⇔ 없음 → «못 옮겨 간다»(확인 열에서 고친 것 0이거나 잃음)"),
]


def preregistration():
    print("\n사전 등록 — 조건 · 관측 · 참/거짓")
    for n, o, t, f in PREREG:
        print(f"  {n:<22} {o}\n  {'':<22}   {t}  |  {f}")
    print("  예측(판정 기준 아님): one은 eval2·eval3의 ⓐ를 고치고 eval3에서 다중값을 수백 건 덮는다 · standing은 ⓑ를 줄이고 eval2 함정을 싣는다.")


# ══════════════════════════════════════════════════════════════════════
# 한 열 × 한 정책
# ══════════════════════════════════════════════════════════════════════
class Bind:
    """정책 · `PV.load` · `soak.ingest` · `memory._unknown_pred`를 잠시 바꾼다 — 되돌렸는지 **객체**로 본다(G13)."""

    def __init__(self, policy=None, loader=None, ingest=None, unknown=None):
        self.new = dict(policy=policy, loader=loader, ingest=ingest, unknown=unknown)

    def __enter__(self):
        self.saved = (M.UNKNOWN_PREDICATE_POLICY, PV.load, soak.ingest, M._unknown_pred)
        if self.new["policy"] is not None:
            M.UNKNOWN_PREDICATE_POLICY = self.new["policy"]
        if self.new["loader"] is not None:
            PV.load = self.new["loader"]
        if self.new["ingest"] is not None:
            soak.ingest = self.new["ingest"]
        if self.new["unknown"] is not None:
            M._unknown_pred = self.new["unknown"]

    def __exit__(self, *a):
        M.UNKNOWN_PREDICATE_POLICY, PV.load, soak.ingest, M._unknown_pred = self.saved
        now = (M.UNKNOWN_PREDICATE_POLICY, PV.load, soak.ingest, M._unknown_pred)
        if any(x is not y for x, y in zip(now, self.saved)):
            raise SystemExit("🔴 복원 실패 — 종료 1")


def hardwired(m, predicate):
    """스위치 **이전**의 표 밖 기본값을 글자 그대로 — `.get(p, "many")` · `.get(p, "mid")` · 상시 표 소속만. L0의 참조."""
    return ("many", "mid", False)


_N = [0]


def analyze(m, name, restore_subject):
    """적재가 끝난 DB에서 덮인 사실 · 색인 무효 · 근거 잃은 문항."""
    _, ledger, qs = E3P.load(name)
    facts = ledger.get("facts", [])
    rows = [dict(r) for r in m.db.execute(
        "SELECT fact_id, subject, predicate, object, valid_until, superseded_by FROM fact WHERE chat_id=?",
        (soak.CHAT,))]
    alive = E3P.stale_alive(m, ledger)
    by_id = {r["fact_id"]: r for r in rows}
    subj_of = {}
    for f in facts:
        subj_of.setdefault((f.get("predicate", "일상_사소"), f.get("object", f["text"])), set()).add(
            f.get("subject", "지우"))
    lost, cross, held = [], 0, []
    for f in facts:
        if f.get("invalidated_at"):
            continue
        key = (f.get("predicate", "일상_사소"), f.get("object", f["text"]))
        mine = [r for r in rows if (r["predicate"], r["object"]) == key
                and (not restore_subject or r["subject"] == f.get("subject", "지우"))]
        if not mine:
            held.append(f["id"])
            continue
        if all(r["valid_until"] is not None for r in mine):
            lost.append(f["id"])
            gone = next((r for r in mine if r["superseded_by"] is not None), None)
            nxt = by_id.get(gone["superseded_by"]) if gone else None
            if nxt and f.get("subject", "지우") not in subj_of.get((nxt["predicate"], nxt["object"]), set()):
                cross += 1
    lost_set = set(lost)
    return dict(lost=lost, cross=cross, held=held, n_q=len(qs),
                q_lost=[x["id"] for x in qs if set(x.get("evidence") or []) & lost_set],
                sup=sum(r["superseded_by"] is not None for r in rows), alive=alive,
                n_valid=sum(1 for f in facts if not f.get("invalidated_at")),
                lost_by_pred=Counter(f["predicate"] for f in facts
                                     if f["id"] in lost_set and not known(f["predicate"])))


def pv_measure(name, policy, unknown=None):
    """
    `predicate_vocab_cost.measure`를 무변경으로 부른다 — eval3 열은 로더만 바꿔 끼운다.
    그 함수 안의 `soak.ingest` 직후 DB를 붙잡아 «하니스 그대로»의 잃음도 같은 적재에서 잰다(적재를 두 번 안 한다).
    """
    loader = None if name in ("eval", "eval2") else E3P.load
    orig, box = soak.ingest, {}

    def ingest(m, corpus, ledger, timed=True):
        out = orig(m, corpus, ledger, timed=timed)
        box["st"] = analyze(m, name, False)
        box["act"] = out[1]
        return out
    with Bind(policy, loader, ingest, unknown):
        pv = PV.measure(name, None)
    assert box["act"] is pv["act"]                      # 붙잡은 적재가 그 측정의 적재다
    return pv, box["st"]


def restored(name, policy, tmp):
    """«대장 주어 복원» — `upsert_fact`의 주어 인자만 대장의 주어로. 나머지는 `soak.seed` + `soak.ingest` 무변경."""
    corpus, ledger, _ = E3P.load(name)
    facts = ledger.get("facts", [])
    _N[0] += 1
    m = Memory(os.path.join(tmp, f"r{_N[0]}.db"))
    try:
        soak.seed(m)
        # 대장 순서대로 적재되므로 (술어, 값) → 주어 대기열의 앞을 꺼낸다 — 같은 (술어, 값)이 여러 주어에 있어도 순서가 맞는다.
        q = {}
        for f in facts:
            q.setdefault((f.get("predicate", "일상_사소"), f.get("object", f["text"])), []).append(
                f.get("subject", "지우"))
        orig = m.upsert_fact

        def upsert(chat_id, subject, predicate, obj, **kw):
            return orig(chat_id, q[(predicate, obj)].pop(0), predicate, obj, **kw)
        m.upsert_fact = upsert
        with Bind(policy):
            soak.ingest(m, corpus, ledger, timed=False)
            return analyze(m, name, True)
    finally:
        m.db.close()


def summarize(name, pv, st, st_r):
    facts = pv["facts"]
    kind = {f["id"]: known(f["predicate"]) for f in facts}
    a_co = sum(x[3] != "superseded" for x in pv["a"])
    b_miss = [fid for fid, _, ok in pv["b"] if not ok]
    trap = [f["id"] for f in facts if "misinjection" in (f.get("tests") or [])]
    shown = {fid for fid, _, ok in pv["b"] if ok}
    return dict(
        a=f"{a_co}/{len(pv['a'])}",
        a_n=a_co,
        b=f"{len(b_miss)}/{len(pv['b'])}",
        b_n=len(b_miss),
        b_split=f"안 {sum(kind[x] for x in b_miss)} · 밖 {sum(not kind[x] for x in b_miss)}",
        c=f"{pv['c']} (기대 {pv['c_expect']})",
        stale=len(pv["stale"]),
        klines=len(pv["klines"]),
        ktok=M.ntok("\n".join(pv["klines"])),
        trap=f"{sum(t in shown for t in trap)}/{len(trap)}",
        trap_n=sum(t in shown for t in trap),
        lost=f"{len(st['lost'])}/{st['n_valid']}",
        lost_n=len(st["lost"]),
        cross=st["cross"],
        lost_r=f"{len(st_r['lost'])}/{st_r['n_valid']}",
        lost_r_n=len(st_r["lost"]),
        held=len(st["held"]),
        held_r=len(st_r["held"]),
        gone=f"{len(st['lost']) + len(st['held'])} · {len(st_r['lost']) + len(st_r['held'])}",
        q_lost=f"{len(st['q_lost'])}/{st['n_q']}",
        q_lost_r=f"{len(st_r['q_lost'])}/{st_r['n_q']}",
        sup_r=st_r["sup"],
        alive=f"{st['alive'][0]}/{st['alive'][1]} · CARD 밖 {st['alive'][2]}/{st['alive'][3]}",
        alive_r=f"{st_r['alive'][0]}/{st_r['alive'][1]} · CARD 밖 {st_r['alive'][2]}/{st_r['alive'][3]}",
        top=", ".join(f"{p} {n}" for p, n in st["lost_by_pred"].most_common(4)) or "—",
    )


# ══════════════════════════════════════════════════════════════════════
# 출력
# ══════════════════════════════════════════════════════════════════════
ROWS = [
    ("a", "ⓐ 갱신 쌍 중 병존 등(≠superseded)"),
    ("b", "ⓑ 유효 사실 중 상시 블록에 안 실림"),
    ("b_split", "   └ 그중 표 안 · 세 표 밖"),
    ("c", "ⓒ superseded_by 채워진 행"),
    ("stale", "   대장 무효 옛 값이 런타임 유효(건)"),
    ("lost", "잃음: 유효 사실 중 덮임(하니스 그대로)"),
    ("cross", "   └ 그중 덮은 쪽 대장 주어가 다름"),
    ("q_lost", "   근거를 잃은 문항(하니스 그대로)"),
    ("lost_r", "잃음: 대장 주어 복원"),
    ("q_lost_r", "   근거를 잃은 문항(주어 복원)"),
    ("alive", "색인에 살아 있는 무효 사실(하니스)"),
    ("alive_r", "색인에 살아 있는 무효 사실(주어 복원)"),
    ("klines", "상시 블록 줄"),
    ("ktok", "상시 블록 ntok(≈1.5/글자)"),
    ("trap", "함정 사실 상시 실림"),
    ("held", "보류로 저장 안 된 유효 사실(하니스)"),
    ("held_r", "보류로 저장 안 된 유효 사실(주어 복원)"),
    ("gone", "잃음 합(덮임+보류) 하니스 · 주어 복원"),
]


def label_fit(names):
    """이름 규칙 유도의 재료 — 대장이 준 라벨(단일값 = 갱신 쌍 · 다중값 = 같은 주어 유효 ≥ 2)과 규칙의 일치."""
    print("\n" + "=" * W)
    print("이름 규칙의 재료 — 세 표 밖 술어 × 대장 라벨 (유도한 열은 적합도 · 나머지는 확인)")
    print("=" * W)
    for name in names:
        _, ledger, _ = E3P.load(name)
        facts = ledger.get("facts", [])
        unk = sorted({f["predicate"] for f in facts if not known(f["predicate"])})
        single = {f["predicate"] for f in facts if f.get("superseded_by")}
        grp = Counter((f.get("subject", "지우"), f["predicate"]) for f in facts if not f.get("invalidated_at"))
        multi = {p for (_, p), n in grp.items() if n >= 2}
        print(f"  {name:<18} 세 표 밖 {len(unk)}종 · 대장 라벨 단일 {len(single & set(unk))} · 다중 {len(multi & set(unk))} · "
              f"없음 {len(set(unk) - single - multi)}")
        for rn, fn, src in (("R-e3", rule_e3, "eval3"), ("R-e2", rule_e2, "eval2")):
            role = "유도(적합도)" if name.startswith(src) else "확인"
            s_hit = sum(fn(p)[0] == "one" for p in single & set(unk))
            m_bad = sum(fn(p)[0] == "one" for p in multi & set(unk))
            print(f"    {rn} [{role:<8}] 단일 라벨을 one으로 {s_hit}/{len(single & set(unk))} · 다중 라벨을 one으로(덮을 자리) "
                  f"{m_bad}/{len(multi & set(unk))} · 이 열에서 one이 되는 술어 {[p for p in unk if fn(p)[0] == 'one']}")


def main():
    t0 = time.perf_counter()
    names = E3P.NAMES
    if "--corpora" in sys.argv:
        pick = sys.argv[sys.argv.index("--corpora") + 1].split(",")
        names = [n for n in E3P.NAMES if n in pick]
    print("=" * W)
    print("표 밖 술어의 기본값 — 후보별 대가 (LLM 0회 · 임시 DB · 정의는 predicate_vocab_cost.measure 그대로)")
    print("=" * W)
    preregistration()
    g16 = [M.UNKNOWN_PREDICATE_POLICY == "legacy"]
    tmp = tempfile.mkdtemp(prefix="w8pred_")
    res, bad = {}, []
    try:
        for name in names:
            # L0 — 스위치 이전의 기본값을 글자 그대로 꽂은 참조(`hardwired`). 정책 값을 «legacy»로 두는 것과 비교하면
            #      동어반복이다(기본값 표를 잘못 고쳐도 둘이 같이 틀린다) — 그래서 표를 거치지 않는 참조와 댄다.
            base, _ = pv_measure(name, None, unknown=hardwired)
            for pname, pol, _ in POLICIES:
                pv, st = pv_measure(name, pol)
                if pname.startswith("legacy"):
                    same = (pv["act"] == base["act"] and pv["a"] == base["a"] and pv["b"] == base["b"]
                            and pv["c"] == base["c"] and pv["klines"] == base["klines"] and pv["stale"] == base["stale"])
                    if not same:
                        bad.append(f"L0 {name}")
                st_r = restored(name, pol, tmp)
                res[(name, pname)] = summarize(name, pv, st, st_r)
            print(f"  … {name} 끝 ({time.perf_counter() - t0:.0f} s)", flush=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    g16.append(M.UNKNOWN_PREDICATE_POLICY == "legacy")

    print("\n" + "=" * W)
    print("후보 × 코퍼스 열 — 열 사이에 화살표를 그리지 않는다(서로 다른 모집단 · eval3 셋은 한 생성기의 지수 하나 차이)")
    print("=" * W)
    for pname, pol, src in POLICIES:
        role = "" if src is None else f"  [유도: {src} — 그 열의 값은 적합도]"
        print(f"\n── {pname}{role}")
        print(f"  {'':<40}" + "".join(f"{n:>{CW}}" for n in names))
        for key, lab in ROWS:
            print(f"  {lab:<40}" + "".join(f"{str(res[(n, pname)][key]):>{CW}}" for n in names))
        tops = [(n, res[(n, pname)]["top"]) for n in names if res[(n, pname)]["top"] != "—"]
        for n, t in tops:
            print(f"  덮인 술어 상위(세 표 밖 · 하니스) {n}: {t}")

    print("\n" + "=" * W)
    print("D 지배 — 열·후보마다 (ⓐ ≤ legacy · ⓑ ≤ legacy · 잃음(하니스) = 0 · 함정 실림 = 0)")
    print("=" * W)
    print(f"  {'':<26}" + "".join(f"{n:>{CW + 6}}" for n in names))
    for pname, _, _ in POLICIES[1:]:
        cells = []
        for n in names:
            r, b = res[(n, pname)], res[(n, POLICIES[0][0])]
            why = [w for w, bad_ in (("ⓐ↑", r["a_n"] > b["a_n"]), ("ⓑ↑", r["b_n"] > b["b_n"]),
                                     ("잃음", r["lost_n"] > 0), ("함정", r["trap_n"] > 0)) if bad_]
            same = r["a_n"] == b["a_n"] and r["b_n"] == b["b_n"]
            cells.append("지배(같음)" if not why and same else ("지배" if not why else "대가:" + "·".join(why)))
        print(f"  {pname:<26}" + "".join(f"{c:>{CW + 6}}" for c in cells))

    print("\n" + "=" * W)
    print("T 규칙 전이 — 이름 규칙마다 «확인» 열에서 ⓐ < legacy 이고 잃음 = 0 인 열")
    print("=" * W)
    for pname, _, src in POLICIES:
        if src is None:
            continue
        chk = [n for n in names if not n.startswith(src)]
        good = [n for n in chk if res[(n, pname)]["a_n"] < res[(n, POLICIES[0][0])]["a_n"]
                and res[(n, pname)]["lost_n"] == 0]
        circ = " ⚠️ eval2 열은 같은 저자·같은 모양이라 확인이 아니다" if src == "코드 표" else ""
        print(f"  {pname:<22} 확인 열 {chk} → {'«옮겨 간다» ' + str(good) if good else '«못 옮겨 간다»'}{circ}")
    label_fit(names)

    print("\n  ⚠️ `soak.ingest`는 사실의 주어를 전부 «지우»로 넣는다 — «하니스 그대로» 줄은 그 성질을 안고 있다. «주어 복원»은")
    print("     `upsert_fact`의 주어 인자만 대장의 주어로 바꾼 것이고 나머지(색인 복사본 · 파생 등록)는 같다.")
    print("  ⚠️ ⓑ의 «안 실림»에는 설계상 상시가 아닌 술어(`일상_사소` 등)가 들어 있다 — «표 안 · 세 표 밖» 줄로 가른다.")
    print(f"  G16 시작·끝 {g16} · L0·동작 대조 어긋남 {bad or '0'}  (소요 {time.perf_counter() - t0:.0f} s)")
    if not all(g16) or bad:
        print("🔴 G16/L0 거짓 — 종료 1")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
