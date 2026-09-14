# -*- coding: utf-8 -*-
"""
test_deletion.py — 유저가 지운 것이 **검색과 게이트에서 함께 빠지는가.**

[ADR-011](../docs/adr/ADR-011-derivation-propagation.md)의 결정표는 파생물을 둘로
가른다: `digest`·`interpretation`은 **stale 표시**(재생성해야 의미가 산다),
**검색 색인(event 복사본)은 `user_deleted=1`로 즉시 제외**(재생성할 게 없다).

그 결정은 `_invalidate_derived`(사실이 **바뀌는** 경로)에만 배선돼 있었고,
**유저가 부르는 `delete_item`에는 없었다.** 그래서 이 저장소는
«바꾸면 빠지고, 지우면 남는다»는 상태였다 — 개인정보 삭제 주장에 직결된다.

  A1  삭제 → `event` 색인 복사본이 `user_deleted=1`  → `retrieve`·`gate`에서 빠진다
  A2  게이트 어휘가 **자기 대화방만** 본다 (`_recall_vocab`의 chat_id 무필터)
  O1  삭제 **전에 데운** 검색·어휘·게이트도 삭제 뒤엔 지운 것을 안 낸다 (w11b · 방 단위 캐시 변이)

## 🔴 이 파일이 지키는 대칭

시끄러운 쪽(지운 것이 빠지는가)만 걸면 **전부 빼 버리는 회귀가 통과한다.**
그래서 모든 삭제 시험에 「조용한 쪽」 짝을 둔다 — **안 지운 사실은 여전히
검색되고 게이트를 발화시켜야 한다.** 과잉 제거는 누수와 같은 크기의 결함이다.

DB는 전부 `tempfile`(= `%TEMP%`) 아래에 만든다 (가드레일).
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from memory import Memory                                   # noqa: E402

CHAT = "c-del"
OTHER = "c-del-other"

# ── 고정물 ──────────────────────────────────────────────────────────────
#
# 두 요약의 **앞 2글자 집합이 `지우` 말고는 안 겹치게** 고른다. 겹치면
# 「조용한 쪽」이 시끄러운 쪽 어휘로 발화해서 대조가 무의미해진다.
#   지운 쪽  : 지우 마케 회사 대리 일한
#   조용한 쪽: 지우 고양 나비 키운
S_DELETED = "지우는 마케팅 회사 대리로 일한다"
S_QUIET = "지우가 고양이 나비를 키운다"
S_OTHER = "민수는 부산에서 낚시를 한다"          # 다른 대화방 (A2)

Q_DELETED = "마케팅 회사 대리"
Q_QUIET = "고양이 나비"

# 게이트 프로브 — **과거 참조 정규식에 안 걸리고 8글자 이상**이어야 어휘 접점
# 분기까지 내려간다. 앞 2글자가 해당 요약에만 있는 낱말을 쓴다.
G_DELETED = "마케팅 쪽 일은 요즘 어떨까"        # 마케 → 지운 쪽에만
G_QUIET = "나비 밥은 잘 챙겨주고 있나"          # 나비 → 조용한 쪽에만
G_OTHER = "낚시 채비는 다 챙겨뒀나"             # 낚시 → 다른 대화방에만


def seed(m, chat_id):
    """`retrieve`·`gate`가 도는 최소 상태."""
    m.db.execute("INSERT OR IGNORE INTO character_version (character_id,"
                 " version, persona_text, speech_rules, taboos)"
                 " VALUES (?,?,?,?,?)", ("seojun", 1, "페르소나", "반말", ""))
    m.db.execute("INSERT INTO chat (chat_id, user_id, character_id,"
                 " character_version) VALUES (?,?,?,?)",
                 (chat_id, "jiwoo", "seojun", 1))
    m.db.commit()


def plant(m, chat_id, subject, predicate, obj, summary, seq):
    """
    사실 하나 + 그 **색인 복사본**(event) + 둘을 잇는 `derivation`.

    소크 하니스가 하는 것과 같은 모양이다 — `retrieve()`는 `event`만 보므로
    사실이 검색되려면 요약이 색인에 복사돼야 하고(`soak.py`의 «대장 facts ->
    upsert_fact + event 색인»), 그 복사본이 바로 삭제가 따라가야 할 파생물이다.
    """
    m.upsert_fact(chat_id, subject, predicate, obj, seq=seq, importance=0.8)
    fid = m.db.execute(
        "SELECT fact_id FROM fact WHERE chat_id=? AND predicate=? AND object=?",
        (chat_id, predicate, obj)).fetchone()["fact_id"]
    _, ev = m.add_event(chat_id, summary, seq,
                        emotional_weight=0.5, importance=0.8)
    m.record_derivation(chat_id, "event", str(ev), [("fact", fid)])
    return fid, ev


class DeletionIndexTest(unittest.TestCase):
    """A1 — 지운 사실의 색인 문장이 검색과 게이트에서 함께 빠지는가."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="del-")
        self.m = Memory(os.path.join(self.tmp, "t.db"))
        seed(self.m, CHAT)
        self.fid, self.ev = plant(
            self.m, CHAT, "지우", "직업", "마케팅 회사 대리", S_DELETED, 1)
        self.q_fid, self.q_ev = plant(
            self.m, CHAT, "지우", "반려동물", "고양이 나비", S_QUIET, 2)

    def tearDown(self):
        self.m.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── 도우미 ─────────────────────────────────────────────────────────
    def _hits(self, query):
        scored, _ = self.m.retrieve(CHAT, query, now_seq=10)
        return [r["summary"] for _, r in scored]

    def _flag(self, event_id):
        return self.m.db.execute(
            "SELECT user_deleted FROM event WHERE event_id=?",
            (event_id,)).fetchone()["user_deleted"]

    # ── 착수 상태 — 심은 것이 실제로 검색·발화된다 ──────────────────────
    def test_before_deletion_both_sides_are_live(self):
        """대조의 바닥. 이것이 빨가면 위 두 시험은 **아무것도 안 잰다.**"""
        self.assertIn(S_DELETED, self._hits(Q_DELETED))
        self.assertIn(S_QUIET, self._hits(Q_QUIET))
        self.assertTrue(self.m.gate(G_DELETED, CHAT)[0])
        self.assertTrue(self.m.gate(G_QUIET, CHAT)[0])

    # ── 🔴 시끄러운 쪽 ─────────────────────────────────────────────────
    def test_delete_clears_index_copy_flag(self):
        """
        `delete_item`이 **event 파생물을 즉시 제외**한다 (ADR-011 결정표).

        **심을 위반:** `delete_item`의 `derived_kind == "event"` 분기를 지우면
        (= 옛 구현) 여기가 발화한다.
        """
        self.m.delete_item(CHAT, "fact", self.fid)
        self.assertEqual(self._flag(self.ev), 1,
                         "지운 사실의 색인 복사본이 user_deleted=0으로 남아 있다")

    def test_delete_removes_from_retrieval(self):
        """지운 사실의 색인 문장이 **검색되지 않는다.**"""
        self.m.delete_item(CHAT, "fact", self.fid)
        self.assertNotIn(S_DELETED, self._hits(Q_DELETED),
                         "삭제 후에도 지운 사실이 검색된다 (색인 누수)")

    def test_delete_removes_from_gate_vocab(self):
        """
        🔴 **게이트까지 빠져야 절반이 아니다.** 검색만 막고 어휘가 남으면
        그 낱말은 계속 검색을 부르고, 부른 자리에서 «아무것도 못 찾음»이 된다.
        """
        self.m.delete_item(CHAT, "fact", self.fid)
        self.assertNotIn("마케", self.m._recall_vocab_for(CHAT))
        self.assertFalse(self.m.gate(G_DELETED, CHAT)[0],
                         "지운 사실의 낱말로 게이트가 계속 발화한다")

    # ── 🔴 조용한 쪽 — 과잉 제거가 아니라는 대조 ────────────────────────
    def test_untouched_fact_still_retrieved(self):
        """안 지운 사실은 **여전히 검색된다.** 전부 빼는 회귀를 여기서 잡는다."""
        self.m.delete_item(CHAT, "fact", self.fid)
        self.assertEqual(self._flag(self.q_ev), 0)
        self.assertIn(S_QUIET, self._hits(Q_QUIET))

    def test_untouched_fact_still_fires_gate(self):
        """안 지운 사실의 낱말은 **여전히 게이트를 발화시킨다.**"""
        self.m.delete_item(CHAT, "fact", self.fid)
        self.assertIn("나비", self.m._recall_vocab_for(CHAT))
        self.assertTrue(self.m.gate(G_QUIET, CHAT)[0])

    # ── 갱신 경로와 같은 결과인가 ──────────────────────────────────────
    def test_update_and_delete_agree(self):
        """
        ⭐ ADR-011 §핵심 — *"삭제와 갱신은 같은 일이다."*

        `upsert_fact`의 supersede(갱신)와 `delete_item`(삭제)이 색인 복사본에
        **같은 처분**을 내리는가. 이 시험이 A1의 결함을 한 줄로 말한다:
        갱신은 오늘도 빼고 있었고 삭제만 안 빼고 있었다.

        ⚠️ **처음 쓴 판이 «발화할 수 없는 검사»였다.** 갱신 짝에 `반려동물`을
           썼는데 그 술어는 `PREDICATE_CARDINALITY`에 없어 기본값 `many`,
           즉 supersede가 아니라 **병존**으로 끝났다. 그래서 두 값이 `0 == 0`으로
           같아지고 결함이 있는 채로 초록이었다. 지금은 ⓐ 단일값 + high 가변성
           술어(`거주지`)를 쓰고 ⓑ **`act == "superseded"`를 먼저 걸고**
           ⓒ 같음이 아니라 **`(1, 1)`이라는 값**을 못박는다 — 셋 중 하나만 빠져도
           이 시험은 다시 아무것도 안 잰다.
        """
        _, u_ev = plant(self.m, CHAT, "지우", "거주지", "성수동",
                        "지우는 성수동 원룸에 산다", 3)
        act, _ = self.m.upsert_fact(CHAT, "지우", "거주지", "망원동",
                                    seq=4, importance=0.8)
        self.assertEqual(act, "superseded",
                         "갱신 경로가 안 돌면 아래 대조는 아무것도 안 잰다")
        updated = self._flag(u_ev)               # 갱신 경로가 뺀 값
        self.m.delete_item(CHAT, "fact", self.fid)
        deleted = self._flag(self.ev)            # 삭제 경로가 뺀 값
        self.assertEqual((updated, deleted), (1, 1),
                         f"갱신은 {updated}, 삭제는 {deleted} — 같은 일에 다른 처분")

    # ── 설계 판단의 대가를 감시하는 자리 ────────────────────────────────
    def test_index_copies_never_land_in_stale(self):
        """
        🔴 **`retrieve()`가 `stale`을 보지 않기로 한 결정의 대가를 여기서 문다.**

        이중 방어(읽기 경로가 `stale`도 보게 하기)를 **안 골랐다** — `stale`은
        «재생성 대기»이지 «삭제»가 아니라서, 그렇게 하면 재생성이 늦은 요약이
        조용히 검색에서 빠진다. `stale_row`의 주석이 정본이다: 같은 bool,
        다른 처분.

        그 대신 **쓰는 쪽에 불변식**을 건다. 색인 복사본(`event`)이 `stale`에
        들어가는 순간이 곧 누수가 다시 열린 순간이므로, 그때 **서빙이 아니라
        이 시험이** 빨개진다.

        **심을 위반:** `_invalidate_derived`의 `derived_kind == "event"` 분기를
        지우면(= 옛 `delete_item`) 발화한다.
        """
        self.m.delete_item(CHAT, "fact", self.fid)
        rows = self.m.db.execute(
            "SELECT derived_kind, derived_key, reason FROM stale"
            " WHERE derived_kind='event'").fetchall()
        self.assertEqual([tuple(r) for r in rows], [],
                         "event 색인 복사본이 stale에 들어갔다 — 읽기 경로는 "
                         "stale을 보지 않으므로 이것은 곧 누수다")

    # ── 🔴 데운 뒤 삭제 (O1) ────────────────────────────────────────────
    def test_delete_after_warm_still_leaves_everything(self):
        """
        🔴 **삭제 전에 검색·어휘·게이트를 먼저 부른다.** 위 시험들은 삭제 **뒤에만** 불러서,
        그 사이에 무엇이든 기억하는 층(방 단위 어휘 캐시 같은 것)이 끼어도 채워질 틈이 없었다 —
        w8code가 그 변이를 심었을 때 이 파일은 12/12 초록이었다(관찰 O1 · `test_retrieve_memo.py` R7이
        대신 지켰다). 여기서는 실제 대화 순서대로 **데우고 → 지우고 → 다시 묻는다.**

        데우는 호출이 곧 대조의 바닥이다 — 삭제 전 네 갈래(검색 둘 · 방 어휘 · 전량 어휘 · 게이트 둘)가
        전부 살아 있어야 뒤의 «빠졌다»가 무엇을 잰다.

        **심을 위반 (`%TEMP%` 사본):** `_recall_vocab_for`가 방마다 집합을 기억하고 삭제에 무효화하지
        않게 하면 발화한다. 조용한 쪽: 같은 캐시를 `delete_item`이 비우게 하면 초록이다 — 이 칸은
        «캐시가 있다»가 아니라 **«삭제가 캐시를 지나 보이지 않는다»**를 문다.
        """
        # 데운다 — 삭제 전에는 전부 산다
        self.assertIn(S_DELETED, self._hits(Q_DELETED))
        self.assertIn(S_QUIET, self._hits(Q_QUIET))
        self.assertIn("마케", self.m._recall_vocab_for(CHAT))
        self.assertIn("마케", self.m._recall_vocab)
        self.assertTrue(self.m.gate(G_DELETED, CHAT)[0])
        self.assertTrue(self.m.gate(G_QUIET, CHAT)[0])

        self.m.delete_item(CHAT, "fact", self.fid)

        # 시끄러운 쪽 — 데운 것이 삭제를 가리지 않는다
        self.assertNotIn(S_DELETED, self._hits(Q_DELETED),
                         "데운 뒤 삭제 — 지운 사실이 여전히 검색된다")
        self.assertNotIn("마케", self.m._recall_vocab_for(CHAT),
                         "데운 뒤 삭제 — 방 어휘에 지운 낱말이 남았다")
        self.assertNotIn("마케", self.m._recall_vocab,
                         "데운 뒤 삭제 — 전량 어휘에 지운 낱말이 남았다")
        self.assertFalse(self.m.gate(G_DELETED, CHAT)[0],
                         "데운 뒤 삭제 — 지운 사실의 낱말로 게이트가 계속 발화한다")
        # 조용한 쪽 — 안 지운 사실은 데운 뒤에도 그대로다
        self.assertIn(S_QUIET, self._hits(Q_QUIET))
        self.assertIn("나비", self.m._recall_vocab_for(CHAT))
        self.assertTrue(self.m.gate(G_QUIET, CHAT)[0])


