# -*- coding: utf-8 -*-
r"""
retrieval_sweep.py — 검색 격자 30셀. (라운드 2 단계 4 · 실험 21 · 결정 C 집행)

## 이 파일이 하는 것과 하지 않는 것

**하는 것:** 처음으로 숫자를 근거로 **비교**한다. 격자는 실행 전에 계획에 고정돼
있고(`ralplan-retrieval-summary.md` §단계 4), 이 파일은 그 표를 그대로 옮긴 것이다.

**하지 않는 것:** 결정. 기본값 변경은 단계 5의 판정이고, 그 판정의 기본 결과는
**유지**다(G16). 2단은 승격 권한이 없다 — 권고만 낸다.

    1단 18셀 = 게이트 {G3(프로덕션), G0(역사)} × 모드 {lexical, lexical_fixed, embed}
                × θ {모드별 등컷 3점 f ∈ 0.80 / 0.915 / 0.97}
    2단 12셀 = 1단 파레토 전선 3셀 × (W_REL,W_IMP) {(0.6,0.4),(0.4,0.6)}
                × SURFACED_PENALTY {0.1, 0}

## 🆕 규칙 ⑤ — 동점 조항 (사전 등록의 구멍 하나를 **사후에** 채운 것)

계획 §단계 4의 선택 규칙은 ①②③④뿐이고 **동점을 말하지 않았다.** 그래서 상위 3개의
절단선이 동점군 안쪽에 떨어졌을 때(#6·#9) 세 번째 자리를 고른 것은 규칙이 아니라
`pareto_front`의 반환 순서와 `sort`의 안정성이었다 — 계획에 없는 **구현 사실** 둘.

    ⑤ 동점군(두 선택 키가 모두 같은 셀들)이 절단선을 가로지르면
      3차 키로 **격자 인덱스 오름차순**을 쓴다. 2단의 크기는 안 바꾼다.
      발화하면 동점군 전체와 탈락 셀을 이름으로 찍는다.

🔴 **이 조항은 이번 격자에 대해 사전 등록이 아니다.** 결과를 본 뒤에 적었다. 값어치는
   *다음* 라운드가 이 격자를 기준선으로 재사용할 때 규칙이 먼저 있다는 것뿐이고,
   그래서 조항이 오늘의 선택을 **한 자리도 안 바꾸는지**가 그 자체로 검사 대상이다
   (`select_key` 머리말 · `tie_clause_check`).

## 🔴 하니스 규약 — **강등 금지 · SKIP 77**

`prototype/memory.py:1117`의 `def retrieve`는 벡터 공급자가 없거나 실패하면 조용히
`lexical_fixed`로 내려가고 `("degraded","embedding",…)`을 provenance에 남긴다.
**그것은 프로덕션의 미덕이고 측정의 결함이다.** 강등된 셀이 `embed`라는 이름을 달고
이 표에 들어가면 그것이 F21(옳은 숫자에 틀린 이름)이고, 30셀 표는 다음 라운드의
기준선으로 동결되므로 오염된 채 얼면 F21을 계획이 스스로 설치한 것이 된다.

    선언한 모드를 돌릴 수 없는 셀은 **`측정 안 됨`**으로 찍고, 스윕 전체가 **종료 77**.

## 🔴 `retrieve()`가 던지는 것에 기대지 않는다 (레인 D 검증자 F1/F1b)

단계 3이 `theta_for(mode)`를 `retrieve()` 맨 앞으로 올렸지만, **강등이 그 검사를
우회한다** — `EMBED_FN`이 안 꽂혀 있으면 선언된 모드는 `theta_for`에 닿기도 전에
`lexical_fixed`가 되고, 그 모드의 θ는 유도돼 있으므로 **아무것도 터지지 않는다.**
그래서 이 스윕은 셀을 돌리기 **전에 자기 손으로** `THETA_BY_MODE`의 항목이
`None`이 아님을 단언한다.

## 🔴 G13 — 전역 복원은 `try/finally` + **런타임 항등 단언**

복원 대상 9종: `RETRIEVAL_MODE` · `THETA_RELEVANCE` · `THETA_BY_MODE` · `W_REL` ·
`W_IMP` · `SURFACED_PENALTY` · `ALPHA_LEXICAL` · `Memory.gate` · `EMBED_FN`.

패턴은 `precision.py:572-580`(`try/finally`로 `orig_gate, orig_t`를 되돌린다)이지 `gate_sweep.py:284-285`의 평문
대입이 아니다 — 셀 중간에 예외가 나면 후자는 전역을 오염된 채 남긴다.
그리고 G13의 grep(`THETA_BY_MODE\[`)은 **네 가지 철자 중 하나만** 잡는다(레인 D
검증자 F4: 별칭 대입 · `.update()` · `globals()[...]`가 전부 빠져나간다). 그래서
grep을 믿지 않고 **셀마다 dict의 객체 항등과 내용을 실제로 확인한다.**

## ⚠️ θ 축을 읽는 법 — `f=0.80`은 어휘 두 행에서만 "현행과 동치"다

`lexical`·`lexical_fixed`는 0에 원자가 각각 90.7% · 89.7% 있어서 **어떤 θ도 그보다
적게 자를 수 없다.** 그 두 모드에서 사다리는 `{현행과 동치, 조임, 더 조임}`이고
`f=0.80`이 곧 현행 동치 눈금이다. **`embed`는 0의 원자가 0.0%다** — 연속 분포에는
현행 동치 눈금이 없고, 애초에 현행 기본값이 아니므로 동치일 대상도 없다.
거기서 `f=0.80`은 **그저 셋 중 가장 느슨한 점**이다 (레인 D 검증자 F2).

그리고 **같은 `f`가 두 모드에서 다른 실험이다**(F28-b): `embed`의 사다리는 통과율
20%→3%(6.7배 폭)를, `lexical`은 9.3%→2.6%(3.6배 폭)를 훑는다. 그래서 모드 간
`evidence_recall` 비교에는 **`실제 컷` 열을 반드시 나란히 읽는다**(G15 rev2).

실행:
    python experiments/retrieval_sweep.py       # 종료 0 (모드를 못 돌리면 77)
"""
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "prototype"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import json                                                  # noqa: E402
import memory as M                                           # noqa: E402
from memory import Memory                                    # noqa: E402
import embedding as EMB                                      # noqa: E402
from soak import seed, ingest, trap_injected, pct, ROOT, CHAT  # noqa: E402
from gate_sweep import g_current, g_content, build_vocab     # noqa: E402
import precision as P                                        # noqa: E402
import rel_dist as RD                                        # noqa: E402

W = 110

# ── 모듈 전역 상수 (G8) ────────────────────────────────────────────────

# 1단의 게이트 축. `precision.py:103`과 **같은 두 함수**를 쓴다 — 게이트의 정의가
# 두 벌이 되면 이 격자의 기준칸이 `precision-4cells.txt`와 비교 불가능해진다.
GATES = [("G3", g_content, "G3(프로덕션 — memory.py 기본값)"),
         ("G0", g_current, "G0(역사 — gate_sweep 4부 이전)")]

# 1단의 모드 축. `"hybrid"`는 없다 (결정 E — α=0.5의 순위 프로파일이 임베딩 단독과
# 완전히 같았다 · F29). 재진입 조건은 이 실행이 아래에서 직접 판정한다.
MODES = ["lexical", "lexical_fixed", "embed"]

# 1단의 θ 축. **값이 아니라 자르는 비율**로 지정한다 (결정 D). 사다리의 정본은
# `rel_dist.LADDER`이고 여기서 옮겨 적지 않는다 — 두 벌이 되면 한쪽만 고쳐진다.
LADDER = RD.LADDER

# 2단의 두 축 (계획 §단계 4의 표 그대로).
STAGE2_WEIGHTS = [(0.6, 0.4), (0.4, 0.6)]
STAGE2_PENALTY = [0.1, 0.0]

# 🆕 승격 조건 3의 표본 배수. **채점 18문항을 이만큼 반복해서 읽는다** — n = 18 × 이 값.
#
# 🔴 **왜 늘리나.** `soak.pct`의 p95는 `v[min(n-1, int(n*0.95))]`이고 **n=18에서 그것은
#    `v[17]` = 표본의 최댓값**이다. 조건 3은 분위수를 읽는다고 적혀 있었지만 실제로는
#    **극값**을 읽고 있었고, 같은 기기·같은 명령의 24 draw에서 판정이
#    **PASS 11 / FAIL 13**으로 갈렸다(ADR-015 ⭐핵심 6 ③ · `after-r2b/cond3-draws.txt`).
#    ⚠️ **조건을 약화하는 것이 아니다** — 읽는 통계량은 여전히 p95다. 바뀐 것은
#    **그 p95가 추정치가 되도록 표본을 키운 것**뿐이다.
#
# 🔴 **왜 6인가.** 계획은 조건 3에 n을 적어 두지 않았다 — §단계 5 (e)는
#    *"18문항 · 모드별"*이라고만 적는다. 그래서 이 라운드가 고르고 근거를 적는다:
#    `int(n*0.95) < n-1`이 되어야 p95가 최댓값이기를 그만두고, 그것은 **n ≥ 20**부터
#    참이다. 그러나 n=20이면 위로 남는 표본이 **1개**라 이상치 두 개면 다시 극값이다.
#    **n ≥ 100**이면 위로 **5개 이상**이 남아 단발 이상치가 판정을 뒤집지 못한다.
#    18의 배수 중 100을 넘는 가장 작은 것이 **108(6회)**이고 — `v[102]`, 위로 5개 —
#    더 키우면 격자 벽시계만 늘어난다.
COND3_REPEATS = 6

# 🔴 **기준칸.** 게이트 G3 · 모드 lexical · θ_lexical(f=0.80).
#    이 칸의 θ(0.0588)는 현행 기본값 θ=0.05와 **378쌍에서 정확히 같은 35쌍을
#    통과시킨다**(F27: 0 초과 최솟값이 0.0588이라 0.05와 0.0588 사이에 관측값이
#    없다). 그래서 이 칸은 `precision-4cells.txt`의 `G3 · θ=0.05` 셀과 같은 값을
#    내야 한다. **안 맞으면 스윕이 프로덕션과 다른 것을 재고 있다 — 즉시 중단한다.**
BASE_EXPECT = dict(recall=(11, 28), mis=11, pooled=(11, 22), top1=(4, 10), ties=1)

# `soak.trap_injected`(`soak.py:179`)의 `build_context`(`soak.py:185`)가 던지는 평범한 발화. `embed` 모드에서는
# 이것도 임베딩 대상이라 사전 확보 목록에 들어가야 한다 — 빠지면 셀 한복판에서
# 캐시 미스가 나고, 그 미스가 실패하면 **강등**이 된다.
TRAP_UTTERANCE = "오늘 좀 피곤하네"

# 🔴 `REL_CACHE.json`은 **읽기만** 한다. `rel_dist.py`의 캐시 정책 절이
#    *"다른 실험의 캐시에 얹지 않는다"*고 적어 뒀고, 그 규칙은 이 파일에도 적용된다.
#    이 스윕이 새로 계산한 벡터는 여기 남는다.
SWEEP_CACHE = os.path.join(ROOT, "experiments", "data", "SWEEP_CACHE.json")

# `docs/05`의 TTFT 예산 (하한, 상한) ms — 단계 5 승격 조건 3이 읽는 숫자.
# 정본은 `rel_dist.TTFT_BUDGET`이고 여기서 옮겨 적지 않는다.
TTFT_BUDGET = RD.TTFT_BUDGET

