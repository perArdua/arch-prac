# -*- coding: utf-8 -*-
"""
summary_ablation.py — **깊이 2의 «네 개의 0»이 무엇 탓인지 가른다.** (실험 28)

## 이 파일이 여는 자리

[실험 27](../docs/11-experiment-results.md)이 lifetime 요약에 대해 **네 개의 0**을 냈다 —
M2 0/10 · M4 0/11 · 혼합 0/10 · M3 판정 불가. 형식은 완벽히 지키면서(M1 3/3) 대장
낱말을 하나도 안 남겼고, 그 라운드는 스스로 이렇게 적고 닫았다:

  *"그 0이 「P4 지시 / 재압축 / 재료 24세션」 중 무엇 탓인지 이 실험은 가르지
    못한다 — 같은 재료·같은 구간에서 지시만 바꿔 한 번 더 재야 한다."*

이 파일이 **그 한 번**이다. 새 지표를 만들지 않는다. 새 채점기를 만들지 않는다.
**요인을 하나씩만 움직여 같은 자로 다시 잰다.**

## 🔴 요인을 하나씩만 움직인다 — 그리고 그것을 종료 코드로 집행한다

후보 원인이 셋이고, **동시에 두 개를 움직이면 아무것도 안 갈린다.**

  ① **지시**    `P4_TEMPLATE`(요약 지시 · 사실 금지) ↔ `SESSION_TEMPLATE`(세션 지시)
  ② **재압축**  재료가 **세션 요약**(이미 압축된 것) ↔ **원본 턴**
  ③ **재료 크기** 구간 S01–S24 ↔ S01–S12

`FactorRule`이 이것을 산문이 아니라 **집행**한다: 팔(`Arm`)은 자기 앵커와 **정확히
한 요인만** 달라야 하고, 어긋나면 표가 그려지기 전에 발화한다. 음성 대조 ⓐ가
두 요인이 함께 움직이는 팔을 실제로 심어 그것을 보인다.

## 🔄 ②의 «같은 구간» 팔은 창을 넘었다 — **A4 라운드가 창을 네 번째 요인으로 올려 채웠다**

🔄 **정정.** 이 절의 첫 판은 *"`A4`를 선언만 하고 «안 돌린다»를 찍는다"*였다.
원본 턴 720건(S01–S24)의 프롬프트가 추정 **12,809 tok**으로 `num_ctx` 8,192 tok을
넘었기 때문이고, ollama는 창을 넘는 프롬프트를 **말없이 버린다**(ADR-016 §정직 8).
**그 판단은 그 창에서 옳았다** — 아래 창 예산 표가 지금도 «A4는 창 8,192에서 제외»를
찍는다. 그리고 ②의 판정은 그래서 **S01–S12에서만** 산 것이었다(Y2).

**이 라운드가 창을 키워 그 자리를 채운다.** 🔴 **그러면 요인이 둘 움직인다** —
`A0`(창 8,192)과 `A4`(창 16,384)는 **재료와 창**이 둘 다 다르고, `FactorRule`이
그것을 종료 코드로 잡는다. **잡는 것이 옳다.** 그래서:

  🔴 **앵커를 같은 창에서 다시 만든다.** `A0′`(= P4 지시 · 세션 요약 24 · S01–S24 ·
     **창 16,384**)를 새로 돌리고 `A4`의 앵커를 `A0′`로 둔다 → **재료 하나만** 다르다.
  🔴 **`A0 → A0′`는 «창» 하나만 다르다 — 별도 행으로 찍는다.** 같으면 «창은 이
     재료에서 결과를 안 바꾼다»이고, 다르면 **그 사실 자체가 이 라운드의 결과**다.
  ⛔ **`A0 ↔ A4`에는 화살표를 안 건다** — 요인이 둘이다. `ArrowRule`이 이미 안다.

②의 **S01–S12 판정은 그대로 A3↔A2에서** 읽는다(구간·지시가 같다). 이 라운드가
더하는 것은 **②′ — 같은 질문을 24세션 구간에서** 읽는 `A0′ → A4` 하나다.

## 🔴 창은 «호출 시 옵션»으로 못 넘어간다 — 그래서 **전역을 블록 동안만** 바꾼다 (G16)

`prototype/llm.py`의 `LLM_NUM_CTX = 8192`는 **전역이고 프로덕션 경로가 쓴다.**
`raw_generate(**options)`는 창을 옵션으로 받지만 **`generate()`도 `summarize._generate`
도 옵션을 안 넘긴다.** 옵션 경로로 가려면 `_generate`의 **재시도·정지 계수·크래시
캐시**를 이 파일에 복사해야 하고, 그것이 F12(사본 금지)다.
→ `use_window()`가 전역을 **블록 동안만** 바꾸고 **`finally`로 되돌린다**(G13).
   `assert_prod_window()`가 팔마다·실행 끝에 복원을 **확인하고 출력에 찍는다.**
   🔴 **`prototype/llm.py`는 한 글자도 안 고친다.**

## 🔴 채점은 실험 27의 것을 그대로 쓴다 — 사본 금지 (F12)

M1~M4의 정의도 §3.3의 비교 규칙도 `TitleRule`도 **`summary_prototype`에서 import
한다.** 사본을 두면 두 실험이 «같은 이름의 다른 자»를 갖게 되고, 그것이 이 저장소가
네 번 겪은 실패 모드 ②다. 그래서 이 파일은 `summary_prototype.py`를 **한 글자도
고치지 않는다** — 실험 27의 출력이 바이트 동일해야 이 실험의 A0이 그 실험의 팔이다.

M2는 **`survived_v2`**로 잰다(실험 27 §B의 결정). `survived_v3`은 같은 표에 이름을
달고 나란히 선다.

## 🔴 프롬프트 조립을 프로덕션에서 **뽑아 대조한다**

이 실험은 `rewrite_lifetime`을 부를 수 없다 — 그 함수는 `P4_TEMPLATE` 하나만
쓰도록 짜여 있고(그것이 P4의 계약이다), **프로덕션 경로를 고치는 것은 이 실험의
일이 아니다.** 그래서 프롬프트를 여기서 조립한다.
🔴 **그러면 «내가 조립한 것이 프로덕션이 만드는 것과 같은가»가 새 미지수가 된다.**
→ `capture_production_prompt()`가 임시 DB에서 `rewrite_lifetime`을 부르되
   `llm.generate`를 가로채 **프롬프트만** 뽑는다(ollama 호출 0회). `assemble()`이
   그것과 **바이트 동일**해야 A0이 실험 27의 팔이다. 음성 대조 ⓒ가 조립을 한 글자
   흔들어 그 대조가 실제로 우는 것을 보인다.

## 실행

    PYTHONIOENCODING=utf-8 python -B experiments/summary_ablation.py

ollama(`qwen3:8b`)가 없고 `ABLATION_S28.json`도 없으면 **종료 77 (SKIP)** —
통과가 아니라 미측정이다(G1).
"""
import contextlib
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "prototype"))

import llm                                                   # noqa: E402
import memory                                                # noqa: E402
import summarize                                             # noqa: E402
import summary_prototype as SP                               # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

W = 78

CORPUS = os.path.join(ROOT, "eval", "corpus", "corpus.jsonl")
CKPT = os.path.join(HERE, "data", "ABLATION_S28.json")
GEN_CACHE = os.path.join(HERE, "data", "ABLATION_GEN_CACHE.json")

# 🔴 **글자 → 실측 토큰 환산.** 상수를 새로 고르지 않았다 — ADR-016 §정직 6이
#    두 길이 회귀로 산 값(**한계 0.7189 tok/글자 · 절편 ≲ 8 tok**)을 그대로 쓴다.
#    ⚠️ 그 절편을 «템플릿·BOS 몫»이라 부르지 않는다 — 점이 둘이면 잔차가 없다.
#    이 환산은 **어느 팔이 창에 들어가나**를 고르는 데만 쓰고, 표의 어떤 값도
#    이것으로 만들지 않는다.
TOK_PER_CHAR = 0.7189
TOK_INTERCEPT = 8

# 생성에 남겨 두는 창. 프롬프트가 창을 다 먹으면 **출력이 잘린다**(`done_reason`이
# `length`로 온다). `LIFETIME_BUDGET_TOKENS`=400에 qwen3의 `<think>` 몫을 얹은 값이고,
# **측정된 값이 아니라 고른 값**이다 — 그래서 실행이 `done_reason`을 매 팔 찍는다.
GEN_HEADROOM_TOK = 1024

# 🔴 **프로덕션 기본값. 이 파일은 이것을 안 고친다** (G16). 수입 시점에 한 번 읽어
#    두고, `assert_prod_window()`가 «돌아왔는가»를 이 값에 대고 잰다. 🔴 아래
#    `use_window()`가 도는 동안에는 `llm.LLM_NUM_CTX`가 이 값이 **아니므로**,
#    복원 가드가 전역을 다시 읽으면 언제나 «같다»가 나온다 — 그래서 여기 박는다.
PROD_NUM_CTX = llm.LLM_NUM_CTX

# 🔴 `A4`·`A0′`가 쓰는 창. **고른 값이지 측정된 값이 아니다** — A4의 추정
#    12,809 tok에 생성 여유 1,024 tok을 얹은 13,833 tok 위의 첫 2의 거듭제곱이다.
#    ⚠️ **모델이 그 창을 지원하는지가 별개의 질문이다.** `qwen3:8b`의
#    `qwen3.context_length`는 40,960 tok이고(`/api/show` 실측), 실행이 **요청 창과
#    실측 `prompt_eval_count`를 나란히 찍어** 말없이 잘리지 않았음을 보인다 (U9).
BIG_NUM_CTX = 16384

# 세션당 턴 수. `summary_prototype.TURNS_PER_SESSION`과 **같은 수여야 한다** —
# 두 실험이 같은 구간 라벨(`턴 1–30`)을 쓰기 때문이다. 사본을 두지 않고 가져온다.
TURNS_PER_SESSION = SP.TURNS_PER_SESSION

# 꼬리표. 🔴 **네 팔에서 고정한다 — 요인이 아니다.** `session_digest`는
# `[세션 요약]`을 쓰지만 그것을 팔마다 갈면 네 번째 것이 함께 움직인다.
TAIL = "\n\n[다시 쓴 요약]\n"


# ══════════════════════════════════════════════════════════════════════
# 0. 🔴 사전 등록 — **생성 한 건 전에** 여기 박고 출력 첫 화면에 찍는다
# ══════════════════════════════════════════════════════════════════════
#
# 실험 24·25가 그렇게 해서 음성 결과가 읽혔다. 이 표를 나중에 고치면 그것은
# 사전 등록이 아니다 — 값을 보고 규칙을 고르는 것이 이 저장소가 금지한 형태다.

# (팔, 지시, 재료 종류, 구간, 앵커, 움직인 요인, 그 팔의 세션 수, **창 tok**)
#
# 🔄 **A4 라운드의 정정 둘.** 첫 판의 A4는 `("A4", "P4", "원본 턴", "S01–S24",
#    "A0", "재료", 24)`였고 **안 돌렸다.** 이 라운드가 그 자리를 채우면서 둘을 고쳤다:
#      ① **창이 네 번째 요인이 됐다** — 마지막 원소가 그것이다. A0–A3은 전부
#         `PROD_NUM_CTX`이므로 **그 넷 사이의 요인 계산은 한 자리도 안 움직인다.**
#      ② **A4의 앵커가 `A0` → `A0′`로 바뀌었다.** 창이 요인이 된 순간 `A0 → A4`는
#         **재료·창 둘**이 다르고, 그것을 그대로 두면 `FactorRule`이 표가 그려지기
#         전에 종료 1을 낸다. **터지는 것이 옳다** — 그래서 앵커를 같은 창에서
#         다시 만들었다.
ARM_SPECS = (
    ("A0",  "P4",      "세션 요약", "S01–S24", None,  None,   24, PROD_NUM_CTX),
    ("A1",  "SESSION", "세션 요약", "S01–S24", "A0",  "지시",  24, PROD_NUM_CTX),
    ("A2",  "P4",      "세션 요약", "S01–S12", "A0",  "구간",  12, PROD_NUM_CTX),
    ("A3",  "P4",      "원본 턴",   "S01–S12", "A2",  "재료",  12, PROD_NUM_CTX),
    ("A0′", "P4",      "세션 요약", "S01–S24", "A0",  "창",    24, BIG_NUM_CTX),
    ("A4",  "P4",      "원본 턴",   "S01–S24", "A0′", "재료",  24, BIG_NUM_CTX),
)

# 🔴 **사전 등록된 판정 규칙.** 각 줄은 `(요인, 팔 쌍, 항목 집합 이름, 읽는 법)`이고
#    **항목 집합을 요인마다 다르게 고른 것이 규칙의 절반**이다:
#    A2·A3의 재료는 S01–S12만 덮으므로 `events 10`에서 읽으면 그 팔들은 애초에
#    7개를 가질 수 없다. 그 자리에서 «낮다»를 읽으면 그것이 실패 모드 ②다.
DECISION_RULES = (
    ("①  지시",
     "A1 vs A0", "events 10 · S01–S24",
     "A1의 M2(v2)가 **0을 벗어나면** → 0의 원인은 «P4 지시»다. "
     "0 그대로면 지시는 원인이 **아니다**"),
    ("③  재료 크기",
     "A2 vs A0", "구간 안 사건 events 3 · S01–S12",
     "A2의 M2(v2)가 **0을 벗어나면** → 원인은 «재료 24세션»이다. "
     "0 그대로면 재료 크기는 원인이 **아니다**"),
    ("②  재압축",
     "A3 vs A2", "구간 안 사건 events 3 · S01–S12",
     "A3가 **A2보다 크면** → 원인은 «재압축»이다(원본 턴을 한 번만 압축하면 남는다). "
     "둘 다 0이면 재압축도 원인이 **아니다**"),
    # 🆕 A4 라운드가 더한 둘. **위 셋의 글자는 한 자도 안 고쳤다** — 고치면 실험 28의
    #    사전 등록이 이 라운드에 의해 다시 쓰인 것이 된다.
    ("④  창",
     "A0′ vs A0", "events 10 · S01–S24",
     "A0′의 M2(v2)가 A0과 **같으면** → 창은 이 재료에서 결과를 **안 바꾼다**. "
     "**다르면 그 차이 자체가 이 라운드의 결과**이고, 아래 ②′의 크기를 그만큼 깎는다"),
    ("②′ 재압축 · 24세션 구간",
     "A4 vs A0′", "events 10 · S01–S24",
     "A4의 M2(v2)가 **A0′보다 크면** → ②(재압축)는 **24세션 구간에서도 참**이다. "
     "**같거나 작으면** → ②는 **S01–S12의 성질**이었고 24세션 구간에서는 "
     "재확인되지 **않는다**. ⚠️ «차이 없음»은 정당한 결과다 — 숫자를 만들지 않는다"),
)

