# -*- coding: utf-8 -*-
"""
response_quality.py — **응답 수준**에서 회상과 오주입의 교환비를 잰다 (Q2-2).

## 이 파일은 실험 24의 **재설계**다

실험 24가 같은 질문을 물었고 **"이 설계로는 잴 수 없다"**를 답으로 돌려줬다.
그 실행이 자기 출력으로 진단한 결함이 셋이고, ADR-015 미해결이 셋 각각에
**이 실험이 직접 세는 숫자**를 열리는 조건으로 적어 뒀다.

    ①  결정적 사실 블록이 셀과 무관하게 정답·오답을 넣는다   →  `검색만` ≥ 5문항
    ②  셀을 파레토 전선에서 골라 두 축이 공선                →  corr(recall, mis) < 0.7
    ③  n=18에 검정력이 없다                                 →  불일치 쌍 ≥ 10

**셋 다 공격하고, 셋 다 찍는다. 열리는지 여부가 결과이고, 열릴 때까지 설계를
고치지 않는다.**

🔴 **실험 24는 이 설계의 부분집합이다.** 사실 블록 ON × 파레토 6셀 × 채점 문항이
정확히 그 실험이고, 그래서 아래 `EXPECT_EXP24`가 그 표를 **문항 단위로 재현**하는지
대조한다. 안 맞으면 중단한다 — 옛 실행의 출력은 `.omc/plans/baseline/after-exp24/`에
그대로 남아 있고, **재현이 곧 그 실험의 보존**이다.

## 무엇을 바꿨나 — 셋

**① 셀을 고르지 않는다. 1단 18셀 전량.** 실험 24의 결함은 *"파레토 전선에서
골랐다"*였고, 전선은 비지배 집합이라 **정의상** 두 축을 같이 움직인다. 고르는
규칙을 손보는 것이 아니라 **고르는 행위를 없앤다** — 격자 전량은 지배당하는 셀
13개를 포함하고, 그 13개가 축을 가른다. (전선 유도는 그대로 남는다: 격자가
움직였는지를 여전히 확인해야 한다.)

**② 사실 블록을 두 번째 축으로 만든다.** `memory.py`는 **손대지 않는다** — 그
전역(`INJECT_KNOWN_FACTS`)은 이미 있고 기본값은 `True`이며 `soak.py`·
`event_metrics.py`가 이미 같은 방식으로 켜고 끈다(G16 무관). 이 실험은 그것을
저장·복원하고 복원을 **단언**한다: `retrieval_sweep.RESTORE_GLOBALS`에 이 이름이
없어서 그쪽 `assert_restored`가 누수를 못 잡기 때문이다.

**③ 모집단을 하나 더 쓴다. 그리고 절대 합치지 않는다.** `probe_set.TYPED_PROBES`는
유형 라벨이 붙은 24개짜리 **두 번째** 집합이다(실험 22). `eval/`은 불변이므로(A8)
채점 문항 18개는 늘릴 수 없고, 두 집합을 **섞으면** 실험 22가 세운 규칙을 어긴다.
그래서 나란히 재고 **모든 숫자에 모집단을 붙인다.**

## 🔴 자기 채점 금지 · 규칙을 다시 구현하지 않는다

`qwen3:8b`가 생성하고 **채점은 규칙이 한다.** 규칙은 `eval/fact-ledger.yaml`의
허용 문자열 집합이고, `precision.key_index`(= `soak.qa_eval`의 `key_of`) ·
`allowed_strings` · `score_question` · `evidence_recall_via_retrieval` ·
`top1_misinjection` · `cell_totals`를 **부른다.** 게이트 두 함수와 셀 적용·전역
복원·파레토 규칙은 `retrieval_sweep`의 것을 부른다. 같은 규칙의 사본이 둘이 되면
한쪽만 고쳐진다 — 그것이 F12였다.

**이 파일이 정의하는 규칙은 딱 하나, `statements`(어느 문자열이 발화됐는가)다.**
그것은 실험 24가 도입했고 여기서 **한 글자도 바꾸지 않았다** — 두 모집단에 같은
함수를 쓴다.

## 🔴 사전 등록 — 생성 전에 고정한다

셀·사실블록 스위치·모집단·채점 규칙·검정을 **코드 상수로** 박고 실행 첫머리에
찍는다. 실험 24가 같은 규율로 돌았고 그것이 그 실험의 음성 결과를 읽을 수 있게
만들었다.

실행:
    python experiments/response_quality.py     # ollama 없으면 77(SKIP)
"""
import hashlib
import json
import math
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "prototype"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import memory as M                                            # noqa: E402
from memory import Memory                                     # noqa: E402
from soak import seed, ingest, ROOT, CHAT                     # noqa: E402
from gate_sweep import build_vocab                            # noqa: E402
import precision as P                                         # noqa: E402
import probe_set as PS                                        # noqa: E402
import rel_dist as RD                                         # noqa: E402
import retrieval_sweep as RS                                  # noqa: E402
import llm as LLM                                             # noqa: E402

W = 116


# ══════════════════════════════════════════════════════════════════════
#  사전 등록 구역 — 아래 상수는 **생성 한 건이 나오기 전에** 고정됐고
#  실행 첫머리에 그대로 찍힌다. 실행 중에 바꾸지 않는다.
# ══════════════════════════════════════════════════════════════════════

# ── ① 셀 ───────────────────────────────────────────────────────────────
#
# 🔴 **고르지 않는다.** 1단 18셀 전량이 생성 대상이다. 실험 24는 파레토 전선 5셀 +
#    기준칸을 골랐고 그 선택이 `corr(recall, mis) = +0.929`를 만들었다 — 비지배
#    집합은 정의상 두 축을 같이 움직인다. 지배당하는 13셀이 축을 가르는 유일한 것이다.
#
# 전선 유도는 **그대로 남는다.** 셀을 고르는 데 쓰지 않고, 격자가 움직였는지를
# 확인하는 데 쓴다 — 움직였으면 아래 재현 대조가 읽을 수 없게 된다.
EXPECT_FRONT = {("G3", "embed", 0.915), ("G3", "lexical_fixed", 0.915),
                ("G3", "lexical_fixed", 0.97), ("G3", "embed", 0.97),
                ("G0", "lexical_fixed", 0.97)}
EXPECT_FRONT_IDX = {5, 6, 8, 9, 15}       # 레인 E의 1단 번호 (교차 확인용)
BASE_KEY = ("G3", "lexical", 0.80)        # 기준칸 = 1단 #1 · θ_lexical(f=0.80)

# ── ② 사실 블록 축 ─────────────────────────────────────────────────────
#
# `memory.INJECT_KNOWN_FACTS`의 두 수준. `True`가 오늘의 기본값이고 **그 기본값은
# 이 실험이 바꾸지 않는다** — 셀마다 켜고 끈 뒤 되돌리고, 되돌아왔는지 단언한다.
FACT_LEVELS = (True, False)
FACT_LABEL = {True: "사실ON", False: "사실OFF"}

# ── ③ 모집단 ───────────────────────────────────────────────────────────
#
# A = 채점 문항 18 (`eval/questions.yaml`). B = 유형 라벨 프로브
# (`probe_set.TYPED_PROBES` 24개 중 아래 규칙으로 걸러진 것).
#
# 🔴 **B에서 빼는 규칙:** gold id가 `precision.key_index`에 없으면 제외한다.
#    대장의 `key_of`는 facts·events만 담고 **debts를 안 담는다.** 허용 문자열
#    집합이 없는 항목은 정답 진술을 정의할 수 없고, 검색 색인에도 debt가 없어
#    애초에 검색으로 도달할 수 없다. 새 규칙이 아니라 `precision.partition`이
#    채점 문항에 쓰는 것과 같은 성질의 규칙이다.
#
# 🔴 **두 모집단을 합치지 않는다** (실험 22의 규칙 · P1 · G12). 모든 숫자에
#    모집단을 붙여 찍는다.
POP_A, POP_B = "A(채점문항)", "B(유형프로브)"

# ── ④ 생성 프롬프트 ────────────────────────────────────────────────────
#
# `ctx.render()` **그대로** + 아래 지시. 실험 24와 **한 글자도 다르지 않다** —
# 다르면 캐시가 안 맞고, 그러면 실험 24의 재현 대조가 성립하지 않는다.
INSTRUCTION = """
[지시]
위 맥락만 근거로 [utterance]의 질문에 답한다. 서준으로서 한국어 두 문장 이내.
맥락에 아는 사실이 있으면 그 사실을 문장 안에 그대로 적는다.
맥락에 근거가 없으면 모른다고 답한다. 추측하지 않는다.
답변:"""

# ── ⑤ 채점 규칙 ────────────────────────────────────────────────────────
#
# 오답 후보의 우주. 브리프가 고정했다 — 대장의 유도 계열이다.
DISTRACTOR_UNIVERSE = ("X001", "X002", "X003", "X004", "X005")

# 무응답/회피 표지. 이것도 규칙이다 — 모델이 자기 답을 "회피였다"고 말하게 하지
# 않는다. 표지가 없으면서 정답도 오답도 아닌 답은 `기타`로 따로 센다.
REFUSAL_MARKERS = ("모르", "기억 안 나", "기억이 안 나", "기억나지 않", "기억 못",
                   "알 수 없", "정보가 없", "근거가 없", "말한 적 없",
                   "확실하지 않", "확실치 않")

# 마스킹에 쓰는 채움 문자. 문자열에 절대 안 나오는 것이어야 하고, **길이를
# 보존**해야 한다 — 길이가 줄면 마스킹이 양옆을 붙여 없던 일치를 만든다.
MASK_CHAR = "\x00"

