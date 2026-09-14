# -*- coding: utf-8 -*-
"""
test_regen_deletion.py — 요약 층 수리 묶음 A 나머지. (w24a · w17 수리 계획 · 결정 Q1=(a) · Q2=v6 안 들임 · Q3=M+1)

  발견 1  삭제로 stale이 된 세션 요약을 **다시 만들 때 지운 사실이 돌아온다.**
          재생성은 원본 턴에서 다시 쓰고(ADR-016 ④) 원본 턴은 지우지 않으므로(ADR-010 ②)
          지운 사실을 말한 턴이 그대로 재료로 간다. → 그 턴을 가리고(`_turns(exclude=…)`)
          · 새 본문에 지운 항목의 어근이 통째로 있으면 저장하지 않고(재등장 검사)
          · 지운 원본을 파생 등록에 다시 적지 않는다(`_session_sources`).
  발견 2  lifetime이 제품 경로(`regen_job.run`)에서 **처음 생기지 않는다.** → 재료가
          `LIFETIME_MIN_SESSIONS`(= M+1)개가 되는 경계에서 만든다.
  w21 ③④ `lifetime_behind`의 기준 — «재료의 최대 끝»이 아니라 «재료 키 집합이 lifetime이
          지난번에 쓴 것과 다른가»(`.omc/notepads/w24a/prereg.md` §1).

## 🔴 제품 경로만

삭제는 `delete_item`, 경계는 `regen_job.run`, 서빙은 `build_context`다. `mark_stale`도
stale 테이블에 손으로 넣는 행도 없다. 사실의 색인 복사본(`add_event` + `record_derivation`)은
소크 하니스가 쓰는 모양 그대로다. lifetime을 미리 세워야 하는 시험(③④)만
`session_digest`·`rewrite_lifetime`을 직접 부른다 — 둘 다 제품 함수다.
대역은 `llm.generate`를 갈아 끼운다 — **LLM 생성 0회.** 대역은 **재료를 보존하는
요약기**다: 세션 요약은 재료의 유저 발화를, lifetime은 재료의 세션 요약 본문을 그대로
옮긴다(최악이 아니라 보통 — 요약기는 사실을 남긴다).

⚠️ `recent` 블록(원본 턴 창)은 «비밀 없음» 단언에서 뺀다. 원본 턴은 지우지 않는다는
   것이 ADR-010 ②의 설계이고, 이 파일이 지키는 것은 **파생물**이다. `utterance`는 질의 자신이다.

## 심을 위반 (각 시험 독스트링이 자기 몫을 적는다)

  (m1) `_deleted_source_seqs`가 늘 빈 집합        → ① · 사건 가리기 · ④
  (m2) 재등장 검사 호출을 없앤다                   → ②
  (m3) `_session_sources`의 `user_deleted=0`를 없앤다 → ①(파생 단언) · ④
  (m4) `_lifetime_material`의 stale 제외를 없앤다   → K1 경계 시험
  (m5) 재등장 사유 문구에서 «재등장»을 뺀다          → ②의 문구 단언
  (m6) `lifetime_due_first`가 늘 거짓               → 둘째 경계 · 첫 생성 실패
  (m7) 문턱 1(`LIFETIME_MIN_SESSIONS = 1`)          → 첫 경계
  (m8a) 재료 키에 stale을 넣는다                    → ③
  (m8b) w21의 대안 «stale 아닌 재료의 최대 끝»        → ④
  (m9) 재등장을 «어근 하나라도 겹치면»으로             → 부분 겹침 조용한 쪽
  (m10) 색인 복사본의 `user_deleted=1`도 지운 원본으로 → 사실 갱신 조용한 쪽

## 🔄 w31f — 묶음 F (Fable 계획 2 · 결정 2: Q8 (a) · Q9 (α) · Q10 (c))

  N1 · N5 첫 요약(①)의 실패는 **표지 행**(본문 "" · 구간) + stale «미완:»을 남기고 다음 경계가 재시도한다 ·
          재시도(②)는 연속 `REGEN_MAX_ATTEMPTS`(= 2 · 유도 없음)회 실패면 «포기» — LLM 0 · stale 유지 ·
          새 삭제·무효화가 사유를 새로 쓰면 다시 K회. `TestFirstGenerationHoldAndRetryCap`.
  N7      «같은 기수 · 다른 키» — 상한 밀림과 새 세션이 한 경계에 오면 lifetime을 다시 쓴다(오늘 초록 ·
          M16을 심어야 운다). `TestLifetimeBehindIsMaterialIdentity`의 마지막 시험.
  Q9 (α)  1어근 값 «의사»가 안 지운 턴의 낱말과 겹치면 그 세션 요약은 K회 뒤 포기 — 규칙은 그대로(보호 우선) ·
          비용만 상수. `TestOneRootValueCollision` (특징짓기 · 의도된 대가).
  Q10 (c) 같은 턴의 안 지운 사실은 요약에서 빠지고 [알고 있는 것] · 검색에는 남는다. `TestSameTurnMasking`
          (특징짓기 · 의도된 대가).

  심을 위반 (w31f · `.omc/notepads/w31f/mutate.py`):
  (h1) `hold_session` 호출 제거(표지 안 남김)       → 표지 · 재시도 · 재설정 · missing
  (h2) `_retryable_keys` → 옛 SQL(포기 무시)        → 포기 뒤 LLM 0 → 1
  (h3) 상한 끔(`REGEN_MAX_ATTEMPTS` = 10**9)        → 포기 · ② 상한 · Q9
  (h4) 계수 안 올림(늘 «시도 1/K»)                  → 포기 · ② 상한 · Q9
  (h5) 포기 판정을 `regen_abandoned` 기록 유무로     → 새 삭제 뒤 재설정(사유 재설정이 안 먹힌다)
  (h6) 표지의 파생 등록 0(계획 원안)                 → 새 삭제 뒤 재설정(삭제가 표지 키에 안 닿는다)
  (h7) 표지 사유 = 예외 메시지 전체                  → 사유 속 비밀 0 → ≥ 1
  (h8) `_live_digest_count`가 표지를 셈              → `missing`
  (h9) `전이:` 사유도 계수                          → 전이 조용한 쪽
  (h10) 표지를 ① `except` 안에서 씀(계획 원안 자리)  → 같은 경계 재시도(경계 1에 이미 «포기»)
  (h11) 있는 행에도 표지(가드 제거)                  → 있는 본문 덮음 조용한 쪽
  (M16) `lifetime_behind`가 집합 대신 기수를 비교     → N7

  ⚠️ 기존 시험 중 기대가 바뀌는 것 하나(이 레인은 기존 시험을 안 고친다 — 마감 K 몫):
     `test_stale_latest_session_does_not_rewrite_every_boundary`는 S02가 경계 13 · 14에서 실패하면(시도 1/2 ·
     2/2 · 포기) 경계 15에서 `failed == []`다(단언은 `["session:S02"]`). K1 몫(같은 재료면 lifetime 프롬프트 0 ·
     `lifetime_material_excluded` 1)은 그대로 선다 — 바뀌는 것은 Q8 상한이 만든 재시도 수뿐이다.
     🔄 w33k (마감 K) — 교체함. 그 시험 독스트링의 «기대 변경» 절이 근거 자리를 적는다.

⚠️ 변이는 `python -B`로 돌린다(낡은 `.pyc`가 생존자를 만든다).
DB는 전부 `tempfile`(= `%TEMP%`) 아래에 만든다.
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import llm                                                  # noqa: E402
import memory                                               # noqa: E402
import regen_job                                            # noqa: E402
import soak                                                 # noqa: E402
import summarize                                            # noqa: E402
from memory import Memory                                   # noqa: E402

CHAT = soak.CHAT

# 지운 쪽 비밀과 조용한 쪽 문장 — `test_deletion.py`의 고정물과 같은 낱말(어근 비겹침)이다.
SECRET = "나 사실 마케팅 회사 대리로 일해"
QUIET = "고양이 나비가 요즘 밥을 잘 먹어"
SWIM = "요즘 수영 강습 다니는 중이야"
LATE = "사실 서준이한테 연락 미뤘어"
TURNS = [(1, "user", "안녕 오늘 좀 피곤하다"), (2, "character", "왜, 무슨 일 있었냐"),
         (3, "user", SECRET), (4, "character", "그랬구나"),
         (5, "user", QUIET), (6, "character", "다행이네"),
         (7, "user", "오늘 동아리 모임 있어"), (8, "character", "재밌게 놀다 와"),
         (9, "user", SWIM), (10, "character", "오 좋네"),
         (11, "user", LATE), (12, "character", "빨리 해라"),
         (13, "user", "밖에 비 온다"), (14, "character", "우산 챙겨"),
         (15, "user", "편의점 들렀다 갈게"), (16, "character", "조심히 와"),
         (17, "user", "도착했어"), (18, "character", "잘했다")]
BOUNDS = {"S01": (1, 6), "S02": (7, 12), "S03": (13, 18)}
# 재등장 대역이 새로 지어내는 문장 — 원문(SECRET)과 **표면이 다르고 어근은 다 든다.**
PARAPHRASE = "지우는 마케팅 회사에서 대리로 일한다"

SESSION_HEAD = summarize._SESSION_MATERIAL_HEADER.split("{")[0]    # «[대화 — 세션 »
LIFE_HEAD = summarize._LIFETIME_MATERIAL_HEADER.split("{")[0]      # «[재료 — 세션 요약 »
LIFE_TAIL = "\n\n[다시 쓴 요약]"


def _session_of(prompt):
    """세션 요약 프롬프트면 그 키(`session:S01`), 아니면 None."""
    if SESSION_HEAD not in prompt:
        return None
    return prompt.split(SESSION_HEAD, 1)[1].split(" · ", 1)[0]


class _Echo:
    """
    `llm.generate` 대역 — **재료 보존 요약기.** 프롬프트를 전부 적는다.

    세션 요약 → 재료의 유저 발화를 ` / `로 이어 붙인다. lifetime → 재료의 세션 요약 본문을
    이어 붙인다. `boom`에 든 키(`session:S01` · `lifetime` · `"sessions"`)의 프롬프트에서는
    `LLMError`(생성이 멈춘 경우). `add`는 세션 요약 본문 끝에 덧붙이는 문장 — 재등장 대역은
    지운 사실을 **다른 표면으로** 되살리는 요약기다.
    """

    def __init__(self, boom=(), add=None):
        self.boom, self.add = set(boom), add
        self.prompts = []

    def __enter__(self):
        self._g, self._u = llm.generate, llm.last_usage
        stub = self

        def gen(prompt):
            stub.prompts.append(prompt)
            key = _session_of(prompt)
            life = LIFE_HEAD in prompt
            if (key in stub.boom or (key and "sessions" in stub.boom)
                    or (life and "lifetime" in stub.boom)):
                raise llm.LLMError("시험이 심은 실패")
            if key:
                body = " / ".join(line.split("] ", 1)[1]
                                  for line in prompt.splitlines() if "[user]" in line)
                return body + (f" / {stub.add}" if stub.add else "")
            material = prompt.split(LIFE_HEAD, 1)[1].split("\n", 1)[1].split(LIFE_TAIL)[0]
            return " / ".join(line for line in material.splitlines()
                              if line.strip() and not line.startswith("[session:"))

        llm.generate = gen
        llm.last_usage = lambda: {"prompt_eval_count": 100}
        return self

    def __exit__(self, *exc):
        llm.generate, llm.last_usage = self._g, self._u
        return False

    def session_prompts(self, key):
        return [p for p in self.prompts if _session_of(p) == key]

    def lifetime_prompts(self):
        return [p for p in self.prompts if LIFE_HEAD in p]


class _Case(unittest.TestCase):
    """새 DB 하나(소크 시드) · 턴 1–18 · 재시도 1회(대역 실패에 3초씩 자지 않게)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.m = Memory(os.path.join(self.tmp, "t.db"))
        soak.seed(self.m)
        for seq, role, text in TURNS:
            self.m.add_turn(CHAT, seq, role, text)
        # 지운 쪽 · 조용한 쪽 · S02 쪽 사실 — 각각 소크 모양의 색인 복사본을 단다.
        self.fid = self._plant("직업", "마케팅 회사 대리", "지우는 마케팅 회사 대리로 일한다", 3)
        self.qid = self._plant("반려동물_이름", "고양이 나비", "지우가 고양이 나비를 키운다", 5)
        self.sid = self._plant("선호", "수영 강습", "지우는 수영 강습을 다닌다", 9)
        self.m.db.commit()
        self._saved = (summarize.GEN_RETRIES, summarize.GEN_RETRY_SLEEP)
        summarize.GEN_RETRIES, summarize.GEN_RETRY_SLEEP = 1, 0.0

    def tearDown(self):
        summarize.GEN_RETRIES, summarize.GEN_RETRY_SLEEP = self._saved
        self.m.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _plant(self, predicate, obj, copy, seq):
        self.m.upsert_fact(CHAT, "지우", predicate, obj, seq=seq, importance=0.8)
        fid = self.m.db.execute("SELECT fact_id FROM fact WHERE chat_id=? AND object=?",
                                (CHAT, obj)).fetchone()[0]
        _, ev = self.m.add_event(CHAT, copy, seq, emotional_weight=0.5, importance=0.8)
        self.m.record_derivation(CHAT, "event", str(ev), [("fact", fid)])
        return fid

    # ── 도우미 ─────────────────────────────────────────────────────────
    def boundary(self, sid, now_seq, stub):
        a, b = BOUNDS[sid]
        with stub:
            return regen_job.run(self.m, CHAT, now_seq=now_seq, ended_session_id=sid,
                                 from_seq=a, to_seq=b)

    def quiet_boundary(self, now_seq, stub):
        with stub:
            return regen_job.run(self.m, CHAT, now_seq=now_seq, make_digest=False)

    def prov(self, kind):
        return [tuple(r) for r in self.m.db.execute(
            "SELECT item, reason FROM provenance WHERE chat_id=? AND kind=?", (CHAT, kind))]

    def stale_digest(self):
        return sorted(r[0] for r in self.m.db.execute(
            "SELECT derived_key FROM stale WHERE chat_id=? AND derived_kind='digest'", (CHAT,)))

    def served(self, utterance="마케팅 회사 대리", now_seq=19):
        """`build_context`의 블록 `{이름: 본문}` — `recent`(L0 설계)·`utterance`(질의)는 뺀다."""
        ctx = self.m.build_context(CHAT, utterance, now_seq)
        return {b.name: b.text for b in ctx.blocks if b.name not in ("recent", "utterance")}

    def body(self, key):
        r = self.m.db.execute("SELECT content FROM digest_session WHERE chat_id=? AND kind=?",
                              (CHAT, key)).fetchone()
        return None if r is None else r[0]

    def deleted_sources(self, key):
        """그 키의 파생 등록 중 `user_deleted=1`인 원본 — 재생성이 지운 원본을 다시 적었나."""
        return [tuple(r) for r in self.m.db.execute(
            "SELECT d.source_kind, d.source_id FROM derivation d"
            " LEFT JOIN fact f ON d.source_kind='fact' AND f.fact_id=CAST(d.source_id AS INTEGER)"
            " LEFT JOIN event e ON d.source_kind='event' AND e.event_id=CAST(d.source_id AS INTEGER)"
            " WHERE d.chat_id=? AND d.derived_kind='digest' AND d.derived_key=?"
            " AND COALESCE(f.user_deleted, e.user_deleted, 0)=1", (CHAT, key))]

    def lifetime_keys(self):
        return sorted(r[0] for r in self.m.db.execute(
            "SELECT source_id FROM derivation WHERE chat_id=? AND derived_kind='digest'"
            " AND derived_key='lifetime' AND source_kind='digest'", (CHAT,)))

    def lifetime_row(self):
        return self.m.db.execute("SELECT content, covers_to_seq FROM digest WHERE chat_id=?"
                                 " AND kind='lifetime'", (CHAT,)).fetchone()

    def delete_after_first_boundary(self):
        """경계 1(S01) → 대조의 바닥 셋 → 비밀 사실 `delete_item`."""
        out = self.boundary("S01", 7, _Echo())
        self.assertEqual(out["session"], ("session:S01", []))
        # 대조의 바닥 — 삭제 전에는 비밀이 요약에 · 서빙에 · 파생 등록에 **있다.**
        # 이것이 없으면 아래 «0회» 단언들은 발화할 수 없는 검사다.
        self.assertEqual(self.body("session:S01").count(SECRET), 1)
        self.assertIn(SECRET, self.served()["digest:session:S01"])
        self.assertIn(("fact", str(self.fid)), [tuple(r) for r in self.m.db.execute(
            "SELECT source_kind, source_id FROM derivation WHERE chat_id=?"
            " AND derived_key='session:S01'", (CHAT,))])
        self.m.delete_item(CHAT, "fact", self.fid)
        self.assertEqual(self.stale_digest(), ["session:S01"])


