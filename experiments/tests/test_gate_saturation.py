# -*- coding: utf-8 -*-
"""
test_gate_saturation.py — 실험 29의 검사 다섯에 **위반을 심어 발화를 확인한다.**

## 왜 이 파일이 이렇게 생겼나

이 저장소의 규율 하나: *«새로 쓰거나 고친 검증 명령·시험은 위반을 심어 발화를
확인한 뒤에만 보고한다.»* 그것이 열한 번 깨졌고, 그때마다 형태가 같았다 —
**검사가 옳게 도는 것처럼 보이는데 실은 발화할 수 없다.**

그래서 시험 하나마다 **둘**을 본다:

  · **심은 쪽** — 위반을 실제로 만들어 넣고 검사가 🔴를 내는가
  · **조용한 쪽** — 정상 입력에서 같은 검사가 ✅인가

조용한 쪽이 없으면 *"무엇을 넣어도 빨간 검사"*와 구별되지 않는다. 그것도
발화할 수 없는 검사의 한 형태다.

🔴 **위반은 되도록 «수를 고쳐서»가 아니라 «기제를 되돌려서» 심는다.** A1·A3·A5는
   실제로 규칙을 바꾼 게이트나 실제로 좁힌 탐색 구간으로 심는다 — 상태 dict의
   숫자만 흔들면 그 시험은 «검사 함수의 부등호»만 확인하고 **그 검사가 지키려는
   기제**는 확인하지 못한다.

재현: PYTHONIOENCODING=utf-8 python -B -m unittest discover -s experiments/tests \
        -p "test_gate_saturation.py" -v
"""

import copy
import io
import re
import sys
import unittest
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "prototype"))

import gate_saturation as G                            # noqa: E402
from memory import Memory                              # noqa: E402


# ── 심을 위반용 게이트 변종 ──────────────────────────────────────────────
#
# ⚠️ 아래 둘은 **일부러 만든 사본**이다. 본 실험(`VocabProbe`)은 사본을 쓰지 않고
#    `Memory.gate` 그 함수를 돌린다 — 여기서 사본을 만드는 이유는 *"사본이
#    갈라지면 무슨 일이 나는가"*를 검사에 보여 주기 위해서다.

def gate_no_pastref(self, utterance):
    """변종 ① — **과거 참조 팔을 뺐다.** A1(앵커)이 잡아야 하는 표류다."""
    if len(utterance) < 8:
        return False, G.R_SHORT
    if any(w[:2] in self._recall_vocab
           for w in re.findall(r"[가-힣]{2,}", utterance)):
        return True, G.R_CONTACT
    return False, G.R_NONE


def gate_pastref_last(self, utterance):
    """
    변종 ② — **과거 참조 팔을 어휘 팔 뒤로 옮겼다.**

    판정(True/False)은 하나도 안 바뀐다. 바뀌는 것은 **사유의 귀속**이고,
    그래서 `과거 참조 표현`으로 세어지는 수가 **어휘 크기의 함수가 된다.**
    A3(정규식 바닥 불변)이 지키는 것이 정확히 이것 — «바닥값»이라는 말이
    성립하려면 그 수가 어휘와 무관해야 한다.
    """
    if len(utterance) < 8 and not re.search(
            r"(기억|그때|저번|예전|아까|전에|했잖아|말했|뭐였|언제)", utterance):
        return False, G.R_SHORT
    if any(w[:2] in self._recall_vocab
           for w in re.findall(r"[가-힣]{2,}", utterance)):
        return True, G.R_CONTACT
    if re.search(r"(기억|그때|저번|예전|아까|전에|했잖아|말했|뭐였|언제)", utterance):
        return True, G.R_PAST
    return False, G.R_NONE


class VariantProbe:
    """`VocabProbe`와 같은 모양인데 게이트만 갈아 끼운다."""
    def __init__(self, vocab, fn):
        self._recall_vocab = set(vocab)
        self._fn = fn

    def gate(self, u):
        return self._fn(self, u)


