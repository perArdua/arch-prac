# -*- coding: utf-8 -*-
"""
eval3_probe.py — **규모 코퍼스(`eval3/`)에서 선행 조건을 잰다.** (LLM 0회 · ollama 0회 · `%TEMP%` DB)

## 왜 이 파일이 있나

`docs/17-gap-disposition.md`의 검B2(θ 스위치 격자) · 검B3(사전 토큰화) · 밖E10(표 밖 술어의
기본값)과 §9의 엔진 라운드가 **같은 선행**을 갖는다 — 색인이 21행뿐이라 잴 수 없다(검C1).
`eval3/`이 그 선행이고(색인 3,000행 × df 레짐 셋), 이 파일은 그 위에서 **조건만 잰다.**
θ 스위치를 켜지도, 엔진 라운드를 돌리지도 않는다.

## 🔴 무변경 규약 — 전부 import해서 그대로 부른다

    prototype/memory.py    : Memory.gate(함수 객체) · _recall_vocab · bigrams · coverage ·
                             PREDICATE_CARDINALITY · PREDICATE_STANDING · TAU_IMPORTANCE
    prototype/soak.py      : seed · ingest · CHAT
    experiments/corpus2_probe.py : gate_breakdown · gate_by_kind · past_ref_source ·
                             ubiquitous_effect · induce_ubiquitous · tie_cut · rescore_with ·
                             breakage · digests · score_all · invariants · frozen_only_examples ·
                             v2_only_examples · rel_population · tau_cut · instrument_coupling ·
                             index_rows · ledger_items   (실험 31의 계측기 — 그 형태 그대로)
    experiments/gate_saturation.py : VocabProbe (게이트 함수 객체에 어휘만 꽂는다 — 실험 29)
    experiments/retrieve_scaling.py: pct · template_rows · build_db · SQL_ONLY · N_CALLS ·
                             WARMUP · TRIGGER_MS · SEED
    experiments/precision.py : key_index · partition
    experiments/predicate_vocab_cost.py : doc14_table · DOC14
    experiments/rel_dist.py : actual_cut · theta_at
    eval3/gen_corpus3.py   : 사전 등록 상수 전부 · render_all (재생성 바이트 대조)

코퍼스를 가리키는 손잡이는 **경로뿐**이다(`CORPORA`). `eval/`·`eval2/`는 읽기만(A8).

⚠️ `corpus2_probe.build`를 **안 쓴다** — 그 함수는 DB를 `prototype/` 아래에 만든다. 이 레인은
   `prototype/`에 한 바이트도 안 남긴다(가드레일: 임시 DB는 `%TEMP%`). 같은 두 호출
   (`soak.seed` + `soak.ingest(timed=False)`)을 `%TEMP%`에서 부른다.

## «IDF가 순위를 움직일 수 있는 문항»의 정의는 여기서 새로 정하지 않는다

`.omc/plans/baseline/after-gap-round/df_probe.py` ②와 **같은 정의**다 — 채점 문항(`precision.partition`)
마다 질의 bigram 중 살아 있는 색인에 있는 항의 df를 모으고, **서로 다른 값이 둘 이상이면**
«움직일 수 있다»(전부 같으면 IDF는 상수배다). 정의가 갈라지지 않았다는 증거로 **eval에서 먼저
기록값(3/18과 df 분포 전체)을 재현하고, 못 하면 종료 1**로 멈춘다(교정 — `CALIBRATION`).

## 🔴 열 사이에 화살표를 그리지 않는다

다섯 열(eval · eval2 · eval3 레짐 셋)은 **서로 다른 모집단**이다. 열 제목에 코퍼스·레짐 이름을
박는다(실험 27 `TitleRule`의 정신). 특히 레짐 셋은 **같은 생성기가 지수 하나만 바꿔 만든 것**이라
«s가 커지면 ~가 늘었다»는 관측이 아니라 그 지수의 정의에 가깝다 — 말할 수 있는 것은
**«df가 이렇게 생겼을 때 조건이 이 값이다»**뿐이다.

## 실행 (G11)

    PYTHONIOENCODING=utf-8 python -B eval3/gen_corpus3.py
    PYTHONIOENCODING=utf-8 python -B experiments/eval3_probe.py
    PYTHONIOENCODING=utf-8 python -B -m unittest discover -s experiments/tests -p "test_eval3_probe.py" -v

⚠️ 3절(지연)은 기계·부하의 함수다 — **같은 실행 안에서만** 비교한다. 그래서 이 파일은
`run_all`에 올리지 않는다(`retrieve_scaling.py`를 안 올린 것과 같은 이유 — docs/17 §12-1).
종료 코드: 자기 검사(재생성 바이트 · eval 교정)가 깨지면 1, 아니면 0. 사전 등록 조건의
참/거짓은 **값으로 찍을 뿐** 종료 코드를 바꾸지 않는다 — «6 이상인 레짐이 없다»도 정당한 결과다.
"""
import json
import math
import os
import platform
import random
import shutil
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "eval3"))
sys.stdout.reconfigure(encoding="utf-8")

import memory as M                                              # noqa: E402
from memory import Memory                                       # noqa: E402
import soak                                                     # noqa: E402
import precision as P                                           # noqa: E402
import rel_dist as RD                                           # noqa: E402
import corpus2_probe as C2                                      # noqa: E402
import retrieve_scaling as RS                                   # noqa: E402
import predicate_vocab_cost as PV                               # noqa: E402
from gate_saturation import VocabProbe                          # noqa: E402
import gen_corpus3 as G3                                        # noqa: E402

W = 112
CW = 15                      # 열 너비

# ── 코퍼스 등록 — 순서가 곧 열 순서이고, **열 제목은 언제나 이 키**다 ─────────
CORPORA = {
    "eval": dict(corpus="eval/corpus/corpus.jsonl", ledger="eval/fact-ledger.yaml",
                 questions="eval/questions.yaml"),
    "eval2": dict(corpus="eval2/corpus/corpus.jsonl", ledger="eval2/fact-ledger.yaml",
                  questions="eval2/questions.yaml"),
}
for _d, _lab, _s, _em in G3.REGIMES:
    CORPORA[f"eval3·{_lab}"] = dict(corpus=f"eval3/regimes/{_d}/corpus/corpus.jsonl",
                                    ledger=f"eval3/regimes/{_d}/fact-ledger.yaml",
                                    questions="eval3/questions.yaml")
NAMES = list(CORPORA)
E3 = NAMES[2:]

