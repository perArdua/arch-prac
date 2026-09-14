# -*- coding: utf-8 -*-
r"""
engine_arms.py — 실험 32. **현행 검색을 진짜 검색 엔진과 «요인별로» 가른다.**

제품 소유자의 물음은 *"OpenSearch나 Postgres의 FTS·유사도 기능을 안 쓰고도 검색 정확도가 차이
안 난다는 말이냐"*였고, 이 저장소의 정직한 답은 **«모른다»**였다 — 비교를 한 번도 안 했기
때문이다. 이 파일이 그 비교다.

## 🔄 w7engines — 이 파일은 «돌지 않은 채» 보존돼 있던 판을 다시 썼다. 뒤집힌 전제 넷

1. **조건은 이미 열려 있었다.** 미룬 근거(«IDF가 순위를 움직일 수 있는 문항 3/18»)는 eval
   하나의 값이었고, eval2가 같은 정의로 7/13이다. 그래서 이 판은 코퍼스 **다섯 열**(eval · eval2 ·
   eval3 레짐 셋)을 나란히 돈다 — 옛 판은 eval 18문항만 봤다.
2. **«규모가 커지면 IDF가 이긴다»는 이 실험의 가설이 아니다** — 그 조건은 df 모양보다 N의 함수였다.
3. **`bigm_similarity`는 자카드가 아니고 pg_bigm의 분석기는 현행과 다르다**(어절마다 앞뒤 공백 ·
   어미를 안 벗김). 옛 판의 B1(현행 분석기 + ∩/max)은 다리를 잘못 놓았다 — A0에서 pg_bigm까지는
   요인이 셋이고, 사슬은 **분석기 → 식 → 구현** 순서로 한 칸씩 간다(B1 → B2 → B3).
4. **OpenSearch 기본 유사도는 Lucene BM25**(k1=1.2 · b=0.75)이고 nori 기본값은 `DISCARD` · 품사 필터 18종 ·
   사용자 사전 없음이다. 파이썬 BM25(`make_bm25`)는 Lucene `BM25Similarity`의 식으로 두었다 — ⚠️ OpenSearch
   2.19.6은 거기에 상수 `(k1+1)`을 boost로 곱한다(값을 보고 안 것 · P4 절). 순위와 V2에는 무관하다.

## 🔴 이 파일이 하는 것과 하지 않는 것

**하는 것:** 팔 일곱을 두 보기로 잰다 — **V1 순위만**(τ·θ·가중치 없이 관련도 순위로 recall@k)과
**V2 파이프라인**(격자 하니스 + 정본 4단계 함수에 `rel`과 θ만 꽂음). 판정은 코퍼스 열마다
**홀드아웃 문항별 부호검정**이고 p < 0.05일 때만 방향을 말한다.

**하지 않는 것:** 기본값을 바꾸지 않는다(G16 — `RETRIEVAL_MODE="lexical"`, 스위치 둘 꺼짐).
응답 품질을 재지 않는다(실험 24 — 검색 지표가 움직여도 응답이 안 움직였다). 엔진을 튜닝하지
않는다(k1·b는 Lucene 기본값 · nori 사용자 사전 없음 · 품사 필터 기본값).

## 🔴 요인 규율의 집행부는 **남의 것을 import한다** (F12 · 사본 금지)

  · `summary_ablation.FactorRule` / `ArrowRule` — «앵커와 한 요인만 다른가» · «화살표 자격»
  · `summary_prototype.TitleRule` / `Col` — «열 제목에 항목 집합·채점기 이름»
  · `scorer_eval.split_blind` / `Holdout` — 실험 26의 사전 등록 분할과 접근 예산
  · `rel_dist.theta_at` / `actual_cut` / `q_at` — 등컷 θ 사다리 · 분위수 규약
  · `probe_types.sign_test` — 정확 부호검정
  · `precision`의 지표 함수 · `retrieval_sweep.run_cell` — 격자 하니스 그 자체

`FactorRule.audit`은 `Arm.FACTORS`를 모듈 전역으로 읽으므로 요인 이름이 다른 이 라운드는
이름표만 갈아 끼운다(`engine_factors`) — 집행 논리는 한 줄도 복사하지 않고, 되돌림을 단언한다(G13).

실행 (컨테이너는 `experiments/engine_infra/README.md`):
    PYTHONIOENCODING=utf-8 python -B experiments/engine_arms.py
    PYTHONIOENCODING=utf-8 python -B experiments/engine_arms.py --corpora eval,eval2 --no-latency   # 부분 실행 — 기록값 아님

종료 코드: 0 = 규칙 전부 통과 · 1 = 규칙 위반(요인 · 화살표 · 제목 · 홀드아웃 예산 · G16 · A0 등가) ·
77 = 엔진이 없다(SKIP — **통과가 아니다**, G1). 판정의 방향·«검출 안 됨»·지연은 종료 코드를 바꾸지 않는다.
"""
import argparse
import contextlib
import hashlib
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "prototype"))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import memory as M                                             # noqa: E402
from memory import Memory                                      # noqa: E402
import precision as P                                          # noqa: E402
import rel_dist as RD                                          # noqa: E402
import retrieval_sweep as RS                                   # noqa: E402
import scoring as SC                                           # noqa: E402
import scorer_eval as SE                                       # noqa: E402
import summary_ablation as SA                                  # noqa: E402
import summary_prototype as SP                                 # noqa: E402
import engine_clients as EC                                    # noqa: E402
from probe_types import sign_test                              # noqa: E402
from soak import CHAT, seed, ingest                            # noqa: E402

W = 112
ROOT = os.path.dirname(HERE)

# ══════════════════════════════════════════════════════════════════════
# 0. 🔴 사전 등록 — **값을 하나도 보기 전에** 여기 박고 출력 첫 화면에 찍는다
# ══════════════════════════════════════════════════════════════════════

# 요인의 이름. `summary_ablation.Arm.FACTORS`를 이것으로 갈아 끼운다.
ENGINE_FACTORS = ("분석기", "관련도 식", "구현")

AN_A0 = "현행 memory.bigrams (어미 벗김 · 어절 이어붙임)"
AN_PG = "pg_bigm식 2-gram (어절마다 앞뒤 공백 · 어미 안 벗김)"
AN_NORI = "nori 토큰 (_analyze field=body · 내장 기본값 · 사용자 사전 없음)"
F_COV = "∩/|q| 덮기율"
F_MAX = "∩/max(|q|,|d|)"
F_BM25 = "BM25 Lucene 식 (k1=1.2 · b=0.75)"
I_PY = "파이썬 선형"
I_PG = "Postgres 16 + pg_bigm 1.2 GIN (=% · bigm_similarity)"
I_OS = "OpenSearch 2.19.6 · Lucene 9.12.3 BM25Similarity"

# (팔, 분석기, 관련도 식, 구현, 앵커, 움직인 요인, 컨테이너가 필요한가)
# 🔴 순서는 시험이 기댄다 — 둘째가 A1이다(`test_engine_arms`의 E3·E4).
ARM_SPECS = (
    ("A0", AN_A0, F_COV, I_PY, None, None, False),
    ("A1", AN_A0, F_BM25, I_PY, "A0", "관련도 식", False),
    ("B1", AN_PG, F_COV, I_PY, "A0", "분석기", False),
    ("B2", AN_PG, F_MAX, I_PY, "B1", "관련도 식", False),
    ("B3", AN_PG, F_MAX, I_PG, "B2", "구현", True),
    ("C1", AN_NORI, F_BM25, I_PY, "A1", "분석기", True),
    ("C2", AN_NORI, F_BM25, I_OS, "C1", "구현", True),
)

# 🔴 화살표를 그릴 쌍 — 계산하지 않고 표로 박는다(실험 28이 계산 규칙으로 두었다가 요인이
#    하나 늘자 판정을 3분의 1만 보게 된 자리). `ArrowRule`이 종료 코드로 다시 확인한다.
ARROWS = (("A0", "A1"), ("A0", "B1"), ("B1", "B2"), ("B2", "B3"), ("A1", "C1"), ("C1", "C2"))

# 🔴 **종합 대조** — 제품 소유자의 물음 그 자체(현행 ↔ 엔진). 부호검정은 하지만 **귀속 없음 ·
#    화살표 없음**이다: 요인이 셋 다 다르므로 «무엇 때문에»를 말할 수 없다. 방향이 나와도 그것은
#    «이 코퍼스에서 두 구성이 다르다»까지다.
TOTAL_PAIRS = (("A0", "B3"), ("A0", "C2"))

# 컨테이너 팔이 `probe_containers()`의 어느 깃발에 기대나. C1은 파이썬 선형이지만 항을
# OpenSearch `_analyze`(nori)에서 받는다.
CONTAINER_OF = {"B3": "pg", "C1": "os", "C2": "os"}

# 🔴 **BM25의 k1·b는 튜닝하지 않는다.** Lucene/OpenSearch 기본값을 모든 BM25 팔(A1·C1·C2)에
#    박는다 — 그래야 C1 ↔ C2가 «구현»만 다르다. 조정 팔은 만들지 않았다(만들면 별도 이름 ·
#    훈련 분할에서만 · 홀드아웃 예산 감사).
BM25_K1, BM25_B = 1.2, 0.75

# 🔴 **nori 사용자 사전은 비운다** — 캐릭터 이름을 넣으면 답을 넣는 것이다. 품사 필터에 VCP(`이`)를
#    더하는 팔도 만들지 않았다(그것은 튜닝이다). 색인 설정은 `engine_clients.os_create_index`의 기본
#    `{"type": "nori"}` — 내장 분석기와 같은 사슬이다(w6infra T1c).
NORI_ANALYZER = {"type": "nori"}
NORI_USER_DICT = None

# ── 두 보기 ─────────────────────────────────────────────────────────────
KS = (1, 3, 5, 10)
JUDGE_K = 5                   # V1의 판정 k — 프로덕션 `TOP_K`와 같은 자리를 본다(값은 리터럴이 아니라 확인한다)
V1_TIE_RULE = ("동점은 **묶음 안에서 무작위 순서의 기대값**으로 센다 — 경계 묶음 크기 g · 남은 자리 s · "
               "그 묶음 안 근거 행 m → 적중 확률 1 − C(g−m, s)/C(g, s). 삽입 순서(`event_id`)로 깨면 "
               "생성기의 배치 순서가 채점기 비교에 섞인다")
V2_NORM_RULE = ("비유계 식(BM25 — A1·C1·C2)만 **질의마다 살아 있는 행의 최댓값으로 나눈다**(최댓값 0이면 "
                "전부 0 · OpenSearch normalization-processor `min_max`의 min=0 꼴). 유계 식(∩/|q| · ∩/max)은 "
                "그대로. V1은 질의 안 순위만 보므로 이 정규화의 영향을 안 받는다")
THETA_RULE = ("A0는 `memory.THETA_RELEVANCE` 그대로(G16). 나머지 팔은 **훈련 분할 문항 × 살아 있는 행** 모집단에서 "
              "f = `rel_dist.actual_cut(A0 rel, THETA_RELEVANCE)`를 재고 θ = `rel_dist.theta_at(팔 rel, f)` "
              "(V2 정규화 뒤의 값). 라벨·지표를 보지 않는다. 요청 f와 실제 컷을 나란히 찍는다(G12·G15)")

# ── 판정 ────────────────────────────────────────────────────────────────
ALPHA = 0.05


def min_n_for(alpha):
    """동률을 뺀 n이 이 이상이어야 양측 정확 부호검정이 p < α에 **도달할 수 있다**(2·0.5ⁿ < α)."""
    n = 1
    while 2 * 0.5 ** n >= alpha:
        n += 1
    return n


