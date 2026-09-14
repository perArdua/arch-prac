# -*- coding: utf-8 -*-
"""
test_digest_cap.py — N 상한에 밀려난 세션 키가 **흔적을 남기지 않는가.** (w20b · w17 수리 계획 발견 4 · 검토 R4)

`put_session_digest`는 저장 상한 N(`DIGEST_KEEP_SESSIONS`)을 넘긴 세션 키를 지우면서
`stale`·`digest_meta`의 고아 행을 함께 지웠다(G19′③). 그런데 **`derivation`은 안 지웠다.**
그 행이 남으면 옛 세션 구간의 사실을 지울 때 `_invalidate_derived`가 이미 없는 키를
stale로 찍고(유령), `regenerate_stale`은 덮을 구간을 몰라 **경계마다 실패를 남긴다** —
그 stale 행은 영원히 안 풀린다.

## 🔴 제품 경로만

세션 요약은 `summarize.session_digest`(진짜 저장 · 진짜 파생 등록), 삭제는 `delete_item`,
재생성은 `regenerate_stale`이다. `mark_stale`도, 손으로 넣는 stale·derivation 행도 없다.
대역은 `llm.generate`만 갈아 끼운다 — **LLM 생성 0회.**

## 심을 위반

  (m1) `_forget_digest_key`에서 derivation DELETE를 뺀다 → 시끄러운 쪽 둘 발화
       (표식: 밀려난 키의 파생 행 0 → 1 · `regen_failed` 0 → ≥1)
조용한 쪽(남은 키의 파생 등록 · lifetime의 파생 등록 · lifetime은 삭제로 stale이 된다)은
과잉 삭제 변이에서 운다 — 모든 키의 파생 행을 지우면 남은 키 대조가 발화한다.

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
import summarize                                            # noqa: E402
from memory import Memory, session_kind                     # noqa: E402

CHAT = "c-cap"
N = memory.DIGEST_KEEP_SESSIONS
TURNS_PER_SESSION = 2


def span(s):
    """세션 번호(1부터) → (첫 seq, 끝 seq)."""
    return (s - 1) * TURNS_PER_SESSION + 1, s * TURNS_PER_SESSION


def sid(s):
    return f"S{s:02d}"


class _Stub:
    """`llm.generate` 대역 — 무엇을 받든 고정 요약. 생성이 실패하는 경로는 이 파일이 재지 않는다."""

    def __enter__(self):
        self._g, self._u = llm.generate, llm.last_usage
        llm.generate = lambda prompt: "요약 (대역)"
        llm.last_usage = lambda: {"prompt_eval_count": 100}
        return self

    def __exit__(self, *exc):
        llm.generate, llm.last_usage = self._g, self._u
        return False


class _Case(unittest.TestCase):
    """
    N+1 세션 · 세션마다 사실 하나(그 세션 첫 턴에서 나온 것). 세션 1..N을 요약하고 lifetime을
    한 번 쓴 뒤(그때는 S01이 재료다), 세션 N+1을 요약해 S01을 상한 밖으로 민다.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cap-")
        self.m = Memory(os.path.join(self.tmp, "t.db"))
        self.m.db.execute("INSERT INTO chat VALUES (?,?,?,?)",
                          (CHAT, "jiwoo", "seojun", 1))
        self.m.db.commit()
        self._saved = (summarize.GEN_RETRIES, summarize.GEN_RETRY_SLEEP)
        summarize.GEN_RETRIES, summarize.GEN_RETRY_SLEEP = 1, 0.0
        self.fid = {}
        for s in range(1, N + 2):
            a, b = span(s)
            for seq in range(a, b + 1):
                self.m.add_turn(CHAT, seq, "user" if seq % 2 else "character", f"{sid(s)} 턴 {seq}")
            # 술어를 세션마다 달리한다 — 단일값 술어의 갱신(무효화)이 끼면 이 시험이 재는 것이 흐려진다.
            self.m.upsert_fact(CHAT, "지우", f"일상_사소_{s}", f"{sid(s)}의 일", seq=a, importance=0.5)
            self.fid[s] = self.m.db.execute(
                "SELECT fact_id FROM fact WHERE chat_id=? AND source_turn_seq=?",
                (CHAT, a)).fetchone()["fact_id"]
        with _Stub():
            for s in range(1, N + 1):
                a, b = span(s)
                summarize.session_digest(self.m, CHAT, sid(s), from_seq=a, to_seq=b)
            summarize.rewrite_lifetime(self.m, CHAT)
            self.before = {k: self.deriv(k) for k in self.kept_keys() + ["lifetime"]}
            self.meta_before = self.n_meta(session_kind(sid(1)))
            a, b = span(N + 1)
            _, _, self.dropped = summarize.session_digest(self.m, CHAT, sid(N + 1), from_seq=a, to_seq=b)

    def tearDown(self):
        summarize.GEN_RETRIES, summarize.GEN_RETRY_SLEEP = self._saved
        self.m.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── 도우미 ─────────────────────────────────────────────────────────
    def kept_keys(self):
        """상한 뒤에도 남을 키 — S02..SN (S(N+1)은 아직 없다)."""
        return [session_kind(sid(s)) for s in range(2, N + 1)]

    def deriv(self, key):
        return sorted(tuple(r) for r in self.m.db.execute(
            "SELECT source_kind, source_id FROM derivation"
            " WHERE chat_id=? AND derived_kind='digest' AND derived_key=?", (CHAT, key)))

    def stale_keys(self):
        return sorted(r[0] for r in self.m.db.execute(
            "SELECT derived_key FROM stale WHERE chat_id=? AND derived_kind='digest'", (CHAT,)))

    def n_meta(self, key):
        return self.m.db.execute("SELECT COUNT(*) FROM digest_meta WHERE chat_id=? AND kind=?",
                                 (CHAT, key)).fetchone()[0]

    def n_prov(self, kind):
        return self.m.db.execute("SELECT COUNT(*) FROM provenance WHERE chat_id=? AND kind=?",
                                 (CHAT, kind)).fetchone()[0]


