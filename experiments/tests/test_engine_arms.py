# -*- coding: utf-8 -*-
"""
test_engine_arms.py — `engine_arms`의 팔이 **관련도 함수만** 다르고 나머지 단계는 `memory.py`의
정본 하나(4단계 함수)를 지나는가. (w6code · docs/17 축-1)

  E1  정적 — `engine_arms.py`에 점수식 사본의 모양이 0곳이다: 가중치·τ·상위 K·스위치 이름이
      계산에 쓰임 · 행의 `importance`/`event_id` 따위를 직접 읽음 · `-점수` 정렬 키 · θ 비교.
      사본 모양을 하나씩 심으면 운다(표식 계수 0 → 1 · 탐지 0 → ≥1). 호출 인자로 넘기는 것은
      안 운다(조용한 쪽 — `cell_for`가 이미 그렇게 쓴다).
  E2  등가 — A0 채점기를 팔 경로(`make_retrieve`)로 꽂은 결과가 프로덕션 4단계 함수와 스위치 셋
      (끔 · THETA_ON_SCORE · W_REC) 모두에서 같다. 편집 전 모양의 사본 `make_retrieve`를 심으면
      켠 두 칸에서 운다 — 그리고 **끈 칸에서는 안 운다.** 스위치를 끈 대조만으로는 이 결함을
      잡을 수 없다는 것이 그 칸의 관측이다.
  E3  전파 — A0가 아닌 팔(A1 · BM25)도 스위치를 켜면 격자 경로와 순위 전체가 둘 다 바뀐다.
      THETA_ON_SCORE에서는 «relevance … < θ» 거절이 0이 된다(θ가 `rel`에 안 걸린다).
  E4  `rank_all`의 순위 전체 앞 K개 = 같은 팔의 격자 경로 반환 — 같은 함수이고 절단만 다르다.
  E5  외부 관련도 목록의 길이가 행 수와 다르면 던진다(조용히 어긋나지 않는다).
  E6  G1 — 컨테이너가 없으면(도구 자체가 없어도) 컨테이너 팔 셋이 SKIP 사유를 받고 순수 파이썬 팔은
      안 받는다. 옛 `_run`(도구 없음에서 터짐)을 심으면 운다.

🔴 컨테이너는 **건드리지 않는다** — E6은 `_run`/`subprocess.run`을 갈아 끼워 «없음»을 만든다.
임시 DB는 `%TEMP%`다(`rel_dist`·`retrieval_sweep`의 `ROOT`를 돌려 둔다).
"""
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import engine_arms as EA  # noqa: E402
import memory as M  # noqa: E402
from memory import Memory  # noqa: E402
import rel_dist as RD  # noqa: E402
import retrieval_sweep as RS  # noqa: E402
from soak import CHAT, seed, ingest  # noqa: E402

SRC = os.path.join(HERE, "engine_arms.py")
KNOBS = ("THETA_ON_SCORE", "W_REC", "RETRIEVAL_MODE", "THETA_RELEVANCE",
         "W_REL", "W_IMP", "SURFACED_PENALTY", "TOP_K")
SWITCHES = {"off": {}, "theta_on_score": {"THETA_ON_SCORE": True}, "w_rec": {"W_REC": 0.2}}

# ── E1 탐지기 ────────────────────────────────────────────────────────────
# 점수식의 부품 — 이 이름이 **계산에** 쓰이면(산술 · 비교 · 슬라이스 · 조건식) 사본이다.
SCORING_NAMES = {"W_REL", "W_IMP", "SURFACED_PENALTY", "TAU_IMPORTANCE", "TOP_K",
                 "THETA_ON_SCORE", "W_REC", "RECENCY_HALF_LIFE"}
COMPUTE = (ast.BinOp, ast.Compare, ast.UnaryOp, ast.BoolOp, ast.Subscript, ast.Slice,
           ast.IfExp, ast.AugAssign)
