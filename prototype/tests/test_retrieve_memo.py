# -*- coding: utf-8 -*-
"""
test_retrieve_memo.py — 검색·게이트의 **내용 주소 메모**(`memory.py` 끝 절 · w8code · docs/17 검B3).

  R1  키는 요약 «내용»이다 — 행 번호가 같고 내용이 다른 두 DB가 서로의 조각을 받지 않는다
  R2  요약이 제자리에서 바뀌면 다음 조회가 새 내용으로 잰다 (낡을 수 없다는 주장의 직접 관측)
  R3  반환은 `frozenset` — 호출부가 변형할 수 없다
  R4  상한이 있다 (`MEMO_ROWS` · `None`이 아니다)
  R5  토크나이저 자체는 감싸지 않았다 — 여전히 리스트를 새로 돌려준다
  R6  eval 색인에서 요약마다 조각 집합이, 그리고 검색·어휘·게이트가 **메모 전 식**(`set(bigrams(요약))` · 행마다 정규식)과 같다
  R7  삭제는 메모가 따뜻한 채로도 검색·어휘에서 빠진다 — 메모가 «누가 살아 있나»를 기억하지 않는다
      · 조용한 쪽: 안 지운 행은 그대로 꺼내지고 어휘에 남는다

«메모 전 식»은 이 파일이 새로 쓴 채점식이 아니다 — 메모가 대신한 **바로 그 두 표현**(`set(bigrams(s))` ·
`{w[:2] for w in re.findall(...)}`)이고, 끝 절의 이름을 `with` 블록(= `try/finally`)으로 잠시 그 식에 되돌려 대조한다(G13).
DB는 `%TEMP%`(`tempfile`)와 `:memory:`뿐이다.
"""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import memory as M                                          # noqa: E402
from memory import Memory                                   # noqa: E402
import soak                                                 # noqa: E402

ROOT = HERE.parent.parent
Q = "나비 사료"


def old_grams(s):
    return set(M.bigrams(s))                                # 메모 전 `retrieve`의 그 줄


def old_heads(s):
    return {w[:2] for w in re.findall(r"[가-힣]{2,}", s)}   # 메모 전 `_recall_vocab_for`의 그 두 줄


class Restore:
    """끝 절의 두 이름을 잠시 바꿨다가 **객체 동일성으로** 되돌렸는지 본다."""

    def __init__(self, grams=None, heads=None):
        self.new = {"_doc_grams": grams, "_doc_heads": heads}

    def __enter__(self):
        self.saved = {k: getattr(M, k) for k in self.new}
        for k, v in self.new.items():
            if v is not None:
                setattr(M, k, v)

    def __exit__(self, *a):
        for k, v in self.saved.items():
            setattr(M, k, v)
        assert all(getattr(M, k) is v for k, v in self.saved.items())


def fresh(tc):
    m = Memory(":memory:")
    tc.addCleanup(m.db.close)
    soak.seed(m)
    return m


def put(m, summary, imp=0.9):
    return m.db.execute(
        "INSERT INTO event (chat_id, summary, occurred_at, emotional_weight, importance,"
        " source_from_seq) VALUES (?,?,?,?,?,?)", (soak.CHAT, summary, 1, imp, imp, 1)).lastrowid


def view(hits):
    return [(repr(s), r["event_id"], r["summary"]) for s, r in hits]


class ContentKey(unittest.TestCase):
    def test_r1_same_row_id_different_content(self):
        a, b = fresh(self), fresh(self)
        ia, ib = put(a, "나비 사료를 새로 샀다"), put(b, "사료 가게가 문을 닫았다")
        self.assertEqual(ia, ib)                            # 전제: 행 번호가 같다
        ha, _ = a.retrieve(soak.CHAT, Q, 10)
        hb, _ = b.retrieve(soak.CHAT, Q, 10)
        for m, h in ((a, ha), (b, hb)):
            s = m.db.execute("SELECT summary FROM event").fetchone()[0]
            want = M.coverage(set(M.bigrams(Q)), old_grams(s))
            self.assertEqual(len(h), 1)
            self.assertAlmostEqual(h[0][0], M.W_REL * want + M.W_IMP * 0.9, places=12, msg=s)

    def test_r2_in_place_change_is_seen(self):
        m = fresh(self)
        eid = put(m, "사료 가게가 문을 닫았다")
        before, _ = m.retrieve(soak.CHAT, Q, 10)            # 메모를 옛 내용으로 데운다
        m.db.execute("UPDATE event SET summary=? WHERE event_id=?", ("나비 사료를 새로 샀다", eid))
        after, _ = m.retrieve(soak.CHAT, Q, 10)
        with Restore(grams=old_grams):
            ref, _ = m.retrieve(soak.CHAT, Q, 10)
        self.assertEqual(view(after), view(ref))
        self.assertNotEqual(repr(before[0][0]), repr(after[0][0]))   # 전제: 내용이 점수를 바꾼다


