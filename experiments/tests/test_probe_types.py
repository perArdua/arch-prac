# -*- coding: utf-8 -*-
"""
test_probe_types.py — 프로브 집합과 하니스의 **음성 대조(negative control)**.

## 이 파일이 지키는 규칙

    새로 쓰거나 고친 검증 명령은 **위반을 일부러 심어 발화를 확인한 뒤에만** 보고한다.

그래서 이 파일의 시험 대부분은 *"맞게 돌아가는가"*가 아니라 ***"틀렸을 때 실제로
소리를 내는가"***를 묻는다. 셋을 심는다.

  1. **존재하지 않는 gold id** → 거부하고 **멈춘다.** 조용히 건너뛰지 않는다.
     조용히 건너뛰면 n이 24에서 23이 되고 *"24개 중"*이라고 적힌 모든 비율이 틀린
     분모 위에 선다 — `hard_misinjection`이 죽은 것과 같은 부류의 병이다.
  2. **분류 밖 유형 라벨** → 던진다. 라벨이 자유 문자열이면 오타가 조용히 **새
     유형**이 되고 유형별 집계의 분모가 갈린다.
  3. **순위 논리 변이** → `probe_types.py`를 임시 사본으로 복제해 정렬을 뒤집고
     (그리고 1-기반을 0-기반으로 바꿔) **시험이 그 사본에서 실패하는 것을 보인다.**
     실패하지 않는 시험은 아무것도 지키지 않는다.

⚠️ ollama도 DB도 쓰지 않는다. 임베딩이 필요한 경로는 SKIP(77) 규약만 시험한다.
"""
import contextlib
import importlib.util
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "..", "prototype"))
import probe_set as PS                                      # noqa: E402
import probe_types as PT                                    # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 합성 고정물(fixture). 정답의 순위가 **손으로 계산되는** 최소 사례다.
#   점수:  A 0.9 > C 0.5 > B 0.1   →  A=1등 · C=2등 · B=3등
FIXTURE = [(0.9, "A"), (0.1, "B"), (0.5, "C")]
FIXTURE_EXPECT = {"A": 1, "C": 2, "B": 3}


def _invariant(mod):
    """
    `mod.rank_of`가 지켜야 하는 것 전부. 어기면 `AssertionError`.

    변이체에 이 함수를 그대로 물려 **같은 시험이 변이체에서 실패하는지**를 본다.
    """
    for gold, want in FIXTURE_EXPECT.items():
        got = mod.rank_of(FIXTURE, gold)
        assert got == want, f"rank_of({gold}) = {got}, 기대 {want}"
    # 없는 id는 꼴찌로 — 조용히 예외를 내거나 0을 주면 순위 통계가 조용히 망가진다.
    assert mod.rank_of(FIXTURE, "없음") == len(FIXTURE)