# ── 발견 1 — 재생성이 지운 사실을 되살리지 않는다 ─────────────────────────

class TestRegenerationMasksDeletedTurns(_Case):

    def test_deleted_turn_is_not_in_the_regeneration_prompt(self):
        """
        🔴 발화 ① — 삭제 → 경계 2 → S01 재생성. 재생성 프롬프트 어디에도 비밀이 없고
        서빙 블록 전부에 없고 stale 0 · 파생 등록에 지운 원본 0 · `regen_masked` 1.

        심을 위반 (m1): 가리기를 없애면 프롬프트에 비밀 0 → 1회(재등장 검사가 저장도 막아
        `ok`가 빈다). (m3): 재등록 필터를 없애면 `deleted_sources` 0 → 1.
        """
        self.delete_after_first_boundary()
        st = _Echo()
        out = self.boundary("S02", 13, st)

        regen = st.session_prompts("session:S01")
        self.assertEqual(len(regen), 1)
        self.assertEqual(regen[0].count(SECRET), 0,
                         "지운 사실의 원문 턴이 재생성 재료로 갔다 — 발견 1")
        self.assertNotIn("\n3. [user] ", regen[0])
        self.assertEqual(out["regen"], {"ok": ["session:S01"], "failed": []})
        self.assertEqual(self.stale_digest(), [])
        self.assertEqual(self.deleted_sources("session:S01"), [],
                         "재생성이 지운 원본을 파생 등록에 다시 적었다 — 다음 삭제가 진동한다")
        for name, text in self.served().items():
            self.assertNotIn("마케팅", text, f"{name} 블록에 지운 사실")
        masked = self.prov("regen_masked")
        self.assertEqual([i for i, _ in masked], ["session:S01"])
        self.assertIn("1개", masked[0][1])
        self.assertNotIn("마케팅", masked[0][1], "provenance가 지운 내용을 옮겨 적었다")

    def test_second_delete_does_not_oscillate(self):
        """
        🔴 발화 ④ — 재생성 뒤 같은 사실을 한 번 더 `delete_item` → stale 0.
        (옛 코드는 재생성이 지운 원본을 다시 등록해서 두 번째 삭제가 S01·lifetime을 또 민다.)

        심을 위반 (m3): 재등록 필터를 없애면 stale 0 → ≥ 1.
        """
        self.delete_after_first_boundary()
        out = self.boundary("S02", 13, _Echo())
        self.assertEqual(out["regen"]["ok"], ["session:S01"])
        self.m.delete_item(CHAT, "fact", self.fid)
        self.assertEqual(self.stale_digest(), [])

    def test_reappearance_refuses_to_store(self):
        """
        🔴 발화 ② — 요약기가 지운 사실을 **다른 표면으로** 되살리면(PARAPHRASE) 저장하지
        않는다: `failed == [session:S01]` · stale 유지 · `regen_failed` 사유에 «재등장» ·
        옛 본문도 서빙되지 않는다.

        심을 위반 (m2): 검사 호출을 없애면 저장된다(`ok`에 S01 · 서빙에 «마케팅»).
        (m5): 사유 문구에서 «재등장»을 빼면 문구 단언이 발화한다.
        """
        self.delete_after_first_boundary()
        old = self.body("session:S01")
        out = self.quiet_boundary(13, _Echo(add=PARAPHRASE))

        self.assertEqual(out["regen"]["ok"], [])
        self.assertEqual([k for k, _ in out["regen"]["failed"]], ["session:S01"])
        self.assertIn("재등장", out["regen"]["failed"][0][1])
        self.assertEqual(self.stale_digest(), ["session:S01"])
        failed = dict(self.prov("regen_failed"))
        self.assertIn("재등장", failed["session:S01"])
        self.assertNotIn("마케팅", failed["session:S01"], "provenance가 지운 내용을 옮겨 적었다")
        self.assertEqual(self.body("session:S01"), old, "거부했는데 행이 바뀌었다")
        served = self.served()
        self.assertNotIn("digest:session:S01", served)
        for name, text in served.items():
            self.assertNotIn("마케팅", text, f"{name} 블록에 지운 사실")

    def test_deleted_event_turn_is_masked(self):
        """
        🔴 발화 — 유저가 **사건**을 지워도 같다(`event.source_from_seq`의 턴을 가린다).

        심을 위반 (m1): 가리기를 없애면 S02 재생성 프롬프트에 턴 11이 돌아온다.
        """
        _, ev = self.m.add_event(CHAT, "지우가 서준에게 연락을 미뤘다", 11)
        self.m.db.commit()
        self.boundary("S01", 7, _Echo())
        self.boundary("S02", 13, _Echo())
        self.assertIn(LATE, self.body("session:S02"))            # 대조의 바닥
        self.m.delete_item(CHAT, "event", ev)
        self.assertIn("session:S02", self.stale_digest())

        st = _Echo()
        out = self.quiet_boundary(14, st)
        self.assertIn("session:S02", out["regen"]["ok"])
        regen = st.session_prompts("session:S02")
        self.assertEqual(regen[0].count(LATE), 0)
        self.assertIn(SWIM, regen[0])                           # 이웃 턴은 남는다
        self.assertNotIn(LATE, self.body("session:S02"))

    def test_lifetime_material_skips_stale_session_across_boundaries(self):
        """
        🔴 발화 ③(K1 · 제품 경로 끝-끝) — 경계 1·2가 lifetime을 만들고(Q3), S01 사실을 지운 뒤
        경계 3에서 S01 재생성만 실패하면 lifetime은 S02·S03으로만 다시 써진다 — 프롬프트에
        비밀 0 · `lifetime_material_excluded` 1.

        심을 위반 (m4): stale 제외를 없애면 lifetime 프롬프트의 비밀 0 → 1.
        (옛 코드에서는 경계 2가 lifetime을 안 만들어 앞 단언에서 발화한다 — 발견 2.)
        """
        self.boundary("S01", 7, _Echo())
        self.boundary("S02", 13, _Echo())
        self.assertIsNotNone(self.lifetime_row(), "경계 2가 lifetime을 만들지 않았다")
        self.assertIn(SECRET, self.lifetime_row()[0])            # 대조의 바닥
        self.m.delete_item(CHAT, "fact", self.fid)
        self.assertEqual(self.stale_digest(), ["lifetime", "session:S01"])

        st = _Echo(boom={"session:S01"})
        out = self.boundary("S03", 19, st)
        self.assertEqual(out["regen"]["ok"], ["lifetime"])
        self.assertEqual([k for k, _ in out["regen"]["failed"]], ["session:S01"])
        life = st.lifetime_prompts()
        self.assertEqual(len(life), 1)
        self.assertEqual(life[0].count(SECRET), 0,
                         "stale인 S01 본문이 lifetime 재료로 갔다 — K1")
        self.assertEqual(len(self.prov("lifetime_material_excluded")), 1)
        self.assertEqual(self.lifetime_keys(), ["session:S02", "session:S03"])
        for name, text in self.served(now_seq=20).items():
            self.assertNotIn("마케팅", text, f"{name} 블록에 지운 사실")

    # ── 조용한 쪽 ────────────────────────────────────────────────────
    def test_undeleted_fact_survives_regeneration(self):
        """
        조용한 쪽 — 안 지운 사실(«고양이 나비»)의 턴은 재생성 프롬프트에 남고, 새 요약과
        `[알고 있는 것]`에 나온다. 재등장 검사가 조용한 사실로 울지 않는다(`regen_failed` 0).
        """
        self.delete_after_first_boundary()
        st = _Echo()
        self.boundary("S02", 13, st)
        self.assertIn(f"\n5. [user] {QUIET}\n", st.session_prompts("session:S01")[0])
        self.assertIn(QUIET, self.body("session:S01"))
        self.assertIn("고양이 나비", self.served("고양이 나비")["알고 있는 것"])
        self.assertEqual(self.prov("regen_failed"), [])

    def test_partial_overlap_is_not_a_reappearance(self):
        """
        조용한 쪽 — 지운 항목의 어근 **일부**(«마케팅»)만 새 본문에 있으면 재등장이 아니다.
        «마케팅»만으로 울면 그 낱말을 쓰는 모든 요약이 영영 stale이다 — 조용한 쪽이 죽는다.

        심을 위반 (m9): «어근 하나라도 겹치면 재등장»으로 바꾸면 저장이 거부된다.
        """
        self.delete_after_first_boundary()
        out = self.quiet_boundary(13, _Echo(add="마케팅 수업 과제 얘기도 했다"))
        self.assertEqual(out["regen"], {"ok": ["session:S01"], "failed": []})
        self.assertIn("마케팅", self.body("session:S01"))     # 대역이 실제로 겹침을 넣었다
        self.assertEqual(self.prov("regen_failed"), [])

    def test_superseded_fact_is_not_a_deletion(self):
        """
        조용한 쪽 — 사실이 **바뀌면**(단일값 술어 갱신) 옛 값의 색인 복사본이 `user_deleted=1`이
        되지만 그것은 유저의 삭제가 아니다. S01은 «무효화됨»으로 stale이 되고 재생성은 턴을
        **가리지 않는다**(옛 값을 말한 이력은 이력이다) · `regen_masked` 0.

        심을 위반 (m10): 복사본의 `user_deleted=1`도 지운 원본으로 세면 턴 3이 가려진다.
        """
        self.boundary("S01", 7, _Echo())
        self.m.upsert_fact(CHAT, "지우", "직업", "프리랜서 디자이너", seq=4, importance=0.8)
        self.assertIn("무효화됨", self.m.stale_row(CHAT, "digest", "session:S01")[0])
        st = _Echo()
        out = self.quiet_boundary(8, st)
        self.assertEqual(out["regen"], {"ok": ["session:S01"], "failed": []})
        self.assertIn(f"\n3. [user] {SECRET}\n", st.session_prompts("session:S01")[0])
        self.assertEqual(self.prov("regen_masked"), [])

    def test_no_deletion_prompt_is_byte_identical(self):
        """
        조용한 쪽 — 삭제가 없는 구간의 세션 요약 프롬프트는 **옛 조립식과 바이트 동일**하다
        (체크포인트 키가 프롬프트다). 다른 세션(S01)의 삭제도 S02의 프롬프트를 안 움직인다.
        """
        def old_prompt(sid):
            a, b = BOUNDS[sid]
            body = "\n".join(f"{s}. [{r}] {t}" for s, r, t in TURNS if a <= s <= b)
            return (summarize.SESSION_TEMPLATE + "\n\n"
                    + summarize._SESSION_MATERIAL_HEADER.format(
                        sid=f"session:{sid}", a=a, b=b)
                    + "\n" + body + "\n\n[세션 요약]\n")

        st = _Echo()
        self.boundary("S01", 7, st)
        self.assertEqual(st.prompts, [old_prompt("S01")])
        self.m.delete_item(CHAT, "fact", self.fid)
        st = _Echo()
        self.boundary("S02", 13, st)
        self.assertEqual(st.session_prompts("session:S02"), [old_prompt("S02")])


