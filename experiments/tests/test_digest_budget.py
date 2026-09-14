# -*- coding: utf-8 -*-
"""
test_digest_budget.py — 5절(부채 예산)의 관측량이 실제로 관측량인가.

## 왜 이 시험이 5절과 따로 있는가

5절은 **종료 코드를 안 바꾼다.** U6이 «이 라운드는 안 고친다»이므로 집행할
계약이 아직 없고, 없는 계약을 종료 코드로 지키는 척하는 것이 이 저장소가
이름으로 금지한 «발화할 수 없는 검사»다.

🔴 **그러면 5절의 수를 누가 지키는가.** 여기다. 이 파일이 지키는 것은
*"`debt`에 상한이 있다"*가 아니라 — 그건 U6이 고칠 때 생긴다 — **5절이 재는
방식이 아직 그 자리를 재고 있는가**다. 구체적으로 셋:

  ① 그림자 판정기가 `due_debts`와 **같은 집합**을 낸다 (안 그러면 ⓒ의 카운트가
     전부 무효다). 심을 위반 셋으로 발화 능력을 함께 시연한다.
  ② 주입 축은 **행 수**지 블록 수가 아니다. `digest` 쪽 `_b_of`를 그대로
     가져오면 이 축은 언제나 1이고 증가를 못 본다.
  ③ 소크 쓰기 경로에 `debt`를 만드는 호출이 **없다**. 이 사실이 바뀌면
     ⓐ의 «분자가 0인 것은 구조다»가 더는 참이 아니고, 그때 U6의 열리는
     조건을 다시 써야 한다 — 이 시험이 그 순간 빨개진다.

## 재현

    PYTHONIOENCODING=utf-8 python -B -m unittest discover -s experiments/tests -p "test_*.py"

720턴을 안 쓴다 — 위 셋은 전부 **구조**에 대한 진술이고, 구조는 작은 픽스처가
더 정확하게 보여준다. 720턴 위의 분포는 5절이 찍는다 (분모가 다르다: 여기는
`TURNS`턴, 거기는 user턴 436개).

🔄 w24d — 4절 집행 확장 둘의 시험도 여기 있다(맨 아래 두 클래스 · Fable 계획 «발견 4» · «C5»):
G19′ 넷째 수(`derivation`의 digest 키 ≤ N+2)와 G17′-a의 `prototype/` 전체 계수. 둘 다 **종료 코드를
바꾸는** 검사라 심은 위반과 조용한 쪽을 함께 둔다.
"""
import contextlib
import io
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import digest_budget as D                                       # noqa: E402
import memory                                                   # noqa: E402
from memory import Memory                                       # noqa: E402

# 🔴 처음에 120으로 잡았다가 **심을 위반 ③(`expire_at=4`)이 조용했다.**
#    120턴 안에서는 어느 행도 `attempt_count`가 3에 닿지 못해 소멸 분기에
#    도달하지 않는다 — 위반이 안 실린 것이 아니라 **픽스처가 그 분기를 안 덮은**
#    것이다. 실측으로 200턴부터 발화하고 300턴에서 세 씨앗 전부가 소멸한다.
#    그래서 아래 `test_픽스처가_세_분기를_전부_덮는다`가 그 덮개를 못박는다 —
#    같은 실패가 다음에는 «조용한 위반»이 아니라 **덮개 미달**로 보인다.
TURNS = 300
# 🔄 wave4 — 씨앗에 spec을 붙이고(판정이 이제 spec을 읽는다) `time`을 둘로 갈랐다: `3d`는
#    트리거 분기를 타고, spec 없는 것은 강등(백오프만)으로 간다. 세션을 10턴으로 줄인
#    이유: 백오프가 **세션 경계**로 세서 소멸까지 경계 18개가 든다(1+3+7+7) — 40턴
#    세션이면 300턴에 경계가 7개라 소멸 분기에 못 닿는다(TURNS=120 때와 같은 덮개 미달).
SEEDS = [("카페 같이 가기로 약속", 0, "session_start", None),
         ("면접 결과 나오면 말해주기로 함", 5, "time", "3d"),
         ("생일에 뭐 할지 말해주기로 함", 7, "time", None),
         ("자기 얘기도 나중에 해주기로 함", 9, "semantic", "서준 얘기가 나오면")]


