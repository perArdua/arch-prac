# -*- coding: utf-8 -*-
"""
test_summarize.py — 단계 S2의 생성 경로. (계획서 §7 S2 · §6.3 I4 · §6.4 ②⑤)

## 이 파일이 지는 것

  P4 금지    `rewrite_lifetime`이 **원본 턴을 안 읽는다** (ADR-013 P4)
  프롬프트   `P4_TEMPLATE`이 `docs/14`의 P4 절과 **글자 그대로 같다**.
             「사실 우선」 지시가 **없다** (계획서 §1.2 S7)
  §6.4 ②     세 값이 **단위와 함께** 찍히고, `ntok / num_ctx` 백분율은 **없다**
  §6.4 ⑤     절단 경고가 **오늘 값에서 안 울고**, 잘린 값에서 **운다**
  I4         `stale` 왕복 — 사실 삭제 → 재생성 → stale **0행**.
             그리고 **실패하면 stale이 남는다**

## 🔴 이 파일의 시험은 전부 «심을 위반»을 갖는다

이 저장소가 채택한 규칙 — *"새로 쓰거나 고친 검증 명령은 **위반을 심어 발화를
확인한 뒤에만** 보고한다. 열거는 검증이 아니다"* — 이 여덟 번 깨졌다.
각 시험의 독스트링이 **무엇을 심으면 그 시험이 발화하는지**를 적는다.
⚠️ 변이는 반드시 `python -B`로 돌린다. 파일 길이를 보존하는 변이는 낡은 `.pyc`를
   돌려 **생존자로 오보된다**(레인 M 실측).

## 🔴 오발화도 결함이다 (P5)

기대값은 **새 DB와 legacy DB 둘 다에서** 참이어야 한다. legacy DB란
`digest.kind='session'` 행이 있는 기존 DB이고, 마이그레이션이 대상으로 삼는
바로 그것이다. I4 왕복은 두 픽스처에서 **같은 클래스로** 돈다
(`_RoundTripBase`의 두 서브클래스).

## ollama — 실생성은 옵트인이다 (Q11 · 2026-09-12)

생성이 필요한 시험(`TestRealGeneration`)은 `MEMARCH_REAL_GEN=1`일 때만 돈다
(`@unittest.skipUnless(REAL_GEN, REAL_GEN_WHY)`). 옵트인이 아니면 ollama에 **묻지도
않는다** — 그래서 기본 `discover`의 뜻이 환경과 무관하다(ollama가 떠 있든 없든 같은
OK 수 · 같은 skipped 5 · 같은 사유 «옵트인 아님»). 옛 판(`skipUnless(OLLAMA_UP)`)은
ollama가 떠 있으면 discover마다 비결정(F39) lifetime 실생성을 1회 했다.
실생성 레인 명령은 `TestRealGeneration` 독스트링에 한 줄로 있다.
🔴 **SKIP은 통과가 아니다** (G1). 옵트인 뒤의 skipped 5는 «환경이 안 돼서»가 아니라
   **«선언된 안 돌림»**이다 — 실생성 레인은 이름이 있고 사람이 켠다(`run_all`의 77
   규약 · `experiments/tests/test_theta_grid.py`의 `skipUnless(ISOLATED)` 셋과 같은 지위).
   사유가 둘로 갈린다: «옵트인 아님»(`SKIP_NOT_OPTED`) / 옵트인인데 «ollama가
   없다»(`SKIP_NO_OLLAMA`).
   `python prototype/tests/test_summarize.py`로 직접 부르면 둘 다 **종료 77**로 끝난다.
   `python -m unittest`로 부를 때는 러너가 종료 코드를 쥐고 있어 77을 낼 수 없으므로,
   대신 **모듈 임포트 시점에 배너를 찍어** 무엇이 안 돌았는지가 출력에 남게 한다.
F40(`MEMARCH_FORBID_REGEN`)과는 무관하다 — 이 레인은 기록값을 안 만든다(형식만 본다).

🔴 **DB는 전부 `tempfile`(= `%TEMP%`) 아래에 만든다** — 저장소 안에 파일 DB를
   남기면 다음 레인이 무엇이 자기 것인지 못 가린다.
"""
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import llm                                                  # noqa: E402
import memory                                               # noqa: E402
import summarize                                            # noqa: E402
from memory import Memory                                   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOC14 = os.path.join(ROOT, "docs", "14-extraction-prompts.md")

CHAT = "c1"

# 계획서 §6.4 ④가 못박은 다이제스트. **생존 확인(`/api/tags`가 응답함)만으로
# 통과시키지 않는다** — 대조는 이 문자열에 대해서만 한다.
EXPECT_DIGEST = "500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41"

# Q11 — 실생성은 옵트인. 이름이 표류하면 `TestRealGenerationIsOptIn`이 운다.
REAL_GEN_ENV = "MEMARCH_REAL_GEN"
SKIP_NOT_OPTED = (f"옵트인 아님({REAL_GEN_ENV}=1 없음) — 선언된 안 돌림 ·"
                  " 🔴 SKIP은 통과가 아니다 (G1)")
SKIP_NO_OLLAMA = (f"ollama가 없다({REAL_GEN_ENV}=1인데 {llm.OLLAMA_HOST}이 응답 안 함) —"
                  " 🔴 SKIP은 통과가 아니다 (G1)")


def _real_gen_gate(env, probe):
    """
    `(돈다?, 사유, runtime_info)`. 옵트인(`env[REAL_GEN_ENV] == "1"`)이 아니면 `probe`
    (= ollama 문의)를 **부르지 않는다** — 그래야 기본 discover가 환경을 안 탄다.
    """
    if env.get(REAL_GEN_ENV) != "1":
        return False, SKIP_NOT_OPTED, None
    info = probe()
    if info.get("ollama") is None:
        return False, SKIP_NO_OLLAMA, info
    return True, None, info


REAL_GEN, REAL_GEN_WHY, _info = _real_gen_gate(os.environ, llm.runtime_info)
DIGEST_NOTE = ""
if REAL_GEN_WHY == SKIP_NOT_OPTED:
    print(f"⏭️ 실생성 시험(TestRealGeneration): {SKIP_NOT_OPTED}."
          "  ollama에 묻지 않았다 — 켜는 명령은 그 클래스 독스트링에.")
