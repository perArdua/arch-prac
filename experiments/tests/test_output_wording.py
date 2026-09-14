# -*- coding: utf-8 -*-
"""
test_output_wording.py — «낡은 출력 문구» 셋(인수인계 §2-8)이 **출력으로** 되돌아오지 않는지 지킨다 (w12close).

셋은 코드가 바뀐 뒤 거짓이 된 출력 문장이었다(w11b · w11a가 고쳤다):
  · `theta_grid.py` 머리 «실험 번호 없음»            — 실험 33으로 번호를 받았다
  · `engine_arms.py` 지연 절 «전량 스캔 + bigram 계산» — 행 bigram은 내용 주소 메모에서 꺼낸다(w8)
  · `retrieve_scaling.py` 끝 «행마다 bigram 재계산»  — 워밍업 뒤 웜 메모다(`run_all` 밖이라 `RESULTS.txt`도 못 지킨다)
넷째(`run_all.py`의 SKIP 설명)는 `test_run_all_skip_reason.py`가 지킨다.

🔴 **출력 문자열만 본다** — `print(...)` 호출 안의 문자열 상수(AST). 독스트링·주석에는 옛 글자를 **일부러** 남겼다
(«그때 그랬다»의 기록) — 파일 전체를 grep하면 그 기록 때문에 늘 울거나, 기록을 지우게 된다.
"""
import ast
import os
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (파일, 지금 출력에 있어야 할 글자, 출력에 없어야 할 옛 글자)
WORDING = [
    ("theta_grid.py", ["검B2 (실험 33 · 보고 전용"], ["실험 번호 없음"]),
    ("engine_arms.py", ["전량 스캔을 하되", "행 bigram은 내용 주소 메모에서 꺼낸다"],
     ["SQLite 전량 스캔 +", "bigram 계산을 한다"]),
    ("retrieve_scaling.py", ["워밍업 뒤 웜 메모"], ["행마다 bigram 재계산"]),
]


def print_text(src):
    """`print(...)` 호출 안의 문자열 상수를 전부 이어 붙인다(f-문자열의 글자 조각 · 이어 쓴 리터럴 포함)."""
    out = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    out.append(sub.value)
    return "\n".join(out)


class TestPrintTextIsOutputOnly(unittest.TestCase):
    """검사기 자신 — 주석·독스트링의 옛 글자에는 조용하고 출력의 옛 글자에는 운다."""

    def test_comment_and_docstring_are_silent(self):
        src = '"""실험 번호 없음"""\nx = 1  # 실험 번호 없음\nprint("실험 33")\n'
        self.assertNotIn("실험 번호 없음", print_text(src))

    def test_print_literal_fires(self):
        for src in ('print("머리 (실험 번호 없음)")\n',
                    'print(f"{1} 실험 번호 없음")\n',
                    'print("앞 "\n      "실험 번호 없음")\n'):
            self.assertIn("실험 번호 없음", print_text(src), src)


class TestStaleWordingStaysGone(unittest.TestCase):

    def test_each_file(self):
        for name, new, old in WORDING:
            with open(os.path.join(HERE, name), encoding="utf-8") as f:
                txt = print_text(f.read())
            with self.subTest(name=name):
                for w in new:
                    self.assertEqual(txt.count(w), 1, f"{name}: 지금 문구 «{w}»가 출력에 한 번 있어야 한다")
                for w in old:
                    self.assertNotIn(w, txt, f"{name}: 낡은 문구 «{w}»가 출력에 돌아왔다")


if __name__ == "__main__":
    unittest.main()