def mini_corpus(n=TURNS, session_every=10):
    """`_debt_replay`가 읽는 네 키만 갖춘 최소 코퍼스. `turn==1`이 session_start다."""
    return [dict(role="user", seq=i, text="그때 얘기 말인데",
                 turn=1 if i % session_every == 1 else i % session_every)
            for i in range(1, n + 1)]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test-debt-budget-")
        self.corpus = mini_corpus()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class 그림자(Base):
    """① 카운트의 자격은 대조가 준다."""

    def test_그림자가_실_경로와_같은_집합을_낸다(self):
        for late in (0, 1):
            with self.subTest(late=late):
                r = D._debt_replay(self.tmp, f"clean{late}", self.corpus, SEEDS, late=late)
                self.assertEqual(r["mismatch"], 0,
                                 f"그림자가 {r['mismatch']}/{r['n']}턴에서 갈렸다 —"
                                 " 5절 ⓒ의 분기 카운트를 믿을 수 없다")
        # 조용한 쪽만 보고 끝내면 «언제나 0을 내는 대조»와 구별이 안 된다.
        self.assertGreater(sum(r["tot"].values()), 0, "평가가 0회면 대조가 공회전이다")

    def test_픽스처가_세_분기를_전부_덮는다(self):
        """🔴 «위반이 조용하다»와 «픽스처가 그 분기를 안 덮는다»는 다른 사건이다.

        아래 심을 위반 시험이 실패했을 때 어느 쪽인지 이 시험이 먼저 가른다.
        (TURNS=120에서 실제로 겪었다 — 위 상수의 주석이 그 기록이다.)
        """
        r = D._debt_replay(self.tmp, "cover", self.corpus, SEEDS)
        # 🔄 wave4 — 게이트는 경계 행이 **늦게** 오는 판에서만 문다(5절 ⓒ′의 설명).
        rl = D._debt_replay(self.tmp, "cover-late", self.corpus, SEEDS, late=1)
        self.assertEqual(r["tot"]["gate"], 0,
                         "경계가 제때 오는데 게이트가 물었다 — 5절 ⓒ′의 «0회인 이유»가 낡았다")
        for k, t in (("backoff", r), ("gate", rl), ("trigger", r), ("expire", r),
                     ("passed", r)):
            with self.subTest(branch=k):
                self.assertGreater(
                    t["tot"][k], 0,
                    f"`{k}` 분기가 {TURNS}턴 픽스처에서 한 번도 안 물었다 —"
                    " 그 분기에 심는 위반은 발화할 수 없다. TURNS를 늘려라")

    def test_심을_위반_셋이_전부_발화한다(self):
        """🔴 위 0건이 «검사가 없어서 0»이 아님을 셋으로 시연한다."""
        for i, kw in enumerate([dict(backoff_tab=(1, 1, 1)),
                                dict(gate_on=False, late=1),
                                dict(trigger_on=False),
                                dict(expire_at=4)]):
            with self.subTest(plant=kw):
                p = D._debt_replay(self.tmp, f"p{i}", self.corpus, SEEDS, **kw)
                self.assertGreater(
                    p["mismatch"], 0,
                    f"{kw}를 심었는데 대조가 조용하다 — 발화할 수 없는 검사다")


