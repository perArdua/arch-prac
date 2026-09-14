# -*- coding: utf-8 -*-
"""
label_pairs.py — 「이 사건이 이 요약에 담겼는가」 **사람 라벨 워크시트**를 만든다.

## 이 파일이 여는 것

`.omc/plans/ralplan-summary-layer.md:196`의 **결정 4 K**(`bge-m3` 기반 의역 허용
채점)는 *"라벨이 없고, 만들면 자기저작이며, θ가 G12를 부른다"*는 이유로 보류됐다.
이 레인은 그 셋 중 **첫 번째**만 연다 — 라벨이 붙을 **자리**를 만든다.

  · 라벨을 만드는 것은 이 파일이 아니다. **사람(사용자)이 손으로 붙인다.**
  · θ를 정하는 것도 이 파일이 아니다 (G12 — 아래 §θ).

## 🔴 사전 등록된 U4 방아쇠는 오늘 당겨지지 않았다 — **제품 결정으로 연다**

U4의 열리는 조건은 «**U1이 열리고**, 라벨 집합이 `eval/` 밖에서 n ≥ 20으로
생기는 순간»이다(계획서 §9 U4 · ADR-016 §미해결 U4). 그리고 U1의 조건은
«재료 밖 위양성 > 재료 안 생존»인데 **오늘 그 값은 1건 vs 3건이다** —
`digest_budget.py`의 3절이 매 실행 그것을 세 열로 찍는다.

즉 **U1이 안 열렸으므로 U4의 방아쇠도 안 당겨졌다.** 이 라운드가 K를 여는 것은
*"조건이 충족되어 자동으로"*가 아니라 **오케스트레이터의 제품 결정**이다.
🔴 **그 구분을 지우면 «사전 등록»이라는 말이 아무것도 뜻하지 않게 된다** — 조건을
적어두고 조건과 무관하게 열면서 «조건대로 열었다»고 적는 것이 이 저장소가
여러 번 센 실패 모드다. 그래서 이 사실은 **세 산출물 전부**에 적힌다:
`SUMMARY_S2.json`의 `meta.u4_trigger` · `LABEL_PAIRS.json`의 `preregistration` ·
`LABEL_WORKSHEET.md`의 머리말.

## 🔴 워크시트에 **어떤 수도 넣지 않는다** — 이 파일의 가장 중요한 제약

라벨 옆에 코사인 값을 찍으면 사람의 판단이 그 수에 **정박**하고, 그 라벨로 유도한
θ는 **순환**이 된다. *"임베딩이 높다고 한 것을 사람이 확인해 준" 라벨로 임베딩의
문턱을 정하는 것*은 측정이 아니라 되풀이다. 이 저장소는 **«공유된 결함을 통과한
독립 측정»**(F38)을 이미 겪었다 — 두 레인이 같은 도구를 두 번 쓰고 그 일치를
독립성의 증거로 읽었다.

→ **분리한다.**
     `LABEL_WORKSHEET.md`   사건 문장 · 요약 본문 · 빈 `담겼는가` 칸. **끝.**
     `LABEL_PAIRS.json`     쌍 id · 사건 id · 세션 id · **유사도** · 후보 종류

  그리고 **순서도 힌트다.** 자연 양성 후보가 앞에 몰리면 표의 위치가 곧 답이
  된다 — 그래서 쌍을 `SEED_PAIR`로 섞고, **섞은 뒤에** `P01…`을 붙인다.
  🔴 종류별로 먼저 id를 붙이면 **id 자체가 종류를 실어 나른다.**

## §θ — 이 레인은 θ를 정하지 않는다 (G12)

문턱은 다음 레인이 **돌아온 라벨**을 받아 «모집단 · n · 자르는 비율»과 함께
유도한다. 🔴 **여기서 θ를 추측해 적으면 그것을 읽은 사람의 라벨이 오염된다** —
그 순간 이 워크시트는 라벨 집합이 아니라 «내 추측에 대한 동의서»가 된다.
그래서 이 파일에는 문턱 후보값이 **한 개도 없다.**

## 자기저작에 대해 이 레인이 여전히 말할 수 없는 것

**쌍을 고른 것은 사람이 아니라 이 스크립트다.** 라벨은 자기저작이 아니지만
**모집단은 자기저작이다** — 경계 후보를 «임베딩이 가장 높다고 한 것»으로 고른
순간, 이 집합은 임베딩이 어려워하는 자리가 아니라 **임베딩이 자신 있어 하는
자리**에 치우친다. 실험 22 §H가 프로브 집합에 대해 선언한 것과 같은 구조이고,
같은 방식으로 **제거하지 못했으므로 출력에 찍는다**(`SELF_AUTHORSHIP`).

## 재현 (G11)

    PYTHONIOENCODING=utf-8 python -B experiments/label_pairs.py

첫 실행은 24세션 요약을 **생성**한다(ollama `qwen3:8b` 24회 · 수십 분).
두 번째부터는 `SUMMARY_S2.json`을 읽어 ollama 생성 0회로 끝난다.
ollama가 없으면 **종료 77(SKIP)** — «못 재는 것은 못 잰다고 적는다»(P3).
"""

import json
import os
import random
import re
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "prototype"))
sys.stdout.reconfigure(encoding="utf-8")