class TestDroppedKeyLeavesNoTrace(_Case):

    def test_setup_really_dropped_the_first_session(self):
        """대조의 바닥. 이것이 빨가면 아래 시험은 **아무것도 안 잰다.**"""
        s01 = session_kind(sid(1))
        self.assertEqual(self.dropped, [s01])
        self.assertEqual(self.m.db.execute(
            "SELECT COUNT(*) FROM digest_session WHERE chat_id=?", (CHAT,)).fetchone()[0], N)
        # 밀려나기 전에는 S01에 그 세션 사실의 파생 등록이 **있었다** — lifetime 재료 계보가 증인이다.
        self.assertIn(("digest", s01), self.before["lifetime"])
        self.assertIn(("fact", str(self.fid[1])), self.before["lifetime"])

    def test_dropped_key_leaves_no_derivation_and_no_ghost_stale(self):
        """
        🔴 시끄러운 쪽. 밀려난 키의 파생 행 0 → 그 세션의 사실을 지워도 유령 stale 0 →
        `regenerate_stale` 실패 0 · `regen_failed` 0.

        **심을 위반:** (m1) 헬퍼에서 derivation DELETE를 빼면 첫 단언부터 운다(0 → 1).
        """
        s01 = session_kind(sid(1))
        self.assertEqual(self.deriv(s01), [], "밀려난 키의 파생 등록이 남았다")
        hit = self.m.delete_item(CHAT, "fact", self.fid[1])
        self.assertNotIn(("digest", s01), hit)
        self.assertNotIn(s01, self.stale_keys(), "이미 없는 키가 stale로 찍혔다 — 유령")
        with _Stub():
            out = summarize.regenerate_stale(self.m, CHAT)
        self.assertEqual(out["failed"], [])
        self.assertEqual(self.n_prov("regen_failed"), 0)

    def test_ghost_does_not_come_back_at_every_boundary(self):
        """경계마다 재생성이 불려도(여기선 세 번) 실패가 쌓이지 않는다 — 검토 R4의 «3/3회 누적»."""
        self.m.delete_item(CHAT, "fact", self.fid[1])
        with _Stub():
            fails = [summarize.regenerate_stale(self.m, CHAT)["failed"] for _ in range(3)]
        self.assertEqual(fails, [[], [], []])
        self.assertEqual(self.stale_keys(), [])


class TestQuietSide(_Case):
    """조용한 쪽 — 헬퍼가 **밀려난 키 하나만** 지운다."""

    def test_kept_keys_keep_their_derivation(self):
        """남은 키(S02..SN)의 파생 등록은 한 행도 안 움직인다."""
        for k in self.kept_keys():
            with self.subTest(key=k):
                self.assertEqual(self.deriv(k), self.before[k])
                self.assertTrue(self.deriv(k), "남은 키의 파생 등록이 비었다")

    def test_new_key_is_registered(self):
        s = N + 1
        self.assertEqual(self.deriv(session_kind(sid(s))), [("fact", str(self.fid[s]))])

    def test_lifetime_derivation_is_untouched_and_still_follows_deletion(self):
        """
        lifetime은 밀려난 세션 키를 **원본**으로 적고 있다 — 그 행은 헬퍼의 대상이 아니다.
        그래서 S01의 사실을 지우면 lifetime은 여전히 stale이 된다(정상 · 발견 1의 방어선).
        """
        self.assertEqual(self.deriv("lifetime"), self.before["lifetime"])
        self.m.delete_item(CHAT, "fact", self.fid[1])
        self.assertIn("lifetime", self.stale_keys())
        with _Stub():
            out = summarize.regenerate_stale(self.m, CHAT)
        self.assertIn("lifetime", out["ok"])
        self.assertNotIn("lifetime", self.stale_keys())

    def test_deleting_a_kept_session_fact_still_pushes_that_key(self):
        """남은 세션의 사실을 지우면 그 세션 키는 여전히 stale이 되고 재생성된다."""
        k = session_kind(sid(5))
        self.m.delete_item(CHAT, "fact", self.fid[5])
        self.assertIn(k, self.stale_keys())
        with _Stub():
            out = summarize.regenerate_stale(self.m, CHAT)
        self.assertIn(k, out["ok"])
        self.assertEqual(out["failed"], [])

    def test_digest_meta_of_the_dropped_key_is_still_cleared(self):
        """
        옛 DELETE가 헬퍼로 옮겨 가며 빠지지 않았다 — 밀려나기 전에 있던 S01의 `digest_meta` 행이
        밀려난 뒤 0이다. (stale 쪽의 같은 성질은 `TestPropagation`의 I5-b 상한이 지킨다.)
        """
        self.assertEqual((self.meta_before, self.n_meta(session_kind(sid(1)))), (1, 0))


if __name__ == "__main__":
    unittest.main()
