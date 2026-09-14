# -*- coding: utf-8 -*-
"""
test_eval3_probe.py — `eval3/`(규모 코퍼스)와 `eval3_probe.py`의 **결정적인 부분**을 시험한다.

지연 값·조건의 참/거짓은 시험하지 않는다 — 지연은 기계의 함수이고, 조건의 값은 **관측**이라
시험이 그것을 고정하면 사전 등록이 사후 고정이 된다. 여기서 지키는 것은:
  · 재생성이 바이트 동일하고 디스크와 같다 (G11)
  · 사전 등록 상수가 파일에서 참이다 (규모 · 문항 · 방해물 · 술어 · 골격 공유)
  · 엔진 조건의 정의가 docs/17 §9의 기록값(eval 3/18)을 재현한다 — 정의가 갈라지면 여기서 운다
  · 생성기의 검사들이 **위반을 심으면 실제로 발화한다** (각각 조용한 쪽과 짝으로)
"""
import copy
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(ROOT / "eval3"))

import eval3_probe as E                                         # noqa: E402
import gen_corpus3 as G3                                        # noqa: E402
import memory as M                                              # noqa: E402

_CACHE = {}


def rendered():
    if "out" not in _CACHE:
        _CACHE["out"] = G3.render_all()
    return _CACHE["out"]