import yaml                                                  # noqa: E402
import embedding                                             # noqa: E402
import llm                                                   # noqa: E402
import memory                                                # noqa: E402
import soak                                                  # noqa: E402
import summarize                                             # noqa: E402
from memory import Memory                                    # noqa: E402

sys.path.insert(0, HERE)
from fsm_probe import session_bounds                         # noqa: E402

W = 78
CHAT = soak.CHAT

# ── 경로 ────────────────────────────────────────────────────────────────
CORPUS = os.path.join(ROOT, "eval", "corpus", "corpus.jsonl")
LEDGER = os.path.join(ROOT, "eval", "fact-ledger.yaml")
SUMMARY_S2 = os.path.join(HERE, "data", "SUMMARY_S2.json")
WORKSHEET = os.path.join(HERE, "data", "LABEL_WORKSHEET.md")
PAIRS_JSON = os.path.join(HERE, "data", "LABEL_PAIRS.json")

# 생성 캐시. `summarize.CACHE_PATH`에 꽂아 **크래시가 앞의 생성을 잃지 않게** 한다
# (`summarize.py` 머리말 §생성이 멈춘다 — 레인 M이 여덟 번 겪었다). 프로덕션에서
# 요약 캐시는 결함이지만 여기는 실험 경로이고, 캐시를 켜는 쪽이 명시적으로 켠다.
GEN_CACHE = os.path.join(HERE, "data", "SUMMARY_S2_CACHE.json")

# ── 사전 등록 상수 (G8) ─────────────────────────────────────────────────
#
# 🔴 **쌍 선택과 섞기의 씨앗. 결과를 보고 고르지 않았다.** 계획서가 다른 레인에
#    쓴 값과 같은 자리의 수다 — `20260908`은 생성(`llm.LLM_SEED`), `20260910`은
#    이 라운드의 날짜다. 씨앗을 바꾸면 모집단이 바뀌고, 그러면 G12가 요구하는
#    «모집단»의 기술이 거짓이 된다.
SEED_PAIR = 20260910

N_BOUNDARY = 10          # 경계 후보 — 사건 하나당 하나
N_FAR = 4                # 먼 대조

# 먼 대조를 뽑는 자리. 남은 쌍을 유사도로 세워 **하위 이 비율** 안에서 고른다.
# 🔴 «최하위 4개»가 아니라 «하위 25% 안에서 무작위»인 이유: 최하위는 결정적이라
#    씨앗이 아무 일도 안 하고, 그러면 «무작위»라고 적은 것이 거짓이 된다.
FAR_QUANTILE = 0.25

# 생성 결정성. `llm.py`의 전역과 **대조만** 하고 덮어쓰지 않는다 — 여기서
# 재바인딩하면 «저장소의 기본 설정으로 만든 요약»이 아니게 된다.
EXPECT_TEMPERATURE = 0
EXPECT_SEED = 20260908
EXPECT_NUM_CTX = 8192

# 🔴 **생존 확인으로 통과시키지 않는다.** ollama가 응답한다는 것과 «계획서가 못박은
#    그 모델»이라는 것은 다른 말이다. 기대값의 정본은 `LLM_CHECKPOINT.json`이고,
#    아래 상수는 그 파일이 없거나 깨졌을 때 쓰는 **사양의 사본**이다(계획서 · 레인
#    지시가 같은 값을 적었다).
EXPECT_DIGEST = "500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41"

SELF_AUTHORSHIP = """🔴 자기저작 편향 — 제거하지 못했고, 출력에 찍는다 (실험 22 §H의 형식)
  1. **라벨은 자기저작이 아니다** — 사람이 붙인다. 이 레인이 K를 여는 이유가 그것이다.
  2. 🔴 **그러나 모집단은 자기저작이다.** 경계 후보를 «임베딩이 가장 높다고 한 것»
     으로 골랐으므로, 이 집합은 임베딩이 **자신 있어 하는 자리**에 치우친다.
     임베딩이 낮게 보는데 사람은 «담겼다»고 할 자리(위음성)는 **자연 양성 후보에
     우연히 들어온 만큼만** 있다. 이 집합으로 잰 정밀도와 재현율은 비대칭이다.
  3. **사건 10개는 `eval/` 대장의 것**이고 그것을 쓴 사람과 이 코퍼스를 만든 사람이
     같다 — `eval/`은 읽기만 했지만(A8) 그 사실이 편향을 없애지는 않는다."""

# ── 워크시트 누출 검사 (①) ─────────────────────────────────────────────
#
# 🔴 **수용 기준의 grep과 같은 정규식이다.** 다른 것을 쓰면 «스크립트는 통과인데
#    수용은 실패»가 되고, 그때 사람은 스크립트를 믿는다.
#      grep -ciE "0\\.[0-9]{2}|유사도|cosine|score" experiments/data/LABEL_WORKSHEET.md
#    그리고 **그것보다 넓게** 잡는다 — 지시가 금지한 것은 수만이 아니라 «점수·순위·
#    후보 종류»이고, 그 셋은 한국어 낱말로도 샌다.
LEAK_PATTERNS = (
    (r"0\.[0-9]{2}", "소수점 둘째 자리 수 — 코사인 값의 모양이다"),
    (r"유사도", "유사도라는 낱말"),
    (r"cosine", "cosine"),
    (r"score", "score"),
    (r"점수", "점수"),
    (r"순위", "순위"),
    (r"코사인", "코사인"),
    (r"자연 양성|경계 후보|먼 대조", "후보 종류 이름"),
)
LEAK_RE = [(re.compile(p, re.I), why) for p, why in LEAK_PATTERNS]


