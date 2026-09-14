# -*- coding: utf-8 -*-
"""
test_eval_controls_audit.py — `eval_controls_audit.py`가 **발화하는가**를 심어서 본다.

규약(이 저장소의 «발화할 수 없는 검사» 열두 번의 대가):
  · 심은 위반은 **표식 계수 0 → ≥1**로 심겼는지 먼저 확인한다
  · 치환이면 **옛 글자가 사라졌는지**도 확인한다
  · 발화 쪽만 보지 않는다 — **조용해야 할 쪽**(주석·문자열·생성 없는 파일)도 심는다
원본은 건드리지 않는다. 변이는 문자열 또는 `%TEMP%` 복사본에만 한다.
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import eval_controls_audit as A  # noqa: E402

QR = (HERE / "quality_run.py").read_text(encoding="utf-8")
ADR = A.ADR_PATH.read_text(encoding="utf-8")


def plant(src, old, new, marker):
    """치환을 심는다 — 심겼다는 증거(표식 0→≥1 · 옛 글자 사라짐)가 없으면 시험을 멈춘다."""
    assert src.count(marker) == 0, f"표식이 원본에 이미 있다: {marker!r}"
    assert src.count(old) == 1, f"치환 대상이 한 곳이 아니다: {old!r} ×{src.count(old)}"
    out = src.replace(old, new)
    assert out.count(marker) >= 1, "표식이 안 심겼다"
    assert out.count(old) == 0 or old in new, "옛 글자가 남았다"
    return out


def append(src, text, marker):
    """덧붙이기 — 표식 0→≥1만 본다(치환이 아니다)."""
    assert src.count(marker) == 0, f"표식이 원본에 이미 있다: {marker!r}"
    out = src + text
    assert out.count(marker) >= 1
    return out


class RequirementsTest(unittest.TestCase):
    def test_real_adr(self):
        r = A.adr_requirements(ADR)
        self.assertEqual(r["arms"], ["A0", "A1", "A2", "A3", "G1"])
        self.assertEqual(r["budget"], 4000)
        self.assertEqual(r["repeat"], 3)
        self.assertEqual(r["kappa"], (20, 30))

    def test_missing_requirement_raises(self):
        # 요구가 비면 모든 검사가 항등 통과한다 — 조용히 넘어가면 안 된다
        bad = plant(ADR, "| 반복 |", "| REPEAT_GONE |", "REPEAT_GONE")
        with self.assertRaises(ValueError):
            A.adr_requirements(bad)

    def test_adr_repeat_change_moves_verdict(self):
        # ADR이 요구를 1회로 낮추면 같은 코드가 «충족»이 된다 — 요구를 파일에서 읽는다는 증거
        low = plant(ADR, "arm·문항당 3회", "arm·문항당 1회", "문항당 1회")
        self.assertEqual(A.check_repeat(QR, A.adr_requirements(low)["repeat"])[0], "충족")


class StaticChecksTest(unittest.TestCase):
    def test_repeat_fires(self):
        self.assertEqual(A.check_repeat(QR, 3)[0], "위반")
        fixed = plant(QR, '"--repeat", type=int, default=1,',
                      '"--repeat", type=int, default=3,', '"--repeat", type=int, default=3,')
        self.assertEqual(A.check_repeat(fixed, 3)[0], "충족")

    def test_seed_fires_and_comment_is_silent(self):
        self.assertEqual(A.check_generation_config(QR)[1][0], "위반")
        with_seed = plant(QR, '"generationConfig": {"temperature": 0.7,',
                          '"generationConfig": {"seed": 7, "temperature": 0.7,', '"seed": 7')
        self.assertEqual(A.check_generation_config(with_seed)[1][0], "충족")
        # 조용한 쪽: 주석에 적은 seed는 AST가 안 본다
        commented = append(QR, '\n# "generationConfig": {"seed": 8}\n', '"seed": 8')
        self.assertEqual(A.check_generation_config(commented)[1][0], "위반")

    def test_second_generation_config_breaks_temperature(self):
        self.assertEqual(A.check_generation_config(QR)[0][0], "충족")
        two = append(QR, '\nOTHER = {"generationConfig": {"temperature": 0.2}}\n',
                     '"temperature": 0.2')
        self.assertEqual(A.check_generation_config(two)[0][0], "위반")

    def test_budget_static_ignores_comments(self):
        self.assertEqual(A.check_budget_static(QR, 4000), ([], []))
        # 조용한 쪽: 주석·문자열에 적은 예산은 «예산이 코드에 있다»가 아니다
        cmt = append(QR, '\n# 예산 4000 budget\nNOTE = "budget 4000"\n', "budget 4000")
        self.assertEqual(A.check_budget_static(cmt, 4000), ([], []))
        code = append(QR, "\nCONTEXT_BUDGET = 4000\n", "CONTEXT_BUDGET")
        nums, names = A.check_budget_static(code, 4000)
        self.assertGreaterEqual(len(nums), 1)
        self.assertGreaterEqual(len(names), 1)


class DirScanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="evalctl_t_"))
        for p in HERE.glob("*.py"):
            shutil.copy(p, self.tmp / p.name)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _edit(self, name, fn):
        p = self.tmp / name
        p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")

    def test_clean_copy_matches_known(self):
        rows = A.scan_dir(self.tmp)
        self.assertEqual(A.check_random_k(rows)[0], "참")
        self.assertEqual(A.check_kappa(rows)[0], "참")

    def test_random_arm_in_generation_file_fires(self):
        self._edit("quality_run.py", lambda s: append(
            s, "\ndef arm_random_k(q):\n    return q\n", "def arm_random_k"))
        self.assertEqual(A.check_random_k(A.scan_dir(self.tmp))[0], "거짓")

    def test_random_arm_in_sim_file_is_silent(self):
        # 조용한 쪽: 생성 호출이 없는 파일에 무작위 arm이 늘어도 «검색 시뮬에만»은 참이다
        (self.tmp / "zz_new_sim.py").write_text("def arm_random(docs):\n    return docs\n",
                                               encoding="utf-8")
        self.assertEqual(A.check_random_k(A.scan_dir(self.tmp))[0], "참")

    def test_no_pattern_hit_is_not_a_pass(self):
        # 적중 0이면 «참»이 아니라 «못 봄» — 패턴이 낡아도 초록이 되지 않게
        only = Path(tempfile.mkdtemp(prefix="evalctl_o_"))
        try:
            shutil.copy(HERE / "quality_run.py", only / "quality_run.py")
            self.assertEqual(A.check_random_k(A.scan_dir(only))[0], "못 봄")
        finally:
            shutil.rmtree(only, ignore_errors=True)

    def test_kappa_code_fires_docstring_silent(self):
        (self.tmp / "zz_doc.py").write_text('"""κ(kappa)는 다음 라운드에 잰다."""\n',
                                           encoding="utf-8")
        self.assertEqual(A.check_kappa(A.scan_dir(self.tmp))[0], "참")
        (self.tmp / "zz_calc.py").write_text("def cohen_kappa(a, b):\n    return 0\n",
                                            encoding="utf-8")
        self.assertEqual(A.check_kappa(A.scan_dir(self.tmp))[0], "거짓")

    def test_main_exit_code_flips_on_planted_fix(self):
        # 고쳐진 위반도 운다 — KNOWN을 고치라는 신호
        self.assertEqual(A.main(["--exp-dir", str(self.tmp), "--no-assemble"]), 0)
        self._edit("quality_run.py", lambda s: plant(
            s, '"--repeat", type=int, default=1,', '"--repeat", type=int, default=3,',
            '"--repeat", type=int, default=3,'))
        self.assertEqual(A.main(["--exp-dir", str(self.tmp), "--no-assemble"]), 1)


class VerdictTest(unittest.TestCase):
    def test_budget_ratio(self):
        same = {"A1 x": {"chars": [100, 100]}, "C  y": {"chars": [105, 105]},
                "A0 z": {"chars": [1, 1]}}
        self.assertLessEqual(A.verdict_budget(same)[0], 1.10)     # A0는 빼고 본다
        apart = {"A1 x": {"chars": [100]}, "C  y": {"chars": [300]}}
        self.assertGreater(A.verdict_budget(apart)[0], 1.10)

    def test_recent(self):
        self.assertEqual(len(set(A.verdict_recent(
            {"A1 x": {"turns": [10]}, "G1 y": {"turns": [10]}, "A0 z": {"turns": [0]}}
        ).values())), 1)


class AssembleTest(unittest.TestCase):
    def test_assemble_leaves_no_file_in_prototype(self):
        db = A.ROOT / "prototype" / ".quality.db"
        self.assertFalse(db.exists())
        asm, nq = A.assemble(HERE / "quality_run.py")
        self.assertFalse(db.exists())                 # ROOT 재바인딩이 먹었다
        self.assertEqual(nq, 26)
        self.assertEqual(len(asm), 6)
        self.assertNotIn("A3", {n.split()[0] for n in asm})


if __name__ == "__main__":
    unittest.main()
