# -*- coding: utf-8 -*-
"""
test_hardcoding_audit.py — **이 감사가 실제로 발화하는가.**

## 왜 이 파일이 있는가

이 저장소의 규율은 *"새로 쓰거나 고친 검증 명령은 **위반을 심어 발화를 확인한 뒤에만**
보고한다"*이고, 그 약속이 **열한 번** 깨졌다. `hardcoding_audit.py`가 내놓는 주장은 넷이다:

  ① sha256 고정물에 **구멍**이 있다 (상수를 갈면 통과하는데 동작이 바뀐다)
  ② 상수 대장의 `file:line`이 **실제 자리**다 (G18)
  ③ `UBIQUITOUS`는 대장 기저에서 **유도된다** — 그리고 기저를 바꾸면 유도되지 않는다
  ④ `len(w) < 2`가 **의미 있는 1글자 토큰**을 버린다

넷 다 «심은 위반이 빨개지는가»와 «**조용한 쪽이 조용한가**» 둘을 함께 잡는다.
한쪽만 잡으면 «전부 빨갛게 하라» 변이가 그대로 통과한다 —
`test_scoring.TestOrdinalMutants`가 이미 그 형태로 적어 둔 규율이다.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "prototype"))

import hardcoding_audit as A                                 # noqa: E402
import scoring                                               # noqa: E402
import summary_local                                         # noqa: E402

ITEMS = summary_local.load()[1]


class TestFrozenFixtureHasAHole(unittest.TestCase):
    """
    ① **심은 위반: 모듈 전역만 갈아 끼운다.**

    구멍의 정의는 `(해시 안 움직임, 동작 움직임)`이다. 두 조건을 **함께** 걸어야
    한다 — «해시가 안 움직인다»만 걸면 아무 상수나 통과하고, «동작이 움직인다»만
    걸면 함수 원문을 고쳐도 통과한다.
    """

    def test_swapping_the_constant_passes_the_hash_and_changes_behaviour(self):
        moved_h, moved_b, before, after = A.hole_probe(
            "UBIQUITOUS", set(), A.PROBE, ITEMS)
        self.assertFalse(moved_h, "상수를 갈았는데 함수 원문 해시가 움직였다"
                                  " — 그러면 구멍이 아니다")
        self.assertTrue(moved_b, "상수를 갈았는데 동작이 안 움직였다"
                                 " — 심은 위반이 발화하지 못했다")
        self.assertEqual(len(before), 0)
        self.assertEqual(len(after), 3, "옛 위양성 3건이 그대로 돌아와야 한다")

    def test_the_real_fixture_test_stays_green_while_behaviour_test_goes_red(self):
        """🔴 **말이 아니라 시험을 돌려서** 확인한다."""
        ok_hash, ok_behav = A.frozen_test_verdict()
        self.assertTrue(ok_hash, "`test_source_hashes`가 빨개졌다"
                                 " — 그러면 상수도 얼어 있다는 뜻이다")
        self.assertFalse(ok_behav, "`test_v2_drops_all_three`가 초록이다"
                                   " — 갈아 끼운 것이 동작에 닿지 않았다")

    def test_quiet_side_a_global_v2_never_reads(self):
        """
        🔴 **조용한 쪽 대조.** `_ORDINALS`는 `survived_v3`만 읽는다. 그것을 갈면
        해시도 동작도 안 움직여야 한다 — 그래야 위 시험이 «전역을 갈면 무조건
        빨개진다»가 아니라 **«v2가 읽는 전역일 때만»**을 잰 것이 된다.
        """
        moved_h, moved_b, _, _ = A.hole_probe(
            "_ORDINALS", frozenset(), A.PROBE, ITEMS)
        self.assertFalse(moved_h)
        self.assertFalse(moved_b, "v2가 안 읽는 전역을 갈았는데 v2 동작이 바뀌었다"
                                  " — 이 프로브는 무엇을 잰 것인지 알 수 없다")

    def test_the_swap_is_restored(self):
        """되돌리지 않으면 뒤따르는 모든 측정이 오염된다 (G13)."""
        A.hole_probe("UBIQUITOUS", set(), A.PROBE, ITEMS)
        self.assertEqual(scoring.UBIQUITOUS, {"지우"})
        self.assertEqual(scoring.survived_v2(A.PROBE, ITEMS).survived, [])


class TestAnchorsAreVerifiedNotAsserted(unittest.TestCase):
    """② 상수 대장의 `file:line` — **심은 오프바이원이 빨개지는가** (G18)."""

    def test_the_shipped_table_is_clean(self):
        bad = A.verify_anchors(A.CONSTANTS)
        self.assertEqual(bad, [], f"앵커가 어긋났다: {bad}")

    def test_an_off_by_one_line_is_caught(self):
        planted = [(n, p, ln + 1, nd, k, d, w)
                   for n, p, ln, nd, k, d, w in A.CONSTANTS]
        bad = A.verify_anchors(planted)
        self.assertGreaterEqual(
            len(bad), len(A.CONSTANTS) - 2,
            "줄 번호를 통째로 한 줄 밀었는데 거의 다 통과했다"
            " — 이 검사는 자리를 안 보고 있다")

    def test_a_wrong_file_is_caught(self):
        planted = [(A.CONSTANTS[0][0], "experiments/scoring.py", 51,
                    "이 줄에 없는 문자열", *A.CONSTANTS[0][4:])]
        self.assertEqual(len(A.verify_anchors(planted)), 1)


class TestDerivation(unittest.TestCase):
    """③ 유도 — **기준이 만드는 집합 전체**가 주장이다."""

    @classmethod
    def setUpClass(cls):
        cls.B = A.bases()
        cls.ledger = cls.B["대장-22 (facts 12 + events 10)"][0]

    def test_ledger_base_derives_exactly_jiwoo(self):
        self.assertEqual(A.derive(self.ledger, 0.50), frozenset({"지우"}))

    def test_the_band_is_wide_enough_to_be_a_derivation(self):
        """🔴 구간이 좁으면 «유도»가 아니라 «맞춤»이다. 폭을 못 박는다."""
        lo, hi = A.stable_band(self.ledger, {"지우"})
        self.assertTrue(lo < 0.50 <= hi,
                        f"고른 문턱 0.50이 구간 ({lo:.3f}, {hi:.3f}] 밖이다")
        self.assertGreaterEqual(hi - lo, 0.30,
                                "`{지우}`만 주는 tau 구간이 30%p보다 좁다"
                                " — 그러면 유도가 아니라 맞춤이다")
        # 🔴 구간 **안**에서는 그 집합이 나오고 **밖**에서는 안 나와야 한다.
        #    한쪽만 걸면 «(0,1]이 구간이다»라는 가짜 답이 조용히 통과한다.
        self.assertEqual(A.derive(self.ledger, hi), frozenset({"지우"}))
        self.assertEqual(A.derive(self.ledger, lo + 1e-9), frozenset({"지우"}))
        self.assertNotEqual(A.derive(self.ledger, hi + 0.01), frozenset({"지우"}))
        self.assertNotEqual(A.derive(self.ledger, lo), frozenset({"지우"}))

    def test_loosening_drags_in_the_other_character(self):
        """심은 위반: 문턱을 한 눈금 내리면 **또 하나의 등장인물 이름**이 딸려 온다."""
        self.assertEqual(A.derive(self.ledger, 0.20), frozenset({"지우", "서준"}))
        wide = A.derive(self.ledger, 0.10)
        self.assertTrue({"번째", "면접"} <= wide,
                        "0.10까지 열었는데 회차 어근이 안 들어왔다"
                        " — 그러면 «넓히면 위험하다»는 말의 근거가 없다")

    def test_the_text_side_base_does_not_derive_jiwoo(self):
        """
        🔴 **조용한 쪽이 아니라 반대 쪽 대조다.** 채점기가 읽는 «본문» 쪽에서
        같은 규칙을 돌리면 `{지우}`가 **어떤 tau에서도 안 나온다.** 이것이
        «유도된다»가 기저에 매여 있다는 증거다.
        """
        summ = self.B["요약-24 (SUMMARY_S2)"][0]
        self.assertIsNone(A.stable_band(summ, {"지우"}))
        self.assertIn("사용자", A.derive(summ, 0.75))
        self.assertNotIn("지우", A.derive(summ, 0.50))

    def test_corpus_turn_base_derives_nothing_useful(self):
        turns = self.B["코퍼스-턴-720"][0]
        self.assertEqual(A.derive(turns, 0.20), frozenset())


class TestSwapActuallyMovesSomething(unittest.TestCase):
    """
    🔴 **절 3이 «안 움직인다»고 말하려면 «움직일 수 있다»가 먼저 참이어야 한다.**

    갈아 끼우기가 아무 데도 안 닿으면 «실험 19·20이 안 움직인다»는 문장은
    측정이 아니라 배관 고장이다. 그래서 **움직이는 자리 하나**를 못 박는다.
    """

    def test_empty_set_moves_a_recorded_number(self):
        rows, items = A.exp19_rows()
        text = dict(rows)["세션 요약"]
        with A.swapped(UBIQUITOUS=frozenset()):
            after = A.score3(text, items)
        before = A.score3(text, items)
        self.assertNotEqual(before[1], after[1],
                            "∅로 갈았는데 실험 19의 v2 값이 안 움직였다"
                            " — 갈아 끼우기가 채점에 닿지 않는다")

    def test_frozen_column_is_immune_by_construction(self):
        """
        🔴 **조용한 쪽.** 같은 텍스트·같은 항목에서 `survived_frozen`은 여섯
        집합 전부에 대해 **같은 수**여야 한다. 그 함수는 `UBIQUITOUS`를
        참조하지 않는다 — 안 움직이는 것이 배관 고장이 아니라 설계다.
        """
        rows, items = A.exp19_rows()
        for name, text in rows:
            got = set()
            for s in (frozenset(), frozenset({"지우"}),
                      frozenset({"지우", "서준"}), A.derive(
                          A.bases()["요약-24 (SUMMARY_S2)"][0], 0.50)):
                with A.swapped(UBIQUITOUS=s):
                    got.add(len(scoring.survived_frozen(text, items)))
            self.assertEqual(len(got), 1, f"{name}: frozen이 움직였다 {got}")

    def test_empty_set_collapses_experiment_26_to_the_trivial_baseline(self):
        """
        🔴 **이 레인이 보고하는 수를 시험이 든다.** 홀드아웃 v2가
        94.4%(17/18) → 77.8%(14/18)로 떨어지고, 그 77.8%는 «전부 N»
        자명한 기준선과 **같은 수**다.
        """
        base, c0 = A.run_script("experiments/scorer_eval.py")
        with A.swapped(UBIQUITOUS=frozenset()):
            gone, c1 = A.run_script("experiments/scorer_eval.py")
        pick = lambda o: A.grab(o, "홀드아웃 (사전 등록",
                                ["축자 v2 (기록)", "축자 단독 (v3)"])
        self.assertIn("17/18", pick(base)["축자 v2 (기록)"])
        self.assertIn("14/18", pick(gone)["축자 v2 (기록)"])
        self.assertIn("18/18", pick(base)["축자 단독 (v3)"])
        self.assertIn("15/18", pick(gone)["축자 단독 (v3)"])
        self.assertEqual(c0, 0)
        self.assertEqual(c1, 1, "∅로 갈았는데 실험 26이 종료 0으로 돌았다"
                                " — 그 실험의 음성 대조가 발화하지 않았다")

    def test_empty_set_makes_experiment_27_refuse_to_draw_its_table(self):
        """🔴 실험 27은 **자기 기준선 앵커**로 이것을 잡는다 — sha256이 못 잡는 것을."""
        with A.swapped(UBIQUITOUS=frozenset()):
            out, code = A.run_script("experiments/summary_prototype.py")
        self.assertEqual(code, 1)
        self.assertIn("🔴 재현 실패", out)
        self.assertIn("화살표를 그릴 근거가 없다", out)

    def test_exp20_cache_rebuild_matches_the_live_run(self):
        """캐시 재조립이 실제 실행과 다르면 3-b의 표는 **다른 실험**이다."""
        import re
        out, code = A.run_script("experiments/summary_local.py")
        self.assertEqual(code, 0)
        live = re.findall(r"(\d+)/11", out)
        rows, items = A.exp20_rows()
        mine = [str(len(scoring.survived_frozen(t, items))) for _, t in rows]
        self.assertEqual(live[:len(mine)], mine)


class TestSingleCharCost(unittest.TestCase):
    """④ `len(w) < 2`의 비용 — 목록이 실제로 그 규칙이 버리는 것인가."""

    @classmethod
    def setUpClass(cls):
        B = A.bases()
        cls.docs = (B["코퍼스-턴-720"][0]
                    + B["대장-22 (facts 12 + events 10)"][0]
                    + B["요약-24 (SUMMARY_S2)"][0])
        cls.df, _ = A.dropped_single_chars(cls.docs)

    def test_ordinals_are_actually_dropped(self):
        """심은 확인: 서수 셋이 목록에 있고, `_roots`가 정말 그것을 안 낸다."""
        from memory import Memory
        for ch in ("첫", "두", "세"):
            self.assertIn(ch, self.df)
        self.assertNotIn("세", Memory._roots("세 번째 면접을 봤다"))
        self.assertIn("번째", Memory._roots("세 번째 면접을 봤다"))

    def test_quiet_side_two_char_tokens_are_not_in_the_list(self):
        """
        🔴 **조용한 쪽.** 2글자 이상은 이 목록에 있으면 안 된다. 없어야
        «이 목록 = `len(w) < 2`가 버리는 것»이라는 이름이 참이다.
        """
        self.assertTrue(all(len(t) == 1 for t in self.df),
                        f"1글자가 아닌 것이 섞였다: "
                        f"{[t for t in self.df if len(t) != 1]}")
        for t in ("면접", "번째", "지우"):
            self.assertNotIn(t, self.df)

    def test_content_words_are_lost_too_not_just_ordinals(self):
        """서수만 잃는 것이 아니다 — 대명사·명사도 같이 사라진다."""
        for ch in ("나", "너", "옷", "밥", "책"):
            self.assertIn(ch, self.df, f"`{ch}`가 목록에 없다")
            self.assertEqual(A.classify_single(ch)[0], A.CONT)

    def test_bullets_are_classified_as_droppable(self):
        """`1`·`2`·`3`은 요약의 글머리다 — 버리는 것이 옳다고 **분류**돼 있어야 한다."""
        for ch in ("1", "2", "3"):
            self.assertEqual(A.classify_single(ch)[0], A.BULLET)


class TestAuditIsReadOnly(unittest.TestCase):
    """🔴 이 레인은 **측정과 제안**이다 — 감사가 원본을 만지면 안 된다."""

    def test_scoring_globals_are_untouched_after_a_full_run(self):
        before = (frozenset(scoring.UBIQUITOUS), scoring.MIN_ROOTS,
                  frozenset(scoring._ORDINALS))
        A.hole_probe("UBIQUITOUS", set(), A.PROBE, ITEMS)
        A.hole_probe("_ORDINALS", frozenset(), A.PROBE, ITEMS)
        after = (frozenset(scoring.UBIQUITOUS), scoring.MIN_ROOTS,
                 frozenset(scoring._ORDINALS))
        self.assertEqual(before, after)

    def test_the_audit_writes_no_file_under_the_repo(self):
        """실험 스크립트 셋을 돌려도 저장소 파일의 mtime이 안 움직여야 한다."""
        watch = ["experiments/scoring.py", "prototype/memory.py",
                 "experiments/data/LIFETIME_S27.json", "experiments/data/SUMMARY_LOCAL.json",
                 "experiments/data/DRIFT_RESULTS.json", "eval/fact-ledger.yaml"]
        before = {p: os.path.getmtime(os.path.join(ROOT, p)) for p in watch}
        with A.swapped(UBIQUITOUS=frozenset()):
            A.run_script("experiments/summary_local.py")
            A.run_script("experiments/summary_prototype.py")
        after = {p: os.path.getmtime(os.path.join(ROOT, p)) for p in watch}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
