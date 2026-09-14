# -*- coding: utf-8 -*-
"""
test_scoring.py — 생존 채점을 **대장 실물 항목**으로 고정한다. (단계 0-b)

## 왜 합성 문자열을 쓰지 않는가

처음엔 `survived_v2('지우는 …', ['지우가 이직했다'])` → `[]` 한 줄로 잡으려 했다.
그런데 `'지우가 이직했다'`는 **대장에 없는 문자열**이라, 채점기가 실제로 만나는
항목을 하나도 대표하지 않는다. 통과해도 회귀를 못 잡는다.

그래서 `summary_local.load()`가 주는 **S01~S12 구간 11개 실물 항목**으로 고정한다.
`ITEMS`를 하드코딩하지 않는 것도 같은 이유다 — **대장이 바뀌면 이 테스트가 깨져야 한다.**
(A8 "대장·질문 수정 금지"의 위반 탐지기 역할을 겸한다.)
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "prototype"))
import yaml                                               # noqa: E402
import scoring                                            # noqa: E402
from scoring import (survived_frozen, survived_v2,        # noqa: E402
                     survived_v3)
import summary_local                                      # noqa: E402

PROBE = "지우는 요즘 고민이 있음. 회사 일이 크게 늘었다."
ITEMS = summary_local.load()[1]        # load()는 2-튜플 (sess, items)


def ledger_events():
    """대장 사건. **읽기만** 한다 (A8)."""
    with open(os.path.join(ROOT, "eval", "fact-ledger.yaml"),
              encoding="utf-8") as f:
        return {e["id"]: e["text"] for e in yaml.safe_load(f)["events"]}


def s2_summaries():
    with open(os.path.join(HERE, "data", "SUMMARY_S2.json"), encoding="utf-8") as f:
        return json.load(f)["summaries"]


class TestScoring(unittest.TestCase):
    """
    고정된 세 항목. 셋 다 **요약이 실제로 담고 있지 않은데** 옛 구현은 생존으로 셌다.

    | 항목 | frozen | 겹친 어근 / 비율 | v2 |
    |---|---|---|---|
    | `지우는 마케팅 회사 대리` | 생존(위양성) | `{지우, 회사}` 2/4 | 비생존 (`회사` 1/3) |
    | `지우에게 여동생이 한 명 있음` | 생존(위양성) | `{있, 지우}` 2/3 | **판정 불가** — 어근이 `{여동생}` 하나 |
    | `지우가 회사에서 크게 깨지고 새벽에 연락함` | 생존(위양성) | `{지우, 크, 회사}` 3/6 | 비생존 (`회사` 1/3) |
    """

    def test_ledger_span_unchanged(self):
        # 분모가 움직이면 아래 세 단언의 뜻이 달라진다. 먼저 잠근다.
        self.assertEqual(len(ITEMS), 11)

    def test_frozen_reproduces_three_false_positives(self):
        assert len(survived_frozen(PROBE, ITEMS)) == 3        # 옛 구현의 위양성 3건을 그대로 재현

    def test_v2_drops_all_three(self):
        res = survived_v2(PROBE, ITEMS)
        assert res.survived == []                              # v2에서 위양성 0

    def test_v2_reports_unscorable(self):
        res = survived_v2(PROBE, ITEMS)
        assert res.unscorable == ['지우에게 여동생이 한 명 있음']   # 판정 불가 1건이 **조용히 0이 되지 않는다**

    def test_v3_does_not_disturb_this_probe(self):
        """서수가 **한쪽에도 없는** 자리에서 v3은 v2와 글자 그대로 같다."""
        a, b = survived_v2(PROBE, ITEMS), survived_v3(PROBE, ITEMS)
        assert (a.survived, a.unscorable) == (b.survived, b.unscorable)


class TestFrozenScorersAreFrozen(unittest.TestCase):
    """
    🔴 **`survived_frozen`과 `survived_v2`의 원문을 sha256으로 못 박는다.**

    왜 시험으로 만드나 — 이 저장소에서 «얼렸다»의 유일한 근거는 **`git diff`에
    헝크가 없다**였다. 그런데 `experiments/scoring.py`는 **커밋된 적이 없다**
    (`git ls-tree HEAD`에 없다). 즉 그 감사는 이 파일에 대해 **아무것도 안 본다.**
    서수 라운드가 그것을 알아챘고, 그래서 다음 라운드가 쓸 기계적 대조를 여기 남긴다.

    ⚠️ 이 해시는 **서수 라운드 시점의 원문**이다. 주석 한 글자만 고쳐도 빨개진다 —
    그것이 요점이다. 값을 갱신하려면 «왜 얼린 것을 고치는가»를 먼저 적어야 한다.
    아래 `test_frozen_reproduces_three_false_positives`가 **행동** 쪽 짝이다.
    """

    FROZEN = {
        "survived_frozen":
            "f95b6e8595af7c3e5f26ad7e5c47be2d"
            "4974825128ed50715c915c6158bfa32f",
        "survived_v2":
            "9ebad832222fbc27b508cdcff7e9b35f"
            "3e22c03984fd755853173f4f76f0ea42",
    }

    def test_source_hashes(self):
        import hashlib
        import inspect
        for name, want in self.FROZEN.items():
            src = inspect.getsource(getattr(scoring, name))
            got = hashlib.sha256(src.encode("utf-8")).hexdigest()
            self.assertEqual(got, want, f"`{name}`의 원문이 움직였다 — 얼린 것이다")


# ── 🔴 위 해시의 구멍, 그리고 그것을 닫는 것 ──────────────────────────────────
#
# `inspect.getsource(함수)`가 못 박는 것은 **그 함수의 원문**이다. 그런데 두
# 동결 함수가 실제로 하는 일은 원문 밖에도 있다:
#
#   survived_v2 → `_clean_roots`(다른 함수) → `UBIQUITOUS`(모듈 전역)
#               → `MIN_ROOTS`(모듈 전역) · `V2Result`(클래스)
#   둘 다      → `Memory._roots` → `_stem` → `_ENDINGS` · `Memory._PARTICLE`
#              (전부 `prototype/memory.py`, 즉 **다른 파일**)
#
# 실험 30이 이것을 심어서 확인했다: `scoring.UBIQUITOUS = set()`으로 갈면
# `test_source_hashes`는 **초록인 채** `survived_v2`가 옛 위양성 3건을 그대로
# 되살린다(`test_v2_drops_all_three`가 빨개진다). 즉 **얼어 있던 것은 함수
# 원문이고, 그 함수가 읽는 것은 안 얼어 있었다.**
#
# 아래는 그 구멍을 닫는다 — **손으로 적은 목록이 아니라 도달 가능성으로** 전개한다.
# 목록을 손으로 유지하면 다음에 전역을 하나 더 읽을 때 그 자리가 조용히 새고,
# 그것이 이 저장소의 열두 번째 «발화할 수 없는 검사»가 되는 방식이다.


def _freeze_text(name, obj):
    """얼릴 원문 한 조각.

    🔴 집합은 **정렬해서** 찍는다. `repr(set)`의 순서는 `PYTHONHASHSEED`의
    함수라 실행마다 갈리고, 그러면 해시가 «내용이 바뀌었다»가 아니라
    «오늘 운이 나빴다»로 빨개진다 — 그런 검사는 곧 꺼진다.
    """
    import inspect
    import re as _re
    if inspect.isroutine(obj) or inspect.isclass(obj):
        return inspect.getsource(obj)
    if isinstance(obj, _re.Pattern):
        return f"{name} = re.compile({obj.pattern!r})"
    if isinstance(obj, (set, frozenset)):
        return f"{name} = {sorted(obj)!r}"
    return f"{name} = {obj!r}"


def frozen_closure(root_name):
    """`scoring.<root_name>`이 **실제로 읽는** 것을 전개한다.

    함수의 `co_names`(전역으로 조회되는 이름)를 따라간다:
      · 그 함수의 모듈 전역에 있으면 → 상수든 함수든 얼린다
      · 없으면 → 이 호출 경로에서 쓰인 **클래스의 속성**인지 본다
        (`cls._PARTICLE`처럼 classmethod가 자기 클래스에서 읽는 것)
      · 표준 모듈(`re`·`os`)은 우리 것이 아니므로 지나친다

    반환: {정규화된 이름: 원문}. 이름 자체가 «경계가 어디까지인가»의 기록이다.
    """
    import inspect
    parts, seen = {}, set()

    def visit(qual, obj, owner):
        if qual in seen:
            return
        seen.add(qual)
        parts[qual] = _freeze_text(qual, obj)
        fn = obj.__func__ if inspect.ismethod(obj) else obj
        if not inspect.isfunction(fn):
            return
        g, names = fn.__globals__, fn.__code__.co_names
        owners = ([owner] if owner is not None else []) + [
            g[n] for n in names if inspect.isclass(g.get(n))]
        for n in names:
            if n in g:
                o = g[n]
                if inspect.ismodule(o):
                    continue
                if inspect.isclass(o):
                    # 클래스는 **쓰인 속성**으로 들어온다. 속성을 하나도 안 쓰면
                    # (생성자 호출뿐이면) 그 클래스 원문 자체가 동작의 일부다.
                    if not any(m in vars(o) for m in names):
                        visit(f"{o.__module__}.{o.__name__}", o, None)
                    continue
                visit(f"{fn.__module__}.{n}", o, None)
            else:
                for c in owners:
                    if n in vars(c):
                        visit(f"{c.__module__}.{c.__name__}.{n}",
                              getattr(c, n), c)
                        break

    visit(f"scoring.{root_name}", getattr(scoring, root_name), None)
    return parts


class TestFrozenClosureIsFrozen(unittest.TestCase):
    """
    🆕 🔴 **함수 원문이 아니라 «그 함수가 읽는 것 전부»를 못 박는다.**

    `TestFrozenScorersAreFrozen`은 계속 남긴다 — 둘은 **다른 자리를 본다.**
    함수 원문 해시가 빨개지면 «동결 함수를 직접 고쳤다»이고, 아래 닫힌 해시만
    빨개지면 «함수는 그대로인데 그 함수가 읽는 상수/도우미/다른 파일이
    움직였다»이다. 한 검사로 합치면 그 구별이 사라진다.

    ⚠️ 이 경계는 `prototype/memory.py`까지 간다(`_roots`·`_stem`·`_ENDINGS`·
    `_PARTICLE`). **그것이 의도다** — 그 넷 중 하나가 움직이면 실험 19/20의
    기록값은 재현되지 않는다. 실험 30이 `len(w) < 2`가 49종 594회를 버린다고
    적었고 그것을 고치자는 논의가 열려 있는데, 고치는 순간 **이 검사가 먼저
    울어야 한다.** 조용히 고쳐지면 옛 표가 조용히 거짓이 된다.
    """

    CLOSURE = {
        "survived_frozen":
            "e188ee9caa34f59b1e272dab8f661987"
            "1497f3ea711720c7243d9f42659c2628",
        "survived_v2":
            "6a03b9001355ca3d812b77cfbc27f7da"
            "8e366e6a8657c84cd58a099559e6237f",
    }

    # 🔴 경계를 **이름으로도** 적는다. 해시 하나만 두면 walker가 고장 나
    # «뿌리 하나»만 돌려줘도 해시는 그냥 다른 값이 되고, 그때 사람이 할 일은
    # «값을 갱신»이다 — 구멍이 그렇게 다시 열린다.
    REACH = {
        "survived_frozen": {
            "scoring.survived_frozen",
            "memory.Memory._roots", "memory.Memory._PARTICLE",
            "memory._stem", "memory._ENDINGS",
        },
        "survived_v2": {
            "scoring.survived_v2", "scoring._clean_roots",
            "scoring.UBIQUITOUS", "scoring.MIN_ROOTS", "scoring.V2Result",
            "memory.Memory._roots", "memory.Memory._PARTICLE",
            "memory._stem", "memory._ENDINGS",
        },
    }

    @staticmethod
    def blob(root):
        p = frozen_closure(root)
        return "\n".join(f"### {k}\n{p[k]}" for k in sorted(p))

    def test_closure_hashes(self):
        import hashlib
        for name, want in self.CLOSURE.items():
            got = hashlib.sha256(self.blob(name).encode("utf-8")).hexdigest()
            self.assertEqual(
                got, want,
                f"`{name}`가 읽는 것 중 무엇인가 움직였다 — 닿는 이름: "
                f"{sorted(frozen_closure(name))}")

    def test_the_reach_is_what_we_wrote_down(self):
        """walker가 닿는 곳이 위에 적은 경계와 **글자 그대로** 같은가."""
        for name, want in self.REACH.items():
            self.assertEqual(set(frozen_closure(name)), want)

    def test_the_leaked_constant_is_inside_the_closure(self):
        """🔴 실험 30이 심어서 확인한 그 구멍 — `UBIQUITOUS`가 해시 안에 있는가."""
        self.assertIn("scoring.UBIQUITOUS", frozen_closure("survived_v2"))
        self.assertIn("지우", self.blob("survived_v2"))

    def test_a_set_is_frozen_by_content_not_by_iteration_order(self):
        """조용한 쪽 — 같은 내용이면 두 번 불러도 같은 원문이다 (해시 seed 무관)."""
        self.assertEqual(self.blob("survived_v2"), self.blob("survived_v2"))
        self.assertEqual(_freeze_text("x", {"나", "가", "다"}),
                         _freeze_text("x", {"다", "가", "나"}))

    def test_what_v2_does_not_read_stays_outside(self):
        """조용한 쪽 대조 — `_ORDINALS`는 v3만 읽는다. 닫혔다고 **전부**를
        해시에 넣으면 그 검사는 «무엇을 고쳐도 빨간 검사»가 된다."""
        self.assertNotIn("scoring._ORDINALS", frozen_closure("survived_v2"))
        self.assertNotIn("scoring.survived_v3", frozen_closure("survived_v2"))


class TestOrdinalRepair(unittest.TestCase):
    """
    🆕 회차(서수) 불일치 — `survived_v3`.

    합성 문자열을 안 쓰는 이유는 이 파일 머리말과 같다. **대장 사건**과
    `SUMMARY_S2.json`의 **실물 요약**으로만 고정한다.
    """

    @classmethod
    def setUpClass(cls):
        cls.ev, cls.su = ledger_events(), s2_summaries()

    def v(self, fn, eid, sid):
        return bool(fn(self.su[sid], [self.ev[eid]]).survived)

    def test_ordinal_head_binding(self):
        """`세 번째 면접` → 머리 둘에 같은 서수. `세 차례`와 갈린다."""
        h = scoring._ordinal_heads(self.ev["E006"])
        self.assertEqual({k: sorted(x) for k, x in h.items()},
                         {"번째": ["세"], "면접": ["세"]})
        self.assertNotIn("차례", h)

    def test_markdown_list_numbers_are_not_ordinals(self):
        """`1. 사용자는 …`의 `1.`은 글머리다 — 가짜 머리를 만들면 안 된다."""
        self.assertEqual(scoring._ordinal_heads("1. 사용자는 두 번째 면접을"),
                         {"번째": {"두"}, "면접": {"두"}})

    def test_v3_kills_the_wrong_round(self):
        """회차가 어긋난 셋 — 겹침이 100%여도 비생존."""
        for eid, sid in (("E004", "S16"), ("E005", "S18"), ("E006", "S16")):
            self.assertTrue(self.v(survived_v2, eid, sid), f"{eid}×{sid} v2")
            self.assertFalse(self.v(survived_v3, eid, sid), f"{eid}×{sid} v3")

    def test_v3_keeps_the_matching_round(self):
        """🔴 **같은 회차는 안 죽인다.** 이것이 없으면 위 시험은 «전부 죽여라»도 통과시킨다."""
        for eid, sid in (("E004", "S14"), ("E005", "S16"), ("E006", "S18")):
            self.assertTrue(self.v(survived_v3, eid, sid), f"{eid}×{sid}")

    def test_v3_is_contained_in_v2_over_the_whole_population(self):
        """
        🔴 **분모가 안 갈라진다.** 240쌍 전부에서 `v3.survived ⊆ v2.survived`이고
        `unscorable`이 **같다.** v3은 뺄 수만 있고 더할 수 없다.
        """
        moved = []
        for eid in sorted(self.ev):
            for sid in sorted(self.su):
                a = survived_v2(self.su[sid], [self.ev[eid]])
                b = survived_v3(self.su[sid], [self.ev[eid]])
                self.assertEqual(a.unscorable, b.unscorable, f"{eid}×{sid}")
                self.assertLessEqual(len(b.survived), len(a.survived))
                if bool(a.survived) != bool(b.survived):
                    moved.append((eid, sid))
        # 🔴 **셋만 고친 것이 아니다.** 라벨이 붙은 3쌍 + 안 붙은 3쌍 = 6쌍이 움직인다.
        self.assertEqual(moved, [("E004", "S16"), ("E004", "S18"),
                                 ("E005", "S14"), ("E005", "S18"),
                                 ("E006", "S14"), ("E006", "S16")])


class TestOrdinalMutants(unittest.TestCase):
    """
    🔴 **심을 위반 둘.** «새 규칙은 위반을 심어 발화를 확인한 뒤에만 보고한다.»
    이 저장소에서 그 약속이 **열 번** 깨졌다.

    ① 예외를 지우면 → 옛 위양성이 **돌아온다**
    ② 회차가 **같을 때도** 죽이면 → **오발화**로 잡힌다 (반대 방향)
    """

    @classmethod
    def setUpClass(cls):
        cls.ev, cls.su = ledger_events(), s2_summaries()

    def survives(self, eid, sid):
        return bool(survived_v3(self.su[sid], [self.ev[eid]]).survived)

    def test_removing_the_exception_brings_the_false_positive_back(self):
        orig = scoring._ordinal_heads
        try:
            scoring._ordinal_heads = lambda text: {}
            back = [(e, s) for e, s in (("E004", "S16"), ("E005", "S18"),
                                        ("E006", "S16"))
                    if self.survives(e, s)]
        finally:
            scoring._ordinal_heads = orig
        self.assertEqual(len(back), 3, "예외를 지웠는데 위양성이 안 돌아왔다"
                                       " — 규칙이 그것을 고친 게 아니다")
        self.assertFalse(self.survives("E004", "S16"))   # 되돌려 놓았는가

    def test_firing_on_agreement_is_caught_as_a_misfire(self):
        """
        🔴 **오발화 대조.** «어긋나면»을 «있으면»으로 바꾼다 — 머리마다 서수에
        일련번호를 붙여 절대 안 겹치게 만들면 그것과 같은 규칙이 된다.
        그러면 **같은 회차를 말하는 쌍**이 죽는다.
        """
        orig = scoring._ordinal_heads
        seq = [0]

        def never_agree(text):
            seq[0] += 1
            return {h: {f"{o}#{seq[0]}" for o in o_}
                    for h, o_ in orig(text).items()}

        same = (("E004", "S14"), ("E005", "S16"), ("E006", "S18"))
        self.assertTrue(all(self.survives(e, s) for e, s in same))
        try:
            scoring._ordinal_heads = never_agree
            killed = [(e, s) for e, s in same if not self.survives(e, s)]
        finally:
            scoring._ordinal_heads = orig
        self.assertEqual(len(killed), 3,
                         "«서수가 있으면 죽인다» 변이가 조용히 지나갔다"
                         " — 이 대조는 발화하지 못한다")
        self.assertTrue(all(self.survives(e, s) for e, s in same))


if __name__ == "__main__":
    unittest.main()
