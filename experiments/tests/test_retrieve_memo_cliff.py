# -*- coding: utf-8 -*-
"""
test_retrieve_memo_cliff.py — `retrieve_memo.py` 3절(C5 절벽)의 **판정부**와 짝 콜드 턴을 시험한다(w13cliff · 사후 정정).

지키는 것:
  · 옛 규칙(PREREG C5 · h ≤ 0.10)은 그대로다 — 상수 · 사전 등록 문장 · 판정 문자열.
  · 새 규칙은 이득 g = h − d(`CLIFF_GAIN`)로 판정한다 — h만 보면 0.114 칸이 «절벽 아님»으로 되돌아간다.
  · d가 없으면 «판정 불가»다(숫자를 만들지 않는다).
  · 짝 콜드 턴은 **새** 빈 메모로 잰다 — 두 번 불러도 같고, 끝 절 메모 객체·그 적중 수를 안 건드린다.

    PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s experiments/tests -p "test_retrieve_memo_cliff.py" -v
"""
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import retrieve_memo as RM  # noqa: E402

M = RM.M


class VerdictTest(unittest.TestCase):
    def test_prereg_untouched(self):
        self.assertEqual(RM.CLIFF_HIT, 0.10)
        self.assertEqual(RM.CLIFF_GAIN, 0.10)
        c5 = [p for p in RM.PREREG if p[0] == "C5 절벽"]
        self.assertEqual(len(c5), 1)
        self.assertEqual(c5[0][2], "h ≤ 0.10 → «절벽»(웜이 콜드가 된다)")
        self.assertEqual(c5[0][3], "h > 0.10 → «절벽 아님»")

    def test_old_rule_kept(self):
        self.assertEqual(RM.c5_old(0.023), "«절벽»")
        self.assertEqual(RM.c5_old(0.114), "«절벽 아님»")       # 옛 판정은 지우지 않는다
        self.assertEqual(RM.c5_old(RM.CLIFF_HIT), "«절벽»")

    def test_new_rule_uses_gain(self):
        self.assertEqual(RM.c5_new(0.114, 0.110), "«절벽»")      # g ≈ 0.004 — docs/11 §C 🔄의 칸
        self.assertEqual(RM.c5_new(0.114, 0.103), "«절벽»")      # 이 파일이 잰 짝 콜드 d(상한 1000)
        self.assertEqual(RM.c5_new(0.647, 0.543), "«절벽 아님»")  # g 0.104
        self.assertEqual(RM.c5_new(0.023, 0.023), "«절벽»")
        self.assertEqual(RM.c5_new(RM.CLIFF_GAIN, 0.0), "«절벽»")
        self.assertEqual(RM.c5_new(RM.CLIFF_GAIN + 1e-9, 0.0), "«절벽 아님»")

    def test_no_d_no_verdict(self):
        self.assertEqual(RM.c5_new(0.114, None), "판정 불가(d 없음)")

    def test_row_prints_old_and_new_side_by_side(self):
        # 이 파일이 잰 지프 칸의 정수(턴당 262 · 238 / 2,300 × 130턴) — 옛 칸은 «절벽 아님», 새 칸은 «절벽»
        row = RM.c5_row("eval3·지프 s=1", 34060, 299000, 30940, 299000, 23.1, 2048, 2300)
        self.assertEqual(re.findall(r"«[^»]*»", row), ["«절벽 아님»", "«절벽»"])
        self.assertIn("34060/299000", row)
        self.assertIn("30940/299000", row)
        self.assertIn("    0.010", row)                            # g = h − d
        self.assertIn("   0.110", row)                             # 1 − D_τ/n (대조 열)
        none = RM.c5_row("x", 34060, 299000, 0, 0, float("nan"), 2048, 2300)
        self.assertEqual(re.findall(r"«[^»]*»", none), ["«절벽 아님»"])
        self.assertIn("판정 불가(d 없음)", none)


class ColdTurnTest(unittest.TestCase):
    """eval 코퍼스(작다)로 DB 하나 — 짝 콜드 턴의 적중이 방 안 중복과 같고 되풀이해도 같다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="w13_rmc_")
        corpus, ledger, qs = RM.E3P.load("eval")
        cls.m = RM.E3P.build(cls.tmp, "eval", corpus, ledger)
        cls.q, cls.last = qs[0]["ask"], corpus[-1]["seq"]
        tau = [r[0] for r in cls.m.db.execute(
            "SELECT summary FROM event WHERE chat_id=? AND user_deleted=0 AND"
            " MAX(COALESCE(importance,0), COALESCE(emotional_weight,0)) >= ?", (RM.soak.CHAT, M.TAU_IMPORTANCE))]
        cls.n_tau, cls.d_tau = len(tau), len(set(tau))

    @classmethod
    def tearDownClass(cls):
        cls.m.db.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_cold_is_fresh_and_repeatable(self):
        g0, h0 = M._doc_grams, M._doc_heads
        self.m.retrieve(RM.soak.CHAT, self.q, self.last)            # 끝 절 메모를 데운다 — 콜드 턴이 이것을 쓰면 다 맞는다
        info0 = M._doc_grams.cache_info()
        a = RM.cold_turn(self.m, self.q, self.last, 10_000)
        b = RM.cold_turn(self.m, self.q, self.last, 10_000)
        self.assertEqual(a[1:], b[1:])
        self.assertEqual(a[2], self.n_tau)                           # 호출 = τ 통과 행
        self.assertEqual(a[1], self.n_tau - self.d_tau)              # 적중 = 방 안 중복(상한이 넉넉하면)
        self.assertIs(M._doc_grams, g0)
        self.assertIs(M._doc_heads, h0)
        self.assertEqual(M._doc_grams.cache_info(), info0)          # 끝 절 메모의 적중 수를 안 건드린다

    def test_cold_cap_bounds_hits(self):
        one = RM.cold_turn(self.m, self.q, self.last, 1)
        big = RM.cold_turn(self.m, self.q, self.last, 10_000)
        self.assertLessEqual(one[1], big[1])
        self.assertEqual(one[2], big[2])


if __name__ == "__main__":
    unittest.main()
