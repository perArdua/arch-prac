# -*- coding: utf-8 -*-
"""
`run_all`의 SKIP 요약 — 이유는 **자식이 찍은 줄**이어야 한다 (2026-09-11 · w10record).

요약의 설명이 «임베딩 캐시 미스 + ollama 부재» 한 줄로 고정돼 있어서 F40 가드의 77
(`llm._guard_regen`)과 컨테이너가 없는 실험 32의 77에 틀린 이유를 붙였다.
여기서는 가짜 자식(종료 0 · 77)을 러너 `main`에 물려 요약에 그 줄이 실리는지 본다.
LLM · ollama · 컨테이너 0회 — `subprocess.run`을 바꿔 끼우고 `OUT`을 임시 파일로 돌린다.

    PYTHONIOENCODING=utf-8 python -B -m unittest experiments/tests/test_run_all_skip_reason.py
"""
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import run_all  # noqa: E402

GUARD = ("⏭️ MEMARCH_FORBID_REGEN — ollama 기록 0.33.3 vs 현재 0.34.0. "
         "라이브 생성을 하지 않는다(77): 체크포인트를 덧쓰면 기록값이 조용히 바뀐다(F39).")
ENGINE = "  ⏭️ 종료 77 — 팔 ['B3', 'C1', 'C2']이 돌지 않았다. **통과가 아니다**(G1)"
OLD_FIXED = "임베딩 캐시 미스 + ollama 부재"


def _done(code, out="", err=""):
    return subprocess.CompletedProcess(args=[], returncode=code, stdout=out, stderr=err)


class SkipReason(unittest.TestCase):
    def test_marked_line_wins_over_later_noise(self):
        # 표식 줄 뒤에 stderr 경고가 와도 이유는 표식 줄이다.
        r = _done(77, "머리 줄\n" + GUARD + "\n", "ResourceWarning: unclosed file\n")
        self.assertEqual(run_all._skip_reason(r), GUARD)

    def test_last_marked_line(self):
        # 머리 설명의 «SKIP»보다 끝의 이유 줄이 이긴다.
        r = _done(77, "SKIP은 통과가 아니다 (머리 설명)\n본문\n" + ENGINE + "\n")
        self.assertEqual(run_all._skip_reason(r), ENGINE.strip())

    def test_fallback_last_nonempty_line(self):
        r = _done(77, "첫 줄\n마지막 줄\n\n")
        self.assertEqual(run_all._skip_reason(r), "마지막 줄")

    def test_silent_child_says_so(self):
        self.assertIn("찍지 않았다", run_all._skip_reason(_done(77)))


class SummaryCarriesReason(unittest.TestCase):
    """러너 `main`을 가짜 자식으로 돌려 `RESULTS.txt` 끝 요약을 본다."""

    def run_main(self, outputs):
        steps = [(name, f"가짜 {name}", False, False, False) for name in outputs]

        def fake_run(cmd, **kw):
            return outputs[Path(cmd[-1]).name]

        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "RESULTS.txt"
            with mock.patch.object(run_all, "STEPS", steps), \
                    mock.patch.object(run_all, "OUT", out), \
                    mock.patch.object(run_all.subprocess, "run", side_effect=fake_run), \
                    mock.patch("sys.stdout", new=io.StringIO()):
                run_all.main([])
            return out.read_text(encoding="utf-8")

    def test_each_skip_shows_child_reason(self):
        text = self.run_main({
            "ok.py": _done(0, "정상\n"),
            "guard.py": _done(77, "본문\n" + GUARD + "\n"),
            "engine.py": _done(77, ENGINE + "\n"),
        })
        tail = text[text.index("건너뜀(77):"):]
        self.assertIn("guard.py, engine.py", tail.splitlines()[0])
        self.assertIn(f"guard.py: {GUARD}", tail)
        self.assertIn(f"engine.py: {ENGINE.strip()}", tail)
        self.assertIn("통과가 아니라 미측정이다", tail)
        self.assertNotIn(OLD_FIXED, text)

    def test_no_skip_no_reason_block(self):
        text = self.run_main({"ok.py": _done(0, "정상\n")})
        self.assertNotIn("건너뜀(77)", text)
        self.assertIn("전체 실험 정상 실행", text)


if __name__ == "__main__":
    unittest.main()