MIN_N = min_n_for(ALPHA)      # α=0.05 → 6 (eval3 조건 «≥ 6»과 같은 산수)

V_UP, V_DOWN, V_NULL, V_WEAK = "팔 ↑", "팔 ↓", "검출 안 됨", "판정 불가(힘 없음)"
SHORT_V = {V_UP: "↑", V_DOWN: "↓", V_NULL: "없음", V_WEAK: "불가"}      # 표 칸 전용 줄임말

DECISION = (
    ("J1 방향", f"동률 뺀 n ≥ {MIN_N}이고 양측 p < {ALPHA} → 이긴 쪽의 방향(«{V_UP}»/«{V_DOWN}»)"),
    ("J2 검출 안 됨", f"n ≥ {MIN_N}이고 p ≥ {ALPHA} → «{V_NULL}» (**«같다»가 아니다**)"),
    ("J3 판정 불가", f"n < {MIN_N} → «{V_WEAK}» — 그 n의 최소 달성 p = 2·0.5ⁿ ≥ {ALPHA}"),
)
JUDGED = (
    ("V1", f"recall@{JUDGE_K} 기대값", "high"),
    ("V2", "근거 적중 수 (evidence_recall 분자 · TOP_K)", "high"),
    ("V2", "오주입 수 (mis@q)", "low"),
)

# 홀드아웃 — 실험 26의 분할을 **재사용**한다. 예산은 «무엇을 여는가»를 미리 세어 적는다.
#   열마다: A0 등가(1) · V1 판정(1) · V2 판정(1) = 3. 이름을 새로 짓는 것으로는 못 피한다.
HO_OPENS = ("A0 등가", "V1 판정", "V2 판정")
HO_BUDGET_PER_COL = len(HO_OPENS)

# 분석기·구현 대조의 허용 오차. bigm_similarity는 float4, OpenSearch `_score`는 float32다.
TOL_PG_ABS = 1e-6
TOL_OS_REL = 1e-4

# 기본값 경로 — 착수·마감에 확인한다(G16). 이름을 문자열로 든다(값 비교가 점수식 사본으로 읽히지 않게).
G16_DEFAULTS = {"RETRIEVAL_MODE": "lexical", "THETA_ON_SCORE": False, "W_REC": 0.0}

# 지연 — 서버 시간으로만 판다. eval3 레짐마다 채점 48문항 × 3회 (+ 워밍업 버림).
LAT_REPS = 3
LAT_WARMUP = 10
LAT_SEED = 20260911

CANNOT_SAY = (
    "코퍼스가 전부 **합성 · 한 저자**다. eval3의 df는 **생성기가 정한다**(docs/12 §4의 순환) — «df가 이렇게 "
    "생겼을 때 이 값이다»까지만 말한다",
    "**검색 지표는 응답을 뜻하지 않는다**(실험 24). 이 실험은 **검색까지만** 잰다",
    "**엔진을 며칠 튜닝한 사람과 겨루는 것이 아니다** — 기본 설정(k1·b 기본 · nori 사전 없음 · 품사 필터 기본)이고, "
    "그것이 상한이 아니다",
    "레짐 사이·코퍼스 사이에 화살표를 그리지 않는다 — 열은 서로 다른 모집단이다",
    "홀드아웃이 작다(eval 2 · eval2 6 · eval3 23문항) — «검출 안 됨»은 «차이 없음»의 증명이 아니다",
)

EXIT_SKIP = 77


def hr(ch="-"):
    print(ch * W)


def title(t):
    print()
    hr("=")
    print(t)
    hr("=")


# ══════════════════════════════════════════════════════════════════════
# 1. 컨테이너 — 살아 있는가 · 무엇이 설치돼 있는가
# ══════════════════════════════════════════════════════════════════════

def _run(cmd, stdin_text=None, timeout=120):
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    try:
        p = subprocess.run(cmd, input=(stdin_text.encode("utf-8")
                                       if stdin_text is not None else None),
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout, env=env)
    except FileNotFoundError as e:
        # 🔄 w6code — `docker`가 PATH에 없으면 여기서 터져 `probe_containers`가 SKIP 대신
        #    예외로 죽었다. 없는 도구는 «컨테이너 없음»과 같은 값으로 돌려준다(G1: 그 뒤는 SKIP).
        return 127, f"{cmd[0]}: 실행 파일 없음 ({e})"
    return p.returncode, p.stdout.decode("utf-8", "replace")


def probe_containers():
    """
    `(OpenSearch 있음, Postgres 있음, 진단 줄들)`. **없으면 지어내지 않고 SKIP한다.**

    🔄 w7engines — 옛 판은 컨테이너 이미지 ID를 기반 다이제스트와 **곧바로** 비교했다. 재현 이미지는
       기반 위에 층을 하나 더 쌓은 것이라 ID가 달라 «불일치(F21)»로 읽혔다(w6infra가 읽고 넘긴 사실).
       이제 `engine_clients.image_provenance`(RootFS 층 접두사)로 본다.
    """
    diag, ok = [], {"os": False, "pg": False}
    rc, out = _run(["docker", "ps", "--filter", "name=memarch",
                    "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"])
    diag.append(f"  docker ps --filter name=memarch →\n{out.rstrip() or '    (없음)'}")
    for c, key in (("memarch-os", "os"), ("memarch-pg", "pg")):
        rc2, _ = _run(["docker", "inspect", "--format", "{{.Image}}", c])
        if rc2 != 0:
            diag.append(f"  🔴 «{c}» 컨테이너가 없다")
            continue
        try:
            prov = EC.image_provenance(c)
            diag.append(f"  «{c}» 이미지 {prov['image'][:19]}… · 기반 {prov['base'][:40]}…\n"
                        f"      → {'✅ 기반 층 전부 + 층 ' + str(prov['extra_layers']) if prov['on_base'] else '🔴 기반 위가 아니다 — 섞였다(F21)'}")
            if not prov["on_base"]:
                continue
            if key == "os":
                v = EC.os_require_nori()
                diag.append(f"      OpenSearch {v['opensearch']} · Lucene {v['lucene']} · "
                            f"analysis-nori {v['analysis-nori']} ✅")
            else:
                v = EC.pg_require_bigm()
                diag.append(f"      Postgres {v['postgres']} · pg_bigm {v['pg_bigm']} ✅")
            ok[key] = True
        except (EC.EngineUnavailable, EC.EngineError) as e:
            diag.append(f"      🔴 엔진 없음/실패: {e}")
    return ok["os"], ok["pg"], diag


def mark_skips(arms, ok_os, ok_pg):
    """
    🆕 w6code — 컨테이너가 없는 팔에 `skipped` 사유를 적고 그 키를 돌려준다.
    **목록이 비지 않으면 전체 종료 코드는 `EXIT_SKIP`(77)이다** — G1: SKIP은 통과가 아니고,
    팔을 조용히 빼면 그 팔은 «차이 없음»으로 읽힌다.
    """
    ok = {"os": ok_os, "pg": ok_pg}
    out = []
    for a in arms:
        if not a.needs_container:
            continue
        need = CONTAINER_OF[a.key]          # 새 컨테이너 팔을 표 없이 더하면 여기서 KeyError
        if not ok[need]:
            a.skipped = f"77-SKIP — «{need}» 컨테이너 없음 또는 기반·플러그인 불일치"
            out.append(a.key)
    return out


# ══════════════════════════════════════════════════════════════════════
# 2. 분석기 — 무엇을 항으로 쓰나
# ══════════════════════════════════════════════════════════════════════

def terms_bigram(t):
    """현행 분석기. **`memory.bigrams`를 그대로 부른다** (사본 금지 · F12)."""
    return M.bigrams(t)


def terms_pgbigm(t):
    """
    `pg_bigm`의 2-gram을 **파이썬으로 재현**한 것. 어절(공백 구분)마다 앞뒤에 공백 하나를 붙여
    2글자씩 자른다 — 어미를 **안 벗기고** 구두점도 남긴다(`show_bigm('뭐였지?')`에 `지?`·`? `가 있다).

    🔴 재현이 맞는지는 주장하지 않고 **모든 행·모든 문항에서 `show_bigm()`과 대조한다**(P1).
       한 건이라도 다르면 B2 → B3 화살표를 거둔다 — 그때 둘은 분석기와 구현 두 요인이 다르다.
    """
    out = []
    for w in t.split():
        s = " " + w + " "
        out += [s[i:i + 2] for i in range(len(s) - 1)]
    return out


def parse_pg_array(s):
    """
    `{" 가",나비,"a\\"b",…}` 꼴의 Postgres 배열 텍스트를 원소 목록으로.

    🔄 w7engines — 옛 `_parse_pg_array`는 따옴표 안의 역슬래시 이스케이프(`\\"`·`\\\\`)를 몰랐다.
       원소에 따옴표가 든 행이 하나라도 있으면 P1이 **분석기가 아니라 파서** 때문에 거짓이 된다.
    """
    s = s.strip()
    if not (s.startswith("{") and s.endswith("}")):
        raise ValueError(f"배열 텍스트가 아니다: {s[:40]!r}")
    body, out, buf, inq, esc, quoted = s[1:-1], [], "", False, False, False
    for ch in body:
        if esc:
            buf += ch
            esc = False
        elif inq and ch == "\\":
            esc = True
        elif ch == '"':
            inq = not inq
            quoted = True
        elif ch == "," and not inq:
            out.append(buf)
            buf, quoted = "", False
        else:
            buf += ch
    if buf or quoted:
        out.append(buf)
    return out


# ══════════════════════════════════════════════════════════════════════
# 3. 관련도 식
# ══════════════════════════════════════════════════════════════════════

def rank_coverage(q_terms, d_terms, stats):
    """현행. **`memory.coverage`를 그대로 부른다** (사본 금지 · F12)."""
    return M.coverage(set(q_terms), set(d_terms))


def rank_overlap_max(q_terms, d_terms, stats):
    """`|A∩B| / max(|A|,|B|)` — `bigm_similarity`의 식(`bigm_op.c` `cnt_sml_bigm` · `DIVUNION` 미정의)."""
    a, b = set(q_terms), set(d_terms)
    return len(a & b) / max(len(a), len(b), 1)


def make_bm25(k1, b):
    """
    Lucene 9 `BM25Similarity`의 식 — **정확 길이 · float64**.

        idf(t) = ln(1 + (N − df + 0.5) / (df + 0.5))
        score  = Σ_{t ∈ q (중복 살림)} idf(t) · f / (f + k1·(1 − b + b·dl/avgdl))

    🔄 w7engines — 옛 판은 분자에 `(k1+1)`이 있었다(교과서 식). Lucene 8의 `BM25Similarity`는 그 상수를
       뺐고 이 판은 그 모양을 사전 등록했다. ⚠️ **값을 보고 안 것:** OpenSearch 2.19.6은 그 상수를 **질의
       boost로 되살린다** — `explain`이 `boost 2.2`(= k1+1)를 찍고, C2/C1 비는 모든 양수 쌍에서 2.2다(float32 안).
       순위에 무관한 상수배이고 V2의 질의별 최댓값 정규화에서 약분된다. 그래서 식을 고치지 않고 P4의 «값»
       대조가 거짓으로 나오는 것을 그대로 찍고, 2.2로 나눈 대조를 **사후 진단**으로 따로 찍는다.
    🔴 **질의 항은 중복을 살린다.** `match` 질의는 토큰마다 절을 만들어 더한다.
    ⚠️ 여기서 N은 색인 행 수 전부 · avgdl은 전 행 평균이다. Lucene은 N·avgdl을 **항이 하나라도 있는
       문서**로 세고 길이를 1바이트로 손실 부호화한다 — 그 차이는 «구현» 요인 **안에** 있고 P4가 잰다.
    """
    def score(q_terms, d_terms, stats):
        N, df, avgdl = stats["N"], stats["df"], stats["avgdl"]
        tf = {}
        for t in d_terms:
            tf[t] = tf.get(t, 0) + 1
        dl = len(d_terms)
        norm = k1 * (1 - b + b * dl / (avgdl or 1))
        s = 0.0
        for t in q_terms:
            f = tf.get(t, 0)
            if not f:
                continue
            idf = math.log(1 + (N - df.get(t, 0) + 0.5) / (df.get(t, 0) + 0.5))
            s += idf * f / (f + norm)
        return s
    return score


