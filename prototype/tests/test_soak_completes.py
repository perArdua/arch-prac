# -*- coding: utf-8 -*-
"""
test_soak_completes.py — **G2: `soak.py`가 끝까지 돈다.**

`soak.py`는 `run_all.STEPS`에 없다. 그래서 `Memory.gate`에 방 인자(`chat_id`)가 붙은
날, 5절이 꽂는 발견 당시 게이트 대역(`_legacy_gate(self, u)`)이 서명을 못 따라가
`TypeError`로 죽었는데 **어느 회귀도 그것을 못 봤다** — 러너가 안 돌리고, 시험도
`main()`을 안 불렀기 때문이다(wave2가 T2의 «기본 소크 불변» 대조를 뜨다가 찾았다).

이 시험이 그 자리를 문다. `main()`을 **통째로** 돌린다.

🔴 **DB는 `%TEMP%`에 만든다.** `soak.main()`은 `ROOT/prototype/` 아래에 파일 DB를
   만들므로, `eval/`의 세 파일을 임시 디렉터리로 **복사해 읽고**(원본은 안 건드린다 —
   A8) `soak.ROOT`를 그리로 돌린 뒤 `finally`로 되돌린다.
🔴 **전역을 스스로 되돌린다.** `soak.main()`은 5절에서 `Memory.gate`·
   `INJECT_KNOWN_FACTS`·`PREDICATE_STANDING`·`THETA_RELEVANCE`를 바꾸고 끝에서만
   되돌린다 — 도중에 죽으면 **다음 시험들이 대역 게이트로 돈다.** 그래서 여기서 뜨고
   `finally`로 되돌린다(G13).
"""
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import memory as M                                          # noqa: E402
import soak                                                 # noqa: E402

EVAL_FILES = ("corpus/corpus.jsonl", "fact-ledger.yaml", "questions.yaml")


class SoakCompletes(unittest.TestCase):

    def test_main_runs_to_the_end(self):
        """
        **심을 위반:** `_legacy_gate`의 `chat_id=None`을 지우면 5절에서 `TypeError`로
        죽어 발화한다.
        """
        tmp = tempfile.mkdtemp(prefix="soak-g2-")
        saved = (soak.ROOT, M.Memory.gate, M.INJECT_KNOWN_FACTS,
                 M.Memory.PREDICATE_STANDING, M.THETA_RELEVANCE)
        try:
            for rel in EVAL_FILES:
                dst = os.path.join(tmp, "eval", rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copyfile(os.path.join(saved[0], "eval", rel), dst)
            os.makedirs(os.path.join(tmp, "prototype"))
            soak.ROOT = tmp
            buf = io.StringIO()
            with redirect_stdout(buf):
                soak.main()
            out = buf.getvalue()
        finally:
            (soak.ROOT, M.Memory.gate, M.INJECT_KNOWN_FACTS,
             M.Memory.PREDICATE_STANDING, M.THETA_RELEVANCE) = saved
            shutil.rmtree(tmp, ignore_errors=True)
        # 5절의 네 설정이 다 찍히고 6절까지 갔는가 — «죽지 않았다»만이 아니라
        # «끝까지 갔다»를 본다.
        for mark in ("A. 검색만", "D. + 실험 12", "6. upsert_fact 실제 동작 분포"):
            self.assertIn(mark, out)
        # 조용한 쪽 — 돌고 난 뒤 프로덕션 게이트가 제자리다(대역이 새지 않았다).
        # 같은 메서드 안에 두는 이유: 따로 두면 알파벳 순서상 `main()`보다 **먼저**
        # 돌아 아무것도 안 잰다.
        self.assertEqual(M.Memory.gate.__name__, "gate")
        self.assertIs(M.INJECT_KNOWN_FACTS, True)


if __name__ == "__main__":
    unittest.main()
