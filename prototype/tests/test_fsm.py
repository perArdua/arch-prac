# -*- coding: utf-8 -*-
"""
test_fsm.py — 관계 상태 기계 (단계 2 · ADR-014).

두 축을 고정한다.

  ① **폴백** — `stage_machine`에 행이 없으면 `DEFAULT_MACHINE`.
     이 저장소에는 행이 하나도 없다(Q1: `seojun`을 시드하지 않는다). 즉
     `soak`·`gate_sweep`·모든 기존 DB가 타는 것이 이 분기다.
  ② **오버라이드** — 행이 있으면 그 기계를 쓴다.
     실사용 0건이므로 **이 테스트가 그 경로의 유일한 실행자**다.

나머지는 검증 규칙이 실제로 세 갈래로 갈라지는지만 확인한다.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fsm                                                 # noqa: E402
import memory                                              # noqa: E402
from memory import Memory                                  # noqa: E402


def rel(stage, affinity, locked=0):
    """`validate`가 읽는 것은 세 필드뿐이다 — dict로 충분하다."""
    return {"stage": stage, "affinity": affinity, "user_locked": locked}


class TestLoadMachine(unittest.TestCase):

    def test_no_row_falls_back_to_default(self):
        """① 실사용 경로. 행이 없으면 기본 기계 **그 객체**를 준다."""
        m = Memory(":memory:")
        self.assertEqual(
            m.db.execute("SELECT COUNT(*) FROM stage_machine").fetchone()[0], 0)
        machine = fsm.load_machine(m.db, "seojun", 1)
        self.assertIs(machine, fsm.DEFAULT_MACHINE)
        self.assertEqual(len(machine["stages"]), 8)

    def test_row_overrides_default(self):
        """② 오버라이드 — `친구→썸`을 금지한 기계를 넣으면 그 전이가 막힌다."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            m = Memory(path)
            m.db.execute(
                "INSERT INTO stage_machine VALUES (?,?,?,?,?)",
                ("seojun", 1,
                 json.dumps(["낯섦", "친구", "썸"]),
                 # 친구의 허용 목적지에서 **썸을 뺐다** — 기본 기계와 갈리는 지점
                 json.dumps({"낯섦": ["친구"], "친구": [], "썸": []}),
                 json.dumps({"낯섦": [0, 100], "친구": [0, 100],
                             "썸": [0, 100]})))
            m.db.commit()

            machine = fsm.load_machine(m.db, "seojun", 1)
            self.assertIsNot(machine, fsm.DEFAULT_MACHINE)
            self.assertEqual(machine["stages"], ("낯섦", "친구", "썸"))

            # 기본 기계에서는 통과하는 전이가 오버라이드에서는 거부된다
            ok, _, _ = fsm.validate(fsm.DEFAULT_MACHINE, rel("친구", 45),
                                    {"stage": "썸"})
            self.assertTrue(ok)
            ok, _, why = fsm.validate(machine, rel("친구", 45), {"stage": "썸"})
            self.assertFalse(ok)
            self.assertEqual(why, fsm.R_TRANSITION)

            # 다른 버전은 여전히 폴백이다 — 키는 (character_id, version)이다
            self.assertIs(fsm.load_machine(m.db, "seojun", 2),
                          fsm.DEFAULT_MACHINE)
            m.db.close()
        finally:
            os.remove(path)


