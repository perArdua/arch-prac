# -*- coding: utf-8 -*-
"""
test_debt_trigger.py — 서사 부채가 설계대로 돈다: 세션 백오프 · 트리거 분기 · 상환. (wave4 T1)

## 왜

실험 10이 부채 표에 칸 셋(`trigger_clock` · 백오프용 두 칸)을 더했는데, 백오프는 턴으로
셌고(`WINDOW_TURNS` × 1·3·7) 시계 칸과 트리거 spec은 **읽는 코드가 없었다.** 그리고
`apply_meta`는 `used_memories`의 `debt:` id를 버려서 `paid`로 가는 길이 아예 없었다.

기본 경로(소크)에는 부채 행이 0이라 여기서 못 본다(U6) — 그래서 **진짜 쓰기 경로**
(`apply_meta`의 `new_debt`)로 심고 **진짜 읽기 경로**(`build_context`)로 태운다.
세션 경계는 요약 층이 쓰는 행(`put_session_digest`)으로 만든다 — 백오프가 그 행을 센다.

## 재현

    PYTHONIOENCODING=utf-8 python -B -m unittest discover -s prototype/tests -p "test_debt_trigger.py"
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import memory                                              # noqa: E402
from memory import Memory                                  # noqa: E402

CHAT = "c-debt"
OTHER = "c-debt-남"
SESSION = 10          # 이 파일의 세션 길이(턴). 세션 k는 10(k-1)+1 .. 10k


def seed(m, chat_id=CHAT):
    m.db.execute("INSERT OR IGNORE INTO character_version (character_id, version,"
                 " persona_text, speech_rules, taboos) VALUES (?,?,?,?,?)",
                 ("seojun", 1, "페르소나", "반말", "금기"))
    m.db.execute("INSERT INTO chat (chat_id, user_id, character_id,"
                 " character_version) VALUES (?,?,?,?)", (chat_id, "jiwoo", "seojun", 1))
    m.db.execute("INSERT INTO relationship (chat_id, stage, affinity, called_as,"
                 " user_locked, updated_by_turn) VALUES (?,?,?,?,?,?)",
                 (chat_id, "연인", 84, "지우", 0, 0))
    m.db.commit()


def plant(m, seq, kind, spec=None, clock="session", chat_id=CHAT):
    """진짜 쓰기 경로로 심는다 — `apply_meta`의 `new_debt`."""
    nd = {"content": f"부채-{kind}-{spec}", "trigger_kind": kind, "trigger_spec": spec,
          "trigger_clock": clock}
    m.apply_meta(chat_id, seq, {"new_debt": nd})
    return m.db.execute("SELECT MAX(debt_id) FROM debt").fetchone()[0]


def end_session(m, k, chat_id=CHAT):
    """세션 k가 끝났다 — 요약 층이 남기는 한 행(내용은 대역)."""
    m.put_session_digest(chat_id, f"S{k:02d}", "(경계 대역)",
                         covers_from_seq=SESSION * (k - 1) + 1, covers_to_seq=SESSION * k)


def start_of(k):
    return SESSION * (k - 1) + 1


def row(m, did):
    return m.db.execute("SELECT * FROM debt WHERE debt_id=?", (did,)).fetchone()


def notes_for(ctx, did):
    return [p for p in ctx.provenance if p[0] == "degraded" and p[1] == f"debt:{did}"]


def injected(ctx):
    return [p[1] for p in ctx.provenance if p[0] == "debt"]


class Base(unittest.TestCase):
    def setUp(self):
        self.m = Memory(":memory:")
        seed(self.m)

    def ctx_at(self, seq, session_start):
        return self.m.build_context(CHAT, "그냥 얘기", seq, session_start=session_start)


class 백오프는_세션(Base):
    def test_같은_세션_안에서는_턴이_지나도_안_나간다(self):
        """🔴 옛 판정(턴 × 10)이면 24턴 뒤에 나갔다. 세션이 안 끝났으면 경계는 0이다."""
        did = plant(self.m, 5, "semantic", "일 얘기가 나오면")
        self.assertEqual(injected(self.ctx_at(29, False)), [], "세션 안에서 나갔다")
        self.assertEqual(row(self.m, did)["attempt_count"], 0)
        end_session(self.m, 1)
        self.assertEqual(len(injected(self.ctx_at(31, True))), 1,
                         "세션이 끝났는데 안 나갔다 — 조용한 쪽")

    def test_1_3_7_세션_뒤_소멸(self):
        """docs/06 §L9 «1세션 → 3세션 → 7세션 → 만료». 세션 시작마다 한 번씩 부른다."""
        did = plant(self.m, 5, "session_start")
        tried, expired_at = [], None
        for k in range(2, 25):
            end_session(self.m, k - 1)
            before = row(self.m, did)["attempt_count"]
            self.ctx_at(start_of(k), True)
            r = row(self.m, did)
            if r["attempt_count"] > before:
                tried.append(k)
            if r["status"] == "expired" and expired_at is None:
                expired_at = k
        self.assertEqual(tried, [2, 5, 12], "시도 세션이 1·3·7 경계 간격이 아니다")
        self.assertEqual(expired_at, 19, "마지막 시도 뒤 7경계에서 소멸해야 한다")

    def test_세션_마지막_턴에_심은_부채도_경계_하나를_센다(self):
        """카운터는 «그 수보다 뒤에 끝난 세션»을 센다 — 마지막 턴(10)에 심으면 그 세션의 끝이
        10이라 `> 10`으로는 안 잡힌다. 한 칸 앞을 넘겨야 경계 1이다(대장 D003이 이 자리다)."""
        did = plant(self.m, SESSION, "session_start")
        end_session(self.m, 1)
        ctx = self.ctx_at(start_of(2), True)
        self.assertEqual(len(injected(ctx)), 1)
        self.assertEqual(notes_for(ctx, did), [], "경계 행이 있는데 카운터가 모른다고 적었다")

    def test_backoff_상수는_요약_보존_상한_안에_있다(self):
        """경계는 `digest_session` 행으로 센다 — 상한보다 긴 백오프는 영영 못 닿는다."""
        self.assertLessEqual(max(memory.DEBT_BACKOFF_SESSIONS), memory.DIGEST_KEEP_SESSIONS)


class 트리거_분기(Base):
    def test_Nd는_세션_시계에서_N_경계(self):
        did = plant(self.m, 5, "time", "3d", "session")
        for k in (2, 3):
            end_session(self.m, k - 1)
            self.assertEqual(injected(self.ctx_at(start_of(k), True)), [],
                             f"S{k:02d}에서 나갔다 — 경계 {k - 1} < 3")
        end_session(self.m, 3)
        ctx = self.ctx_at(start_of(4) + 3, False)   # 세션 시작이 아니어도 된다
        self.assertEqual(len(injected(ctx)), 1, "경계 3에서 안 나갔다")
        self.assertEqual(notes_for(ctx, did), [], "평가한 트리거에 강등 기록이 붙었다")

    def test_세션_시작_게이트(self):
        plant(self.m, 5, "session_start")
        end_session(self.m, 1)
        self.assertEqual(injected(self.ctx_at(start_of(2) + 1, False)), [])
        self.assertEqual(len(injected(self.ctx_at(start_of(2) + 2, True))), 1)

    def test_평가_못_하는_트리거는_강등을_남기고_나간다(self):
        cases = [("semantic", "서준의 과거 얘기가 나오면", "session", "의미 트리거"),
                 ("time", "2026-07-28", "session", "셀 수 없다"),
                 ("time", "3d", "wall", "셀 수 없다"),
                 ("time", None, "session", "셀 수 없다"),
                 ("time", "30d", "session", "요약 보존 상한"),
                 ("엉뚱", None, "session", "모르는 trigger_kind")]
        for i, (kind, spec, clock, word) in enumerate(cases):
            with self.subTest(kind=kind, spec=spec, clock=clock):
                m = Memory(":memory:")
                seed(m)
                did = plant(m, 5, kind, spec, clock)
                end_session(m, 1)
                ctx = m.build_context(CHAT, "그냥 얘기", start_of(2), session_start=True)
                self.assertEqual(len([p for p in ctx.provenance if p[0] == "debt"]), 1,
                                 "강등 경로가 조용히 죽었다")
                got = notes_for(ctx, did)
                self.assertEqual(len(got), 1, f"강등 기록 {len(got)}건")
                self.assertIn(word, got[0][2])

    def test_경계_카운터가_비면_최소_1로_세고_남긴다(self):
        """요약 층이 안 돌면(U8) 카운터는 0이다. 세션 첫 턴은 경계를 지났다는 직접 관측이다."""
        did = plant(self.m, 5, "session_start")
        ctx = self.ctx_at(start_of(2), True)         # end_session을 부르지 않았다
        self.assertEqual(len(injected(ctx)), 1)
        self.assertTrue(any("카운터" in p[2] for p in notes_for(ctx, did)))
        # 조용한 쪽 — 행이 있으면 그 기록은 없다
        m = Memory(":memory:")
        seed(m)
        d2 = plant(m, 5, "session_start")
        end_session(m, 1)
        ctx = m.build_context(CHAT, "그냥 얘기", start_of(2), session_start=True)
        self.assertEqual(notes_for(ctx, d2), [])


class 상환(Base):
    def _inject(self, did):
        end_session(self.m, 1)
        self.assertEqual(len(injected(self.ctx_at(start_of(2), True))), 1)
        self.assertEqual(row(self.m, did)["attempt_count"], 1)

    def test_open에서_paid로(self):
        did = plant(self.m, 5, "session_start")
        self._inject(did)
        self.m.apply_meta(CHAT, start_of(2) + 1, {"used_memories": [f"debt:{did}"]})
        self.assertEqual(row(self.m, did)["status"], "paid")
        paid = self.m.db.execute("SELECT item FROM provenance WHERE kind='debt_paid'").fetchall()
        self.assertEqual([p[0] for p in paid], [f"debt:{did}"])
        # 갚은 부채는 다시 안 나간다
        end_session(self.m, 2)
        self.assertEqual(injected(self.ctx_at(start_of(3), True)), [])

    def test_주입된_적_없는_부채는_못_갚는다(self):
        did = plant(self.m, 5, "session_start")
        self.m.apply_meta(CHAT, 6, {"used_memories": [f"debt:{did}"]})
        self.assertEqual(row(self.m, did)["status"], "open")
        rej = self.m.db.execute("SELECT reason FROM provenance WHERE kind='meta_rejected'"
                                " AND item=?", (f"used_memories.debt:{did}",)).fetchall()
        self.assertEqual([r[0] for r in rej], ["주입된 적 없는 부채"])

    def test_남의_방_부채는_못_갚는다(self):
        seed(self.m, OTHER)
        did = plant(self.m, 5, "session_start", chat_id=OTHER)
        self.m.db.execute("UPDATE debt SET attempt_count=1 WHERE debt_id=?", (did,))
        self.m.apply_meta(CHAT, 6, {"used_memories": [f"debt:{did}"]})
        self.assertEqual(row(self.m, did)["status"], "open")

    def test_두_번은_못_갚는다(self):
        did = plant(self.m, 5, "session_start")
        self._inject(did)
        self.m.apply_meta(CHAT, start_of(2) + 1, {"used_memories": [f"debt:{did}"]})
        self.m.apply_meta(CHAT, start_of(2) + 2, {"used_memories": [f"debt:{did}"]})
        rej = self.m.db.execute("SELECT reason FROM provenance WHERE kind='meta_rejected'"
                                " AND item=?", (f"used_memories.debt:{did}",)).fetchall()
        self.assertEqual([r[0] for r in rej], ["이미 paid"])

    def test_event_선언은_그대로_surfaced를_올린다(self):
        """상환 분기를 넣으면서 옆 분기를 안 건드렸는가."""
        self.m.db.execute("INSERT INTO event (chat_id, summary) VALUES (?,?)", (CHAT, "사건"))
        eid = self.m.db.execute("SELECT MAX(event_id) FROM event").fetchone()[0]
        self.m.apply_meta(CHAT, 6, {"used_memories": [f"event:{eid}"]})
        self.assertEqual(self.m.db.execute("SELECT surfaced_count FROM event WHERE"
                                           " event_id=?", (eid,)).fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
