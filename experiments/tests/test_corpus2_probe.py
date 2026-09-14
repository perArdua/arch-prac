# -*- coding: utf-8 -*-
"""
test_corpus2_probe.py — `corpus2_probe.py`와 `eval2/gen_corpus2.py`의 시험.

## 🔴 이 시험이 지키는 규율

*"새로 쓰거나 고친 검증 명령은 **위반을 심어 발화를 확인한 뒤에만** 보고한다."*

그래서 각 검사마다 **두 짝**을 둔다:

    test_*_fires_on_violation   위반을 심으면 발화하는가
    test_*_silent_on_clean      **심지 않으면 조용한가** (조용한 쪽 대조)

한쪽만 있으면 «언제나 발화하는 검사»와 «언제나 조용한 검사»를 구별할 수 없다.
그 둘은 각각 쓸모없고, 그 사실이 이 저장소에서 열한 번 확인됐다.

실행:
    PYTHONIOENCODING=utf-8 python -B -m unittest discover -s experiments/tests \\
        -p "test_corpus2_probe.py" -v
"""
import copy
import io
import json
import os
import re
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "..", "prototype"))

import corpus2_probe as CP                                   # noqa: E402
import scoring as SC                                         # noqa: E402
from memory import Memory                                    # noqa: E402

ROOT = CP.ROOT
sys.path.insert(0, os.path.join(ROOT, "eval2"))
import gen_corpus2 as G2                                     # noqa: E402


def _data():
    if not hasattr(_data, "v"):
        _data.v = {n: CP.load(n) for n in CP.NAMES}
    return copy.deepcopy(_data.v)


# ══════════════════════════════════════════════════════════════════════
# 1. 축 ① — 이름이 정말 갈렸는가
# ══════════════════════════════════════════════════════════════════════

class Axis1(unittest.TestCase):

    def test_silent_on_clean(self):
        """조용한 쪽 — 실제 eval2에는 금지 이름이 없으므로 통과하고 0을 돌려준다."""
        hits = CP.axis1_check(_data())
        self.assertEqual(hits, {"지우": 0, "서준": 0})

    def test_fires_on_violation(self):
        """위반 — 턴 하나에 `지우`를 심으면 검사가 죽어야 한다."""
        d = _data()
        d["eval2"][0][0]["text"] = "지우님 일정 공유 부탁드립니다"
        with self.assertRaises(AssertionError) as cm:
            CP.axis1_check(d)
        self.assertIn("축 ① 위반", str(cm.exception))

    def test_fires_on_violation_in_ledger(self):
        """위반 — 코퍼스가 아니라 **대장**에 심어도 잡아야 한다 (경로가 둘이다)."""
        d = _data()
        d["eval2"][1]["facts"][0]["text"] = "서준님 소속은 플랫폼개발팀입니다"
        with self.assertRaises(AssertionError):
            CP.axis1_check(d)


# ══════════════════════════════════════════════════════════════════════
# 2. 스키마 동일성 — «같게 둔 것»이 정말 같은가
# ══════════════════════════════════════════════════════════════════════

class SchemaSameness(unittest.TestCase):

    def test_silent_on_clean(self):
        """조용한 쪽 — 두 코퍼스의 JSONL 키 집합과 `role` 값역이 같다."""
        a, b = _data()["eval"][0], _data()["eval2"][0]
        self.assertEqual({tuple(sorted(r)) for r in a},
                         {tuple(sorted(r)) for r in b})
        self.assertEqual({r["role"] for r in a}, {r["role"] for r in b})

    def test_fires_on_violation(self):
        """위반 — 키를 하나 바꾸면 같지 않다고 나와야 한다."""
        b = _data()["eval2"][0]
        b[0]["speaker"] = b[0].pop("role")
        a = _data()["eval"][0]
        self.assertNotEqual({tuple(sorted(r)) for r in a},
                            {tuple(sorted(r)) for r in b})


# ══════════════════════════════════════════════════════════════════════
# 3. G13 — `scoring.UBIQUITOUS` 재바인딩이 되돌아오는가
# ══════════════════════════════════════════════════════════════════════