# ── 0. 사전 조건 — 결정성과 다이제스트 ─────────────────────────────────

def determinism_check():
    """
    `llm.py`의 전역이 계획서가 못박은 셋과 같은가. **다르면 예외다.**

    🔴 여기서 `llm.LLM_SEED = 20260908`처럼 **덮어쓰지 않는다.** 덮어쓰면 이
       스크립트는 언제나 통과하고, 저장소 기본값이 바뀐 날 그 사실이 **아무
       데서도 안 보인다.** 검사는 «맞추는 것»이 아니라 «다르면 우는 것»이다.
    """
    got = (llm.LLM_TEMPERATURE, llm.LLM_SEED, llm.LLM_NUM_CTX)
    want = (EXPECT_TEMPERATURE, EXPECT_SEED, EXPECT_NUM_CTX)
    if got != want:
        raise RuntimeError(
            f"생성 결정성이 사양과 다르다 — (temp, seed, num_ctx) 현재 {got}"
            f" vs 사양 {want}. `prototype/llm.py`의 전역이 바뀌었다.")
    return dict(temperature=got[0], seed=got[1], num_ctx=got[2])


def expected_digest():
    """기대 다이제스트의 **정본은 `LLM_CHECKPOINT.json`**이다. 못 읽으면 사본."""
    try:
        with open(llm.CHECKPOINT_PATH, encoding="utf-8") as f:
            rec = json.load(f)
        d = rec.get("digest")
        return (d, "LLM_CHECKPOINT.json") if d else (EXPECT_DIGEST, "사양 사본")
    except (OSError, ValueError):
        return EXPECT_DIGEST, "사양 사본 (체크포인트를 못 읽었다)"


def digest_check():
    """
    ollama가 살아 있는가 **그리고** 그 모델이 기록의 그 모델인가.

    반환: `(info, want, source, ok)`. ollama가 없으면 `info["digest"]`가 `None`이고
    호출부가 **77(SKIP)**으로 끝낸다.

    🔴 **«생존 확인만으로 통과시키지 마라»** — `/api/version`이 200을 주는 것과
       `qwen3:8b`가 계획서의 그 빌드인 것은 다른 명제다. 모델 빌드가 바뀌면
       `temperature=0`·고정 seed여도 요약이 움직인다(`llm.py` §결정성).
    """
    info = llm.runtime_info()
    want, src = expected_digest()
    return info, want, src, (info.get("digest") == want)


# ── 1. 재료 — 24세션 요약을 **재생성**한다 ──────────────────────────────

def load_eval():
    """`eval/`은 **읽기만** 한다 (A8). 여는 손잡이가 여기 하나뿐인 이유다."""
    corpus = [json.loads(l) for l in open(CORPUS, encoding="utf-8")]
    with open(LEDGER, encoding="utf-8") as f:
        ledger = yaml.safe_load(f)
    return corpus, ledger


def build_db(corpus, ledger, tmpdir):
    """
    `%TEMP%`에 DB를 세우고 코퍼스를 넣는다.

    🔴 **`soak.build`를 안 쓴다.** 그 함수는 DB 경로를
       `{ROOT}` 아래에 잡는다 (`soak.py:170`) — 즉 저장소 안이다.
       이 레인은 `prototype/**`에 한 바이트도 쓰지 않는다. 대신 그 함수가 부르는
       둘(`seed`·`ingest`)을 **그대로** 부른다 — 시드와 ingest 규칙의 사본을
       만들지 않는 것이 요점이다(F12).
    """
    m = Memory(os.path.join(tmpdir, "label-pairs.db"))
    soak.seed(m)
    soak.ingest(m, corpus, ledger, timed=False)
    return m