class RegenerationTest(unittest.TestCase):
    def test_two_renders_are_byte_identical(self):
        a, _ = G3.render_all()
        b, _ = rendered()
        self.assertEqual(a, b)

    def test_disk_matches_generator(self):
        self.assertEqual(E.regen_mismatch(), [])

    def test_mismatch_is_reported(self):
        # 🔴 심은 위반: 디스크 사본 하나를 한 바이트 바꾸면 그 파일이 목록에 나와야 한다
        out, _ = rendered()
        tmp = tempfile.mkdtemp(prefix="eval3_t_")
        try:
            for k, v in out.items():
                p = Path(tmp) / k
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(v)
            self.assertEqual(E.regen_mismatch(tmp), [])              # 조용한 쪽
            q = Path(tmp) / "questions.yaml"
            q.write_bytes(q.read_bytes() + b"# EVAL3_T_PLANT\n")
            self.assertEqual(E.regen_mismatch(tmp), ["questions.yaml"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class PreregistrationTest(unittest.TestCase):
    def setUp(self):
        self.lg = {n: E.load(n)[1] for n in E.E3}
        self.qs = E.load(E.E3[0])[2]

    def test_counts(self):
        for n, lg in self.lg.items():
            self.assertEqual((len(lg["facts"]), len(lg["events"])),
                             (G3.N_FACTS_TOTAL, G3.N_EVENTS_TOTAL), n)
        self.assertEqual(G3.N_FACTS_TOTAL + G3.N_EVENTS_TOTAL - G3.N_SUPERSEDED_IN_TABLE, G3.N_ALIVE)
        self.assertEqual(len(self.qs), G3.N_QUESTIONS)
        self.assertEqual(sum(1 for q in self.qs if q.get("evidence")), G3.N_SCORED)

    def test_regimes_share_everything_but_slot_values(self):
        def skel(lg):
            return [(x["id"], x["at"]["session"], x["at"]["turn"], x.get("predicate"),
                     x.get("importance"), x.get("emotional_weight")) for x in lg["facts"] + lg["events"]]
        base = next(iter(self.lg.values()))
        core_ids = {x["id"] for x in base["facts"] + base["events"] if x["tests"] != ["bulk"]}
        for lg in self.lg.values():
            self.assertEqual(skel(lg), skel(base))
            core = {x["id"]: x for x in lg["facts"] + lg["events"] if x["id"] in core_ids}
            ref = {x["id"]: x for x in base["facts"] + base["events"] if x["id"] in core_ids}
            self.assertEqual(core, ref)                     # 핵심 층은 글자 그대로 같다

    def test_distractors_and_clusters(self):
        core = yaml.safe_load((ROOT / "eval3" / "fact-ledger.yaml").read_text(encoding="utf-8"))
        d = E.cluster_design(core)
        self.assertEqual(len(d), len(G3.CLUSTER_KEYS))
        self.assertTrue(all(len(v["distractor"]) >= G3.MIN_DISTRACTORS_PER_CLUSTER for v in d.values()))
        n = sum(1 for x in core["facts"] + core["events"] if x.get("lexical_role") == "distractor")
        self.assertEqual(n, G3.N_DISTRACTORS)

    def test_predicates_in_and_out_of_table(self):
        preds = {f["predicate"] for lg in self.lg.values() for f in lg["facts"]}
        inn = {p for p in preds if p in M.Memory.PREDICATE_CARDINALITY}
        self.assertEqual((len(inn), len(preds - inn)), (G3.PRED_IN, G3.PRED_OUT))

    def test_no_prototype_dir_is_written(self):
        # `corpus2_probe.build`는 prototype/ 아래에 DB를 만든다 — 이 프로브는 그 함수를 안 쓴다
        self.assertNotIn("C2.build(", (HERE / "eval3_probe.py").read_text(encoding="utf-8"))


class EngineConditionTest(unittest.TestCase):
    def test_movable_definition(self):
        df = {"가나": 1, "나다": 1, "다라": 5}
        self.assertEqual(E.movable(["가나다"], df)["movable"], 0)     # 겹침 둘 · df 같음 → 상수배
        self.assertEqual(E.movable(["가나다라"], df)["movable"], 1)   # df 1과 5 → 움직일 수 있다
        self.assertEqual(E.movable(["다라"], df)["movable"], 0)       # 겹침 하나
        self.assertEqual(E.movable(["마바"], df)["overlap_q"], 0)

    def test_verdict(self):
        k = G3.ENGINE_K
        self.assertEqual(E.engine_verdict({"a": k - 1, "b": 0}), (False, []))
        self.assertEqual(E.engine_verdict({"a": k - 1, "b": k}), (True, ["b"]))

    def test_calibration_reproduces_docs17_on_eval(self):
        tmp = tempfile.mkdtemp(prefix="eval3_t_")
        try:
            c, l, q = E.load("eval")
            m = E.build(tmp, "eval", c, l)
            rows = E.C2.index_rows(m)
            m.db.close()
            scored, _ = E.P.partition(q, E.P.key_index(l))
            df = E.df_of([r["summary"] for r in rows])
            mv = E.movable([x["ask"] for x in scored], df)
            self.assertEqual((len(rows), len(df), mv["movable"], len(scored)),
                             (E.CALIBRATION["rows"], E.CALIBRATION["terms"],
                              E.CALIBRATION["movable"], E.CALIBRATION["scored"]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_subsample_full_equals_movable(self):
        summ = ["지우가 나비랑 놀았음", "서준이 나비 밥 줌", "지우 회사 야근", "나비 병원 감"]
        asks = ["나비 병원 갔었나", "지우 회사 어때"]
        full = E.subsample_movable(summ, asks, ns=(4,), draws=3)
        self.assertEqual(full[4][1], E.movable(asks, E.df_of(summ))["movable"])


class ThetaIdentityTest(unittest.TestCase):
    def test_short_questions_cannot_break_the_property(self):
        # |Q| ≤ 20이면 0이 아닌 rel은 전부 ≥ 0.05 — 산수
        q = "가나다라마바사아자차카타파하거너더러머버터"               # 21자 → bigram 20 (끝 `터`는 어미표에 없다)
        self.assertEqual(len(set(M.bigrams(q))), 20)
        self.assertEqual(E.long_questions([q]), [])
        self.assertGreaterEqual(M.coverage(set(M.bigrams(q)), {"가나"}), M.THETA_RELEVANCE)

    def test_long_question_is_flagged_and_can_be_cut(self):
        # 🔴 심은 위반: |Q| = 21이면 겹침 1개의 rel = 1/21 < 0.05 — θ가 0이 아닌 값을 자른다
        q = "가나다라마바사아자차카타파하거너더러머버서터"
        self.assertEqual(len(set(M.bigrams(q))), 21)
        self.assertEqual(E.long_questions([q]), [q])
        self.assertLess(M.coverage(set(M.bigrams(q)), {"가나"}), M.THETA_RELEVANCE)


class GeneratorChecksFireTest(unittest.TestCase):
    """생성기의 검사를 **위반을 심어** 부른다 — 각 검사에 조용한 쪽이 짝으로 있다."""

    def setUp(self):
        self.facts, self.events = G3.core_facts(), G3.core_events()

    def test_check_core_quiet_then_fires(self):
        G3.check_core(self.facts, self.events)                       # 조용한 쪽
        f = copy.deepcopy(self.facts)
        f[0]["lexical_role"] = None                                   # F001(나비·고양이 표적) 표지 제거
        with self.assertRaises(AssertionError):
            G3.check_core(f, self.events)

    def test_check_keys_fires_on_cluster_key_in_bulk(self):
        bulk = [{"id": "V9999", "text": "지우가 공원에서 두부 먹음"}]
        with self.assertRaisesRegex(AssertionError, "군집 키"):
            G3.check_keys(bulk, set(), [])
        G3.check_keys([{"id": "V9999", "text": "지우가 공원에서 떡국 먹음"}], set(), [])   # 조용한 쪽

    def test_check_keys_fires_on_abstention_topic(self):
        with self.assertRaisesRegex(AssertionError, "기권 화제"):
            G3.check_keys([], set(), ["지우가 수영 강습 등록함"])

    def test_check_positions_fires_on_dropped_item(self):
        _, corpora = rendered()
        name = G3.REGIMES[0][0]
        lg = yaml.safe_load((ROOT / "eval3" / "regimes" / name / "fact-ledger.yaml")
                            .read_text(encoding="utf-8"))
        corpus = corpora[name]
        G3.check_positions(lg, corpus)                                # 조용한 쪽
        bad = [dict(r) for r in corpus]
        victim = next(r for r in bad if r["planted_id"])
        victim["planted_id"] = None                                   # generate가 조용히 버린 모양
        with self.assertRaisesRegex(AssertionError, "배치 불일치"):
            G3.check_positions(lg, bad)

    def test_pick_is_one_draw_per_slot(self):
        pool = ["a", "b", "c", "d"]
        self.assertEqual([G3.pick(pool, 0.0, u) for u in (0.0, 0.26, 0.51, 0.99)], pool)
        self.assertEqual(G3.pick(pool, 2.0, 0.5), "a")                # 1위 몫 1/1.4236 ≈ 0.70
        self.assertNotEqual(G3.pick(pool, 2.0, 0.1, exclude="a"), "a")


if __name__ == "__main__":
    unittest.main()