# 🔴 **화살표마다 어느 항목 집합에서 읽을지도 사전 등록이다.** 첫 판은 이것을
#    «다른 요인이 «지시»면 events 10, 아니면 구간 안 3»이라는 **규칙**으로 계산했다.
#    창이 요인으로 늘어난 순간 그 규칙은 `A0→A0′`(창)와 `A0′→A4`(재료)를 **둘 다
#    구간 안 3으로** 보내는데, 그 두 팔의 재료는 S01–S24를 전부 덮으므로 그것은
#    **판정을 3분의 1만 보고 읽는 것**이다. → 계산하지 말고 **표로 박는다.**
#    `main`이 «자격 있는 쌍마다 여기 항목이 있는가»를 종료 코드로 집행한다.
ARROW_ITEMSET = {
    ("A0", "A1"):   "10",     # 지시 — A1의 재료는 S01–S24를 덮는다
    ("A0", "A2"):   "3",      # 구간 — A2의 재료는 S01–S12만 덮는다
    ("A2", "A3"):   "3",      # 재료 — 두 팔 다 S01–S12
    ("A0", "A0′"):  "10",     # 🆕 창 — 두 팔의 재료가 같고 S01–S24를 덮는다
    ("A0′", "A4"):  "10",     # 🆕 재료(24세션) — 두 팔 다 S01–S24를 덮는다
}

PREREG_CLOSING = (
    "셋 다 0이면 **어느 한 요인을 되돌려도 0을 못 벗어난다**는 뜻이고, 그때 남는 "
    "설명은 «세 요인의 결합» 또는 «자(M2 자체)»다 — 🔴 그 경우 이 실험은 "
    "«가르지 못했다»가 아니라 **«셋 다 단독 원인이 아니다»를 가른 것**이고, "
    "«재압축 자체»(⭐핵심 1)를 재확인하려면 A3가 0을 벗어나야 한다. "
    "A3까지 0이면 ⭐핵심 1은 이 재료에서 **재확인되지 않는다.**"
)


# ══════════════════════════════════════════════════════════════════════
# 1. 팔 — 요인을 들고 다닌다
# ══════════════════════════════════════════════════════════════════════

class FactorViolation(RuntimeError):
    """요인 규율 위반. **삼키지 않는다** — 위반한 표는 그려지면 안 된다."""


class Arm:
    """
    한 팔. **세 요인과 앵커 없이는 만들 수 없다.**

    🔴 `summary_prototype.Col`과 같은 이유로 존재한다: 산문으로 «요인 하나만
       움직여라»라고 적으면 다음 사람이 한 팔에서 잊는다. **못 만들게 하고,
       그래도 만들면 `FactorRule`이 종료 코드로 잡는다.**
    """

    # 🔄 **A4 라운드가 「창」을 네 번째 요인으로 올렸다.** 첫 판은 셋이었고, 그때는
    #    네 팔이 전부 같은 창을 썼으므로 창이 «움직이지 않는 것»이었다. A4를 돌리려면
    #    창을 키워야 하고, **키우는 순간 그것은 요인이다.** 여기 안 올리면
    #    `FactorRule`이 `A0`과 `A0′`를 «한 요인도 다르지 않다»(위반 ②)로 읽는다 —
    #    즉 **같은 팔을 두 이름으로 부르는 것**으로 본다. 그것이 이 승격의 시험이다.
    FACTORS = ("지시", "재료", "구간", "창")

    def __init__(self, key, instruction, material, span, anchor, moved,
                 window=None):
        self.key = key
        self.instruction = instruction     # 「지시」 요인의 값 — `P4` / `SESSION`
        self.material = material           # 「재료」 요인의 값 — 세션 요약 / 원본 턴
        self.span = span                   # 「구간」 요인의 값
        # 「창」 요인의 값. 기본은 **프로덕션 기본값**이고, 그래서 A0–A3을 만들던
        # 첫 판의 호출부(인자 여섯)는 한 글자도 안 고치고 그대로 돈다.
        self.window = PROD_NUM_CTX if window is None else int(window)
        self.anchor = anchor               # 앵커 팔의 키 (없으면 None)
        self.moved = moved                 # **선언된** 움직인 요인 (없으면 None)
        self.n_sessions = int(span.split("–")[1][1:])
        self.prompt = None
        self.est_tok = None
        self.ran = False
        self.text = None
        self.meta = None

    def factors(self):
        return {"지시": self.instruction, "재료": self.material,
                "구간": self.span, "창": f"{self.window} tok"}

    def label(self):
        return (f"{self.key} · {self.instruction} 지시 · {self.material}"
                f" · {self.span} · 창 {self.window} tok")

    def short(self):
        return f"{self.key} ({self.instruction} · {self.material} · {self.span})"


class FactorRule:
    """
    §요인 규율의 **집행부**. 위반 목록을 돌려준다 — 비어 있어야 한다.

      ① 앵커가 있는 팔이 앵커와 **두 요인 이상** 다르다
      ② 앵커와 **한 요인도** 다르지 않다 (같은 팔을 두 이름으로 부른 것)
      ③ **선언한 요인**과 실제로 다른 요인이 어긋난다
      ④ 앵커 이름이 팔 목록에 없다
    """

    def audit(self, arms):
        by_key = {a.key: a for a in arms}
        bad = []
        for a in arms:
            if a.anchor is None:
                continue
            if a.anchor not in by_key:
                bad.append(f"④«{a.key}»의 앵커 «{a.anchor}»가 팔 목록에 없다")
                continue
            base = by_key[a.anchor]
            diff = sorted(f for f in Arm.FACTORS
                          if a.factors()[f] != base.factors()[f])
            if len(diff) == 0:
                bad.append(f"②«{a.key}»가 앵커 «{a.anchor}»와 한 요인도 다르지"
                           f" 않다 — 같은 팔을 두 이름으로 부른 것이다")
            elif len(diff) > 1:
                bad.append(f"①«{a.key}»가 앵커 «{a.anchor}»와 **{len(diff)}개**"
                           f" 요인이 다르다: {diff} — 귀속이 안 된다")
            elif a.moved != diff[0]:
                bad.append(f"③«{a.key}»가 «{a.moved}»를 움직였다고 선언했는데"
                           f" 실제로 다른 것은 «{diff[0]}»이다")
        return bad

    def diff(self, arms, k1, k2):
        by_key = {a.key: a for a in arms}
        f1, f2 = by_key[k1].factors(), by_key[k2].factors()
        return sorted(f for f in Arm.FACTORS if f1[f] != f2[f])


class ArrowRule:
    """
    🔴 **팔 사이 화살표의 자격.** §3.3 ①보다 한 칸 더 좁게 간다.

    화살표는 **요인이 정확히 하나만 다른 팔 쌍**에만, 그리고 **둘 다 실제로 돈
    경우에만** 붙는다. 실험 27이 «재료 구간과 깊이가 다르면 화살표를 안 건다»고
    적은 것과 같은 규칙이고, 여기서는 그것이 요인의 언어로 적힌다.

    ⚠️ `summary_prototype.TitleRule`의 화살표 규칙(**기준선** 화살표)과 다른 것이다.
       그쪽은 «기준선 파일과 같은 항목 집합인가»를 보고, 이쪽은 «두 팔이 한
       요인만 다른가»를 본다. **두 규칙을 한 이름으로 부르지 않는다.**
    """

    def audit(self, arms, pairs):
        fr = FactorRule()
        by_key = {a.key: a for a in arms}
        bad = []
        for k1, k2 in pairs:
            d = fr.diff(arms, k1, k2)
            if len(d) != 1:
                bad.append(f"«{k1}↔{k2}»에 화살표가 붙었다 — 다른 요인이"
                           f" {len(d)}개다: {d or '없다'}")
            for k in (k1, k2):
                if not by_key[k].ran:
                    bad.append(f"«{k1}↔{k2}»에 화살표가 붙었다 —"
                               f" «{k}»는 돌지 않았다(값이 없다)")
        return bad


# ══════════════════════════════════════════════════════════════════════
# 2. 재료와 프롬프트 조립
# ══════════════════════════════════════════════════════════════════════

def round_summaries():
    """이 라운드 재료 — 실험 27과 **같은 파일·같은 24건**을 읽는다."""
    return SP.round_summaries()


