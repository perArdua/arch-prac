# -*- coding: utf-8 -*-
r"""
theta_grid.py — θ 스위치(`THETA_ON_SCORE`)를 켤지 가르는 격자 (검B2 · 실험 번호 없음 · run_all 미등록) 🔄 (w9close · 2026-09-11) 마감 레인이 **실험 33**으로 번호를 주고 `run_all`에 올렸다 — 근거는 docs/11 «실험 결과 (33)» 머리 §0. 아래 출력 머리 문구는 레인 판 그대로다(이 레인은 출력을 안 바꾼다) 🔄 (w11b) 출력 머리도 «실험 33»으로 바꿨다 — RESULTS.txt 글자가 그 한 줄 움직인다

## 무엇을 묻는가

`theta_position.py`(레인 A)가 잰 것: θ가 `rel`에 걸린 동안 격자의 가중치 축 0/36 · recency 축 0/12.
켜면 축이 살지만 설계대로(θ 그대로) 켜면 오주입 11 → 51 · θ를 재유도해도 네 구성 전부 나빠졌다.
그 측정의 한계 셋 — 색인 21행 · `surfaced_count` 늘 0 · θ를 `rel` 모집단 기준으로만 — 을 이 파일이
걷는다: 규모 코퍼스(`eval3/` 레짐 셋) · 모의 `<meta>` 경로(`meta_arm`) · score 모집단 재유도.

## 하지 않는 것

**판정.** 켤지 말지는 제품 결정이다. 표와 «켜려면 무엇이 참이어야 하나»까지만 낸다. 스위치 기본값은
끈 채로 둔다. LLM · 임베딩 · 엔진을 부르지 않는다 — 소켓 연결 시도는 첫 회에 종료 1이다.

## 🔴 한 버전 (F21)

병렬 레인이 `prototype/**`을 고친다. 그래서 이 파일은 실행 머리에서 `prototype/`을 `%TEMP%`로
통째로 복사하고 **그 사본을 `sys.path` 맨 앞에 두고** prototype 모듈을 전부 먼저 import한다.
시작과 끝에 `sys.modules`를 훑어 원본에서 온 prototype 모듈이 하나라도 있으면 종료 1이다.
실행 중 원본이 바뀌면 적기만 한다 — 표는 사본 한 벌 위에서 끝난다.

## 재사용 (사본 금지 · F12)

코퍼스 열·분할·홀드아웃 = `engine_arms.Column`(`scorer_eval.split_blind`·`Holdout`) · θ 등컷 =
`engine_arms.derive_thetas` + `rel_dist.theta_at`/`actual_cut` · 칸 실행·지표 = `theta_position.run`
(`retrieval_sweep.run_cell` + 기록기) · 부호검정 = `engine_arms.judge` · 모의 `<meta>` = `meta_arm`의
`make_db`·`Mock`·`run_arm` · 열 제목 = `summary_prototype.TitleRule`/`Col`.
이 파일이 더한 것: 적재 단계를 미리 만든 색인의 복원으로 바꾸는 손잡이(실제 적재와 sha 대조) ·
score 모집단을 `Memory.retrieve` 자신에게 세게 하는 읽기(식을 옮겨 적지 않는다) · 열 병렬.

실행:
    PYTHONIOENCODING=utf-8 python -B experiments/theta_grid.py            # 0 · 자기 대조 실패 1
    PYTHONIOENCODING=utf-8 python -B experiments/theta_grid.py --corpora eval   # 한 열만(변이 시험용)
"""
import argparse
import hashlib
import importlib
import json
import math
import os
import shutil
import socket
import sqlite3
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
# 변이 시험은 이 파일의 사본을 %TEMP%에서 돌린다 — 그때도 이웃 모듈과 재료는 저장소 것을 읽는다.
EXP = os.environ.get("THETA_GRID_EXP") or HERE
REPO = os.path.dirname(os.path.abspath(EXP))
PROTO = os.path.join(REPO, "prototype")
sys.stdout.reconfigure(encoding="utf-8")

# ══════════════════════════════════════════════════════════════════════════
# 사본 — 모든 import보다 먼저
# ══════════════════════════════════════════════════════════════════════════

SNAP_ENV = "THETA_GRID_SNAPSHOT"
# 사본에서 먼저 import할 prototype 모듈 — 실험 모듈들이 뒤에서 원본 경로를 `sys.path` 맨 앞에
# 넣으므로, 그 뒤에 처음 import되는 prototype 모듈은 원본에서 온다. 여기서 전부 먼저 부른다.
PROTO_MODULES = ("memory", "soak", "gate_sweep", "embedding", "llm", "summarize", "fsm", "regen_job")