# ── 발견 2 — 첫 lifetime (Q3 = M+1) ──────────────────────────────────────

class TestFirstLifetime(_Case):

    def test_first_boundary_creates_no_lifetime(self):
        """
        조용한 쪽 — 세션 요약 1개는 세션 블록(M=1)이 이미 덮는다. lifetime을 만들면
        같은 재료가 두 블록으로 나간다. 호출 1(세션 요약뿐).

        심을 위반 (m7): 문턱을 1로 두면 여기서 lifetime이 생긴다.
        """
        st = _Echo()
        out = self.boundary("S01", 7, st)
        self.assertIsNone(out["lifetime"])
        self.assertIsNone(self.lifetime_row())
        self.assertEqual(len(st.prompts), 1)

    def test_second_boundary_creates_the_lifetime(self):
        """
        🔴 발화 — 재료가 M+1개가 되는 경계에서 `regen_job.run`이 lifetime을 **처음 만든다**
        (`out["lifetime"] == "created"`) · 덮는 끝 = S02 끝 · 계보 = S01·S02 · 서빙에 lifetime 블록.

        심을 위반 (m6): `lifetime_due_first`가 늘 거짓이면 행 0으로 발화한다(옛 코드 그대로).
        """
        self.boundary("S01", 7, _Echo())
        st = _Echo()
        out = self.boundary("S02", 13, st)
        self.assertEqual(out["lifetime"], "created")
        self.assertEqual(self.lifetime_row()[1], BOUNDS["S02"][1])
        self.assertEqual(len(st.prompts), 2, "세션 요약 1 + lifetime 1이어야 한다")
        self.assertEqual(self.lifetime_keys(), ["session:S01", "session:S02"])
        self.assertIn("digest:lifetime", self.served())

    def test_first_creation_failure_is_regen_failed_not_stale(self):
        """
        🔴 발화 — 첫 생성이 실패하면 행을 만들지 않고 stale로도 찍지 않는다 — `regen_failed`
        (기존 규약). 세션 요약은 그대로 저장된다.

        심을 위반 (m6): 첫 생성을 시도조차 안 하면 `out["lifetime"]`이 None이다.
        """
        self.boundary("S01", 7, _Echo())
        out = self.boundary("S02", 13, _Echo(boom={"lifetime"}))
        self.assertTrue(str(out["lifetime"]).startswith("failed"), out["lifetime"])
        self.assertIsNone(self.lifetime_row())
        self.assertIsNone(self.m.stale_row(CHAT, "digest", "lifetime"))
        self.assertIn("lifetime", [i for i, _ in self.prov("regen_failed")])
        self.assertEqual(out["session"], ("session:S02", []))

    def test_stale_sessions_do_not_count_toward_the_first_lifetime(self):
        """
        조용한 쪽 — 문턱은 **재료**(stale 아닌 세션 요약)로 센다. S01이 삭제로 stale이고 재생성이
        실패하면 재료는 S02 하나 → lifetime을 안 만든다(만들면 S02 한 개짜리 lifetime이
        session:S02 블록과 같은 재료로 나간다). `prereg.md` §2.

        심을 위반: `digest_session` 행 수로 세면 여기서 lifetime이 생긴다.
        """
        self.delete_after_first_boundary()
        out = self.boundary("S02", 13, _Echo(boom={"session:S01"}))
        self.assertEqual([k for k, _ in out["regen"]["failed"]], ["session:S01"])
        self.assertIsNone(out["lifetime"])
        self.assertIsNone(self.lifetime_row())