# ── ⑥ 축 셋 ────────────────────────────────────────────────────────────
#
# 실험 24는 앞 둘만 검정했다. `무응답`을 더한 이유: **사실 블록을 빼면 "모른다"가
# 늘 것이고 그것은 응답 수준의 실제 결과다.** 안 재면 사실 블록의 효과가
# `정답 진술`의 감소로만 보이고, 그 감소가 *"틀리게 답한 것"*인지 *"안 답한
# 것"*인지 갈리지 않는다.
AXES = (("정답 진술", "said_gold"), ("오답 진술", "said_dist"),
        ("무응답", "said_none"))

# ── ⑦ 열리는 조건 (ADR-015 미해결 `실험 24 잔여`가 적어 둔 것 그대로) ────
OPEN_1_MIN_RETRIEVAL_ONLY = 5     # `검색만` 열이 어느 셀에서 5문항 이상
OPEN_2_MAX_CORR = 0.7             # corr(recall, mis) < 0.7
OPEN_3_MIN_DISCORDANT = 10        # 어느 비교의 불일치 쌍이 10 이상

# ── ⑧ 재현 대조 — 실험 24의 표 (문서에서 옮겨 적은 **기대값**이다) ──────
#
# 🔴 이것은 G11이 금지하는 "전사"가 **아니다.** 전사는 남의 값을 **결과로** 적는
#    것이고, 이것은 이 실행이 **스스로 유도한 값과 대조할 기대값**이다 —
#    `EXPECT_FRONT`가 서 있는 자리와 같다. 안 맞으면 중단한다.
#    (셀 → recall, mis, 정답 진술, 오답 진술, 무응답 · 사실ON · 모집단 A)
EXPECT_EXP24 = {1: (11, 11, 4, 1, 3), 5: (12, 8, 4, 1, 4), 6: (6, 3, 3, 1, 4),
                8: (13, 10, 4, 1, 3), 9: (6, 3, 4, 1, 5), 15: (3, 2, 3, 1, 6)}

# 🔴 **`검색만` 열의 기대값** — 실험 24 §D의 주입 경로 표가 찍은 세 셀(사실ON · A).
#    이 열이 ①의 판정을 통째로 지고 있으므로, 계산이 조용히 헐거워지면(예: 사실
#    블록을 빼는 조건이 빠지면) ①이 **공짜로 열린다.** 그래서 기록된 값과 대조한다:
#    조건이 빠지면 여기 2·2·0이 8·10·3으로 뛰고 그 자리에서 멈춘다.
EXPECT_EXP24_RETONLY = {1: 2, 8: 2, 15: 0}

RESPONSE_CACHE = os.path.join(ROOT, "experiments", "data", "RESPONSE_CACHE.json")
# 🔴 `REL_CACHE.json`·`SWEEP_CACHE.json`·`PROBE_CACHE.json`은 **읽기만** 한다
#    (남의 실험 것이다). 이 실험이 새로 계산한 벡터가 있으면 여기 남는다.
PROBE_CACHE = os.path.join(ROOT, "experiments", "data", "PROBE_CACHE.json")
RQ_VEC_CACHE = os.path.join(ROOT, "experiments", "data", "RQ_VEC_CACHE.json")

PREREG_TEXT = """\
  ① 셀: **1단 18셀 전량 — 고르지 않는다.** 실험 24는 파레토 전선에서 골랐고 그
     선택이 두 축을 공선으로 만들었다(비지배 집합은 정의상 같이 움직인다).
     전선은 여전히 유도해 기대 집합과 대조한다 — 셀 선택이 아니라 격자 검사용이다.
  ② 사실 블록: `memory.INJECT_KNOWN_FACTS` 2수준(ON=오늘의 기본값 / OFF).
     🔴 `memory.py`를 수정하지 않는다. 전역은 이미 있고 `soak.py`가 이미 같은
     방식으로 켜고 끈다. 셀마다 복원하고 **복원됐는지 단언**한다.
  ③ 모집단 둘, **절대 합치지 않는다**: A=채점 18문항 · B=유형 라벨 프로브
     (`probe_set` 24개 중 gold가 `precision.key_index`에 없는 것 제외).
  ④ 프롬프트: `ctx.render()` 그대로 + 고정 지시 1개 (실험 24와 동일 — 그래야 재현).
  ⑤ 정답 진술: `precision.allowed_strings(evidence(q))` 중 하나가 **최장 일치 우선
     마스킹** 뒤에도 남아 발화된 경우. 오답 진술: X001–X005 중 **이 문항의 근거가
     아닌** 항목의 허용 문자열이 같은 마스킹 뒤에 발화된 경우.
     · 판별 가능성 필터 — 정답 문자열의 **진부분문자열**인 오답 문자열은 버린다.
     · 최장 일치 우선 — `'나비넥타이'`(오답)를 먼저 마스킹해야 `'나비'`(정답)가
       그 자리에서 잘못 발화되지 않는다.
  ⑥ 축 셋: 정답 진술 · 오답 진술 · **무응답**(실험 24는 앞 둘만 검정했다).
  ⑦ 비교 계열 둘, **③의 판정을 계열별로 따로 적는다**:
     R(검색 축) = 같은 사실 블록 수준 안에서 기준칸 대 나머지 17셀 ·
     F(사실 블록 축) = 같은 셀에서 ON 대 OFF.
     🔴 F가 불일치 10을 넘겨도 *"검색 축을 잴 검정력이 생겼다"*가 아니다.
  ⑧ 유의성: 문항 단위 쌍체 **부호검정(= McNemar 정확검정)** · 양측 정확 이항.
     **이 n에서 달성 가능한 최소 p를 옆에 같이 찍는다.**
  ⑨ 교환비: 셀 18개를 점으로 둔 `정답진술 ~ a·recall + b·mis + c` 최소제곱을
     사실블록 수준 × 모집단마다. 🔴 셀은 독립 표본이 아니다 — **기술 통계**다.
  ⑩ 오주입 사용률: **①이 열린 설정에서만** 재고 ON/OFF를 쌍체로 검정한다.
     안 열리면 재지 않고 열어 둔 채로 보고한다.
  ⑪ 재현: 사실ON × 실험 24의 6셀 × 모집단 A가 그 실험의 표를 재현해야 한다.
  ⑫ 종료: ollama가 없거나 다이제스트 대조에 필요한 키가 없으면 **77(SKIP)**."""


# ══════════════════════════════════════════════════════════════════════
#  채점 — 이 파일이 정의하는 유일한 규칙 (실험 24에서 한 글자도 안 바꿨다)
# ══════════════════════════════════════════════════════════════════════

def discriminable(dist_strings, gold_strings):
    """
    오답 문자열 중 **정답과 구별되는 것**만 남긴다. `(남은 것, 버린 것)`.

    버리는 조건은 하나: 어떤 정답 문자열의 **진부분문자열**인 것.

    ⚠️ **방향이 있다.** 반대(정답이 오답의 진부분문자열)는 버리지 않는다 —
       `'나비'`(정답) ⊂ `'나비넥타이'`(오답)는 최장 일치 우선 마스킹이 이미
       옳게 가른다: 답변이 `'나비넥타이'`면 긴 쪽이 먼저 먹고 `'나비'`는 그
       자리에 남지 않는다. 답변이 `'나비'`뿐이면 그것은 진짜 정답 진술이다.

       버려야 하는 것은 그 반대다. `'스타트업'`(오답) ⊂ `'스타트업 프로덕트
       매니저'`(정답)에서 모델이 정답을 **의역**하면(`'스타트업에서 제품 관리'`)
       긴 정답은 안 맞고 짧은 오답만 맞는다. 그 일치는 오주입의 증거가 아니라
       **정답의 파편**이다. 실측으로 확인한 사례이고, 그래서 생성 전에 막는다.

    🔴 **`owner`(버린 근거로 찍는 정답 문자열)는 `sorted`에서 고른다.** `gold_strings`가
       set이라 그냥 훑으면 **어느 것이 나오는지가 실행마다 달라진다** — 필터의 판정은
       같은데 출력 줄만 흔들린다. 실측: 같은 웜 실행 셋에서 Q04의 `owner`가
       `'스타트업 프로덕트 매니저'` 둘 · `'지우는 스타트업으로 이직함'` 하나로 갈렸다
       (둘 다 `'스타트업'`을 포함하므로 **둘 다 참**이다). 판정에는 영향이 없지만
       **스냅샷의 바이트 동일성 대조가 그 줄에서 항상 깨진다** — 아래 `statements`가
       같은 이유로 `sorted(side, ...)`를 쓰는 것과 같은 규약이다.
    """
    keep, dropped = set(), []
    for d in sorted(dist_strings):
        owner = next((g for g in sorted(gold_strings) if d in g and d != g), None)
        if owner is None:
            keep.add(d)
        else:
            dropped.append((d, owner))
    return keep, sorted(dropped)


def statements(answer, gold, dist):
    """
    답변이 **어느 쪽을 발화했는가**. `(정답 진술?, 오답 진술?, 맞은 문자열들)`.

    최장 일치 우선으로 한 번씩 훑고, 맞은 자리는 **길이를 보존한 채** 지운다.
    지우지 않으면 짧은 문자열이 긴 문자열 안에서 두 번 세어진다.

    🔴 `gold`와 `dist`가 겹치면 조용히 지나가지 않고 터진다. 겹치면 그 문자열의
       발화가 어느 쪽인지 정의되지 않고, 그 상태로 나온 숫자는 읽을 수 없다.
    """
    both = gold & dist
    if both:
        raise ValueError(
            f"정답 문자열과 오답 문자열이 겹친다 {sorted(both)} — 발화가 어느 쪽인지 "
            f"정의되지 않는다. 문항의 근거 id를 오답 우주에서 뺐는지 확인할 것.")
    side = {s: "gold" for s in gold}
    side.update({s: "dist" for s in dist})
    rest, hit = answer, {"gold": [], "dist": []}
    # 길이 내림차순, 같은 길이는 사전순 — 순서가 실행마다 달라지면 안 된다.
    for s in sorted(side, key=lambda x: (-len(x), x)):
        if s and s in rest:
            hit[side[s]].append(s)
            rest = rest.replace(s, MASK_CHAR * len(s))
    return bool(hit["gold"]), bool(hit["dist"]), hit


