# -*- coding: utf-8 -*-
"""
test_theta_grid.py — `theta_grid.py`의 검사들이 **발화할 수 있는가**, 그리고 조용한 쪽에서 조용한가.

eval 한 열만 쓴다(색인 21행 · 수 초). 규모 열은 본 실행이 잰다.
실행: PYTHONIOENCODING=utf-8 python -B -m unittest discover -s experiments/tests -p "test_theta_grid.py" -v
"""
import contextlib
import io
import math
import os
import random
import shutil
import socket
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

# 🔴 격리 (2026-09-11, 오케스트레이터) — 이 모듈의 «사본만 쓴다» 검사는 **새 프로세스에서만** 참일 수 있다.
#    `unittest discover`로 다른 시험과 한 프로세스에서 돌면, 앞선 시험이 원본 `prototype/`의 `memory` 등을
#    먼저 `sys.modules`에 올려 두고, 파이썬은 같은 이름을 다시 안 불러 사본이 쓰일 수 없다 — 그래서 셋이
#    빨갛게 운다(검사는 옳다). 그 경우 셋을 건너뛰고 `IsolatedRun`이 이 모듈 전체를 새 프로세스로 돌려 본다.
def _proto_already_loaded():
    orig = os.path.normcase(os.path.abspath(os.path.join(HERE, "..", "prototype")))
    for m in list(sys.modules.values()):
        f = getattr(m, "__file__", None)
        if f and os.path.normcase(os.path.dirname(os.path.abspath(f))) == orig:
            return True
    return False

ISOLATED = not _proto_already_loaded()
_SHARED = "원본 prototype이 먼저 올라온 공유 프로세스 — IsolatedRun이 새 프로세스로 대신 본다"

import theta_grid as T                                      # noqa: E402

M, RS, RD, SP, EA, MA = T.M, T.RS, T.RD, T.SP, T.EA, T.MA


def tearDownModule():
    if T.SNAP_OWNED:
        shutil.rmtree(os.path.dirname(T.SNAP), ignore_errors=True)


def J(on, off, better):
    """판정 튜플은 `engine_arms.judge`가 만든다 — 손으로 짓지 않는다."""
    return EA.judge(on, off, better)