class RebindRestore(unittest.TestCase):

    def test_silent_on_clean(self):
        """조용한 쪽 — 정상 경로에서 전역이 원래 객체 그대로 돌아온다."""
        saved = SC.UBIQUITOUS
        c, l, _ = _data()["eval2"]
        CP.rescore_with(l, {"결제"}, digs=CP.digests(c, l))
        self.assertIs(SC.UBIQUITOUS, saved)

    def test_fires_on_violation(self):
        """
        위반 — 채점 도중 터져도 `finally`가 되돌려야 한다.

        되돌리지 않으면 **뒤에 오는 모든 채점이 조용히 다른 상수로 돈다.**
        그것이 실험 26이 «모양만 같고 다른 집합»이라 부른 실패 모드다.
        """
        saved = SC.UBIQUITOUS
        c, l, _ = _data()["eval2"]
        dg = CP.digests(c, l)
        real = CP.score_all

        def boom(*a, **k):
            raise RuntimeError("심은 위반")
        CP.score_all = boom
        try:
            with self.assertRaises(RuntimeError):
                CP.rescore_with(l, {"결제"}, digs=dg)
        finally:
            CP.score_all = real
        self.assertIs(SC.UBIQUITOUS, saved)


# ══════════════════════════════════════════════════════════════════════
# 4. 편재 어근 유도
# ══════════════════════════════════════════════════════════════════════

class Induce(unittest.TestCase):

    def test_silent_on_clean(self):
        """
        조용한 쪽 — eval에서는 `지우`가 유도되고, eval2에서는 **아무것도** 안 나온다.
        문턱은 eval의 `지우` df 비율이다 (프로브 2절과 같은 규칙).
        """
        _, rank, _ = CP.induce_ubiquitous(_data()["eval"][1], min_frac=0.0,
                                          top=999)
        jw = dict((r, f) for r, _c, f in rank)["지우"]
        _, _, ind_a = CP.induce_ubiquitous(_data()["eval"][1], min_frac=jw)
        _, _, ind_b = CP.induce_ubiquitous(_data()["eval2"][1], min_frac=jw)
        self.assertEqual(ind_a, {"지우"})
        self.assertEqual(ind_b, set())

    def test_fires_on_violation(self):
        """
        위반 — eval2 항목 전부에 한 이름을 박으면 그 이름이 유도돼야 한다.
        (유도기가 «언제나 공집합»을 돌려주는 항등 함수가 아님을 보인다.)
        """
        led = _data()["eval2"][1]
        for f in led["facts"]:
            f["text"] = "하람님 " + f["text"]
        for e in led["events"]:
            e["text"] = "하람님 " + e["text"]
        _, _, ind = CP.induce_ubiquitous(led, min_frac=0.545)
        self.assertIn("하람님", ind)


class InduceTieOrder(unittest.TestCase):
    """
    🔄 wave2 · T3 — 「어근 df 상위」가 **`PYTHONHASHSEED`의 함수가 아닌가.**

    `df`는 **집합**을 돌며 채워진다(`Memory._roots`). 그래서 동점의 삽입 순서가
    해시 seed에 매이고, `most_common()`은 그 순서를 그대로 칸에 옮긴다. eval2의
    df=3은 7종 공동인데 칸은 5개라 **여섯째 줄의 정체**가 실행마다 갈렸다.

    ⚠️ 한 프로세스 안에서는 seed를 못 바꾼다 — 그래서 시끄러운 쪽은 **서로 다른
       seed의 자식 프로세스 셋**을 띄워 출력을 맞댄다. seed 값을 고정했으므로 이
       시험의 발화 여부 자체는 결정적이다(착수 전 실측: seed 0·1·2가 셋 다 달랐다).
    """

    SEEDS = ("0", "1", "2")
    SNIPPET = ("import sys; sys.path.insert(0, {here!r}); "
               "import corpus2_probe as CP; "
               "print(CP.induce_ubiquitous(CP.load('eval2')[1], 0.0)[1])")

    def _run(self, seed):
        import subprocess
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONIOENCODING="utf-8",
                   PYTHONDONTWRITEBYTECODE="1")
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        r = subprocess.run([sys.executable, "-B", "-c",
                            self.SNIPPET.format(here=here)],
                           capture_output=True, text=True, encoding="utf-8",
                           env=env, cwd=ROOT)
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        return r.stdout.strip().splitlines()[-1]

    def test_fires_on_violation(self):
        """
        **심을 위반:** `sorted(df.items(), key=…)`를 옛 `df.most_common(top)`으로
        되돌리면 세 seed의 출력이 갈라져 발화한다.
        """
        outs = {s: self._run(s) for s in self.SEEDS}
        self.assertEqual(len(set(outs.values())), 1,
                         "seed마다 순위가 다르다 — 동점 순서가 해시에 매였다:\n"
                         + "\n".join(f"  {s}: {o}" for s, o in outs.items()))

    def test_silent_on_clean(self):
        """조용한 쪽 — 이 프로세스의 순위는 `(-df, 어근)` 순서 그대로다."""
        _, ranked, _ = CP.induce_ubiquitous(_data()["eval2"][1], 0.0)
        self.assertEqual(ranked, sorted(ranked, key=lambda x: (-x[1], x[0])))

    def test_the_cut_inside_a_tie_is_named(self):
        """
        칸 수는 표의 모양이지 모집단의 경계가 아니다. eval2는 df=3이 7종인데 칸에
        5종만 들어가므로 **밀린 둘을 이름으로** 돌려줘야 한다. eval은 df=3이 4종이고
        전부 칸 안이라 빈 목록이 조용한 쪽이다.
        """
        d = _data()
        _, r2, _ = CP.induce_ubiquitous(d["eval2"][1], 0.0)
        self.assertEqual(CP.tie_cut(d["eval2"][1], r2), (3, ["번째", "사내"]))
        _, r1, _ = CP.induce_ubiquitous(d["eval"][1], 0.0)
        self.assertEqual(CP.tie_cut(d["eval"][1], r1), (3, []))