# ── w21 ③④ — `lifetime_behind`의 기준 = 재료 키 집합 ─────────────────────

class TestLifetimeBehindIsMaterialIdentity(_Case):
    """lifetime을 S01·S02로 미리 세운다(제품 함수 `session_digest`·`rewrite_lifetime`)."""

    def setUp(self):
        super().setUp()
        with _Echo():
            for sid in ("S01", "S02"):
                a, b = BOUNDS[sid]
                summarize.session_digest(self.m, CHAT, sid, from_seq=a, to_seq=b)
            summarize.rewrite_lifetime(self.m, CHAT)
        self.assertEqual(self.lifetime_keys(), ["session:S01", "session:S02"])

    def test_stale_latest_session_does_not_rewrite_every_boundary(self):
        """
        🔴 발화 ③ — 최신 세션(S02)이 삭제로 stale이고 재생성이 계속 실패한다. 첫 경계는 lifetime을
        S01로 다시 쓰고(②) 그 뒤 경계들은 **같은 재료이므로 부르지 않는다** — lifetime 프롬프트 0 ·
        `lifetime_material_excluded`는 1에서 안 는다.

        옛 기준(«lifetime 덮는 끝 < 세션 요약 최대 끝»)은 경계마다 참이라 매번 다시 쓴다(w21 ③).
        심을 위반 (m8a): 재료 키에 stale 행을 넣으면 경계마다 다시 쓴다.

        🔄 기대 변경 — Q8 (a) · w31f D1~D5 · 근거 자리: `.omc/notepads/w31f/prereg.md` §4(값 보기 전 예측) ·
           `.omc/notepads/w31f/progress.md` «K 몫» 2 · `.omc/notepads/w33k/expect_out.txt`(수리 전 사본 옛 기대 초록 ·
           새 기대 빨강 / 수리 뒤 반대 · m8a는 새 기대에서도 운다). S02의 재생성은 경계 13(시도 1/2) · 14(2/2 · 포기)에서
           실패하고 경계 15는 **부르지 않는다** — `failed`가 `[S02]` → `[]`(D5의 기제 산수). 목적(최신 세션이 stale인 채
           재료가 같으면 lifetime을 다시 안 쓴다)은 그대로 선다: 경계 15에서도 S02는 stale(포기)이라 «stale 최신 세션»
           전제가 살아 있고, 그 경계의 lifetime 프롬프트 0이 빈 검사가 아님을 아래 단언이 박는다.
        """
        self.m.delete_item(CHAT, "fact", self.sid)
        self.assertEqual(self.stale_digest(), ["lifetime", "session:S02"])
        first = self.quiet_boundary(13, _Echo(boom={"session:S02"}))
        self.assertEqual(first["regen"]["ok"], ["lifetime"])
        self.assertEqual(self.lifetime_keys(), ["session:S01"])

        for now, failed in ((14, ["session:S02"]), (15, [])):
            st = _Echo(boom={"session:S02"})
            out = self.quiet_boundary(now, st)
            self.assertEqual([k for k, _ in out["regen"]["failed"]], failed)
            self.assertIsNone(out["lifetime"])
            self.assertEqual(st.lifetime_prompts(), [], f"경계 {now}: 같은 재료로 lifetime을 다시 썼다")
        self.assertEqual(len(self.prov("lifetime_material_excluded")), 1)
        # 경계 15의 전제 — 최신 세션 S02는 여전히 stale(포기)이다. 포기가 stale을 지웠다면 위 «lifetime 0»은
        # «재료가 바뀌지 않았다»가 아니라 «S02가 돌아왔다»의 다른 상황을 보는 것이 된다.
        self.assertEqual(self.stale_digest(), ["session:S02"])
        self.assertTrue(self.m.stale_row(CHAT, "digest", "session:S02")[0].endswith(" · 시도 2/2 · 포기"))
        self.assertEqual([i for i, _ in self.prov("regen_abandoned")], ["session:S02"])

    def test_regenerated_older_session_returns_to_the_lifetime(self):
        """
        🔴 발화 ④ — S01(최신 아님)이 삭제로 stale → lifetime이 S02로만 다시 써진다 → 다음 경계에서
        S01 재생성이 **성공**하면 그 경계의 ③이 lifetime을 다시 쓴다 — 계보에 S01이 돌아오고
        비밀은 없다.

        옛 기준은 덮는 끝(S02 끝)이 그대로라 다음 새 세션까지 S01을 안 품는다(w21 ④).
        심을 위반 (m8b): w21의 대안 «stale 아닌 재료의 최대 끝»도 여기서 발화한다.
        """
        self.m.delete_item(CHAT, "fact", self.fid)
        self.quiet_boundary(13, _Echo(boom={"session:S01"}))
        self.assertEqual(self.lifetime_keys(), ["session:S02"])

        st = _Echo()
        out = self.quiet_boundary(14, st)
        self.assertEqual(out["regen"], {"ok": ["session:S01"], "failed": []})
        self.assertEqual(out["lifetime"], "rewritten")
        self.assertEqual(self.lifetime_keys(), ["session:S01", "session:S02"])
        life = st.lifetime_prompts()
        self.assertEqual(len(life), 1)
        self.assertIn(QUIET, life[0])
        self.assertEqual(life[0].count(SECRET), 0)

    def test_same_material_no_call(self):
        """조용한 쪽 — 재료 키 집합이 lifetime이 쓴 것과 같으면 호출 0 · `out["lifetime"]` None."""
        st = _Echo()
        out = self.quiet_boundary(13, st)
        self.assertIsNone(out["lifetime"])
        self.assertEqual(st.prompts, [])

    def test_cap_push_and_new_session_in_one_boundary_still_rewrites(self):
        """
        🔴 N7 (w31f) — **같은 기수 · 다른 키.** lifetime이 S01..S(N)을 품은 뒤 S(N+1) 경계에서 N 상한이
        S01을 밀고 S(N+1)을 더한다 — 재료 수는 N 그대로인데 키가 다르다 → lifetime을 **다시 쓴다**
        (`out["lifetime"] == "rewritten"` · 계보에 S(N+1) 있음 · S01 없음 · lifetime 프롬프트 1회).

        오늘 코드에서 초록이다(«수리 전 빨강»이 없다). 이 시험이 지키는 것은 집합 비교 자체다 —
        심을 위반 (M16): `lifetime_behind`가 `now != written` 대신 `len(now) != len(written)`을 보면
        마지막 경계가 조용해진다(`None` · 계보에 S01 잔존). w26final까지는 끝-끝 7단계만 이것을 잡았다.
        비용: 경계 N−1회 · 대역 · LLM 0.
        """
        n = memory.DIGEST_KEEP_SESSIONS
        for s in range(4, n + 2):                               # S04..S(N+1) — 턴 6개씩
            for k in range(1, 7):
                seq = 6 * (s - 1) + k
                self.m.add_turn(CHAT, seq, "user" if k % 2 else "character", f"세션{s} 이야기 {k}")
        self.m.db.commit()
        bounds = dict(BOUNDS, **{f"S{s:02d}": (6 * (s - 1) + 1, 6 * s) for s in range(4, n + 2)})

        def run(sid, stub):
            a, b = bounds[sid]
            with stub:
                return regen_job.run(self.m, CHAT, now_seq=b + 1, ended_session_id=sid,
                                     from_seq=a, to_seq=b)

        for s in range(3, n + 1):                               # S03..S(N) — 경계마다 새 세션 → 다시 씀
            self.assertEqual(run(f"S{s:02d}", _Echo())["lifetime"], "rewritten")
        # 대조의 바닥 — 마지막 경계 전 lifetime은 S01을 포함한 N개를 품는다.
        before = self.lifetime_keys()
        self.assertEqual(len(before), n)
        self.assertIn("session:S01", before)

        last = f"S{n + 1:02d}"
        st = _Echo()
        out = run(last, st)
        self.assertEqual(out["session"], (f"session:{last}", ["session:S01"]))   # 상한이 S01을 밀었다
        self.assertEqual(len(summarize.lifetime_material_keys(self.m, CHAT)), n)  # 기수 같음
        self.assertEqual(out["lifetime"], "rewritten",
                         "같은 기수 · 다른 키에서 lifetime을 다시 쓰지 않았다 — N7")
        after = self.lifetime_keys()
        self.assertIn(f"session:{last}", after)
        self.assertNotIn("session:S01", after)
        self.assertEqual(len(st.lifetime_prompts()), 1)