def corpus_turns():
    """`eval/corpus/corpus.jsonl` 전량. **읽기만** 한다 (A8)."""
    with open(CORPUS, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def summary_blocks(sums, k):
    """
    세션 요약 k건을 프로덕션과 **같은 모양**의 블록으로.

    모양(`[session:S01 · 턴 1–30]\\n본문`)은 `rewrite_lifetime`이 만드는 것이고,
    아래 `capture_production_prompt`가 그것을 실제로 뽑아 대조한다.
    """
    out = []
    for i, (sid, text) in enumerate(sums[:k], start=1):
        out.append(f"[{memory.session_kind(sid)} ·"
                   f" 턴 {(i - 1) * TURNS_PER_SESSION + 1}–"
                   f"{i * TURNS_PER_SESSION}]\n{text}")
    return out


def turn_blocks(rows, sids):
    """
    원본 턴을 **같은 블록 모양**으로. 블록 안의 줄만 `session_digest`의 것이다.

    🔴 **머리글이 달라지는 것은 피할 수 없는 «②의 몸»이다.** 재료가 세션 요약이
       아닌데 `[재료 — 세션 요약 k건]`이라 적으면 그것이 거짓말이다. 그래서 이
       한 줄만 갈고, **그 한 줄이 요인 ②의 일부라고 여기 적는다** — 네 번째
       변수가 아니다.
    """
    out = []
    for i, sid in enumerate(sids, start=1):
        rs = [r for r in rows if r["session"] == sid]
        body = "\n".join(f"{r['seq']}. [{r['role']}] {r['text']}" for r in rs)
        out.append(f"[{memory.session_kind(sid)} ·"
                   f" 턴 {(i - 1) * TURNS_PER_SESSION + 1}–"
                   f"{i * TURNS_PER_SESSION}]\n{body}")
    return out


def assemble(instruction, header, blocks):
    """
    프롬프트 한 벌. **이 함수가 조립의 유일한 자리다.**

    🔴 프로덕션(`rewrite_lifetime`)의 조립과 **바이트 동일**해야 A0이 실험 27의
       팔이다. `capture_production_prompt`가 그 대조를 실행으로 한다.
    """
    return instruction + "\n\n" + header + "\n" + "\n\n".join(blocks) + TAIL


def capture_production_prompt(sums):
    """
    `rewrite_lifetime`이 **실제로 만드는** 프롬프트를 뽑는다. **ollama 호출 0회.**

    임시 DB에 세션 요약을 넣고 `rewrite_lifetime`을 부르되 `llm.generate`를
    가로채 프롬프트만 낚아채고 감시용 문자열을 돌려준다. 🔴 **프로덕션 파일을
    한 글자도 안 고친다** — 고치면 «프로덕션이 무엇을 만드나»라는 질문 자체가
    이 실험의 산물로 바뀐다.
    """
    tmp = tempfile.mkdtemp(prefix="exp28-anchor-")
    m = SP._build_db(os.path.join(tmp, "anchor.db"), sums)
    cap = {}
    orig = llm.generate

    def _spy(prompt):
        cap["prompt"] = prompt
        return "[앵커 뽑기 — 이 호출은 ollama를 안 불렀다]"

    llm.generate = _spy
    try:
        summarize.rewrite_lifetime(m, SP.CHAT)
    finally:
        llm.generate = orig
        m.db.close()
    return cap["prompt"]


def est_tokens(prompt):
    """
    글자 수에서 실측 토큰을 **추정**한다. 🔴 표의 어떤 값도 이것으로 안 만든다 —
    **어느 팔이 창에 들어가나**를 고르는 데만 쓴다.
    """
    return int(round(len(prompt) * TOK_PER_CHAR + TOK_INTERCEPT))


def window_fits(est, ctx=None, headroom=None):
    """창에 들어가는가. `(들어가나, 필요 tok, 창 tok)`."""
    ctx = llm.LLM_NUM_CTX if ctx is None else ctx
    headroom = GEN_HEADROOM_TOK if headroom is None else headroom
    need = est + headroom
    return need <= ctx, need, ctx


# ══════════════════════════════════════════════════════════════════════
# 2-b. 🔴 팔별 창 — **프로덕션 기본값을 안 고친다** (G16 · G13)
# ══════════════════════════════════════════════════════════════════════

class WindowNotRestored(RuntimeError):
    """`llm.LLM_NUM_CTX`가 프로덕션 기본값으로 안 돌아왔다. **삼키지 않는다.**"""


@contextlib.contextmanager
def use_window(ctx, restore=True):
    """
    `llm.LLM_NUM_CTX`를 **이 블록 동안만** `ctx`로 바꾼다. `finally`로 되돌린다.

    🔴 **왜 옵션이 아니라 전역 재바인딩인가.** `llm.raw_generate(**options)`는 창을
       옵션으로 받지만 그 위의 둘이 안 넘긴다 — `llm.generate(prompt)`는 `str -> str`
       계약이고, `summarize._generate(prompt, tag=)`도 옵션 자리가 없다. 옵션 경로로
       가려면 `_generate`의 **재시도·정지 계수·크래시 캐시**를 이 파일에 복사해야
       하고 **그것이 F12(사본 금지)다.** 그래서 전역을 블록 동안만 바꾸고,
       **되돌렸다는 것을 `assert_prod_window()`가 매번 확인해 출력에 찍는다.**
       🔴 `prototype/llm.py`는 **한 글자도 안 고친다** (G16).

    ⚠️ `restore=False`는 **음성 대조 전용**이다 — 복원 가드가 실제로 우는지 보려면
       복원을 안 하는 경로가 하나 있어야 한다. 실제 팔은 절대 이것을 안 쓴다.
    """
    old = llm.LLM_NUM_CTX
    llm.LLM_NUM_CTX = int(ctx)
    try:
        yield int(ctx)
    finally:
        if restore:
            llm.LLM_NUM_CTX = old       # 🔴 예외로 나가도 여기를 지난다


def assert_prod_window():
    """
    창이 프로덕션 기본값으로 돌아왔는가. 아니면 **터진다** — 안 터지면 이 실험이
    프로덕션 전역을 조용히 바꿔 둔 채 끝나고, 다음 사람의 `rewrite_lifetime`이
    **다른 창에서** 돈다. 그것이 G16이 막으려는 형태다.
    """
    if llm.LLM_NUM_CTX != PROD_NUM_CTX:
        raise WindowNotRestored(
            f"`llm.LLM_NUM_CTX`가 {llm.LLM_NUM_CTX} tok이다 — 프로덕션 기본값"
            f" {PROD_NUM_CTX} tok으로 복원되지 않았다. 이 상태로 프로덕션 경로를"
            f" 부르면 창이 조용히 바뀐 채 돈다 (G16)")
    return PROD_NUM_CTX


def truncation_footprint(ctx):
    """
    U9가 실측한 «절반 절단»의 자국. 프롬프트가 창을 넘으면 ollama 0.33.3 ·
    `qwen3:8b`에서 `prompt_eval_count`가 **`num_ctx/2 + 2`**로 왔다.

    🔴 **이 값을 판정에 안 쓴다.** 판정은 `summarize._truncation_warning`의 **두
       관측 조건**이 하고(그쪽은 이 규칙에 안 기댄다 — U9), 이 함수가 만드는 수는
       출력에 **나란히** 찍혀 «실측이 그 자국과 다르다»를 눈으로 보이게 할 뿐이다.
    """
    return ctx // 2 + 2


# ══════════════════════════════════════════════════════════════════════
# 3. 생성 — 체크포인트 · 재시도 계수 · 다이제스트 문자열 대조
# ══════════════════════════════════════════════════════════════════════

def load_ckpt():
    if os.path.exists(CKPT):
        with open(CKPT, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_ckpt(rec):
    tmp = CKPT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CKPT)          # 크래시가 **반쯤 쓴 체크포인트**를 남기지 않게


def generate_arm(arm, rec):
    """
    한 팔의 생성. 체크포인트가 있으면 **생성 0건**.

    🔴 **소진되면 예외를 올린다.** `summarize._generate`의 계약 그대로 —
       여기서 빈 문자열을 돌려주면 «요약이 비었다»와 «못 만들었다»가 구별되지
       않는다. 재시도와 정지는 그 함수가 세고, 이 함수가 그 수를 받아 적는다.
    """
    if arm.key in rec:
        arm.text = rec[arm.key]["text"]
        arm.meta = rec[arm.key]["meta"]
        arm.ran = True
        return False

    saved_cache = summarize.CACHE_PATH
    summarize.CACHE_PATH = GEN_CACHE     # 크래시가 앞의 생성을 잃지 않게
    stall0 = summarize.STALL_COUNT
    t0 = time.perf_counter()
    # 🔴 **팔의 창은 여기서만 산다.** `_truncation_warning`과 `token_report`도
    #    `llm.LLM_NUM_CTX`를 읽으므로 **블록 안에서** 불러야 그 팔의 창으로 잰다.
    with use_window(arm.window):
        try:
            text, usage = summarize._generate(arm.prompt, tag=arm.key)
            wall = time.perf_counter() - t0
            info = llm.runtime_info()
            warn = summarize._truncation_warning(arm.prompt, usage)
            seen_ctx = llm.LLM_NUM_CTX
        finally:
            summarize.CACHE_PATH = saved_cache
    # 🔴 블록을 나오자마자 **복원을 확인한다.** 여기서 안 터지면 다음 팔이 남의
    #    창에서 돈다.
    assert_prod_window()
    arm.text = text
    arm.meta = {
        "model": llm.LLM_MODEL, "ollama": info.get("ollama"),
        "digest": info.get("digest"),
        "temperature": llm.LLM_TEMPERATURE, "seed": llm.LLM_SEED,
        "num_ctx": seen_ctx,
        "requested_num_ctx": arm.window,
        "prod_num_ctx": PROD_NUM_CTX,
        "generator_version": summarize.GENERATOR_VERSION,
        "n_generated": 1,
        "retries_used": 1 + (summarize.STALL_COUNT - stall0),
        "stalls": summarize.STALL_COUNT - stall0,
        "wall_s": round(wall, 1),
        "prompt_chars": len(arm.prompt),
        "est_tok": arm.est_tok,
        "prompt_eval_count": (usage or {}).get("prompt_eval_count"),
        "done_reason": (usage or {}).get("done_reason"),
        "truncation_warning": warn,
        "instruction": arm.instruction, "material": arm.material,
        "span": arm.span,
        "source": "prototype/summarize.py::_generate (사본 없음 — F12)",
        "window_source": ("experiments/summary_ablation.py::use_window"
                          " (전역을 블록 동안만 · llm.py 무변경 — G16)"),
    }
    arm.ran = True
    rec[arm.key] = {"meta": arm.meta, "text": arm.text}
    save_ckpt(rec)                        # **팔마다** 쓴다 — 크래시 안전
    return True


# ══════════════════════════════════════════════════════════════════════
# 4. M1 — 🔴 **없는 계약을 채점하지 않는다**
# ══════════════════════════════════════════════════════════════════════

class ContractViolation(RuntimeError):
    """계약이 없는 팔에 M1을 매기려 했다."""


def m1_of(arm):
    """
    `docs/14` P4 표제 셋. **`P4` 지시 팔에만 정의된다.**

    🔴 실험 27이 적은 규율을 코드로 옮긴 것이다 — *"세션 요약에는 M1을 적용하지
       않는다. 그 지시(`SESSION_TEMPLATE`)는 형식을 요구하지 않고, **없는 계약을
       채점하면 그 0은 결함이 아니다**."* 산문으로 두면 표에 `0/3`이 찍히고,
       그 0은 **지시가 형식을 안 시켰다는 뜻인데 요약이 못했다는 뜻으로 읽힌다.**
       음성 대조 ⓑ가 그것을 실제로 심어 발화를 확인한다.
    """
    if arm.instruction != "P4":
        raise ContractViolation(
            f"«{arm.key}»의 지시는 `{arm.instruction}`이고 형식 표제를 요구하지"
            f" 않는다. 없는 계약을 채점하면 그 0은 결함이 아니라 **계약의"
            f" 부재**다 — 숫자를 만들지 않는다.")
    return SP.m1(arm.text)


def m1_cell(arm):
    try:
        hit, tot, _ = m1_of(arm)
        return f"{hit}/{tot}"
    except ContractViolation:
        return "해당 없음"


# ══════════════════════════════════════════════════════════════════════
# 5. 음성 대조 — 심을 위반. **전부 실제로 돌린다**
# ══════════════════════════════════════════════════════════════════════

def negative_controls(arms, prod_prompt, sums, live_quiet, live_fired):
    """
    **열** 갈래. 각각 **위반을 심어 발화를 확인**하고 **조용한 쪽 대조**를 함께 낸다.
    🆕 A4 라운드가 셋을 더했다 — ⓗ 창 복원(G16) · ⓘ A0′ 앵커 · ⓙ 판정 규칙의
    항목 집합. 셋 다 **이 라운드가 새로 만든 검사**이고, 그래서 셋 다 심은 위반이
    붙는다(*"새로 쓰거나 고친 검증은 위반을 심어 발화를 확인한 뒤에만 보고한다"*).

    🔴 *"울지 않는 검사는 발화 증명이 없다"*(P5) — 그리고 **오발화도 결함이다.**
       그래서 갈래마다 두 줄이다: 심은 것에 울고, 정상에 조용한가.
    """
    print("\n" + "=" * W)
    print("음성 대조 — 심을 위반 **열**. 검사가 **발화하는지**, 그리고"
          " **조용한지** 본다")
    print("  (🆕 ⓗ 창 복원 · ⓘ A0′ 앵커 · ⓙ 판정 규칙의 항목 집합 — A4 라운드가"
          " 더한 셋)")
    print("=" * W)
    ok = []
    frule, arule = FactorRule(), ArrowRule()

    # ── ⓐ 요인 규율 ──────────────────────────────────────────────────
    print("\n  ⓐ **두 요인이 함께 움직이는 팔**을 심는다 (이 실험의 중심 규율)")
    v_ok = frule.audit(arms)
    print(f"       실제 다섯 팔          → 위반 {len(v_ok)}건"
          f"  {'✅ 조용하다 (오발화 대조)' if not v_ok else '🔴 오발화'}")
    for b in v_ok:
        print(f"          {b}")
    planted = [
        ("두 요인 동시", Arm("Z1", "SESSION", "원본 턴", "S01–S24", "A0", "지시")),
        ("한 요인도 안 움직임", Arm("Z2", "P4", "세션 요약", "S01–S24", "A0", "지시")),
        ("선언과 실제가 어긋남", Arm("Z3", "P4", "세션 요약", "S01–S12", "A0", "지시")),
    ]
    fired_a = True
    for name, z in planted:
        v = frule.audit(list(arms) + [z])
        mine = [b for b in v if f"«{z.key}»" in b]
        print(f"       심은 팔 «{name}»  → 위반 {len(mine)}건"
              f"  {'✅' if mine else '🔴'}")
        for b in mine:
            print(f"          {b}")
        fired_a = fired_a and bool(mine)
    fired = fired_a and not v_ok
    print(f"       {'✅ 발화' if fired else '🔴 발화 실패'}")
    ok.append(fired)

    # ── ⓑ M1 계약 가드 ───────────────────────────────────────────────
    print("\n  ⓑ **없는 계약을 채점한다** — `SESSION` 지시 팔에 M1을 매긴다")
    by = {a.key: a for a in arms}
    quiet_arm = next(a for a in arms if a.instruction == "P4" and a.ran)
    try:
        h, t, _ = m1_of(quiet_arm)
        quiet_ok, why_q = True, f"M1 = {h}/{t}"
    except ContractViolation as e:
        quiet_ok, why_q = False, f"🔴 오발화: {e}"
    print(f"       P4 지시 팔 «{quiet_arm.key}» → {why_q}"
          f"  {'✅ 조용하다 (오발화 대조)' if quiet_ok else ''}")
    a1 = by["A1"]
    if a1.ran:
        try:
            m1_of(a1)
            loud_ok, why_l = False, "🔴 아무 일도 안 났다 — 0/3이 표에 찍힌다"
        except ContractViolation as e:
            loud_ok, why_l = True, f"`ContractViolation` — {e}"
    else:
        loud_ok, why_l = False, "🔴 A1이 안 돌아 심을 수가 없었다"
    print(f"       SESSION 지시 팔 «A1» → {why_l}")
    print("       🔴 가드가 없으면 그 자리에 **0/3**이 찍히고, 그 0은 «요약이"
          " 형식을 못 지켰다»로")
    print("          읽힌다 — 실제로는 **그 지시가 형식을 시킨 적이 없다.**")
    fired = quiet_ok and loud_ok
    print(f"       {'✅ 발화' if fired else '🔴 발화 실패'}")
    ok.append(fired)

    # ── ⓒ 프롬프트 조립 앵커 ─────────────────────────────────────────
    print("\n  ⓒ **조립을 한 글자 흔든다** — 프로덕션과 바이트 동일한가")
    good = assemble(
        summarize.P4_TEMPLATE.format(budget=summarize.LIFETIME_BUDGET_TOKENS),
        summarize._LIFETIME_MATERIAL_HEADER.format(k=len(sums)),
        summary_blocks(sums, len(sums)))
    same_good = good == prod_prompt
    print(f"       정상 조립 → 프로덕션과 {'바이트 동일' if same_good else '다르다'}"
          f"  {'✅ 조용하다 (오발화 대조)' if same_good else '🔴'}")
    # 🔴 셋을 심는 이유: «한 글자»의 자리가 하나가 아니다. 블록 구분자 · 머리글의
    #    건수 · 예산 자리 — 셋 다 잡혀야 이 대조가 조립 전체를 지킨다.
    mutants = [
        ("블록 구분자 `\\n\\n` → `\\n`",
         summarize.P4_TEMPLATE.format(budget=summarize.LIFETIME_BUDGET_TOKENS)
         + "\n\n" + summarize._LIFETIME_MATERIAL_HEADER.format(k=len(sums))
         + "\n" + "\n".join(summary_blocks(sums, len(sums))) + TAIL),
        ("머리글 건수 24 → 23",
         assemble(
             summarize.P4_TEMPLATE.format(
                 budget=summarize.LIFETIME_BUDGET_TOKENS),
             summarize._LIFETIME_MATERIAL_HEADER.format(k=len(sums) - 1),
             summary_blocks(sums, len(sums)))),
        ("예산 400 → 300",
         assemble(summarize.P4_TEMPLATE.format(budget=300),
                  summarize._LIFETIME_MATERIAL_HEADER.format(k=len(sums)),
                  summary_blocks(sums, len(sums)))),
    ]
    fired_c = True
    for name, mut in mutants:
        differs = mut != prod_prompt
        print(f"       심은 변이 «{name}» → 프로덕션과"
              f" {'다르다' if differs else '같다'}  {'✅' if differs else '🔴'}")
        fired_c = fired_c and differs
    fired = same_good and fired_c
    print(f"       {'✅ 발화' if fired else '🔴 발화 실패'}")
    ok.append(fired)

    # ── ⓓ 창 예산 가드 ───────────────────────────────────────────────
    print("\n  ⓓ **창 예산 가드** — 같은 가드가 오늘의 실제 팔들에서 갈리는가")
    a3, a4 = by["A3"], by["A4"]
    f3 = window_fits(a3.est_tok, ctx=a3.window)
    f4 = window_fits(a4.est_tok, ctx=a4.window)
    # 🔄 **정정 — 이 갈래의 «우는 쪽»이 바뀌었다.** 첫 판은 «A4가 실제 창에서
    #    제외된다»를 우는 쪽으로 썼다. A4가 이제 **자기 창(16,384)에서는 통과**
    #    하므로 그 줄은 더 이상 안 운다. **가드를 느슨하게 푼 것이 아니다** —
    #    같은 A4를 **프로덕션 창에 대 보면 그대로 운다**. 우는 쪽을 그리로 옮겼다.
    f4_small = window_fits(a4.est_tok, ctx=PROD_NUM_CTX)
    print(f"       A3(원본 턴 S01–S12) 추정 {a3.est_tok} tok →"
          f" 필요 {f3[1]} / 창 {f3[2]} tok · {'통과' if f3[0] else '제외'}"
          f"  {'✅ 조용하다 (오발화 대조)' if f3[0] else '🔴'}")
    print(f"       A4(원본 턴 S01–S24) 추정 {a4.est_tok} tok →"
          f" 필요 {f4[1]} / 창 {f4[2]} tok · {'통과' if f4[0] else '제외'}"
          f"  {'✅ 조용하다 (오발화 대조)' if f4[0] else '🔴'}")
    print(f"       🔄 **같은 A4를 프로덕션 창 {PROD_NUM_CTX} tok에 대 본다** →"
          f" 필요 {f4_small[1]} tok ·"
          f" {'통과' if f4_small[0] else '제외'}"
          f"  {'✅ 실제 팔에서 운다' if not f4_small[0] else '🔴'}")
    tiny = window_fits(a3.est_tok, ctx=2048)
    print(f"       심은 위반: 창을 2048 tok으로 낮춘다 → A3도"
          f" {'통과' if tiny[0] else '제외'}  {'✅' if not tiny[0] else '🔴'}")
    print("       🔴 **한쪽으로 쏠리지 않는다:** 심은 것에 울고(창 2048),"
          " 실제 팔 A4를 프로덕션")
    print("          창에 대면 울고, 각 팔이 **자기 창에서는** 조용하다."
          " 넷이 있어야 한 짝이다.")
    fired = f3[0] and f4[0] and (not f4_small[0]) and (not tiny[0])
    print(f"       {'✅ 발화' if fired else '🔴 발화 실패'}")
    ok.append(fired)

    # ── ⓔ 화살표 자격 ────────────────────────────────────────────────
    print("\n  ⓔ **두 요인이 다른 팔 쌍에 화살표**를 건다")
    legit = [(a.anchor, a.key) for a in arms if a.anchor and a.ran
             and by[a.anchor].ran]
    v_ok = arule.audit(arms, legit)
    print(f"       자격 있는 쌍 {legit} → 위반 {len(v_ok)}건"
          f"  {'✅ 조용하다 (오발화 대조)' if not v_ok else '🔴 오발화'}")
    for b in v_ok:
        print(f"          {b}")
    v_bad = arule.audit(arms, [("A0", "A3")])
    print(f"       심은 화살표 «A0↔A3» (지시는 같고 재료·구간 둘이 다르다)"
          f" → 위반 {len(v_bad)}건")
    for b in v_bad:
        print(f"          {b}")
    # 🔄 **정정 — 이 줄의 이유가 바뀌었다.** 첫 판은 «A0↔A4는 요인이 하나인데
    #    A4가 안 돌았다»였다. A4가 돌았으므로 그 사유는 죽었고, **다른 사유로
    #    여전히 운다** — 창이 요인이 된 순간 A0↔A4는 **요인 둘**이다.
    v_win = arule.audit(arms, [("A0", "A4")])
    print(f"       🔄 심은 화살표 «A0↔A4» (A4는 **돌았다**. 그런데 재료·창"
          f" **둘**이 다르다) → 위반 {len(v_win)}건")
    for b in v_win:
        print(f"          {b}")
    # 🔴 «안 돈 팔에 화살표» 갈래는 이 라운드에 **실제 예가 없다**(여섯 팔이 다
    #    돌았다). 검사를 지우면 그 갈래가 조용히 사라지므로 **팔을 심어** 세운다.
    ghost = Arm("Z9", "P4", "세션 요약", "S01–S24", "A0", "창",
                window=BIG_NUM_CTX)          # ran = False
    v_dead = arule.audit(list(arms) + [ghost], [("A0", "Z9")])
    print(f"       심은 화살표 «A0↔Z9» (요인은 하나(창)인데 Z9가 **안 돌았다**)"
          f" → 위반 {len(v_dead)}건")
    for b in v_dead:
        print(f"          {b}")
    fired = bool(v_bad) and bool(v_win) and bool(v_dead) and not v_ok
    print(f"       {'✅ 발화' if fired else '🔴 발화 실패'}")
    ok.append(fired)

    # ── ⓕ 표 제목 규율 — 실험 27의 `TitleRule`을 **그대로** 쓴다 ─────
    print("\n  ⓕ **분모 숫자만 적힌 열**을 심는다 (§3.1 · 실험 27의 `TitleRule`)")
    rule = SP.TitleRule()
    v_ok = rule.audit([SP.Col("M2 사건", "events 10", "S01–S24", "v2")])
    print(f"       정상 제목 «events 10» → 위반 {len(v_ok)}건"
          f"  {'✅ 조용하다 (오발화 대조)' if not v_ok else '🔴 오발화'}")
    fired_f = True
    for planted_t in ("10", "/10", " 0 / 3 "):
        v = rule.audit([SP.Col("M2 사건", planted_t, "S01–S24", "v2")])
        print(f"       심은 제목  «{planted_t}» → 위반 {len(v)}건"
              f"  {'✅' if v else '🔴'}")
        fired_f = fired_f and bool(v)
    v_rows = rule.audit_rows(["A2 요약", "A2 요약"])
    print(f"       심은 행 라벨 «A2 요약» 둘 → 위반 {len(v_rows)}건"
          f"  {'✅' if v_rows else '🔴'}")
    fired = fired_f and bool(v_rows) and not v_ok
    print(f"       {'✅ 발화' if fired else '🔴 발화 실패'}")
    ok.append(fired)

    # ── ⓖ M3 `k<2` 가드 — 실험 27의 `m3`를 **그대로** 쓴다 ───────────
    print("\n  ⓖ **M3 `k<2` 가드** — 실험 27의 함수가 이 라운드의 입력에서 갈리는가")
    print(f"       조용한 쪽 «{live_quiet[0]}» 매칭 k={live_quiet[1].k}"
          f" → 사유 {live_quiet[1].reason or '없다'}"
          f" · 쌍 {live_quiet[1].pairs}")
    print(f"       우는 쪽   «{live_fired[0]}» 매칭 k={live_fired[1].k}"
          f" → 사유 {live_fired[1].reason or '없다'}"
          f" · 쌍 {live_fired[1].pairs}")
    quiet = live_quiet[1].reason is None and live_quiet[1].pairs
    loud = live_fired[1].reason is not None and live_fired[1].pairs is None
    print("       심은 위반: 가드를 제거한다 (`min_matches=0`)")
    r0 = SP.m3("나비가 응급실에 갔다.",
               [{"id": "E007", "at": {"session": "S19"},
                 "text": "나비가 갑자기 아파서 응급실에 감"}], min_matches=0)
    try:
        SP.m3_fmt(r0)
        blew, why = False, "🔴 아무 일도 안 났다"
    except ZeroDivisionError as e:
        blew, why = True, (f"`ZeroDivisionError` — 찍히는 분수가"
                           f" **{r0.hit}/{r0.pairs}**이다: {e}")
    print(f"       → {why}")
    fired = bool(quiet) and loud and blew
    print(f"       {'✅ 발화' if fired else '🔴 발화 실패'}")
    ok.append(fired)

    # ── ⓗ 🆕 창 복원 가드 (G16) ──────────────────────────────────────
    print("\n  ⓗ 🆕 **창 복원 가드** — 전역을 되돌리지 않으면 우는가"
          " (`prototype/llm.py` 무변경)")
    print(f"       프로덕션 기본값 `llm.LLM_NUM_CTX` = **{PROD_NUM_CTX} tok**"
          f" (수입 시점에 박아 둔 `PROD_NUM_CTX`)")
    # 조용한 쪽 ① — 정상 종료
    with use_window(BIG_NUM_CTX) as w:
        inside = llm.LLM_NUM_CTX
    try:
        quiet1, why1 = assert_prod_window(), None
    except WindowNotRestored as e:
        quiet1, why1 = None, str(e)
    print(f"       정상 블록: 안에서 {inside} tok (요청 {w}) → 나와서"
          f" {llm.LLM_NUM_CTX} tok"
          f"  {'✅ 조용하다 (오발화 대조)' if quiet1 else '🔴 오발화: ' + str(why1)}")
    # 조용한 쪽 ② — 🔴 **예외로 나가도** 되돌아오는가. `finally`가 없으면 여기서 샌다
    try:
        with use_window(BIG_NUM_CTX):
            raise RuntimeError("생성이 터진 척한다")
    except RuntimeError:
        pass
    try:
        quiet2 = bool(assert_prod_window())
    except WindowNotRestored:
        quiet2 = False
    print(f"       예외로 나간 블록: 나와서 {llm.LLM_NUM_CTX} tok"
          f"  {'✅ 조용하다 — `finally`가 지난다' if quiet2 else '🔴 샜다'}")
    # 우는 쪽 — 복원을 뺀다
    with use_window(BIG_NUM_CTX, restore=False):
        pass
    try:
        assert_prod_window()
        loud_h, why_h = False, "🔴 아무 일도 안 났다 — 전역이 바뀐 채 남는다"
    except WindowNotRestored as e:
        loud_h, why_h = True, f"`WindowNotRestored` — {e}"
    finally:
        llm.LLM_NUM_CTX = PROD_NUM_CTX     # 심은 위반을 여기서 치운다
    print(f"       심은 위반: `use_window(restore=False)` → {why_h}")
    print(f"       치운 뒤 {llm.LLM_NUM_CTX} tok · 다시 확인"
          f" **{assert_prod_window()} tok**")
    print("       🔴 가드가 없으면 이 실험이 **프로덕션 전역을 바꿔 둔 채 끝나고**,")
    print("          다음 사람의 `rewrite_lifetime`이 남의 창에서 돈다 — G16이"
          " 막으려는 형태다.")
    fired = bool(quiet1) and quiet2 and loud_h
    print(f"       {'✅ 발화' if fired else '🔴 발화 실패'}")
    ok.append(fired)

    # ── ⓘ 🆕 A0′ 앵커 규율 ───────────────────────────────────────────
    print("\n  ⓘ 🆕 **A0′ 앵커 규율** — 앵커를 같은 창에서 다시 안 만들면 우는가")
    real_a4 = by["A4"]
    v_ok_f = frule.audit(arms)
    print(f"       실제 A4의 앵커 «{real_a4.anchor}» (창"
          f" {by[real_a4.anchor].window} tok = A4의 창 {real_a4.window} tok)"
          f" → 위반 {len(v_ok_f)}건"
          f"  {'✅ 조용하다 (오발화 대조)' if not v_ok_f else '🔴 오발화'}")
    # 🔴 심은 위반: **첫 판의 A4를 그대로 되살린다** — 앵커가 A0(창 8,192)인 팔.
    #    이것이 «그대로 넣으면 터진다, 그리고 터지는 것이 옳다»의 실행이다.
    naive = Arm("Z8", "P4", "원본 턴", "S01–S24", "A0", "재료",
                window=BIG_NUM_CTX)
    naive.ran = True
    v_naive = [b for b in frule.audit(list(arms) + [naive]) if "«Z8»" in b]
    print(f"       심은 팔 «Z8» — 창을 키운 A4를 **A0(창 {PROD_NUM_CTX})에**"
          f" 그대로 건다 → 위반 {len(v_naive)}건")
    for b in v_naive:
        print(f"          {b}")
    # 그리고 그 팔에 화살표를 걸면 `ArrowRule`도 운다 — 두 규율이 같은 것을 잡는다
    v_naive_arrow = arule.audit(list(arms) + [naive], [("A0", "Z8")])
    print(f"       같은 팔에 화살표 «A0↔Z8» → 위반 {len(v_naive_arrow)}건"
          f"  {'✅' if v_naive_arrow else '🔴'}")
    print("       🔴 이것이 이 라운드의 함정이다: **창을 키우면 요인이 둘 움직인다.**")
    print("          A0′를 같은 창에서 다시 만드는 것이 그 둘을 하나로 되돌리는"
          " 유일한 길이다.")
    fired = (not v_ok_f) and bool(v_naive) and bool(v_naive_arrow)
    print(f"       {'✅ 발화' if fired else '🔴 발화 실패'}")
    ok.append(fired)

    # ── ⓙ 🆕 판정 규칙이 항목 집합을 들고 있는가 ──────────────────────
    print("\n  ⓙ 🆕 **판정 규칙의 항목 집합** — 화살표마다 사전 등록돼 있는가")
    legit_all = [(a.anchor, a.key) for a in arms if a.anchor and a.ran
                 and by[a.anchor].ran]
    miss_ok = [p for p in legit_all if p not in ARROW_ITEMSET]
    print(f"       실제 자격 쌍 {len(legit_all)}개 → 사전 등록 안 된 것"
          f" {len(miss_ok)}개"
          f"  {'✅ 조용하다 (오발화 대조)' if not miss_ok else '🔴 오발화'}")
    planted_map = {k: v for k, v in ARROW_ITEMSET.items() if k != ("A0′", "A4")}
    miss_bad = [p for p in legit_all if p not in planted_map]
    print(f"       심은 위반: `ARROW_ITEMSET`에서 «A0′→A4»를 뺀다 →"
          f" 사전 등록 안 된 것 {len(miss_bad)}개 {miss_bad}"
          f"  {'✅' if miss_bad else '🔴'}")
    # 🔴 그리고 «항목 집합 이름이 숫자뿐인가»는 실험 27의 `TitleRule`이 본다 —
    #    사전 등록의 네 줄·다섯 줄이 그 검사를 실제로 통과하는지 여기서 돌린다.
    trule = SP.TitleRule()
    bare = [f for f, _p, itemset, _h in DECISION_RULES
            if trule.BARE.match(itemset.strip())]
    print(f"       판정 규칙 {len(DECISION_RULES)}줄의 항목 집합 이름 →"
          f" 숫자뿐인 것 {len(bare)}개"
          f"  {'✅ 조용하다 (오발화 대조)' if not bare else '🔴 ' + str(bare)}")
    planted_bare = [t for t in ("10", "/10", " 3 ") if trule.BARE.match(t)]
    print(f"       심은 이름 «10» · «/10» · « 3 » → 숫자뿐으로 잡힌 것"
          f" {len(planted_bare)}개  {'✅' if len(planted_bare) == 3 else '🔴'}")
    print("       🔴 이름 없이 열을 만들면 «A4가 낮다»가 어느 분모에 대한"
          " 것인지가 사라진다 —")
    print("          A0′·A4의 재료는 S01–S24를 덮으므로 «구간 안 3»에서 읽으면"
          " 3분의 1만 보는 것이다.")
    fired = (not miss_ok) and bool(miss_bad) and (not bare) \
        and len(planted_bare) == 3
    print(f"       {'✅ 발화' if fired else '🔴 발화 실패'}")
    ok.append(fired)

    return all(ok), ok


# ══════════════════════════════════════════════════════════════════════
# 6. main
# ══════════════════════════════════════════════════════════════════════

def main():
    print("=" * W)
    print("실험 28 — 깊이 2의 «네 개의 0»이 무엇 탓인지 가른다")
    print("=" * W)
    print("  묻는 것: 실험 27의 lifetime이 낸 0이 «① P4 지시 / ② 재압축 /")
    print("           ③ 재료 24세션» 중 무엇 탓인가")
    print("  사양: `.omc/plans/ralplan-summary-layer.md` §3.1·§3.2·§3.3"
          " · 채점은 실험 27의 것을 **import**한다 (사본 금지 · F12)")

    # ── 0. 🔴 사전 등록 — 생성 한 건 전에 ──
    print("\n" + "=" * W)
    print("0. 🔴 사전 등록 — **무엇을 돌리고 어떤 값이 어떤 원인을 가리키나**")
    print("   (이 절은 생성 한 건이 나오기 전에 코드 상수에서 찍힌다)")
    print("=" * W)
    print(f"\n  팔 {len(ARM_SPECS)} — **앵커와 다른 요인이 정확히 하나**여야 한다"
          f" (요인은 **넷** — 창이 늘었다)")
    hdr = ["팔", "지시", "재료", "구간", "창 tok", "앵커", "움직인 요인"]
    widths = [6, 9, 11, 10, 9, 7, 12]
    print("  " + "".join(h.ljust(w) for h, w in zip(hdr, widths)))
    print("  " + "-" * sum(widths))
    for key, ins, mat, span, anc, moved, _n, win in ARM_SPECS:
        print("  " + "".join(str(v).ljust(w) for v, w in zip(
            [key, ins, mat, span, win, anc or "—", moved or "— (앵커)"],
            widths)))
    print("\n  🔴 **`A0′`가 이 라운드의 중심이다.** `A4`를 돌리려면 창을 키워야 하고,")
    print("     그러면 `A0`(창 8,192)과 `A4`(창 16,384)는 **재료와 창 둘**이 다르다.")
    print("     → **앵커를 같은 창에서 다시 만든다.** `A0′ → A4`가 재료 하나만"
          " 다르고,")
    print("     `A0 → A0′`가 창 하나만 다르다. **`A0 ↔ A4`에는 화살표를 안 건다.**")
    print("\n  🔴 판정 규칙 — **어떤 값이 어떤 원인을 가리키기로 했나**")
    for factor, pair, itemset, how in DECISION_RULES:
        print(f"\n     {factor}   {pair}   항목 집합: **{itemset}**")
        print(f"        {how}")
    print("\n  🔒 **화살표마다 읽을 항목 집합도 사전 등록이다** (계산하지 않는다)")
    for (k1, k2), which in ARROW_ITEMSET.items():
        print(f"     {k1} → {k2}   항목 집합 키 **{which}**")
    print(f"\n  🔴 {PREREG_CLOSING}")
    print("\n  ⚠️ **사전 등록된 한계 둘** (값을 보기 전에 적는다):")
    print("     · ①의 «지시»는 단일 요인이 **아니다** — `SESSION_TEMPLATE`은 형식·"
          "금지·길이 예산을")
    print("       한 덩어리로 바꾼다(3문장 vs 400토큰). 그래서 A1이 0이어도"
          " «어느 조각 탓인지»는")
    print("       못 가른다. 대신 **출력 글자 수를 팔마다 찍어** 길이가 설명이"
          " 되는지 보인다.")
    print("     · 🔄 **둘째 한계가 이 라운드에서 형태를 바꿨다.** 첫 판은"
          " *«A4는 창을 넘을 것으로")
    print("       예상하고, 넘으면 안 돌린다»*였다. **그 판단은 창 8,192에서"
          " 옳았다** — 아래 창")
    print("       예산 표가 지금도 그 줄을 찍는다. 이 라운드는 **창을 키워** 돌리고,"
          " 창이 요인이 된")
    print("       대가로 **앵커를 하나 더 만든다**(A0′). 남는 한계는 «창을 키운"
          " 것이 다른 무엇을")
    print("       움직였는가»이고, ④가 그것을 **별도 행**으로 잰다 —"
          " **못 재는 것이 아니라 잰다.**")

    # ── 1. 재료 ──
    print("\n" + "-" * W)
    print("1. 재료 — 실험 27과 **같은 파일**을 읽는다")
    print("-" * W)
    led = SP.load_ledger()
    sums, s2meta = round_summaries()
    rows = corpus_turns()
    sids = [sid for sid, _ in sums]
    print(f"  세션 요약  `SUMMARY_S2.json` **{len(sums)}건** (S01–S24)"
          f" — `summarize.session_digest` (사본 없음 · F12)")
    print(f"  원본 턴    `eval/corpus/corpus.jsonl` **{len(rows)}턴**"
          f" / 세션 {len({r['session'] for r in rows})}개 (읽기만 — A8)")
    print(f"  대장       `eval/fact-ledger.yaml` facts **{len(led['facts'])}**"
          f" · events **{len(led['events'])}** (읽기만 — A8)")
    print(f"  다이제스트 {s2meta['digest'][:16]}…  seed {s2meta['seed']}"
          f" · temperature {s2meta['temperature']}"
          f" · num_ctx {s2meta['num_ctx']}")

    # ── 2. 프롬프트 조립 앵커 ──
    print("\n" + "-" * W)
    print("2. 프롬프트 조립 앵커 — **프로덕션이 만드는 것을 뽑아 대조한다**"
          " (ollama 0회)")
    print("-" * W)
    prod = capture_production_prompt(sums)
    mine = assemble(
        summarize.P4_TEMPLATE.format(budget=summarize.LIFETIME_BUDGET_TOKENS),
        summarize._LIFETIME_MATERIAL_HEADER.format(k=len(sums)),
        summary_blocks(sums, len(sums)))
    same = mine == prod
    print(f"  `rewrite_lifetime`이 만드는 프롬프트 **{len(prod)}글자**")
    print(f"  이 파일의 `assemble()`이 만드는 것 **{len(mine)}글자**")
    print(f"  → {'✅ **바이트 동일**' if same else '🔴 다르다'}"
          f"  — {'A0은 실험 27의 팔이다' if same else '화살표를 그릴 근거가 없다'}")
    if not same:
        print("  🔴 조립이 프로덕션과 다르다. **종료 1** — A0을 실험 27의 팔이라"
              " 부를 수 없다")
        return 1

    # ── 3. 팔을 세우고 요인 규율을 집행한다 ──
    print("\n" + "-" * W)
    print(f"3. 팔 {len(ARM_SPECS)} — 🔴 **요인 규율을 종료 코드로 집행한다**")
    print("-" * W)
    arms = []
    for key, ins, mat, span, anc, moved, nsess, win in ARM_SPECS:
        a = Arm(key, ins, mat, span, anc, moved, window=win)
        instruction = (
            summarize.P4_TEMPLATE.format(
                budget=summarize.LIFETIME_BUDGET_TOKENS)
            if ins == "P4" else summarize.SESSION_TEMPLATE)
        if mat == "세션 요약":
            header = summarize._LIFETIME_MATERIAL_HEADER.format(k=nsess)
            blocks = summary_blocks(sums, nsess)
        else:
            take = sids[:nsess]
            blocks = turn_blocks(rows, take)
            nturn = sum(1 for r in rows if r["session"] in set(take))
            header = f"[재료 — 원본 턴 {nturn}건 · 세션 {nsess}개]"
        a.prompt = assemble(instruction, header, blocks)
        a.est_tok = est_tokens(a.prompt)
        arms.append(a)

    frule = FactorRule()
    viol_f = frule.audit(arms)
    print(f"  팔 {len(arms)}개 · 요인 규율 위반 **{len(viol_f)}건**"
          f"  {'✅' if not viol_f else '🔴'}")
    for v in viol_f:
        print(f"     {v}")
    if viol_f:
        print("  🔴 요인이 둘 이상 움직이는 팔이 있다. **종료 1** —"
              " 귀속할 수 없는 표는 그리지 않는다")
        return 1

    print("\n  창 예산 — **어느 팔이 돌 수 있나** (추정 글자×"
          f"{TOK_PER_CHAR} + {TOK_INTERCEPT} · ADR-016 §정직 6의 회귀)")
    hdr = ["팔", "프롬프트 글자", "추정 tok", "+생성 여유", "창 tok", "판정"]
    widths = [6, 15, 11, 12, 9, 10]
    print("  " + "".join(h.ljust(w) for h, w in zip(hdr, widths)))
    print("  " + "-" * sum(widths))
    for a in arms:
        fits, need, ctx = window_fits(a.est_tok, ctx=a.window)
        print("  " + "".join(str(v).ljust(w) for v, w in zip(
            [a.key, len(a.prompt), a.est_tok, need, ctx,
             "돈다" if fits else "🔴 안 돌린다"], widths)))

    # 🔴 **같은 가드를 A4에 두 창으로 대 본다.** 이 두 줄이 «창을 키운 것이 A4를
    #    돌게 한 유일한 변화»라는 주장을 **실행으로** 만든다 — 한 줄만 찍으면
    #    «원래 돌았던 것 아닌가»를 다음 사람이 물을 수 없다.
    a4 = next(a for a in arms if a.key == "A4")
    small = window_fits(a4.est_tok, ctx=PROD_NUM_CTX)
    big = window_fits(a4.est_tok, ctx=BIG_NUM_CTX)
    print(f"\n  🔴 **같은 팔 A4를 두 창에 대 본다** — 가드가 양쪽으로 갈린다")
    print(f"     창 {PROD_NUM_CTX} tok (프로덕션 기본값): 필요 {small[1]} tok →"
          f" **{'통과' if small[0] else '제외'}**"
          f"   ← 실험 28이 A4를 안 돌린 이유가 이 줄이다")
    print(f"     창 {BIG_NUM_CTX} tok (이 라운드):        필요 {big[1]} tok →"
          f" **{'통과' if big[0] else '제외'}**"
          f"   ← A0′도 같은 창에서 다시 만든다")
    print("\n  ⚠️ ollama는 창을 **넘는** 프롬프트를 말없이 버린다"
          " (HTTP 200 · `truncated` 필드")
    print("     없음 · 예외 없음 — ADR-016 §정직 8). 그래서 창을 키운 것으로"
          " 끝나지 않는다 —")
    print("     🔴 **모델이 그 창을 실제로 준다는 것을 실측으로 보여야 한다.**"
          " 아래 §4-b가")
    print("     **요청 창과 실측 `prompt_eval_count`를 나란히** 찍어 그것을"
          " 대신한다 (U9).")
    print("     ②의 S01–S12 판정은 그대로 **A3를 A2에 걸어** 읽는다."
          " 이 라운드가 더하는 것은")
    print("     ②′ — **같은 질문을 24세션 구간에서** 읽는 `A0′ → A4` 하나다.")

    # ── 4. 생성 ──
    print("\n" + "-" * W)
    print("4. 생성 — 체크포인트가 있으면 **생성 0건**")
    print("-" * W)
    rec = load_ckpt()
    todo = [a for a in arms
            if window_fits(a.est_tok, ctx=a.window)[0] and a.key != "A0"]
    if "A0" in rec:
        a0 = next(a for a in arms if a.key == "A0")
        a0.text, a0.meta, a0.ran = (rec["A0"]["text"], rec["A0"]["meta"], True)
    else:
        # A0은 **실험 27이 만든 lifetime 그 자체**다. 다시 만들지 않는다 —
        # 다시 만들면 그것은 실험 27의 팔이 아니라 이 실험이 만든 새 요약이다.
        if not os.path.exists(SP.LIFETIME_CKPT):
            info = llm.runtime_info()
            if not info.get("ollama"):
                print(f"  🔴 ollama({llm.OLLAMA_HOST})도 `LIFETIME_S27.json`도"
                      f" 없다. **종료 77 (SKIP)** — 통과가 아니라 미측정이다 (G1)")
                return 77
        life, lmeta, _fresh = SP.make_lifetime(sums)
        if life is None:
            print(f"  🔴 ollama({llm.OLLAMA_HOST})도 체크포인트도 없다."
                  f" **종료 77 (SKIP)** — 통과가 아니라 미측정이다 (G1)")
            return 77
        a0 = next(a for a in arms if a.key == "A0")
        a0.text, a0.ran = life, True
        a0.meta = dict(lmeta, instruction="P4", material="세션 요약",
                       span="S01–S24", est_tok=a0.est_tok,
                       prompt_chars=len(a0.prompt),
                       done_reason=None,
                       source="experiments/data/LIFETIME_S27.json (실험 27이 만든 것)")
        rec["A0"] = {"meta": a0.meta, "text": a0.text}
        save_ckpt(rec)
    print(f"  A0 — 실험 27이 만든 lifetime을 **그대로 읽는다**"
          f" (`LIFETIME_S27.json`). 이 실행의 생성 0건")

    made = 0
    for a in todo:
        if a.key in rec:
            print(f"  {a.key} — 체크포인트에서 읽었다. 이 실행의 생성 0건")
            generate_arm(a, rec)
            continue
        info = llm.runtime_info()
        if not info.get("ollama"):
            print(f"  🔴 ollama({llm.OLLAMA_HOST})가 없고 «{a.key}»의"
                  f" 체크포인트도 없다. **종료 77 (SKIP)** (G1)")
            return 77
        print(f"  {a.key} — 생성한다 ({a.instruction} 지시 · {a.material}"
              f" · {a.span})")
        made += int(generate_arm(a, rec))
    for a in arms:
        if not a.ran and window_fits(a.est_tok, ctx=a.window)[0]:
            print(f"  🔴 «{a.key}»가 돌지 않았다 — **종료 1**")
            return 1
    # 🔴 생성이 다 끝났다. **전역이 프로덕션 기본값으로 돌아왔는가** (G16).
    print(f"\n  🔴 창 복원 — `llm.LLM_NUM_CTX` = **{assert_prod_window()} tok**"
          f" (프로덕션 기본값 {PROD_NUM_CTX} tok)  ✅ 되돌아왔다")
    print(f"     팔별 창은 `use_window()`가 **블록 동안만** 바꾸고 `finally`로"
          f" 되돌린다 —")
    print(f"     `prototype/llm.py`는 **한 글자도 안 고쳤다.**"
          f" ⚠️ 그 파일이 아직 git에 추적되지 않으므로")
    print(f"     `git diff --stat prototype/llm.py`는 **무엇을 하든 조용하다** —"
          f" 무변경의 증거가 아니다.")
    print(f"     **이 줄이 그 증거다:** 창은 런타임 값이고, 여기서 그것이"
          f" 되돌아온 것을 실행이 확인했다.")

    print("\n  생성 회계 — **팔마다 단위와 함께** (G15)")
    hdr = ["팔", "생성", "벽시계", "정지", "시도", "실측 tok", "종료 사유",
           "출력 글자"]
    widths = [6, 6, 9, 6, 6, 11, 12, 11]
    print("  " + "".join(h.ljust(w) for h, w in zip(hdr, widths)))
    print("  " + "-" * sum(widths))
    total_wall, total_stall = 0.0, 0
    for a in arms:
        if not a.ran:
            print("  " + "".join(str(v).ljust(w) for v, w in zip(
                [a.key, "—", "—", "—", "—", "—", "안 돌림 (창)", "—"], widths)))
            continue
        m = a.meta
        total_wall += m.get("wall_s") or 0
        total_stall += m.get("stalls") or 0
        print("  " + "".join(str(v).ljust(w) for v, w in zip(
            [a.key, f"{m.get('n_generated', 1)}건", f"{m.get('wall_s')}s",
             f"{m.get('stalls')}회", f"{m.get('retries_used')}회",
             m.get("prompt_eval_count") or "?",
             m.get("done_reason") or "—", len(a.text)], widths)))
    print(f"\n  🔴 **위 벽시계·정지는 «그 팔을 만든 실행»의 기록이다** —"
          f" 체크포인트에서 읽은 팔의")
    print(f"     수는 이 실행이 쓴 시간이 아니다. 합계 **{total_wall:.1f}초**"
          f" · 정지 **{total_stall}회**")
    print(f"     · **이 실행이 새로 만든 것 {made}건**")
    for a in arms:
        if a.ran and a.meta.get("truncation_warning"):
            print(f"  🔴 «{a.key}» 절단 경고: {a.meta['truncation_warning']}")
    if not any(a.ran and a.meta.get("truncation_warning") for a in arms):
        print("  절단 경고: **없다** (돈 팔 전부)")

    # ── 4-b. 🔴 요청 창 vs 실측 토큰 — **말없이 잘리지 않았다는 증거** ──
    print("\n" + "-" * W)
    print("4-b. 🔴 **요청 창 vs 실측 토큰** — 말없이 잘리지 않았다는 증거 (U9)")
    print("-" * W)
    print("  ollama는 창을 넘는 프롬프트를 말없이 버리고, 그때 0.33.3 · `qwen3:8b`"
          "에서")
    print(f"  `prompt_eval_count`가 **`num_ctx/2 + 2`**로 왔다(세 척도 실측)."
          f" 그 자국이 **없다**는 것을")
    print("  보이려면 요청 창과 실측을 **나란히** 놓아야 한다. ⚠️ 이 표의 «자국»"
          " 열은 **판정이 아니다** —")
    print("  판정은 `summarize._truncation_warning`의 두 관측 조건이 하고,"
          " 그쪽은 `/2+2`에 안 기댄다.")
    hdr = ["팔", "요청 num_ctx", "추정 tok", "실측 tok", "실측/추정",
           "절단 자국 tok", "절단 경고"]
    widths = [6, 14, 10, 10, 11, 15, 12]
    print("  " + "".join(h.ljust(w) for h, w in zip(hdr, widths)))
    print("  " + "-" * sum(widths))
    trunc_clear = True
    for a in arms:
        if not a.ran:
            continue
        m = a.meta
        got = m.get("prompt_eval_count")
        # A0은 실험 27이 만든 것이라 `requested_num_ctx`를 안 들고 있다 —
        # **추정으로 메우지 않는다.** 그 팔의 기록된 `num_ctx`가 곧 요청 창이다.
        req = m.get("requested_num_ctx") or m.get("num_ctx") or a.window
        foot = truncation_footprint(req)
        ratio = f"{100.0 * got / a.est_tok:.0f}%" if got else "?"
        # 🔴 «자국과 다른가»만 본다. 같으면 그 팔은 **잘렸을 수 있다**는 뜻이고,
        #    그때 숫자를 그냥 못 쓴다.
        clear = got is not None and got != foot
        trunc_clear = trunc_clear and clear
        print("  " + "".join(str(v).ljust(w) for v, w in zip(
            [a.key, req, a.est_tok, got or "?", ratio,
             f"{foot} ({'≠ 실측' if clear else '🔴 = 실측'})",
             m.get("truncation_warning") or "없다"], widths)))
    print(f"\n  → 절단 자국과 일치한 팔 **{'없다  ✅' if trunc_clear else '있다  🔴'}**"
          f" · `_truncation_warning`이 붙은 팔"
          f" **{sum(1 for a in arms if a.ran and a.meta.get('truncation_warning'))}"
          f"개**")
    a4m = next((a for a in arms if a.key == "A4" and a.ran), None)
    if a4m is not None:
        got4 = a4m.meta.get("prompt_eval_count")
        print(f"  🔴 **A4가 이 표의 하중을 받는 줄이다.** 요청 {a4m.window} tok ·"
              f" 실측 **{got4} tok** —")
        print(f"     프로덕션 창 {PROD_NUM_CTX} tok**보다 크다**"
              f" ({got4 - PROD_NUM_CTX:+d} tok). 즉 이 프롬프트는")
        print(f"     8,192 창에서는 **들어갈 수 없었고**, 16,384 창에서는"
              f" **통째로 들어갔다.**")
        print(f"     그리고 실측이 «절반 절단» 자국"
              f" {truncation_footprint(a4m.window)} tok과 **다르다** —")
        print(f"     `qwen3.context_length` 40,960 tok이 그것을 뒷받침한다"
              f" (`/api/show`).")

    print("\n  🔴 다이제스트 **문자열 대조** (생존 확인이 아니다):")
    for a in arms:
        if not a.ran:
            continue
        for key, ckv, mineval, now in SP.digest_compare(a.meta):
            if key != "digest":
                continue
            same_d = ckv == mineval == now
            print(f"     {a.key}  기록 {str(ckv)[:16]}…"
                  f" · 이 팔 {str(mineval)[:16]}…"
                  f" · 지금 {str(now)[:16]}…   "
                  f"{'✅ 같다' if same_d else '⚠️ 다르다'}")

    # ── 5. 본문 ──
    print("\n" + "-" * W)
    print("5. 각 팔이 실제로 쓴 것 — **본문을 찍는다**")
    print("-" * W)
    for a in arms:
        if not a.ran:
            continue
        print(f"\n  ── {a.label()} · {len(a.text)}글자 ──")
        for line in a.text.strip().splitlines():
            print(f"     | {line.rstrip()}")

    # ── 6. 표 ──
    print("\n" + "-" * W)
    print("6. 결과 — 🔴 **항목 집합마다 표를 가르고 제목에 이름을 박는다**"
          " (§3.1·§3.3)")
    print("-" * W)
    ev_all = led["events"]
    span12 = {f"S{i:02d}" for i in range(1, 13)}
    ev_in12 = [e for e in ev_all if e["at"]["session"] in span12]
    facts = led["facts"]
    names = SP.SCORER_NAMES

    def rows_for(items):
        out = []
        for a in arms:
            # 재료의 상한은 **재료 자체**를 채점한다 — 지시도 꼬리표도 빼고,
            # 요약이 담을 수 있었던 최대치가 얼마였나만 본다.
            if a.material == "세션 요약":
                mat_text = SP.join(sums[:a.n_sessions])
            else:
                mat_text = "\n".join(
                    f"{r['seq']}. [{r['role']}] {r['text']}" for r in rows
                    if r["session"] in {f"S{i:02d}"
                                        for i in range(1, a.n_sessions + 1)})
            g = SP.score_all(mat_text, items)
            out.append((f"{a.key} 재료 상한 ({a.material} · {a.span})",
                        [SP.cell(g, s) for s in names]))
            if a.ran:
                gg = SP.score_all(a.text, items)
                out.append((f"{a.key} 요약 ({a.instruction} 지시)",
                            [SP.cell(gg, s) for s in names]))
            else:
                out.append((f"{a.key} 요약 ({a.instruction} 지시)",
                            ["—"] * len(names)))
        return out

    rule = SP.TitleRule()
    cols_a = [SP.Col("M2 사건", "events 10", "S01–S24", s) for s in names]
    rows_a = rows_for(ev_all)
    SP.render("표 A — **M2 사건(events 10 · S01–S24)** — ⛔ 기준선 화살표 없음",
              cols_a, rows_a,
              note=("  🔴 **A2·A3의 재료는 S01–S12만 덮는다** — 이 표에서 그 두"
                    " 팔의 낮은 수를\n"
                    "     «요약이 못 담았다»로 읽으면 안 된다. 그 팔들의 판정은"
                    " 아래 표 B에서 읽는다.\n"
                    "     그것이 사전 등록이 항목 집합을 요인마다 다르게 고른"
                    " 이유다."))

    print("\n  " + "─" * (W - 4))
    print("  🔴 **위 표와 아래 표 사이에 화살표를 그리지 않는다.** 분모가 `/10`과"
          " `/3`으로 다르고")
    print("     항목 집합도 다르다 — 모양이 달라 눈에 띌 뿐, 규칙은 같다(§3.3 ②).")
    print("  " + "─" * (W - 4))

    cols_b = [SP.Col("M2 구간 안 사건", f"events {len(ev_in12)}", "S01–S12", s)
              for s in names]
    rows_b = rows_for(ev_in12)
    SP.render("표 B — **M2 구간 안 사건"
              f"(events {len(ev_in12)} · S01–S12)** — 🔴 ③·②의 판정 열",
              cols_b, rows_b,
              note=("  구간 안 사건: "
                    + ", ".join(f"{e['id']}({e['at']['session']})"
                                for e in ev_in12) + "\n"
                    "  🔴 **네 팔의 재료가 전부 이 3개를 덮는다** — A0·A1의"
                    " 재료(S01–S24)도 포함한다.\n"
                    "     그래서 이 항목 집합에서는 네 팔이 **같은 자격**으로"
                    " 채점된다."))

    # 🔴 **생존 항목의 id를 찍는다.** 분수만 적으면 «어느 사건이 남았나»가
    #    사라지고, X1(축자 채점기의 위양성·위음성)을 다음 사람이 못 본다 —
    #    실험 27이 `E010`의 위양성을 그렇게 잡았다.
    print("\n  🔴 **생존 항목 (v2) — 분수만 적으면 어느 사건이 남았는지가 사라진다**")
    for a in arms:
        if not a.ran:
            print(f"     {a.key} 요약: — (안 돌린 팔)")
            continue
        g10 = SP.score_all(a.text, ev_all)
        g3 = SP.score_all(a.text, ev_in12)
        print(f"     {a.key} 요약  events 10: "
              f"{', '.join(g10['v2'][3]) or '**없다**'}"
              f"   ·   구간 안 events {len(ev_in12)}: "
              f"{', '.join(g3['v2'][3]) or '**없다**'}")

    # ── 6-b. 🔴 두 채점기가 갈리는 자리 ──────────────────────────────
    #
    # 실험 27 §B가 **v2를 골랐다** — 그 재료에서 v3의 유일한 차이가 위음성
    # (`E004`)이었기 때문이다. 🔴 **이 라운드의 A1에서는 방향이 반대다.**
    # 갈리는 사건을 이름으로 찍고 서수 머리로 귀속시킨다 — 실험 27 §2-b와
    # 같은 형태이고, 같은 함수(`scoring._ordinal_heads`)를 부른다.
    print("\n  🔴 **두 채점기가 갈리는 자리 — 사전 등록한 자는 `v2`다"
          " (실험 27 §B의 결정)**")
    import scoring                                           # noqa: PLC0415
    any_split = False
    for a in arms:
        if not a.ran:
            continue
        g = SP.score_all(a.text, ev_all)
        only_v2 = sorted(set(g["v2"][3]) - set(g["v3"][3]))
        if not only_v2:
            print(f"     {a.key}: 갈리는 사건 **없다** (v2 {SP.cell(g, 'v2')}"
                  f" = v3 {SP.cell(g, 'v3')})")
            continue
        any_split = True
        print(f"     {a.key}: v2 {SP.cell(g, 'v2')} · v3 {SP.cell(g, 'v3')}"
              f" — 갈리는 사건 **{', '.join(only_v2)}**")
        th = scoring._ordinal_heads(a.text)
        for eid in only_v2:
            e = next(x for x in ev_all if x["id"] == eid)
            ih = scoring._ordinal_heads(e["text"])
            conflict = [h for h, o in ih.items() if th.get(h) and not (o & th[h])]
            print(f"        {eid} «{e['text']}» — 항목 서수 머리 {ih}")
            print(f"           본문 서수 머리 "
                  f"{ {h: sorted(th[h]) for h in ih if h in th} }"
                  f"  · 어긋나는 머리 {conflict}")
    if any_split:
        print("     🔴 **이것은 실험 27 §B가 본 것의 반대 방향이다.** 그 라운드는"
              " v3이 «재료 안에")
        print("        있는 사건을 죽인다»(위음성)는 이유로 v2를 골랐다. 여기서"
              " v2는 요약이 **쓰지도")
        print("        않은 회차**를 살려 준다 — 실험 26이 «면접 회차 위양성"
              " 셋»이라 이름 붙인 그 갈래다.")
        print("     🔒 **그래도 채점기를 바꾸지 않는다.** 사전 등록이 v2이고,"
              " 값을 보고 자를 고르는 것이")
        print("        이 저장소가 금지한 형태다. **대신 두 열을 나란히 찍고,"
              " 아래 §12가 그 대가를")
        print("        이름으로 적는다** — 판정의 방향은 두 자에서 같고,"
              " **크기만 다르다.**")

    print("\n  " + "─" * (W - 4))
    cols_c = [SP.Col("M4 사실 누출", f"facts {len(facts)} (판정불가 별도)",
                     "S01–S24", s) for s in names]
    rows_c = rows_for(facts)
    SP.render("표 C — **M4 사실 누출(facts 12 · S01–S24)** — 🔴 **부호가 반대다."
              " 낮을수록 준수**",
              cols_c, rows_c,
              note=("  🔴 **M4를 «준수»로 읽으려면 같은 팔의 M2가 0이 아니어야"
                    " 한다.**\n"
                    "     사실도 사건도 0이면 «사실을 안 썼다»와 «아무것도 안"
                    " 남았다»가 같은 관측이다\n"
                    "     (실험 27 §E). 그래서 아래 판정은 M4를 **혼자 쓰지"
                    " 않는다.**"))

    # ── 7. M1 ──
    print("\n" + "-" * W)
    print("7. M1 형식 준수 — 🔴 **없는 계약은 채점하지 않는다**")
    print("-" * W)
    for a in arms:
        if not a.ran:
            print(f"  {a.key}  —        (안 돌린 팔)")
            continue
        cellv = m1_cell(a)
        why = ("" if a.instruction == "P4" else
               "  ← `SESSION_TEMPLATE`은 표제를 요구하지 않는다."
               " **0/3이 아니라 «해당 없음»이다**")
        print(f"  {a.key}  **{cellv}**  ({a.instruction} 지시){why}")
    print("\n  ⚠️ **위생 검사이지 판정이 아니다**(§3.1). 표제가 있다는 것은 형식을"
          " 지켰다는 뜻이지")
    print("     내용이 옳다는 뜻이 아니다 — X3. 실험 27의 3/3과 M2 0/10이"
          " 모순이 아닌 것과 같다.")

    # ── 8. M3 ──
    print("\n" + "-" * W)
    print("8. M3 시간 순서 — 🔴 **M2가 그 텍스트에서 잡은 사건 위에서만** 정의된다")
    print("-" * W)
    m3res = {}
    for a in arms:
        if not a.ran:
            continue
        g = SP.score_all(a.text, ev_all)
        matched = [e for e in ev_all if e["id"] in g["v2"][3]]
        r = SP.m3(a.text, matched)
        m3res[a.key] = r
        head = (f"  {a.key} — M2(v2)가 잡은 사건 **{len(matched)}건**"
                f" → 위치를 얻은 것 **k={r.k}**")
        if r.reason:
            print(head + f"\n     → **{r.reason}** — 숫자를 만들지 않는다")
        else:
            print(head + f" · 쌍 **{r.pairs}**"
                         f"\n     → **M3 = {SP.m3_fmt(r)}** (동률 {r.ties}쌍을"
                         f" 불일치로 셌다)")

    # ── 9. 🔴 판정 ──
    print("\n" + "=" * W)
    print("9. 🔴 **판정 — 사전 등록한 규칙 그대로 읽는다**")
    print("=" * W)
    m2_all = {a.key: SP.score_all(a.text, ev_all) for a in arms if a.ran}
    m2_12 = {a.key: SP.score_all(a.text, ev_in12) for a in arms if a.ran}
    mat_12 = {}
    for a in arms:
        mt = (SP.join(sums[:a.n_sessions]) if a.material == "세션 요약" else
              "\n".join(f"{r['seq']}. [{r['role']}] {r['text']}" for r in rows
                        if r["session"] in {f"S{i:02d}"
                                            for i in range(1, a.n_sessions + 1)}))
        mat_12[a.key] = SP.score_all(mt, ev_in12)

    # (요인, 앵커, 팔, **사전 등록된** 항목 집합 키)
    CONTRASTS = (("①  지시", "A0", "A1", "10"),
                 ("③  재료 크기", "A0", "A2", "3"),
                 ("②  재압축", "A2", "A3", "3"))
    SETS = {"10": ("events 10 · S01–S24", m2_all),
            "3": (f"구간 안 events {len(ev_in12)} · S01–S12", m2_12)}

    verdicts, splits = [], []
    for factor, base, arm_k, prereg in CONTRASTS:
        label, table = SETS[prereg]
        b, v = table[base]["v2"][0], table[arm_k]["v2"][0]
        hit = v > b
        # 🔴 사전 등록의 문구는 «0을 벗어나면»이고 여기 코드는 «앵커보다 크면»이다.
        #    앵커 값이 0이 아니면 그 둘이 갈린다 — **갈리는지 매 실행 확인한다.**
        assert b == 0 or (v > 0) == hit, (
            f"«{factor}»의 앵커 값이 {b}이라 «0을 벗어나면»과 «앵커보다 크면»이"
            f" 다른 답을 준다 — 사전 등록의 문구를 다시 적어야 한다")
        other = "3" if prereg == "10" else "10"
        olabel, otable = SETS[other]
        ob, ov = otable[base]["v2"][0], otable[arm_k]["v2"][0]
        ohit = ov > ob
        # 🔴 **다른 자로도 읽는다.** 사전 등록은 v2이고 바꾸지 않지만, «자를
        #    바꾸면 답이 뒤집히는가»는 판정의 강도 그 자체다 (§3.3 ④).
        b3, v3n = table[base]["v3"][0], table[arm_k]["v3"][0]
        # ⚠️ 🔄 **정정 — 이 절의 첫 판이 여기서 틀렸다.** v3 줄을 아래 인쇄
        #    루프에서 만들면서 `table`·`b`·`v`를 **바깥 루프의 마지막 값**으로
        #    읽었고, 그래서 세 요인이 전부 ②의 표와 크기를 찍었다. 출력이 그것을
        #    드러냈다(①의 v3 줄이 `/3` 분모를 달고 나왔다). **한 요인의 값을 다른
        #    요인의 표에서 읽는 것** — 이 저장소가 실패 모드 ②라 부르는 그 형태다.
        #    → 한 요인의 모든 수를 **그 요인의 반복 안에서** 만들어 dict에 담는다.
        verdicts.append({
            "factor": factor, "hit": hit, "base": base, "arm": arm_k,
            "label": label, "bc": SP.cell(table[base], "v2"),
            "vc": SP.cell(table[arm_k], "v2"), "size": v - b,
            "olabel": olabel, "obc": SP.cell(otable[base], "v2"),
            "ovc": SP.cell(otable[arm_k], "v2"), "ohit": ohit,
            "b3c": SP.cell(table[base], "v3"),
            "v3c": SP.cell(table[arm_k], "v3"),
            "h3": v3n > b3, "size3": v3n - b3,
        })
        if ohit != hit:
            splits.append((factor, label, olabel))

    for d in verdicts:
        hit, base, arm_k = d["hit"], d["base"], d["arm"]
        print(f"\n  {d['factor']}"
              f"  {'🔴 **원인이다**' if hit else '⛔ 원인이 **아니다**'}")
        print(f"     🔒 사전 등록한 열 — 항목 집합 **{d['label']}**")
        print(f"        {base} **{d['bc']}**  →  {arm_k} **{d['vc']}**"
              f"   (M2 · v2 · 크기 {d['size']:+d})")
        print(f"        재료 상한(구간 안): {base} {SP.cell(mat_12[base], 'v2')}"
              f"  →  {arm_k} {SP.cell(mat_12[arm_k], 'v2')}"
              f"   ← 🔴 **상한이 함께 움직였는지 여기서 본다**")
        mark = "🔴 **갈린다**" if d["ohit"] != hit else "같은 답"
        print(f"     참고 열 — 항목 집합 {d['olabel']}: {base} {d['obc']}"
              f" → {arm_k} {d['ovc']}"
              f"  ({'원인이다' if d['ohit'] else '원인이 아니다'} · {mark})")
        print(f"     다른 자 — **같은 열**({d['label']})을 `v3`으로:"
              f" {base} {d['b3c']} → {arm_k} {d['v3c']}"
              f"  ({'원인이다' if d['h3'] else '원인이 아니다'} ·"
              f" {'같은 방향' if d['h3'] == hit else '🔴 **자를 바꾸면 뒤집힌다**'}"
              f" · 크기 {d['size3']:+d} vs v2 {d['size']:+d})")
    if splits:
        print("\n  🔴 **두 항목 집합이 갈린 요인이 있다 — 숨기지 않고 적는다:**")
        for factor, label, olabel in splits:
            print(f"     · {factor} — «{label}»에서는 원인이고"
                  f" «{olabel}»에서는 아니다(또는 그 반대다).")
        print("     **판정은 사전 등록한 열을 따른다**(값을 보고 열을 고르는 것이")
        print("     이 저장소가 금지한 형태다). 갈린 것 자체는 아래 §12에 남긴다.")
    culprits = [d["factor"] for d in verdicts if d["hit"]]
    print("\n  " + "─" * (W - 4))
    if len(culprits) == 1:
        print(f"  🔴 **0의 원인은 «{culprits[0].strip()}» 하나다.**"
              f" 나머지 둘은 되돌려도 0을 못 벗어난다.")
    elif len(culprits) > 1:
        print(f"  🔴 **원인이 둘 이상 갈렸다: {culprits}.**"
              f" 각각 단독으로 0을 벗어나게 한다.")
    else:
        print("  🔴 **셋 다 단독 원인이 아니다.** 어느 한 요인을 되돌려도 M2는"
              " 0을 안 벗어난다.")
        print("     ⚠️ **«가르지 못했다»가 아니다** — 세 후보를 하나씩 실제로"
              " 되돌려 보고 셋 다")
        print("     기각한 것이다. 남는 설명은 **«세 요인의 결합»** 또는"
              " **«자(M2) 자체»**이고,")
        print("     🔴 **A3까지 0이면 ⭐핵심 1(«범인은 재압축»)은 이 재료에서"
              " 재확인되지 않는다** —")
        print("     원본 턴을 **한 번만** 압축해도 같은 0이 나오기 때문이다.")
    print("  " + "─" * (W - 4))

    # ── 9-b. 🆕 창의 효과와 ②′ — **별도 행이다** ─────────────────────
    #
    # 🔴 위 `CONTRASTS`에 안 넣는다. 그 루프의 «hit»은 «0의 **원인**인가»를 뜻하고
    #    `culprits`가 그 답을 센다. **창은 0의 후보 원인이 아니었다** — 실험 28의
    #    사전 등록이 후보로 셋만 세웠다. 창을 그 목록에 끼우면 «원인이 넷 중
    #    하나»라는 문장이 나오는데, 그것은 **이 라운드가 만든 요인**이다.
    print("\n" + "=" * W)
    print("9-b. 🆕 🔴 **창의 효과(④)와 ②′ — 별도 행으로 읽는다**")
    print("=" * W)
    print("  🔒 두 행 다 사전 등록한 항목 집합은 **events 10 · S01–S24**다"
          " — A0·A0′·A4의")
    print("     재료가 전부 그 구간을 덮으므로 세 팔이 **같은 자격**으로 채점된다.")

    by = {a.key: a for a in arms}
    a0k, a0p, a4k = "A0", "A0′", "A4"
    extra_verdicts = []
    absent = [k for k in (a0k, a0p, a4k) if k not in m2_all]
    if absent:
        print(f"  🔴 세 팔 중 안 돈 것이 있다 {absent} —"
              f" **숫자를 만들지 않는다**")
    else:
        b_win = m2_all[a0k]["v2"][0]
        v_win = m2_all[a0p]["v2"][0]
        same_win = v_win == b_win
        print(f"\n  ④  창"
              f"  {'⛔ 결과를 **안 바꾼다**' if same_win else '🔴 **바꾼다**'}")
        print(f"     🔒 사전 등록한 열 — 항목 집합 **events 10 · S01–S24**")
        print(f"        {a0k} **{SP.cell(m2_all[a0k], 'v2')}**  →"
              f"  {a0p} **{SP.cell(m2_all[a0p], 'v2')}**"
              f"   (M2 · v2 · 크기 {v_win - b_win:+d})")
        print(f"        다른 자 v3: {SP.cell(m2_all[a0k], 'v3')} →"
              f" {SP.cell(m2_all[a0p], 'v3')}"
              f"   · 참고 열 구간 안 {len(ev_in12)}:"
              f" {SP.cell(m2_12[a0k], 'v2')} → {SP.cell(m2_12[a0p], 'v2')}")
        print(f"        재료 상한(구간 안): {SP.cell(mat_12[a0k], 'v2')} →"
              f" {SP.cell(mat_12[a0p], 'v2')}"
              f"   ← 재료가 **같으므로 움직이면 안 된다**")
        print(f"        출력 글자 {len(by[a0k].text)} → {len(by[a0p].text)}"
              f"  · 실측 입력 {by[a0k].meta.get('prompt_eval_count')} →"
              f" {by[a0p].meta.get('prompt_eval_count')} tok"
              f"  (프롬프트는 **바이트 동일**하다)")
        # 🔴 **M2가 같은 것보다 강한 관측이 있으면 그것을 적는다.** 두 팔의
        #    프롬프트가 바이트 동일하므로 «본문도 바이트 동일한가»를 물을 수 있다.
        same_text = by[a0k].text == by[a0p].text
        print(f"        🔴 **본문 바이트 대조**: A0 ↔ A0′ →"
              f" {'**동일하다**' if same_text else '다르다'}"
              f"   (M2가 같은 것보다 **강한** 관측이다)")
        if same_text:
            print("        ⚠️ 그래도 «생성이 결정적이다»로 읽지 않는다 —"
                  " ADR-016 §미해결 U3이 24세션")
            print("           전량 실행 **두 번**이 3,202 tok과 3,276 tok을 냈다고"
                  " 적어 뒀다. 이것은")
            print("           **이 한 쌍의 관측**이고, n=1이다 (Y5·Y10).")
        if same_win:
            print("     → 🔴 **창은 이 재료에서 M2를 안 바꿨다.** 그래서 아래 ②′의"
                  " 크기를 «창 탓»으로")
            print("        깎을 근거가 **없다** — 사전 등록이 요구한 대조가 바로"
                  " 이것이다.")
        else:
            print("     → 🔴 **창이 값을 움직였다. 그것 자체가 이 라운드의"
                  " 결과다.** 아래 ②′의 크기를")
            print(f"        읽을 때 **이만큼({v_win - b_win:+d})을 깎는다** —"
                  f" 재료가 아니라 창이 만든 몫이다.")

        b2, v2n = m2_all[a0p]["v2"][0], m2_all[a4k]["v2"][0]
        hit2 = v2n > b2
        b2v3, v2v3 = m2_all[a0p]["v3"][0], m2_all[a4k]["v3"][0]
        print(f"\n  ②′ 재압축 · 24세션 구간"
              f"  {'🔴 **참이다**' if hit2 else '⛔ **재확인되지 않는다**'}")
        print(f"     🔒 사전 등록한 열 — 항목 집합 **events 10 · S01–S24**")
        print(f"        {a0p} **{SP.cell(m2_all[a0p], 'v2')}**  →"
              f"  {a4k} **{SP.cell(m2_all[a4k], 'v2')}**"
              f"   (M2 · v2 · 크기 {v2n - b2:+d})")
        print(f"        다른 자 — **같은 열**을 v3으로:"
              f" {SP.cell(m2_all[a0p], 'v3')} → {SP.cell(m2_all[a4k], 'v3')}"
              f"  ({'참이다' if v2v3 > b2v3 else '재확인되지 않는다'} ·"
              f" {'같은 방향' if (v2v3 > b2v3) == hit2 else '🔴 **뒤집힌다**'}"
              f" · 크기 {v2v3 - b2v3:+d} vs v2 {v2n - b2:+d})")
        print(f"        참고 열 — 구간 안 events {len(ev_in12)} · S01–S12:"
              f" {SP.cell(m2_12[a0p], 'v2')} → {SP.cell(m2_12[a4k], 'v2')}")
        print(f"        재료 상한(구간 안): {SP.cell(mat_12[a0p], 'v2')} →"
              f" {SP.cell(mat_12[a4k], 'v2')}"
              f"   ← 🔴 **상한이 함께 움직였는지 여기서 본다** (Y7)")
        print(f"        생존 항목(v2) — {a0p}"
              f" {', '.join(m2_all[a0p]['v2'][3]) or '**없다**'}  →  {a4k}"
              f" {', '.join(m2_all[a4k]['v2'][3]) or '**없다**'}")
        print("\n  " + "─" * (W - 4))
        if hit2:
            print("  🔴 **②는 24세션 구간에서도 참이다.** 같은 지시·같은 구간·같은"
                  " 창에서 재료를")
            print("     «이미 압축된 세션 요약»에서 «원본 턴»으로 바꾸는 것만으로"
                  " M2가 0을 벗어난다.")
            print("     Y2가 «모른다»고 적어 둔 자리가 **채워졌다.**")
        else:
            print("  ⛔ **②는 24세션 구간에서 재확인되지 않는다.** A3↔A2가 낸"
                  " 판정은 **S01–S12의**")
            print("     **성질**이었고, 구간을 24세션으로 늘리면 재압축을 되돌려도"
                  " M2가 안 움직인다.")
            print("     ⚠️ **«차이 없음»은 정당한 결과다** — 숫자를 만들지 않는다."
                  " 그리고 이것은")
            print("     «②가 거짓»이 아니라 **«②가 이 구간에서는 안 보인다»**이다."
                  " 아래 §12가 그 차이를 적는다.")
        print("  " + "─" * (W - 4))
        extra_verdicts = [
            ("④  창", a0k, a0p, same_win, v_win - b_win,
             "결과를 안 바꾼다" if same_win else "🔴 바꾼다"),
            ("②′ 재압축·24세션", a0p, a4k, hit2, v2n - b2,
             "🔴 참이다" if hit2 else "재확인되지 않는다"),
        ]

    # ── 10. 화살표를 그릴 수 있는 자리 / 없는 자리 ──
    print("\n" + "-" * W)
    print("10. 🔴 화살표를 **그릴 수 있는 자리 / 없는 자리**")
    print("-" * W)
    arule = ArrowRule()
    legit = [(a.anchor, a.key) for a in arms
             if a.anchor and a.ran and
             next(x for x in arms if x.key == a.anchor).ran]
    viol_arrow = arule.audit(arms, legit)
    # 🔴 **사전 등록된 항목 집합이 없는 화살표는 안 그린다.** 첫 판은 이것을
    #    요인 이름에서 **계산**했고, 창이 요인으로 늘자 그 규칙이 A0→A0′·A0′→A4를
    #    둘 다 «구간 안 3»으로 보냈다 — 두 팔의 재료가 S01–S24를 전부 덮는데
    #    3분의 1만 보고 읽는 것이다. → 계산을 버리고 `ARROW_ITEMSET`을 읽는다.
    missing = [p for p in legit if p not in ARROW_ITEMSET]
    print(f"  자격 있는 팔 쌍 **{len(legit)}개** · 자격 규율 위반"
          f" **{len(viol_arrow)}건**  {'✅' if not viol_arrow else '🔴'}"
          f" · 항목 집합이 사전 등록 안 된 쌍 **{len(missing)}개**"
          f"  {'✅' if not missing else '🔴'}")
    if missing:
        print(f"  🔴 {missing}의 항목 집합이 `ARROW_ITEMSET`에 없다. **종료 1** —"
              f" 어느 자에서 읽을지를")
        print("     값을 보고 고르는 것이 이 저장소가 금지한 형태다")
        return 1
    for k1, k2 in legit:
        d = frule.diff(arms, k1, k2)
        a2 = next(x for x in arms if x.key == k2)
        items, label = ((ev_all, "events 10 · S01–S24")
                        if ARROW_ITEMSET[(k1, k2)] == "10"
                        else (ev_in12,
                              f"구간 안 events {len(ev_in12)} · S01–S12"))
        g1 = SP.score_all(next(x for x in arms if x.key == k1).text, items)
        g2 = SP.score_all(a2.text, items)
        print(f"  🔁 **{k1} → {k2}**  (다른 요인 «{d[0]}» 하나)"
              f"  항목 집합 {label}")
        print(f"       M2(v2) **{SP.cell(g1, 'v2')} → {SP.cell(g2, 'v2')}**"
              f"   [v3 {SP.cell(g1, 'v3')} → {SP.cell(g2, 'v3')}]")
    print("\n  ⛔ **화살표가 없는 자리 — 이유를 이름으로 적는다**")
    print(f"  · **A0 ↔ A3**: 요인 둘(재료·구간)이 함께 움직인다."
          f" ②의 판정은 A3↔A2에서 읽는다")
    print(f"  · 🔄 **A0 ↔ A4**: **정정.** 첫 판은 *«요인은 하나(재료)인데 A4가"
          f" 안 돌았다»*였다.")
    print(f"    A4는 이제 **돌았고**, 그래서 이유가 바뀌었다 —"
          f" **요인이 둘(재료·창)이다.**")
    print(f"    창 {PROD_NUM_CTX} → {BIG_NUM_CTX} tok과 재료가 함께 움직인다."
          f" ②′는 **A0′에 걸어** 읽는다")
    print(f"  · **A0′ ↔ A1/A2/A3**: 창이 다른 위에 지시·구간·재료가 겹쳐 다르다")
    print(f"  · **A1 ↔ A2/A3**: 지시와 구간이 함께 다르다")
    print(f"  · **실험 28 ↔ 실험 27의 기준선 «2층 · 기본 지시»(2/10)**:"
          f" 항목 집합(혼합 11)과")
    print(f"    재료·지시가 함께 다르다. 실험 27이 이미 «화살표 없음»으로 적었고"
          f" 이 라운드도 안 건다")
    print(f"  · **A0 ↔ 실험 27**: 화살표가 아니라 **같은 값**이다 —"
          f" A0의 본문은 `LIFETIME_S27.json`")
    print(f"    그 자체이고, 위 §2가 프롬프트까지 바이트 동일임을 확인했다")

    # ── 11. 표 규율 감사 ──
    print("\n" + "-" * W)
    print("11. 표 규율 감사 — 실험 27의 `TitleRule`을 그대로 돌린다")
    print("-" * W)
    all_cols = cols_a + cols_b + cols_c
    all_rows = ([r[0] for r in rows_a] + [r[0] for r in rows_b]
                + [r[0] for r in rows_c])
    # 🔴 세 표가 **같은 행 라벨 집합**을 쓴다 — 한 표 안에서만 유일하면 된다.
    #    `audit_rows`는 중복을 X6 재발로 보므로 표마다 따로 부른다.
    viol = rule.audit(all_cols)
    for rr in (rows_a, rows_b, rows_c):
        viol += rule.audit_rows([r[0] for r in rr])
    print(f"  열 {len(all_cols)}개 · 행 라벨 {len(all_rows)}개 (표 3개)"
          f" · 위반 **{len(viol)}건**  {'✅' if not viol else '🔴'}")
    for v in viol:
        print(f"     {v}")

    # ── 12. 못 가른 것 ──
    print("\n" + "-" * W)
    print("12. ⚠️ **이 실험이 닫지 않는 것**")
    print("-" * W)
    print("""
  Y1  **①의 «지시»는 단일 요인이 아니다.** `SESSION_TEMPLATE`은 형식·사실 금지·
      길이 예산(3문장 vs 400토큰)을 한 덩어리로 바꾼다. A1의 값이 그중 어느
      조각 탓인지 이 실험은 **못 가른다.** 사전 등록에 미리 적었고, 완화는
      «출력 글자 수를 팔마다 찍는 것» 하나다.

  Y2  🔄 **정정 — A4가 돌았다.** 이 항목의 첫 판은 *"②의 «같은 구간» 팔(A4)은
      돌지 않았다 … 창을 늘려 재려면 그것이 또 하나의 요인이 된다"*였다.
      **창을 늘렸고, 예고한 대로 그것이 또 하나의 요인이 됐다** — 그래서
      앵커를 같은 창에서 다시 만들었다(A0′). ②′의 판정은 §9-b에 있고,
      **④가 창의 몫을 별도 행으로 뺀다.** 🔴 **이 줄을 지우지 않는다:**
      «창 8,192에서는 못 쟀다»가 참이고, 그 «못 쟀다»가 이 라운드를 만들었다.

  Y3  **X1~X6은 하나도 안 지웠다** (실험 27 §I). 특히 X1 — M2는 «요약이 사건을
      담았는가»가 아니라 «요약이 대장과 낱말을 나눠 쓰는가»를 잰다. 이 실험의
      모든 0은 **그 자로 잰 0**이다.

  Y4  **X3 — «읽을 만한가»에 이 실험 뒤에도 숫자가 없다.** 팔을 넷 더 만들었지만
      전부 같은 축자 대리 지표로 쟀다. 심판은 여전히 없다(P3).

  Y5  **n=1이다.** 팔마다 생성 한 건이고 temperature 0 · seed 고정이지만,
      ADR-016 §미해결 U3이 *"생성이 결정적이지 않아 요약 길이가 실행마다
      다르다"*를 두 실측으로 적어 뒀다. **한 팔의 값이 한 자리 움직이는 것을
      결과로 읽지 않는다** — 이 실험이 읽는 것은 «0인가 아닌가»뿐이다.""")
    if splits:
        print("""
  Y6  🔴 **두 항목 집합이 갈린 요인이 있다** (위 §9가 이름으로 적었다). 판정은
      사전 등록한 열을 따랐지만, **갈렸다는 사실이 그 요인의 크기를 깎는다** —
      «어느 사건이 남았나»가 구간에 따라 다르다는 뜻이기 때문이다. 위 §6의
      생존 항목 목록이 그것을 낱개로 보여 준다.""")
    print("""
  Y7  🔴 **②의 화살표는 «상한이 함께 움직인 자리»다.** A2의 재료(세션 요약
      S01–S12)와 A3의 재료(원본 턴 S01–S12)는 **같은 구간을 덮는데 상한이
      다르다** — 세션 요약이 이미 깎아 놓았기 때문이다. 그것이 곧 ②의 몸이지만,
      «생성기가 더 잘 담았다»로 읽으면 틀린다. **깎인 것은 깊이 1에서 이미
      깎였다.** §9가 두 상한을 화살표 옆에 함께 찍는 이유다.

  Y8  🔴 **두 판정이 다 얇다 — 사건 몇 건에 걸려 있다.** §9가 v2와 v3의 «크기»를
      나란히 찍는 이유가 그것이다. 특히 ①의 v2 쪽 크기는 **실험 26이 이름 붙인
      «면접 회차 위양성»이 부풀린 것**이고(위 §6-b), v3으로 읽으면 크기가
      줄어든다. **방향은 두 자에서 같지만 크기는 다르다** — 그래서 이 실험은
      «①이 ②보다 크다»를 주장하지 않는다. 주장하는 것은 «둘 다 0을 벗어나게
      하고 ③은 안 그런다»뿐이다.

  Y9  🔴 **U1이 이 라운드에서 대가를 한 번 더 치렀다.** 실험 27 §B는 v3이
      **위음성**을 낸다는 이유로 M2를 v2에 뒀는데, A1에서는 v2가 **위양성 둘**을
      낸다 — 같은 결정이 재료에 따라 반대 방향으로 값을 흔든다. 이 실험은
      채점기를 바꾸지 않았고(사전 등록), **그 대가를 이름으로 남긴다.**

  Y10 🆕 🔴 **A4가 채운 것은 «24세션 구간»이지 «창 일반»이 아니다.** 이 라운드는
      창을 **두 값**(8,192 · 16,384)에서만 봤고, ④는 그 **한 쌍**에서 «창이
      M2를 바꾸는가»에 답한다. **창–결과 곡선을 잰 것이 아니다** — 다른 창에서
      다른 답이 나올 수 있고, 이 실험은 그것을 모른다. 그리고 A0′·A4는
      **n=1**이다(Y5가 여섯 팔 전부에 그대로 적용된다).

  Y11 🆕 🔴 **«창을 키운 것»과 «전역을 블록 동안 바꾼 것»은 다른 위험이다.**
      `use_window()`는 `llm.LLM_NUM_CTX`를 **재바인딩**한다. 복원은
      `assert_prod_window()`가 팔마다·실행 끝에 확인하고 음성 대조 ⓗ가
      «복원 안 하면 우는가»를 심어 보이지만, **다른 스레드가 그 창을 함께
      본다**는 사실은 안 지워진다. 이 실험은 단일 스레드이고 그 가정을
      **여기 이름으로 적어 둔다** — 병렬로 돌리면 이 장치는 틀린다.

  Y12 🆕 ⚠️ **A4의 재료 상한이 다른 팔보다 높다는 것은 ②′의 몸이자 한계다.**
      원본 턴 720건은 `events 10`을 전부 덮는데(상한 10/10) 세션 요약 24건은
      8/10만 덮는다. **A4가 더 담을 수 있었다는 사실 자체가 «재압축이 깎는다»의
      다른 얼굴**이고, 그래서 ②′의 크기를 «생성기가 더 잘했다»로 읽으면
      틀린다 — Y7이 A3에 대해 적은 것과 같은 주의다.""")

    # ── 13. 음성 대조 ──
    live_pairs = sorted(m3res.items(),
                        key=lambda kv: (kv[1].reason is not None, kv[0]))
    quiet = next(((k, r) for k, r in live_pairs if r.reason is None),
                 (None, None))
    loud = next(((k, r) for k, r in live_pairs if r.reason is not None),
                (None, None))
    if quiet[0] is None or loud[0] is None:
        print("\n  ⚠️ M3 가드의 **실측 양쪽 대조를 이 라운드 입력에서 못 만들었다** —"
              " 조용한 쪽과")
        print("     우는 쪽이 둘 다 필요한데 한쪽이 없다. 그래서 ⓖ는 실험 27의"
              " 입력을 함께 쓴다.")
        cat = SP.join(sums)
        gcat = SP.score_all(cat, ev_all)
        mcat = [e for e in ev_all if e["id"] in gcat["v2"][3]]
        rcat = SP.m3(cat, mcat)
        if quiet[0] is None:
            quiet = ("R27 세션 요약 이어붙임 S01–S24", rcat)
        if loud[0] is None:
            loud = ("R27 lifetime (= A0)", m3res.get("A0", rcat))
    good, each = negative_controls(arms, prod, sums, quiet, loud)

    # ── 14. 요약 ──
    print("\n" + "=" * W)
    print(f"  프롬프트 조립 앵커      : {'바이트 동일' if same else '🔴 다르다'}"
          f"  (A0 = 실험 27의 팔)")
    print(f"  요인 규율 위반         : {len(viol_f)}건"
          f"  (팔 {len(arms)}개 · 앵커와 정확히 한 요인 · 요인 **넷**)")
    print(f"  창 복원 (G16)         : `llm.LLM_NUM_CTX` ="
          f" **{assert_prod_window()} tok** = 프로덕션 기본값"
          f"  ·  `prototype/llm.py` 무변경")
    for a in arms:
        val = (f"{SP.cell(m2_all[a.key], 'v2')}"
               f"  [구간 안 {SP.cell(m2_12[a.key], 'v2')}]") if a.ran else \
              "— (창을 넘어 안 돌렸다)"
        print(f"  {a.key} M2(v2)".ljust(24) + f": {val}"
              f"   {a.instruction} · {a.material} · {a.span}"
              f" · 창 {a.window}")
    for d in verdicts:
        print(f"  판정 {d['factor']:<10}   : "
              f"{'🔴 원인이다 ' if d['hit'] else '⛔ 원인이 아니다'}"
              f"  {d['base']} {d['bc']} → {d['arm']} {d['vc']}"
              f"  ({d['label']} · v2 크기 {d['size']:+d}"
              f" · v3 크기 {d['size3']:+d})")
    for factor, base, arm_k, hit_x, size_x, word in extra_verdicts:
        print(f"  🆕 {factor:<13}   : {word}"
              f"  {base} {SP.cell(m2_all[base], 'v2')} →"
              f" {arm_k} {SP.cell(m2_all[arm_k], 'v2')}"
              f"  (events 10 · S01–S24 · v2 크기 {size_x:+d})")
    if splits:
        print(f"  두 항목 집합이 갈린 요인   : "
              f"{[s[0].strip() for s in splits]}  ← §9가 이름으로 적었다")
    print(f"  화살표가 붙는 자리      : {len(legit)}쌍 {legit}")
    print(f"  표 규율 위반           : {len(viol)}건"
          f"  ·  화살표 자격 위반: {len(viol_arrow)}건")
    print(f"  음성 대조 **열** 갈래   : 검사 {len(each)}건 —"
          f" {'✅ 전부 발화' if good else '🔴 발화 실패 ' + str(each)}")
    print(f"  생성                  : 이 실행 {made}건 ·"
          f" 합계 벽시계 **기록** {total_wall:.1f}초 · 정지 {total_stall}회")
    print("=" * W)
    return 0 if (good and not viol and not viol_arrow and not viol_f) else 1


if __name__ == "__main__":
    sys.exit(main())
