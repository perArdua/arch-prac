# -*- coding: utf-8 -*-
"""
hardcoding_audit.py — **코퍼스에 박힌 상수를 세고, 유도 가능한지 재고, 갈아 끼워 본다.**

## 무엇을 묻는가

제품 소유자의 질문은 *"휴리스틱이 대화 종류가 다양해져도 일반적으로 동작하는가"*였다.
가장 노골적인 자리가 `scoring.UBIQUITOUS = {"지우"}`다 — **이 코퍼스 등장인물의 이름**이고
다른 코퍼스에서는 아무 뜻이 없다. 그런 자리를 **전부 열거**하고, 각각에
«코퍼스 고유 / 언어 고유 / 도메인 무관»을 붙이고, 그중 하나(`UBIQUITOUS`)에 대해
**코퍼스에서 유도할 수 있는가**를 실제로 계산한다.

## 🔴 이 파일은 아무것도 고치지 않는다

`experiments/scoring.py`와 `prototype/**`는 **읽기만** 한다. 갈아 끼우기는 전부
**런타임 재바인딩**(`scoring.UBIQUITOUS = ...`)이고 `try/finally`로 되돌린다(G13).
끝에 `git diff --stat`이 비어 있어야 한다.

## 🔴 절 0이 먼저인 이유 — 「얼렸다」가 절반만 참이다

`test_scoring.py`의 `TestFrozenScorersAreFrozen`은 `survived_frozen`·`survived_v2`의
**함수 원문**을 sha256으로 못 박는다. 그런데 `UBIQUITOUS`는 **모듈 전역**이라 그 원문
밖에 있다. 즉 **상수를 갈면 해시는 통과하는데 동작은 바뀐다.** 절 0이 그것을 심어서
확인한다 — 이 레인의 첫 발견이고, 나머지 절 전부의 전제다(갈아 끼우기가 조용하다는 뜻).

## 종료 코드

0 = 전부 통과. 1 = 앵커(`file:line`) 불일치 · 기록값 재현 실패 · 심은 위반 미발화.
"""
import collections
import contextlib
import hashlib
import inspect
import io
import json
import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [HERE, os.path.join(HERE, "tests")]
sys.path.insert(0, os.path.join(ROOT, "prototype"))
sys.stdout.reconfigure(encoding="utf-8")

import yaml                                                  # noqa: E402
import scoring                                               # noqa: E402
from memory import Memory                                    # noqa: E402

W = 86