class TestValidate(unittest.TestCase):
    """검증 규칙이 갈라지는 지점만 — 규칙 하나에 케이스 하나."""

    D = fsm.DEFAULT_MACHINE

    def test_legal_transition_passes(self):
        ok, new, why = fsm.validate(self.D, rel("친구", 45), {"stage": "썸"})
        self.assertTrue(ok)
        self.assertEqual(new["stage"], "썸")
        self.assertIsNone(why)

    def test_self_transition_always_allowed(self):
        ok, _, why = fsm.validate(self.D, rel("연인", 84), {"stage": "연인"})
        self.assertTrue(ok)
        self.assertIsNone(why)

    def test_illegal_transition_rejected(self):
        """`연인 → 낯섦` — 한 방에 관계를 리셋하던 경로."""
        ok, _, why = fsm.validate(self.D, rel("연인", 84), {"stage": "낯섦"})
        self.assertFalse(ok)
        self.assertEqual(why, fsm.R_TRANSITION)

    def test_unknown_stage_rejected(self):
        ok, _, why = fsm.validate(self.D, rel("연인", 84), {"stage": "사장님"})
        self.assertFalse(ok)
        self.assertEqual(why, fsm.R_STAGE_UNKNOWN)

    def test_stage_type_error_rejected(self):
        """`stage=123` — enum 검사 전에 타입에서 걸러야 한다."""
        ok, _, why = fsm.validate(self.D, rel("연인", 84), {"stage": 123})
        self.assertFalse(ok)
        self.assertEqual(why, fsm.R_STAGE_TYPE)

    def test_affinity_out_of_range_rejected(self):
        for bad in (999, -1):
            ok, _, why = fsm.validate(self.D, rel("연인", 84),
                                      {"affinity": bad})
            self.assertFalse(ok)
            self.assertEqual(why, fsm.R_AFFINITY_RANGE)

    def test_affinity_type_error_rejected(self):
        """`True`는 `int`의 인스턴스다 — 그래서 따로 막는다."""
        for bad in ("높음", 50.5, True):
            ok, _, why = fsm.validate(self.D, rel("연인", 84),
                                      {"affinity": bad})
            self.assertFalse(ok)
            self.assertEqual(why, fsm.R_AFFINITY_TYPE)

    def test_affinity_band_rejected(self):
        """범위 안이지만 그 stage의 밴드 밖 — *"연인인데 호감도 3"*."""
        ok, _, why = fsm.validate(self.D, rel("연인", 84), {"affinity": 3})
        self.assertFalse(ok)
        self.assertEqual(why, fsm.R_AFFINITY_BAND)

    # ── 밴드는 **결과 상태**의 불변식이다 (단계 2 검증자 지적) ──────────
    def test_stage_only_delta_out_of_band_rejected(self):
        """
        🔴 `연인/84 → 헤어짐`은 **합법 전이**지만 헤어짐 밴드 `(0,70)` 밖이다.

        고치기 전에는 통과했다. 그러면 `헤어짐/84`가 저장되고, 그 뒤로 84→82
        같은 정상적인 작은 변화가 전부 `affinity_band`로 거부된다 — 빠져나가는
        길이 `narrative_event` 플래그밖에 없는 상태에 **합법 전이가 행을
        가두는** 셈이었다. 20개 공격이 전부 affinity를 들고 있어서 아무도
        이 경로에 닿지 않았다.
        """
        ok, _, why = fsm.validate(self.D, rel("연인", 84), {"stage": "헤어짐"})
        self.assertFalse(ok)
        self.assertEqual(why, fsm.R_AFFINITY_BAND)

    def test_stage_only_delta_inside_band_still_passes(self):
        """반대 방향 회귀 방지 — 밴드 안이면 stage만 오는 델타도 그대로 통과한다."""
        ok, new, why = fsm.validate(self.D, rel("연인", 84), {"stage": "다툼중"})
        self.assertTrue(ok)
        self.assertEqual((new["stage"], new["affinity"]), ("다툼중", 84))
        self.assertIsNone(why)

    def test_out_of_band_transition_needs_the_declared_exception(self):
        """
        탈출 경로. 헤어짐으로 가려면 affinity를 밴드 안으로 함께 내려야 하고,
        84 → 68은 |Δ|=16 > 5이므로 **선언된 예외**가 있어야 한다. 즉 규칙은
        전이를 막는 것이 아니라 **감사 없이 지나가는 것**을 막는다.
        """
        d = {"stage": "헤어짐", "affinity": 68}
        ok, _, why = fsm.validate(self.D, rel("연인", 84), d)
        self.assertFalse(ok)
        self.assertEqual(why, fsm.R_AFFINITY_JUMP)

        ok, new, why = fsm.validate(self.D, rel("연인", 84), d,
                                    narrative_event=True)
        self.assertTrue(ok)
        self.assertEqual((new["stage"], new["affinity"]), ("헤어짐", 68))
        self.assertEqual(why, fsm.R_NARRATIVE)

    # ── 변화량 규칙 3분기 (F15) ────────────────────────────────────────
    def test_delta_within_step_passes(self):
        ok, new, why = fsm.validate(self.D, rel("연인", 84), {"affinity": 89})
        self.assertTrue(ok)
        self.assertEqual(new["affinity"], 89)
        self.assertIsNone(why)

    def test_big_delta_without_flag_rejected(self):
        ok, _, why = fsm.validate(self.D, rel("다툼중", 55), {"affinity": 95})
        self.assertFalse(ok)
        self.assertEqual(why, fsm.R_AFFINITY_JUMP)

    def test_big_delta_with_flag_is_audited_not_rejected(self):
        """**거부가 아니라 감사 기록**이다 — 통과하되 사유가 남는다."""
        ok, new, why = fsm.validate(self.D, rel("다툼중", 55),
                                    {"stage": "연인", "affinity": 84},
                                    narrative_event=True)
        self.assertTrue(ok)
        self.assertEqual((new["stage"], new["affinity"]), ("연인", 84))
        self.assertEqual(why, fsm.R_NARRATIVE)

    def test_user_locked_rejects_everything(self):
        """유저가 잠갔으면 **합법 전이도** 거부된다. 다른 검사보다 먼저다."""
        ok, _, why = fsm.validate(self.D, rel("친구", 45, locked=1),
                                  {"stage": "썸"})
        self.assertFalse(ok)
        self.assertEqual(why, fsm.R_LOCKED)