# 행을 직접 읽어 점수를 짓는 칸 — 4단계 함수만 읽어야 한다.
ROW_COLS = {"importance", "emotional_weight", "surfaced_count", "event_id", "source_from_seq"}


def _name(n):
    if isinstance(n, ast.Attribute):
        return n.attr
    if isinstance(n, ast.Name):
        return n.id
    return None


def copies(src):
    """점수식 사본의 모양을 `[(줄, 사유)]`로. 빈 목록 = 사본 없음."""
    tree = ast.parse(src)
    parent = {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
    out = set()
    for n in ast.walk(tree):
        nm = _name(n)
        if nm in SCORING_NAMES and isinstance(parent.get(n), COMPUTE):
            out.add((n.lineno, f"점수식 부품 `{nm}`이 계산에 쓰인다"))
        if (isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant)
                and n.slice.value in ROW_COLS):
            out.add((n.lineno, f"행의 `{n.slice.value}`를 직접 읽는다"))
        if isinstance(n, ast.Call) and (_name(n.func) in ("sort", "sorted")):
            for kw in n.keywords:
                if kw.arg == "key" and any(isinstance(x, ast.UnaryOp) and isinstance(x.op, ast.USub)
                                           for x in ast.walk(kw.value)):
                    out.add((n.lineno, "`-점수` 정렬 키 — 순위 규약 사본"))
        if isinstance(n, ast.Compare):
            if any((_name(x) or "").lower().find("theta") >= 0 for x in (n.left, *n.comparators)):
                out.add((n.lineno, "θ 비교 — 컷 사본"))
    return sorted(out)


# 심을 사본 모양. 표식(`w6plant-…`)은 원본에 없어야 하고 심은 뒤 정확히 1이어야 한다.
PLANTS = {
    "가중합": "def _p():\n    s = M.W_REL * rel + M.W_IMP * imp  # w6plant-sum\n",
    "τ 게이트": "def _p():\n    if imp < M.TAU_IMPORTANCE:  # w6plant-tau\n        pass\n",
    "상위 K": "def _p():\n    return hits[:M.TOP_K]  # w6plant-topk\n",
    "동점 정렬": "def _p():\n    cand.sort(key=lambda x: (-x[0], x[1]))  # w6plant-sort\n",
    "θ 컷": "def _p():\n    if rel < arm.theta:  # w6plant-theta\n        pass\n",
    "행 직접 읽기": 'def _p():\n    imp = max(r["importance"] or 0, 0)  # w6plant-imp\n',
    "recency": "def _p():\n    s -= M.W_REC * p  # w6plant-rec\n",
}
QUIET = "def _q():\n    print(M.TOP_K, M.W_REL)  # w6plant-quiet\n"


def copy_make_retrieve(scorer, theta, full=False):
    """
    🔴 **발화 확인용 변이** — 편집 전 `engine_arms.make_retrieve`의 모양(점수식 사본)을 그대로 옮긴
    것이다. E2가 이것을 심어 우는지를 본다. 여기 말고 어디에도 쓰지 않는다.
    """
    def retrieve(self, chat_id, query, now_seq):
        self._retrieval_notes = []
        rows = self.db.execute(
            "SELECT event_id, summary, importance, emotional_weight,"
            " surfaced_count FROM event WHERE chat_id=? AND user_deleted=0",
            (chat_id,)).fetchall()
        if not rows:
            return [], []
        rels = scorer.rels(query, [r["summary"] for r in rows])
        scored, rejected = [], []
        for i, r in enumerate(rows):
            imp = max(r["importance"] or 0, r["emotional_weight"] or 0)
            if imp < M.TAU_IMPORTANCE:
                rejected.append((r["summary"], f"importance {imp:.2f} < τ"))
                continue
            rel = rels[i]
            if rel < theta:
                rejected.append((r["summary"], f"relevance {rel:.2f} < θ"))
                continue
            s = (M.W_REL * rel + M.W_IMP * imp
                 - M.SURFACED_PENALTY * (r["surfaced_count"] or 0))
            scored.append((s, r))
        scored.sort(key=lambda x: (-x[0], x[1]["event_id"]))
        return scored[:M.TOP_K], rejected
    return retrieve