BM25 = make_bm25(BM25_K1, BM25_B)


# ══════════════════════════════════════════════════════════════════════
# 4. 팔 — 요인 셋과 앵커 없이는 만들 수 없다
# ══════════════════════════════════════════════════════════════════════

class EngineArm:
    """
    한 팔. `summary_ablation.FactorRule`이 읽는 계약(`key`·`anchor`·`moved`·`factors()`·`ran`)만
    갖춘다 — **집행부는 그쪽 것을 쓴다.**
    """

    def __init__(self, key, analyzer, ranking, impl, anchor, moved, needs):
        self.key, self.anchor, self.moved = key, anchor, moved
        self.analyzer, self.ranking, self.impl = analyzer, ranking, impl
        self.needs_container = needs
        self.ran = False
        self.skipped = None
        self.theta = None
        self.cut = None
        self.tot = None
        self.rels = None
        self.scorer = None

    def factors(self):
        return {"분석기": self.analyzer, "관련도 식": self.ranking, "구현": self.impl}

    def label(self):
        return f"{self.key} · {self.analyzer} · {self.ranking} · {self.impl}"

    def short(self):
        an = {AN_A0: "현행bigram", AN_PG: "pg_bigm식", AN_NORI: "nori"}.get(self.analyzer, self.analyzer)
        fm = {F_COV: "∩/|q|", F_MAX: "∩/max", F_BM25: "BM25"}.get(self.ranking, self.ranking)
        im = {I_PY: "파이썬", I_PG: "PG GIN", I_OS: "OpenSearch"}.get(self.impl, self.impl)
        return f"{self.key} {an}·{fm}·{im}"


@contextlib.contextmanager
def engine_factors():
    """`FactorRule`·`ArrowRule`이 이 라운드의 요인 이름으로 읽게 이름표만 갈아 끼운다(G13 되돌림 단언)."""
    saved = SA.Arm.FACTORS
    SA.Arm.FACTORS = ENGINE_FACTORS
    try:
        yield
    finally:
        SA.Arm.FACTORS = saved
    assert SA.Arm.FACTORS is saved, "Arm.FACTORS 복원 실패 (G13)"


class PyScorer:
    """파이썬 선형 채점기 — 분석기 하나와 관련도 식 하나를 든다."""

    def __init__(self, terms_fn, rank_fn):
        self.terms_fn, self.rank_fn = terms_fn, rank_fn
        self._docs = None

    def fit(self, docs):
        if self._docs == tuple(docs):
            return
        self._docs = tuple(docs)
        self.dterms = [self.terms_fn(d) for d in docs]
        df = {}
        for dt in self.dterms:
            for t in set(dt):
                df[t] = df.get(t, 0) + 1
        self.stats = {"N": len(docs), "df": df,
                      "avgdl": sum(len(d) for d in self.dterms) / max(len(docs), 1)}

    def rels(self, query, docs):
        self.fit(docs)
        q = self.terms_fn(query)
        return [self.rank_fn(q, dt, self.stats) for dt in self.dterms]

    def close(self):
        pass


class MaxNormalized:
    """
    V2 전용 — 비유계 식의 rel을 **질의마다 살아 있는 행의 최댓값으로 나눈다**(`V2_NORM_RULE`).
    같은 `rels(query, docs)` 계약이라 `make_retrieve`에 그대로 꽂힌다. V1은 이것을 안 지난다.
    """

    def __init__(self, inner):
        self.inner = inner

    def rels(self, query, docs):
        vals = self.inner.rels(query, docs)
        top = max(vals) if vals else 0.0
        return [v / top for v in vals] if top > 0 else [0.0] * len(vals)


class PgGinScorer:
    """
    B3 — **Postgres 안의 `bigm_similarity()`가 낸 값을 그대로 받는다.** 행 선택은 GIN 색인의
    `=%` 연산자(유사도 하한 1e-6 · `enable_seqscan=off`)가 한다 — 그래서 «구현» 칸이 GIN이다.
    `=%`에 안 걸린 행은 공유 bigram이 없는 행이고 값은 0이다.

    질의마다 psql 프로세스를 띄우면 그 시작 비용(벽시계 ≈217 ms, w6infra)이 지연을 삼키므로 **한 세션에
    전부 먹이고**, 지연은 `EXPLAIN (ANALYZE)`의 실행 시간(서버 시간)으로만 읽는다(§지연).
    """

    PRE = ("LOAD 'pg_bigm';\nSET pg_bigm.similarity_limit = 0.000001;\n"
           "SET enable_seqscan = off;\n")

    def __init__(self, table, docs):
        self.table, self.docs = table, tuple(docs)
        self.cache = {}
        EC.pg_create_index(table)
        EC.pg_index_docs(table, [(str(i), d) for i, d in enumerate(self.docs)])

    def _sql(self, q):
        return (f"SELECT id, bigm_similarity(body, {EC.lit(q)}) FROM {self.table} "
                f"WHERE body =% {EC.lit(q)};")

    def prefetch(self, queries):
        need = [q for q in dict.fromkeys(queries) if q not in self.cache]
        if not need:
            return
        marks = [f"__w7q{i}__" for i in range(len(need))]
        sql = self.PRE + "\n".join(f"SELECT {EC.lit(m)};\n" + self._sql(q) for m, q in zip(marks, need))
        rows = EC.psql(sql)
        cur, got = None, {}
        for r in rows:
            if len(r) == 1 and r[0] in marks:
                cur = need[marks.index(r[0])]
                got[cur] = [0.0] * len(self.docs)
            elif cur is not None and len(r) == 2:
                got[cur][int(r[0])] = float(r[1])
            else:
                raise EC.EngineError(f"psql 출력 형식이 안 맞는다: {r!r}")
        if len(got) != len(need):
            raise EC.EngineError(f"응답 질의 수가 안 맞는다: {len(got)} vs {len(need)}")
        self.cache.update(got)

    def rels(self, query, docs):
        if tuple(docs) != self.docs:
            raise ValueError("색인한 문서 목록과 다른 목록으로 물었다 — 위치가 어긋난다")
        if query not in self.cache:
            self.prefetch([query])
        return list(self.cache[query])

    def show_bigm_docs(self):
        rows = EC.psql(f"SELECT id, show_bigm(body) FROM {self.table};")
        out = [None] * len(self.docs)
        for i, arr in rows:
            out[int(i)] = set(parse_pg_array(arr))
        return out

    def show_bigm_texts(self, texts):
        marks = [f"__w7s{i}__" for i in range(len(texts))]
        sql = "\n".join(f"SELECT {EC.lit(m)};\nSELECT show_bigm({EC.lit(t)});" for m, t in zip(marks, texts))
        rows, out, cur = EC.psql(sql), {}, None
        for r in rows:
            if len(r) == 1 and r[0] in marks:
                cur = texts[marks.index(r[0])]
            elif cur is not None and len(r) == 1:
                out[cur] = set(parse_pg_array(r[0]))
        return out

    def plan_nodes(self, q):
        """계획이 GIN 색인을 쓰는지 — `EXPLAIN (FORMAT JSON)`의 노드 종류와 색인 이름."""
        rows = EC.psql(self.PRE + "EXPLAIN (FORMAT JSON) " + self._sql(q))
        plan = json.loads("\n".join("\t".join(r) for r in rows))

        def walk(n):
            yield (n.get("Node Type"), n.get("Index Name"))
            for c in n.get("Plans", []):
                yield from walk(c)
        return list(walk(plan[0]["Plan"]))

    def exec_ms(self, queries, force_gin):
        """`EXPLAIN (ANALYZE, TIMING OFF)`의 `Execution Time`(서버 시간 ms) — 한 세션에 전부."""
        pre = self.PRE if force_gin else self.PRE.replace("SET enable_seqscan = off;\n", "")
        marks = [f"__w7e{i}__" for i in range(len(queries))]
        sql = pre + "\n".join(
            f"SELECT {EC.lit(m)};\nEXPLAIN (ANALYZE, TIMING OFF, FORMAT JSON) "
            f"SELECT id, bigm_similarity(body, {EC.lit(q)}) AS s FROM {self.table} "
            f"WHERE body =% {EC.lit(q)} ORDER BY s DESC, id LIMIT {M.TOP_K};"
            for m, q in zip(marks, queries))
        rows, bufs = EC.psql(sql), []
        for r in rows:
            if len(r) == 1 and r[0] in marks:
                bufs.append([])
            else:
                bufs[-1].append("\t".join(r))
        out, nodes = [], Counter()

        def scans(n):
            if "Scan" in (n.get("Node Type") or ""):
                yield n["Node Type"]
            for c in n.get("Plans", []):
                yield from scans(c)
        for b in bufs:
            j = json.loads("\n".join(b))[0]
            out.append(float(j["Execution Time"]))
            nodes["+".join(sorted(set(scans(j["Plan"]))))] += 1
        return out, nodes

    def close(self):
        EC.pg_drop(self.table)


class OsNori:
    """
    C1·C2가 함께 쓰는 OpenSearch 색인 하나(샤드 1 · 내장 nori · BM25 k1·b 기본값).

    🔴 C1의 항은 **이 색인의 `body` 필드 분석기**가 돌려준 토큰이다(`/{index}/_analyze` · `field`).
       내장 분석기 이름으로 부르지 않는 이유: 색인 설정과 같은 사슬인지를 «같은 이름»으로 믿지 않고
       색인 자체에 묻는다. 그리고 P2가 색인이 실제로 든 항(`_mtermvectors`)과 계수까지 대조한다.
    """

    def __init__(self, index, docs):
        self.index, self.docs = index, tuple(docs)
        self.cache, self.hits = {}, {}
        EC.os_create_index(index, analyzer_body=NORI_ANALYZER, k1=BM25_K1, b=BM25_B)
        EC.os_index_docs(index, [(str(i), d) for i, d in enumerate(self.docs)])

    def analyze(self, text):
        if text not in self.cache:
            r = EC.os_request(f"/{self.index}/_analyze", {"field": "body", "text": text})
            self.cache[text] = [t["token"] for t in r["tokens"]]
        return list(self.cache[text])

    def warm(self, texts, workers=8):
        todo = [t for t in dict.fromkeys(texts) if t not in self.cache]
        with ThreadPoolExecutor(workers) as ex:
            for t, toks in zip(todo, ex.map(lambda x: EC.os_request(
                    f"/{self.index}/_analyze", {"field": "body", "text": x})["tokens"], todo)):
                self.cache[t] = [k["token"] for k in toks]

    def termvectors(self, batch=500):
        """색인이 든 항 빈도 `[{항: tf}]`와 필드 통계. 항이 없는 문서는 빈 dict."""
        out, fstats = [None] * len(self.docs), None
        ids = [str(i) for i in range(len(self.docs))]
        for s in range(0, len(ids), batch):
            r = EC.os_request(f"/{self.index}/_mtermvectors", {
                "ids": ids[s:s + batch],
                "parameters": {"fields": ["body"], "positions": False, "offsets": False,
                               "payloads": False, "term_statistics": False,
                               "field_statistics": True}}, timeout=120)
            for d in r["docs"]:
                tv = d.get("term_vectors", {}).get("body", {})
                fstats = tv.get("field_statistics", fstats)
                out[int(d["_id"])] = {t: v["term_freq"] for t, v in tv.get("terms", {}).items()}
        return out, fstats

    def search_all(self, query):
        r = EC.os_request(f"/{self.index}/_search", {"query": {"match": {"body": query}},
                                                     "size": len(self.docs), "_source": False})
        vals = [0.0] * len(self.docs)
        for h in r["hits"]["hits"]:
            vals[int(h["_id"])] = float(h["_score"])
        return vals

    def took_ms(self, query):
        t0 = time.perf_counter()
        r = EC.os_request(f"/{self.index}/_search", {"query": {"match": {"body": query}},
                                                     "size": M.TOP_K, "_source": False})
        return float(r["took"]), (time.perf_counter() - t0) * 1000

    def close(self):
        EC.os_delete_index(self.index)


