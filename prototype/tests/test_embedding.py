# -*- coding: utf-8 -*-
"""
test_embedding.py — `embed()`의 **강등 계약**을 고정한다. (단계 1 작업 2)

두 가지만 본다. 둘 다 ollama가 **없어도** 성립해야 한다 — 이 테스트가 CI든 남의
노트북이든 돌아야 하기 때문이다.

  1. ollama가 없으면 `None`을 돌려준다. **예외를 내지 않는다.**
     호출부는 `None`을 받아 어휘 검색으로 강등한다. 여기서 예외가 새면 검색 경로
     전체가 죽는다 — ollama 부재 환경에서 가장 나쁜 결과다.
  2. 캐시에 있으면 **네트워크를 아예 타지 않는다.**
     죽은 포트를 가리켜 놓고도 값이 나오는 것으로 증명한다. 단계 4 격자 ~98셀이
     이 성질 위에 서 있다 (458회 vs 44,900회).
"""
import hashlib
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import embedding as E                                      # noqa: E402

DEAD = "http://127.0.0.1:1"     # 아무도 듣지 않는 포트


def _seed(path, mapping):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(mapping, f)


class TestEmbedDegrade(unittest.TestCase):
    """실패는 예외가 아니라 `None`이다."""

    def setUp(self):
        self._save = (E.OLLAMA_HOST, E.CACHE_PATH, E.LEGACY_CACHE_PATH,
                      E._cache, E._legacy, E.PROBE_TIMEOUT, E.EMBED_TIMEOUT)
        self.tmp = tempfile.mkdtemp()
        # 상수 재바인딩 — `gate_sweep.py` 스타일 몽키패치 (G8).
        E.CACHE_PATH = os.path.join(self.tmp, "SWEEP.json")
        E.LEGACY_CACHE_PATH = os.path.join(self.tmp, "LEGACY.json")
        E._cache = E._legacy = None
        E.PROBE_TIMEOUT = E.EMBED_TIMEOUT = 2   # 죽은 포트는 즉시 거부된다

    def tearDown(self):
        (E.OLLAMA_HOST, E.CACHE_PATH, E.LEGACY_CACHE_PATH,
         E._cache, E._legacy, E.PROBE_TIMEOUT, E.EMBED_TIMEOUT) = self._save

    def test_wrong_port_returns_none(self):
        E.OLLAMA_HOST = DEAD
        self.assertIsNone(E.embed(["없는 서버로 보내는 텍스트"]))

    def test_wrong_port_does_not_raise(self):
        """`assertIsNone`만으로는 부족하다 — 예외가 안 난다는 것 자체가 계약이다."""
        E.OLLAMA_HOST = DEAD
        try:
            E.embed(["가", "나", "다"])
        except Exception as e:                              # noqa: BLE001
            self.fail(f"embed()가 예외를 냈다 — 강등 계약 위반: {e!r}")

    def test_partial_failure_returns_none_not_short_list(self):
        """캐시 1건 + 미스 1건. 일부만 채운 리스트를 주면 호출부가 성공으로 착각한다."""
        E.OLLAMA_HOST = DEAD
        _seed(E.CACHE_PATH, {"있는 것": [0.1, 0.2]})
        self.assertIsNone(E.embed(["있는 것", "없는 것"]))

    def test_no_cache_write_on_failure(self):
        E.OLLAMA_HOST = DEAD
        E.embed(["실패할 텍스트"])
        self.assertFalse(os.path.exists(E.CACHE_PATH))