def sha1_of(path):
    with open(path, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()


def proto_shas(d):
    return {n: sha1_of(os.path.join(d, n)) for n in sorted(os.listdir(d)) if n.endswith(".py")}


def make_snapshot():
    root = tempfile.mkdtemp(prefix=f"w8theta_grid_{time.strftime('%Y%m%d_%H%M%S')}_")
    dst = os.path.join(root, "prototype")
    shutil.copytree(PROTO, dst, ignore=shutil.ignore_patterns("__pycache__", "*.db", "*.db-*"))
    with open(os.path.join(root, "COPIED_AT.txt"), "w", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    return dst


SNAP = os.environ.get(SNAP_ENV)
SNAP_OWNED = False
if not SNAP or not os.path.isdir(SNAP):
    SNAP, SNAP_OWNED = make_snapshot(), True
    os.environ[SNAP_ENV] = SNAP             # 자식 프로세스(열 병렬)가 같은 사본을 탄다
with open(os.path.join(os.path.dirname(SNAP), "COPIED_AT.txt"), encoding="utf-8") as _f:
    SNAP_AT = _f.read().strip()

sys.path.insert(0, SNAP)
for _m in PROTO_MODULES:
    importlib.import_module(_m)
sys.path.insert(0, EXP)

import memory as M                                           # noqa: E402
from memory import Memory                                    # noqa: E402
from soak import CHAT                                        # noqa: E402
import precision as P                                        # noqa: E402
import rel_dist as RD                                        # noqa: E402
import retrieval_sweep as RS                                 # noqa: E402
import theta_position as TP                                  # noqa: E402
import meta_arm as MA                                        # noqa: E402
import scorer_eval as SE                                     # noqa: E402
import summary_prototype as SP                               # noqa: E402
import engine_arms as EA                                     # noqa: E402
import eval3_probe as E3                                     # noqa: E402


def snapshot_leaks():
    """원본 `prototype/`에서 온 모듈 · 사본에서 오지 않은 필수 모듈 — 비어 있어야 한다."""
    snap = os.path.normcase(os.path.abspath(SNAP))
    orig = os.path.normcase(os.path.abspath(PROTO))
    bad = []
    for name, mod in sorted(sys.modules.items()):
        f = getattr(mod, "__file__", None)
        if f and os.path.normcase(os.path.dirname(os.path.abspath(f))) == orig:
            bad.append(f"{name} ← {f}")
    for name in PROTO_MODULES:
        f = getattr(sys.modules.get(name), "__file__", None) or "(없음)"
        if os.path.normcase(os.path.dirname(os.path.abspath(f))) != snap:
            bad.append(f"{name}이 사본에서 오지 않았다: {f}")
    return bad


# ══════════════════════════════════════════════════════════════════════════
# §0 사전 등록 — **값을 보기 전에** 여기 박았고, 실행하면 무엇보다 먼저 찍는다
# ══════════════════════════════════════════════════════════════════════════

W = 112
KS = TP.RECALL_KS                           # (1, 3, 5, 10)
THETA_POS = (False, True)                   # 끔 = θ가 rel에 · 켬 = θ가 최종 점수에(재유도)
WEIGHTS = ((0.8, 0.2), (0.6, 0.4), (0.4, 0.6))   # (W_REL, W_IMP) — 격자 2단의 두 값 + 아래 한 값
W_RECS = (0.0, 0.1, 0.4)                    # H = memory.RECENCY_HALF_LIFE(행) · theta_position 눈금의 양 끝
PENS_META = (0.01, 0.1)                     # 모의 `<meta>` 경로에서만. 0.0은 기본 경로와 같다(자기 대조)
REF = ((M.W_REL, M.W_IMP), M.SURFACED_PENALTY, M.W_REC)     # 현행 조합 — 옮겨 적지 않고 읽는다
DEFAULTS = {"THETA_ON_SCORE": False, "W_REC": 0.0, "RETRIEVAL_MODE": "lexical", "TOP_K": 5,
            "W_REL": 0.6, "W_IMP": 0.4, "SURFACED_PENALTY": 0.1}
PATH_BASE, PATH_META, PATH_SLOW = "base", "meta", "slow"
PATH_NAME = {PATH_BASE: "기본 경로 (surfaced_count 늘 0)",
             PATH_META: "모의 <meta> 경로 (meta_arm A1 재생 끝의 surfaced_count)"}
HO_OPENS = ("기준칸 대조", "판정", "홀드아웃 표")
HO_BUDGET = len(HO_OPENS)
# `rel_dist.theta_at`은 고유값마다 전 모집단을 다시 센다(이차). 고유값이 이보다 많으면 같은 정의를
# `rel_dist.actual_cut`으로 이분 탐색하고 증명한다(`theta_on`). 이하이면 두 길이 같은지 매번 대조한다.
THETA_AT_MAX_UNIQUE = 400
MIN_N = EA.MIN_N
ALPHA = EA.ALPHA
# 판정 칸의 낱말 — `engine_arms`의 판정 문자열은 화살표를 담고 있어 표에 그대로 싣지 않는다.
WORD = {EA.V_UP: "좋아짐", EA.V_DOWN: "나빠짐", EA.V_NULL: "검출 안 됨", EA.V_WEAK: "판정 불가"}
LAB_BETTER, LAB_WORSE, LAB_BOTH = "켬 나음", "켬 나쁨", "나음·나쁨 둘 다"
LAB_MIXED, LAB_NULL, LAB_WEAK = "엇갈림", "검출 안 됨", "판정 불가(n<6)"
ARROWS = "→←↑↓⇒⇐⟶"

PREREG = [
    ("분할", "문항 분할은 실험 26 규칙 — `scorer_eval.split_blind`(sha1(문항 id) 마지막 비트 · 라벨을 안 "
             "본다)를 `engine_arms.Column`이 부르는 그대로 쓴다.",
     f"θ 유도는 훈련 분할 문항만 읽는다. 홀드아웃은 열마다 `scorer_eval.Holdout`(예산 {HO_BUDGET}: "
     f"{' · '.join(HO_OPENS)})으로만 연다 — 모든 열의 `audit()`가 빈 목록이면 참, 아니면 종료 1."),
    ("한 버전", "모든 수는 실행 머리에서 뜬 `prototype/` 사본 한 벌 위에서 난다.",
     "시작과 끝에 `sys.modules`의 prototype 모듈 파일이 전부 사본 경로면 참, 하나라도 원본 경로면 "
     "종료 1. 실행 중 원본 sha가 바뀐 것은 적기만 한다(표는 사본 위다)."),
    ("θ", "켬 칸의 θ는 칸마다 «훈련 분할 문항 × τ 통과 행»의 최종 점수 모집단에서 «현행 θ가 같은 "
          "모집단의 rel에서 자르는 실제 비율 f»로 재유도한다(f = `engine_arms.derive_thetas`의 A0 칸 · "
          "θ = `rel_dist.theta_at`의 정의 — 고유값이 많으면 같은 정의를 `actual_cut`으로 이분 탐색·증명). "
          "최종 점수와 rel은 `Memory.retrieve`가 센 값을 읽는다.",
     "요청 f와 재유도 θ의 실제 컷을 칸마다 나란히 찍는다 — 판정 조건이 아니라 보고다. θ가 +∞(전량 "
     "컷)이면 그대로 적는다. τ 미달 행은 두 모집단에서 다 뺀다 — θ 컷은 어느 위치에서든 τ 통과 행에만 걸린다."),
    ("기본값", "끔 · 현행 가중치 · 현행 페널티 · W_REC 0의 eval 기준칸은 기록값 그대로다.",
     "eval 전 문항 값이 `retrieval_sweep.BASE_EXPECT` 다섯 칸과 같으면 참, 한 칸이라도 다르면 종료 1."),
    ("빠른 길", "칸 실행은 격자 하니스(`retrieval_sweep.run_cell`)의 적재 단계만 «미리 만든 색인의 복원»으로 "
                "바꾸고, 계측 DB 연결에 속도 PRAGMA 둘(`FAST_PRAGMAS`)을 건다.",
     "열마다 기준칸(끔)과 recency가 켜진 켬 칸 하나를 실제 적재 · 기본 PRAGMA로 한 번 더 돌려(켬은 θ 유도까지) "
     "문항 행과 `retrieve` 기록의 sha256 · θ가 같으면 참, 다르면 종료 1."),
    ("페널티 영점", "기본 경로에서 `surfaced_count`는 늘 0이라 페널티 축은 아무것도 못 뺀다 — 그래서 페널티 "
                    "축은 모의 `<meta>` 경로에서만 잰다.",
     "기본 경로의 surfaced 최댓값이 0이고 페널티 0.0 칸 = 현행 칸(sha)이면 참. 모의 경로에서 페널티 0.0 칸 = "
     "기본 경로의 같은 칸(sha)이면 참. 어긋나면 종료 1. 모의 경로의 surfaced 최댓값이 0이면 그 열의 페널티 "
     "축은 «판정 불가(채널 비어 있음)»로 적는다."),
    ("모의 경로", "모의 `<meta>` 경로 = 기본 경로 색인 + `meta_arm`의 A1 팔(character 턴마다 `apply_meta`)을 "
                  "현행 설정으로 코퍼스 끝까지 한 번 재생해 남은 `surfaced_count`만 옮겨 심은 색인.",
     "옮기기 전 두 색인의 (event_id · 요약 · 삭제 · importance · emotional_weight · source_from_seq)가 전 행 "
     "같고 옮긴 합 = 모의 `used_memories`의 event 선언 수면 참, 아니면 종료 1. ⚠️ 페널티가 재생 중 주입을 "
     "바꾸는 되먹임은 재지 않는다. 요약이 둘 이상의 행과 같은 행에 떨어진 선언은 «귀속 모호»로 센다."),
    ("판정 규칙", "«켬이 끔보다 낫다»는 코퍼스 열 × 같은 (W_IMP · 페널티 · W_REC) 칸마다 홀드아웃 문항별 "
                  f"부호검정(`engine_arms.judge` · 양측 정확 · 동률 버림 · α {ALPHA} · n ≥ {MIN_N})으로 말한다.",
     f"«{LAB_BETTER}» 참 ⇔ 근거 적중 수(주입 5건) 판정이 «좋아짐»(n ≥ {MIN_N} · p < {ALPHA} · 켬이 이긴 "
     f"문항이 더 많다)이고 홀드아웃 오주입 합이 켬 ≤ 끔. «{LAB_WORSE}» 참 ⇔ 근거 적중 판정이 «나빠짐»이거나 "
     f"오주입 판정이 «나빠짐»(켬이 유의하게 더 많다). 둘 다 참이면 «{LAB_BOTH}». 둘 다 거짓이면: 근거 적중이 "
     f"«좋아짐»인데 오주입 합이 늘었으면 «{LAB_MIXED}», n < {MIN_N}이면 «{LAB_WEAK}», 나머지는 «{LAB_NULL}» — "
     "여섯이 모든 관측을 나눈다. 머리 수 = 경로별로 현행 조합 칸에서 «켬 나음»인 열의 수 · 전 칸 집계를 "
     "함께 찍는다. «켜도 나아지지 않는다»(나음 0)도 정당한 결과다."),
    ("판정 안 함", "켤지 말지는 제품 결정이다 — 표와 «켜려면 무엇이 참이어야 하나»까지만 낸다. 스위치 "
                   "기본값은 끈 채로 둔다.",
     "시작과 끝에 `THETA_ON_SCORE` · `W_REC` · `RETRIEVAL_MODE` · `TOP_K` · 가중치 · 페널티가 현행값이면 "
     "참, 아니면 종료 1."),
    ("불변", "체크포인트 JSON을 쓰지 않고(sha만 뜬다), 네트워크를 쓰지 않는다(LLM · 임베딩 0회).",
     "`experiments/data/*.json` sha1이 시작 = 끝이고 소켓 연결 시도가 0회면 참. 연결 시도는 첫 회에 종료 1."),
    ("힘", "eval 홀드아웃은 2문항이라 그 열은 구조적으로 «판정 불가»다 — 값 보기 전에 안다. eval2 "
           "홀드아웃 6문항은 여섯이 전부 한쪽일 때만 판정된다.",
     "관측 조건이 아니라 산수다(동률 뺀 n의 최소 달성 p = 2·0.5ⁿ)."),
]


def print_prereg(names):
    print("=" * W)
    print("θ 스위치를 켤지 가르는 격자 — 검B2 (실험 33 · 보고 전용 · 판정하지 않는다)")  # 🔄 (w9close) 번호는 실험 33 · (w11b) 출력 머리도 그 번호로 바꿨다 — 옛 글자는 «실험 번호 없음»
    print("=" * W)
    print(f"\n  사본: {SNAP}  (복사 시각 {SNAP_AT})")
    for n, s in proto_shas(SNAP).items():
        if not n.startswith("test_"):
            print(f"    {s}  {n}")
    print("\n§0. 🔴 사전 등록 — 값을 하나도 보기 전에 코드 상수(`PREREG`)로 박은 것\n")
    for key, claim, how in PREREG:
        print(f"  [{key}] {claim}")
        print(f"        관측: {how}\n")
    print(f"  격자: THETA_ON_SCORE {THETA_POS} × (W_REL, W_IMP) {list(WEIGHTS)} × W_REC {list(W_RECS)}"
          f" (H = {M.RECENCY_HALF_LIFE}행)")
    print(f"        × 페널티: 기본 경로는 현행 {REF[1]} 하나(surfaced 0이라 축이 없다) · 모의 <meta> 경로는"
          f" {list(PENS_META)}")
    print(f"  현행 조합(머리 수의 칸): (W_REL, W_IMP) {REF[0]} · 페널티 {REF[1]} · W_REC {REF[2]}")
    print(f"  열: {', '.join(names)} — 열 제목은 `eval3_probe.CORPORA`의 키")
    print(f"  지표: recall@{'/'.join(map(str, KS))} = {P.RECALL_NAME}(순위 앞 k건) · 정밀도 = 정답 항목/검색 항목"
          f" · top1 = 1등 오주입 문항/검색≥1 문항 · 오주입 = 오주입 항목/검색 항목")


# ══════════════════════════════════════════════════════════════════════════
# 가드 — 네트워크 · 스위치 기본값 · 체크포인트
# ══════════════════════════════════════════════════════════════════════════

NET_TRIES = []
_SOCK_CONNECT = (socket.socket.connect, socket.socket.connect_ex)


def install_net_guard():
    def refuse(self, addr, *a, **k):
        NET_TRIES.append(repr(addr))
        raise SystemExit(f"🔴 네트워크 연결 시도 {addr!r} — 이 파일은 LLM · 임베딩 · 엔진을 부르지 않는다")
    socket.socket.connect = refuse
    socket.socket.connect_ex = refuse


def uninstall_net_guard():
    socket.socket.connect, socket.socket.connect_ex = _SOCK_CONNECT


def defaults_drift():
    return {k: getattr(M, k) for k, v in DEFAULTS.items() if getattr(M, k) != v}


CKPT_DIR = os.path.join(EXP, "data")


def ckpt_shas():
    return {n: sha1_of(os.path.join(CKPT_DIR, n)) for n in sorted(os.listdir(CKPT_DIR))
            if n.endswith(".json")}


# ══════════════════════════════════════════════════════════════════════════
# θ — score 모집단을 `retrieve`에게 세게 하고 등컷으로 유도
# ══════════════════════════════════════════════════════════════════════════

class _Pop:
    """`engine_arms.derive_thetas`가 읽는 채점기 모양 — 문항마다 이미 센 모집단을 돌려준다."""

    def __init__(self, by_ask):
        self.by_ask = by_ask

    def rels(self, ask, docs):
        return self.by_ask[ask]


def pop_by_ask(m, asks, now, wr, wi, pen, w_rec):
    """
    문항마다 τ 통과 행의 최종 점수 — `Memory.retrieve` 자신이 센 값이다(점수식을 옮겨 적지 않는다).
    θ를 −∞로 두고 최종 점수 위치로 옮기면 τ 통과 행이 전부 `scored`에 남는다. `(W_REL, W_IMP, 페널티,
    W_REC) = (1, 0, 0, 0)`이면 그 값이 곧 rel이다(1·rel + 0·imp − 0·surfaced).
    """
    snap, own = RS.snapshot_globals(), TP.snapshot_own()
    out, rows = {}, {}
    try:
        M.THETA_ON_SCORE, M.THETA_RELEVANCE, M.TOP_K = True, -math.inf, 10 ** 9
        M.W_REL, M.W_IMP, M.SURFACED_PENALTY, M.W_REC = wr, wi, pen, w_rec
        for a in asks:
            hits, _ = m.retrieve(CHAT, a, now)
            out[a] = [s for s, _ in hits]
            rows[a] = [r["summary"] for _, r in hits]
    finally:
        RS.restore_globals(snap)
        TP.restore_own(own)
    RS.assert_restored(snap, "θ 유도")
    TP.assert_own(own, "θ 유도")
    return out, rows


def theta_on(vals, f):
    """
    `rel_dist.theta_at(vals, f)`과 같은 정의 — min{x ∈ vals : actual_cut(vals, x) ≥ f}, 없으면 +∞.
    고유값이 `THETA_AT_MAX_UNIQUE` 이하면 `theta_at`을 그대로 부르고 이분 탐색 값과 대조한다. 넘으면
    (`theta_at`이 이차라 한 칸에 몇 분) 이분 탐색 값이 정의를 만족하는지 `actual_cut`으로 증명한다 —
    θ에서 ≥ f, 바로 앞 관측값에서 < f. `(θ, 길)`을 돌려준다. 어긋나면 종료 1.
    """
    u = sorted(set(vals))
    lo, hi = 0, len(u)
    while lo < hi:                          # actual_cut은 x에 대해 단조 비감소
        mid = (lo + hi) // 2
        if RD.actual_cut(vals, u[mid]) >= f:
            hi = mid
        else:
            lo = mid + 1
    fast = u[lo] if lo < len(u) else math.inf
    if len(u) <= THETA_AT_MAX_UNIQUE:
        slow = RD.theta_at(vals, f)
        if slow != fast:
            raise SystemExit(f"🔴 θ 이분 탐색 {fast} ≠ rel_dist.theta_at {slow} (f={f})")
        return slow, "theta_at"
    ok = (fast == math.inf and RD.actual_cut(vals, u[-1]) < f) or (
        fast != math.inf and RD.actual_cut(vals, fast) >= f
        and (lo == 0 or RD.actual_cut(vals, u[lo - 1]) < f))
    if not ok:
        raise SystemExit(f"🔴 θ 증명 실패 — {fast}가 등컷 정의를 만족하지 않는다 (f={f})")
    return fast, "이분+증명"


def f_of(col, rel_pop):
    """«현행 θ가 자르는 실제 비율» — `engine_arms.derive_thetas`의 A0 칸 그대로(모집단만 τ 통과 행)."""
    return EA.derive_thetas(col, [SimpleNamespace(key="A0")], {"A0": _Pop(rel_pop)})["A0"]


def derive(col, f, score_pop):
    """
    score 모집단의 등컷 θ. ⚠️ `derive_thetas`에 score 팔을 넘기지 않는 이유: 그 함수는 팔마다
    `rel_dist.theta_at`을 부르고, recency가 켜진 score 모집단(고유값 ≈ n)에서는 한 칸에 몇 분이다.
    같은 정의를 `theta_on`이 푼다(작으면 `theta_at` 그대로 · 크면 이분 탐색 + `actual_cut` 증명).
    """
    pop = [v for i in col.train for v in score_pop[col.asks[i]]]
    th, how = theta_on(pop, f)
    return dict(theta=th, f=f, cut=RD.actual_cut(pop, th), n=len(pop), how=how, uniq=len(set(pop)))


# ══════════════════════════════════════════════════════════════════════════
# 작업 — 열 병렬 (자식 프로세스에서 돈다)
# ══════════════════════════════════════════════════════════════════════════

def worker_init():
    install_net_guard()


_RETRIEVE0, _INGEST0, _ROOT0 = Memory.retrieve, RS.ingest, RS.ROOT


def task_guard(where):
    """자식 프로세스는 작업을 이어 받는다 — 앞 작업이 흘린 손잡이가 다음 작업을 오염시키면 안 된다 (G13)."""
    bad = defaults_drift()
    if Memory.retrieve is not _RETRIEVE0 or RS.ingest is not _INGEST0 or RS.ROOT != _ROOT0 or bad:
        raise SystemExit(f"🔴 G13 — 작업 사이로 손잡이가 새었다 ({where}): {bad}")


def _tmp_root():
    """격자 하니스는 `ROOT/prototype/.sweep.db`에 쓴다 — 작업마다 %TEMP% 아래 제 뿌리를 준다."""
    t = tempfile.mkdtemp(prefix="w8theta_")
    os.makedirs(os.path.join(t, "prototype"))
    return t


def col_rows(m):
    return [tuple(r) for r in m.db.execute(
        "SELECT event_id, summary, user_deleted, importance, emotional_weight, source_from_seq,"
        " surfaced_count FROM event WHERE chat_id=? ORDER BY event_id", (CHAT,))]


def stage_a1(name, idx, out_dir):
    """열 하나: 색인 틀(기본 경로) · rel 모집단과 f · recency 범위."""
    task_guard(f"A1 {name}")
    t = _tmp_root()
    col = EA.Column(name, t, idx)
    try:
        tpl = os.path.join(out_dir, f"base{idx}.db")
        dst = sqlite3.connect(tpl)
        col.m.db.commit()
        col.m.db.backup(dst)
        dst.close()
        asks = [col.asks[i] for i in col.train]
        rel_pop, rel_rows = pop_by_ask(col.m, asks, col.last, 1.0, 0.0, 0.0, 0.0)
        # rel을 `retrieve`에게 세게 한 읽기가 정말 rel인가 — 같은 함수(`coverage`)를 직접 불러 대조
        rel_bad = sum(1 for a in asks for s, d in zip(rel_pop[a], rel_rows[a])
                      if s != M.coverage(set(M.bigrams(a)), set(M.bigrams(d))))
        a0 = f_of(col, rel_pop)
        live = col.m.db.execute("SELECT source_from_seq FROM event WHERE chat_id=? AND user_deleted=0",
                                (CHAT,)).fetchall()
        rec = [x for x in (M.recency_penalty(col.last, r[0]) for r in live) if x is not None]
        rows = col_rows(col.m)
        return dict(name=name, idx=idx, tpl=tpl, train=list(col.train), ho=list(col.ho_ids),
                    n_scored=len(col.scored), docs=len(col.docs), last=col.last,
                    tau=len(rel_pop[asks[0]]) if asks else 0, rel_pop=rel_pop, rel_bad=rel_bad,
                    f=a0[1], n_rel=a0[3], rel_uniq=len({v for a in asks for v in rel_pop[a]}),
                    rec=(min(rec), max(rec), sum(1 for x in rec if x >= 0.99), len(rec)),
                    surf_max=max(r[6] for r in rows), n_ev=sum(len(col.ev_pos[q["id"]]) for q in col.scored),
                    leaks=snapshot_leaks())
    finally:
        col.close()
        shutil.rmtree(t, ignore_errors=True)


def stage_a2(name, idx):
    """열 하나: 모의 `<meta>` 재생(meta_arm A1 팔 — 현행 설정) → 행별 surfaced_count."""
    task_guard(f"A2 {name}")
    t = tempfile.mkdtemp(prefix="w8theta_meta_")
    corpus, ledger, _ = E3.load(name)
    arc = ledger.get("relationship_arc")
    # 관계 궤적이 없는 대장(eval2 · eval3)은 `Mock`이 읽는 키만 빈 궤적으로 채운 **복사본**을 넘긴다
    # (원본 YAML은 안 건드린다 · A8) — state_delta 0건. eval은 meta_arm.main의 A1과 같은 출발점.
    led = ledger if arc else dict(ledger, relationship_arc=[None])
    start = (arc[0]["stage"], arc[0]["affinity"]) if arc else None
    t0 = time.perf_counter()
    m = MA.make_db(t, f"a2-{idx}", corpus, ledger, start)
    try:
        fast_conn(m.db)                    # 재생은 턴마다 커밋한다 — 옮겨 심기 대조가 값을 지킨다
        a = MA.run_arm(m, corpus, MA.Mock(corpus, led))
        return dict(name=name, rows=col_rows(m), emitted=dict(a["emitted"]), gated=a["gated"],
                    hits=a["hits"], sec=time.perf_counter() - t0, leaks=snapshot_leaks())
    finally:
        m.db.close()
        shutil.rmtree(t, ignore_errors=True)


def make_meta_template(base_tpl, meta_tpl, a2):
    """기본 틀을 복사하고 surfaced_count만 옮겨 심는다. 다른 칸이 한 행이라도 다르면 종료 1."""
    shutil.copyfile(base_tpl, meta_tpl)
    db = sqlite3.connect(meta_tpl)
    try:
        base = [tuple(r) for r in db.execute(
            "SELECT event_id, summary, user_deleted, importance, emotional_weight, source_from_seq,"
            " surfaced_count FROM event WHERE chat_id=? ORDER BY event_id", (CHAT,))]
        if [r[:6] for r in base] != [r[:6] for r in a2["rows"]]:
            raise SystemExit(f"🔴 옮겨 심기: 재생 색인과 기본 틀이 surfaced 밖에서 다르다 — {a2['name']}")
        if any(r[6] for r in base):
            raise SystemExit(f"🔴 옮겨 심기: 기본 틀의 surfaced_count가 0이 아니다 — {a2['name']}")
        db.executemany("UPDATE event SET surfaced_count=? WHERE event_id=?",
                       [(r[6], r[0]) for r in a2["rows"] if r[6]])
        db.commit()
        got = db.execute("SELECT SUM(surfaced_count) FROM event WHERE chat_id=?", (CHAT,)).fetchone()[0] or 0
    finally:
        db.close()
    if got != a2["emitted"].get("used_event", 0):
        raise SystemExit(f"🔴 옮겨 심기: surfaced 합 {got} ≠ event 선언 {a2['emitted'].get('used_event', 0)}"
                         f" — {a2['name']}")
    mult = Counter(r[1] for r in a2["rows"])
    return dict(sum=got, max=max((r[6] for r in a2["rows"]), default=0),
                rows_pos=sum(1 for r in a2["rows"] if r[6]),
                amb=sum(r[6] for r in a2["rows"] if mult[r[1]] > 1),
                on_deleted=sum(r[6] for r in a2["rows"] if r[2]))


# 계측 DB 연결에만 거는 PRAGMA — 값이 아니라 속도만 바꾼다. 트랜잭션 밖의 SELECT는 문장마다 파일 잠금을
# 잡고 놓는다(Windows 파일 DB 실측 ≈ 94 µs · 트랜잭션 안 ≈ 1 µs). `W_REC`가 켜지면 `_admit`이 τ 통과 행마다
# SELECT를 하나 더 하므로 3,000행에서 그 잠금이 한 칸을 수십 초로 만든다. 값이 같다는 것은 «빠른 길» 대조가
# 실제 적재·기본 PRAGMA 경로와 sha로 확인한다(recency가 켜진 칸 포함).
FAST_PRAGMAS = ("PRAGMA locking_mode=EXCLUSIVE", "PRAGMA synchronous=OFF")


def fast_conn(db):
    for p in FAST_PRAGMAS:
        db.execute(p)


def template_ingest(tpl):
    """`retrieval_sweep.run_cell`의 적재 단계 대신 — 미리 만든 색인을 통째로 복원한다."""
    def ingest(m, corpus, ledger, timed=False):
        src = sqlite3.connect(tpl)
        try:
            src.backup(m.db)
        finally:
            src.close()
        fast_conn(m.db)
    return ingest


def _sha(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
                          .encode("utf-8")).hexdigest()


def run_one(cx, col, cell, tpl, m_tpl, f):
    """칸 하나 — θ(켬이면 재유도) → `theta_position.run`. 문항별 값만 돌려준다(순위 전량은 무겁다)."""
    path, on, (wr, wi), pen, w_rec = cell
    th = None
    if on:
        asks = [col.asks[i] for i in col.train]
        score_pop, _ = pop_by_ask(m_tpl, asks, col.last, wr, wi, pen, w_rec)
        th = derive(col, f, score_pop)
        theta = th["theta"]
    else:
        theta = M.THETA_RELEVANCE
    keep = RS.ingest
    if path != PATH_SLOW:
        RS.ingest = template_ingest(tpl)
    try:
        tot, rec = TP.run(cx, "lexical", theta, 0.80, wr, wi, pen, on_score=on, w_rec=w_rec)
    finally:
        RS.ingest = keep
    if RS.ingest is not keep:
        raise SystemExit("🔴 G13 — 적재 단계 손잡이가 새었다")
    mt = TP.metrics(cx, tot, rec)             # recall@TOP_K = 격자 회상 대조(기록기 자기 대조)
    rows = []
    for r in tot["rows"]:
        q = cx.by_id[r["id"]]
        call = rec.calls.get(q["ask"], {"hits": [], "full": []})
        one = SimpleNamespace(scored=[q], key_of=cx.key_of)
        rows.append(dict(r, rk={k: TP.recall_at(one, rec, k)[0] for k in KS},
                         npass=len(call["full"]), inj=sorted(call["hits"])))
    return dict(cell=cell, theta=theta, th=th, rows=rows, surf=rec.surf, npass_max=mt["npass_max"],
                over_k=mt["over_k"], sha=_sha([tot["rows"], sorted(rec.calls.items())]))


def stage_b(name, idx, cells, tpls, f):
    """열 하나의 칸 묶음. `tpls` = {경로: 틀 파일} · `f` = A1이 잰 등컷 비율."""
    task_guard(f"B {name}")
    t = _tmp_root()
    roots = RS.ROOT
    RS.ROOT = t
    col = EA.Column(name, t, idx)
    mems = {}
    try:
        cx = SimpleNamespace(env=col.env, cache={}, base_theta=dict(M.THETA_BY_MODE), scored=col.scored,
                             key_of=col.key_of, asks={q["ask"] for q in col.scored},
                             by_id={q["id"]: q for q in col.scored})
        out = []
        for cell in cells:
            if cell[0] == PATH_SLOW:
                # 느린 길은 θ 유도까지 실제 적재 색인(`Column`이 `seed`+`ingest`로 만든 것 · 기본 PRAGMA)에서
                out.append(run_one(cx, col, cell, None, col.m, f))
                continue
            src = cell[0]
            if src not in mems:
                mm = Memory(os.path.join(t, f"deriv-{src}.db"))
                s = sqlite3.connect(tpls[src])
                s.backup(mm.db)
                s.close()
                fast_conn(mm.db)
                mems[src] = mm
            out.append(run_one(cx, col, cell, tpls[src], mems[src], f))
        return dict(name=name, out=out, leaks=snapshot_leaks(), drift=defaults_drift())
    finally:
        for mm in mems.values():
            mm.db.close()
        col.close()
        RS.ROOT = roots
        shutil.rmtree(t, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════════
# 칸 목록
# ══════════════════════════════════════════════════════════════════════════

def cells_for(path):
    if path == PATH_BASE:
        return [(PATH_BASE, on, w, REF[1], r) for on in THETA_POS for w in WEIGHTS for r in W_RECS]
    return [(PATH_META, on, w, p, r) for on in THETA_POS for w in WEIGHTS for p in PENS_META for r in W_RECS]


def check_cells():
    """자기 대조용 칸 — 페널티 0.0(기본 · 모의)과 실제 적재(느린 길)."""
    return ([(PATH_BASE, on, REF[0], 0.0, REF[2]) for on in THETA_POS],
            [(PATH_META, on, REF[0], 0.0, REF[2]) for on in THETA_POS],
            [(PATH_SLOW, False, REF[0], REF[1], REF[2]), (PATH_SLOW, True, REF[0], REF[1], max(W_RECS))])


def chunks(seq, k):
    k = max(1, min(k, len(seq)))
    return [seq[i::k] for i in range(k)]


# ══════════════════════════════════════════════════════════════════════════
# 집계 · 판정
# ══════════════════════════════════════════════════════════════════════════

def agg(res, ids):
    """문항 부분집합의 지표. 분모를 값에서 떼지 않는다 (G15)."""
    s = set(ids)
    rows = [r for r in res["rows"] if r["id"] in s]
    t = P.cell_totals(rows)
    return dict(rk={k: (sum(r["rk"][k] for r in rows), t["ev_tot"]) for k in KS},
                prec=(t["ret"] - t["mis"], t["ret"]), mis=(t["mis"], t["ret"]),
                top1=(t["top1"], t["top1_n"]), ev=(t["ev_hit"], t["ev_tot"]), ties=len(t["ties"]))


def classify(rj, mj, mis_on, mis_off):
    """사전 등록 «판정 규칙» 그대로. `rj`·`mj` = `engine_arms.judge`의 반환(끝 칸이 판정)."""
    better = rj[5] == EA.V_UP and mis_on <= mis_off
    worse = rj[5] == EA.V_DOWN or mj[5] == EA.V_DOWN
    if better and worse:
        return LAB_BOTH
    if better:
        return LAB_BETTER
    if worse:
        return LAB_WORSE
    if rj[5] == EA.V_UP:
        return LAB_MIXED
    return LAB_WEAK if rj[5] == EA.V_WEAK else LAB_NULL


def judge_pair(res_on, res_off, ids):
    on = {r["id"]: r for r in res_on["rows"]}
    off = {r["id"]: r for r in res_off["rows"]}
    rj = EA.judge([on[i]["ev_hit"] for i in ids], [off[i]["ev_hit"] for i in ids], "high")
    mj = EA.judge([on[i]["mis"] for i in ids], [off[i]["mis"] for i in ids], "low")
    mo, mf = sum(on[i]["mis"] for i in ids), sum(off[i]["mis"] for i in ids)
    return dict(rj=rj, mj=mj, mis_on=mo, mis_off=mf, lab=classify(rj, mj, mo, mf))


# ══════════════════════════════════════════════════════════════════════════
# 표 — 열 = 코퍼스 (`TitleRule`) · 화살표 없음
# ══════════════════════════════════════════════════════════════════════════

TABLE_BAD = []


def table(caption, cols, rows, cw=22):
    """`cols`: `summary_prototype.Col`(이름 = 코퍼스). 규칙 위반과 화살표는 모아 끝에서 종료 1."""
    lw = max([12] + [len(r[0]) + 3 for r in rows])     # 행 라벨은 자르지 않는다 — 잘리면 두 칸이 한 이름이 된다
    rule = SP.TitleRule()
    bad = rule.audit(cols) + rule.audit_rows([r[0] for r in rows])
    texts = [caption] + [c.name for c in cols] + [c.title() for c in cols] + \
            [r[0] for r in rows] + [str(x) for r in rows for x in r[1]]
    bad += [f"화살표 «{t}»" for t in texts if any(a in t for a in ARROWS)]
    TABLE_BAD.extend(f"«{caption}» {b}" for b in bad)
    print(f"\n  {caption}")
    heads = [c.name.split(" · ") for c in cols]
    for line in range(max(len(h) for h in heads)):
        lab = "칸" if line == 0 else ""
        print("  " + lab.ljust(lw) + "".join((h[line] if line < len(h) else "")[:cw - 1].ljust(cw)
                                               for h in heads))
    print("  " + "-" * (lw + cw * len(cols)))
    for lab, cells in rows:
        print("  " + lab[:lw - 1].ljust(lw) + "".join(str(x)[:cw - 1].ljust(cw) for x in cells))
    for c in cols:
        print(f"     · {c.title()}")


def frac(p):
    return f"{p[0]}/{p[1]}" if p[1] else f"{p[0]}/0"


def cell_label(cell, with_pen):
    _, on, (wr, wi), pen, w_rec = cell
    s = f"{'켬' if on else '끔'} · W_IMP {wi} · W_REC {w_rec}"
    return s + (f" · 페널티 {pen}" if with_pen else "")


def colname(name, path):
    return name if path == PATH_BASE else f"{name} · 모의 <meta>"


# ══════════════════════════════════════════════════════════════════════════
# 본 실행
# ══════════════════════════════════════════════════════════════════════════

def title(s, ch="="):
    print("\n" + ch * W)
    print(s)
    print(ch * W)


def pick_names(spec):
    out = []
    for tok in spec.split(","):
        tok = tok.strip()
        out.append(E3.NAMES[int(tok)] if tok.isdigit() else tok)
    bad = [n for n in out if n not in E3.NAMES]
    if bad:
        raise SystemExit(f"🔴 모르는 열: {bad} — {E3.NAMES}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpora", default=",".join(E3.NAMES))
    ap.add_argument("--workers", type=int, default=max(1, min(12, (os.cpu_count() or 2) - 2)))
    ap.add_argument("--split", type=int, default=4, help="규모 열(eval3)의 칸 묶음 수")
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)
    names = pick_names(args.corpora)
    print_prereg(names)
    fail = []
    t_start = time.time()
    proto_before = proto_shas(PROTO)
    ck0 = ckpt_shas()
    lk = snapshot_leaks()
    if lk:
        fail.append(f"한 버전(시작): {lk}")
    if defaults_drift():
        fail.append(f"판정 안 함(시작): 스위치가 현행값이 아니다 {defaults_drift()}")
    if RS.STAGE2_WEIGHTS and not set(RS.STAGE2_WEIGHTS) <= set(WEIGHTS):
        fail.append(f"격자 2단 가중치 {RS.STAGE2_WEIGHTS}가 이 격자에 없다")
    if REF[0] not in WEIGHTS or REF[1] not in PENS_META or REF[2] not in W_RECS:
        fail.append(f"현행 조합 {REF}이 격자 밖이다")
    install_net_guard()
    if fail:
        print("\n  🔴 착수 대조 실패:\n    " + "\n    ".join(fail))
        return 1
    out_dir = tempfile.mkdtemp(prefix="w8theta_tpl_")
    try:
        a1, a2, meta, res = run_all_tasks(names, args, out_dir)
    finally:
        uninstall_net_guard()
    rc = report(names, a1, a2, meta, res, fail)
    shutil.rmtree(out_dir, ignore_errors=True)

    # ── 마감 대조 ──
    title("§9. 마감 대조 — 한 버전 · 스위치 · 체크포인트 · 네트워크 · 표 규칙")
    lk = snapshot_leaks() + [l for d in list(a1.values()) + list(a2.values()) for l in d["leaks"]] + \
        [l for rs in res.values() for b in rs["_leaks"] for l in b]
    print(f"  한 버전: 원본 경로에서 온 prototype 모듈 {len(lk)}개 (부모 + 자식 작업 전부)"
          f" {'' if not lk else lk[:3]}")
    if lk:
        fail.append("한 버전(끝)")
    drift = defaults_drift()
    wdrift = [d for rs in res.values() for d in rs["_drift"] if d]
    print(f"  스위치: 부모 {drift or '현행값'} · 자식 작업 끝 {wdrift or '전부 현행값'}")
    if drift or wdrift:
        fail.append("판정 안 함(끝): 스위치가 새었다")
    changed = {n for n in set(proto_before) | set(proto_shas(PROTO))
               if proto_before.get(n) != proto_shas(PROTO).get(n)}
    snap_vs_orig = {n for n, s in proto_shas(SNAP).items() if proto_shas(PROTO).get(n) != s}
    print(f"  원본 prototype/: 실행 중 바뀐 파일 {sorted(changed) or '없음'} · 끝에서 사본과 다른 파일"
          f" {sorted(snap_vs_orig) or '없음'} — 표는 사본({SNAP_AT}) 한 벌 위다")
    ck1 = ckpt_shas()
    dck = sorted(n for n in set(ck0) | set(ck1) if ck0.get(n) != ck1.get(n))
    print(f"  체크포인트 JSON {len(ck1)}개: sha 차이 {dck or 0}")
    if dck:
        fail.append(f"불변: 체크포인트가 바뀌었다 {dck}")
    print(f"  네트워크 연결 시도: {len(NET_TRIES)}회")
    if NET_TRIES:
        fail.append("불변: 네트워크")
    print(f"  표 규칙(TitleRule · 화살표) 위반: {len(TABLE_BAD)}")
    for b in TABLE_BAD[:10]:
        print(f"    {b}")
    if TABLE_BAD:
        fail.append("표 규칙")
    print(f"  걸린 시간 {time.time() - t_start:.0f}초")
    if SNAP_OWNED:
        shutil.rmtree(os.path.dirname(SNAP), ignore_errors=True)
    if fail or rc:
        print("\n  🔴 자기 대조 실패:\n    " + "\n    ".join(fail))
        return 1
    print("\n  종료 0 — 판정하지 않았다. 켤지 말지는 제품 결정이다.")
    return 0


def run_all_tasks(names, args, out_dir):
    """A1(틀·f) · A2(모의 재생) → B(칸 묶음). A1이 끝난 열은 기본 경로 칸부터 바로 돈다."""
    a1, a2, meta, res = {}, {}, {}, {n: {"_leaks": [], "_drift": []} for n in names}
    base_cells = cells_for(PATH_BASE)
    chk_base, chk_meta, chk_slow = check_cells()
    ex = ProcessPoolExecutor(max_workers=args.workers, initializer=worker_init)
    try:
        pend = {}
        for n in names:
            i = E3.NAMES.index(n)
            pend[ex.submit(stage_a1, n, i, out_dir)] = ("a1", n)
            pend[ex.submit(stage_a2, n, i)] = ("a2", n)
        while pend:
            done, _ = wait(pend, return_when=FIRST_COMPLETED)
            for fu in done:
                kind, n = pend.pop(fu)
                r = fu.result()                    # 자식의 SystemExit도 여기서 다시 던져진다
                i = E3.NAMES.index(n)
                k = 1 if n in E3.NAMES[:2] else args.split
                if kind == "a1":
                    a1[n] = r
                    for ch in chunks(base_cells + chk_base + chk_slow, k):
                        pend[ex.submit(stage_b, n, i, ch, {PATH_BASE: r["tpl"]}, r["f"])] = ("b", n)
                elif kind == "a2":
                    a2[n] = r
                if kind in ("a1", "a2") and n in a1 and n in a2 and n not in meta:
                    mt = os.path.join(out_dir, f"meta{i}.db")
                    meta[n] = make_meta_template(a1[n]["tpl"], mt, a2[n])
                    for ch in chunks(cells_for(PATH_META) + chk_meta, 2 * k if k > 1 else 1):
                        pend[ex.submit(stage_b, n, i, ch, {PATH_META: mt}, a1[n]["f"])] = ("b", n)
                if kind == "b":
                    for o in r["out"]:
                        res[n][o["cell"]] = o
                    res[n]["_leaks"].append(r["leaks"])
                    res[n]["_drift"].append(r["drift"])
    except BaseException:
        # 한 작업이 죽으면 남은 작업을 기다리지 않는다 — 자기 대조 실패는 곧장 종료 1이어야 한다.
        ex.shutdown(wait=False, cancel_futures=True)
        raise
    ex.shutdown(wait=True)
    return a1, a2, meta, res


def report(names, a1, a2, meta, res, fail):
    """§1~§8. `fail`에 자기 대조 실패를 쌓는다. 반환은 쓰지 않는다(0)."""
    hos = {n: SE.Holdout(a1[n]["ho"], HO_BUDGET) for n in names}
    train = {n: a1[n]["train"] for n in names}

    # ── §1 재료 ─────────────────────────────────────────────────────────
    title("§1. 재료 — 열마다 문항 · 색인 · 모의 <meta> 재생 · recency 입력")
    for n in names:
        a, b, mt = a1[n], a2[n], meta[n]
        print(f"  {n}")
        print(f"    채점 {a['n_scored']}문항 = 훈련 {len(a['train'])} + 홀드아웃 {len(a['ho'])} · 근거 {a['n_ev']} ·"
              f" 살아 있는 색인 {a['docs']}행 · τ({M.TAU_IMPORTANCE}) 통과 {a['tau']}행 · now_seq {a['last']}행")
        print(f"    모의 <meta> 재생 {b['sec']:.0f}초 · 게이트 통과 {b['gated']}턴 · 주입 턴 {b['hits']} · 선언 "
              f"{dict(sorted(b['emitted'].items()))}")
        print(f"    옮겨 심은 surfaced 합 {mt['sum']} · 최댓값 {mt['max']} · >0인 행 {mt['rows_pos']} · "
              f"귀속 모호(요약이 둘 이상의 행과 같은 행) {mt['amb']}/{mt['sum']} · 삭제 행 {mt['on_deleted']}")
        lo, hi, sat, nn = a["rec"]
        print(f"    recency 페널티(H={M.RECENCY_HALF_LIFE}행 · now_seq에서) 범위 {lo:.3f}~{hi:.3f} ·"
              f" 0.99 이상 {sat}/{nn}행")

    # ── §2 자기 대조 ────────────────────────────────────────────────────
    title("§2. 자기 대조 — 사전 등록 [기본값] [빠른 길] [페널티 영점] [θ의 rel 읽기]")
    ref_off = (PATH_BASE, False, REF[0], REF[1], REF[2])
    for n in names:
        r = res[n]
        miss = [c for c in cells_for(PATH_BASE) + cells_for(PATH_META) + sum(check_cells(), [])
                if c not in r]
        if miss:
            fail.append(f"{n}: 칸 {len(miss)}개가 안 돌았다")
            print(f"  🔴 {n}: 칸 {len(miss)}개가 안 돌았다")
            continue
        slow = check_cells()[2]
        same_slow = all(r[(PATH_BASE,) + c[1:]]["sha"] == r[c]["sha"] and
                        r[(PATH_BASE,) + c[1:]]["theta"] == r[c]["theta"] for c in slow)
        pen0 = all(r[(PATH_BASE, on, REF[0], 0.0, REF[2])]["sha"] == r[(PATH_BASE, on, REF[0], REF[1], REF[2])]["sha"]
                   for on in THETA_POS)
        meta0 = all(r[(PATH_META, on, REF[0], 0.0, REF[2])]["sha"] == r[(PATH_BASE, on, REF[0], REF[1], REF[2])]["sha"]
                    for on in THETA_POS)
        base_surf = max(r[c]["surf"] for c in cells_for(PATH_BASE))
        meta_surf = max(r[c]["surf"] for c in cells_for(PATH_META))
        print(f"  {n}: 빠른 길 = 느린 길 {'참' if same_slow else '🔴 거짓'} · 기본 경로 surfaced 최댓값 {base_surf}"
              f" · 페널티 0.0 = 현행(기본) {'참' if pen0 else '🔴 거짓'} · 모의 페널티 0.0 = 기본"
              f" {'참' if meta0 else '🔴 거짓'} · 모의 surfaced 최댓값 {meta_surf}"
              f" · θ의 rel 읽기 ≠ coverage {a1[n]['rel_bad']}쌍")
        if not same_slow:
            fail.append(f"빠른 길 ≠ 느린 길 — {n}")
        if base_surf or not pen0:
            fail.append(f"페널티 영점(기본 경로) — {n}")
        if not meta0:
            fail.append(f"페널티 영점(모의 경로) — {n}")
        if a1[n]["rel_bad"]:
            fail.append(f"θ의 rel 읽기 ≠ coverage — {n}")
        if meta_surf == 0:
            print(f"    ⚠️ {n}: 모의 surfaced 최댓값 0 — 이 열의 페널티 축은 판정 불가(채널 비어 있음)")
    if "eval" in names and ref_off in res["eval"]:
        # BASE_EXPECT는 전 문항 값이다 — 홀드아웃이 섞이므로 그 열을 여는 것으로 센다.
        ids = list(train["eval"]) + list(hos["eval"].open("기준칸 대조"))
        t = agg(res["eval"][ref_off], ids)
        got = dict(recall=t["ev"], mis=t["mis"][0], pooled=t["mis"], top1=t["top1"], ties=t["ties"])
        ok = got == RS.BASE_EXPECT
        print(f"  eval 기준칸(끔 · {REF}) 전 {len(ids)}문항: {got} · BASE_EXPECT {RS.BASE_EXPECT}"
              f" {'같다' if ok else '🔴 다르다'}")
        if not ok:
            fail.append("기본값: eval 기준칸 ≠ BASE_EXPECT")
    if fail:
        print("\n  🔴 자기 대조가 깨졌다 — 아래 표는 찍지 않는다:\n    " + "\n    ".join(fail))
        return 1

    # ── §3 θ ───────────────────────────────────────────────────────────
    title("§3. score 모집단에서 재유도한 θ — 칸마다 (요청 f · 실제 컷 · 모집단 n)")
    print("  모집단 = 훈련 분할 문항 × τ 통과 행 · 값 = `Memory.retrieve`가 센 최종 점수(θ −∞ · 최종 점수 위치)")
    print("  f = 현행 θ(" + f"{M.THETA_RELEVANCE}" + ")가 같은 모집단의 rel에서 자르는 실제 비율(`rel_dist.actual_cut`)")
    for n in names:
        a = a1[n]
        print(f"    {n}: rel 모집단 n={a['n_rel']}쌍(훈련 {len(a['train'])}문항 × τ 통과 {a['tau']}행) · 고유값 "
              f"{a['rel_uniq']} · f = {a['f']:.4f}")
    for path in (PATH_BASE, PATH_META):
        cols = [SP.Col(colname(n, path), f"훈련 {len(train[n])}문항 × τ 통과 {a1[n]['tau']}행",
                       f"색인 {a1[n]['docs']}행", f"score 모집단 등컷 θ · 요청 f / 실제 컷 · {PATH_NAME[path]}")
                for n in names]
        rows = []
        for c in cells_for(path):
            if not c[1]:
                continue
            cells = []
            for n in names:
                th = res[n][c]["th"]
                cells.append(f"{th['theta']:.4f} {th['f']:.3f}/{th['cut']:.3f}" if th["theta"] != math.inf
                             else f"+inf(전량) {th['f']:.3f}/{th['cut']:.3f}")
            rows.append((cell_label(c, path == PATH_META), cells))
        table(f"θ — {PATH_NAME[path]} · 칸 = θ 요청f/실제컷", cols, rows)
        how = Counter(res[n][c]["th"]["how"] for n in names for c in cells_for(path) if c[1])
        gap = max(abs(res[n][c]["th"]["cut"] - res[n][c]["th"]["f"]) for n in names for c in cells_for(path) if c[1])
        print(f"     θ를 구한 길: {dict(how)} · |실제 컷 − 요청 f| 최댓값 {gap:.4f}")
        npass = [(n, c, res[n][c]["npass_max"], res[n][c]["over_k"]) for n in names for c in cells_for(path)]
        for on in THETA_POS:
            mx = {n: max(x[2] for x in npass if x[0] == n and x[1][1] == on) for n in names}
            print(f"     {'켬' if on else '끔'} — 문항별 |θ 통과| 최댓값(열마다 칸 중 최대): {mx} · TOP_K {M.TOP_K}")

    # ── §4·§5 격자 ──────────────────────────────────────────────────────
    ho_tab = {n: hos[n].open("홀드아웃 표") for n in names}
    metrics = [(f"recall@{k}", lambda t, k=k: frac(t["rk"][k]), f"근거 적중/근거 · 순위 앞 {k}건") for k in KS] + [
        ("정밀도", lambda t: frac(t["prec"]), "정답 항목/검색 항목"),
        ("top1 오주입", lambda t: frac(t["top1"]), "1등 오주입 문항/검색≥1 문항"),
        ("오주입", lambda t: frac(t["mis"]), "오주입 항목/검색 항목")]
    for sec, path in (("§4", PATH_BASE), ("§5", PATH_META)):
        title(f"{sec}. 🔴 격자 — {PATH_NAME[path]} · 칸 = 훈련 | 홀드아웃")
        if path == PATH_META:
            print("  🔴 이 절의 값은 전부 **모의 <meta>** 값이다 — `used_memories`는 LLM이 아니라 meta_arm의 자가저작"
                  " 규칙(«주입된 기억을 전부 썼다»)이 냈다.")
            print(f"  {MA.MOCK_BANNER}")
        for mname, fn, unit in metrics:
            cols = [SP.Col(colname(n, path), f"훈련 {len(train[n])}문항 | 홀드아웃 {len(ho_tab[n])}문항",
                           f"색인 {a1[n]['docs']}행", f"{mname} ({unit}) · {PATH_NAME[path]}") for n in names]
            rows = [(cell_label(c, path == PATH_META),
                     [f"{fn(agg(res[n][c], train[n]))} | {fn(agg(res[n][c], ho_tab[n]))}" for n in names])
                    for c in cells_for(path)]
            table(f"{mname} — {unit}", cols, rows)

    # ── §6 축이 살아 있나 (훈련 분할 · 서술) ─────────────────────────────
    title("§6. 축이 살아 있나 — 한 축만 흔들 때 주입 집합이 바뀐 문항 (훈련 분할 · 서술 전용)")
    print("  칸 = 바뀐 문항/훈련 문항 · 다른 축은 현행 조합 · 페널티 축은 모의 <meta> 경로에서만")
    axes = [("W_IMP", PATH_BASE, lambda on: [(PATH_BASE, on, w, REF[1], REF[2]) for w in WEIGHTS]),
            ("W_REC", PATH_BASE, lambda on: [(PATH_BASE, on, REF[0], REF[1], r) for r in W_RECS]),
            ("페널티", PATH_META, lambda on: [(PATH_BASE, on, REF[0], REF[1], REF[2])] +
             [(PATH_META, on, REF[0], p, REF[2]) for p in PENS_META])]
    cols = [SP.Col(n, f"훈련 {len(train[n])}문항", f"색인 {a1[n]['docs']}행",
                   "주입 집합이 바뀐 문항 (축의 모든 값 쌍 중 하나라도)") for n in names]
    rows = []
    for ax, _, cl in axes:
        for on in THETA_POS:
            cells = []
            for n in names:
                rs = [{r["id"]: tuple(r["inj"]) for r in res[n][c]["rows"]} for c in cl(on)]
                ch = sum(1 for i in train[n] if len({x[i] for x in rs}) > 1)
                cells.append(f"{ch}/{len(train[n])}")
            rows.append((f"{ax} 축 · {'켬' if on else '끔'}" + (" · 모의 <meta>" if ax == "페널티" else ""), cells))
    table("축마다 주입 집합이 바뀐 문항 · 페널티 행은 기본 경로(페널티 무관) 대 모의 <meta> 두 값", cols, rows)

    # ── §7 판정 규칙 적용 (홀드아웃) ─────────────────────────────────────
    title("§7. 사전 등록 판정 규칙을 홀드아웃에 적용 — 켬(재유도 θ) 대 끔(θ 현행) · 같은 칸끼리")
    ho_j = {n: hos[n].open("판정") for n in names}
    tally = {}
    heads = {}
    n_tests = n_power = 0
    for path in (PATH_BASE, PATH_META):
        pairs = sorted({(c[2], c[3], c[4]) for c in cells_for(path)}, key=lambda x: (x[0][1], x[1], x[2]))
        cols = [SP.Col(colname(n, path), f"홀드아웃 {len(ho_j[n])}문항", f"색인 {a1[n]['docs']}행",
                       f"사전 등록 판정 · 근거 적중 부호검정 + 오주입 합 · {PATH_NAME[path]}") for n in names]
        rl, rr, rm = [], [], []
        for w, pen, w_rec in pairs:
            lab = cell_label((path, True, w, pen, w_rec), path == PATH_META).replace("켬 · ", "")
            c1, c2, c3 = [], [], []
            for n in names:
                j = judge_pair(res[n][(path, True, w, pen, w_rec)], res[n][(path, False, w, pen, w_rec)], ho_j[n])
                tally.setdefault((path, j["lab"]), 0)
                tally[(path, j["lab"])] += 1
                if (w, pen, w_rec) == REF:
                    heads.setdefault(path, Counter())[j["lab"]] += 1
                rw, rl_, rt, rp, _, rv = j["rj"]
                mw, ml, mt_, mp, _, mv = j["mj"]
                n_tests += 2
                n_power += (rw + rl_ >= MIN_N) + (mw + ml >= MIN_N)
                c1.append(j["lab"])
                c2.append(f"{WORD[rv]} {rw}/{rl_}/{rt} p={rp:.3f}")
                c3.append(f"{WORD[mv]} {j['mis_on']}:{j['mis_off']} p={mp:.3f}")
            rl.append((lab, c1))
            rr.append((lab, c2))
            rm.append((lab, c3))
        table(f"판정 라벨 — {PATH_NAME[path]}", cols, rl)
        table(f"근거 적중 부호검정 — 켬 이김/짐/동률 · p — {PATH_NAME[path]}", cols, rr)
        table(f"오주입 — 판정 · 합 켬:끔 · p — {PATH_NAME[path]}", cols, rm)
    print(f"\n  검정 {n_tests}회 · 동률 뺀 n ≥ {MIN_N}(힘 있음) {n_power}회 · 다중 검정 보정 없음")
    print("\n  🔴 머리 수 — 현행 조합 칸((W_REL, W_IMP) "
          f"{REF[0]} · 페널티 {REF[1]} · W_REC {REF[2]})에서 라벨별 열 수:")
    for path in (PATH_BASE, PATH_META):
        h = heads.get(path, Counter())
        print(f"    {PATH_NAME[path]}: «{LAB_BETTER}» {h[LAB_BETTER]}/{len(names)}열 · "
              + " · ".join(f"«{k}» {v}" for k, v in sorted(h.items()) if k != LAB_BETTER))
    print("  전 칸 집계(열 × 칸):")
    for path in (PATH_BASE, PATH_META):
        print(f"    {PATH_NAME[path]}: " + " · ".join(f"«{lab}» {v}" for (p, lab), v in sorted(tally.items())
                                                     if p == path))

    # ── §8 켜려면 ───────────────────────────────────────────────────────
    title("§8. 켜려면 무엇이 참이어야 하나 — 제품 결정에 넘기는 것 (판정 아님)")
    hb, hm = heads.get(PATH_BASE, Counter()), heads.get(PATH_META, Counter())
    gaps = max(abs(res[n][c]["th"]["cut"] - res[n][c]["th"]["f"]) for n in names
               for c in cells_for(PATH_BASE) + cells_for(PATH_META) if c[1])
    amb = {n: f"{meta[n]['amb']}/{meta[n]['sum']}" for n in names}
    sat = {n: f"{a1[n]['rec'][2]}/{a1[n]['rec'][3]}" for n in names}
    weak = [n for n in names if len(ho_j[n]) < MIN_N]
    lines = [
        f"① 현행 조합에서 «{LAB_BETTER}»인 열이 몇 개면 켜는가 — 제품이 정할 수. 관측: 기본 경로 {hb[LAB_BETTER]}/{len(names)} ·"
        f" 모의 <meta> 경로 {hm[LAB_BETTER]}/{len(names)}.",
        f"② «{LAB_WORSE}»이 몇 개까지 허용되는가 — 관측: 기본 경로 {hb[LAB_WORSE]} · 모의 <meta> 경로 {hm[LAB_WORSE]}"
        f" (현행 조합 칸).",
        f"③ θ 등컷이 요청 비율을 맞추는가 — 관측: 켬 칸 전부의 |실제 컷 − 요청 f| 최댓값 {gaps:.4f}. 동점 덩어리가"
        " 크면 같은 f라도 실제로 자르는 비율이 달라진다(실험 32 V2의 B1과 같은 함정).",
        f"④ 페널티 축은 실제 응답의 `used_memories`가 있어야 모의가 아닌 값이 된다 — 여기 값은 자가저작 규칙의 함수다."
        f" 귀속 모호(요약 중복 행에 떨어진 선언) {amb}.",
        f"⑤ recency 반감기 H={M.RECENCY_HALF_LIFE}행은 코퍼스 고유다 — 0.99 이상으로 포화한 행 {sat}. 포화한 열에서"
        " W_REC는 거의 상수를 빼고, 켬에서는 칸마다 재유도한 θ가 그 상수를 흡수한다.",
        f"⑥ 홀드아웃이 {MIN_N}문항 미만인 열은 구조적으로 판정 불가다 — {weak or '없음'}.",
        "⑦ 이 격자는 모의 경로의 surfaced를 현행 설정 재생 한 번에서 얼렸다 — 켠 뒤의 되먹임(페널티가 주입을 바꾸고"
        " 그것이 다시 surfaced를 바꾸는 고리)은 재지 않았다.",
    ]
    for ln in lines:
        print(f"  {ln}")
    bad = {n: h.audit() for n, h in hos.items() if h.audit()}
    print(f"\n  홀드아웃 접근 — 열마다 {dict((n, h.reads) for n, h in hos.items())} · 예산 {HO_BUDGET} · 위반 {bad or '없음'}")
    if bad:
        fail.append(f"분할: 홀드아웃 예산 {bad}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