class OsScorer:
    """C2 — **OpenSearch가 매긴 `_score`를 그대로 받는다.** 파이썬은 아무것도 안 센다."""

    def __init__(self, osn):
        self.osn = osn
        self.cache = {}

    def rels(self, query, docs):
        if tuple(docs) != self.osn.docs:
            raise ValueError("색인한 문서 목록과 다른 목록으로 물었다 — 위치가 어긋난다")
        if query not in self.cache:
            self.cache[query] = self.osn.search_all(query)
        return list(self.cache[query])


# ══════════════════════════════════════════════════════════════════════
# 5. 팔의 `retrieve` — **프로덕션 4단계 함수 그 자체**에 `rel`과 θ만 꽂는다
# ══════════════════════════════════════════════════════════════════════

# 🔴 import 시점의 진짜 4단계 함수를 붙든다. 실행 중에 `Memory.retrieve`를 감싸는
#    기록기(`theta_position.Recorder` 같은 것)는 `ext`를 모르므로, 그 자리에서 다시
#    읽으면 팔이 기록기를 거쳐 `TypeError`로 죽거나 `ext` 없이 A0로 돈다.
_RETRIEVE = Memory.retrieve


def make_retrieve(scorer, theta, full=False):
    """
    팔 하나의 `retrieve`. **점수식을 들고 있지 않다** — `memory.py`의 4단계 함수를
    그대로 부르고 3단계 `rel`과 그 척도의 θ만 `M.ExtRel`로 꽂는다. τ 하드 게이트 ·
    θ 컷(과 그 위치 스위치 `THETA_ON_SCORE`) · 가중합 · recency(`W_REC`) · 동점 규약 ·
    상위 K 절단은 전부 프로덕션의 그 줄들이다.

    🔄 w6code (docs/17 축-1) — 여기 있던 것은 그 4단계의 **사본**이었다. 이제 등가는 논증이 아니라
       **구조**다 — 같은 함수다. `test_engine_arms.py`가 A0 채점기를 이 경로로 꽂은 결과가 프로덕션과
       스위치 셋 모두에서 바이트 같음을 확인한다.
    """
    def retrieve(self, chat_id, query, now_seq):
        return _RETRIEVE(self, chat_id, query, now_seq,
                         ext=M.ExtRel(scorer.rels, theta, full))
    return retrieve


# ══════════════════════════════════════════════════════════════════════
# 6. 실행 도우미 — 격자 하니스(V2)와 순위만(V1)
# ══════════════════════════════════════════════════════════════════════

def env_and_docs():
    """격자와 **같은 재료**(eval). `retrieval_sweep`의 `run_cell`이 받는 그 env다."""
    corpus, ledger, qs = P.load()
    key_of = P.key_index(ledger)
    scored, excluded = P.partition(qs, key_of)
    docs = RD.population()[1]
    return (corpus, ledger, qs, scored, key_of), docs, excluded


def cell_for(gate, theta):
    return RS.Cell(0, 1, gate, "lexical", 0.80, theta, None, M.W_REL, M.W_IMP,
                   M.SURFACED_PENALTY)


def run_arm(env, arm, gate, scorer=None):
    """
    한 팔을 격자 하니스로 돌린다. 지표 함수는 전부 `precision.py`의 것이다.
    A0는 프로덕션 `retrieve` 그대로 돈다(바꿔 끼우지 않는다) — 그래야 A0가 격자와 같은지를 볼 수 있다.
    """
    orig_retrieve = Memory.retrieve
    orig_gate = Memory.gate
    try:
        if arm.key != "A0":
            Memory.retrieve = make_retrieve(scorer or arm.scorer, arm.theta)
        tot = RS.run_cell(env, cell_for(gate, arm.theta), None)
    finally:
        Memory.retrieve = orig_retrieve
        Memory.gate = orig_gate
    assert Memory.retrieve is orig_retrieve, "retrieve 복원 실패 (G13)"
    return tot


def metric_row(tot):
    """**분모를 값에서 떼지 않는다** (G15) — 전부 `(분자, 분모)` 쌍으로 든다."""
    return dict(
        recall=(tot["ev_hit"], tot["ev_tot"]),
        mis=tot["mis"],
        pooled=(tot["ret"] - tot["mis"], tot["ret"]),
        top1=(tot["top1"], tot["top1_n"]),
        ties=len(tot["ties"]),
        gate=(tot["gate_pass"], tot["gate_pass"] + tot["gate_block"]),
        tok_p50=tot["tok_p50"],
        bc_p50=tot["bc_p50"], bc_p95=tot["bc_p95"],
        degraded=tot["degraded"], hard=tot["hard"], trap=tot["trap"],
    )


def recall_at_k(arm, env, ks=(1, 3, 5, 10)):
    """`rank_all`이 남긴 순위로 센 recall@k (eval 18문항 · 게이트 무시). w6code 지문이 읽는다."""
    corpus, ledger, qs, scored, key_of = env
    out = {}
    for k in ks:
        hit = tot = 0
        for q in scored:
            allowed = set(arm.ranked[q["id"]][:k])
            ev = [e for e in q.get("evidence", []) if e in key_of]
            hit += sum(1 for e in ev if key_of[e] & allowed)
            tot += len(ev)
        out[k] = (hit, tot)
    return out


def rank_all(arm, docs, env):
    """
    팔의 rel로 색인 전량을 4단계 함수로 **줄 세운다** (`full=True` — 상위 K로 자르지 않는다).
    🔄 w6code (docs/17 축-1) — 둘째 점수식 사본을 걷고 `make_retrieve`와 같은 함수를 부른다.
    ⚠️ 이것은 V1이 아니다 — τ·θ·가중합을 지난 순위다. V1(관련도만)은 `v1_expected`가 센다.
    """
    corpus, ledger, qs, scored, key_of = env
    arm.ranked, arm.rels = {}, {}
    tmp = tempfile.mkdtemp(prefix="engine_rank_")
    m = None
    try:
        m = Memory(os.path.join(tmp, "rank.db"))
        seed(m)
        ingest(m, corpus, ledger, timed=False)
        rows = [dict(r) for r in m.db.execute(
            "SELECT event_id, summary, importance, emotional_weight, surfaced_count"
            " FROM event WHERE chat_id=? AND user_deleted=0", (CHAT,)).fetchall()]
        assert [r["summary"] for r in rows] == list(docs), \
            "색인 순서가 `rel_dist.population()`과 다르다 — θ 유도 모집단이 갈린다"
        last = corpus[-1]["seq"]
        for q in scored:
            arm.rels[q["id"]] = arm.scorer.rels(q["ask"], docs)
            hits, _ = make_retrieve(arm.scorer, arm.theta, full=True)(
                m, CHAT, q["ask"], last)
            arm.ranked[q["id"]] = [r["summary"] for _, r in hits]
    finally:
        if m is not None:
            m.db.close()
        shutil.rmtree(tmp, ignore_errors=True)
    return rows


# ── V1 — 관련도 순위만, 동점은 기대값 ────────────────────────────────────

def tie_groups(rels):
    """값 내림차순의 서로 다른 값과 그 계수. 정렬 키에 부호를 쓰지 않는다(`reverse`)."""
    cnt = Counter(rels)
    return sorted(cnt, reverse=True), cnt


def hit_prob(rels, groups, pos, k):
    """
    근거 하나(그 문자열을 가진 행 위치 `pos`)가 상위 k에 들 **확률** — 동점 묶음 안 순서는 무작위.
    `Fraction`으로 센다: 같은 유리수는 같은 값이어야 부호검정의 동률이 부동소수 잡음으로 안 깨진다.
    """
    if not pos:
        return Fraction(0)
    vals, cnt = groups
    cum = 0
    for v in vals:
        c = cnt[v]
        if cum + c >= k:
            if any(rels[i] > v for i in pos):
                return Fraction(1)
            m = sum(1 for i in pos if rels[i] == v)
            if not m:
                return Fraction(0)
            s = k - cum
            return 1 - Fraction(math.comb(c - m, s), math.comb(c, s))
        cum += c
    return Fraction(1)                      # 행이 k개보다 적다 — 전부 든다


def v1_expected(rels, ev_pos, ks=KS):
    """한 문항: `{k: (기대 적중 합, 근거 수)}`. 근거 수 = 색인 키가 있는 근거(격자와 같은 분모)."""
    g = tie_groups(rels)
    return {k: (sum((hit_prob(rels, g, p, k) for p in ev_pos), Fraction(0)), len(ev_pos)) for k in ks}


def boundary_tie(rels, k):
    """상위 k 경계가 동점 묶음을 가르는가 — 가르면 기대값이 무작위를 품는다(서술용)."""
    vals, cnt = tie_groups(rels)
    cum = 0
    for v in vals:
        if cum + cnt[v] >= k:
            return cum + cnt[v] > k and cum < k
        cum += cnt[v]
    return False


def order_signature(rels):
    """«순위 같음»의 대상 — 값 내림차순 동점 묶음의 행 집합 열. 값 자체는 안 본다."""
    by = {}
    for i, v in enumerate(rels):
        by.setdefault(v, []).append(i)
    return [tuple(by[v]) for v in sorted(by, reverse=True)]


# ── 판정 ────────────────────────────────────────────────────────────────

def judge(arm_vals, anchor_vals, better="high"):
    """
    문항별 쌍 → `(이김, 짐, 동률, p, 최소 달성 p, 판정)`. 부호검정은 `probe_types.sign_test`(작을수록
    좋다)를 부른다 — 높을수록 좋은 지표는 부호를 뒤집어 넘긴다. 판정 셋이 모든 관측을 나눈다(`DECISION`).
    """
    a = [-x for x in arm_vals] if better == "high" else list(arm_vals)
    b = [-x for x in anchor_vals] if better == "high" else list(anchor_vals)
    win, loss, tie, p = sign_test(a, b)
    n = win + loss
    min_p = min(1.0, 2 * 0.5 ** n) if n else 1.0
    if n < MIN_N:
        verdict = V_WEAK
    elif p < ALPHA:
        verdict = V_UP if win > loss else V_DOWN
    else:
        verdict = V_NULL
    return win, loss, tie, p, min_p, verdict


# ══════════════════════════════════════════════════════════════════════
# 7. 코퍼스 한 열
# ══════════════════════════════════════════════════════════════════════