# ── 교정 — eval에서 재현해야 하는 기록값 ──────────────────────────────────
# 출처: `.omc/plans/baseline/after-gap-round/df_probe.txt` ①·② (docs/17 §9 표의 원본).
CALIBRATION = dict(rows=21, terms=182, df1=156,
                   dist={1: 156, 2: 17, 3: 4, 4: 2, 5: 1, 6: 1, 12: 1},
                   scored=18, overlap_q=11, all_df1_q=1, over_terms=27, over_df2=20,
                   over_df1=7, movable=3)

# 부분표본 곡선 — 사전 등록한 격자와 반복 수. 곡선이 말하는 것은 «조건이 N의 함수인가»뿐이다.
SUB_NS = (21, 100, 300, 1000, 3000)
SUB_DRAWS = 20
SUB_SEED = 20260910

# 게이트 곡선의 색인 행 격자 (살아 있는 행 기준)
CURVE_MARKS = (21, 100, 500, 1000, 2000, 3000)

# θ의 «겹침 0만 버린다» 성질이 **깨질 수 있는** 문항의 최소 크기. rel = |Q∩D|/|Q|가
# 0이 아니면서 0.05 미만이려면 |Q| > 1/0.05 = 20이어야 한다 — 그래서 |Q| ≤ 20인 문항만
# 있는 코퍼스에서 그 성질은 **관측이 아니라 산수**다(깨질 수 없다).
THETA_BREAKABLE_Q = int(1 / M.THETA_RELEVANCE)


# ══════════════════════════════════════════════════════════════════════
# 사전 등록 — 첫 화면
# ══════════════════════════════════════════════════════════════════════

def conditions():
    """(이름, 무엇을 보나, 참이 되는 관측, 거짓이 되는 관측). 값 보기 전에 박은 문장들."""
    k = G3.ENGINE_K
    return [
        ("C1 규모", f"세 레짐의 살아 있는 색인 행(`_population_sig` 둘째 값)",
         f"세 레짐 모두 {G3.N_ALIVE}", "하나라도 다르다"),
        ("C2 문항", "`precision.partition`이 채점 대상으로 고른 문항 수",
         f"세 레짐 모두 {G3.N_SCORED} (전체 {G3.N_QUESTIONS})", "다르다"),
        ("C3 레짐이 실제로 갈렸나", "`지우`가 든 살아 있는 행의 비율 · df 상위 10항이 차지하는 (항,행) 쌍의 몫",
         "둘 다 s0 < s1 < s2로 엄격히 커진다", "어느 하나라도 순서가 안 선다(생성기가 선언대로 안 갈랐다)"),
        ("C4 방해물", f"군집 키 {len(G3.CLUSTER_KEYS)}개 각각이 든 살아 있는 색인 행 수",
         "세 레짐 모두 핵심 층이 설계한 수와 같다(벌크가 0을 더한다) · 서로 다른 방해 항목 "
         f"{G3.N_DISTRACTORS}", "한 칸이라도 다르다(방해물 수가 레짐의 함수가 됐다)"),
        ("C5 술어 안/밖", "DB의 서로 다른 술어 중 `PREDICATE_CARDINALITY`에 있는 것",
         f"안 {G3.PRED_IN} · 밖 {G3.PRED_OUT}", "다르다"),
        ("C6 표 밖 갱신", f"대장이 무효라 한 표 밖 사실 {G3.N_OUT_TABLE_CHAINS}개 중 색인에 살아 있는 것",
         f"{G3.N_OUT_TABLE_CHAINS}/{G3.N_OUT_TABLE_CHAINS} — 예측(코드를 읽고 한 것: 표 밖 기본값 «many» → 병존)",
         f"< {G3.N_OUT_TABLE_CHAINS} — 표 밖 술어도 어딘가에서 무효화된다"),
        ("C7 🔴 엔진 라운드", "레짐마다 «IDF가 순위를 움직일 수 있는 문항» 수 (분모: 채점 문항)",
         f"≥ {k}인 레짐이 하나라도 있다 → 엔진 라운드가 **열린다**",
         f"세 레짐 모두 < {k} → 안 열린다 (정당한 결과다)"),
        ("C8 20 ms 자", f"레짐마다 `retrieve` p95 (n={RS.N_CALLS} · 이 실행 안)",
         f"p95 > {RS.TRIGGER_MS:g} ms인 레짐이 있다 → «닿는다»", "없다 → «안 닿는다»"),
        ("C9 채점기 순서", "레짐마다 `survived_frozen` ≥ `survived_v2` ≥ `survived_v3` (생존 건수)",
         "레짐마다 참/거짓을 따로 찍는다", "—"),
        ("C10 θ 성질", "θ=0.05의 실제 컷 == θ=0.0001의 실제 컷 (겹침 0만 버린다)",
         "레짐마다 참/거짓 — 단 |Q| > 20인 채점 문항이 0이면 그 코퍼스에서는 **깨질 수 없다**(산수)",
         "θ=0.05가 0이 아닌 rel도 자른다"),
    ]


def preregistration():
    rule("0. 🔴 사전 등록 — 값 보기 전에 `eval3/gen_corpus3.py`에 상수로 박았다 (여기서 import)")
    print(f"  규모     살아 있는 색인 {G3.N_ALIVE}행 = 사실 {G3.N_FACTS_TOTAL} + 사건 {G3.N_EVENTS_TOTAL}"
          f" − 단일값 무효화 {G3.N_SUPERSEDED_IN_TABLE} · 세션 {G3.SESSIONS} × {G3.TURNS_PER_SESSION}턴")
    print("           왜: ADR-003 «우리 규모» 상단 · `retrieve_scaling`의 20 ms 교차(≈ 3,000)가 여기 떨어진다")
    print(f"  문항     {G3.N_QUESTIONS} (채점 {G3.N_SCORED} · 제외 {G3.N_QUESTIONS - G3.N_SCORED}) · 유형 "
          + " · ".join(f"{k} {v}" for k, v in G3.QUESTION_TYPES.items()))
    print(f"  방해물   군집 {len(G3.CLUSTER_KEYS)} ({' · '.join(G3.CLUSTER_KEYS)}) · 서로 다른 방해 항목 "
          f"{G3.N_DISTRACTORS} · 군집마다 ≥ {G3.MIN_DISTRACTORS_PER_CLUSTER}")
    print(f"  술어     `PREDICATE_CARDINALITY` 기준 안 {G3.PRED_IN} · 밖 {G3.PRED_OUT} · 표 밖 갱신 사슬 "
          f"{G3.N_OUT_TABLE_CHAINS}")
    print("  df 레짐  벌크 슬롯 값을 순위 r의 가중치 r^(-s)로 뽑는다 — 레짐이 바꾸는 것은 s 하나뿐")
    for d, lab, s, em in G3.REGIMES:
        print(f"    · {lab:<12} (eval3/regimes/{d}) — {em}")
    print(f"  🔴 엔진 라운드: «IDF가 움직일 수 있는 문항 ≥ {G3.ENGINE_K}»인 레짐이 **하나라도** 있으면 열린다"
          " (docs/17 §9 ① — k=6은 부호검정 양측 p = 2·0.5^k < 0.05의 최소 k)")
    print("  🔴 예측(값 보기 전): C7은 세 레짐 모두 참일 것이다 — 3,000행에서는 채점 문항이 색인과 겹치는"
          " 항이 거의 늘 둘 이상이고 그 df가 같을 일이 드물다.")
    print("     참으로 나오면 그것은 «df 모양이 조건을 만족시켰다»가 아니라 **«N이 만족시켰다»**일 수 있다 —"
          " 그래서 부분표본 곡선(2-3)을 함께 사전 등록했다.")
    print("\n  각 조건이 어떤 관측으로 참/거짓이 되는가:")
    for name, what, t, f in conditions():
        print(f"    {name:<16} 무엇: {what}")
        print(f"    {'':<16} 참 : {t}")
        print(f"    {'':<16} 거짓: {f}")


