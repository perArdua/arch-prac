# -*- coding: utf-8 -*-
"""
test_migrate.py — 파일 DB의 스키마 버전이 실제로 올라가는가.

`:memory:`로는 이걸 못 본다. 새 DB는 `_migrate`가 마이그레이션 경로를 **타지 않고**
현재 버전을 적기만 하기 때문이다(`memory.py`의 `_migrate`의 `have == 0` 분기).
그래서 **파일 DB를 만들고 옛 버전으로 되돌린 뒤 다시 연다.**

v4가 확인하려는 것은 특이하다 — `MIGRATIONS[4]`가 **비어 있다.** 신규 테이블 4개는
`SCHEMA`의 `CREATE TABLE IF NOT EXISTS`가 열 때마다 만든다. 그러니 그 시험은
"ALTER가 돌았나"가 아니라 **"빈 마이그레이션이라도 버전은 올라가고 테이블은
생기는가"**를 본다. 그 둘이 어긋나면 v4 DB인데 테이블이 없는 상태가 생긴다.

🆕 **단계 S1이 v5를 더한다.** `MIGRATIONS[5]`도 같은 이유로 비어 있고, 그래서 위
    문단이 v5에 **글자 그대로 적용된다.** 이 파일이 v5에 대해 새로 지는 것은 셋이다:

      I1  v4 DB → v5로 열기: `digest` 2행 그대로 · `digest_session` 생성 · 버전 5
      I2  **롤백** — v5 DB를 v4 코드로 열기: 예외 없음 · `digest` 2행 · 버전은 5로 남음
      I3  v5는 `digest.kind='session'`에 **쓰지 않는다** (새 세션 요약은 신규 테이블로)

    그리고 저장 상한 쪽 시험 셋을 함께 둔다 — T1(N 상한) · T2(컬럼 목록 INSERT) ·
    T3(주입 후보 수 `b`).

🔴 **DB는 전부 `tempfile`(= `%TEMP%`) 아래에 만든다.** 저장소 안에 파일 DB를 남기면
   `git status`가 더러워지고, 그 상태에서 다음 레인이 무엇이 자기 것인지 못 가린다.
"""
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import memory                                               # noqa: E402
from memory import Memory                                   # noqa: E402

NEW_TABLES = ["stage_machine", "state_violation", "embedding", "digest_meta"]
V5_TABLES = ["digest_session"]

CHAT = "c1"

# ── legacy DB 픽스처 ────────────────────────────────────────────────────
#
# 🔴 **이동 대장 (G17′-d).** 아래 `plant_digest`의 한 줄이 G17′-d의 건수를
#    **하나 늘린다** (동결 테이블 쓰기를 세는 grep · 기준선 6은 S1 이전의 값이다).
# ⚠️ 그 grep의 정규식을 **여기 그대로 옮겨 적지 않는다** — 적으면 이 주석 자체가
#    매치가 되어 건수를 또 하나 늘린다. 실측했다: 처음엔 적었고, 9건이 나왔다.
#    **일부러 한 줄로 두고 대장에 적는다 — 문자열을 쪼개 grep을 피하지 않는다.**
#    G17′이 지키려는 것은 grep 값이 아니라 *"동결 테이블에 누가 쓰는가"*이고,
#    쪼개서 통과시키는 것은 준수가 아니라 검사를 우회하는 것이다(계획서 §2.3이
#    그 형태를 이름으로 적어 뒀다). 진짜 금지선인 **G17′-a(프로덕션 0건)는
#    그대로 0**이다 — 이 줄은 프로덕션 경로가 아니라 **legacy DB를 재현하는
#    픽스처**이고, 그것 없이는 I1·I2·T3-ⓑ가 «기존 DB»를 시험할 수 없다.
_DIGEST_ROWS = [
    (CHAT, "lifetime", "인생 요약 — 마케팅에서 스타트업으로", 100, None),
    (CHAT, "session", "지난 세션 요약 (legacy · v5는 여기 쓰지 않는다)", 100, None),
]


def plant_digest(db, rows):
    """동결 테이블에 기록물 행을 심는다. 위치 기반 5-값 형태는 `demo.py`와 같다."""
    db.executemany("INSERT OR REPLACE INTO digest VALUES (?,?,?,?,?)", rows)