def _distractor_as_text(q):
    """
    eval3의 `distractor`는 **id 목록**이다(eval·eval2는 산문 문자열). `precision.distractor_ids`는
    문자열에서 X-id를 정규식으로 뽑으므로 목록을 공백으로 이은 문자열로 **복사본에만** 바꿔 넘긴다.
    원본 YAML은 안 건드린다(A8). 바꾸지 않으면 격자 하니스가 `hard` 계산에서 TypeError로 죽는다.
    """
    d = q.get("distractor")
    return dict(q, distractor=" ".join(d)) if isinstance(d, list) else q


class Column:
    """코퍼스 한 열 — 색인 · 문항 · 분할 · 홀드아웃 접근기."""

    def __init__(self, name, tmp, idx):
        import eval3_probe as E3                   # 코퍼스 등록의 정본(열 이름 = 그 키)
        self.name = name
        corpus, ledger, qs = E3.load(name)
        qs = [_distractor_as_text(q) for q in qs]
        key_of = P.key_index(ledger)
        scored, self.excluded = P.partition(qs, key_of)
        self.env = (corpus, ledger, qs, scored, key_of)
        self.scored, self.key_of = scored, key_of
        self.last = corpus[-1]["seq"]
        self.m = Memory(os.path.join(tmp, f"col{idx}.db"))
        seed(self.m)
        ingest(self.m, corpus, ledger, timed=False)
        # 살아 있는 색인 — `retrieve`의 SELECT와 같은 조건 · 같은 순서(rowid)
        self.docs = tuple(r["summary"] for r in self.m.db.execute(
            "SELECT summary FROM event WHERE chat_id=? AND user_deleted=0", (CHAT,)))
        self.train, ho = SE.split_blind([q["id"] for q in scored])
        self.ho_ids = tuple(ho)
        self.ho = SE.Holdout(ho, HO_BUDGET_PER_COL)
        pos = {}
        for i, d in enumerate(self.docs):
            pos.setdefault(d, []).append(i)
        self.ev_pos = {q["id"]: [sorted(i for s in key_of[e] for i in pos.get(s, []))
                                 for e in q.get("evidence", []) if e in key_of]
                       for q in scored}
        self.asks = {q["id"]: q["ask"] for q in scored}

    def n_ev(self, ids):
        return sum(len(self.ev_pos[i]) for i in ids)

    def close(self):
        self.m.db.close()


# ══════════════════════════════════════════════════════════════════════
# 8. 절 — 사전 등록 출력 (값 전)
# ══════════════════════════════════════════════════════════════════════

def print_prereg(arms, cols_meta):
    title("§0. 🔴 사전 등록 — 요인 표 · 두 보기 · 판정 규칙 · 홀드아웃 (**값을 하나도 보기 전에**)")
    print("\n  요인 표 — 각 팔의 셋. 앵커와 **정확히 한 요인만** 다르다 (`summary_ablation.FactorRule`이 종료 코드로 집행)\n")
    hdr = ("팔", "분석기", "관련도 식", "구현", "앵커 ← 움직인 요인")
    wid = (4, 46, 26, 46, 18)
    print("  " + "".join(h.ljust(w) for h, w in zip(hdr, wid)))
    print("  " + "-" * sum(wid))
    for a in arms:
        cells = (a.key, a.analyzer, a.ranking, a.impl,
                 f"{a.anchor} ← {a.moved}" if a.anchor else "— (앵커)")
        print("  " + "".join(str(c).ljust(w) for c, w in zip(cells, wid)))
    fr = SA.FactorRule()
    with engine_factors():
        print("\n  🔴 화살표 — 한 요인 사슬에만 (표로 박았다 · `ArrowRule`이 다시 확인)")
        for k1, k2 in ARROWS:
            print(f"     → {k1} → {k2}   움직인 요인: {fr.diff(arms, k1, k2)}")
        print("\n  ⛔ 화살표를 그리지 않는 쌍 — 요인이 둘 이상 다르다 (`FactorRule.diff`)")
        keys = [a.key for a in arms]
        for i, k1 in enumerate(keys):
            for k2 in keys[i + 1:]:
                if (k1, k2) not in ARROWS:
                    d = fr.diff(arms, k1, k2)
                    print(f"     ⛔ {k1} ↔ {k2} — 다른 요인 {len(d)}개: {d}")
    print("\n  🔴 종합 대조 (제품 소유자의 물음) — 부호검정은 하되 **귀속 없음 · 화살표 없음**")
    for k1, k2 in TOTAL_PAIRS:
        print(f"     ⊘ {k1} ↔ {k2}")

    print("\n  두 보기")
    print(f"     V1 순위만 (주 판정) — τ·θ·가중치 없이 관련도로 살아 있는 색인 **전 행**을 줄 세운다. recall@{list(KS)}, "
          f"**판정은 k={JUDGE_K}**")
    print(f"        동점: {V1_TIE_RULE}")
    print("     V2 파이프라인 — `retrieval_sweep.run_cell`(G3 게이트 · `build_context`) + 정본 4단계(`ExtRel`로 rel·θ만)."
          f" 지표는 격자의 것(`{P.RECALL_NAME}` @TOP_K · pooled 정밀도 · top1 오주입 · 오주입 · 1위 동점)")
    print(f"        정규화: {V2_NORM_RULE}")
    print(f"        θ: {THETA_RULE}")
    print(f"     BM25 k1={BM25_K1} · b={BM25_B} — **튜닝 안 한다** (Lucene 기본값 · 모든 BM25 팔 공통)")
    print(f"     nori 색인 분석기 {NORI_ANALYZER} · 사용자 사전 {NORI_USER_DICT!r} · VCP 필터 팔 없음")

    print("\n  판정 규칙 — 코퍼스 열마다 · 화살표 쌍(과 종합 둘)마다 · **홀드아웃 문항별** 부호검정 (팔 − 앵커 · 동률 버림 · 양측 정확)")
    for name, rule in DECISION:
        print(f"     {name:<12} {rule}")
    print("     → 세 경우가 **모든 관측을 나눈다** — 어느 결과도 한쪽으로만 떨어지지 않는다.")
    print("     판정 지표: " + " · ".join(f"{v} {what} ({'높을수록' if b == 'high' else '낮을수록'} 좋다)" for v, what, b in JUDGED))
    n_tests = len(cols_meta) * (len(ARROWS) + len(TOTAL_PAIRS)) * len(JUDGED)
    print(f"     다중 검정 보정 **없음** — 검정 {n_tests}개(열 {len(cols_meta)} × 쌍 {len(ARROWS) + len(TOTAL_PAIRS)} × 지표 {len(JUDGED)})."
          " «힘 있는 검정» 수를 끝에 찍는다. 홀로 선 p < 0.05는 약하게 읽는다.")

    print("\n  각 조건이 어떤 관측으로 참/거짓이 되는가")
    conds = (
        ("P1 분석기 재현", "모든 열의 모든 살아 있는 행·채점 문항에서 set(terms_pgbigm(t)) == show_bigm(t)",
         "한 건이라도 다르다 → B2→B3 화살표를 거둔다(두 요인)"),
        ("P2 nori 항", "모든 행에서 C1 토큰 계수 == 색인 항 빈도(`_mtermvectors`) · 색인 `sum_ttf` == C1 토큰 합",
         "한 건이라도 다르다 → C1→C2 화살표를 거둔다"),
        ("P3 B3 = B2", f"값: 모든 (채점 문항 × 행) 쌍 |B3 − B2| ≤ {TOL_PG_ABS:g} · 순위: 모든 문항의 동점 묶음 열이 같다",
         "어느 하나라도 다르다 → **그 차이가 결과**(구현 요인이 값/순위를 움직였다)"),
        ("P4 C1 vs C2", f"값: 모든 쌍 |C1 − C2| ≤ {TOL_OS_REL:g}·max(1,|C1|) · 순위: P3과 같은 정의",
         "다르다 → 그 크기와 원인(길이 손실 부호화 · N 세는 법 · float32)을 찍는다"),
        ("G16", f"착수·마감에 {G16_DEFAULTS} · `Memory.retrieve` 복원", "다르다 → 종료 1"),
        ("A0 등가", "열마다 V2 A0(프로덕션 `retrieve`) 문항 행 == A0 채점기를 `ExtRel`로 꽂은 행 · eval은 `retrieval_sweep.BASE_EXPECT`와도",
         "다르다 → 종료 1 (팔 경로가 정본이 아니다)"),
        ("홀드아웃", f"열마다 여는 곳 {HO_OPENS} — 예산 {HO_BUDGET_PER_COL}", "초과 → 종료 1 (`scorer_eval.Holdout.audit`)"),
    )
    for name, t, f in conds:
        print(f"     {name:<14} 참 : {t}")
        print(f"     {'':<14} 거짓: {f}")

    print("\n  홀드아웃 — 실험 26의 분할 함수를 **재사용**(`scorer_eval.split_blind` · sha1(문항 id) 마지막 비트 · 라벨을 안 본다)")
    for name, n_sc, n_tr, n_ho in cols_meta:
        power = ("✅ 방향을 낼 수 있다" if n_ho >= MIN_N else
                 f"🔴 **구조적으로 판정 불가** — 동률이 0이어도 최소 p = {2 * 0.5 ** n_ho:.4f} ≥ {ALPHA}")
        print(f"     {name:<18} 채점 {n_sc:>2} → 훈련 {n_tr:>2} · 홀드아웃 {n_ho:>2}   {power}")
    print("     ⚠️ 이 줄은 값이 아니라 **문항 수**다 — 값 보기 전에 «어느 열이 판정을 낼 수 있는가»가 정해진다.")

    print("\n  🔴 이 실험이 말할 수 없는 것")
    for s in CANNOT_SAY:
        print(f"     · {s}")


# ══════════════════════════════════════════════════════════════════════
# 9. 표 — 열 제목에 코퍼스 이름 · 항목 집합 · 채점기 (`TitleRule`)
# ══════════════════════════════════════════════════════════════════════

TITLE_BAD = []          # 모든 표의 `TitleRule` 위반 — 끝에서 종료 1


def table(caption, cols, rows, cw=20):
    """`cols`: `summary_prototype.Col` 목록(열 = 코퍼스). `rows`: `(행 라벨, [칸…])`. 규칙 위반은 모은다."""
    rule = SP.TitleRule()
    bad = rule.audit(cols) + rule.audit_rows([r[0] for r in rows])
    TITLE_BAD.extend(f"«{caption}» {b}" for b in bad)
    print(f"\n  {caption}")
    print("  " + "팔".ljust(30) + "".join(c.name[:cw - 1].ljust(cw) for c in cols))
    print("  " + "-" * (30 + cw * len(cols)))
    for lab, cells in rows:
        print("  " + lab[:29].ljust(30) + "".join(str(x)[:cw - 1].ljust(cw) for x in cells))
    for c in cols:
        print(f"     · {c.title()}")


def fx(fr, digits=2):
    return f"{float(fr):.{digits}f}"


# ══════════════════════════════════════════════════════════════════════
# 10. 본 실행
# ══════════════════════════════════════════════════════════════════════

def g16_state():
    return {k: getattr(M, k) for k in G16_DEFAULTS}


def build_engines(col, idx, ok_os, ok_pg):
    """열마다 엔진 색인을 만든다 → `{팔 키: 채점기}`와 엔진 손잡이."""
    eng = {"pg": None, "os": None}
    sc = {"A0": PyScorer(terms_bigram, rank_coverage),
          "A1": PyScorer(terms_bigram, BM25),
          "B1": PyScorer(terms_pgbigm, rank_coverage),
          "B2": PyScorer(terms_pgbigm, rank_overlap_max)}
    if ok_pg:
        eng["pg"] = PgGinScorer(f"w7_c{idx}", col.docs)
        sc["B3"] = eng["pg"]
    if ok_os:
        eng["os"] = OsNori(f"memarch-w7-c{idx}", col.docs)
        eng["os"].warm(list(col.docs) + list(col.asks.values()) + [RS.TRAP_UTTERANCE])
        sc["C1"] = PyScorer(eng["os"].analyze, BM25)
        sc["C2"] = OsScorer(eng["os"])
    return sc, eng