# ── w31f — N1 · N5: ①의 실패는 표지를 남기고 · 재시도는 연속 K회에서 멈춘다 (Q8 (a)) ──────────

# 턴 5 — 안 지운 발화인데 지운 값(«마케팅 회사 대리»)의 어근을 **통째로** 품는다(w26final P4 모양).
# 재료 보존 대역에서 재등장 거부가 **결정적으로** 난다 — 원인이 안 지운 턴에 있으니 다시 만들어도 같다.
ECHO5 = "마케팅 회사 대리 일이 요즘 힘들다"
HOLD_TURNS = [(1, "user", "안녕 오늘 좀 피곤하다"), (2, "character", "왜, 무슨 일 있었냐"),
              (3, "user", SECRET), (4, "character", "그랬구나"),
              (5, "user", ECHO5), (6, "character", "힘내라")] + TURNS[6:]


class _Leaky(_Echo):
    """`_Echo`와 같되 생성 실패의 **메시지가 재료를 싣는다** — 생성기 오류가 무엇을 실을지 모르는 경우."""

    def __enter__(self):
        super().__enter__()
        inner = llm.generate

        def gen(prompt):
            try:
                return inner(prompt)
            except llm.LLMError:
                raise llm.LLMError(f"생성 실패 — 입력 머리: {SECRET}") from None

        llm.generate = gen
        return self


