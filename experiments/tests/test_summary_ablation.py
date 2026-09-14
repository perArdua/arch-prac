# -*- coding: utf-8 -*-
"""
test_summary_ablation.py — `summary_ablation.py`의 **검사들이 발화하는지** 본다.

## 이 파일이 시험하는 것

숫자가 아니다. A1의 3/10도 A3의 1/3도 그 스크립트가 매 실행 다시 뽑는 값이고,
여기 박아 두면 **같은 값을 두 곳에 적는 것**이다(`run_all.py`가 있는 이유).
여기서 보는 것은 **규율이 코드인가**다:

  · 「앵커와 정확히 한 요인」이 **실제로 두 요인짜리 팔을 막는가** (`FactorRule`)
  · 「요인이 둘 다른 팔 쌍에 화살표 금지」가 **잡히는가** (`ArrowRule`)
  · 「없는 계약은 채점하지 않는다」가 **`SESSION` 지시 팔의 M1을 거부하는가**
  · 「조립이 프로덕션과 바이트 동일」이 **한 글자 변이에 우는가**
  · 「창을 넘으면 안 돌린다」가 **양쪽으로 갈리는가** — 심으면 제외, 정상에선 통과
  · 🔴 **사전 등록이 상수인가** — 팔 표와 판정 규칙이 코드에 있고, 판정 규칙이
    요인마다 **항목 집합의 이름을 들고 있는가**
  · 🆕 「창」이 **네 번째 요인인가** — `A0`과 `A0′`가 같은 팔로 안 보이는가
  · 🆕 「창을 키운 팔의 앵커도 같은 창인가」 — 첫 판의 A4(앵커 A0)를 되살리면 우는가
  · 🆕 「전역 창을 되돌리는가」 — 정상·예외 두 길로 나가도 복원되고, 안 하면 우는가
  · 🆕 「화살표마다 항목 집합이 **사전 등록**돼 있는가」 — 계산하지 않는다

⚠️ `python -B`로 돌려라. 낡은 `.pyc`가 변이를 살려 준 전례가 있다(실험 25 §G).
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "prototype"))

import llm                                                   # noqa: E402
import summarize                                             # noqa: E402
import summary_ablation as SA                                # noqa: E402
import summary_prototype as SP                               # noqa: E402


def _arm(key, ins="P4", mat="세션 요약", span="S01–S24",
         anchor=None, moved=None, window=None):
    return SA.Arm(key, ins, mat, span, anchor, moved, window=window)


BASE = _arm("A0")


# ── 사전 등록 — 상수인가 ────────────────────────────────────────────────

class TestPreregistration(unittest.TestCase):
    """🔴 사전 등록은 **코드 상수**여야 한다. 산문이면 값을 보고 고칠 수 있다."""

    def test_exactly_one_anchor_arm(self):
        roots = [s for s in SA.ARM_SPECS if s[4] is None]
        self.assertEqual(len(roots), 1, "앵커 없는 팔이 하나가 아니다")
        self.assertEqual(roots[0][0], "A0")

    def test_every_non_root_arm_declares_a_moved_factor(self):
        for key, _i, _m, _s, anchor, moved, _n, _w in SA.ARM_SPECS:
            if anchor is None:
                continue
            self.assertIn(moved, SA.Arm.FACTORS,
                          f"«{key}»가 선언한 요인 «{moved}»가 요인 넷에 없다")

    def test_three_factors_each_have_a_decision_rule(self):
        """①②③ 셋 다 판정 규칙이 있어야 한다 — 하나라도 빠지면 못 가른다.

        🔄 A4 라운드가 ④(창)와 ②′(24세션)를 더했으므로 «정확히 셋»이 아니라
        **«셋이 다 있는가»**로 읽는다. ①②③이 하나라도 빠지면 여전히 운다.
        """
        marks = {r[0][0] for r in SA.DECISION_RULES}
        self.assertTrue({"①", "②", "③"} <= marks, marks)

    def test_a4_round_added_the_window_and_span24_rules(self):
        """🆕 ④(창)와 ②′(24세션 구간)이 **코드 상수**로 있어야 한다."""
        factors = [r[0] for r in SA.DECISION_RULES]
        self.assertTrue(any(f.startswith("④") for f in factors), factors)
        self.assertTrue(any(f.startswith("②′") for f in factors), factors)

    def test_decision_rule_labels_are_unique(self):
        """②와 ②′는 **다른 줄**이다 — 같은 이름이면 둘 중 하나가 사라진다."""
        factors = [r[0] for r in SA.DECISION_RULES]
        self.assertEqual(len(factors), len(set(factors)), factors)

    def test_the_first_three_rules_are_untouched(self):
        """🔒 실험 28의 사전 등록 세 줄은 **글자 그대로** 남아 있어야 한다 —
        이 라운드가 그것을 다시 쓰면 «사전 등록»이 아무것도 뜻하지 않는다."""
        self.assertEqual([r[0] for r in SA.DECISION_RULES[:3]],
                         ["①  지시", "③  재료 크기", "②  재압축"])
        self.assertEqual([r[1] for r in SA.DECISION_RULES[:3]],
                         ["A1 vs A0", "A2 vs A0", "A3 vs A2"])

    def test_every_decision_rule_names_an_item_set(self):
        """🔴 §3.1 — 항목 집합의 **이름** 없이 판정 규칙을 적을 수 없다."""
        rule = SP.TitleRule()
        for factor, pair, itemset, how in SA.DECISION_RULES:
            self.assertTrue(itemset.strip(), f"«{factor}»에 항목 집합이 없다")
            self.assertFalse(rule.BARE.match(itemset.strip()),
                             f"«{factor}»의 항목 집합 «{itemset}»가 숫자뿐이다")
            self.assertTrue(how.strip())

    def test_decision_rules_only_reference_declared_arms(self):
        keys = {s[0] for s in SA.ARM_SPECS}
        for _f, pair, _i, _h in SA.DECISION_RULES:
            for k in pair.replace("vs", " ").split():
                self.assertIn(k, keys, f"판정 규칙이 없는 팔 «{k}»를 가리킨다")

    def test_arrow_itemset_is_preregistered_for_every_anchored_arm(self):
        """🆕 🔴 자격 있는 화살표마다 **어느 항목 집합에서 읽을지**가 상수여야 한다.

        첫 판은 이것을 요인 이름에서 **계산**했고, 창이 요인으로 늘자 그 규칙이
        `A0→A0′`·`A0′→A4`를 둘 다 «구간 안 3»으로 보냈다 — 두 팔의 재료가
        S01–S24를 전부 덮는데 3분의 1만 보고 읽는 것이다.
        """
        for key, _i, _m, _s, anchor, _mv, _n, _w in SA.ARM_SPECS:
            if anchor is None:
                continue
            self.assertIn((anchor, key), SA.ARROW_ITEMSET,
                          f"«{anchor}→{key}»의 항목 집합이 사전 등록에 없다")

    def test_arrow_itemset_keys_are_known(self):
        for which in SA.ARROW_ITEMSET.values():
            self.assertIn(which, ("10", "3"))

    def test_full_span_arms_read_the_full_item_set(self):
        """🔴 재료가 S01–S24를 덮는 쌍을 «구간 안 3»에서 읽으면 안 된다."""
        spans = {s[0]: s[3] for s in SA.ARM_SPECS}
        for (k1, k2), which in SA.ARROW_ITEMSET.items():
            if spans[k1] == "S01–S24" and spans[k2] == "S01–S24":
                self.assertEqual(which, "10", f"«{k1}→{k2}»")


# ── 요인 규율 ───────────────────────────────────────────────────────────

class TestFactorRule(unittest.TestCase):
    """**정상에 조용하고 위반에 운다** — 두 방향을 다 본다."""

    def setUp(self):
        self.rule = SA.FactorRule()

    def test_real_spec_is_quiet(self):
        """오발화 대조 — 사전 등록된 여섯 팔에는 울지 않는다."""
        arms = [SA.Arm(k, i, m, s, a, mv, window=w)
                for k, i, m, s, a, mv, _n, w in SA.ARM_SPECS]
        self.assertEqual(self.rule.audit(arms), [])

    def test_two_factors_fire(self):
        z = _arm("Z", ins="SESSION", mat="원본 턴", anchor="A0", moved="지시")
        bad = self.rule.audit([BASE, z])
        self.assertTrue(any(b.startswith("①") for b in bad), bad)

    def test_three_factors_fire(self):
        z = _arm("Z", ins="SESSION", mat="원본 턴", span="S01–S12",
                 anchor="A0", moved="지시")
        bad = self.rule.audit([BASE, z])
        self.assertTrue(any(b.startswith("①") for b in bad), bad)

    def test_zero_factors_fire(self):
        """같은 팔을 두 이름으로 부르는 것도 위반이다 — X6의 형태다."""
        z = _arm("Z", anchor="A0", moved="지시")
        bad = self.rule.audit([BASE, z])
        self.assertTrue(any(b.startswith("②") for b in bad), bad)

    def test_declared_factor_mismatch_fires(self):
        z = _arm("Z", span="S01–S12", anchor="A0", moved="지시")
        bad = self.rule.audit([BASE, z])
        self.assertTrue(any(b.startswith("③") for b in bad), bad)

    def test_missing_anchor_fires(self):
        z = _arm("Z", span="S01–S12", anchor="없는팔", moved="구간")
        bad = self.rule.audit([BASE, z])
        self.assertTrue(any(b.startswith("④") for b in bad), bad)

    def test_each_single_factor_move_is_quiet(self):
        """네 요인 각각을 혼자 움직이면 조용해야 한다 — 규칙이 한쪽으로 안 쏠린다."""
        for moved, arm in (
                ("지시", _arm("Z", ins="SESSION", anchor="A0", moved="지시")),
                ("재료", _arm("Z", mat="원본 턴", anchor="A0", moved="재료")),
                ("구간", _arm("Z", span="S01–S12", anchor="A0", moved="구간")),
                ("창", _arm("Z", window=SA.BIG_NUM_CTX, anchor="A0",
                            moved="창"))):
            with self.subTest(moved=moved):
                self.assertEqual(self.rule.audit([BASE, arm]), [])

    def test_diff_names_the_factors(self):
        z = _arm("Z", ins="SESSION", span="S01–S12", anchor="A0", moved="지시")
        self.assertEqual(self.rule.diff([BASE, z], "A0", "Z"), ["구간", "지시"])


# ── 🆕 창이 네 번째 요인이다 ────────────────────────────────────────────

class TestWindowIsAFactor(unittest.TestCase):
    """
    🔴 **A4 라운드의 함정을 코드로 세운다.** 창을 키우면 요인이 둘 움직인다 —
    그것을 규칙이 모르면 `A0`과 `A0′`가 «같은 팔의 두 이름»으로 통과한다.
    """

    def setUp(self):
        self.rule = SA.FactorRule()

    def test_window_is_one_of_the_factors(self):
        self.assertIn("창", SA.Arm.FACTORS)

    def test_same_arm_with_a_different_window_is_not_the_same_arm(self):
        """가드가 없으면 위반 ②(«한 요인도 다르지 않다»)로 잡혀 버린다."""
        a0p = _arm("A0′", window=SA.BIG_NUM_CTX, anchor="A0", moved="창")
        self.assertEqual(self.rule.audit([BASE, a0p]), [])
        self.assertEqual(self.rule.diff([BASE, a0p], "A0", "A0′"), ["창"])

    def test_naive_a4_anchored_to_the_small_window_fires(self):
        """🔴 **첫 판의 A4를 되살리면 운다** — 이 라운드의 중심 시험이다.

        `("A4", "P4", "원본 턴", "S01–S24", "A0", "재료")`에 큰 창을 주면
        앵커와 **재료·창 둘**이 달라진다. «그대로 넣으면 터진다»가 그 뜻이다.
        """
        naive = _arm("A4", mat="원본 턴", window=SA.BIG_NUM_CTX,
                     anchor="A0", moved="재료")
        bad = self.rule.audit([BASE, naive])
        self.assertTrue(any(b.startswith("①") for b in bad), bad)
        self.assertIn("2개", bad[0])

    def test_a4_anchored_to_a0_prime_is_quiet(self):
        """오발화 대조 — 앵커를 같은 창에서 다시 만들면 조용하다."""
        a0p = _arm("A0′", window=SA.BIG_NUM_CTX, anchor="A0", moved="창")
        a4 = _arm("A4", mat="원본 턴", window=SA.BIG_NUM_CTX,
                  anchor="A0′", moved="재료")
        self.assertEqual(self.rule.audit([BASE, a0p, a4]), [])

    def test_default_window_is_the_production_default(self):
        """인자 여섯짜리 옛 호출부가 **한 글자도 안 고치고** 그대로 돌아야 한다."""
        self.assertEqual(_arm("Z").window, SA.PROD_NUM_CTX)
        self.assertEqual(SA.PROD_NUM_CTX, 8192)

    def test_the_four_original_arms_share_one_window(self):
        """🔒 A0–A3의 요인 계산이 **한 자리도 안 움직여야** 한다."""
        wins = {s[0]: s[7] for s in SA.ARM_SPECS}
        self.assertEqual({wins[k] for k in ("A0", "A1", "A2", "A3")},
                         {SA.PROD_NUM_CTX})
        self.assertEqual({wins[k] for k in ("A0′", "A4")}, {SA.BIG_NUM_CTX})

    def test_a4s_anchor_is_a0_prime(self):
        anchors = {s[0]: s[4] for s in SA.ARM_SPECS}
        self.assertEqual(anchors["A4"], "A0′")
        self.assertEqual(anchors["A0′"], "A0")


# ── 화살표 자격 ─────────────────────────────────────────────────────────

class TestArrowRule(unittest.TestCase):

    def setUp(self):
        self.rule = SA.ArrowRule()
        self.a0 = _arm("A0")
        self.a1 = _arm("A1", ins="SESSION", anchor="A0", moved="지시")
        self.a3 = _arm("A3", mat="원본 턴", span="S01–S12",
                       anchor="A0", moved="재료")
        for a in (self.a0, self.a1, self.a3):
            a.ran = True

    def test_single_factor_pair_is_quiet(self):
        """오발화 대조 — 한 요인만 다르고 둘 다 돈 쌍에는 울지 않는다."""
        self.assertEqual(
            self.rule.audit([self.a0, self.a1, self.a3], [("A0", "A1")]), [])

    def test_two_factor_pair_fires(self):
        bad = self.rule.audit([self.a0, self.a1, self.a3], [("A0", "A3")])
        self.assertTrue(bad)
        self.assertIn("2개", bad[0])

    def test_arrow_to_arm_that_did_not_run_fires(self):
        """🔴 «값이 없는 팔»에 화살표를 그리는 것도 위반이다 (A4의 자리)."""
        self.a1.ran = False
        bad = self.rule.audit([self.a0, self.a1, self.a3], [("A0", "A1")])
        self.assertTrue(bad)
        self.assertIn("돌지 않았다", bad[0])

    def test_zero_factor_pair_fires(self):
        twin = _arm("Z")
        twin.ran = True
        bad = self.rule.audit([self.a0, self.a1, twin], [("A0", "Z")])
        self.assertTrue(bad)


# ── M1 계약 가드 ────────────────────────────────────────────────────────

class TestM1Contract(unittest.TestCase):
    """🔴 «없는 계약을 채점하면 그 0은 결함이 아니다» — 실험 27의 규율이다."""

    def _ran(self, ins, text):
        a = _arm("Z", ins=ins)
        a.ran, a.text = True, text
        return a

    def test_session_instruction_arm_refuses_m1(self):
        a = self._ran("SESSION", "## 타임라인\n## 관계 변화\n## 다음에")
        with self.assertRaises(SA.ContractViolation):
            SA.m1_of(a)

    def test_session_arm_cell_is_not_a_number(self):
        """표에 `0/3`이 찍히면 그 0이 «못 지켰다»로 읽힌다."""
        a = self._ran("SESSION", "아무 표제도 없다")
        self.assertEqual(SA.m1_cell(a), "해당 없음")

    def test_p4_arm_is_scored(self):
        """오발화 대조 — 계약이 있는 팔은 조용히 채점된다."""
        a = self._ran("P4", "## 타임라인\n## 관계 변화\n## 다음에")
        hit, tot, _ = SA.m1_of(a)
        self.assertEqual((hit, tot), (3, 3))

    def test_p4_arm_missing_headings_is_a_real_zero(self):
        a = self._ran("P4", "표제가 없다")
        self.assertEqual(SA.m1_of(a)[0], 0)


# ── 프롬프트 조립 앵커 ──────────────────────────────────────────────────

class TestAssemblyAnchor(unittest.TestCase):
    """🔴 프로덕션이 만드는 프롬프트와 **바이트 동일**해야 A0이 실험 27의 팔이다."""

    @classmethod
    def setUpClass(cls):
        cls.sums, _meta = SA.round_summaries()
        cls.prod = SA.capture_production_prompt(cls.sums)   # ollama 호출 0회

    def _mine(self, **over):
        k = over.get("k", len(self.sums))
        budget = over.get("budget", summarize.LIFETIME_BUDGET_TOKENS)
        blocks = SA.summary_blocks(self.sums, len(self.sums))
        return SA.assemble(summarize.P4_TEMPLATE.format(budget=budget),
                           summarize._LIFETIME_MATERIAL_HEADER.format(k=k),
                           blocks)

    def test_assembly_is_byte_identical(self):
        self.assertEqual(self._mine(), self.prod)

    def test_budget_mutation_is_caught(self):
        self.assertNotEqual(self._mine(budget=300), self.prod)

    def test_header_count_mutation_is_caught(self):
        self.assertNotEqual(self._mine(k=len(self.sums) - 1), self.prod)

    def test_block_separator_mutation_is_caught(self):
        mut = (summarize.P4_TEMPLATE.format(
            budget=summarize.LIFETIME_BUDGET_TOKENS) + "\n\n"
            + summarize._LIFETIME_MATERIAL_HEADER.format(k=len(self.sums))
            + "\n" + "\n".join(SA.summary_blocks(self.sums, len(self.sums)))
            + SA.TAIL)
        self.assertNotEqual(mut, self.prod)

    def test_tail_is_shared_by_every_arm(self):
        """꼬리표는 요인이 아니다 — 팔마다 갈면 네 번째 것이 함께 움직인다."""
        self.assertTrue(self.prod.endswith(SA.TAIL))

    def test_capture_calls_no_ollama(self):
        """🔴 앵커 뽑기가 ollama를 부르면 «생성 0건»이 거짓말이 된다."""
        called = []

        def _boom(*a, **k):
            called.append(1)
            raise AssertionError("앵커 뽑기가 ollama를 불렀다")

        orig = summarize.llm.raw_generate
        summarize.llm.raw_generate = _boom
        try:
            SA.capture_production_prompt(self.sums)
        except AssertionError:
            pass                      # 아래 단언이 그 사실을 이름으로 적는다
        finally:
            summarize.llm.raw_generate = orig
        self.assertEqual(called, [], "앵커 뽑기가 ollama를 불렀다")


# ── 창 예산 가드 ────────────────────────────────────────────────────────

class TestWindowGuard(unittest.TestCase):

    def test_small_prompt_fits(self):
        """오발화 대조 — 창에 한참 못 미치는 팔에는 울지 않는다."""
        self.assertTrue(SA.window_fits(100)[0])

    def test_huge_prompt_is_excluded(self):
        self.assertFalse(SA.window_fits(100000)[0])

    def test_boundary_is_inclusive_and_moves_with_headroom(self):
        ctx, head = 8192, 1024
        self.assertTrue(SA.window_fits(ctx - head, ctx=ctx, headroom=head)[0])
        self.assertFalse(SA.window_fits(ctx - head + 1, ctx=ctx,
                                        headroom=head)[0])

    def test_headroom_is_actually_subtracted(self):
        """여유가 0이면 통과하는 프롬프트가, 여유를 주면 제외돼야 한다."""
        self.assertTrue(SA.window_fits(8000, ctx=8192, headroom=0)[0])
        self.assertFalse(SA.window_fits(8000, ctx=8192, headroom=1024)[0])

    def test_estimator_uses_the_recorded_regression(self):
        """🔴 새 상수를 고르지 않았다 — ADR-016 §정직 6의 값 그대로다."""
        self.assertAlmostEqual(SA.TOK_PER_CHAR, 0.7189)
        self.assertEqual(SA.TOK_INTERCEPT, 8)
        self.assertEqual(SA.est_tokens("a" * 1000), round(718.9 + 8))

    def test_the_same_prompt_splits_across_the_two_windows(self):
        """🆕 🔴 A4의 추정치가 **두 창에서 다른 답**을 받아야 한다.

        한 창에서만 보면 «원래 돌았던 것 아닌가»를 다음 사람이 못 묻는다.
        """
        est = 12809                       # 실험 28이 실측 없이 적어 둔 추정치
        self.assertFalse(SA.window_fits(est, ctx=SA.PROD_NUM_CTX)[0])
        self.assertTrue(SA.window_fits(est, ctx=SA.BIG_NUM_CTX)[0])

    def test_big_window_leaves_generation_headroom(self):
        """창을 «딱 맞게» 고르면 출력이 잘린다 — 여유가 실제로 남는가."""
        self.assertGreaterEqual(SA.BIG_NUM_CTX - 12809, SA.GEN_HEADROOM_TOK)


# ── 🆕 창 복원 가드 (G16) ───────────────────────────────────────────────

class TestWindowRestore(unittest.TestCase):
    """
    🔴 **프로덕션 전역을 바꿔 둔 채 끝나면 안 된다.** `prototype/llm.py`는
    무변경이고, 팔별 창은 `use_window()`가 블록 동안만 준다.
    """

    def tearDown(self):
        llm.LLM_NUM_CTX = SA.PROD_NUM_CTX

    def test_inside_the_block_the_window_is_the_requested_one(self):
        with SA.use_window(SA.BIG_NUM_CTX):
            self.assertEqual(llm.LLM_NUM_CTX, SA.BIG_NUM_CTX)

    def test_normal_exit_restores(self):
        with SA.use_window(SA.BIG_NUM_CTX):
            pass
        self.assertEqual(llm.LLM_NUM_CTX, SA.PROD_NUM_CTX)
        self.assertEqual(SA.assert_prod_window(), SA.PROD_NUM_CTX)

    def test_exception_exit_restores(self):
        """🔴 `finally`가 없으면 여기서 샌다 — 생성은 실제로 터진다(정지 여덟 번)."""
        with self.assertRaises(RuntimeError):
            with SA.use_window(SA.BIG_NUM_CTX):
                raise RuntimeError("생성이 터진 척한다")
        self.assertEqual(llm.LLM_NUM_CTX, SA.PROD_NUM_CTX)

    def test_nested_blocks_restore_to_the_outer_value(self):
        with SA.use_window(SA.BIG_NUM_CTX):
            with SA.use_window(2048):
                self.assertEqual(llm.LLM_NUM_CTX, 2048)
            self.assertEqual(llm.LLM_NUM_CTX, SA.BIG_NUM_CTX)
        self.assertEqual(llm.LLM_NUM_CTX, SA.PROD_NUM_CTX)

    def test_guard_fires_when_restore_is_skipped(self):
        """심은 위반 — 복원을 빼면 가드가 **터져야** 한다."""
        with SA.use_window(SA.BIG_NUM_CTX, restore=False):
            pass
        with self.assertRaises(SA.WindowNotRestored):
            SA.assert_prod_window()

    def test_prod_default_is_pinned_at_import(self):
        """🔴 가드가 전역을 다시 읽으면 언제나 «같다»가 나온다 — 그래서 박아 둔다."""
        with SA.use_window(SA.BIG_NUM_CTX):
            self.assertNotEqual(llm.LLM_NUM_CTX, SA.PROD_NUM_CTX)
            with self.assertRaises(SA.WindowNotRestored):
                SA.assert_prod_window()

    def test_llm_module_default_is_untouched_after_import(self):
        """G16 — 이 파일을 수입한 것만으로 프로덕션 기본값이 움직이면 안 된다."""
        self.assertEqual(llm.LLM_NUM_CTX, 8192)


# ── 🆕 절단 자국 (U9) ───────────────────────────────────────────────────

class TestTruncationFootprint(unittest.TestCase):
    """U9가 세 척도에서 실측한 `num_ctx/2 + 2`. **판정이 아니라 눈금이다.**"""

    def test_the_three_measured_scales(self):
        for ctx, foot in ((512, 258), (2048, 1026), (8192, 4098)):
            with self.subTest(ctx=ctx):
                self.assertEqual(SA.truncation_footprint(ctx), foot)

    def test_a4s_measurement_must_clear_the_footprint(self):
        """🔴 16,384 창의 자국은 8,194 tok이다 — A4의 실측이 그것과 같으면
        «잘렸을 수 있다»이고, 그때 숫자를 못 쓴다."""
        self.assertEqual(SA.truncation_footprint(SA.BIG_NUM_CTX), 8194)


# ── 사본 금지 (F12) ────────────────────────────────────────────────────

class TestNoCopies(unittest.TestCase):
    """🔴 채점기·상수를 **복사하지 않았는가.** 사본은 «같은 이름의 다른 자»다."""

    def test_no_local_scorer(self):
        for name in dir(SA):
            self.assertFalse(name.startswith("survived_"),
                             f"채점기 사본 «{name}»이 있다 — F12")

    def test_turns_per_session_comes_from_experiment_27(self):
        self.assertIs(SA.TURNS_PER_SESSION, SP.TURNS_PER_SESSION)

    def test_templates_come_from_production(self):
        """지시 문자열을 옮겨 적으면 프롬프트가 바뀔 때 이 실험이 옛 것을 잰다."""
        with open(os.path.join(HERE, "summary_ablation.py"),
                  encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("아래 대화 전체를 다시 요약하라", src)
        self.assertNotIn("이번 세션 요약을 3문장 이내로 써라", src)

    def test_production_file_is_not_imported_by_copy(self):
        self.assertIs(SA.SP, SP)


if __name__ == "__main__":
    unittest.main(verbosity=2)