def is_refusal(answer):
    """빈 답 또는 회피 표지. **정답/오답 판정 뒤에만** 의미가 있다."""
    a = (answer or "").strip()
    return (not a) or any(mk in a for mk in REFUSAL_MARKERS)


def classify(answer, gold, dist):
    """한 답변의 다섯 갈래. 합이 언제나 1이 되도록 배타적으로 가른다."""
    g, d, hit = statements(answer or "", gold, dist)
    if g and d:
        bucket = "정답+오답"
    elif g:
        bucket = "정답"
    elif d:
        bucket = "오답"
    elif is_refusal(answer):
        bucket = "무응답"
    else:
        bucket = "기타"
    return dict(gold=g, dist=d, bucket=bucket, hit=hit)


# ══════════════════════════════════════════════════════════════════════
#  유의성 — 부호검정과 **이 n에서 달성 가능한 최소 p**
# ══════════════════════════════════════════════════════════════════════

def sign_test(pairs):
    """
    쌍체 이진 결과의 양측 정확 부호검정(= McNemar 정확검정).

    `pairs` = [(기준 결과, 비교 결과), …] · 각 원소는 0/1.
    돌려주는 것: `(b, c, p, min_p)`
      b = 기준만 성공 · c = 비교만 성공 · 동률 쌍은 **버린다**(부호검정의 정의).
      min_p = **불일치 쌍이 이만큼일 때 달성 가능한 가장 작은 p** = `2·0.5^(b+c)`.

    🔴 `min_p`를 같이 돌려주는 이유. 불일치가 2쌍이면 어느 쪽으로 쏠려도 p가
       0.5 아래로 못 내려간다. 그때 "p = 0.5, 유의하지 않음"이라고 적으면 마치
       검정을 한 것처럼 읽히지만 **검정할 힘이 없었던 것**이다.
    """
    b = sum(1 for x, y in pairs if x == 1 and y == 0)
    c = sum(1 for x, y in pairs if x == 0 and y == 1)
    n = b + c
    if n == 0:
        return b, c, 1.0, 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return b, c, min(1.0, 2 * tail), min(1.0, 2 * 0.5 ** n)


def pearson(xs, ys):
    """두 열의 상관. 셀이 3개 미만이거나 한 열이 상수면 `None`."""
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    sxx = sum((a - mx) ** 2 for a in xs)
    syy = sum((b - my) ** 2 for b in ys)
    if sxx == 0 or syy == 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def _inv(mat):
    """가우스-조던 역행렬. 특이하면 `None` — **0으로 나누고 넘어가지 않는다.**"""
    n = len(mat)
    a = [list(row) + [1.0 if i == j else 0.0 for j in range(n)]
         for i, row in enumerate(mat)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[piv][col]) < 1e-12:
            return None
        a[col], a[piv] = a[piv], a[col]
        d = a[col][col]
        a[col] = [v / d for v in a[col]]
        for r in range(n):
            if r != col and a[r][col]:
                f = a[r][col]
                a[r] = [v - f * w for v, w in zip(a[r], a[col])]
    return [row[n:] for row in a]


def ols(ys, cols):
    """
    `y ~ c + Σ bᵢ·xᵢ` 최소제곱. `(계수, 표준오차, R², None이면 특이)`.

    🔴 **이것은 기술 통계다.** 점 하나가 셀 하나이고, 18개 셀은 **같은 문항 위의
       18가지 구성**이라 독립 표본이 아니다. 표준오차는 그 독립성을 가정하므로
       여기 t는 *"우연히 이 기울기가 나올 확률"*이 아니다. 이 회귀가 답하는 것은
       하나뿐이다: **두 축이 분리되는가** — 즉 `a`와 `b`가 따로 추정되는가.
       판정은 부호검정이 한다.
    """
    n, k = len(ys), len(cols) + 1
    X = [[1.0] + [c[i] for c in cols] for i in range(n)]
    xtx = [[sum(X[i][p] * X[i][q] for i in range(n)) for q in range(k)]
           for p in range(k)]
    inv = _inv(xtx)
    if inv is None:
        return None, None, None, True
    xty = [sum(X[i][p] * ys[i] for i in range(n)) for p in range(k)]
    beta = [sum(inv[p][q] * xty[q] for q in range(k)) for p in range(k)]
    fit = [sum(beta[p] * X[i][p] for p in range(k)) for i in range(n)]
    ss_res = sum((y - f) ** 2 for y, f in zip(ys, fit))
    my = sum(ys) / n
    ss_tot = sum((y - my) ** 2 for y in ys)
    if n <= k:
        return beta, None, None, False
    s2 = ss_res / (n - k)
    se = [math.sqrt(max(s2 * inv[p][p], 0.0)) for p in range(k)]
    r2 = None if ss_tot == 0 else 1 - ss_res / ss_tot
    return beta, se, r2, False


# ══════════════════════════════════════════════════════════════════════
#  생성 — 체크포인트가 있으면 다시 만들지 않는다
# ══════════════════════════════════════════════════════════════════════

def gen_key(prompt, rt):
    """
    캐시 키. **런타임 정보를 키에 넣는다** — 모델이 바뀌면 같은 프롬프트라도
    다른 답이고, 옛 답을 조용히 재사용하면 그 실행의 숫자에 두 모델이 섞인다.
    """
    blob = json.dumps({"m": LLM.LLM_MODEL, "digest": rt.get("digest"),
                       "ollama": rt.get("ollama"), "seed": LLM.LLM_SEED,
                       "temp": LLM.LLM_TEMPERATURE, "ctx": LLM.LLM_NUM_CTX,
                       "p": prompt}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# 🔴 **스톨 재시도.** 사전 등록 뒤에 더한 것이고, 이유를 여기 적는다.
#
# 실험 24가 생성 1건이 `timed out`으로 죽은 것을 *"일시적 스톨"*로 적었다. 이
# 실행에서 **같은 일이 두 번** 났고, 두 번 다 **연속 생성 52~55건 근처**였다.
# 실측으로 확인한 것:
#   · 스톨 직후의 짧은 생성은 4.2~7.8초로 정상이다.
#   · **스톨을 일으켰다는 그 프롬프트 자체가 따로 돌리면 10.4초에 끝난다**
#     (스트리밍으로 확인 · `done_reason=stop` · 372토큰).
# 즉 스톨은 **프롬프트의 성질이 아니다.** 한 건이 `LLM_TIMEOUT`(600초)을 통째로
# 태우고 죽으면 실행 전체가 날아가는데, 그 한 건은 다시 부르면 나온다.
#
# 🔴 **이것은 실패를 삼키는 것이 아니다.** `llm.py`의 정책(*"실패하면 예외"*)은
#    그대로다 — 예외는 여기까지 올라오고, 재시도는 **한 건씩 출력에 찍히고 세어져**
#    마지막 절에 나온다. 재시도 횟수가 0이 아니면 그 실행은 깨끗한 실행이 아니고,
#    그 사실이 숫자 옆에 남는다. 재시도가 다 떨어지면 **그대로 터진다.**
#
# 🔄 F39(wave3) — 옛 근거 «`temperature=0`·`seed` 고정이라 재시도는 결과를 안 바꾼다»는
#    거짓이다: 서버 캐시 상태가 다르면 같은 프롬프트도 답이 갈린다. 재시도 건은 기록된 답으로만 안정.
GEN_RETRIES = 12
GEN_RETRY_WAIT = 5.0          # 초. 재시도 사이의 숨 고르기

# 🔴 **이 실험이 쓰는 생성 타임아웃.** `llm.LLM_TIMEOUT`(600초)은 *"8B 로컬 모델은
#    느리다"*를 대비한 값이고 그 판단은 옳다. 그러나 여기서 관측된 것은 느린 생성이
#    아니라 **아무것도 안 오는 정지**다:
#      · 이 실험의 정상 생성 실측 범위 = **2.5 ~ 11초** (스트리밍으로 확인한 최장 10.4초)
#      · 정지는 600초를 통째로 태우고 **그 안에 회복하지 않는다**
#      · 같은 프롬프트를 다시 부르면 정상 시간에 나온다 (정지는 프롬프트의 성질이 아니다)
#    즉 600초를 기다려서 얻는 것이 없다. **관측된 최장의 10배가 넘는 120초**로 끊고
#    다시 부르는 것이 답 하나를 훨씬 싸게 얻는 길이다(🔄 «같은 답»이라는 보장은 없다 — 위 F39).
#
# ⚠️ **대가를 적는다.** 정말로 120초가 필요한 생성이 있다면 이 값이 그것을 자른다.
#    그 경우 재시도가 다 떨어지고 **실행이 터진다** — 조용히 틀린 답이 되지 않는다.
#    `llm.py`의 모듈 기본값은 **안 바꾼다**; 이 실험이 자기 실행에만 꽂는다.
GEN_TIMEOUT = 120


class Generator:
    """디스크 체크포인트를 낀 생성기. **한 건 나올 때마다 쓴다.**"""

    def __init__(self, rt):
        self.rt = rt
        self.store = RS._read(RESPONSE_CACHE)
        self.hits = self.misses = 0
        self.gen_seconds = 0.0
        self.retries = []                 # (tag, 시도번호, 걸린 초, 사유)

    def _generate(self, prompt, tag):
        """`LLM.generate`를 부르되 스톨이면 정해진 횟수만큼 다시 부른다."""
        for attempt in range(1, GEN_RETRIES + 2):
            t0 = time.perf_counter()
            try:
                return LLM.generate(prompt)
            except LLM.LLMError as e:
                took = time.perf_counter() - t0
                self.retries.append((tag, attempt, took, str(e)))
                print(f"\n  ⚠️ 생성 실패 {tag} · 시도 {attempt}/{GEN_RETRIES + 1} · "
                      f"{took:.1f}초 · {e}", flush=True)
                if attempt > GEN_RETRIES:
                    print(f"  🔴 재시도 {GEN_RETRIES}회를 다 썼다 — 삼키지 않고 터진다.",
                          flush=True)
                    raise
                time.sleep(GEN_RETRY_WAIT)

    def __call__(self, prompt, tag):
        k = gen_key(prompt, self.rt)
        if k in self.store:
            self.hits += 1
            return self.store[k]["answer"]
        t0 = time.perf_counter()
        ans = self._generate(prompt, tag)
        self.gen_seconds += time.perf_counter() - t0
        self.misses += 1
        self.store[k] = {"answer": ans, "tag": tag,
                         "digest": self.rt.get("digest"),
                         "ollama": self.rt.get("ollama")}
        self.flush()
        return ans

    def flush(self):
        tmp = RESPONSE_CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.store, f, ensure_ascii=False)
        os.replace(tmp, RESPONSE_CACHE)       # 크래시가 반쯤 쓴 파일을 안 남기게