elif REAL_GEN:
    if _info.get("digest") != EXPECT_DIGEST:
        DIGEST_NOTE = (f"⚠️ 모델 다이제스트가 계획서 기록과 다르다 — 기록"
                       f" {EXPECT_DIGEST[:16]}… vs 현재"
                       f" {str(_info.get('digest'))[:16]}…")
        print(DIGEST_NOTE)
        print("   → 막지 않는다. 대신 이 실행의 모든 수 옆에 이 사실이 붙는다.")
    else:
        print(f"ollama {_info['ollama']} · {_info['model']} · digest"
              f" {str(_info['digest'])[:16]}…  ✅ 계획서 기록과 같다")
else:
    print(f"⏭️ 실생성 시험(TestRealGeneration): {SKIP_NO_OLLAMA}.")

# 재시도가 의미를 가지려면 첫 시도가 언젠가 끝나야 한다 — 기본 600초짜리 시도를
# 3번 하면 30분이고 그동안 아무도 정지를 못 본다.
summarize.GEN_TIMEOUT = 300

# 성공한 생성을 %TEMP%에 남긴다 — 정지로 죽어도 앞의 생성을 다시 안 만든다.
# 🔴 저장소 안이 아니다. 그리고 `summarize.CACHE_PATH`의 기본값은 `None`이다 —
#    프로덕션에서 요약 캐시는 «재료가 바뀌었는데 옛 요약을 돌려주는» 결함이다.
summarize.CACHE_PATH = os.path.join(tempfile.gettempdir(),
                                    "omc-s2-summarize-cache.json")