def _mutant(*replacements):
    """
    `probe_types.py`를 **임시 디렉터리에 복제**하고 소스를 치환해 import한다.

    원본을 건드리지 않는다. 치환이 한 건도 안 맞으면 `AssertionError` —
    소스가 바뀌어 변이가 조용히 무효가 되는 것이 이 시험의 유일한 실패 방식이다.
    """
    with open(os.path.join(HERE, "probe_types.py"), encoding="utf-8") as f:
        src = f.read()
    for old, new in replacements:
        assert src.count(old) == 1, f"변이 대상이 유일하지 않다: {old!r}"
        src = src.replace(old, new)
    d = tempfile.mkdtemp(prefix="probe_mutant_")
    path = os.path.join(d, "probe_types_mutant.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    spec = importlib.util.spec_from_file_location("probe_types_mutant", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 1. 음성 대조 — 존재하지 않는 gold id ────────────────────────────────

class TestUnknownGoldIsRejectedLoudly(unittest.TestCase):

    def test_unknown_gold_raises(self):
        """🔴 **없는 근거를 가리키는 프로브는 멈춘다.** 경고가 아니다."""
        bad = list(PS.TYPED_PROBES) + [PS.Probe("있지도 않은 근거를 묻는다",
                                                "F999_NOPE", PS.DIRECT)]
        planned = dict(PS.PLANNED, **{PS.DIRECT: 9})
        with self.assertRaises(PS.ProbeSetError) as cm:
            PS.validate(bad, planned=planned)
        self.assertIn("F999_NOPE", str(cm.exception))

    def test_unknown_gold_is_not_silently_dropped(self):
        """
        🔴 **이 시험이 이 파일의 이유다.** 조용히 빼는 구현도 위 시험은 통과할 수
        있다(빼고 나서 나머지가 멀쩡하니까). 그래서 **분모**를 직접 본다:
        위반이 있으면 `validate`는 참을 돌려주지 않으므로 채점이 시작될 수 없고,
        따라서 24가 23으로 줄어든 채 *"24개 중"*이라고 찍히는 일이 생길 수 없다.
        """
        bad = list(PS.TYPED_PROBES) + [PS.Probe("없는 근거", "F999_NOPE",
                                                PS.DIRECT)]
        planned = dict(PS.PLANNED, **{PS.DIRECT: 9})
        with self.assertRaises(PS.ProbeSetError):
            PS.validate(bad, planned=planned)
        # 그리고 하니스의 본문도 같은 자리에서 멈춘다 — 임베딩을 부르기 **전에**다.
        orig = PS.TYPED_PROBES
        PS.TYPED_PROBES = bad
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                with self.assertRaises(PS.ProbeSetError):
                    PT.main()
            self.assertNotIn("[표 1]", buf.getvalue())   # 채점표는 안 찍힌다
        finally:
            PS.TYPED_PROBES = orig

    def test_every_violation_is_listed_not_just_the_first(self):
        """고치고 다시 돌리기를 위반 수만큼 반복하게 만들지 않는다."""
        bad = [PS.Probe("q1", "F999_A", PS.DIRECT),
               PS.Probe("q2", "F999_B", PS.DIRECT)]
        with self.assertRaises(PS.ProbeSetError) as cm:
            PS.validate(bad, planned={PS.DIRECT: 2}, n_min=2)
        self.assertIn("F999_A", str(cm.exception))
        self.assertIn("F999_B", str(cm.exception))

    def test_real_set_resolves_against_eval(self):
        """
        양성 대조 — 실제 24개는 `eval/`의 코퍼스 **와** 원장 양쪽에서 해석된다.
        (`eval/`은 읽기만 한다 — A8.)
        """
        cids, lids = PS.corpus_ids(), PS.ledger_ids()
        self.assertTrue(PS.validate(PS.TYPED_PROBES, valid_ids=cids & lids))
        for p in PS.TYPED_PROBES:
            self.assertIn(p.gold, cids, f"{p.gold}가 코퍼스에 없다")
            self.assertIn(p.gold, lids, f"{p.gold}가 원장에 없다")

    def test_corpus_only_id_is_not_accepted_as_gold(self):
        """
        `F002_INV`는 **코퍼스에는 있고 원장에는 없다**(무효화 레코드). gold를
        코퍼스만으로 검사하면 통과하고 원장까지 보면 걸린다 — 그 차이를 못박는다.
        """
        self.assertIn("F002_INV", PS.corpus_ids())
        self.assertNotIn("F002_INV", PS.ledger_ids())
        with self.assertRaises(PS.ProbeSetError):
            PS.validate([PS.Probe("무효화를 가리킨다", "F002_INV", PS.DIRECT)],
                        valid_ids=PS.corpus_ids() & PS.ledger_ids(),
                        planned={PS.DIRECT: 1}, n_min=1)


# ── 2. 음성 대조 — 분류 밖 유형 라벨 ────────────────────────────────────

class TestTaxonomyIsClosed(unittest.TestCase):

    def test_unknown_type_raises(self):
        bad = [PS.Probe("고양이 이름이 나비였지", "F001", "어휘형")]
        with self.assertRaises(PS.ProbeSetError) as cm:
            PS.validate(bad, valid_ids={"F001"}, planned={}, n_min=1)
        self.assertIn("어휘형", str(cm.exception))
        self.assertIn("직접형", str(cm.exception))       # 허용 목록을 같이 보여준다

    def test_typo_in_a_known_label_is_a_new_type_and_is_caught(self):
        """`직접형` → `직접형 ` (뒤 공백). 눈으로는 안 보이는 위반이다."""
        bad = [PS.Probe("고양이 이름이 나비였지", "F001", "직접형 ")]
        with self.assertRaises(PS.ProbeSetError):
            PS.validate(bad, valid_ids={"F001"}, planned={}, n_min=1)

    def test_planned_split_is_enforced(self):
        """8/8/8은 사전 등록이다 — 나중에 조용히 기울면 안 된다."""
        bad = [p for p in PS.TYPED_PROBES if p.type != PS.PARA][:20]
        with self.assertRaises(PS.ProbeSetError) as cm:
            PS.validate(bad, valid_ids={p.gold for p in bad})
        self.assertIn(PS.PARA, str(cm.exception))

    def test_n_min_is_enforced(self):
        few = list(PS.TYPED_PROBES)[:19]
        with self.assertRaises(PS.ProbeSetError) as cm:
            PS.validate(few, valid_ids={p.gold for p in few},
                        planned={t: sum(1 for p in few if p.type == t)
                                 for t in PS.TYPES})
        self.assertIn("20", str(cm.exception))

    def test_duplicate_gold_is_rejected(self):
        """한 근거에 프로브 둘을 붙이면 그 근거의 난이도가 표본에 두 번 든다."""
        dup = list(PS.TYPED_PROBES) + [PS.Probe("고양이 이름 뭐랬지", "F001",
                                                PS.DIRECT)]
        with self.assertRaises(PS.ProbeSetError) as cm:
            PS.validate(dup, planned=dict(PS.PLANNED, **{PS.DIRECT: 9}))
        self.assertIn("F001", str(cm.exception))


# ── 3. 음성 대조 — 순위 논리를 실제로 부순다 ────────────────────────────

class TestRankingMutantsAreCaught(unittest.TestCase):
    """
    🔴 시험이 **부순 코드에서 실패하는 것**을 여기서 보인다. 통과만 보이는
    시험은 통과 말고 아무것도 증명하지 않는다.
    """

    def test_real_module_satisfies_invariant(self):
        _invariant(PT)                                   # 양성 대조

    def test_mutant_reversed_sort_is_caught(self):
        """내림차순 → 오름차순. *"점수가 높을수록 위"*가 깨진다."""
        mut = _mutant(("sorted(scored, key=lambda x: -x[0])",
                       "sorted(scored, key=lambda x: x[0])"))
        with self.assertRaises(AssertionError):
            _invariant(mut)

    def test_mutant_off_by_one_rank_is_caught(self):
        """1-기반 → 0-기반. 1등이 0등이 되고 평균 순위가 통째로 1 내려간다."""
        mut = _mutant(("ids.index(gold) + 1 if gold in ids else len(ids)",
                       "ids.index(gold) if gold in ids else len(ids)"))
        with self.assertRaises(AssertionError):
            _invariant(mut)

    def test_mutant_ranking_moves_the_reported_numbers(self):
        """
        변이가 **보고되는 숫자를 실제로 움직이는지**까지 본다. 불변이면 그
        변이는 아무것도 지키지 않는 자리를 건드린 것이고, 시험도 무의미하다.
        """
        docs = [{"text": "지우의 고양이 이름은 나비. 말했었나?", "planted_id": "F001"},
                {"text": "첫 번째 면접 — 탈락", "planted_id": "E004"}]
        probes = [PS.Probe("고양이 이름이 나비였지", "F001", PS.DIRECT)]
        real = PT.run_mode(PT.score_lexical, probes, docs)
        mut = _mutant(("sorted(scored, key=lambda x: -x[0])",
                       "sorted(scored, key=lambda x: x[0])"))
        bad = mut.run_mode(mut.score_lexical, probes, docs)
        self.assertEqual(real[0][0], 1)
        self.assertEqual(bad[0][0], 2)                   # 뒤집히면 꼴찌가 된다


# ── 4. 부호 검정 — 작은 n에서 무엇을 물을 수 있나 ───────────────────────

class TestSignTest(unittest.TestCase):

    def test_all_wins_at_n8(self):
        w, l, t, p = PT.sign_test([1] * 8, [2] * 8)
        self.assertEqual((w, l, t), (8, 0, 0))
        self.assertAlmostEqual(p, 2 / 256)               # 0.0078

    def test_even_split_is_not_significant(self):
        w, l, t, p = PT.sign_test([1, 1, 1, 1, 3, 3, 3, 3], [2] * 8)
        self.assertEqual((w, l, t), (4, 4, 0))
        self.assertEqual(p, 1.0)

    def test_ties_are_dropped_and_counted(self):
        """동점을 승으로 세면 p가 가짜로 작아진다."""
        w, l, t, p = PT.sign_test([1, 2, 2, 2], [2, 2, 2, 2])
        self.assertEqual((w, l, t), (1, 0, 3))
        self.assertEqual(p, 1.0)                         # n=1이면 2/2 = 1.0

    def test_p_is_never_zero(self):
        """`_p`가 작은 p를 0.0000으로 찍어 *"정확히 0"*으로 읽히게 두지 않는다."""
        _, _, _, p = PT.sign_test([1] * 24, [2] * 24)
        self.assertGreater(p, 0.0)
        self.assertNotIn("0.0000", PT._p(p))

    def test_five_per_type_could_never_reach_005(self):
        """
        유형당 8인 이유를 못박는다: n=5면 **모든 프로브가 한쪽이어도** 양측
        p = 0.0625 > 0.05다. 도달 불가능한 유의수준을 표에 적지 않기 위해서다.
        """
        _, _, _, p5 = PT.sign_test([1] * 5, [2] * 5)
        self.assertAlmostEqual(p5, 2 / 32)
        self.assertGreater(p5, 0.05)
        _, _, _, p8 = PT.sign_test([1] * 8, [2] * 8)
        self.assertLess(p8, 0.05)


# ── 5. SKIP(77) 규약과 자기저작 선언 ────────────────────────────────────

class TestSkipAndDeclaration(unittest.TestCase):

    def test_missing_keys_are_listed_and_none_returned(self):
        """
        ollama가 없으면 **없는 키를 전부 찍고** `None`을 돌려준다. 조용히
        빈 벡터를 주면 코사인이 전부 0이 되고 표가 멀쩡해 보인다.
        """
        real_avail, real_cache = PT.EMB.available, PT.PROBE_CACHE
        PT.EMB.available = lambda: False
        PT.PROBE_CACHE = os.path.join(tempfile.mkdtemp(), "없는캐시.json")
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                vecs, hit, miss = PT.ensure_vectors(["지우의 고양이"])
        finally:
            PT.EMB.available, PT.PROBE_CACHE = real_avail, real_cache
        self.assertIsNone(vecs)
        self.assertEqual((hit, miss), (0, 1))
        self.assertIn("없는 키: 지우의 고양이", buf.getvalue())
        self.assertIn("SKIP", buf.getvalue())

    def test_main_returns_77_when_vectors_unavailable(self):
        """SKIP은 **통과가 아니다**(G1) — 종료 코드가 0이 아니어야 한다."""
        real_ev, real_ci = PT.ensure_vectors, PT.EMB.checkpoint_info
        PT.ensure_vectors = lambda texts: (None, 0, len(texts))
        PT.EMB.checkpoint_info = lambda: {"ollama": None, "model": "bge-m3",
                                          "digest": None, "at": ""}
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = PT.main()
        finally:
            PT.ensure_vectors, PT.EMB.checkpoint_info = real_ev, real_ci
        self.assertEqual(rc, 77)
        self.assertNotEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("측정 안 됨", out)
        self.assertNotIn("[표 1]", out)                  # 숫자를 만들지 않는다
        # 🔴 자기저작 선언은 **숫자가 안 나오는 실행에서도** 찍힌다.
        self.assertIn("자기저작", out)
        self.assertIn("E005", out)                       # 뺀 것을 밝히는 문장
        # 🔴 표 0도 같은 지위다 — 임베딩을 안 쓰므로 SKIP 실행에서도 찍혀야 한다.
        #    이 절이 벡터 뒤로 밀리면 *"ollama가 없으면 격자 문항 분포도 못 본다"*가
        #    되고, 그것은 이 표가 답하는 질문과 아무 상관이 없는 의존이다.
        self.assertIn("[표 0]", out)
        self.assertIn("배정 결과", out)

    def test_declaration_is_not_empty_and_names_the_fix(self):
        """선언이 한계만 적고 **고칠 방법**을 안 적으면 자백이지 계측이 아니다."""
        d = PS.SELF_AUTHORSHIP
        self.assertIn("자기저작", d)
        self.assertIn("코퍼스만 보고", d)
        self.assertIn("실제 사용자 질문", d)


# ── 5-b. 표 0 (레인 J) — 격자 18문항 분류의 음성 대조 ────────────────────

class TestEvalQuestionClassification(unittest.TestCase):
    """
    표 0이 찍는 *"직접형 1/18"*은 **두 가지에 의존한다**: (1) 레인 I의 두 대역이
    실제로 분리된다는 것, (2) 경계가 그 빈 구간 안에 있다는 것. 둘 중 하나가
    무너지면 이 표는 **숫자를 찍으면 안 된다.** 아래가 그것을 실제로 부숴 본다.
    """

    def _run(self, mod):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r = mod.report_eval_question_types(PS.corpus_docs())
        return r, buf.getvalue()

    def test_real_module_separates_and_reports_one(self):
        """🟢 양성 대조. 값이 바뀌면 여기가 먼저 운다."""
        (boundary, n_direct, n, sep), out = self._run(PT)
        self.assertTrue(sep)
        self.assertEqual(n, 18)                          # 채점 18문항
        self.assertEqual(n_direct, 1)
        self.assertAlmostEqual(boundary, 0.412, places=3)
        self.assertIn("배정 결과", out)
        # 🔴 라벨이 이 파일의 것이라는 선언이 **출력에** 있어야 한다.
        self.assertIn("`eval/`의 것이 아니다", out)

    def test_mutant_flat_score_makes_bands_overlap_and_the_table_refuses(self):
        """
        🔴 **음성 대조 ①** — 척도를 상수로 만들면 세 대역이 한 점으로 무너진다.
        그러면 경계가 정의되지 않고, 표는 **숫자를 찍지 않고 침묵해야 한다.**
        (숫자를 찍으면 '분류'가 측정이 아니라 관성이 된다.)
        """
        mut = _mutant(("    return M.coverage(M.bigrams(q), M.bigrams(t))",
                       "    return 0.5"))
        (boundary, n_direct, n, sep), out = self._run(mut)
        self.assertFalse(sep)
        self.assertIsNone(boundary)
        self.assertIsNone(n_direct)
        self.assertEqual(n, 18)
        self.assertIn("경계를 그을 수 없다", out)
        self.assertNotIn("배정 결과", out)               # ← 이것이 대조의 핵심

    def test_mutant_boundary_moves_the_reported_count(self):
        """
        🔴 **음성 대조 ②** — 경계를 0으로 내리면 18문항 **전부**가 직접형이 된다.
        즉 *"직접형 1/18"*은 데이터가 아니라 **경계와 데이터의 함수**이고,
        경계가 움직이면 숫자가 실제로 움직인다는 것을 보인다.
        """
        mut = _mutant(("    boundary = (mean[PS.DIRECT] + mean[PS.PARA]) / 2",
                       "    boundary = 0.0"))
        (_b, n_direct, n, sep), _out = self._run(mut)
        self.assertTrue(sep)
        self.assertEqual((n_direct, n), (18, 18))

    def test_questions_come_from_eval_not_from_a_hardcoded_list(self):
        """
        분모 18이 **하드코딩이면** `eval/`이 움직여도 이 표는 안 움직인다.
        `precision.partition`이 고른 집합과 **같은 id**여야 한다.
        """
        _corpus, ledger, qs = PT.PR.load()
        key_of = PT.PR.key_index(ledger)
        scored, _ = PT.PR.partition(qs, key_of)
        self.assertEqual([q["id"] for q in scored],
                         [r[0] for r in PT.eval_gold_rel()])


# ── 6. 채점 규칙의 출처 — 사본을 만들지 않았다는 것을 시험한다 ──────────

class TestScorersComeFromProduction(unittest.TestCase):
    """
    F12는 같은 규칙의 사본이 둘이 되면서 한쪽만 고쳐진 일이었다.
    이 하니스가 `rel` 식을 **다시 구현하지 않았다**는 것을 값으로 확인한다.
    """

    def test_lexical_equals_memory_coverage(self):
        import memory as M
        q, t = "고양이 이름이 나비였지", "지우의 고양이 이름은 나비. 말했었나?"
        self.assertEqual(PT.score_lexical(q, t),
                         M.coverage(M.bigrams(q), M.bigrams(t)))

    def test_fixed_equals_memory_jaccard(self):
        import memory as M
        q, t = "지우가 새 직장으로 옮긴 거 말이야", "지우는 스타트업으로 이직함. 말했었나?"
        self.assertEqual(PT.score_fixed(q, t),
                         M.jaccard(M.tokens_fixed(q), M.tokens_fixed(t)))

    def test_alpha_comes_from_embed_vs_bigram(self):
        import embed_vs_bigram as EB
        self.assertEqual(PT.ALPHA_HYBRID, EB.ALPHA_HYBRID)
        self.assertIn(str(EB.ALPHA_HYBRID), PT.MODES[3])

    def test_probe_cache_is_a_new_file(self):
        """🔴 `EMBED_CACHE.json`·`REL_CACHE.json`에 쓰지 않는다."""
        base = os.path.basename(PT.PROBE_CACHE)
        self.assertNotIn(base, ("EMBED_CACHE.json", "REL_CACHE.json",
                                "EMBED_CACHE_SWEEP.json"))

    def test_host_is_not_localhost(self):
        """F38 — `localhost`는 이 기기에서 호출당 ~2.02초를 붙인다."""
        self.assertNotIn("localhost", PT.EMB.OLLAMA_HOST)


if __name__ == "__main__":
    unittest.main()