def generate_summaries(corpus, ledger, meta):
    """
    24세션 요약을 `summarize.session_digest`로 만든다. 반환 `(sums, stats)`.

    🔴 **`session_digest`의 사본을 만들지 않는다** (F12). 세션 요약이 무엇인지는
       `prototype/summarize.py`가 정의하고, 이 파일은 **경계와 순서만** 준다.
       여기서 프롬프트를 다시 적으면 이 워크시트의 요약은 «저장소가 만드는
       요약»이 아니라 «이 스크립트가 만든 무언가»가 되고, 라벨은 그것에 붙는다.

    ⚠️ **정지한다.** 레인 M이 여덟 번 겪었고 `summarize._generate`가 재시도를
       세어 찍는다(`GEN_RETRIES`=3). 소진되면 **예외를 올린다** — 여기서
       잡아 빈 요약으로 넘어가면 «요약이 비었다»와 «요약을 못 만들었다»가
       구별되지 않는다. 정지 누계는 `summarize.STALL_COUNT`가 들고 있다.
    """
    bounds = session_bounds(corpus)
    sids = sorted(bounds)
    summarize.CACHE_PATH = GEN_CACHE       # 크래시가 앞의 생성을 잃지 않게

    tmpdir = tempfile.mkdtemp(prefix="label-pairs-")
    t0 = time.perf_counter()
    stall_before = summarize.STALL_COUNT
    out = []
    try:
        m = build_db(corpus, ledger, tmpdir)
        print(f"  DB: {tmpdir} (%TEMP%) · 코퍼스 {len(corpus)}턴 ·"
              f" 세션 {len(sids)}개")
        print(f"  N = `memory.DIGEST_KEEP_SESSIONS` = {memory.DIGEST_KEEP_SESSIONS}"
              f" — 24세션이 전부 남는다 (밀려나는 행 0)\n")
        for sid in sids:
            lo, hi = bounds[sid]
            # 🔴 **캐시 키에 다이제스트를 넣는다.** 안 넣으면 `load_summaries`가
            #    «다른 조건이니 다시 생성한다»고 판정해도 **캐시가 옛 모델의
            #    요약을 그대로 돌려준다** — 검사는 발화하고 결과는 안 바뀌는,
            #    이 저장소가 «발화할 수 없는 검사»와 쌍둥이로 세는 형태다.
            kind, content, dropped = summarize.session_digest(
                m, CHAT, sid, from_seq=lo, to_seq=hi,
                tag=f"{llm.LLM_MODEL}:{meta['digest'][:12]}:s2:{sid}")
            if dropped:
                # N=24에 24개를 넣으므로 **한 건도 안 밀려나는 것이 정상**이다.
                # 밀려났다면 상한이나 경계 계산이 내 기대와 다르다는 뜻이다.
                raise RuntimeError(
                    f"{sid}: N 상한에 밀려난 키가 있다 {dropped} —"
                    f" 24세션에 N={memory.DIGEST_KEEP_SESSIONS}면 0건이어야 한다.")
            out.append((sid, content))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    stats = dict(n=len(out), wall_s=round(time.perf_counter() - t0, 1),
                 stalls=summarize.STALL_COUNT - stall_before,
                 generator_version=summarize.GENERATOR_VERSION)
    write_summary_s2(out, meta, stats)
    return out, stats


def write_summary_s2(sums, meta, stats):
    rec = {
        "meta": dict(meta, **stats,
                     source="prototype/summarize.py::session_digest (사본 없음 — F12)",
                     corpus="eval/corpus/corpus.jsonl (읽기만 — A8)"),
        "summaries": {sid: text for sid, text in sums},
    }
    with open(SUMMARY_S2, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)


def load_summaries(meta):
    """
    `SUMMARY_S2.json`이 **이 조건에서 만들어진 것**이면 읽고, 아니면 `None`.

    🔴 파일이 있다는 것만으로 쓰지 않는다. 다이제스트·seed·num_ctx가 다르면
       그것은 **다른 조건의 요약**이고, 그 위에 붙인 라벨로 유도한 θ는 오늘의
       요약에 대해 아무 말도 하지 않는다.
    """
    try:
        with open(SUMMARY_S2, encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError):
        return None
    mt = rec.get("meta", {})
    keys = ("digest", "seed", "num_ctx", "temperature", "model")
    if any(mt.get(k) != meta.get(k) for k in keys):
        print("  ⚠️ 기존 `SUMMARY_S2.json`이 **다른 조건**에서 만들어졌다 —"
              " 다시 생성한다.")
        for k in keys:
            if mt.get(k) != meta.get(k):
                print(f"       {k}: 파일 {mt.get(k)} vs 지금 {meta.get(k)}")
        return None
    sums = list(rec["summaries"].items())
    if len(sums) != 24:
        print(f"  ⚠️ 기존 파일의 요약이 {len(sums)}건이다 (24 아님) — 다시 생성한다.")
        return None
    return sums, rec.get("meta", {})


# ── 2. 임베딩 유사도 — 🔴 워크시트에는 안 들어간다 ─────────────────────

def cosine(a, b):
    num = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return num / (na * nb) if na and nb else 0.0


def similarity_matrix(events, sums):
    """
    `{(사건 id, 세션 id): 코사인}`. `bge-m3`.

    ⚠️ `embed()`는 실패해도 **예외를 내지 않고 `None`**을 준다(`embedding.py`
       §실패는 예외가 아니라 `None`이다). 여기서는 강등할 대상이 없으므로
       `None`을 **77(SKIP)**로 올린다 — 어휘 유사도로 대신 고르면 그것은 이
       워크시트가 겨냥한 «임베딩이 위양성을 두는 자리»가 아니게 된다.
    """
    texts = [e["text"] for e in events] + [t for _, t in sums]
    vecs = embedding.embed(texts)
    if vecs is None:
        return None
    ev = {e["id"]: v for e, v in zip(events, vecs[:len(events)])}
    sv = {sid: v for (sid, _), v in zip(sums, vecs[len(events):])}
    return {(eid, sid): cosine(ev[eid], sv[sid]) for eid in ev for sid in sv}


# ── 3. 쌍 선택 — **사전 등록한 규칙** ──────────────────────────────────