# ══════════════════════════════════════════════════════════════════════
#  모집단
# ══════════════════════════════════════════════════════════════════════

def probe_population(key_of):
    """
    모집단 B — `probe_set.TYPED_PROBES`를 채점 가능한 문항 모양으로 바꾼다.

    `(문항 목록, 버린 것)`. 버리는 규칙은 §사전 등록 ③ 그대로: **gold id가
    `precision.key_index`에 없으면 제외.** 대장의 `key_of`는 facts·events만 담고
    debts를 안 담는다 — 허용 문자열 집합이 없으면 정답 진술이 정의되지 않는다.

    🔴 이 함수는 프로브를 **읽기만** 한다. 질의를 고쳐 쓰지 않는다 —
       `probe_set`의 사전 등록(*"순위를 보기 전에 고정했다"*)이 그대로 살아 있어야
       이 모집단의 값이 실험 22와 나란히 읽힌다.
    """
    out, dropped = [], []
    for i, p in enumerate(PS.TYPED_PROBES):
        if p.gold not in key_of:
            dropped.append((p.gold, p.type))
            continue
        out.append({"id": f"P{i:02d}", "ask": p.q, "evidence": [p.gold],
                    "type": p.type})
    return out, dropped


def question_keys(q, key_of):
    """
    한 문항의 `(정답 문자열, 오답 문자열, 버린 오답 문자열)`.

    둘 다 `precision.allowed_strings` — 즉 `soak.qa_eval`의 `key_of` 규칙이다.
    오답 우주에서 **이 문항의 근거를 뺀다**: X004는 Q26의 근거이므로 Q26에서
    오답이 아니다(`precision.hard_misinjection`이 같은 특수 사례를 적어 뒀다).
    모집단 B도 같은 함수를 쓴다 — 프로브의 `evidence`는 gold 하나짜리 목록이다.
    """
    gold = P.allowed_strings(q.get("evidence", []), key_of)
    dist_ids = [d for d in DISTRACTOR_UNIVERSE if d not in q.get("evidence", [])]
    raw = P.allowed_strings(dist_ids, key_of)
    dist, dropped = discriminable(raw, gold)
    return gold, dist, dropped


# ══════════════════════════════════════════════════════════════════════
#  셀 실행
# ══════════════════════════════════════════════════════════════════════

def assert_inject(expected, where):
    """
    `INJECT_KNOWN_FACTS`가 되돌아왔는지 **런타임에** 확인한다.

    🔴 `retrieval_sweep.RESTORE_GLOBALS`에 이 이름이 **없다.** 그래서 그쪽
       `assert_restored`는 이 전역의 누수를 못 잡는다 — 못 잡는 것을 아는 쪽이 잡는다.

    🔴 **호출 위치가 이 검사의 전부다.** `run_cell_gen`의 `finally` 바로 뒤에서
       그 함수가 방금 되돌린 값을 다시 확인하면 **언제나 참인 문장**이고 그것은
       검사가 아니다(이 저장소가 이미 세 번 만든 발화 불가능한 검사). 그래서
       기대값은 **생성 루프에 들어가기 전에** 뜬 것을 쓰고, 검사는 셀마다 한다 —
       `build_context`든 `run_cell_gen`이든 그 사이의 누구든 이 전역을 흘리면 여기서 운다.
    """
    if M.INJECT_KNOWN_FACTS is not expected:
        raise SystemExit(
            f"🔴 `INJECT_KNOWN_FACTS`가 복원되지 않았다 ({where}): "
            f"{expected!r} → {M.INJECT_KNOWN_FACTS!r}")


def run_cell_gen(env, cell, gen, keys, qlist, inject):
    """
    한 셀 × 한 사실블록 수준 × 한 모집단을 돌리고 **문항마다 생성까지 한다.**

    ⚠️ `retrieval_sweep.run_cell`을 그대로 못 부르는 이유는 하나다: 그 함수는
       `ctx.render()`를 안 돌려준다. 생성 프롬프트는 그 문자열이어야 하고,
       나중에 두 번째로 `build_context`를 부르면 `retrieval_count`·`surfaced`가
       이미 올라가 **다른 맥락**이 나온다. 그래서 순회를 한 번만 돈다.

       🔴 지표 함수는 그래도 **전부 `precision.py`의 것**을 부른다.

    🔴 `INJECT_KNOWN_FACTS`는 **여기서 켜고 `finally`에서 되돌린다.**
       `retrieval_sweep.RESTORE_GLOBALS`에 이 이름이 없어서 그쪽 `assert_restored`가
       이 누수를 못 잡는다 — 못 잡는 것을 아는 쪽이 잡는다.
    """
    corpus, ledger, key_of = env
    dbf = f"{ROOT}/prototype/.rq.db"
    if os.path.exists(dbf):
        os.remove(dbf)
    m = Memory(dbf)
    seed(m)
    ingest(m, corpus, ledger, timed=False)
    m._vocab = build_vocab(m)
    Memory.gate = cell.gate[1]

    saved_inject = M.INJECT_KNOWN_FACTS
    M.INJECT_KNOWN_FACTS = inject
    last = corpus[-1]["seq"]
    rows, degraded = [], 0
    try:
        for q in qlist:
            ctx = m.build_context(CHAT, q["ask"], last)
            degraded += sum(1 for k, _, _ in ctx.provenance if k == "degraded")
            ordered = [item for kind, item, _ in ctx.provenance
                       if kind == "retrieved"]
            retrieved = set(ordered)
            gate_pass = bool([1 for kind, item, _ in ctx.provenance
                              if kind == "gate" and item == "통과"])
            hits = m.retrieve(CHAT, q["ask"], last)[0] if gate_pass else []
            if [r["summary"] for _, r in hits] != ordered:
                raise SystemExit(f"{q['id']}: retrieve()와 provenance의 순서가 다르다.")

            # ── 검색 지표 — 전부 남의 함수 ──────────────────────────────
            mis, prec = P.score_question(q, retrieved, key_of)
            ev_hit, ev_tot = P.evidence_recall_via_retrieval(q, retrieved, key_of)
            tie_n, tie_s = P.tie_rank1(hits)

            # ── 주입 경로 — 진단이 읽는 것 ──────────────────────────────
            rendered = ctx.render()
            facts_text = "\n".join(b.text for b in ctx.blocks
                                   if b.name == "알고 있는 것")
            gold, dist, _ = keys[q["id"]]
            inj = {
                "dist_in_ctx": sorted(s for s in dist if s in rendered),
                "dist_in_facts": sorted(s for s in dist if s in facts_text),
                "dist_in_ret": sorted(s for s in dist
                                      if any(s in r for r in retrieved)),
                "gold_in_ctx": sorted(s for s in gold if s in rendered),
                "gold_in_facts": sorted(s for s in gold if s in facts_text),
                "gold_in_ret": sorted(s for s in gold
                                      if any(s in r for r in retrieved)),
            }

            # ── 생성 + 규칙 채점 ────────────────────────────────────────
            answer = gen(rendered + INSTRUCTION,
                         f"{cell.name}|{FACT_LABEL[inject]}|{q['id']}")
            cls = classify(answer, gold, dist)
            # 오주입 **사용** = 오답을 발화했고 그 문자열이 실제로 맥락에 있었다.
            used = sorted(set(cls["hit"]["dist"]) & set(inj["dist_in_ctx"]))

            rows.append(dict(id=q["id"], mis=mis, n_ret=len(retrieved), prec=prec,
                             ev_hit=ev_hit, ev_tot=ev_tot, gate=gate_pass,
                             top1=P.top1_misinjection(q, ordered, key_of),
                             tie_n=tie_n, tie_s=tie_s,
                             ordered=ordered, tokens=ctx.tokens,
                             answer=answer, bucket=cls["bucket"],
                             said_gold=cls["gold"], said_dist=cls["dist"],
                             said_none=cls["bucket"] == "무응답",
                             hit=cls["hit"], inj=inj, used_dist=used))
    finally:
        M.INJECT_KNOWN_FACTS = saved_inject
        m.db.close()
        os.remove(dbf)

    tot = P.cell_totals(rows)
    tot["degraded"] = degraded
    tot["rows"] = rows
    tot["n_gold"] = sum(1 for r in rows if r["said_gold"])
    tot["n_dist"] = sum(1 for r in rows if r["said_dist"])
    tot["n_refuse"] = sum(1 for r in rows if r["said_none"])
    tot["n_other"] = sum(1 for r in rows if r["bucket"] == "기타")
    tot["n_dist_inj"] = sum(1 for r in rows if r["inj"]["dist_in_ctx"])
    tot["n_dist_used"] = sum(1 for r in rows if r["used_dist"])
    # `검색만` — 사실 블록에 없고 검색만 가져온 문항. **①의 열리는 조건이 읽는 열.**
    tot["gold_ret_only"] = sum(1 for r in rows if r["inj"]["gold_in_ret"]
                               and not r["inj"]["gold_in_facts"])
    tot["gold_in_facts"] = sum(1 for r in rows if r["inj"]["gold_in_facts"])
    tot["gold_in_ret"] = sum(1 for r in rows if r["inj"]["gold_in_ret"])
    tot["gold_in_ctx"] = sum(1 for r in rows if r["inj"]["gold_in_ctx"])
    return tot