class 주입축(Base):
    """② 세는 대상이 «행»인가 «블록»인가."""

    def _ctx(self, K):
        m = D._debt_db(self.tmp, f"k{K}.db")
        for i in range(K):
            D._plant_debt(m, "나중에 얘기해주기로 함", 0, "time")
        D._end_session(m, 1, 1, 99)   # 🔄 wave4 — 백오프가 경계로 센다. 없으면 0행
        m.db.commit()
        ctx = m.build_context(D.DEBT_CHAT, "오늘 좀 피곤하네", 100,
                              session_start=False)
        m.db.close()
        return ctx

    def test_주입_행_수는_K를_그대로_따라간다(self):
        for K in (1, 2, 5):
            with self.subTest(K=K):
                self.assertEqual(D._debt_lines(self._ctx(K)), K,
                                 "주입 행 수가 K와 갈렸다 — 상한이 생겼거나"
                                 " 관측량이 바뀌었다. 어느 쪽이든 5절 ⓔ를 다시 읽어라")

    def test_블록_수는_축이_아니다(self):
        """`digest` 쪽 «블록 수»를 그대로 가져오면 이 축은 언제나 1이다."""
        ctx = self._ctx(5)
        blocks = sum(1 for b in ctx.blocks if b.name == "debt")
        self.assertEqual(blocks, 1)
        self.assertEqual(D._debt_lines(ctx), 5)
        self.assertNotEqual(blocks, D._debt_lines(ctx),
                            "둘이 같아지면 블록 수로 세도 되고, 5절의 경고가 낡는다")

    def test_주입에_행_수_상한이_없다(self):
        """U6의 본문. 상한이 생기면 이 시험이 빨개지고, 그때 U6을 닫는다."""
        big = D._debt_lines(self._ctx(50))
        self.assertEqual(big, 50,
                         "주입이 50행에서 잘렸다 — **U6이 고쳐졌다는 뜻이다.**"
                         " ADR-016 §미해결 U6과 5절 ⓔ를 함께 갱신하라")