# ══════════════════════════════════════════════════════════════════════════
# 0. 상수 대장 — 자리(`file:line`)를 **기계로** 확인한다 (G18)
# ══════════════════════════════════════════════════════════════════════════
#
# `kind`는 셋 중 하나다. **«박혀 있다 = 나쁘다»가 아니다** — 가르는 것이 요점이다.
#
#   코퍼스 고유   이 코퍼스(eval/)의 성질에서 나온 값. 다른 코퍼스에서 **틀린다**
#   언어 고유     한국어의 성질에서 나온 값. 다른 코퍼스에서도 한국어면 **맞는다**
#   도메인 무관   자료와 무관한 논변·산술에서 나온 값
#
# `derived`는 «그 값이 무엇에서 나왔나»다 — 분류와 **다른 축**이다.
# 코퍼스 고유인데 유도된 것(`THETA_BY_MODE`)도, 도메인 무관인데 미유도인 것도 있다.
CONSTANTS = [
    # name, 파일, 줄, 그 줄에 있어야 하는 문자열, kind, derived, 근거
    ("UBIQUITOUS", "experiments/scoring.py", 51, "UBIQUITOUS = ",
     "코퍼스 고유", "🟢 유도 — **유도 이력이 값 옆에 있다** (`UBIQUITOUS_PROVENANCE`)",
     "값이 등장인물 이름 `지우`다 — 코퍼스가 바뀌면 틀린다. 🆕 그러나 이제 «왜 그 "
     "값인가»가 코드에 산다: 기저·규칙·tau·n·구간·모집단 서명을 값 **옆**에 "
     "(닫힌 해시 밖 별도 객체로) 들고, `stale_ubiquitous()`가 대조한다 — "
     "`THETA_BY_MODE`/`stale_theta`와 같은 형태다"),
    ("MIN_ROOTS", "experiments/scoring.py", 85, "MIN_ROOTS = ",
     "도메인 무관", "미유도 (논변)",
     "«분모 1이면 한 번만 맞아도 100%»는 산술이다. 한국어와도 이 코퍼스와도 무관"),
    ("겹침 문턱 0.5 (frozen)", "experiments/scoring.py", 110, ">= 0.5",
     "도메인 무관", "미유도 (이름 없는 리터럴)",
     "비율 문턱 자체는 자료와 무관하지만 **어디서도 유도된 적이 없다.** "
     "이름도 없어 세 곳(:110 :136 :240)에 각각 박혀 있다"),
    ("겹침 문턱 0.5 (v2)", "experiments/scoring.py", 136, ">= 0.5",
     "도메인 무관", "미유도 (이름 없는 리터럴)", "위와 같은 값의 두 번째 사본"),
    ("겹침 문턱 0.5 (v3)", "experiments/scoring.py", 240, ">= 0.5",
     "도메인 무관", "미유도 (이름 없는 리터럴)", "위와 같은 값의 세 번째 사본"),
    ("_ORDINALS", "experiments/scoring.py", 148, "_ORDINALS = frozenset",
     "언어 고유", "미유도 (한국어 고유수사)",
     "`첫 두 세 네 …` — 한국어 수관형사 표. 영어 코퍼스면 통째로 무의미하고, "
     "한국어면 코퍼스가 바뀌어도 맞는다"),
    ("_ORDINAL_MARKER", "experiments/scoring.py", 154, "_ORDINAL_MARKER = ",
     "언어 고유", "미유도 (한국어 문법)",
     "`번째`가 **뒤 낱말**의 회차를 매긴다는 것은 한국어 분류사 문법이다"),
    ("_ENDINGS", "prototype/memory.py", 312, "_ENDINGS = re.compile",
     "언어 고유", "미유도 (수기 어미표)",
     "한국어 용언 어미 목록. `memory.py:312`가 «형태소 분석기 없이 쓰는 "
     "최소 대용»이라 적었다 — 언어에 매였지 코퍼스에 매이지 않았다"),
    ("_PART", "prototype/memory.py", 337, "_PART = re.compile",
     "언어 고유", "미유도 (수기 조사표)",
     "한국어 조사 목록(`lexical_fixed` 쪽). 아래 `_PARTICLE`과 **두 벌**이다"),
    ("_PARTICLE", "prototype/memory.py", 776, "_PARTICLE = re.compile",
     "언어 고유", "미유도 (수기 조사표)",
     "같은 종류의 조사 목록 **두 번째 사본**. 🔄 갈린 것은 **7종**이다 — "
     "`께서`·`랑`·`에게서`·`으로서`·`으로써`·`이랑`·`한테서`가 여기에만 있고 "
     "`_PART`에만 있는 것은 **없다**(`_PART ⊂ _PARTICLE`). 실험 30이 대표 4종만 "
     "이름 붙였던 자리이고, 절 1-c가 그 차집합을 기계로 다시 뽑는다"),
    ("`len(w) < 2` (_roots)", "prototype/memory.py", 785, "len(w) < 2",
     "언어 고유", "미유도 (수기)",
     "«한글 2음절 미만은 어근이 아니다»라는 가정. 절 4가 이 규칙의 비용을 센다"),
    ("`len(w) > 2` (_fixed_word)", "prototype/memory.py", 343, "len(w) > 2",
     "언어 고유", "미유도 (수기)",
     "«강아지 → 강 방지» — 2음절 하한을 조사 제거 쪽에 다시 박은 것"),
    ("ntok 1.5토큰/글자", "prototype/memory.py", 307, "len(t) * 1.5",
     "언어 고유", "유도 (docs/05 §2)",
     "한국어 글자당 토큰 비. 언어가 바뀌면 통째로 틀린다"),
    # 🔄 아래 넷의 줄 번호는 2026-09-10에 밀렸다 — A1(삭제 전파)이 `delete_item`
    #    위쪽에 주석을 더하면서 게이트 블록이 21줄 내려갔다. **값도 규칙도 안
    #    바뀌었고 자리만 움직였다.**
    ("게이트 과거참조 정규식", "prototype/memory.py", 1017, "기억|그때|저번",
     "언어 고유", "미유도 (수기 어휘목록)",
     "`기억|그때|저번|예전|아까|전에|했잖아|말했|뭐였|언제` — 한국어 과거참조 표현. "
     "특정 인물·사건이 아니라 **문법적 표현**이라 코퍼스 고유가 아니다"),
    ("게이트 의례발화 정규식", "prototype/memory.py", 1021, "응|ㅇㅇ|ㅋ+",
     "언어 고유", "미유도 (수기 어휘목록)",
     "`ㅇㅇ`·`ㅋ+`는 한국어 **채팅체**다. 언어 + 매체에 매였다"),
    ("게이트 `len < 8`", "prototype/memory.py", 1019, "len(utterance) < 8",
     "언어 고유", "미유도 (이름 없는 리터럴)",
     "«한글 8글자 미만은 신호 없음». 글자 단위라 언어에 매였고 유도된 적 없다"),
    ("게이트 `w[:2]` / `{2,}`", "prototype/memory.py", 1024, "w[:2] in vocab",
     "언어 고유", "미유도 (수기)",
     "«앞 2글자» 접점. 위 `len(w) < 2`와 같은 2음절 가정의 세 번째 자리. "
     "🔄 A2가 어휘의 **출처**를 방 단위로 바꿨지만(`_recall_vocab_for`) "
     "«앞 2글자»라는 상수 자체는 그대로다 — 움직인 것은 이 앵커의 철자뿐이다"),
    ("TAU_IMPORTANCE", "prototype/memory.py", 185, "TAU_IMPORTANCE = ",
     "도메인 무관", "유도 (실험 7 스윕)",
     "0.2~0.4가 **둔감구간**이라 점이 아니라 구간이 답이다 — 구간이 넓은 것이 "
     "코퍼스 의존을 줄인다"),
    ("THETA_RELEVANCE", "prototype/memory.py", 193, "THETA_RELEVANCE = ",
     "코퍼스 고유", "유도 (gate_sweep 무릎)",
     "`memory.py:193`이 스스로 «lexical 척도 전용»이라 못 박았다(F27). "
     "무릎은 **이 코퍼스의 오주입 곡선**에서 나왔다"),
    ("TOP_K", "prototype/memory.py", 194, "TOP_K = ",
     "코퍼스 고유", "🔴 미유도 — 실험이 «정할 수 없다»고 적었다",
     "docs/11 실험 7 §B: «k — 이 실험으로는 정할 수 없다 (평가 설계의 산물)»"),
    ("WINDOW_TURNS", "prototype/memory.py", 195, "WINDOW_TURNS = ",
     "코퍼스 고유", "유도 (실험 7C 무릎)",
     "무릎은 이 코퍼스의 턴 밀도에서 나온다. 세션당 30턴이라는 이 코퍼스의 모양이 "
     "바뀌면 무릎도 움직인다"),
    ("SURFACED_PENALTY", "prototype/memory.py", 196, "SURFACED_PENALTY = ",
     "코퍼스 고유", "유도 (실험 10B 무릎)", "위와 같다 — 무릎은 자료의 함수다"),
    ("W_REL / W_IMP", "prototype/memory.py", 203, "W_REL, W_IMP = ",
     "코퍼스 고유", "🔴 미유도 — «현행값 그대로»(G16)",
     "`memory.py:202`: «값은 전부 현행값 그대로다». 0.6/0.4는 어디서도 "
     "유도되지 않았고 격자 대상으로 남아 있다"),
    ("THETA_BY_MODE", "prototype/memory.py", 224, "THETA_BY_MODE = ",
     "코퍼스 고유", "🟢 유도 — **유도 이력이 값 옆에 있다**",
     "`(theta, f, n, population_sig)` 튜플이 «어느 모집단 n=378 · 서명 (22,21)에서 "
     "나왔나»를 값과 함께 든다. 이 저장소에서 **유일하게** 코퍼스 의존을 "
     "런타임에 감지하는 상수다(`stale_theta`)"),
    ("DEDUP_WINDOW", "prototype/memory.py", 771, "DEDUP_WINDOW = ",
     "코퍼스 고유", "미유도 (수기)",
     "«20턴 안의 같은 어근 뭉치는 대개 같은 사건». 턴 밀도가 다른 코퍼스에서 "
     "20턴은 다른 시간 길이다"),
    ("DEDUP_JACCARD", "prototype/memory.py", 772, "DEDUP_JACCARD = ",
     "도메인 무관", "미유도 (수기)",
     "겹침 비율 문턱. 위 0.5와 같은 종류이고 역시 유도된 적이 없다"),
    ("DIGEST_KEEP_SESSIONS", "prototype/memory.py", 264, "DIGEST_KEEP_SESSIONS = ",
     "코퍼스 고유", "🟢 유도 — **주석이 코퍼스를 직접 가리킨다**",
     "`memory.py:264`: «24를 구속하는 것은 코퍼스 하나 — "
     "`eval/fact-ledger.yaml`의 `meta.sessions = 24`». 코퍼스 고유라고 "
     "**스스로 적어 둔** 유일한 상수다"),
    ("STALE_EXPIRE_SESSIONS", "prototype/memory.py", 271, "STALE_EXPIRE_SESSIONS = ",
     "도메인 무관", "미유도 (설계 기록)", "«설계 기록의 값 그대로 3»"),
    ("MIN_EVIDENCE_FOR_INTERPRETATION", "prototype/memory.py", 198,
     "MIN_EVIDENCE_FOR_INTERPRETATION = ",
     "코퍼스 고유", "미유도 («수기 세션에서 도출»)",
     "주석이 출처를 «수기 세션»이라 적었다 — 그 세션이 이 코퍼스다"),
    ("SCENE_VALUE_MAXLEN", "prototype/memory.py", 302, "SCENE_VALUE_MAXLEN = ",
     "언어 고유", "미유도 (docs/16 인용)", "글자 수 상한이라 언어에 매였다"),
    ("KNOWN_CHARS", "experiments/guard_sim.py", 61, "KNOWN_CHARS = ",
     "코퍼스 고유", "미유도 (수기)",
     "🔴 **`UBIQUITOUS`와 같은 종류의 두 번째 자리다** — `{\"지우\", \"서준\"}`. "
     "🆕 `memory.py`의 `_fixed_word` 근처가 «평가용 하드코딩 2원소 집합이지 런타임 "
     "명부가 아니다»라고 붙여 둔 이름표를 **이 파일에도** 붙였다. 유도는 절 1-b가 "
     "실제로 시도했고 **구간이 좁아 «맞춘 것»에 가깝다** — 그래서 미유도로 남긴다"),
]

# ══════════════════════════════════════════════════════════════════════════
# 0-b. 🆕 유도 이력 · 이름표 · 갈림 — **닫힌 것 셋의 대조** (마감 레인)
# ══════════════════════════════════════════════════════════════════════════
#
# 🔴 세 대조 전부 **동결 함수가 읽지 않는 자리**에서 돈다. `stale_ubiquitous`가
#   `scoring.py`의 동결 경계 밖에 사는 것과 같은 이유다 — 대조가 경계 안으로
#   들어오면 대조를 손볼 때마다 얼린 것이 움직인다.