def analyzer_checks(col, sc, eng):
    """P1 · P2 — 라벨을 안 보는 대조. 결과 dict."""
    res = {}
    if eng["pg"] is not None:
        srv_docs = eng["pg"].show_bigm_docs()
        texts = list(col.asks.values())
        srv_q = eng["pg"].show_bigm_texts(texts)
        bad = [(d, sorted(s ^ set(terms_pgbigm(d)))) for d, s in zip(col.docs, srv_docs)
               if s != set(terms_pgbigm(d))]
        bad += [(t, sorted(srv_q[t] ^ set(terms_pgbigm(t)))) for t in texts if srv_q[t] != set(terms_pgbigm(t))]
        res["P1"] = dict(n=len(col.docs) + len(texts), bad=len(bad), ex=bad[:3])
        eng["pg"].prefetch(list(col.asks.values()))
        res["plan"] = eng["pg"].plan_nodes(next(iter(col.asks.values())))
    if eng["os"] is not None:
        tv, fst = eng["os"].termvectors()
        mine = [Counter(eng["os"].analyze(d)) for d in col.docs]
        bad = [(col.docs[i], dict(mine[i]), tv[i]) for i in range(len(col.docs)) if dict(mine[i]) != tv[i]]
        res["P2"] = dict(n=len(col.docs), bad=len(bad), ex=bad[:3],
                         sum_ttf=(fst or {}).get("sum_ttf"), mine_ttf=sum(sum(c.values()) for c in mine),
                         doc_count=(fst or {}).get("doc_count"), mine_nonempty=sum(1 for c in mine if c),
                         n_docs=len(col.docs))
    return res


def rels_all(col, scorer, ids):
    return {i: scorer.rels(col.asks[i], col.docs) for i in ids}


# 🆕 사후 진단(값을 보고 더했다 · 사전 등록 아님) — OpenSearch 2.19.6이 BM25에 곱하는 질의 boost.
#    `explain`이 `boost 2.2`를 찍는다. P4의 «값» 대조는 사전 등록대로 이것 없이 하고, 이것으로 나눈
#    대조는 «남는 차이가 무엇인가»를 보려는 별도 줄이다.
OS_BM25_BOOST = BM25_K1 + 1


def impl_compare(col, a, b, rel_tol=None, abs_tol=None, scale=1.0):
    """P3/P4 — 두 채점기의 값·순위를 **모든 채점 문항**에서 대조(라벨 무관 — 홀드아웃을 안 연다).
    `scale`은 `b`의 값을 나눌 상수(사후 진단 전용 · 기본 1 = 사전 등록 대조)."""
    worst, over, pairs, order_diff, top_diff = 0.0, 0, 0, 0, 0
    for qid, ask in col.asks.items():
        x, y = a.rels(ask, col.docs), [v / scale for v in b.rels(ask, col.docs)]
        for u, v in zip(x, y):
            d = abs(u - v)
            lim = abs_tol if abs_tol is not None else rel_tol * max(1.0, abs(u))
            worst = max(worst, d)
            over += d > lim
            pairs += 1
        sx, sy = order_signature(x), order_signature(y)
        order_diff += sx != sy
        # 상위 10행 앞머리(경계 묶음까지)만 다른가 — 순위 차이가 V1 recall@≤10에 닿을 수 있는 자리
        cut_x, cut_y, acc = [], [], 0
        for g in sx:
            cut_x.append(g)
            acc += len(g)
            if acc >= max(KS):
                break
        acc = 0
        for g in sy:
            cut_y.append(g)
            acc += len(g)
            if acc >= max(KS):
                break
        top_diff += cut_x != cut_y
    return dict(worst=worst, over=over, pairs=pairs, order_diff=order_diff, top_diff=top_diff,
                n_q=len(col.asks))


def derive_thetas(col, arms, v2sc):
    """V2 θ — 훈련 분할 × 살아 있는 행. A0 실제 컷 f를 다른 팔에 옮긴다(`rel_dist` import)."""
    out = {}
    pop = {a.key: [v for i in col.train for v in v2sc[a.key].rels(col.asks[i], col.docs)]
           for a in arms}
    a0 = pop["A0"]
    f = RD.actual_cut(a0, M.THETA_RELEVANCE)
    for a in arms:
        th = M.THETA_RELEVANCE if a.key == "A0" else RD.theta_at(pop[a.key], f)
        out[a.key] = (th, f, RD.actual_cut(pop[a.key], th), len(pop[a.key]))
    return out


def rows_sha(tot):
    return hashlib.sha256(json.dumps(tot["rows"], ensure_ascii=False, sort_keys=True,
                                     default=str).encode("utf-8")).hexdigest()


def run_column(col, idx, arms_proto, ok_os, ok_pg, report):
    """한 열의 V1·V2 전부. 반환 `report[col.name]`에 쌓는다."""
    arms = [EngineArm(*s) for s in ARM_SPECS]
    mark_skips(arms, ok_os, ok_pg)
    live = [a for a in arms if not a.skipped]
    sc, eng = build_engines(col, idx, ok_os, ok_pg)
    rep = report.setdefault(col.name, {"arms": arms})
    try:
        rep["checks"] = analyzer_checks(col, sc, eng)
        if eng["pg"] is not None:
            rep["P3"] = impl_compare(col, sc["B2"], sc["B3"], abs_tol=TOL_PG_ABS)
        if eng["os"] is not None:
            rep["P4"] = impl_compare(col, sc["C1"], sc["C2"], rel_tol=TOL_OS_REL)
            rep["P4s"] = impl_compare(col, sc["C1"], sc["C2"], rel_tol=TOL_OS_REL, scale=OS_BM25_BOOST)
            # UBIQUITOUS 절의 재료(라벨 무관) — nori 토큰의 df
            sc["C1"].fit(col.docs)
            rep["nori_stats"] = sc["C1"].stats
        sc["A1"].fit(col.docs)
        rep["bigram_stats"] = sc["A1"].stats

        # ── V1: 모든 채점 문항의 기대 적중(값은 담아 두고, 훈련/홀드아웃으로 갈라 찍는다) ──
        v1, ties = {}, {}
        for a in live:
            per = {}
            nb = 0
            for q in col.scored:
                r = sc[a.key].rels(q["ask"], col.docs)
                per[q["id"]] = v1_expected(r, col.ev_pos[q["id"]])
                nb += boundary_tie(r, JUDGE_K)
            v1[a.key], ties[a.key] = per, nb
            a.ran = True
        rep["v1"], rep["v1_ties"] = v1, ties

        # ── V2: θ 유도(훈련) → 격자 하니스 ──
        v2sc = {a.key: (MaxNormalized(sc[a.key]) if a.ranking == F_BM25 else sc[a.key]) for a in live}
        rep["theta"] = derive_thetas(col, live, v2sc)
        v2 = {}
        saved_root = RS.ROOT
        tmp = tempfile.mkdtemp(prefix="w7_v2_")
        os.makedirs(os.path.join(tmp, "prototype"))
        RS.ROOT = tmp                                  # 격자 하니스의 임시 DB를 %TEMP%로(prototype/에 안 남긴다)
        try:
            for a in live:
                a.theta = rep["theta"][a.key][0]
                v2[a.key] = run_arm(col.env, a, RS.GATES[0], scorer=v2sc[a.key])
            # A0 등가 — 같은 A0 채점기를 팔 경로(ExtRel)로 꽂는다
            probe = EngineArm(*ARM_SPECS[0])
            probe.key = "A0·ext"
            probe.theta = M.THETA_RELEVANCE
            rep["a0_ext"] = run_arm(col.env, probe, RS.GATES[0], scorer=PyScorer(terms_bigram, rank_coverage))
        finally:
            RS.ROOT = saved_root
            shutil.rmtree(tmp, ignore_errors=True)
        assert RS.ROOT is saved_root
        rep["v2"] = v2
    finally:
        for e in eng.values():
            if e is not None:
                e.close()
    return rep


# ── 출력 절들 ─────────────────────────────────────────────────────────────

def col_obj(col, ids, scorer_name, which):
    return SP.Col(col.name, f"{which} {len(ids)}문항 · 근거 {col.n_ev(ids)}", f"색인 {len(col.docs)}행", scorer_name)


def v1_cells(rep, key, ids, k):
    v = rep["v1"].get(key)
    if v is None:
        return "SKIP"
    s = sum((v[i][k][0] for i in ids), Fraction(0))
    n = sum(v[i][k][1] for i in ids)
    return f"{fx(s)}/{n}"


def print_v1(cols, report, which):
    """V1 표 — `which`는 «훈련»(자유) 또는 «홀드아웃»(각 열의 `Holdout.open`을 거친 ids)."""
    for k in KS:
        tcols, rows = [], []
        ids_of = {}
        for c in cols:
            ids = c.train if which == "훈련" else report[c.name]["ho_v1"]
            ids_of[c.name] = ids
            tcols.append(col_obj(c, ids, f"V1 recall@{k} 기대 적중/근거", which))
        for s in ARM_SPECS:
            rows.append((EngineArm(*s).short(), [v1_cells(report[c.name], s[0], ids_of[c.name], k) for c in cols]))
        table(f"V1 순위만 · {which} · recall@{k}{' ← 판정 k' if k == JUDGE_K else ''}", tcols, rows)


def v2_subset(tot, ids):
    rows = [r for r in tot["rows"] if r["id"] in set(ids)]
    t = P.cell_totals(rows)
    return t, rows


def print_v2(cols, report, which):
    metrics = (("recall", "근거 적중/근거"), ("mis", "오주입 항목"), ("pooled", "정밀도(검색 항목)"),
               ("top1", "top1 오주입/검색≥1 문항"))
    for mk, mname in metrics:
        tcols, rows = [], []
        ids_of = {c.name: (c.train if which == "훈련" else report[c.name]["ho_v2"]) for c in cols}
        for c in cols:
            tcols.append(col_obj(c, ids_of[c.name], f"V2 {mname}", which))
        for s in ARM_SPECS:
            cells = []
            for c in cols:
                tot = report[c.name]["v2"].get(s[0])
                if tot is None:
                    cells.append("SKIP")
                    continue
                t, rows_ = v2_subset(tot, ids_of[c.name])
                if mk == "recall":
                    cells.append(f"{t['ev_hit']}/{t['ev_tot']}")
                elif mk == "mis":
                    cells.append(f"{t['mis']}")
                elif mk == "pooled":
                    cells.append(f"{t['ret'] - t['mis']}/{t['ret']}")
                else:
                    cells.append(f"{t['top1']}/{t['top1_n']}" if t["top1_n"] else "정의 안 됨(0)")
            rows.append((EngineArm(*s).short(), cells))
        table(f"V2 파이프라인 · {which} · {mname}", tcols, rows)