class TestApplyMetaIntegration(unittest.TestCase):
    """`apply_meta`가 검증기를 얹었는지 — 거부는 두 테이블에 모두 남는다."""

    CHAT = "chat-fsm"

    def setUp(self):
        self.m = Memory(":memory:")
        self.m.db.execute("INSERT INTO chat VALUES (?,?,?,?)",
                          (self.CHAT, "지우", "seojun", 1))
        self.m.db.execute("INSERT INTO relationship VALUES (?,?,?,?,?,?,?,?)",
                          (self.CHAT, "연인", None, 84, "안도", "지우", 0, 0))
        # 🔄 **단계 S3(I5)이 이 픽스처의 구멍을 드러냈다.**
        #
        # `_propagate_transition`의 `targets`가 v4까지는 하드코딩
        # `[("digest","lifetime"), ("digest","session")]`이라 **요약이 하나도
        # 없어도 두 키를 stale로 찍었다.** 그래서 아래 시험은 digest 행을
        # 하나도 안 만들고 «lifetime이 stale이 됐는가»를 물을 수 있었다.
        #
        # I5가 그것을 **실제 키 열거**로 바꿨다 — 있는 요약만 민다. 그러면
        # 이 픽스처에서는 밀 것이 0건이고, 시험이 묻던 것(«전이가 요약을
        # `전이:` 사유로 미는가»)이 **재료 없이는 물을 수 없는 질문**이 된다.
        # → 시험의 뜻을 지키기 위해 **재료를 준다.** 기대값을 낮추지 않는다.
        #
        # ⚠️ 없는 요약을 stale로 찍던 옛 동작이 «더 안전»했던 것이 아니다.
        #    그 유령 키는 `regenerate_stale`이 영원히 재생성에 실패하는 항목이
        #    되고(재료가 없으니 `rewrite_lifetime`이 터진다), 그 실패는
        #    「낡은 요약이 하나 있다」는 거짓 기록으로 남는다.
        for kind, content in (("lifetime", "인생 요약(합성)"),
                              ("session", "지난 세션 요약(합성)")):
            self.m.db.execute(
                "INSERT OR REPLACE INTO digest (chat_id, kind, content,"
                " covers_to_seq) VALUES (?,?,?,?)",
                (self.CHAT, kind, content, 0))
        self.m.db.commit()

    def rel_row(self):
        return self.m.db.execute("SELECT * FROM relationship WHERE chat_id=?",
                                 (self.CHAT,)).fetchone()

    def violations(self):
        return [(r["field"], r["reason"]) for r in self.m.db.execute(
            "SELECT field, reason FROM state_violation ORDER BY rowid")]

    def test_illegal_transition_blocked_and_logged_twice(self):
        self.m.apply_meta(self.CHAT, 5, {"state_delta": {"stage": "낯섦"}})
        self.assertEqual(self.rel_row()["stage"], "연인")
        self.assertEqual(self.violations(),
                         [("state_delta", fsm.R_TRANSITION)])
        # `provenance`의 `meta_rejected`도 그대로 남는다 (승격이지 이관이 아니다)
        n = self.m.db.execute(
            "SELECT COUNT(*) FROM provenance WHERE kind='meta_rejected'"
        ).fetchone()[0]
        self.assertEqual(n, 1)

    def test_narrative_exception_applies_and_audits(self):
        self.m.apply_meta(self.CHAT, 5, {"state_delta": {"stage": "다툼중",
                                                         "affinity": 55},
                                         "narrative_event": True})
        self.assertEqual(self.rel_row()["stage"], "다툼중")
        self.assertEqual(self.rel_row()["affinity"], 55)
        self.assertIn(("affinity", fsm.R_NARRATIVE), self.violations())

    def test_default_transition_stales_interpretation_not_digests(self):
        """
        🔄 wave3 — 기본값에서 전이는 해석만 민다. digest는 두 요약 프롬프트가 `stage`를
        안 싣기 때문에 밀지 않는다(`memory.py` 끝의 스위치). **심을 위반:** 스위치를
        `True`로 되돌리면 이 시험이, 해석 전파를 지우면 둘째 단언이 발화한다.
        """
        self.m.apply_meta(self.CHAT, 5, {"state_delta": {"stage": "다툼중",
                                                         "affinity": 80}})
        self.assertIsNone(self.m.stale_row(self.CHAT, "digest", "lifetime"))
        self.assertEqual(self.m.stale_row(self.CHAT, "interpretation", "*")[0],
                         "전이:연인→다툼중")

    def test_transition_stales_derivations_with_prefix(self):
        # 🔄 wave3 — **옛 전파 경로**(스위치 켬)의 시험이다. 지우지 않는다: 되돌리는
        #    날 이 경로가 살아 있어야 한다.
        saved = memory.TRANSITION_PROPAGATES_DIGEST
        memory.TRANSITION_PROPAGATES_DIGEST = True
        self.addCleanup(setattr, memory, "TRANSITION_PROPAGATES_DIGEST", saved)
        self.m.apply_meta(self.CHAT, 5, {"state_delta": {"stage": "다툼중",
                                                         "affinity": 80}})
        row = self.m.stale_row(self.CHAT, "digest", "lifetime")
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "전이:연인→다툼중")
        self.assertTrue(row[0].startswith("전이:"))
        # 단계 5가 읽을 경계 카운터가 이때 찍힌다 (비어 있을 때만)
        seqs = [r[0] for r in self.m.db.execute(
            "SELECT stale_since_seq FROM digest_meta WHERE chat_id=?",
            (self.CHAT,))]
        self.assertEqual(sorted(seqs), [5, 5])
        # 두 번째 전이는 그 값을 덮지 않는다 — 알고 싶은 것은 **첫** stale 시점이다
        self.m.apply_meta(self.CHAT, 9, {"state_delta": {"stage": "연인",
                                                         "affinity": 84},
                                         "narrative_event": True})
        seqs = [r[0] for r in self.m.db.execute(
            "SELECT stale_since_seq FROM digest_meta WHERE chat_id=?",
            (self.CHAT,))]
        self.assertEqual(sorted(seqs), [5, 5])

    def test_transition_does_not_stale_summaries_that_do_not_exist(self):
        """
        🆕 **단계 S3(I5)이 세운 새 계약을 여기서도 못박는다.**

        위 시험이 재료를 받게 되면서, *"재료가 없으면 어떻게 되는가"*는 아무도
        안 묻는 질문이 됐다. 픽스처를 고치면서 그 자리를 비워 두면 **옛 동작으로
        되돌아가도 아무 시험도 안 깨진다** — 그래서 여기 한 줄로 남긴다.
        """
        self.m.db.execute("DELETE FROM digest WHERE chat_id=?", (self.CHAT,))
        self.m.db.commit()
        self.m.apply_meta(self.CHAT, 5, {"state_delta": {"stage": "다툼중",
                                                         "affinity": 80}})
        self.assertIsNone(self.m.stale_row(self.CHAT, "digest", "lifetime"))
        n = self.m.db.execute(
            "SELECT COUNT(*) FROM digest_meta WHERE chat_id=?",
            (self.CHAT,)).fetchone()[0]
        self.assertEqual(n, 0)

    def test_no_relationship_row_is_a_noop(self):
        self.m.db.execute("DELETE FROM relationship WHERE chat_id=?",
                          (self.CHAT,))
        self.m.db.commit()
        self.m.apply_meta(self.CHAT, 5, {"state_delta": {"stage": "다툼중"}})
        self.assertEqual(self.violations(), [])
        items = [r[0] for r in self.m.db.execute(
            "SELECT reason FROM provenance WHERE kind='meta_rejected'")]
        self.assertEqual(items, ["관계 행 없음 — 검증 불가"])


if __name__ == "__main__":
    unittest.main()