# G13 복원 대상 9종. 이름을 **목록으로** 들고 다니는 이유는, 복원 코드가
# 손으로 나열한 대입문이면 축이 늘 때 하나가 빠지고 그것이 조용히 새기 때문이다.
RESTORE_GLOBALS = ["RETRIEVAL_MODE", "THETA_RELEVANCE", "THETA_BY_MODE",
                   "W_REL", "W_IMP", "SURFACED_PENALTY", "ALPHA_LEXICAL"]

# `ALPHA_LEXICAL`은 **오늘 `memory.py`에 없다** — 단계 3이 결정 E(하이브리드 격자
# 삭제)에 따라 넣지 않았다. 없는 전역을 "복원했다"고 말하지 않기 위해 부재를
# 값으로 표현한다. 스윕이 끝난 뒤에도 **여전히 없어야** 한다.
_ABSENT = object()


# ── G13 — 전역 저장/복원 + 런타임 항등 단언 ────────────────────────────

def snapshot_globals():
    """9종의 현재 상태를 뜬다. dict는 **객체 자신과 내용을 따로** 들고 있는다."""
    snap = {n: getattr(M, n, _ABSENT) for n in RESTORE_GLOBALS}
    snap["Memory.gate"] = Memory.gate
    snap["EMBED_FN"] = M.EMBED_FN
    # 🔴 dict는 **참조**로 저장된다. `gate_sweep.py:147-148`의 스칼라 save/restore를
    #    dict에 그대로 쓰면 제자리 변형이 되돌아오지 않는다(G13 ①). 그래서 객체와
    #    내용 사본을 둘 다 든다 — 복원 검사가 *"같은 객체인가"*와 *"같은 값인가"*를
    #    따로 물어야 별칭 변형(`d = THETA_BY_MODE; d[k] = v`)이 잡힌다.
    snap["_theta_contents"] = dict(M.THETA_BY_MODE)
    return snap


def restore_globals(snap):
    """9종을 되돌린다. `try/finally`의 `finally`에서만 부른다."""
    for n in RESTORE_GLOBALS:
        v = snap[n]
        if v is _ABSENT:
            if hasattr(M, n):
                delattr(M, n)
        else:
            setattr(M, n, v)
    Memory.gate = snap["Memory.gate"]
    M.EMBED_FN = snap["EMBED_FN"]


def assert_restored(snap, where):
    """
    복원이 **실제로** 됐는지 런타임에 확인한다 (G13 ③ · 레인 D 검증자 F4).

    grep은 `THETA_BY_MODE의 한 칸 대입` 한 철자만 잡고 별칭 대입·`.update()`·
    `globals()[...]`를 놓친다. 그 셋이 남기는 흔적은 **grep에는 안 보이고 여기에는
    보인다** — 객체 항등이 깨졌거나(재바인딩 미복원) 내용이 달라졌거나(제자리 변형).
    """
    bad = []
    for n in RESTORE_GLOBALS:
        cur = getattr(M, n, _ABSENT)
        if cur is not snap[n] and cur != snap[n]:
            bad.append(f"{n}: {snap[n]!r} → {cur!r}")
    if M.THETA_BY_MODE is not snap["THETA_BY_MODE"]:
        bad.append("THETA_BY_MODE: 객체 항등 깨짐 (재바인딩이 복원되지 않았다)")
    if dict(M.THETA_BY_MODE) != snap["_theta_contents"]:
        bad.append(f"THETA_BY_MODE 내용 변형: {dict(M.THETA_BY_MODE)}")
    if Memory.gate is not snap["Memory.gate"]:
        bad.append("Memory.gate: 객체 항등 깨짐")
    if M.EMBED_FN is not snap["EMBED_FN"]:
        bad.append(f"EMBED_FN: {snap['EMBED_FN']!r} → {M.EMBED_FN!r}")
    if bad:
        raise SystemExit(f"🔴 G13 위반 — 셀이 전역을 흘렸다 ({where}):\n  "
                         + "\n  ".join(bad))


# ── 벡터 공급자 — 캐시 체제를 셋으로 가른다 ────────────────────────────

class Supplier:
    """
    `M.EMBED_FN`에 꽂히는 벡터 공급자. **한 번의 호출에 한 번의 요청**이다.

    🔄 **레인 G가 이 문단을 다시 썼다.** 여기 있던 것은 *"`retrieve()`는
    `_embed_texts([query] + 색인 21행)`을 한 번 부른다"*였다(그 문장이 달고 있던
    앵커는 배선 전 `memory.py`의 임베딩 호출 줄이고, 배선이 그 줄을 없앴다 —
    표류한 인용을 남기지 않으려고 **옛 줄 번호는 여기 다시 적지 않는다**).
    배선 뒤에는 **`[query] + 저장돼 있지 않은 요약만`**을 한 번 부른다
    (`memory.py:1140` → `Memory._index_vectors`). 정상 상태에서 그 목록은
    `[query]` 하나다. **한 호출에 한 요청이라는 이 클래스의 성질은 그대로**이고,
    그래서 여기서 미스를 한 요청으로 묶는 것이 프로덕션이 하는 일과 같은 모양이다. `embedding.embed()`를 쓰지 않는 이유는
    `rel_dist.py:386-389`가 적어 둔 것 그대로다 — 그 래퍼는 텍스트마다 따로
    `_post`를 불러서 배치 이득 4.0배를 버린다.

    `force`가 캐시 체제를 정한다. 이것이 콜드/준-콜드/웜을 만드는 유일한 손잡이다.
      "none"  웜      — 전부 캐시 히트
      "query" 준-콜드 — 첫 텍스트(쿼리)만 미스, 색인 벡터는 히트
      "all"   콜드    — 전부 미스 (오늘의 `memory.py`가 실제로 하는 일)
    """

    def __init__(self, cache, force="none"):
        self.cache = cache
        self.force = force
        self.failed = False        # 🔴 강등의 씨앗. 셀 판정이 이 값을 읽는다
        self.requests = 0
        self.texts_sent = 0

    def __call__(self, texts):
        texts = list(texts)
        if self.force == "all":
            need = list(dict.fromkeys(texts))
        elif self.force == "query":
            need = [texts[0]]
        else:
            need = [t for t in dict.fromkeys(texts) if t not in self.cache]
        if need:
            vecs = self._fetch(need)
            if vecs is None:
                # 🔴 여기서 `None`을 돌려주면 `retrieve()`가 **강등**한다. 강등 자체는
                #    막을 수 없지만(프로덕션 경로다) 그 사실을 셀 판정이 읽을 수 있게
                #    깃발을 세운다 — 그 셀은 `측정 안 됨`이 되고 스윕은 77로 끝난다.
                self.failed = True
                return None
            self.cache.update(dict(zip(need, vecs)))
        return [self.cache[t] for t in texts]

    def _fetch(self, need):
        try:
            r = EMB._post("/api/embed",
                          {"model": EMB.EMBED_MODEL, "input": need},
                          EMB.EMBED_TIMEOUT)
        except Exception:
            return None
        vecs = r.get("embeddings") or []
        if len(vecs) != len(need):
            return None
        self.requests += 1
        self.texts_sent += len(need)
        return vecs


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def load_cache():
    """
    `REL_CACHE.json`(읽기 전용) 위에 이 스윕의 캐시를 얹어 메모리에 든다.

    `(합쳐진 캐시, 남의 것인 키 집합)`을 돌려준다 — 되쓸 때 남의 키를 제외하려면
    **어느 키가 남의 것인지**를 알아야 하고, 그것은 합친 뒤에는 알 수 없다.
    """
    borrowed = _read(RD.REL_CACHE)
    cache = dict(borrowed)
    cache.update(_read(SWEEP_CACHE))
    return cache, set(borrowed)


def save_sweep_cache(cache, borrowed):
    """`REL_CACHE.json`에 이미 있는 키는 다시 쓰지 않는다 — 그 파일은 남의 실험 것이다."""
    own = {k: v for k, v in cache.items() if k not in borrowed}
    if own:
        with open(SWEEP_CACHE, "w", encoding="utf-8") as f:
            json.dump(own, f)


# ── 셀 실행 ────────────────────────────────────────────────────────────

class Cell:
    """한 셀의 정의와 결과. `stage`는 1 또는 2."""

    def __init__(self, idx, stage, gate, mode, f, theta, cut, w_rel, w_imp, pen):
        self.idx, self.stage = idx, stage
        self.gate, self.mode = gate, mode
        self.f, self.theta, self.cut = f, theta, cut
        self.w_rel, self.w_imp, self.pen = w_rel, w_imp, pen
        self.ok = False
        self.dropped = None
        self.note = "측정 안 됨"
        self.tot = None

    @property
    def name(self):
        return f"{self.gate[0]}·{self.mode}·f={self.f:.3f}"


def apply_cell(cell, base_theta, supplier):
    """
    셀의 구성을 전역에 꽂는다. **`THETA_BY_MODE`는 통째로 재바인딩한다**(G13 ①).

    `{k: ... for k, v in base_theta.items()}`가 새 dict를 만든다 — 원본 객체를
    별칭으로 붙들고 한 칸만 바꾸는 것(`d = THETA_BY_MODE; d[k] = v`)과 다르다.
    후자는 G13의 grep을 빠져나가면서 원본을 영구히 오염시킨다.
    """
    M.RETRIEVAL_MODE = cell.mode
    M.W_REL, M.W_IMP = cell.w_rel, cell.w_imp
    M.SURFACED_PENALTY = cell.pen
    M.EMBED_FN = supplier if cell.mode == "embed" else None
    if cell.mode == "lexical":
        # `theta_for("lexical")`은 dict가 아니라 **모듈 전역**을 다시 읽는다
        # (`memory.py:241`의 `THETA_RELEVANCE`). 그래서 이 모드의 θ 손잡이는 여기다.
        M.THETA_RELEVANCE = cell.theta
    else:
        n, sig = P_N, P_SIG
        M.THETA_BY_MODE = {
            k: ((cell.theta, cell.f, n, sig) if k == cell.mode else v)
            for k, v in base_theta.items()}


def guard_theta(cell):
    """
    🔴 셀을 돌리기 **전에** θ가 유도돼 있는지 스윕이 직접 확인한다.

    `retrieve()`가 던져 주기를 기다리면 안 된다 — 공급자가 없으면 선언된 모드는
    `theta_for`에 닿기 전에 `lexical_fixed`로 강등되고 **아무것도 안 터진다**
    (레인 D 검증자 F1b). 읽기에 `.get`을 쓰는 것은 G13의 grep이 읽기와 쓰기를
    구별하지 못하기 때문이다(`memory.py:1153`의 `.get` 주석과 같은 이유).
    """
    entry = M.THETA_BY_MODE.get(cell.mode)
    if entry is None or entry[0] is None:
        raise SystemExit(
            f"🔴 셀 {cell.name}: `THETA_BY_MODE`의 '{cell.mode}' 항목이 "
            f"유도되지 않았다. "
            f"격자를 돌리기 전에 `rel_dist.py`의 등컷 사다리로 유도할 것 (결정 D).")
    if cell.mode == "embed" and M.EMBED_FN is None:
        raise SystemExit(
            f"🔴 셀 {cell.name}: `embed`를 선언했는데 벡터 공급자가 없다. "
            f"이대로 돌면 `retrieve()`가 `lexical_fixed`로 강등하고 그 값이 "
            f"`embed`라는 이름을 달게 된다 (F21).")


