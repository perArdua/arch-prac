# -*- coding: utf-8 -*-
"""
test_summary_prototype.py — `summary_prototype.py`의 **검사들이 발화하는지** 본다.

## 이 파일이 시험하는 것

숫자가 아니다. M1 3/3 · M2 8/10 · M3 15/28 · M4 −8은 그 스크립트가 매 실행 다시
뽑는 값이고, 여기 박아 두면 **같은 값을 두 곳에 적는 것**이다(`run_all.py`가 있는
이유). 여기서 보는 것은 **규율이 코드인가**다:

  · §3.1의 «분모 숫자만 적힌 열» 금지가 **실제로 열을 막는가**
  · §3.3 ②의 «M2 열에 화살표 금지»가 **잡히는가**
  · X6의 «두 값에 두 이름»이 **같은 이름을 거부하는가** (열도 행도)
  · §3.4가 지정한 `k<2` 가드가 **양쪽으로 갈리는가** — 심으면 터지고 정상에서는 조용
  · 기준선 앵커가 **항목 집합을 흔들면 재현 실패로 잡는가**
  · 🔴 **이 라운드가 산 결함이 고정물이 됐다** — `E004`의 서수 위음성.
    누군가 `survived_v3`을 고치면 그 이름의 기록값(실험 26의 13/13·18/18)이
    다른 채점기의 수가 되므로, **여기서 먼저 빨개져야 한다.**

⚠️ `python -B`로 돌려라. 낡은 `.pyc`가 변이를 살려 준 전례가 있다(실험 25 §G).
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "prototype"))

import summary_prototype as SP                               # noqa: E402
import scoring                                               # noqa: E402
import summarize                                             # noqa: E402


def _ev(eid, sess, text):
    return {"id": eid, "at": {"session": sess}, "text": text}


# ── §3.1 · §3.3 — 표 규율 ───────────────────────────────────────────────

class TestTitleRule(unittest.TestCase):
    """제목 규율. **정상에 조용하고 위반에 운다** — 두 방향을 다 본다."""

    def setUp(self):
        self.rule = SP.TitleRule()

    def test_named_item_set_is_quiet(self):
        """오발화 대조 — 이름이 붙은 열에는 울지 않는다."""
        cols = [SP.Col("M2 사건", "events 10", "S01–S24", "v2"),
                SP.Col("M4 사실 누출", "facts 12 (판정불가 1 → 11)",
                       "S01–S24", "v3")]
        self.assertEqual(self.rule.audit(cols), [])

    def test_bare_denominator_fires_in_three_shapes(self):
        """🔴 «분모만»의 모양이 하나가 아니다. 셋 다 물어야 규칙이다."""
        for planted in ("10", "/10", " 8 / 11 ", "11", "0/10"):
            with self.subTest(planted=planted):
                bad = self.rule.audit(
                    [SP.Col("M2 사건", planted, "S01–S24", "v2")])
                self.assertTrue(bad, f"«{planted}»를 통과시켰다")
                self.assertTrue(bad[0].startswith("①"))

    def test_empty_item_set_fires(self):
        bad = self.rule.audit([SP.Col("M2 사건", "", "S01–S24", "v2")])
        self.assertTrue(any(b.startswith("①") for b in bad))

    def test_missing_scorer_name_fires(self):
        """§3.3 ④ — 자가 바뀐 것은 채점기 이름이 없으면 표에 안 남는다."""
        bad = self.rule.audit([SP.Col("M2 사건", "events 10", "S01–S24", "")])
        self.assertTrue(any(b.startswith("④") for b in bad))

    def test_arrow_on_different_item_set_fires(self):
        """§3.3 ② — M2 열에 기준선 화살표를 붙이면 잡힌다."""
        bad = self.rule.audit([SP.Col(
            "M2 사건", "events 10", "S01–S24", "v2",
            same_item_set_as_baseline=False, arrow=("행", "6/10", "8/10"))])
        self.assertTrue(any(b.startswith("③") for b in bad))

    def test_arrow_on_same_item_set_is_quiet(self):
        """오발화 대조 — 자격이 있는 열의 화살표는 위반이 아니다."""
        self.assertEqual(self.rule.audit([SP.Col(
            "기준선 재채점", "혼합 8사실+3사건", "S01–S12", "v2",
            same_item_set_as_baseline=True,
            arrow=("행", "6/10", "6/10"))]), [])

    def test_same_name_two_sets_fires(self):
        """X6 · U1-b — 같은 이름이 두 집합/구간을 가리키면 잡힌다."""
        bad = self.rule.audit([
            SP.Col("M2 상한", "events 10", "S01–S12", "v2"),
            SP.Col("M2 상한", "events 10", "S01–S24", "v2")])
        self.assertTrue(any(b.startswith("②") for b in bad))

    def test_two_names_two_sets_is_quiet(self):
        """오발화 대조 — 이름을 갈라 두면 조용하다. 그것이 U1-b의 요구다."""
        self.assertEqual(self.rule.audit([
            SP.Col("M2 기록물 상한", "events 10", "S01–S12", "v2"),
            SP.Col("M2 이 라운드 재료 상한", "events 10", "S01–S24", "v2")]), [])

    def test_row_labels_duplicate_fires(self):
        bad = self.rule.audit_rows(["M2 상한", "M2 상한"])
        self.assertTrue(any(b.startswith("⑤") for b in bad))

    def test_row_label_bare_number_fires(self):
        bad = self.rule.audit_rows(["4/10"])
        self.assertTrue(any(b.startswith("⑤") for b in bad))

    def test_row_labels_distinct_is_quiet(self):
        self.assertEqual(self.rule.audit_rows(
            ["기록물 상한 (12세션)", "이 라운드 재료 상한 (24세션)"]), [])


# ── §3.4의 실행 검사 — `k<2` 가드 ───────────────────────────────────────

class TestM3Guard(unittest.TestCase):
    """
    🔴 §3.4가 `grep -c "판정 불가" ≥ 2`를 폐기하고 **실행 검사로** 물려준 자리.

    존재 검사는 «파일에 낱말이 있는가»만 보고 «음성 경로가 도는가»는 아무것도
    말하지 않는다. 그래서 여기서는 **실제로 돌린다.**
    """

    ONE = [_ev("E007", "S19", "나비가 갑자기 아파서 응급실에 감")]
    TEXT_ONE = "나비가 응급실에 갔다."

    def test_one_match_says_exact_sentence(self):
        r = SP.m3(self.TEXT_ONE, self.ONE)
        self.assertEqual(r.k, 1)
        self.assertEqual(r.reason, "판정 불가 — 매칭 사건 1건")
        self.assertIsNone(r.pairs)
        self.assertIsNone(r.hit)

    def test_zero_match_also_says_the_count(self):
        r = SP.m3("아무 상관 없는 문장이다.",
                  [_ev("E009", "S21", "최종 합격")])
        self.assertEqual(r.k, 0)
        self.assertEqual(r.reason, "판정 불가 — 매칭 사건 0건")
        self.assertIsNone(r.pairs)

    def test_removing_the_guard_makes_a_fake_number(self):
        """🔴 심을 위반 — 가드를 없애면 쌍이 0인데 분수가 만들어진다."""
        r = SP.m3(self.TEXT_ONE, self.ONE, min_matches=0)
        self.assertIsNone(r.reason)             # 음성 경로가 사라졌다
        self.assertEqual(r.pairs, 0)
        self.assertEqual(r.hit, 0)
        with self.assertRaises(ZeroDivisionError):
            SP.m3_fmt(r)

    def test_guard_is_quiet_when_k_is_enough(self):
        """오발화 대조 (P5) — 문턱을 넘으면 울지 않는다."""
        items = [_ev("E001", "S05", "지우가 회사에서 크게 깨지고 새벽에 연락함"),
                 _ev("E009", "S21", "최종 합격")]
        text = "지우가 회사에서 깨지고 새벽에 연락함. 그 뒤 최종 합격 소식."
        r = SP.m3(text, items)
        self.assertIsNone(r.reason)
        self.assertEqual(r.k, 2)
        self.assertEqual(r.pairs, 1)
        self.assertIn("=", SP.m3_fmt(r))        # 숫자가 만들어진다

    def test_threshold_constant_is_the_only_place(self):
        """가드의 자리가 하나여야 «제거»가 의미를 갖는다."""
        self.assertEqual(SP.M3_MIN_MATCHES, 2)

    def test_ties_are_counted_as_mismatch_not_dropped(self):
        """
        같은 낱말로만 찾히면 오프셋이 같다 — 그 쌍은 **갈 수 없다.**
        조용히 분모에서 빼면 «순서가 맞았다»가 되므로 불일치로 센다.
        """
        items = [_ev("A", "S14", "첫 번째 면접"), _ev("B", "S16", "두 번째 면접")]
        r = SP.m3("면접 얘기만 있다 면접 면접", items)
        self.assertEqual(r.k, 2)
        self.assertEqual(r.pairs, 1)
        self.assertEqual(r.ties, 1)
        self.assertEqual(r.hit, 0)

    def test_unlocatable_item_is_dropped_and_named(self):
        """위치를 **추측하지 않는다.** 뺀 것은 이름으로 남는다."""
        items = [_ev("E009", "S21", "최종 합격"),
                 _ev("E002", "S11", "서준이 지우 집 앞까지 데려다줌 (처음으로)")]
        r = SP.m3("최종 합격 소식만 있다.", items)
        self.assertEqual(r.lost, ["E002"])
        self.assertEqual(r.k, 1)
        self.assertEqual(r.reason, "판정 불가 — 매칭 사건 1건")

    def test_first_pos_returns_none_without_shared_root(self):
        self.assertIsNone(SP.first_pos("전혀 다른 이야기", "최종 합격"))


# ── M1 — 형식. **사본을 두지 않았는가** ─────────────────────────────────

class TestM1(unittest.TestCase):

    def test_headings_are_three_and_come_from_the_prompt(self):
        """🔴 문자열 사본 금지(F12) — 표제는 `summarize.P4_TEMPLATE`에서 나온다."""
        self.assertEqual(len(SP.M1_HEADINGS), 3)
        for h in SP.M1_HEADINGS:
            self.assertIn(h, summarize.P4_TEMPLATE)

    def test_missing_one_heading_scores_two(self):
        """심을 위반 — 표제 하나를 지우면 3/3이 아니다."""
        full = "\n".join(SP.M1_HEADINGS) + "\n본문"
        self.assertEqual(SP.m1(full)[0], 3)
        cut = "\n".join(SP.M1_HEADINGS[:-1]) + "\n본문"
        self.assertEqual(SP.m1(cut)[0], 2)

    def test_empty_text_scores_zero(self):
        self.assertEqual(SP.m1("")[0], 0)


# ── 항목 집합 · 기준선 앵커 ─────────────────────────────────────────────

class TestMixedItemSet(unittest.TestCase):
    """
    🔴 `/11`·`/10`이라는 모양이 `events` 10과 같아 이 저장소가 한 번 속았다(S16).
    그래서 재구성이 **8사실 + 3사건**임을 이름으로 고정한다.
    """

    @classmethod
    def setUpClass(cls):
        cls.led = SP.load_ledger()

    def test_mixed_set_is_eight_facts_and_three_events(self):
        items = SP.mixed_items(self.led)
        fids = {f["id"] for f in self.led["facts"]}
        eids = {e["id"] for e in self.led["events"]}
        self.assertEqual(len(items), 11)
        self.assertEqual(sum(1 for i in items if i["id"] in fids), 8)
        self.assertEqual(sum(1 for i in items if i["id"] in eids), 3)

    def test_mixed_set_is_not_the_events_set(self):
        """**모양만 같고 집합이 다르다** — 그것이 §3.3의 전부다."""
        mixed = {i["id"] for i in SP.mixed_items(self.led)}
        events = {e["id"] for e in self.led["events"]}
        self.assertNotEqual(mixed, events)
        self.assertEqual(len(self.led["events"]), 10)

    def test_shrinking_the_span_changes_the_set(self):
        """심을 위반 — 구간을 줄이면 «같은 혼합»이 다른 집합이 된다."""
        a = {i["id"] for i in SP.mixed_items(self.led)}
        b = {i["id"] for i in SP.mixed_items(self.led, SP.BASELINE_SPAN[:-1])}
        self.assertNotEqual(a, b)
        self.assertIn("E003", a - b)        # S12의 사건이 빠진다


class TestBaselineAnchor(unittest.TestCase):
    """**재현되기 때문에 화살표를 그릴 수 있다.** 안 되면 못 그린다."""

    @classmethod
    def setUpClass(cls):
        cls.led = SP.load_ledger()
        cls.raw = SP.archive_raw()

    def test_both_rows_are_read_not_copied(self):
        """기록값은 파일에서 **읽는다** (G11). 코드에 박혀 있지 않다."""
        rows = SP.read_baseline_rows()
        self.assertEqual(len(rows), 2)
        for row, (depth, key, rec) in rows.items():
            self.assertIn("frozen", rec)
            self.assertIn("v2", rec)
            self.assertRegex(rec["frozen"], r"^\d+/\d+$")

    def test_both_rows_reproduce(self):
        for row, depth, rec, got, same in SP.baseline_anchor(self.led, self.raw):
            with self.subTest(row=row):
                self.assertTrue(same, f"«{row}» 재현 실패: {rec} vs {got}")

    def test_shrunken_span_fails_to_reproduce(self):
        """🔴 심을 위반 — 항목 집합을 흔들면 앵커가 **잡는다.**"""
        out = SP.baseline_anchor(self.led, self.raw,
                                 span=SP.BASELINE_SPAN[:-1])
        self.assertFalse(any(s for *_, s in out))


# ── 채점기 — 사본 금지 · P1 · 이 라운드가 산 결함 ───────────────────────

class TestScorers(unittest.TestCase):

    def test_scorers_are_the_real_functions_not_copies(self):
        """F12 — `scoring`의 함수를 그대로 부른다."""
        got = dict(SP.SCORERS)
        self.assertIs(got["frozen"], scoring.survived_frozen)
        self.assertIs(got["v2"], scoring.survived_v2)
        self.assertIs(got["v3"], scoring.survived_v3)

    def test_v3_subset_of_v2_and_same_unscorable(self):
        """P1의 성질 — v3은 뺄 수만 있고 **분모를 안 건드린다.**"""
        led = SP.load_ledger()
        sums, _ = SP.round_summaries()
        text = SP.join(sums)
        got = SP.score_all(text, led["events"])
        self.assertTrue(set(got["v3"][3]) <= set(got["v2"][3]))
        self.assertEqual(got["v3"][2], got["v2"][2])

    def test_e004_ordinal_false_negative_is_a_fixture(self):
        """
        🔴 **이 라운드가 산 결함을 고정물로 둔다.**

        `E004 첫 번째 면접`은 재료 안(S14)에 있고 그 세션 요약이 그것을 적는데도
        이어붙인 텍스트에서 v3이 죽인다 — 머리 `번째`가 S16·S18의 `{두, 세}`를
        모으고 S14는 `번째`를 안 쓰기 때문이다. **M2를 v2로 둔 근거가 이것이다.**

        누군가 `survived_v3`을 고치면 이 시험이 먼저 빨개진다. 그때 물어야 할
        것은 이 시험이 아니라 **`survived_v3`이라는 같은 이름 아래 다른 채점기가
        서는 것을 어떻게 할 것인가**다(S16 실패 모드 ②).

        🔄 **정정 — 실측했다.** 그 수리(`번째` 머리를 안 남기게)를 심어 보니
        실험 26의 홀드아웃은 **한 자리도 안 움직인다**(13/13 · 18/18 그대로).
        즉 «기록값이 깨진다»는 근거는 **이 코퍼스에서 거짓**이고, 남는 근거는
        «값이 같으니 괜찮다»가 다음 코퍼스에서 성립하지 않는다는 것 하나다.
        """
        led = SP.load_ledger()
        sums, _ = SP.round_summaries()
        text = SP.join(sums)
        got = SP.score_all(text, led["events"])
        self.assertIn("E004", got["v2"][3])
        self.assertNotIn("E004", got["v3"][3])
        self.assertEqual(sorted(set(got["v2"][3]) - set(got["v3"][3])),
                         ["E004"])

    def test_the_false_negative_is_attributed_to_the_marker_head(self):
        """귀속 — 머리 `번째`를 빼면 v3이 v2와 같아진다. **진단이지 수리가 아니다.**"""
        led = SP.load_ledger()
        sums, _ = SP.round_summaries()
        text = SP.join(sums)
        texts = [e["text"] for e in led["events"]]
        base_v2 = scoring.survived_v2(text, texts)
        orig = scoring._ordinal_heads
        try:
            scoring._ordinal_heads = lambda t: {
                h: o for h, o in orig(t).items()
                if h != scoring._ORDINAL_MARKER}
            no_marker = scoring.survived_v3(text, texts)
        finally:
            scoring._ordinal_heads = orig
        self.assertIs(scoring._ordinal_heads, orig)      # 되돌렸다
        self.assertEqual(len(no_marker.survived), len(base_v2.survived))

    def test_s14_summary_really_mentions_the_first_interview(self):
        """
        위 위음성이 «위음성»인 근거 — 재료에 그 사건이 **있다.**
        이 한 줄이 없으면 `E004`가 죽는 것을 «옳은 판정»이라 부를 수 있다.
        """
        sums, _ = SP.round_summaries()
        s14 = dict(sums)["S14"]
        self.assertIn("첫 면접", s14)


# ── 재료 · 체크포인트 ───────────────────────────────────────────────────

class TestMaterial(unittest.TestCase):

    def test_round_material_is_24_sessions(self):
        sums, meta = SP.round_summaries()
        self.assertEqual(len(sums), 24)
        self.assertEqual([s for s, _ in sums][0], "S01")
        self.assertEqual([s for s, _ in sums][-1], "S24")
        self.assertEqual(meta["digest"], meta["expect_digest"])

    def test_archive_material_is_12_sessions(self):
        self.assertEqual(len(SP.archive_summaries()), 12)

    def test_join_does_not_move_the_baseline_row(self):
        """
        이음 방식이 값을 안 움직인다 — 어근 집합 채점이라 구분자가 어근이 아니다.
        **산문으로 적고 시험 안 하면 다음 사람이 이음을 바꾸고 값을 잃는다.**
        """
        led = SP.load_ledger()
        items = SP.mixed_items(led)
        sums = SP.archive_summaries()
        a = SP.score_all(SP.join(sums), items)
        b = SP.score_all("\n\n".join(t for _, t in sums), items)
        c = SP.score_all("\n".join(t for _, t in sums), items)
        for s in ("frozen", "v2", "v3"):
            self.assertEqual(SP.cell(a, s), SP.cell(b, s))
            self.assertEqual(SP.cell(a, s), SP.cell(c, s))

    @unittest.skipUnless(os.path.exists(SP.LIFETIME_CKPT),
                         "LIFETIME_S27.json이 없다 — ollama 없는 환경")
    def test_lifetime_checkpoint_has_generation_accounting(self):
        """생성 회계가 체크포인트에 남는다 — 건수·벽시계·정지·시도."""
        import json
        with open(SP.LIFETIME_CKPT, encoding="utf-8") as f:
            rec = json.load(f)
        for k in ("n_generated", "wall_s", "stalls", "retries_used",
                  "k_session_digests", "prompt_eval_count"):
            self.assertIn(k, rec["meta"])
        self.assertEqual(rec["meta"]["k_session_digests"], 24)
        self.assertEqual(rec["meta"]["n_generated"], 1)

    @unittest.skipUnless(os.path.exists(SP.LIFETIME_CKPT),
                         "LIFETIME_S27.json이 없다 — ollama 없는 환경")
    def test_lifetime_material_digest_matches_the_session_summaries(self):
        """
        🔴 **문자열 대조다.** 체크포인트가 있다는 것은 «전에 돌았다»이지
        «같은 조건이다»가 아니다.
        """
        import json
        with open(SP.LIFETIME_CKPT, encoding="utf-8") as f:
            lmeta = json.load(f)["meta"]
        _, s2meta = SP.round_summaries()
        self.assertEqual(lmeta["digest"], s2meta["digest"])
        self.assertEqual(lmeta["seed"], s2meta["seed"])
        self.assertEqual(lmeta["num_ctx"], s2meta["num_ctx"])


# ── 러너 등록 ───────────────────────────────────────────────────────────

class TestRunnerWiring(unittest.TestCase):
    """
    🔴 가드레일이 읽으라고 만든 종료 코드를 아무도 안 읽으면 그 가드레일은 없다.
    G14 rev2가 고친 것과 같은 형태 — `STEPS`에 실제로 있는지 본다.
    """

    def test_registered_in_run_all(self):
        import run_all
        row = [s for s in run_all.STEPS if s[0] == "summary_prototype.py"]
        self.assertEqual(len(row), 1)
        fname, desc, needs_extra, grid, audit = row[0]
        self.assertEqual(len(row[0]), 5)
        self.assertTrue(needs_extra)     # 로컬 `qwen3:8b`가 필요하다
        self.assertFalse(grid)           # 격자가 아니다 — `--quick`도 돌린다
        self.assertFalse(audit)          # 🔴 종료 1은 **실행 실패**다, 지적이 아니다

    def test_not_counted_as_grid_or_audit(self):
        """다섯 번째 원소가 `True`면 이 실험의 실패가 «원래 빨간 것»이 된다."""
        import run_all
        self.assertNotIn("summary_prototype.py", run_all.GRID_FILES)
        self.assertNotIn("summary_prototype.py", run_all.AUDIT_FILES)


if __name__ == "__main__":
    unittest.main()
