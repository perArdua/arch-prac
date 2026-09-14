# -*- coding: utf-8 -*-
"""
test_predicate_policy.py — 표 밖 술어의 기본값 스위치(`memory.py` 끝 절 `UNKNOWN_PREDICATE_POLICY` · w8code · docs/17 밖E10).

  P1  기본값은 `"legacy"`이고 그 값은 스위치 이전의 글자 그대로다 — `("many", "mid", False)` (G16)
  P2  legacy에서 표 밖 술어의 두 값은 **병존**하고 상시 블록에 **안 실린다** (오늘의 동작)
  P3  `"one"`에서 표 밖 술어의 새 값은 옛 값을 **무효화**한다 — `valid_until` · `superseded_by` · 색인 복사본 제외
  P4  `"standing"`에서 표 밖 술어는 상시 블록에 실린다 · 조용한 쪽: 표 안의 비상시 술어(`일상_사소`)는 여전히 안 실린다
  P5  «표 밖»은 **세 표 모두의 밖**이다 — 상시 표에만 있는 `지인_직업`은 `"one"`에서도 병존한다
  P6  모르는 정책 키는 `KeyError` — 조용히 오늘 값으로 떨어지지 않는다
  P7  호출 가능 정책은 술어 이름으로 불린다 (계측 전용 자리)

정책은 매 시험 뒤 `addCleanup`으로 되돌리고 객체 동일성으로 확인한다(G13). DB는 `:memory:`.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import memory as M                                          # noqa: E402
from memory import Memory                                   # noqa: E402
import soak                                                 # noqa: E402

UNK = "쓰는_노트북"          # 세 표 어디에도 없다 (전제로 단언한다)


class Base(unittest.TestCase):
    def setUp(self):
        saved = M.UNKNOWN_PREDICATE_POLICY

        def back():
            M.UNKNOWN_PREDICATE_POLICY = saved
            assert M.UNKNOWN_PREDICATE_POLICY is saved
        self.addCleanup(back)
        self.m = Memory(":memory:")
        self.addCleanup(self.m.db.close)
        soak.seed(self.m)

    def put(self, pred, obj, seq):
        act, _ = self.m.upsert_fact(soak.CHAT, "지우", pred, obj, seq=seq)
        cur = self.m.db.execute(
            "INSERT INTO event (chat_id, summary, occurred_at, emotional_weight, importance, narrative_role,"
            " source_from_seq) VALUES (?,?,?,?,?,?,?)", (soak.CHAT, f"지우 {pred} {obj}", seq, 0.0, 0.5, "사실", seq))
        fid = self.m.db.execute("SELECT fact_id FROM fact WHERE predicate=? AND object=?", (pred, obj)).fetchone()
        self.m.record_derivation(soak.CHAT, "event", str(cur.lastrowid), [("fact", fid["fact_id"])])
        return act

    def valid(self, pred):
        return [r["object"] for r in self.m.facts_at(soak.CHAT) if r["predicate"] == pred]

    def known_lines(self):
        ctx = self.m.build_context(soak.CHAT, "오늘 좀 피곤하네", 10)
        return [b.text for b in ctx.blocks if b.name == "알고 있는 것"][0].splitlines()


class Premise(unittest.TestCase):
    def test_premise(self):
        for t in (Memory.PREDICATE_CARDINALITY, Memory.PREDICATE_MUTABILITY, Memory.PREDICATE_STANDING):
            self.assertNotIn(UNK, t)
        self.assertIn("지인_직업", Memory.PREDICATE_STANDING)
        self.assertNotIn("지인_직업", Memory.PREDICATE_CARDINALITY)
        self.assertIn("일상_사소", Memory.PREDICATE_CARDINALITY)
        self.assertNotIn("일상_사소", Memory.PREDICATE_STANDING)


class Legacy(Base):
    def test_p1_default_is_today(self):
        self.assertEqual(M.UNKNOWN_PREDICATE_POLICY, "legacy")
        self.assertEqual(M.UNKNOWN_PREDICATE_DEFAULTS["legacy"], ("many", "mid", False))

    def test_p2_coexist_and_not_standing(self):
        self.assertEqual(self.put(UNK, "맥북", 1), "created")
        self.assertEqual(self.put(UNK, "그램", 2), "coexist")
        self.assertEqual(sorted(self.valid(UNK)), ["그램", "맥북"])
        self.assertFalse(any(UNK in ln for ln in self.known_lines()))


class Policies(Base):
    def test_p3_one_supersedes(self):
        M.UNKNOWN_PREDICATE_POLICY = "one"
        self.put(UNK, "맥북", 1)
        self.assertEqual(self.put(UNK, "그램", 2), "superseded")
        self.assertEqual(self.valid(UNK), ["그램"])
        old = self.m.db.execute("SELECT valid_until, superseded_by FROM fact WHERE object='맥북'").fetchone()
        self.assertIsNotNone(old["valid_until"])
        self.assertIsNotNone(old["superseded_by"])
        live = [r[0] for r in self.m.db.execute("SELECT summary FROM event WHERE user_deleted=0")]
        self.assertNotIn(f"지우 {UNK} 맥북", live)
        self.assertIn(f"지우 {UNK} 그램", live)                         # 조용한 쪽 — 새 값의 색인은 산다

    def test_p4_standing_injects_but_not_known_trivia(self):
        M.UNKNOWN_PREDICATE_POLICY = "standing"
        self.put(UNK, "맥북", 1)
        self.put("일상_사소", "크로와상", 2)
        lines = self.known_lines()
        self.assertIn(f"· 지우의 {UNK}: 맥북", lines)
        self.assertFalse(any("일상_사소" in ln for ln in lines))       # 조용한 쪽

    def test_p5_boundary_is_all_three_tables(self):
        M.UNKNOWN_PREDICATE_POLICY = "one"
        self.put("지인_직업", "디자이너", 1)
        self.assertEqual(self.put("지인_직업", "개발자", 2), "coexist")
        self.assertEqual(sorted(self.valid("지인_직업")), ["개발자", "디자이너"])

    def test_p6_unknown_key_raises(self):
        M.UNKNOWN_PREDICATE_POLICY = "모르는_정책"
        with self.assertRaises(KeyError):
            self.m.upsert_fact(soak.CHAT, "지우", UNK, "맥북")

    def test_p7_callable_policy(self):
        seen = []

        def pol(p):
            seen.append(p)
            return ("one", "mid", False)
        M.UNKNOWN_PREDICATE_POLICY = pol
        self.put(UNK, "맥북", 1)
        self.assertEqual(self.put(UNK, "그램", 2), "superseded")
        self.assertIn(UNK, seen)
        self.assertNotIn("직업", seen)                                   # 표 안 술어로는 부르지 않는다
        self.put("직업", "PM", 3)
        self.assertNotIn("직업", seen)


if __name__ == "__main__":
    unittest.main()