PREREG = """사전 등록 — 쌍 선택 규칙 (실행 전에 정했고, 결과를 보고 고치지 않는다)
  모집단   대장 `events` 10개 × 24세션 요약 = 240쌍. `eval/`은 **읽기만** (A8)
  ① 자연 양성 후보 10   각 사건 × **그 사건의 `at.session`에 해당하는 요약**
                        🔴 «후보»는 **자리**이지 라벨이 아니다 — 담겼는지는 사람이 정한다
  ② 경계 후보     10    각 사건 × **자기 세션이 아닌 요약 중 코사인 최댓값**
                        🔴 **위양성이 사는 자리**이고 θ가 갈라야 하는 곳이다
                        (오늘 `E010`이 어근 겹침으로 통과한 그 자리 — digest_budget.py 3절 ②)
  ③ 먼 대조        4    남은 쌍을 코사인으로 세워 **하위 25% 안에서 무작위**
                        (`SEED_PAIR`=20260910) — θ가 아무것도 안 자르는 극단이
                        아님을 보이는 자리다
  중복    같은 (사건, 세션) 쌍은 **한 번만**. ①→②→③ 순으로 먼저 잡은 쪽이 이긴다
  합계    n = 10 + 10 + 4 = **24** (요구는 n ≥ 24)
  순서    `SEED_PAIR`로 **섞은 뒤** `P01…`을 붙인다 — 종류가 id에도 위치에도 안 실린다"""


def select_pairs(events, sums, sims):
    """
    위 `PREREG` 그대로. 반환은 **선택 순서**(섞기 전)의 리스트다.

    각 원소: `{pair_id(나중), event_id, session, kind, sim}`.
    """
    sids = [sid for sid, _ in sums]
    rng = random.Random(SEED_PAIR)
    picked, seen = [], set()

    def take(eid, sid, kind):
        if (eid, sid) in seen:      # 중복은 **조용히 버리지 않고** 세어 둔다
            return False
        seen.add((eid, sid))
        picked.append(dict(event_id=eid, session=sid, kind=kind,
                           sim=round(sims[(eid, sid)], 6)))
        return True

    # ① 자연 양성 후보 — 사건이 실제로 일어난 세션의 요약
    for e in events:
        own = (e.get("at") or {}).get("session")
        if own not in sids:
            raise RuntimeError(
                f"{e['id']}: `at.session`={own}이 요약 세션 {sids[0]}–{sids[-1]}"
                f" 밖이다. 자연 양성 후보의 자리가 없다.")
        take(e["id"], own, "natural_positive")

    # ② 경계 후보 — 자기 세션이 아닌 요약 중 최댓값.
    #    🔴 동률 tie-break를 세션 id로 못박는다. `max`의 «먼저 온 것»에 기대면
    #       dict 순서가 바뀌는 날 모집단이 조용히 달라진다.
    for e in events:
        own = (e.get("at") or {}).get("session")
        best = max((s for s in sids if s != own),
                   key=lambda s: (sims[(e["id"], s)], s))
        take(e["id"], best, "boundary")

    # ③ 먼 대조 — 남은 쌍의 **하위 FAR_QUANTILE** 안에서 무작위.
    rest = sorted(((sims[(e["id"], s)], e["id"], s)
                   for e in events for s in sids
                   if (e["id"], s) not in seen),
                  key=lambda t: (t[0], t[1], t[2]))
    cut = max(N_FAR, int(len(rest) * FAR_QUANTILE))
    for _, eid, sid in rng.sample(rest[:cut], N_FAR):
        take(eid, sid, "far_control")

    return picked


def shuffle_and_id(pairs):
    """
    섞고 **그 뒤에** `P01…`을 붙인다.

    🔴 순서가 곧 힌트다. 자연 양성 후보 10개가 앞에 몰린 표는 «앞은 Y, 뒤는 N»
       이라는 답을 표의 모양으로 말한다. 그리고 **id를 먼저 붙이면 섞어도
       소용이 없다** — `P01`이 언제나 자연 양성이면 id가 종류를 실어 나른다.
    """
    out = list(pairs)
    random.Random(SEED_PAIR).shuffle(out)
    for i, p in enumerate(out, 1):
        p["pair_id"] = f"P{i:02d}"
    return out


# ── 4. 가드 — ①누출 ②중복 ③n < 24 ─────────────────────────────────────

def worksheet_leaks(text):
    """
    워크시트 본문에서 **정박을 일으킬 수 있는 것**을 찾는다. 반환은 위반 목록.

    빈 목록이 통과다. 수용 기준의 grep과 같은 정규식을 포함하되 더 넓다
    (`LEAK_PATTERNS`의 주석이 그 이유를 갖는다).
    """
    bad = []
    for ln, line in enumerate(text.splitlines(), 1):
        for rx, why in LEAK_RE:
            mt = rx.search(line)
            if mt:
                bad.append((ln, why, mt.group(0), line.strip()[:60]))
    return bad


def duplicate_pairs(pairs):
    """같은 (사건, 세션)이 두 번 나오는가. 반환은 중복된 키 목록."""
    seen, dup = set(), []
    for p in pairs:
        k = (p["event_id"], p["session"])
        if k in seen:
            dup.append(k)
        seen.add(k)
    return dup


MIN_PAIRS = 24


def too_few(pairs):
    """n이 요구(≥24)에 못 미치는가. 반환은 사유 문자열 또는 `None`."""
    if len(pairs) < MIN_PAIRS:
        return f"쌍이 {len(pairs)}개다 — 요구는 n ≥ {MIN_PAIRS}"
    return None