class E1Static(unittest.TestCase):
    def setUp(self):
        with open(SRC, encoding="utf-8") as f:
            self.src = f.read()

    def test_real_file_has_no_copy(self):
        self.assertEqual(copies(self.src), [])

    def test_each_plant_fires(self):
        for label, plant in PLANTS.items():
            marker = re.search(r"w6plant-[a-z]+", plant).group(0)
            with self.subTest(label):
                self.assertEqual(self.src.count(marker), 0)          # 원본에 표식 없음
                mutant = self.src + "\n\n" + plant
                self.assertEqual(mutant.count(marker), 1)            # 심겼다
                self.assertGreaterEqual(len(copies(mutant)), 1)      # 운다

    def test_whole_old_copy_fires(self):
        import inspect
        body = inspect.getsource(copy_make_retrieve)
        self.assertEqual(self.src.count("def copy_make_retrieve"), 0)
        mutant = self.src + "\n\n" + body
        self.assertEqual(mutant.count("def copy_make_retrieve"), 1)
        self.assertGreaterEqual(len(copies(mutant)), 5)

    def test_call_arguments_are_quiet(self):
        marker = "w6plant-quiet"
        self.assertEqual(self.src.count(marker), 0)
        mutant = self.src + "\n\n" + QUIET
        self.assertEqual(mutant.count(marker), 1)
        self.assertEqual(copies(mutant), [])