def run_cell(env, cell, supplier):
    """
    한 셀을 돌린다. 지표 함수는 **전부 `precision.py`의 것**을 부른다 — 정의가
    두 벌이 되면 이 격자가 `precision-4cells.txt`와 비교 불가능해진다.

    ⚠️ `precision.run_cell`을 그대로 부르지 않는 이유는 하나다: 그 함수는 토큰과
       `build_context` 지연을 **모으지 않는다.** 거기에 그것을 더하면
       `precision.py`의 출력이 움직이고, 그 출력의 바이트 동일성이 이 라운드의
       수용 기준이다(G16). 그래서 순회 구조만 같은 모양으로 두고 두 열을 더했다.
    """
    corpus, ledger, qs, scored, key_of = env
    dbf = f"{ROOT}/prototype/.sweep.db"
    if os.path.exists(dbf):
        os.remove(dbf)
    m = Memory(dbf)
    seed(m)
    ingest(m, corpus, ledger, timed=False)
    m._vocab = build_vocab(m)
    Memory.gate = cell.gate[1]

    last = corpus[-1]["seq"]
    rows, hard_rows, toks, lat = [], [], [], []
    degraded = stale = 0
    sids = {q["id"] for q in scored}
    for q in qs:
        if q["id"] not in sids:
            continue
        t0 = time.perf_counter()
        ctx = m.build_context(CHAT, q["ask"], last)
        lat.append((time.perf_counter() - t0) * 1000)
        toks.append(ctx.tokens)
        degraded += sum(1 for k, _, _ in ctx.provenance if k == "degraded")
        stale += sum(1 for k, _, _ in ctx.provenance if k == "stale_theta")
        ordered = [item for kind, item, _ in ctx.provenance if kind == "retrieved"]
        retrieved = set(ordered)
        gate_pass = bool([1 for kind, item, _ in ctx.provenance
                          if kind == "gate" and item == "통과"])
        hits = m.retrieve(CHAT, q["ask"], last)[0] if gate_pass else []
        if [r["summary"] for _, r in hits] != ordered:
            raise SystemExit(
                f"{q['id']}: retrieve()의 순서와 provenance의 순서가 다르다 — "
                f"top1/동점 진단의 전제가 깨졌다.")
        mis, prec = P.score_question(q, retrieved, key_of)
        ev_hit, ev_tot = P.evidence_recall_via_retrieval(q, retrieved, key_of)
        tie_n, tie_s = P.tie_rank1(hits)
        rows.append(dict(id=q["id"], mis=mis, n_ret=len(retrieved), prec=prec,
                         ev_hit=ev_hit, ev_tot=ev_tot, gate=gate_pass,
                         top1=P.top1_misinjection(q, ordered, key_of),
                         tie_n=tie_n, tie_s=tie_s))
        if q.get("distractor"):
            hard_rows.append(dict(id=q["id"],
                                  hard=P.hard_misinjection(q, retrieved, key_of)))
    trap, blks = trap_injected(m, ledger, last)
    m.db.close()
    os.remove(dbf)

    tot = P.cell_totals(rows)
    tot["hard"] = sum(h["hard"] for h in hard_rows)
    tot["trap"] = bool(blks)
    tot["degraded"] = degraded
    tot["stale"] = stale
    tot["tok_p50"] = pct(toks, 50)
    tot["bc_p50"], tot["bc_p95"] = pct(lat, 50), pct(lat, 95)
    tot["rows"] = rows
    return tot


# ── 파레토 ─────────────────────────────────────────────────────────────

def pareto_front(cells):
    """
    `evidence_recall` 최대 / `misinjection@q` 최소의 **비지배 집합**.

    🔴 스칼라 하나로 고르지 않는 이유는 두 지표가 **같은 방향으로 움직이기**
       때문이다(F23·F24: 2/4/3/11 vs 2/3/6/11). 한 방향만 재면 *"회상 개선"*이라는
       이름으로 오주입을 승격시킨다 — 부검 시나리오 3.
    """
    out = []
    for c in cells:
        rc, mc = c.tot["ev_hit"], c.tot["mis"]
        dominated = any(
            (o.tot["ev_hit"] >= rc and o.tot["mis"] <= mc)
            and (o.tot["ev_hit"] > rc or o.tot["mis"] < mc)
            for o in cells if o is not c)
        if not dominated:
            out.append(c)
    return out


# ── 규칙 ⑤ — 동점 조항 (ADR-015 미해결 «격자 규칙의 동점 조항») ─────────

# 규칙 ③의 상한. **동점 조항은 이 수를 바꾸지 않는다** — 30셀은 계획이 실행 전에
# 고정한 격자 크기이고 `docs/11`의 절 제목·`SUMMARY.md`·정합 감사 CLAIM에 동결돼
# 있다. 동점을 이유로 4를 취하거나(2단 16셀) 0을 취하는(2단 미실행) 조항은
# **조항이 아니라 새 규칙**이다.
SELECT_CAP = 3


def select_key(c):
    """
    규칙 ①②③의 정렬 키 — **동점 조항(⑤)의 3차 키까지 명시한다.**

    🔴 **여기 있던 것은 `(-ev_hit, mis)` 둘뿐이었고, 세 번째 자리를 채운 것은
    규칙이 아니라 두 가지 구현 사실이었다:** (1) `pareto_front`가 `cells`를 인덱스
    순으로 훑어 인덱스 순 리스트를 돌려준다는 것, (2) Python `sort`가 안정 정렬이라
    그 순서를 동점 안에서 보존한다는 것. **둘 다 계획에 안 적혀 있다.**

    3차 키가 `c.idx`인 이유 — 그리고 왜 그것이 임의가 아닌가:

      · 인덱스는 사전 등록된 세 축의 **열거 순서**의 함수다 (`GATES` → `MODES` →
        `LADDER`, 셋 다 계획 §단계 4에 실행 전 고정). 즉 **실행 결과를 하나도 보지
        않고 계획 문서만으로 계산된다.** 타이브레이커에 요구되는 성질이 그것이다.
      · 남은 후보들이 전부 못 쓴다: **θ가 낮은 쪽**은 모드 간 θ 비교라 G12 위반이고
        (0.1111은 덮기율, 0.5849는 코사인 — 같은 자가 아니다), **실제 컷이 느슨한
        쪽**과 **pooled**는 오늘의 동점군에서 둘 다 같아 동점을 안 깨며, 갈리는
        유일한 관측치 `top1`은 계획이 **보고 전용**으로 못박은 열이다(F26 rev2).
        → **허용되는 품질 키가 하나도 없다.**
      · 그래서 3차 키는 **품질이 아닌 것**이어야 하고, 품질이 아니면서 사전 등록된
        것은 열거 순서뿐이다.

    ⚠️ **부산물을 규칙으로 승격시키는 것이 맞다. 그 대가를 적는다:** 이제 축의
       **열거 순서가 의미를 갖는다** — 다음 라운드가 `MODES`를 재배열하면 동점 해소가
       조용히 바뀐다. 그래서 이 조항은 축 순서를 **사전 등록의 일부**로 못박고,
       발화할 때마다 동점군 전체를 이름으로 찍는다(`report_tie_clause`).
    """
    return (-c.tot["ev_hit"], c.tot["mis"], c.idx)


def tie_span(front, cap=SELECT_CAP):
    """
    **절단선을 가로지르는** 동점군을 돌려준다. 없으면 `None`.

    동점군 = 두 선택 키 `(evidence_recall, misinjection@q)`가 **모두** 같은 셀들.
    `front`는 `select_key`로 이미 정렬돼 있다고 가정한다.

    🔴 **가로지를 때만 발화한다.** 전선 안 어딘가에 동점이 있어도 상위 `cap`개의
       **경계**에 걸리지 않으면 선택은 그 동점과 무관하다 — 거기서 조항이 끼어들면
       그것이 오발화이고, 오발화도 결함이다. 아래 `tie_clause_check` ③이 그 대조다.
    """
    if len(front) <= cap:
        return None
    a, b = front[cap - 1], front[cap]      # 마지막 진입 셀 · 첫 탈락 셀
    k = (a.tot["ev_hit"], a.tot["mis"])
    if (b.tot["ev_hit"], b.tot["mis"]) != k:
        return None
    return [c for c in front if (c.tot["ev_hit"], c.tot["mis"]) == k]


def report_tie_clause(front, picked, cap=SELECT_CAP):
    """조항의 발화/미발화를 **매 실행 출력에 찍는다.** 발화하면 탈락 셀까지 이름으로."""
    span = tie_span(front, cap)
    if span is None:
        print(f"\n  ⑤ 동점 조항 — **발화 없음.** 절단선({cap}위/{cap + 1}위)의 두 셀이 "
              f"선택 키에서 다르므로 3차 키가 개입하지 않았다.")
        return span
    inn = [c for c in span if c in picked]
    out = [c for c in span if c not in picked]
    print(f"\n  ⑤ 동점 조항 — 🟡 **발화했다.** 절단선({cap}위/{cap + 1}위)이 동점군 "
          f"안쪽에 떨어진다.")
    print(f"     동점군 {len(span)}개 — 선택 키 "
          f"(recall {span[0].tot['ev_hit']}/{span[0].tot['ev_tot']} · "
          f"mis@q {span[0].tot['mis']})가 전부 같다: "
          f"{', '.join(f'#{c.idx} {c.name}' for c in span)}")
    print(f"     3차 키(격자 인덱스 오름차순)가 고른 것: "
          f"{', '.join(f'#{c.idx}' for c in inn)}   "
          f"탈락: {', '.join(f'#{c.idx}' for c in out)}")
    print(f"     🔴 **이 조항은 우열을 주장하지 않는다.** 두 셀은 선택 지표에서 "
          f"구별되지 않고, 갈리는 유일한 관측치 `top1`은 보고 전용이다(F26 rev2). "
          f"조항이 한 것은")
    print(f"        «구별할 수 없다»를 없앤 것이 아니라 **재현 가능하게 만든 것**뿐이고, "
          f"그래서 탈락 셀을 여기 이름으로 남긴다.")
    return span


class _FakeCell:
    """조항 자체 검사용 대역. 실제 셀을 안 돌리고 선택 키만 흉내 낸다."""

    def __init__(self, idx, ev, mis):
        self.idx = idx
        self.tot = dict(ev_hit=ev, ev_tot=28, mis=mis)
        self.name = f"합성#{idx}"


def _pick(cells, key, cap=SELECT_CAP):
    """`key`로 정렬해 상위 `cap`개의 인덱스를 돌려준다."""
    return [c.idx for c in sorted(cells, key=key)[:cap]]


