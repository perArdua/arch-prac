# -*- coding: utf-8 -*-
"""
precision.py — 오주입 지표 *교체*: 질문별 정밀도. (단계 0-g)

## 왜 새 지표가 필요한가

옛 지표는 *"**대장 전체에** 없는 것을 꺼냈는가"*였다. 그런데 이 하니스에서는
`soak.py:91-94`가 대장 항목만 `event` 색인에 넣는다 — **대장 밖 문자열이
색인에 존재할 수 없다.** 그래서 gold 집합을 옳게 고치자마자(단계 0-a)
8셀 전부에서 **항등 0**이 됐다. 0이 좋아서가 아니라 **잴 것이 없어서**다.

정밀도는 그게 아니라 *"**이 질문에** 쓸모없는 것을 꺼냈는가"*다.
`eval/questions.yaml`은 이미 필요한 것을 갖고 있다 — 문항마다 `evidence: [id]`가
있고, 일부는 `distractor`까지 명시한다.

## 매칭 의미론

`build_context(q.ask)`의 `ctx.provenance`에서 `kind == "retrieved"`인 항목
**문자열** 집합을 본다. 각 문자열이 `q["evidence"]`에 열거된 id의
`allowed_strings`(= `{object, text}` 합집합, `soak.py:142-145` 규칙)에
**속하는지** 검사한다. 속하지 않으면 이 질문에 대한 오주입 1건이다.

    misinjected(q) = |{ r ∈ retrieved(q) : r ∉ allowed_strings(q.evidence) }|
    precision(q)   = 1 - misinjected(q) / max(|retrieved(q)|, 1)

단계 0-a의 수리가 **여기서 비로소 값을 갖는다** — 수리가 없으면 `object != text`인
사실 12개가 **자기 근거인데도** 오주입으로 세어진다.

## 🔄 단계 1 (라운드 2) — 지표를 **쌍**으로 만든다 (결정 A·B · P6-b)

매크로 `precision(q)`는 `|retrieved(q)| = 0`인 문항에 **1.0을 공짜로 준다.**
프로덕션 셀에서도 8문항이 그 1.0을 받는다(F21). 즉 매크로 평균은
*"검색을 안 할수록 좋다"*를 최적화한다. 그래서 지표를 넷으로 늘린다.

    misinjection@q          문항별 오주입 건수의 합 (기존 · 불변)
    evidence_recall(검색경로) 근거 id 중 검색 경로로 올라온 것 / 근거 id 합계(28)
    pooled(micro) 정밀도     1 - Σmis / Σ|ret|  — 검색 0건 문항은 분자·분모 어디에도 없다
    top1_misinjection       1등이 근거 밖인 문항 수 / 검색 ≥1건 문항 수

- **매크로 열은 지우지 않는다.** 대신 합계 줄에 `macro(자동 1.0 n개 포함)`이라고
  이름을 박는다 (G15). 값이 옳아도 **무엇의 값인지**가 안 적혀 있으면 F21이 반복된다
- ⚠️ **`evidence_recall`의 이름에 `검색경로`가 박혀 있다.** `soak.qa_eval`의 회상은
  결정적 사실 주입(`via_facts`)을 포함한다 — **같은 단어를 두 뜻으로 쓰지 않는다**
- ⚠️ **pooled의 분모(검색 항목 수)는 셀마다 4~22로 다르다.** 절대 비교 금지,
  `evidence_recall`과 **쌍으로만** 읽는다 (결정 A4의 ❌ 열)
- 🔄 **(레인 G) `top1_misinjection`은 이제 결정적 동점 처리 위에 서 있다** —
  `memory.py:1189`(`scored.sort`)이 `(-s, event_id)`로 정렬한다(후속 10). 그전까지는 점수 하나로만
  정렬해 **동점의 1등을 rowid가 정했다.** 오늘의 값은 그 변경으로 **한 자리도
  안 움직였다**(`event_id`가 곧 rowid이고 SQLite가 오늘 그 순서로 돌려주기 때문).
  그래도 출력에 **동점 문항 수와 목록을 병기**한다 (F26 · 결정 B3). 결정적 2차 정렬 키는
  G16(이 라운드는 기본값을 하나도 바꾸지 않는다)에 걸려 **후속 10**이다
- **`hard_misinjection`은 은퇴했다**(F25). 계산과 출력은 유지한다 — 0이 아닌 값이
  나오면 하니스나 대장이 움직였다는 뜻이라 **회귀 탐지기로서의 값**이 남는다

## ⚠️ 이 지표가 말할 수 없는 것 (ADR-015로 그대로 옮긴다)

- `evidence`는 **정답 근거**이지 "허용 가능한 문맥"이 아니다. 관련은 있지만
  `evidence`에 없는 항목이 주입되면 오주입으로 세어진다 →
  **정밀도를 과대추정하지 않고 과소추정한다.** 상한으로 쓰기에 안전한 방향이다
- **QA 경로 18문항**이다. 436개 user 턴 전부의 정밀도가 아니다. 옛 지표보다
  범위가 **좁다** — 그 대가로 **분모가 살아 있다.** 넓은 범위는 `trap_injected`가 맡는다
- **한 번도 잰 적 없는 지표다.** 여기서는 **기준선만 찍는다.** 임계값은 단계 4에서
  이 기준선 대비 상대값으로만 쓴다
- ⚠️ `|retrieved(q)| = 0`이면 `precision(q) = 1.0`이다 — **아무것도 안 꺼내는 것이
  만점**이다. 그래서 문항별 `|retrieved(q)|`를 항상 병기하고, 방향 검정은
  기준셀에서 `|retrieved(q)| > 0`인 문항으로만 한다
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "prototype"))
sys.stdout.reconfigure(encoding="utf-8")
import yaml                                                # noqa: E402
import memory as M                                         # noqa: E402
from memory import Memory                                  # noqa: E402
from soak import seed, ingest, trap_injected, ROOT, CHAT   # noqa: E402
from gate_sweep import (g_current, g_content, g_always,     # noqa: E402
                        build_vocab)

W = 78

# 기준선 4셀 — `gate_sweep.py` 4부 격자의 부분집합. G8: 몽키패치가 읽는 값은
# 전부 모듈 전역이라 스칼라 재바인딩으로 갈아끼운다.
#
# 🔄 단계 0 (라운드 2) — **기준셀을 프로덕션으로 옮기고, 라벨과 키를 영구히 분리한다.**
#   `memory.py:1007-1026`의 `Memory.gate`가 내용어 접점 게이트이고, 462개 발화
#   (user 턴 436 + 문항 26)에서 `gate_sweep.g_content`와 판정이 **100% 일치**한다(F21).
#   즉 프로덕션 기본 조합은 `G3 · θ=0.05`다. **G0은 `gate_sweep` 4부 이전의 정책이며
#   프로덕션이 아니다** — 그동안 `G0 · θ=0.05`를 "기본셀"이라 부른 것은 틀린 라벨이었다.
#   값은 전부 옳았고 **어느 구성의 값인지가 틀렸다.**
#
#   ⚠️ **라벨은 `CELL_LABEL`에만 두고 `cells`의 조회 키로 쓰지 않는다.** 라벨을 고칠 때
#   `cells[BASE_CELL]`(:487 — `direction_test`)이 `KeyError`로 깨지지 않게 하기 위해서다.
#   라벨과 `BASE_CELL`을 함께 바꾸는 방식은 이 인스턴스는 고치지만 **결합을 남긴다** —
#   다음 사람이 라벨을 또 고치면 같은 `KeyError`가 돌아온다. 이 저장소가 F21에서 배운
#   것이 *"라벨은 사실이 아니다"*인데, 그 라벨을 조회 키로 쓰는 것은 그 교훈과 어긋난다.
#   키를 그대로 두면 덤으로 `cells`의 키가 기준선과 바이트 동일이라 수용 기준도 단순해진다.
#
#   ⚠️ **`Memory.gate`를 직접 셀 함수로 넣지 않는다.** `main()`의 몽키패치 복원
#   (`orig_gate` — :564,:572)이 같은 객체를 붙들게 되어 저장·복원이 **항등**이 된다.
#   `g_content`를 쓰고 두 함수의 동치성은 단위 시험으로 못박는다.
CELLS = [("G0", g_current), ("G3", g_content)]     # 키는 바꾸지 않는다
THETAS = [0.15, 0.05]
CELL_LABEL = {                                     # 표시명은 여기서만 온다
    "G0": "G0(역사 — gate_sweep 4부 이전)",
    "G3": "G3(프로덕션 — memory.py 기본값)",
}
BASE_CELL = ("G3", 0.05)      # 방향 검정의 기준셀 = 프로덕션 조합 (F21)

# 🆕 단계 1 (G12) — **θ는 값만 적을 수 없다.** 모집단·n·자르는 비율이 같이 붙어야 한다.
#   여기 적힌 비율은 실제 검색 모집단(채점 18문항 × `event` 색인 21행 = **378쌍**)에서
#   각 θ가 자르는 비율이다(F27). `experiments/rel_dist.py`가 매 실행 이 값을 다시 찍으므로
#   둘이 어긋나면 색인이 움직인 것이다.
#   🔴 어휘 척도에서 `θ=0.05`는 `θ=0.0001`과 **같은 35쌍을 통과시킨다** — 임계 컷이 아니라
#      *"겹침이 정확히 0인 것만 버린다"*는 규칙이다.
POPULATION_378 = "378쌍 = 채점 18문항 × event 색인 21행(user_deleted=0)"
THETA_CUT_378 = {0.15: "96.3%", 0.05: "90.7%"}

# 🆕 단계 1 작업 5 — `hard_misinjection` **은퇴** 표기와 도달 불가능성 진단의 축.
#   τ 사다리는 선행 라운드가 지목한 원인(`TAU_IMPORTANCE`)을 직접 친다. 5번째 행은
#   그 원인 가설을 완전히 죽인다 — τ=0·θ=0·게이트 전개(G1)·TOP_K=1에서도 0이다(F25).
RETIRED_HARD_NOTE = "게이트 아님 · 은퇴(F25)"
TAU_LADDER = [0.20, 0.15, 0.10, 0.05]

# 🆕 지표의 **표시명**. `soak.qa_eval`의 회상(결정적 사실 주입 포함)과 갈라야 하므로
#   경로를 이름에 박는다 (F23 · §5.4 관측성).
RECALL_NAME = "evidence_recall(검색경로)"

# `distractor` 필드에서 대장 id를 뽑는 패턴. **X 계열만** 유효하다.
DISTRACTOR_ID = re.compile(r"([A-Z])(\d{3})")

# 🔄 rev5 — Q04의 `distractor`는 산문도 X-id도 아닌 `'마케팅 회사 대리'`,
#    즉 **`F002.object`**다. 색인에는 `F002.text`(`'지우는 마케팅 회사 대리'`)가
#    들어가므로 **리터럴 매칭은 영원히 0**이다. id로 통일해 집합 멤버십으로 푼다.
DISTRACTOR_LITERAL = {"Q04": {"F002"}}

# 근거를 해석할 수 없어 채점에서 빼는 문항 (🔴 rev3, Architect 실측).
# 넣으면 `allowed_strings`가 공집합이 되어 `misinjected(q) = |retrieved(q)|`가 되고,
# 그러면 집계는 정밀도가 아니라 **검색 *분량*을 재게 된다.**
EXPECTED_HEADER = ("scored 18/26 · excluded: "
                   "Q11(debt D001), Q14,Q17-Q22(no evidence key)")


def load():
    corpus = [json.loads(l) for l in
              open(f"{ROOT}/eval/corpus/corpus.jsonl", encoding="utf-8")]
    with open(f"{ROOT}/eval/fact-ledger.yaml", encoding="utf-8") as f:
        ledger = yaml.safe_load(f)
    with open(f"{ROOT}/eval/questions.yaml", encoding="utf-8") as f:
        qs = yaml.safe_load(f)["qa_questions"]
    return corpus, ledger, qs


def key_index(ledger):
    """`soak.py:142-145`의 `key_of`와 **같은 규칙** — `{object, text}` 합집합."""
    key_of = {}
    for f in ledger.get("facts", []):
        key_of[f["id"]] = {k for k in (f.get("object"), f.get("text")) if k}
    for e in ledger.get("events", []):
        key_of[e["id"]] = {e["text"]}
    return key_of


def allowed_strings(ids, key_of):
    return {s for i in ids if i in key_of for s in key_of[i]}


def distractor_ids(q):
    """
    `distractor` 필드를 **대장 id 집합**으로 푼다.

    5문항 중 4개의 값은 **사람이 읽으라고 쓴 산문**이라 색인 문자열과 결코
    일치하지 않는다 (`"코코 (X003 — 친구 민지네 고양이)"`). 필드를 그대로
    `in` 비교하면 `hard_misinjection`은 영원히 0이다 — 0-a가 죽인 것과
    **정확히 같은 종류의 항등적 지표**가 된다.

    X 계열도 Q04도 아닌 접두사(`E`·`D`)가 들어오면 **조용히 빠지지 않고 터진다.**
    """
    qid = q["id"]
    if qid in DISTRACTOR_LITERAL:
        return set(DISTRACTOR_LITERAL[qid])
    raw = q.get("distractor") or ""
    found = DISTRACTOR_ID.findall(raw)
    bad = [f"{p}{n}" for p, n in found if p != "X"]
    if bad:
        raise ValueError(
            f"{qid}: distractor에 X 계열이 아닌 id {bad} — 해석 규칙이 없다. "
            f"§5.1에 케이스를 추가하고 규칙을 명시할 것: {raw!r}")
    if not found:
        raise ValueError(
            f"{qid}: distractor에서 대장 id를 못 찾았다 — 리터럴 매칭으로 흘러가면 "
            f"항등 0 지표가 된다: {raw!r}")
    return {f"{p}{n}" for p, n in found}


def score_question(q, retrieved, key_of):
    """한 문항의 오주입·정밀도. `retrieved`는 문자열 집합."""
    allowed = allowed_strings(q.get("evidence", []), key_of)
    mis = len([r for r in retrieved if r not in allowed])
    prec = 1 - mis / max(len(retrieved), 1)
    return mis, prec


def evidence_recall_via_retrieval(q, retrieved, key_of):
    """
    🆕 단계 1 작업 1 (F23) — **검색 경로** 회상. `(적중 근거 수, 총 근거 수)`.

    출력에 찍는 이름은 언제나 **`evidence_recall(검색경로)`**다 (`RECALL_NAME`).
    함수 이름은 이 저장소의 관례대로 ASCII로 두고, **읽는 사람이 보는 이름**에
    경로를 박는다.

        recall(q) = |{e ∈ evidence(q) : key_of[e] ∩ retrieved(q) ≠ ∅}| / |evidence(q)|

    ⚠️ **이름에 `검색경로`가 박혀 있는 이유.** `soak.qa_eval`이 재는 회상은 결정적
    사실 주입(`via_facts`)을 **포함한다.** 같은 낱말을 두 뜻으로 쓰면 *"회상이 올랐다"*가
    어느 경로의 이야기인지 갈리지 않는다. 여기서 세는 것은 `provenance`의 `retrieved`
    뿐이다.

    분모가 **채점 18문항 전부에 정의된다**는 것이 이 지표의 요점이다 —
    `partition`이 근거 색인이 있는 문항만 남기므로 공집합이 될 수 없다.
    그래서 *"아무것도 안 꺼냈다"*가 만점(정밀도 1.0)이 아니라 **회상 0**으로 보인다.
    """
    ev = [e for e in q.get("evidence", []) if e in key_of]
    hit = sum(1 for e in ev if key_of[e] & retrieved)
    return hit, len(ev)


def top1_misinjection(q, ordered, key_of):
    """
    🆕 단계 1 작업 3 (F26 · 결정 B3) — 1등이 근거 밖인가. 검색 0건이면 `None`.

    `ordered`는 `retrieve()`가 돌려준 **점수 내림차순** 요약 문자열 목록이다
    (`memory.py:1189`의 `scored.sort` 정렬 → 그 순서대로 `provenance`에 append).

    🔄 **(레인 G) 이 지표가 서 있던 임의성이 제거됐다.** 여기 있던 것은
    *"`memory.py:839`는 점수 하나로만 정렬하고 Python `sort`는 안정 정렬이라 동점의
    1등은 SQLite 행 순서(rowid)가 정한다"*였다. 지금 `memory.py:1189`(`scored.sort`)은
    `(-s, event_id)`로 정렬한다(후속 10) — **1등이 SELECT 반환 순서를 안 따른다.**
    ⚠️ **값은 안 움직였다**: `event_id`가 곧 rowid이고 SQLite가 오늘 그 순서로
    돌려주므로, 이 변경이 없앤 것은 *"오늘 틀린 값"*이 아니라 *"내일 조용히 움직일
    수 있음"*이다. 아래 동점 병기는 **그대로 둔다** — 동점 자체는 여전히 있고,
    그 사실은 지표를 읽는 사람이 알아야 한다.
    프로덕션 셀 Q05의 1·2·3위가 정확히 동점(s=0.4)이고
    1위만 근거이므로, 순서가 뒤집히면 셀 값이 `4/10 → 5/10`(10%p) 움직인다.
    → 그래서 이 지표는 **동점 문항 수를 병기해서만** 읽는다(`tie_rank1`).
    """
    if not ordered:
        return None
    return 0 if ordered[0] in allowed_strings(q.get("evidence", []), key_of) else 1


def tie_rank1(hits):
    """
    1등 자리의 동점 수와 그 점수. `hits`는 `retrieve()`의 `[(score, row), ...]`.

    **부동소수 정확 동일성으로 센다** — 그것이 `sort`가 보는 것과 같은 기준이기
    때문이다. 1e-17 차이는 동점이 아니라 결정적 순서이고, 그 둘을 뭉뚱그리면
    "rowid가 정했다"와 "점수가 정했다"가 섞인다.
    """
    if not hits:
        return 0, None
    top = hits[0][0]
    return sum(1 for s, _ in hits if s == top), top


def hard_misinjection(q, retrieved, key_of):
    """
    🔄 rev5 — AND 규칙을 5문항 전부로 일반화.

        hard(q) = 1 if (distractor ∈ retrieved) AND (¬ all(e ∈ retrieved)) else 0

    *"distractor가 주입됐는데 evidence가 완전히 동반되지 않은 경우"*만 센다.
    이것이 **"근거를 대체해 버린 유도"**라는 실패 모드다. Q26(`X004 ∈ evidence`)은
    이 정의의 **특수 사례**가 된다 — X004가 주입돼도 F003이 함께 있으면 hard = 0.

    🔴 **rev7 (Verifier) — 색인에 없는 evidence는 조용히 빠지지 않고 터진다.**
    이전 구현은 `for e in evidence if e in key_of`로 걸렀다. 그러면 evidence가
    **전부** 미색인일 때 `all([])`이 `True`가 되어 `hard = 0`이 나온다 —
    "동반 검색됐다"가 아니라 "검사할 것이 없었다"인데 같은 값을 낸다.
    0-a가 죽인 것과 정확히 같은 종류의 **항등 0**이다. 오늘은 5문항 전부
    완전 색인이라 발화하지 않지만, 단계 3+가 `debt`를 색인하거나 evidence 목록이
    늘어나면 그때 조용히 죽는다. 그래서 지금 소리내게 만든다.
    """
    d_hit = bool(allowed_strings(distractor_ids(q), key_of) & retrieved)
    evidence = q.get("evidence", [])
    missing = [e for e in evidence if e not in key_of]
    if missing:
        raise ValueError(
            f"{q['id']}: evidence {missing}가 색인(`key_of`)에 없다 — 조용히 빼면 "
            f"`all([])`가 True가 되어 hard가 항등 0이 된다. "
            f"색인 규칙(`key_index`)을 고치거나 이 문항을 `partition`에서 제외할 것.")
    ev_all = all(key_of[e] & retrieved for e in evidence)
    return 1 if (d_hit and not ev_all) else 0


def partition(qs, key_of):
    """채점 대상 18문항과 제외 8문항을 가른다. 제외는 **매 실행 출력에 찍는다.**"""
    scored, excluded = [], []
    for q in qs:
        ev = q.get("evidence")
        if ev and any(e in key_of for e in ev):
            scored.append(q)
        else:
            reason = ("no evidence key" if not ev
                      else f"unindexed {','.join(ev)}")
            excluded.append((q["id"], reason))
    return scored, excluded


def run_cell(corpus, ledger, qs, scored, key_of, gate_fn, theta):
    """한 셀(게이트 × θ)을 돌린다. `gate_sweep.py`와 같은 방식으로 재바인딩한다."""
    M.THETA_RELEVANCE = theta
    dbf = f"{ROOT}/prototype/.prec.db"
    if os.path.exists(dbf):
        os.remove(dbf)
    m = Memory(dbf)
    seed(m)
    ingest(m, corpus, ledger, timed=False)
    m._vocab = build_vocab(m)
    Memory.gate = gate_fn

    last = corpus[-1]["seq"]
    rows, hard_rows = [], []
    sids = {q["id"] for q in scored}
    # 26문항을 **대장 순서 그대로** 훑는다 — `soak.qa_eval`과 같은 순회라야
    # 셀 값이 `gate_sweep`·`soak`와 비교 가능하다. 채점은 18개만 한다.
    for q in qs:
        if q["id"] not in sids:
            continue
        ctx = m.build_context(CHAT, q["ask"], last)
        # 🆕 단계 1 — 집합이 아니라 **순서**가 필요해졌다(`top1`·동점).
        #    `provenance`가 순서를 갖고 있지만 **점수는 `score %.2f`로 반올림돼 있어**
        #    동점 판정에 쓸 수 없다(0.401과 0.400이 같아 보인다). 그래서 점수는
        #    `retrieve()`를 한 번 더 불러 원값으로 받는다 — `retrieve()`는 순수 읽기라
        #    부작용이 없고, `build_context`가 올리는 `retrieval_count`는 점수식
        #    (`memory.py:1183`: rel · importance · `surfaced_count`)에 들어가지 않는다.
        ordered = [item for kind, item, _ in ctx.provenance if kind == "retrieved"]
        retrieved = set(ordered)
        gate_pass = bool([1 for kind, item, _ in ctx.provenance
                          if kind == "gate" and item == "통과"])
        hits = m.retrieve(CHAT, q["ask"], last)[0] if gate_pass else []
        # 두 경로가 어긋나면 조용히 지나가지 않는다 — `top1`의 근거가 무너진 것이다.
        if [r["summary"] for _, r in hits] != ordered:
            raise SystemExit(
                f"{q['id']}: retrieve()의 순서와 provenance의 순서가 다르다 — "
                f"top1/동점 진단의 전제가 깨졌다.\n  retrieve: "
                f"{[r['summary'] for _, r in hits]}\n  provenance: {ordered}")
        mis, prec = score_question(q, retrieved, key_of)
        ev_hit, ev_tot = evidence_recall_via_retrieval(q, retrieved, key_of)
        tie_n, tie_s = tie_rank1(hits)
        rows.append(dict(id=q["id"], mis=mis, n_ret=len(retrieved), prec=prec,
                         ev_hit=ev_hit, ev_tot=ev_tot, gate=gate_pass,
                         top1=top1_misinjection(q, ordered, key_of),
                         tie_n=tie_n, tie_s=tie_s))
        if q.get("distractor"):
            hard_rows.append(dict(
                id=q["id"],
                hard=hard_misinjection(q, retrieved, key_of),
                # `d_hit`은 AND 규칙의 **첫째 항**이다. F25가 밝힌 대로 0의 원인은
                # 둘째 항이 아니라 여기이므로, 진단 절이 이 값을 따로 읽는다.
                d_hit=bool(allowed_strings(distractor_ids(q), key_of) & retrieved),
                n_ret=len(retrieved)))
    _, blks = trap_injected(m, ledger, last)
    m.db.close()
    os.remove(dbf)
    return rows, hard_rows, bool(blks)


def cell_totals(rows):
    """
    🆕 단계 1 — 한 셀의 집계 4종 + 게이트 분해. **분모를 언제나 함께 돌려준다**(G15).

    `pooled`와 `top1`은 분모가 셀마다 다르다(F24: 항목 4~22 · F26: 문항 2~10).
    분모를 값과 떼어 놓으면 셀 간 절대 비교가 조용히 들어온다 — 그래서 한 dict에
    같이 담아 출력이 분모를 안 찍을 수 없게 만든다.
    """
    mis = sum(r["mis"] for r in rows)
    ret = sum(r["n_ret"] for r in rows)
    live = [r for r in rows if r["n_ret"] > 0]
    top1_rows = [r for r in live if r["top1"] is not None]
    ties = [r for r in live if r["tie_n"] > 1]
    return dict(
        mis=mis,
        ret=ret,
        # pooled = 1 − Σmis/Σ|ret|. 검색 0건 문항은 분자·분모 어디에도 없다(A4 ①).
        pooled=(1 - mis / ret) if ret else None,
        # 매크로는 **지우지 않는다.** 대신 자동 1.0의 개수를 함께 들고 다닌다(G15).
        macro=sum(r["prec"] for r in rows) / max(len(rows), 1),
        auto1=sum(1 for r in rows if r["n_ret"] == 0),
        ev_hit=sum(r["ev_hit"] for r in rows),
        ev_tot=sum(r["ev_tot"] for r in rows),
        top1=sum(r["top1"] for r in top1_rows),
        top1_n=len(top1_rows),
        ties=ties,
        gate_pass=sum(1 for r in rows if r["gate"]),
        gate_block=sum(1 for r in rows if not r["gate"]),
        pass_zero=sum(1 for r in rows if r["gate"] and r["n_ret"] == 0),
        live=len(live))


def _fmt_tie(r):
    """`Q05 — 1·2·3위 s=0.4` (F26 · 단계 1 작업 3의 형식)."""
    ranks = "·".join(str(i + 1) for i in range(r["tie_n"]))
    return f"{r['id']} — {ranks}위 s={r['tie_s']:g}"


def dispersion_report(cells) -> bool:
    """
    분산 검정 — 이 지표가 격자 축에 반응하는가. **살아 있으면 True.**

    🔴 rev7 (Verifier) — `main()`에서 분리한 이유는 두 가지다. 하나는 종료 코드가
    이 판정에 걸리게 하려는 것이고(죽은 지표가 exit 0으로 지나가면 안 된다),
    다른 하나는 **4셀 스윕을 돌리지 않고 실패 경로를 시험**할 수 있게 하려는
    것이다 — 스윕은 4셀 x 26문항이라 단위 테스트에서 돌릴 물건이 아니다.

    🔴 **단계 1 (G14 rev2) — 이 함수는 `BASE_CELL`을 읽지 않는다.** 방향 검정 절을
    `direction_test()`로 떼어낸 이유가 그것이다. 분산 판정이 기준셀에 의존하면
    **단계 0의 라벨 수리가 게이트 값을 조용히 움직인다** — 라벨을 고치는 사람은
    자기가 종료 코드를 바꿨다는 것을 모른다. 지금까지 안 움직인 것은 우연이었다.

    🔄 **단계 1 — 신규 3종으로 넓혔다.** 네 지표 중 **하나라도 FAIL이면 False**이고
    `main()`이 그것을 종료 코드 1로 바꾼다.
    """
    print("\n" + "=" * W)
    print("분산 검정 — 이 지표들이 격자 축에 반응하는가 (G14 · 기준셀 비의존)")
    print("=" * W)

    tot = {k: cell_totals(v[0]) for k, v in cells.items()}
    per_q = {}
    for k, (rows, _, _) in cells.items():
        for r in rows:
            d = per_q.setdefault(r["id"], {})
            d.setdefault("mis", set()).add(r["mis"])
            d.setdefault("ev", set()).add(r["ev_hit"])
            d.setdefault("pooled", set()).add((r["mis"], r["n_ret"]))
            d.setdefault("top1", set()).add(r["top1"])

    def judge(name, cell_val, q_key, fmt):
        """셀 간 spread > 0 **AND** 값이 다른 문항 ≥ 1. 둘 다여야 살아 있다."""
        vals = [cell_val(t) for t in tot.values()]
        obs = [v for v in vals if v is not None]
        spread = (max(obs) - min(obs)) if obs else 0
        movers = sorted(q for q, d in per_q.items() if len(d[q_key]) > 1)
        c1, c2 = spread > 0, len(movers) >= 1
        print(f"\n  {name}")
        for k, t in tot.items():
            print(f"    {CELL_LABEL[k[0]]} · θ={k[1]:.2f}   {fmt(t)}")
        print(f"    (i)  셀 간 spread = {spread:{'g' if isinstance(spread, float) else 'd'}}"
              f" > 0{'':<24}{'PASS' if c1 else 'FAIL':>8}")
        print(f"    (ii) 값이 다른 문항 {len(movers)}개 "
              f"{movers if movers else ''}{'':<4}{'PASS' if c2 else 'FAIL':>8}")
        return c1 and c2

    ok_mis = judge("misinjection@q (기존)", lambda t: t["mis"], "mis",
                   lambda t: f"{t['mis']}  (18문항 합계)")
    ok_rec = judge(f"{RECALL_NAME} (신규)", lambda t: t["ev_hit"], "ev",
                   lambda t: f"{t['ev_hit']}/{t['ev_tot']}")
    ok_pool = judge("pooled(micro) 정밀도 (신규)", lambda t: t["pooled"], "pooled",
                    lambda t: (f"{t['pooled']:.3f}  (분모 {t['ret']} 항목)"
                               if t["pooled"] is not None else "정의 안 됨 (검색 0건)"))
    ok_top1 = judge("top1_misinjection (신규)",
                    lambda t: (t["top1"] / t["top1_n"]) if t["top1_n"] else None,
                    "top1",
                    lambda t: (f"{t['top1']}/{t['top1_n']}"
                               if t["top1_n"] else "정의 안 됨 (검색 ≥1건 문항 0)"))

    alive = ok_mis and ok_rec and ok_pool and ok_top1
    if alive:
        print("\n  ✅ 네 지표 전부 살아 있다 — 격자가 읽을 숫자가 생겼다.")
    else:
        dead = [n for n, ok in [("misinjection@q", ok_mis), (RECALL_NAME, ok_rec),
                                ("pooled 정밀도", ok_pool),
                                ("top1_misinjection", ok_top1)] if not ok]
        print(f"\n  🔴 **죽은 지표: {', '.join(dead)}.** 게이트로 쓰지 않는다 — "
              f"재설계한다 (부검 시나리오 4).")
    # 🔴 rev7 (Verifier) — 사람만 읽는 경고로는 부족하다. 종료 코드로 가르지 않으면
    # `run_all.py`처럼 코드만 보는 호출부가 **죽은 지표를 통과로 읽고 지나간다.**
    # 출력은 그대로 두고, `main()`이 이 값을 종료 코드로 바꾼다.
    return alive


def direction_test(cells):
    """
    방향 검정 절 — **`BASE_CELL`을 읽는 유일한 곳**이다 (G14 rev2).

    ⚠️ Critic M4 — `|retrieved(q)| = 0`이면 정밀도가 1.0이다.
    **아무것도 안 꺼내는 것이 만점**이므로 방향 검정 대상에서 뺀다.

    🔴 **판정을 돌려주지 않는다.** 이 절이 종료 코드에 기여하면 라벨(기준셀) 변경이
    게이트를 움직이게 된다 — `dispersion_report`에서 이 절을 떼어낸 이유 그 자체다.
    """
    base_rows = cells[BASE_CELL][0]
    zero = [r["id"] for r in base_rows if r["n_ret"] == 0]
    live = [r["id"] for r in base_rows if r["n_ret"] > 0]
    print(f"\n  방향 검정 대상 — 기준셀 {CELL_LABEL[BASE_CELL[0]]}·θ={BASE_CELL[1]}"
          f"에서 |retrieved(q)| > 0 인 문항 {len(live)}개")
    print(f"    제외 ({len(zero)}개, 0건이라 정밀도가 자동 1.0): "
          f"{zero if zero else '없음'}")
    print("    ⚠️ 이 절은 **종료 코드에 기여하지 않는다** — 기준셀 라벨이 게이트를 "
          "움직이면 안 된다 (G14).")


def unreachability_diagnostic(corpus, ledger, qs, scored, key_of):
    """
    🆕 단계 1 작업 5 — `hard_misinjection`이 **파라미터로 도달 불가능**하다는 것을
    매 실행 다시 보인다 (F25 · 결정 B1 기각의 근거).

    두 축으로 잰다.
      ① τ 사다리 {0.2, 0.15, 0.1, 0.05} · G3 · θ=0.05  → hard 합계
      ② τ=0 · θ=0 · 게이트 전개(G1) · **TOP_K=1**      → 5문항의 `d_hit`

    ②가 결정적이다. AND 규칙의 **첫째 항**(`distractor ∈ retrieved`)이 1등 자리에서
    한 번도 안 켜진다 — 즉 0의 이유는 *"근거가 늘 동반됐다"*가 아니라
    **"유도가 근거를 이길 수 없다"**이다. τ를 격자에 올려도 살아나지 않는다.

    ⚠️ 전역을 넷 재바인딩하므로 `try/finally`로 되돌린다(G13 · `orig_gate, orig_t`를 되돌리는 `:572-580`의 패턴).
       G16은 **기본값을 바꾸지 않는다**이고, 진단이 끝난 뒤 값이 원래대로면 지켜진다.
    """
    print("\n" + "-" * W)
    print("도달 불가능성 진단 — `hard`의 0은 τ 때문이 아니다 (F25)")
    print("-" * W)
    orig = (Memory.gate, M.THETA_RELEVANCE, M.TAU_IMPORTANCE, M.TOP_K)
    try:
        print(f"  ① τ 사다리 (게이트=G3(프로덕션) · θ=0.05 · TOP_K={M.TOP_K})")
        for tau in TAU_LADDER:
            M.TAU_IMPORTANCE = tau
            _, hard_rows, _ = run_cell(corpus, ledger, qs, scored, key_of,
                                       g_content, 0.05)
            hs = sum(h["hard"] for h in hard_rows)
            dh = sum(h["d_hit"] for h in hard_rows)
            print(f"    τ={tau:<6}hard 합계 {hs}   d_hit {dh}/{len(hard_rows)}")

        M.TAU_IMPORTANCE, M.TOP_K = 0.0, 1
        _, hard_rows, _ = run_cell(corpus, ledger, qs, scored, key_of,
                                   g_always, 0.0)
        print("\n  ② TOP_K=1 · τ=0 · θ=0 · G1(게이트 전개) — 1등 자리 전수")
        for h in hard_rows:
            print(f"    {h['id']:<7}d_hit={h['d_hit']!s:<7}hard={h['hard']}   "
                  f"|retrieved|={h['n_ret']}")
        print(f"    → d_hit True {sum(h['d_hit'] for h in hard_rows)}"
              f"/{len(hard_rows)}문항. **1등 자리를 distractor가 한 번도 "
              f"못 가져간다**면 그 실패 모드는 이 코퍼스에서 도달 불가다.")
    finally:
        Memory.gate, M.THETA_RELEVANCE, M.TAU_IMPORTANCE, M.TOP_K = orig


def main():
    corpus, ledger, qs = load()
    key_of = key_index(ledger)
    scored, excluded = partition(qs, key_of)

    # 조용한 제외는 이 계획이 §0.5에서 고발한 것과 같은 종류의 사고다. 무조건 찍는다.
    header = (f"scored {len(scored)}/{len(qs)} · excluded: "
              f"Q11(debt D001), Q14,Q17-Q22(no evidence key)")
    print("=" * W)
    print("질문별 정밀도 — 오주입 지표 교체 (단계 0-g)")
    print("=" * W)
    print(f"\n{header}\n")
    if header != EXPECTED_HEADER:
        raise SystemExit(f"제외 집합이 움직였다 — A8 위반 의심.\n"
                         f"  기대: {EXPECTED_HEADER}\n  실제: {header}\n"
                         f"  제외 내역: {excluded}")
    print(f"  제외 내역 (실측): " + ", ".join(f"{i}({r})" for i, r in excluded))
    print("  → 이 8문항은 `allowed_strings`가 공집합이라 넣으면 "
          "**모든 검색 항목이 오주입**으로 세어진다.")
    print("     그러면 집계는 정밀도가 아니라 **검색 분량**을 재고, "
          "트립와이어는 항상 참이라 발화하지 않는다.")

    orig_gate, orig_t = Memory.gate, M.THETA_RELEVANCE
    cells = {}
    try:
        for gname, gfn in CELLS:
            for th in THETAS:
                cells[(gname, th)] = run_cell(corpus, ledger, qs, scored,
                                              key_of, gfn, th)
    finally:
        Memory.gate, M.THETA_RELEVANCE = orig_gate, orig_t

    for (gname, th), (rows, hard_rows, trap) in cells.items():
        t = cell_totals(rows)
        print("\n" + "-" * W)
        print(f"셀 {CELL_LABEL[gname]} · θ={th:.2f}")
        # 🆕 실행 구성 스탬프 (G15 · §5.4) — *"이 값은 어느 실행 구성의 값인가"*를
        #    값 옆이 아니라 **값 위**에 박는다. F21이 반복되지 않게 하는 최소 장치다.
        #    θ에는 모집단과 자르는 비율이 붙는다 (G12).
        print(f"  구성: 게이트={CELL_LABEL[gname]} · 모드=lexical · "
              f"θ={th}(컷 {THETA_CUT_378.get(th, '측정 안 됨')}/{POPULATION_378}) · "
              f"τ={M.TAU_IMPORTANCE} · TOP_K={M.TOP_K}")
        print("-" * W)
        print(f"  {'문항':<7}{'오주입':>7}{'|retrieved|':>13}{'정밀도':>9}"
              f"{'근거회상':>10}{'게이트':>8}{'top1':>7}{'동점':>6}")
        for r in rows:
            rec = f"{r['ev_hit']}/{r['ev_tot']}"
            print(f"  {r['id']:<7}{r['mis']:>7}{r['n_ret']:>13}{r['prec']:>9.3f}"
                  f"{rec:>10}"
                  f"{'통과' if r['gate'] else '차단':>8}"
                  f"{('-' if r['top1'] is None else r['top1']):>7}"
                  f"{(r['tie_n'] if r['tie_n'] > 1 else '-'):>6}")
        hard = sum(h["hard"] for h in hard_rows)
        rec_tot = f"{t['ev_hit']}/{t['ev_tot']}"
        pooled_s = "정의 안 됨" if t["pooled"] is None else f"{t['pooled']:.3f}"
        top1_s = f"{t['top1']}/{t['top1_n']}" if t["top1_n"] else "정의 안 됨"
        print(f"  {'-' * 60}")
        print(f"  {'misinjection@q':<26}{t['mis']:>10}   (18문항 합계)")
        print(f"  {RECALL_NAME:<26}{rec_tot:>10}"
              f"   (근거 id 합계 — 18문항 전부에 정의됨)")
        print(f"  {'pooled(micro) 정밀도':<26}{pooled_s:>10}"
              f"   (1 − {t['mis']}/{t['ret']} · 분모 {t['ret']} 항목 — 셀마다 다르다)")
        print(f"  {'macro 정밀도':<26}{t['macro']:>10.3f}"
              f"   (자동 1.0 {t['auto1']}개 포함 — 검색 0건이 만점을 받는다)")
        print(f"  {'top1_misinjection':<26}{top1_s:>10}"
              f"   (분모 = 검색 ≥1건 문항 수)")
        ties = t["ties"]
        print(f"  {'  └ 동점 병기 (F26)':<26}"
              f"{f'동점 {len(ties)}건':>10}   "
              f"{('; '.join(_fmt_tie(r) for r in ties) if ties else '없음')}")
        if ties:
            # 🔄 **레인 J — 레인 G가 오케스트레이터로 올린 세 건 중 하나를 여기서 닫는다.**
            #    레인 G는 이 두 줄을 *"값이 아니라 설명이 틀렸다"*고 적어 두고
            #    고치지 않았다 — 출력 줄이라(`precision-4cells.txt:167`) 고치면
            #    *"여섯 스크립트 바이트 동일"* 수용 기준을 밟기 때문이다. 그 기준은
            #    레인 G의 것이고 이 라운드의 것이 아니다. **틀린 설명을 출력에 두는
            #    쪽이 더 비싸다** — 이 저장소가 표류 인용으로 다섯 번 데었다.
            #    고친 것 둘: `memory.py:839` → `:938`, 그리고 **문장 자체**
            #    (후속 10이 닫혀 동점의 1등은 이제 rowid를 안 따른다).
            print("       ⚠️ 동점은 `event_id` 오름차순이 가른다(`memory.py:1189`의 `scored.sort`는 "
                  "`(-s, event_id)`로 정렬한다 — 후속 10).")
            print("          값은 안 움직였다: `event_id`가 곧 rowid다. 없어진 것은 "
                  "**SELECT 반환 순서에 대한 의존**이다.")
        print(f"  {'hard_misinjection':<26}{hard:>10}   "
              f"(distractor 5문항, AND 규칙) · **{RETIRED_HARD_NOTE}**")
        print(f"  {'trap_injected':<26}{'주입됨' if trap else '없음':>10}"
              f"   (soak.trap_injected — 질문이 아니라 잡담 경로)")
        # 🆕 작업 4 — 게이트 분해 (F22). *"퇴화의 주된 원인은 검색기가 아니라 게이트다."*
        print(f"\n  게이트 분해 — 통과 {t['gate_pass']} · 차단 {t['gate_block']} · "
              f"통과했지만 검색 0건 {t['pass_zero']} · 검색 ≥1건 {t['live']}"
              f"   (합 {t['gate_block'] + t['gate_pass']}/18)")
        print(f"\n  hard(q) 문항별 (겹침 규약: 하드 케이스는 misinjection@q에도 "
              f"그대로 포함해 센다)")
        for h in hard_rows:
            print(f"    {h['id']:<7}hard={h['hard']}   d_hit={h['d_hit']!s:<7}"
                  f"|retrieved|={h['n_ret']}")

    # ── 분산 검정 (🔴 rev3: 스칼라 `> 0`을 셀 간 분산으로 교체) ────────
    alive = dispersion_report(cells)
    direction_test(cells)

    # ── hard_misinjection 은퇴 (🔄 단계 1 작업 5 · 결정 B3) ─────────────────
    hard_vals = [h["hard"] for _, hr, _ in cells.values() for h in hr]
    print("\n" + "-" * W)
    print(f"hard_misinjection — 4셀 × 5문항 = {len(hard_vals)}개 값: {hard_vals}")
    print(f"  **{RETIRED_HARD_NOTE}** — `top1_misinjection`이 이 자리를 물려받았다"
          " (결정 B3).")
    if not any(hard_vals):
        print("  ⚠️ **항등 0 지표 — 게이트로 쓰지 않는다.**")
        # 🔄 레인 J — 레인 G가 올린 세 건 중 둘째. `memory.py:158` → **`:159`**
        #    (`import embedding` 한 줄이 위에 들어가 전부 +1). 출력 줄이지만
        #    (`precision-4cells.txt:226`) 위와 같은 이유로 고친다.
        print("     🔴 선행 라운드는 원인을 `TAU_IMPORTANCE = 0.2`"
              "(memory.py:159)로 지목했다. **실측이 그 가설을 반증했다**(F25) —")
        print("     τ를 0까지 열고 θ=0·게이트 전개(G1)·TOP_K=1로 조여도 0이다. "
              "아래 진단 절이 그것을 매 실행 다시 보인다.")
        print("     진짜 원인은 **distractor가 근거보다 위로 못 올라간다**는 것이고, "
              "그것은 파라미터가 아니라 `eval/`의 설계다(A8 — 고치지 않는다).")
        print("     → 계산과 출력은 **유지한다**: 0이 아닌 값이 나오면 하니스나 "
              "대장이 움직인 것이라 **회귀 탐지기**로서의 값이 남는다.")
    else:
        print("  🔴 **0이 아니다.** 은퇴한 지표가 값을 냈다 = 하니스나 대장이 "
              "움직였다는 뜻이다. `eval/`(A8)과 `partition`을 먼저 확인할 것.")
    unreachability_diagnostic(corpus, ledger, qs, scored, key_of)
    print("=" * W)
    # 분산 검정이 깨지면 **0으로 끝내지 않는다.** `hard_misinjection`의 항등 0은
    # 예상된 관측이라 종료 코드를 바꾸지 않지만, 분산 검정은 이 지표가 살아 있다는
    # 전제 그 자체다 — 그것이 무너지면 뒤 단계가 읽을 숫자가 없다.
    return 0 if alive else 1


if __name__ == "__main__":
    sys.exit(main())
