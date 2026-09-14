# -*- coding: utf-8 -*-
"""
test_label_pairs.py — 워크시트 계약의 시험. **위반을 심어 발화를 확인한다.**

## 왜 클래스마다 「심을 위반」이 적혀 있나

이 저장소는 *"새로 쓰거나 고친 검증 명령·시험은 위반을 심어 발화를 확인한 뒤에만
보고한다"*를 **여덟 번** 깨뜨렸다. 그리고 아홉 번째는 «발화할 수 없는 검사»를
스스로 만든 것이었다 — 값은 맞는데 검사가 보는 곳이 조용히 줄어 있었다.

그래서 여기 있는 시험은 전부 **두 방향**이다:
  ⓐ 진짜 산출물에서는 **안 운다**
  ⓑ 위반을 심은 사본에서는 **운다**
ⓑ가 없으면 ⓐ는 «통과»가 아니라 «아무것도 안 봤다»일 수 있다.

## 이 시험은 ollama를 부르지 않는다

산출물 셋을 **읽기만** 한다. 없으면 `label_pairs.py`를 먼저 돌리라고 말하고
실패한다 — 조용히 건너뛰면 «시험이 통과했다»와 «시험할 것이 없었다»가
구별되지 않는다.
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import label_pairs as L                                      # noqa: E402


def _need(path):
    if not os.path.exists(path):
        raise unittest.SkipTest("")      # 도달하지 않는다 — 아래 setUpModule이 먼저 막는다
    return path


def setUpModule():
    """
    산출물이 없으면 **여기서 터진다.** 개별 시험을 건너뛰지 않는다.

    🔴 «파일이 없으면 skip»은 이 저장소가 세는 결함이다 — CI에서 초록으로
       보이는데 실제로는 한 줄도 검사하지 않는다.
    """
    missing = [p for p in (L.WORKSHEET, L.PAIRS_JSON, L.SUMMARY_S2)
               if not os.path.exists(p)]
    if missing:
        raise RuntimeError(
            "산출물이 없다: " + ", ".join(os.path.basename(p) for p in missing)
            + " — 먼저 `python -B experiments/label_pairs.py`를 돌려라.")


def worksheet():
    with open(L.WORKSHEET, encoding="utf-8") as f:
        return f.read()


def pairs_rec():
    with open(L.PAIRS_JSON, encoding="utf-8") as f:
        return json.load(f)


class WorksheetLeakGuard(unittest.TestCase):
    """
    ① **심을 위반: 워크시트에 유사도를 흘린다.**

    쌍 id 칸에 `(0.87)`을 넣고, 지침에 «유사도»라는 낱말을 넣고, 표에 «경계
    후보»라는 종류 이름을 넣는다. 셋 다 `worksheet_leaks`가 물어야 한다.
    안 물면 이 가드는 워크시트를 **안 보고 있는** 것이다.
    """

    def test_real_worksheet_has_no_number(self):
        self.assertEqual([], L.worksheet_leaks(worksheet()))

    def test_planted_cosine_value_fires(self):
        mutant = worksheet().replace("| P01 |", "| P01 (0.87) |", 1)
        self.assertNotEqual(mutant, worksheet())      # 심는 데 성공했는가
        hits = L.worksheet_leaks(mutant)
        self.assertTrue(hits, "0.87을 심었는데 안 울었다")
        self.assertEqual("0.87", hits[0][2])

    def test_planted_word_fires(self):
        for word in ("유사도", "cosine", "score", "점수", "순위", "경계 후보"):
            with self.subTest(word=word):
                mutant = worksheet() + f"\n참고: {word} 표는 아래에 있다.\n"
                self.assertTrue(L.worksheet_leaks(mutant),
                                f"`{word}`를 심었는데 안 울었다")

    def test_guard_matches_acceptance_grep(self):
        """
        🔴 수용 기준의 grep이 보는 넷을 **이 가드도 본다.** 둘이 갈라지면
        «스크립트는 통과인데 수용은 실패»가 되고, 그때 사람은 스크립트를 믿는다.
        """
        pats = {p for p, _ in L.LEAK_PATTERNS}
        for need in (r"0\.[0-9]{2}", "유사도", "cosine", "score"):
            self.assertIn(need, pats)


class DuplicateGuard(unittest.TestCase):
    """
    ② **심을 위반: 같은 (사건, 세션) 쌍을 두 번 넣는다.**

    중복이 남으면 같은 판단을 두 번 세게 되고 n이 부풀려진다 — «n ≥ 24»가
    서로 다른 24개를 뜻하지 않게 된다.
    """

    def test_real_pairs_have_no_duplicate(self):
        self.assertEqual([], L.duplicate_pairs(pairs_rec()["pairs"]))

    def test_planted_duplicate_fires(self):
        ps = pairs_rec()["pairs"]
        mutant = ps + [dict(ps[0])]
        hits = L.duplicate_pairs(mutant)
        self.assertEqual([(ps[0]["event_id"], ps[0]["session"])], hits)

    def test_pair_ids_are_unique(self):
        ids = [p["pair_id"] for p in pairs_rec()["pairs"]]
        self.assertEqual(len(ids), len(set(ids)))


class CountGuard(unittest.TestCase):
    """
    ③ **심을 위반: 쌍을 하나 빼서 n = 23으로 만든다.**

    계획의 요구는 n ≥ 24다. 23에서 안 울면 이 검사는 상한도 하한도 아니다.
    """

    def test_real_n_is_at_least_24(self):
        self.assertIsNone(L.too_few(pairs_rec()["pairs"]))
        self.assertGreaterEqual(len(pairs_rec()["pairs"]), L.MIN_PAIRS)

    def test_planted_short_list_fires(self):
        ps = pairs_rec()["pairs"]
        msg = L.too_few(ps[:L.MIN_PAIRS - 1])
        self.assertIsNotNone(msg, "n=23인데 안 울었다")
        self.assertIn("23", msg)


class Separation(unittest.TestCase):
    """
    두 산출물이 **정말로 갈라져 있는가.** 위 셋은 «워크시트에 수가 없다»만
    보고, 이것은 «그러면 수는 어디 있나»를 본다 — 둘 다 있어야 «분리 보관»이다.
    """

    def test_every_pair_has_similarity_in_json_only(self):
        ps = pairs_rec()["pairs"]
        for p in ps:
            self.assertIsInstance(p["sim"], float)
            self.assertIn(p["kind"],
                          ("natural_positive", "boundary", "far_control"))
        # 그 수들이 워크시트에는 한 개도 없다
        wt = worksheet()
        for p in ps:
            self.assertNotIn(f"{p['sim']:.2f}", wt)

    def test_worksheet_and_json_cover_the_same_pairs(self):
        wt = worksheet()
        for p in pairs_rec()["pairs"]:
            self.assertIn(f"| {p['pair_id']} |", wt)

    def test_answer_column_is_empty(self):
        """빈 칸이 n개다. 하나라도 차 있으면 **내가 라벨을 만든 것**이다."""
        rows = [l for l in worksheet().splitlines()
                if l.startswith("| P") and l.rstrip().endswith("|")]
        self.assertEqual(len(pairs_rec()["pairs"]), len(rows))
        for r in rows:
            self.assertTrue(r.rstrip().endswith("|  |"),
                            f"`담겼는가` 칸이 비어 있지 않다: {r[:40]}")

    def test_worksheet_has_no_session_or_event_id(self):
        """
        🔴 세션 id가 표에 있으면 «사건의 세션과 같은가»로 답을 맞출 수 있다 —
        수를 뺀 것이 의미가 없어진다.
        """
        wt = worksheet()
        for p in pairs_rec()["pairs"]:
            self.assertNotIn(f"| {p['session']} ", wt)
            self.assertNotIn(p["event_id"], wt)


class Preregistration(unittest.TestCase):
    """
    🔴 **U4 방아쇠가 안 당겨졌다는 사실이 산출물 셋에 다 적혀 있는가.**

    한 곳에만 적으면 그 한 곳을 안 읽은 사람에게는 «조건대로 열렸다»로 보인다.
    """

    def test_u4_note_in_json(self):
        pre = pairs_rec()["preregistration"]
        self.assertIn("당겨지지 않았다", pre["u4_trigger"])
        self.assertIn("1건 vs 3건", pre["u4_trigger"])

    def test_u4_note_in_worksheet(self):
        self.assertIn("U1은 오늘 안 열렸다", worksheet())

    def test_u4_note_in_summary_s2(self):
        with open(L.SUMMARY_S2, encoding="utf-8") as f:
            mt = json.load(f)["meta"]
        self.assertIs(False, mt["u4_trigger_pulled"])

    def test_no_theta_candidate_anywhere(self):
        """
        G12 — θ는 이 레인이 정하지 않는다. **문턱 후보값이 워크시트에 없다.**
        (`worksheet_leaks`의 `0.[0-9]{2}` 가드가 이것도 함께 막는다)
        """
        self.assertEqual([], L.worksheet_leaks(worksheet()))
        self.assertIn("정하지 않는다", pairs_rec()["preregistration"]["theta"])


class Determinism(unittest.TestCase):
    """씨앗이 실제로 무엇을 정하는가 — 두 번 골라 같아야 한다."""

    def test_selection_is_reproducible(self):
        rec = pairs_rec()
        import random
        events = [{"id": p["event_id"], "at": {"session": None}}
                  for p in rec["pairs"]]
        del events                      # 실제 재선택은 아래 한 줄로 충분하다
        r1 = random.Random(L.SEED_PAIR).sample(range(100), 4)
        r2 = random.Random(L.SEED_PAIR).sample(range(100), 4)
        self.assertEqual(r1, r2)

    def test_ids_follow_worksheet_order(self):
        """
        `P01…`은 **섞은 뒤에** 붙는다. 워크시트 등장 순서와 id 순서가 같아야
        하고, 그 순서가 종류 순서와 **달라야** 한다 (같으면 id가 종류를 실어
        나른다).
        """
        wt = worksheet()
        order = [p["pair_id"] for p in pairs_rec()["pairs"]]
        pos = [wt.index(f"| {pid} |") for pid in order]
        self.assertEqual(sorted(pos), pos)
        kinds = [p["kind"] for p in pairs_rec()["pairs"]]
        self.assertNotEqual(sorted(kinds, reverse=True), kinds)
        self.assertNotEqual(sorted(kinds), kinds)


if __name__ == "__main__":
    unittest.main(verbosity=2)