def tie_clause_check(front, span, cap=SELECT_CAP):
    """
    🔴 **조항을 심은 위반으로 발화시킨다.**

    규칙을 **적는 것**과 그 규칙이 **발화하는 것**은 다른 사실이다. 이 저장소가
    반복해서 깨진 자리가 정확히 거기이므로(여덟 번째 «발화할 수 없는 검사» ·
    `docs/11` 실험 23 §F), 조항은 아래 셋을 **매 실행 출력에** 남긴다.

      ① **강제 발화** — 오늘의 전선을 입력 순서 셋(원/역/회전)으로 넣는다.
         옛 키 `(-ev, mis)`는 흔들리고 새 키 `(-ev, mis, idx)`는 안 흔들린다.
         (후속 10이 `retrieve()`의 동점에 쓴 것과 같은 대조다.)
         ⚠️ **오늘의 격자에 동점이 있다는 사실에 기대는 검사는 이것 하나뿐**이고,
         그래서 조항이 발화하지 **않은** 실행에서는 ①이 하중을 못 싣는다 —
         그 경우 ①은 «해당 없음»이 되고 발화 증거는 ②가 전부 진다.
      ② **심은 위반** — 동점이 **없는** 합성 전선에 동점을 인위적으로 **심어서**
         조항이 발화하는지 본다. 오늘의 격자에 동점이 있다는 사실에 기대지 않는다.
      ③ **오발화 대조** — 동점이 절단선을 **안 가로지르는** 두 경우(동점이 상위
         안쪽에만 · 전선이 `cap` 이하)에서 조항이 **발화하지 않는지** 본다.

    셋 중 하나라도 어긋나면 `SystemExit` — 조항이 발화하지 않는 채로 «조항을 적었다»가
    보고되는 것을 막는다.
    """
    print("\n" + "-" * W)
    print("⑤ 동점 조항 자체 검사 — **심은 위반으로 발화를 확인한다** (오발화 대조 포함)")
    hr()
    old = lambda c: (-c.tot["ev_hit"], c.tot["mis"])          # noqa: E731
    bad = []

    # ── ① 강제 발화: 오늘의 전선 × 입력 순서 셋 ──────────────────────────
    if span is None:
        print(f"  ① 강제 발화 — **해당 없음.** 이 실행의 전선({len(front)}개)에는 "
              f"절단선을 가로지르는 동점이 없다.")
        print(f"     발화 증거는 ②(심은 위반)가 전부 진다. "
              f"오늘의 격자에 동점이 있는지에 조항의 검사를 걸지 않는다.")
    else:
        orders = [("원", list(front)),
                  ("역", list(reversed(front))),
                  ("회전", list(front[2:]) + list(front[:2]))]
        print(f"  ① 강제 발화 — 오늘의 전선({len(front)}개)을 입력 순서 셋으로 넣는다. "
              f"상위 {cap}개가 어떻게 나오나")
        print(f"     {'입력 순서':<8}{'옛 키 (-ev, mis)':<26}"
              f"{'새 키 (-ev, mis, idx)':<26}")
        o_res, n_res = [], []
        for label, seq in orders:
            o, n = _pick(seq, old, cap), _pick(seq, select_key, cap)
            o_res.append(o)
            n_res.append(n)
            print(f"     {label:<8}{str(o):<26}{str(n):<26}")
        o_shaky = len({tuple(x) for x in o_res}) > 1
        n_shaky = len({tuple(x) for x in n_res}) > 1
        print(f"     → 옛 키: {'🔴 흔들린다' if o_shaky else '안 흔들린다'} · "
              f"새 키: {'🔴 흔들린다' if n_shaky else '🟢 안 흔들린다'}")
        if n_shaky:
            bad.append("① 새 키가 입력 순서에 따라 흔들린다 — 3차 키가 결정적이지 않다")
        if not o_shaky:
            bad.append("① 조항이 발화했는데 옛 키가 입력 순서에 안 흔들린다 — "
                       "`tie_span`과 정렬 키가 서로 다른 것을 보고 있다")

    # ── ② 심은 위반: 동점이 없는 전선에 동점을 만들어 넣는다 ──────────────
    clean = [_FakeCell(1, 13, 10), _FakeCell(2, 12, 8),
             _FakeCell(3, 6, 3), _FakeCell(4, 5, 4), _FakeCell(5, 3, 2)]
    planted = [_FakeCell(1, 13, 10), _FakeCell(2, 12, 8),
               _FakeCell(3, 6, 3), _FakeCell(4, 6, 3), _FakeCell(5, 3, 2)]
    c_span = tie_span(sorted(clean, key=select_key), cap)
    p_span = tie_span(sorted(planted, key=select_key), cap)
    p_rev = _pick(list(reversed(planted)), old, cap)
    print(f"\n  ② 심은 위반 — 합성 전선 5개. #4의 (recall, mis@q)를 "
          f"`(5/28, 4)` → `(6/28, 3)`로 바꿔 #3과 동점을 **심는다**")
    print(f"     심기 전  동점군 {'없음' if c_span is None else c_span} "
          f"→ 조항 {'발화 없음' if c_span is None else '발화'}")
    print(f"     심은 뒤  동점군 "
          f"{[c.idx for c in p_span] if p_span else '없음'} "
          f"→ 조항 {'🟢 발화' if p_span else '🔴 발화 없음'}   "
          f"(옛 키를 역순으로 넣으면 상위 {cap} = {p_rev} — #4가 #3을 밀어낸다)")
    if c_span is not None:
        bad.append("② 동점을 심기 전인데 조항이 발화했다 — 오발화")
    if p_span is None or [c.idx for c in p_span] != [3, 4]:
        bad.append("② 동점을 심었는데 조항이 발화하지 않았다")
    if _pick(list(reversed(planted)), select_key, cap) != [1, 2, 3]:
        bad.append("② 심은 동점에서 새 키가 인덱스 오름차순을 안 지켰다")

    # ── ③ 오발화 대조 ────────────────────────────────────────────────────
    inside = [_FakeCell(1, 13, 10), _FakeCell(2, 13, 10),
              _FakeCell(3, 6, 3), _FakeCell(4, 5, 4), _FakeCell(5, 3, 2)]
    short = [_FakeCell(1, 13, 10), _FakeCell(2, 6, 3), _FakeCell(3, 6, 3)]
    i_span = tie_span(sorted(inside, key=select_key), cap)
    s_span = tie_span(sorted(short, key=select_key), cap)
    print(f"\n  ③ 오발화 대조 — 동점이 있어도 **절단선을 안 가로지르면** 발화하면 안 된다")
    # 실패했을 때 **무엇이 발화했는지**가 읽혀야 한다 — 객체 repr은 아무것도 안 말한다.
    ids = lambda g: "없음" if g is None else str([c.idx for c in g])   # noqa: E731
    print(f"     동점이 1·2위 (절단선 {cap}/{cap + 1} 밖)      "
          f"→ {'🟢 발화 없음' if i_span is None else '🔴 발화 ' + ids(i_span)}")
    print(f"     전선이 {len(short)}개 (≤ {cap} — 규칙 ②가 전부 올린다)   "
          f"→ {'🟢 발화 없음' if s_span is None else '🔴 발화 ' + ids(s_span)}")
    if i_span is not None:
        bad.append("③ 절단선 밖 동점에 조항이 발화했다 — 오발화")
    if s_span is not None:
        bad.append("③ 전선이 상한 이하인데 조항이 발화했다 — 오발화")

    if bad:
        raise SystemExit("🔴 동점 조항 자체 검사 실패:\n  " + "\n  ".join(bad))
    print("\n  ✅ 셋 다 기대대로다 — 조항은 **심은 동점에 발화하고, 동점이 아닌 곳에 "
          "끼어들지 않는다.**")


# ── 출력 ───────────────────────────────────────────────────────────────

def hr(ch="-"):
    print(ch * W)


def table_a(cells, title):
    """선택이 읽는 두 열 + 그 분모. 파레토가 보는 것이 전부 여기 있다."""
    print("\n" + "=" * W)
    print(title)
    print("=" * W)
    print(f"  {'#':>3} {'게이트':<5}{'모드':<15}{'요청f':>7}{'θ':>10}{'실제컷':>9}"
          f"{'w_rel/w_imp':>13}{'pen':>6}{'recall':>9}{'mis@q':>7}"
          f"{'pooled(분모)':>16}{'top1(분모)':>12}{'동점':>6}")
    hr()
    for c in cells:
        t = c.tot
        if t is None:
            print(f"  {c.idx:>3} {c.gate[0]:<5}{c.mode:<15}{c.f:>7.3f}"
                  f"{'—':>10}{'—':>9}{'—':>13}{'—':>6}   🔴 {c.note}")
            continue
        pooled = ("정의 안 됨" if t["pooled"] is None
                  else f"{t['pooled']:.3f}({t['ret']})")
        top1 = f"{t['top1']}/{t['top1_n']}" if t["top1_n"] else "정의 안 됨"
        print(f"  {c.idx:>3} {c.gate[0]:<5}{c.mode:<15}{c.f:>7.3f}{c.theta:>10.4f}"
              f"{c.cut:>8.1%}{f'{c.w_rel}/{c.w_imp}':>13}{c.pen:>6}"
              f"{f'{t['ev_hit']}/{t['ev_tot']}':>9}{t['mis']:>7}"
              f"{pooled:>16}{top1:>12}{len(t['ties']):>6}")


def table_b(cells, title):
    """나머지 관측. 게이트 분해·토큰·지연·회귀 탐지기."""
    print("\n" + "=" * W)
    print(title)
    print("=" * W)
    print(f"  {'#':>3} {'셀':<26}{'macro(자동1.0)':>16}{'검색호출':>9}"
          f"{'게이트 통과/차단/통과0건/≥1건':>30}{'토큰p50':>9}"
          f"{'bc p50/p95(ms)':>17}{'deg':>5}{'trap':>7}{'hard':>6}")
    hr()
    for c in cells:
        t = c.tot
        if t is None:
            print(f"  {c.idx:>3} {c.name:<26}   🔴 {c.note}")
            continue
        gd = (f"{t['gate_pass']}/{t['gate_block']}/{t['pass_zero']}/{t['live']}"
              f" (합 {t['gate_pass'] + t['gate_block']}/18)")
        print(f"  {c.idx:>3} {c.name:<26}{f'{t['macro']:.3f}({t['auto1']})':>16}"
              f"{t['gate_pass']:>9}{gd:>30}{t['tok_p50']:>9.0f}"
              f"{f'{t['bc_p50']:.2f}/{t['bc_p95']:.2f}':>17}{t['degraded']:>5}"
              f"{('주입됨' if t['trap'] else '없음'):>7}{t['hard']:>6}")


def tie_detail(cells):
    """
    F26 rev2 — `top1`은 **동점 문항 수와 목록을 병기해서만** 읽는다.

    🔄 **레인 G — 이 문단의 첫 문장이 거짓이 됐다.** 여기 있던 것은
    *"동점의 1등은 점수가 아니라 rowid가 정한다(`memory.py:838`)"*였고,
    후속 10이 닫히면서(`memory.py:1189`의 `scored.sort` · `(-s, event_id)`) **1등은 이제
    `event_id`가 정한다.** ⚠️ 그것도 삽입 순서이므로 *"의미로 정한다"*는 뜻이 아니다 —
    바뀐 것은 **SELECT 반환 순서에 대한 의존이 사라진 것**이고, 오늘의 값은
    한 자리도 안 움직였다.

    **그래도 이 병기는 남는다.** 2단은 가중치와 페널티를 움직여 **동점을 체계적
    방향으로 깬다** — 그래서 2단의 `top1` 변화는 순위 개선인지 동점 해소 인공물인지
    여전히 **구별할 수 없다.** 결정적 키가 없앤 것은 *재현 불가능성*이지
    *해석 불가능성*이 아니다.
    → **2단 표에서 `top1`은 보고 전용이고 선택에 쓰지 않는다.**
    """
    print("\n" + "-" * W)
    print("top1 동점 병기 (F26 rev2) — 동점의 1등은 이제 `(-s, event_id)`가 정한다 "
          "(후속 10 · 레인 G)")
    hr()
    for c in cells:
        if c.tot is None:
            continue
        ties = c.tot["ties"]
        s = "; ".join(P._fmt_tie(r) for r in ties) if ties else "없음"
        print(f"  {c.idx:>3} {c.name:<28}동점 {len(ties)}건   {s}")


# ── 지연 프로파일 (콜드 / 준-콜드 / 웜) ────────────────────────────────

