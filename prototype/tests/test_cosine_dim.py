# -*- coding: utf-8 -*-
"""
test_cosine_dim.py — 벡터 차원 (w6code · docs/17 축-2). 끝 절 `_same_dim` · `_dims_agree`.

  V1  길이가 다른 두 벡터의 코사인은 **던진다**(`DimMismatch` ⊂ `ValueError`). 예전에는 `zip`이
      짧은 쪽에서 조용히 끊어 `[1,0,0]·[1,0]` = 1.0이었다.
  V2  같은 길이는 **예전과 같은 값**이다 — 옛 식(`zip` 그대로)과 `==`로 같다(조용한 쪽).
  V3  임베딩 모드의 검색에서 질의와 문서의 차원이 갈리면 **예외 없이 강등**한다 — 결과는 공급자가
      없을 때의 강등과 같고, provenance 노트에 `dim_mismatch` 한 줄과 `degraded` 한 줄(두 줄이
      아니다)이 남는다.
  V4  차원이 같으면 강등하지 않는다(조용한 쪽) — `dim_mismatch`·`degraded` 0줄이고 임베딩 경로가 돈다.
  V5  발화 — 옛 코사인(조용히 끊기)을 심으면 V1의 판정이 뒤집히고, 차원 대조를 끄면(`_dims_agree`
      = 항등) V3의 판정이 뒤집힌다: 강등 대신 예외가 4단계 루프 밖으로 샌다.

DB는 `:memory:`다. 벡터 공급자는 이 파일의 가짜다 — 네트워크 0.
"""
import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import memory as M                                          # noqa: E402
from memory import Memory                                   # noqa: E402

CHAT = "c-dim"
Q = "나비 사료"
DOCS = (("나비 사료를 새로 샀다", 0.8, 100), ("사료 가게에 들렀다", 0.9, 200))
KNOBS = ["RETRIEVAL_MODE", "EMBED_FN", "THETA_ON_SCORE", "W_REC"]


def old_cosine(a, b):
    """편집 전 `_cosine` 그대로 — V2의 기준이자 V5에 심는 변이."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


def supplier(q_dim, d_dim):
    """첫 텍스트(질의)는 `q_dim`, 나머지(문서)는 `d_dim` 차원. 방향은 모두 첫 축."""
    def fn(texts):
        return [[1.0] + [0.0] * ((q_dim if i == 0 else d_dim) - 1) for i, _ in enumerate(texts)]
    return fn


def cosine_refuses_mismatch():
    try:
        M._cosine([1.0, 0.0, 0.0], [1.0, 0.0])
    except M.DimMismatch:
        return True
    return False


class Base(unittest.TestCase):
    def setUp(self):
        self.saved = {k: getattr(M, k) for k in KNOBS}
        self.m = Memory()
        for s, imp, seq in DOCS:
            self.m.db.execute(
                "INSERT INTO event (chat_id, summary, occurred_at, emotional_weight,"
                " importance, source_from_seq) VALUES (?,?,?,?,?,?)",
                (CHAT, s, seq, 0.0, imp, seq))
        self.m.db.commit()

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(M, k, v)
        self.m.db.close()

    def run_embed(self, fn):
        """`(반환 또는 예외, 노트 종류 목록)`."""
        M.RETRIEVAL_MODE, M.EMBED_FN = "embed", fn
        try:
            out = self.m.retrieve(CHAT, Q, 720)
        except Exception as e:                              # noqa: BLE001
            out = e
        return out, [k for k, _, _ in self.m._retrieval_notes]

    def degrades_on_mismatch(self):
        out, kinds = self.run_embed(supplier(3, 2))
        return (not isinstance(out, Exception) and kinds.count("dim_mismatch") == 1
                and kinds.count("degraded") == 1)


class V1Refuse(Base):
    def test_mismatch_raises(self):
        self.assertTrue(cosine_refuses_mismatch())
        self.assertTrue(issubclass(M.DimMismatch, ValueError))
        with self.assertRaises(M.DimMismatch):
            M._cosine([1.0, 0.0], [1.0, 0.0, 0.0])          # 어느 쪽이 길어도


class V2SameValue(Base):
    def test_equal_length_is_bytewise_old_value(self):
        rng = random.Random(7)
        for dim in (1, 2, 3, 256, 1000):     # 1024를 쓰지 않는다 — vecdim_ppr_probe ①이 prototype/*.py의 차원 리터럴을 센다
            for _ in range(5):
                a = [rng.uniform(-1, 1) for _ in range(dim)]
                b = [rng.uniform(-1, 1) for _ in range(dim)]
                self.assertEqual(M._cosine(a, b), old_cosine(a, b))
        self.assertEqual(M._cosine([0.0, 0.0], [1.0, 0.0]), old_cosine([0.0, 0.0], [1.0, 0.0]))


class V3Degrade(Base):
    def test_mismatch_degrades_like_no_supplier(self):
        got, kinds = self.run_embed(supplier(3, 2))
        self.assertNotIsInstance(got, Exception)
        self.assertEqual(kinds.count("dim_mismatch"), 1)
        self.assertEqual(kinds.count("degraded"), 1)        # 한 번의 강등은 한 줄
        self.assertLess(kinds.index("dim_mismatch"), kinds.index("degraded"))
        ref, ref_kinds = self.run_embed(None)                # 공급자 없음 → 같은 강등
        self.assertEqual(ref_kinds.count("degraded"), 1)
        self.assertEqual([(repr(s), r["summary"]) for s, r in got[0]],
                         [(repr(s), r["summary"]) for s, r in ref[0]])
        self.assertEqual(got[1], ref[1])

    def test_shorter_query_also_degrades(self):
        # 새 DB에서 반대 방향만 본다 — 앞 실행이 문서 벡터를 저장하면 그다음 실행은 저장된 차원을 읽는다.
        out, kinds = self.run_embed(supplier(2, 3))
        self.assertNotIsInstance(out, Exception)
        self.assertEqual(kinds.count("dim_mismatch"), 1)


class V4Quiet(Base):
    def test_same_dim_stays_embed(self):
        out, kinds = self.run_embed(supplier(3, 3))
        self.assertNotIsInstance(out, Exception)
        self.assertEqual(kinds.count("dim_mismatch"), 0)
        self.assertEqual(kinds.count("degraded"), 0)
        self.assertEqual(len(out[0]), len(DOCS))            # 코사인 1.0 ≥ θ — 임베딩 경로가 돌았다


class V5Fire(Base):
    def test_planted_lenient_cosine_flips_v1(self):
        orig = M._cosine
        try:
            M._cosine = old_cosine
            self.assertFalse(cosine_refuses_mismatch())
        finally:
            M._cosine = orig
        self.assertIs(M._cosine, orig)
        self.assertTrue(cosine_refuses_mismatch())

    def test_planted_no_dim_check_flips_v3(self):
        orig = M._dims_agree
        try:
            M._dims_agree = lambda notes, qv, dvecs: (qv, dvecs)
            self.assertFalse(self.degrades_on_mismatch())
            out, _ = self.run_embed(supplier(3, 2))
            self.assertIsInstance(out, M.DimMismatch)       # 강등 대신 예외가 샌다
        finally:
            M._dims_agree = orig
        self.assertIs(M._dims_agree, orig)


if __name__ == "__main__":
    unittest.main()
