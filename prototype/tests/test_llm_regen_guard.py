"""
`llm._guard_regen` — 기록과 런타임이 다르면 `run_all` 아래에서 **라이브 생성 전에** 77.

2026-09-11: ollama 자동 업데이트(0.33.3 → 0.34.0) 뒤 `run_all`이 `response_quality.py`를 통해
`RESPONSE_CACHE.json`에 153건을 덧썼다(되돌렸다). 이 시험은 그 경로가 다시 열리면 운다.

세 칸을 본다 — 소리 나는 쪽 하나와 조용한 쪽 둘:
  ① 변수 있음 + 불일치 → SystemExit(77), 그리고 `/api/generate`는 **한 번도 안 불린다**
  ② 변수 있음 + 일치   → 생성한다 (막으면 안 되는 것까지 막는 과잉 차단을 잡는다)
  ③ 변수 없음 + 불일치 → 생성한다 (손으로 돌릴 때는 경고만 — 재측정은 사람이 고른다)
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import llm  # noqa: E402

RECORD = {"ollama": "0.33.3", "model": "qwen3:8b", "digest": "d" * 64}


class _FakeResp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._b


class RegenGuard(unittest.TestCase):
    def setUp(self):
        # G13 — 모듈 전역을 바꾸면 tearDown에서 **반드시** 되돌린다.
        self._saved = (llm.CHECKPOINT_PATH, llm.runtime_info,
                       llm.urllib.request.urlopen, llm._checked,
                       os.environ.get(llm.FORBID_REGEN_ENV))
        fd, self.path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(RECORD, f)
        llm.CHECKPOINT_PATH = self.path
        llm._checked = False
        self.generate_calls = 0

        def fake_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if url.endswith("/api/generate"):
                self.generate_calls += 1
                return _FakeResp({"response": "ok", "prompt_eval_count": 1})
            raise AssertionError(f"예상 밖 요청: {url}")
        llm.urllib.request.urlopen = fake_urlopen

    def tearDown(self):
        (llm.CHECKPOINT_PATH, llm.runtime_info, llm.urllib.request.urlopen,
         llm._checked, env) = self._saved
        if env is None:
            os.environ.pop(llm.FORBID_REGEN_ENV, None)
        else:
            os.environ[llm.FORBID_REGEN_ENV] = env
        os.remove(self.path)

    def _runtime(self, ollama):
        llm.runtime_info = lambda: {"ollama": ollama, "model": "qwen3:8b",
                                    "digest": RECORD["digest"]}

    def test_mismatch_under_run_all_stops_before_generating(self):
        os.environ[llm.FORBID_REGEN_ENV] = "1"
        self._runtime("0.34.0")
        with self.assertRaises(SystemExit) as cm:
            llm.raw_generate("안녕")
        self.assertEqual(cm.exception.code, 77)
        self.assertEqual(self.generate_calls, 0,
                         "불일치인데 `/api/generate`가 불렸다 — 체크포인트가 덧쓰인다")

    def test_match_under_run_all_still_generates(self):
        os.environ[llm.FORBID_REGEN_ENV] = "1"
        self._runtime("0.33.3")
        self.assertEqual(llm.raw_generate("안녕")["response"], "ok")
        self.assertEqual(self.generate_calls, 1)

    def test_mismatch_by_hand_only_warns(self):
        os.environ.pop(llm.FORBID_REGEN_ENV, None)
        self._runtime("0.34.0")
        self.assertEqual(llm.raw_generate("안녕")["response"], "ok")
        self.assertEqual(self.generate_calls, 1)


    # ── 2026-09-11 사용자 결정: 다운그레이드 대신 «기록 판 키로 재채점 · 측정은 막지 않는다» ──
    def test_measure_is_not_blocked_and_does_not_consume_the_check(self):
        os.environ[llm.FORBID_REGEN_ENV] = "1"
        self._runtime("0.34.0")
        self.assertEqual(llm.measure_prompt("안녕", num_predict=1)["response"], "ok")
        self.assertEqual(self.generate_calls, 1)
        # 측정이 검사를 «소비»했다면 아래 진짜 생성이 검사 없이 통과한다 — 그것이 구멍이다
        with self.assertRaises(SystemExit) as cm:
            llm.raw_generate("안녕")
        self.assertEqual(cm.exception.code, 77)
        self.assertEqual(self.generate_calls, 1, "측정 뒤 진짜 생성이 불렸다 — 가드가 소비됐다")
        self.assertFalse(llm._MEASURING)

    def test_key_runtime_uses_record_under_run_all(self):
        os.environ[llm.FORBID_REGEN_ENV] = "1"
        now = {"ollama": "0.34.0", "model": "qwen3:8b", "digest": "e" * 64}
        k = llm.key_runtime(now)
        self.assertEqual((k["ollama"], k["digest"]), (RECORD["ollama"], RECORD["digest"]))
        self.assertEqual(now["ollama"], "0.34.0", "원본 런타임 사전을 바꾸면 안 된다")

    def test_key_runtime_by_hand_is_current(self):
        os.environ.pop(llm.FORBID_REGEN_ENV, None)
        now = {"ollama": "0.34.0", "model": "qwen3:8b", "digest": "e" * 64}
        self.assertIs(llm.key_runtime(now), now)


class RunAllPassesTheFlag(unittest.TestCase):
    def test_child_env_carries_the_flag(self):
        # 러너가 변수를 안 넘기면 위 ①은 어디서도 발화하지 않는다 — 배선을 따로 본다.
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "..", "..", "experiments", "run_all.py"),
                  encoding="utf-8") as f:
            src = f.read()
        self.assertIn('MEMARCH_FORBID_REGEN="1"', src)
        self.assertIn("env=CHILD_ENV", src)
        self.assertEqual(llm.FORBID_REGEN_ENV, "MEMARCH_FORBID_REGEN")


if __name__ == "__main__":
    unittest.main()
