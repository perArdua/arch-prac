# -*- coding: utf-8 -*-
"""
test_memo_multiroom.py — `memo_multiroom.py`의 **계산부**를 시험한다(적중률·지연 값 자체는 시험하지 않는다).

지키는 것:
  · 꼬리표가 두 토크나이저에서 사라진다 — 메모 **키만** 갈리고 조각·앞 2글자는 틀과 같다.
  · 공유 몫 · 방 접근 순서가 정의대로이고 결정적이다.
  · sim(정수 키 LRU)이 **독립 참조 구현**(OrderedDict LRU)과 같다 · 순환의 경계 법칙(R·D ≤ C ⇔ 방 사이 적중).
  · 실측 칸의 (적중, 빗나감)이 sim과 정수로 같다(eval 틀 21행 · 작은 상한) · 실제 코드가 흘리는 키 순서 = 구성.
  · 끝 절 두 이름 바꾸기가 예외에도 복원된다(G13) · `MEMO_ROWS` 다시 묶기로는 상한이 안 바뀐다.

    PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s experiments/tests -p "test_memo_multiroom.py" -v
"""
import collections
import random
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import memo_multiroom as MM  # noqa: E402

M = MM.M
RS = MM.RS


def lru_reference(keys, cap, warm_at):
    """독립 참조 — OrderedDict LRU. (잰 구간의 적중, 빗나감)."""
    od, hit, miss = collections.OrderedDict(), 0, 0
    for i, k in enumerate(keys):
        if k in od:
            od.move_to_end(k)
            hit += i >= warm_at
        else:
            miss += i >= warm_at
            od[k] = None
            if len(od) > cap:
                od.popitem(last=False)
    return hit, miss


class FakeSet:
    """방마다 서로 다른 D개 키(방 안 중복 없음) — 경계 법칙용."""

    def __init__(self, d, dup=0):
        self.d, self.dup = d, dup

    def seq(self, w, k):
        base = list(range(self.d)) + list(range(self.dup))       # 앞 dup개가 한 번 더 — 방 안 중복
        return [i * 1000 + k + 1 for i in base]


class TagTest(unittest.TestCase):
    def test_alphabet_is_nonword(self):
        self.assertEqual(len(MM.TAG_ALPHABET), 10)
        self.assertFalse(any(re.match(r"\w", c) for c in MM.TAG_ALPHABET))

    def test_tags_distinct_same_length(self):
        tags = [MM.tag(k) for k in range(1000)]
        self.assertEqual(len(set(tags)), 1000)
        self.assertEqual({len(t) for t in tags}, {4})

    def test_tag_vanishes_in_both_tokenizers(self):
        corpus, ledger, _ = RS.load_eval()
        tmp = tempfile.mkdtemp(prefix="w11a_t_")
        try:
            tpl = RS.template_rows(tmp, corpus, ledger)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        extra = ["3월 12일에 만났다", "지우가 회사에서 크게 깨지고 새벽에 연락함.", "a", "가", "고양이 나비랑 놀았어요!"]
        self.assertEqual(MM.tag_invariant([r["summary"] for r in tpl] + extra), [])

    def test_invariance_check_can_fire(self):
        saved = MM.TAG_ALPHABET
        try:
            MM.TAG_ALPHABET = "0123456789"                         # 낱말 문자 — 조각에 남는다
            self.assertTrue(MM.tag_invariant(["가나다라"]))
        finally:
            MM.TAG_ALPHABET = saved