# ══════════════════════════════════════════════════════════════════════
# 적재 · 자기 검사
# ══════════════════════════════════════════════════════════════════════

def load(name):
    """`corpus2_probe.load`와 같은 형태 — 그 함수는 자기 `CORPORA`만 본다."""
    c = CORPORA[name]
    with open(ROOT / c["corpus"], encoding="utf-8") as f:
        corpus = [json.loads(l) for l in f]
    with open(ROOT / c["ledger"], encoding="utf-8") as f:
        ledger = yaml.safe_load(f)
    with open(ROOT / c["questions"], encoding="utf-8") as f:
        qs = yaml.safe_load(f)["qa_questions"]
    return corpus, ledger, qs


def build(tmp, name, corpus, ledger):
    """`soak.seed` + `soak.ingest(timed=False)` — 무변경. DB는 `%TEMP%` 아래."""
    m = Memory(os.path.join(tmp, f"{NAMES.index(name)}.db"))
    soak.seed(m)
    soak.ingest(m, corpus, ledger, timed=False)
    return m


def regen_mismatch(base=None):
    """`eval3/gen_corpus3.py`가 **지금 만드는 바이트**와 디스크가 다른 파일 목록."""
    base = Path(base) if base else ROOT / "eval3"
    out, _ = G3.render_all()
    return [k for k, v in sorted(out.items())
            if not (base / k).exists() or (base / k).read_bytes() != v]


# ══════════════════════════════════════════════════════════════════════
# 엔진 조건 — df_probe ②와 같은 정의
# ══════════════════════════════════════════════════════════════════════

def df_of(docs, terms=M.bigrams):
    """`df_probe.df_of`와 같은 식 — 문서마다 **집합**으로 센다."""
    df = Counter()
    for d in docs:
        for t in set(terms(d)):
            df[t] += 1
    return df


def movable(asks, df):
    """
    채점 문항마다 (질의 bigram ∩ 색인 항)의 df를 모아:
      겹침이 있는 문항 · 그 겹침이 전부 df=1인 문항 · 겹침 항 계수(df=1 / df≥2) ·
      🔴 **df가 서로 다른 값 둘 이상인 문항 = IDF가 순위를 움직일 수 있는 문항.**
    """
    over, any_ov, all1, mixed = Counter(), 0, 0, 0
    for a in asks:
        ds = [df[t] for t in set(M.bigrams(a)) & set(df)]
        for v in ds:
            over["df=1" if v == 1 else "df≥2"] += 1
        any_ov += bool(ds)
        all1 += bool(ds) and all(v == 1 for v in ds)
        mixed += len(set(ds)) >= 2
    return dict(overlap_q=any_ov, all_df1_q=all1, over_terms=sum(over.values()),
                over_df2=over["df≥2"], over_df1=over["df=1"], movable=mixed)


def engine_verdict(counts, k=G3.ENGINE_K):
    """`{레짐: 움직일 수 있는 문항 수}` → (열리나, 조건을 만족한 레짐들)."""
    hit = [n for n, v in counts.items() if v >= k]
    return bool(hit), hit


def idf_spread(asks, df, n):
    """문항마다 겹침 항 idf = ln(N/df)의 최대 − 최소. **서술용** — 조건이 아니다."""
    out = []
    for a in asks:
        ds = [df[t] for t in set(M.bigrams(a)) & set(df)]
        if len(ds) >= 2:
            idf = [math.log(n / d) for d in ds]
            out.append(max(idf) - min(idf))
    return out


def subsample_movable(summaries, asks, ns=SUB_NS, draws=SUB_DRAWS, seed=SUB_SEED):
    """색인에서 N행을 뽑아 같은 수를 센다 — 조건이 **N의 함수인가**를 본다(외삽하지 않는다)."""
    rng = random.Random(seed)
    sets = [set(M.bigrams(s)) for s in summaries]
    qsets = [set(M.bigrams(a)) for a in asks]
    out = {}
    for n in ns:
        if n > len(sets):
            continue
        vals = []
        for _ in range(draws if n < len(sets) else 1):
            df = Counter()
            for s in (rng.sample(sets, n) if n < len(sets) else sets):
                df.update(s)
            vals.append(sum(1 for q in qsets
                            if len({df[t] for t in q if t in df}) >= 2))
        out[n] = (min(vals), sum(vals) / len(vals), max(vals))
    return out


def long_questions(asks, limit=THETA_BREAKABLE_Q):
    """|set(bigrams(ask))| > limit 인 문항 — θ=0.05의 «겹침 0만» 성질이 깨질 수 있는 유일한 자리."""
    return [a for a in asks if len(set(M.bigrams(a))) > limit]


# ══════════════════════════════════════════════════════════════════════
# 출력 도우미
# ══════════════════════════════════════════════════════════════════════

def rule(title=""):
    print("\n" + "=" * W)
    if title:
        print(title)
        print("=" * W)


def cols(label, cells, names=NAMES):
    print(f"  {label:<40}" + "".join(f"{str(c):>{CW}}" for c in cells))


def header(names=NAMES):
    cols("", names, names)
    print("  " + "-" * (40 + CW * len(names)))


def pctf(a, b):
    return f"{a}/{b}={a / b * 100:.1f}%" if b else "-"


# ══════════════════════════════════════════════════════════════════════
# 3. 지연 — retrieve_scaling의 부품으로, 한 실행 안에서 번갈아 잰다
# ══════════════════════════════════════════════════════════════════════

