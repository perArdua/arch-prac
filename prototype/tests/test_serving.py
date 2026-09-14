# -*- coding: utf-8 -*-
"""
test_serving.py — 서빙 정책과 파급 상한. (단계 S3 · ADR-016)

S1이 저장(`put_session_digest`)을, S2가 생성(`summarize`)을 놓았다. **읽는 쪽은
아직 v4 그대로였다** — `build_context`의 digest 루프는 소스가 `digest` 하나였고
stale이면 무조건 뺐다. 여기가 그것을 가른다.

  T3    주입 상한 — `digest:` 블록 수 `b`. **고정물 둘에서만 정확값을 못박는다**
  T4    주입 순서가 결정적이다 (`covers_to_seq DESC`, 동률은 `kind DESC`)
  T5    서빙 3분기 — 제외 / 경고 주입 / 만료 강등, 그리고 `exclude_all`
  I5    `_propagate_transition`이 **모든** `session:*` 키를 민다
  I5-b  그 파급의 **상한** — `stale`·`digest_meta`가 `N+2`에 수렴하는가 (G19′③)

## 🔴 상한식과 등식을 갈라 쓴다 (계획서 편집 1)

`b`의 계약은 **`b ≤ |digest 행| + M ≤ 2 + M`**이다. 상한식만 걸면 «주입이 아예
안 되는» 회귀(`b`=0)도 통과하므로, **이름 있는 고정물 둘에서 등식**을 못박는다:

    ⓐ 새 DB   (`digest`에 lifetime 1행)          → `b` == 2
    ⓑ legacy DB (lifetime + `kind='session'`)     → `b` == 3

*"정확히 2"*만 적으면 **마이그레이션이 대상으로 삼는 바로 그 DB에서 정상 경로가
빨개진다.** 오발화하는 검사는 «발화할 수 없는 검사»의 쌍둥이다.

🔴 **DB는 전부 `tempfile`(= `%TEMP%`) 아래에 만든다.** 저장소 안에 파일 DB를
   남기면 `git status`가 더러워진다.
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import memory                                               # noqa: E402
import regen_job                                            # noqa: E402
from memory import Memory, session_kind                     # noqa: E402

CHAT = "c-serve"

# 이 파일이 쓰는 stale 사유 세 종. **문자열이 곧 분기 조건**이라 한 곳에 둔다 —
# `_serve_digest`가 보는 것은 `전이:` 접두사이고, 나머지 둘은 기존 형태다.
R_DELETED = "fact:12 삭제됨"
R_INVALID = "relationship:c-serve 무효화됨"
R_TRANSITION = "전이:연인→다툼중"


def seed(m, chat_id=CHAT):
    """`build_context`가 도는 최소 상태. `relationship`은 **필수 계층**이다."""
    m.db.execute("INSERT INTO character_version (character_id, version,"
                 " persona_text, speech_rules, taboos) VALUES (?,?,?,?,?)",
                 ("seojun", 1, "페르소나", "반말", "금기"))
    m.db.execute("INSERT INTO chat (chat_id, user_id, character_id,"
                 " character_version) VALUES (?,?,?,?)",
                 (chat_id, "jiwoo", "seojun", 1))
    m.db.execute("INSERT INTO relationship (chat_id, stage, affinity,"
                 " called_as, user_locked, updated_by_turn)"
                 " VALUES (?,?,?,?,?,?)", (chat_id, "연인", 84, "지우", 0, 0))
    m.db.execute("INSERT INTO turn (chat_id, seq, role, text, created_at,"
                 " token_count) VALUES (?,?,?,?,?,?)",
                 (chat_id, 1, "user", "안녕", 0.0, 2))
    m.db.commit()


def plant_lifetime(m, chat_id=CHAT):
    """새 DB의 모양 — `digest`에 lifetime 1행."""
    m.db.execute("INSERT OR REPLACE INTO digest (chat_id, kind, content,"
                 " covers_to_seq) VALUES (?,?,?,?)",
                 (chat_id, "lifetime", "인생 요약", 0))
    m.db.commit()


def plant_legacy_session(m, chat_id=CHAT):
    """
    기존 DB의 모양 — legacy `digest.kind='session'` 한 행이 더 있다.

    🔴 **v5는 이 키에 쓰지 않는다**(I3). 그런데 **서빙에서는 빼지 않는다** —
       빼면 기존 DB가 이 라운드에서 블록 하나를 잃고, `fsm_probe`의 제외
       합계가 10→5가 되어 ADR-013:139의 대조값이 재현되지 않는다.
       그 대가는 U11이 이름을 갖는다.
    """
    m.db.execute("INSERT OR REPLACE INTO digest (chat_id, kind, content,"
                 " covers_to_seq) VALUES (?,?,?,?)",
                 (chat_id, "session", "옛 세션 요약 (legacy)", 0))
    m.db.commit()


def put_sessions(m, sids, chat_id=CHAT):
    """`covers_to_seq`가 sid 순서로 커지도록 세션 요약을 넣는다."""
    for i, sid in enumerate(sids, 1):
        m.put_session_digest(chat_id, sid, f"{sid} 세션 요약",
                             covers_from_seq=i * 10 - 9, covers_to_seq=i * 10)


def mark_stale(m, key, reason, *, since_seq=None, chat_id=CHAT):
    """`_propagate_transition`이 남기는 것과 **같은 두 행**을 직접 심는다."""
    m.db.execute("INSERT OR REPLACE INTO stale VALUES (?,?,?,?,?)",
                 (chat_id, "digest", key, reason, 0.0))
    if since_seq is not None:
        m.db.execute("INSERT OR IGNORE INTO digest_meta (chat_id, kind)"
                     " VALUES (?,?)", (chat_id, key))
        m.db.execute("UPDATE digest_meta SET stale_since_seq=? WHERE chat_id=?"
                     " AND kind=?", (since_seq, chat_id, key))
    m.db.commit()


def blocks_and_prov(m, chat_id=CHAT, seq=2):
    ctx = m.build_context(chat_id, "그때 얘기 말인데", seq)
    names = [b.name for b in ctx.blocks if b.name.startswith("digest:")]
    prov = {p[0]: p for p in ctx.provenance}
    return ctx, names, prov


class ServingCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test-serving-")
        self.m = Memory(os.path.join(self.tmp, "s.db"))
        seed(self.m)

    def tearDown(self):
        self.m.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)


# ── T3 — 주입 상한 ──────────────────────────────────────────────────────

class TestInjectCap(ServingCase):
    """
    `b ≤ |digest 행| + M ≤ 2 + M`. 상한식과 두 등식을 **둘 다** 건다.

    **심을 위반 — 검증 레인이 실제로 심어 확인했다.**
      ⓐ `_serve_digest`의 주입 상한(`LIMIT DIGEST_INJECT_MAX`)을 지우면
         → `b`가 새 DB 6 · legacy DB 7이 되어 **이 클래스 3건 발화**
      ⓑ `_serve_digest`의 `digest_session` 분기를 지우면 (**과소 주입**)
         → `b`가 1·2로 내려가 **등식 둘이 발화**한다.
         🔴 **상한식은 `b`=0도 통과시킨다** — 과소 주입을 잡는 것은 상한식이
         아니라 **고정물 등식**이고, 그래서 둘을 함께 건다.
      ⚠️ 상한을 «정확히 2»로 적으면 **legacy DB의 정상 경로가 빨개진다**
         (rev2가 그렇게 적었고 Critic이 잡았다). 오발화도 결함이다.
    """

    def test_a_new_db_is_exactly_two_blocks(self):
        """ⓐ 새 DB — lifetime 1 + M 1 = **2**. 오늘의 컨텍스트 모양 그대로다."""
        plant_lifetime(self.m)
        put_sessions(self.m, [f"S{i:02d}" for i in range(1, 6)])
        _, names, _ = blocks_and_prov(self.m)
        self.assertEqual(len(names), 2, names)
        self.assertIn("digest:lifetime", names)
        # 🔴 `b`=2가 «lifetime 하나 + session 하나»인지 확인한다. 상한식만 보면
        #    `digest_session` 분기가 통째로 사라진 회귀(`b`=1)를 못 잡는다.
        self.assertTrue(any(n.startswith("digest:session:") for n in names),
                        names)

    def test_b_legacy_db_is_exactly_three_blocks(self):
        """ⓑ legacy DB — lifetime 1 + legacy session 1 + M 1 = **3**."""
        plant_lifetime(self.m)
        plant_legacy_session(self.m)
        put_sessions(self.m, [f"S{i:02d}" for i in range(1, 6)])
        _, names, _ = blocks_and_prov(self.m)
        self.assertEqual(len(names), 3, names)
        self.assertIn("digest:session", names)

    def test_cap_holds_when_stored_rows_grow(self):
        """
        저장 N과 주입 M이 다른 수라는 것 자체의 시험.

        행을 20개 넣어도 블록은 안 늘어난다. **`LIMIT`을 지우면 여기서 터진다** —
        ⓐ는 1+N, ⓑ는 2+N이 된다.
        """
        plant_lifetime(self.m)
        plant_legacy_session(self.m)
        put_sessions(self.m, [f"S{i:02d}" for i in range(1, 21)])
        _, names, _ = blocks_and_prov(self.m)
        cap = 2 + memory.DIGEST_INJECT_MAX
        self.assertLessEqual(len(names), cap, names)
        self.assertEqual(len(names), 3, names)

    def test_stored_rows_are_not_deleted_by_the_inject_cap(self):
        """주입에서 빼는 것이지 **지우는 것이 아니다** — lifetime 재생성의 재료다."""
        put_sessions(self.m, [f"S{i:02d}" for i in range(1, 6)])
        n = self.m.db.execute("SELECT COUNT(*) c FROM digest_session"
                              " WHERE chat_id=?", (CHAT,)).fetchone()["c"]
        self.assertEqual(n, 5)
        self.assertEqual(len(self.m.session_digests(CHAT)),
                         memory.DIGEST_INJECT_MAX)


# ── T4 — 주입 순서 ──────────────────────────────────────────────────────

class TestInjectOrder(ServingCase):
    def test_newest_wins_regardless_of_insert_order(self):
        """
        삽입 순서를 **뒤섞어** 심는다. SQLite가 우연히 안정적일 수 있어서,
        정렬이 실제로 도는지는 삽입 순서와 어긋나게 넣어야만 보인다.
        """
        plant_lifetime(self.m)
        order = ["S03", "S01", "S05", "S02", "S04"]
        for sid in order:
            self.m.put_session_digest(CHAT, sid, f"{sid} 요약",
                                      covers_from_seq=int(sid[1:]) * 10 - 9,
                                      covers_to_seq=int(sid[1:]) * 10)
        _, names, _ = blocks_and_prov(self.m)
        self.assertIn(f"digest:{session_kind('S05')}", names)

    def test_block_order_is_stable_across_ten_assemblies(self):
        plant_lifetime(self.m)
        plant_legacy_session(self.m)
        put_sessions(self.m, [f"S{i:02d}" for i in range(1, 6)])
        seen = {tuple(blocks_and_prov(self.m)[1]) for _ in range(10)}
        self.assertEqual(len(seen), 1, seen)

    def test_tie_break_is_kind_desc(self):
        """동률 `covers_to_seq`에서는 `kind DESC` — 결정적이어야 캐시가 산다."""
        for sid in ("S01", "S02"):
            self.m.put_session_digest(CHAT, sid, f"{sid} 요약",
                                      covers_from_seq=1, covers_to_seq=10)
        rows = self.m.session_digests(CHAT, limit=2)
        self.assertEqual([r["kind"] for r in rows],
                         [session_kind("S02"), session_kind("S01")])


# ── T5 — 서빙 3분기 ─────────────────────────────────────────────────────

class TestServePolicy(ServingCase):
    """
    3분기 — 삭제/무효화 → 제외 · `전이:` → 경고와 함께 주입 · E경계 초과 → `stale_expired`. 🔄 (w24c · 2026-09-12 · Fable 검토 발견 3 · C3 · 사용자 결정 Q4 = A 휴면) 뒤의 두 분기는 기본값에서 휴면이다 — `mark_stale`은 옛 전파가 만드는 행을 손으로 심는다. 기본값 제품 경로에서는 삭제·무효화 사유만 생긴다(`TRANSITION_PROPAGATES_DIGEST = False` · 기본값의 계약은 `TestTransitionDefault`).

    **심을 위반.**
      ⓐ 각 분기의 조건을 뒤집으면 → 해당 분기 시험이 **하나씩** 발화한다
         (셋이 서로를 가리지 않는다는 것이 이 클래스의 계약이다)
      ⓑ `STALE_SERVE_POLICY="exclude_all"` 복원 경로를 지우면
         → 옛 동작 대조가 깨져 **판정 앵커(제외 10회)가 재현되지 않는다**
      🔴 legacy `digest.kind='session'`을 서빙에서 **빼면** 전이당 제외가
         2→1이 되어 그 앵커가 10→5로 깨진다. 그래서 빼지 않는다.
    """

    def setUp(self):
        super().setUp()
        plant_lifetime(self.m)

    def test_deleted_reason_is_excluded(self):
        mark_stale(self.m, "lifetime", R_DELETED, since_seq=1)
        _, names, prov = blocks_and_prov(self.m)
        self.assertNotIn("digest:lifetime", names)
        self.assertIn("stale", prov)
        self.assertNotIn("stale_served", prov)

    def test_invalidated_reason_is_excluded(self):
        mark_stale(self.m, "lifetime", R_INVALID, since_seq=1)
        _, names, prov = blocks_and_prov(self.m)
        self.assertNotIn("digest:lifetime", names)
        self.assertIn("stale", prov)

    def test_transition_reason_is_served_with_a_warning(self):
        mark_stale(self.m, "lifetime", R_TRANSITION, since_seq=1)
        ctx, names, prov = blocks_and_prov(self.m)
        self.assertIn("digest:lifetime", names)
        self.assertIn("stale_served", prov)
        self.assertNotIn("stale", prov)
        blk = next(b for b in ctx.blocks if b.name == "digest:lifetime")
        # 🔴 경고가 **블록 안에** 있어야 한다. provenance에만 있으면 모델은
        #    그것을 절대 못 본다 — provenance는 컨텍스트에 안 실린다.
        self.assertTrue(blk.text.startswith(memory.STALE_SERVE_NOTE), blk.text)

    def test_transition_expires_after_E_session_boundaries(self):
        """
        E(=3) 경계를 넘으면 **제외로 강등**된다.

        경계는 `digest_session`의 «끝난 세션» 행으로 센다. `stale_since_seq`
        이후에 덮인 행이 E개 쌓이면 그 요약은 만료다.
        """
        mark_stale(self.m, "lifetime", R_TRANSITION, since_seq=0)
        put_sessions(self.m, ["S01", "S02"])          # 경계 2회 — 아직 산다
        _, names, prov = blocks_and_prov(self.m)
        self.assertIn("digest:lifetime", names)
        self.assertIn("stale_served", prov)

        put_sessions(self.m, ["S03"])                 # 경계 3회 = E
        _, names, prov = blocks_and_prov(self.m)
        self.assertNotIn("digest:lifetime", names)
        self.assertIn("stale_expired", prov)
        self.assertNotIn("stale_served", prov)

    def test_boundary_counter_only_counts_after_the_stale_point(self):
        """`stale_since_seq` **이전**에 끝난 세션은 경계가 아니다."""
        put_sessions(self.m, ["S01", "S02", "S03"])   # covers_to_seq 10·20·30
        mark_stale(self.m, "lifetime", R_TRANSITION, since_seq=30)
        self.assertEqual(self.m.session_boundaries_since(CHAT, 30), 0)
        self.assertEqual(self.m.session_boundaries_since(CHAT, 0), 3)
        _, names, prov = blocks_and_prov(self.m)
        self.assertIn("digest:lifetime", names)
        self.assertIn("stale_served", prov)

    def test_unknown_stale_since_is_not_read_as_expired(self):
        """
        «언제부터 낡았나»를 모르면 만료로 읽지 않는다. 모르는 것을 만료로
        읽으면 `digest_meta` 행이 없는 모든 낡은 요약이 조용히 사라진다.
        """
        mark_stale(self.m, "lifetime", R_TRANSITION)   # since_seq 없음
        put_sessions(self.m, ["S01", "S02", "S03", "S04"])
        _, names, prov = blocks_and_prov(self.m)
        self.assertIn("digest:lifetime", names)
        self.assertIn("stale_served", prov)
        self.assertIn("미상", prov["stale_served"][2])

    def test_exclude_all_restores_the_old_behaviour(self):
        """
        되돌리는 법 — **코드 되돌리기 없이 한 값으로** 옛 동작 전부가 온다.
        전역을 바꾸므로 반드시 복원한다 (G13).
        """
        mark_stale(self.m, "lifetime", R_TRANSITION, since_seq=1)
        saved = memory.STALE_SERVE_POLICY
        memory.STALE_SERVE_POLICY = "exclude_all"
        try:
            _, names, prov = blocks_and_prov(self.m)
        finally:
            memory.STALE_SERVE_POLICY = saved
        self.assertNotIn("digest:lifetime", names)
        self.assertIn("stale", prov)
        self.assertNotIn("stale_served", prov)
        self.assertEqual(memory.STALE_SERVE_POLICY, "transition_warn")

    def test_both_sources_take_the_same_policy(self):
        """
        `digest`와 `digest_session`이 **같은 3분기**를 탄다. 한쪽만 정책을
        태우면 같은 낡음이 소스에 따라 다르게 처분된다.
        """
        put_sessions(self.m, ["S01"])
        key = session_kind("S01")
        mark_stale(self.m, key, R_TRANSITION, since_seq=0)
        ctx, names, prov = blocks_and_prov(self.m)
        self.assertIn(f"digest:{key}", names)
        self.assertIn("stale_served", prov)
        blk = next(b for b in ctx.blocks if b.name == f"digest:{key}")
        self.assertTrue(blk.text.startswith(memory.STALE_SERVE_NOTE))

        mark_stale(self.m, key, R_DELETED)
        _, names, prov = blocks_and_prov(self.m)
        self.assertNotIn(f"digest:{key}", names)
        self.assertIn("stale", prov)


# ── I5 / I5-b — 파급과 그 상한 ──────────────────────────────────────────

def stale_digest_keys(m, chat_id=CHAT):
    return sorted(r["derived_key"] for r in m.db.execute(
        "SELECT derived_key FROM stale WHERE chat_id=? AND derived_kind='digest'",
        (chat_id,)))


def n_stale_digest(m, chat_id=CHAT):
    return m.db.execute(
        "SELECT COUNT(*) c FROM stale WHERE chat_id=? AND derived_kind='digest'",
        (chat_id,)).fetchone()["c"]


def n_digest_meta(m, chat_id=CHAT):
    return m.db.execute("SELECT COUNT(*) c FROM digest_meta WHERE chat_id=?",
                        (chat_id,)).fetchone()["c"]


class _OldPropagation:
    """
    🔄 wave3 — 이 믹스인을 단 클래스는 **옛 전파 경로**(`memory.TRANSITION_PROPAGATES_DIGEST
    = True`)를 잰다. 기본값에서는 전이가 digest를 stale로 밀지 않는다(아래
    `TestTransitionDefault`). 옛 경로를 지우지 않고 이름으로 켜 두는 이유: 되돌리는
    날(`test_summarize.py`의 전이 전후 프롬프트 대조가 «다름»을 내는 날) 그 경로가
    살아 있어야 한다 — I5 · I5-b · U12는 그때 다시 지킬 것이다.
    """

    def setUp(self):
        super().setUp()
        self._switch = memory.TRANSITION_PROPAGATES_DIGEST
        memory.TRANSITION_PROPAGATES_DIGEST = True

    def tearDown(self):
        memory.TRANSITION_PROPAGATES_DIGEST = self._switch
        super().tearDown()


class TestTransitionDefault(ServingCase):
    """
    🔄 wave3 — **기본값에서 전이는 digest를 건드리지 않는다.** 해석(`interpretation:*`)은
    그대로 민다 — 그쪽은 stage 의존이 설계다.

    **심을 위반:** 파일 끝의 스위치를 `True`로 되돌리면 두 시험이 발화한다.
    조용한 쪽은 `_OldPropagation` 클래스들이다(스위치를 켜면 옛 열거가 그대로 돈다).
    """

    def test_default_pushes_no_digest_key_but_still_pushes_interpretation(self):
        plant_lifetime(self.m)
        plant_legacy_session(self.m)
        put_sessions(self.m, [f"S{i:02d}" for i in range(1, 6)])
        self.m._propagate_transition(CHAT, 10, "연인", "다툼중")
        self.assertEqual(stale_digest_keys(self.m), [])
        self.assertEqual(n_digest_meta(self.m), 0)
        self.assertEqual(self.m.stale_row(CHAT, "interpretation", "*")[0],
                         "전이:연인→다툼중")

    def test_summaries_are_served_without_a_warning_after_a_transition(self):
        """전이 뒤 요약은 경고 없이 신선한 것으로 나간다 — 이길 블록(`relationship`)은 따로 있다."""
        plant_lifetime(self.m)
        put_sessions(self.m, ["S01"])
        self.m._propagate_transition(CHAT, 10, "연인", "다툼중")
        _, names, prov = blocks_and_prov(self.m, seq=12)
        self.assertIn("digest:lifetime", names)
        self.assertIn(f"digest:{session_kind('S01')}", names)
        self.assertNotIn("stale_served", prov)


class TestPropagation(_OldPropagation, ServingCase):
    """
    I5 — `_propagate_transition`의 `targets`가 하드코딩 2행이 아니라 **실제 키 열거**다.
    (🔄 wave3 — 옛 전파 경로에서 잰다. `_OldPropagation`)

    **심을 위반 — 검증 레인이 심어 확인했다.**
      ⓐ `targets`를 하드코딩 `[("digest","lifetime"), ("digest","session")]`로
         되돌리면 → `test_i5_every_session_key_is_pushed`(하한) ·
         `test_i5b_upper_bound_is_keep_plus_two`(상한, `2 != 26`) ·
         `test_i5_does_not_invent_keys_for_rows_that_do_not_exist` **셋 발화**
      ⓑ `put_session_digest`의 고아 행 삭제를 지우면
         → I5-b가 `28 > 26`으로 발화한다. **720턴에서는 안 보이고
         실서비스에서만 보이는 단조 증가**를 잡는 자리다.
      ⚠️ ⓐ는 `fsm_probe`를 **안 움직인다**(그 하네스가 심는 키가 정확히
         하드코딩된 둘이다) — 즉 **판정은 I5를 전제하지 않는다.**
    """

    def test_i5_every_session_key_is_pushed(self):
        """
        **하한.** 하드코딩 `targets`로 되돌리면 `session:S*` N개가 안 밀려
        여기서 터진다.
        """
        plant_lifetime(self.m)
        plant_legacy_session(self.m)
        sids = [f"S{i:02d}" for i in range(1, 6)]
        put_sessions(self.m, sids)
        self.m._propagate_transition(CHAT, 10, "연인", "다툼중")
        keys = stale_digest_keys(self.m)
        for sid in sids:
            self.assertIn(session_kind(sid), keys)
        self.assertIn("lifetime", keys)
        self.assertIn("session", keys)
        self.assertEqual(len(keys), len(sids) + 2)

    def test_i5_does_not_invent_keys_for_rows_that_do_not_exist(self):
        """
        열거는 **있는 행만** 민다. 없는 요약을 stale로 찍는 것은 «낡은 요약이
        있다»는 거짓 기록이고, `regenerate_stale`이 그것을 영원히 실패시킨다.
        """
        self.m._propagate_transition(CHAT, 10, "연인", "다툼중")
        self.assertEqual(stale_digest_keys(self.m), [])

    def test_i5b_upper_bound_is_keep_plus_two(self):
        """
        🔴 **상한 (G19′③).** rev1의 I5는 하한만 봤다. `put_session_digest`가
           밀어낸 키의 `stale`·`digest_meta` 고아 행을 함께 지우지 않으면 두
           테이블은 N에 수렴하지 않고 **세션 수만큼 단조 증가한다.**
        """
        plant_lifetime(self.m)
        plant_legacy_session(self.m)
        cap = memory.DIGEST_KEEP_SESSIONS + 2
        n = memory.DIGEST_KEEP_SESSIONS

        put_sessions(self.m, [f"S{i:02d}" for i in range(1, n + 1)])
        self.m._propagate_transition(CHAT, 10, "연인", "다툼중")
        self.assertEqual(n_stale_digest(self.m), cap)
        self.assertEqual(n_digest_meta(self.m), cap)

        # N+3개째까지 밀어 넣는다 — 가장 오래된 것들이 밀려난 **뒤에도** 상한.
        for i in range(n + 1, n + 4):
            self.m.put_session_digest(CHAT, f"S{i:02d}", "요약",
                                      covers_from_seq=i * 10 - 9,
                                      covers_to_seq=i * 10)
            self.m._propagate_transition(CHAT, 10 + i, "다툼중", "연인")
            self.assertLessEqual(n_stale_digest(self.m), cap)
            self.assertLessEqual(n_digest_meta(self.m), cap)

        self.assertEqual(
            self.m.db.execute("SELECT COUNT(*) c FROM digest_session"
                              " WHERE chat_id=?", (CHAT,)).fetchone()["c"], n)
        # 🔴 **두 수는 같아야 한다** — `_propagate_transition`의 `digest_meta`
        #    루프가 `stale` 루프와 **같은 `targets` 집합**을 돌기 때문이다.
        self.assertEqual(n_stale_digest(self.m), n_digest_meta(self.m))

    def test_stale_since_seq_is_not_rewound_by_a_second_transition(self):
        """첫 stale 시점이 알고 싶은 값이지 마지막 전이 시점이 아니다."""
        plant_lifetime(self.m)
        self.m._propagate_transition(CHAT, 5, "연인", "다툼중")
        self.m._propagate_transition(CHAT, 9, "다툼중", "연인")
        r = self.m.db.execute(
            "SELECT stale_since_seq FROM digest_meta WHERE chat_id=?"
            " AND kind='lifetime'", (CHAT,)).fetchone()
        self.assertEqual(r["stale_since_seq"], 5)


class TestTransitionKeepsDeletion(_OldPropagation, ServingCase):
    """
    🔴 wave2 — **전이가 «삭제됨» 사유를 덮어 지운 사실을 다시 서빙하지 않는다.**
    (🔄 wave3 — upsert의 가드가 일하는 것은 옛 전파 경로뿐이라 그 경로에서 잰다.
    두 스위치 값을 한 시험으로 묶은 끝-끝 회귀는 `test_deletion.py`의
    `TransitionAfterDeletionTest`다.)

    `_propagate_transition`은 `INSERT OR REPLACE`로 사유를 썼다. 그러면 사실 삭제로
    `fact:N 삭제됨`(→ 제외)이 된 요약이 전이 한 번에 `전이:…`(→ 경고와 함께 주입)가
    됐다 — 서빙 3분기의 비대칭(삭제에는 반대 블록이 없다)이 **쓰는 쪽에서** 뚫린
    것이다. 한 키에 두 사유가 겹치면 더 엄한 쪽이 이긴다.

    **심을 위반:** 그 upsert를 옛 `INSERT OR REPLACE INTO stale VALUES (?,?,?,?,?)`로
    되돌리면 시끄러운 쪽 둘이 발화한다.
    """
    SECRET = "지우는 마케팅 회사 대리로 일한다(지운 사실)"

    def _plant(self):
        self.m.upsert_fact(CHAT, "지우", "직업", "마케팅 회사 대리", seq=1)
        fid = self.m.db.execute("SELECT fact_id FROM fact").fetchone()["fact_id"]
        self.m.put_session_digest(CHAT, "S01", self.SECRET,
                                  covers_from_seq=1, covers_to_seq=10)
        self.m.record_derivation(CHAT, "digest", session_kind("S01"),
                                 [("fact", fid)])
        return fid

    def _served(self):
        ctx, names, prov = blocks_and_prov(self.m, seq=12)
        return any(self.SECRET in b.text for b in ctx.blocks), names, prov

    def test_deleted_summary_stays_out_after_a_transition(self):
        """시끄러운 쪽 — 진짜 `delete_item` 경로로 지우고 진짜 전이를 낸다."""
        fid = self._plant()
        self.assertTrue(self._served()[0], "대조의 바닥 — 삭제 전에는 서빙돼야 한다")
        self.m.delete_item(CHAT, "fact", fid)
        self.assertFalse(self._served()[0])
        self.m._propagate_transition(CHAT, 11, "연인", "다툼중")
        leaked, names, prov = self._served()
        self.assertFalse(leaked, "전이 뒤에 지운 사실의 요약이 다시 서빙됐다")
        self.assertNotIn("stale_served", prov)
        self.assertTrue(self.m.stale_row(CHAT, "digest",
                                         session_kind("S01"))[0].endswith("삭제됨"))

    def test_invalidation_reason_is_not_overwritten_either(self):
        """시끄러운 쪽 — `무효화됨`도 제외 사유다. 전이가 그것을 못 바꾼다."""
        put_sessions(self.m, ["S01"])
        mark_stale(self.m, session_kind("S01"), R_INVALID)
        self.m._propagate_transition(CHAT, 11, "연인", "다툼중")
        self.assertEqual(self.m.stale_row(CHAT, "digest", session_kind("S01"))[0],
                         R_INVALID)

    def test_transition_still_overwrites_a_transition(self):
        """
        조용한 쪽 — 전이 → 전이는 **예전처럼 새 사유로 덮는다.** 가드가 모든 덮어쓰기를
        막으면(`INSERT OR IGNORE`) 실험 20 3절의 «전이마다 민 수»가 두 번째 전이부터 0이 된다.
        """
        put_sessions(self.m, ["S01"])
        mark_stale(self.m, session_kind("S01"), "전이:썸→연인")
        self.m._propagate_transition(CHAT, 11, "연인", "다툼중")
        self.assertEqual(self.m.stale_row(CHAT, "digest", session_kind("S01"))[0],
                         R_TRANSITION)


# ── regen_job — 세션 경계 호출자 ────────────────────────────────────────

class TestRegenJob(ServingCase):
    """
    ⚠️ **여기 시험은 ollama를 한 번도 안 부른다.** `make_digest=False`이고
       stale이 없으면 `regenerate_stale`이 생성 경로에 닿지 않는다. 닿는
       경로(`session_digest`·`rewrite_lifetime`)는 `test_summarize.py`의 것이다.
    """

    def test_boundary_is_a_noop_when_not_a_session_start(self):
        """경계 판정이 **한 곳**에 산다 — 호출부마다 `if`를 적지 않는다."""
        self.assertIsNone(regen_job.boundary(
            self.m, CHAT, now_seq=5, session_start=False, make_digest=False))

    def test_empty_digest_session_is_reported_not_swallowed(self):
        """
        «세션이 지났는데 요약이 없다»가 이 계층의 가장 큰 침묵이다 (§6.4 ①).
        막지 않는다 — 첫 세션에는 언제나 참이다. **찍는다.**
        """
        out = regen_job.run(self.m, CHAT, now_seq=30, ended_session_id="S01",
                            make_digest=False)
        self.assertTrue(out["missing"])
        rows = self.m.db.execute(
            "SELECT item FROM provenance WHERE chat_id=? AND kind='regen_missing'",
            (CHAT,)).fetchall()
        self.assertEqual([r["item"] for r in rows], ["S01"])

    def test_missing_is_false_once_a_session_summary_exists(self):
        put_sessions(self.m, ["S01"])
        out = regen_job.run(self.m, CHAT, now_seq=60, make_digest=False)
        self.assertFalse(out["missing"])

    def test_legacy_session_key_can_never_be_regenerated(self):
        """
        🔴 **`stale_expired`가 실제로 물리는 경로가 이것이다.** 🔄 (w24c · 2026-09-12 · Fable 검토 B-6 · 발견 3 · 사용자 결정 Q4 = A 휴면) 기본값에서는 아니다 — 아래 `mark_stale`은 옛 전파가 만드는 행을 손으로 심는다. 기본값 제품 경로에서는 삭제·무효화 사유만 생기고, 그 사유는 만료가 아니라 제외로 간다. 이 시험이 지키는 것은 스위치를 켠 옛 경로의 만료 분기다.

        legacy `digest.kind='session'`은 v5가 다시 쓰지 않으므로(I3)
        `regenerate_stale`이 구조적으로 재생성할 수 없다 — 경계가 지날수록
        `stale`로 남고, E회에서 서빙에서 빠진다. 그 경로가 살아 있는지
        여기서 못박는다. **이것이 없으면 만료 분기는 시험에서만 도는 가지다.**
        """
        plant_legacy_session(self.m)
        mark_stale(self.m, "session", R_TRANSITION, since_seq=0)
        out = regen_job.run(self.m, CHAT, now_seq=30, make_digest=False)
        self.assertEqual(out["regen"]["ok"], [])
        self.assertEqual([k for k, _ in out["regen"]["failed"]], ["session"])
        self.assertIsNotNone(self.m.stale_row(CHAT, "digest", "session"))

        # 경계가 E회 쌓이면 만료로 강등된다.
        put_sessions(self.m, ["S01", "S02", "S03"])
        _, names, prov = blocks_and_prov(self.m)
        self.assertNotIn("digest:session", names)
        self.assertIn("stale_expired", prov)


if __name__ == "__main__":
    unittest.main()