class SharedOrderTest(unittest.TestCase):
    def test_share_fraction(self):
        d = [f"요약{i}" for i in range(200)]
        self.assertEqual(MM.shared_set(d, 0.0), frozenset())
        self.assertEqual(MM.shared_set(d, 1.0), frozenset(d))
        for s in (0.25, 0.5, 0.75):
            self.assertEqual(len(MM.shared_set(d, s)), round(s * 200))
        self.assertEqual(MM.shared_set(d, 0.5), MM.shared_set(list(reversed(d)), 0.5))   # 입력 순서 무관
        self.assertTrue(MM.shared_set(d, 0.25) < MM.shared_set(d, 0.5))                    # 몫이 커지면 포함

    def test_room_keys_disjoint_at_zero_identical_at_one(self):
        tpl = [dict(summary=f"요약{i % 30}", importance=0.9, emotional_weight=0.0) for i in range(40)]
        z = MM.RoomSet(tpl, 40, 0.0)
        self.assertFalse(set(z.strings("h", 0)) & set(z.strings("h", 1)))
        self.assertFalse(set(z.seq("h", 0)) & set(z.seq("h", 1)))
        o = MM.RoomSet(tpl, 40, 1.0)
        self.assertEqual(o.strings("h", 0), o.strings("h", 5))
        self.assertEqual(o.seq("h", 0), o.seq("h", 5))
        self.assertEqual(z.stats("h")[:3], (40, 30, 0))
        self.assertAlmostEqual(z.stats("h")[3], 10 / 40)

    def test_orders(self):
        self.assertEqual(MM.room_order("순환", 3, 7, "k"), [0, 1, 2, 0, 1, 2, 0])
        a = MM.room_order("균등 무작위", 5, 500, "k")
        self.assertEqual(a, MM.room_order("균등 무작위", 5, 500, "k"))
        self.assertEqual(set(a), set(range(5)))
        hot = MM.room_order("한 방 몰림", 6, 20000, "k")
        self.assertAlmostEqual(hot.count(0) / len(hot), MM.HOT_P, delta=0.02)
        self.assertEqual(set(hot), set(range(6)))
        self.assertEqual(MM.room_order("한 방 몰림", 1, 10, "k"), [0] * 10)

    def test_cliff_word_boundary(self):
        self.assertEqual(MM.cliff_word(MM.CLIFF_HIT), "절벽")
        self.assertEqual(MM.cliff_word(MM.CLIFF_HIT + 1e-9), "—")

    # 🔄 (w13cliff · 사후 정정) 새 규칙 — 이득 g = h − d. 옛 규칙과 사전 등록은 그대로다.
    def test_prereg_threshold_untouched(self):
        self.assertEqual(MM.CLIFF_HIT, 0.10)
        self.assertEqual(MM.CLIFF_GAIN, 0.10)
        mun = [p for p in MM.PREREG if p[0] == "문턱"]
        self.assertEqual(len(mun), 1)
        self.assertTrue(mun[0][1].startswith("h ≤ 0.10 → «절벽»"), mun[0][1][:20])

    def test_cliff_gain_word(self):
        self.assertEqual(MM.cliff_word(0.114), "—")                  # 옛: 수준만 본다 — 0.114는 «절벽 아님»
        self.assertEqual(MM.cliff_gain_word(0.114, 0.110), "절벽")   # 새: g ≈ 0.004 → 절벽
        self.assertEqual(MM.cliff_gain_word(0.114, 0.0), "—")
        self.assertEqual(MM.cliff_gain_word(0.647, 0.543), "—")     # g 0.104
        self.assertEqual(MM.cliff_gain_word(MM.CLIFF_GAIN, 0.0), "절벽")
        self.assertEqual(MM.cliff_gain_word(MM.CLIFF_GAIN + 1e-9, 0.0), "—")
        self.assertEqual(MM.cliff_gain_word(0.5, None), "판정 불가")

    def test_first_cliffs_old_and_new(self):
        h = {1: 1.0, 2: 0.95, 3: 0.114, 4: 0.110}
        self.assertEqual(MM.first_cliffs(h, 0.110, (1, 2, 3, 4)), (None, 3))   # 옛은 못 잡고 새는 R=3
        lo = {1: 1.0, 2: 0.05, 3: 0.02}
        self.assertEqual(MM.first_cliffs(lo, 0.0, (1, 2, 3)), (2, 2))
        self.assertEqual(MM.first_cliffs(h, 0.0, (1, 2, 3, 4)), (None, None))