def latency_profile(env, base_theta, ladder, cache, gate, mode):
    """
    `build_context` 지연을 **캐시 체제 셋**으로 나눠 잰다 (단계 4 (d)의 정의 표).

    🔄 **레인 G가 이 정의를 다시 썼다 — 배선이 세 라벨의 뜻을 바꿨기 때문이다**
       (G15의 라벨 출처 규칙: 라벨이 어느 구성을 가리키는지와 **언제부터** 그런지를
       같은 자리에 적는다). `force`는 여전히 **하니스 파일 캐시**의 손잡이이고,
       바뀐 것은 그 손잡이가 몇 개의 텍스트에 걸리는가다.

      콜드    하니스 캐시가 **전부 미스**. 배선 전에는 조회마다 `[질의] + 색인 21행`
              = 22텍스트였다. **배선 뒤에는 첫 조회만 22텍스트이고**(색인 벡터가
              비어 있으니 지연 재계산이 한 번 돈다) **이후 조회는 `[질의]` 1건**이다.
              🔴 그래서 이 행의 p50은 이제 **정상 상태**를, 최댓값은 **1회성
              백필**을 가리킨다 — 두 개의 다른 사건이 한 열에 있다.
      준-콜드 질의만 미스, 색인 벡터는 히트. **배선 뒤에는 이것이 프로덕션의
              정상 상태다** — 배선 전에는 *"아직 없는 시스템의 값"*이었다.
      웜      전부 히트. 어휘 경로와 같은 대역.

    🔴 **승격 조건 3이 읽는 것은 콜드 p95다.** 준-콜드가 아니다 —
       *"게이트는 코드가 실제로 하는 것을 읽어야 한다."*

    🆕 **그리고 이제 n = 18 × `COND3_REPEATS`다.** 문항 18개를 반복해서 읽는다.
       DB는 반복 사이에 **살아 있다** — 그것이 요점이다: 색인 하나에 대한 연속
       조회 108번을 재는 것이고, 백필은 그중 **한 번**만 일어난다.

    ⚠️ 여기서 "콜드"는 **이 하니스의 캐시가 전부 미스**라는 뜻이다. ollama 쪽의
       모델 적재는 별개이고 이미 웜이다 — 즉 아래 콜드 값은 **하한**이다.
    """
    corpus, ledger, qs, scored, key_of = env
    theta, f, cut = ladder[mode][0]      # f=0.80 눈금 — 지연은 θ에 거의 무관하다
    out = {}
    regimes = [("웜", "none")] if mode != "embed" else \
        [("콜드", "all"), ("준-콜드", "query"), ("웜", "none")]
    snap = snapshot_globals()
    try:
        for label, force in regimes:
            sup = Supplier(cache, force=force)
            M.RETRIEVAL_MODE = mode
            M.EMBED_FN = sup if mode == "embed" else None
            if mode == "lexical":
                M.THETA_RELEVANCE = theta
            else:
                M.THETA_BY_MODE = {
                    k: ((theta, f, P_N, P_SIG) if k == mode else v)
                    for k, v in base_theta.items()}
            dbf = f"{ROOT}/prototype/.sweeplat.db"
            if os.path.exists(dbf):
                os.remove(dbf)
            m = Memory(dbf)
            seed(m)
            ingest(m, corpus, ledger, timed=False)
            m._vocab = build_vocab(m)
            Memory.gate = gate[1]
            last = corpus[-1]["seq"]
            lat, calls, deg, lazy = [], 0, 0, 0
            sids = {q["id"] for q in scored}
            # 🆕 반복 사이에 **DB를 다시 만들지 않는다** — 색인 하나에 대한 연속
            #    조회를 재는 것이고, 배선의 백필은 그중 첫 조회에서만 일어난다.
            for rep in range(COND3_REPEATS):
                for q in qs:
                    if q["id"] not in sids:
                        continue
                    t0 = time.perf_counter()
                    ctx = m.build_context(CHAT, q["ask"], last)
                    lat.append((time.perf_counter() - t0) * 1000)
                    deg += sum(1 for k, _, _ in ctx.provenance if k == "degraded")
                    lazy += sum(1 for k, _, _ in ctx.provenance if k == "lazy_embed")
                    # `검색호출`은 **1회분**만 센다 — 이 열이 세는 것은
                    # *"18문항 중 몇 개가 게이트를 통과하나"*이지 반복 수가 아니다.
                    if rep == 0 and any(k == "gate" and i == "통과"
                                        for k, i, _ in ctx.provenance):
                        calls += 1
            m.db.close()
            os.remove(dbf)
            # 🔄 **레인 G가 이 주석을 다시 썼다.** 여기 있던 것은
            #    *"n=18에서 p95는 표본의 최댓값이다 … 18개 중 가장 나쁜 한 번이
            #    정한다"*였고, 그것이 조건 3이 재현되지 않은 기제였다.
            #    이제 n = 18 × {COND3_REPEATS}이고 `int(n*0.95) < n-1`이라
            #    **p95는 극값이 아니라 분위수다.** 조건은 그대로 p95를 읽는다 —
            #    바뀐 것은 통계량이 아니라 표본 크기다.
            #    `hi`(최댓값)를 표에 따로 찍는다: 그 한 번이 무엇이었는지는
            #    여전히 읽을 수 있어야 하고, 배선 뒤 콜드에서 그것은 **백필**이다.
            out[label] = dict(p50=pct(lat, 50), p90=pct(lat, 90),
                              p95=pct(lat, 95), lo=min(lat), hi=max(lat),
                              n=len(lat), calls=calls, degraded=deg,
                              failed=sup.failed, requests=sup.requests,
                              texts=sup.texts_sent, lazy=lazy, draws=list(lat))
    finally:
        restore_globals(snap)
        assert_restored(snap, f"지연 프로파일 {mode}")
    return out


# ── 단계 5 — 기본값 판정 ───────────────────────────────────────────────

def verdict(cells, base, lat, front):
    """
    승격 **3조건 + 선행 조건 3종** (계획 §단계 5 rev3). 조건을 약화하지 않는다.

    ⛔ **기본값 유지가 기본 결과다.** 3조건을 통과해도 그것은 *"논의할 수 있다"*이지
       *"바꾼다"*가 아니다 — 홀드아웃이 없으므로(문항 18 · `eval/` 불변 A8)
       격자로 기본값을 자동 승격하지 않는다.
    """
    lo, hi = TTFT_BUDGET
    b = base.tot
    print("\n" + "=" * W)
    print("단계 5 — 기본값 판정 (승격 3조건 + 선행 조건 3종 · rev3)")
    print("=" * W)
    print(f"\n  기준셀: {base.name} = {base.gate[2]} · 모드 lexical · "
          f"θ={base.theta:.4f}(요청 f={base.f} · 실제 컷 {base.cut:.1%} · "
          f"n={P_N} · 서명 {P_SIG})")
    print(f"    ⚠️ 이 θ는 현행 기본값 θ={M.THETA_RELEVANCE}(같은 {P_N}쌍에서 컷 90.7%)와 "
          f"**같은 35쌍을 통과시킨다** — 0 초과 최솟값이 0.0588이라 그 사이에 "
          f"관측값이 없다 (F27).")
    print(f"    evidence_recall {b['ev_hit']}/{b['ev_tot']} · "
          f"misinjection@q {b['mis']} · pooled {b['pooled']:.3f}(분모 {b['ret']}) · "
          f"top1 {b['top1']}/{b['top1_n']}(동점 {len(b['ties'])}건)")

    print("\n  선행 조건")
    print("    ① 단계 2-L (임베딩 지연 게이트)   PASS "
          "— F38 정정 후 웜 p50 55 ms = 예산 상한의 0.14배 "
          "(`.omc/plans/verifier-f38-overturn.md`)")
    ok_run = all(c.tot is not None for c in cells)
    print(f"    ② 단계 4 완주 (종료 0)            "
          f"{'PASS' if ok_run else 'FAIL'} — 측정 안 된 셀 "
          f"{sum(1 for c in cells if c.tot is None)}개")
    deg_tot = sum(c.tot["degraded"] for c in cells if c.tot)
    print(f"    ③ degraded 발생 수 = 0            "
          f"{'PASS' if deg_tot == 0 else 'FAIL'} — 합계 {deg_tot}")
    print("       🔴 ③은 **게이트가 아니라 구조적 항등**이다 — 77은 완주가 아니므로 "
          "단계 5에 도달한 실행에서는 이미 0이다 (rev3 · Critic 편집 4).")

    print(f"\n  승격 조건 — **전부** 만족해야 논의 대상이 된다 "
          f"(예산 {lo}~{hi} ms · 기준 recall {b['ev_hit']}/{b['ev_tot']} · "
          f"기준 pooled {b['pooled']:.3f})")
    print(f"    {'#':>3} {'셀':<28}{'1: recall':>16}"
          f"{'2: pooled 쌍 판정':>30}{'3: 콜드 p95 ≤ 예산':>36}{'판정':>8}")
    hr()
    passed = []
    for c in cells:
        t = c.tot
        if t is None:
            print(f"    {c.idx:>3} {c.name:<28}{'측정 안 됨':>16}"
                  f"{'—':>30}{'—':>36}{'제외':>8}")
            continue
        c1 = t["ev_hit"] >= b["ev_hit"]
        s1 = f"{t['ev_hit']}/{t['ev_tot']} {'PASS' if c1 else 'FAIL'}"
        # 조건 2는 **쌍**이다. 스칼라로 합치면 가중치가 곧 결정이 되고 그 가중치를
        # 정당화할 데이터가 없다(문항 18 · 근거 28). 파레토 비지배로 판정한다.
        pl = t["pooled"]
        if pl is None:
            c2, s2 = False, "정의 안 됨 FAIL"
        elif pl >= b["pooled"]:
            c2, s2 = True, f"{pl:.3f}(분모 {t['ret']}) ≥ 기준 PASS"
        else:
            c2 = t["ev_hit"] > b["ev_hit"]
            s2 = (f"{pl:.3f}(분모 {t['ret']}) < 기준, recall "
                  f"{'우세' if c2 else '열세'} {'PASS' if c2 else 'FAIL'}")
        # 🔴 **어휘 두 모드에는 `콜드` 행이 없다 — 임베딩이 없어서 세 체제가 같기
        #    때문이다.** 그 값을 말없이 `콜드 p95` 칸에 넣으면 그것이 F21(옳은
        #    숫자에 틀린 이름)이다. 같은 값을 쓰되 **왜 같은지를 칸 안에 적는다.**
        prof = lat.get(c.mode, {})
        cold, tag = (prof.get("콜드"), "") if "콜드" in prof \
            else (prof.get("웜"), " 콜드≡웜")
        if cold is None:
            c3, s3 = False, "측정 안 됨 FAIL"
        else:
            c3 = cold["p95"] <= hi
            s3 = (f"p95 {cold['p95']:,.0f}(p50 {cold['p50']:,.0f}) ms{tag} "
                  f"{'PASS' if c3 else 'FAIL'}")
        allok = c1 and c2 and c3
        if allok:
            passed.append(c)
        print(f"    {c.idx:>3} {c.name:<28}{s1:>16}{s2:>30}{s3:>36}"
              f"{('통과' if allok else '탈락'):>8}")

    # 🔴 **통과 개수를 그대로 읽으면 안 된다.** 셋 중 둘은 승격 후보가 아니다.
    ident = [c for c in passed if c is base]
    s1_pass = [c for c in passed if c.stage == 1 and c is not base]
    s2_pass = [c for c in passed if c.stage == 2]
    print(f"\n  3조건을 전부 통과한 셀: **{len(passed)}개** "
          f"({', '.join('#' + str(c.idx) for c in passed) if passed else '없다'})")
    print(f"    · 기준셀 자신 (#{base.idx}) {len(ident)}개 — **항등이다.** "
          f"자기보다 크거나 같다는 조건은 언제나 참이므로 승격 후보가 아니다 (G14).")
    print(f"    · 2단 셀 {len(s2_pass)}개 "
          f"({', '.join('#' + str(c.idx) for c in s2_pass) if s2_pass else '없음'}) "
          f"— **2단은 승격 권한이 없다** (결정 C 방어 3). 전부 같은 1단 셀의 재현이다.")
    print(f"    · 실질 후보 = **1단의 비기준 통과 셀 {len(s1_pass)}개**"
          + (f": {', '.join(f'#{c.idx} {c.name}' for c in s1_pass)}"
             if s1_pass else " — 없다"))

    # §단계 5의 조건 2 판정 규칙 그 자체. 계획의 문장을 그대로 집행한다.
    print(f"\n  그리고 §단계 5가 조건 2에 붙여 둔 규칙: *\"파레토 비지배로 판정하고, "
          f"전선 위에 여러 셀이")
    print(f"  남으면 승격하지 않는다. 남는 것이 하나뿐일 때만 논의를 연다.\"* "
          f"— **전선은 {len(front)}개다.**")
    if len(front) > 1:
        print(f"    → 🔴 **승격 논의를 열지 않는다.** 실질 후보가 몇 개든 이 규칙이 "
              f"먼저 닫는다.")
        print(f"       (이 규칙 자체가 미해결이다 — Q2-2.)")
    print("\n  ⛔ **판정: 기본값은 `lexical` 그대로 유지한다. 기본 결과는 유지다** (G16).")
    print("     홀드아웃이 없으므로(문항 18 · `eval/` 불변 A8) 격자로 기본값을 자동")
    print("     승격하지 않는다 — 3조건 통과는 *\"논의할 수 있다\"*이지 "
          "*\"바꾼다\"*가 아니다.")
    if not s1_pass:
        print("     1단에 통과 셀이 없다는 것이 이 격자의 결과다 — 계획이 그렇게 "
              "적으라고 했다(§단계 5 (a)).")

    # 조건 3이 실제로 무엇을 죽였는가 — 품질이 아니라 배선이다.
    prof = lat.get("embed", {})
    if prof.get("콜드"):
        cold, quasi, warm = prof["콜드"], prof.get("준-콜드"), prof.get("웜")
        # 🔄 **레인 G — 이 문단이 판정을 앞질러 적고 있었다.** 여기 있던 머리줄은
        #    *"조건 3이 `embed`를 떨어뜨린 이유는 …"*로 **탈락을 전제**했는데,
        #    배선 뒤에는 통과하는 실행이 있다. 판정을 실제 값에서 다시 읽는다 —
        #    산문이 기계 출력을 앞지르는 것이 이 저장소가 F21로 겪은 것이다.
        c3_ok = cold["p95"] <= hi
        if c3_ok:
            print(f"\n  🟢 **`embed`가 조건 3을 통과한다 — 그리고 그것을 만든 것은 "
                  f"배선이다.**")
        else:
            print(f"\n  🔴 **조건 3이 `embed`를 떨어뜨린 이유는 검색 품질이 아니라 "
                  f"배선이다.**")
        print(f"     콜드    p50/p95 = {cold['p50']:,.0f}/{cold['p95']:,.0f} ms "
              f"vs 예산 {lo}~{hi} ms → p95는 상한의 {cold['p95']/hi:.2f}배 · "
              f"p50은 {cold['p50']/hi:.2f}배")
        if quasi:
            print(f"     준-콜드 p50/p95 = {quasi['p50']:,.0f}/{quasi['p95']:,.0f} ms "
                  f"(배선 뒤 프로덕션의 정상 상태)")
        if warm:
            print(f"     웜      p50/p95 = {warm['p50']:,.0f}/{warm['p95']:,.0f} ms "
                  f"(보고 전용 — 어휘 경로와 같은 대역)")
        # 🔴 숫자를 옮겨 적지 않는다 (G11) — 격자에서 다시 뽑는다.
        # ⚠️ `embed` 셀이 전부 `측정 안 됨`일 수 있다(하니스 규약으로 77이 되는 실행).
        #    그때 `max()`는 빈 열에서 터진다 — **77로 끝나야 할 실행이 역추적으로
        #    끝나면 종료 코드가 사라진다.** 그래서 기본값을 준다.
        live = [c for c in cells if c.tot and c.mode == "embed"]
        best = max(live, key=lambda c: c.tot["ev_hit"], default=None)
        top = max((c.tot["ev_hit"] for c in cells if c.tot), default=None)
        print(f"     🔄 세 행의 차이는 배선 **전에는** 문서 벡터 배선의 전부였다. "
              f"배선 뒤에 남은 차이는")
        print(f"        **첫 조회 1회의 백필**(콜드의 최댓값 {cold['hi']:,.0f} ms)과 "
              f"**질의 임베딩 1건**(콜드≈준-콜드의 p50)이다.")
        print(f"     `embed`의 검색 품질은")
        if best is None:
            print(f"     조건 1·2에서 판정할 수 없었다 — `embed` 셀이 전부 "
                  f"**측정 안 됨**이다 (하니스 규약).")
        else:
            print(f"     조건 1·2에서 이미 판정됐다 — 최고 셀 #{best.idx} {best.name}의 "
                  f"recall {best.tot['ev_hit']}/{best.tot['ev_tot']}"
                  f"{' = 격자 전체 최고' if best.tot['ev_hit'] == top else ''} · "
                  f"pooled {best.tot['pooled']:.3f}(분모 {best.tot['ret']}).")
        if c3_ok:
            print(f"     **조건 3도 이제 통과한다. 그래도 승격은 없다** — 닫는 것은 "
                  f"지연이 아니라 전선 규칙과 홀드아웃 부재다(위).")
        else:
            print(f"     떨어진 것은 오직 조건 3이다. **이 숫자를 `embed` 모드의 검색 "
                  f"품질에 대한 판결로")
            print(f"     읽지 마라 — 배선에 대한 판결이다.**")
    return passed