def enforce(worksheet_text, pairs):
    """
    셋을 **쓰기 전에** 건다. 위반이 있으면 예외 — 파일을 안 남긴다.

    🔴 «검사하고 그래도 쓴다»는 검사가 아니다. 새는 워크시트가 디스크에 남으면
       그것을 사람이 읽고, 라벨은 이미 정박된 뒤다.
    """
    bad = []
    leaks = worksheet_leaks(worksheet_text)
    if leaks:
        bad.append("① 워크시트 누출: " + "; ".join(
            f"{ln}행 {why}(`{hit}`)" for ln, why, hit, _ in leaks[:5]))
    dup = duplicate_pairs(pairs)
    if dup:
        bad.append(f"② 중복 쌍: {dup}")
    few = too_few(pairs)
    if few:
        bad.append(f"③ {few}")
    if bad:
        raise AssertionError("워크시트 계약 위반 — 파일을 쓰지 않는다:\n  "
                             + "\n  ".join(bad))


# ── 5. 산출물 ① — 사람이 채우는 워크시트 ──────────────────────────────

GUIDE = """### 라벨링 지침 — 이것만 읽고 채우면 된다

1. 각 행의 **사건 문장**이 오른쪽 **요약 본문** 안에서 *말해지고 있는가*를 보고
   `담겼는가` 칸에 **`Y` / `N`**을 적는다.
2. 기준은 **«그 사건을 말하고 있는가»**다 — *낱말이 겹치는가가 아니다.* 다른 말로
   바꿔 썼어도 그 일을 말하고 있으면 `Y`, 같은 낱말이 있어도 다른 일을 말하고
   있으면 `N`이다.
3. 애매하면 **`?`를 적어라.** 억지로 가르지 마라 — **`?`도 데이터다.** 어느 쪽인지
   못 정하겠다는 사실 자체가 다음 단계가 알아야 할 것이다.
4. 행 사이에는 아무 관계도 없다. 순서에서 규칙을 찾지 마라 — **섞어 두었다.**
5. 🔴 이 라벨이 문턱(θ)을 정하고, **그 θ가 이 저장소의 요약 채점 방식을 바꾼다.**
   그래서 라벨을 만드는 사람과 채점기를 만든 사람이 달라야 한다."""

U4_NOTE = """> **왜 이걸 지금 하나 — 사전 등록된 조건은 오늘 충족되지 않았다.**
> 계획서(§9 U4)와 ADR-016은 이 라벨 집합을 «U1이 열리고 … 생기는 순간»에 만들기로
> 적어 두었다. **U1은 오늘 안 열렸다**(재료 밖 위양성 1건 vs 재료 안 생존 3건).
> 즉 이 워크시트는 **방아쇠가 당겨져서가 아니라 제품 결정으로** 만들어졌다.
> 그 구분을 적어 두지 않으면 «사전 등록»이 아무것도 제약하지 않게 된다."""


def cell(text):
    """
    표 한 칸. 줄바꿈과 `|`가 표를 깨므로 바꾼다 — **글자는 하나도 안 버린다.**

    🔴 «전문»이 요구사항이다. 자르면 라벨이 «내가 보여준 만큼»에 붙고, 그것은
       다음 레인이 다시 잴 수 없는 라벨이다.
    """
    return text.replace("|", "\\|").replace("\r\n", "\n").replace("\n", "<br>")


def render_worksheet(pairs, events, sums):
    ev = {e["id"]: e["text"] for e in events}
    sm = dict(sums)
    L = ["# 라벨 워크시트 — 「이 사건이 이 요약에 담겼는가」", "",
         f"채울 칸 **{len(pairs)}개**. 손으로 채운다. 자동으로 채우지 않는다.", "",
         GUIDE, "", U4_NOTE, "",
         "---", "",
         "| 쌍 id | 사건 (대장 문장 전문) | 요약 (그 요약 본문 전문) |"
         " 담겼는가 (Y/N) |",
         "|---|---|---|---|"]
    for p in pairs:
        L.append(f"| {p['pair_id']} | {cell(ev[p['event_id']])} |"
                 f" {cell(sm[p['session']])} |  |")
    L += ["",
          "---",
          "",
          "채운 뒤에 이 파일을 그대로 두면 된다. 다음 단계가 이 표의 `담겼는가`",
          "칸만 읽어 문턱을 유도한다 — **그 문턱은 이 표가 돌아오기 전에는",
          "정해지지 않는다.**", ""]
    return "\n".join(L)


# ── 6. 산출물 ② — 라벨이 돌아오기 전에는 아무도 안 보는 파일 ──────────

def write_pairs_json(pairs, meta, sims_n):
    rec = {
        "preregistration": {
            "rule": PREREG,
            "seed_pair": SEED_PAIR,
            "population": f"대장 events 10 × 세션 요약 24 = {sims_n}쌍",
            "u4_trigger": (
                "🔴 사전 등록된 U4 방아쇠는 **당겨지지 않았다.** U4는 «U1이 열리고,"
                " 라벨 집합이 eval/ 밖에서 n≥20으로 생기는 순간»이고, U1(«재료 밖"
                " 위양성 > 재료 안 생존»)은 오늘 1건 vs 3건으로 **안 열렸다**"
                " (experiments/digest_budget.py 3절이 매 실행 그 세 열을 찍는다)."
                " 이 라벨 집합은 방아쇠가 아니라 **오케스트레이터의 제품 결정**으로"
                " 만들어졌다."),
            "theta": (
                "🔴 θ는 이 레인이 정하지 않는다 (G12). 다음 레인이 돌아온 라벨을"
                " 받아 «모집단·n·자르는 비율»과 함께 유도한다. 이 파일에도"
                " 워크시트에도 문턱 후보값은 한 개도 없다."),
            "self_authorship": SELF_AUTHORSHIP,
        },
        "meta": meta,
        "read_order": (
            "🔴 이 파일은 워크시트와 **분리 보관**한다. 라벨이 돌아오기 전에"
            " `sim`을 보면 그 수가 라벨을 정박시키고, 그 라벨로 유도한 θ는"
            " 순환이 된다 (F38 — 공유된 결함을 통과한 독립 측정)."),
        "embedding": {"model": embedding.EMBED_MODEL,
                      "host": embedding.OLLAMA_HOST},
        "pairs": pairs,
    }
    with open(PAIRS_JSON, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)