class SimTest(unittest.TestCase):
    def test_sim_matches_reference_lru(self):
        rng = random.Random(7)
        for cap in (1, 3, 17, 100):
            fs = FakeSet(40, dup=5)
            for order_name in MM.ORDERS:
                order = MM.room_order(order_name, 6, 60, f"t{cap}{order_name}")
                n_warm = 17
                got = MM.sim_cell(fs, order, n_warm, cap)["g"]
                keys, warm_at = [], None
                for i, r in enumerate(order):
                    if i == n_warm:
                        warm_at = len(keys)
                    keys += fs.seq("g", r)
                self.assertEqual(got, lru_reference(keys, cap, warm_at), (cap, order_name))
        self.assertTrue(rng)

    def test_cold_sim_matches_reference(self):
        # 🔄 (w13cliff) 새 규칙의 d — 같은 상한의 빈 LRU에 방 하나를 한 번 흘린 적중. 상한이 작으면 방 안 중복도 빗나간다.
        fs = FakeSet(40, dup=5)
        for cap in (1, 3, 40, 44, 45, 100):
            hit, miss = lru_reference(fs.seq("g", 0), cap, 0)
            self.assertEqual(MM.cold_sim(fs, "g", cap), hit / (hit + miss), cap)
        self.assertEqual(MM.cold_sim(fs, "g", 100), 5 / 45)
        self.assertEqual(MM.cold_sim(fs, "g", 3), 0.0)

    def test_rr_boundary_law(self):
        d = 50
        for r in (1, 2, 4, 7):
            fs = FakeSet(d)
            order = MM.room_order("순환", r, MM.warmup(r) + 30, "law")
            fit = MM.sim_cell(fs, order, MM.warmup(r), r * d)["g"]           # R·D = C → 전부 적중
            over = MM.sim_cell(fs, order, MM.warmup(r), r * d - 1)["g"]      # R·D = C + 1 → 전부 빗나감(방 안 중복 0)
            self.assertEqual(fit[1], 0, r)
            self.assertEqual(over[0], 0, r)
        # 🔄 첫 판은 «경계 너머의 바닥 = 방 안 중복»으로 (300, 1500)을 기대했다 — 틀린 산수였다. 두 번 나오는 키(앞 10개)는
        #    **마지막** 출현(훑기 끝)에서 다음 방문의 첫 출현까지 재므로 사이의 서로 다른 키가 9−i + 2×50 + i = 109개뿐이다
        #    → C = 149에서는 방 사이에서도 맞는다(턴마다 20 적중 · 40 빗나감). C ≤ 109면 그것도 빗나가 바닥이 방 안 중복이 된다.
        dup = FakeSet(d, dup=10)
        order = MM.room_order("순환", 3, MM.warmup(3) + 30, "law")
        self.assertEqual(MM.sim_cell(dup, order, MM.warmup(3), 3 * d - 1)["g"], (20 * 30, 40 * 30))
        self.assertEqual(MM.sim_cell(dup, order, MM.warmup(3), 110)["g"], (20 * 30, 40 * 30))   # 적중 ⇔ 사이 키 109 < C
        self.assertEqual(MM.sim_cell(dup, order, MM.warmup(3), 109)["g"], (10 * 30, 50 * 30))