# ══════════════════════════════════════════════════════════════════════
# 5. `_roots` 깨짐 탐지
# ══════════════════════════════════════════════════════════════════════

class Breakage(unittest.TestCase):

    def test_fires_on_real_examples(self):
        """
        위반(=실물 깨짐) — `됐습니다`·`갔습니다` 계열이 잔여어미로 잡혀야 한다.
        `_ENDINGS`의 첫 그룹은 뒤 그룹 없이 안 벗겨지므로 `됐`이 남는다.
        """
        self.assertEqual(CP.root_of("보류됐습니다"), "보류됐")
        self.assertEqual(CP.root_of("올라갔습니다"), "올라갔")
        self.assertNotEqual(CP.root_of("보류됐습니다"), CP.root_of("보류"))

    def test_silent_on_clean(self):
        """
        조용한 쪽 — `했습니다`는 `했`이 뒤 그룹에 있어 **깨지지 않는다.**
        탐지기가 «존댓말이면 무조건 깨졌다»고 말하는 것이 아님을 보인다.
        """
        self.assertEqual(CP.root_of("진행했습니다"), "진행")
        self.assertEqual(CP.root_of("체결했습니다"), "체결")

    def test_length1_drop_is_real(self):
        """서수 `첫`·`두`·`세`는 토큰 단계에서 버려진다 (scoring.py의 서술 확인)."""
        for w in ("첫", "두", "세"):
            self.assertIsNone(CP.root_of(w))
        self.assertEqual(CP.root_of("번째"), "번째")

    def test_nonhangul_roots_exist_only_in_eval2(self):
        """표기 축 — 비한글 어근은 eval2에만 있다."""
        _, _, _, nh_a = CP.breakage(*_data()["eval"])
        _, _, _, nh_b = CP.breakage(*_data()["eval2"])
        self.assertEqual(len(nh_a), 0)
        self.assertGreater(len(nh_b), 0)


# ══════════════════════════════════════════════════════════════════════
# 6. 세 채점기의 불변식
# ══════════════════════════════════════════════════════════════════════