class GateVocabScopeTest(unittest.TestCase):
    """A2 — 게이트 어휘가 **자기 대화방만** 보는가."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="del-")
        self.m = Memory(os.path.join(self.tmp, "t.db"))
        seed(self.m, CHAT)
        seed(self.m, OTHER)
        plant(self.m, CHAT, "지우", "반려동물", "고양이 나비", S_QUIET, 1)
        plant(self.m, OTHER, "민수", "취미", "낚시", S_OTHER, 1)

    def tearDown(self):
        self.m.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_vocab_is_chat_scoped(self):
        """
        **심을 위반:** `_recall_vocab_for`의 `WHERE chat_id=?`를 지우면 발화한다.
        """
        self.assertIn("나비", self.m._recall_vocab_for(CHAT))
        self.assertNotIn("낚시", self.m._recall_vocab_for(CHAT),
                         "다른 대화방의 어휘가 이 방의 게이트를 발화시킨다")
        self.assertIn("낚시", self.m._recall_vocab_for(OTHER))
        self.assertNotIn("고양", self.m._recall_vocab_for(OTHER))

    def test_gate_does_not_fire_on_other_chat_vocab(self):
        """조용한 쪽 짝 — 자기 방 어휘로는 **여전히 발화한다.**"""
        self.assertFalse(self.m.gate(G_OTHER, CHAT)[0])
        self.assertTrue(self.m.gate(G_OTHER, OTHER)[0])
        self.assertTrue(self.m.gate(G_QUIET, CHAT)[0])
        self.assertFalse(self.m.gate(G_QUIET, OTHER)[0])

    def test_sweep_and_production_agree_on_vocab(self):
        """
        🔴 **스윕의 G3와 프로덕션 게이트가 같은 어휘를 본다** (F12/F21).

        `gate_sweep.build_vocab`은 chat_id로 자르고 `user_deleted`를 안 봤다.
        `_recall_vocab`은 반대였다 — **두 축이 정확히 엇갈려 있었다.** 같은
        이름의 «G3 현행»이 두 파일에서 다른 집합을 뜻하면 스윕의 판정은
        프로덕션의 판정이 아니다.

        ⚠️ **이 시험이 무엇을 못 잡는지 먼저 적는다.** `build_vocab`은 이제
           `_recall_vocab_for`에 **위임**하므로, 그 함수 안을 어떻게 망가뜨려도
           양쪽이 함께 틀려서 여기는 초록으로 남는다. 이 시험이 지키는 것은
           «두 정의가 맞는가»가 아니라 **«두 정의가 하나인가»**다.

        **심을 위반:** `build_vocab`을 옛 지역 SQL 사본(`WHERE chat_id=?`만)으로
        되돌리면 발화한다 — 그것이 이 시험이 막는 유일하고 정확한 회귀다.
        """
        import gate_sweep
        fid = self.m.db.execute(
            "SELECT fact_id FROM fact WHERE chat_id=? AND object=?",
            (CHAT, "고양이 나비")).fetchone()["fact_id"]
        self.m.delete_item(CHAT, "fact", fid)
        # `build_vocab`은 모듈 상수 `CHAT`(소크 방)을 읽으므로 방을 인자로 받는
        # 형태로 통일된 뒤에만 이 대조가 성립한다.
        self.assertEqual(gate_sweep.build_vocab(self.m, CHAT),
                         self.m._recall_vocab_for(CHAT))
        self.assertEqual(gate_sweep.build_vocab(self.m, OTHER),
                         self.m._recall_vocab_for(OTHER))


class TransitionAfterDeletionTest(unittest.TestCase):
    """
    🔴 wave3 T3 — **삭제 → 전이 → 지운 사실은 여전히 안 나온다.** (ADR-016 U12의 회귀 시험)

    wave2가 고친 것: `_propagate_transition`의 `INSERT OR REPLACE`가 `fact:N 삭제됨`을
    `전이:…`로 덮어, 서빙 정책이 지운 사실의 요약을 **경고와 함께 다시 내보냈다** — 바로
    앞 파도(A1)가 닫은 누수를 전이가 되돌리고 있었다. 그 수리를 끝-끝 한 시험으로 못박는다:
    진짜 `delete_item` → 진짜 `apply_meta`(단계 전이) → 진짜 `build_context`에서 지운 사실의
    문장이 **어느 블록에도** 없어야 한다.

    전이 스위치(`memory.TRANSITION_PROPAGATES_DIGEST`) **두 값 모두**에서 돈다. 끔(기본)은
    전이가 요약을 안 건드려서 안전하고, 켬은 upsert의 가드가 지켜서 안전하다 — 한쪽만
    걸면 되돌리는 날 가드 없는 경로가 조용히 열린다.

    조용한 쪽: 안 지운 사실로 만든 lifetime은 전이 뒤에도 **나온다.** 전부 빼는 회귀는
    누수와 같은 크기의 결함이다(이 파일 머리의 대칭).

    **심을 위반 (python -B):**
      ⓐ 가드를 옛 `INSERT OR REPLACE INTO stale VALUES (?,?,?,?,?)`로 되돌린다 → «켬» 발화
      ⓑ 전이가 digest stale을 비우게 한다(`_propagate_transition` 첫 줄에 DELETE) → 둘 다 발화
      ⓒ 조용한 쪽 — `STALE_SERVE_POLICY`를 `"exclude_all"`로 → «켬»의 lifetime이 빠져 발화
    """

    SECRET = S_DELETED

    def _run(self, switch):
        import memory
        tmp = tempfile.mkdtemp(prefix="del-tr-")
        saved = memory.TRANSITION_PROPAGATES_DIGEST
        memory.TRANSITION_PROPAGATES_DIGEST = switch
        m = Memory(os.path.join(tmp, "t.db"))
        try:
            seed(m, CHAT)
            m.db.execute("INSERT INTO relationship (chat_id, stage, affinity, called_as,"
                         " user_locked, updated_by_turn) VALUES (?,?,?,?,?,?)",
                         (CHAT, "연인", 84, "지우", 0, 0))
            m.db.execute("INSERT INTO turn (chat_id, seq, role, text, created_at,"
                         " token_count) VALUES (?,?,?,?,?,?)",
                         (CHAT, 1, "user", "안녕", 0.0, 2))
            fid, _ = plant(m, CHAT, "지우", "직업", "마케팅 회사 대리", S_DELETED, 1)
            qid, _ = plant(m, CHAT, "지우", "반려동물", "고양이 나비", S_QUIET, 2)
            # 지운 사실로 만든 세션 요약 · 안 지운 사실로 만든 lifetime — 계보를 건다.
            m.put_session_digest(CHAT, "S01", f"{S_DELETED}. 회의가 길었다.",
                                 covers_from_seq=1, covers_to_seq=10)
            m.record_derivation(CHAT, "digest", "session:S01", [("fact", fid)])
            m.db.execute("INSERT INTO digest (chat_id, kind, content, covers_to_seq)"
                         " VALUES (?,?,?,?)", (CHAT, "lifetime", f"{S_QUIET}.", 10))
            m.record_derivation(CHAT, "digest", "lifetime", [("fact", qid)])
            m.db.commit()

            def served():
                ctx = m.build_context(CHAT, "그때 얘기 말인데", 12)
                text = "\n".join(b.text for b in ctx.blocks)
                return (self.SECRET in text, S_QUIET in "\n".join(
                    b.text for b in ctx.blocks if b.name.startswith("digest:")),
                    {p[0] for p in ctx.provenance})

            out = {"before": served()}
            m.delete_item(CHAT, "fact", fid)
            out["deleted"] = served()
            m.apply_meta(CHAT, 11, {"state_delta": {"stage": "다툼중", "affinity": 80}})
            out["stage"] = m.db.execute("SELECT stage FROM relationship WHERE chat_id=?",
                                        (CHAT,)).fetchone()["stage"]
            out["transition"] = served()
            out["reason"] = m.stale_row(CHAT, "digest", "session:S01")
            return out
        finally:
            memory.TRANSITION_PROPAGATES_DIGEST = saved
            m.db.close()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_deleted_fact_stays_out_after_a_transition(self):
        for switch in (False, True):
            with self.subTest(TRANSITION_PROPAGATES_DIGEST=switch):
                out = self._run(switch)
                self.assertTrue(out["before"][0], "대조의 바닥 — 삭제 전에는 나와야 한다")
                self.assertFalse(out["deleted"][0], "삭제 직후에 이미 샌다")
                self.assertEqual(out["stage"], "다툼중", "대조의 바닥 — 전이가 실제로 났어야 한다")
                self.assertFalse(out["transition"][0],
                                 "🔴 전이 뒤에 지운 사실이 다시 서빙됐다 (U12 회귀)")
                self.assertTrue(out["reason"][0].endswith("삭제됨"),
                                f"삭제 사유가 덮였다: {out['reason'][0]}")
                # 조용한 쪽 — 안 지운 사실의 lifetime은 전이 뒤에도 나온다.
                self.assertTrue(out["transition"][1],
                                "조용한 쪽 — 안 지운 lifetime까지 빠졌다 (과잉 제거)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