def derive_ladder(cache):
    """
    θ 사다리를 **다시 유도한다** (G11 — 전사 금지).

    규칙은 전부 남의 것이다: 모집단은 `rel_dist.population`, 척도는
    `memory.coverage`/`jaccard`/`rel_dist.cos`, 등컷은 `rel_dist.theta_at`.

    🔴 사다리의 모집단은 **채점 18문항 × 색인 21행 = 378쌍** 그대로다. 프로브를
       여기 넣지 않는다 — 넣으면 θ가 움직이고 1단 격자가 실험 21의 것이 아니게 된다.
       프로브는 **같은 셀을 다른 문항에 적용해 보는 것**이지 셀을 다시 정의하는
       것이 아니다.
    """
    asks, sums, total_rows = RD.population()
    lex = [M.coverage(set(M.bigrams(a)), set(M.bigrams(s)))
           for a in asks for s in sums]
    fix = [M.jaccard(set(M.tokens_fixed(a)), set(M.tokens_fixed(s)))
           for a in asks for s in sums]
    emb = [RD.cos(cache[a], cache[s]) for a in asks for s in sums]
    vals = {"lexical": lex, "lexical_fixed": fix, "embed": emb}
    ladder = {mode: [(RD.theta_at(vals[mode], f), f,
                      RD.actual_cut(vals[mode], RD.theta_at(vals[mode], f)))
                     for f in RD.LADDER] for mode in RS.MODES}
    return ladder, len(asks) * len(sums), (total_rows, len(sums))


def build_stage1(ladder):
    """1단 18셀 — `retrieval_sweep.main`과 **같은 순서**라야 번호가 비교된다."""
    cells, idx = [], 0
    for gate in RS.GATES:
        for mode in RS.MODES:
            for th, f, cut in ladder[mode]:
                idx += 1
                cells.append(RS.Cell(idx, 1, gate, mode, f, th, cut, 0.6, 0.4, 0.1))
    return cells


def load_vectors():
    """남의 캐시 셋은 **읽기만**, 내 것만 되쓴다."""
    borrowed = dict(RS._read(RD.REL_CACHE))
    borrowed.update(RS._read(RS.SWEEP_CACHE))
    # 🔴 프로브 질의 24개의 벡터는 `PROBE_CACHE.json`(실험 22)에 있다. 같은
    #    `bge-m3`이므로 값이 같고, **읽기만** 한다.
    borrowed.update(RS._read(PROBE_CACHE))
    cache = dict(borrowed)
    cache.update(RS._read(RQ_VEC_CACHE))
    return cache, set(borrowed)


# ══════════════════════════════════════════════════════════════════════
#  출력
# ══════════════════════════════════════════════════════════════════════

def hr(ch="-"):
    print(ch * W)


def cell_table(title, cells, level, pop, note):
    """한 (사실블록 수준 × 모집단)의 18행."""
    print(f"\n{title}")
    hr()
    print(f"  {'#':>3} {'셀':<28}{'recall':>9}{'mis@q':>7}{'정답':>6}{'오답':>6}"
          f"{'무응답':>7}{'기타':>6}{'정답+오답':>10}{'검색만':>8}{'사실블록':>9}")
    hr()
    for c in cells:
        t = c.res[(level, pop)]
        both = sum(1 for r in t["rows"] if r["bucket"] == "정답+오답")
        print(f"  {c.idx:>3} {c.name:<28}"
              f"{f'{t['ev_hit']}/{t['ev_tot']}':>9}{t['mis']:>7}"
              f"{t['n_gold']:>6}{t['n_dist']:>6}{t['n_refuse']:>7}"
              f"{t['n_other']:>6}{both:>10}{t['gold_ret_only']:>8}"
              f"{t['gold_in_facts']:>9}")
    print(f"  {note}")


