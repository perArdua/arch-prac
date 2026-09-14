# -*- coding: utf-8 -*-
"""
test_rel_dist.py — 등컷 규칙 `theta_at`의 **정의역과 규약**을 고정한다. (단계 2)

🔴 **`θ := +∞` 분기가 R2a에서 시험되는 유일한 곳이다.** 어휘 사다리는 `f=0.97`에서도
`θ=0.2000`으로 달성되고 `embed`는 연속분포라, **실측 경로에서는 이 분기를 밟지 않는다.**
밟지 않는 분기는 다음 사람이 지워도 아무 실험이 안 깨진다 — 그래서 시험이 있다.

⚠️ 이 시험은 ollama도 DB도 쓰지 않는다. 분포를 **손으로 만든다.**
"""
import contextlib
import io
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "..", "prototype"))
import rel_dist as R                                       # noqa: E402

ATOM = [0] * 91 + [0.1] * 9        # 0에 원자가 91%인 분포


class TestThetaAt(unittest.TestCase):

    def test_u5_achievable_f(self):
        """U5 — `f=0.91`은 달성 가능하다. `#{v<0.1}/100 = 0.91 ≥ 0.91`."""
        self.assertEqual(R.theta_at(ATOM, 0.91), 0.1)

    def test_u5b_unachievable_f_is_infinity_not_exception(self):
        """
        U5-b — `f=0.915`는 이 분포에서 **달성 불가능**하다.

        `#{v<0}/100 = 0.00` · `#{v<0.1}/100 = 0.91 < 0.915` — 조건을 만족하는
        관측값이 없다. 규약은 `+∞`이고 **`RuntimeError`가 아니다.**
        계획 rev1이 스스로 고른 시험 케이스가 규칙의 정의역 밖이었고, 그때의
        규약이 어디에도 적혀 있지 않았다.
        """
        self.assertEqual(R.theta_at(ATOM, 0.915), math.inf)

    def test_infinity_is_full_cut(self):
        """`θ = +∞`의 실제 컷은 100%다 — *"전량 컷"*이 그 뜻이다."""
        self.assertEqual(R.actual_cut(ATOM, R.theta_at(ATOM, 0.915)), 1.0)

    def test_domain_is_restricted_to_observed_values(self):
        """
        🔴 돌려주는 θ는 **언제나 관측값 중 하나**다 (또는 +∞).

        정의역 제한이 없으면 조건집합이 `(0, 0.1]` 꼴이라 `min`이 존재하지 않는
        경우가 생긴다. 여기서는 `0.1`이 관측값이라는 것이 그 제한의 결과다.
        """
        for f in (0.0, 0.5, 0.91):
            self.assertIn(R.theta_at(ATOM, f), set(ATOM))

    def test_f_zero_returns_smallest_observed_value(self):
        """`f=0`이면 아무것도 안 잘라도 되므로 최소 관측값이다 (`#{v<0} = 0 ≥ 0`)."""
        self.assertEqual(R.theta_at(ATOM, 0.0), 0)
        self.assertEqual(R.actual_cut(ATOM, 0), 0.0)

    def test_empty_population_is_infinity(self):
        """모집단이 비면 어떤 f도 달성할 수 없다 — 빈 분포에서 조용히 0을 주면 안 된다."""
        self.assertEqual(R.theta_at([], 0.5), math.inf)

    def test_actual_cut_is_recomputed_independently(self):
        """
        `actual_cut`은 `theta_at`의 내부 계산을 **재사용하지 않는다.**

        요청 `f`와 실제 컷이 같아야 할 이유가 없다는 것이 결정 D의 요점이고,
        같은 계산을 두 번 쓰면 그 차이가 구조적으로 안 보인다.
        """
        th = R.theta_at(ATOM, 0.5)              # → 0 (0%만 자르면 된다... 가 아니다)
        self.assertEqual(th, 0.1)               # #{v<0}=0 < 0.5 이므로 다음 눈금
        self.assertAlmostEqual(R.actual_cut(ATOM, th), 0.91)
        self.assertGreater(R.actual_cut(ATOM, th), 0.5)   # 요청 f를 **초과**한다

    def test_continuous_like_distribution_lands_close_to_f(self):
        """
        원자가 없으면 실제 컷이 요청 `f`에 가깝다 — 하지만 **정확히 같지는 않다.**
        정의역이 관측값이라 눈금이 유한하기 때문이다.
        """
        vals = [i / 1000 for i in range(1000)]
        th = R.theta_at(vals, 0.8)
        self.assertAlmostEqual(R.actual_cut(vals, th), 0.8, places=3)