class SwapTest(unittest.TestCase):
    def test_restores_on_exception(self):
        g0, h0 = M._doc_grams, M._doc_heads
        with self.assertRaises(ZeroDivisionError):
            with MM.Swap(*MM.memo_pair(3)):
                self.assertIsNot(M._doc_grams, g0)
                1 / 0
        self.assertIs(M._doc_grams, g0)
        self.assertIs(M._doc_heads, h0)

    def test_nested_restores_outer(self):
        g0 = M._doc_grams
        outer = MM.memo_pair(5)
        with MM.Swap(*outer):
            with MM.Swap(*MM.memo_pair(2)):
                pass
            self.assertIs(M._doc_grams, outer[0])
        self.assertIs(M._doc_grams, g0)

    def test_memo_rows_rebinding_does_not_resize(self):
        before, during, fresh, restored = MM.cap_is_fixed()
        self.assertEqual(before, M.MEMO_ROWS)
        self.assertEqual(during, (M.MEMO_ROWS, M.MEMO_ROWS))
        self.assertEqual(fresh, 7)
        self.assertTrue(restored)
        self.assertEqual(MM.memo_pair(11)[1].cache_info().maxsize, 11)


class RealVsSimTest(unittest.TestCase):
    """eval 틀(21행)로 방을 만들어 실제 코드 경로의 적중을 sim과 정수로 대조한다."""

    @classmethod
    def setUpClass(cls):
        corpus, ledger, qs = RS.load_eval()
        cls.asks = [q["ask"] for q in qs]
        cls.last = corpus[-1]["seq"]
        cls.tmp = tempfile.mkdtemp(prefix="w11a_rv_")
        tpl = RS.template_rows(cls.tmp, corpus, ledger)
        cls.sets, cls.rooms = {}, {}
        for s in (0.0, 0.5):
            rs = cls.sets[s] = MM.RoomSet(tpl, len(tpl), s)
            cls.rooms[s] = {k: MM.build_room(f"{cls.tmp}/r{s}_{k}.db", rs, k) for k in range(5)}

    @classmethod
    def tearDownClass(cls):
        for rooms in cls.rooms.values():
            for m in rooms.values():
                m.db.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_recorded_sequence_is_the_construction(self):
        for s, rs in self.sets.items():
            self.assertEqual(MM.check_rooms(rs, self.rooms[s], self.asks, self.last, all_asks=True), [])

    def test_real_equals_sim(self):
        rs = self.sets[0.0]
        dg, dh = rs.stats("g")[1], rs.stats("h")[1]
        for s in (0.0, 0.5):
            for order_name in MM.ORDERS:
                for cap in (dg, 2 * dg, 2 * dg + 1, 3 * dh, 4 * dh + 3):
                    for r in (1, 3, 5):
                        key = f"t|{s}|{order_name}|{cap}|{r}"
                        order = MM.room_order(order_name, r, MM.warmup(r) + 12, key)
                        hm, lat, hc = MM.real_cell(self.rooms[s], order, MM.warmup(r), cap, self.asks, self.last,
                                                   random.Random(key))
                        self.assertEqual(hm, MM.sim_cell(self.sets[s], order, MM.warmup(r), cap), key)
                        for w in "gh":                                                  # 🔄 (w13cliff) 짝 콜드 d = sim 콜드 d
                            self.assertEqual(MM.cold_sim(self.sets[s], w, cap), hc[w], (key, w))
                        self.assertEqual(len(lat["turn"]), 12)
                        self.sets[s].forget()

    def test_real_boundary_law(self):
        rs = self.sets[0.0]
        _, dg, _, fg = rs.stats("g")
        for r in (2, 4):
            order = MM.room_order("순환", r, MM.warmup(r) + 10, "law")
            hm, _, hc = MM.real_cell(self.rooms[0.0], order, MM.warmup(r), r * dg, self.asks, self.last, random.Random(1))
            self.assertEqual(hm["g"][1], 0)                               # R·D_τ = C → 검색 메모 전부 적중
            hm, _, hc = MM.real_cell(self.rooms[0.0], order, MM.warmup(r), r * dg - 1, self.asks, self.last,
                                     random.Random(1))
            self.assertAlmostEqual(MM.rate(hm["g"]), fg)                   # 한 칸 모자라면 바닥 = 방 안 중복
            self.assertAlmostEqual(hc["g"], fg)                            # 짝 콜드의 적중도 같은 바닥


if __name__ == "__main__":
    unittest.main()