def main():
    t_start = time.perf_counter()
    print("=" * W)
    print("응답 수준 교환비 (Q2-2) — **실험 24의 재설계.** 그 실험이 진단한 결함 셋을 걷어낸다")
    print("=" * W)
    print("\n  실험 24는 *'이 설계로는 교환비를 잴 수 없다'*를 결과로 돌려줬고, 이유 셋을")
    print("  자기 출력으로 짚었다. ADR-015 미해결이 셋 각각에 **이 실험이 직접 세는**")
    print("  숫자를 열리는 조건으로 적어 뒀다. 셋을 다 공격하고 셋을 다 찍는다.")
    print("  🔴 **열리는지 여부가 결과다.** 열릴 때까지 설계를 고치지 않는다.")
    print("  🔴 생성은 `qwen3:8b`가 하고 **채점은 규칙이 한다.** 모델은 자기 답을")
    print("     채점하지 않는다 — 자기 채점이면 결과가 아무것도 아니다.")

    print("\n" + "=" * W)
    print("사전 등록 — 생성 한 건이 나오기 전에 고정됐다 (아래는 코드의 상수 그대로)")
    print("=" * W)
    print(PREREG_TEXT)
    print("\n  프롬프트 (셀·문항 공통 접미):")
    for line in INSTRUCTION.strip("\n").splitlines():
        print(f"    │ {line}")
    print(f"\n  오답 우주: {', '.join(DISTRACTOR_UNIVERSE)}")
    print(f"  회피 표지: {', '.join(REFUSAL_MARKERS)}")
    print(f"\n  열리는 조건 (ADR-015 미해결 `실험 24 잔여`가 적어 둔 것 그대로):")
    print(f"    ① `검색만` 열이 어느 셀에서 **{OPEN_1_MIN_RETRIEVAL_ONLY}문항 이상**")
    print(f"    ② `corr(recall, mis)` < **{OPEN_2_MAX_CORR}**")
    print(f"    ③ 어느 비교의 불일치 쌍이 **{OPEN_3_MIN_DISCORDANT} 이상**")

    # ── 런타임 대조 — 생존 확인이 아니라 **다이제스트 대조**다 ────────────
    print("\n" + "-" * W)
    print("런타임 — 기록된 다이제스트와 대조한다 (생존 확인만으로는 부족하다 · ADR-015)")
    hr()
    rt = LLM.runtime_info()
    rec = RS._read(LLM.CHECKPOINT_PATH)
    missing = [k for k in ("ollama", "digest") if not rt.get(k)]
    print(f"  체크포인트 파일 : {os.path.relpath(LLM.CHECKPOINT_PATH, ROOT)}")
    print(f"  기록  ollama={rec.get('ollama')}  model={rec.get('model')}  "
          f"digest={str(rec.get('digest'))[:16]}…")
    print(f"  현재  ollama={rt.get('ollama')}  model={LLM.LLM_MODEL}  "
          f"digest={str(rt.get('digest'))[:16]}…")
    if missing:
        print(f"\n  🔴 ollama({LLM.OLLAMA_HOST})에서 {missing}를 못 읽었다 — "
              f"생성을 시작하지 않는다.")
        print(f"     종료 77 (SKIP). 없는 키: {missing}")
        return 77
    same = (rec.get("digest") == rt.get("digest")
            and rec.get("ollama") == rt.get("ollama"))
    print(f"  대조  {'✅ 일치 — 기록된 실행과 같은 조건이다' if same else '⚠️ 불일치 — 이 실행의 숫자는 기록된 실행과 같은 조건이 아니다'}")
    if not same:
        print("        (막지 않는다. 캐시 키에 다이제스트가 들어 있어 옛 답이 "
              "섞이지는 않는다.)")

    # ── 모집단 둘 ────────────────────────────────────────────────────────
    corpus, ledger, qs = P.load()
    key_of = P.key_index(ledger)
    scored, excluded = P.partition(qs, key_of)
    probes, pdrop = probe_population(key_of)
    env = (corpus, ledger, key_of)
    pops = [(POP_A, scored), (POP_B, probes)]
    print("\n" + "-" * W)
    print("모집단 둘 — **합치지 않는다** (실험 22의 규칙 · P1 · G12)")
    hr()
    print(f"  {POP_A}: {len(scored)}/{len(qs)}문항 · 제외 {len(excluded)}"
          f" ({', '.join(i for i, _ in excluded)})")
    tc = Counter(p["type"] for p in probes)
    print(f"  {POP_B}: {len(probes)}/{len(PS.TYPED_PROBES)}프로브 · 제외 "
          f"{len(pdrop)} ({', '.join(f'{i}({t})' for i, t in pdrop)})")
    print(f"     제외 규칙: gold id가 `precision.key_index`에 없음 — 대장의 `key_of`는"
          f" facts·events만 담는다")
    print(f"     유형 배분: " + " · ".join(f"{t} {tc[t]}" for t in PS.TYPES))

    cache, borrowed = load_vectors()
    asks, sums, _ = RD.population()
    need = list(dict.fromkeys(asks + sums + [RS.TRAP_UTTERANCE]
                              + [p["ask"] for p in probes]))
    miss = [t for t in need if t not in cache]
    print(f"\n  임베딩 캐시: 필요 {len(need)} · 히트 {len(need) - len(miss)} · "
          f"미스 {len(miss)}  (`REL_CACHE`/`SWEEP_CACHE`/`PROBE_CACHE` 읽기 전용)")
    if miss:
        sup = RS.Supplier(cache, force="none")
        if sup(miss) is None:
            print(f"\n  🔴 ollama({LLM.OLLAMA_HOST})가 임베딩 {len(miss)}건을 "
                  f"돌려주지 못했다 — `embed` 셀을 돌릴 수 없다. 종료 77 (SKIP).")
            print(f"     없는 키: {miss[:5]}{' …' if len(miss) > 5 else ''}")
            return 77
        own = {k: v for k, v in cache.items() if k not in borrowed}
        if own:
            with open(RQ_VEC_CACHE, "w", encoding="utf-8") as f:
                json.dump(own, f)

    ladder, p_n, p_sig = derive_ladder(cache)
    RS.P_N, RS.P_SIG = p_n, p_sig      # `RS.apply_cell`이 튜플 θ에 박는 서명
    print(f"  사다리 모집단: 채점 {len(asks)}문항 × event 색인 {len(sums)}행 = "
          f"**{p_n}쌍** · 서명 {p_sig}  (다시 유도했다 — 전사 아님)")

    # ── 셀 확정 — 18셀 전량. 전선은 **격자 검사용**이다 ───────────────────
    print("\n" + "=" * W)
    print("셀 — **1단 18셀 전량. 고르지 않는다.** 전선은 격자가 움직였는지 보는 데만 쓴다")
    print("=" * W)
    base_theta = dict(M.THETA_BY_MODE)
    stage1 = build_stage1(ladder)
    snap = RS.snapshot_globals()
    try:
        for c in stage1:
            sup = RS.Supplier(cache, force="none")
            RS.apply_cell(c, base_theta, sup)
            RS.guard_theta(c)
            c.tot = RS.run_cell(env[:2] + (qs, scored, key_of), c, sup)
            if sup.failed or c.tot["degraded"]:
                print(f"\n  🔴 셀 {c.idx} {c.name}에서 강등이 났다 — "
                      f"선언한 모드를 못 돌린다. 종료 77 (SKIP).")
                return 77
            c.ok = True
            RS.restore_globals(snap)
            RS.assert_restored(snap, f"격자 확인 셀 {c.idx}")
    finally:
        RS.restore_globals(snap)
    RS.assert_restored(snap, "격자 확인 종료")

    front = RS.pareto_front(stage1)
    got = {(c.gate[0], c.mode, c.f) for c in front}
    print(f"  전선 {len(front)}셀: "
          + " · ".join(f"#{c.idx} {c.name} ({c.tot['ev_hit']}/{c.tot['ev_tot']}·"
                       f"{c.tot['mis']})"
                       for c in sorted(front, key=lambda x: -x.tot['ev_hit'])))
    if got != EXPECT_FRONT:
        raise SystemExit(
            f"🔴 전선이 사전 등록과 다르다.\n  유도: {sorted(got)}\n"
            f"  기대: {sorted(EXPECT_FRONT)}\n"
            f"  격자가 움직였다 — 재현 대조가 성립하지 않는다. 생성하지 않는다.")
    idxs = {c.idx for c in front}
    print(f"  1단 번호 대조  : 유도 {sorted(idxs)} vs 기대 {sorted(EXPECT_FRONT_IDX)}"
          f"  {'✅ 일치' if idxs == EXPECT_FRONT_IDX else '⚠️ 번호만 다름'}")
    base = next(c for c in stage1 if (c.gate[0], c.mode, c.f) == BASE_KEY)
    dominated = [c.idx for c in stage1 if c not in front]
    print(f"  기준칸 #{base.idx} {base.name} · **지배당하는 셀 {len(dominated)}개가 "
          f"생성 대상에 들어간다**: {dominated}")
    print(f"  → 생성 대상 = 18셀 × 사실블록 2수준 × 모집단 "
          f"({len(scored)}+{len(probes)}) = **{18 * 2 * (len(scored) + len(probes))}"
          f" 문항-셀** (맥락이 같으면 프롬프트가 같아 생성은 그보다 훨씬 적다)")

    # ── 문항별 정답/오답 문자열 + 버린 것 ────────────────────────────────
    keys = {}
    for pop, qlist in pops:
        for q in qlist:
            keys[q["id"]] = question_keys(q, key_of)
    print("\n" + "-" * W)
    print("판별 가능성 필터 — 정답 문자열의 진부분문자열인 오답 문자열은 버린다")
    hr()
    for pop, qlist in pops:
        drops = [(q["id"], d, o) for q in qlist for d, o in keys[q["id"]][2]]
        print(f"  {pop}: 버림 {len(drops)}건 "
              + (" · ".join(f"{i} {d!r}⊂{o!r}" for i, d, o in drops[:4])
                 + (" …" if len(drops) > 4 else "") if drops else "(없음)"))
        empty = [q["id"] for q in qlist if not keys[q["id"]][1]]
        print(f"     🔴 버린 뒤 오답 문자열이 하나도 없는 문항: {empty or '없음'}")

    # ── 생성 ─────────────────────────────────────────────────────────────
    print("\n" + "=" * W)
    print("생성 — 18셀 × 사실블록 2수준 × 모집단 2")
    print("=" * W)
    gen = Generator(LLM.key_runtime(rt))   # 🔄 run_all 아래에서는 기록 판 키로 찾는다(재채점 · 생성 0) — llm.key_runtime
    llm_default = LLM.LLM_TIMEOUT
    LLM.LLM_TIMEOUT = GEN_TIMEOUT      # 🔴 이 실행에만. `llm.py`의 상수는 그대로다
    print(f"  체크포인트 {os.path.relpath(RESPONSE_CACHE, ROOT)} · "
          f"기존 항목 {len(gen.store)}건 (웜이면 다시 만들지 않는다)")
    print(f"  생성 타임아웃 {GEN_TIMEOUT}초 (`llm.py` 기본값 {llm_default}초를 이 실행에만 "
          f"낮췄다) · 정지 시 재시도 {GEN_RETRIES}회 · 재시도는 전부 아래에 센다")
    t_gen = time.perf_counter()
    snap = RS.snapshot_globals()
    inject_before = M.INJECT_KNOWN_FACTS
    try:
        for level in FACT_LEVELS:
            print(f"\n  ── {FACT_LABEL[level]} "
                  f"(`INJECT_KNOWN_FACTS={level}`) ────────────────")
            for c in stage1:
                for pop, qlist in pops:
                    sup = RS.Supplier(cache, force="none")
                    RS.apply_cell(c, base_theta, sup)
                    RS.guard_theta(c)
                    if not hasattr(c, "res"):
                        c.res = {}
                    t = run_cell_gen(env, c, gen, keys, qlist, level)
                    if sup.failed or t["degraded"]:
                        print(f"\n  🔴 셀 {c.name}/{pop}에서 강등 — 종료 77 (SKIP).")
                        return 77
                    c.res[(level, pop)] = t
                    RS.restore_globals(snap)
                    RS.assert_restored(snap, f"생성 셀 {c.idx}/{pop}")
                    assert_inject(inject_before, f"생성 셀 {c.idx}/{pop}")
                a = c.res[(level, POP_A)]
                b_ = c.res[(level, POP_B)]
                print(f"  {c.idx:>3} {c.name:<28} A: recall {a['ev_hit']:>2}/"
                      f"{a['ev_tot']} mis {a['mis']:>2} 정답 {a['n_gold']:>2} "
                      f"오답 {a['n_dist']:>2} 무응답 {a['n_refuse']:>2}  │  "
                      f"B: recall {b_['ev_hit']:>2}/{b_['ev_tot']} mis "
                      f"{b_['mis']:>2} 정답 {b_['n_gold']:>2} 오답 {b_['n_dist']:>2} "
                      f"무응답 {b_['n_refuse']:>2}   (히트 {gen.hits}/생성 {gen.misses})")
    finally:
        RS.restore_globals(snap)
        M.INJECT_KNOWN_FACTS = inject_before
        LLM.LLM_TIMEOUT = llm_default   # 남의 모듈 상수를 흘리지 않는다
    RS.assert_restored(snap, "생성 종료")
    gen_wall = time.perf_counter() - t_gen

    # ── 🔴 직교성 대조 — 사실 블록이 검색을 안 건드렸는가 ────────────────
    print("\n" + "-" * W)
    print("직교성 대조 — 사실 블록 스위치가 **검색 축을 건드리지 않았는가**")
    hr()
    bad = []
    for c in stage1:
        for pop, _ in pops:
            on, off = c.res[(True, pop)], c.res[(False, pop)]
            if ([r["ev_hit"] for r in on["rows"]] != [r["ev_hit"] for r in off["rows"]]
                    or [r["mis"] for r in on["rows"]] != [r["mis"] for r in off["rows"]]):
                bad.append(f"#{c.idx} {c.name}/{pop}")
    print(f"  18셀 × 모집단 2에서 ON/OFF의 `evidence_recall`·`mis@q`가 문항 단위로 "
          f"같은가: {'✅ 전부 같다' if not bad else '🔴 다른 곳 ' + ', '.join(bad)}")
    print("  🔴 이것이 참이라야 두 축이 **직교**한다 — 아니면 사실 블록을 끈 것이")
    print("     검색까지 바꾼 것이고, 그러면 아래 교환비는 두 원인이 섞인 값이다.")
    if bad:
        raise SystemExit("🔴 직교성이 깨졌다 — 이 설계는 두 축을 가를 수 없다.")

    # ── 재현 대조 — 실험 24가 이 설계의 부분집합인가 ─────────────────────
    print("\n" + "-" * W)
    print("재현 대조 — 사실ON × 실험 24의 6셀 × 모집단 A가 그 실험의 표를 재현하는가")
    hr()
    print(f"  {'#':>3} {'셀':<28}{'이 실행':>26}{'실험 24':>26}  판정")
    mism = []
    for idx in sorted(EXPECT_EXP24):
        c = next(x for x in stage1 if x.idx == idx)
        t = c.res[(True, POP_A)]
        got_t = (t["ev_hit"], t["mis"], t["n_gold"], t["n_dist"], t["n_refuse"])
        exp_t = EXPECT_EXP24[idx]
        ok = got_t == exp_t
        if not ok:
            mism.append((idx, got_t, exp_t))
        print(f"  {idx:>3} {c.name:<28}{str(got_t):>26}{str(exp_t):>26}  "
              f"{'✅' if ok else '🔴 다름'}")
    if mism:
        raise SystemExit(
            f"🔴 실험 24를 재현하지 못했다: {mism}\n"
            f"   같은 셀·같은 조건·같은 캐시인데 값이 다르면 두 실행 중 하나가 "
            f"다른 것을 재고 있다. 숫자를 읽기 전에 그것부터 설명해야 한다.")
    ro_got = {i: next(x for x in stage1 if x.idx == i).res[(True, POP_A)]
              ["gold_ret_only"] for i in sorted(EXPECT_EXP24_RETONLY)}
    print(f"  `검색만` 열 대조 (실험 24 §D 주입 경로 표): 유도 {ro_got} vs "
          f"기대 {EXPECT_EXP24_RETONLY}"
          f"  {'✅' if ro_got == EXPECT_EXP24_RETONLY else '🔴 다름'}")
    if ro_got != EXPECT_EXP24_RETONLY:
        raise SystemExit(
            f"🔴 `검색만` 열이 실험 24와 다르다: {ro_got} vs {EXPECT_EXP24_RETONLY}. "
            f"이 열이 조건 ①의 판정을 통째로 지고 있다 — 계산이 헐거워지면 ①이 "
            f"공짜로 열린다.")
    print("  ✅ 6셀 5지표 + `검색만` 전부 일치 — **실험 24는 이 설계의 부분집합이고, 재현이 곧 보존이다.**")

    # ── 결과표 ───────────────────────────────────────────────────────────
    print("\n" + "=" * W)
    print("결과 — 사실블록 수준 × 모집단마다 18셀")
    print("=" * W)
    for level in FACT_LEVELS:
        for pop, qlist in pops:
            cell_table(f"◆ {FACT_LABEL[level]} · 모집단 {pop} (문항 n={len(qlist)})",
                       stage1, level, pop,
                       "`recall`은 근거 건수 · `mis@q`는 항목 건수 · 나머지는 문항 수. "
                       "분모가 다르므로 나란히 읽되 나누지 않는다 (G15).")

    # ── 열리는 조건 ① ────────────────────────────────────────────────────
    print("\n" + "=" * W)
    print(f"열리는 조건 ① — `검색만` 열이 어느 셀에서 {OPEN_1_MIN_RETRIEVAL_ONLY}문항 이상인가")
    print("=" * W)
    print("  `검색만` = 정답 문자열이 **사실 블록에 없고 검색만 가져온** 문항.")
    print("  셀 사이의 응답 차이가 나올 수 있는 자리는 여기뿐이다.")
    print(f"\n  {'조건':<22}{'최대 `검색만`':>14}{'그 셀':>32}{'≥5인 셀 수':>12}  판정")
    hr()
    open1 = {}
    for level in FACT_LEVELS:
        for pop, _ in pops:
            vals = [(c.res[(level, pop)]["gold_ret_only"], c) for c in stage1]
            mx, mc = max(vals, key=lambda v: v[0])
            n_ok = sum(1 for v, _ in vals if v >= OPEN_1_MIN_RETRIEVAL_ONLY)
            open1[(level, pop)] = (mx, n_ok)
            print(f"  {FACT_LABEL[level] + ' · ' + pop:<22}{mx:>14}"
                  f"{f'#{mc.idx} {mc.name}':>32}{n_ok:>12}  "
                  f"{'🟢 열림' if mx >= OPEN_1_MIN_RETRIEVAL_ONLY else '⛔ 안 열림'}")
    opened1 = any(v[0] >= OPEN_1_MIN_RETRIEVAL_ONLY for v in open1.values())
    print(f"\n  → ① {'🟢 **열렸다**' if opened1 else '⛔ 안 열렸다'}")
    print("  ⚠️ 사실OFF에서 `검색만`은 곧 `검색이 정답을 가져온 문항 수`다 — 사실 블록이")
    print("     없으므로 분모에서 뺄 것이 없다. **그것이 이 축을 만든 목적이다.**")

    # ── 열리는 조건 ② ────────────────────────────────────────────────────
    print("\n" + "=" * W)
    print(f"열리는 조건 ② — 셀 집합에서 corr(recall, mis) < {OPEN_2_MAX_CORR}인가")
    print("=" * W)
    print("  실험 24는 파레토 전선 5셀 + 기준칸에서 `r = +0.929`였다. 비지배 집합은")
    print("  **정의상** 두 축을 같이 움직인다 — 표본이 작아서가 아니라 선택 때문이다.")
    print(f"\n  {'집합':<34}{'셀 수':>7}{'모집단':<14}{'r':>9}  판정")
    hr()
    corr_by = {}
    for pop, _ in pops:
        rec_c = [c.res[(True, pop)]["ev_hit"] for c in stage1]
        mis_c = [c.res[(True, pop)]["mis"] for c in stage1]
        r_all = pearson(rec_c, mis_c)
        corr_by[pop] = r_all
        sub = [c for c in stage1 if c.idx in EXPECT_EXP24]
        r_sub = pearson([c.res[(True, pop)]["ev_hit"] for c in sub],
                        [c.res[(True, pop)]["mis"] for c in sub])
        for nm, r_, n_ in (("실험 24의 6셀 (전선+기준칸)", r_sub, len(sub)),
                           ("**1단 18셀 전량 (이 실험)**", r_all, len(stage1))):
            v = "정의 안 됨" if r_ is None else f"{r_:+.3f}"
            ok = r_ is not None and abs(r_) < OPEN_2_MAX_CORR
            print(f"  {nm:<34}{n_:>7}{pop:<14}{v:>9}  "
                  f"{'🟢 열림' if ok else '⛔ 안 열림'}")
    opened2 = any(r is not None and abs(r) < OPEN_2_MAX_CORR
                  for r in corr_by.values())
    print(f"\n  → ② {'🟢 **열렸다**' if opened2 else '⛔ 안 열렸다'}")
    print("  🔴 이 값은 **검색 지표만의 함수라 생성 이전에 정해진다.** 응답을 보고 셀을")
    print("     고른 것이 아니다 — 애초에 고르지 않았다.")

    # ── 유의성 + 열리는 조건 ③ ───────────────────────────────────────────
    print("\n" + "=" * W)
    print("유의성 — 쌍체 부호검정(McNemar 정확검정) · **이 n의 최소 달성 p를 병기한다**")
    print("=" * W)
    print("  🔴 계열 둘을 **따로** 적는다. F계열이 불일치 10을 넘겨도 그것은")
    print("     *'검색 축을 잴 검정력이 생겼다'*가 아니다 — 다른 축의 이야기다.")

    def cmp_rows(series, level_a, cell_a, level_b, cell_b, pop, label):
        ra = cell_a.res[(level_a, pop)]["rows"]
        rb = cell_b.res[(level_b, pop)]["rows"]
        out = []
        for name, field in AXES:
            pairs = [(int(x[field]), int(y[field])) for x, y in zip(ra, rb)]
            b, cc, p, minp = sign_test(pairs)
            out.append(dict(series=series, label=label, pop=pop, axis=name,
                            b=b, c=cc, disc=b + cc, p=p, minp=minp))
        return out

    verdicts = []
    for pop, qlist in pops:
        for level in FACT_LEVELS:
            for c in stage1:
                if c is base:
                    continue
                verdicts += cmp_rows("R", level, base, level, c, pop,
                                     f"{FACT_LABEL[level]} #{base.idx}↔#{c.idx} {c.name}")
        for c in stage1:
            verdicts += cmp_rows("F", True, c, False, c, pop,
                                 f"#{c.idx} {c.name} ON↔OFF")

    for series, title in (("R", "계열 R (검색 축) — 같은 사실블록 수준에서 기준칸 대 나머지 17셀"),
                          ("F", "계열 F (사실블록 축) — 같은 셀에서 ON 대 OFF")):
        rows_s = [v for v in verdicts if v["series"] == series]
        print(f"\n  ◆ {title}  ({len(rows_s)}비교)")
        hr()
        sig = [v for v in rows_s if v["p"] < 0.05]
        top = sorted(rows_s, key=lambda v: (-v["disc"], v["p"]))[:12]
        print(f"  {'모집단':<14}{'비교':<44}{'축':<10}{'b':>4}{'c':>4}"
              f"{'불일치':>7}{'p(양측)':>10}{'최소달성p':>11}  판정")
        for v in top:
            note = ("🔴 유의" if v["p"] < 0.05 else
                    "불일치 0 — 검정할 것이 없다" if v["disc"] == 0 else
                    f"검정력 없음 (불일치 {v['disc']}쌍으로는 유의 불가능)"
                    if v["minp"] >= 0.05 else "유의하지 않음")
            print(f"  {v['pop']:<14}{v['label']:<44}{v['axis']:<10}{v['b']:>4}"
                  f"{v['c']:>4}{v['disc']:>7}{v['p']:>10.4f}{v['minp']:>11.6f}  {note}")
        print(f"  (불일치 내림차순 상위 {len(top)}행만. 전량 {len(rows_s)}행)")
        mx = max((v["disc"] for v in rows_s), default=0)
        print(f"  → 계열 {series}: 최대 불일치 **{mx}쌍** · p<0.05인 비교 "
              f"**{len(sig)}건** / {len(rows_s)}건 · "
              f"{'🟢 ③ 열림' if mx >= OPEN_3_MIN_DISCORDANT else '⛔ ③ 안 열림'}")

    maxdisc = {s: max((v["disc"] for v in verdicts if v["series"] == s), default=0)
               for s in ("R", "F")}
    opened3 = any(m >= OPEN_3_MIN_DISCORDANT for m in maxdisc.values())
    n_a, n_b = len(scored), len(probes)
    print(f"\n  문항 n = {n_a}(A) · {n_b}(B). 모든 쌍이 불일치하고 한 방향으로 쏠려도")
    print(f"  p ≥ {2 * 0.5 ** n_a:.2e}(A) · {2 * 0.5 ** n_b:.2e}(B) — **그것이 하한이다.**")
    print(f"  → ③ {'🟢 **열렸다**' if opened3 else '⛔ 안 열렸다'} "
          f"(계열 R 최대 {maxdisc['R']}쌍 · 계열 F 최대 {maxdisc['F']}쌍)")
    print("  🔴 **'비교가 늘었다'와 '검정력이 생겼다'는 다르다.** 셀을 6→18로 늘린 것은")
    print("     비교 수를 늘렸을 뿐 한 비교의 n(문항 수)은 그대로다. 불일치를 늘린 것이")
    print("     무엇인지는 위 두 줄의 계열별 최대값이 말한다.")

    # ── 세 조건 요약 ─────────────────────────────────────────────────────
    print("\n" + "=" * W)
    print("세 열리는 조건 — **이 실행이 직접 센 값**")
    print("=" * W)
    print(f"  {'#':<4}{'조건':<40}{'실측':<30}  판정")
    hr()
    mx1 = max(v[0] for v in open1.values())
    r18 = corr_by[POP_A]
    print(f"  {'①':<4}{'`검색만` ≥ 5문항인 셀이 있는가':<40}"
          f"{f'최대 {mx1}문항':<30}  {'🟢 열림' if opened1 else '⛔ 안 열림'}")
    print(f"  {'②':<4}{'corr(recall, mis) < 0.7':<40}"
          f"{f'18셀 전량 {r18:+.3f} (A) · exp24 6셀은 위 표':<30}  "
          f"{'🟢 열림' if opened2 else '⛔ 안 열림'}")
    d3 = f"R {maxdisc['R']}쌍 · F {maxdisc['F']}쌍"
    print(f"  {'③':<4}{'불일치 쌍 ≥ 10인 비교가 있는가':<40}{d3:<30}  "
          f"{'🟢 열림' if opened3 else '⛔ 안 열림'}")

    # ── 교환비 ───────────────────────────────────────────────────────────
    print("\n" + "=" * W)
    print("교환비 — `정답진술 ~ a·recall + b·mis + c` (셀 18개가 점이다)")
    print("=" * W)
    print("  🔴 **기술 통계다.** 점 하나가 셀 하나이고 18셀은 같은 문항 위의 18구성이라")
    print("     독립 표본이 아니다. 이 회귀가 답하는 것은 **두 축이 분리되는가** 하나뿐이고,")
    print("     판정은 위 부호검정이 한다.")
    print(f"\n  {'조건':<22}{'a(recall)':>22}{'b(mis)':>22}{'상수':>12}{'R²':>8}"
          f"{'|a/b|':>9}")
    hr()
    for level in FACT_LEVELS:
        for pop, _ in pops:
            rec_c = [c.res[(level, pop)]["ev_hit"] for c in stage1]
            mis_c = [c.res[(level, pop)]["mis"] for c in stage1]
            y = [c.res[(level, pop)]["n_gold"] for c in stage1]
            beta, se, r2, singular = ols(y, [rec_c, mis_c])
            if singular:
                print(f"  {FACT_LABEL[level] + ' · ' + pop:<22}"
                      f"{'특이 — 두 축이 완전 공선이다':>66}")
                continue
            ratio = (f"{abs(beta[1] / beta[2]):.2f}" if beta[2] else "정의 안 됨")
            print(f"  {FACT_LABEL[level] + ' · ' + pop:<22}"
                  f"{f'{beta[1]:+.4f} ± {se[1]:.4f}':>22}"
                  f"{f'{beta[2]:+.4f} ± {se[2]:.4f}':>22}"
                  f"{beta[0]:>12.3f}{(r2 if r2 is not None else float('nan')):>8.3f}"
                  f"{ratio:>9}")
    print("\n  `± `는 최소제곱 표준오차다. **계수가 자기 표준오차보다 작으면 그 축은")
    print("  분리되긴 했으나 값이 0과 구별되지 않는다** — 그것도 결과다.")

    # ── 오주입 사용률 재측정 ─────────────────────────────────────────────
    print("\n" + "=" * W)
    print("오주입 사용률 — ①이 열린 설정에서 다시 잰다 (ADR-015 `오주입 지표의 세 번째 문제`)")
    print("=" * W)
    print("  실험 24가 여섯 셀 전부 **6%**(18문항 중 1건)로 쟀고, 그 값은 **정답조차")
    print("  사실 블록에서 오던 조건**의 것이었다. 닫히는 조건은 그 조건이 걷힌 설정에서")
    print("  다시 재고 6%와 유의하게 다른지 판정하는 것이다.")
    if not opened1:
        print("\n  ⛔ ①이 안 열렸다 — **재지 않는다.** 6%가 서 있던 조건이 그대로이므로")
        print("     여기서 나온 어떤 값도 그 조건을 벗어나지 못한다. 행은 열어 둔다.")
    else:
        print(f"\n  {'조건':<22}{'셀':<28}{'검색만':>7}{'오답주입':>9}{'사용':>6}"
              f"{'사용률':>8}{'경로(사실/검색)':>18}")
        hr()
        cand = [c for c in stage1
                if c.res[(False, POP_A)]["gold_ret_only"] >= OPEN_1_MIN_RETRIEVAL_ONLY]
        for pop, _ in pops:
            for level in FACT_LEVELS:
                for c in cand:
                    t = c.res[(level, pop)]
                    inj_n, used_n = t["n_dist_inj"], t["n_dist_used"]
                    vf = sum(1 for r in t["rows"] if r["inj"]["dist_in_facts"])
                    vr = sum(1 for r in t["rows"] if r["inj"]["dist_in_ret"])
                    rate = f"{used_n / inj_n * 100:.0f}%" if inj_n else "—"
                    print(f"  {FACT_LABEL[level] + ' · ' + pop:<22}"
                          f"{f'#{c.idx} {c.name}':<28}"
                          f"{t['gold_ret_only']:>7}{inj_n:>9}{used_n:>6}{rate:>8}"
                          f"{f'{vf} / {vr}':>18}")
        print("\n  판정 — 같은 셀의 ON 대 OFF를 **문항 단위로 짝지어** 부호검정")
        print(f"  {'모집단':<14}{'셀':<28}{'b(ON만 사용)':>13}{'c(OFF만)':>10}"
              f"{'불일치':>7}{'p(양측)':>10}{'최소달성p':>11}  판정")
        hr()
        for pop, _ in pops:
            for c in cand:
                on = c.res[(True, pop)]["rows"]
                off = c.res[(False, pop)]["rows"]
                pairs = [(int(bool(x["used_dist"])), int(bool(y["used_dist"])))
                         for x, y in zip(on, off)]
                b, cc, p, minp = sign_test(pairs)
                note = ("🔴 유의 — 6%가 조건에 달려 있었다" if p < 0.05 else
                        "불일치 0 — 사용률이 사실 블록과 무관하다" if b + cc == 0 else
                        f"검정력 없음 (불일치 {b + cc}쌍)" if minp >= 0.05 else
                        "유의하지 않음")
                print(f"  {pop:<14}{f'#{c.idx} {c.name}':<28}{b:>13}{cc:>10}"
                      f"{b + cc:>7}{p:>10.4f}{minp:>11.6f}  {note}")

    # ── 결론 ─────────────────────────────────────────────────────────────
    print("\n" + "=" * W)
    print("이 실행이 Q2-2에 돌려주는 것")
    print("=" * W)
    n_open = sum([opened1, opened2, opened3])
    print(f"  열린 조건 {n_open}/3 — ①{'🟢' if opened1 else '⛔'} "
          f"②{'🟢' if opened2 else '⛔'} ③{'🟢' if opened3 else '⛔'}")
    sig_r = [v for v in verdicts if v["series"] == "R" and v["p"] < 0.05]
    sig_f = [v for v in verdicts if v["series"] == "F" and v["p"] < 0.05]
    print(f"  검색 축(계열 R)에서 p<0.05인 비교: **{len(sig_r)}건** · "
          f"사실블록 축(계열 F): **{len(sig_f)}건**")
    if sig_r:
        print("  🔴 검색 축에서 유의한 차이가 있다 — 교환비의 첫 근거다:")
        for v in sig_r[:8]:
            print(f"     {v['pop']} · {v['label']} · {v['axis']} · "
                  f"b={v['b']} c={v['c']} p={v['p']:.4f}")
    else:
        print("  ⛔ **검색 축에서는 여전히 셀 간 응답 차이가 관측되지 않는다.**")
    print("\n  🔴 **이 실행은 판정하지 않는다.** `lexical` 대 `embed`의 승격 판단은")
    print("     단계 5의 것이고 기본값은 G16이 못박았다. 여기 있는 것은 그 규칙에")
    print("     **입력**되는 숫자다.")

    wall = time.perf_counter() - t_start
    print("\n" + "-" * W)
    print(f"  벽시계 {wall:.1f}초 (그중 생성 {gen_wall:.1f}초 · 순 LLM "
          f"{gen.gen_seconds:.1f}초) · 생성 {gen.misses}건 · 캐시 히트 {gen.hits}건")
    if gen.retries:
        print(f"  ⚠️ **생성 스톨 {len(gen.retries)}건 — 이 실행은 깨끗한 실행이 아니다.**")
        for tag, att, took, why in gen.retries:
            print(f"       {tag} · 시도 {att} · {took:.1f}초 · {why}")
    else:
        print("  생성 스톨 0건 (이 실행에서는 재시도가 없었다)")
    print(f"  ollama {rt.get('ollama')} · {LLM.LLM_MODEL} "
          f"digest {str(rt.get('digest'))[:16]}… · temp={LLM.LLM_TEMPERATURE} "
          f"seed={LLM.LLM_SEED} num_ctx={LLM.LLM_NUM_CTX}")
    hr()
    return 0


if __name__ == "__main__":
    sys.exit(main())