def print_judgements(cols, report):
    """홀드아웃 부호검정 — 화살표 여섯 + 종합 둘 × 판정 지표 셋. 칸 = `판정 (이김/짐/동률 · p)`."""
    out = {}
    pairs = [(a, b, "→") for a, b in ARROWS] + [(a, b, "⊘") for a, b in TOTAL_PAIRS]
    for view, what, better in JUDGED:
        tcols = [col_obj(c, report[c.name]["ho_v1" if view == "V1" else "ho_v2"],
                         f"{view} {what} 부호검정", "홀드아웃") for c in cols]
        rows = []
        for anc, arm, mark in pairs:
            cells = []
            for c in cols:
                rep = report[c.name]
                ids = rep["ho_v1"] if view == "V1" else rep["ho_v2"]
                if view == "V1":
                    va, vb = rep["v1"].get(arm), rep["v1"].get(anc)
                    if va is None or vb is None:
                        cells.append("SKIP")
                        continue
                    xa = [va[i][JUDGE_K][0] / max(va[i][JUDGE_K][1], 1) for i in ids]
                    xb = [vb[i][JUDGE_K][0] / max(vb[i][JUDGE_K][1], 1) for i in ids]
                else:
                    ta, tb = rep["v2"].get(arm), rep["v2"].get(anc)
                    if ta is None or tb is None:
                        cells.append("SKIP")
                        continue
                    fld = "ev_hit" if better == "high" else "mis"
                    da = {r["id"]: r[fld] for r in ta["rows"]}
                    db = {r["id"]: r[fld] for r in tb["rows"]}
                    xa, xb = [da[i] for i in ids], [db[i] for i in ids]
                w, l, t, p, mp, v = judge(xa, xb, better)
                out[(c.name, view, what, anc, arm)] = (w, l, t, p, mp, v)
                cells.append(f"{SHORT_V[v]} {w}/{l}/{t} p={p:.3f}")
            lab = f"{anc}{mark}{arm}" + ("" if mark == "→" else " 종합")
            rows.append((lab, cells))
        table(f"판정 · {view} · {what} · 칸 = 판정 이김/짐/동률 p (홀드아웃) · "
              f"{' · '.join(f'{b}={a}' for a, b in SHORT_V.items())}", tcols, rows, cw=24)
    return out


def main(argv=None):
    import eval3_probe as E3
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpora", default=",".join(E3.NAMES),
                    help="쉼표 목록(열 이름 또는 0부터의 번호). 기본은 다섯 열 전부")
    ap.add_argument("--no-latency", action="store_true")
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)
    names = []
    for tok in args.corpora.split(","):
        tok = tok.strip()
        names.append(E3.NAMES[int(tok)] if tok.isdigit() else tok)
    unknown = [n for n in names if n not in E3.NAMES]
    if unknown:
        print(f"모르는 열: {unknown} — 가능한 것 {E3.NAMES}")
        return 2
    partial = names != list(E3.NAMES)

    bad = []                                   # 종료 1 사유
    g16_0 = g16_state()
    retrieve_0 = Memory.retrieve
    if g16_0 != G16_DEFAULTS:
        bad.append(f"G16 착수 — 기본값이 아니다: {g16_0}")

    arms0 = [EngineArm(*s) for s in ARM_SPECS]
    tmp = tempfile.mkdtemp(prefix="w7_cols_")
    cols = []
    try:
        for i, n in enumerate(names):
            cols.append(Column(n, tmp, i))
        print_prereg(arms0, [(c.name, len(c.scored), len(c.train), len(c.ho_ids)) for c in cols])
        if partial:
            print(f"\n  ⚠️ **부분 실행** — 열 {names}. 기록값이 아니다(docs/11에 옮기지 않는다).")

        # 요인 규칙 — 값 전
        with engine_factors():
            fbad = SA.FactorRule().audit(arms0)
        bad += [f"FactorRule {b}" for b in fbad]

        # ── §1 환경 ─────────────────────────────────────────────────
        title("§1. 환경 — 기반 이미지 · 플러그인 · 분석기가 **실제로** 무엇을 했나")
        ok_os, ok_pg, diag = probe_containers()
        for line in diag:
            print(line)
        skipped = mark_skips(arms0, ok_os, ok_pg)
        print(f"\n  G16 착수: {g16_0} {'✅' if g16_0 == G16_DEFAULTS else '🔴'}")
        if ok_os:
            print("\n  nori가 실제로 자른 것 (`_analyze` analyzer=nori · 응답 원문)")
            for t in ("나비가 아팠던 날", "나비를", "나비는", "사내 교육 정원은 40명입니다", "명이었죠",
                      "결제 API v2.4"):
                print(f"     {t:<24} → {EC.os_analyze(t)}")
            print("     ⚠️ `40명입니다` → `…명, 이` · `명이었죠` → `명, 이` — 긍정 지정사 `이`(VCP)가 기본 품사 필터 18종 밖이라"
                  " **기능어가 공유 항이 된다**(nori 기본값의 결함 · 이 실험은 그대로 둔다)")
        if ok_pg:
            rows = EC.psql("SELECT bigm_similarity('나비가 아팠던', '나비가 아프다'), "
                           "show_bigm('나비가 아팠던');")
            print(f"\n  pg_bigm 실동작 — bigm_similarity('나비가 아팠던','나비가 아프다') = {rows[0][0]} · "
                  f"show_bigm = {rows[0][1]}")
            A, B = set(terms_pgbigm("나비가 아팠던")), set(terms_pgbigm("나비가 아프다"))
            print(f"     파이썬 재현: ∩/max = {len(A & B)}/{max(len(A), len(B))} = {len(A & B) / max(len(A), len(B)):.6f} · "
                  f"자카드 = {len(A & B) / len(A | B):.6f}  ← 식은 ∩/max")
        print("\n  맥락(뒤집힌 전제 ①) — «IDF가 순위를 움직일 수 있는 문항» (`eval3_probe.movable` · docs/17 §9 정의)")
        for c in cols:
            mv = E3.movable([q["ask"] for q in c.scored], E3.df_of(c.docs))
            print(f"     {c.name:<18} {mv['movable']}/{len(c.scored)} (색인 {len(c.docs)}행)")
        if skipped:
            print(f"\n  ⏭️ 77-SKIP 팔: {skipped} — G1: SKIP은 통과가 아니다. 그 팔에 닿는 화살표는 거둔다.")

        # ── 열마다 실행 ───────────────────────────────────────────────
        report = {}
        for i, c in enumerate(cols):
            t0 = time.perf_counter()
            run_column(c, i, arms0, ok_os, ok_pg, report)
            print(f"\n  열 «{c.name}» 실행 {time.perf_counter() - t0:.1f} s")

        # ── §2 분석기 · 구현 대조 (라벨 무관) ──────────────────────────
        title("§2. 분석기 재현(P1 · P2)과 구현 요인(P3 B3=B2 · P4 C1 vs C2) — 라벨을 안 보는 대조")
        p1_ok = p2_ok = True
        for c in cols:
            ch = report[c.name].get("checks", {})
            print(f"\n  «{c.name}» (색인 {len(c.docs)}행 · 채점 {len(c.scored)}문항)")
            if "P1" in ch:
                p1 = ch["P1"]
                p1_ok &= p1["bad"] == 0
                print(f"     P1 show_bigm == terms_pgbigm : 불일치 {p1['bad']}/{p1['n']} "
                      f"{'✅' if not p1['bad'] else '🔴 ' + str(p1['ex'])}")
                print(f"        계획 노드 {ch['plan']}")
            if "P2" in ch:
                p2 = ch["P2"]
                ttf_same = p2["sum_ttf"] == p2["mine_ttf"]
                p2_ok &= p2["bad"] == 0 and ttf_same
                print(f"     P2 C1 토큰 == 색인 항 빈도   : 불일치 {p2['bad']}/{p2['n']} "
                      f"{'✅' if not p2['bad'] else '🔴 ' + str(p2['ex'])}")
                print(f"        sum_ttf 색인 {p2['sum_ttf']} · C1 {p2['mine_ttf']} {'✅' if ttf_same else '🔴'} · "
                      f"doc_count(항 ≥1) 색인 {p2['doc_count']} · C1 {p2['mine_nonempty']} / 전 행 {p2['n_docs']}")
            for key, lab in (("P3", "B3 = B2 (float4 · 절대 ≤ 1e-6)"), ("P4", "C1 vs C2 (상대 ≤ 1e-4)"),
                             ("P4s", f"(사후 진단) C1 vs C2÷{OS_BM25_BOOST:g}")):
                if key in report[c.name]:
                    r = report[c.name][key]
                    print(f"     {key} {lab}: 최대 |차| {r['worst']:.3g} · 허용 넘은 쌍 {r['over']}/{r['pairs']} · "
                          f"순위 묶음이 다른 문항 {r['order_diff']}/{r['n_q']} · 상위 10 머리가 다른 문항 {r['top_diff']}/{r['n_q']}")
        # P1·P2가 거짓이면 사전 등록대로 화살표를 거둔다 — 분석기 칸의 이름표를 실측으로 바꿔 FactorRule이 두 요인으로 읽게 한다
        withdrawn = []
        if not p1_ok:
            withdrawn.append(("B2", "B3", "P1 거짓 — 파이썬 재현이 서버 분석기와 다르다(두 요인)"))
        if not p2_ok:
            withdrawn.append(("C1", "C2", "P2 거짓 — C1 토큰이 색인 항과 다르다(두 요인)"))
        for k in skipped:
            for a, b in ARROWS:
                if k in (a, b):
                    withdrawn.append((a, b, f"«{k}» 77-SKIP — 돌지 않았다"))

        # ── §3 V1 ─────────────────────────────────────────────────────
        title("§3. 🔴 V1 순위만 (주 판정) — 코퍼스 열마다 · 열 제목에 코퍼스 이름 · 분모와 함께")
        print("  훈련 분할은 자유롭게 본다(아무것도 고르지 않는다). 홀드아웃은 `Holdout.open('V1 판정')` 한 번으로만 연다.")
        print_v1(cols, report, "훈련")
        for c in cols:
            report[c.name]["ho_v1"] = list(c.ho.open("V1 판정"))
        print_v1(cols, report, "홀드아웃")
        print("\n  경계 동점(상위 5 경계가 동점 묶음을 가르는 문항 수 · 채점 문항 전부 — 기대값이 무작위를 품는 자리)")
        for s in ARM_SPECS:
            print("     " + EngineArm(*s).short().ljust(30) + "".join(
                f"{report[c.name]['v1_ties'].get(s[0], 'SKIP')}/{len(c.scored)}".ljust(20) for c in cols))

        # ── §4 V2 ─────────────────────────────────────────────────────
        title("§4. 🔴 V2 파이프라인 — 정본 4단계 하나를 지난다 (G3 게이트 · τ · θ · 가중합 · 동점 · TOP_K)")
        print("  θ — 팔마다 **훈련 분할 × 살아 있는 행**에서 A0의 실제 컷 f를 옮긴다 (요청 f · 유도 θ · 실제 컷 · n)")
        for c in cols:
            print(f"\n  «{c.name}»")
            for k, (th, f, cut, n) in report[c.name]["theta"].items():
                print(f"     {k:<3} θ = {th:.6g}   요청 f = {f:.4f}   실제 컷 = {cut:.4f}   n = {n}"
                      + ("   (A0 — `THETA_RELEVANCE` 그대로)" if k == "A0" else ""))
        # A0 등가 — 홀드아웃을 여는 자리(값을 찍지는 않고 해시만 대조)
        print("\n  A0 등가 — 프로덕션 `retrieve`와 A0 채점기를 `ExtRel`로 꽂은 경로의 문항 행 sha256")
        for c in cols:
            c.ho.open("A0 등가")
            rep = report[c.name]
            a, b = rows_sha(rep["v2"]["A0"]), rows_sha(rep["a0_ext"])
            same = a == b
            if not same:
                bad.append(f"A0 등가 «{c.name}» — 팔 경로가 프로덕션과 다르다")
            print(f"     {c.name:<18} 프로덕션 {a[:16]}… · ExtRel {b[:16]}… {'✅ 같다' if same else '🔴 다르다'}")
        if "eval" in names:
            got = metric_row(report["eval"]["v2"]["A0"])
            want = RS.BASE_EXPECT
            cmp_ = {k: (got[k], want[k]) for k in want}
            same = all(x == y for x, y in cmp_.values())
            if not same:
                bad.append(f"A0 ≠ 격자 기준선 BASE_EXPECT: {cmp_}")
            print(f"     eval A0 V2 vs `retrieval_sweep.BASE_EXPECT` (채점 18문항 · 근거 28): "
                  f"{ {k: v[0] for k, v in cmp_.items()} } {'✅ 같다' if same else '🔴 다르다'}")
        print_v2(cols, report, "훈련")
        for c in cols:
            report[c.name]["ho_v2"] = list(c.ho.open("V2 판정"))
        print_v2(cols, report, "홀드아웃")

        # ── §5 판정 ────────────────────────────────────────────────────
        title("§5. 🔴 판정 — 홀드아웃 문항별 부호검정 · 한 요인 사슬에만 화살표 · 종합 둘은 귀속 없음")
        with engine_factors():
            arrows_ok = [(a, b) for a, b in ARROWS if (a, b) not in {(x, y) for x, y, _ in withdrawn}]
            for a in arms0:
                a.ran = a.key not in skipped
            abad = SA.ArrowRule().audit(arms0, arrows_ok)
        bad += [f"ArrowRule {b}" for b in abad]
        for a, b, why in withdrawn:
            print(f"  ⛔ 거둔 화살표 {a}→{b} — {why}")
        verdicts = print_judgements(cols, report)
        # 🆕 사후 서술(값을 보고 더했다 · 판정 아님 · 라벨 무관) — V2의 θ는 등컷 규칙으로 유도되지만 척도가 성기면
        #    실제 컷이 요청 f를 못 맞춘다. 화살표 두 팔의 실제 컷이 다르면 V2 차이에 «θ 눈금»이 섞인다.
        print("\n  (사후 서술 · 판정 아님) V2 화살표 두 팔의 **실제 컷**(훈련 × 살아 있는 행) — 다르면 V2 차이에 θ 눈금이 섞인다")
        for anc, arm in list(ARROWS) + list(TOTAL_PAIRS):
            cells = []
            for c in cols:
                th = report[c.name]["theta"]
                cells.append(f"{th[anc][2]:.4f}→{th[arm][2]:.4f}" if anc in th and arm in th else "SKIP")
            print("     " + f"{anc}→{arm}".ljust(10) + "".join(x.ljust(24) for x in cells))
        powered = sum(1 for v in verdicts.values() if v[5] != V_WEAK)
        dirs = [(k, v) for k, v in verdicts.items() if v[5] in (V_UP, V_DOWN)]
        print(f"\n  검정 {len(verdicts)}개 · 힘 있는 검정(n ≥ {MIN_N}) {powered}개 · 방향이 난 검정 {len(dirs)}개"
              f" · 보정 없이 α={ALPHA}에서 우연히 날 기대 수 ≈ {ALPHA * powered:.1f}")
        for (cn, view, what, anc, arm), v in dirs:
            pair = f"{anc}→{arm}" if (anc, arm) in ARROWS else f"{anc}⊘{arm} (종합 · 귀속 없음)"
            print(f"     {cn:<18} {view} {what:<34} {pair}: {v[5]} ({v[0]}/{v[1]}/{v[2]} · p={v[3]:.4f})")

        # ── §6 UBIQUITOUS ──────────────────────────────────────────────
        title("§6. `UBIQUITOUS`를 IDF가 대체하는가 — 라벨 무관 · 색인 통계만")
        tau = SC.UBIQUITOUS_PROVENANCE["tau"]
        print(f"  `scoring.UBIQUITOUS` = {sorted(SC.UBIQUITOUS)} — 생존 채점기(요약 층)의 손 목록이다. **검색 경로에는 목록이 없다.**")
        print(f"  같은 규칙(df/N ≥ {tau} — `UBIQUITOUS_PROVENANCE`)을 검색 색인(살아 있는 행)에 걸면 무엇이 편재 항인가,"
              " 그리고 BM25 idf가 그 항에 주는 무게는 얼마인가")
        for c in cols:
            rep = report[c.name]
            print(f"\n  «{c.name}» N = {len(c.docs)}")
            for lab, st, probe_t in (("현행 bigram (A1)", rep.get("bigram_stats"), "지우"),
                                     ("nori 토큰 (C1)", rep.get("nori_stats"), "지우")):
                if not st:
                    print(f"     {lab}: SKIP")
                    continue
                N, df = st["N"], st["df"]
                ub = sorted(t for t, d in df.items() if d / N >= tau)
                idf = {t: math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5)) for t in df}
                idf_max = math.log(1 + (N - 1 + 0.5) / 1.5)
                d_j = df.get(probe_t, 0)
                print(f"     {lab:<18} df/N ≥ {tau} 인 항 {len(ub)}개: {ub[:12]}"
                      f" · `{probe_t}` df {d_j}/{N} idf {idf.get(probe_t, float('nan')):.3f} (df=1의 idf {idf_max:.3f})")
        print("\n  → 읽는 법: IDF는 편재 항을 **없애지 않고 깎는다**(idf > 0). 목록은 코퍼스마다 색인에서 **저절로** 나온다 —")
        print("    손 목록 `{지우}`는 eval2(이름이 바뀐 코퍼스)에서 아무것도 안 했다(실험 31). 검색 정확도에 그 깎음이 무엇을")
        print("    했는지는 §5의 A0→A1(식) 화살표가 답한다 — 이 절은 그 무게만 보인다.")

        # ── §7 지연 ────────────────────────────────────────────────────
        if not args.no_latency:
            latency(cols, ok_os, ok_pg)

        # ── 마감 검사 ───────────────────────────────────────────────────
        title("§8. 종료 판정 — 규칙 위반만 종료 코드를 바꾼다 (판정의 방향 · «검출 안 됨» · 지연은 안 바꾼다)")
        for c in cols:
            hb = c.ho.audit()
            print(f"  홀드아웃 «{c.name}»: 연 곳 {c.ho.reads} · 총 {c.ho.total}/{c.ho.budget} "
                  f"{'✅' if not hb else '🔴 ' + str(hb)}")
            if hb:
                bad.append(f"홀드아웃 «{c.name}» {hb}")
        bad += TITLE_BAD
        g16_1 = g16_state()
        if g16_1 != G16_DEFAULTS or Memory.retrieve is not retrieve_0:
            bad.append(f"G16 마감 — {g16_1} · retrieve 복원 {Memory.retrieve is retrieve_0}")
        print(f"  G16 마감: {g16_1} · `Memory.retrieve` 복원 {Memory.retrieve is retrieve_0}")
        print(f"  FactorRule 위반 {len(fbad)} · ArrowRule 위반 {len(abad)} · TitleRule 위반 {len(TITLE_BAD)}")
        if bad:
            print("\n  🔴 규칙 위반 — 종료 1")
            for b in bad:
                print(f"     · {b}")
            return 1
        if skipped:
            print(f"\n  ⏭️ 종료 77 — 팔 {skipped}이 돌지 않았다. **통과가 아니다**(G1)")
            return EXIT_SKIP
        print("\n  ✅ 규칙 전부 통과 — 종료 0 (판정 내용은 §5)")
        return 0
    finally:
        for c in cols:
            c.close()
        shutil.rmtree(tmp, ignore_errors=True)


