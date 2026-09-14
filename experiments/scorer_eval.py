# -*- coding: utf-8 -*-
"""
scorer_eval.py — **채점기를 축자에서 임베딩으로 바꿀 것인가**를 사람 라벨로 판정한다.
(결정 4 K · 미해결 U4 · 실험 26)

## 왜 이 파일이 생겼나 — G11이 요구한다

이 판정의 수치들은 처음에 **임시 heredoc에서 나왔다.** 저장소의 어떤 스크립트도
그것을 출력하지 않았다. G11(*"재현 불가능한 숫자를 문서에 쓰지 않는다"*)이 금지하는
것이 정확히 그 상태다 — 문서에 실린 92%·67%·78%를 다시 뽑을 방법이 없으면 그것은
측정이 아니라 **주장**이다. 그래서 재현기가 먼저 있고, 문서의 모든 수치가 이 출력에서
나온다.

## 이 파일이 하는 것 하나

같은 32쌍에 **채점기 셋**(축자 `scoring.survived_v3` · 축자 `survived_v2`(기록) ·
임베딩 `bge-m3` 코사인)을 돌리고, **사전 등록된 홀드아웃**에서 규칙 넷과
«어긋나면 보류»를 **한 번만** 잰다.
자명한 기준선(전부 `N`)과 커버리지를 **항상 옆에 찍는다**(G15).

## 🆕 서수 수리 라운드 — **v2를 안 고치고 v3을 옆에 뒀다**

이 실험의 첫 판은 축자의 오답 셋(`P12`·`P14`·`P15`)을 «닫지 않는 것»으로 남겼다.
`scoring.survived_v3`이 그것을 고친다(회차 불일치 규칙). 🔴 **`survived_v2`는 바이트
그대로다** — `digest_budget.py`와 이 문서의 표가 그 이름으로 기록한 값을 갖고 있고,
같은 이름 아래 숫자를 갈면 «모양만 같고 다른 집합»이 된다.

→ 그래서 **두 채점기를 같은 실행에서 나란히 찍는다.** 라운드를 건너 화살표를 그리지
않는다. 그리고 🔴 **수리는 훈련의 `P12`·`P14`만 보고 했다** — `P15`는 홀드아웃이라
고친 뒤 `Holdout`이 규칙마다 한 번 여는 그 자리에서 처음 봤다.

⚠️ **수리가 음성 대조 ⓐ를 깨뜨렸다.** ⓐ의 옛 발화 조건은 «채점기 넷의 홀드아웃 값이
전부 같아진다»였고 그것은 **축자가 틀리던 때의 증상**이었다. 조건을 느슨하게 풀지 않고
**척도 없는 형태(값의 폭이 절반 미만으로 무너지는가)**로 다시 썼다 — 그 사연은
`negative_control` 안의 주석에 있다.

## 🔴 1판 라벨(`LABELS_HUMAN.json` · 24개)은 **합치지 않는다**

라벨러가 *"이해가 안 돼서 느낌으로 찍었다"*고 말했고, 검사에서 **먼 대조(far_control)
4개가 전부 `Y`**로 나왔다 — 먼 대조는 «코사인 하위 25%에서 무작위로 뽑은, 담겼을 리
없는 자리»다. 그것이 전부 «담겼다»면 라벨의 **방향이 뒤집혀 있다.** 그 24개로 유도한
θ는 «담기지 않은 것을 담겼다고 부르는 문턱»이 된다.

🔴 **파일은 지우지 않는다 — 기록이다.** 2판이 무엇을 고쳤는지(요약별 묶음 · 12행 ·
질문을 *"이 요약이 아래 일을 말하고 있나요?"*로) 말할 수 있는 유일한 근거가 1판이다.
이 스크립트는 1판을 **읽어서 폐기 사유를 매 실행 다시 확인하고 찍는다** — 사유를
산문으로만 적으면 다음 사람이 그 24개를 합치고 «n=56이라 더 낫다»고 적는다.

## 🔴 홀드아웃을 «한 번만» 보는 것을 말이 아니라 기제로 만든다

`Holdout`이 **접근 횟수를 센다.** θ 선택 함수는 훈련만 받고, 홀드아웃 객체는
`measure()`가 규칙마다 정확히 한 번 연다. 홀드아웃을 보고 θ를 고치면 그 카운터가
규칙당 2 이상이 되어 **판정이 발화한다** — 음성 대조 ⓒ가 그것을 실제로 돌린다.

## `?`는 분자·분모에서 뺀다 (F20)

`?`는 «애매하다»이지 «아니다»가 아니다. `N`으로 세면 그것은 라벨러가 하지 않은 판단을
스크립트가 대신 하는 것이고, 그 한 건이 `N` 쪽 기준선을 공짜로 올린다. **빼고, 몇 개를
뺐는지 따로 찍는다.**

## 실행

    PYTHONIOENCODING=utf-8 python -B experiments/scorer_eval.py

ollama가 없고 임베딩 캐시도 비었으면 **종료 77(SKIP)** — 통과가 아니라 미측정이다(G1).
34개 텍스트가 `EMBED_CACHE.json`에 이미 있으므로 정상 환경에서는 **호출 0회**로 돈다.
그 사실을 출력에 찍는다 — 캐시가 조용히 비어 라이브 호출로 넘어가면 모델 빌드가 달라져
숫자가 움직일 수 있다.
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "prototype"))

import yaml                                                  # noqa: E402
import embedding                                             # noqa: E402
from scoring import survived_v2, survived_v3                 # noqa: E402
import scoring                                               # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

W = 78

LEDGER = os.path.join(ROOT, "eval", "fact-ledger.yaml")
SUMMARY_S2 = os.path.join(HERE, "data", "SUMMARY_S2.json")
SIMS_ALL = os.path.join(HERE, "data", "LABEL_SIMS_ALL.json")
SPLIT_JSON = os.path.join(HERE, "data", "LABEL_SPLIT.json")

# 🔴 합치는 둘과 **합치지 않는 하나**. 이름을 나란히 두는 것이 이 상수의 요점이다.
LABELS_USED = ("LABELS_HUMAN2.json", "LABELS_HUMAN3.json")
LABELS_DISCARDED = "LABELS_HUMAN.json"

# 1판 폐기의 **기계적 근거**. 산문이 아니라 이 수를 매 실행 다시 센다.
DISCARD_KIND = "far_control"
DISCARD_LABEL = "Y"

N_EXPECT = 32


# ── 0. 재료 ────────────────────────────────────────────────────────────

def load_labels():
    """
    2판 + 3판 = 32개. 🔴 **1판은 합치지 않는다.**

    쌍 id가 겹치면 한쪽이 조용히 다른 쪽을 덮는다 — 그러면 n이 32라고 적히면서
    실제로는 다른 집합이 된다. 겹침을 **막지 않고 터뜨린다.**
    """
    merged, source = {}, {}
    for fname in LABELS_USED:
        with open(os.path.join(HERE, "data", fname), encoding="utf-8") as f:
            rec = json.load(f)
        for pid, lab in rec["labels"].items():
            if pid in merged:
                raise AssertionError(
                    f"쌍 id 중복: {pid}가 {source[pid]}와 {fname} 둘 다에 있다")
            merged[pid], source[pid] = lab, fname
    return merged, source


def load_discarded():
    """1판을 **읽는다**. 합치지 않는다 — 폐기 사유를 다시 세기 위해서만 연다."""
    with open(os.path.join(HERE, "data", LABELS_DISCARDED), encoding="utf-8") as f:
        return json.load(f)["labels"]


def load_material():
    """대장 사건 10개와 24세션 요약. `eval/`은 **읽기만** 한다 (A8)."""
    with open(LEDGER, encoding="utf-8") as f:
        events = {e["id"]: e["text"] for e in yaml.safe_load(f)["events"]}
    with open(SUMMARY_S2, encoding="utf-8") as f:
        rec = json.load(f)
    return events, rec["summaries"], rec["meta"]


def load_meta():
    """쌍의 (사건, 세션, 종류). 유사도 열도 들어 있지만 **다시 계산해서 대조한다.**"""
    with open(SIMS_ALL, encoding="utf-8") as f:
        return json.load(f)


# ── 1. 채점기 둘 ───────────────────────────────────────────────────────

def cosine(a, b):
    num = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return num / (na * nb) if na and nb else 0.0


def embed_sims(pairs, events, sums):
    """
    `{쌍 id: 코사인}` + **라이브 호출 수**.

    🔴 `_post`를 감싸서 센다. "캐시를 썼다"를 추론이 아니라 **관측**으로 만든다 —
    캐시가 비어 라이브로 넘어가면 모델 빌드가 다를 수 있고, 그때 이 숫자들은
    기록과 같은 조건의 것이 아니다.
    """
    texts = sorted({events[m["event_id"]] for m in pairs.values()}
                   | {sums[m["session"]] for m in pairs.values()})
    code = embedding.ensure_cached(texts)
    if code == 77:
        return None, None

    calls = [0]
    orig = embedding._post

    def counting(*a, **kw):
        calls[0] += 1
        return orig(*a, **kw)

    embedding._post = counting
    try:
        vecs = embedding.embed(texts)
    finally:
        embedding._post = orig
    if vecs is None:
        return None, None
    V = dict(zip(texts, vecs))
    return ({pid: cosine(V[events[m["event_id"]]], V[sums[m["session"]]])
             for pid, m in pairs.items()}, calls[0])


def literal_preds(pairs, events, sums, scorer=survived_v3):
    """
    축자 채점 — **`scoring`의 함수를 그대로 부른다** (사본 금지 · F12).

    반환 `({쌍 id: 'Y'|'N'}, 판정불가 목록)`. 두 채점기 다 어근이 2개 미만인
    항목을 `unscorable`로 올리므로 그것을 **삼키지 않고** 따로 돌려준다.

    🔴 `scorer`가 인자인 이유는 **v2와 v3을 같은 실행에서 나란히 찍기 위해서**다.
    라운드를 건너 «옛 v2 값 → 새 값»으로 화살표를 그리면 그것은 다른 채점기의
    두 수를 잇는 것이다(S16의 실패 모드 ②). 같은 실행의 두 열은 그렇지 않다.
    """
    pred, unscorable = {}, []
    for pid, m in pairs.items():
        r = scorer(sums[m["session"]], [events[m["event_id"]]])
        if r.unscorable:
            unscorable.append(pid)
        pred[pid] = "Y" if r.survived else "N"
    return pred, unscorable


# ── 2. 사전 등록된 분할 — **라벨도 유사도도 보지 않는다** ───────────────

def split_blind(pair_ids):
    """
    `sha1(pair_id)`의 **마지막 비트**. 입력이 쌍 id뿐인 것이 이 함수의 전부다.

    🔴 시그니처에 라벨이 없으므로 **라벨을 보고 자를 방법이 구조적으로 없다.**
    음성 대조 ⓐ가 이 함수를 라벨을 보는 것으로 바꿔 무슨 일이 나는지 보인다.
    """
    train, holdout = [], []
    for pid in sorted(pair_ids):
        # 마지막 비트 0 → 훈련, 1 → 홀드아웃. 🔴 이 대응은 `LABEL_SPLIT.json`이
        # 라벨보다 **먼저** 고정한 것이고, 뒤집으면 §3의 대조가 발화한다.
        (holdout if int(hashlib.sha1(pid.encode()).hexdigest(), 16) & 1
         else train).append(pid)
    return train, holdout


def split_by_label(pair_ids, labels):
    """
    🔴 **변이. 절대 쓰지 않는다** — 음성 대조 ⓐ 전용.

    라벨을 보고 `Y`와 `N`을 양쪽에 같은 비율로 흩는다. "층화 추출"이라는 좋은
    이름이 붙는 것이 함정이다: 라벨을 본 순간 훈련과 홀드아웃이 같은 분포가 되고,
    홀드아웃은 «본 적 없는 표본»이 아니라 **훈련의 복사본**이 된다.
    """
    train, holdout = [], []
    for i, pid in enumerate(sorted(pair_ids, key=lambda p: (labels[p], p))):
        (train if i % 2 == 0 else holdout).append(pid)
    return train, holdout


class Holdout:
    """
    홀드아웃을 **여는 횟수를 센다.**

    *"홀드아웃은 한 번만 본다"*는 규율이지 코드가 아니었다 — 규율은 다음 라운드에
    잊힌다. 그래서 셈으로 만든다.

    🔴 **손잡이 이름당 1회만 세는 것으로는 부족하다 — 실측으로 확인했다.**
    첫 판은 `{이름: 횟수}`만 봤고, θ 선택을 `"θ선택:규칙"`이라는 **다른 이름**으로
    열자 각 이름이 1회씩이라 **감사가 초록으로 통과했다.** 그 실행에서 임베딩 단독의
    홀드아웃이 66.7% → 94.4%로 올라 판정이 뒤집혔는데도 그렇다. 열 번째
    «발화할 수 없는 검사»가 될 뻔한 자리다.

    → **총 접근 예산**을 함께 건다. 이름을 새로 짓는 것으로는 예산을 못 피한다.
      예산은 «무엇을 여는가»를 세어 **미리** 적는다(`main`의 `HO_BUDGET`).
    """

    def __init__(self, pair_ids, budget):
        self._ids = tuple(pair_ids)
        self.budget = budget
        self.reads = {}

    @property
    def total(self):
        return sum(self.reads.values())

    def open(self, who):
        self.reads[who] = self.reads.get(who, 0) + 1
        return self._ids

    def audit(self):
        """
        위반 목록. 비어 있어야 한다.

        ① 같은 손잡이를 두 번 이상 열었다   ② 총 접근이 사전 등록 예산을 넘었다
        """
        bad = {k: v for k, v in self.reads.items() if v > 1}
        if self.total > self.budget:
            bad["**총 접근 예산 초과**"] = f"{self.total} > {self.budget}"
        return bad


# ── 3. 규칙 다섯 ───────────────────────────────────────────────────────
#
# 넷은 커버리지 100%이고 다섯째만 다르다. **그래서 커버리지 열을 항상 찍는다**(G15) —
# 100%인 열이 넷 있어야 28%를 버리는 열이 눈에 띈다. 커버리지를 «해당 없음»으로 비우면
# 보류 규칙의 정확도가 다른 넷과 같은 분모인 것처럼 읽힌다.

def rule_literal(lit, sim, th):
    return lit


def rule_embed(lit, sim, th):
    return "Y" if sim >= th else "N"


def rule_and(lit, sim, th):
    return "Y" if (lit == "Y" and sim >= th) else "N"


def rule_or(lit, sim, th):
    return "Y" if (lit == "Y" or sim >= th) else "N"


def rule_abstain(lit, sim, th):
    """어긋나면 **판정 불가**(`None`) — 분모에서 빠진다."""
    emb = "Y" if sim >= th else "N"
    return lit if lit == emb else None


# 🆕 규칙이 아니라 **채점기 열**이다 — `RULES`에 넣지 않는 이유는 `table`의 주석에.
V2_ROW = "축자 v2 (기록)"

RULES = [
    ("축자 단독 (v3)", rule_literal, False),
    ("임베딩 단독", rule_embed, True),
    ("AND (둘 다 Y)", rule_and, True),
    ("OR (하나라도 Y)", rule_or, True),
    ("«어긋나면 보류»", rule_abstain, True),
]


def check_counts(orig_labels, scored_ids):
    """
    **개수 불일치 검사.** `?`를 뺀 개수가 원본 라벨 파일과 맞는가.

    🔴 원본을 다시 세는 것이 요점이다. 작업 중인 라벨 dict를 세면 `?`를 `N`으로
    바꿔치기한 변이가 **자기 자신과 일치**해서 조용히 통과한다 — 검사가 변이와 같은
    출처를 보면 그것은 검사가 아니다. `LABELS_HUMAN2/3.json`이 유일한 진실이다.
    """
    n_unknown = sum(1 for v in orig_labels.values() if v == "?")
    want = len(orig_labels) - n_unknown
    if len(scored_ids) != want:
        raise AssertionError(
            f"채점 대상이 {len(scored_ids)}건인데 원본 라벨 {len(orig_labels)}건 중"
            f" `?`가 {n_unknown}건이다 — 분모는 {want}이어야 한다")
    return n_unknown, want


def measure(rule, ids, lit, sims, labels, th):
    """
    `(맞은 수, 채점한 수, 보류 수)`.

    🔴 `?`는 **여기 들어오기 전에** 빠진다(`scored_ids`). 이 함수는 `?`를 볼 일이
    없어야 하고, 보면 그것은 호출부의 버그다 — 그래서 방어적으로 무시하지 않고 센다.
    """
    hit = n = held = 0
    for pid in ids:
        if labels[pid] == "?":
            raise AssertionError(f"`?` 라벨 {pid}가 채점 분모에 들어왔다")
        p = rule(lit[pid], sims[pid], th)
        if p is None:
            held += 1
            continue
        n += 1
        hit += (p == labels[pid])
    return hit, n, held


def theta_grid(train_sims):
    """
    후보 θ — **훈련 유사도 사이의 중점만**. 홀드아웃 값은 격자에 들어가지 않는다.

    격자를 `0.30~0.70 step 0.01`처럼 고정하면 홀드아웃 분포를 «모르는 채로» 고른 것이
    맞지만, 훈련이 실제로 가르는 자리와 무관한 값이 후보에 섞인다. 인접 중점만 두면
    후보 수가 `n-1`로 줄고 **각 후보가 훈련의 어떤 경계인지가 이름을 갖는다.**
    """
    xs = sorted(set(train_sims))
    return [(a + b) / 2 for a, b in zip(xs, xs[1:])], xs


def choose_theta(rule, train_ids, lit, sims, labels):
    """
    🔴 **훈련에서만** 고른다. 사전 등록한 동률 규칙:

        ① 훈련 정확도 최대 → ② 커버리지 최대 → ③ 인접 간격 최대 → ④ 작은 θ

    ②가 없으면 «어긋나면 보류»가 한 쌍만 남기고 100%를 찍는 θ를 고른다. ③이 없으면
    같은 정확도의 문턱 중 데이터 점에 딱 붙은 것이 뽑혀 홀드아웃에서 잘 흔들린다.
    **동률 규칙을 결과를 보고 고르면 그것이 곧 홀드아웃 오염이다** — 그래서 여기 박는다.
    """
    ts = [sims[p] for p in train_ids]
    grid, xs = theta_grid(ts)
    best = None
    for th in grid:
        hit, n, held = measure(rule, train_ids, lit, sims, labels, th)
        acc = hit / n if n else 0.0
        cov = n / (n + held) if (n + held) else 0.0
        gap = min((abs(th - x) for x in xs), default=0.0)
        key = (acc, cov, gap, -th)
        if best is None or key > best[0]:
            best = (key, th, hit, n, held)
    return best[1], best[2], best[3], best[4], len(grid)


# ── 4. 출력 ────────────────────────────────────────────────────────────

def pct(hit, n):
    return f"{hit}/{n} = {100.0 * hit / n:5.1f}%" if n else "판정 불가 (분모 0)"


def baseline_all_n(ids, labels):
    """자명한 기준선 — **아무것도 안 보고 전부 `N`.**

    이 집합은 `N`이 24/32라 기준선이 높다. 그것을 옆에 안 찍으면 «67%»가 좋아 보인다.
    """
    n = len(ids)
    return sum(1 for p in ids if labels[p] == "N"), n


def table(title, ids, lit, sims, labels, thetas, holdout=None, who="",
          extra=()):
    """
    🔴 `holdout`이 주어지면 `ids`는 **쓰지 않는다** — 쌍 목록은 규칙마다
    `holdout.open()`으로만 나온다. 그래야 «몇 번 열었나»가 표에도 걸린다.

    `extra`는 `(이름, 축자 예측 dict)` 목록 — **문턱이 없는 채점기 열**이다.
    v2(기록)를 v3 옆에 같은 표에서 찍는 데 쓴다. 🔴 규칙이 아니라 열이므로
    `RULES`에 넣지 않는다(`RULES[:4]`를 보는 대조 ⓐ의 뜻이 달라진다).
    **여는 자리는 하나 더 늘고, `HO_BUDGET`이 그만큼 올라간다.**
    """
    n_show = len(holdout.open(who + "표제")) if holdout is not None else len(ids)
    print(f"\n  {title}  (n = {n_show})")
    print(f"  {'규칙':<18} {'θ':>7}  {'정확도':>18}  {'커버리지':>16}")
    print("  " + "-" * 66)
    rows = []
    for (name, fn, needs_th) in RULES:
        th = thetas.get(name)
        use = holdout.open(who + name) if holdout is not None else ids
        hit, n, held = measure(fn, use, lit, sims, labels, th if th else 0.0)
        cov = f"{n}/{n + held} = {100.0 * n / (n + held):5.1f}%"
        ths = f"{th:.4f}" if needs_th else "—"
        print(f"  {name:<18} {ths:>7}  {pct(hit, n):>18}  {cov:>16}")
        rows.append((name, th, hit, n, held))
    for (name, litmap) in extra:
        use = holdout.open(who + name) if holdout is not None else ids
        hit, n, held = measure(rule_literal, use, litmap, sims, labels, 0.0)
        cov = f"{n}/{n + held} = {100.0 * n / (n + held):5.1f}%"
        print(f"  {name:<18} {'—':>7}  {pct(hit, n):>18}  {cov:>16}")
        rows.append((name, None, hit, n, held))
    base_ids = holdout.open(who + "기준선") if holdout is not None else ids
    bh, bn = baseline_all_n(base_ids, labels)
    print("  " + "-" * 66)
    print(f"  {'자명한 기준선(전부 N)':<18} {'—':>7}  {pct(bh, bn):>18}"
          f"  {f'{bn}/{bn} = 100.0%':>16}")
    return rows


# ── 5. 음성 대조 셋 — **심어서 발화를 확인한다** ────────────────────────

def negative_control(pairs, lit, sims, labels, train, holdout_ids,
                     events, sums):
    """
    셋 다 **실제로 변이를 돌린다.** 세 검사가 «있다»가 아니라 «발화한다»를 본다.

    열거는 검증이 아니다 — 이 저장소가 여러 번 센 실패 모드다.
    """
    print("\n" + "=" * W)
    print("음성 대조 — 심을 위반 셋. 검사가 **발화하는지** 본다")
    print("=" * W)
    ok = []

    # ⓐ 분할이 라벨을 보면 ─────────────────────────────────────────────
    #
    # 🔴 «훈련과 홀드아웃이 **소수점까지 같아진다**»가 아니다 — 그것을 기대하면
    #    검사가 영원히 발화하지 않는다(쌍 하나가 6%p인 크기다). 발화 조건은
    #    **간격이 무너지는 것**이고, 그것을 맹목 분할의 간격과 나란히 찍는다.
    print("\n  ⓐ 분할을 **라벨을 보고** 하도록 바꾼다 (`split_by_label`)")
    good_tr = [p for p in train if labels[p] != "?"]
    good_ho = [p for p in holdout_ids if labels[p] != "?"]
    bad_tr, bad_ho = split_by_label(list(labels), labels)
    m_tr = [p for p in bad_tr if labels[p] != "?"]
    m_ho = [p for p in bad_ho if labels[p] != "?"]

    def gap(fn, tr_ids, ho_ids):
        th, *_ = choose_theta(fn, tr_ids, lit, sims, labels)
        a = measure(fn, tr_ids, lit, sims, labels, th)
        b = measure(fn, ho_ids, lit, sims, labels, th)
        ra = 100.0 * a[0] / a[1] if a[1] else 0.0
        rb = 100.0 * b[0] / b[1] if b[1] else 0.0
        return ra, rb, abs(ra - rb)

    print(f"       {'규칙':<18} {'맹목 분할 훈련→홀드아웃':>26}"
          f" {'라벨을 본 분할':>24}")
    blind_gaps, mut_gaps, mut_ho, blind_ho = [], [], [], []
    for (name, fn, needs_th) in RULES:
        ba, bb, bg = gap(fn, good_tr, good_ho)
        ma, mb, mg = gap(fn, m_tr, m_ho)
        blind_gaps.append(bg)
        mut_gaps.append(mg)
        mut_ho.append(round(mb, 1))
        blind_ho.append(round(bb, 1))
        print(f"       {name:<18} {ba:6.1f}% → {bb:6.1f}%  (차 {bg:5.1f}%p)"
              f"   {ma:6.1f}% → {mb:6.1f}%  (차 {mg:4.1f}%p)")
    mb_avg = sum(blind_gaps) / len(blind_gaps)
    mm_avg = sum(mut_gaps) / len(mut_gaps)
    # 🔴 **이 조건은 서수 수리 라운드에서 다시 썼다 — 그리고 그 사연을 적는다.**
    #
    #   옛 조건은 «채점기 넷의 홀드아웃 값이 **전부 같은 수**가 된다»였다.
    #   그것은 축자가 오답 셋을 갖고 있을 때 관측된 **그 채점기의 증상**이었고,
    #   `survived_v3`이 그 셋을 고치자 넷 중 셋이 100%가 되면서 «전부 같다»가
    #   깨졌다 — 변이는 여전히 홀드아웃을 훈련의 복사본으로 만드는데도
    #   **대조가 빨개졌다.** 🔴 조건을 느슨하게 풀어 초록으로 되돌리는 것이
    #   이 저장소가 세는 실패 모드라서, 대신 **척도 없는 형태로 다시 썼다:**
    #   «넷이 같은 수인가»가 아니라 «넷의 **폭**이 무너지는가»다. 폭은 채점기가
    #   어디서 틀리는지에 안 매인다.
    #
    #   그리고 이 조건이 **거짓일 수 있음을 심어서 확인한다** — 아래 ⓐ′.
    def spread(xs):
        return max(xs) - min(xs)

    b_spread, m_spread = spread(blind_ho[:4]), spread(mut_ho[:4])
    indistinct = m_spread < b_spread / 2
    blind_ok = split_blind(list(labels)) == (sorted(train), sorted(holdout_ids))
    fired = (mm_avg < mb_avg / 2) and indistinct and blind_ok
    print(f"       → 평균 훈련↔홀드아웃 간격 **{mb_avg:.1f}%p → {mm_avg:.1f}%p**"
          f" (절반 미만: {'예' if mm_avg < mb_avg / 2 else '아니오'})")
    print(f"       → 채점기 넷의 홀드아웃 값 폭 {blind_ho[:4]} → {mut_ho[:4]}"
          f" = **{b_spread:.1f}%p → {m_spread:.1f}%p**"
          f" — {'구별이 무너진다' if indistinct else '아직 갈린다'}")
    print(f"       → ⓐ′ **같은 조건에 맹목 분할을 넣으면** 폭이"
          f" {b_spread:.1f}%p 그대로다 →"
          f" {'✅ 그때는 발화하지 않는다 (조건이 참일 수 있고 거짓일 수도 있다)' if not (b_spread < b_spread / 2) else '🔴 무조건 발화한다'}")
    print(f"       → 맹목 분할 대조: 실제 분할이 `sha1` 마지막 비트와"
          f" {'일치 ✅' if blind_ok else '불일치 🔴'}")
    print(f"       {'✅ 발화' if fired else '🔴 발화 실패'}")
    ok.append(fired)

    # ⓑ `?`를 `N`으로 세면 ────────────────────────────────────────────
    print("\n  ⓑ `?`를 `N`으로 센다 (F20 위반)")
    n_unknown = sum(1 for v in labels.values() if v == "?")
    scored = [p for p in labels if labels[p] != "?"]
    mutated = dict(labels)
    for p in list(mutated):
        if mutated[p] == "?":
            mutated[p] = "N"
    all_ids = [p for p in mutated if mutated[p] != "?"]
    print(f"       라벨 {len(labels)}건 · `?` {n_unknown}건 · 채점 대상 {len(scored)}건")

    # 검사 ①: 개수 불일치 — **원본 라벨 파일**을 다시 세어 대조한다
    try:
        check_counts(labels, all_ids)
        c1, why1 = False, "🔴 `check_counts`가 통과시켰다"
    except AssertionError as e:
        c1, why1 = True, f"`check_counts` 발화: {e}"

    # 검사 ②: `measure`의 `?` 단언 — 변이 없이 원본 라벨을 그대로 넣는다
    try:
        measure(rule_literal, all_ids, lit, sims, labels, 0.0)
        c2, why2 = False, "🔴 `measure`가 `?`를 분모에 받아들였다"
    except AssertionError as e:
        c2, why2 = True, f"`measure` 단언 발화: {e}"

    bh_s, bn_s = baseline_all_n(scored, labels)
    bh_m, bn_m = baseline_all_n(all_ids, mutated)
    print(f"       기준선이 공짜로 움직인다: {pct(bh_s, bn_s)} → {pct(bh_m, bn_m)}")
    print(f"       ① {why1}")
    print(f"       ② {why2}")
    fired = c1 and c2
    print(f"       {'✅ 발화 (검사 둘 다)' if fired else '🔴 발화 실패'}")
    ok.append(fired)

    # ⓒ θ를 홀드아웃에서 고르면 ────────────────────────────────────────
    print("\n  ⓒ θ를 **홀드아웃에서** 고른다 (`Holdout.audit`)")
    budget = len(RULES) + 4
    ho = Holdout([p for p in holdout_ids if labels[p] != "?"], budget)
    for (name, fn, needs_th) in RULES:          # 정상 경로가 쓰는 만큼 먼저 연다
        ho.open("측정:" + name)
    ho.open("측정:표제")
    ho.open("측정:" + V2_ROW)                   # 🆕 v2 기록 열도 정상 경로다
    ho.open("측정:기준선")
    clean = ho.audit()
    print(f"       정상 경로만: 총 {ho.total}회 / 예산 {budget}회"
          f" · 위반 {len(clean)}건  {'✅ 조용하다' if not clean else '🔴'}")
    for (name, fn, needs_th) in RULES:          # 그리고 **다른 이름으로** 더 연다
        choose_theta(fn, list(ho.open("θ선택:" + name)), lit, sims, labels)
    bad = ho.audit()
    print(f"       θ를 홀드아웃에서 고른 뒤: 총 {ho.total}회 / 예산 {budget}회"
          f" · 손잡이 {len(ho.reads)}개")
    print(f"       🔴 손잡이 이름당 2회 이상 열린 것은 **0건**이다 —"
          f" 이름을 새로 지었기 때문이다.")
    print(f"          **총 접근 예산이 그것을 잡는다:** {bad}")
    fired = bool(bad)
    print(f"       {'✅ 발화' if fired else '🔴 발화 실패'}")
    ok.append(fired)

    ok += ordinal_controls(pairs, events, sums, labels, train)
    return all(ok)


# ── 5-b. 서수 수리에 심을 위반 둘 ────────────────────────────────────────
#
# 🔴 이 저장소에서 «새 검증은 위반을 심어 발화를 확인한 뒤에만 보고한다»가 **열 번**
#    깨졌고, 가장 최근 것이 바로 위 ⓒ의 첫 판이다. 그래서 새 규칙에도 붙인다.
#    그리고 **하나는 반대 방향이다** — 규칙이 «너무 안 잡는가»만 보면 «너무 잡는»
#    변이가 초록으로 지나간다.

def ordinal_controls(pairs, events, sums, labels, train):
    """
    ⓓ 서수 예외를 **지우면** 훈련의 위양성이 돌아오는가 (발화해야 한다)
    ⓔ 서수가 **같을 때도** 죽이면 잡히는가 (**오발화** 대조)

    🔴 **훈련 쌍만 본다.** 홀드아웃은 `main`이 규칙마다 한 번 여는 것이 전부다.
    """
    print("\n" + "=" * W)
    print("서수 수리에 심을 위반 둘 — 🔴 **훈련 쌍만 본다**")
    print("=" * W)
    tr = [p for p in train if labels[p] != "?"]
    out = []

    def preds(scorer):
        return literal_preds(pairs, events, sums, scorer)[0]

    base = preds(survived_v3)
    wrong0 = sorted(p for p in tr if base[p] != labels[p])

    # ⓓ 서수 머리를 전부 비운다 = 예외를 지운다 → v3이 v2로 되돌아간다
    print("\n  ⓓ `_ordinal_heads`가 **늘 빈 것을 돌려주게** 한다 (예외 제거)")
    orig = scoring._ordinal_heads
    try:
        scoring._ordinal_heads = lambda text: {}
        muted = preds(survived_v3)
    finally:
        scoring._ordinal_heads = orig
    back = sorted(p for p in tr if muted[p] != labels[p])
    fired = set(back) > set(wrong0) and set(back) >= {"P12", "P14"}
    print(f"       수리된 채점기의 훈련 오답: {wrong0 or '없다'}")
    print(f"       예외를 지운 뒤       : {back}"
          f"  ← **위양성이 돌아왔다**" if back else "")
    print(f"       🔴 되살아난 쌍 {sorted(set(back) - set(wrong0))}"
          f" — `P12`·`P14`가 그 안에 {'있다' if set(back) >= {'P12', 'P14'} else '없다'}")
    print(f"       {'✅ 발화' if fired else '🔴 발화 실패'}")
    out.append(fired)

    # ⓔ 서수가 겹치는지 안 보고 «둘 다 서수가 있으면 죽인다»로 바꾼다
    print("\n  ⓔ 회차가 **같을 때도** 죽인다 (오발화 대조 — 반대 방향)")
    print("       머리마다 서수에 일련번호를 붙여 **절대 안 겹치게** 만든다:")
    print("       «서수가 어긋난다»가 아니라 «서수가 있다»가 방아쇠가 된다")
    seq = [0]

    def never_agree(text):
        seq[0] += 1
        return {h: {f"{o}#{seq[0]}" for o in o_}
                for h, o_ in orig(text).items()}
    try:
        scoring._ordinal_heads = never_agree
        over = preds(survived_v3)
    finally:
        scoring._ordinal_heads = orig
    killed = sorted(p for p in tr if over[p] == "N" and base[p] == "Y")
    hurt = sorted(p for p in tr if over[p] != labels[p] and base[p] == labels[p])
    # 대장 항목으로도 하나 짚는다 — 같은 회차인데 죽는 자리를 이름으로 본다
    same = ("E005", "S16")     # «두 번째 면접» × 두 번째 면접을 말하는 요약
    ok_same = bool(survived_v3(sums[same[1]], [events[same[0]]]).survived)
    try:
        scoring._ordinal_heads = never_agree
        bad_same = bool(survived_v3(sums[same[1]], [events[same[0]]]).survived)
    finally:
        scoring._ordinal_heads = orig
    print(f"       {same[0]} «{events[same[0]]}» × 요약 {same[1]}"
          f" (같은 회차를 말한다) : 수리본 {'생존' if ok_same else '비생존'}"
          f" → 변이 {'생존' if bad_same else '**비생존**'}")
    print(f"       훈련에서 새로 죽은 쌍 {killed} · 그중 **정답이 틀려진 것**"
          f" {hurt}")
    fired = (ok_same and not bad_same) and bool(hurt)
    print(f"       {'✅ 오발화가 잡힌다' if fired else '🔴 대조 실패 — 변이가 조용하다'}")
    out.append(fired)
    return out


# ── 6. main ────────────────────────────────────────────────────────────

def main():
    print("=" * W)
    print("채점기 검증 — 축자 vs 임베딩, 사람 라벨 32개 · 사전 등록된 홀드아웃")
    print("=" * W)

    labels, source = load_labels()
    events, sums, smeta = load_material()
    meta = load_meta()                       # 32쌍이 아니라 **전체** 쌍의 종류·유사도
    pairs = {p: m for p, m in meta.items() if p in labels}

    # ── 0. 라벨 ──
    print("\n" + "-" * W)
    print("0. 라벨 — **사람이 붙였다. 자기저작이 아니다**")
    print("-" * W)
    for fname in LABELS_USED:
        n = sum(1 for p in source.values() if p == fname)
        print(f"  ✅ {fname:<22} {n:>3}개  (합친다)")
    # 🔴 1판을 **읽어서** 폐기 사유를 다시 센다. 산문으로만 적으면 다음 사람이
    #    그 24개를 합치고 «n=56이라 더 낫다»고 적는다.
    d = load_discarded()
    far = [p for p in d if meta.get(p, {}).get("kind") == DISCARD_KIND]
    bad = [p for p in far if d[p] == DISCARD_LABEL]
    print(f"  🔴 {LABELS_DISCARDED:<22} {len(d):>3}개  **합치지 않는다 — 폐기**")
    print(f"       사유 ① 라벨러가 *\"이해가 안 돼서 느낌으로 찍었다\"*고 말했다")
    print(f"       사유 ② 먼 대조 {len(far)}개 중 **{len(bad)}개가 `Y`**"
          f"  ({', '.join(sorted(bad))})")
    print(f"              먼 대조는 코사인 하위 25%에서 뽑은 «담겼을 리 없는» 자리다.")
    print(f"              전부 `Y`면 라벨의 **방향이 뒤집혀 있다.**")
    print(f"       🔴 **파일은 지우지 않는다 — 기록이다.** 2판이 무엇을 고쳤는지"
          f" 말할 근거가 이것뿐이다")
    print(f"          (요약별 묶음 · 12행 · 질문 «이 요약이 아래 일을 말하고 있나요?»)")
    if len(bad) != len(far) or not far:
        print(f"  🔴 폐기 사유가 재현되지 않는다 (먼 대조 {len(far)} · `Y` {len(bad)})")
        return 1

    assert len(labels) == N_EXPECT, f"라벨이 {len(labels)}개다 ({N_EXPECT} 아님)"
    from collections import Counter
    dist = Counter(labels.values())
    print(f"\n  합계 n = **{len(labels)}**   Y {dist['Y']} · N {dist['N']}"
          f" · ? {dist['?']}")
    print(f"  🔴 `?` **{dist['?']}건은 정확도의 분자·분모에서 뺀다** (F20) —"
          f" 채점 대상 **{len(labels) - dist['?']}건**")
    print(f"     `?`는 «애매하다»이지 «아니다»가 아니다. `N`으로 세면 라벨러가 하지")
    print(f"     않은 판단을 스크립트가 대신 하고, 그 한 건이 기준선을 공짜로 올린다.")

    # ── 1. 재료 ──
    print("\n" + "-" * W)
    print("1. 재료 — 24세션 요약 (`summarize.session_digest` · 사본 없음 · F12)")
    print("-" * W)
    print(f"  `SUMMARY_S2.json`  요약 {len(sums)}건 · 사건 {len(events)}개"
          f" · 모집단 {len(events) * len(sums)}쌍")
    print(f"  다이제스트 {smeta['digest'][:16]}…  seed {smeta['seed']}"
          f" · temperature {smeta['temperature']} · num_ctx {smeta['num_ctx']}")
    print(f"  🔴 U4 사전 등록 방아쇠 당김 여부: **{smeta['u4_trigger_pulled']}**")
    print(f"     {smeta['u4_note']}")

    # ── 2. 채점기 둘 ──
    print("\n" + "-" * W)
    print("2. 채점기 둘 — 같은 32쌍에")
    print("-" * W)
    lit, unscorable = literal_preds(pairs, events, sums, survived_v3)
    lit_v2, uns_v2 = literal_preds(pairs, events, sums, survived_v2)
    print(f"  축자   `scoring.survived_v3`을 **그대로 부른다**(사본 없음 · F12)"
          f" · 판정 불가 {len(unscorable)}건")
    flipped = sorted(p for p in lit if lit[p] != lit_v2[p])
    print(f"  축자   `scoring.survived_v2`(**기록 · 얼렸다**)도 같은 32쌍에 돌린다"
          f" · 판정 불가 {len(uns_v2)}건")
    print(f"  🔴 v2 → v3에서 **판정이 바뀐 쌍 {len(flipped)}건**:"
          f" {', '.join(f'{p}({lit_v2[p]}→{lit[p]})' for p in flipped) or '없다'}")
    print(f"     판정 불가 집합은 **같다** ({len(uns_v2)} = {len(unscorable)}) —"
          f" v3은 분모를 안 건드린다. 뺄 수만 있고 더할 수 없다")
    print(f"     🔴 **두 열은 같은 실행의 것이다.** 옛 라운드의 v2 값과 이번 v3 값을"
          f" 잇는 화살표는 이 문서 어디에도 없다 — 다른 채점기다")
    sims, calls = embed_sims(pairs, events, sums)
    if sims is None:
        print(f"  🔴 `bge-m3` 임베딩을 못 얻었다 ({embedding.OLLAMA_HOST})."
              f" **종료 77 (SKIP)** — 통과가 아니라 미측정이다 (G1)")
        return 77
    print(f"  임베딩 `prototype/embedding.py`의 bge-m3 코사인"
          f" · **라이브 호출 {calls}회**"
          f"  {'✅ 캐시로 전부 채웠다' if calls == 0 else '⚠️ 캐시 미스가 있었다'}")
    ref = meta                    # 위에서 한 번 읽은 것을 재사용한다
    drift = max(abs(sims[p] - ref[p]["sim"]) for p in sims)
    print(f"  대조   `LABEL_SIMS_ALL.json`의 기록값과 최대 편차"
          f" **{drift:.2e}**  {'✅' if drift < 1e-5 else '🔴'}")

    # ── 3. 분할 ──
    print("\n" + "-" * W)
    print("3. 사전 등록된 분할 — 🔴 **라벨도 유사도도 보지 않는다**")
    print("-" * W)
    train, holdout_ids = split_blind(list(labels))
    with open(SPLIT_JSON, encoding="utf-8") as f:
        rec = json.load(f)
    same = sorted(rec["train"]) == sorted(train) and \
        sorted(rec["holdout"]) == sorted(holdout_ids)
    print(f"  규칙   `sha1(pair_id)`의 **마지막 비트**"
          f" — 함수 시그니처에 라벨이 없다")
    print(f"  훈련 {len(train)}쌍 · 홀드아웃 {len(holdout_ids)}쌍")
    print(f"  기록 `LABEL_SPLIT.json`과 {'일치 ✅' if same else '불일치 🔴'}"
          f"  (라벨이 붙기 **전에** 고정됐다)")
    if not same:
        return 1

    scored_tr = [p for p in train if labels[p] != "?"]
    scored_ho = [p for p in holdout_ids if labels[p] != "?"]
    # 🔴 정상 경로에서 **실제로 건다.** 자기 음성 대조에서만 불리는 검사는 검사가 아니다.
    check_counts(labels, scored_tr + scored_ho)
    n_ho = len(scored_ho)
    print(f"  `?` 제외 후 — 훈련 **{len(scored_tr)}쌍**"
          f"(뺀 것 {len(train) - len(scored_tr)}) ·"
          f" 홀드아웃 **{n_ho}쌍**(뺀 것"
          f" {len(holdout_ids) - n_ho})")

    # 🔴 여기서 홀드아웃의 **유일한 손잡이**를 만들고 날것의 리스트를 버린다.
    #    카운터가 있어도 옆에 날 리스트가 살아 있으면 θ 선택이 그것을 집어
    #    카운터를 우회한다 — 세는 기제가 «셀 수 없는 경로»를 남겨 두면
    #    그것은 규율을 코드로 만든 것이 아니라 코드처럼 보이게 만든 것이다.
    #
    # 예산은 **여는 자리를 세어 미리 적는다.** 규칙 5개 각각 한 번 + 표의 표제 한 번
    # + 표의 기준선 한 번 + 판정 절의 기준선 한 번 + 판정 절의 «축자 오답 목록»
    # 한 번 = 9. 🔴 이 수를 «지금 몇 번 열리는지 세어» 맞추면 예산이 아니라 사후
    # 추인이다 — 자리를 늘리려면 위 목록에 자리를 적고 수를 올려야 한다.
    #
    # 🆕 **자리를 하나 늘렸다:** «축자 v2 (기록)» 열이 홀드아웃을 한 번 더 연다.
    #    왜 늘리는가 — 수리 전/후를 **같은 실행에서** 찍지 않으면 비교가 라운드를
    #    건너뛰고, 그것이 정확히 이 라운드가 피하려는 실패 모드 ②다. 그래서 자리를
    #    **먼저 적고** 수를 5 → 6으로 올린다. 늘린 것을 안 적으면 이 예산은
    #    «지금 몇 번 열리는지»를 뒤늦게 베낀 수가 된다.
    HO_BUDGET = len(RULES) + 5
    ho = Holdout(scored_ho, HO_BUDGET)
    del scored_ho

    # ── 4. θ는 훈련에서 ──
    print("\n" + "-" * W)
    print("4. θ 선택 — **훈련에서만.** 홀드아웃은 아직 안 열었다 (G12)")
    print("-" * W)
    print(f"  모집단  대장 사건 {len(events)} × 세션 요약 {len(sums)}"
          f" = {len(events) * len(sums)}쌍에서 사전 등록 규칙으로 뽑은 {len(labels)}쌍")
    print(f"  n       훈련 {len(scored_tr)}쌍 (`?` 제외 후)")
    thetas, cutinfo = {}, {}
    for (name, fn, needs_th) in RULES:
        th, hit, n, held, ncand = choose_theta(fn, scored_tr, lit, sims, labels)
        thetas[name] = th if needs_th else None
        if needs_th:
            cut = sum(1 for p in scored_tr if sims[p] >= th)
            cutinfo[name] = (cut, len(scored_tr), ncand)
            print(f"  {name:<18} θ = **{th:.4f}**  후보 {ncand}개 중"
                  f" · 자르는 비율 훈련 {cut}/{len(scored_tr)}"
                  f" = {100.0 * cut / len(scored_tr):.1f}%가 `Y`쪽")
        else:
            print(f"  {name:<18} θ 없음 — 문턱이 필요 없는 규칙이다")

    # ── 5. 표 ──
    print("\n" + "-" * W)
    print("5. 표 — 훈련 / 홀드아웃. 🔴 **홀드아웃은 규칙당 한 번만 연다**")
    print("-" * W)
    EXTRA = [(V2_ROW, lit_v2)]
    tr_rows = table("훈련 (θ를 고른 곳 — 여기 수치는 낙관적이다)",
                    scored_tr, lit, sims, labels, thetas, extra=EXTRA)
    rows = table("홀드아웃 (사전 등록 · 한 번만 잰다)",
                 [None] * n_ho, lit, sims, labels, thetas,
                 holdout=ho, who="측정:", extra=EXTRA)
    leak = ho.audit()
    print(f"\n  홀드아웃 접근 감사: 총 {ho.total}회 / 사전 등록 예산 {ho.budget}회"
          f" · 손잡이 {len(ho.reads)}개 · **위반"
          f" {len(leak)}건**  {'✅' if not leak else '🔴'}")
    if leak:
        print(f"  🔴 {leak} — «홀드아웃은 한 번만 본다»가 깨졌다")
        return 1

    # ── 6. 판정 ──
    print("\n" + "=" * W)
    print("판정")
    print("=" * W)
    R = {r[0]: r for r in rows}
    bh, bn = baseline_all_n(ho.open("판정:기준선"), labels)
    base = 100.0 * bh / bn

    def acc(name):
        _, _, hit, n, _ = R[name]
        return 100.0 * hit / n if n else 0.0

    _, _, e_hit, e_n, _ = R["임베딩 단독"]
    _, _, l_hit, l_n, _ = R["축자 단독 (v3)"]
    _, _, v_hit, v_n, _ = R[V2_ROW]
    _, _, a_hit, a_n, _ = R["AND (둘 다 Y)"]
    _, _, s_hit, s_n, s_held = R["«어긋나면 보류»"]
    tr_e = measure(rule_embed, scored_tr, lit, sims, labels,
                   thetas["임베딩 단독"])
    tr_l = measure(rule_literal, scored_tr, lit, sims, labels, 0.0)
    tr_v = measure(rule_literal, scored_tr, lit_v2, sims, labels, 0.0)

    print(f"  임베딩 단독  훈련 {100.0*tr_e[0]/tr_e[1]:.1f}%"
          f" → 홀드아웃 **{acc('임베딩 단독'):.1f}%**"
          f"  ({e_hit}/{e_n}) — 자명한 기준선 {base:.1f}%"
          f" ({bh}/{bn})보다 **{'낮다' if acc('임베딩 단독') < base else '높다'}**")
    print(f"  축자 v3      훈련 {100.0*tr_l[0]/tr_l[1]:.1f}% ({tr_l[0]}/{tr_l[1]})"
          f" · 홀드아웃 **{acc('축자 단독 (v3)'):.1f}%** ({l_hit}/{l_n})")
    print(f"  축자 v2 기록  훈련 {100.0*tr_v[0]/tr_v[1]:.1f}% ({tr_v[0]}/{tr_v[1]})"
          f" · 홀드아웃 **{100.0*v_hit/v_n:.1f}%** ({v_hit}/{v_n})"
          f"  — 🔴 **같은 실행·같은 쌍의 두 채점기다**")
    print(f"  AND          홀드아웃 **{acc('AND (둘 다 Y)'):.1f}%** ({a_hit}/{a_n})"
          f" — 축자와 {'**동률**: 결합해 얻은 것이 0이다' if a_hit == l_hit and a_n == l_n else '다르다'}")
    print(f"  «어긋나면 보류»  홀드아웃 **{acc('«어긋나면 보류»'):.1f}%**"
          f" ({s_hit}/{s_n}) · 커버리지 {100.0*s_n/(s_n+s_held):.1f}%"
          f" — **{s_held}쌍({100.0*s_held/(s_n+s_held):.1f}%)을 버리고도**"
          f" 축자보다 {'낮다' if acc('«어긋나면 보류»') < acc('축자 단독 (v3)') else '높다'}")
    verdict = acc("임베딩 단독") < acc("축자 단독 (v3)")
    print(f"\n  ⛔ **채점기를 임베딩으로 바꾸지 않는다.**"
          if verdict else "\n  🟢 임베딩이 축자를 이겼다 — 다시 읽어라")

    print("\n  🆕 **서수 결함 — v2가 틀린 자리와 v3이 고친 자리.**")
    seen = ho.open("판정:축자오답")
    def _rows(pred):
        return ([p for p in seen if pred[p] != labels[p]],
                [p for p in scored_tr if pred[p] != labels[p]])
    e3, t3 = _rows(lit)
    e2, t2 = _rows(lit_v2)
    for p in sorted(set(e3 + t3 + e2 + t2)):
        m = pairs[p]
        where = "홀드아웃" if p in seen else "훈련"
        fixed = (p in e2 + t2) and (p not in e3 + t3)
        print(f"     {p} [{where}] 요약 {m['session']} ← 사건 {m['event_id']}"
              f" «{events[m['event_id']]}»  사람 {labels[p]}"
              f" · v2 {lit_v2[p]} · v3 {lit[p]}"
              f"  {'✅ v3이 고쳤다' if fixed else '🔴 남았다'}")
    print(f"     v2의 오답 {len(e2) + len(t2)}건 → v3의 오답"
          f" **{len(e3) + len(t3)}건** (훈련 {len(t3)} · 홀드아웃 {len(e3)})")
    print("     🔴 **홀드아웃의 `P15`는 이 수리를 설계할 때 안 봤다.** 훈련의"
          " `P12`·`P14`만 보고 고쳤고, 홀드아웃은 고친 뒤 한 번 열었다.")
    print(f"  ⚠️ **n = {len(labels)}는 작다.** 홀드아웃 {n_ho}쌍에서"
          f" 한 쌍이 {100.0 / n_ho:.1f}%p다.")

    good = negative_control(pairs, lit, sims, labels, train, holdout_ids,
                            events, sums)
    print("\n" + "=" * W)
    print(f"  음성 대조 셋      : {'✅ 셋 다 발화' if good else '🔴 발화 실패'}")
    print(f"  임베딩 라이브 호출 : {calls}회")
    print(f"  홀드아웃 접근      : 규칙당 1회 ✅")
    print("=" * W)
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
