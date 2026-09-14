# -*- coding: utf-8 -*-
"""
test_cos_copies.py — 남은 `cos` 사본 둘의 **차원 규약**을 고정한다 (w12close · docs/17 축-2의 딸린 🔓 뒤끝).

`experiments/embed_vs_bigram.py`의 `cos`(→ `probe_types.py`가 import · 실험 22)와
`experiments/embed_model_sweep.py`의 `quality()` 안 지역 `cos`(후속 9)는 `memory._cosine`의 옛 식과 같은
`zip(a, b)`였다 — 길이가 다르면 짧은 쪽에서 **조용히** 끊는다. `rel_dist.cos`(w11b)와 같은 방식으로 고쳤다:
검사는 사본이 아니라 `memory._same_dim`을 **부른다**(F12). 규약이 두 벌이면 한쪽만 고쳐지는 날이 온다.

⚠️ ollama도 DB도 쓰지 않는다. `quality()`의 임베딩 호출은 결정적인 가짜 벡터로 갈아 끼운다.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "prototype"))
import embed_vs_bigram as EV                                # noqa: E402
import embed_model_sweep as EMS                             # noqa: E402

M = EV.M


class Called(Exception):
    pass


def _raise_called(a, b):
    raise Called


def _fake_vec(text, dim=4):
    """텍스트마다 결정적인 작은 벡터 — 값은 무엇이든 좋고 길이만 뜻이 있다."""
    s = sum(map(ord, text))
    return [float((s * (i + 3)) % 17 - 8) for i in range(dim)]


class TestEmbedVsBigramCos(unittest.TestCase):

    def test_length_mismatch_raises(self):
        for a, b in (([1.0, 0.0, 0.0], [1.0, 0.0]), ([1.0, 0.0], [1.0, 0.0, 0.0])):
            with self.assertRaises(M.DimMismatch, msg=f"{len(a)} vs {len(b)}"):
                EV.cos(a, b)

    def test_check_is_memorys_not_a_copy(self):
        """`memory._same_dim`을 잠시 바꾸면 `cos`가 **그것을** 부른다 — 지역 사본이면 여기가 운다."""
        saved = M._same_dim
        M._same_dim = _raise_called
        try:
            with self.assertRaises(Called):
                EV.cos([1.0, 2.0], [3.0, 4.0])
        finally:
            M._same_dim = saved
        self.assertIs(M._same_dim, saved)

    def test_same_length_is_bitwise_memory_cosine(self):
        """조용한 쪽 — 같은 길이면 `memory._cosine`과 **비트까지** 같다(기록값이 안 움직인다는 주장의 단위판)."""
        for a, b in (([0.3, -1.2, 2.5, 0.0], [1.1, 0.4, -0.7, 3.3]),
                     ([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]),
                     ([0.0, 0.0], [0.0, 0.0])):
            self.assertEqual(repr(EV.cos(a, b)), repr(M._cosine(a, b)))


class TestSweepQualityCos(unittest.TestCase):
    """`embed_model_sweep.quality`의 지역 `cos` — 모델 하나의 벡터만 받는 경로지만 규약은 같다."""

    def _run(self, short=None):
        saved = EMS.embed_one

        def fake(model, text, timeout=180):
            return _fake_vec(text, 3 if text == short else 4)

        EMS.embed_one = fake
        try:
            return EMS.quality("가짜-모델")
        finally:
            EMS.embed_one = saved

    def test_length_mismatch_raises(self):
        """질의 하나의 벡터만 짧으면 — 옛 식은 앞 3차원으로 그럴듯한 순위를 냈다."""
        with self.assertRaises(M.DimMismatch):
            self._run(short=EV.PROBES[0][0])

    def test_check_is_memorys_not_a_copy(self):
        saved = M._same_dim
        M._same_dim = _raise_called
        try:
            with self.assertRaises(Called):
                self._run()
        finally:
            M._same_dim = saved
        self.assertIs(M._same_dim, saved)

    def test_same_length_runs_every_pair_through_the_check(self):
        """조용한 쪽 — 같은 길이면 던지지 않고, 코사인 한 번마다 검사를 한 번 지난다(프로브 × 후보)."""
        saved = M._same_dim
        seen = []

        def count(a, b):
            seen.append((len(a), len(b)))
            return saved(a, b)

        M._same_dim = count
        try:
            q = self._run()
        finally:
            M._same_dim = saved
        self.assertIsNotNone(q)
        self.assertEqual(q["n"], len(EV.PROBES))
        self.assertEqual(set(seen), {(4, 4)})
        self.assertEqual(len(seen) % len(EV.PROBES), 0)
        self.assertGreater(len(seen), 0)


if __name__ == "__main__":
    unittest.main()