# ② `KNOWN_CHARS`가 «같은 기저 · 같은 규칙»으로 유도되는가. 답은 **반쯤**이고
#    그 «반쯤»을 수로 적는 것이 이 상수의 이름표다.
KNOWN_CHARS_PROVENANCE = {
    "basis": "대장-22 — `UBIQUITOUS`와 **같은 기저**",
    "rule": "문서빈도 DF >= tau — `UBIQUITOUS`와 **같은 규칙**",
    "derived": ("서준", "지우"),
    "band": (3 / 22, 5 / 22),       # (13.6%, 22.7%] — 폭 9.1%p
    # 🔴 비교값. `UBIQUITOUS`의 구간은 (5/22, 12/22] = 폭 31.8%p — **세 배 넓다.**
    "compare_to_ubiquitous_band": (5 / 22, 12 / 22),
    "verdict": "미유도 — 구간이 좁고 바로 아래 눈금에서 `나비`가 들어온다",
}

# ③ 조사 표 두 벌의 **오늘의 갈림**. 정본 검사는
#    `prototype/tests/test_tokens.py`의 `TestTheTwoParticleTablesDoNotDriftFurther`이고,
#    여기서는 그 차집합을 **다시 뽑아 찍기만** 한다 (사본이 아니라 표시 · F12).
PARTICLE_TABLES = (("_PART", "prototype/memory.py", 337),
                   ("_PARTICLE", "prototype/memory.py", 776))


def particle_alts(pat):
    """정규식 `(a|b|c)$`의 대안 집합. **정렬해서** 다룬다 (`repr(set)`은 seed의 함수다)."""
    body = pat.pattern
    body = body[body.index("(") + 1:body.rindex(")")]
    return frozenset(a for a in body.split("|") if a)


def verify_anchors(rows):
    """각 상수의 `file:line`이 실제로 그 자리인가. **틀린 줄은 목록으로 돌려준다.**

    🔴 이 함수가 있는 이유는 G18이다 — 새로 적는 `file:line`은 감사로 확인한 것만
    보고한다. 표를 손으로 적으면 다음 편집에서 조용히 밀린다.
    """
    bad = []
    cache = {}
    for name, path, line, needle, *_ in rows:
        full = os.path.join(ROOT, path)
        if path not in cache:
            with open(full, encoding="utf-8") as f:
                cache[path] = f.read().splitlines()
        lines = cache[path]
        got = lines[line - 1] if 0 < line <= len(lines) else "<범위 밖>"
        if needle not in got:
            bad.append((name, path, line, needle, got.strip()[:60]))
    return bad


# ══════════════════════════════════════════════════════════════════════════
# 1. sha256 고정물의 구멍 — 상수만 갈면 통과하는가
# ══════════════════════════════════════════════════════════════════════════

# 🔴 프로브 문자열을 **여기 옮겨 적지 않는다** — `test_scoring.py:30`이 정본이고,
#    사본을 두면 한 글자만 달라도 «같은 프로브»라는 말이 거짓이 된다 (F12).
import test_scoring                                          # noqa: E402
PROBE = test_scoring.PROBE


def src_sha(name):
    return hashlib.sha256(
        inspect.getsource(getattr(scoring, name)).encode("utf-8")).hexdigest()


@contextlib.contextmanager
def swapped(**kw):
    """`scoring`의 모듈 전역을 잠깐 갈아 끼운다. **`finally`로 되돌린다** (G13)."""
    old = {k: getattr(scoring, k) for k in kw}
    try:
        for k, v in kw.items():
            setattr(scoring, k, v)
        yield
    finally:
        for k, v in old.items():
            setattr(scoring, k, v)


def hole_probe(global_name, new_value, probe, items):
    """
    **하나의 모듈 전역**을 갈고 «해시가 움직이나 / 동작이 움직이나»를 함께 본다.

    돌려주는 것: `(해시_움직임, 동작_움직임, 전, 후)`.
    구멍은 **`(False, True)`** — 해시는 가만있는데 동작이 바뀌는 자리다.
    """
    before_h = (src_sha("survived_frozen"), src_sha("survived_v2"))
    before_b = tuple(scoring.survived_v2(probe, items).survived)
    with swapped(**{global_name: new_value}):
        after_h = (src_sha("survived_frozen"), src_sha("survived_v2"))
        after_b = tuple(scoring.survived_v2(probe, items).survived)
    return before_h != after_h, before_b != after_b, before_b, after_b


def frozen_test_verdict():
    """`test_scoring.py`의 고정물 시험을 **상수를 간 채로** 실제로 돌린다.

    돌려주는 것: `(해시시험_초록, 행동시험_초록)`. 심은 위반의 발화 확인은
    «해시가 초록인데 행동이 빨갛다»여야 한다 — 그것이 구멍의 정의다.
    """
    import unittest
    import test_scoring

    def run(cls, meth):
        r = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(
            unittest.TestSuite([cls(meth)]))
        return r.wasSuccessful()

    with swapped(UBIQUITOUS=set()):
        h = run(test_scoring.TestFrozenScorersAreFrozen, "test_source_hashes")
        b = run(test_scoring.TestScoring, "test_v2_drops_all_three")
    return h, b


# ══════════════════════════════════════════════════════════════════════════
# 2. 유도 — «편재 어근»을 코퍼스에서 빈도로 계산한다
# ══════════════════════════════════════════════════════════════════════════
#
# 🔴 **기저가 답을 정한다.** «편재»는 «문서의 몇 %에 나오나»인데, 그 «문서»가
#    무엇인지가 정해져 있지 않다. 채점기는 두 텍스트를 본다 — **항목**(대장)과
#    **본문**(요약). 그래서 기저를 다섯 개 다 재고 나란히 찍는다.


def bases():
    """`{기저 이름: (문서 리스트, 설명)}`. 전부 `eval/`·체크포인트를 **읽기만** 한다."""
    with open(os.path.join(ROOT, "eval", "fact-ledger.yaml"), encoding="utf-8") as f:
        led = yaml.safe_load(f)
    with open(os.path.join(ROOT, "eval", "corpus", "corpus.jsonl"),
              encoding="utf-8") as f:
        corpus = [json.loads(l) for l in f]
    import summary_local
    _, items11 = summary_local.load()
    with open(os.path.join(HERE, "data", "SUMMARY_S2.json"), encoding="utf-8") as f:
        sums = json.load(f)["summaries"]

    by = {}
    for r in corpus:
        by.setdefault(r["session"], []).append(r["text"])
    all22 = [f["text"] for f in led["facts"]] + [e["text"] for e in led["events"]]
    return {
        "대장-22 (facts 12 + events 10)": (all22, "채점기의 **항목** 쪽 전량"),
        "대장-11 (S01–S12 혼합)": (items11,
                                 "`scoring.py:47-48` 주석이 «11개 중 10개»라 쓴 그 기저"),
        "요약-24 (SUMMARY_S2)": (list(sums.values()),
                                "채점기의 **본문** 쪽 — `_clean_roots`가 실제로 읽는다"),
        "코퍼스-세션-24": ([" ".join(v) for v in by.values()], "원본 턴을 세션으로 묶은 것"),
        "코퍼스-턴-720": ([r["text"] for r in corpus], "원본 턴 하나가 문서 하나"),
    }


# 🔄 🔴 **유도 규칙의 지역 사본을 지웠다** (F12 · 사본 금지 — 이 레인이 ③에서 고발한
#   바로 그 형태였다). `doc_freq`·`derive`·`stable_band`는 이제 `scoring.py`가
#   **한 벌만** 든다. 사본이 둘이면 «유도값이 현행값과 같다»가 **어느 규칙에 대한
#   말인지** 알 수 없어지고, 그게 실험 30이 상수에 대해 말한 것과 같은 병이다.
from scoring import (doc_freq, stable_band,                  # noqa: E402,F401
                     derive_ubiquitous, ledger_docs, stale_ubiquitous)