# ── 픽스처 ──────────────────────────────────────────────────────────────
#
# 🔴 `eval/`은 **읽기만** 한다 (A8).
def _corpus(n_sessions):
    import json
    rows = []
    seen = []
    with open(os.path.join(ROOT, "eval", "corpus", "corpus.jsonl"),
              encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["session"] not in seen:
                if len(seen) == n_sessions:
                    break
                seen.append(r["session"])
            rows.append(r)
    return seen, rows


def _bounds(rows):
    """세션별 `(from_seq, to_seq)`. 코퍼스의 `session` 열이 경계를 공짜로 준다."""
    out = {}
    for r in rows:
        a, b = out.get(r["session"], (r["seq"], r["seq"]))
        out[r["session"]] = (min(a, r["seq"]), max(b, r["seq"]))
    return out


# legacy DB 픽스처. `test_migrate.py`의 `_DIGEST_ROWS`와 같은 모양이고, 같은
# 이유로 위치 기반 5-값 INSERT다(`demo.py`가 그 형태다).
# ⚠️ 이 줄이 G17′-d의 grep 건수를 하나 늘린다 — 이동 대장에 적혀 있다.
_LEGACY_DIGEST = [
    (CHAT, "lifetime", "인생 요약 (legacy)", 100, None),
    (CHAT, "session", "지난 세션 요약 (legacy · v5는 여기 쓰지 않는다)", 100, None),
]


class _Rec:
    """
    `execute`가 본 SQL을 전부 적어 두는 얇은 프록시.

    🔴 **P4의 «원본 턴 금지»를 주석이 아니라 관측으로 만든다.** 소스에 `turn`이
       있는지 grep하는 검사는 주석·문자열에도 걸리고, 무엇보다 *실행되는 경로*를
       안 본다. 여기서는 **그 호출이 실제로 연 테이블**을 본다.
    """

    def __init__(self, db):
        self._db, self.sql = db, []

    def execute(self, sql, *a, **k):
        self.sql.append(sql)
        return self._db.execute(sql, *a, **k)

    def executemany(self, sql, *a, **k):
        self.sql.append(sql)
        return self._db.executemany(sql, *a, **k)

    def __getattr__(self, name):
        return getattr(self._db, name)


def _fake_generate(text="## 타임라인\n- 초기: 만남\n## 관계 변화\n"
                        "- 중반: 가까워짐\n## 다음에\n- 안부"):
    """
    ollama 없이 도는 대역. **생성기를 대신할 뿐 나머지 경로는 진짜다** —
    P4 금지·derivation·stale 왕복은 전부 실제 코드가 돈다.
    """
    def gen(prompt):
        gen.prompts.append(prompt)
        return text
    gen.prompts = []
    return gen


class _StubLLM:
    """`llm.generate`/`llm.last_usage`를 갈아 끼우고 되돌린다."""

    def __init__(self, gen, usage=None):
        self.gen, self.usage = gen, usage

    def __enter__(self):
        self._g, self._u = llm.generate, llm.last_usage
        llm.generate = self.gen
        llm.last_usage = lambda: (dict(self.usage) if self.usage else None)
        return self

    def __exit__(self, *e):
        llm.generate, llm.last_usage = self._g, self._u
        return False


# ── 1. 프롬프트 — docs/14 P4 그대로 · 「사실 우선」 없음 ────────────────

class TestPromptIsDoc14P4(unittest.TestCase):
    """
    **심을 위반:** `summarize.P4_TEMPLATE`의 한 글자라도 고치면(예: 규칙 줄에
    *"구체적 사실을 **먼저** 적어라"*를 넣으면) 두 시험이 함께 발화한다 —
    문서 대조가 불일치를 내고, 「사실 우선」 검사가 금지 어구를 잡는다.
    """

    @staticmethod
    def _doc_p4():
        """`docs/14`의 `### P4` 절에서 첫 코드펜스를 통째로 꺼낸다."""
        with open(DOC14, encoding="utf-8") as f:
            body = f.read()
        after = body.split("### P4 — 요약 재작성", 1)[1]
        return after.split("```", 2)[1].strip("\n")

    def test_template_is_byte_identical_to_doc14(self):
        """
        🔴 정규화는 **정확히 둘**이고 둘 다 `summarize.py`에 이름이 있다 —
           문서가 비워 둔 자리 `<N>`, 그리고 문서 자신의 편집 이력
           `DOC14_ANNOTATION`. 나머지 한 글자라도 어긋나면 발화한다.
        """
        doc = self._doc_p4()
        # 편집 이력이 문서에 **실제로 있는지** 먼저 못박는다. 없는 것을 지우는
        # 정규화는 조용히 무해해지고, 그러면 이 대조가 무엇을 봐주는지 모른다.
        self.assertIn(summarize.DOC14_ANNOTATION, doc)
        # 🔴 문서 쪽에 `.format`을 적용하지 않는다 — `{"trigger": …}` 같은
        #    중괄호가 문서 곳곳에 있고, 그것을 서식으로 읽으면 이 대조가
        #    프롬프트가 아니라 서식 문법을 시험하게 된다.
        norm = doc.replace("<N>", "{budget}").replace(
            summarize.DOC14_ANNOTATION, "")
        self.assertEqual(norm, summarize.P4_TEMPLATE)

    def test_no_fact_first_instruction(self):
        """
        🔴 계획서 §1.2 S7 — frozen의 `2/11 vs 4/11` 우위는 v2 재채점에서
           **동률 2/10**이 되어 위양성으로 판정됐다. 그리고 `docs/14`의 P4가
           *"구체적 사실은 여기서 다루지 않는다"*고 분업을 선언한다.
        """
        rendered = summarize.P4_TEMPLATE.format(budget=400)
        for banned in ("사실 우선", "먼저 적", "**먼저**"):
            self.assertNotIn(banned, rendered)
        # 그리고 문서가 선언한 분업 문장은 **남아 있어야** 한다.
        self.assertIn("여기서 다루지 않는다", rendered)

    def test_session_layer_does_not_forbid_facts(self):
        """
        두 층은 다른 지시를 쓴다. 같은 지시를 쓰면 M4(세션 vs lifetime의 사실
        누출 차이)가 원리적으로 항등이 된다.
        """
        self.assertIn("사실", summarize.SESSION_TEMPLATE)
        self.assertNotIn("여기서 다루지 않는다", summarize.SESSION_TEMPLATE)


# ── 2. §6.4 ② — 세 값 · 단위 · 금지된 나눗셈 ───────────────────────────

class TestTokenReport(unittest.TestCase):
    """
    **심을 위반:** `token_report`의 백분율 분자를 `est`로 바꾸면(= `ntok`을
    `num_ctx`로 나누면) `test_percentage_is_measured_over_num_ctx`가 발화한다.
    단위 접미사를 하나라도 지우면 `test_all_three_carry_units`가 발화한다.
    """

    def test_all_three_carry_units(self):
        line = summarize.token_report("가" * 100, {"prompt_eval_count": 72})
        self.assertRegex(line, r"추정 \d+ ntok")
        self.assertRegex(line, r"실측 \d+ tok")
        self.assertRegex(line, r"num_ctx \d+ tok")

    def test_percentage_is_measured_over_num_ctx(self):
        got = 2592
        line = summarize.token_report("가" * 3413, {"prompt_eval_count": got})
        want = f"{100.0 * got / llm.LLM_NUM_CTX:.1f}%"
        self.assertIn(f"실측 기준 {want}", line)
        # 🔴 `ntok / num_ctx`는 **어떤 형태로도** 이 줄에 없어야 한다 (G15 · S17).
        est = memory.ntok("가" * 3413)
        forbidden = f"{100.0 * est / llm.LLM_NUM_CTX:.1f}%"
        self.assertNotIn(forbidden, line)

    def test_missing_measurement_is_not_filled_with_the_estimate(self):
        """실측이 없으면 `?`다. 추정으로 메우면 다음 사람이 실측으로 읽는다."""
        line = summarize.token_report("가" * 100, None)
        self.assertIn("실측 ? tok", line)
        self.assertNotIn("%", line.split("num_ctx")[0])


# ── 3. §6.4 ⑤ — 조용한 절단 ────────────────────────────────────────────

class TestTruncationWarning(unittest.TestCase):
    """
    **심을 위반 — 다섯을 심어 «무엇이 무엇을 발화시키는지»를 실제로 봤다.**
      ⓐ `_truncation_warning`이 무조건 `None`을 돌려주면
         → `test_fires_when_measured_falls_far_short` ·
           `test_condition_does_not_depend_on_half_plus_two` **발화**
      ⓑ 조건 ②(`TRUNC_NEAR_CAP`)를 지우면
         → `test_short_ascii_prompt_does_not_false_fire` **발화** (오발화 = 결함)
      ⓒ 조건 ①(`TRUNC_SHORTFALL`)을 지우면
         → `test_large_but_honest_prompt_does_not_fire` **발화**
      ⓓ `TRUNC_SHORTFALL`을 0.75 → 1.5로 올리면
         → `test_large_but_honest_prompt_does_not_fire` **발화** (ⓒ와 같은 자리)
      ⓔ 조건 둘을 다 지워 **무조건 경고**하게 하면
         → 위 셋이 전부 **발화** (`test_todays_values_do_not_fire` 포함)

    🔴 **심어 보고 두 번 틀린 것을 고쳤다.**
       ① 처음엔 ⓒ가 `test_todays_values_do_not_fire`를 발화시킨다고 적었다.
          **거짓이었다 — 생존했다.** 오늘 값(실측 2,592 tok)은 `num_ctx`의
          31.6%라 조건 ②가 혼자 막는다. 즉 그 시험은 조건 ①을 **안 지키고**
          있었고, 조건 ①을 지키는 시험이 **하나도 없었다.**
          → `test_large_but_honest_prompt_does_not_fire`를 그 자리에 새로 놓았다.
            **창에 가깝지만 정직한** 프롬프트여야 두 조건이 갈린다.
       ② `test_todays_values_do_not_fire`를 발화시키는 단일 조건 변이는 **없다**
          (ⓑ에서도 조건 ①이, ⓓ에서도 조건 ②가 각각 혼자 막는다). 그것은 결함이
          아니라 **두 조건의 논리곱이 오늘 값을 이중으로 덮는다**는 사실이고,
          그 시험을 발화시키는 것은 ⓔ뿐이다. **그렇게 적는다** — «심을 위반이
          있다»고 뭉뚱그리면 그 시험이 무엇을 지키는지 아무도 모른다.
    """

    def test_todays_values_do_not_fire(self):
        """
        오늘의 정상 경로 — 24세션 재료 ≈ 실측 2,592 tok · num_ctx 8,192 tok.
        **여기서 울면 여섯 달 뒤 «저건 원래 빨간 거야»가 된다** (P5).
        """
        prompt = "가" * 3413                       # ntok 5119 ≈ 계획서의 5,120
        self.assertIsNone(summarize._truncation_warning(
            prompt, {"prompt_eval_count": 2592}))

    def test_short_ascii_prompt_does_not_false_fire(self):
        """
        조건 ② 없이 ①만 쓰면 여기서 **오발화한다.** ASCII·마크다운은 한국어보다
        글자당 토큰이 훨씬 적어 실측이 추정의 절반 아래로 내려가는데, 그런
        프롬프트는 **애초에 잘릴 수가 없다** — 창의 0.2%다.
        """
        prompt = "## timeline\n- a: b\n" * 20      # 순 ASCII
        self.assertIsNone(summarize._truncation_warning(
            prompt, {"prompt_eval_count": 20}))

    def test_large_but_honest_prompt_does_not_fire(self):
        """
        🔴 **조건 ①을 지키는 유일한 시험이다.** 창에 가깝지만(실측이 `num_ctx`의
           53% — 조건 ②를 통과한다) **실측이 추정과 맞는** 프롬프트다. 잘리지
           않았으므로 울면 안 된다. 조건 ①을 지우면 여기서 발화한다.
        """
        prompt = "가" * 5980                       # ntok 8970 → 추정 4333 tok
        got = 4300                                 # 추정과 1.5% 차 · 창의 52.5%
        self.assertGreaterEqual(got, llm.LLM_NUM_CTX * summarize.TRUNC_NEAR_CAP)
        self.assertIsNone(summarize._truncation_warning(
            prompt, {"prompt_eval_count": got}))

    def test_fires_when_measured_falls_far_short(self):
        """
        계획서 §6.4 ⑤의 심을 위반 그대로 — `num_ctx`를 512로 두고 24세션 재료를
        넘기면 ollama가 말없이 ~258로 버린다. HTTP 200 · `truncated` 없음.
        """
        saved = llm.LLM_NUM_CTX
        llm.LLM_NUM_CTX = 512
        try:
            warn = summarize._truncation_warning(
                "가" * 3413, {"prompt_eval_count": 258})
        finally:
            llm.LLM_NUM_CTX = saved
        self.assertIsNotNone(warn)
        self.assertIn("잘렸을 가능성", warn)

    def test_condition_does_not_depend_on_half_plus_two(self):
        """
        🔴 U9 — `num_ctx/2 + 2`가 버전 고유일 수 있다. 그 규칙에서 **벗어난**
           절단값(창의 70%)에서도 경고가 서는지 본다. 규칙에 배선했다면 여기서
           조용히 통과해 버린다.
        """
        saved = llm.LLM_NUM_CTX
        llm.LLM_NUM_CTX = 512
        try:
            self.assertIsNotNone(summarize._truncation_warning(
                "가" * 3413, {"prompt_eval_count": 358}))
        finally:
            llm.LLM_NUM_CTX = saved

    def test_no_usage_is_silence_not_a_warning(self):
        """실측이 없으면 판정할 근거가 없다. 없는 근거로 경고를 만들지 않는다."""
        self.assertIsNone(summarize._truncation_warning("가" * 3413, None))


# ── 4. 🔴 P4 — `rewrite_lifetime`은 원본 턴을 안 읽는다 ────────────────

class TestP4NeverReadsRawTurns(unittest.TestCase):
    """
    **심을 위반:** `rewrite_lifetime`의 재료 조립을
    `_turns(m, chat_id, 1, 10**9)`로 바꾸면 — 즉 «재료가 얇으니 원본도 좀 보자» —
    `test_rewrite_lifetime_touches_no_turn_table`이 발화한다.

    🔴 grep이 아니라 **실행된 SQL**을 본다. 소스 grep은 주석·문자열에도 걸리고,
       무엇보다 그 줄이 실제로 도는지 안 본다.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.m = Memory(os.path.join(self.tmp, "p4.db"))
        sess, rows = _corpus(2)
        for r in rows:
            self.m.add_turn(CHAT, r["seq"], r["role"], r["text"])
        self.bounds = _bounds(rows)
        self.sessions = sess

    def tearDown(self):
        self.m.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_rewrite_lifetime_touches_no_turn_table(self):
        gen = _fake_generate()
        with _StubLLM(gen, {"prompt_eval_count": 200}):
            for sid in self.sessions:
                a, b = self.bounds[sid]
                summarize.session_digest(self.m, CHAT, sid,
                                         from_seq=a, to_seq=b)
            rec = _Rec(self.m.db)
            self.m.db = rec
            try:
                summarize.rewrite_lifetime(self.m, CHAT)
            finally:
                self.m.db = rec._db

        touched = [s for s in rec.sql
                   if re.search(r"\bturn\b", s) and "turn_seq" not in s]
        self.assertEqual(touched, [], f"P4 위반 — 원본 턴을 읽었다: {touched}")

    def test_the_material_is_the_session_digests_verbatim(self):
        """
        재료가 세션 요약인지 **프롬프트 본문으로** 확인한다. 위 시험은
        «턴을 안 읽었다»를 보고, 이것은 «세션 요약을 읽었다»를 본다 —
        둘 다 없으면 «아무것도 안 읽고 지어냈다»가 통과한다.
        """
        gen = _fake_generate()
        with _StubLLM(gen, {"prompt_eval_count": 200}):
            for sid in self.sessions:
                a, b = self.bounds[sid]
                summarize.session_digest(self.m, CHAT, sid, from_seq=a, to_seq=b)
            gen.prompts.clear()
            summarize.rewrite_lifetime(self.m, CHAT)

        prompt = gen.prompts[-1]
        rows = self.m.session_digests(CHAT, limit=memory.DIGEST_KEEP_SESSIONS)
        self.assertTrue(rows)
        for r in rows:
            self.assertIn(r["content"], prompt)

    def test_empty_session_digests_raises_instead_of_falling_back(self):
        """
        재료가 0건이면 **터진다.** 원본으로 폴백하면 그것은 P4가 아니라 ADR-013이
        기각한 P1(매 세션 원본 재독 · $376)이 된다 — 조용한 강등이다.
        """
        with _StubLLM(_fake_generate(), {"prompt_eval_count": 200}):
            with self.assertRaises(ValueError):
                summarize.rewrite_lifetime(self.m, CHAT)


# ── 5. I4 — stale 왕복 (새 DB · legacy DB 둘 다) ───────────────────────

class _RoundTripBase:
    """
    🔴 **기대값이 두 DB 모두에서 참인지 본다** (P5). legacy DB란
    `digest.kind='session'` 행이 있는 기존 DB이고, 마이그레이션이 대상으로 삼는
    바로 그것이다. 새 DB에서만 참인 기대값은 정상 경로를 빨갛게 만든다.
    """

    LEGACY = False

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.m = Memory(os.path.join(self.tmp, "rt.db"))
        if self.LEGACY:
            self.m.db.executemany(
                "INSERT OR REPLACE INTO digest VALUES (?,?,?,?,?)",
                _LEGACY_DIGEST)
        sess, rows = _corpus(2)
        for r in rows:
            self.m.add_turn(CHAT, r["seq"], r["role"], r["text"])
        self.bounds, self.sessions = _bounds(rows), sess
        a, b = self.bounds[sess[0]]
        # S01 구간에 사실 하나와 사건 하나를 심는다 — `derivation`이 걸릴 원본이
        # 있어야 삭제 전파가 관측된다.
        self.m.upsert_fact(CHAT, "지우", "직업", "마케팅 회사 대리", seq=a + 4)
        self.m.add_event(CHAT, "지우가 서준에게 연락을 미뤘다", a + 6)
        self.fact_id = self.m.db.execute(
            "SELECT fact_id FROM fact WHERE chat_id=?", (CHAT,)).fetchone()[0]
        self.m.db.commit()

    def tearDown(self):
        self.m.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _build(self, gen_text=None):
        for sid in self.sessions:
            a, b = self.bounds[sid]
            summarize.session_digest(self.m, CHAT, sid, from_seq=a, to_seq=b)
        summarize.rewrite_lifetime(self.m, CHAT)

    def _stale_digest(self):
        return sorted(r[0] for r in self.m.db.execute(
            "SELECT derived_key FROM stale WHERE chat_id=? AND"
            " derived_kind='digest'", (CHAT,)))

    # ── I4 ────────────────────────────────────────────────────────────
    def test_i4_delete_marks_then_regenerate_clears(self):
        """
        **심을 위반:** `regenerate_stale`이 실패해도 `_clear_stale`을 부르게 하면
        `test_failed_regeneration_keeps_stale`이 발화한다. 반대로
        `_clear_stale` 호출을 지우면 **이 시험**이 발화한다(왕복이 0으로 안 간다).
        """
        with _StubLLM(_fake_generate(), {"prompt_eval_count": 200}):
            self._build()
            self.assertEqual(self._stale_digest(), [])

            self.m.delete_item(CHAT, "fact", self.fact_id)
            marked = self._stale_digest()
            self.assertIn(memory.session_kind(self.sessions[0]), marked)
            self.assertIn("lifetime", marked)

            out = summarize.regenerate_stale(self.m, CHAT)

        self.assertEqual(out["failed"], [])
        self.assertEqual(self._stale_digest(), [],
                         "I4 — 왕복 뒤 stale digest 행이 0이어야 한다")

    def test_failed_regeneration_keeps_stale(self):
        """
        🔴 §6.4 ③ — 실패를 성공처럼 지우면 낡은 요약이 «신선하다»는 표시를 달고
           계속 주입된다. 이 계층에서 가장 나쁜 결과다.

        **심을 위반:** `regenerate_stale`의 `except`에서 `_clear_stale`을
        부르거나 `failed` 적재를 지우면 발화한다.
        """
        with _StubLLM(_fake_generate(), {"prompt_eval_count": 200}):
            self._build()
            self.m.delete_item(CHAT, "fact", self.fact_id)
            before = self._stale_digest()
            self.assertTrue(before)

            def boom(_prompt):
                raise llm.LLMError("생성이 멈췄다 (시험이 심은 실패)")

            saved_retries = summarize.GEN_RETRIES
            summarize.GEN_RETRIES = 1        # 심은 실패를 3번 기다릴 이유가 없다
            try:
                with _StubLLM(boom):
                    out = summarize.regenerate_stale(self.m, CHAT)
            finally:
                summarize.GEN_RETRIES = saved_retries

        self.assertEqual(out["ok"], [])
        self.assertEqual(self._stale_digest(), before,
                         "실패했는데 stale이 지워졌다")
        prov = [r[0] for r in self.m.db.execute(
            "SELECT item FROM provenance WHERE chat_id=? AND kind='regen_failed'",
            (CHAT,))]
        self.assertEqual(sorted(prov), before)

    def test_digest_meta_stale_since_is_cleared_only_on_success(self):
        """`stale` 삭제와 `digest_meta.stale_since_seq = NULL`은 한 몸이다."""
        with _StubLLM(_fake_generate(), {"prompt_eval_count": 200}):
            self._build()
            key = memory.session_kind(self.sessions[0])
            self.m.db.execute(
                "UPDATE digest_meta SET stale_since_seq=99 WHERE chat_id=?"
                " AND kind=?", (CHAT, key))
            self.m.db.execute(
                "INSERT OR REPLACE INTO stale VALUES (?,?,?,?,?)",
                (CHAT, "digest", key, "전이:연인→다툼중", 0.0))
            self.m.db.commit()
            summarize.regenerate_stale(self.m, CHAT)
        left = self.m.db.execute(
            "SELECT stale_since_seq FROM digest_meta WHERE chat_id=? AND kind=?",
            (CHAT, key)).fetchone()[0]
        self.assertIsNone(left)


class TestRoundTripNewDb(_RoundTripBase, unittest.TestCase):
    LEGACY = False


class TestRoundTripLegacyDb(_RoundTripBase, unittest.TestCase):
    LEGACY = True

    def test_legacy_session_row_is_not_rewritten(self):
        """
        🔴 I3 — v5는 `digest.kind='session'`에 **쓰지 않는다.** 그 키가 stale로
           밀려도 재생성 대상이 아니고, **못 하는 것을 한 척하지 않는다:**
           stale을 유지하고 `regen_failed`를 남긴다.

        **심을 위반:** `regenerate_stale`의 `rest` 루프에서 `key != "lifetime"`
        가드를 지우면 legacy 키에 대해 `rewrite_lifetime`이 돌아 lifetime을 두 번
        쓰고 `ok`에 legacy 키가 들어간다 · **발화**.
        """
        with _StubLLM(_fake_generate(), {"prompt_eval_count": 200}):
            self._build()
            self.m.db.execute(
                "INSERT OR REPLACE INTO stale VALUES (?,?,?,?,?)",
                (CHAT, "digest", "session", "전이:썸→연인", 0.0))
            self.m.db.commit()
            out = summarize.regenerate_stale(self.m, CHAT)

        self.assertIn("session", [k for k, _ in out["failed"]])
        self.assertNotIn("session", out["ok"])
        self.assertIn("session", self._stale_digest())
        # legacy 행의 **내용은 그대로**다 — 안 지우고 안 덮어쓴다.
        row = self.m.db.execute(
            "SELECT content FROM digest WHERE chat_id=? AND kind='session'",
            (CHAT,)).fetchone()[0]
        self.assertEqual(row, _LEGACY_DIGEST[1][2])

    def test_lifetime_upsert_preserves_session_end_note(self):
        """
        `INSERT OR REPLACE`였다면 legacy lifetime 행의 `session_end_note`가
        말없이 NULL이 된다. `ON CONFLICT … DO UPDATE`인 이유가 그것이다.
        """
        self.m.db.execute(
            "UPDATE digest SET session_end_note='지키는 값' WHERE chat_id=?"
            " AND kind='lifetime'", (CHAT,))
        self.m.db.commit()
        with _StubLLM(_fake_generate(), {"prompt_eval_count": 200}):
            self._build()
        note = self.m.db.execute(
            "SELECT session_end_note FROM digest WHERE chat_id=? AND"
            " kind='lifetime'", (CHAT,)).fetchone()[0]
        self.assertEqual(note, "지키는 값")


# ── 6. 실생성 — 옵트인(`MEMARCH_REAL_GEN=1`) + ollama가 있어야 한다 ─────────

@unittest.skipUnless(REAL_GEN, REAL_GEN_WHY)
class TestRealGeneration(unittest.TestCase):
    """
    진짜 `qwen3:8b`로 세션 요약 2건 + lifetime 1건을 만든다. **옵트인일 때만** (Q11).

    실생성 레인(사람이 켠다 · 저장소 뿌리에서 · POSIX 셸):
        MEMARCH_REAL_GEN=1 PYTHONIOENCODING=utf-8 python -B -m unittest prototype.test_summarize.TestRealGeneration

    옵트인이 아니면 사유 «옵트인 아님», 옵트인인데 ollama가 없으면 사유 «ollama가
    없다»로 SKIP이다(둘 다 통과가 아니다 — G1). 옵트인해서 생성이 실패하면(`LLMError`
    · F39) `setUpClass`가 죽어 ERROR 1건이다(5건은 안 돈다) — 사람이 켠 레인의 실패는
    **실패로 둔다**(SKIP으로 바꾸지 않는다).

    **심을 위반:** `token_report` 호출을 지우면 `rewrite_lifetime`의 세 값 줄이
    출력에서 사라져 `test_three_values_are_printed_with_units`가 발화한다.

    ⚠️ 이 시험은 **품질에 대해 아무 수도 만들지 않는다** (계획서 §3.4).
       보는 것은 형식(표제 셋)과 토큰 회계뿐이다.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.m = Memory(os.path.join(cls.tmp, "real.db"))
        sess, rows = _corpus(2)
        for r in rows:
            cls.m.add_turn(CHAT, r["seq"], r["role"], r["text"])
        cls.bounds, cls.sessions = _bounds(rows), sess
        cls.out = []
        for sid in sess:
            a, b = cls.bounds[sid]
            cls.out.append(summarize.session_digest(
                cls.m, CHAT, sid, from_seq=a, to_seq=b, tag=f"real:{sid}"))
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            # 🔴 **lifetime 호출에는 `tag`를 주지 않는다 = 캐시를 안 탄다.**
            #    캐시 적중이면 `usage`가 `None`이고, 그러면 §6.4 ②의 세 값 줄이
            #    «실측 ? tok»이 되어 **이 시험이 공허해진다** — 재는 것을 안 재고
            #    통과한다. 세션 요약은 캐시해도 되지만(정지 대비) 수용 기준이
            #    가리키는 이 한 호출은 매번 진짜로 잰다.
            cls.content, cls.usage, cls.warn = summarize.rewrite_lifetime(
                cls.m, CHAT)
        cls.printed = buf.getvalue()
        print(cls.printed, end="")

    @classmethod
    def tearDownClass(cls):
        cls.m.db.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_session_digests_landed_in_the_new_table(self):
        rows = self.m.session_digests(CHAT, limit=memory.DIGEST_KEEP_SESSIONS)
        self.assertEqual(len(rows), len(self.sessions))
        for r in rows:
            self.assertTrue(r["content"].strip())

    def test_lifetime_landed_and_is_not_empty(self):
        row = self.m.db.execute(
            "SELECT content FROM digest WHERE chat_id=? AND kind='lifetime'",
            (CHAT,)).fetchone()
        self.assertIsNotNone(row)
        self.assertTrue(row[0].strip())

    def test_three_values_are_printed_with_units(self):
        self.assertRegex(self.printed, r"추정 \d+ ntok · 실측 (\d+|\?) tok"
                                       r" · num_ctx \d+ tok")

    def test_prompt_eval_count_came_back(self):
        """
        lifetime 호출은 캐시를 안 타므로 **실측이 반드시 있다.** «없어도 된다»고
        적으면 캐시가 켜지는 날 이 시험이 조용히 공허해진다.
        """
        self.assertIsNotNone(self.usage, "lifetime 호출이 캐시를 탔다 — 실측이 없다")
        self.assertIsInstance(self.usage.get("prompt_eval_count"), int)
        self.assertNotIn("실측 ? tok", self.printed)

    def test_todays_real_call_does_not_fire_the_truncation_warning(self):
        """
        🔴 오늘의 정상 경로에서 경고가 울면 그것이 결함이다 (P5). 계획서가
           «이 심을 위반이 유일한 발화 증명»이라 적은 이유가 이것이다 —
           정상 경로에서는 안 운다.
        """
        self.assertIsNone(self.warn)


class TestRealGenerationIsOptIn(unittest.TestCase):
    """
    Q11 — 실생성은 `MEMARCH_REAL_GEN=1`일 때만. **LLM 0 · 네트워크 0**(ollama 문의는 대역).

    **심을 위반:**
      ⓐ `_real_gen_gate`의 옵트인 검사를 지우면 `test_not_opted_in_never_asks_ollama`가
         발화한다(대역 문의 ≥ 1 · 사유가 «옵트인 아님»이 아니다).
      ⓑ 두 사유를 뒤바꾸면(값이든 `return`이든) `test_opted_in_without_ollama_has_its_own_reason`이
         발화한다.
      ⓒ 데코레이터를 옛 `skipUnless(OLLAMA_UP, "ollama가 없다 …")`로 되돌리면
         `test_the_class_carries_this_process_gate`가 발화한다(사유가 다르다).
    조용한 쪽: `test_opted_in_with_ollama_runs` — 옵트인 + ollama 있음이면 돈다(사유 없음).
    """

    @staticmethod
    def _probe(up):
        def probe():
            probe.calls += 1
            return {"ollama": "대역" if up else None, "model": "qwen3:8b", "digest": None}
        probe.calls = 0
        return probe

    def test_not_opted_in_never_asks_ollama(self):
        for env in ({}, {REAL_GEN_ENV: "0"}, {REAL_GEN_ENV: ""}, {REAL_GEN_ENV: "true"}):
            for up in (True, False):
                probe = self._probe(up)
                run, why, info = _real_gen_gate(env, probe)
                self.assertEqual((run, why, info), (False, SKIP_NOT_OPTED, None), (env, up))
                self.assertEqual(probe.calls, 0, f"옵트인이 아닌데 ollama에 물었다 — {env}")

    def test_opted_in_without_ollama_has_its_own_reason(self):
        probe = self._probe(False)
        run, why, _ = _real_gen_gate({REAL_GEN_ENV: "1"}, probe)
        self.assertEqual((run, why, probe.calls), (False, SKIP_NO_OLLAMA, 1))
        self.assertIn("옵트인 아님", SKIP_NOT_OPTED)
        self.assertNotIn("옵트인 아님", SKIP_NO_OLLAMA)
        self.assertIn("ollama가 없다", SKIP_NO_OLLAMA)
        for w in (SKIP_NOT_OPTED, SKIP_NO_OLLAMA):
            self.assertIn("SKIP은 통과가 아니다 (G1)", w)

    def test_opted_in_with_ollama_runs(self):
        probe = self._probe(True)
        run, why, _ = _real_gen_gate({REAL_GEN_ENV: "1"}, probe)
        self.assertEqual((run, why, probe.calls), (True, None, 1))

    def test_the_class_carries_this_process_gate(self):
        self.assertEqual(getattr(TestRealGeneration, "__unittest_skip__", False), not REAL_GEN)
        self.assertEqual(getattr(TestRealGeneration, "__unittest_skip_why__", None), REAL_GEN_WHY)

    def test_env_name_and_the_lane_command(self):
        self.assertEqual(REAL_GEN_ENV, "MEMARCH_REAL_GEN")
        self.assertIn(f"{REAL_GEN_ENV}=1 PYTHONIOENCODING=utf-8 python -B -m unittest"
                      " prototype.test_summarize.TestRealGeneration", TestRealGeneration.__doc__)


# ── 7. wave3 — 전이가 요약 프롬프트를 모른다 · lifetime은 세션 경계에서 ───────

def _rel_db(tmp, n_sessions):
    """코퍼스 앞 `n_sessions` 세션 + `relationship` 한 행 (전이를 내려면 필요하다)."""
    m = Memory(os.path.join(tmp, "w3.db"))
    m.db.execute("INSERT INTO chat VALUES (?,?,?,?)", (CHAT, "jiwoo", "seojun", 1))
    m.db.execute("INSERT INTO relationship (chat_id, stage, affinity, called_as,"
                 " user_locked, updated_by_turn) VALUES (?,?,?,?,?,?)",
                 (CHAT, "아는사이", 20, "지우", 0, 0))
    sess, rows = _corpus(n_sessions)
    for r in rows:
        m.add_turn(CHAT, r["seq"], r["role"], r["text"])
    m.db.commit()
    return m, sess, _bounds(rows)


class TestTransitionIsNotInThePrompt(unittest.TestCase):
    """
    🔓 **`memory.TRANSITION_PROPAGATES_DIGEST`를 되돌리는 조건이 이 시험이다.**

    전이 전파를 끈 근거는 «두 요약 프롬프트가 전이를 모른다 → 전이 뒤 재생성은 새
    정보 0»이다. 그 근거가 무너지는 순간 — 요약 프롬프트가 `stage`·전이 사유·시각을
    싣게 되는 순간 — 이 시험이 빨개지고, 그때가 전파를 다시 켤지 판정할 때다.

    **심을 위반:** `session_digest`의 프롬프트에 현재 stage를 붙이면 세션 쪽이,
    `rewrite_lifetime`의 프롬프트에 붙이면 lifetime 쪽이 발화한다.
    """

    def test_prompts_are_byte_identical_across_a_transition(self):
        tmp = tempfile.mkdtemp()
        try:
            m, sess, bounds = _rel_db(tmp, 3)
            gen = _fake_generate()

            def build():
                n0 = len(gen.prompts)
                for sid in sess:
                    a, b = bounds[sid]
                    summarize.session_digest(m, CHAT, sid, from_seq=a, to_seq=b)
                summarize.rewrite_lifetime(m, CHAT)
                return gen.prompts[n0:]

            with _StubLLM(gen, {"prompt_eval_count": 200}):
                before = build()
                m.apply_meta(CHAT, bounds[sess[-1]][1],
                             {"state_delta": {"stage": "친구", "affinity": 35},
                              "narrative_event": True})
                self.assertEqual(m.db.execute(
                    "SELECT stage FROM relationship WHERE chat_id=?",
                    (CHAT,)).fetchone()[0], "친구", "대조의 바닥 — 전이가 실제로 났어야 한다")
                after = build()
            m.db.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(len(before), len(sess) + 1)
        for i, sid in enumerate(sess):
            self.assertEqual(before[i], after[i],
                             f"{sid} 세션 요약 프롬프트가 전이를 안다 — 전파를 되돌릴 조건")
        self.assertEqual(before[-1], after[-1],
                         "lifetime 프롬프트가 전이를 안다 — 전파를 되돌릴 조건")


class TestLifetimeRefreshAtBoundary(unittest.TestCase):
    """
    ADR-016 U13 — 전이 전파를 끄기 **전에** lifetime에 제 방아쇠를 준다(`regen_job.run` ③).

    **심을 위반:**
      ⓐ ③을 지우면(`lifetime_behind`가 늘 거짓) `test_a_new_session_moves_the_lifetime`이
         `covers_to_seq`가 안 움직여 발화한다 — wave2가 대역으로 본 «90 → 90»이다.
      ⓑ `lifetime_behind`가 늘 참이면 조용한 쪽 `test_no_new_material_no_call`이 발화한다.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.m, self.sess, self.bounds = _rel_db(self.tmp, 3)

    def tearDown(self):
        self.m.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _covers(self):
        r = self.m.db.execute("SELECT covers_to_seq FROM digest WHERE chat_id=?"
                              " AND kind='lifetime'", (CHAT,)).fetchone()
        return None if r is None else r[0]

    def _two_then_lifetime(self, gen):
        with _StubLLM(gen, {"prompt_eval_count": 200}):
            for sid in self.sess[:2]:
                a, b = self.bounds[sid]
                summarize.session_digest(self.m, CHAT, sid, from_seq=a, to_seq=b)
            summarize.rewrite_lifetime(self.m, CHAT)

    def test_a_new_session_moves_the_lifetime(self):
        import regen_job
        gen = _fake_generate()
        self._two_then_lifetime(gen)
        self.assertEqual(self._covers(), self.bounds[self.sess[1]][1])
        a, b = self.bounds[self.sess[2]]
        n0 = len(gen.prompts)
        with _StubLLM(gen, {"prompt_eval_count": 200}):
            out = regen_job.run(self.m, CHAT, now_seq=b, ended_session_id=self.sess[2],
                                from_seq=a, to_seq=b)
        self.assertEqual(out["lifetime"], "rewritten")
        self.assertEqual(self._covers(), b, "새 세션 요약이 생겼는데 lifetime이 안 움직였다")
        self.assertEqual(len(gen.prompts) - n0, 2, "세션 요약 1 + lifetime 1이어야 한다")

    def test_no_new_material_no_call(self):
        """조용한 쪽 — 새 세션 요약이 없으면 lifetime을 안 다시 쓴다(새 정보 0 · 호출 0)."""
        import regen_job
        gen = _fake_generate()
        self._two_then_lifetime(gen)
        n0, cov = len(gen.prompts), self._covers()
        with _StubLLM(gen, {"prompt_eval_count": 200}):
            out = regen_job.run(self.m, CHAT, now_seq=cov, make_digest=False)
        self.assertIsNone(out["lifetime"])
        self.assertEqual(len(gen.prompts), n0)
        self.assertEqual(self._covers(), cov)

    def test_no_lifetime_row_is_not_created_here(self):
        """
        경계 — 🔄 w24a (발견 2 · Q3 = M+1): **첫 경계에서는** 안 만든다(세션 1개는 세션 블록
        M=1이 이미 덮는다 — 행 0 · 호출 1). **둘째 경계에서** 만든다(행 1 · 호출 3 · 덮는 끝 = 둘째
        세션 끝). 옛 계약(«새로고침 방아쇠이지 생성 방아쇠가 아니다»)은 첫 단언으로만 남는다 —
        그 계약 아래서는 제품 경로에서 lifetime이 영영 안 생겼다.

        **심을 위반:** `lifetime_due_first`가 늘 거짓이면 둘째 단언이, 문턱이 1이면 첫 단언이 발화한다.
        """
        import regen_job
        gen = _fake_generate()
        a, b = self.bounds[self.sess[0]]
        with _StubLLM(gen, {"prompt_eval_count": 200}):
            out = regen_job.run(self.m, CHAT, now_seq=b, ended_session_id=self.sess[0],
                                from_seq=a, to_seq=b)
        self.assertIsNone(out["lifetime"])
        self.assertIsNone(self._covers())
        self.assertEqual(len(gen.prompts), 1)

        a, b = self.bounds[self.sess[1]]
        with _StubLLM(gen, {"prompt_eval_count": 200}):
            out = regen_job.run(self.m, CHAT, now_seq=b, ended_session_id=self.sess[1],
                                from_seq=a, to_seq=b)
        self.assertEqual(out["lifetime"], "created")
        self.assertEqual(self._covers(), b)
        self.assertEqual(len(gen.prompts), 3, "세션 요약 2 + lifetime 1이어야 한다")

    def test_failed_refresh_keeps_the_old_lifetime_served(self):
        """
        뒤처진 lifetime은 틀린 것이 아니다 — 새로고침이 실패해도 **stale로 찍지 않고**
        옛 것을 계속 서빙한다. 실패는 `regen_failed`로 남는다.
        """
        import regen_job
        self._two_then_lifetime(_fake_generate())
        old = self.m.db.execute("SELECT content FROM digest WHERE chat_id=? AND"
                                " kind='lifetime'", (CHAT,)).fetchone()[0]
        with _StubLLM(_fake_generate(), {"prompt_eval_count": 200}):
            a, b = self.bounds[self.sess[2]]
            summarize.session_digest(self.m, CHAT, self.sess[2], from_seq=a, to_seq=b)

        def boom(_prompt):
            raise llm.LLMError("생성이 멈췄다 (시험이 심은 실패)")

        saved = summarize.GEN_RETRIES
        summarize.GEN_RETRIES = 1
        try:
            with _StubLLM(boom):
                out = regen_job.run(self.m, CHAT, now_seq=b, make_digest=False)
        finally:
            summarize.GEN_RETRIES = saved
        self.assertTrue(out["lifetime"].startswith("failed"))
        self.assertIsNone(self.m.stale_row(CHAT, "digest", "lifetime"))
        self.assertEqual(self.m.db.execute(
            "SELECT content FROM digest WHERE chat_id=? AND kind='lifetime'",
            (CHAT,)).fetchone()[0], old)
        self.assertIn("lifetime", [r[0] for r in self.m.db.execute(
            "SELECT item FROM provenance WHERE chat_id=? AND kind='regen_failed'",
            (CHAT,))])


if __name__ == "__main__":
    if not REAL_GEN:        # 옵트인 아님 · ollama 없음 — 둘 다 77 (Q11)
        print(f"\n⏭️ {REAL_GEN_WHY} — 종료 77 (SKIP · 통과로 세지 않는다).")
        raise SystemExit(77)
    raise SystemExit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)