class _Fixture(_Case):
    """`_Case`와 같은 틀(소크 시드 · 대역 재시도 1회) — 턴(`ROWS`)과 심는 사실(`plants`)만 다르다."""
    ROWS = HOLD_TURNS

    def plants(self):
        self.fid = self._plant("직업", "마케팅 회사 대리", "지우는 마케팅 회사 대리로 일한다", 3)
        # 턴 5의 사실(색인 복사본 포함) — 지우면 턴 5가 가려져 재등장의 원인이 사라진다.
        self.eid = self._plant("선호", "대리 일 줄이기", "지우는 대리 일을 줄이고 싶어 한다", 5)

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.m = Memory(os.path.join(self.tmp, "t.db"))
        soak.seed(self.m)
        for seq, role, text in self.ROWS:
            self.m.add_turn(CHAT, seq, role, text)
        self.plants()
        self.m.db.commit()
        self._saved = (summarize.GEN_RETRIES, summarize.GEN_RETRY_SLEEP)
        summarize.GEN_RETRIES, summarize.GEN_RETRY_SLEEP = 1, 0.0

    def reason(self, key="session:S01"):
        row = self.m.stale_row(CHAT, "digest", key)
        return None if row is None else row[0]

    def calls(self, stub, key="session:S01"):
        return len(stub.session_prompts(key))

    def bare_holds(self):
        """stale 없는 표지 행 — 빈 본문이 서빙되는 상태. 제품 경로에서 늘 0이다(DB 불변 · 계획 위험 ②)."""
        return [r[0] for r in self.m.db.execute(
            "SELECT kind FROM digest_session d WHERE chat_id=? AND content=''"
            " AND NOT EXISTS (SELECT 1 FROM stale s WHERE s.chat_id=d.chat_id"
            " AND s.derived_kind='digest' AND s.derived_key=d.kind)", (CHAT,))]


