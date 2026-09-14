# -*- coding: utf-8 -*-
"""
test_cache_state_repro.py — F39 재현기와 전이 재판정의 **기록 모드** 검사. (wave3)

두 스크립트 다 기록이 있으면 ollama 0회로 판정을 **다시 계산한다.** 여기서 지키는 것은
그 재계산이 기록을 믿지 않는가(본문에서 sha를 다시 뽑는가)와, 규칙과 코드가 어긋날 때
우는가 둘이다. ollama를 부르지 않는다.

**심을 위반 (python -B):**
  ⓐ `verify_record`가 sha를 다시 안 뽑게 하면(`bad = []`) `test_a_tampered_body_is_caught`
  ⓑ `rejudge`의 어긋남 검사를 지우면 `test_rejudge_cries_when_the_default_disagrees`
"""
import copy
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "prototype"))

import cache_state_repro as R                                  # noqa: E402
import memory                                                  # noqa: E402
import transition_regen_probe as T                             # noqa: E402


@unittest.skipUnless(os.path.exists(R.RESULT_PATH) and os.path.exists(R.SOURCE_PATH),
                     "기록이 없다 — 🔴 SKIP은 통과가 아니다 (G1)")
class TestCacheStateRecord(unittest.TestCase):

    def setUp(self):
        with open(R.RESULT_PATH, encoding="utf-8") as f:
            self.res = json.load(f)

    def test_the_record_verifies(self):
        bad, _ = R.verify_record(self.res)
        self.assertEqual(bad, [])

    def test_a_tampered_body_is_caught(self):
        res = copy.deepcopy(self.res)
        res["calls"][0]["body"] += "."
        bad, _ = R.verify_record(res)
        self.assertEqual(bad, [res["calls"][0]["label"]])
        with redirect_stdout(io.StringIO()):
            self.assertEqual(R.report(res, "변조"), 1)

    def test_verdicts_are_recomputed_from_the_record(self):
        """기록된 호출에서 다시 센 판정. 기록 문자열이 아니라 sha 집합에서 나온다."""
        v = R.judge(self.res)
        self.assertEqual({k: v[k][0] for k in v},
                         {"P1": True, "P2": True, "P3": True, "P4": True})
        # 조용한 쪽 — 콜드 셋을 한 호출만 바꿔도 P4가 거짓이 된다.
        res = copy.deepcopy(self.res)
        next(c for c in res["calls"] if c["label"] == "B2")["body_sha"] = "0" * 64
        self.assertFalse(R.judge(res)["P4"][0])


@unittest.skipUnless(os.path.exists(T.RESULT_PATH), "기록이 없다 — 🔴 SKIP은 통과가 아니다 (G1)")
class TestTransitionRejudge(unittest.TestCase):

    def setUp(self):
        with open(T.RESULT_PATH, encoding="utf-8") as f:
            self.rows, _, _ = T.compare(json.load(f))

    def test_today_the_rule_and_the_default_agree(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(T.rejudge(self.rows), 0)

    def test_rejudge_cries_when_the_default_disagrees(self):
        saved = memory.TRANSITION_PROPAGATES_DIGEST
        memory.TRANSITION_PROPAGATES_DIGEST = True
        try:
            with redirect_stdout(io.StringIO()) as buf:
                code = T.rejudge(self.rows)
        finally:
            memory.TRANSITION_PROPAGATES_DIGEST = saved
        self.assertEqual(code, 1)
        self.assertIn("규칙과 기본값이 어긋난다", buf.getvalue())

    def test_a_prompt_that_knows_the_transition_flips_the_rule(self):
        """
        규칙이 **발화할 수 있다** — 세션 한 키의 프롬프트가 달랐다고 치면 «빼지 않는다»가
        되고, 그러면 오늘의 기본값(끔)과 어긋나 1이다.
        """
        rows = [(k, (False if i == 0 else sp), st, fd, ln)
                for i, (k, sp, st, fd, ln) in enumerate(self.rows)]
        with redirect_stdout(io.StringIO()) as buf:
            code = T.rejudge(rows)
        self.assertIn("빼지 않는다", buf.getvalue())
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
