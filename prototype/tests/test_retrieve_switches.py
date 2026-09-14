# -*- coding: utf-8 -*-
"""
test_retrieve_switches.py — `retrieve`의 두 스위치(끝 절 `THETA_ON_SCORE` · `W_REC`). (레인 A)

  S0  기본값이 오늘이다 — 둘 다 꺼져 있다 (G16)
  S1  기본값에서 점수는 3항 식 그대로이고, 컷 사유도 `relevance … < θ` 그대로다
  S2  기본값에서 `W_REC`는 SQL을 하나도 늘리지 않는다 («0.0이면 글자 그대로»의 관측)
  S3  θ가 `rel`에 걸리면 가중치는 **순서만** 바꾼다 (ADR-015 핵심 7의 기제)
  S4  θ가 최종 점수에 걸리면 가중치가 **집합**을 바꾼다
  S5  페널티 축은 `surfaced_count` > 0일 때만 산다 — 점수 θ에서 집합을 바꾸고 rel θ에서는 못 바꾼다
  S6  recency 페널티의 모양 (나이 0 → 0 · 반감기 → 0.5 · 미래 → 0 · 모름 → None)
  S7  `W_REC`는 정확히 `W_REC · recency_penalty`만큼 뺀다 · 나이를 모르면 provenance에 남긴다

점수와 θ는 **이 파일이 고른 수가 아니라** `coverage`로 잰 `rel`에서 계산한다 — 토크나이저가
바뀌어도 시험의 전제(교차가 존재한다)를 먼저 단언하고, 전제가 깨지면 그 자리에서 실패한다.
DB는 `:memory:`다.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import memory as M                                          # noqa: E402
from memory import Memory                                   # noqa: E402

CHAT = "c-switch"
Q = "나비 사료"
A = "나비 사료를 새로 샀다"          # rel 높음 · imp 낮음
B = "사료 가게"                     # rel 낮음 · imp 높음
IMP_A, IMP_B = 0.3, 0.9
W1, W2 = (0.6, 0.4), (0.1, 0.9)
KNOBS = ["THETA_ON_SCORE", "W_REC", "RECENCY_HALF_LIFE", "THETA_RELEVANCE",
         "W_REL", "W_IMP", "SURFACED_PENALTY", "RETRIEVAL_MODE"]


def rel(s):
    return M.coverage(M.bigrams(Q), M.bigrams(s))


class Base(unittest.TestCase):
    def setUp(self):
        self.saved = {k: getattr(M, k) for k in KNOBS}
        M.RETRIEVAL_MODE = "lexical"
        self.m = Memory()
        self.ids = {}
        for s, imp, seq in ((A, IMP_A, 100), (B, IMP_B, 600)):
            cur = self.m.db.execute(
                "INSERT INTO event (chat_id, summary, occurred_at, emotional_weight,"
                " importance, source_from_seq) VALUES (?,?,?,?,?,?)",
                (CHAT, s, seq, 0.0, imp, seq))
            self.ids[s] = cur.lastrowid
        self.m.db.commit()
        # 전제 — A는 질의를 다 덮고 B는 일부만 덮는다
        self.assertEqual(rel(A), 1.0)
        self.assertTrue(0 < rel(B) < 1)

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(M, k, v)
        self.m.db.close()

    def run_with(self, w, theta, on=False, pen=0.1, w_rec=0.0, now=720):
        M.W_REL, M.W_IMP = w
        M.THETA_RELEVANCE, M.THETA_ON_SCORE = theta, on
        M.SURFACED_PENALTY, M.W_REC = pen, w_rec
        hits, rejected = self.m.retrieve(CHAT, Q, now)
        return [r["summary"] for _, r in hits], hits, rejected

    def crossing_theta(self):
        """W1에서는 A만, W2에서는 B만 최종 점수 θ를 넘게 하는 θ. 없으면 시험 전제가 깨진 것."""
        s = {(w, x): w[0] * rel(x) + w[1] * imp for w in (W1, W2) for x, imp in
             ((A, IMP_A), (B, IMP_B))}
        lo = max(s[(W1, B)], s[(W2, A)])
        hi = min(s[(W1, A)], s[(W2, B)])
        self.assertLess(lo, hi, "교차 구간이 비었다 — 고정물을 다시 골라야 한다")
        theta = (lo + hi) / 2
        self.assertGreater(theta, rel(B))        # rel θ로 쓰면 B를 자르고 A를 남긴다
        return theta


class TestDefaults(Base):
    def test_s0_defaults_are_today(self):
        self.assertIs(self.saved["THETA_ON_SCORE"], False)
        self.assertEqual(self.saved["W_REC"], 0.0)

    def test_s1_three_term_score_and_reason(self):
        M.W_REL, M.W_IMP = self.saved["W_REL"], self.saved["W_IMP"]
        theta = (rel(B) + 1.0) / 2                  # A만 rel θ를 넘는다
        M.THETA_RELEVANCE = theta
        hits, rejected = self.m.retrieve(CHAT, Q, 720)
        self.assertEqual([r["summary"] for _, r in hits], [A])
        want = (M.W_REL * rel(A) + M.W_IMP * IMP_A - M.SURFACED_PENALTY * 0)
        self.assertEqual(hits[0][0], want)          # 부동소수까지 같은 식
        self.assertEqual(rejected, [(B, f"relevance {rel(B):.2f} < θ")])

    def test_s2_default_reads_no_seq(self):
        seen = []
        self.m.db.set_trace_callback(seen.append)
        self.m.retrieve(CHAT, Q, 720)
        self.m.db.set_trace_callback(None)
        self.assertTrue(seen, "추적이 아무것도 못 봤다 — 관측이 성립하지 않는다")
        self.assertEqual([s for s in seen if "source_from_seq" in s], [])


class TestThetaPosition(Base):
    def test_s3_rel_theta_weights_move_order_only(self):
        order1, _, _ = self.run_with(W1, 0.05)
        order2, _, _ = self.run_with(W2, 0.05)
        self.assertEqual(order1, [A, B])
        self.assertEqual(order2, [B, A])
        self.assertEqual(set(order1), set(order2))
        # θ가 A와 B 사이에 있어도 rel 컷이면 가중치와 무관하게 {A}
        th = self.crossing_theta()
        self.assertEqual(self.run_with(W1, th)[0], [A])
        self.assertEqual(self.run_with(W2, th)[0], [A])

    def test_s4_score_theta_weights_move_set(self):
        th = self.crossing_theta()
        got1, _, rej1 = self.run_with(W1, th, on=True)
        got2, _, rej2 = self.run_with(W2, th, on=True)
        self.assertEqual(got1, [A])
        self.assertEqual(got2, [B])
        self.assertTrue(rej1[0][1].startswith("최종 점수 "))
        self.assertTrue(rej2[0][1].startswith("최종 점수 "))

    def test_s5_penalty_lives_only_with_surfaced(self):
        th = self.crossing_theta()
        # 채널이 비어 있으면 (`surfaced_count` = 0) 페널티는 점수 θ에서도 아무것도 못 바꾼다
        self.assertEqual(self.run_with(W1, th, on=True, pen=0.0)[0],
                         self.run_with(W1, th, on=True, pen=0.9)[0])
        self.m.db.execute("UPDATE event SET surfaced_count=2 WHERE event_id=?", (self.ids[A],))
        self.assertEqual(self.run_with(W1, th, on=True, pen=0.0)[0], [A])
        self.assertEqual(self.run_with(W1, th, on=True, pen=0.3)[0], [])
        # rel θ에서는 페널티가 집합에 못 닿는다
        self.assertEqual(self.run_with(W1, th, on=False, pen=0.3)[0], [A])


class TestRecency(Base):
    def test_s6_penalty_shape(self):
        M.RECENCY_HALF_LIFE = 240
        self.assertEqual(M.recency_penalty(720, 720), 0.0)
        self.assertAlmostEqual(M.recency_penalty(720, 480), 0.5)
        self.assertEqual(M.recency_penalty(100, 300), 0.0)      # 미래 행
        self.assertIsNone(M.recency_penalty(720, None))
        self.assertLess(M.recency_penalty(720, 700), M.recency_penalty(720, 100))

    def test_s7_w_rec_subtracts_exact_penalty(self):
        _, base, _ = self.run_with(W1, 0.05)
        _, rec, _ = self.run_with(W1, 0.05, w_rec=0.2)
        b = {r["summary"]: s for s, r in base}
        for s, r in rec:
            seq = 100 if r["summary"] == A else 600
            self.assertAlmostEqual(s, b[r["summary"]] - 0.2 * M.recency_penalty(720, seq))
        self.assertEqual(self.m._retrieval_notes, [])

    def test_s7b_unknown_age_is_noted(self):
        self.m.db.execute("UPDATE event SET source_from_seq=NULL WHERE event_id=?",
                          (self.ids[B],))
        self.run_with(W1, 0.05, w_rec=0.2)
        notes = [n for n in self.m._retrieval_notes if n[:2] == ("degraded", "recency")]
        self.assertEqual(len(notes), 1)


if __name__ == "__main__":
    unittest.main()