class TestCacheHitOffline(unittest.TestCase):
    """미리 채운 캐시 파일만으로 네트워크 없이 동작한다."""

    def setUp(self):
        self._save = (E.OLLAMA_HOST, E.CACHE_PATH, E.LEGACY_CACHE_PATH,
                      E._cache, E._legacy)
        self.tmp = tempfile.mkdtemp()
        E.OLLAMA_HOST = DEAD
        E.CACHE_PATH = os.path.join(self.tmp, "SWEEP.json")
        E.LEGACY_CACHE_PATH = os.path.join(self.tmp, "LEGACY.json")
        E._cache = E._legacy = None
        self.vec = [0.5] * 8
        _seed(E.CACHE_PATH, {"미리 넣어둔 텍스트": self.vec})

    def tearDown(self):
        (E.OLLAMA_HOST, E.CACHE_PATH, E.LEGACY_CACHE_PATH,
         E._cache, E._legacy) = self._save

    def test_cache_hit_without_network(self):
        self.assertEqual(E.embed(["미리 넣어둔 텍스트"]), [self.vec])

    def test_legacy_cache_shares_the_same_key(self):
        """`EMBED_CACHE.json`의 항목이 그대로 통한다 — `cache_key()`가 하나이므로."""
        E._cache = E._legacy = None
        _seed(E.LEGACY_CACHE_PATH, {"기존 캐시의 텍스트": self.vec})
        self.assertEqual(E.embed(["기존 캐시의 텍스트"]), [self.vec])

    def test_missing_keys_lists_only_the_misses(self):
        self.assertEqual(E.missing_keys(["미리 넣어둔 텍스트", "없는 텍스트"]),
                         ["없는 텍스트"])

    def test_ensure_cached_hit_is_zero(self):
        self.assertEqual(E.ensure_cached(["미리 넣어둔 텍스트"]), 0)

    def test_ensure_cached_miss_without_ollama_is_77(self):
        """3분기의 세 번째 — 재현 불가를 정직하게 신고하는 경로."""
        self.assertEqual(E.ensure_cached(["없는 텍스트"]), 77)

    def test_cache_key_is_identity(self):
        """해시로 바꾸면 기존 37개가 고아가 된다 — 그 결정을 테스트로 못박는다."""
        self.assertEqual(E.cache_key("아무 텍스트"), "아무 텍스트")


class TestLegacyCacheIsReadOnly(unittest.TestCase):
    """
    🆕 단계 2 이월 (단계 1 검증자 지적) — **`EMBED_CACHE.json`에는 쓰지 않는다.**

    지금까지 이 계약은 `embedding.py:37`·`:86`의 **주석**과 외부에서 손으로 잰
    md5로만 지켜지고 있었다. `_cache_save()`를 한 번 잘못 고치면 조용히 깨지고,
    그러면 0-f가 만든 37개(미추적·재계산 불가)가 오염된다.

    성공 경로에서만 의미가 있다 — 실패하면 애초에 아무것도 안 쓴다
    (`test_no_cache_write_on_failure`). 그래서 `_post`를 가짜 성공으로 갈아끼운다.
    """

    def setUp(self):
        self._save = (E.CACHE_PATH, E.LEGACY_CACHE_PATH, E._cache, E._legacy,
                      E._post)
        self.tmp = tempfile.mkdtemp()
        E.CACHE_PATH = os.path.join(self.tmp, "SWEEP.json")
        E.LEGACY_CACHE_PATH = os.path.join(self.tmp, "LEGACY.json")
        E._cache = E._legacy = None
        _seed(E.LEGACY_CACHE_PATH, {"기존 캐시의 텍스트": [0.5] * 8})
        self.before = self._md5(E.LEGACY_CACHE_PATH)
        E._post = lambda path, payload, timeout: {"embeddings": [[0.25] * 8]}

    def tearDown(self):
        (E.CACHE_PATH, E.LEGACY_CACHE_PATH, E._cache, E._legacy,
         E._post) = self._save

    @staticmethod
    def _md5(path):
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()

    def test_uncached_embed_writes_sweep_not_legacy(self):
        v = E.embed(["캐시에 없는 새 텍스트"])
        self.assertEqual(v, [[0.25] * 8])                  # 계산은 실제로 됐다
        self.assertEqual(self._md5(E.LEGACY_CACHE_PATH), self.before)
        # 쓰기는 스윕 경로로 갔다
        with open(E.CACHE_PATH, encoding="utf-8") as f:
            self.assertIn("캐시에 없는 새 텍스트", json.load(f))

    def test_cache_save_alone_never_touches_legacy(self):
        """`_cache_save()`를 직접 불러도 마찬가지 — 계약은 함수에 있다."""
        E._cache_load()[0]["직접 넣은 키"] = [0.1] * 8
        E._cache_save()
        self.assertEqual(self._md5(E.LEGACY_CACHE_PATH), self.before)


if __name__ == "__main__":
    unittest.main()