class CorpusCase(unittest.TestCase):
    """soak 코퍼스의 색인 하나를 클래스 전체가 쓴다. 4단계 함수는 DB를 쓰지 않는다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="test_engine_arms_")
        os.makedirs(os.path.join(cls.tmp, "prototype"))
        cls.saved_root = (RD.ROOT, RS.ROOT)
        RD.ROOT = RS.ROOT = cls.tmp
        cls.env, cls.docs, _ = EA.env_and_docs()
        corpus, ledger, qs, scored, key_of = cls.env
        cls.asks = [q["ask"] for q in scored]
        cls.last = corpus[-1]["seq"]
        cls.m = Memory(os.path.join(cls.tmp, "t.db"))
        seed(cls.m)
        ingest(cls.m, corpus, ledger, timed=False)
        cls.a0 = EA.PyScorer(EA.terms_bigram, EA.rank_coverage)
        # 🔄 w7engines — `make_bm25`가 Lucene `BM25Similarity` 식(분자 `(k1+1)` 없음)으로 바뀌었다. 이 시험들이
        #    재는 것은 «스위치가 A0 아닌 팔에 닿는가»라는 **구조**이고 척도가 아니다 — 척도가 1/2.2로 줄자
        #    THETA_ON_SCORE가 순위 전체를 우연히 안 바꾸는 칸이 생겼다(E3 [theta_on_score] 실측). 그래서 이 시험의
        #    A1은 편집 전과 같은 척도(교과서 식 = Lucene 식 × (k1+1))로 둔다 — 편집 전 시험과 같은 칸을 잰다.
        _bm25 = EA.make_bm25(EA.BM25_K1, EA.BM25_B)
        cls.a1 = EA.PyScorer(EA.terms_bigram,
                             lambda q, d, st: (EA.BM25_K1 + 1) * _bm25(q, d, st))

        def pop(sc):
            return [v for a in cls.asks for v in sc.rels(a, cls.docs)]
        cut = RD.actual_cut(pop(cls.a0), M.THETA_RELEVANCE)
        cls.th1 = RD.theta_at(pop(cls.a1), cut)

    @classmethod
    def tearDownClass(cls):
        cls.m.db.close()
        RD.ROOT, RS.ROOT = cls.saved_root
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.saved = {k: getattr(M, k) for k in KNOBS}
        self.assertIs(Memory.retrieve, EA._RETRIEVE)

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(M, k, v)
        self.assertIs(Memory.retrieve, EA._RETRIEVE)

    def switch(self, name):
        for k, v in SWITCHES[name].items():
            setattr(M, k, v)

    def log(self, fn):
        out = []
        for a in self.asks:
            hits, rej = fn(self.m, CHAT, a, self.last)
            out.append(([(repr(s), r["summary"]) for s, r in hits], list(rej)))
        return out

    def divergence(self, make, name):
        """A0 채점기를 `make`로 꽂은 경로가 프로덕션과 갈리는 문항 수 (18문항 중)."""
        self.switch(name)
        try:
            prod = self.log(Memory.retrieve)
            arm = self.log(make(self.a0, M.THETA_RELEVANCE))
        finally:
            for k in SWITCHES[name]:
                setattr(M, k, self.saved[k])
        self.assertEqual(len(prod), 18)
        return sum(1 for x, y in zip(prod, arm) if x != y)


class E2Equivalence(CorpusCase):
    def test_arm_path_equals_production_under_every_switch(self):
        for name in SWITCHES:
            with self.subTest(name):
                self.assertEqual(self.divergence(EA.make_retrieve, name), 0)

    def test_planted_copy_fires_only_when_switched_on(self):
        self.assertEqual(self.divergence(copy_make_retrieve, "off"), 0)      # 조용한 쪽
        self.assertGreaterEqual(self.divergence(copy_make_retrieve, "theta_on_score"), 1)
        self.assertGreaterEqual(self.divergence(copy_make_retrieve, "w_rec"), 1)


class E3Propagation(CorpusCase):
    def ranked(self, name):
        arm = EA.EngineArm(*EA.ARM_SPECS[1])
        self.assertEqual(arm.key, "A1")
        arm.scorer, arm.theta = self.a1, self.th1
        self.switch(name)
        try:
            EA.rank_all(arm, self.docs, self.env)
        finally:
            for k in SWITCHES[name]:
                setattr(M, k, self.saved[k])
        return arm.ranked

    def grid(self, name):
        self.switch(name)
        try:
            return self.log(EA.make_retrieve(self.a1, self.th1))
        finally:
            for k in SWITCHES[name]:
                setattr(M, k, self.saved[k])

    def test_switches_reach_non_a0_arm_on_both_paths(self):
        off_g, off_r = self.grid("off"), self.ranked("off")
        for name in ("theta_on_score", "w_rec"):
            with self.subTest(name):
                self.assertNotEqual(self.grid(name), off_g)
                self.assertNotEqual(self.ranked(name), off_r)

    def test_theta_leaves_rel_under_theta_on_score(self):
        def relrej(log):
            return sum(1 for _, rej in log for _, why in rej if why.startswith("relevance"))
        self.assertGreaterEqual(relrej(self.grid("off")), 1)
        self.assertEqual(relrej(self.grid("theta_on_score")), 0)


class E4FullIsUncut(CorpusCase):
    def test_rank_all_head_equals_grid_path(self):
        # 전제(«절단이 실제로 무언가를 잘랐다»)는 스위치 셋 합계로 건다 — THETA_ON_SCORE에서는
        # BM25 θ가 최종 점수에 걸려 모든 문항이 K개 이하로 준다(실측). 머리 동일성은 칸마다 본다.
        longer = 0
        for name in SWITCHES:
            with self.subTest(name):
                arm = EA.EngineArm(*EA.ARM_SPECS[1])
                arm.scorer, arm.theta = self.a1, self.th1
                self.switch(name)
                try:
                    EA.rank_all(arm, self.docs, self.env)
                    grid = self.log(EA.make_retrieve(self.a1, self.th1))
                finally:
                    for k in SWITCHES[name]:
                        setattr(M, k, self.saved[k])
                corpus, ledger, qs, scored, key_of = self.env
                for q, (hits, _) in zip(scored, grid):
                    full = arm.ranked[q["id"]]
                    self.assertEqual(full[:M.TOP_K], [s for _, s in hits])
                    longer += len(full) > M.TOP_K
        self.assertGreaterEqual(longer, 1)              # 절단이 실제로 무언가를 잘랐다


class E5Length(CorpusCase):
    def test_short_rel_list_raises(self):
        ext = M.ExtRel(lambda q, docs: [0.5] * (len(docs) - 1), 0.0)
        with self.assertRaises(ValueError):
            EA._RETRIEVE(self.m, CHAT, self.asks[0], self.last, ext=ext)


def old_run(cmd, stdin_text=None, timeout=120):
    """🔴 발화 확인용 — 편집 전 `_run`의 모양(도구가 없으면 `FileNotFoundError`가 샌다)."""
    p = subprocess.run(cmd, input=None, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=timeout)
    return p.returncode, p.stdout.decode("utf-8", "replace")


class E6Skip(unittest.TestCase):
    def arms(self):
        return [EA.EngineArm(*s) for s in EA.ARM_SPECS]

    def test_container_table_matches_specs(self):
        self.assertEqual(set(EA.CONTAINER_OF),
                         {a.key for a in self.arms() if a.needs_container})

    def test_no_containers_means_three_skips(self):
        orig = EA._run
        try:
            EA._run = lambda cmd, stdin_text=None, timeout=120: (1, "")
            ok_os, ok_pg, diag = EA.probe_containers()
        finally:
            EA._run = orig
        self.assertIs(EA._run, orig)
        self.assertEqual((ok_os, ok_pg), (False, False))
        arms = self.arms()
        # 🔄 w7engines — 컨테이너 팔이 A2·A3·C1에서 B3·C1·C2로 바뀌었다(사슬을 분석기 → 식 → 구현으로 다시 놓음)
        self.assertEqual(sorted(EA.mark_skips(arms, ok_os, ok_pg)), ["B3", "C1", "C2"])
        for a in arms:
            self.assertEqual(a.skipped is not None, a.needs_container, a.key)

    def test_one_container_skips_only_its_arms(self):
        arms = self.arms()
        self.assertEqual(EA.mark_skips(arms, True, False), ["B3"])
        arms = self.arms()
        self.assertEqual(sorted(EA.mark_skips(arms, False, True)), ["C1", "C2"])
        self.assertEqual(EA.mark_skips(self.arms(), True, True), [])

    def _probe_without_docker(self, run_fn):
        orig_sp, orig_run = subprocess.run, EA._run

        def boom(*a, **k):
            raise FileNotFoundError("docker")
        try:
            subprocess.run = boom
            EA._run = run_fn
            return EA.probe_containers()
        finally:
            subprocess.run, EA._run = orig_sp, orig_run

    def test_missing_docker_is_skip_not_crash(self):
        ok_os, ok_pg, diag = self._probe_without_docker(EA._run)
        self.assertEqual((ok_os, ok_pg), (False, False))

    def test_planted_old_run_crashes(self):
        with self.assertRaises(FileNotFoundError):
            self._probe_without_docker(old_run)


# ══════════════════════════════════════════════════════════════════════
# 🆕 w7engines — 실험 32의 새 부품 (컨테이너 없이 도는 것만)
# ══════════════════════════════════════════════════════════════════════
from fractions import Fraction  # noqa: E402
import summary_ablation as SA  # noqa: E402
import summary_prototype as SP  # noqa: E402
from scorer_eval import Holdout as SE_Holdout  # noqa: E402


class E7TieExpectation(unittest.TestCase):
    """V1 — 동점 묶음 안 무작위 순서의 기대값. 손으로 센 값과 같아야 한다."""

    def test_strictly_above_is_certain(self):
        rels = [0.9, 0.5, 0.5, 0.1]
        self.assertEqual(EA.hit_prob(rels, EA.tie_groups(rels), [0], 1), 1)

    def test_boundary_group_is_hypergeometric(self):
        # 상위 2: 0.9 한 자리 + 0.5 묶음(3행)에서 한 자리 → 근거 한 행이 묶음에 있으면 1/3
        rels = [0.9, 0.5, 0.5, 0.5, 0.1]
        g = EA.tie_groups(rels)
        self.assertEqual(EA.hit_prob(rels, g, [2], 2), Fraction(1, 3))
        # 근거 문자열이 묶음 안 두 행에 있으면 1 − C(1,1)/C(3,1) = 2/3
        self.assertEqual(EA.hit_prob(rels, g, [1, 3], 2), Fraction(2, 3))
        self.assertEqual(EA.hit_prob(rels, g, [4], 2), 0)                 # 경계 아래
        self.assertEqual(EA.hit_prob(rels, g, [], 2), 0)                  # 색인에 없는 근거

    def test_fewer_rows_than_k(self):
        self.assertEqual(EA.hit_prob([0.0, 0.0], EA.tie_groups([0.0, 0.0]), [1], 5), 1)

    def test_insertion_order_does_not_matter(self):
        # 🔴 조용한 쪽 대조 — 행 순서를 뒤집어도 기대값은 같다(삽입 순서로 깨는 규약이면 달라진다)
        rels = [0.5, 0.5, 0.5, 0.2]
        rev = rels[::-1]
        a = EA.v1_expected(rels, [[0]], ks=(1,))
        b = EA.v1_expected(rev, [[3]], ks=(1,))
        self.assertEqual(a, b)
        self.assertEqual(a[1][0], Fraction(1, 3))

    def test_boundary_tie_flag(self):
        self.assertTrue(EA.boundary_tie([0.9, 0.5, 0.5], 2))
        self.assertFalse(EA.boundary_tie([0.9, 0.8, 0.5], 2))


class E8Judge(unittest.TestCase):
    """판정 셋이 관측을 나눈다 — 힘 없음 · 검출 안 됨 · 방향."""

    def test_min_n(self):
        self.assertEqual(EA.min_n_for(0.05), 6)
        self.assertEqual(EA.MIN_N, 6)

    def test_weak_when_n_small(self):
        # 다섯 문항이 전부 한쪽이어도 p = 0.0625 — 방향을 말하면 안 된다
        v = EA.judge([1, 1, 1, 1, 1], [0, 0, 0, 0, 0])
        self.assertEqual(v[-1], EA.V_WEAK)

    def test_direction_when_six_agree(self):
        self.assertEqual(EA.judge([1] * 6, [0] * 6)[-1], EA.V_UP)
        self.assertEqual(EA.judge([0] * 6, [1] * 6)[-1], EA.V_DOWN)
        # 낮을수록 좋은 지표(오주입)는 부호가 반대다
        self.assertEqual(EA.judge([0] * 6, [3] * 6, better="low")[-1], EA.V_UP)

    def test_null_when_split(self):
        self.assertEqual(EA.judge([1, 1, 1, 0, 0, 0], [0, 0, 0, 1, 1, 1])[-1], EA.V_NULL)

    def test_ties_are_dropped(self):
        w, l, t, p, mp, v = EA.judge([1] * 6 + [0] * 4, [0] * 6 + [0] * 4)
        self.assertEqual((w, l, t), (6, 0, 4))
        self.assertEqual(v, EA.V_UP)


class E9PgArrayAndAnalyzer(unittest.TestCase):
    def test_parse_quotes_commas_escapes(self):
        raw = '{" 가",나비,", ","a\\"b","c\\\\d"}'
        self.assertEqual(EA.parse_pg_array(raw), [" 가", "나비", ", ", 'a"b', "c\\d"])
        self.assertEqual(EA.parse_pg_array("{}"), [])

    def test_pgbigm_reproduces_recorded_server_output(self):
        # 2026-09-11 `show_bigm('나비 얘기 나왔었잖아, 뭐였지?')`의 응답(서버 원문) — 구두점도 항이다
        server = {"기 ", "나비", "나왔", "뭐였", "비 ", "아,", "얘기", "었잖", "였지", "왔었", "잖아",
                  "지?", " 나", " 뭐", " 얘", ", ", "? "}
        self.assertEqual(set(EA.terms_pgbigm("나비 얘기 나왔었잖아, 뭐였지?")), server)

    def test_pgbigm_differs_from_current_analyzer(self):
        # 분석기 요인이 실제로 다른 항을 낸다(어미·공백) — 같으면 A0→B1 화살표가 공허하다
        t = "나비가 아팠던 날"
        self.assertNotEqual(set(EA.terms_pgbigm(t)), set(EA.terms_bigram(t)))


class E10Normalize(unittest.TestCase):
    def test_max_normalized(self):
        class S:
            def rels(self, q, docs):
                return [2.0, 1.0, 0.0]
        self.assertEqual(EA.MaxNormalized(S()).rels("q", [1, 2, 3]), [1.0, 0.5, 0.0])

    def test_all_zero_stays_zero(self):
        class S:
            def rels(self, q, docs):
                return [0.0, 0.0]
        self.assertEqual(EA.MaxNormalized(S()).rels("q", [1, 2]), [0.0, 0.0])


class E11FactorTable(unittest.TestCase):
    """요인 표·화살표·제목 규칙 — 남의 집행부를 부른다. 심으면 운다, 안 심으면 조용하다."""

    def arms(self):
        return [EA.EngineArm(*s) for s in EA.ARM_SPECS]

    def test_real_table_is_quiet(self):
        with EA.engine_factors():
            self.assertEqual(SA.FactorRule().audit(self.arms()), [])
            arms = self.arms()
            for a in arms:
                a.ran = True
            self.assertEqual(SA.ArrowRule().audit(arms, EA.ARROWS), [])
        self.assertIsNot(SA.Arm.FACTORS, EA.ENGINE_FACTORS)          # 되돌렸다

    def test_two_factor_arm_fires(self):
        arms = self.arms()
        b2 = next(a for a in arms if a.key == "B2")
        b2.anchor = "A0"                         # A0 ↔ B2는 분석기·식 두 요인
        with EA.engine_factors():
            bad = SA.FactorRule().audit(arms)
        self.assertGreaterEqual(sum("«B2»" in b for b in bad), 1)

    def test_non_chain_arrow_fires(self):
        arms = self.arms()
        for a in arms:
            a.ran = True
        with EA.engine_factors():
            bad = SA.ArrowRule().audit(arms, EA.ARROWS + (("A0", "C2"),))
        self.assertGreaterEqual(sum("A0↔C2" in b for b in bad), 1)

    def test_unran_arm_arrow_fires(self):
        arms = self.arms()
        for a in arms:
            a.ran = a.key != "B3"                # B3가 SKIP이면 B2→B3 화살표는 자격이 없다
        with EA.engine_factors():
            bad = SA.ArrowRule().audit(arms, EA.ARROWS)
        self.assertGreaterEqual(sum("B3" in b for b in bad), 1)

    def test_bare_column_title_fires(self):
        good = SP.Col("eval3·지프 s=1", "홀드아웃 23문항 · 근거 26", "색인 3000행", "V1 recall@5")
        bare = SP.Col("eval3·지프 s=1", "23", "색인 3000행", "V1 recall@5")
        self.assertEqual(SP.TitleRule().audit([good]), [])
        self.assertGreaterEqual(len(SP.TitleRule().audit([bare])), 1)

    def test_holdout_budget_fires(self):
        ho = SE_Holdout(("K03", "K04"), EA.HO_BUDGET_PER_COL)
        for w in EA.HO_OPENS:
            ho.open(w)
        self.assertEqual(ho.audit(), {})
        ho.open("V1 판정·다시")                   # 이름을 새로 지어도 예산은 못 피한다
        self.assertIn("**총 접근 예산 초과**", ho.audit())

    def test_order_signature(self):
        self.assertEqual(EA.order_signature([0.5, 0.9, 0.5]), [(1,), (0, 2)])
        self.assertNotEqual(EA.order_signature([0.5, 0.9, 0.5]), EA.order_signature([0.5, 0.9, 0.4]))


if __name__ == "__main__":
    unittest.main()