class 소멸(Base):
    """③ `attempt_count >= 3`이 모든 행에 대해 참인가."""

    def test_시도되지_않는_부채는_소멸하지_않는다(self):
        # 🔄 wave4 — 경계도 세션 시작도 안 오는 채팅: 먼저 막는 것은 백오프(경계 0)다.
        m = D._debt_db(self.tmp, "never.db")
        D._plant_debt(m, "카페 같이 가기로 약속", 0, "session_start")
        m.db.commit()
        for seq in range(1, 301):
            m.build_context(D.DEBT_CHAT, "그냥 얘기", seq, session_start=False)
        row = m.db.execute("SELECT status, attempt_count FROM debt").fetchone()
        m.db.close()
        self.assertEqual(row["attempt_count"], 0)
        self.assertEqual(row["status"], "open",
                         "300턴 만에 소멸했다 — 소멸이 attempt_count에서 풀렸다는"
                         " 뜻이고, 5절 ⓕ의 판정이 낡았다")

    def test_시도되는_부채는_세_번_만에_소멸한다(self):
        """🔴 조용한 쪽의 대조. 위가 «영원히 open»이라고 말하려면 이쪽이 소멸해야 한다."""
        m = D._debt_db(self.tmp, "expire.db")
        D._plant_debt(m, "면접 결과 나오면 말해주기로 함", 0, "time")
        m.db.commit()
        for seq in range(1, 301):
            if seq > 1 and seq % 10 == 1:        # 🔄 wave4 — 10턴마다 경계 한 행
                D._end_session(m, seq // 10, seq - 10, seq - 1)
            m.build_context(D.DEBT_CHAT, "그냥 얘기", seq, session_start=False)
        row = m.db.execute("SELECT status, attempt_count FROM debt").fetchone()
        m.db.close()
        self.assertEqual(row["attempt_count"], 3)
        self.assertEqual(row["status"], "expired")


class 쓰기경로(Base):
    """④ ⓐ의 «분자 0은 구조다»가 아직 참인가."""

    def test_add_turn은_meta를_안_받는다(self):
        import inspect
        self.assertNotIn(
            "meta", inspect.signature(Memory.add_turn).parameters,
            "`add_turn`이 meta를 받게 됐다 — 소크 쓰기 경로가 debt를 만들 수"
            " 있게 됐다는 뜻이고, 5절 ⓐ와 U6의 열리는 조건을 다시 써야 한다")

    def test_debt_쓰기는_apply_meta_한_곳뿐이다(self):
        import inspect
        import re
        pat = re.compile(r"INSERT INTO debt\b")
        with open(os.path.join(D.ROOT, "prototype", "memory.py"),
                  encoding="utf-8") as f:
            whole = len(pat.findall(f.read()))
        inside = len(pat.findall(inspect.getsource(Memory.apply_meta)))
        self.assertEqual((whole, inside), (1, 1),
                         "debt 쓰기 자리가 늘었다 — 어디서 늘었는지 확인하고"
                         " 5절 ⓐ를 갱신하라")

    def test_상한_이름이_아직_코드에_없다(self):
        """G19′①②가 요구한 **이름**. 생기면 U6이 닫히는 순간이고, 이 시험이 알린다."""
        for name in ("DEBT_KEEP_MAX", "DEBT_INJECT_MAX"):
            with self.subTest(name=name):
                self.assertFalse(
                    hasattr(memory, name),
                    f"`memory.{name}`이 생겼다 — U6이 닫혔다는 뜻이다."
                    " ADR-016과 5절의 «상한이 없다»를 갱신하라")


# ── 🔄 w24d — 4절 집행 확장 둘 ──────────────────────────────────────────────────

def _forget_before_w20b(m, chat_id, key):
    """w20b 전 `put_session_digest`가 하던 **옛 두 DELETE** — 밀려난 키의 `derivation`은 남긴다."""
    m.db.execute("DELETE FROM stale WHERE chat_id=? AND derived_kind='digest'"
                 " AND derived_key=?", (chat_id, key))
    m.db.execute("DELETE FROM digest_meta WHERE chat_id=? AND kind=?", (chat_id, key))


def _quiet(fn, *a):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return fn(*a)


class G19파생(unittest.TestCase):
    """G19′ 넷째 수 — `derivation`의 digest 키 기수 ≤ N+2 (Fable 발견 4 · w20b 수리를 집행이 본다)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test-g19-deriv-")
        self.n = memory.DIGEST_KEEP_SESSIONS

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _store(self, tag):
        d = os.path.join(self.tmp, tag)
        os.makedirs(d)
        m = D._g19_store(d)
        c = D.g19_prime_counts(m.db, D.G19_CHAT, self.n)
        m.db.close()
        return c

    def test_픽스처는_제품_경로로_채워지고_현행_코드는_조용하다(self):
        """🔴 «발화할 수 없는 검사» 금지 — 넷째 수가 보는 DB는 `put_session_digest` N+3회로 찬다."""
        orig, dropped = Memory.put_session_digest, []

        def spy(m, *a, **kw):
            out = orig(m, *a, **kw)
            dropped.extend(out)
            return out

        with mock.patch.object(Memory, "put_session_digest", spy):
            c = self._store("clean")
        self.assertEqual(len(dropped), 3, "N 상한이 키를 밀어내지 않았다 — ①′가 볼 것이 없다")
        self.assertEqual(c["digest_session"], self.n)
        self.assertEqual(c["derivation_digest"], self.n + 1,
                         "lifetime 1 + 남은 세션 키 N이어야 한다")
        os.makedirs(os.path.join(self.tmp, "clean-enf"))
        self.assertEqual(_quiet(D.enforce_g19, os.path.join(self.tmp, "clean-enf")), [])

    def test_옛_두_DELETE로_되돌리면_넷째_수가_발화한다(self):
        with mock.patch.object(memory, "_forget_digest_key", _forget_before_w20b):
            c = self._store("old")
            os.makedirs(os.path.join(self.tmp, "old-enf"))
            bad = _quiet(D.enforce_g19, os.path.join(self.tmp, "old-enf"))
        self.assertEqual(c["derivation_digest"], self.n + 4,
                         "밀려난 세 키의 등록이 남아 lifetime 1 + 세션 N+3이어야 한다")
        self.assertGreater(c["derivation_digest"], c["cap"])
        # 옛 두 DELETE는 stale · digest_meta를 여전히 지운다 — 우는 것은 ①′ 하나뿐이어야 한다.
        self.assertEqual(len(bad), 1, bad)
        self.assertTrue(bad[0].startswith("G19′①′"), bad)


class G17a전체(unittest.TestCase):
    """G17′-a — 동결 `digest` 쓰기를 `prototype/*.py` 전체에서 센다(`memory.py` 0 · 제품 1)."""

    # 🔴 표 이름을 `INTO` 바로 뒤에 붙여 적지 않는다 — 그 모양이 이 파일에 있으면 G17′-d의 grep이
    #    이 시험을 «digest 쓰기»로 센다(`prototype/tests/test_migrate.py`의 같은 규약). 심는 글자는 조립한다.
    PLANT = "INTO " + "digest"
    # ⚠️ 맨 부분 문자열로 세면 `digest_meta` · `digest_session`까지 문다 — 계수기와 같은 경계(`\b`)로 센다.
    HIT = re.compile(re.escape(PLANT) + r"\b")

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test-g17a-")
        src, self.proto = os.path.join(D.ROOT, "prototype"), os.path.join(self.tmp, "prototype")
        os.makedirs(self.proto)
        for name in (os.path.relpath(os.path.join(a, b), src) for a, _, fs in os.walk(src) for b in fs):
            if name.endswith(".py"):
                os.makedirs(os.path.dirname(os.path.join(self.proto, name)), exist_ok=True) or shutil.copyfile(os.path.join(src, name), os.path.join(self.proto, name))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _read(self, name):
        with open(os.path.join(self.proto, name), encoding="utf-8", newline="") as f:
            return f.read()

    def _write(self, name, src):
        with open(os.path.join(self.proto, name), "w", encoding="utf-8", newline="") as f:
            f.write(src)

    def _append(self, name):
        self._write(name, self._read(name) + f"\n# 심은 위반 — {self.PLANT}\n")

    def _main(self):
        """사본 트리를 뿌리로 `main()` — 위반이면 ollama 앞에서 1. 새면 77(ollama 대신 예외)."""
        with mock.patch.object(D, "ROOT", self.tmp), \
                mock.patch.object(D.llm, "checkpoint", side_effect=RuntimeError("시험: ollama 금지")):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = D.main()
        return rc, buf.getvalue()

    def test_사본_트리는_조용하다(self):
        line, bad = D._g17a_check(self.tmp)
        self.assertEqual(bad, [], line)
        self.assertEqual(D._count_prod_digest_insert(self.tmp)[0],
                         {"summarize.py": ["rewrite_lifetime"]})

    def test_summarize에_두_번째를_심으면_종료_1(self):
        """같은 함수 안 두 번째 건 — 자리가 아니라 **건수**만으로 운다."""
        src = self._read("summarize.py")
        hits = self.HIT.findall(src)
        self.assertEqual(len(hits), 1, "옛 글자가 정확히 1회가 아니다 — 심을 자리가 흔들렸다")
        j = src.index("\n", self.HIT.search(src).start()) + 1
        self._write("summarize.py", src[:j] + f"        # 심은 위반 — 두 번째 {self.PLANT}\n" + src[j:])
        self.assertEqual(D._count_prod_digest_insert(self.tmp)[0]["summarize.py"],
                         ["rewrite_lifetime", "rewrite_lifetime"])
        rc, out = self._main()
        self.assertEqual(rc, 1, out[-600:])
        self.assertIn("G17′-a: prototype/ 제품의 digest INSERT", out)

    def test_memory에_하나를_심으면_종료_1(self):
        self.assertEqual(self.HIT.findall(self._read("memory.py")), [])
        self._append("memory.py")
        rc, out = self._main()
        self.assertEqual(rc, 1, out[-600:])
        self.assertIn("G17′-a: prototype/memory.py의 digest INSERT 1건", out)

    def test_시험_파일과_데모의_글자는_안_센다(self):
        """조용한 쪽 — 그러나 **읽기는 했다**: 뺀 건수가 심은 만큼 는다(표식 0 → ≥1)."""
        before = D._count_prod_digest_insert(self.tmp)[1]
        self._append("tests/test_summarize.py")
        self._write("test_planted.py", f"# {self.PLANT}\n")
        self._append("demos/demo.py")
        prod, skipped = D._count_prod_digest_insert(self.tmp)
        self.assertEqual(skipped, {"시험": before["시험"] + 2, "데모": before["데모"] + 1})
        self.assertEqual(prod, {"summarize.py": ["rewrite_lifetime"]})
        self.assertEqual(D._g17a_check(self.tmp)[1], [])


if __name__ == "__main__":
    unittest.main()