class Scorers(unittest.TestCase):

    def _res(self, name):
        c, l, q = _data()[name]
        return CP.score_all(l, digs=CP.digests(c, l))

    def test_silent_on_clean(self):
        """
        조용한 쪽 — `scoring.py`가 **주장하는** 불변식은 두 코퍼스에서 참이다:
        `v3.survived ⊆ v2.survived` · `v3.unscorable == v2.unscorable`.
        """
        for n in CP.NAMES:
            sub, den = CP.invariants(self._res(n))
            self.assertTrue(sub, n)
            self.assertTrue(den, n)

    def test_frozen_ge_v2_is_not_an_invariant(self):
        """
        🔴 **주장되지 않은 것은 성립하지 않는다.** `frozen ≥ v2`는 코드가 보장하지
        않고, eval에서는 두 방향이 4건씩 상쇄돼 우연히 같았을 뿐이다.
        eval2에서 그 상쇄가 안 일어난다 — 그것이 이 시험의 내용이다.
        """
        a, b = self._res("eval"), self._res("eval2")
        _, n_fo_a = CP.frozen_only_examples(a)
        _, n_vo_a = CP.v2_only_examples(a)
        self.assertEqual((n_fo_a, n_vo_a), (4, 4))       # eval: 상쇄
        _, n_fo_b = CP.frozen_only_examples(b)
        _, n_vo_b = CP.v2_only_examples(b)
        self.assertEqual((n_fo_b, n_vo_b), (0, 1))       # eval2: 상쇄 없음
        self.assertLess(b["frozen"], b["v2"])

    def test_digests_are_deterministic(self):
        """G11 — 같은 입력이 같은 다이제스트를 낸다."""
        c, l, _ = _data()["eval2"]
        self.assertEqual(CP.digests(c, l), CP.digests(c, l))


# ══════════════════════════════════════════════════════════════════════
# 7. 생성기 — 배치 못 한 항목이 조용히 사라지지 않는가
# ══════════════════════════════════════════════════════════════════════

class Generator(unittest.TestCase):

    def test_silent_on_clean(self):
        """조용한 쪽 — 실제 대장은 25개 전부 배치되고 터지지 않는다."""
        led = G2.load_ledger()
        turns = G2.generate(led)
        self.assertEqual(len(turns), 192)
        self.assertEqual(sum(1 for t in turns if t["planted_id"]), 25)

    def test_fires_on_violation(self):
        """
        위반 — 항목 셋을 마지막 세션 마지막 턴에 몰면 밀어낼 자리가 없다.
        조용히 사라지면 대장과 색인이 어긋난 채로 계측이 돈다.
        """
        led = G2.load_ledger()
        last = f"S{led['meta']['sessions']:02d}"
        for e in led["events"][:3]:
            e["at"] = {"session": last, "turn": G2.TURNS_PER_SESSION}
        with self.assertRaises(RuntimeError) as cm:
            G2.generate(led)
        self.assertIn("배치되지 못했다", str(cm.exception))

    def test_regenerates_byte_identical(self):
        """G11 — 디스크의 코퍼스가 지금 생성한 것과 같다 (결정적 생성)."""
        led = G2.load_ledger()
        turns = G2.generate(led)
        on_disk = [json.loads(l) for l in
                   open(os.path.join(ROOT, "eval2", "corpus", "corpus.jsonl"),
                        encoding="utf-8")]
        self.assertEqual(turns, on_disk)


# ══════════════════════════════════════════════════════════════════════
# 8. 🔴 보고 규약 — 두 코퍼스 사이에 화살표를 그리지 않는다
# ══════════════════════════════════════════════════════════════════════

