# -*- coding: utf-8 -*-
"""
test_response_quality.py — 응답 수준 실험의 채점 규칙과 **재설계가 더한 것들**의 시험.

## 🔴 이 파일의 규율

*"새로 쓰거나 고친 검증 명령은 **위반을 심어 발화를 확인한 뒤에만** 보고한다.
열거는 검증이 아니다."*

그래서 여기 있는 것의 대부분은 **음성 대조**다 — 규칙이 잡아야 하는 것을 손으로
만들어 넣고, 실제로 잡히는지 본다. 특히:

  · 오답을 말한 답변은 **반드시** `오답 진술`로 잡혀야 한다
  · 정답을 말한 답변은 **반드시** `정답`으로 잡혀야 한다
  · 빈 답·회피는 **둘 다 아니어야** 한다

이 셋이 이 실험의 전부다. 셋 중 하나라도 조용히 통과하면 108건의 생성이
아무것도 재지 않은 것이 된다.

⚠️ **여기서 쓰는 문자열은 손으로 만든 fixture다.** 진짜 대장 값을 쓰는 시험은
   아래 `TestLedgerWiring`에 따로 있고, 그것은 `eval/`을 **읽기만** 한다.
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "..", "prototype"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import memory as M                                           # noqa: E402
import precision as P                                        # noqa: E402
import probe_set as PS                                       # noqa: E402
import response_quality as RQ                                # noqa: E402


# 손으로 만든 fixture — 대장의 모양을 흉내내되 대장 값이 아니다.
GOLD = {"스타트업 프로덕트 매니저", "지우는 스타트업으로 이직함"}
DIST = {"코코", "친구 민지네 고양이 이름은 코코"}


class TestNegativeControls(unittest.TestCase):
    """규칙이 **발화하는가.** 셋이 이 실험의 계측기 전부다."""

    def test_오답을_말하면_오답_진술로_잡힌다(self):
        # 🔴 음성 대조 ① — 오주입을 그대로 받아 말한 답변.
        a = "네 고양이 이름은 코코다. 민지네 고양이였지."
        r = RQ.classify(a, GOLD, DIST)
        self.assertTrue(r["dist"], "오답을 말했는데 오답 진술로 안 잡혔다")
        self.assertFalse(r["gold"])
        self.assertEqual(r["bucket"], "오답")

    def test_정답을_말하면_정답으로_잡힌다(self):
        # 🔴 음성 대조 ② — 정답 문자열을 그대로 담은 답변.
        a = "너 스타트업 프로덕트 매니저잖아. 잊었냐."
        r = RQ.classify(a, GOLD, DIST)
        self.assertTrue(r["gold"])
        self.assertFalse(r["dist"])
        self.assertEqual(r["bucket"], "정답")

    def test_빈_답과_회피는_정답도_오답도_아니다(self):
        # 🔴 음성 대조 ③ — 무응답이 만점으로도 오답으로도 새면 안 된다.
        for a in ("", "   ", "모르겠다.", "기억 안 나는데.",
                  "그건 맥락에 정보가 없다."):
            with self.subTest(answer=a):
                r = RQ.classify(a, GOLD, DIST)
                self.assertFalse(r["gold"], f"{a!r}가 정답으로 샜다")
                self.assertFalse(r["dist"], f"{a!r}가 오답으로 샜다")
                self.assertEqual(r["bucket"], "무응답")

    def test_둘_다_말하면_둘_다_잡힌다(self):
        a = "너는 스타트업 프로덕트 매니저고, 고양이는 코코다."
        r = RQ.classify(a, GOLD, DIST)
        self.assertTrue(r["gold"])
        self.assertTrue(r["dist"])
        self.assertEqual(r["bucket"], "정답+오답")

    def test_아무것도_아닌_말은_기타다(self):
        # 회피 표지도 없고 사실도 없는 답 — 무응답으로 세면 회피율이 부풀려진다.
        r = RQ.classify("밥은 먹었냐.", GOLD, DIST)
        self.assertEqual(r["bucket"], "기타")


class TestMasking(unittest.TestCase):
    """최장 일치 우선 마스킹 — 짧은 문자열이 긴 문자열 안에서 세어지면 안 된다."""

    def test_나비넥타이는_나비로_세어지지_않는다(self):
        # 정답 '나비'가 오답 '나비넥타이'의 부분문자열이다. 긴 쪽이 먼저 먹어야 한다.
        g, d, hit = RQ.statements("선물로 나비넥타이 샀다며.", {"나비"}, {"나비넥타이"})
        self.assertFalse(g, "'나비넥타이'가 정답 '나비'로 잘못 세어졌다")
        self.assertTrue(d)
        self.assertEqual(hit["dist"], ["나비넥타이"])

    def test_짧은_정답_자체는_여전히_잡힌다(self):
        g, d, _ = RQ.statements("고양이 이름은 나비다.", {"나비"}, {"나비넥타이"})
        self.assertTrue(g)
        self.assertFalse(d)

    def test_마스킹이_길이를_보존해_없던_일치를_안_만든다(self):
        # 🔴 이 시험은 **순서까지 맞아야** 발화한다. 마스킹은 나중에 검사되는
        #    문자열에만 영향을 주고, 검사 순서는 길이 내림차순이다. 그래서
        #    **정답이 오답보다 짧아야** 이 결함이 재현된다 — 처음 쓴 판은 정답이
        #    먼저 검사돼서 결함을 심어도 통과했다(변이 ③이 살아남아 들켰다).
        #    'AXYZB'에서 'XYZ'를 길이 0으로 지우면 'A'와 'B'가 붙어 없던 'AB'가 생긴다.
        g, d, _ = RQ.statements("AXYZB", {"AB"}, {"XYZ"})
        self.assertFalse(g, "마스킹이 양옆을 붙여 없던 정답을 만들었다")
        self.assertTrue(d)

    def test_마스킹이_길이를_보존해_없던_오답을_안_만든다(self):
        # 같은 결함의 반대 방향 — 정답을 지우다가 없던 오답을 만들면 안 된다.
        g, d, _ = RQ.statements("코XYZ코", {"XYZ"}, {"코코"})
        self.assertTrue(g)
        self.assertFalse(d, "마스킹이 양옆을 붙여 없던 오답을 만들었다")

    def test_정답과_오답이_겹치면_터진다(self):
        with self.assertRaises(ValueError):
            RQ.statements("아무거나", {"코코"}, {"코코"})

    def test_같은_길이_동점은_결정적이다(self):
        # 순서가 실행마다 달라지면 같은 답변이 다른 갈래로 간다.
        for _ in range(5):
            _, _, hit = RQ.statements("가가 나나", {"가가"}, {"나나"})
            self.assertEqual((hit["gold"], hit["dist"]), (["가가"], ["나나"]))


class TestDiscriminableFilter(unittest.TestCase):
    """판별 가능성 필터 — 정답의 진부분문자열인 오답 문자열은 버린다."""

    def test_스타트업은_버려진다(self):
        keep, dropped = RQ.discriminable({"스타트업", "코코"}, GOLD)
        self.assertNotIn("스타트업", keep)
        self.assertIn("코코", keep)
        self.assertEqual([d for d, _ in dropped], ["스타트업"])

    def test_반대_방향은_안_버린다(self):
        # 정답 '나비'가 오답 '나비넥타이'의 부분문자열인 경우 — 마스킹이 가른다.
        keep, dropped = RQ.discriminable({"나비넥타이"}, {"나비"})
        self.assertEqual(keep, {"나비넥타이"})
        self.assertEqual(dropped, [])

    def test_필터를_안_거치면_정답_의역이_오답으로_뒤집힌다(self):
        # 🔴 이 시험이 필터의 **존재 이유**다. 실측으로 본 생성 하나의 재현이다.
        para = "너 스타트업에서 제품 관리하잖아."
        raw = {"스타트업"}
        g, d, _ = RQ.statements(para, GOLD, raw)
        self.assertFalse(g)
        self.assertTrue(d, "전제가 깨졌다 — 필터 없이도 안 뒤집힌다면 필터가 불필요하다")
        keep, _ = RQ.discriminable(raw, GOLD)
        g2, d2, _ = RQ.statements(para, GOLD, keep)
        self.assertFalse(d2, "필터를 거쳤는데도 정답 의역이 오답으로 잡힌다")


class TestSignTest(unittest.TestCase):
    """부호검정과 **이 n에서 달성 가능한 최소 p**."""

    def test_한쪽으로_완전히_쏠린_5쌍(self):
        pairs = [(1, 0)] * 5 + [(1, 1)] * 13
        b, c, p, minp = RQ.sign_test(pairs)
        self.assertEqual((b, c), (5, 0))
        self.assertAlmostEqual(p, 2 * 0.5 ** 5)      # 0.0625
        self.assertAlmostEqual(minp, 2 * 0.5 ** 5)   # 쏠렸으므로 p == minp

    def test_불일치_2쌍이면_유의가_불가능하다(self):
        # 🔴 이것이 `min_p`를 병기하는 이유다 — p=0.5는 "차이 없음"이 아니라
        #    "이 쌍 수로는 어떤 결과도 0.05 아래로 못 간다"이다.
        b, c, p, minp = RQ.sign_test([(1, 0), (0, 1)] + [(0, 0)] * 16)
        self.assertEqual((b, c), (1, 1))
        self.assertGreater(minp, 0.05)

    def test_불일치가_없으면_검정할_것이_없다(self):
        b, c, p, minp = RQ.sign_test([(1, 1), (0, 0)])
        self.assertEqual((b, c, p, minp), (0, 0, 1.0, 1.0))

    def test_n18_전부_불일치일_때의_하한(self):
        b, c, p, minp = RQ.sign_test([(1, 0)] * 18)
        self.assertAlmostEqual(minp, 2 * 0.5 ** 18)
        self.assertLess(minp, 1e-5)

    def test_양측이라_대칭이다(self):
        _, _, p1, _ = RQ.sign_test([(1, 0)] * 7)
        _, _, p2, _ = RQ.sign_test([(0, 1)] * 7)
        self.assertAlmostEqual(p1, p2)


class TestGenKey(unittest.TestCase):
    """캐시 키 — 모델이 바뀌면 옛 답이 재사용되면 안 된다."""

    def test_다이제스트가_다르면_키가_다르다(self):
        a = RQ.gen_key("같은 프롬프트", {"digest": "aaa", "ollama": "0.33.3"})
        b = RQ.gen_key("같은 프롬프트", {"digest": "bbb", "ollama": "0.33.3"})
        self.assertNotEqual(a, b)

    def test_같은_조건이면_같은_키다(self):
        rt = {"digest": "aaa", "ollama": "0.33.3"}
        self.assertEqual(RQ.gen_key("p", rt), RQ.gen_key("p", rt))


class TestStallRetry(unittest.TestCase):
    """
    스톨 재시도 — **삼키는 것과 다시 부르는 것을 가른다.**

    🔴 이 시험이 지키는 것은 두 가지다: 스톨이 나면 다시 부르고 **센다**,
       그리고 재시도가 다 떨어지면 **그대로 터진다.** 둘째가 없으면 이것은
       `llm.py`가 금지한 *"실패를 삼키기"*가 된다.
    """

    def setUp(self):
        self.gen = RQ.Generator({"digest": "d", "ollama": "0.0.0"})
        self.gen.store = {}                       # 디스크를 안 건드린다
        self._real = RQ.LLM.generate
        self._wait = RQ.GEN_RETRY_WAIT
        RQ.GEN_RETRY_WAIT = 0.0

    def tearDown(self):
        RQ.LLM.generate = self._real
        RQ.GEN_RETRY_WAIT = self._wait

    def test_한_번_스톨하면_다시_불러서_답을_얻고_센다(self):
        calls = []

        def flaky(prompt):
            calls.append(prompt)
            if len(calls) == 1:
                raise RQ.LLM.LLMError("qwen3:8b 생성 실패: timed out")
            return "두 번째에 나온 답."

        RQ.LLM.generate = flaky
        self.assertEqual(self.gen._generate("p", "태그"), "두 번째에 나온 답.")
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(self.gen.retries), 1, "스톨이 안 세어졌다")
        self.assertEqual(self.gen.retries[0][0], "태그")

    def test_재시도를_다_쓰면_삼키지_않고_터진다(self):
        def always(prompt):
            raise RQ.LLM.LLMError("qwen3:8b 생성 실패: timed out")

        RQ.LLM.generate = always
        with self.assertRaises(RQ.LLM.LLMError):
            self.gen._generate("p", "태그")
        self.assertEqual(len(self.gen.retries), RQ.GEN_RETRIES + 1)

    def test_스톨이_없으면_재시도_기록이_비어_있다(self):
        RQ.LLM.generate = lambda prompt: "한 번에 나온 답."
        self.assertEqual(self.gen._generate("p", "태그"), "한 번에 나온 답.")
        self.assertEqual(self.gen.retries, [])

    def test_생성_타임아웃이_관측된_최장의_열_배를_넘는다(self):
        # 🔴 이 값을 낮추는 것이 곧 *"정상 생성을 자를 위험"*이다. 실측 최장은
        #    10.4초였고, 여기가 그 10배 아래로 내려가면 시험이 운다.
        self.assertGreaterEqual(RQ.GEN_TIMEOUT, 104)
        self.assertLess(RQ.GEN_TIMEOUT, RQ.LLM.LLM_TIMEOUT,
                        "낮추는 것이 목적인데 `llm.py` 기본값 이상이면 아무 일도 안 한다")

    def test_LLMError가_아닌_예외는_재시도하지_않는다(self):
        # 🔴 스톨만 다시 부른다. 다른 고장을 재시도로 덮으면 그것이 삼키기다.
        def boom(prompt):
            raise ValueError("이건 스톨이 아니다")

        RQ.LLM.generate = boom
        with self.assertRaises(ValueError):
            self.gen._generate("p", "태그")
        self.assertEqual(self.gen.retries, [])


class TestLedgerWiring(unittest.TestCase):
    """
    진짜 대장에 붙였을 때의 성질. **`eval/`은 읽기만 한다** (A8).

    fixture 시험이 통과해도 배선이 틀리면 실험은 아무것도 안 잰다 — 그래서
    실제 18문항에 대해 규칙이 어떤 모양이 되는지를 여기서 못박는다.
    """

    @classmethod
    def setUpClass(cls):
        _corpus, ledger, qs = P.load()
        cls.key_of = P.key_index(ledger)
        cls.scored, _ = P.partition(qs, cls.key_of)
        cls.keys = {q["id"]: RQ.question_keys(q, cls.key_of) for q in cls.scored}

    def test_채점_대상은_18문항이다(self):
        self.assertEqual(len(self.scored), 18)

    def test_X004는_Q26에서_오답이_아니다(self):
        # X004(`라떼`)는 Q26의 **근거**다. 오답으로 세면 정답을 말한 답변이
        # 오답으로 뒤집힌다 — `precision.hard_misinjection`이 적어 둔 특수 사례.
        gold, dist, _ = self.keys["Q26"]
        self.assertIn("라떼", gold)
        self.assertNotIn("라떼", dist)

    def test_스타트업은_해당_문항에서_버려진다(self):
        # 실측: Q04·Q07·Q13·Q15·Q25의 정답에 `'스타트업'`이 들어 있다.
        dropped_any = False
        for qid in ("Q04", "Q13", "Q25"):
            _gold, dist, dropped = self.keys[qid]
            self.assertNotIn("스타트업", dist, f"{qid}에서 '스타트업'이 안 버려졌다")
            if any(d == "스타트업" for d, _ in dropped):
                dropped_any = True
        self.assertTrue(dropped_any, "'스타트업'이 어느 문항에서도 안 버려졌다")

    def test_모든_문항에서_정답과_오답_집합이_겹치지_않는다(self):
        for q in self.scored:
            gold, dist, _ = self.keys[q["id"]]
            self.assertFalse(gold & dist, f"{q['id']}에서 정답·오답이 겹친다")

    def test_모든_문항에_정답_문자열이_있다(self):
        # 비면 `정답 진술`이 항등 0이 된다 — 0-a가 죽인 것과 같은 종류의 지표.
        for q in self.scored:
            self.assertTrue(self.keys[q["id"]][0], f"{q['id']}의 정답 문자열이 비었다")

    def test_대장_문자열로_만든_답변이_실제로_채점된다(self):
        # 🔴 배선 음성 대조 — fixture가 아니라 **대장에서 꺼낸 문자열**로 답변을
        #    만들어 넣는다. 규칙이 대장 값에 대해 발화하는지가 여기서 확인된다.
        q24 = next(q for q in self.scored if q["id"] == "Q24")
        gold, dist, _ = self.keys["Q24"]
        g_str, d_str = sorted(gold)[0], sorted(dist)[0]
        self.assertTrue(RQ.classify(f"그건 {g_str}다.", gold, dist)["gold"])
        r = RQ.classify(f"그건 {d_str}다.", gold, dist)
        self.assertTrue(r["dist"], "대장의 오답 문자열이 오답으로 안 잡혔다")

    def test_오답_문자열이_전혀_없는_문항을_소리내어_센다(self):
        # 이 문항들에서는 `오답 진술`이 구조적으로 0이다. 개수가 바뀌면 알아야 한다.
        empty = [q["id"] for q in self.scored if not self.keys[q["id"]][1]]
        self.assertEqual(empty, [], f"오답 문자열이 빈 문항: {empty}")


class TestPrereg(unittest.TestCase):
    """사전 등록 상수가 코드에 실제로 박혀 있는가."""

    def test_오답_우주는_X계열_다섯이다(self):
        self.assertEqual(RQ.DISTRACTOR_UNIVERSE,
                         ("X001", "X002", "X003", "X004", "X005"))

    def test_기준칸과_기대_전선이_겹치지_않는다(self):
        self.assertNotIn(RQ.BASE_KEY, RQ.EXPECT_FRONT)
        self.assertEqual(len(RQ.EXPECT_FRONT), 5)

    def test_생성_설정이_llm_py의_고정값이다(self):
        import llm
        self.assertEqual((llm.LLM_TEMPERATURE, llm.LLM_SEED, llm.LLM_NUM_CTX),
                         (0, 20260908, 8192))
        self.assertIn("127.0.0.1", llm.OLLAMA_HOST)

    def test_열리는_조건이_ADR_015가_적은_값_그대로다(self):
        # 🔴 조건을 느슨하게 하면 "열렸다"가 공짜가 된다. 값이 움직이면 여기서 운다.
        self.assertEqual(RQ.OPEN_1_MIN_RETRIEVAL_ONLY, 5)
        self.assertEqual(RQ.OPEN_2_MAX_CORR, 0.7)
        self.assertEqual(RQ.OPEN_3_MIN_DISCORDANT, 10)

    def test_사실블록_축은_두_수준이고_기본값이_True다(self):
        self.assertEqual(RQ.FACT_LEVELS, (True, False))
        # 🔴 G16 — `memory.py`의 기본 동작은 이 실험이 바꾸지 않는다.
        self.assertIs(M.INJECT_KNOWN_FACTS, True)

    def test_축은_셋이고_무응답이_들어_있다(self):
        self.assertEqual([n for n, _ in RQ.AXES],
                         ["정답 진술", "오답 진술", "무응답"])

    def test_실험24_기대표는_여섯_셀_다섯_지표다(self):
        self.assertEqual(sorted(RQ.EXPECT_EXP24), [1, 5, 6, 8, 9, 15])
        for v in RQ.EXPECT_EXP24.values():
            self.assertEqual(len(v), 5)


class TestProbePopulation(unittest.TestCase):
    """모집단 B — 유형 라벨 프로브. **`eval/`도 `probe_set`도 읽기만 한다.**"""

    @classmethod
    def setUpClass(cls):
        _corpus, ledger, _qs = P.load()
        cls.key_of = P.key_index(ledger)
        cls.probes, cls.dropped = RQ.probe_population(cls.key_of)

    def test_버려지는_것은_debt_넷뿐이다(self):
        # 🔴 대장의 `key_of`는 facts·events만 담는다. debt에는 허용 문자열 집합이
        #    없고, 검색 색인에도 없어 애초에 검색으로 도달할 수 없다.
        self.assertEqual(sorted(i for i, _ in self.dropped),
                         ["D001", "D002", "D003", "D004_UNPAID"])
        self.assertEqual(len(self.probes), 20)
        self.assertEqual(len(self.probes) + len(self.dropped),
                         len(PS.TYPED_PROBES))

    def test_남은_프로브의_gold는_전부_대장에_있다(self):
        for p in self.probes:
            self.assertIn(p["evidence"][0], self.key_of, p["id"])

    def test_유형_라벨이_닫힌_집합_안에_있다(self):
        for p in self.probes:
            self.assertIn(p["type"], PS.TYPES)

    def test_문항_id가_유일하고_모집단_A와_안_겹친다(self):
        ids = [p["id"] for p in self.probes]
        self.assertEqual(len(set(ids)), len(ids))
        _c, _l, qs = P.load()
        self.assertFalse(set(ids) & {q["id"] for q in qs},
                         "모집단 B의 id가 A와 겹치면 두 모집단이 섞인다")

    def test_프로브에도_같은_채점_규칙이_붙는다(self):
        # 🔴 배선 음성 대조 — 대장에서 꺼낸 문자열로 답변을 만들어 넣는다.
        for p in self.probes:
            gold, dist, _ = RQ.question_keys(p, self.key_of)
            self.assertTrue(gold, f"{p['id']}의 정답 문자열이 비었다")
            self.assertFalse(gold & dist, f"{p['id']}에서 정답·오답이 겹친다")
            g = sorted(gold)[0]
            self.assertTrue(RQ.classify(f"그건 {g}다.", gold, dist)["gold"],
                            f"{p['id']}의 대장 정답 문자열이 정답으로 안 잡혔다")

    def test_자기_gold가_X계열이면_오답_우주에서_빠진다(self):
        # X003이 gold인 프로브(민지네 고양이)에서 `코코`는 근거지 오답이 아니다.
        p = next(x for x in self.probes if x["evidence"] == ["X003"])
        gold, dist, _ = RQ.question_keys(p, self.key_of)
        self.assertIn("코코", gold)
        self.assertNotIn("코코", dist)


class TestInjectGuard(unittest.TestCase):
    """
    `INJECT_KNOWN_FACTS` 복원 단언 — **`retrieval_sweep`이 못 잡는 전역**이다.

    🔴 이 시험은 위반을 심어서 발화를 확인한다. 심지 않으면 이 단언은 언제나
       참인 문장이고, 그런 검사는 이 저장소가 이미 세 번 만들었다.
    """

    def test_전역이_안_돌아왔으면_터진다(self):
        saved = M.INJECT_KNOWN_FACTS
        try:
            M.INJECT_KNOWN_FACTS = not saved          # ← 심은 위반
            with self.assertRaises(SystemExit):
                RQ.assert_inject(saved, "시험")
        finally:
            M.INJECT_KNOWN_FACTS = saved

    def test_돌아왔으면_안_터진다(self):
        RQ.assert_inject(M.INJECT_KNOWN_FACTS, "시험")

    def test_이름이_retrieval_sweep의_복원_목록에_없다(self):
        # 🔴 이 시험이 지키는 것은 **왜 이 단언이 따로 있는가**이다.
        #    언젠가 `RESTORE_GLOBALS`에 이 이름이 들어가면 그때는 두 곳이 같은
        #    일을 하게 되고, 이 시험이 그것을 알린다.
        import retrieval_sweep as RS
        self.assertNotIn("INJECT_KNOWN_FACTS", RS.RESTORE_GLOBALS)


class TestFactBlockSwitch(unittest.TestCase):
    """
    🔴 **이 설계 전체가 이 한 가지 성질 위에 서 있다:** 사실 블록을 끄는 것이
    검색을 건드리지 않는다. 그래야 두 축이 직교하고 교환비가 읽힌다.

    그래서 여기서 진짜 `Memory`를 세워 두 가지를 확인한다 — 블록이 실제로
    사라지는가, 그리고 그때 `retrieve()`가 **한 글자도 안 달라지는가.**
    """

    @classmethod
    def setUpClass(cls):
        from memory import Memory
        from soak import seed, ingest, ROOT, CHAT
        from gate_sweep import build_vocab
        corpus, ledger, qs = P.load()
        cls.CHAT, cls.last = CHAT, corpus[-1]["seq"]
        cls.ask = qs[0]["ask"]
        cls.dbf = f"{ROOT}/prototype/.rq_test.db"
        if os.path.exists(cls.dbf):
            os.remove(cls.dbf)
        cls.m = Memory(cls.dbf)
        seed(cls.m)
        ingest(cls.m, corpus, ledger, timed=False)
        cls.m._vocab = build_vocab(cls.m)

    @classmethod
    def tearDownClass(cls):
        cls.m.db.close()
        os.remove(cls.dbf)

    def _ctx(self, inject):
        saved = M.INJECT_KNOWN_FACTS
        try:
            M.INJECT_KNOWN_FACTS = inject
            return self.m.build_context(self.CHAT, self.ask, self.last)
        finally:
            M.INJECT_KNOWN_FACTS = saved

    def test_켜면_블록이_있고_끄면_없다(self):
        on = [b.name for b in self._ctx(True).blocks]
        off = [b.name for b in self._ctx(False).blocks]
        self.assertIn("알고 있는 것", on)
        self.assertNotIn("알고 있는 것", off,
                         "스위치를 껐는데 사실 블록이 그대로다 — 두 축이 안 갈린다")

    def test_끈다고_검색이_달라지지_않는다(self):
        on = [i for k, i, _ in self._ctx(True).provenance if k == "retrieved"]
        off = [i for k, i, _ in self._ctx(False).provenance if k == "retrieved"]
        self.assertEqual(on, off,
                         "사실 블록을 껐더니 검색 결과가 움직였다 — 직교성이 깨졌다")

    def test_사실_블록의_문자열이_실제로_맥락에서_사라진다(self):
        # 🔴 블록 이름만 보면 안 된다 — 같은 문자열이 다른 블록에 남아 있으면
        #    `검색만` 열이 부풀려진다.
        on_ctx = self._ctx(True)
        txt = "\n".join(b.text for b in on_ctx.blocks if b.name == "알고 있는 것")
        self.assertTrue(txt.strip(), "전제가 깨졌다 — 켠 상태의 사실 블록이 비었다")
        off = self._ctx(False).render()
        for line in (l.strip("· ").strip() for l in txt.splitlines() if l.strip()):
            self.assertNotIn(line, off, f"{line!r}가 끈 맥락에 그대로 남아 있다")


class TestOls(unittest.TestCase):
    """교환비 회귀 — **아는 답으로 시험한다.**"""

    def test_정확히_선형인_자료의_계수를_되찾는다(self):
        rec = [1, 2, 3, 4, 5, 6]
        mis = [2, 1, 5, 3, 8, 4]
        y = [7 + 2 * r - 3 * m for r, m in zip(rec, mis)]
        beta, se, r2, singular = RQ.ols(y, [rec, mis])
        self.assertFalse(singular)
        self.assertAlmostEqual(beta[0], 7, places=6)
        self.assertAlmostEqual(beta[1], 2, places=6)
        self.assertAlmostEqual(beta[2], -3, places=6)
        self.assertAlmostEqual(r2, 1.0, places=6)

    def test_완전_공선이면_특이라고_말하고_숫자를_안_만든다(self):
        # 🔴 실험 24가 못 넘은 벽이 바로 이것이다. 0으로 나누고 넘어가면
        #    분리되지 않은 두 계수가 값처럼 찍힌다.
        rec = [1, 2, 3, 4]
        mis = [2, 4, 6, 8]                    # 정확히 2배 — 공선
        beta, _se, _r2, singular = RQ.ols([1, 2, 3, 4], [rec, mis])
        self.assertTrue(singular)
        self.assertIsNone(beta)

    def test_표준오차가_교과서_공식과_같다(self):
        # 🔴 **자유도를 못박는 시험이다.** 아래 `se1`은 단순 회귀의 닫힌 형태로
        #    따로 계산한 것이고, 거기 `n-2`가 박혀 있다. `ols`가 `ss_res/(n-k)`를
        #    `ss_res/n`으로 바꾸면 표준오차가 √(6/8)배 작아지고 **계수가 실제보다
        #    잘 결정된 것처럼 보인다.** 상대 비교만 하는 시험은 그 변이를 못 잡는다
        #    (실측: 변이 ⑤가 그렇게 살아남았다).
        x = [1, 2, 3, 4, 5, 6, 7, 8]
        y = [2.0, 4.5, 5.0, 8.5, 9.0, 12.5, 13.0, 16.5]
        beta, se, _r2, singular = RQ.ols(y, [x])
        self.assertFalse(singular)
        n = len(x)
        mx, my = sum(x) / n, sum(y) / n
        sxx = sum((a - mx) ** 2 for a in x)
        b1 = sum((a - mx) * (c - my) for a, c in zip(x, y)) / sxx
        b0 = my - b1 * mx
        ssr = sum((c - (b0 + b1 * a)) ** 2 for a, c in zip(x, y))
        self.assertAlmostEqual(beta[1], b1, places=9)
        self.assertAlmostEqual(se[1], math.sqrt(ssr / (n - 2) / sxx), places=9)

    def test_거의_공선이면_계수를_만들지_않는다(self):
        # 🔴 정확히 공선인 자료에서는 피벗이 **정확히 0.0**이라 문턱값이 아무리
        #    작아도 걸린다 — 그래서 그 시험만으로는 문턱값이 지켜지지 않는다.
        #    여기서는 거의 공선인(조건수가 터진) 자료를 넣어 문턱값 자체를 못박는다.
        #    이것이 없으면 `1e-12 → 1e-30` 변이가 살아남고, 그 상태에서는
        #    **분리되지 않은 두 계수가 1e20짜리 값으로 찍힌다.**
        rec = [1, 2, 3, 4, 5, 6]
        mis = [2 * r + i * 1e-13 for i, r in enumerate(rec)]
        beta, _se, _r2, singular = RQ.ols([1, 3, 2, 5, 4, 6], [rec, mis])
        self.assertTrue(singular, "거의 공선인데 계수를 만들었다")
        self.assertIsNone(beta)

    def test_표준오차가_잔차와_함께_커진다(self):
        rec = [1, 2, 3, 4, 5, 6]
        mis = [2, 1, 5, 3, 8, 4]
        y1 = [2 * r - m for r, m in zip(rec, mis)]
        y2 = [v + s for v, s in zip(y1, (5, -5, 5, -5, 5, -5))]
        _b1, se1, _r1, _ = RQ.ols(y1, [rec, mis])
        _b2, se2, _r2, _ = RQ.ols(y2, [rec, mis])
        self.assertLess(se1[1], se2[1])

    def test_상관이_정의되는_최소_점수는_셋이다(self):
        self.assertIsNone(RQ.pearson([1, 2], [1, 2]))
        self.assertAlmostEqual(RQ.pearson([1, 2, 3], [2, 4, 6]), 1.0)
        self.assertIsNone(RQ.pearson([1, 1, 1], [1, 2, 3]))


if __name__ == "__main__":
    unittest.main()