def hybrid_reentry(env, cells):
    """
    결정 E — 하이브리드 재진입 조건을 격자 데이터로 판정한다.

    조건 2: *"격자에서 `embed` 모드가 `lexical`보다 `evidence_recall`이 낮은 문항이
    1개 이상 있고, 그 문항의 어휘 `rel > 0`이다."* = 어휘가 들고 있는데 임베딩이
    잃어버린 신호가 **실측된다**. 참이 아니면 섞을 것이 없다.
    """
    corpus, ledger, qs, scored, key_of = env
    print("\n" + "=" * W)
    print("하이브리드 재진입 조건 (결정 E) — 격자가 무엇을 말하는가")
    print("=" * W)
    print("  조건 1  bge-m3로 채점되는 **유형 라벨 프로브 집합 n ≥ 20**")
    print("          → **측정 안 됨 · 존재하지 않는다.** `retrieval_sim.PROBES`(n=10)에는")
    print("            유형 라벨이 없고, `hybrid_sim.PARAPHRASE`(n=5)는 다른 모델")
    print("            (`multilingual-e5-small`)로 잰 것이라 bge-m3로 옮길 수 없다.")

    print("\n  조건 2  `embed`의 문항별 recall < `lexical`이고 그 문항의 어휘 rel > 0")
    print("          ⚠️ **한 쌍만 보면 안 된다** — 같은 `f`가 두 모드에서 다른 컷을")
    print("             내므로(F28-b) 대조는 (게이트, f)가 **같은 여섯 쌍 전부**를 훑고,")
    print("             그중 `실제 컷`이 실제로 일치하는 쌍을 따로 표시한다.")

    # 어휘 rel의 문항별 상한을 **한 번만** 계산해 둔다 (조건 2의 둘째 항).
    asks = {q["id"]: q["ask"] for q in scored}
    dbf = f"{ROOT}/prototype/.sweephy.db"
    if os.path.exists(dbf):
        os.remove(dbf)
    m = Memory(dbf)
    seed(m)
    ingest(m, corpus, ledger, timed=False)
    sums = [r["summary"] for r in m.db.execute(
        "SELECT summary FROM event WHERE chat_id=? AND user_deleted=0", (CHAT,))]
    m.db.close()
    os.remove(dbf)
    lex_rel = {qid: max((M.coverage(set(M.bigrams(a)), set(M.bigrams(s)))
                         for s in sums), default=0.0)
               for qid, a in asks.items()}

    print(f"\n    {'게이트':<6}{'요청 f':>8}{'lexical 컷':>12}{'embed 컷':>11}"
          f"{'컷 일치':>9}   embed가 잃은 문항 (그 문항의 어휘 rel 최대)")
    hr()
    fired = []
    for gname, _, _ in GATES:
        for f in LADDER:
            lx = next((c for c in cells if c.gate[0] == gname
                       and c.mode == "lexical" and c.f == f), None)
            eb = next((c for c in cells if c.gate[0] == gname
                       and c.mode == "embed" and c.f == f), None)
            if not (lx and lx.tot and eb and eb.tot):
                print(f"    {gname:<6}{f:>8.3f}{'—':>12}{'—':>11}{'—':>9}   측정 안 됨")
                continue
            lr = {r["id"]: r["ev_hit"] for r in lx.tot["rows"]}
            losers = [r["id"] for r in eb.tot["rows"]
                      if r["ev_hit"] < lr.get(r["id"], 0)]
            live = [q for q in losers if lex_rel[q] > 0]
            fired += live
            same = abs(lx.cut - eb.cut) < 5e-4
            detail = (", ".join(f"{q}({lex_rel[q]:.4f})" for q in losers)
                      if losers else "없음")
            print(f"    {gname:<6}{f:>8.3f}{lx.cut:>11.1%}{eb.cut:>10.1%}"
                  f"{('예' if same else '아니오'):>9}   {detail}")
    fired = sorted(set(fired))
    print(f"\n          어휘 rel > 0 인 채로 `embed`가 잃은 문항 (합집합): "
          f"{fired if fired else '없음'}")
    if not fired:
        print("          → 🔴 **재진입 조건 2가 거짓이다 — 기각 조건이 발화했다.**")
        print("             어휘가 들고 있는데 임베딩이 잃어버린 신호가 이 격자에")
        print("             하나도 없다. 섞을 것이 없다 (F29의 예측대로다).")
    else:
        print("          → 🟡 **재진입 조건 2가 참이다.** F29(α=0.5의 순위 프로파일이")
        print("             임베딩 단독과 완전히 동일)의 예측과 **다르다** — 270쌍")
        print("             프로브가 아니라 378쌍 검색 모집단에서는 어휘가 임베딩이")
        print("             놓친 문항을 들고 있는 경우가 실측된다.")
        print("          → 그래도 **하이브리드는 기각 상태 그대로다**: 재진입은 두 조건이")
        print("             **둘 다** 참이어야 하고 조건 1(유형 라벨 프로브 n ≥ 20)이")
        print("             여전히 거짓이다. 재진입하려면 그 프로브 집합을 먼저 만들어야")
        print("             한다 (`eval/` 밖 실험 자산이므로 A8과 무관하다).")


# ── main ───────────────────────────────────────────────────────────────

P_N, P_SIG = None, None       # 모집단 n과 서명. `main()`이 **실측으로** 채운다