# ── 7. 음성 대조 — **심을 위반 셋** ────────────────────────────────────

def negative_control(worksheet_text, pairs):
    """
    가드 셋에 **위반을 심어** 발화를 확인한다. 발화 안 하면 종료 코드가 갈린다.

    🔴 이 저장소가 여덟 번 깨진 규약이다 — *"새로 쓰거나 고친 검증 명령·시험은
       위반을 심어 발화를 확인한 뒤에만 보고한다."* 발화를 확인하지 않은 검사는
       «통과했다»가 아니라 «아무것도 안 했다»일 수 있다.

    ⚠️ 심는 것은 **메모리 안의 사본**이다. 디스크의 워크시트는 안 건드린다.
    """
    print("\n" + "-" * W)
    print("음성 대조 — 가드 셋에 위반을 심는다 (디스크는 안 건드린다)")
    print("-" * W)
    rows, ok = [], True

    # ① 워크시트에 유사도가 새어 들어간 사본
    mutant = worksheet_text.replace(
        "| P01 |", "| P01 (0.87) |", 1)
    fired = worksheet_leaks(mutant)
    ok &= bool(fired) and not worksheet_leaks(worksheet_text)
    rows.append(("① 누출", "P01 칸에 `(0.87)`을 심었다",
                 f"{len(fired)}건 — {fired[0][1]} `{fired[0][2]}`" if fired
                 else "🔴 발화 안 함"))

    # ② 중복 쌍
    dmut = list(pairs) + [dict(pairs[0])]
    fired2 = duplicate_pairs(dmut)
    ok &= bool(fired2) and not duplicate_pairs(pairs)
    rows.append(("② 중복", f"{pairs[0]['pair_id']}의 (사건,세션)을 한 번 더 넣었다",
                 f"{fired2}" if fired2 else "🔴 발화 안 함"))

    # ③ n < 24
    fired3 = too_few(pairs[:MIN_PAIRS - 1])
    ok &= bool(fired3) and not too_few(pairs)
    rows.append(("③ n<24", f"마지막 한 쌍을 뺐다 (n={MIN_PAIRS - 1})",
                 fired3 or "🔴 발화 안 함"))

    for name, planted, out in rows:
        print(f"  {name:<8} 심은 것: {planted}")
        print(f"           발화  : {out}")
    print(f"\n  🔴 그리고 **진짜 산출물에는 셋 다 안 걸린다** —"
          f" 누출 {len(worksheet_leaks(worksheet_text))}건 ·"
          f" 중복 {len(duplicate_pairs(pairs))}건 · n={len(pairs)}")
    print(f"  판정: {'✅ 셋 다 발화' if ok else '🔴 발화하지 않은 가드가 있다'}")
    return ok


# ── main ────────────────────────────────────────────────────────────────