class GateSaturationChecks(unittest.TestCase):
    """검사 다섯 × (심은 쪽 · 조용한 쪽)."""

    @classmethod
    def setUpClass(cls):
        # 실험을 **실제로 한 번 돌린다** (≈2초). 합성 상태만 흔들면 이 시험은
        # 진짜 데이터에서 검사가 통과한다는 사실을 확인하지 못한다.
        cls.st = G.measure()
        cls.results = {name: (ok, detail)
                       for name, ok, detail in G.run_checks(cls.st)}

    def fire(self, check, st):
        """검사 하나를 돌려 (통과, 상세)를 돌려준다."""
        _, ok, detail = check(st)
        return ok, detail

    # ── 조용한 쪽 — 전체 ────────────────────────────────────────────────
    def test_00_quiet_side_all_checks_pass_on_real_data(self):
        """조용한 쪽 (전체) — 손대지 않은 실측에서 검사 다섯이 전부 ✅."""
        bad = {n: d for n, (ok, d) in self.results.items() if not ok}
        self.assertEqual(bad, {}, f"정상 입력에서 발화한 검사가 있다: {bad}")

    def test_01_probe_runs_the_production_gate_function(self):
        """`VocabProbe.gate`는 사본이 아니라 `Memory.gate` **그 함수**여야 한다."""
        self.assertIs(G.VocabProbe.gate, Memory.gate)

    # ── A1 앵커 ────────────────────────────────────────────────────────
    def test_A1_planted_drifted_gate_fires(self):
        """
        심은 쪽 — 과거 참조 팔을 뺀 게이트로 다시 세면 불일치가 실제로 생기고,
        A1이 그것을 🔴로 낸다.
        """
        m, vocab, _sig, dbf = G.production_vocab(
            *G.load_corpus())
        try:
            dis = sum(1 for u in self.st["users"]
                      if m.gate(u) != VariantProbe(vocab, gate_no_pastref).gate(u))
        finally:
            m.db.close()
            if dbf.exists():
                dbf.unlink()
        self.assertGreater(dis, 0, "표류를 심었는데 불일치가 0이다 — 앵커가 눈이 멀었다")
        st = dict(self.st, anchor_disagreements=dis)
        ok, detail = self.fire(G.check_anchor, st)
        self.assertFalse(ok, f"A1이 표류를 통과시켰다: {detail}")
        self.assertIn(str(dis), detail)

    def test_A1_quiet(self):
        """조용한 쪽 — 실제 불일치 0건에서 A1은 ✅."""
        ok, detail = self.fire(G.check_anchor, self.st)
        self.assertTrue(ok, detail)
        self.assertIn("0/", detail)

    # ── A2 단조성 ──────────────────────────────────────────────────────
    def test_A2_planted_non_monotone_curve_fires(self):
        """
        심은 쪽 — 중첩 표본의 한 칸을 **뒤로 밀면**(k가 커졌는데 발화율이 내려감)
        A2가 그 seed와 k쌍을 이름으로 찍으며 🔴.
        """
        st = copy.deepcopy(self.st)
        ks = st["ks"]
        k_hi = ks[-1]
        st["curve"][k_hi][0] = st["curve"][ks[-2]][0] - 0.01
        ok, detail = self.fire(G.check_monotone, st)
        self.assertFalse(ok, f"A2가 역전을 통과시켰다: {detail}")
        self.assertIn("seed0", detail)
        self.assertIn(str(k_hi), detail)

    def test_A2_quiet(self):
        """조용한 쪽 — 손대지 않은 중첩 곡선에서 A2는 ✅."""
        ok, detail = self.fire(G.check_monotone, self.st)
        self.assertTrue(ok, detail)
        self.assertIn("위반 0건", detail)

    # ── A3 정규식 바닥 불변 ────────────────────────────────────────────
    def test_A3_planted_vocab_dependent_regex_arm_fires(self):
        """
        심은 쪽 — 과거 참조 팔을 어휘 팔 **뒤로** 옮긴 게이트로 다시 세면
        `과거 참조 표현` 계수가 어휘 크기를 따라 움직이고, A3가 🔴.

        🔴 이것이 «수를 고친 것»이 아니라 «기제를 되돌린 것»이다 — 실제로
           규칙 순서 하나만 바꾼 게이트의 출력을 그대로 넣는다.
        """
        order = sorted(self.st["pool"])
        import random
        random.Random(20260910).shuffle(order)
        past = {}
        for k in self.st["ks"]:
            p = VariantProbe(order[:k], gate_pastref_last)
            past[k] = Counter(p.gate(u)[1] for u in self.st["users"])[G.R_PAST]
        self.assertGreater(len(set(past.values())), 1,
                           f"팔 순서를 바꿨는데 바닥이 그대로다: {past}")
        st = dict(self.st, past_by_k=past)
        ok, detail = self.fire(G.check_floor_invariant, st)
        self.assertFalse(ok, f"A3가 어휘 의존 바닥을 통과시켰다: {detail}")
        self.assertIn("어휘에 따라 움직인다", detail)

    def test_A3_quiet(self):
        """조용한 쪽 — 프로덕션 순서에서는 바닥이 k 전 구간 동일하고 A3는 ✅."""
        ok, detail = self.fire(G.check_floor_invariant, self.st)
        self.assertTrue(ok, detail)
        self.assertEqual(len(set(self.st["past_by_k"].values())), 1)

    # ── A4 분모 고정 ───────────────────────────────────────────────────
    def test_A4_planted_lost_turn_fires(self):
        """
        심은 쪽 — 한 k에서 사유 하나를 1 줄이면(턴 하나가 어느 사유에도 안 세어짐)
        A4가 그 k를 찍으며 🔴.
        """
        st = copy.deepcopy(self.st)
        k = st["ks"][3]
        st["counts_by_k"][k][G.R_SHORT] -= 1
        st["totals_by_k"][k] = sum(st["counts_by_k"][k].values())
        ok, detail = self.fire(G.check_denominator, st)
        self.assertFalse(ok, f"A4가 사라진 턴을 통과시켰다: {detail}")
        self.assertIn(str(k), detail)
        self.assertIn(str(st["n_utt"] - 1), detail)

    def test_A4_quiet(self):
        """조용한 쪽 — 손대지 않은 계수에서 A4는 ✅."""
        ok, detail = self.fire(G.check_denominator, self.st)
        self.assertTrue(ok, detail)
        self.assertIn(str(self.st["n_utt"]), detail)

    # ── A6 실제 어휘 점 ────────────────────────────────────────────────
    def test_A6_planted_vocab_outside_pool_fires(self):
        """
        심은 쪽 ⓐ — 실제 어휘에 pool 밖 접두를 넣으면 A6이 🔴.

        pool 밖에 어휘가 있으면 무작위 곡선은 실제가 사는 공간을 표본하지 않는
        것이고, 그때 두 수를 나란히 놓는 것 자체가 무의미하다.
        """
        st = dict(self.st, today_vocab=set(self.st["today_vocab"]) | {"쨍쨍"})
        st["today_counts_n"] = len(st["today_vocab"])
        ok, detail = self.fire(G.check_real_point, st)
        self.assertFalse(ok, f"A6이 pool 밖 어휘를 통과시켰다: {detail}")
        self.assertIn("pool 밖", detail)

    def test_A6_planted_point_read_from_curve_fires(self):
        """
        심은 쪽 ⓑ — 실제 점을 «다른 어휘로» 계산해 놓으면 A6이 🔴.

        이것이 이 라운드가 실제로 저지를 뻔한 사고다: §D의 `k=62` 행에 `← 오늘`을
        붙이면 **크기만 같고 어휘가 다른 수**에 오늘의 이름이 붙는다(F21).
        """
        st = dict(self.st, today_counts_n=self.st["today_counts_n"] + 1)
        ok, detail = self.fire(G.check_real_point, st)
        self.assertFalse(ok, f"A6이 «다른 어휘로 계산된 점»을 통과시켰다: {detail}")
        self.assertIn("아닌 어휘로 계산됐다", detail)

    def test_A6_quiet(self):
        """
        조용한 쪽 — 실제 어휘는 pool의 부분집합이고 점은 그 어휘로 계산됐다.
        그리고 **그 점이 무작위 구간 밖에 있다는 사실이 상세에 찍힌다.**
        """
        ok, detail = self.fire(G.check_real_point, self.st)
        self.assertTrue(ok, detail)
        self.assertTrue(self.st["today_vocab"] <= self.st["pool"])
        band = self.st["curve"][len(self.st["today_vocab"])]
        self.assertLess(self.st["today_rate"], min(band),
                        "실제 점이 무작위 표본 구간 안에 들어왔다 — 이 라운드의 "
                        "관측(실제가 무작위보다 훨씬 덜 덮는다)이 뒤집힌 것이다")
        self.assertIn("밖", detail)

    # ── A5 열리는 조건 ─────────────────────────────────────────────────
    def test_A5_planted_narrow_range_fires(self):
        """
        심은 쪽 ⓐ — 탐색 구간을 **실제로 좁혀** 다시 유도한다. `N_all`이 그 안에
        없으면 A5가 «못 찾았다»를 🔴로 낸다 — 조용히 «없다»로 적지 않는다.

        🔴 이 위반은 개발 중에 **실제로 났다**: `FINE_HI`가 110이던 판에서
           `N_all`이 `None`이었고 A5가 그것을 잡았다. 그래서 상한이 130이다.
        """
        thr = G.derive_threshold(self.st["pool"], self.st["users"],
                                 self.st["M"], 55, 90, 8)
        self.assertIsNone(thr["N_all"], "구간을 좁혔는데 N_all이 잡혔다 — 심기 실패")
        st = dict(self.st, thr=thr)
        ok, detail = self.fire(G.check_threshold, st)
        self.assertFalse(ok, f"A5가 미유도 N을 통과시켰다: {detail}")
        self.assertIn("N_all", detail)
        self.assertIn("닿지 않는다", detail)

    def test_A5_planted_wrong_order_fires(self):
        """심은 쪽 ⓑ — 셋의 순서를 뒤집으면(`N_any > N_all`) A5가 🔴."""
        st = copy.deepcopy(self.st)
        st["thr"]["N_any"], st["thr"]["N_all"] = (st["thr"]["N_all"],
                                                 st["thr"]["N_any"])
        ok, detail = self.fire(G.check_threshold, st)
        self.assertFalse(ok, f"A5가 뒤집힌 순서를 통과시켰다: {detail}")
        self.assertIn("순서 어긋남", detail)

    def test_A5_planted_boundary_break_fires(self):
        """
        심은 쪽 ⓒ — N을 한 칸 **위로** 밀면 `rate(N-1) < M`이 깨진다
        (N-1도 이미 M을 넘으므로 «처음 넘는 곳»이 아니다). A5가 🔴.
        """
        st = copy.deepcopy(self.st)
        st["thr"]["N_mean"] += 1
        ok, detail = self.fire(G.check_threshold, st)
        self.assertFalse(ok, f"A5가 «처음이 아닌 N»을 통과시켰다: {detail}")
        self.assertIn("경계 어긋남", detail)

    def test_A5_quiet(self):
        """조용한 쪽 — 유도된 셋에서 A5는 ✅이고 순서가 맞는다."""
        ok, detail = self.fire(G.check_threshold, self.st)
        self.assertTrue(ok, detail)
        d = self.st["thr"]
        self.assertLessEqual(d["N_any"], d["N_mean"])
        self.assertLessEqual(d["N_mean"], d["N_all"])

    # ── 종료 코드 ──────────────────────────────────────────────────────
    def test_exit_code_follows_checks(self):
        """
        `report()`의 종료 코드가 검사 결과를 따르는가 — 조용한 쪽 0,
        심은 쪽 1. **출력이 초록인데 종료가 0이 아닌 것**도, 그 반대도 사고다.
        """
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc_ok = G.report(self.st)
        self.assertEqual(rc_ok, 0)
        self.assertNotIn("🔴 A", buf.getvalue())

        st = copy.deepcopy(self.st)
        st["anchor_disagreements"] = 7
        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc_bad = G.report(st)
        self.assertEqual(rc_bad, 1)
        self.assertIn("🔴 A1", buf2.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
