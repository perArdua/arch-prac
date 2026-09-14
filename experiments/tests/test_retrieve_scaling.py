# -*- coding: utf-8 -*-
"""
test_retrieve_scaling.py — 지연 곡선의 **계산부**를 시험한다(지연 값 자체는 시험하지 않는다 —
기계·부하의 함수라 단정할 수 없다).

🔄 첫 판의 `crossing`은 늘 가장 큰 두 N의 직선을 써서, 교차가 2,000–5,000 사이인데
10,000·20,000에서 **거꾸로 외삽**한 값을 «내삽»이라 찍었다. 그 모양을 심어 다시 안 나오는지 본다.
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import retrieve_scaling as R  # noqa: E402
import soak  # noqa: E402


class CrossingTest(unittest.TestCase):
    def test_bracket_is_used_not_the_tail(self):
        # 교차는 2–3 사이. 꼬리(3·4)의 기울기는 다르다 — 꼬리를 쓰면 다른 답이 나온다
        first, est, slope, kind = R.crossing([1, 2, 3, 4], [1, 10, 30, 100], 20)
        self.assertEqual(first, 3)
        self.assertAlmostEqual(est, 2.5)
        self.assertTrue(kind.startswith("내삽"))

    def test_not_crossed_is_labelled_extrapolation(self):
        first, est, _, kind = R.crossing([1, 2], [5, 10], 20)
        self.assertIsNone(first)
        self.assertAlmostEqual(est, 4.0)
        self.assertTrue(kind.startswith("외삽"))

    def test_crossed_at_first_point(self):
        first, est, _, _ = R.crossing([1, 2], [25, 30], 20)
        self.assertEqual((first, est), (1, None))

    def test_unsorted_input(self):
        self.assertEqual(R.crossing([4, 1, 3, 2], [100, 1, 30, 10], 20)[0], 3)

    def test_pct_matches_soak(self):
        v = [float(i) for i in range(1, 131)]
        self.assertEqual(R.pct(v, 50), soak.pct(v, 50))
        self.assertEqual(R.pct(v, 95), soak.pct(v, 95))


class BuildTest(unittest.TestCase):
    def test_db_has_exactly_n_live_rows(self):
        corpus, ledger, _ = R.load_eval()
        tmp = tempfile.mkdtemp(prefix="retscale_t_")
        try:
            tpl = R.template_rows(tmp, corpus, ledger)
            self.assertEqual(len(tpl), 21)
            for n, all_pass in ((50, False), (50, True)):
                m = R.build_db(tmp, "t" + str(all_pass), n, tpl, all_pass)
                try:
                    imps = [r["importance"] for r in m.db.execute(
                        "SELECT importance FROM event").fetchall()]
                    self.assertEqual(len(imps), n)
                    if all_pass:
                        self.assertTrue(all(i >= R.M.TAU_IMPORTANCE for i in imps))
                finally:
                    m.db.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
