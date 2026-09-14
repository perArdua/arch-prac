# -*- coding: utf-8 -*-
"""
test_predicate_vocab_cost.py — `predicate_vocab_cost.py`의 세 계수(ⓐⓑⓒ)가 **움직일 수 있는가**와
재바인딩이 **되돌려지는가**를 심어서 본다.

«25종으로 넓혀도 아무것도 안 움직였다»는 측정의 결론이 계수가 원래 안 움직이는 것이라면
발화할 수 없는 검사다. 그래서 대장이 실제로 쓰는 술어를 **심어** 계수가 움직이는 것을 먼저 본다.
심김 확인은 표식 계수 0 → ≥1(dict 키) · 조용한 쪽은 대장에 없는 술어를 심는 것.
"""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import predicate_vocab_cost as P  # noqa: E402
from memory import Memory  # noqa: E402

DOC = P.DOC14.read_text(encoding="utf-8")


def cur():
    return (Memory.PREDICATE_CARDINALITY, Memory.PREDICATE_MUTABILITY, Memory.PREDICATE_STANDING)


def with_key(arm, idx, key, val):
    """arm의 idx번째 어휘에 key를 심는다 — 심기 전 0, 심은 뒤 1을 확인한다."""
    parts = [dict(x) if isinstance(x, dict) else set(x) for x in arm]
    assert key not in parts[idx], f"표식이 이미 있다: {key}"
    if isinstance(parts[idx], dict):
        parts[idx][key] = val
    else:
        parts[idx].add(key)
    assert key in parts[idx]
    return tuple(parts)


def counts(r):
    return (sum(x[3] != "superseded" for x in r["a"]), sum(not x[2] for x in r["b"]),
            r["c"], tuple(r["stale"]))


class Doc14Test(unittest.TestCase):
    def test_table(self):
        t = P.doc14_table(DOC)
        self.assertEqual(len(t), 25)
        self.assertEqual(sum(r["standing"] for r in t.values()), 22)
        self.assertEqual(t["호칭"], dict(card="one", mut="mid", standing=True))

    def test_missing_table_raises(self):
        marker = "| PRED_GONE | 카디널리티"
        self.assertEqual(DOC.count(marker), 0)
        bad = DOC.replace("| 술어 | 카디널리티", marker)
        self.assertEqual(bad.count(marker), 1)
        self.assertEqual(bad.count("| 술어 | 카디널리티"), 0)
        with self.assertRaises(ValueError):
            P.doc14_table(bad)


class RestoreTest(unittest.TestCase):
    def test_restored_even_when_measure_raises(self):
        # 가변성 값이 `_MUT_TOLERANCE`에 없으면 단일값 충돌 분기에서 KeyError가 난다
        before = cur()
        arm = with_key(cur(), 0, "운영_버전", "one")
        arm = with_key(arm, 1, "운영_버전", "bogus")
        with self.assertRaises(KeyError):
            P.measure("eval2", arm)
        for a, b in zip(cur(), before):
            self.assertIs(a, b)                 # 값이 아니라 객체가 돌아왔다


class FiresTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = counts(P.measure("eval2", None))

    def test_baseline_eval2(self):
        # 다시 뽑은 값(G11) — ⓐ 병존 1 · ⓑ 안 실림 12 · ⓒ 0 · 옛 값 G002가 살아 있다
        self.assertEqual(self.base, (1, 12, 0, ("G002",)))

    def test_cardinality_moves_a_and_c(self):
        arm = with_key(cur(), 0, "운영_버전", "one")
        arm = with_key(arm, 1, "운영_버전", "high")
        self.assertEqual(counts(P.measure("eval2", arm)), (0, 12, 1, ()))

    def test_standing_moves_b(self):
        arm = with_key(cur(), 2, "소속", None)
        r = P.measure("eval2", arm)
        self.assertEqual(counts(r)[1], 11)
        self.assertIn("· 지우의 소속: 플랫폼개발팀", r["klines"])

    def test_predicate_outside_corpus_is_silent(self):
        # 조용한 쪽: 대장이 안 쓰는 술어(docs/14의 `이름`)를 심으면 아무것도 안 움직인다
        arm = with_key(cur(), 0, "이름", "one")
        arm = with_key(arm, 2, "이름", None)
        self.assertEqual(counts(P.measure("eval2", arm)), self.base)


if __name__ == "__main__":
    unittest.main()
