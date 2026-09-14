# -*- coding: utf-8 -*-
r"""
theta_position.py — 2단 격자를 되살린다: θ의 위치와 recency 항. (레인 A · 실험 번호 없음)

## 무엇을 묻는가

설계(ADR-005 §결정)는 `score = w_rel·rel + w_imp·imp + w_emo·emo − w_rec·recency − w_rep·surfaced`
에 θ를 **최종 점수**로 건다. 구현(`Memory.retrieve`)은 3항이고 θ가 `rel`에서 **먼저** 자른다.
ADR-015 핵심 7은 그 때문에 격자 2단(가중치·페널티)이 아무것도 못 움직였다고 적었다.
이 파일은 그것이 참인지 **값으로** 잰다. `memory.py` 끝 절의 스위치 둘을 켜고 끈다:

    THETA_ON_SCORE  (기본 False) — θ 컷을 가중합 뒤로 옮긴다
    W_REC           (기본 0.0)   — recency 항 (정의는 `memory.py` 끝 절)

## 하지 않는 것

**판정.** 켤지 말지는 제품 결정이다. 이 파일은 표와 «켜려면 무엇이 필요한가»까지만 낸다.
LLM도 임베딩 서버도 부르지 않는다 — `embed` 구성의 벡터는 격자의 캐시에서만 읽고, 미스가
있으면 그 구성을 `측정 안 됨`으로 두고 종료 77이다.

## 재사용 (사본 금지 · F12)

셀 실행·지표·전역 복원은 전부 `retrieval_sweep`의 것이고(`Cell` · `apply_cell` · `guard_theta` ·
`run_cell` · `snapshot_globals`), 지표 함수는 `precision`의 것이다. θ 사다리는 `rel_dist`의
`theta_at`/`actual_cut`이다. 이 파일이 더한 것은 `Memory.retrieve`를 감싸 **절단 전 순위**를
적는 기록기 하나다 — `run_cell`은 주입된 5건만 돌려주므로 `recall@10`과 θ 통과 수를 못 본다.

실행:
    PYTHONIOENCODING=utf-8 python -B experiments/theta_position.py     # 0 · 자기 대조 실패 1 · 캐시 미스 77
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "prototype"))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import memory as M                                           # noqa: E402
from memory import Memory                                    # noqa: E402
from soak import seed, ingest, CHAT                          # noqa: E402
import precision as P                                        # noqa: E402
import rel_dist as RD                                        # noqa: E402
import retrieval_sweep as RS                                 # noqa: E402

W = 110

# ══════════════════════════════════════════════════════════════════════════
# §0 사전 등록 — **값을 보기 전에** 여기 박았고, 실행하면 무엇보다 먼저 찍는다
# ══════════════════════════════════════════════════════════════════════════

# 구성 — 격자 2단으로 올라간 3셀(`RESULTS.txt`의 «2단으로 올릴 셀 3개» 줄)과 기준칸.
# 🔴 판정은 2단 3구성에서만 한다 — 물음이 «그 12셀이 무엇을 쟀는가»이기 때문이다.
#    기준칸은 프로덕션 경로라 함께 찍지만 보고 전용이다.
BASE_CFG = ("lexical", None)                 # θ = 현행 `THETA_RELEVANCE` 그대로
STAGE2_CFGS = [("embed", 0.915), ("lexical_fixed", 0.915), ("lexical_fixed", 0.97)]

# 축 — 격자 2단의 값 그대로다. 옮겨 적지 않고 읽는다.
WEIGHTS = RS.STAGE2_WEIGHTS                  # [(0.6, 0.4), (0.4, 0.6)]
PENALTIES = RS.STAGE2_PENALTY                # [0.1, 0.0]
REF = (WEIGHTS[0], PENALTIES[0])             # 기준 조합 (0.6, 0.4) · 0.1 = 오늘의 기본값

# recency — 값을 보기 전에 고정한 눈금. 단위는 `memory.py` 끝 절(행 단위 · H는 행).
W_REC_LADDER = [0.1, 0.2, 0.4]               # H = memory.RECENCY_HALF_LIFE (240행)
HALF_LIFE_SENS = [80, 720]                   # W_REC = 0.2에서만 — H 민감도
RECALL_KS = (1, 3, 5, 10)

PREREG = [
    ("①", "기본값(THETA_ON_SCORE=False · W_REC=0.0)에서 기록값은 한 칸도 안 움직인다.",
     "기준칸을 스위치 기본값으로 돌린 값이 `retrieval_sweep.BASE_EXPECT`(= precision-4cells의 "
     "G3·θ=0.05)와 다섯 칸 모두 같으면 참, 한 칸이라도 다르면 거짓(종료 1). "
     "이 파일 밖의 관측 둘(편집 전후 `retrieve()` 반환 지문 · `run_all` 대조)은 레인 보고가 적는다."),
    ("②", "THETA_ON_SCORE=False에서는 W_IMP·SURFACED_PENALTY를 흔들어도 «주입 집합»이 안 바뀐다"
          "(순서만). True면 바뀐다. — 🔴 이 레인의 판정",
     "주입 집합 = `retrieve()`가 돌려준 hits의 요약 집합(τ·θ 통과 뒤 TOP_K 절단 — 실제로 주입되는 "
     "것). 문항이 «바뀜»이면 그 축의 두 값 쌍 중 하나라도 집합이 다르다. 분모 = 구성별 게이트 통과 "
     "문항. False 쪽은 2단 3구성 합계 «바뀜» = 0이면 참, ≥ 1이면 거짓(= 핵심 7 과장). True 쪽은 "
     "≥ 1이면 참, 0이면 거짓. ②는 두 쪽이 모두 참일 때 참."),
    ("②-주", "⚠️ «θ 통과 집합»(절단 전)을 세지 않는 이유 — False에서는 그것이 **정의상** 가중치와 "
             "무관하다. 그것을 세면 발화할 수 없는 검사다.",
     "그래서 False의 θ 통과 집합 불변은 판정이 아니라 구현의 자기 대조로만 쓴다(어기면 종료 1). "
     "그리고 False의 «바뀜 ≥ 1»은 |θ 통과| > TOP_K인 문항에서만 가능하다 — 어기면 종료 1."),
    ("②-pen", "페널티 축은 `surfaced_count`가 0이면 θ 위치와 무관하게 0을 뺀다(ADR-005 미해결: "
              "계측 경로에서는 채널이 비어 있다).",
     "모집단의 `surfaced_count` 최댓값이 0이면 «True면 바뀐다»는 페널티 축에 대해 **만족 불가능**"
     "하다 → ②-pen은 «판정 불가(채널 비어 있음)»로 적고 ②의 참·거짓에 넣지 않는다. > 0이면 "
     "가중치 축과 같은 규칙."),
    ("③", "켰을 때의 지표(THETA_ON_SCORE · W_REC)는 **보고 전용**이다. 판정하지 않는다 — 켤지 "
          "말지는 제품 결정이다.",
     "관측으로 참·거짓이 되는 조건이 아니다(판정 없음을 적은 조항). 눈금은 위 상수로 값을 "
     "보기 전에 고정했다."),
    ("④", "θ를 최종 점수로 옮기면 오늘의 θ는 뜻이 달라진다 — 재유도가 필요한가.",
     "같은 θ가 378쌍 score 모집단에서 자르는 비율(실제 컷)이 rel 모집단의 실제 컷과 다르면 «뜻이 "
     "바뀌었다 → 켜려면 재유도가 선행»으로 적고, 같으면 «재유도 불필요»로 적는다. 재유도 값은 "
     "`rel_dist.theta_at`에 rel 모집단의 실제 컷을 넣어 찍는다(동일 실제 컷 · 보고 전용)."),
]


def print_prereg():
    print("=" * W)
    print("θ의 위치와 recency 항 — 2단 격자를 되살린다 (레인 A · 실험 번호 없음 · 보고 전용)")
    print("=" * W)
    print("\n§0. 🔴 사전 등록 — 값을 하나도 보기 전에 코드 상수(`PREREG`)로 박은 것\n")
    for key, claim, how in PREREG:
        print(f"  {key:<6}{claim}")
        print(f"        관측 → {how}\n")
    print(f"  구성: 기준칸 G3·{BASE_CFG[0]}·θ=현행(보고 전용) + 2단 3구성 "
          f"{', '.join(f'G3·{m}·f={f}' for m, f in STAGE2_CFGS)}")
    print(f"  축(격자 2단 그대로): (W_REL, W_IMP) {WEIGHTS} × SURFACED_PENALTY {PENALTIES}"
          f" · 기준 조합 {REF}")
    print(f"  recency 눈금: W_REC {W_REC_LADDER} @ H={M.RECENCY_HALF_LIFE}행 + H {HALF_LIFE_SENS}"
          f" @ W_REC=0.2 — 단위: 대화 행(user·character 각각 1)")


# ══════════════════════════════════════════════════════════════════════════
# 기록기 — `Memory.retrieve`를 감싼다
# ══════════════════════════════════════════════════════════════════════════

class Recorder:
    """
    run 하나 동안 `retrieve()` 호출마다 (주입 순서, 절단 전 순위, surfaced 최댓값)을 적는다.

    절단 전 순위는 **같은 호출을 `TOP_K`를 풀고 한 번 더** 불러 얻는다. `retrieve()`는 DB를
    쓰지 않고(`retrieval_count`는 `build_context`가 올린다) 계측 기록만 새로 만든다 — 그래서
    두 번째 호출 뒤 `_retrieval_notes`를 첫 호출의 것으로 되돌린다.
    """

    def __init__(self):
        self.calls = {}
        self.surf = 0
        self._orig = None

    def install(self):
        orig = self._orig = Memory.retrieve
        rec = self

        def wrapped(m, chat_id, query, now_seq):
            hits, rejected = orig(m, chat_id, query, now_seq)
            notes, k = m._retrieval_notes, M.TOP_K
            M.TOP_K = 10 ** 9
            try:
                full, _ = orig(m, chat_id, query, now_seq)
            finally:
                M.TOP_K = k
                m._retrieval_notes = notes
            if [(s, r["event_id"]) for s, r in full[:k]] != \
                    [(s, r["event_id"]) for s, r in hits]:
                raise SystemExit(f"🔴 기록기: 절단 전 순위의 앞 {k}건이 주입과 다르다 — {query!r}")
            # 절단 전 길이는 첫 호출만으로도 셀 수 있다(색인 행 − 컷 사유). 두 길이가 다르면
            # 두 번째 호출이 절단을 못 풀었다 — 그러면 `recall@10`과 |θ 통과|가 조용히 5에 묶인다.
            n = m.db.execute("SELECT COUNT(*) c FROM event WHERE chat_id=? AND user_deleted=0",
                             (chat_id,)).fetchone()["c"]
            if len(full) != n - len(rejected):
                raise SystemExit(f"🔴 기록기: 절단 전 순위 길이 {len(full)} ≠ 행 {n} − 컷 "
                                 f"{len(rejected)} — {query!r}")
            got = dict(hits=[r["summary"] for _, r in hits],
                       full=[r["summary"] for _, r in full])
            if query in rec.calls and rec.calls[query] != got:
                raise SystemExit(f"🔴 기록기: 같은 질의의 두 호출이 다르다 — {query!r}")
            rec.calls[query] = got
            s = m.db.execute("SELECT MAX(surfaced_count) x FROM event WHERE chat_id=?",
                             (chat_id,)).fetchone()["x"] or 0
            rec.surf = max(rec.surf, s)
            return hits, rejected

        Memory.retrieve = wrapped

    def uninstall(self):
        Memory.retrieve = self._orig


# 이 파일이 흔드는 `memory.py` 끝 절의 전역. `retrieval_sweep.RESTORE_GLOBALS`에는 없으므로
# 따로 뜨고 되돌리고 **항등을 단언**한다(G13 — 셀 사이로 새면 표 전체가 오염된다).
OWN_GLOBALS = ["THETA_ON_SCORE", "W_REC", "RECENCY_HALF_LIFE", "TOP_K"]


def snapshot_own():
    return {n: getattr(M, n) for n in OWN_GLOBALS} | {"Memory.retrieve": Memory.retrieve}


def restore_own(snap):
    for n in OWN_GLOBALS:
        setattr(M, n, snap[n])
    Memory.retrieve = snap["Memory.retrieve"]


def assert_own(snap, where):
    bad = [n for n in OWN_GLOBALS if getattr(M, n) != snap[n]]
    if Memory.retrieve is not snap["Memory.retrieve"]:
        bad.append("Memory.retrieve")
    if bad:
        raise SystemExit(f"🔴 G13 위반 — 스위치가 새었다 ({where}): {bad}")


# ══════════════════════════════════════════════════════════════════════════
# 한 run
# ══════════════════════════════════════════════════════════════════════════

class Ctx:
    """모집단과 캐시 — 한 번 만들고 모든 run이 읽는다."""


def run(cx, mode, theta, f, wr, wi, pen, on_score=False, w_rec=0.0, half=None):
    """셀 하나를 격자 하니스로 돌리고 (tot, 기록)을 돌려준다. 전역은 끝에서 되돌린다."""
    cell = RS.Cell(0, 2, RS.GATES[0], mode, f, theta, None, wr, wi, pen)
    sup = RS.Supplier(cx.cache, force="none")
    rec = Recorder()
    snap, own = RS.snapshot_globals(), snapshot_own()
    try:
        RS.apply_cell(cell, cx.base_theta, sup)
        M.THETA_ON_SCORE, M.W_REC = on_score, w_rec
        if half is not None:
            M.RECENCY_HALF_LIFE = half
        RS.guard_theta(cell)
        rec.install()
        tot = RS.run_cell(cx.env, cell, sup)
    finally:
        rec.uninstall()
        RS.restore_globals(snap)
        restore_own(own)
    RS.assert_restored(snap, f"{mode} θ={theta}")
    assert_own(own, f"{mode} θ={theta}")
    if sup.failed or sup.requests or tot["degraded"]:
        # 🔴 캐시만 읽기로 했다 — 요청이 하나라도 나갔으면 그 run은 이 파일의 약속 밖이다.
        raise SystemExit(f"🔴 {mode}: 임베딩 요청 {sup.requests}건 · 강등 {tot['degraded']}건 — "
                         f"캐시만 읽는다는 전제가 깨졌다")
    return tot, rec


def recall_at(cx, rec, k):
    """`evidence_recall(검색경로)`를 절단 k로. 게이트 차단 문항은 순위가 없어 적중 0이다."""
    hit = tot = 0
    for q in cx.scored:
        ranked = rec.calls.get(q["ask"], {}).get("full", [])
        h, t = P.evidence_recall_via_retrieval(q, set(ranked[:k]), cx.key_of)
        hit, tot = hit + h, tot + t
    return hit, tot


def metrics(cx, tot, rec):
    """격자 지표 + recall@k + |θ 통과|. 🔴 recall@TOP_K는 격자의 회상과 같아야 한다."""
    rk = {k: recall_at(cx, rec, k) for k in RECALL_KS}
    if rk[M.TOP_K][0] != tot["ev_hit"]:
        raise SystemExit(f"🔴 recall@{M.TOP_K} {rk[M.TOP_K]} ≠ 격자 회상 {tot['ev_hit']} — "
                         f"기록기가 격자와 다른 것을 보고 있다")
    npass = [len(c["full"]) for q, c in rec.calls.items() if q in cx.asks]
    return dict(rk=rk, mis=tot["mis"], ret=tot["ret"], pooled=tot["pooled"],
                top1=(tot["top1"], tot["top1_n"]), ties=len(tot["ties"]),
                hard=tot["hard"], hard_n=sum(1 for q in cx.scored if q.get("distractor")),
                trap=tot["trap"], gate=tot["gate_pass"],
                npass_max=max(npass, default=0), npass_sum=sum(npass),
                over_k=sum(1 for n in npass if n > M.TOP_K), surf=rec.surf)


def sets_of(cx, rec):
    """문항별 (주입 집합, θ 통과 집합). 게이트 차단 문항은 없다."""
    return {q["id"]: (frozenset(rec.calls[q["ask"]]["hits"]),
                      frozenset(rec.calls[q["ask"]]["full"]))
            for q in cx.scored if q["ask"] in rec.calls}


# ══════════════════════════════════════════════════════════════════════════
# 출력
# ══════════════════════════════════════════════════════════════════════════

def title(s, ch="="):
    print("\n" + ch * W)
    print(s)
    print(ch * W)


def row_head(first="구성"):
    ks = "".join(f"{'r@' + str(k):>8}" for k in RECALL_KS)
    print(f"  {first:<40}{ks}{'mis@q':>7}{'pooled(분모)':>14}{'top1(분모)':>11}"
          f"{'동점':>5}{'hard(분모)':>11}{'|θ통과| max':>12}{'>TOP_K':>8}{'게이트':>7}")


def row(label, mt):
    ks = "".join(f"{f'{mt['rk'][k][0]}/{mt['rk'][k][1]}':>8}" for k in RECALL_KS)
    pooled = f"{mt['pooled']:.3f}({mt['ret']})" if mt["pooled"] is not None else f"정의 안 됨({mt['ret']})"
    top1 = f"{mt['top1'][0]}/{mt['top1'][1]}" if mt["top1"][1] else "정의 안 됨"
    hard = f"{mt['hard']}/{mt['hard_n']}"
    print(f"  {label:<40}{ks}{mt['mis']:>7}{pooled:>14}{top1:>11}{mt['ties']:>5}{hard:>11}"
          f"{mt['npass_max']:>12}{mt['over_k']:>8}{mt['gate']:>7}")


def cfg_name(mode, f):
    return f"G3·{mode}·" + ("θ=현행" if f is None else f"f={f}")


# ══════════════════════════════════════════════════════════════════════════

def build_ctx():
    cx = Ctx()
    corpus, ledger, qs = P.load()
    cx.key_of = P.key_index(ledger)
    cx.scored, _ = P.partition(qs, cx.key_of)
    cx.env = (corpus, ledger, qs, cx.scored, cx.key_of)
    cx.now = corpus[-1]["seq"]
    asks, sums, total = RD.population()
    if len(set(asks)) != len(asks):
        raise SystemExit("🔴 채점 문항의 ask가 겹친다 — 기록기가 질의 문자열로 문항을 찾는다")
    cx.asks, cx.sums = set(asks), sums
    RS.P_N, RS.P_SIG = len(asks) * len(sums), (total, len(sums))
    cx.cache, _ = RS.load_cache()          # 🔴 읽기만 — `save_sweep_cache`를 부르지 않는다
    cx.missing = [t for t in dict.fromkeys(asks + sums + [RS.TRAP_UTTERANCE])
                  if t not in cx.cache]
    cx.base_theta = dict(M.THETA_BY_MODE)
    # rel 모집단 — `retrieval_sweep.main`의 세 줄과 같은 식이다(함수로 뽑혀 있지 않아 import할
    # 수 없다). 같은 것을 재는지는 아래에서 `THETA_BY_MODE`의 f=0.80 유도값과 대조해 확인한다.
    cx.vals = {"lexical": [M.coverage(set(M.bigrams(a)), set(M.bigrams(s)))
                           for a in asks for s in sums],
               "lexical_fixed": [M.jaccard(set(M.tokens_fixed(a)), set(M.tokens_fixed(s)))
                                 for a in asks for s in sums]}
    if not cx.missing:
        cx.vals["embed"] = [RD.cos(cx.cache[a], cx.cache[s]) for a in asks for s in sums]
    for mode in ("lexical_fixed", "embed"):
        if mode in cx.vals and RD.theta_at(cx.vals[mode], 0.80) != M.THETA_BY_MODE.get(mode)[0]:
            raise SystemExit(f"🔴 {mode}: f=0.80 유도값이 `THETA_BY_MODE`와 다르다 — 이 파일의 "
                             f"rel 모집단이 격자의 것과 다르다")
    # 행별 imp·나이 — 같은 적재 경로(`soak.seed`/`ingest`)로 한 번 만든다. 순서는 모집단과 같아야 한다.
    m = Memory(os.path.join(RS.ROOT, "prototype", ".theta_pos.db"))
    seed(m)
    ingest(m, corpus, ledger, timed=False)
    rows = m.db.execute("SELECT summary, importance, emotional_weight, source_from_seq, "
                        "surfaced_count FROM event WHERE chat_id=? AND user_deleted=0",
                        (CHAT,)).fetchall()
    m.db.close()
    if [r["summary"] for r in rows] != list(sums):
        raise SystemExit("🔴 행 순서가 `rel_dist.population()`과 다르다")
    cx.imp = [max(r["importance"] or 0, r["emotional_weight"] or 0) for r in rows]
    cx.seq = [r["source_from_seq"] for r in rows]
    return cx


def theta_of(cx, mode, f):
    return M.THETA_RELEVANCE if f is None else RD.theta_at(cx.vals[mode], f)


def main():
    print_prereg()
    tmp = tempfile.mkdtemp(prefix="theta_pos_")
    os.makedirs(os.path.join(tmp, "prototype"))
    # 임시 DB는 %TEMP%에 — `run_cell`·`population`이 `ROOT/prototype/` 아래에 만든다. 병렬 레인과
    # 같은 파일(`.sweep.db`)을 두고 다투지 않도록 두 모듈의 ROOT만 여기서 재바인딩한다.
    roots = (RS.ROOT, RD.ROOT)
    RS.ROOT = RD.ROOT = tmp
    try:
        return body()
    finally:
        RS.ROOT, RD.ROOT = roots


def body():
    cx = build_ctx()
    fail = []
    cfgs = [BASE_CFG] + STAGE2_CFGS
    if cx.missing:
        print(f"\n  🔴 임베딩 캐시 미스 {len(cx.missing)}건 — `embed` 구성은 측정 안 됨 "
              f"(요청을 보내지 않는다). 끝에 종료 77.")
        cfgs = [c for c in cfgs if c[0] != "embed"]

    # ── §1 모집단 ────────────────────────────────────────────────────────
    title("§1. 모집단 · recency의 입력", "-")
    ages = sorted(cx.now - s for s in cx.seq)
    tau_rows = sum(1 for i in cx.imp if i >= M.TAU_IMPORTANCE)
    print(f"  채점 {len(cx.scored)}문항 × event 색인 {len(cx.sums)}행 = {RS.P_N}쌍 · 서명 {RS.P_SIG}"
          f" · τ({M.TAU_IMPORTANCE}) 통과 행 {tau_rows}/{len(cx.imp)}")
    print(f"  now_seq = {cx.now}행(코퍼스 마지막 행 — 격자는 모든 문항을 여기서 묻는다)")
    print(f"  색인 나이(행): 최소 {ages[0]} · 중앙 {ages[len(ages) // 2]} · 최대 {ages[-1]} · "
          f"source_from_seq=0인 행 {sum(1 for s in cx.seq if s == 0)} · 미래 행(age<0) "
          f"{sum(1 for a in ages if a < 0)}")
    keep = M.RECENCY_HALF_LIFE
    try:
        for h in [keep] + HALF_LIFE_SENS:
            M.RECENCY_HALF_LIFE = h
            p = [M.recency_penalty(cx.now, s) for s in cx.seq]
            print(f"  H={h:>4}행 → 페널티 범위 {min(p):.3f}~{max(p):.3f}")
    finally:
        M.RECENCY_HALF_LIFE = keep

    # ── §2 ① 기본값 ─────────────────────────────────────────────────────
    title("§2. ① 기본값에서 기록값이 움직였나 — 기준칸 × `retrieval_sweep.BASE_EXPECT`")
    th0 = theta_of(cx, *BASE_CFG)
    tot, rec = run(cx, BASE_CFG[0], th0, 0.80, *REF[0], REF[1])
    got = dict(recall=(tot["ev_hit"], tot["ev_tot"]), mis=tot["mis"],
               pooled=(tot["mis"], tot["ret"]), top1=(tot["top1"], tot["top1_n"]),
               ties=len(tot["ties"]))
    for k, want in RS.BASE_EXPECT.items():
        print(f"  {k:<8}기대 {str(want):<10}실측 {str(got[k]):<10}"
              f"{'PASS' if got[k] == want else '🔴 FAIL'}")
    p1 = got == RS.BASE_EXPECT
    print(f"  → ① {'참' if p1 else '🔴 거짓'} (스위치 기본값: THETA_ON_SCORE={M.THETA_ON_SCORE}"
          f" · W_REC={M.W_REC})")
    if not p1:
        fail.append("① 기준칸")

    # ── §3 ② 판정 ───────────────────────────────────────────────────────
    title("§3. 🔴 ② 판정 — 격자 2단의 두 축은 정말 죽어 있었나")
    grid = {}          # (cfg, on) → {(w, pen): (metrics, sets)}
    for cfg in cfgs:
        th = theta_of(cx, *cfg)
        for on in (False, True):
            for w in WEIGHTS:
                for pen in PENALTIES:
                    t, r = run(cx, cfg[0], th, cfg[1] or 0.80, *w, pen, on_score=on)
                    grid.setdefault((cfg, on), {})[(w, pen)] = (metrics(cx, t, r), sets_of(cx, r))

    def changed(cfg, on, axis):
        """축 하나에서 주입 집합·θ 통과 집합·순서가 바뀐 문항."""
        g = grid[(cfg, on)]
        if axis == "W":
            pairs = [((WEIGHTS[0], p), (WEIGHTS[1], p)) for p in PENALTIES]
        else:
            pairs = [((w, PENALTIES[0]), (w, PENALTIES[1])) for w in WEIGHTS]
        inj, pas = set(), set()
        for a, b in pairs:
            sa, sb = g[a][1], g[b][1]
            for qid in sa:
                if sa[qid][0] != sb[qid][0]:
                    inj.add(qid)
                if sa[qid][1] != sb[qid][1]:
                    pas.add(qid)
        return inj, pas, len(g[REF][1])

    print("\n  칸 = 주입 집합이 바뀐 문항 / 게이트 통과 문항 · 괄호 = θ 통과 집합(절단 전)이 바뀐 문항")
    print(f"  {'구성':<30}{'θ':>10}{'가중치 False':>14}{'가중치 True':>14}"
          f"{'페널티 False':>14}{'페널티 True':>14}{'surfaced max':>14}")
    tally = {(ax, on): 0 for ax in ("W", "pen") for on in (False, True)}
    surf_max, ids = 0, []
    for cfg in cfgs:
        th = theta_of(cx, *cfg)
        cells = []
        for ax in ("W", "pen"):
            for on in (False, True):
                inj, pas, den = changed(cfg, on, ax)
                cells.append(f"{len(inj)}/{den}({len(pas)})")
                if cfg in STAGE2_CFGS:
                    tally[(ax, on)] += len(inj)
                if not on and pas:
                    fail.append(f"②-주 {cfg_name(*cfg)} {ax}: False인데 θ 통과 집합이 바뀌었다")
                if not on and inj:
                    mx = max(grid[(cfg, on)][k][0]["npass_max"] for k in grid[(cfg, on)])
                    if mx <= M.TOP_K:
                        fail.append(f"②-주 {cfg_name(*cfg)} {ax}: |θ통과| max {mx} ≤ TOP_K인데 "
                                    f"주입 집합이 바뀌었다")
                if inj:
                    ids.append(f"{cfg_name(*cfg)} · {'가중치' if ax == 'W' else '페널티'} "
                               f"{'True' if on else 'False'}: {', '.join(sorted(inj))}")
        s = max(mt["surf"] for on in (False, True) for mt, _ in grid[(cfg, on)].values())
        surf_max = max(surf_max, s)
        tag = "" if cfg in STAGE2_CFGS else "  (보고 전용)"
        print(f"  {cfg_name(*cfg):<30}{th:>10.4f}" + "".join(f"{c:>14}" for c in cells)
              + f"{s:>14}{tag}")
    print("\n  바뀐 문항 id:")
    for line in ids or ["(없음)"]:
        print(f"    {line}")
    mx_false = {cfg_name(*c): max(v[0]["npass_max"] for v in grid[(c, False)].values()) for c in cfgs}
    print(f"\n  |θ 통과| 문항별 최댓값 (False · 절단 전) — {mx_false} · TOP_K = {M.TOP_K}")
    wf, wt = tally[("W", False)], tally[("W", True)]
    side_f, side_t = wf == 0, wt >= 1
    print(f"\n  ②-W  False 쪽: 2단 3구성 합계 «바뀜» = {wf} → {'참' if side_f else '거짓 (핵심 7 과장)'}")
    print(f"       True  쪽: 2단 3구성 합계 «바뀜» = {wt} → {'참' if side_t else '거짓'}")
    # 기제를 가른다 — True의 «바뀜»이 θ가 점수에서 실제로 잘라서인가, θ가 아무것도 못 잘라
    # 후보가 TOP_K를 넘고 그 절단이 가중치를 받아서인가. 둘은 «축이 살았다»의 다른 뜻이다.
    for cfg in cfgs:
        inj, pas, den = changed(cfg, True, "W")
        if inj:
            how = ("θ 통과 집합까지 바뀜 — 점수 위의 θ가 가중치를 받는다" if pas else
                   "θ 통과 집합은 그대로 — θ가 못 잘라 후보가 TOP_K를 넘고 절단이 가중치를 받는다")
            print(f"       · {cfg_name(*cfg)}: 주입 {len(inj)}/{den} · θ 통과 {len(pas)}/{den} — {how}")
    if surf_max == 0:
        pen_v = "판정 불가 — surfaced_count 최댓값 0 (채널 비어 있음 · 사전 등록 ②-pen)"
        pen_ok = None
    else:
        pen_ok = tally[("pen", False)] == 0 and tally[("pen", True)] >= 1
        pen_v = f"False {tally[('pen', False)]} · True {tally[('pen', True)]} → {'참' if pen_ok else '거짓'}"
    print(f"  ②-pen {pen_v}")
    verdict2 = side_f and side_t and pen_ok is not False
    print(f"  → ② {'참' if verdict2 else '거짓'}"
          + (" (페널티 축은 판정에서 뺐다)" if pen_ok is None else ""))

    # ── §4 지표 — THETA_ON_SCORE ─────────────────────────────────────────
    title("§4. THETA_ON_SCORE를 켰을 때 지표 — 보고 전용 (③) · 분모: recall 28 근거 · "
          "pooled 검색 항목 · top1 검색 ≥1 문항")
    print("  페널티 0.0 행은 surfaced_count가 0이면 0.1 행과 전 열이 같다 — 같으면 생략하고 "
          "그 사실만 적는다.")
    row_head()
    same_pen = True
    for cfg in cfgs:
        for on in (False, True):
            for w in WEIGHTS:
                a, b = grid[(cfg, on)][(w, PENALTIES[0])][0], grid[(cfg, on)][(w, PENALTIES[1])][0]
                same_pen &= a == b
                row(f"{cfg_name(*cfg)} {'점수' if on else 'rel '}θ W{w}", a)
        print()
    print(f"  페널티 0.0 행 = 0.1 행: {'전 행 동일 (생략함)' if same_pen else '🔴 다른 행이 있다'}")

    # ── §5 θ 재유도 ─────────────────────────────────────────────────────
    title("§5. ④ θ를 최종 점수로 옮기면 — 오늘의 θ가 자르는 비율과 재유도값 (378쌍 · 등컷 규칙 재사용)")
    print(f"  {'구성':<30}{'θ':>9}{'rel 실제 컷':>12}{'score 실제 컷':>14}{'τ통과 최저 score':>16}"
          f"{'θ_score(동일 컷)':>17}{'재유도 뒤 컷':>13}")
    rederived, moved = {}, []
    for cfg in cfgs:
        th = theta_of(cx, *cfg)
        rel = cx.vals[cfg[0]]
        n = len(cx.sums)
        wr, wi = REF[0]
        score = [wr * rel[i] + wi * cx.imp[i % n] for i in range(len(rel))]
        low = min(sc for i, sc in enumerate(score) if cx.imp[i % n] >= M.TAU_IMPORTANCE)
        cut_rel, cut_sc = RD.actual_cut(rel, th), RD.actual_cut(score, th)
        ths = RD.theta_at(score, cut_rel)
        rederived[cfg] = ths
        moved.append((cfg, cut_rel, cut_sc))
        print(f"  {cfg_name(*cfg):<30}{th:>9.4f}{cut_rel:>11.1%}{cut_sc:>13.1%}{low:>16.4f}"
              f"{ths:>17.4f}{RD.actual_cut(score, ths):>12.1%}")
    print("  (score = W_REL·rel + W_IMP·imp · 기준 가중치 · surfaced 0 · W_REC 0. 모집단은 rel 사다리와 "
          "같은 378쌍 — τ 미달 쌍도 센다)")
    diff = [c for c, a, b in moved if a != b]
    print(f"\n  ④ 같은 θ의 실제 컷이 rel 모집단과 score 모집단에서 다른 구성 {len(diff)}/{len(moved)} → "
          + ("«뜻이 바뀌었다 → 켜려면 재유도가 선행»" if diff else "«재유도 불필요»"))
    print("\n  재유도 θ로 켰을 때 (보고 전용 · 기준 가중치):")
    row_head()
    for cfg in cfgs:
        t, r = run(cx, cfg[0], rederived[cfg], cfg[1] or 0.80, *REF[0], REF[1], on_score=True)
        row(f"{cfg_name(*cfg)} 점수θ 재유도", metrics(cx, t, r))

    # ── §6 W_REC ─────────────────────────────────────────────────────────
    title(f"§6. W_REC를 켰을 때 지표 — 보고 전용 (③) · 기준 가중치 {REF} · H 단위 = 대화 행")
    print("  «바뀜» = 같은 θ 위치의 W_REC=0 대비 주입 집합이 바뀐 문항 / 게이트 통과 문항")
    row_head("구성 · θ 위치 · W_REC · H")
    plan = [(w, M.RECENCY_HALF_LIFE) for w in W_REC_LADDER] + [(0.2, h) for h in HALF_LIFE_SENS]
    for cfg in cfgs:
        th = theta_of(cx, *cfg)
        for on in (False, True):
            base_m, base_s = grid[(cfg, on)][REF]
            row(f"{cfg_name(*cfg)} {'점수' if on else 'rel '}θ W_REC 0", base_m)
            for w_rec, h in plan:
                t, r = run(cx, cfg[0], th, cfg[1] or 0.80, *REF[0], REF[1],
                           on_score=on, w_rec=w_rec, half=h)
                mt, st = metrics(cx, t, r), sets_of(cx, r)
                ch = sum(1 for q in st if st[q][0] != base_s.get(q, (None,))[0])
                row(f"  … W_REC {w_rec} H {h} · 바뀜 {ch}/{len(st)}", mt)
        print()

    # ── 끝 ───────────────────────────────────────────────────────────────
    title("요약")
    print(f"  ① {'참' if p1 else '거짓'} · ② {'참' if verdict2 else '거짓'} "
          f"(가중치 축 False {wf} / True {wt} · 페널티 축 {pen_v})")
    print("  🔴 판정하지 않는다 — 켤지 말지는 제품 결정이다(사전 등록 ③).")
    if fail:
        print("\n  🔴 자기 대조 실패:\n    " + "\n    ".join(fail))
        return 1
    return 77 if cx.missing else 0


if __name__ == "__main__":
    sys.exit(main())