class NoArrows(unittest.TestCase):
    """
    실험 27 `TitleRule`의 정신. 화살표는 «같은 것이 변했다»를 뜻하는데 여기서는
    모집단이 둘이다. 사람이 지키기로 한 규약은 사람이 깬다 — 기계가 본다.
    """
    ARROW = re.compile(r"(→|->|=>)")
    # 숫자→숫자. 단위 한 글자(`%`·`건`·`행`·`개`)를 사이에 허용한다 —
    # 지표는 맨 숫자로 안 적히고 `21.8% → 49.6%` 꼴로 적힌다.
    NUM_ARROW = re.compile(r"\d\s*[%건행개]?\s*(→|->|=>)\s*\d")

    @staticmethod
    def _names_both(line):
        """
        한 줄이 **두 코퍼스를 모두** 가리키는가.

        🔴 `"eval" in line`으로는 안 된다 — `"[eval2]"`가 그 검사를 통과해버려
           코퍼스 **하나**를 다루는 줄이 전부 위반으로 잡힌다(첫 판이 그랬다).
           `eval` 뒤에 `2`가 오지 않는 자리를 찾아야 «eval을 가리킨다»가 된다.
        """
        return bool(re.search(r"eval(?!2)", line)) and "eval2" in line

    @classmethod
    def setUpClass(cls):
        buf = io.StringIO()
        with redirect_stdout(buf):
            CP.main()
        cls.out = buf.getvalue()
        cls.lines = cls.out.splitlines()

    @staticmethod
    def _scoped_to_one(line):
        """한 코퍼스 **하나만** 가리키는 줄인가. 그런 줄은 코퍼스를 가로지를 수 없다."""
        return (bool(re.search(r"eval(?!2)", line)) != ("eval2" in line)
                and re.search(r"eval", line) is not None)

    def test_silent_on_clean(self):
        """
        조용한 쪽 — 실제 출력에 위반 줄이 하나도 없다.

        규칙 둘:
          A. 두 코퍼스를 **모두** 가리키는 줄에는 화살표가 없다.
          B. 숫자→숫자 화살표가 있는 줄은 **정확히 한 코퍼스만** 가리킨다.

        🔴 B가 «화살표 금지»가 아닌 이유: `#391 → 391` 같은 «어절 → 어근» 줄은
           한 코퍼스 **안의** 사상이고 금지 대상이 아니다. 첫 판은 그것까지 잡아서
           검사가 못 쓰게 됐다 — 그래서 그 줄들에 코퍼스 이름을 박고, 검사는
           «이름이 없는 채로 숫자를 잇는 화살표»만 잡는다.
        """
        bad_a = [l for l in self.lines
                 if self.ARROW.search(l) and self._names_both(l)]
        self.assertEqual(bad_a, [])
        bad_b = [l for l in self.lines
                 if self.NUM_ARROW.search(l) and not self._scoped_to_one(l)]
        self.assertEqual(bad_b, [])

    def test_fires_on_violation(self):
        """위반 — 두 규칙 각각에 걸리는 줄을 하나씩 심으면 검사가 잡는다."""
        v_a = "  게이트 eval 21.8% → eval2 49.6%"
        v_b = "  게이트 통과율 21.8% → 49.6%"          # 이름 없이 숫자를 잇는다
        planted = self.lines + [v_a, v_b]
        bad_a = [l for l in planted
                 if self.ARROW.search(l) and self._names_both(l)]
        self.assertEqual(bad_a, [v_a])
        bad_b = [l for l in planted
                 if self.NUM_ARROW.search(l) and not self._scoped_to_one(l)]
        # `v_a`는 화살표 뒤가 숫자가 아니라 이름이므로 B가 아니라 **A**가 잡는다.
        # 두 규칙이 같은 것을 두 번 잡지 않는다는 것도 여기서 확인된다.
        self.assertEqual(bad_b, [v_b])

    def test_every_two_column_table_names_both_corpora(self):
        """열 제목에 코퍼스 이름이 박혀 있는가 — 표가 이름 없이 서지 않는다."""
        heads = [l for l in self.lines if l.strip().startswith("---")]
        self.assertGreater(len(heads), 3)
        for i, l in enumerate(self.lines):
            if l.strip().startswith("---") and i:
                self.assertTrue("eval" in self.lines[i - 1]
                                and "eval2" in self.lines[i - 1],
                                f"표 제목에 코퍼스 이름이 없다: {self.lines[i-1]!r}")

    def test_report_declares_its_limits(self):
        """«말할 수 없는 것»이 출력에 실제로 찍히는가 (지우면 시험이 죽는다)."""
        for must in ("합성", "저자가 하나", "순환", "n이 작다", "밀도"):
            self.assertIn(must, self.out)


# ══════════════════════════════════════════════════════════════════════
# 9. A8 — `eval/`은 불변이다
# ══════════════════════════════════════════════════════════════════════

class EvalImmutable(unittest.TestCase):

    def test_probe_opens_eval_read_only(self):
        """
        프로브가 `eval/`을 **쓰기 모드로 여는 자리가 없다.**
        문자열 검사이므로 약한 증거다 — 강한 증거는 `git status --porcelain -- eval/`
        이고 그것은 수용 명령에 있다. 둘 다 둔다.
        """
        src = open(os.path.join(ROOT, "experiments", "corpus2_probe.py"),
                   encoding="utf-8").read()
        for m in re.finditer(r"open\(([^)]*)\)", src):
            arg = m.group(1)
            if "eval" in arg:
                self.assertNotIn('"w"', arg)
                self.assertNotIn("'w'", arg)
                self.assertNotIn('"a"', arg)

    def test_generator_writes_only_into_eval2(self):
        """생성기의 출력 경로가 `eval2/` 아래인가."""
        self.assertTrue(str(G2.OUT_DIR).replace("\\", "/").endswith(
            "eval2/corpus"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