def derive(docs, tau):
    """`derive_ubiquitous`의 **집합 뷰**. 규칙은 여기 없다 — 정본은 `scoring.py`다.

    ⚠️ 이 파일의 표시 코드가 집합 연산(`<=` 등)을 쓰므로 형만 바꿔 준다.
       `frozenset`으로 감싸도 **찍을 때는 반드시 `sorted()`** 를 거친다.
    """
    return frozenset(derive_ubiquitous(docs, tau))


# ══════════════════════════════════════════════════════════════════════════
# 3. 갈아 끼우기 — 기존 값이 얼마나 움직이는가
# ══════════════════════════════════════════════════════════════════════════


class _Buf(io.StringIO):
    """`sys.stdout.reconfigure`를 부르는 실험 스크립트를 삼키기 위한 최소 보강."""

    def reconfigure(self, **kw):
        return None


def run_script(rel):
    """실험 스크립트를 **같은 프로세스에서** 돌리고 stdout을 문자열로 받는다.

    🔴 `runpy`를 쓰는 이유: `scoring`이 이미 `sys.modules`에 있으므로 스크립트의
       `from scoring import …`가 **갈아 끼운 모듈**을 집는다. 하위 프로세스로
       돌리면 그 배선이 끊긴다.
    ⚠️ 이 셋은 전부 체크포인트를 읽어 **생성 0건**으로 돈다 — 확인은 절 3 머리말에.
    """
    path = os.path.join(ROOT, rel)
    buf, old_argv, old_out = _Buf(), sys.argv, sys.stdout
    sys.argv = [path]
    code = 0
    try:
        with contextlib.redirect_stdout(buf):
            try:
                runpy.run_path(path, run_name="__main__")
            except SystemExit as e:
                code = e.code or 0
    finally:
        sys.argv, sys.stdout = old_argv, old_out
    return buf.getvalue(), code


def exp19_rows():
    """실험 19(`drift_probe.py`)의 표를 **캐시된 생성물에서** 다시 채점한다.

    🔴 API를 부르지 않는다 — `DRIFT_RESULTS.json`의 28개 태그가 전부 있어서
       `drift_probe.gen()`이 한 번도 네트워크를 타지 않는 상태와 같은 입력이다.
       태그 이름과 조립 순서는 `drift_probe.py:107-124,180-186`을 따른다.
    """
    with open(os.path.join(HERE, "data", "DRIFT_RESULTS.json"), encoding="utf-8") as f:
        ck = json.load(f)
    import summary_local
    sess, items = summary_local.load()          # n_sess=12 · 같은 구간·같은 항목
    sd = [ck[f"s:{k}"] for k, _ in sess]
    allsd = "\n".join(f"[{k}] {d}" for (k, _), d in zip(sess, sd))
    with open(os.path.join(ROOT, "eval", "corpus", "corpus.jsonl"),
              encoding="utf-8") as f:
        corpus = [json.loads(l) for l in f]
    span = {k for k, _ in sess}
    raw = " ".join(r["text"] for r in corpus if r["session"] in span)
    rows = [("원본 턴", raw), ("세션 요약", " ".join(sd)),
            ("lifetime — P4 (깊이2)", ck["p4"]),
            ("lifetime — P2 (증분)", ck["p2:11"])]
    rows += [(f"예산 · {lbl}", ck[f"b:{lbl}"])
             for lbl in ("5문장 (원래)", "15문장", "사실 우선 15문장")]
    return rows, items


def exp20_rows():
    """실험 20(`summary_local.py`)의 **6방식 + 세션요약** 행을 캐시에서 재조립한다.

    🔴 태그 이름·조립 순서는 `summary_local.py:121-163`을 따른다. 그 파일이
       바뀌면 여기가 조용히 달라지므로, 아래 `main`이 **`summary_local`을 실제로
       돌린 출력의 frozen 값과 대조**해 어긋나면 종료 1로 잡는다.
    """
    import summary_local as S
    with open(S.CK, encoding="utf-8") as f:
        ck = json.load(f)
    sess, items = S.load()
    P = "qwen3:8b:"
    sd = [ck[f"{P}s:{k}"] for k, _ in sess]
    allsd = "\n".join(f"[{k}] {d}" for (k, _), d in zip(sess, sd))
    rows = [("세션 요약 (전체 합침)", allsd),
            ("2층 · 기본 지시", ck[f"{P}a:base"]),
            ("2층 · 사실 우선", ck[f"{P}a:ff"]),
            ("2층 · 밀도 올리기 1회", ck[f"{P}a:cod1"]),
            ("2층 · 밀도 올리기 2회", ck[f"{P}a:cod2"]),
            ("3층 · 세션→구간→전체", ck[f"{P}b:l3"]),
            (f"증분 · 깊이가 {len(sd)}까지 자람", ck[f"{P}b:inc{len(sd)-1}"])]
    return rows, items


def score3(text, items):
    """`(frozen, v2, v3, 판정불가)` — 세 채점기를 **한 번에** 찍는다."""
    v2 = scoring.survived_v2(text, items)
    v3 = scoring.survived_v3(text, items)
    return (len(scoring.survived_frozen(text, items)),
            len(v2.survived), len(v3.survived), len(v2.unscorable))


def grab(out, header, labels):
    """캡처한 stdout에서 «머리말 뒤 첫 라벨 줄»의 수를 뽑는다.

    라벨을 못 찾으면 `None`을 넣는다 — 조용히 0으로 세면 그것이 F21이다.
    """
    lines = out.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if header in l)
    except StopIteration:
        return {l: None for l in labels}
    got = {}
    for lab in labels:
        got[lab] = next((l.strip() for l in lines[start:start + 40]
                         if l.strip().startswith(lab)), None)
    return got


# ══════════════════════════════════════════════════════════════════════════
# 4. `len(w) < 2`가 버리는 것
# ══════════════════════════════════════════════════════════════════════════
#
# 🔴 **의미 있음의 근거는 이 저장소의 실측이다.** `첫`·`두`·`세`는 서수 라운드가
#    «회차 위양성 셋»을 만든 원인으로 이름 붙인 글자들이고(`scoring.py:111-117`),
#    그 셋은 `_roots`가 **토큰 단계에서** 버려서 `_clean_roots`가 본 적도 없다.
#
# 🔴 **판정을 셋으로 가른다.** «의미 있다/없다» 이분법으로 적으면 근거가 안 보인다.
#   서수·분류사   수를 나른다. 이 저장소가 **실측으로** 대가를 확인한 부류다
#   내용어        명사·대명사. 검색 신호가 될 수 있는데 토큰 단계에서 사라진다
#   글머리        마크다운 목록 번호. **버리는 편이 옳다** — `_ordinal_heads`도 뺀다
#   기능어·조각   부사·감탄사·용언 조각. 버리는 편이 옳다
ORD, CONT, BULLET, FUNC = "서수·분류사", "내용어", "글머리", "기능어·조각"
SINGLE_CHAR_CLASS = {
    "첫": (ORD, "실험 26의 위양성 `P12`(E004×S16)를 만든 글자"),
    "두": (ORD, "위양성 `P14`(E005×S18)"),
    "세": (ORD, "위양성 `P15`(E006×S16) · `survived_v3`이 원문을 다시 읽는 이유"),
    "한": (ORD, "수관형사 — 대장 항목 «여동생이 **한** 명»"),
    "명": (ORD, "분류사 — 위와 짝"),
    "개": (ORD, "분류사"),
    "권": (ORD, "분류사 — «책 두 **권**»"),
    "차": (ORD, "«세 **차**례»의 조각"),
    "반": (ORD, "수량 — «**반** 개»·«**반**차»"),
    "나": (CONT, "1인칭 대명사 — 코퍼스 턴 40개에 있다"),
    "너": (CONT, "2인칭 대명사"),
    "옷": (CONT, "명사 — 코퍼스 20턴"),
    "밥": (CONT, "명사 — 코퍼스 16턴"),
    "책": (CONT, "명사 — 코퍼스 11턴"),
    "비": (CONT, "명사(날씨) — 코퍼스 10턴"),
    "집": (CONT, "명사"),
    "몸": (CONT, "명사"),
    "감": (CONT, "명사(감기의 조각/독립 명사) — 요약 쪽 고빈도 어근과 같은 글자"),
    "일": (CONT, "명사"),
    "1": (BULLET, "요약의 마크다운 목록 번호 전용(코퍼스 0턴) — 버리는 것이 옳다"),
    "2": (BULLET, "위와 같다"),
    "3": (BULLET, "위와 같다"),
}


