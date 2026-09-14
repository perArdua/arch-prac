# -*- coding: utf-8 -*-
"""
test_tokens.py — 고친 토크나이저와 검색 모드 (라운드 2 단계 3 · ADR-015).

이 파일이 고정하는 것은 셋이다.

  ① **정본 승격이 식을 안 바꿨다** — `tokens_fixed`·`jaccard`·`coverage`.
     `coverage`는 현행 `retrieve()`의 `rel`과 **같은 식**이어야 한다. 그 등식이
     깨지면 기본값이 조용히 움직인다(G16).
  ② **U7 — 유도되지 않은 θ(`None`)를 가진 모드는 기본값이 될 수 없다.**
     θ 없이 도는 것은 게이트가 사라진 상태이고, F27이 그것이 눈에 안 보인다는 것을
     실측했다. 죽는 편이 낫다(P5).
  ③ **U8 — 임베딩 실패는 강등이지 침묵이 아니다.** 결과가 `lexical_fixed`와
     같아야 하고, `provenance`에 `("degraded", "embedding", …)`이 남아야 한다.

U5/U5-b(`theta_at`의 `+∞` 분기)는 `experiments/tests/test_rel_dist.py`에 있다 —
등컷 규칙은 실험 쪽 자산이고 여기로 옮겨 적지 않는다(F9: 두 벌로 적으면 한쪽만
고쳐진다).

⚠️ 이 파일은 **전역을 흔든다.** 흔든 것은 전부 `try/finally`로 되돌린다(G13) —
   되돌리지 않으면 같은 프로세스의 다른 테스트가 오염된 값을 본다.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "prototype"))
sys.path.insert(0, os.path.join(ROOT, "experiments"))
import memory as M                                         # noqa: E402
from memory import Memory                                  # noqa: E402

CHAT = "c1"


def seed(m):
    """
    검색이 실제로 무언가를 꺼내는 최소 색인. τ=0.2를 넘는 값으로 심는다.

    ⚠️ 컬럼을 **이름으로** 적는다 (G6). `soak.seed`의 위치 INSERT를 흉내 내면
       컬럼 순서가 바뀌는 날 조용히 엉뚱한 칸에 들어간다 — 이 파일을 쓰면서
       `chat`의 2번째 칸이 `user_id`인 것을 놓쳐 실제로 한 번 그랬다.
    """
    m.db.execute("INSERT INTO chat (chat_id, user_id, character_id,"
                 " character_version) VALUES (?,?,?,?)",
                 (CHAT, "jiwoo", "seojun", 1))
    m.db.execute("INSERT INTO character_version (character_id, version,"
                 " persona_text, speech_rules) VALUES (?,?,?,?)",
                 ("seojun", 1, "서준이다.", "반말."))
    m.db.execute("INSERT INTO relationship (chat_id, stage, affinity, called_as)"
                 " VALUES (?,?,?,?)", (CHAT, "지인", 30, "지우"))
    for i, s in enumerate(["지우가 면접 준비를 하느라 밤을 새웠다",
                           "지우가 강아지를 데리고 병원에 갔다",
                           "지우가 이사 준비로 짐을 쌌다"]):
        m.add_event(CHAT, s, i * 100, emotional_weight=0.8)
    m.db.commit()
    return m


def kinds(notes):
    return [k for k, _, _ in notes]


class TestTokensFixed(unittest.TestCase):

    def test_word_boundary_not_crossed(self):
        """어절 경계를 넘는 가짜 조각을 만들지 않는 것이 이 토크나이저의 존재 이유다."""
        self.assertNotIn("가강", M.tokens_fixed("지우가 강아지"))
        self.assertIn("강아", M.tokens_fixed("지우가 강아지"))

    def test_particle_stripped(self):
        """
        조사를 벗긴다 — 현행 토크나이저가 못 하던 절반이다.

        🔴 **`_ENDINGS`에 없는 조사를 써야 한다.** 원래 이 시험은 `면접을`을 썼는데
        `을`은 `_ENDINGS`에 이미 있어서, **`_PART`를 통째로 꺼도 통과했다**
        (검증자가 뮤테이션으로 증명: `_PART` 제거 후 23개 전부 green).
        조사 제거를 실제로 붙잡으려면 두 집합이 겹치지 않는 낱말이 필요하다 —
        `가·이·에게·에서·의·도·만·으로·부터·까지·한테`.
        """
        self.assertEqual(M.tokens_fixed("나비가"), M.tokens_fixed("나비"))
        self.assertEqual(M.tokens_fixed("지우에게"), M.tokens_fixed("지우"))
        self.assertEqual(M.tokens_fixed("회사에서"), M.tokens_fixed("회사"))

    def test_two_char_floor(self):
        """
        2글자 밑으로는 안 깎는다. '강아지 -> 강'이 실제로 났던 사고다.

        ⚠️ '강아지 -> 강아'까지는 간다 — 어미 목록에 `지`가 있기 때문이다(`memory.py:260`).
           하한이 막는 것은 그 **다음** 한 걸음이고, 그것이 이 함수가 지키는 전부다.
        """
        self.assertEqual(M._fixed_word("강아지"), "강아")
        self.assertEqual(M._fixed_word("강아"), "강아")

    def test_single_char_word_survives(self):
        """1글자 어절도 조각 하나로 남는다 — 빈 리스트를 돌려주면 분모가 0이 된다."""
        self.assertEqual(M.tokens_fixed("밤"), ["밤"])

    def test_empty(self):
        self.assertEqual(M.tokens_fixed(""), [])

    def test_promotion_is_a_rename(self):
        """정본 승격은 **이름의 이동이지 식의 변경이 아니다** — 실험이 같은 것을 읽는다."""
        from embed_vs_bigram import bigrams2, stem2         # noqa: E402
        self.assertIs(bigrams2, M.tokens_fixed)
        self.assertIs(stem2, M._fixed_word)


def _alts(pat):
    """정규식 `(a|b|c)$`의 대안 목록. **정렬해서** 다룬다 — `repr(set)`은 seed의 함수다."""
    body = pat.pattern
    body = body[body.index("(") + 1:body.rindex(")")]
    return frozenset(a for a in body.split("|") if a)


class TestTheTwoParticleTablesDoNotDriftFurther(unittest.TestCase):
    """
    🆕 🔴 **조사 표가 두 벌이고 갈렸다** — `_PART`(`_fixed_word` 쪽)와
    `Memory._PARTICLE`(`_roots` 쪽). 실험 30이 그 갈림을 찾았고, 마감 레인이
    **재고 통합하지 않기로** 했다. 이 검사는 그 결정의 짝이다.

    🔴 **«두 표가 같아야 한다»고 쓰지 않는 이유.** 그 검사는 오늘 당장 빨갛고,
    빨간 채로 태어난 검사는 곧 꺼진다 — 이 저장소가 «발화할 수 없는 검사»로
    열두 번 겪은 것의 쌍둥이다. 대신 **오늘의 갈림을 이름으로 박고, 그 밖으로
    벌어지면** 운다. 갈림이 «있다»는 것은 기록이고, 갈림이 «자란다»는 것이 사고다.

    ⚠️ **통합은 왜 이 레인에서 안 했나.** 재 보니 동작은 한 칸도 안 움직인다
    (240쌍 · 실험 19/20 각 7행 × 11항목 · 실험 26 홀드아웃 18쌍 · 실험 27 M2와
    기준선 앵커 · `_fixed_word` 623어절 전부 — 전 항목 0칸). 그런데 `_PARTICLE`은
    `survived_frozen`/`survived_v2`의 **닫힌 해시 안**이고
    (`experiments/tests/test_scoring.py`의 `TestFrozenClosureIsFrozen.REACH`),
    그 해시가 얼리는 것은 **정규식이 받아들이는 언어가 아니라 패턴 문자열의 철자**다.
    철자를 다시 쓰면 동작이 같아도 해시가 움직이고, 그때 사람이 할 일이
    «값을 갱신»이 된다 — 구멍이 그렇게 다시 열린다. 그래서 통합은 **제품 판단**으로
    넘긴다(`docs/11` 실험 30 §J).
    """

    # 🔴 **오늘의 갈림.** `_PARTICLE`에만 있는 7종이다. `_PART`에만 있는 것은 없다
    #    (`_PART ⊂ _PARTICLE`). 손으로 적되 **한 방향뿐**이라는 사실까지 박는다.
    ONLY_IN_PARTICLE = frozenset({"께서", "랑", "에게서", "으로서", "으로써",
                                  "이랑", "한테서"})
    ONLY_IN_PART = frozenset()

    def test_the_divergence_is_exactly_what_we_wrote_down(self):
        """갈림이 **오늘 적어 둔 그것**인가. 한 원소라도 벌어지면 운다."""
        part, particle = _alts(M._PART), _alts(Memory._PARTICLE)
        self.assertEqual(sorted(particle - part), sorted(self.ONLY_IN_PARTICLE),
                         "`_PARTICLE`에만 있는 조사가 달라졌다 — 갈림이 자랐거나 줄었다")
        self.assertEqual(sorted(part - particle), sorted(self.ONLY_IN_PART),
                         "`_PART`에만 있는 조사가 생겼다 — 갈림이 **반대 방향으로** 자랐다")

    def test_the_containment_direction_is_still_one_way(self):
        """🔴 **방향**이 기록이다. `_PART ⊂ _PARTICLE`이 깨지면 위 차집합 둘만으로는
        «어느 쪽이 앞서 나갔나»를 못 읽는다."""
        self.assertLess(_alts(M._PART), _alts(Memory._PARTICLE))

    def test_the_wider_table_is_the_one_inside_the_frozen_closure(self):
        """⚠️ 조용한 쪽 — 넓은 표(`_PARTICLE`)가 **동결 경계 안**이라는 것이
        «합치면 해시가 움직인다»의 이유 전부다. 이 배치가 뒤집히면 그 문장이 거짓이 된다."""
        self.assertIn("_PARTICLE", Memory._roots.__func__.__code__.co_names)
        self.assertNotIn("_PART", Memory._roots.__func__.__code__.co_names)
        self.assertIn("_PART", M._fixed_word.__code__.co_names)


class TestScores(unittest.TestCase):

    def test_coverage_is_the_current_rel(self):
        """🔴 현행 `retrieve()`의 `rel`과 **같은 식**이어야 한다 (G16)."""
        q, d = set(M.bigrams("면접 준비")), set(M.bigrams("면접 준비를 했다"))
        self.assertEqual(M.coverage(q, d), len(q & d) / max(len(q), 1))

    def test_jaccard_is_symmetric_coverage_is_not(self):
        """두 척도가 **다른 것**을 재는 것이 lexical_fixed를 따로 두는 이유다."""
        q, d = {"a", "b"}, {"a", "b", "c", "d"}
        self.assertEqual(M.jaccard(q, d), M.jaccard(d, q))
        self.assertEqual(M.coverage(q, d), 1.0)
        self.assertEqual(M.jaccard(q, d), 0.5)

    def test_empty_query_does_not_divide_by_zero(self):
        self.assertEqual(M.coverage(set(), {"a"}), 0.0)
        self.assertEqual(M.jaccard(set(), set()), 0.0)


class TestThetaByMode(unittest.TestCase):

    def test_lexical_theta_follows_the_global(self):
        """
        🔴 `lexical`의 θ 정본은 dict가 아니라 `THETA_RELEVANCE`다. 스윕 4종이 그
        전역을 흔들기 때문에, 여기서 리터럴을 읽으면 **스윕이 죽는다.**
        """
        orig = M.THETA_RELEVANCE
        try:
            M.THETA_RELEVANCE = 0.42
            self.assertEqual(M.theta_for("lexical"), 0.42)
        finally:
            M.THETA_RELEVANCE = orig
        self.assertEqual(M.theta_for("lexical"), orig)

    def test_derived_entries_carry_their_provenance(self):
        """G12 — θ는 **모집단·n·컷비율 없이** 쓸 수 없다. 값이 그것을 들고 다닌다."""
        for mode in ("lexical_fixed", "embed"):
            theta, f, n, sig = M.THETA_BY_MODE.get(mode)   # G13: `[...]`를 안 쓴다
            self.assertIsInstance(theta, float)
            self.assertEqual((f, n, sig), (0.80, 378, (22, 21)))

    def test_no_hybrid_key(self):
        """결정 E — 하이브리드는 격자에서 삭제됐다. 재진입 조건이 충족되면 그때 넣는다."""
        self.assertNotIn("hybrid", M.THETA_BY_MODE)

    def test_u7_undeliverable_mode_cannot_become_the_default(self):
        """
        **U7.** θ가 `None`인 모드를 기본으로 세우면 `RuntimeError`.
        `set_retrieval_mode`로도, `retrieve()`로도 죽어야 한다 — 전역을 직접
        재바인딩하는 경로(스윕이 그렇게 한다)를 막을 방법이 없기 때문이다.
        """
        orig = (M.THETA_BY_MODE, M.RETRIEVAL_MODE, M.EMBED_FN)
        try:
            M.THETA_BY_MODE = dict(M.THETA_BY_MODE, embed=None)  # G13: 전체 재바인딩
            with self.assertRaises(RuntimeError):
                M.set_retrieval_mode("embed")
            self.assertEqual(M.RETRIEVAL_MODE, orig[1])    # 실패했으면 안 세워졌다

            # 전역을 직접 재바인딩하면 `set_retrieval_mode`를 우회한다 — 스윕이
            # 그렇게 한다. 그래서 `retrieve()`도 같은 자리에서 죽어야 한다.
            # ⚠️ 강등이 θ 조회보다 **먼저** 일어나므로 공급자가 살아 있어야
            #    `embed`의 θ를 실제로 읽는 데까지 간다.
            m = seed(Memory(":memory:"))
            M.RETRIEVAL_MODE = "embed"
            M.EMBED_FN = lambda texts: [[1.0, 0.0] for _ in texts]
            with self.assertRaises(RuntimeError):
                m.retrieve(CHAT, "면접 준비 어떻게 됐더라", 400)
        finally:
            M.THETA_BY_MODE, M.RETRIEVAL_MODE, M.EMBED_FN = orig

    def test_unknown_mode_also_raises(self):
        with self.assertRaises(RuntimeError):
            M.theta_for("hybrid")


class TestDegradation(unittest.TestCase):
    """**U8** — 임베딩 실패는 강등이지 침묵이 아니다 (P5)."""

    def setUp(self):
        self.orig = (M.RETRIEVAL_MODE, M.EMBED_FN, M.THETA_BY_MODE)
        self.m = seed(Memory(":memory:"))
        self.ask = "지우 면접 준비한다고 밤새운 거 기억나?"

    def tearDown(self):
        M.RETRIEVAL_MODE, M.EMBED_FN, M.THETA_BY_MODE = self.orig

    def _hits(self, mode, embed_fn=None):
        M.RETRIEVAL_MODE, M.EMBED_FN = mode, embed_fn
        hits, _ = self.m.retrieve(CHAT, self.ask, 400)
        return [r["summary"] for _, r in hits], list(self.m._retrieval_notes)

    def test_no_supplier_degrades_to_lexical_fixed(self):
        """공급자가 안 꽂혔다 = ollama 정지와 같은 자리. 결과가 `lexical_fixed`와 같다."""
        want, _ = self._hits("lexical_fixed")
        got, notes = self._hits("embed")
        self.assertEqual(got, want)
        self.assertIn(("degraded", "embedding"),
                      [(k, w) for k, w, _ in notes])

    def test_degraded_note_names_embedding_not_the_mode(self):
        """
        🔴 강등 기록은 **`embed`로 라벨되지 않는다.** 강등된 셀이 `embed`라는
        이름으로 표에 들어가는 것이 F21(옳은 숫자에 틀린 이름)이다.
        """
        _, notes = self._hits("embed")
        deg = [n for n in notes if n[0] == "degraded"]
        self.assertEqual(len(deg), 1)
        self.assertIn("lexical_fixed", deg[0][2])

    def test_failing_supplier_degrades(self):
        """공급자가 터져도 예외가 밖으로 나가지 않는다 — 나가면 강등 경로가 안 돈다."""
        def boom(_texts):
            raise ConnectionError("ollama가 응답하지 않는다")
        want, _ = self._hits("lexical_fixed")
        got, notes = self._hits("embed", boom)
        self.assertEqual(got, want)
        self.assertIn("degraded", kinds(notes))

    def test_working_supplier_does_not_degrade(self):
        """강등 기록이 **없을 때 없어야** 그 기록이 신호가 된다."""
        def fake(texts):
            # 쿼리와 완전히 같은 벡터를 첫 문서에만 준다 → 그 쌍만 코사인 1.0
            return [[1.0, 0.0]] * 2 + [[0.0, 1.0]] * (len(texts) - 2)
        got, notes = self._hits("embed", fake)
        self.assertNotIn("degraded", kinds(notes))
        self.assertTrue(got)

    def test_degradation_reaches_provenance(self):
        """`build_context`가 그 기록을 실제로 옮긴다 — 안 옮기면 아무도 못 본다."""
        M.RETRIEVAL_MODE, M.EMBED_FN = "embed", None
        ctx = self.m.build_context(CHAT, self.ask, 400)
        self.assertIn("degraded", [p[0] for p in ctx.provenance])

    def test_default_path_leaves_no_notes(self):
        """🔴 G16 — 기본값 경로는 provenance에 **한 줄도** 더하지 않는다."""
        _, notes = self._hits("lexical")
        self.assertEqual(notes, [])


class TestStaleTheta(unittest.TestCase):
    """**Q2-11** — θ는 모집단의 함수다. 색인이 움직여도 리터럴은 안 움직인다."""

    def setUp(self):
        self.orig = (M.RETRIEVAL_MODE, M.THETA_BY_MODE)
        self.m = seed(Memory(":memory:"))

    def tearDown(self):
        M.RETRIEVAL_MODE, M.THETA_BY_MODE = self.orig

    def test_signature_mismatch_is_recorded_but_not_fatal(self):
        M.RETRIEVAL_MODE = "lexical_fixed"       # 서명 (22, 21)로 유도된 모드
        self.m.retrieve(CHAT, "면접 준비 어떻게 됐더라", 400)
        kinds = [k for k, _, _ in self.m._retrieval_notes]
        self.assertIn("stale_theta", kinds)      # 이 색인은 3행이다 — 다르다
        self.assertNotIn("degraded", kinds)      # 값을 바꾸지도 죽지도 않았다

    def test_matching_signature_is_silent(self):
        """서명이 맞으면 **아무 말도 안 한다** — 그래야 말할 때 신호가 된다."""
        sig = self.m._population_sig(CHAT)
        M.THETA_BY_MODE = dict(M.THETA_BY_MODE,
                               lexical_fixed=(0.0435, 0.80, 378, sig))
        M.RETRIEVAL_MODE = "lexical_fixed"
        self.m.retrieve(CHAT, "면접 준비 어떻게 됐더라", 400)
        self.assertEqual(self.m._retrieval_notes, [])

    def test_lexical_never_claims_staleness(self):
        """`lexical`은 유도 모집단이 없다 — 대조할 것이 없으면 주장하지 않는다."""
        M.RETRIEVAL_MODE = "lexical"
        self.m.retrieve(CHAT, "면접 준비 어떻게 됐더라", 400)
        self.assertEqual(self.m._retrieval_notes, [])


class TestVectorWiring(unittest.TestCase):
    """
    **후속 9-b** — 문서 벡터 배선. 격자는 이 절반을 못 잰다.

    `soak.ingest`가 `add_event`를 거치지 않고 `INSERT INTO event`를 직접 치기
    때문에, **쓰기 경로 사전계산이 발화하는 곳은 이 파일뿐이다.** 격자가 재는 것은
    나머지 절반(읽기 경로의 지연 재계산)이다.

    🔴 **이 클래스가 붙잡는 계약은 넷이다.**
      ① 기본값 `lexical`에서는 벡터를 **한 개도** 만들지 않는다 (G16).
      ② `embed`에서 쓰기 경로가 만들고, 읽기 경로는 **질의만** 임베딩한다.
      ③ 없는 벡터·모델이 다른 벡터는 **지연 재계산**된다 — 조용히 건너뛰지 않는다.
         건너뛰면 그 행은 `rel`이 계산된 적도 없이 사라지고, 그것이 F21이다.
      ④ 공급자가 죽으면 **강등 경로는 배선 전과 똑같다.**
    """

    def setUp(self):
        self.orig = (M.RETRIEVAL_MODE, M.EMBED_FN, M.EMBED_MODEL_NAME)
        self.seen = []                 # 공급자가 실제로 받은 텍스트 목록

    def tearDown(self):
        M.RETRIEVAL_MODE, M.EMBED_FN, M.EMBED_MODEL_NAME = self.orig

    def _fn(self, dim=(1.0, 0.0)):
        """받은 텍스트를 기록하는 공급자. **몇 개를 받았는가**가 배선의 증거다."""
        def fn(texts):
            self.seen.append(list(texts))
            return [list(dim) for _ in texts]
        return fn

    def _vecs(self, m):
        return m.db.execute("SELECT key, model FROM embedding").fetchall()

    def test_default_mode_stores_no_vectors(self):
        """🔴 G16 — `lexical`에서는 `embedding` 테이블이 **비어 있다.**"""
        M.RETRIEVAL_MODE, M.EMBED_FN = "lexical", self._fn()
        m = seed(Memory(":memory:"))
        self.assertEqual(self._vecs(m), [])
        self.assertEqual(self.seen, [])          # 공급자를 부르지도 않았다

    def test_write_path_precomputes_in_embed_mode(self):
        """`embed`에서 `add_event`가 요약 하나마다 벡터 하나를 남긴다."""
        M.RETRIEVAL_MODE, M.EMBED_FN = "embed", self._fn()
        m = seed(Memory(":memory:"))
        rows = self._vecs(m)
        self.assertEqual(len(rows), 3)           # `seed`가 심는 사건 3개
        self.assertEqual({r["model"] for r in rows}, {M.EMBED_MODEL_NAME})
        self.assertEqual([len(t) for t in self.seen], [1, 1, 1])   # 한 건씩

    def test_read_path_embeds_only_the_query(self):
        """
        🟢 **배선이 산 것이 정확히 이것이다.** 배선 전에는 조회마다
        `[질의] + 색인 전량`이었다 — 여기서는 색인 3행이므로 4텍스트.
        """
        M.RETRIEVAL_MODE, M.EMBED_FN = "embed", self._fn()
        m = seed(Memory(":memory:"))
        self.seen.clear()
        m.retrieve(CHAT, "면접 준비 어떻게 됐더라", 400)
        self.assertEqual(self.seen, [["면접 준비 어떻게 됐더라"]])
        self.assertEqual(kinds(m._retrieval_notes).count("lazy_embed"), 0)

    def test_missing_vector_is_recomputed_not_skipped(self):
        """
        🔴 **F21 방어.** 벡터가 없는 행을 건너뛰면 그 행은 `rel` 없이 사라진다.
        여기서는 **없는 행에 만점 벡터를 주고**, 그 행이 1등으로 나오는지 본다 —
        건너뛰는 구현이라면 나올 수 없다.
        """
        M.RETRIEVAL_MODE = "lexical"
        m = seed(Memory(":memory:"))             # 벡터 0개로 색인을 만든다
        self.assertEqual(self._vecs(m), [])
        target = "지우가 강아지를 데리고 병원에 갔다"

        def fn(texts):
            self.seen.append(list(texts))
            return [[1.0, 0.0] if t in (texts[0], target) else [0.0, 1.0]
                    for t in texts]
        M.RETRIEVAL_MODE, M.EMBED_FN = "embed", fn
        hits, _ = m.retrieve(CHAT, "강아지 병원 갔던 거", 400)
        self.assertEqual(hits[0][1]["summary"], target)
        # 지연 재계산이 기록되고 **저장까지** 됐다
        note = [n for n in m._retrieval_notes if n[0] == "lazy_embed"]
        self.assertEqual(len(note), 1)
        self.assertIn("3/3", note[0][2])
        self.assertEqual(len(self._vecs(m)), 3)
        # 그리고 다음 조회는 질의 하나만 보낸다 — 저장이 실제로 먹혔다는 뜻이다
        self.seen.clear()
        m.retrieve(CHAT, "강아지 병원 갔던 거", 400)
        self.assertEqual([len(t) for t in self.seen], [1])

    def test_other_model_is_recomputed_not_reused(self):
        """
        모델이 다르면 옛 벡터를 **쓰지 않는다.** `db_get_vec`이 `(key, model)`로
        조회하므로 분기 없이 성립한다 — 그 성질을 시험이 붙잡는다.
        """
        M.RETRIEVAL_MODE, M.EMBED_FN = "embed", self._fn()
        m = seed(Memory(":memory:"))
        self.assertEqual(len(self._vecs(m)), 3)
        M.EMBED_MODEL_NAME = "다른-모델"         # 모델을 갈았다
        self.seen.clear()
        m.retrieve(CHAT, "면접 준비 어떻게 됐더라", 400)
        self.assertEqual(len(self.seen[0]), 4)   # 질의 1 + 색인 3 전부 다시
        self.assertIn("lazy_embed", kinds(m._retrieval_notes))
        # 옛 모델의 3행은 그대로 있고 새 모델의 3행이 **더해졌다**
        self.assertEqual(len(self._vecs(m)), 6)
        self.assertEqual({r["model"] for r in self._vecs(m)},
                         {self.orig[2], "다른-모델"})

    def test_degradation_is_unchanged_by_the_wiring(self):
        """④ 공급자가 죽으면 배선 전과 **똑같이** `lexical_fixed`로 내려간다."""
        M.RETRIEVAL_MODE = "lexical_fixed"
        m = seed(Memory(":memory:"))
        want, _ = m.retrieve(CHAT, "면접 준비 어떻게 됐더라", 400)
        M.RETRIEVAL_MODE, M.EMBED_FN = "embed", None
        got, _ = m.retrieve(CHAT, "면접 준비 어떻게 됐더라", 400)
        self.assertEqual([r["summary"] for _, r in got],
                         [r["summary"] for _, r in want])
        self.assertIn(("degraded", "embedding"),
                      [(k, w) for k, w, _ in m._retrieval_notes])
        self.assertEqual(self._vecs(m), [])      # 강등은 아무것도 저장하지 않는다


class TestDeterministicTieBreak(unittest.TestCase):
    """
    **후속 10** — `scored.sort`의 2차 키. 동점의 1등이 `SELECT` 반환 순서를
    그만 따르는가.

    🔴 **오늘의 숫자는 이 변경으로 움직이지 않는다** — SQLite가 오늘 rowid 순으로
       돌려주고 `event_id`가 곧 rowid이기 때문이다. 그래서 *"의존을 없앴다"*는
       주장은 **의존을 강제로 발화시켜야만** 검사할 수 있다. 아래가 그것이다:
       같은 후보 집합을 **다른 순서로** 넣고 1등이 같은지 본다.
    """

    def setUp(self):
        self.orig = M.RETRIEVAL_MODE
        self.m = seed(Memory(":memory:"))
        # 세 사건의 점수를 정확히 동점으로 만든다 (`imp` 같음 · `rel` 0 아님).
        self.m.db.execute("UPDATE event SET importance=0.5, emotional_weight=0.5,"
                          " summary='지우가 밤을 새웠다' WHERE event_id IN (1,2,3)")
        self.m.db.commit()

    def tearDown(self):
        M.RETRIEVAL_MODE = self.orig

    def _rows(self):
        return self.m.db.execute(
            "SELECT event_id, summary, importance, emotional_weight,"
            " surfaced_count FROM event WHERE chat_id=? AND user_deleted=0",
            (CHAT,)).fetchall()

    def test_the_three_are_actually_tied(self):
        """대조가 성립하려면 **먼저 동점이어야 한다** — 아니면 아무것도 안 재는 시험이다."""
        M.RETRIEVAL_MODE = "lexical"
        hits, _ = self.m.retrieve(CHAT, "지우 밤새운 거 기억나", 400)
        self.assertEqual(len(hits), 3)
        self.assertEqual(len({round(s, 10) for s, _ in hits}), 1)

    def test_winner_does_not_follow_input_order(self):
        """🟢 입력 순서를 셋으로 흔들어도 1등의 `event_id`가 같다."""
        M.RETRIEVAL_MODE = "lexical"
        base = self._rows()
        winners = set()
        for order in (base, base[::-1], base[1:] + base[:1]):
            scored = sorted(
                [(0.6 * 1.0 + 0.4 * 0.5, r) for r in order],
                key=lambda x: (-x[0], x[1]["event_id"]))
            winners.add(scored[0][1]["event_id"])
        self.assertEqual(winners, {min(r["event_id"] for r in base)})

    def test_the_old_key_did_follow_input_order(self):
        """
        🔴 **음성 대조.** 옛 키(`-s` 안정 정렬)로 같은 것을 하면 1등이 **셋 다 다르다.**
        이것이 없으면 위 시험은 통과할 수밖에 없는 시험이다 (G14 계열).
        """
        base = self._rows()
        winners = set()
        for order in (base, base[::-1], base[1:] + base[:1]):
            scored = sorted([(0.6 * 1.0 + 0.4 * 0.5, r) for r in order],
                            key=lambda x: -x[0])
            winners.add(scored[0][1]["event_id"])
        self.assertEqual(len(winners), 3)


if __name__ == "__main__":
    unittest.main()
