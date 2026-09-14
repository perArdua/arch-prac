# -*- coding: utf-8 -*-
"""
test_regen_k1_c9.py — 요약 층 수리 둘. (w20a · w17 수리 계획 묶음 A 중 결정과 무관한 둘)

  K1  `rewrite_lifetime`이 **stale인 세션 요약의 본문을 재료로 읽지 않는다.**
      삭제가 세션 요약을 stale로 밀고 그 재생성이 실패하면, 지운 사실이 든 그
      본문이 lifetime 프롬프트로 가서 **lifetime이 지운 사실을 되살린다.**
      `session_digests(limit=N)`의 SQL은 stale을 모른다 — 거르는 것은 호출부다.
  C9  `regen_job.run` ①(세션 요약)의 실패가 **경계 전체를 삼키지 않는다.**
      ②③처럼 잡아 `regen_failed`로 남기고 계속 간다. 그리고 요약을 만드는
      경계에 구간이 없으면 `ValueError` — 경계를 아는 호출부는 구간을 준다.

## 🔴 제품 경로만

삭제는 `delete_item`, 경계는 `regen_job.run`이다. `mark_stale`도, stale 테이블에
손으로 넣는 행도 없다 — 손으로 심은 stale은 제품이 만들지 않는 모양일 수 있고,
그러면 시험이 지키는 것이 제품이 아니게 된다.
대역은 `llm.generate`를 갈아 끼운다 — **LLM 생성 0회.**

## 심을 위반 (각 시험 독스트링이 자기 몫을 적는다)

  (m4)   `rewrite_lifetime`의 stale 제외를 없앤다      → K1 발화 둘
  (C9-a) ①의 `try`를 없앤다                           → C9 실패 기록 시험이 예외로 발화
  (C9-b) 구간 검사를 없앤다                           → «구간 미지정» 시험 발화

🔄 w31f (N1 · Q8 (a)) — ①의 실패는 이제 표지 행(본문 "" · 구간) + stale «미완:»을 남기고 다음 경계가
   재시도한다(`summarize.hold_session`). 그래서 `test_session_failure_is_recorded_and_the_boundary_goes_on`의
   `_session_rows()` 단언 둘은 **옛 기대**다 — 경계 1 뒤 `[("session:S01", 1, 6)]`(표지) · 경계 2 뒤
   `[("session:S01", 1, 6), ("session:S02", 7, 12)]`(②가 표지를 재시도해 성공 · 두 세션은 여전히 제 구간 ·
   `out["regen"]["ok"] == ["session:S01"]`). C9 계약(예외 없음 · `regen_failed` 1 · `missing` True · 구간 없는
   경계 거부 · 다음 경계에 S01 턴이 안 섞임)은 그대로다. 기대 교체는 마감 K 몫(이 레인은 이 파일의 독스트링만
   쓴다 · `.omc/notepads/w31f/progress.md`).
   🔄 w33k (마감 K) — 교체함. 그 시험 독스트링의 «기대 변경» 절이 근거 자리를 적는다.

⚠️ 변이는 `python -B`로 돌린다(낡은 `.pyc`가 생존자를 만든다).
DB는 전부 `tempfile`(= `%TEMP%`) 아래에 만든다.
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import llm                                                  # noqa: E402
import memory                                               # noqa: E402
import regen_job                                            # noqa: E402
import summarize                                            # noqa: E402
from memory import Memory                                   # noqa: E402

CHAT = "c-k1c9"

# 지운 쪽 비밀과 조용한 쪽 문장 — `test_deletion.py`의 고정물과 같은 낱말이다.
SECRET = "나 사실 마케팅 회사 대리로 일해"
QUIET = "고양이 나비가 요즘 밥을 잘 먹어"
TURNS = [(1, "user", "안녕 오늘 좀 피곤하다"), (2, "character", "왜, 무슨 일 있었냐"),
         (3, "user", SECRET), (4, "character", "그랬구나"),
         (5, "user", QUIET), (6, "character", "다행이네"),
         (7, "user", "오늘 동아리 모임 있어"), (8, "character", "재밌게 놀다 와")]

SESSION_HEAD = summarize._SESSION_MATERIAL_HEADER.split("{")[0]    # «[대화 — 세션 »
LIFE_HEAD = summarize._LIFETIME_MATERIAL_HEADER.split("{")[0]      # «[재료 — 세션 요약 »


class _Stub:
    """
    `llm.generate` 대역. 프롬프트를 전부 적는다.

    세션 요약 프롬프트에는 **재료의 유저 발화를 그대로 옮긴 요약**을 돌려준다 —
    요약기가 사실을 보존한 보통 경우다(최악이 아니다). lifetime에는 고정 문자열.
    `boom_sessions`면 세션 요약 프롬프트에서만, `boom_all`이면 전부에서
    `LLMError`를 올린다 — 생성이 멈춘 경우다.
    """

    def __init__(self, boom_sessions=False, boom_all=False):
        self.boom_sessions, self.boom_all = boom_sessions, boom_all
        self.prompts = []

    def __enter__(self):
        self._g, self._u = llm.generate, llm.last_usage
        stub = self

        def gen(prompt):
            stub.prompts.append(prompt)
            session = SESSION_HEAD in prompt
            if stub.boom_all or (stub.boom_sessions and session):
                raise llm.LLMError("시험이 심은 실패")
            if session:
                return " / ".join(line.split("] ", 1)[1]
                                  for line in prompt.splitlines() if "[user]" in line)
            return "lifetime 요약 (대역)"

        llm.generate = gen
        llm.last_usage = lambda: {"prompt_eval_count": 100}
        return self

    def __exit__(self, *exc):
        llm.generate, llm.last_usage = self._g, self._u
        return False

    def lifetime_prompts(self):
        return [p for p in self.prompts if LIFE_HEAD in p]


class _Case(unittest.TestCase):
    """새 DB 하나 · 재시도 1회(대역 실패에 3초씩 자지 않게)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.m = Memory(os.path.join(self.tmp, "t.db"))
        self.m.db.execute("INSERT INTO chat VALUES (?,?,?,?)",
                          (CHAT, "jiwoo", "seojun", 1))
        self.m.db.commit()
        self._saved = (summarize.GEN_RETRIES, summarize.GEN_RETRY_SLEEP)
        summarize.GEN_RETRIES, summarize.GEN_RETRY_SLEEP = 1, 0.0

    def tearDown(self):
        summarize.GEN_RETRIES, summarize.GEN_RETRY_SLEEP = self._saved
        self.m.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def prov(self, kind):
        return [tuple(r) for r in self.m.db.execute(
            "SELECT item, reason FROM provenance WHERE chat_id=? AND kind=?",
            (CHAT, kind))]