def classify_single(tok):
    return SINGLE_CHAR_CLASS.get(tok, (FUNC, ""))


def dropped_single_chars(docs):
    """`_roots`의 `len(w) < 2`가 버리는 1글자 토큰. `{토큰: 등장 문서 수}`.

    🔴 `Memory._roots`의 전처리(`re.sub(r"[^\\w가-힣]", "", w)`)를 **같은 철자로**
       재현한다. 다르게 적으면 «버려지는 것»의 정의가 둘이 된다.
    """
    import re
    df = collections.Counter()
    empt = collections.Counter()
    for t in docs:
        seen, seen_e = set(), set()
        for w in t.split():
            w = re.sub(r"[^\w가-힣]", "", w)
            if len(w) == 1:
                seen.add(w)
            elif len(w) == 0:
                seen_e.add("<구두점만>")
        df.update(seen)
        empt.update(seen_e)
    return df, empt


# ══════════════════════════════════════════════════════════════════════════
# 본문
# ══════════════════════════════════════════════════════════════════════════

def hr(c="─"):
    print("  " + c * (W - 4))


def main():
    fail = []
    import summary_local
    _, ITEMS11 = summary_local.load()

    print("=" * W)
    print("박힌 상수 감사 — 코퍼스 고유인가, 유도할 수 있는가, 갈면 무엇이 움직이는가")
    print("=" * W)

    # ── 절 0 ────────────────────────────────────────────────────────────
    print("\n0. 🔴 sha256 고정물의 구멍 — **상수를 갈면 통과하는가** (심어서 확인)")
    hr()
    print("   `TestFrozenScorersAreFrozen`은 **함수 원문**을 못 박는다.")
    print("   `UBIQUITOUS`는 **모듈 전역**이라 그 원문 밖에 있다.\n")
    print(f"   {'심은 것':<34}{'해시 움직임':>12}{'동작 움직임':>12}   판정")
    hr("·")
    probes = [("UBIQUITOUS = set()  (v2가 읽는다)", "UBIQUITOUS", set()),
              ("UBIQUITOUS = {지우, 서준}", "UBIQUITOUS", frozenset({"지우", "서준"})),
              ("_ORDINALS = set()   (v2는 안 읽는다)", "_ORDINALS", frozenset())]
    hole_rows = []
    for label, g, v in probes:
        mh, mb, b0, b1 = hole_probe(g, v, PROBE, ITEMS11)
        verdict = ("🔴 **구멍**" if (not mh and mb) else
                   "✅ 조용 (동작도 안 변함)" if not mb else "해시가 잡는다")
        hole_rows.append((label, mh, mb, b0, b1))
        print(f"   {label:<34}{'예' if mh else '아니오':>12}"
              f"{'예' if mb else '아니오':>12}   {verdict}")
    hr("·")
    print(f"   프로브: {PROBE}")
    print(f"   `UBIQUITOUS = set()` 뒤 v2 생존 {len(hole_rows[0][4])}건 "
          f"(전 {len(hole_rows[0][3])}건):")
    for it in hole_rows[0][4]:
        print(f"     · {it}")
    print("   → **이 셋이 `scoring.py:17-22`가 «v2가 잡는다»고 적은 위양성 그대로다.**")

    ok_hash, ok_behav = frozen_test_verdict()
    print(f"\n   실제 시험을 상수를 간 채로 돌린 결과:")
    print(f"     `TestFrozenScorersAreFrozen.test_source_hashes` → "
          f"{'🟢 초록 (통과)' if ok_hash else '🔴 빨강'}")
    print(f"     `TestScoring.test_v2_drops_all_three`          → "
          f"{'🟢 초록' if ok_behav else '🔴 빨강 (실패)'}")
    if not (ok_hash and not ok_behav):
        fail.append("구멍 심기가 발화하지 않았다 — 해시 초록 + 행동 빨강이어야 한다")
    else:
        print("   ✅ **심은 위반이 발화했다** — 「얼렸다」는 절반만 참이다:")
        print("      함수 원문은 얼었고, **그 함수가 읽는 상수는 안 얼었다.**")
    # 되돌아왔는가 — 조용한 쪽 대조
    print(f"   되돌림 확인: UBIQUITOUS = {sorted(scoring.UBIQUITOUS)} · "
          f"v2 생존 {len(scoring.survived_v2(PROBE, ITEMS11).survived)}건 (0이어야 한다)")
    if scoring.survived_v2(PROBE, ITEMS11).survived:
        fail.append("갈아 끼운 것이 되돌아오지 않았다")

    # ── 절 1 ────────────────────────────────────────────────────────────
    print(f"\n1. 박힌 상수 전수 — {len(CONSTANTS)}개")
    hr()
    bad = verify_anchors(CONSTANTS)
    if bad:
        fail.append(f"앵커 불일치 {len(bad)}건")
        for row in bad:
            print(f"   🔴 앵커 어긋남: {row}")
    else:
        print(f"   ✅ `file:line` 앵커 {len(CONSTANTS)}개를 파일에서 **읽어** 확인했다 (G18)\n")
    counts = collections.Counter(r[4] for r in CONSTANTS)
    for kind in ("코퍼스 고유", "언어 고유", "도메인 무관"):
        print(f"   ── {kind} ({counts[kind]}개) " + "─" * (W - 24 - len(kind)))
        for name, path, line, _, k, derived, why in CONSTANTS:
            if k != kind:
                continue
            print(f"     {name}")
            print(f"       자리   {path}:{line}")
            print(f"       유도   {derived}")
            print(f"       근거   {why}")
    print(f"\n   합계: 코퍼스 고유 {counts['코퍼스 고유']} · "
          f"언어 고유 {counts['언어 고유']} · 도메인 무관 {counts['도메인 무관']}")
    nd = sum(1 for r in CONSTANTS if r[5].startswith("미유도") or "미유도" in r[5])
    print(f"   그중 **미유도** {nd}개 — 분류와 유도는 다른 축이다"
          f" (도메인 무관인데 미유도인 것도, 코퍼스 고유인데 유도된 것도 있다)")
    print(f"   🔄 실험 30은 여기를 **24개**라 적었다. `UBIQUITOUS`가 유도 이력을"
          f" 갖게 되어 {nd}개다 — 상수 총수 {len(CONSTANTS)}개는 안 변했다.")

    # ── 절 1-b ─────────────────────────────────────────────────────────
    print("\n1-b. 🆕 ② `KNOWN_CHARS` — 이름표를 붙이고, 유도를 **실제로 시도했다**")
    hr()
    import guard_sim
    K = KNOWN_CHARS_PROVENANCE
    LEDGER0, SIG0 = ledger_docs(ROOT)
    print(f"   현행값        {sorted(guard_sim.KNOWN_CHARS)}"
          f"   (`experiments/guard_sim.py`)")
    print(f"   기저          {K['basis']} · 문서 {len(LEDGER0)}개 · 서명 {SIG0}")
    print(f"   규칙          {K['rule']}")
    got_k = derive_ubiquitous(LEDGER0, (K['band'][0] + K['band'][1]) / 2)
    band_k = stable_band(LEDGER0, K["derived"])
    print(f"   유도값        {list(got_k)}")
    print(f"   구간          ({band_k[0]*100:.1f}%, {band_k[1]*100:.1f}%] — 폭 "
          f"**{(band_k[1]-band_k[0])*100:.1f}%p**   (분모 {len(LEDGER0)}문서)")
    ub = scoring.UBIQUITOUS_PROVENANCE["band"]
    print(f"   비교          `UBIQUITOUS`의 구간은 ({ub[0]*100:.1f}%, {ub[1]*100:.1f}%]"
          f" — 폭 **{(ub[1]-ub[0])*100:.1f}%p**")
    below = sorted(derive_ubiquitous(LEDGER0, band_k[0]))
    print(f"   구간 바로 아래 눈금(DF ≥ {band_k[0]*100:.1f}%)에서 딸려 오는 것: "
          f"|{len(below)}종| {' '.join(below)}")
    print(f"   → **판정: {K['verdict']}.**")
    print("     🔴 «고양이가 인물인가»는 이 기저가 답하지 않는다 — 코퍼스 밖 판단이다.")
    print("     구간이 좁으면 유도가 아니라 **맞춘 것**이고, 그래서 미유도로 남긴다.")
    # 이름표가 두 파일에 다 붙었는가 — «다른 파일의 같은 형태»가 이 항목의 전부였다
    lbl = "평가용 하드코딩 2원소 집합"
    with open(os.path.join(ROOT, "prototype", "memory.py"), encoding="utf-8") as f:
        in_mem = lbl in f.read()
    with open(os.path.join(HERE, "guard_sim.py"), encoding="utf-8") as f:
        in_guard = lbl in f.read()
    print(f"   이름표 «{lbl}» — memory.py {'있다' if in_mem else '🔴 없다'}"
          f" · guard_sim.py {'있다' if in_guard else '🔴 없다'}")
    if not (in_mem and in_guard):
        fail.append("«평가용 하드코딩 2원소 집합» 이름표가 두 파일에 다 붙지 않았다")
    if tuple(got_k) != tuple(K["derived"]) or tuple(sorted(guard_sim.KNOWN_CHARS)) != tuple(K["derived"]):
        fail.append(f"KNOWN_CHARS 유도 이력이 어긋났다: {got_k} vs {K['derived']}")

    # ── 절 1-c ─────────────────────────────────────────────────────────
    print("\n1-c. 🆕 ③ 조사 표 두 벌 — **갈림을 기계로 다시 뽑는다**")
    hr()
    import memory as _M
    pa, pl = particle_alts(_M._PART), particle_alts(Memory._PARTICLE)
    print(f"   `_PART`     ({PARTICLE_TABLES[0][1]}:{PARTICLE_TABLES[0][2]})"
          f"  {len(pa):2d}종")
    print(f"   `_PARTICLE` ({PARTICLE_TABLES[1][1]}:{PARTICLE_TABLES[1][2]})"
          f"  {len(pl):2d}종")
    print(f"   `_PARTICLE`에만  {len(pl-pa):2d}종  {' '.join(sorted(pl - pa))}")
    print(f"   `_PART`에만      {len(pa-pl):2d}종  {' '.join(sorted(pa - pl)) or '— (없다)'}")
    print(f"   포함 방향: `_PART` ⊂ `_PARTICLE` = **{pa < pl}**")
    print("   🔴 **합치지 않았다.** 동작은 한 칸도 안 움직이지만(실험 30 §J의 표),")
    print("      넓은 쪽 `_PARTICLE`이 **동결 경계 안**이고 닫힌 해시가 얼리는 것은")
    print("      «정규식이 받아들이는 언어»가 아니라 **패턴 문자열의 철자**다.")
    print("      갈림 감시는 `prototype/tests/test_tokens.py`의")
    print("      `TestTheTwoParticleTablesDoNotDriftFurther`가 한다 — «두 표가 같아야")
    print("      한다»가 아니라 «오늘의 갈림 밖으로 벌어지면 운다»로 걸었다.")

    # ── 절 2 ────────────────────────────────────────────────────────────
    print("\n2. `UBIQUITOUS` 유도 — 기준과 **그 기준이 만드는 집합 전체**")
    hr()
    B = bases()
    LADDER = (0.10, 0.20, 0.25, 1 / 3, 0.50, 0.75, 0.90)
    for bname, (docs, desc) in B.items():
        n = len(docs)
        df = doc_freq(docs)
        # 🔴 🔄 **순위를 동점 무관하게 센다.** 전에는 `Counter.most_common()`의
        #   자리를 순위로 썼는데, 그 동점 순서는 삽입 순서이고 `Memory._roots`가
        #   **집합**을 돌려주므로 삽입 순서가 `PYTHONHASHSEED`의 함수였다 —
        #   즉 **순위가 실행마다 갈렸다.** 실험 30의 표에 실린 `29/174`·`47/174`는
        #   그중 한 번의 뽑기다(같은 코드가 이 레인에서 `27`·`47`을 찍었다).
        #   그래서 «자리»가 아니라 **경쟁 순위**(자기보다 엄격히 큰 것의 수 + 1)로
        #   센다. 이 정의는 동점을 어떻게 늘어놓든 같은 수를 준다.
        pos = (sum(1 for c in df.values() if c > df["지우"]) + 1
               if "지우" in df else None)
        ties = sum(1 for c in df.values() if c == df.get("지우"))
        print(f"\n   ▸ 기저 «{bname}» · 문서 {n}개 · 어근 {len(df)}종")
        print(f"     {desc}")
        print(f"     `지우` 문서빈도 {df['지우']}/{n} = {df['지우']/n*100:.1f}%"
              f" · 빈도 **경쟁 순위 {pos}/{len(df)}종**"
              f"{'' if ties <= 1 else f' (같은 빈도 {ties}종 공동)'}")
        for tau in LADDER:
            s = sorted(derive(docs, tau))
            shown = " ".join(s) if len(s) <= 40 else " ".join(s[:40]) + f" … (외 {len(s)-40})"
            mark = "  ← **{지우}**" if s == ["지우"] else ""
            print(f"       DF ≥ {tau*100:5.1f}%  |{len(s):3d}종| {shown}{mark}")
        band = stable_band(docs, {"지우"})
        if band:
            print(f"     🟢 `{{지우}}`만 나오는 tau 구간: "
                  f"({band[0]*100:.1f}%, {band[1]*100:.1f}%] — 폭 "
                  f"{(band[1]-band[0])*100:.1f}%p")
        else:
            print("     🔴 **어떤 tau에서도 `{지우}`만 나오지 않는다.**")

    print("\n   ── 기준 하나를 고른다 " + "─" * (W - 26))
    LEDGER = B["대장-22 (facts 12 + events 10)"][0]
    CHOSEN_TAU = 0.50
    chosen = derive(LEDGER, CHOSEN_TAU)
    print(f"   **기저 «대장-22» · DF ≥ {CHOSEN_TAU*100:.0f}%** → {sorted(chosen)}")
    print("   고른 이유: 채점기가 «편재»를 문제 삼는 자리는 **항목 쪽 분모**다"
          " (`_clean_roots(it)`).")
    print("   느슨하게 하면 무엇이 딸려 오는가 — 바로 아래 눈금들:")
    dfl = doc_freq(LEDGER)
    for tau in (0.50, 0.25, 0.20, 0.15, 0.10):
        s = sorted(derive(LEDGER, tau))
        print(f"     DF ≥ {tau*100:5.1f}%  |{len(s):3d}종| {' '.join(s)}")
    # ── 🆕 ① 유도 이력이 **코드에 산다** ────────────────────────────────
    print("\n   ── 🆕 ① 그 기준을 **코드에 적었다** " + "─" * (W - 38))
    P = scoring.UBIQUITOUS_PROVENANCE
    print("   `scoring.UBIQUITOUS_PROVENANCE` — 위에서 방금 유도한 것이 값 **옆**에 산다.")
    print(f"     기저          {P['basis']}")
    print(f"     규칙          {P['rule']} · tau = {P['tau']}")
    print(f"     분모          n = {P['n']}문서 · 모집단 서명 {P['population_sig']}"
          f" (facts 행 수, events 행 수)")
    print(f"     구간          ({P['band'][0]*100:.1f}%, {P['band'][1]*100:.1f}%]"
          f" — 폭 **{(P['band'][1]-P['band'][0])*100:.1f}%p**")
    print(f"     유도값        {list(P['derived'])}"
          f"   현행값 {sorted(scoring.UBIQUITOUS)}")
    print("\n   🔴 **왜 값 안이 아니라 값 옆인가.** `THETA_BY_MODE`는 유도 이력을 값")
    print("      자체에 튜플로 넣는다. `UBIQUITOUS`는 그럴 수 없다 — `survived_v2`의")
    print("      **닫힌 해시 안**이라 값의 모양을 바꾸면 얼린 것이 움직인다.")
    print("      그래서 **동결 함수가 읽지 않는 별도 객체**로 옆에 두고, 대조는")
    print("      **별도 함수** `stale_ubiquitous()`가 한다 — `stale_theta`와 같은 분업이다.")
    notes = stale_ubiquitous()
    print(f"\n   `stale_ubiquitous()` → {len(notes)}건"
          f"{'  ✅ 이력이 지금 기저에서도 참이다' if not notes else ''}")
    for why, want, got in notes:
        print(f"     🔴 {why}: 기록 {want} · 지금 {got}")
    if notes:
        fail.append(f"유도 이력이 지금 기저와 어긋난다 ({len(notes)}건)")
    # 🔴 대조가 **발화할 수 있는가** — 심어서 본다. 구간의 안/밖을 다 걸었는지 여기서 갈린다.
    LD, LS = ledger_docs(ROOT)
    planted = [
        ("tau를 구간 밖(0.75)으로", dict(tau=0.75)),
        ("유도값을 {지우,서준}으로", dict(derived=("서준", "지우"))),
        ("구간을 넓혀 (0.0, 0.9]로", dict(band=(0.0, 0.9))),
        ("모집단 서명을 (12, 11)로", dict(population_sig=(12, 11))),
    ]
    print("\n   심은 위반 — 이 대조가 **발화할 수 있는가** (전부 런타임 · try/finally):")
    silent = stale_ubiquitous(LD, LS)
    print(f"     {'조용한 쪽 — 아무것도 안 건드린다':<36} {len(silent)}건"
          f"  {'✅ 조용' if not silent else '🔴 울었다'}")
    for label, kw in planted:
        bad = dict(P, **kw)
        with swapped(UBIQUITOUS_PROVENANCE=bad):
            n_ = len(scoring.stale_ubiquitous(LD, LS))
        print(f"     {label:<36} {n_}건  {'✅ 발화' if n_ else '🔴 **조용히 지나갔다**'}")
        if not n_:
            fail.append(f"유도 이력 대조가 «{label}»에 발화하지 못했다")
    print(f"     되돌림 확인: tau = {scoring.UBIQUITOUS_PROVENANCE['tau']} · "
          f"stale {len(stale_ubiquitous(LD, LS))}건 (0이어야 한다)")

    print("   → `지우`(12/22) 바로 아래는 `서준`(5/22) — **또 하나의 등장인물 이름**이다.")
    print("     그 다음 눈금(3/22)에서 `나비`(고양이 이름)·`회사`·`번째`·`면접`이 함께 들어온다.")
    print("     🔴 `번째`·`면접`은 **실험 26의 회차 위양성을 만든 바로 그 어근**이다 —")
    print("        편재 제외를 조금만 넓히면 `survived_v3`이 고친 신호를 다시 지운다.")

    # ── 절 3 ────────────────────────────────────────────────────────────
    print("\n3. 갈아 끼웠을 때 움직인 값 — 실험 19 · 20 · 26 · 27")
    hr()
    SETS = [
        ("현행 {지우}", frozenset({"지우"})),
        ("∅ (제외 없음)", frozenset()),
        ("대장-22 τ=.50 → {지우}", derive(LEDGER, 0.50)),
        ("대장-22 τ=.20 → {지우,서준}", derive(LEDGER, 0.20)),
        ("요약-24 τ=.50", derive(B["요약-24 (SUMMARY_S2)"][0], 0.50)),
        ("코퍼스-세션 τ=.50", derive(B["코퍼스-세션-24"][0], 0.50)),
    ]
    for label, s in SETS:
        show = sorted(s)
        print(f"   {label:<28} |{len(s):3d}종| "
              f"{' '.join(show) if len(show) <= 12 else ' '.join(show[:12]) + ' …'}")

    def swap_table(title, rows, items, note):
        """한 실험의 행들을 여섯 집합으로 다시 채점한다. `(움직인 칸 수, frozen 표)`."""
        print(f"\n   {title}")
        print(f"        {note}")
        head = ["현행", "∅", "대장.50", "대장.20", "요약.50", "코퍼스.50"]
        print(f"\n        {'행':<24}{'frozen':>8}   " +
              "".join(f"{h:>10}" for h in head) + "   ← v2 (생존/채점가능)")
        hr("·")
        moved, frozen_vals = 0, []
        for name, text in rows:
            cells, fs = [], set()
            for _, s in SETS:
                with swapped(UBIQUITOUS=s):
                    f_, v2_, v3_, un = score3(text, items)
                fs.add(f_)
                cells.append(f"{v2_}/{len(items)-un}")
            frozen_vals.append((name, sorted(fs)))
            moved += sum(1 for c in cells[1:] if c != cells[0])
            print(f"        {name:<24}{sorted(fs)[0]:>4}/{len(items)}   " +
                  "".join(f"{c:>10}" for c in cells))
        hr("·")
        multi = [n for n, f in frozen_vals if len(f) > 1]
        print(f"        frozen 열이 여섯 집합에서 **전부 같은** 행: "
              f"{len(rows)-len(multi)}/{len(rows)}"
              f"{'' if not multi else ' — 다른 행: ' + ', '.join(multi)}")
        print(f"        v2 칸이 «현행»과 다른 자리: **{moved}개** / "
              f"{len(rows)*(len(SETS)-1)}")
        return moved

    print("\n   3-a. 실험 19 — `drift_probe.py` (Gemini 캐시 28태그 · **호출 0회**)")
    rows19, items19 = exp19_rows()
    swap_table("실험 19 · 4단계 + 예산 3행 (대장 혼합 11)", rows19, items19,
               "🔴 **문서에 실린 표는 `survived_frozen`으로 찍힌다** "
               "(`drift_probe.py:66`) — 그 열은 `UBIQUITOUS`를 참조하지 않는다.")

    print("\n   3-b. 실험 20 — `summary_local.py` (ollama 캐시 32태그 · **호출 0회**)")
    rows20, items20 = exp20_rows()
    # 🔴 캐시 재조립이 실제 실행과 같은 표를 만드는가 — 아니면 아래 표는 딴것이다
    out20 = {}
    for label, s in SETS:
        with swapped(UBIQUITOUS=s):
            out20[label] = run_script("experiments/summary_local.py")
    base20, code20 = out20["현행 {지우}"]
    import re as _re
    live = _re.findall(r"(\d+)/11", base20)
    mine = []
    for name, text in rows20:
        mine.append(str(len(scoring.survived_frozen(text, items20))))
    if live[:len(mine)] != mine:
        fail.append(f"실험 20 캐시 재조립이 실제 실행과 다르다: {live[:len(mine)]} vs {mine}")
        print(f"        🔴 재조립 불일치 {live[:len(mine)]} vs {mine}")
    else:
        print(f"        ✅ 캐시 재조립이 실제 실행의 frozen 표를 재현한다: "
              f"{' '.join(mine)} (/11)")
    swap_table("실험 20 · 6방식 + 세션요약 행 (대장 혼합 11)", rows20, items20,
               "🔴 이 표도 `survived_frozen`이다 (`summary_local.py:90`).")
    print("\n        실제 실행 stdout이 여섯 집합에서 다른 줄:")
    for label in out20:
        o, c = out20[label]
        d = sum(1 for a, b in zip(base20.splitlines(), o.splitlines()) if a != b)
        d += abs(len(base20.splitlines()) - len(o.splitlines()))
        print(f"          {label:<28} **{d}줄** (종료 {c})")

    print("\n   3-c. 실험 26 — `scorer_eval.py` (임베딩 캐시 · 라이브 호출 0회)")
    print(f"        {'집합':<28}{'홀드아웃 v3':>16}{'홀드아웃 v2(기록)':>20}   종료")
    hr("·")
    for label, s in SETS:
        with swapped(UBIQUITOUS=s):
            o, c = run_script("experiments/scorer_eval.py")
        g = grab(o, "홀드아웃 (사전 등록", ["축자 단독 (v3)", "축자 v2 (기록)"])

        def pick(k, _g=g):
            v = _g[k]
            if v is None:
                return "없음"
            m = _re.search(r"(\d+/\d+ =\s*[\d.]+%)", v)
            return m.group(1).replace(" ", "") if m else "없음"
        print(f"        {label:<28}{pick('축자 단독 (v3)'):>16}"
              f"{pick('축자 v2 (기록)'):>20}{c:>7}")

    print("\n   3-d. 실험 27 — `summary_prototype.py` (`LIFETIME_S27.json` · 생성 0건)")
    print("        표 B «M2 사건(events 10 · S01–S24)» 행 «이 라운드 재료 상한»")
    print(f"        {'집합':<28}{'frozen':>8}{'v2':>7}{'v3':>7}{'종료':>6}"
          "   기준선 앵커 재계산 (기록: frozen 8/11 · v2 6/10)")
    hr("·")
    out27 = {}
    for label, s in SETS:
        with swapped(UBIQUITOUS=s):
            out27[label] = run_script("experiments/summary_prototype.py")
    base27 = out27["현행 {지우}"][0]
    for label in out27:
        o, c = out27[label]
        cell = grab(o, "표 B —", ["이 라운드 재료 상한"])["이 라운드 재료 상한"] or ""
        nums = (_re.findall(r"(\d+/\d+)", cell) + ["—"] * 3)[:3]
        anchor = next((l.strip() for l in o.splitlines() if "재계산 frozen" in l), "—")
        d = sum(1 for a, b in zip(base27.splitlines(), o.splitlines()) if a != b)
        d += abs(len(base27.splitlines()) - len(o.splitlines()))
        print(f"        {label:<28}{nums[0]:>8}{nums[1]:>7}{nums[2]:>7}{c:>6}"
              f"   {anchor[:52]}")
        diff1 = [(a, b) for a, b in zip(base27.splitlines(), o.splitlines())
                 if a != b]
        tail = ""
        if 0 < len(diff1) <= 3:
            # 🔴 한두 줄이 움직였을 때 «어느 줄인가»를 안 찍으면 그 수는 못 읽는다
            tail = "  ⟶ " + " | ".join(f"«{a.strip()[:34]}» → «{b.strip()[:34]}»"
                                       for a, b in diff1)
        print(f"        {'':<28}{'':>28}   (기준과 다른 줄 {d}개){tail}")

    # ── 절 4 ────────────────────────────────────────────────────────────
    print("\n4. `len(w) < 2`가 버리는 1글자 토큰 — 이 코퍼스 전량")
    hr()
    ALL = (B["코퍼스-턴-720"][0] + B["대장-22 (facts 12 + events 10)"][0]
           + B["요약-24 (SUMMARY_S2)"][0])
    df1, empt = dropped_single_chars(ALL)
    print(f"   모집단: 코퍼스 턴 720 + 대장 항목 22 + 세션 요약 24 = **{len(ALL)}문서**")
    print(f"   버려지는 1글자 토큰 **{len(df1)}종** "
          f"(등장 문서 수 합 {sum(df1.values())}회)")
    print(f"   구두점만 남아 빈 문자열이 되는 어절: {sum(empt.values())}회\n")
    print(f"   {'토큰':<6}{'문서':>6}  {'부류':<12} 근거")
    hr("·")
    per = collections.Counter()
    doc_per = collections.Counter()
    # 🔴 🔄 **동점을 토큰으로 깬다.** `df1`은 문서마다 **집합**을 세어 만든 Counter라
    #   `most_common()`의 동점 순서가 `PYTHONHASHSEED`의 함수였다 — 같은 표가
    #   실행마다 다른 줄 순서로 나온다. 부류별 합계는 안 변하지만, «전량»을
    #   문서에 옮겨 적는 순간 그 순서가 재현되지 않는다.
    for tok, c in sorted(df1.items(), key=lambda kv: (-kv[1], kv[0])):
        kind, why = classify_single(tok)
        per[kind] += 1
        doc_per[kind] += c
        print(f"   {tok:<6}{c:>6}  {kind:<12} {why or '—'}")
    hr("·")
    keep = per[ORD] + per[CONT]
    print(f"   부류별: " + " · ".join(
        f"{k} {per[k]}종/{doc_per[k]}회" for k in (ORD, CONT, BULLET, FUNC)))
    print(f"   → **{len(df1)}종 중 {keep}종**({doc_per[ORD]+doc_per[CONT]}회)이 "
          f"수 또는 내용을 나른다.")
    print(f"     나머지 {len(df1)-keep}종은 글머리({per[BULLET]})와 "
          f"기능어·조각({per[FUNC]})이라 **버리는 편이 옳다** —")
    print("     즉 `len(w) < 2`는 **틀린 규칙이 아니라 너무 굵은 규칙**이다.")
    print(f"   🔴 그리고 대가가 서수 셋보다 크다: 내용어 {per[CONT]}종이 "
          f"토큰 단계에서 사라지므로")
    print("      `_clean_roots`에서 길이 조건을 풀어도 **돌아오지 않는다** "
          "(`scoring.py:113-117`).")
    if not {"첫", "두", "세"} <= set(df1):
        fail.append("서수 `첫`·`두`·`세`가 «버려지는 것» 목록에 없다 — 계산이 틀렸다")
    else:
        print("   ✅ 심어 둔 확인: `첫`·`두`·`세`가 실제로 이 목록에 있다"
              " — `_clean_roots`가 그 글자들을 **본 적이 없다**는 뜻이다"
              " (`scoring.py:113-117`)")

    # ── 절 5 ────────────────────────────────────────────────────────────
    print("\n5. 이 레인이 말할 수 없는 것")
    hr()
    print("   · **코퍼스가 하나다.** 위의 «유도된다»는 전부 «**이 코퍼스에서** 유도된다»이고,")
    print("     다른 코퍼스에서 같은 tau가 같은 집합을 줄지는 **모른다.** 잴 자료가 없다.")
    print("   · **«박혀 있다 = 나쁘다»가 아니다.** 도메인 무관한 상수는 박아도 된다.")
    print("     이 절이 한 일은 가른 것뿐이고, 무엇을 고칠지는 이 레인의 판정이 아니다.")
    print("   · **요약 품질을 재지 않았다.** 움직인 것은 전부 «채점기의 판정»이지")
    print("     «요약이 좋아졌는가»가 아니다.")
    print("   · 절 3의 실험 19·20은 **캐시된 생성물**을 다시 채점한 것이다. 모델을")
    print("     다시 부르면 생성이 달라지고, 그때 이 표는 재현되지 않는다(실험 14).")

    print("\n" + "=" * W)
    if fail:
        for m in fail:
            print(f"🔴 {m}")
        print("=" * W)
        return 1
    print("✅ 앵커 · 심은 위반 발화 · 되돌림 — 전부 통과")
    print("=" * W)
    return 0


if __name__ == "__main__":
    sys.exit(main())