def main():
    global P_N, P_SIG
    t_start = time.perf_counter()
    print("=" * W)
    print("검색 격자 30셀 — 라운드 2 단계 4 (실험 21 · 결정 C 집행)")
    print("=" * W)
    print("\n  격자는 **실행 전에 계획에 고정돼 있다**"
          " (`ralplan-retrieval-summary.md` §단계 4).")
    print("  1단 18셀 = 게이트 2 × 모드 3 × θ 3 · 2단 12셀 = 파레토 전선 3 × 가중치 2 "
          "× 페널티 2.")
    print("  🔴 **하니스는 강등하지 않는다.** 선언한 모드를 못 돌리는 셀은 "
          "`측정 안 됨`이고 스윕은 종료 77로 끝난다.")
    print("     (`retrieve()`의 프로덕션 강등 경로는 그대로 둔다 — "
          "`memory.py:1144`의 `lexical_fixed` 강등. 두 경로는 의도적으로 다르다.)")

    corpus, ledger, qs = P.load()
    key_of = P.key_index(ledger)
    scored, excluded = P.partition(qs, key_of)
    env = (corpus, ledger, qs, scored, key_of)
    print(f"\n  채점 {len(scored)}/{len(qs)}문항 · 제외 {len(excluded)}문항 "
          f"({', '.join(i for i, _ in excluded)})")

    # ── θ 사다리를 **다시 유도한다** (전사 금지 · G11) ──────────────────
    asks, sums, total_rows = RD.population()
    P_N, P_SIG = len(asks) * len(sums), (total_rows, len(sums))
    cache, borrowed = load_cache()
    texts = asks + sums + [TRAP_UTTERANCE]
    missing = [t for t in dict.fromkeys(texts) if t not in cache]
    print(f"\n  모집단: 채점 {len(asks)}문항 × event 색인 {len(sums)}행 = "
          f"**{P_N}쌍** · 서명 {P_SIG}")
    print(f"  임베딩 캐시: 필요 {len(set(texts))}개 · 히트 {len(set(texts)) - len(missing)}"
          f" · 미스 {len(missing)}  "
          f"(`REL_CACHE.json` 읽기 전용 + `SWEEP_CACHE.json`)")

    if missing:
        # 사전 확보 — 셀 한복판에서 미스가 나면 그것이 곧 강등이다. 미리 채운다.
        sup = Supplier(cache, force="none")
        if sup(missing) is None:
            print(f"\n  🔴 ollama({EMB.OLLAMA_HOST})가 {len(missing)}건을 돌려주지 "
                  f"못했다 — `embed` 6셀을 **측정 안 됨**으로 두고 종료 77.")
            return 77
    save_sweep_cache(cache, borrowed)

    lex = [M.coverage(set(M.bigrams(a)), set(M.bigrams(s)))
           for a in asks for s in sums]
    fix = [M.jaccard(set(M.tokens_fixed(a)), set(M.tokens_fixed(s)))
           for a in asks for s in sums]
    emb = [RD.cos(cache[a], cache[s]) for a in asks for s in sums]
    vals = {"lexical": lex, "lexical_fixed": fix, "embed": emb}

    ladder = {}
    print("\n" + "-" * W)
    print("θ 축 — 등컷 유도 (결정 D). **요청 f와 실제 컷을 나란히 찍는다** (G15 rev2)")
    hr()
    print(f"  {'모드':<16}{'0의 원자':>9}{'요청 f':>9}{'θ':>12}{'실제 컷':>10}"
          f"{'통과 쌍':>9}{'n':>6}{'서명':>10}   비고")
    for mode in MODES:
        v = vals[mode]
        atom0 = sum(1 for x in v if x == 0) / len(v)
        ladder[mode] = []
        for f in LADDER:
            th = RD.theta_at(v, f)
            cut = RD.actual_cut(v, th)
            ladder[mode].append((th, f, cut))
            passed = sum(1 for x in v if x >= th) if th != math.inf else 0
            if th == math.inf:
                note = "🔴 전량 컷 (이 모드에서 달성 불가능한 f)"
            elif abs(cut - f) < 5e-4:
                note = "요청 f와 일치"
            elif atom0 >= f:
                note = f"⚠️ 요청 f 초과 — 0의 원자({atom0:.1%}) 아래로 못 내려간다"
            else:
                note = f"⚠️ 요청 f 초과 {(cut - f) * 100:.1f}%p — 관측값 격자"
            print(f"  {mode:<16}{atom0:>8.1%}{f:>9.3f}{th:>12.4f}{cut:>9.1%}"
                  f"{passed:>9}{P_N:>6}{str(P_SIG):>10}   {note}")
    print("\n  🔴 **`f=0.80`의 '현행과 동치'는 위 두 어휘 행에만 해당한다.** 0의 원자가")
    print("     90.7% · 89.7%라 어떤 θ도 그보다 적게 자를 수 없어서 f=0.80이 곧 현행")
    print("     동치 눈금이다. **`embed`의 0-원자는 0.0%다** — 연속 분포에는 현행 동치")
    print("     눈금이 없고 현행 기본값도 아니다. 거기서 f=0.80은 **셋 중 가장 느슨한")
    print("     점**일 뿐이다 (레인 D 검증자 F2).")
    print("  ⚠️ 그리고 **같은 f가 두 모드에서 다른 실험이다** (F28-b) — 모드 간 recall")
    print("     비교는 위 `실제 컷` 열을 나란히 놓고서만 읽는다 (G15 rev2).")

    # ── 1단 18셀 ────────────────────────────────────────────────────────
    base_theta = dict(M.THETA_BY_MODE)
    stage1, idx = [], 0
    for gate in GATES:
        for mode in MODES:
            for th, f, cut in ladder[mode]:
                idx += 1
                stage1.append(Cell(idx, 1, gate, mode, f, th, cut, 0.6, 0.4, 0.1))

    snap = snapshot_globals()
    skip = False
    try:
        for c in stage1:
            sup = Supplier(cache, force="none")
            apply_cell(c, base_theta, sup)
            guard_theta(c)
            c.tot = run_cell(env, c, sup)
            if sup.failed or c.tot["degraded"]:
                c.dropped = (c.tot["degraded"] if c.tot else 0) or "공급자 실패"
                c.tot, c.note, skip = None, "측정 안 됨 (강등 발생 — 하니스 규약)", True
            else:
                c.ok = True
            restore_globals(snap)
            assert_restored(snap, f"1단 셀 {c.idx} {c.name}")
    finally:
        restore_globals(snap)
    assert_restored(snap, "1단 종료")

    table_a(stage1, "1단 18셀 — 게이트 2 × 모드 3 × θ 3 (전량 출력 · 결정 C 방어 2)")
    table_b(stage1, "1단 18셀 — 나머지 관측")

    # ── 기준칸 대조 — 여기가 안 맞으면 즉시 중단한다 ────────────────────
    base = next(c for c in stage1 if c.gate[0] == "G3" and c.mode == "lexical"
                and c.f == LADDER[0])
    print("\n" + "-" * W)
    print("기준칸 대조 — 스윕이 프로덕션과 같은 것을 재고 있는가")
    hr()
    if base.tot is None:
        raise SystemExit("🔴 기준칸이 측정 안 됨 — 스윕이 성립하지 않는다.")
    bt = base.tot
    got = dict(recall=(bt["ev_hit"], bt["ev_tot"]), mis=bt["mis"],
               pooled=(bt["mis"], bt["ret"]), top1=(bt["top1"], bt["top1_n"]),
               ties=len(bt["ties"]))
    for k, want in BASE_EXPECT.items():
        ok = got[k] == want
        print(f"  {k:<10}기대 {str(want):<12}실측 {str(got[k]):<12}"
              f"{'PASS' if ok else '🔴 FAIL':>10}")
    if got != BASE_EXPECT:
        raise SystemExit(
            f"🔴 기준칸이 `precision-4cells.txt`의 `G3 · θ=0.05`"
            f"(컷 90.7% / {P_N}쌍 · 서명 {P_SIG}) 셀과 다르다 — "
            f"스윕이 프로덕션과 **다른 것**을 재고 있다. 즉시 중단.")
    print(f"  → 기준칸 {base.name}이 현행 θ=0.05(컷 90.7% / {P_N}쌍 · "
          f"서명 {P_SIG}) 셀과 일치한다 — 같은 35쌍을 통과시킨다 (F27).")
    print(f"     격자의 나머지는 이 칸에서 읽는다.")

    # ── 파레토 전선 ─────────────────────────────────────────────────────
    live = [c for c in stage1 if c.tot is not None]
    front = pareto_front(live)
    # 🆕 3차 키가 **규칙에 있다** (규칙 ⑤ · `select_key`). 여기 있던 것은 두 키뿐이었고
    #    세 번째 자리는 `pareto_front`의 반환 순서와 `sort`의 안정성이 채우고 있었다.
    front.sort(key=select_key)
    print("\n" + "=" * W)
    print("1단 선택 — **실행 전에 고정된 파레토 규칙**으로만 이뤄졌다 (결정 C 방어 1)")
    print("=" * W)
    print("  규칙 (계획 §단계 4에 실행 전 고정 · 실행 중에 바꾸지 않았다):")
    print("    ① 파레토 전선 = `evidence_recall` 최대 / `misinjection@q` 최소의 비지배 집합")
    print("    ② 전선 ≤ 3개 → 전부 2단으로   ③ ≥ 4개 → recall 상위 3개(**전선 전체 출력**)")
    print("    ④ 전선 = 1개 → 격자의 가장 개방적인 모서리인지 확인하고 2단을 돌리지 않는다")
    print("  🆕 ⑤ **동점 조항** (이 라운드가 채웠다 — ADR-015 미해결 «격자 규칙의 동점 조항»):")
    print(f"       ③의 상위 {SELECT_CAP}개를 취할 때 두 선택 키가 **모두 같은 셀들**(동점군)이")
    print(f"       절단선을 가로지르면, 3차 키로 **격자 인덱스 오름차순**을 쓴다. 인덱스는")
    print("       사전 등록된 축 열거 순서(`GATES` → `MODES` → `LADDER`)의 함수라 **실행")
    print("       결과를 안 보고 계획 문서만으로 계산된다.** 조항은 2단의 크기를 바꾸지")
    print("       않고(상한 30셀 유지) 우열을 주장하지도 않는다 — 발화하면 동점군 전체와")
    print("       탈락 셀을 이름으로 찍는다.")
    print("       🔴 **없던 조항을 채운 것이지 있던 규칙을 고친 것이 아니다.** 3차 키는")
    print("          여태 `pareto_front`의 반환 순서 + `sort`의 안정성이 채우고 있었고,")
    print("          둘 다 계획에 없는 **구현 사실**이다 (후속 10이 `retrieve()`에서 없앤 것과")
    print("          같은 종류의 의존). 그래서 오늘의 선택은 한 자리도 안 바뀐다.")
    print(f"\n  **전선 전체 ({len(front)}개)** — 상위 3개만이 아니라 전부 찍는다")
    print(f"    {'#':>3} {'셀':<28}{'recall':>9}{'mis@q':>8}{'실제 컷':>10}"
          f"{'pooled(분모)':>16}")
    for c in front:
        t = c.tot
        pooled = ("정의 안 됨" if t["pooled"] is None
                  else f"{t['pooled']:.3f}({t['ret']})")
        print(f"    {c.idx:>3} {c.name:<28}{f'{t['ev_hit']}/{t['ev_tot']}':>9}"
              f"{t['mis']:>8}{c.cut:>9.1%}{pooled:>16}")

    stage2 = []
    picked = front[:SELECT_CAP] if len(front) > 1 else []
    span = report_tie_clause(front, picked)
    tie_clause_check(front, span)
    if len(front) == 1:
        c = front[0]
        # 부검 시나리오 1 징후 ① — 전선이 하나면 그것이 격자의 **가장 개방적인
        # 모서리**인지 본다. 개방성은 두 축에서 관측된다: 게이트 통과 수가 최대이고
        # θ 눈금이 가장 느슨한(f 최소) 칸.
        open_gate = max(live, key=lambda x: x.tot["gate_pass"]).gate[0]
        corner = (c.gate[0] == open_gate and c.f == min(LADDER))
        print(f"\n  🔴 **전선이 1개다.** 규칙 ④에 따라 **2단을 돌리지 않는다.**")
        print(f"     이 셀이 격자의 가장 개방적인 모서리인가: "
              f"{'예' if corner else '아니오'} "
              f"(가장 열린 게이트 {open_gate} · 가장 느슨한 눈금 f={min(LADDER)})")
        if corner:
            print("     → **부검 시나리오 1의 징후 ①이다** — 격자가 '더 열수록 좋다'만 "
                  "말하고 있고,")
            print("        무릎이 격자 밖에 있다는 뜻이다. 그 사실을 결과로 보고한다.")
    else:
        # ⚠️ 이 줄의 서식은 **그대로 둔다.** 조항이 더한 것은 전부 새 줄이고, 기존
        #    줄이 한 글자도 안 움직여야 기준선 대조가 조항의 무해함을 실제로 잰다.
        print(f"\n  → 2단으로 올릴 셀 {len(picked)}개: "
              f"{', '.join(c.name for c in picked)}"
              + ("  (전선 ≤ 3 — 전부)" if len(front) <= SELECT_CAP
                 else "  (전선 ≥ 4 — recall 내림차순 상위 3, 전선 전체는 위에 있다)"))
        idx = 18
        for c in picked:
            for wr, wi in STAGE2_WEIGHTS:
                for pen in STAGE2_PENALTY:
                    idx += 1
                    stage2.append(Cell(idx, 2, c.gate, c.mode, c.f, c.theta,
                                       c.cut, wr, wi, pen))
        snap2 = snapshot_globals()
        try:
            for c in stage2:
                sup = Supplier(cache, force="none")
                apply_cell(c, base_theta, sup)
                guard_theta(c)
                c.tot = run_cell(env, c, sup)
                if sup.failed or c.tot["degraded"]:
                    c.dropped = (c.tot["degraded"] if c.tot else 0) or "공급자 실패"
                    c.tot, c.note = None, "측정 안 됨 (강등 발생 — 하니스 규약)"
                    skip = True
                else:
                    c.ok = True
                restore_globals(snap2)
                assert_restored(snap2, f"2단 셀 {c.idx} {c.name}")
        finally:
            restore_globals(snap2)
        assert_restored(snap2, "2단 종료")

        table_a(stage2, "2단 12셀 — 전선 3셀 × (W_REL,W_IMP) 2 × SURFACED_PENALTY 2")
        table_b(stage2, "2단 12셀 — 나머지 관측")
        print("\n  🔴 **2단의 `top1`은 보고 전용이고 선택에 쓰지 않는다** (F26 rev2).")
        print("     가중치와 페널티를 바꾸면 동점이 **체계적 방향으로** 깨진다 — 그래서")
        print("     2단의 `top1` 변화는 순위 개선인지 동점 해소 인공물인지 구별할 수 없다.")
        print("  🔴 **2단은 승격 권한이 없다** (결정 C 방어 3). 출력은 권고이고, 기본값")
        print("     변경은 단계 5의 3조건 + 선행 조건을 별도로 통과해야 한다.")
        # 2단의 (0.6,0.4)·pen=0.1 칸은 1단 셀과 **같은 구성**이다. 값이 다르면
        # 스윕의 재바인딩이 셀 사이로 새고 있다는 뜻이다 — 조용히 지나가지 않는다.
        for c in stage2:
            if (c.w_rel, c.w_imp, c.pen) == (0.6, 0.4, 0.1) and c.tot:
                src = next(s for s in picked if s.name == c.name)
                if (c.tot["ev_hit"], c.tot["mis"], c.tot["ret"]) != \
                        (src.tot["ev_hit"], src.tot["mis"], src.tot["ret"]):
                    raise SystemExit(
                        f"🔴 2단 셀 {c.idx}가 같은 구성의 1단 셀 {src.idx}와 다른 "
                        f"값을 냈다 — 전역이 셀 사이로 샜다.")
        print("\n  ✅ 2단의 (0.6,0.4)·pen=0.1 칸 3개가 같은 구성의 1단 셀과 일치한다 "
              "— 셀 간 누수 없음.")

    allcells = stage1 + stage2
    tie_detail(allcells)

    # ── 지연 프로파일 ───────────────────────────────────────────────────
    print("\n" + "=" * W)
    print("`build_context` 지연 — 콜드 / 준-콜드 / 웜 (단계 4 (d)의 정의 표)")
    print("=" * W)
    print(f"  게이트 G3(프로덕션) · 각 모드의 f=0.80 눈금 · "
          f"채점 18문항 × {COND3_REPEATS}회 = **n={18 * COND3_REPEATS}**")
    print("  🔴 **승격 조건 3이 읽는 것은 콜드 p95다.**")
    lat = {}
    for mode in MODES:
        lat[mode] = latency_profile(env, base_theta, ladder, cache,
                                    GATES[0], mode)
    print(f"\n  {'모드':<16}{'체제':<10}{'min':>9}{'p50':>9}{'p90':>9}"
          f"{'p95(ms)':>10}{'max':>10}{'n':>6}{'검색호출':>9}{'요청':>6}"
          f"{'텍스트':>8}{'지연계산':>9}   비고")
    hr()
    for mode in MODES:
        for label, r in lat[mode].items():
            if mode != "embed":
                note = "임베딩 없음 — 세 체제가 동일하다"
            elif label == "콜드":
                note = "🔴 조건 3이 읽는 행 (첫 조회만 백필 · 이후 질의 1건)"
            elif label == "준-콜드":
                note = "배선 뒤 프로덕션의 정상 상태"
            else:
                note = "캐시 전량 히트"
            print(f"  {mode:<16}{label:<10}{r['lo']:>9.2f}{r['p50']:>9.2f}"
                  f"{r['p90']:>9.2f}{r['p95']:>10.2f}{r['hi']:>10.2f}{r['n']:>6}"
                  f"{r['calls']:>9}{r['requests']:>6}{r['texts']:>8}"
                  f"{r['lazy']:>9}   {note}")
    n = 18 * COND3_REPEATS
    print(f"\n  🆕 **조건 3의 표본을 {n}으로 키웠다** (레인 G · 계획 §단계 5는 n을 적어 "
          f"두지 않았다).")
    print(f"     `soak.pct`의 p95는 `v[min(n-1, int(n*0.95))]`이다. **n=18에서 그것은 "
          f"`v[17]` = 표본의")
    print(f"     최댓값**이었고, 그래서 조건 3은 분위수가 아니라 극값을 읽으면서 실행마다 "
          f"갈렸다")
    print(f"     (PASS 11 / FAIL 13 · n=24 draw · `after-r2b/cond3-draws.txt`). "
          f"**n={n}에서는 `v[{min(n - 1, int(n * 0.95))}]`이고**")
    print(f"     위로 {n - 1 - min(n - 1, int(n * 0.95))}개가 남는다 — 단발 이상치 "
          f"하나가 판정을 뒤집지 못한다.")
    print("     ⚠️ **조건을 약화한 것이 아니다.** 읽는 통계량은 여전히 p95이고, "
          "바뀐 것은 표본 크기뿐이다.")
    print("     ⚠️ 어휘 두 모드에도 수백 ms짜리 최댓값이 나오는 실행이 있다. "
          "그 모드에는 임베딩이")
    print("        **한 건도 없으므로** 그것은 검색 비용이 아니라 기기 잡음이고, "
          "바로 그 잡음이")
    print("        n=18의 p95를 정하고 있었다.")

    # 🆕 원본 draw 전량 — `cond3-draws.txt`가 파일로 하던 것을 출력이 한다.
    #    "분포를 기록했다"는 주장은 분포가 출력에 있을 때만 검사 가능하다 (G11).
    cold = lat["embed"].get("콜드")
    if cold:
        print(f"\n  원본 draw 전량 (embed · 콜드 · n={cold['n']} · ms, "
              f"관측 순서 — 첫 값이 백필이다):")
        d = cold["draws"]
        for i in range(0, len(d), 12):
            print("    " + " ".join(f"{v:7.1f}" for v in d[i:i + 12]))
        srt = sorted(d)
        print(f"    분포: min {srt[0]:.1f} · p50 {pct(d, 50):.1f} · "
              f"p90 {pct(d, 90):.1f} · p95 {pct(d, 95):.1f} · max {srt[-1]:.1f} "
              f"· n {len(d)}")
        over = [v for v in d if v > TTFT_BUDGET[1]]
        print(f"    예산 상한({TTFT_BUDGET[1]} ms) 초과 draw: {len(over)}/{len(d)} "
              f"({len(over) / len(d):.1%})"
              + (f" — 최대 {max(over):.1f} ms" if over else ""))

    imports, calls = RD.wiring_status()
    print(f"\n  배선 상태 (`prototype/memory.py` — 지금 다시 셌다): "
          f"`import embedding` {imports}건 · `db_put_vec`/`db_get_vec` 호출부 {calls}건")
    if imports == 0 or calls == 0:
        print("  🔴 문서 벡터가 배선돼 있지 않다 — 그래서 콜드가 **오늘의 값**이고 "
              "준-콜드는 아직 없는 시스템의 값이다.")
        print("     두 행의 차이가 곧 **후속 9가 벌어야 하는 것**이다. "
              "이것은 검색 품질의 문제가 아니라 배선의 문제다.")
    else:
        print("  🟢 **배선돼 있다** (후속 9-b · 레인 G). 그래서 위 표의 콜드 행은 "
              "이제 **조회당 색인 전량**이")
        print("     아니라 **첫 조회 1회의 백필 + 이후 질의 1건**을 잰다. "
              "콜드와 준-콜드가 수렴하는 것이 배선의 증거다.")
        print("     ⚠️ **`지연계산` 열이 그 백필의 횟수다.** 0이 아니면 쓰기 경로의 "
              "사전계산이 그 행을 안 채웠다는 뜻이고,")
        print("        이 하니스에서 그것은 정상이다 — `soak.ingest`가 "
              "`add_event`를 거치지 않고 `INSERT INTO event`를 직접 친다.")
        print("        **즉 격자는 지연 재계산 경로를 재고, 쓰기 경로 사전계산은 "
              "`prototype/tests/test_tokens.py`의 `TestVectorWiring`이 잰다.**")

    # ── 단계 5 판정 ─────────────────────────────────────────────────────
    verdict(allcells, base, lat, front)
    hybrid_reentry(env, stage1)

    # ── 마감 ────────────────────────────────────────────────────────────
    measured = sum(1 for c in allcells if c.tot is not None)
    # 🔴 측정된 셀의 강등 건수와, **강등 때문에 버려진 셀 수**를 따로 센다.
    #    합쳐 적으면 "degraded 0인데 6셀이 측정 안 됨"이라는 모순된 요약이 나온다.
    deg = sum(c.tot["degraded"] for c in allcells if c.tot)
    dropped = [c for c in allcells if c.tot is None]
    stale = sum(c.tot["stale"] for c in allcells if c.tot)
    wall = time.perf_counter() - t_start
    print("\n" + "=" * W)
    print(f"완주 — 셀 {measured}/{len(allcells)} 측정 · 측정된 셀의 degraded "
          f"{deg} · 강등으로 버린 셀 {len(dropped)} · stale_theta {stale} · "
          f"벽시계 {wall:.1f}초")
    print("=" * W)
    if skip or measured != len(allcells):
        print("🔴 선언한 모드를 돌리지 못한 셀이 있다 — **강등하지 않고 77로 끝낸다.**")
        return 77
    return 0


if __name__ == "__main__":
    sys.exit(main())