def main():
    print("=" * W)
    print("라벨 워크시트 — 「이 사건이 이 요약에 담겼는가」 (결정 4 K · 미해결 U4)")
    print("=" * W)

    # 🔴 **첫 화면이 사전 등록이다.** 결과를 보고 규칙을 고치지 않았다는 것을
    #    말로 주장하는 대신, 규칙이 결과보다 위에 찍히게 둔다.
    print("\n" + PREREG)
    print("\n" + "-" * W)
    print("🔴 사전 등록된 U4 방아쇠는 **오늘 당겨지지 않았다**")
    print("-" * W)
    print("  U4 = «U1이 열리고, 라벨 집합이 eval/ 밖에서 n≥20으로 생기는 순간»")
    print("  U1 = «재료 밖 위양성 > 재료 안 생존» → 오늘 **1건 vs 3건 · 안 열렸다**")
    print("  → 이 라벨 집합은 **방아쇠가 아니라 제품 결정으로** 만들어졌다.")
    print("     `digest_budget.py` 3절이 매 실행 그 세 열을 찍는다.")
    print("\n" + SELF_AUTHORSHIP)
    print("\n  🔴 θ는 이 레인이 정하지 않는다 (G12) — 이 출력에도 두 산출물에도")
    print("     문턱 후보값은 **한 개도 없다.**")

    det = determinism_check()
    info, want, src, ok = digest_check()
    print("\n" + "-" * W)
    print("0. 사전 조건 — 결정성과 모델 다이제스트")
    print("-" * W)
    print(f"  결정성: temperature={det['temperature']} · seed={det['seed']}"
          f" · num_ctx={det['num_ctx']}  (`prototype/llm.py`의 전역과 대조 — 덮어쓰지 않았다)")
    if info.get("digest") is None or not embedding.available():
        print(f"  🔴 ollama({llm.OLLAMA_HOST})가 응답하지 않는다"
              f" — 생성도 임베딩도 못 한다. **종료 77 (SKIP)**")
        print("     «못 재는 것은 못 잰다고 적는다» (P3).")
        return 77
    print(f"  ollama {info['ollama']} · {info['model']}")
    print(f"  다이제스트 현재 {info['digest']}")
    print(f"            기대 {want}   (출처: {src})")
    if ok:
        print("  ✅ **다이제스트로 대조했다** — 생존 확인이 아니다.")
    else:
        print("  🔴 다이제스트가 기록과 다르다. 같은 seed·temperature여도 요약이")
        print("     움직인다. 이 실행의 라벨 집합은 기록과 **같은 조건이 아니다.**")
        return 1

    meta = dict(model=llm.LLM_MODEL, ollama=info["ollama"],
                digest=info["digest"], expect_digest=want,
                digest_source=src, **det)
    meta["u4_trigger_pulled"] = False
    meta["u4_note"] = ("U1(재료 밖 위양성 > 재료 안 생존)이 1건 vs 3건으로 안 열렸다."
                       " 방아쇠가 아니라 제품 결정으로 열었다.")

    corpus, ledger = load_eval()
    events = ledger["events"]

    print("\n" + "-" * W)
    print("1. 재료 — 24세션 요약 (`summarize.session_digest` · 사본 없음)")
    print("-" * W)
    cached = load_summaries(meta)
    if cached:
        sums, mt = cached
        print(f"  ↩ `SUMMARY_S2.json`을 읽었다 — 같은 조건이다"
              f" (생성 {mt.get('n')}건 · 정지 {mt.get('stalls')}회"
              f" · 벽시계 {mt.get('wall_s')}초). **이 실행의 생성 호출 0회.**")
        stats = mt
    else:
        sums, stats = generate_summaries(corpus, ledger, meta)
        print(f"\n  ✅ {stats['n']}건 · 벽시계 {stats['wall_s']}초"
              f" · **정지 {stats['stalls']}회** → `SUMMARY_S2.json`")

    print("\n" + "-" * W)
    print("2. 임베딩 유사도 — 🔴 **워크시트에는 안 들어간다**")
    print("-" * W)
    sims = similarity_matrix(events, sums)
    if sims is None:
        print(f"  🔴 `bge-m3` 임베딩을 못 얻었다 ({embedding.OLLAMA_HOST})."
              f" **종료 77 (SKIP)**")
        return 77
    print(f"  {len(events)}개 사건 × {len(sums)}개 요약 = {len(sims)}쌍 계산"
          f" (`bge-m3`)")
    print("  이 수들은 `LABEL_PAIRS.json`에만 들어간다. 라벨이 돌아오기 전에는")
    print("  아무도 안 본다 — 보면 라벨이 그 수에 정박한다 (F38).")

    print("\n" + "-" * W)
    print("3. 쌍 선택")
    print("-" * W)
    pairs = shuffle_and_id(select_pairs(events, sums, sims))
    kinds = {}
    for p in pairs:
        kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
    for k in ("natural_positive", "boundary", "far_control"):
        print(f"  {k:<18} {kinds.get(k, 0):>3}쌍")
    print(f"  {'합계':<18} {len(pairs):>3}쌍   (요구 n ≥ {MIN_PAIRS})")
    print("  🔴 종류별 분해는 여기까지다. **워크시트에는 종류가 안 실린다.**")

    text = render_worksheet(pairs, events, sums)
    enforce(text, pairs)            # 🔴 쓰기 **전에** 건다
    with open(WORKSHEET, "w", encoding="utf-8") as f:
        f.write(text)
    write_pairs_json(pairs, meta, len(sims))

    print("\n" + "-" * W)
    print("4. 산출물")
    print("-" * W)
    print(f"  사람이 채운다 : {os.path.relpath(WORKSHEET, ROOT)}"
          f"   (수 0개 · 빈 `담겼는가` 칸 {len(pairs)}개)")
    print(f"  분리 보관     : {os.path.relpath(PAIRS_JSON, ROOT)}"
          f"   (유사도·종류 — 라벨 전에는 안 본다)")
    print(f"  재료          : {os.path.relpath(SUMMARY_S2, ROOT)}")

    good = negative_control(text, pairs)

    print("\n" + "=" * W)
    print("판정")
    print("=" * W)
    print(f"  n                 : {len(pairs)}  (≥ {MIN_PAIRS} — {'✅' if len(pairs) >= MIN_PAIRS else '🔴'})")
    print(f"  워크시트 누출     : {len(worksheet_leaks(text))}건"
          f"  {'✅' if not worksheet_leaks(text) else '🔴'}")
    print(f"  중복 쌍           : {len(duplicate_pairs(pairs))}건"
          f"  {'✅' if not duplicate_pairs(pairs) else '🔴'}")
    print(f"  음성 대조 셋      : {'✅ 셋 다 발화' if good else '🔴 발화 실패'}")
    print(f"  다이제스트 대조   : {'✅ 일치' if ok else '🔴 불일치'}")
    print("  θ                 : **이 레인이 정하지 않는다** (G12)")
    print("=" * W)
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