# ── K1 — lifetime 재료에서 stale 세션 요약을 뺀다 ────────────────────────

class TestLifetimeMaterialSkipsStale(_Case):

    def _build(self, sessions):
        """턴 1–8 · 비밀 사실(턴 3) · 세션 요약 · lifetime. 반환: 삭제 전 lifetime 프롬프트."""
        for seq, role, text in TURNS:
            self.m.add_turn(CHAT, seq, role, text)
        self.m.upsert_fact(CHAT, "지우", "직업", "마케팅 회사 대리", seq=3,
                           importance=0.8)
        self.fid = self.m.db.execute("SELECT fact_id FROM fact WHERE chat_id=?",
                                     (CHAT,)).fetchone()[0]
        with _Stub() as st:
            for sid, a, b in sessions:
                summarize.session_digest(self.m, CHAT, sid, from_seq=a, to_seq=b)
            summarize.rewrite_lifetime(self.m, CHAT)
        before = st.lifetime_prompts()
        self.assertEqual(len(before), 1)
        # 대조의 바닥 — 삭제 전 lifetime 프롬프트에 비밀이 **정확히 한 번** 있다.
        # 이것이 없으면 아래 «0회» 단언은 발화할 수 없는 검사다.
        self.assertEqual(before[0].count(SECRET), 1)
        return before[0]

    def test_stale_session_body_is_not_in_the_lifetime_prompt(self):
        """
        🔴 발화 — 진짜 `delete_item`으로 S01이 stale · S01 재생성은 실패 · lifetime은
        다시 쓴다. 그 프롬프트에 S01 본문(비밀)이 **없다.**

        심을 위반 (m4): stale 제외를 없애면 비밀이 0회 → 1회가 되고
        `lifetime_material_excluded`가 1 → 0이 된다.
        """
        self._build([("S01", 1, 4), ("S02", 5, 8)])
        self.m.delete_item(CHAT, "fact", self.fid)
        self.assertIn("삭제됨", self.m.stale_row(CHAT, "digest", "session:S01")[0])
        self.assertIsNotNone(self.m.stale_row(CHAT, "digest", "lifetime"))

        with _Stub(boom_sessions=True) as st:
            out = regen_job.run(self.m, CHAT, now_seq=9, make_digest=False)

        self.assertEqual([k for k, _ in out["regen"]["failed"]], ["session:S01"])
        self.assertEqual(out["regen"]["ok"], ["lifetime"])
        life = st.lifetime_prompts()
        self.assertEqual(len(life), 1)
        self.assertEqual(life[0].count(SECRET), 0,
                         "stale인 S01 본문이 lifetime 재료로 갔다 — 지운 사실이 되살아난다")
        # 조용한 쪽 — 안 빠진 재료는 그대로 간다(전부 빼는 회귀를 막는다).
        s02 = self.m.db.execute("SELECT content FROM digest_session WHERE chat_id=?"
                                " AND kind='session:S02'", (CHAT,)).fetchone()[0]
        self.assertIn(QUIET, s02)
        self.assertIn(s02, life[0])
        self.assertIn(summarize._LIFETIME_MATERIAL_HEADER.format(k=1), life[0])

        got = self.prov("lifetime_material_excluded")
        self.assertEqual(len(got), 1)
        self.assertIn("session:S01", got[0][1])
        # 재생성이 실패한 S01은 stale로 남는다(§6.4 ③) — 빼는 것은 재료에서뿐이다.
        self.assertIsNotNone(self.m.stale_row(CHAT, "digest", "session:S01"))
        self.assertIsNone(self.m.stale_row(CHAT, "digest", "lifetime"))
        # 새 lifetime의 계보에 뺀 키가 없다 — 재료에 없던 것을 원본으로 적지 않는다.
        keys = [r[0] for r in self.m.db.execute(
            "SELECT source_id FROM derivation WHERE chat_id=? AND derived_kind='digest'"
            " AND derived_key='lifetime' AND source_kind='digest'", (CHAT,))]
        self.assertEqual(keys, ["session:S02"])

    def test_all_material_stale_is_the_zero_material_error(self):
        """
        🔴 발화 — 재료가 S01 하나뿐이고 그것이 stale이면 재료 0건 → `ValueError` →
        `regenerate_stale`의 기존 `except`가 `regen_failed`로 남기고 lifetime은 stale
        유지. lifetime 프롬프트는 **만들어지지도 않는다.**

        심을 위반 (m4): stale 제외를 없애면 lifetime이 비밀을 싣고 다시 써진다
        (`ok`에 lifetime · 프롬프트 1건).
        """
        self._build([("S01", 1, 4)])
        self.m.delete_item(CHAT, "fact", self.fid)

        with _Stub(boom_sessions=True) as st:
            out = regen_job.run(self.m, CHAT, now_seq=9, make_digest=False)

        self.assertEqual(out["regen"]["ok"], [])
        self.assertEqual([k for k, _ in out["regen"]["failed"]],
                         ["session:S01", "lifetime"])
        self.assertEqual(st.lifetime_prompts(), [])
        self.assertIsNotNone(self.m.stale_row(CHAT, "digest", "lifetime"))
        reasons = dict(self.prov("regen_failed"))
        self.assertIn("재료 0건", reasons["lifetime"])
        self.assertEqual(len(self.prov("lifetime_material_excluded")), 1)

    def test_stale_free_material_prompt_is_byte_identical(self):
        """
        조용한 쪽 — stale이 없으면 lifetime 프롬프트는 **옛 조립식과 바이트 동일**하고
        `lifetime_material_excluded`는 0이다. 체크포인트 키가 프롬프트다 — 여기서
        한 글자가 움직이면 기록된 lifetime 생성이 전부 다시 돈다.
        """
        before = self._build([("S01", 1, 4), ("S02", 5, 8)])
        rows = list(self.m.session_digests(
            CHAT, limit=memory.DIGEST_KEEP_SESSIONS))[::-1]
        material = "\n\n".join(
            f"[{r['kind']} · 턴 {r['covers_from_seq']}–{r['covers_to_seq']}]\n"
            f"{r['content']}" for r in rows)
        expect = (summarize.P4_TEMPLATE.format(budget=summarize.LIFETIME_BUDGET_TOKENS)
                  + "\n\n" + summarize._LIFETIME_MATERIAL_HEADER.format(k=len(rows))
                  + "\n" + material + "\n\n[다시 쓴 요약]\n")
        self.assertEqual(before, expect)
        with _Stub() as st:
            summarize.rewrite_lifetime(self.m, CHAT)
        self.assertEqual(st.lifetime_prompts(), [expect])
        self.assertEqual(self.prov("lifetime_material_excluded"), [])