def latency(mems, asks, last_seq):
    """
    `retrieve_scaling.run`의 **절차**를 따른다 — n = `RS.N_CALLS`(워밍업 `RS.WARMUP` 제외) ·
    라운드마다 DB 순서를 섞음(seed `RS.SEED`) · 0-연산 대조(`RS.SQL_ONLY`) · 게이트(방 어휘).
    ⚠️ 그 함수를 부르지 못하는 이유: 틀을 `eval` 색인으로 **하드코딩**했다(`load_eval`).
       여기서는 eval3 레짐 DB 셋과 그 틀 DB를 **한 루프에 섞어야** 같은 부하 창을 받는다.
    """
    rng = random.Random(RS.SEED)
    keys = list(mems)
    t = {(k, w): [] for k in keys for w in ("retrieve", "sql", "gate")}
    hits = {k: 0 for k in keys}
    for rnd in range(RS.WARMUP + RS.N_CALLS):
        rng.shuffle(keys)
        q = asks[rnd % len(asks)]
        for k in keys:
            m = mems[k]
            t0 = time.perf_counter()
            got, _ = m.retrieve(soak.CHAT, q, last_seq)
            t1 = time.perf_counter()
            m.db.execute(RS.SQL_ONLY, (soak.CHAT,)).fetchall()
            t2 = time.perf_counter()
            m.gate(q, soak.CHAT)
            t3 = time.perf_counter()
            if rnd >= RS.WARMUP:
                t[(k, "retrieve")].append((t1 - t0) * 1000)
                t[(k, "sql")].append((t2 - t1) * 1000)
                t[(k, "gate")].append((t3 - t2) * 1000)
                hits[k] += len(got)
    return t, hits


# ══════════════════════════════════════════════════════════════════════
# 본문
# ══════════════════════════════════════════════════════════════════════