def latency(cols, ok_os, ok_pg):
    title("§7. 지연 — **서버 시간으로만** · p50/p95 · 판정에 안 쓴다 (실행마다 흔들린다)")
    print("  🔴 «같은 조건이 아니다»(F21): 엔진 행은 서버가 잰 시간(Postgres `EXPLAIN ANALYZE` Execution Time · OpenSearch `took`)이고,")
    print("     파이썬 행은 이 프로세스 안의 `perf_counter`다. 엔진은 역색인을 미리 지었고, A0 `retrieve`는 호출마다 SQLite 전량 스캔을 하되")
    print("     행 bigram은 내용 주소 메모에서 꺼낸다(w8 · 웜업이 채운다). 벽시계(엔진 왕복)는 **참고로만** 찍는다 — `docker exec psql` 벽시계 ≈217 ms vs 서버 1.6 ms(w6infra),")
    print("     벽시계로 판정하면 F38과 같은 거짓 판정이 난다.")
    targets = [c for c in cols if len(c.docs) >= 1000] or cols
    rng = random.Random(LAT_SEED)
    for c in targets:
        asks = [q["ask"] for q in c.scored] * LAT_REPS
        rng.shuffle(asks)
        seq = asks[:LAT_WARMUP] + asks
        n = len(asks)
        print(f"\n  «{c.name}» 색인 {len(c.docs)}행 · n = {n} (워밍업 {LAT_WARMUP} 버림 · 채점 {len(c.scored)}문항 × {LAT_REPS})")
        res = []
        # A0 — 프로덕션 retrieve (in-process)
        ts = []
        for q in seq:
            t0 = time.perf_counter()
            c.m.retrieve(CHAT, q, c.last)
            ts.append((time.perf_counter() - t0) * 1000)
        res.append(("A0 `Memory.retrieve` (파이썬 · SQL 스캔+토큰화 포함)", ts[LAT_WARMUP:]))
        b2 = PyScorer(terms_pgbigm, rank_overlap_max)
        b2.fit(c.docs)
        ts = []
        for q in seq:
            t0 = time.perf_counter()
            b2.rels(q, c.docs)
            ts.append((time.perf_counter() - t0) * 1000)
        res.append(("B2 파이썬 rel 계산만 (문서 항 미리 자름)", ts[LAT_WARMUP:]))
        pg = osn = None
        try:
            if ok_pg:
                pg = PgGinScorer("w7_lat", c.docs)
                ms, nodes = pg.exec_ms(seq, force_gin=True)
                res.append((f"B3 Postgres 서버 실행 (GIN 강제 · 노드 {dict(nodes)})", ms[LAT_WARMUP:]))
                ms, nodes = pg.exec_ms(seq, force_gin=False)
                res.append((f"B3′ Postgres 서버 실행 (계획기 선택 · 노드 {dict(nodes)})", ms[LAT_WARMUP:]))
            if ok_os:
                osn = OsNori("memarch-w7-lat", c.docs)
                osn.warm(list(c.docs) + list(set(asks)))
                c1 = PyScorer(osn.analyze, BM25)
                c1.fit(c.docs)
                ts = []
                for q in seq:
                    t0 = time.perf_counter()
                    c1.rels(q, c.docs)
                    ts.append((time.perf_counter() - t0) * 1000)
                res.append(("C1 파이썬 BM25 rel 계산만 (nori 항 미리 받음)", ts[LAT_WARMUP:]))
                took, wall = [], []
                for q in seq:
                    a, b = osn.took_ms(q)
                    took.append(a)
                    wall.append(b)
                res.append(("C2 OpenSearch `took` (서버 · 정수 ms — 0은 «1 ms 미만»)", took[LAT_WARMUP:]))
                res.append(("  (참고 · 판정 안 씀) C2 벽시계 왕복", wall[LAT_WARMUP:]))
        finally:
            if pg is not None:
                pg.close()
            if osn is not None:
                osn.close()
        for lab, ts in res:
            print(f"     {lab:<64} p50 {RD.q_at(ts, 50):8.2f} ms   p95 {RD.q_at(ts, 95):8.2f} ms   n {len(ts)}")


if __name__ == "__main__":
    sys.exit(main())
