# -*- coding: utf-8 -*-
"""
test_precision.py — 질문별 정밀도 지표의 **해석 규칙**을 고정한다. (단계 0-g)

`retrieved` 집합을 **손으로 만든다.** 그래서 이 시험은 하니스의 현재 파라미터와
무관하게 규칙 자체를 잡는다.

⚠️ **이 시험이 탐지할 수 없는 것:** `hard_misinjection`이 실제 하니스에서
**항등 0**인지 여부. 손으로 만든 집합은 언제나 원하는 값을 낼 수 있기 때문이다.
그 탐지는 `precision.py`가 찍는 **4셀 × 5문항 = 20개 값**이 한다.
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
import precision as P                                      # noqa: E402

_, LEDGER, QS = P.load()
KEY = P.key_index(LEDGER)
Q = {q["id"]: q for q in QS}


def _row(**kw):
    """
    🆕 단계 1 — `run_cell`이 만드는 행의 **전체 모양**을 한 곳에 둔다.

    필드가 늘 때 `.get(기본값)`으로 때우지 않는 이유: 그러면 실제 실행에서 필드가
    빠져도 조용히 기본값이 들어가고, 그것이 이 저장소가 반복해서 겪은 "조용한 0"이다.
    시험 픽스처가 대신 아프면 된다.
    """
    r = dict(id="Q01", mis=1, n_ret=2, prec=0.5, ev_hit=0, ev_tot=2,
             gate=True, top1=0, tie_n=1, tie_s=0.4)
    r.update(kw)
    return r


def s(*ids):
    """대장 id들을 **색인에 실제로 들어가는 문자열**(text)로 푼다."""
    out = set()
    for i in ids:
        f = next((x for x in LEDGER["facts"] if x["id"] == i), None)
        e = next((x for x in LEDGER["events"] if x["id"] == i), None)
        out.add((f or e)["text"])
    return out


class TestDistractorResolution(unittest.TestCase):
    """`distractor` 필드는 대부분 **산문**이다. 문자열 매칭하면 안 된다."""

    def test_q04_literal_resolves_to_f002(self):
        """
        🔄 rev5 — Q04의 필드 값은 `'마케팅 회사 대리'`, 즉 **`F002.object`**다.
        색인에는 `F002.text`가 들어가므로 **리터럴 매칭은 영원히 0**이다.
        """
        self.assertEqual(P.distractor_ids(Q["Q04"]), {"F002"})
        self.assertEqual(P.allowed_strings({"F002"}, KEY),
                         {"마케팅 회사 대리", "지우는 마케팅 회사 대리"})

    def test_q04_hard_via_f002_text(self):
        # F002.text가 주입됐고 근거 F021은 안 왔다 → 근거를 **대체한** 유도
        self.assertEqual(P.hard_misinjection(Q["Q04"], s("F002"), KEY), 1)

    def test_q24_x_id_path_can_actually_fail(self):
        """
        X-id 경로가 **실제로 발화하는지** 본다 (§5.1 필수 케이스).

        필드 원문은 `"코코 (X003 — 친구 민지네 고양이)"`라는 산문이다.
        그걸 그대로 `in` 비교하면 이 단언은 영원히 0이 되고, 지표는
        0-a·F19가 죽인 것과 **정확히 같은 종류의 항등적 지표**가 된다.
        """
        self.assertEqual(P.distractor_ids(Q["Q24"]), {"X003"})
        self.assertIn("친구 민지네 고양이 이름은 코코",
                      P.allowed_strings({"X003"}, KEY))
        # X003만 왔고 근거 F001은 안 왔다 → hard = 1 (**실패할 수 있는 구성**)
        self.assertEqual(P.hard_misinjection(Q["Q24"], s("X003"), KEY), 1)

    def test_q23_q25_prose_resolve_to_ids(self):
        self.assertEqual(P.distractor_ids(Q["Q23"]), {"X001", "X002"})
        self.assertEqual(P.distractor_ids(Q["Q25"]), {"X005"})

    def test_non_x_prefix_raises(self):
        """`E`·`D` 접두사가 들어오면 **조용히 빠지지 않고 터진다.**"""
        for bad in ("E003", "D001"):
            with self.assertRaises(ValueError) as cm:
                P.distractor_ids({"id": "QX", "distractor": f"뭔가 ({bad})"})
            self.assertIn(bad, str(cm.exception))

    def test_no_id_at_all_raises(self):
        with self.assertRaises(ValueError):
            P.distractor_ids({"id": "QY", "distractor": "그냥 산문이다"})


class TestAndRule(unittest.TestCase):
    """
    🔄 rev5 — AND 규칙 일반화. Q26(`X004 ∈ evidence`)이 **특수 사례**가 된다.

        hard(q) = 1 iff (distractor ∈ retrieved) AND ¬all(evidence ∈ retrieved)
    """

    def test_q26_distractor_with_full_evidence_is_not_hard(self):
        # X004가 주입돼도 F003이 함께 있으면 유도가 아니다
        self.assertEqual(P.hard_misinjection(Q["Q26"], s("X004", "F003"), KEY), 0)

    def test_q26_distractor_without_full_evidence_is_hard(self):
        # X004만 왔다 — F003이 빠졌으므로 "근거를 대체한 유도"다
        self.assertEqual(P.hard_misinjection(Q["Q26"], s("X004"), KEY), 1)

    def test_q26_evidence_only_is_not_hard(self):
        # distractor가 애초에 안 왔다
        self.assertEqual(P.hard_misinjection(Q["Q26"], s("F003"), KEY), 0)

    def test_empty_retrieved_is_not_hard(self):
        self.assertEqual(P.hard_misinjection(Q["Q26"], set(), KEY), 0)


class TestEvidenceRecall(unittest.TestCase):
    """
    🆕 U2 (단계 1 작업 1) — `evidence_recall(검색경로)`의 정의.

    핵심은 **공집합이 0**이라는 것이다. 매크로 정밀도는 같은 입력에 1.0을 주고,
    그 차이가 결정 A4의 전부다 — *"아무것도 안 꺼내기"*가 만점이 아니게 된다.
    """

    def test_all_evidence_retrieved(self):
        q = Q["Q26"]                                    # evidence = F003, X004
        hit, tot = P.evidence_recall_via_retrieval(q, s(*q["evidence"]), KEY)
        self.assertEqual((hit, tot), (tot, 2))
        self.assertEqual(hit / tot, 1.0)

    def test_half_evidence_retrieved(self):
        q = Q["Q26"]
        hit, tot = P.evidence_recall_via_retrieval(q, s("F003"), KEY)
        self.assertEqual((hit, tot), (1, 2))
        self.assertEqual(hit / tot, 0.5)

    def test_empty_retrieved_is_zero_not_one(self):
        """⚠️ 같은 입력에서 매크로 정밀도는 **1.0**이다. 두 지표를 쌍으로 읽는 이유."""
        q = Q["Q26"]
        self.assertEqual(P.evidence_recall_via_retrieval(q, set(), KEY), (0, 2))
        self.assertEqual(P.score_question(q, set(), KEY)[1], 1.0)

    def test_denominator_counts_only_indexed_evidence(self):
        """색인에 없는 근거(D001)는 분모에 못 들어간다 — `partition`이 이미 뺐다."""
        q = dict(Q["Q26"], evidence=list(Q["Q26"]["evidence"]) + ["D001"])
        self.assertEqual(P.evidence_recall_via_retrieval(q, set(), KEY)[1], 2)


class TestTop1AndTies(unittest.TestCase):
    """🆕 U4-b (단계 1 작업 3) — 1등만 읽는 지표와 그 동점 병기."""

    def test_top1_reads_only_rank_one(self):
        q = Q["Q13"]                                    # evidence = F021
        ok = next(iter(P.allowed_strings(q["evidence"], KEY)))
        bad = next(iter(P.allowed_strings({"X003"}, KEY)))
        self.assertEqual(P.top1_misinjection(q, [ok, bad], KEY), 0)
        self.assertEqual(P.top1_misinjection(q, [bad, ok], KEY), 1)

    def test_empty_is_none_not_zero(self):
        """검색 0건은 **0이 아니라 정의 안 됨**이다 — 0이면 분자에 들어간다."""
        self.assertIsNone(P.top1_misinjection(Q["Q13"], [], KEY))

    def test_tie_count_uses_exact_equality(self):
        """
        1e-17 차이는 동점이 **아니다** — `sort`가 보는 기준과 같아야 한다.
        뭉뚱그리면 *"rowid가 정했다"*와 *"점수가 정했다"*가 섞인다.
        """
        hits = [(0.4, None), (0.4, None), (0.4, None), (0.32, None)]
        self.assertEqual(P.tie_rank1(hits), (3, 0.4))
        # `nextafter`로 **표현 가능한 최소 차**를 만든다. `0.4 - 1e-17`은 0.4의
        # ULP(≈5.6e-17)보다 작아 float에서 그냥 0.4다 — 그러면 시험이 아무것도 안 한다.
        just_below = math.nextafter(0.4, 0)
        self.assertNotEqual(just_below, 0.4)
        self.assertEqual(P.tie_rank1([(0.4, None), (just_below, None)])[0], 1)
        self.assertEqual(P.tie_rank1([]), (0, None))

    def test_tie_format_is_the_planned_one(self):
        """형식(G15): `Q05 — 1·2·3위 s=0.4`."""
        self.assertEqual(
            P._fmt_tie(dict(id="Q05", tie_n=3, tie_s=0.4)),
            "Q05 — 1·2·3위 s=0.4")


class TestScoring(unittest.TestCase):

    def test_object_text_union_is_used(self):
        """
        단계 0-a의 수리가 **여기서 값을 갖는다.** `object != text`인 사실이
        자기 근거로 왔을 때 오주입으로 세면 안 된다 (Q13 근거 = F021).
        """
        mis, prec = P.score_question(Q["Q13"], s("F021"), KEY)
        self.assertEqual(mis, 0)
        self.assertEqual(prec, 1.0)

    def test_off_evidence_item_counts_as_misinjection(self):
        mis, prec = P.score_question(Q["Q13"], s("F021", "X003"), KEY)
        self.assertEqual(mis, 1)
        self.assertAlmostEqual(prec, 0.5)

    def test_degenerate_zero_retrieved_scores_perfect(self):
        """⚠️ Critic M4 — 아무것도 안 꺼내면 정밀도 1.0이다. 방향 검정에서 뺀다."""
        mis, prec = P.score_question(Q["Q13"], set(), KEY)
        self.assertEqual((mis, prec), (0, 1.0))


class TestPartition(unittest.TestCase):
    """분모는 26이 아니라 18이다 (🔴 rev3)."""

    def setUp(self):
        self.scored, self.excluded = P.partition(QS, KEY)

    def test_eighteen_of_twentysix(self):
        self.assertEqual(len(QS), 26)
        self.assertEqual(len(self.scored), 18)
        self.assertEqual(len(self.excluded), 8)

    def test_exact_excluded_set(self):
        self.assertEqual(sorted(i for i, _ in self.excluded),
                         ["Q11", "Q14", "Q17", "Q18", "Q19", "Q20", "Q21", "Q22"])

    def test_q11_excluded_because_debt_not_indexed(self):
        # D001은 debt라 `key_of`에 색인되지 않는다 — `evidence` 키는 있는데도 제외다
        self.assertEqual(Q["Q11"]["evidence"], ["D001"])
        self.assertNotIn("D001", KEY)
        self.assertIn(("Q11", "unindexed D001"), self.excluded)

    def test_header_is_pinned(self):
        """헤더는 **무조건 출력**된다. 조용한 제외를 막는 장치다."""
        self.assertEqual(
            f"scored {len(self.scored)}/{len(QS)} · excluded: "
            f"Q11(debt D001), Q14,Q17-Q22(no evidence key)",
            P.EXPECTED_HEADER)


class TestLoudFailures(unittest.TestCase):
    """
    🔴 rev7 (Verifier) — **조용한 0**을 두 군데서 막는다.

    둘 다 오늘은 발화하지 않는다. 그래서 시험이 필요하다 — 발화하는 날에는
    이미 늦고, 그때의 증상은 "값이 0"이라 정상과 구별되지 않는다.
    """

    def test_unindexed_evidence_raises_naming_the_id(self):
        """
        `all([])`은 `True`다. evidence를 조용히 걸러내면 **검사할 것이 없었다**가
        **동반 검색됐다**와 같은 값(hard=0)을 낸다. D001(debt)은 색인에 없는
        실제 id다 — 단계 3+가 `debt`를 색인하면 이 경로가 열린다.
        """
        self.assertNotIn("D001", KEY)
        q = dict(Q["Q24"], evidence=["F001", "D001"])
        with self.assertRaises(ValueError) as cm:
            P.hard_misinjection(q, s("X003"), KEY)
        self.assertIn("D001", str(cm.exception))

    def test_dispersion_failure_is_not_exit_zero(self):
        """
        분산이 죽은 가짜 `cells`를 만들어 판정만 태운다 (4셀 스윕은 돌리지 않는다).
        모든 셀의 값이 같으면 `spread = 0`이고 움직이는 문항도 없다.
        """
        cells = {(g, th): ([_row()], [], False)
                 for g in ("G0", "G3") for th in (0.15, 0.05)}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            alive = P.dispersion_report(cells)
        self.assertFalse(alive)                 # main()이 이 값을 exit 1로 바꾼다
        self.assertIn("죽은 지표", buf.getvalue())

    def test_dispersion_success_path_still_alive(self):
        """대칭 확인 — 값이 움직이면 True다. 위 시험이 항상 False면 무의미하다."""
        cells = {}
        for i, (g, th) in enumerate([("G0", 0.15), ("G0", 0.05),
                                     ("G3", 0.15), ("G3", 0.05)]):
            cells[(g, th)] = ([_row(mis=i, ev_hit=i, top1=i % 2)], [], False)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(P.dispersion_report(cells))

    def test_one_dead_metric_fails_the_whole_report(self):
        """
        🆕 단계 1 작업 6 — **하나라도 FAIL이면 False**다. 넷 중 셋만 살아 있어도
        통과시키면 죽은 지표가 격자 축에 남는다 (G14).
        """
        cells = {}
        for i, (g, th) in enumerate([("G0", 0.15), ("G0", 0.05),
                                     ("G3", 0.15), ("G3", 0.05)]):
            # `mis`·`pooled`·`top1`은 움직이고 `ev_hit`만 상수다.
            cells[(g, th)] = ([_row(mis=i, ev_hit=1, top1=i % 2)], [], False)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertFalse(P.dispersion_report(cells))
        self.assertIn(P.RECALL_NAME, buf.getvalue().split("죽은 지표")[-1])

    def test_dispersion_never_reads_base_cell(self):
        """
        🔴 **G14 rev2 — 분산 판정은 `BASE_CELL`을 읽지 않는다.**

        기준셀이 아예 없는 `cells`로 태운다. 예전 구현은 여기서 `KeyError`로
        죽었다 — 그것이 곧 *"라벨을 고치면 게이트 값이 움직인다"*의 기계적 형태다.
        방향 검정 절은 `direction_test()`로 떼어냈고, **그쪽만** 기준셀을 읽는다.
        """
        cells = {("G0", 0.15): ([_row(mis=0)], [], False),
                 ("G0", 0.05): ([_row(mis=1, ev_hit=1, top1=1)], [], False)}
        self.assertNotIn(P.BASE_CELL, cells)
        with contextlib.redirect_stdout(io.StringIO()):
            P.dispersion_report(cells)          # KeyError가 나면 안 된다
        with self.assertRaises(KeyError):       # 방향 검정은 반대로 읽는다
            with contextlib.redirect_stdout(io.StringIO()):
                P.direction_test(cells)


if __name__ == "__main__":
    unittest.main()