def main():
    t_start = time.perf_counter()
    print("=" * W)
    print("eval3 — 규모 코퍼스에서 선행 조건을 잰다 (계측기 무변경 · LLM 0회 · 임시 DB)")
    print("=" * W)
    print("🔴 다섯 열은 **서로 다른 모집단**이다. 화살표를 그리지 않는다 — 열 제목이 코퍼스·레짐 이름이다.")
    preregistration()

    rule("0-b. 자기 검사 — 재생성 바이트 대조 (이 프로브가 재는 파일이 생성기가 지금 내는 파일인가)")
    bad = regen_mismatch()
    print(f"  `eval3/gen_corpus3.render_all()` ↔ 디스크: 다름 {len(bad)} / 8 {bad if bad else ''}")
    if bad:
        print("  🔴 멈춘다 — 디스크의 eval3/이 생성기와 다르다. `python -B eval3/gen_corpus3.py`로 다시 만들 것")
        return 1

    data = {n: load(n) for n in NAMES}
    tmp = tempfile.mkdtemp(prefix="eval3_probe_")
    mems, extra = {}, []
    try:
        for n in NAMES:
            mems[n] = build(tmp, n, data[n][0], data[n][1])
        rows = {n: C2.index_rows(mems[n]) for n in NAMES}
        sig = {n: mems[n]._population_sig(soak.CHAT) for n in NAMES}
        scored = {}
        for n in NAMES:
            s, ex = P.partition(data[n][2], P.key_index(data[n][1]))
            scored[n] = (s, ex)

        # ── 1. 규모 ────────────────────────────────────────────────
        rule("1. 규모 — 각 열은 **다른 모집단**이다")
        header()
        f = lambda fn: [fn(*data[n], n) for n in NAMES]            # noqa: E731
        cols("턴 (JSONL 행)", f(lambda c, l, q, n: len(c)))
        cols("  그중 user 턴 (게이트 분모)", f(lambda c, l, q, n: sum(r["role"] == "user" for r in c)))
        cols("세션", f(lambda c, l, q, n: len({r["session"] for r in c})))
        cols("심은 항목 (밀도)", f(lambda c, l, q, n: f"{sum(bool(r['planted_id']) for r in c)}"
                                   f" ({sum(bool(r['planted_id']) for r in c) / len(c):.1%})"))
        cols("대장 항목 (facts + events)", f(lambda c, l, q, n: len(C2.ledger_items(l))))
        cols("문항 / 채점 대상", [f"{len(data[n][2])} / {len(scored[n][0])}" for n in NAMES])
        cols("색인 (총 행, 살아 있는 행) = 서명", [f"{a}, {b}" for a, b in (sig[n] for n in NAMES)])
        cols("살아 있는 행 평균 요약 길이 (자)",
             [f"{sum(len(r['summary']) for r in rows[n]) / len(rows[n]):.1f}" for n in NAMES])
        cols("서로 다른 요약 문자열", [len({r["summary"] for r in rows[n]}) for n in NAMES])
        cols(f"τ={M.TAU_IMPORTANCE} 미만 행", [pctf(C2.tau_cut(rows[n])[1], len(rows[n])) for n in NAMES])
        print("  ⚠️ eval3의 밀도는 축이 아니라 결과다 — `gen_corpus.generate`의 세션당 30턴을 그대로 쓰고")
        print(f"     {G3.SESSIONS}세션에 심은 항목 {sum(bool(r['planted_id']) for r in data[E3[0]][0])}개를 넣으면"
              " 이 값이 된다. 게이트는 턴 **종류별**로 본다(4절).")

        # ── 2. 🔴 엔진 조건 ────────────────────────────────────────
        rule("2. 🔴 엔진 라운드의 조건 — «IDF가 순위를 움직일 수 있는 문항» (df_probe ②와 같은 정의)")
        alive = {n: [r["summary"] for r in rows[n]] for n in NAMES}
        dfs = {n: df_of(alive[n]) for n in NAMES}
        asks = {n: [q["ask"] for q in scored[n][0]] for n in NAMES}
        mv = {n: movable(asks[n], dfs[n]) for n in NAMES}

        cal = dict(rows=len(alive["eval"]), terms=len(dfs["eval"]),
                   df1=sum(1 for v in dfs["eval"].values() if v == 1),
                   dist=dict(sorted(Counter(dfs["eval"].values()).items())),
                   scored=len(asks["eval"]), **mv["eval"])
        diff = {k: (cal[k], v) for k, v in CALIBRATION.items() if cal[k] != v}
        print("  2-0 교정 — eval에서 기록값(df_probe.txt ①·②)을 재현하는가:")
        print(f"      재현 {len(CALIBRATION) - len(diff)}/{len(CALIBRATION)} 칸 · "
              f"움직일 수 있는 문항 {cal['movable']}/{cal['scored']} (기록 3/18)")
        if diff:
            print(f"  🔴 멈춘다 — 정의가 기록과 갈라졌다: {diff}")
            return 1

        print("\n  2-1 df 분포 (분석기 `memory.bigrams` · 살아 있는 행)")
        header()
        cols("살아 있는 행 (N)", [len(alive[n]) for n in NAMES])
        cols("서로 다른 항", [len(dfs[n]) for n in NAMES])
        cols("df=1 항의 비율", [pctf(sum(1 for v in dfs[n].values() if v == 1), len(dfs[n])) for n in NAMES])
        cols("`지우`가 든 행의 비율", [pctf(sum("지우" in s for s in alive[n]), len(alive[n])) for n in NAMES])
        top10 = {}
        for n in NAMES:
            pairs = sum(dfs[n].values())
            top10[n] = sum(v for _, v in dfs[n].most_common(10)) / pairs
        cols("df 상위 10항의 (항,행) 쌍 몫", [f"{top10[n]:.1%}" for n in NAMES])
        for n in NAMES:
            top = sorted(dfs[n].items(), key=lambda x: (-x[1], x[0]))[:6]
            print(f"    [{n}] df 상위: " + " · ".join(f"{t}({v})" for t, v in top))

        print("\n  2-2 🔴 질의 쪽 (채점 문항 × 살아 있는 행)")
        header()
        cols("채점 문항 (분모)", [len(asks[n]) for n in NAMES])
        cols("색인과 겹치는 항이 있는 문항", [mv[n]["overlap_q"] for n in NAMES])
        cols("  그 겹침이 전부 df=1", [mv[n]["all_df1_q"] for n in NAMES])
        cols("겹침 항 (df≥2 / df=1)", [f"{mv[n]['over_df2']}/{mv[n]['over_df1']}" for n in NAMES])
        cols("🔴 IDF가 움직일 수 있는 문항", [f"{mv[n]['movable']}/{len(asks[n])}" for n in NAMES])
        cols("  한 방향 불일치 그 수 쌍의 p 최솟값", [f"{2 * 0.5 ** mv[n]['movable']:.2g}" for n in NAMES])
        spreads = {n: idf_spread(asks[n], dfs[n], len(alive[n])) for n in NAMES}
        cols("(서술) 겹침 idf 폭 중앙값 [nat]",
             [f"{sorted(v)[len(v) // 2]:.2f}" if v else "-" for v in spreads.values()])
        verdict, which = engine_verdict({n: mv[n]["movable"] for n in E3})
        print(f"\n  → C7 판정: eval3 레짐 중 «≥ {G3.ENGINE_K}»인 것 {len(which)}/{len(E3)}"
              f" {which if which else ''} → 엔진 라운드 **{'열린다' if verdict else '안 열린다'}**")
        print("    ⚠️ docs/17 §9의 단서가 그대로다: 이 수는 «IDF의 상대 가중» 몫에 한정된다 — 척도(θ 컷)·"
              "비중(rel/imp)·길이 정규화는 이 수와 무관하게 팔 사이 불일치를 만든다.")

        print(f"\n  2-3 부분표본 곡선 — 같은 수를 색인 N행 부분표본에서 (최소 · 평균 · 최대, {SUB_DRAWS}회 · seed {SUB_SEED})")
        print("      무엇을 보나: 조건이 **df 모양의 함수인가, N의 함수인가.** 외삽하지 않는다.")
        for n in E3:
            cur = subsample_movable(alive[n], asks[n])
            print(f"    [{n}] " + " · ".join(f"N={k}: {a}/{b:.1f}/{c}" for k, (a, b, c) in cur.items())
                  + f"  (분모 {len(asks[n])})")

        # ── 3. 지연 ────────────────────────────────────────────────
        rule(f"3. `retrieve` 지연 — p50·p95 (n={RS.N_CALLS}/DB · 워밍업 {RS.WARMUP} 제외 · 라운드마다 순서를 섞음)")
        print(f"  기계: {platform.platform()} · 논리 CPU {os.cpu_count()} · Python {platform.python_version()}"
              f" · {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("  ⚠️ 지연은 기계·부하의 함수다 — **이 표의 값은 이 실행 안에서만** 비교한다.")
        tpl = RS.template_rows(tmp, *data["eval"][:2])
        lat_mems = {n: mems[n] for n in E3}
        lab_tpl = f"eval 틀 ×{G3.N_ALIVE}"
        lat_mems[lab_tpl] = RS.build_db(tmp, "tpl", G3.N_ALIVE, tpl, False)
        extra.append(lat_mems[lab_tpl])
        q_lat = asks[E3[0]]
        t, hits = latency(lat_mems, q_lat, data[E3[0]][0][-1]["seq"])
        order = E3 + [lab_tpl]
        print(f"  질의: eval3 채점 문항 {len(q_lat)}개를 돌려 씀(네 DB 같은 순서) · `{lab_tpl}` = "
              f"`retrieve_scaling`의 eval 분포 합성 색인(요약 {len(tpl)}종 되풀이)")
        print(f"  {'DB':<22}{'행':>6}{'retrieve p50':>14}{'p95':>9}{'max':>9} │{'SQL만 p50':>11}{'p95':>8}"
              f" │{'gate p50':>10}{'p95':>8} │{'µs/행(p50)':>11}{'꺼냄/회':>8}")
        p95 = {}
        for k in order:
            r, s, g = t[(k, "retrieve")], t[(k, "sql")], t[(k, "gate")]
            nrow = lat_mems[k]._population_sig(soak.CHAT)[1]
            p95[k] = RS.pct(r, 95)
            flag = f" 🔴>{RS.TRIGGER_MS:g}" if p95[k] > RS.TRIGGER_MS else ""
            print(f"  {k:<22}{nrow:>6}{RS.pct(r, 50):>12.3f}ms{p95[k]:>7.3f}ms{max(r):>7.2f}ms │"
                  f"{RS.pct(s, 50):>9.3f}ms{RS.pct(s, 95):>6.3f}ms │{RS.pct(g, 50):>8.3f}ms"
                  f"{RS.pct(g, 95):>6.3f}ms │{RS.pct(r, 50) / nrow * 1000:>11.2f}{hits[k] / RS.N_CALLS:>8.2f}"
                  f"{flag}")
        over20 = [k for k in E3 if p95[k] > RS.TRIGGER_MS]
        print(f"  → C8: eval3 레짐 중 p95 > {RS.TRIGGER_MS:g} ms {len(over20)}/{len(E3)} "
              f"→ 이 실행에서 **{'닿는다' if over20 else '안 닿는다'}**")
        print("    ⚠️ 교차점이 자 근처라 실행마다 뒤집힐 수 있다(docs/17 §12-1 — 같은 코드의 두 실행이"
              " 19.186 / 20.195 ms). 이 줄은 «이 실행에서»다.")

        # ── 4. 게이트 ──────────────────────────────────────────────
        rule("4. `Memory.gate` — 턴 종류별 발화율 (실험 31의 형태 · 게이트 함수 객체 + 방 어휘 한 번 읽기)")
        print("  `gate_saturation.VocabProbe`: `Memory.gate` **그 함수 객체**에 `_recall_vocab`만 꽂는다."
              " 어휘는 DB에 **한 번 묻는다**(방이 하나라 `_recall_vocab_for(CHAT)`과 같은 집합).")
        vp = {n: VocabProbe(mems[n]._recall_vocab) for n in NAMES}
        gb = {n: C2.gate_breakdown(vp[n], data[n][0]) for n in NAMES}
        gk = {n: C2.gate_by_kind(vp[n], data[n][0]) for n in NAMES}
        header()
        cols("|_recall_vocab|", [len(vp[n]._recall_vocab) for n in NAMES])
        cols("게이트 통과 / user 턴", [pctf(gb[n][1], gb[n][0]) for n in NAMES])
        for kind in ("심긴 항목", "하드 네거티브", "순수 노이즈"):
            cols(f"  {kind}", [pctf(gk[n].get(kind, [0, 0])[1], gk[n].get(kind, [0, 0])[0]) for n in NAMES])
        reasons = sorted(set().union(*[set(gb[n][2]) for n in NAMES]))
        print()
        for why in reasons:
            cols(f"  이유: {why[:30]}", [gb[n][2].get(why, 0) for n in NAMES])
        cols("  «과거 참조» 중 심긴 항목 턴 / 그 밖",
             [f"{a}/{b}" for a, b in (C2.past_ref_source(vp[n], data[n][0]) for n in NAMES)])
        print("  ⚠️ eval·eval3의 사실 턴은 `gen_corpus.render`의 `\"{text}. 말했었나?\"`라 «과거 참조»로 걸린다"
              " — 언어 현상이 아니라 템플릿이다(실험 31이 적은 그대로).")

        # ── 5. UBIQUITOUS ──────────────────────────────────────────
        rule("5. `scoring.UBIQUITOUS = {\"지우\"}`가 각 열에서 하는 일")
        ub = {n: C2.ubiquitous_effect(data[n][1]) for n in NAMES}
        header()
        cols("대장 항목 (분모)", [ub[n][0] for n in NAMES])
        cols("UBIQUITOUS가 어근을 걷어낸 항목", [pctf(ub[n][1], ub[n][0]) for n in NAMES])
        cols("`지우` 항목 빈도 df", [ub[n][3].get("지우", 0) for n in NAMES])
        _, all_rank, _ = C2.induce_ubiquitous(data["eval"][1], min_frac=0.0, top=999)
        jw = next((fr for r, c, fr in all_rank if r == "지우"), 0.0)
        print(f"\n  유도 문턱 (G15): eval에서 `지우`의 df 비율 = {jw:.3f} — 이 비율 이상을 «편재»로 부른다")
        for n in NAMES:
            ni, ranked, induced = C2.induce_ubiquitous(data[n][1], min_frac=jw, top=4)
            cut_df, rest = C2.tie_cut(data[n][1], ranked)
            print(f"    [{n}] 상위: " + " · ".join(f"{r}({c}, {fr:.0%})" for r, c, fr in ranked)
                  + (f" · 동점 {len(rest)}종 더" if rest else "")
                  + f" → 유도된 편재 집합 {sorted(induced) if induced else '∅'}")

        # ── 6. _roots ──────────────────────────────────────────────
        rule("6. `Memory._roots` · `_stem`이 깨지는 자리 (분모 = 서로 다른 어절)")
        brk = {n: C2.breakage(*data[n]) for n in NAMES}
        header()
        cols("서로 다른 어절 (분모)", [len(brk[n][0]) for n in NAMES])
        cols("① `len(w) < 2`로 버려진 어절", [len(brk[n][1]) for n in NAMES])
        cols("② `습니다` 뗀 뒤 잔여 표지", [len(brk[n][2]) for n in NAMES])
        cols("③ 한글이 없는 어근", [len(brk[n][3]) for n in NAMES])
        for n in E3:
            print(f"    [{n}] ① 실물: {sorted(brk[n][1])[:10]} · ③ 실물: {sorted(brk[n][3].items())[:5]}")

        # ── 7. 세 채점기 ───────────────────────────────────────────
        rule("7. 세 채점기의 순서 — 추출식 다이제스트(세션의 심긴 항목을 잇고 150자에서 자름) × 대장 항목 전부")
        print("  🔴 LLM 요약이 아니다 — 실험 19/20의 수와 같은 것이 아니다. 여기서 보는 것은 **순서**뿐이다.")
        sc, emp = {}, {}
        for n in NAMES:
            dg = C2.digests(data[n][0], data[n][1])
            sc[n] = C2.score_all(data[n][1], digs=dg)
            emp[n] = C2.rescore_with(data[n][1], set(), digs=dg)
        header()
        cols("판정 쌍 (다이제스트 × 항목)", [f"{sc[n]['n_digests']}×{sc[n]['n_items']}" for n in NAMES])
        cols("survived_frozen", [sc[n]["frozen"] for n in NAMES])
        cols("survived_v2", [sc[n]["v2"] for n in NAMES])
        cols("survived_v3", [sc[n]["v3"] for n in NAMES])
        cols("v2 판정불가", [sc[n]["un2"] for n in NAMES])
        cols("frozen ≥ v2 ≥ v3", [sc[n]["frozen"] >= sc[n]["v2"] >= sc[n]["v3"] for n in NAMES])
        cols("v3 ⊆ v2 · 판정불가 같음", ["{} · {}".format(*C2.invariants(sc[n])) for n in NAMES])
        cols("두 방향: frozen만 / v2만",
             [f"{C2.frozen_only_examples(sc[n])[1]}/{C2.v2_only_examples(sc[n])[1]}" for n in NAMES])
        cols("UBIQUITOUS=∅ 재채점 v2 (현행/∅)", [f"{sc[n]['v2']}/{emp[n]['v2']}" for n in NAMES])
        cols("UBIQUITOUS=∅ 재채점 판정불가", [f"{sc[n]['un2']}/{emp[n]['un2']}" for n in NAMES])

        # ── 8. θ ───────────────────────────────────────────────────
        rule(f"8. θ={M.THETA_RELEVANCE} — «겹침 0만 버린다»가 여기서도 성립하나 (척도 `coverage` · `retrieve`의 lexical 분기)")
        header()
        th = {}
        for n in NAMES:
            s_, ex_, vals = C2.rel_population(data[n][2], data[n][1], rows[n])
            c05, c0 = RD.actual_cut(vals, 0.05), RD.actual_cut(vals, 0.0001)
            th[n] = (len(vals), sum(v == 0.0 for v in vals) / len(vals), c05, c0,
                     len(long_questions([q["ask"] for q in s_])))
        cols("모집단 n (채점 문항 × 살아 있는 행)", [th[n][0] for n in NAMES])
        cols("rel == 0 의 원자", [f"{th[n][1]:.2%}" for n in NAMES])
        cols("θ=0.05 실제 컷", [f"{th[n][2]:.2%}" for n in NAMES])
        cols("θ=0.0001 실제 컷", [f"{th[n][3]:.2%}" for n in NAMES])
        cols(f"|Q| > {THETA_BREAKABLE_Q}인 채점 문항 (깨질 수 있는 자리)", [th[n][4] for n in NAMES])
        cols("두 컷이 같다 (C10)", [abs(th[n][2] - th[n][3]) < 1e-12 for n in NAMES])
        print(f"  🔴 |Q| > {THETA_BREAKABLE_Q}인 문항이 0인 열에서 «같다»는 **관측이 아니라 산수**다 —"
              " 0이 아닌 rel은 전부 ≥ 1/|Q| ≥ 0.05다.")

        # ── 9. 표 밖 술어 ──────────────────────────────────────────
        rule("9. 술어 — `PREDICATE_CARDINALITY`(8) 안/밖 · 표 밖 갱신이 무효화되는가 (밖E10)")
        doc14 = PV.doc14_table(PV.DOC14.read_text(encoding="utf-8"))
        ic = {n: C2.instrument_coupling(mems[n]) for n in NAMES}
        header()
        cols("DB의 서로 다른 술어", [ic[n][2] for n in NAMES])
        cols("  그중 CARDINALITY(8)에 있는 것", [len(ic[n][3]) for n in NAMES])
        cols("  그중 STANDING(9)에 있는 것",
             [len([p for p in preds(mems[n]) if p in Memory.PREDICATE_STANDING]) for n in NAMES])
        cols("  그중 docs/14 표(25)에 있는 것", [len([p for p in preds(mems[n]) if p in doc14]) for n in NAMES])
        cols("fact.subject (soak.ingest가 넣은 것)", [",".join(ic[n][0]) for n in NAMES])
        cols("superseded_by가 채워진 fact 행", [ic[n][1] for n in NAMES])
        st = {n: stale_alive(mems[n], data[n][1]) for n in NAMES}
        cols("대장 무효 사실 중 색인에 살아 있는 것", [f"{a}/{b}" for a, b, _, _ in st.values()])
        cols("  그중 표 밖 술어 (C6)", [f"{c}/{d}" for _, _, c, d in st.values()])
        sp = shared_predicates(data[E3[0]][1], core_only=True)
        print(f"\n  «같은 술어를 여러 인물이 공유» (핵심 층 · 레짐 불변): {len(sp)}종 — "
              + " · ".join(f"{p}({k}명)" for p, k in sp))
        for n in E3:
            spb = shared_predicates(data[n][1], core_only=False)
            print(f"    [{n}] 벌크 포함: {len(spb)}종 · 인물 수 최대 {max(k for _, k in spb)}")

        # ── 10. 방해물 ─────────────────────────────────────────────
        rule("10. 어휘적 방해물 — 군집 키가 든 **살아 있는** 색인 행 (FP-4 · 실험 5가 «반증 자격 없음»이던 조건)")
        core = yaml.safe_load((ROOT / "eval3" / "fact-ledger.yaml").read_text(encoding="utf-8"))
        design = cluster_design(core)
        print(f"  {'키':<8}{'설계(핵심 층)':>14}" + "".join(f"{n:>{CW + 3}}" for n in E3)
              + f"{'방해 항목':>10}{'  그중 τ 통과':>12}")
        ok4 = True
        for key in G3.CLUSTER_KEYS:
            cnt = [sum(key in s for s in alive[n]) for n in E3]
            ok4 &= all(c == design[key]["alive"] for c in cnt)
            print(f"  {key:<8}{design[key]['alive']:>14}" + "".join(f"{c:>{CW + 3}}" for c in cnt)
                  + f"{len(design[key]['distractor']):>10}{design[key]['pass_tau']:>12}")
        n_d = sum(1 for x in core["facts"] + core["events"] if x.get("lexical_role") == "distractor")
        n_pass = sum(1 for x in core["facts"] + core["events"] if x.get("lexical_role") == "distractor"
                     and max(x.get("importance", 0) or 0, x.get("emotional_weight", 0) or 0)
                     >= M.TAU_IMPORTANCE)
        print(f"  서로 다른 방해 항목 {n_d} · 그중 τ({M.TAU_IMPORTANCE}) 이상이라 **검색에서 경쟁하는** 것 {n_pass}"
              f" — 나머지 {n_d - n_pass}은 τ가 먼저 자른다(무게는 저자가 배정했다)")
        print("  ⚠️ 이 코퍼스는 방해물이 **있다**는 것만 보증한다. 검색이 그것을 구별하는가(회상·오주입)는"
              " 이 레인이 재지 않았다.")

        # ── 4-b. 게이트 곡선 (DB를 건드리므로 마지막) ───────────────
        rule("4-b. 색인 행 수 축의 게이트 곡선 — |_recall_vocab| · 발화율 (분모는 언제나 전체 user 턴)")
        for n in E3:
            cur = vocab_curve(mems[n], data[n][0])
            print(f"  [{n}] " + " · ".join(f"{k}행 |v|{v} {fired / nu:.1%}" for k, v, fired, nu in cur))

        # ── 11. 판정표 ─────────────────────────────────────────────
        rule("11. 사전 등록 판정표 — 관측 → 참/거짓")
        c1 = all(sig[n][1] == G3.N_ALIVE for n in E3)
        c2 = all(len(scored[n][0]) == G3.N_SCORED and len(data[n][2]) == G3.N_QUESTIONS for n in E3)
        jr = [sum("지우" in s for s in alive[n]) / len(alive[n]) for n in E3]
        tp = [top10[n] for n in E3]
        c3 = jr[0] < jr[1] < jr[2] and tp[0] < tp[1] < tp[2]
        c5 = all(ic[n][2] == G3.PRED_IN + G3.PRED_OUT and len(ic[n][3]) == G3.PRED_IN for n in E3)
        c6 = [st[n][2] for n in E3]
        c9 = {n: sc[n]["frozen"] >= sc[n]["v2"] >= sc[n]["v3"] for n in E3}
        c10 = {n: abs(th[n][2] - th[n][3]) < 1e-12 for n in E3}
        for name, val, obs in [
            ("C1 규모", c1, f"살아 있는 행 {[sig[n][1] for n in E3]}"),
            ("C2 문항", c2, f"채점 {[len(scored[n][0]) for n in E3]}"),
            ("C3 레짐이 갈렸나", c3, f"`지우` 행 {[f'{x:.1%}' for x in jr]} · 상위10 몫 {[f'{x:.1%}' for x in tp]}"),
            ("C4 방해물", ok4 and n_d == G3.N_DISTRACTORS, f"12키 × 3레짐이 설계와 같음 {ok4} · 방해 항목 {n_d}"),
            ("C5 술어 안/밖", c5, f"{[(ic[n][2], len(ic[n][3])) for n in E3]} (전체, 안)"),
            ("C6 표 밖 갱신", all(v == G3.N_OUT_TABLE_CHAINS for v in c6),
             f"살아 있는 표 밖 무효 사실 {c6}/{G3.N_OUT_TABLE_CHAINS}"),
            ("C7 🔴 엔진 라운드", verdict, f"움직일 수 있는 문항 {[mv[n]['movable'] for n in E3]}/"
                                     f"{len(asks[E3[0]])} → {'열린다' if verdict else '안 열린다'}"),
            ("C8 20 ms 자", bool(over20), f"p95 {[f'{p95[n]:.2f}' for n in E3]} ms (이 실행)"),
            ("C9 채점기 순서", all(c9.values()), f"{c9}"),
            ("C10 θ 성질", all(c10.values()), f"{c10} · |Q|>{THETA_BREAKABLE_Q} 문항 {[th[n][4] for n in E3]}"),
        ]:
            print(f"  {name:<18} {'참' if val else '거짓':<4} ← {obs}")
    finally:
        for m in list(mems.values()) + extra:
            try:
                m.db.close()
            except Exception:                                   # noqa: BLE001
                pass
        shutil.rmtree(tmp, ignore_errors=True)

    rule("🔴 이 프로브가 말할 수 없는 것")
    print("  · eval3는 **합성**이고 **저자가 하나**다. df 레짐 셋은 같은 생성기가 지수 하나만 바꿔 만든 것이다 —")
    print("    «s가 커지면 ~»는 관측이 아니라 지수의 정의에 가깝다. 어느 레짐도 «실사용 df»가 아니다.")
    print("  · C7이 참이어도 **엔진이 이긴다는 뜻이 아니다.** «IDF의 상대 가중이 순위를 움직일 수 있는 문항이")
    print("    부호검정이 가를 만큼 있다»까지다. 그리고 그 수가 df 모양이 아니라 N에서 왔을 수 있다(2-3).")
    print("  · 지연은 이 실행·이 기계의 값이다. 다른 실행의 값과 나란히 놓지 않는다.")
    print("  · 회상·오주입(방해물을 검색이 구별하는가)은 재지 않았다 — 조건을 재는 레인이다.")
    print(f"  (소요 {time.perf_counter() - t_start:.0f} s)")
    print("=" * W)
    return 0


# ── 9·10절 도우미 ─────────────────────────────────────────────────────

def preds(m):
    return [r[0] for r in m.db.execute("SELECT DISTINCT predicate FROM fact WHERE chat_id=?",
                                       (soak.CHAT,))]


def stale_alive(m, ledger):
    """대장이 `invalidated_at`을 준 사실 중 색인 복사본이 **살아 있는** 것 (전체 / 표 밖)."""
    live = {r[0] for r in m.db.execute(
        "SELECT summary FROM event WHERE chat_id=? AND user_deleted=0", (soak.CHAT,))}
    inv = [f for f in ledger.get("facts", []) if f.get("invalidated_at")]
    out_t = [f for f in inv if f.get("predicate") not in Memory.PREDICATE_CARDINALITY]
    return (sum(f["text"] in live for f in inv), len(inv),
            sum(f["text"] in live for f in out_t), len(out_t))


def shared_predicates(ledger, core_only):
    subj = {}
    for f in ledger["facts"]:
        if core_only and f.get("tests") == ["bulk"]:
            continue
        subj.setdefault(f["predicate"], set()).add(f.get("subject", "?"))
    return sorted(((p, len(s)) for p, s in subj.items() if len(s) >= 2), key=lambda x: (-x[1], x[0]))


def cluster_design(core):
    """핵심 층이 설계한 수 — 키마다 (그 키가 든 **살아 있는** 핵심 항목, 방해 항목, τ 통과)."""
    dead = {f["text"] for f in core["facts"]
            if f.get("invalidated_at") and f["predicate"] in Memory.PREDICATE_CARDINALITY}
    items = core["facts"] + core["events"]
    out = {}
    for k in G3.CLUSTER_KEYS:
        has = [x for x in items if k in x["text"]]
        dis = [x for x in has if x.get("lexical_role") == "distractor"]
        out[k] = dict(alive=sum(x["text"] not in dead for x in has), distractor=dis,
                      pass_tau=sum(max(x.get("importance", 0) or 0, x.get("emotional_weight", 0) or 0)
                                   >= M.TAU_IMPORTANCE for x in dis))
    return out


def vocab_curve(m, corpus, marks=CURVE_MARKS):
    """
    `corpus2_probe.vocab_curve`와 같은 방법(행을 새로 INSERT하지 않고 `user_deleted`로 눕혔다
    세운다)이지만 **처음부터 살아 있던 행만** 건드린다 — 그 함수는 전량을 눕혔다 전량을 세워,
    갱신으로 지워진 행(eval3에서 3행)까지 되살린다. 그리고 DB를 `prototype/`에 만들어서 못 부른다.
    """
    ids = [r[0] for r in m.db.execute(
        "SELECT event_id FROM event WHERE chat_id=? AND user_deleted=0 ORDER BY occurred_at, event_id",
        (soak.CHAT,))]
    m.db.execute("UPDATE event SET user_deleted=1 WHERE chat_id=? AND user_deleted=0", (soak.CHAT,))
    out, seen = [], 0
    for mk in [x for x in marks if x <= len(ids)]:
        while seen < mk:
            m.db.execute("UPDATE event SET user_deleted=0 WHERE event_id=?", (ids[seen],))
            seen += 1
        vp = VocabProbe(m._recall_vocab)
        n_user, fired, _ = C2.gate_breakdown(vp, corpus)
        out.append((seen, len(vp._recall_vocab), fired, n_user))
    return out


if __name__ == "__main__":
    sys.exit(main())