# ── C9 — `regen_job.run` ①의 실패를 잡는다 · 구간 없는 경계를 거부한다 ──

class TestRegenJobSessionFailure(_Case):

    def setUp(self):
        super().setUp()
        for s in range(1, 13):
            self.m.add_turn(CHAT, s, "user" if s % 2 else "character", f"턴{s}")
        self.m.db.commit()

    def _session_rows(self):
        return [tuple(r) for r in self.m.db.execute(
            "SELECT kind, covers_from_seq, covers_to_seq FROM digest_session"
            " WHERE chat_id=? ORDER BY kind", (CHAT,))]

    def test_session_failure_is_recorded_and_the_boundary_goes_on(self):
        """
        🔴 발화 — ①의 생성이 멈춰도 `run()`은 예외를 올리지 않는다. 실패는
        `out["session"]`과 `regen_failed`에 남고 ②③과 침묵 탐지는 그대로 돈다.
        다음 경계는 자기 구간(7–12)만 요약한다 — 두 세션이 한 키로 묶이지 않는다.

        심을 위반 (C9-a): ①의 `try`를 없애면 `LLMError`가 이 시험 밖으로 샌다.

        🔄 기대 변경 — Q8 (a) · w31f D1~D5 · 근거 자리: `.omc/notepads/w31f/prereg.md` §4(값 보기 전 예측) ·
           `.omc/notepads/w31f/progress.md` «K 몫» 1 · `.omc/notepads/w33k/expect_out.txt`(수리 전 사본에서 옛 기대
           초록 · 새 기대 빨강 / 수리 뒤 트리에서 새 기대 초록 · 옛 기대로 되돌린 변이 빨강). ①의 실패는 이제
           표지 행(본문 "" · 구간 1–6)을 남기고(D1 — ②③ 뒤에 써서 같은 경계는 재시도 안 함) 다음 경계의 ②가
           재시도한다 → 경계 1 뒤 `_session_rows()`는 `[]` → 표지 한 행 · 경계 2 뒤 `[S02]` → `[S01, S02]`.
           목적(두 세션이 한 키로 묶이지 않는다)은 재시도 쪽에서도 단언한다 — S01 재시도 프롬프트는 1–6만,
           S02 프롬프트는 7–12만 품는다. C9 계약(예외 없음 · `regen_failed` 1 · `missing` True)은 그대로다.
        """
        with _Stub(boom_all=True):
            out = regen_job.run(self.m, CHAT, now_seq=7, ended_session_id="S01",
                                from_seq=1, to_seq=6)
        self.assertEqual(out["session"][0], "failed")
        self.assertIn("시험이 심은 실패", out["session"][1])
        self.assertEqual([i for i, _ in self.prov("regen_failed")], ["session:S01"])
        self.assertEqual(out["regen"], {"ok": [], "failed": []})
        self.assertTrue(out["missing"])
        self.assertEqual(len(self.prov("regen_missing")), 1)
        self.assertEqual(self._session_rows(), [("session:S01", 1, 6)])   # 표지 행 — 요약이 아니다
        self.assertEqual(self.m.db.execute("SELECT content FROM digest_session WHERE chat_id=?",
                                           (CHAT,)).fetchone()[0], "")

        with _Stub() as st:
            out = regen_job.run(self.m, CHAT, now_seq=13, ended_session_id="S02",
                                from_seq=7, to_seq=12)
        self.assertEqual(out["session"], ("session:S02", []))
        self.assertEqual(out["regen"], {"ok": ["session:S01"], "failed": []})   # ②가 표지를 재시도해 성공
        self.assertFalse(out["missing"])
        self.assertEqual(self._session_rows(), [("session:S01", 1, 6), ("session:S02", 7, 12)])
        self.assertNotIn("\n1. [user] 턴1\n", st.prompts[0])     # S01 턴이 안 섞였다
        self.assertIn("\n7. [user] 턴7\n", st.prompts[0])
        by = {k: [p for p in st.prompts if f"{SESSION_HEAD}{k} · " in p] for k in ("session:S01", "session:S02")}
        self.assertEqual([len(v) for v in by.values()], [1, 1])
        self.assertIn("\n7. [user] 턴7\n", by["session:S02"][0])
        self.assertNotIn("\n1. [user] 턴1\n", by["session:S02"][0])
        self.assertIn("\n1. [user] 턴1\n", by["session:S01"][0])
        self.assertNotIn("\n7. [user] 턴7\n", by["session:S01"][0])     # 재시도가 S02 턴을 끌어오지 않았다

    def test_digest_boundary_without_range_is_refused(self):
        """
        🔴 발화 — 요약을 만드는 경계에 구간이 없으면 `ValueError`이고 LLM을 안
        부른다. 구간을 추측하면(`session_digest`의 기본값) 앞 세션이 실패한 뒤에
        두 세션이 한 키로 묶인다.

        심을 위반 (C9-b): 구간 검사를 없애면 예외가 안 나고 `session:S02`가 1–12로
        생긴다.
        """
        for kw in ({}, {"from_seq": 7}, {"to_seq": 12}):
            with self.subTest(**{k: str(v) for k, v in kw.items()}):
                with _Stub() as st:
                    with self.assertRaises(ValueError):
                        regen_job.run(self.m, CHAT, now_seq=13,
                                      ended_session_id="S02", **kw)
                self.assertEqual(st.prompts, [])
                self.assertEqual(self._session_rows(), [])

    def test_normal_boundary_output_is_unchanged(self):
        """조용한 쪽 — 정상 경계의 `out["session"]`은 `(kind, dropped)` 그대로 · 실패 기록 0."""
        with _Stub() as st:
            out = regen_job.run(self.m, CHAT, now_seq=7, ended_session_id="S01",
                                from_seq=1, to_seq=6)
        self.assertEqual(out["session"], ("session:S01", []))
        self.assertEqual(out["regen"], {"ok": [], "failed": []})
        self.assertIsNone(out["lifetime"])
        self.assertFalse(out["missing"])
        self.assertEqual(self.prov("regen_failed"), [])
        self.assertEqual(len(st.prompts), 1)
        self.assertEqual(self._session_rows(), [("session:S01", 1, 6)])

    def test_boundary_that_makes_no_digest_needs_no_range(self):
        """
        조용한 쪽 — 기존 계약. `make_digest=False`면 `ended_session_id`만 주고 구간을
        안 줘도 된다(`test_serving.py`의 `TestRegenJob`이 그렇게 부른다). 구간 검사는
        **①이 도는 경계에만** 건다.
        """
        with _Stub() as st:
            out = regen_job.run(self.m, CHAT, now_seq=7, ended_session_id="S01",
                                make_digest=False)
        self.assertIsNone(out["session"])
        self.assertTrue(out["missing"])
        self.assertEqual(st.prompts, [])


if __name__ == "__main__":
    unittest.main()