class TestFirstGenerationHoldAndRetryCap(_Fixture):

    def test_first_generation_refusal_leaves_a_hold_and_the_next_boundary_retries(self):
        """
        🔴 발화 ① (N1) — 경계 **전에** 지우고 턴 5가 같은 낱말이면 ①이 재등장으로 거부된다 →
        표지 행(본문 "" · 구간 1–6) · stale «미완: … · 시도 1/2» · `missing` True · 서빙에 S01 블록 0 ·
        이 경계의 ②는 표지를 부르지 않는다 → 다음 경계가 **한 번** 재시도한다(LLM 1 · `failed == [S01]`).

        오늘(수리 전): 행 0 · stale 0 · 다음 경계 LLM 0 — 아무도 다시 만들지 않는다(w26final P4).
        심을 위반 (h1): 표지 호출을 없애면 본문 단언에서 운다. (h10): 표지를 ① 안에서 쓰면 같은 경계의
        ②가 곧바로 재시도해 `out["regen"]`이 빈 것이 아니게 된다.
        """
        self.m.delete_item(CHAT, "fact", self.fid)                 # 경계 전에 지움
        st = _Echo()
        out = self.boundary("S01", 7, st)
        self.assertEqual(self.calls(st), 1)
        self.assertEqual(out["session"][0], "failed")
        self.assertIn("재등장", out["session"][1])
        self.assertEqual(out["regen"], {"ok": [], "failed": []}, "같은 경계에서 표지를 다시 불렀다")
        self.assertEqual(self.body("session:S01"), "",
                         "첫 요약이 실패했는데 표지 행이 없다 — 다음 경계가 구간을 모른다 (N1)")
        self.assertEqual(tuple(self.m.db.execute(
            "SELECT covers_from_seq, covers_to_seq FROM digest_session WHERE chat_id=?"
            " AND kind='session:S01'", (CHAT,)).fetchone()), (1, 6))
        self.assertTrue(self.reason().startswith("미완: "), self.reason())
        self.assertTrue(self.reason().endswith(" · 시도 1/2"), self.reason())
        self.assertTrue(out["missing"])
        served = self.served()
        self.assertNotIn("digest:session:S01", served)
        for name, text in served.items():
            self.assertNotIn(SECRET, text, f"{name} 블록에 지운 사실")
        self.assertEqual(self.bare_holds(), [])

        st = _Echo()
        out = self.quiet_boundary(13, st)
        self.assertEqual(self.calls(st), 1, "표지가 있는데 다음 경계가 재시도하지 않았다 (N1)")
        self.assertEqual([k for k, _ in out["regen"]["failed"]], ["session:S01"])
        self.assertIn("재등장", out["regen"]["failed"][0][1])
        self.assertEqual(self.bare_holds(), [])

    def test_second_failure_abandons_and_stops_calling(self):
        """
        🔴 발화 ② (N5) — 위에 이어 재시도도 거부되면 사유 끝 « · 시도 2/2 · 포기» · `regen_abandoned` 1 →
        그 뒤 경계는 LLM **0** · `regen_failed`는 2(① 1 + ② 1)에서 멈춤 · stale 유지 · 서빙 제외 그대로.
        **표식:** 셋째 경계의 S01 LLM 호출 수 — 수리 뒤 0 ↔ 변이 1.

        오늘(수리 전): 재시도 자체가 없다(P4) — 앞 단언에서 운다.
        심을 위반 (h2): 포기 필터를 없애면 셋째 경계 LLM 0 → 1. (h3) 상한 끔 · (h4) 계수 안 올림 → 포기 0.
        """
        self.m.delete_item(CHAT, "fact", self.fid)
        self.boundary("S01", 7, _Echo())
        self.quiet_boundary(13, _Echo())
        self.assertTrue(self.reason().startswith("미완: "), self.reason())
        self.assertTrue(self.reason().endswith(" · 시도 2/2 · 포기"), self.reason())
        self.assertEqual([i for i, _ in self.prov("regen_abandoned")], ["session:S01"])

        for now in (14, 15):
            st = _Echo()
            out = self.quiet_boundary(now, st)
            self.assertEqual(self.calls(st), 0, f"경계 {now}: 포기한 키를 또 불렀다 (N5)")
            self.assertEqual(out["regen"], {"ok": [], "failed": []})
        self.assertEqual(len(self.prov("regen_failed")), 2)
        self.assertEqual(len(self.prov("regen_abandoned")), 1)
        self.assertIsNotNone(self.reason(), "포기가 stale을 지웠다 — 서빙 제외가 풀린다")
        self.assertNotIn("digest:session:S01", self.served(now_seq=16))
        self.assertEqual(self.bare_holds(), [])

    def test_new_deletion_resets_the_episode_and_can_succeed(self):
        """
        🔴 발화 ③ — 포기 뒤 턴 5의 사실을 `delete_item` → 표지 키의 사유가 «fact:N 삭제됨»으로 **새로 써지고**
        (꼬리 0) 다시 K회다: 다음 경계가 실패하면 «시도 1/2»(포기 아님) · 그다음 경계가 **성공** —
        턴 3 · 5가 가려져 재등장 원인이 사라진다 → 표지가 본문으로 · stale 0 · 서빙에 S01 블록(비밀 둘 다 0).

        오늘(수리 전): 표지가 없어 재시도 자체가 없다.
        심을 위반 (h5): 포기 판정을 `regen_abandoned` 기록 유무로 하면 사유를 새로 써도 계속 건너뛴다.
        (h6): 표지가 파생 등록을 안 하면(계획 원안) 턴 5의 삭제가 표지 키에 닿지 않는다 — 사유가 안 바뀐다.
        """
        self.m.delete_item(CHAT, "fact", self.fid)
        self.boundary("S01", 7, _Echo())
        self.quiet_boundary(13, _Echo())
        self.assertTrue(self.reason().endswith(" · 포기"))                 # 대조의 바닥
        self.m.delete_item(CHAT, "fact", self.eid)
        self.assertEqual(self.reason(), f"fact:{self.eid} 삭제됨", "새 삭제가 표지 키의 사유를 새로 쓰지 않았다")

        st = _Echo(boom={"session:S01"})                                  # 재설정 뒤 첫 시도가 실패해도
        self.quiet_boundary(14, st)
        self.assertEqual(self.calls(st), 1)
        self.assertEqual(self.reason(), f"fact:{self.eid} 삭제됨 · 시도 1/2", "재설정 뒤 K가 다시 세어지지 않았다")

        st = _Echo()
        out = self.quiet_boundary(15, st)
        self.assertEqual(self.calls(st), 1)
        self.assertEqual(out["regen"], {"ok": ["session:S01"], "failed": []})
        body = self.body("session:S01")
        self.assertTrue(body)
        for text in (SECRET, ECHO5, "마케팅"):
            self.assertNotIn(text, body)
        self.assertEqual(self.stale_digest(), [])
        self.assertFalse(out["missing"])
        served = self.served(now_seq=16)
        self.assertIn("digest:session:S01", served)
        for name, text in served.items():
            self.assertNotIn(SECRET, text, f"{name} 블록에 지운 사실")
            self.assertNotIn(ECHO5, text, f"{name} 블록에 지운 사실(턴 5)")
        self.assertEqual(self.deleted_sources("session:S01"), [])

    def test_transient_failure_recovers_within_the_cap(self):
        """
        조용한 쪽 ④ — 삭제 없이 ①의 생성이 한 번 멈추면 표지 → 다음 경계(S02)의 ②가 S01을 **성공**시킨다 →
        stale 0 · `regen_abandoned` 0 · `missing` False. 재시도 규약이 N1 전에는 ①에서 거짓이었다.
        """
        out = self.boundary("S01", 7, _Echo(boom={"session:S01"}))
        self.assertEqual(out["session"][0], "failed")
        self.assertTrue(self.reason().startswith("미완: 1회 재시도가 전부 실패했다"), self.reason())
        self.assertTrue(self.reason().endswith(" · 시도 1/2"), self.reason())

        out = self.boundary("S02", 13, _Echo())
        self.assertEqual(out["session"], ("session:S02", []))
        self.assertEqual(out["regen"], {"ok": ["session:S01"], "failed": []})
        self.assertIn(ECHO5, self.body("session:S01"))
        self.assertEqual(self.stale_digest(), [])
        self.assertEqual(self.prov("regen_abandoned"), [])
        self.assertFalse(out["missing"])

    def test_normal_first_generation_leaves_no_hold(self):
        """
        조용한 쪽 — 정상 첫 생성은 표지도 stale도 · «미완»도 «시도»도 안 남긴다 · 호출 1 · 프롬프트는
        옛 조립식 그대로(`test_no_deletion_prompt_is_byte_identical`이 바이트를 본다).
        """
        st = _Echo()
        out = self.boundary("S01", 7, st)
        self.assertEqual(out["session"], ("session:S01", []))
        self.assertEqual(len(st.prompts), 1)
        self.assertEqual(self.m.db.execute("SELECT COUNT(*) FROM stale WHERE chat_id=?"
                                           " AND derived_kind='digest'", (CHAT,)).fetchone()[0], 0)
        self.assertEqual(self.prov("regen_abandoned"), [])
        self.assertFalse(out["missing"])

    def test_hold_reason_and_provenance_carry_no_deleted_text(self):
        """
        🔴 발화 ⑤ — 표지 사유 · 재생성 계열 provenance에 지운 값(«마케팅») 0회. 대조의 바닥: 같은 DB의
        `turn` 표에는 비밀이 있다(원본 턴은 안 고친다 · ADR-010 ②).

        (가) 재등장 경로의 사유는 라벨만 싣는다(오늘부터 그렇다 — 조용한 쪽).
        (나) 생성기 오류 메시지가 재료를 실으면(`_Leaky`) 표지 사유에는 **첫 절만** 간다.
        **표식:** (나)의 사유 속 비밀 — 수리 뒤 0 ↔ 변이 ≥ 1.
        심을 위반 (h7): 표지 사유에 예외 메시지 전체를 적으면 (나)에서 운다.
        ⚠️ 관찰(이 시험이 바꾸지 않는 것): `regen_failed`의 사유는 오늘처럼 예외 **전체**다 — (나)의 메시지는
           거기에 그대로 남는다. 표지 사유와 같은 규칙을 거기에 걸지는 이 묶음의 결정 밖이다(K 몫으로 적음).
        """
        self.assertEqual(self.m.db.execute("SELECT COUNT(*) FROM turn WHERE chat_id=? AND text=?",
                                           (CHAT, SECRET)).fetchone()[0], 1)
        self.m.delete_item(CHAT, "fact", self.fid)
        self.boundary("S01", 7, _Echo())
        self.quiet_boundary(13, _Echo())
        self.assertIn("포기", self.reason())
        for (reason,) in self.m.db.execute("SELECT reason FROM stale WHERE chat_id=?", (CHAT,)):
            self.assertNotIn("마케팅", reason)
        for kind in ("regen_failed", "regen_masked", "regen_abandoned", "regen_missing"):
            for item, reason in self.prov(kind):
                self.assertNotIn("마케팅", reason, f"{kind} {item}가 지운 내용을 옮겨 적었다")

        out = self.boundary("S02", 13, _Leaky(boom={"session:S02"}))      # (나)
        self.assertEqual(out["session"][0], "failed")
        self.assertIn(SECRET, out["session"][1])                          # 대역이 정말 실었다
        leaked = self.reason("session:S02")
        self.assertTrue(leaked.startswith("미완: "), leaked)
        self.assertNotIn(SECRET, leaked, "표지 사유가 예외 메시지 전체를 옮겨 적었다")
        self.assertNotIn("마케팅", leaked)

    def test_regen_missing_ignores_the_hold_row(self):
        """
        🔴 발화 ⑥ — 첫 세션 ①이 실패한 방은 표지가 있어도 `missing` True(표지는 요약이 아니다) ·
        `regen_missing` 사유가 표지 1건을 말한다 → 다음 경계의 ②가 성공하면 False.

        오늘(수리 전): 행이 없어 `missing` True는 같지만 표지 단언에서 운다.
        심을 위반 (h8): `_live_digest_count`가 표지를 세면 첫 경계 `missing` False.
        """
        out = self.boundary("S01", 7, _Echo(boom={"session:S01"}))
        self.assertEqual(self.body("session:S01"), "")
        self.assertTrue(out["missing"], "표지 행을 요약으로 셌다")
        missing = self.prov("regen_missing")
        self.assertEqual(len(missing), 1)
        self.assertIn("표지 행 1건", missing[0][1])

        out = self.quiet_boundary(8, _Echo())
        self.assertEqual(out["regen"], {"ok": ["session:S01"], "failed": []})
        self.assertFalse(out["missing"])
        self.assertEqual(len(self.prov("regen_missing")), 1)

    def test_regeneration_refusal_is_capped_too(self):
        """
        🔴 발화 (N5 · ② 쪽) — ①은 성공(삭제 전)하고 삭제 뒤 재생성이 턴 5 때문에 계속 거부되면
        경계마다 S01 LLM 호출 **[1, 1, 0, 0]** · `regen_failed` 2 · `regen_masked` 2 · `regen_abandoned` 1 ·
        stale 유지. 오늘(수리 전): [1, 1, 1, 1] · 4 · 4(w26final P7 · P2′).
        ⚠️ 계획의 기대 델타 «P7 → [1,0,0,0]»은 계획 자신의 기제(삭제로 stale인 키의 첫 실패 = 시도 1/2)와
           맞지 않는다 — 기제대로 [1,1,0,0]이다(`.omc/notepads/w31f/prereg.md` D5).
        심을 위반 (h3) · (h4): 포기가 안 나 [1,1,1,1]. (h2): 포기는 적히나 [1,1,1,1].
        """
        self.boundary("S01", 7, _Echo())
        self.assertEqual(self.body("session:S01").count(SECRET), 1)       # 대조의 바닥
        self.m.delete_item(CHAT, "fact", self.fid)
        calls = []
        for now in (8, 9, 10, 11):
            st = _Echo()
            self.quiet_boundary(now, st)
            calls.append(self.calls(st))
        self.assertEqual(calls, [1, 1, 0, 0])
        self.assertEqual(len(self.prov("regen_failed")), 2)
        self.assertEqual(len(self.prov("regen_masked")), 2)
        self.assertEqual(len(self.prov("regen_abandoned")), 1)
        self.assertEqual(self.reason(), f"fact:{self.fid} 삭제됨 · 시도 2/2 · 포기")
        self.assertNotIn("digest:session:S01", self.served(now_seq=12))

    def test_transition_reasons_are_outside_the_attempt_count(self):
        """
        조용한 쪽 ⑦ — 옛 전파를 켠 전이(`apply_meta`)가 민 키(`전이:` 사유)는 계수 밖이다: 재생성이 세 경계
        연달아 실패해도 경계마다 재시도 · 사유에 «시도» · «포기» 0 · `regen_abandoned` 0 → 넷째 경계 성공.
        옛 전파 측정(`transition_regen_probe`)의 재생성 수를 지키는 자리다.
        심을 위반 (h9): 전이 사유도 세면 셋째 경계 LLM 0 · «포기».
        """
        self.boundary("S01", 7, _Echo())
        saved = memory.TRANSITION_PROPAGATES_DIGEST
        memory.TRANSITION_PROPAGATES_DIGEST = True
        try:
            self.m.apply_meta(CHAT, 8, {"state_delta": {"stage": "다툼중", "affinity": 80}})
        finally:
            memory.TRANSITION_PROPAGATES_DIGEST = saved
        self.assertTrue(self.reason().startswith("전이:"), self.reason())      # 대조의 바닥

        for now in (9, 10, 11):
            st = _Echo(boom={"session:S01"})
            out = self.quiet_boundary(now, st)
            self.assertEqual(self.calls(st), 1, f"경계 {now}: 전이 사유 키를 건너뛰었다")
            self.assertEqual([k for k, _ in out["regen"]["failed"]], ["session:S01"])
            self.assertTrue(self.reason().startswith("전이:"))
            self.assertNotIn("시도", self.reason())
            self.assertNotIn("포기", self.reason())
        self.assertEqual(self.prov("regen_abandoned"), [])
        out = self.quiet_boundary(12, _Echo())
        self.assertEqual(out["regen"], {"ok": ["session:S01"], "failed": []})

    def test_hold_does_not_overwrite_an_existing_summary(self):
        """
        조용한 쪽 — 같은 세션 id로 ①이 다시 불려 실패하면(스케줄러가 한 경계를 두 번 부른 경우) 있는 본문을
        빈 표지로 덮지 않는다 · stale도 안 찍는다 — 오늘의 ① 실패와 같다(`put_session_digest`는 `OR REPLACE`다).
        심을 위반 (h11): 가드를 없애면 본문이 ""가 되고 S01이 서빙에서 빠진다.
        """
        self.boundary("S01", 7, _Echo())
        old = self.body("session:S01")
        out = self.boundary("S01", 8, _Echo(boom={"session:S01"}))
        self.assertEqual(out["session"][0], "failed")
        self.assertEqual(self.body("session:S01"), old)
        self.assertIsNone(self.reason())
        self.assertFalse(out["missing"])