class G1Prereg(unittest.TestCase):
    def test_every_condition_has_an_observation(self):
        for key, claim, how in T.PREREG:
            self.assertTrue(key and claim.strip() and how.strip(), key)

    def test_prereg_prints_first_and_has_no_arrow(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            T.print_prereg(["eval"])
        out = buf.getvalue()
        for key, _, _ in T.PREREG:
            self.assertIn(f"[{key}]", out)
        self.assertFalse([a for a in T.ARROWS if a in out])

    def test_grid_contains_current_combination(self):
        self.assertIn(T.REF[0], T.WEIGHTS)
        self.assertIn(T.REF[1], T.PENS_META)
        self.assertIn(T.REF[2], T.W_RECS)
        self.assertTrue(set(RS.STAGE2_WEIGHTS) <= set(T.WEIGHTS))
        self.assertEqual(len(T.cells_for(T.PATH_BASE)), 2 * 3 * 3)
        self.assertEqual(len(T.cells_for(T.PATH_META)), 2 * 3 * 2 * 3)

    def test_chunks_lose_nothing(self):
        cells = T.cells_for(T.PATH_META)
        for k in (1, 3, 8, 100):
            ch = T.chunks(cells, k)
            self.assertEqual(sorted(sum(ch, [])), sorted(cells))


class G2Classify(unittest.TestCase):
    """사전 등록 «판정 규칙»의 여섯 라벨이 모두 나오고, 각 관측이 제 라벨로 간다."""

    def test_six_labels(self):
        up9 = J([1] * 9, [0] * 9, "high")
        cases = {
            T.LAB_BETTER: (up9, J([0] * 9, [0] * 9, "low"), 0, 0),
            T.LAB_MIXED: (up9, J([1] + [0] * 8, [0] * 9, "low"), 1, 0),
            T.LAB_WORSE: (J([0] * 9, [1] * 9, "high"), J([0] * 9, [0] * 9, "low"), 0, 0),
            T.LAB_BOTH: (up9, J([1] * 8 + [0], [0] * 8 + [20], "low"), 8, 20),
            T.LAB_WEAK: (J([1, 0], [0, 0], "high"), J([0, 0], [0, 0], "low"), 0, 0),
            T.LAB_NULL: (J([1, 0] * 4, [0, 1] * 4, "high"), J([0] * 8, [0] * 8, "low"), 0, 0),
        }
        got = {lab: T.classify(*c) for lab, c in cases.items()}
        self.assertEqual(got, {lab: lab for lab in cases})

    def test_worse_by_misinjection_alone(self):
        self.assertEqual(T.classify(J([1, 0] * 4, [0, 1] * 4, "high"), J([1] * 8, [0] * 8, "low"), 8, 0),
                         T.LAB_WORSE)

    def test_better_requires_misinjection_not_up(self):
        up9 = J([1] * 9, [0] * 9, "high")
        self.assertEqual(T.classify(up9, J([0] * 9, [0] * 9, "low"), 3, 3), T.LAB_BETTER)
        self.assertNotEqual(T.classify(up9, J([0] * 9, [0] * 9, "low"), 4, 3), T.LAB_BETTER)


class G3Guards(unittest.TestCase):
    @unittest.skipUnless(ISOLATED, _SHARED)
    def test_snapshot_clean(self):
        self.assertEqual(T.snapshot_leaks(), [])
        self.assertTrue(os.path.normcase(M.__file__).startswith(os.path.normcase(T.SNAP)))

    @unittest.skipUnless(ISOLATED, _SHARED)
    def test_snapshot_leak_fires(self):
        fake = types.ModuleType("w8_fake_proto")
        fake.__file__ = os.path.join(T.PROTO, "w8_fake_proto.py")
        sys.modules["w8_fake_proto"] = fake
        try:
            self.assertTrue(any("w8_fake_proto" in b for b in T.snapshot_leaks()))
        finally:
            del sys.modules["w8_fake_proto"]
        self.assertEqual(T.snapshot_leaks(), [])

    def test_net_guard_fires(self):
        T.install_net_guard()
        try:
            s = socket.socket()
            with self.assertRaises(SystemExit):
                s.connect(("127.0.0.1", 9))
            s.close()
        finally:
            T.uninstall_net_guard()
            n = len(T.NET_TRIES)
            T.NET_TRIES.clear()
        self.assertEqual(n, 1)

    def test_defaults_drift_fires(self):
        self.assertEqual(T.defaults_drift(), {})
        keep = M.W_REC
        M.W_REC = 0.1
        try:
            self.assertIn("W_REC", T.defaults_drift())
        finally:
            M.W_REC = keep

    def test_task_guard_fires(self):
        T.task_guard("조용한 쪽")
        keep = RS.ingest
        RS.ingest = lambda *a, **k: None
        try:
            with self.assertRaises(SystemExit):
                T.task_guard("심은 위반")
        finally:
            RS.ingest = keep


class G4Theta(unittest.TestCase):
    """`theta_on`의 두 길이 `rel_dist.theta_at`과 같은 수를 낸다 — 큰 모집단 길(이분+증명)까지."""

    def test_equals_theta_at(self):
        rng = random.Random(20260911)
        pops = [[rng.choice([0.0, 0.1, 0.25, 0.5, 1.0]) for _ in range(300)],
                [round(rng.random(), 3) for _ in range(900)],            # 고유값 > 한도 → 이분+증명 길
                [rng.gauss(0, 1) for _ in range(700)]]
        for pop in pops:
            for f in (0.0, 0.3, 0.9, 0.9999, 1.0):
                th, how = T.theta_on(pop, f)
                self.assertEqual(th, RD.theta_at(pop, f), (how, f))
        self.assertEqual(T.theta_on(pops[1], 0.5)[1], "이분+증명")
        self.assertEqual(T.theta_on(pops[0], 0.5)[1], "theta_at")

    def test_unattainable_is_inf(self):
        self.assertEqual(T.theta_on([0.0] * 10, 0.5)[0], math.inf)
        self.assertEqual(RD.theta_at([0.0] * 10, 0.5), math.inf)


class G5Tables(unittest.TestCase):
    def setUp(self):
        T.TABLE_BAD.clear()

    def tearDown(self):
        T.TABLE_BAD.clear()

    def _t(self, cols, rows):
        with contextlib.redirect_stdout(io.StringIO()):
            T.table("시험 표", cols, rows)
        return list(T.TABLE_BAD)

    def test_clean_is_silent(self):
        self.assertEqual(self._t([SP.Col("eval", "훈련 16문항", "색인 21행", "recall@5")],
                                 [("끔 · W_IMP 0.4", ["1/2"])]), [])

    def test_bare_item_set_fires(self):
        self.assertTrue(self._t([SP.Col("eval", "16", "색인 21행", "recall@5")], [("끔", ["1/2"])]))

    def test_arrow_fires(self):
        self.assertTrue(self._t([SP.Col("eval", "훈련 16문항", "색인 21행", "recall@5")], [("끔", ["1→2"])]))

    def test_duplicate_row_label_fires(self):
        self.assertTrue(self._t([SP.Col("eval", "훈련 16문항", "색인 21행", "recall@5")],
                                [("끔", ["1"]), ("끔", ["2"])]))


class G6Pipeline(unittest.TestCase):
    """eval 한 열을 순차로 — 자기 대조가 조용한 쪽에서 조용하고, 옮겨 심기 대조가 발화한다."""

    @classmethod
    def setUpClass(cls):
        # 자기 대조는 `SystemExit`로 멈춘다 — `setUpClass`에서 그대로 새면 unittest가 전체 실행을 끊고 요약도
        # 안 찍는다(실측: 심은 위반 T2). 보통 오류로 바꿔 나머지 시험이 돌고 요약에 이름이 남게 한다.
        try:
            cls._setup()
        except SystemExit as e:
            raise RuntimeError(f"자기 대조가 종료를 던졌다: {e}") from e

    @classmethod
    def _setup(cls):
        cls.tmp = tempfile.mkdtemp(prefix="w8theta_test_")
        cls.a1 = T.stage_a1("eval", 0, cls.tmp)
        cls.a2 = T.stage_a2("eval", 0)
        cls.mt = os.path.join(cls.tmp, "meta0.db")
        cls.meta = T.make_meta_template(cls.a1["tpl"], cls.mt, cls.a2)
        w, p, r = T.REF
        hi = max(T.W_RECS)
        cls.cells = {
            "off": (T.PATH_BASE, False, w, p, r), "on": (T.PATH_BASE, True, w, p, r),
            "slow": (T.PATH_SLOW, False, w, p, r),
            "on_rec": (T.PATH_BASE, True, w, p, hi), "slow_on_rec": (T.PATH_SLOW, True, w, p, hi),
            "off0": (T.PATH_BASE, False, w, 0.0, r), "on0": (T.PATH_BASE, True, w, 0.0, r)}
        cls.mcells = {"moff0": (T.PATH_META, False, w, 0.0, r), "mon0": (T.PATH_META, True, w, 0.0, r),
                      "mon": (T.PATH_META, True, w, p, r)}
        b = T.stage_b("eval", 0, list(cls.cells.values()), {T.PATH_BASE: cls.a1["tpl"]}, cls.a1["f"])
        m = T.stage_b("eval", 0, list(cls.mcells.values()), {T.PATH_META: cls.mt}, cls.a1["f"])
        cls.res = {o["cell"]: o for o in b["out"] + m["out"]}
        cls.leaks = b["leaks"] + m["leaks"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def r(self, key):
        return self.res[{**self.cells, **self.mcells}[key]]

    def test_base_expect(self):
        t = T.agg(self.r("off"), self.a1["train"] + self.a1["ho"])
        got = dict(recall=t["ev"], mis=t["mis"][0], pooled=t["mis"], top1=t["top1"], ties=t["ties"])
        self.assertEqual(got, RS.BASE_EXPECT)

    def test_fast_equals_slow(self):
        self.assertEqual(self.r("off")["sha"], self.r("slow")["sha"])
        self.assertEqual(self.r("on_rec")["sha"], self.r("slow_on_rec")["sha"])
        self.assertEqual(self.r("on_rec")["theta"], self.r("slow_on_rec")["theta"])
        self.assertEqual(list(T.check_cells()[2]), [self.cells["slow"], self.cells["slow_on_rec"]])

    def test_penalty_zero_points(self):
        self.assertEqual(self.r("off0")["sha"], self.r("off")["sha"])
        self.assertEqual(self.r("on0")["sha"], self.r("on")["sha"])
        self.assertEqual(self.r("moff0")["sha"], self.r("off")["sha"])
        self.assertEqual(self.r("mon0")["sha"], self.r("on")["sha"])

    def test_penalty_channel_is_live_only_on_meta(self):
        self.assertEqual(self.r("off")["surf"], 0)
        self.assertGreater(self.r("mon")["surf"], 0)
        self.assertEqual(self.meta["sum"], self.a2["emitted"]["used_event"])

    def test_rel_read_is_coverage_and_f_reported(self):
        self.assertEqual(self.a1["rel_bad"], 0)
        self.assertTrue(0 < self.a1["f"] < 1)
        th = self.r("on")["th"]
        self.assertEqual(set(th), {"theta", "f", "cut", "n", "how", "uniq"})
        self.assertEqual(th["n"], len(self.a1["train"]) * self.a1["tau"])

    @unittest.skipUnless(ISOLATED, _SHARED)
    def test_switches_restored_and_one_version(self):
        self.assertEqual(T.defaults_drift(), {})
        self.assertIs(M.Memory.retrieve, T._RETRIEVE0)
        self.assertIs(RS.ingest, T._INGEST0)
        self.assertEqual(self.leaks, [])

    def test_transplant_mismatch_fires(self):
        rows = list(self.a2["rows"])
        r0 = list(rows[0])
        r0[3] = (r0[3] or 0) + 0.5                       # importance 한 칸
        bad = dict(self.a2, rows=[tuple(r0)] + rows[1:])
        with self.assertRaises(SystemExit):
            T.make_meta_template(self.a1["tpl"], os.path.join(self.tmp, "bad.db"), bad)

    def test_transplant_sum_mismatch_fires(self):
        bad = dict(self.a2, emitted=dict(self.a2["emitted"], used_event=self.a2["emitted"]["used_event"] + 1))
        with self.assertRaises(SystemExit):
            T.make_meta_template(self.a1["tpl"], os.path.join(self.tmp, "bad2.db"), bad)


class IsolatedRun(unittest.TestCase):
    """공유 프로세스일 때만 — 이 모듈 전체를 새 인터프리터로 돌려 «사본만 쓴다» 검사까지 통과하는지 본다."""

    @unittest.skipIf(ISOLATED, "이미 격리된 프로세스 — 위 시험들이 직접 돈다")
    def test_module_passes_in_fresh_process(self):
        import subprocess
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        r = subprocess.run([sys.executable, "-B", "-m", "unittest", "-v", "test_theta_grid"],
                           cwd=os.path.dirname(os.path.abspath(__file__)), env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, "격리 실행 실패:\n" + r.stderr[-2000:])
        # 새 프로세스에서 세 시험이 **실제로 돌아 ok**였는가 — 건너뛰었다면 격리 판정이 틀린 것이다
        for name in ("test_snapshot_clean", "test_snapshot_leak_fires",
                     "test_switches_restored_and_one_version"):
            self.assertRegex(r.stderr, name + r" \(.*\) \.\.\. ok",
                             f"격리 실행에서 {name}이 돌지 않았다")


if __name__ == "__main__":
    unittest.main()