class Shape(unittest.TestCase):
    def test_r3_frozen(self):
        self.assertIs(type(M._doc_grams("나비가 사료를 먹었다")), frozenset)
        self.assertIs(type(M._doc_heads("나비가 사료를 먹었다")), frozenset)

    def test_r4_bounded(self):
        self.assertIsInstance(M.MEMO_ROWS, int)
        self.assertGreater(M.MEMO_ROWS, 0)
        for f in (M._doc_grams, M._doc_heads):
            self.assertEqual(f.cache_info().maxsize, M.MEMO_ROWS)

    def test_r5_tokenizer_not_wrapped(self):
        self.assertFalse(hasattr(M.bigrams, "cache_info"))
        a, b = M.bigrams("나비가 왔다"), M.bigrams("나비가 왔다")
        self.assertIsInstance(a, list)
        self.assertIsNot(a, b)


class EvalIdentity(unittest.TestCase):
    """eval 색인(21행) — 검색은 채점 문항 전부, 게이트는 user 턴 전부."""

    @classmethod
    def setUpClass(cls):
        with open(ROOT / "eval" / "corpus" / "corpus.jsonl", encoding="utf-8") as f:
            cls.corpus = [json.loads(l) for l in f]
        import yaml
        with open(ROOT / "eval" / "fact-ledger.yaml", encoding="utf-8") as f:
            ledger = yaml.safe_load(f)
        with open(ROOT / "eval" / "questions.yaml", encoding="utf-8") as f:
            cls.asks = [q["ask"] for q in yaml.safe_load(f)["qa_questions"]]
        cls.tmp = tempfile.mkdtemp(prefix="w8memo_")
        cls.m = Memory(os.path.join(cls.tmp, "e.db"))
        soak.seed(cls.m)
        soak.ingest(cls.m, cls.corpus, ledger, timed=False)
        cls.last = cls.corpus[-1]["seq"]

    @classmethod
    def tearDownClass(cls):
        cls.m.db.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def snap(self):
        m = self.m
        ret = [(view(h), list(r)) for h, r in (m.retrieve(soak.CHAT, a, self.last) for a in self.asks)]
        users = [r["text"] for r in self.corpus if r["role"] == "user"]
        return ret, sorted(m._recall_vocab_for(soak.CHAT)), [m.gate(u, soak.CHAT) for u in users]

    def test_r6_same_as_before_memo(self):
        # 🔄 첫 판은 문항 단위 결과만 비교했다 — 메모 안 토크나이저를 `normalize=False`로 바꾼 변이(w8mut-M4)에
        #    **조용했다**: eval 문항에서는 그 변이가 반환을 한 바이트도 안 바꾼다. 그래서 요약마다 조각 집합을 직접 댄다.
        live = [r[0] for r in self.m.db.execute("SELECT summary FROM event WHERE user_deleted=0")]
        for s in live:
            self.assertEqual(M._doc_grams(s), old_grams(s), s)
            self.assertEqual(M._doc_heads(s), old_heads(s), s)
        now = self.snap()
        with Restore(grams=old_grams, heads=old_heads):
            ref = self.snap()
        self.assertGreater(sum(len(h) for h, _ in ref[0]), 0)       # 전제: 꺼내는 게 있다
        self.assertGreater(sum(ok for ok, _ in ref[2]), 0)          # 전제: 게이트가 어휘로 발화한다
        self.assertEqual(now[0], ref[0], "검색 반환")
        self.assertEqual(now[1], ref[1], "게이트 어휘")
        self.assertEqual(now[2], ref[2], "게이트 판정")


class DeleteWhileWarm(unittest.TestCase):
    GONE = "지우는 마케팅 회사 대리로 일한다"
    STAY = "지우가 고양이 나비를 키운다"

    def test_r7_delete_leaves_memo_irrelevant(self):
        m = fresh(self)
        eg, es = put(m, self.GONE), put(m, self.STAY)
        for q in ("마케팅 회사 대리", "고양이 나비"):
            m.retrieve(soak.CHAT, q, 10)                    # 두 행 모두 메모에 들어간다
        v0 = m._recall_vocab_for(soak.CHAT)
        self.assertIn("마케", v0)                           # 전제
        m.delete_item(soak.CHAT, "event", eg)
        h0 = M._doc_grams.cache_info().hits
        M._doc_grams(self.GONE)
        self.assertEqual(M._doc_grams.cache_info().hits, h0 + 1)     # 전제: 지운 요약이 아직 메모에 있다
        h, _ = m.retrieve(soak.CHAT, "마케팅 회사 대리", 10)
        self.assertNotIn(self.GONE, [r["summary"] for _, r in h])
        self.assertNotIn("마케", m._recall_vocab_for(soak.CHAT))
        # 조용한 쪽 — 안 지운 행
        h2, _ = m.retrieve(soak.CHAT, "고양이 나비", 10)
        self.assertIn(self.STAY, [r["summary"] for _, r in h2])
        self.assertIn("나비", m._recall_vocab_for(soak.CHAT))


if __name__ == "__main__":
    unittest.main()