# ── w31f — Q9 (α): 1어근 값의 충돌은 규칙 그대로 · 비용만 K회 (특징짓기) ─────────────────

class TestOneRootValueCollision(_Fixture):
    """
    지운 값 «의사»(어근 1개) · 안 지운 턴 5 «친구가 병원 의사 일을 해»(친구의 직업). 재등장 규칙
    «어근 집합 ⊆ 본문»은 1어근 값에서 «낱말 하나 일치»다(N2) — 턴 5를 옮긴 요약은 늘 거부된다.

    🔴 **의도된 대가 · Q9 (α)** — 규칙을 풀지 않는다(재료 귀속은 재언급 K3도 함께 통과시켜 지운 사실을
       요약으로 되돌린다 · v6 Q2와 함께). 대가: 그 세션 요약은 K회 뒤 포기되어 요약 층에서 빠진다(안 지운
       친구의 말까지). 이 시험은 그 대가가 **상수**(LLM 합 2)임을 못 박는다 — 규칙이 바뀌는 날 운다.
    """
    ROWS = [(1, "user", "안녕 오늘 좀 피곤하다"), (2, "character", "왜, 무슨 일 있었냐"),
            (3, "user", "나 의사야"), (4, "character", "오"),
            (5, "user", "친구가 병원 의사 일을 해"), (6, "character", "좋네")] + TURNS[6:]

    def plants(self):
        self.fid = self._plant("직업", "의사", "지우는 의사다", 3)

    def _assert_abandoned_and_quiet(self, calls):
        self.assertEqual(calls, [1, 1, 0, 0], "1어근 충돌이 K회 뒤 멈추지 않았다 — N2의 비용이 경계마다 난다")
        self.assertEqual(len(self.prov("regen_abandoned")), 1)
        self.assertTrue(self.reason().endswith(" · 포기"), self.reason())
        served = self.served("그때 병원 얘기 기억나?", now_seq=20)
        self.assertNotIn("digest:session:S01", served)                   # 대가: 요약 층에서 빠진다
        for name, text in served.items():
            self.assertNotIn("나 의사야", text, f"{name} 블록에 지운 사실")
        self.assertNotIn("의사", served.get("알고 있는 것", ""))

    def test_collision_at_first_generation_is_abandoned_after_k(self):
        """①에서 시작(경계 전 삭제): 경계마다 S01 LLM [1, 1, 0, 0]. (h1) · (h2) · (h3) · (h4)에서 운다."""
        self.m.delete_item(CHAT, "fact", self.fid)
        calls = []
        for i, now in enumerate((7, 13, 14, 15)):
            st = _Echo()
            if i == 0:
                self.boundary("S01", now, st)
            else:
                self.quiet_boundary(now, st)
            calls.append(self.calls(st))
        self._assert_abandoned_and_quiet(calls)

    def test_collision_at_regeneration_is_abandoned_after_k(self):
        """②에서 시작(경계 뒤 삭제): 첫 경계는 삭제 전이라 성공 → 재생성 [1, 1, 0, 0]. (h2) · (h3) · (h4)에서 운다."""
        self.boundary("S01", 7, _Echo())
        self.assertIn("의사", self.body("session:S01"))                  # 대조의 바닥
        self.m.delete_item(CHAT, "fact", self.fid)
        calls = []
        for now in (8, 9, 10, 11):
            st = _Echo()
            self.quiet_boundary(now, st)
            calls.append(self.calls(st))
        self._assert_abandoned_and_quiet(calls)


# ── w31f — Q10 (c): 가리기 단위는 턴 하나 — 같은 턴의 안 지운 사실은 요약에서 빠진다 (특징짓기) ──

class TestSameTurnMasking(_Fixture):
    """
    턴 3 한 발화에 사실 둘(직업 · 반려동물). 직업만 지운다.

    🔴 **의도된 대가 · Q10 (c)** — 가리기의 단위가 턴이라(사실→턴 대응은 `source_turn_seq` 하나 · 스팬 없음)
       안 지운 «고양이 나비»도 그 세션 요약에서 빠진다. [알고 있는 것] · 검색(색인 복사본)에는 남는다.
       스팬 치환(Q10 (a))은 추출기가 사실→스팬을 주는 날의 일이다. 이 시험은 오늘 초록이고 **부작용을
       숨기지 않는다** — 가리기 단위가 바뀌는 날 운다(= 그 변경이 ADR-010 ② 옆 문장을 고치게 강제한다).
    ⚠️ 이 시험만으로는 과잉 가리기(다른 턴까지)를 못 잡는다 — [알고 있는 것]은 그대로라 조용하다.
       그 변이는 `test_undeleted_fact_survives_regeneration`(턴 5의 «나비»가 재료에 남는가)이 잡는다.
    """
    MIXED = "나 마케팅 회사 대리로 일하고 고양이 나비 키워"
    ROWS = [(1, "user", "안녕 오늘 좀 피곤하다"), (2, "character", "왜, 무슨 일 있었냐"),
            (3, "user", MIXED), (4, "character", "그렇구나"),
            (5, "user", "밖에 비 온다"), (6, "character", "우산 챙겨")] + TURNS[6:]

    def plants(self):
        self.fid = self._plant("직업", "마케팅 회사 대리", "지우는 마케팅 회사 대리로 일한다", 3)
        self.qid = self._plant("반려동물_이름", "고양이 나비", "지우가 고양이 나비를 키운다", 3)

    def test_undeleted_fact_in_the_same_turn_leaves_the_summary_but_stays_known(self):
        self.boundary("S01", 7, _Echo())
        self.assertIn("나비", self.body("session:S01"))                  # 대조의 바닥
        self.m.delete_item(CHAT, "fact", self.fid)
        out = self.quiet_boundary(8, _Echo())
        self.assertEqual(out["regen"], {"ok": ["session:S01"], "failed": []})
        body = self.body("session:S01")
        self.assertNotIn("마케팅", body)
        self.assertEqual(body.count("나비"), 0, "같은 턴의 안 지운 사실이 요약에 남았다 — 가리기 단위가 바뀌었다(Q10)")
        self.assertIn("1개(seq 3)", self.prov("regen_masked")[0][1])
        served = self.served("그때 고양이 나비 얘기 기억나?", now_seq=9)
        self.assertEqual(served["알고 있는 것"].count("고양이 나비"), 1)
        self.assertEqual(served.get("retrieved", "").count("고양이 나비"), 1)
        self.assertNotIn("마케팅", served["알고 있는 것"])


if __name__ == "__main__":
    unittest.main()
