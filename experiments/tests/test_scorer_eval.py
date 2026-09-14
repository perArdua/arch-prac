# -*- coding: utf-8 -*-
"""
test_scorer_eval.py — `scorer_eval.py`의 **검사들이 실제로 발화하는지** 본다.

## 이 파일이 시험하는 것

숫자가 아니다. `scorer_eval.py`가 매 실행 다시 뽑는 값(92.3% · 66.7% · …)을 여기
박아 두면 **같은 값을 두 곳에 적는 것**이고, 그것이 이 저장소가 `run_all.py`를 만든
이유다(단일 출처). 여기서 보는 것은 **규율이 코드인가**다:

  · 분할이 라벨을 **볼 수 없는가** (시그니처와 불변성)
  · `?`가 분모에 들어오면 **터지는가**
  · 홀드아웃을 두 번 열면 **잡히는가**
  · 1판 폐기 사유가 파일에서 **다시 세어지는가**
  · 🆕 **얼린 `survived_v2`가 옛 결함을 아직 재현하는가** — 결함이 있었다는 증거다
    (이 시험의 옛 이름은 `test_root_overlap_flaw_is_still_there`였고, 서수 수리가
     그 결함을 닫았다. **지우지 않고 고정물로 바꿨다.**)

⚠️ `python -B`로 돌려라. 낡은 `.pyc`가 변이를 살려 준 전례가 있다(실험 25 §G).
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

sys.path.insert(0, os.path.join(HERE, "..", "prototype"))

import scorer_eval as SE                                     # noqa: E402
import scoring                                               # noqa: E402


class TestLabelMerge(unittest.TestCase):
    """라벨 합치기 — **32개이고, 1판은 안 들어온다.**"""

    def test_merged_is_32(self):
        labels, source = SE.load_labels()
        self.assertEqual(len(labels), SE.N_EXPECT)
        self.assertEqual(set(source.values()), set(SE.LABELS_USED))

    def test_first_edition_is_not_merged(self):
        """🔴 1판의 쌍이 합쳐진 집합에 **값으로도** 새어 들어오지 않는다."""
        labels, source = SE.load_labels()
        self.assertNotIn(SE.LABELS_DISCARDED, set(source.values()))
        d = SE.load_discarded()
        self.assertEqual(len(d), 24)          # 파일은 그대로 있다 — 기록이다
        # 1판에만 있는 라벨값(`?` 8건)이 합친 집합의 그 쌍에 그대로 오지 않았다
        differing = [p for p in d if p in labels and d[p] != labels[p]]
        self.assertTrue(differing, "1판과 합친 집합이 전부 같다 — 합쳐졌을 수 있다")

    def test_discard_reason_recomputes(self):
        """폐기 사유가 **산문이 아니라 파일에서** 다시 세어진다: 먼 대조 4/4가 `Y`."""
        d = SE.load_discarded()
        meta = SE.load_meta()
        far = [p for p in d if meta.get(p, {}).get("kind") == SE.DISCARD_KIND]
        self.assertEqual(len(far), 4)
        self.assertEqual([d[p] for p in far], [SE.DISCARD_LABEL] * 4)

    def test_duplicate_pair_id_explodes(self):
        """겹치는 쌍 id는 **덮어쓰지 않고 터진다** — n이 조용히 달라지는 것을 막는다."""
        real = SE.LABELS_USED
        try:
            SE.LABELS_USED = (real[0], real[0])   # 같은 파일 두 번
            with self.assertRaises(AssertionError):
                SE.load_labels()
        finally:
            SE.LABELS_USED = real


class TestSplitIsBlind(unittest.TestCase):
    """사전 등록된 분할 — 🔴 **라벨도 유사도도 보지 않는다.**"""

    def test_matches_preregistered_file(self):
        labels, _ = SE.load_labels()
        tr, ho = SE.split_blind(list(labels))
        with open(os.path.join(HERE, "data", "LABEL_SPLIT.json"), encoding="utf-8") as f:
            rec = json.load(f)
        self.assertEqual(sorted(tr), sorted(rec["train"]))
        self.assertEqual(sorted(ho), sorted(rec["holdout"]))

    def test_invariant_to_labels(self):
        """라벨을 전부 뒤집어도 분할이 **바이트 그대로**다."""
        labels, _ = SE.load_labels()
        a = SE.split_blind(list(labels))
        flipped = {p: {"Y": "N", "N": "Y", "?": "?"}[v] for p, v in labels.items()}
        self.assertNotEqual(labels, flipped)
        b = SE.split_blind(list(flipped))
        self.assertEqual(a, b)

    def test_signature_takes_no_labels(self):
        """시그니처에 라벨이 없다 — **라벨을 볼 방법이 구조적으로 없다.**"""
        import inspect
        self.assertEqual(list(inspect.signature(SE.split_blind).parameters),
                         ["pair_ids"])

    def test_label_aware_split_collapses_the_gap(self):
        """
        🔴 **음성 대조 ⓐ.** 라벨을 보고 자르면 채점기 넷의 홀드아웃 값 **폭이
        절반 미만으로 무너진다** — 홀드아웃이 훈련의 복사본이 된다.

        🔴 **옛 조건은 «넷이 같은 수를 낸다»였고, 서수 수리가 그것을 깨뜨렸다.**
        축자가 오답 셋을 고치자 넷 중 셋이 100%가 되어 «전부 같다»가 성립하지
        않는다 — 변이는 여전히 홀드아웃을 복사본으로 만드는데도 그렇다. 그 조건은
        **채점기가 어디서 틀리는지에 매인 증상**이었다. 폭은 그렇지 않다.
        그리고 아래 **맹목 분할 대조**가 이 조건이 무조건 참이 아님을 보인다.
        """
        labels, _ = SE.load_labels()
        ev, su, _ = SE.load_material()
        pairs = {p: m for p, m in SE.load_meta().items() if p in labels}
        lit, _ = SE.literal_preds(pairs, ev, su)
        sims = {p: SE.load_meta()[p]["sim"] for p in labels}

        def holdout_values(tr_ids, ho_ids):
            out = []
            for (name, fn, needs_th) in SE.RULES[:4]:
                th, *_ = SE.choose_theta(fn, tr_ids, lit, sims, labels)
                hit, n, _ = SE.measure(fn, ho_ids, lit, sims, labels, th)
                out.append(round(100.0 * hit / n, 1))
            return out

        bad_tr, bad_ho = SE.split_by_label(list(labels), labels)
        mut = holdout_values([p for p in bad_tr if labels[p] != "?"],
                             [p for p in bad_ho if labels[p] != "?"])
        tr, ho = SE.split_blind(list(labels))
        blind = holdout_values([p for p in tr if labels[p] != "?"],
                               [p for p in ho if labels[p] != "?"])
        spread = (lambda xs: max(xs) - min(xs))
        self.assertLess(spread(mut), spread(blind) / 2,
                        f"폭이 안 무너졌다: 맹목 {blind} → 변이 {mut}")
        # 🔴 **오발화 대조:** 맹목 분할을 그대로 넣으면 이 조건은 **거짓**이다.
        self.assertFalse(spread(blind) < spread(blind) / 2,
                         "조건이 무조건 참이다 — 그것은 검사가 아니다")


class TestUnknownIsExcluded(unittest.TestCase):
    """`?`는 분자·분모에서 뺀다 (F20) — 그리고 **넣으면 터진다.**"""

    def setUp(self):
        self.labels, _ = SE.load_labels()
        self.scored = [p for p in self.labels if self.labels[p] != "?"]

    def test_one_unknown_and_31_scored(self):
        n_unknown, want = SE.check_counts(self.labels, self.scored)
        self.assertEqual(n_unknown, 1)
        self.assertEqual(want, 31)

    def test_counting_unknown_as_N_fires(self):
        """🔴 **음성 대조 ⓑ.** `?`→`N` 변이가 `check_counts`를 발화시킨다."""
        mutated = {p: ("N" if v == "?" else v) for p, v in self.labels.items()}
        with self.assertRaises(AssertionError):
            SE.check_counts(self.labels, list(mutated))

    def test_check_counts_reads_the_original_files(self):
        """
        🔴 검사가 **변이와 같은 출처**를 보면 검사가 아니다.

        변이된 dict를 원본 자리에도 넣으면 자기 자신과 일치해 통과한다 —
        그래서 `main`은 `load_labels()`의 결과를 원본으로 넘긴다.
        """
        mutated = {p: ("N" if v == "?" else v) for p, v in self.labels.items()}
        SE.check_counts(mutated, list(mutated))       # 같은 출처 → 통과한다
        with self.assertRaises(AssertionError):        # 원본을 보면 → 터진다
            SE.check_counts(self.labels, list(mutated))

    def test_measure_rejects_unknown_in_denominator(self):
        ev, su, _ = SE.load_material()
        pairs = {p: m for p, m in SE.load_meta().items() if p in self.labels}
        lit, _ = SE.literal_preds(pairs, ev, su)
        sims = {p: SE.load_meta()[p]["sim"] for p in self.labels}
        with self.assertRaises(AssertionError):
            SE.measure(SE.rule_literal, list(self.labels), lit, sims,
                       self.labels, 0.0)


class TestHoldoutOpenedOnce(unittest.TestCase):
    """«홀드아웃은 한 번만 본다»를 **셈으로** 만든다."""

    def test_single_open_is_clean(self):
        h = SE.Holdout(["P01", "P02"], budget=2)
        h.open("규칙 A")
        h.open("규칙 B")
        self.assertEqual(h.audit(), {})

    def test_second_open_is_caught(self):
        """같은 손잡이를 두 번 열면 잡힌다."""
        h = SE.Holdout(["P01", "P02"], budget=8)
        h.open("규칙 A")
        h.open("규칙 A")
        self.assertIn("규칙 A", h.audit())

    def test_renaming_the_handle_does_not_escape_the_budget(self):
        """
        🔴 **음성 대조 ⓒ의 핵심.** 손잡이 이름을 새로 지으면 «이름당 1회» 검사는
        조용하다 — 실제로 그렇게 통과한 실행이 있었고 그때 판정이 뒤집혔다.
        **총 접근 예산**이 그것을 잡는다.
        """
        h = SE.Holdout(["P01"], budget=3)
        for name in ("측정:A", "측정:B", "측정:C"):
            h.open(name)
        self.assertEqual(h.audit(), {}, "예산 안에서는 조용해야 한다")
        h.open("θ선택:A")                      # 이름이 새것이라 이름당 횟수는 1
        bad = h.audit()
        self.assertEqual({k: v for k, v in h.reads.items() if v > 1}, {})
        self.assertTrue(bad, "이름을 새로 지어 예산을 빠져나갔다 — 검사가 눈을 감았다")


class TestThetaFromTrainOnly(unittest.TestCase):
    """θ는 **훈련 유사도의 중점만** 후보로 본다 (G12)."""

    def test_grid_lies_inside_train_range(self):
        grid, xs = SE.theta_grid([0.30, 0.50, 0.70])
        self.assertEqual(grid, [0.40, 0.60])
        self.assertTrue(all(min(xs) < t < max(xs) for t in grid))

    def test_grid_ignores_values_not_given(self):
        """홀드아웃 값을 안 넘기면 격자에 **들어올 방법이 없다.**"""
        grid, _ = SE.theta_grid([0.30, 0.50])
        self.assertEqual(grid, [0.40])


class TestScorersAreNotCopies(unittest.TestCase):
    """축자는 `scoring`의 함수를 **그대로** 부른다 (F12)."""

    def test_literal_matches_the_scorer_directly(self):
        labels, _ = SE.load_labels()
        ev, su, _ = SE.load_material()
        pairs = {p: m for p, m in SE.load_meta().items() if p in labels}
        for fn in (scoring.survived_v2, scoring.survived_v3):
            lit, _ = SE.literal_preds(pairs, ev, su, fn)
            for pid, m in pairs.items():
                want = fn(su[m["session"]], [ev[m["event_id"]]])
                self.assertEqual(lit[pid], "Y" if want.survived else "N",
                                 f"{fn.__name__} {pid}")

    def test_default_scorer_is_v3(self):
        """🔴 기본값이 조용히 v2로 돌아가면 실험 26의 표가 옛 채점기를 찍는다."""
        import inspect
        sig = inspect.signature(SE.literal_preds)
        self.assertIs(sig.parameters["scorer"].default, scoring.survived_v3)

    def test_root_overlap_flaw_was_here_and_v2_still_reproduces_it(self):
        """
        🔴 **옛 이름은 `test_root_overlap_flaw_is_still_there`였다.**

        그 시험은 결함이 **아직 있다**를 초록으로 지키고 있었다. 서수 수리가 그것을
        고쳤으므로 시험은 빨개져야 맞다 — 그런데 **지우면 결함이 있었다는 증거가
        사라진다.** 그래서 지우지 않고 **고정물로 바꿨다:** 기록 채점기 `v2`가
        그 위양성을 **여전히 재현하고**, 수리본 `v3`이 그것을 고친다.

        `P14`는 «두 번째 면접»(E005)을 «세 번째 면접» 세션(S18)의 요약에 대고 묻는다.
        사람은 `N`. 겹친 어근이 `{면접, 번째}`뿐이라 v2는 `Y`라 답했다.
        """
        labels, _ = SE.load_labels()
        ev, su, _ = SE.load_material()
        pairs = {p: m for p, m in SE.load_meta().items() if p in labels}
        lit_v3, _ = SE.literal_preds(pairs, ev, su, scoring.survived_v3)
        lit_v2, _ = SE.literal_preds(pairs, ev, su, scoring.survived_v2)
        self.assertEqual(pairs["P14"]["event_id"], "E005")
        self.assertEqual(pairs["P14"]["session"], "S18")
        self.assertEqual(labels["P14"], "N")
        self.assertEqual(lit_v2["P14"], "Y", "v2가 결함을 재현하지 않는다"
                                             " — 얼린 채점기가 움직였다")
        self.assertEqual(lit_v3["P14"], "N", "v3이 서수 불일치를 못 잡는다")

    def test_v3_fixes_every_literal_error_v2_had(self):
        """수리 전/후를 **훈련·홀드아웃 나누기 전** 전체 32쌍에서 한 줄로 고정한다."""
        labels, _ = SE.load_labels()
        ev, su, _ = SE.load_material()
        pairs = {p: m for p, m in SE.load_meta().items() if p in labels}
        lit_v3, u3 = SE.literal_preds(pairs, ev, su, scoring.survived_v3)
        lit_v2, u2 = SE.literal_preds(pairs, ev, su, scoring.survived_v2)
        scored = [p for p in labels if labels[p] != "?"]
        e2 = sorted(p for p in scored if lit_v2[p] != labels[p])
        e3 = sorted(p for p in scored if lit_v3[p] != labels[p])
        self.assertEqual(e2, ["P12", "P14", "P15"])
        self.assertEqual(e3, [])
        self.assertEqual(u2, u3)      # 판정 불가 집합은 안 갈린다 — 분모가 같다


class TestRuleSemantics(unittest.TestCase):
    """규칙 다섯의 뜻이 이름과 같은가."""

    def test_and_or(self):
        self.assertEqual(SE.rule_and("Y", 0.9, 0.5), "Y")
        self.assertEqual(SE.rule_and("Y", 0.1, 0.5), "N")
        self.assertEqual(SE.rule_or("N", 0.9, 0.5), "Y")
        self.assertEqual(SE.rule_or("N", 0.1, 0.5), "N")

    def test_abstain_returns_none_on_disagreement(self):
        self.assertIsNone(SE.rule_abstain("Y", 0.1, 0.5))
        self.assertIsNone(SE.rule_abstain("N", 0.9, 0.5))
        self.assertEqual(SE.rule_abstain("Y", 0.9, 0.5), "Y")

    def test_abstain_shrinks_the_denominator(self):
        """보류는 **분모에서 빠진다** — 커버리지를 옆에 안 찍으면 안 보인다 (G15)."""
        lit = {"a": "Y", "b": "N"}
        sims = {"a": 0.1, "b": 0.1}
        labels = {"a": "Y", "b": "N"}
        hit, n, held = SE.measure(SE.rule_abstain, ["a", "b"], lit, sims,
                                  labels, 0.5)
        self.assertEqual((hit, n, held), (1, 1, 1))


class TestEmbeddingCache(unittest.TestCase):
    """캐시가 있으면 **호출 0회**로 돈다 — 그 사실을 관측으로 만든다."""

    def test_all_texts_are_cached(self):
        import embedding
        ev, su, _ = SE.load_material()
        texts = list(ev.values()) + list(su.values())
        self.assertEqual(embedding.missing_keys(texts), [],
                         "임베딩 캐시 미스가 있다 — 라이브 호출이 일어난다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