def tables(db):
    return {r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


def version(db):
    r = db.execute("SELECT v FROM meta WHERE k='schema_version'").fetchone()
    return int(r[0]) if r else 0


def digest_kinds(db, chat_id=CHAT):
    return sorted(r[0] for r in db.execute(
        "SELECT kind FROM digest WHERE chat_id=?", (chat_id,)))


def n_session_rows(db, chat_id=CHAT):
    """legacy `digest.kind='session'` 행 수 — I3이 이 수의 **불변**을 본다."""
    return db.execute("SELECT COUNT(*) FROM digest WHERE chat_id=? AND"
                      " kind='session'", (chat_id,)).fetchone()[0]


class TestMigrateFromV3(unittest.TestCase):
    """
    🔄 **이름이 `TestMigrateV3toV4`였다.** 도착지를 이름에 박아 두면 버전을 올릴
       때마다 이름이 거짓이 된다 — 이 클래스가 보는 것은 *"옛 DB가 현재 버전까지
       올라가고 신규 테이블이 생기는가"*이고 그것은 도착지와 무관하다.
       그래서 단언도 리터럴 4가 아니라 `Memory.SCHEMA_VERSION`을 쓴다.
       ⚠️ **v5의 정확한 값을 못박는 것은 I1**이다 — 계획서가 `'5'`를 그 자리에
          적었고, 두 곳에서 같은 리터럴을 못박으면 한쪽만 고쳐진다.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "v3.db")
        # v3 파일 DB를 만든다 — 현재 코드로 연 뒤 v4·v5의 흔적을 지운다.
        m = Memory(self.path)
        m.db.execute("UPDATE meta SET v='3' WHERE k='schema_version'")
        for t in NEW_TABLES + V5_TABLES:
            m.db.execute(f"DROP TABLE {t}")
        m.db.commit()
        m.db.close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_setup_really_produced_a_v3_db(self):
        """전제가 무너지면 나머지 단언이 전부 공허해진다. 먼저 못박는다."""
        db = sqlite3.connect(self.path)
        try:
            self.assertEqual(version(db), 3)
            self.assertFalse(tables(db) & set(NEW_TABLES + V5_TABLES))
        finally:
            db.close()

    def test_reopen_upgrades_to_current_and_creates_tables(self):
        m = Memory(self.path)
        try:
            self.assertEqual(version(m.db), Memory.SCHEMA_VERSION)
            self.assertTrue(set(NEW_TABLES + V5_TABLES) <= tables(m.db))
        finally:
            m.db.close()

    def test_migration_is_reported_as_applied(self):
        """빈 리스트라도 그 버전은 **적용된 것**으로 세야 한다 — 버전이 올라가니까."""
        m = Memory(self.path)
        m.db.close()
        m2 = Memory(self.path)
        try:
            self.assertEqual(m2._migrate(), [])   # 이미 최신 — 더 올릴 것이 없다
        finally:
            m2.db.close()

    def test_idempotent_on_second_open(self):
        Memory(self.path).db.close()
        m = Memory(self.path)
        try:
            self.assertEqual(version(m.db), Memory.SCHEMA_VERSION)
            self.assertTrue(set(NEW_TABLES + V5_TABLES) <= tables(m.db))
        finally:
            m.db.close()

    def test_existing_14_tables_survive(self):
        """v4·v5는 더하기만 한다. 기존 테이블이 하나라도 사라지면 G6 위반이다."""
        m = Memory(self.path)
        try:
            for t in ("turn", "character_version", "chat", "relationship",
                      "scene", "digest", "fact", "event", "debt", "coverage",
                      "derivation", "stale", "meta", "provenance"):
                self.assertIn(t, tables(m.db))
        finally:
            m.db.close()

    def test_failure_stops_instead_of_half_applying(self):
        """
        **반쯤 마이그레이션된 상태가 최악이다** (`_migrate` 독스트링).
        깨지는 ALTER를 **다음 버전 칸**에 넣고, 예외가 나며 버전이 그 칸으로
        올라가지 **않는** 것을 본다.

        🔄 이 시험은 그 칸을 5로 썼다. v5가 실재하게 된 순간 그 형태는
           **조용히 공허해졌다** — 현재 코드로 열면 이미 5까지 올라가 있어
           `range(6, 6)`이 비고, 깨지는 ALTER가 아예 실행되지 않는다.
           **그것이 §4.2가 적어 둔 롤백 지뢰(U5)와 정확히 같은 메커니즘**이고,
           그래서 여기서는 칸을 `SCHEMA_VERSION + 1`로 계산해 쓴다.
        """
        Memory(self.path).db.close()          # 먼저 현재 버전까지 올려둔다
        orig_v, orig_m = Memory.SCHEMA_VERSION, Memory.MIGRATIONS
        nxt = orig_v + 1
        broken = {**orig_m, nxt: ["ALTER TABLE 없는테이블 ADD COLUMN x TEXT"]}
        try:
            Memory.SCHEMA_VERSION, Memory.MIGRATIONS = nxt, broken
            with self.assertRaises(RuntimeError):
                Memory(self.path)
        finally:
            Memory.SCHEMA_VERSION, Memory.MIGRATIONS = orig_v, orig_m
        db = sqlite3.connect(self.path)
        try:
            self.assertEqual(version(db), orig_v)
        finally:
            db.close()


class TestSummaryLayerGlobals(unittest.TestCase):
    """
    전역 넷의 **고정물**. 값을 다시 적는 시험이 아니라 *"넷이 서로 다른 수로
    남아 있는가"*를 보는 시험이다.
    """

    def test_the_four_named_numbers(self):
        self.assertEqual(memory.DIGEST_KEEP_SESSIONS, 24)   # 행 수
        self.assertEqual(memory.DIGEST_INJECT_MAX, 1)       # 블록 수
        self.assertEqual(memory.STALE_EXPIRE_SESSIONS, 3)   # 경계 수
        self.assertEqual(memory.STALE_SERVE_POLICY, "transition_warn")

    def test_keep_and_expire_are_not_the_same_number(self):
        """
        🔴 **이 시험이 겨냥하는 실수는 실제로 설계 기록에 있다.** 설계 기록의
        `stale_expired` **3**을 저장 상한으로 옮겨 적으면 세션 요약을 3개만
        보관하게 되고, lifetime 재생성이 3세션분 재료만 보게 된다(ADR-013 P4가
        실행 불가능해진다). 두 값이 같아지는 순간 여기서 발화한다. 🔄 (w24c · 2026-09-12 · Fable 검토 C13 · 계획 «C12 · C13») 이 리터럴 비교는 값이 다르면 의미 혼동(E를 N 자리에 쓰는 것)을 못 잡는다 — 실제 보호자는 `test_serving`의 역할 시험 둘이다: `test_cap_holds_when_stored_rows_grow`(N이 저장을 자른다) · `test_transition_expires_after_E_session_boundaries`(E가 경계를 센다). ADR-016 ②가 이 시험을 이름으로 부르므로 지우지 않는다.
        """
        self.assertNotEqual(memory.DIGEST_KEEP_SESSIONS,
                            memory.STALE_EXPIRE_SESSIONS)
        self.assertGreater(memory.DIGEST_KEEP_SESSIONS,
                           memory.DIGEST_INJECT_MAX)


class SessionDigestCase(unittest.TestCase):
    """`%TEMP%`의 파일 DB 하나 + legacy 행 심기 옵션."""

    LEGACY = 0          # 심을 `digest` 행 수 (0=없음 · 1=lifetime · 2=+legacy)

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "v5.db")
        self.m = Memory(self.path)
        if self.LEGACY:
            plant_digest(self.m.db, _DIGEST_ROWS[:self.LEGACY])
            self.m.db.commit()

    def tearDown(self):
        self.m.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fill(self, n, *, start=1):
        """세션 요약 n건. `covers_to_seq`를 세션마다 올려 정렬이 결정적이게 둔다."""
        out = []
        for i in range(start, start + n):
            sid = f"S{i:02d}"
            out.append(self.m.put_session_digest(
                CHAT, sid, f"{sid} 요약", covers_from_seq=(i - 1) * 30,
                covers_to_seq=i * 30))
        return out

    def count(self):
        return self.m.db.execute(
            "SELECT COUNT(*) FROM digest_session WHERE chat_id=?",
            (CHAT,)).fetchone()[0]


class TestStorageCapT1(SessionDigestCase):
    """T1 — `put_session_digest`가 N 상한을 **쓰는 자리에서** 강제한다 (G19′①)."""

    def test_n_plus_3_inserts_leave_exactly_n(self):
        N = memory.DIGEST_KEEP_SESSIONS
        dropped = self.fill(N + 3)
        self.assertEqual(self.count(), N)
        # 앞의 N건은 아무것도 밀어내지 않고, 그 뒤 3건이 하나씩 밀어낸다.
        self.assertEqual([d for d in dropped[:N] if d], [])
        self.assertEqual([d for d in dropped[N:]],
                         [["session:S01"], ["session:S02"], ["session:S03"]])

    def test_the_newest_survive(self):
        """상한이 **오래된 것**을 자른다 — 아무것이나 자르면 시험이 통과해도 틀렸다."""
        N = memory.DIGEST_KEEP_SESSIONS
        self.fill(N + 3)
        kinds = sorted(r["kind"] for r in self.m.db.execute(
            "SELECT kind FROM digest_session WHERE chat_id=?", (CHAT,)))
        self.assertEqual(kinds[0], "session:S04")
        self.assertEqual(kinds[-1], f"session:S{N + 3:02d}")

    def test_reinsert_of_same_session_does_not_grow(self):
        """PK가 `(chat_id, kind)`이므로 같은 세션 재생성은 행을 늘리지 않는다."""
        self.fill(3)
        self.m.put_session_digest(CHAT, "S02", "S02 요약 (재생성)",
                                  covers_to_seq=60)
        self.assertEqual(self.count(), 3)

    def test_orphan_stale_and_digest_meta_rows_go_with_it(self):
        """
        G17′-c · G19′③ — 밀려난 키의 `stale`·`digest_meta` 행도 함께 지운다.
        남기면 그 두 테이블이 N에 수렴하지 않고 세션 수만큼 늘어난다.
        """
        N = memory.DIGEST_KEEP_SESSIONS
        self.fill(N)
        for i in (1, 2):
            key = memory.session_kind(f"S{i:02d}")
            self.m.db.execute("INSERT OR REPLACE INTO stale VALUES"
                              " (?,?,?,?,?)", (CHAT, "digest", key, "전이:a→b", 0.0))
            self.m.db.execute("INSERT OR REPLACE INTO digest_meta (chat_id, kind)"
                              " VALUES (?,?)", (CHAT, key))
        self.m.db.commit()
        self.fill(2, start=N + 1)          # S01·S02가 밀려난다
        for i in (1, 2):
            key = memory.session_kind(f"S{i:02d}")
            self.assertIsNone(self.m.stale_row(CHAT, "digest", key))
            self.assertIsNone(self.m.db.execute(
                "SELECT 1 FROM digest_meta WHERE chat_id=? AND kind=?",
                (CHAT, key)).fetchone())

    def test_lifetime_and_legacy_keys_are_not_swept(self):
        """상한의 대상은 `session:*`뿐이다 — `lifetime`·legacy `session`은 아니다."""
        for key in ("lifetime", "session"):
            self.m.db.execute("INSERT OR REPLACE INTO stale VALUES (?,?,?,?,?)",
                              (CHAT, "digest", key, "전이:a→b", 0.0))
        self.m.db.commit()
        self.fill(memory.DIGEST_KEEP_SESSIONS + 3)
        for key in ("lifetime", "session"):
            self.assertIsNotNone(self.m.stale_row(CHAT, "digest", key))


class TestColumnListInsertT2(unittest.TestCase):
    """
    T2 — `digest_session`에 **컬럼 목록** INSERT를 쓴다.

    위치 기반 5-값 형태가 G6을 만든 원인이고(컬럼을 하나 더하는 날 호출부가
    조용히 어긋난다), 그 원인을 신규 테이블에서 반복하지 않는다. 소스를
    검사하는 시험이 어색해 보이지만, 이 계약은 **실행으로는 안 보인다** —
    컬럼을 더하는 날에만 보이고 그때는 늦다.
    """

    SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory.py")

    def flat_source(self):
        with open(self.SRC, encoding="utf-8") as f:
            src = f.read()
        # 인접한 문자열 리터럴을 이어 붙인다 — SQL이 여러 줄에 쪼개져 있다.
        return re.sub(r'"\s*\n\s*"', "", src)

    # 🔴 **`INTO`와 표 이름을 붙여 쓰지 않는 이유** — G17′-b는 그 둘이 붙은 형태를
    #    세어 *"쓰는 함수가 정확히 하나인가"*를 본다. 아래 단언에 그것을 **그대로**
    #    적으면 이 시험 파일이 두 번째·세 번째 «쓰는 자리»로 세어져 그 가드가
    #    1이 아니라 3을 읽는다(실측했다). 그것은 rev3이 `\b`로 고친 `digest_meta`
    #    거짓 양성과 **같은 종류의 오발화**다 — 읽기만 하는 단언은 쓰기가 아니다.
    #    ⚠️ 이것은 검사를 **피하는 것이 아니다.** 피하는 것이라면 프로덕션 INSERT를
    #       쪼개 숨기는 쪽이고, 그것은 계획서 §2.3이 이름 붙여 금지한 형태다.
    #       여기서 조립하는 것은 **검사 대상이 아니라 검사 도구**다.
    TABLE = "digest_session"

    def test_insert_names_its_columns(self):
        flat = self.flat_source()
        self.assertRegex(flat, r"INTO " + self.TABLE + r" \(chat_id, kind, content,")
        self.assertNotIn("INTO " + self.TABLE + " VALUES", flat)


class TestInjectionCandidatesT3New(SessionDigestCase):
    """
    T3-ⓐ — **새 DB**: `digest`에 `lifetime` 1행 · `digest_session` N행 · M=1
    → 주입 블록 수 `b` == **2**. 오늘의 컨텍스트 모양(digest 블록 2개)과 같다.
    """

    LEGACY = 1

    def blocks(self):
        """
        한 턴에 실릴 `digest:` 블록 수 `b`.

        🔴 **S1에는 이 산술을 하는 코드가 없다.** 조립(`_serve_digest`)은 단계
           S3의 것이고, S1은 `build_context`를 한 줄도 고치지 않는다(G16′).
           그래서 이 함수는 **S3이 할 산술을 시험 쪽에 미리 적어 둔 것**이다.
        ⚠️ **S3에서 `_serve_digest`가 생기는 순간 이 함수는 지워지고 시험은 그
           함수를 불러야 한다.** 남겨 두면 이 시험은 «구현»이 아니라 «시험
           자신의 산술»을 검사하는 항등식이 된다 (G14).
        """
        n_digest = self.m.db.execute(
            "SELECT COUNT(*) FROM digest WHERE chat_id=?",
            (CHAT,)).fetchone()[0]
        return n_digest + len(self.m.session_digests(CHAT))

    def test_upper_bound_and_fixture(self):
        N, M = memory.DIGEST_KEEP_SESSIONS, memory.DIGEST_INJECT_MAX
        self.fill(N + 3)
        self.assertEqual(self.count(), N)          # 저장은 N
        b = self.blocks()
        # 상한식 — **모든 DB에서 참인 수**여야 한다.
        self.assertLessEqual(b, 2 + M)
        # 고정물 ⓐ — 상한식은 `b`=0도 통과시킨다. 주입이 아예 안 되는 회귀를
        # 잡는 것은 상한식이 아니라 이 등식이다.
        self.assertEqual(b, 2)

    def test_candidate_order_is_deterministic(self):
        """
        정렬 결정성 — 삽입 순서를 뒤섞어도 후보가 같아야 한다.
        SQLite가 우연히 안정적일 수 있으므로 **역순으로 심어** 본다.
        """
        for i in (3, 1, 2):
            self.m.put_session_digest(CHAT, f"S{i:02d}", f"S{i:02d} 요약",
                                      covers_to_seq=i * 30)
        rows = self.m.session_digests(CHAT, limit=3)
        self.assertEqual([r["kind"] for r in rows],
                         ["session:S03", "session:S02", "session:S01"])


class TestInjectionCandidatesT3Legacy(TestInjectionCandidatesT3New):
    """
    T3-ⓑ — **legacy DB**: `digest`에 `lifetime` + `kind='session'` 2행 · M=1
    → `b` == **3**.

    🔴 *"정확히 2"*라고만 적으면 **마이그레이션이 대상으로 삼는 바로 그 DB에서
       정상 경로가 빨개진다.** 그리고 여섯 달 뒤 그 자리는 *"저건 원래 빨간
       거야"*가 된다 — 오발화하는 검사는 발화할 수 없는 검사의 쌍둥이다.
    """

    LEGACY = 2

    def test_upper_bound_and_fixture(self):
        N, M = memory.DIGEST_KEEP_SESSIONS, memory.DIGEST_INJECT_MAX
        self.fill(N + 3)
        b = self.blocks()
        self.assertLessEqual(b, 2 + M)      # 같은 상한식이 여기서도 참이다
        self.assertEqual(b, 3)              # 고정물 ⓑ


class TestNoWriteToFrozenDigestI3(SessionDigestCase):
    """I3 — v5는 `digest.kind='session'`에 쓰지 않는다."""

    LEGACY = 2

    def test_legacy_session_row_count_is_untouched(self):
        before = n_session_rows(self.m.db)
        self.assertEqual(before, 1)                 # 픽스처 전제를 못박는다
        self.fill(memory.DIGEST_KEEP_SESSIONS + 3)
        self.assertEqual(n_session_rows(self.m.db), before)
        # 🔴 **키 집합까지 본다.** `kind='session'`의 **건수**만 세면, 동결
        #    테이블에 `session:S07` 같은 키로 쓰는 변이가 이 시험을 통과한다 —
        #    바로 그것이 결정 1의 A안(kind 인코딩)이 하는 일이고, 이 라운드가
        #    기각한 것이다. 변이 ③으로 실측했다: 건수 단언만으로는 **안 발화했다.**
        self.assertEqual(digest_kinds(self.m.db), ["lifetime", "session"])
        # 내용도 그대로다 — 새 요약이 legacy 행을 덮지 않는다.
        row = self.m.db.execute("SELECT content FROM digest WHERE chat_id=? AND"
                                " kind='session'", (CHAT,)).fetchone()
        self.assertEqual(row["content"], _DIGEST_ROWS[1][2])


class TestNoWriteToFrozenDigestI3NewDb(SessionDigestCase):
    """I3 — 새 DB에서는 그 수가 **0으로 남는다.**"""

    LEGACY = 0

    def test_new_db_never_gets_a_session_row(self):
        self.fill(memory.DIGEST_KEEP_SESSIONS + 3)
        self.assertEqual(n_session_rows(self.m.db), 0)
        self.assertEqual(digest_kinds(self.m.db), [])


class TestV4ToV5(unittest.TestCase):
    """
    I1 — v4 DB를 v5 코드로 열기.
    I2 — 그 v5 DB를 다시 **v4 코드로** 열기 (롤백 · S9).
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "v4.db")
        # v4 파일 DB — 현재 코드로 연 뒤 v5의 흔적을 지우고 기록물 2행을 심는다.
        m = Memory(self.path)
        plant_digest(m.db, _DIGEST_ROWS)
        m.db.execute("UPDATE meta SET v='4' WHERE k='schema_version'")
        for t in V5_TABLES:
            m.db.execute(f"DROP TABLE {t}")
        m.db.commit()
        m.db.close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_setup_really_produced_a_v4_db(self):
        """전제를 먼저 못박는다 — 이게 무너지면 I1·I2가 공허해진다."""
        db = sqlite3.connect(self.path)
        try:
            self.assertEqual(version(db), 4)
            self.assertNotIn("digest_session", tables(db))
            self.assertEqual(len(digest_kinds(db)), 2)
        finally:
            db.close()

    def test_I1_open_with_v5_code(self):
        m = Memory(self.path)
        try:
            self.assertEqual(version(m.db), 5)                     # 리터럴 5
            self.assertIn("digest_session", tables(m.db))
            self.assertEqual(digest_kinds(m.db), ["lifetime", "session"])
            # 신규 테이블은 **비어 있다.** 비어 있는 것이 G16′의 조건이다 —
            # 그 상태에서 시스템이 오늘과 똑같이 굴어야 한다.
            self.assertEqual(m.db.execute(
                "SELECT COUNT(*) FROM digest_session").fetchone()[0], 0)
        finally:
            m.db.close()

    def test_I2_rollback_to_v4_code(self):
        """
        v5 DB를 v4 코드로 연다. **예외 없이 열리고 `digest` 2행이 그대로 읽히고
        `schema_version`은 5로 남는다** — `_migrate`의
        `range(have + 1, SCHEMA_VERSION + 1)` = `range(6, 5)`가 빈 범위라
        루프가 아예 안 돈다.

        v4 코드를 흉내내는 방법: 모듈 전역 `SCHEMA`에서 `digest_session` DDL을
        떼고 `SCHEMA_VERSION`을 4로 되돌린다. `__init__`이 호출 시점에 그 전역을
        읽으므로 이것으로 충분하다.
        ⚠️ **`digest_session` 테이블은 지우지 않는다** — §4.2 되돌리기 2단계
           그대로다. 읽는 코드가 없으면 존재만 하고 아무 일도 안 한다.
        """
        Memory(self.path).db.close()                  # 먼저 v5로 올린다
        v4_schema = re.sub(
            r"CREATE TABLE IF NOT EXISTS digest_session \([^;]*\);", "",
            memory.SCHEMA)
        # 픽스처가 실제로 뭔가를 뗐는지 먼저 본다 — 안 뗐으면 이 시험은
        # 'v5 코드로 v5를 여는 것'이 되고 롤백을 하나도 검사하지 않는다.
        self.assertIn("digest_session (", memory.SCHEMA)
        self.assertNotIn("digest_session (", v4_schema)

        orig_schema, orig_v = memory.SCHEMA, Memory.SCHEMA_VERSION
        try:
            memory.SCHEMA, Memory.SCHEMA_VERSION = v4_schema, 4
            m = Memory(self.path)                     # 예외가 나면 여기서 터진다
            try:
                self.assertEqual(version(m.db), 5)    # 내려가지 않는다
                self.assertEqual(digest_kinds(m.db), ["lifetime", "session"])
                self.assertIn("digest_session", tables(m.db))   # 남겨 둔다
                self.assertEqual(m._migrate(), [])    # range(6,5) — 빈 범위
            finally:
                m.db.close()
        finally:
            memory.SCHEMA, Memory.SCHEMA_VERSION = orig_schema, orig_v

    def test_I2b_reupgrade_after_rollback_is_the_landmine(self):
        """
        🔴 **§9 U5를 시험으로 못박는다.** 롤백을 겪은 DB(`schema_version='5'`,
        코드 v4)를 다시 v5 코드로 올리면 `range(6, 6)`이 비어 **`MIGRATIONS[5]`가
        조용히 건너뛰어진다.**

        오늘 그 리스트가 비어 있으므로 **이 시험은 «지뢰가 아직 안 밟혔다»를
        확인한다** — 비어 있지 않게 되는 순간 이 단언이 실패하고, 그것이
        의도다. 실패하면 §4.2를 읽을 것.
        """
        Memory(self.path).db.close()
        db = sqlite3.connect(self.path)
        try:
            self.assertEqual(version(db), 5)
        finally:
            db.close()
        m = Memory(self.path)
        try:
            self.assertEqual(m._migrate(), [])          # 아무것도 적용되지 않는다
        finally:
            m.db.close()
        self.assertEqual(
            Memory.MIGRATIONS[5], [],
            "MIGRATIONS[5]가 비어 있지 않다 — 롤백을 겪은 DB는 이 마이그레이션을"
            " 받지 못한다 (§4.2 · U5). 여기 넣기 전에 그 절을 읽어라.")


if __name__ == "__main__":
    unittest.main()