class TestLadderOutput(unittest.TestCase):
    """
    U5-b의 나머지 절반 — **출력 규약**. `+∞`를 돌려주는 것만으로는 부족하고,
    사람이 읽는 줄에 `"전량 컷"`이 찍혀야 한다. 값이 `inf`인 표는 그냥 깨져 보인다.
    """

    def test_full_cut_is_printed(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rows = R.ladder_rows("원자 91% (시험용)", ATOM)
        out = buf.getvalue()
        self.assertIn("전량 컷", out)
        self.assertIn("+∞", out)
        # 사다리의 세 f 중 0.915·0.97이 달성 불가다 (원자 91%).
        self.assertEqual([th for _f, th, _c in rows],
                         [0.1, math.inf, math.inf])

    def test_requested_f_and_actual_cut_are_both_printed(self):
        """G15 rev2 — `요청 f`만 적으면 두 모드가 같은 실험을 한 것처럼 보인다."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            R.ladder_rows("원자 91% (시험용)", ATOM)
        head = next(l for l in buf.getvalue().splitlines() if "요청 f" in l)
        self.assertIn("실제 컷", head)          # 같은 줄에 나란히 있어야 한다


class TestQuantileConvention(unittest.TestCase):
    """
    분위수 규약을 못박는다 — `embed_vs_bigram.py`의 지역 `q_at`과 **같은 식**이다
    (`sorted(v)[min(n-1, int(n*p/100))]`). 규약이 갈리면 두 파일의 `p95`가
    다른 뜻이 되고, 그 차이는 값만 봐서는 안 보인다.
    """

    def test_index_formula(self):
        vals = [i / 100 for i in range(100)]
        for p in (25, 50, 75, 90, 95):
            self.assertEqual(R.q_at(vals, p),
                             sorted(vals)[min(len(vals) - 1,
                                              int(len(vals) * p / 100))])

    def test_p100_does_not_overflow(self):
        self.assertEqual(R.q_at([1, 2, 3], 100), 3)


class TestCosDim(unittest.TestCase):
    """
    `cos`의 **차원 규약**은 `memory._cosine`의 것이다 (w11b · docs/17 축-2의 딸린 🔓).

    `zip`은 짧은 쪽에서 **조용히** 끊는다 — 옛 `cos([1,0,0], [1,0])`은 `1.0`이었다. 차원 축소를
    색인·질의 중 한쪽에만 건 벡터가 들어오면 앞 몇 차원만으로 그럴듯한 값이 나오고, 등컷 θ가 그
    위에서 잘린다. 검사는 사본이 아니라 `memory._same_dim`을 **부른다**(F12) — 규약이 두 벌이면
    한쪽만 고쳐지는 날이 온다.
    """

    def test_length_mismatch_raises(self):
        for a, b in (([1.0, 0.0, 0.0], [1.0, 0.0]), ([1.0, 0.0], [1.0, 0.0, 0.0])):
            with self.assertRaises(R.M.DimMismatch, msg=f"{len(a)} vs {len(b)}"):
                R.cos(a, b)

    def test_check_is_memorys_not_a_copy(self):
        """`memory._same_dim`을 잠시 바꾸면 `cos`가 **그것을** 부른다 — 지역 사본이면 여기가 운다."""
        class Called(Exception):
            pass

        def spy(a, b):
            raise Called

        saved = R.M._same_dim
        R.M._same_dim = spy
        try:
            with self.assertRaises(Called):
                R.cos([1.0, 2.0], [3.0, 4.0])
        finally:
            R.M._same_dim = saved
        self.assertIs(R.M._same_dim, saved)

    def test_same_length_is_bitwise_memory_cosine(self):
        """조용한 쪽 — 같은 길이면 `memory._cosine`과 **비트까지** 같다(기록값이 안 움직인다는 주장의 단위판)."""
        for a, b in (([0.3, -1.2, 2.5, 0.0], [1.1, 0.4, -0.7, 3.3]),
                     ([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]),
                     ([0.0, 0.0], [0.0, 0.0])):
            self.assertEqual(repr(R.cos(a, b)), repr(R.M._cosine(a, b)))


if __name__ == "__main__":
    unittest.main()
