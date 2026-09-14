# -*- coding: utf-8 -*-
"""
corpus2_probe.py — **두 번째 코퍼스**에 기존 계측기를 그대로 통과시킨다.

## 왜 이 파일이 있나

이 저장소의 모든 검증이 코퍼스 하나(`eval/`)에서 돌았다. 한국어 · 롤플레이 ·
등장인물 둘(지우·서준) · 단일 줄거리 · 24세션 720턴 · 합성. **다른 코퍼스가
존재한 적이 없다.** 그러므로 *"휴리스틱이 일반화되는가"*는 약하게 검증된 것이
아니라 **한 번도 검증된 적이 없다.**

`eval2/`가 두 번째 코퍼스이고, 그 **사전 등록**(무엇을 다르게 두고 무엇을 같게
뒀는가, 그리고 왜)은 `eval2/README.md` §1·§2에 있다. 이 파일은 그 코퍼스에
계측기를 **고치지 않고** 통과시켜 «휴리스틱이 무엇에 붙어 있는지»를 찍는다.

## 🔴 무변경 규약

아래 전부 **import해서 그대로 부른다.** 이 파일은 원본을 한 줄도 고치지 않는다.

    prototype/memory.py   : Memory.gate · Memory._recall_vocab · Memory._roots ·
                            _stem · _ENDINGS · _PARTICLE · bigrams · coverage ·
                            TAU_IMPORTANCE · THETA_RELEVANCE
    prototype/soak.py     : seed · ingest
    experiments/scoring.py: survived_frozen · survived_v2 · survived_v3 · UBIQUITOUS
    experiments/rel_dist.py: theta_at · actual_cut
    experiments/precision.py: key_index · partition

코퍼스를 가리키는 방법은 **경로 인자뿐**이다 (`CORPORA` dict). `eval/`은 읽기만
한다 (A8).

## 🔴 두 코퍼스 사이에 화살표를 그리지 않는다

두 열을 **나란히** 놓고 각 열 제목에 **코퍼스 이름을 박는다** (실험 27 `TitleRule`의
정신). `a → b`는 «같은 것이 변했다»를 뜻하는데 여기서는 **모집단이 다르다.**
축을 선언하고 만든 코퍼스이므로 «그 축에서 다른 것»은 관측이 아니라 전제다.
말할 수 있는 것은 **«그 축 위에서 휴리스틱이 어떻게 반응하는가»**뿐이다.

## 실행 (G11)

    PYTHONIOENCODING=utf-8 python -B eval2/gen_corpus2.py        # 코퍼스 재생성
    PYTHONIOENCODING=utf-8 python -B experiments/corpus2_probe.py
    PYTHONIOENCODING=utf-8 python -B -m unittest discover -s experiments/tests \\
        -p "test_corpus2_probe.py" -v
"""
import json
import os
import re
import sys

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "prototype"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import memory as M                                          # noqa: E402
from memory import Memory                                   # noqa: E402
import scoring as SC                                        # noqa: E402
import rel_dist as RD                                       # noqa: E402
import precision as P                                       # noqa: E402
from soak import seed, ingest, CHAT                         # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = 88

# ── 코퍼스 등록 (경로 인자 — 원본 계측기를 고치지 않는 유일한 손잡이) ──────
#
# 🔴 순서가 곧 열 순서이고, **열 제목은 언제나 이 키**다. 숫자만 있는 표를
#    만들지 않는다 — 어느 코퍼스의 값인지가 표에서 사라지면 두 모집단이 조용히
#    한 모집단이 된다.
CORPORA = {
    "eval":  dict(corpus="eval/corpus/corpus.jsonl",
                  ledger="eval/fact-ledger.yaml",
                  questions="eval/questions.yaml"),
    "eval2": dict(corpus="eval2/corpus/corpus.jsonl",
                  ledger="eval2/fact-ledger.yaml",
                  questions="eval2/questions.yaml"),
}
NAMES = list(CORPORA)

# 🔴 축 ①의 검사 대상. `eval2`에서 이 두 이름의 출현이 0이어야 «이름 축»이
#    성립한다. 0이 아니면 그 뒤의 UBIQUITOUS 관측은 전부 무의미하다.
BANNED_IN_EVAL2 = ("지우", "서준")

# 다이제스트 규칙 (4절). **LLM 요약이 아니다** — 아래 `digests()` 주석 참조.
DIGEST_CHARS = 150

# `_roots` 잔여 표지 — `습니다`를 뗀 뒤에도 **더 이상 안 깎이는** 마지막 글자.
#
# 🔴 **`었`·`았`·`였`·`겠`은 여기 없다. 첫 판에는 있었고, 그것은 죽은 항목이었다.**
#    그 넷은 `_ENDINGS`의 첫 그룹 `(었|았|였|겠|시|으)?`에 있고, 뒤 그룹(`습니다`)이
#    함께 매치되면 **같이 벗겨진다** — 실측: `받았습니다 → 받` · `하겠습니다 → 하` ·
#    `늘었습니다 → 늘`. 즉 «니다로 끝나는데 `았`이 남는» 어절은 존재할 수 없고,
#    넣어두면 «절대 발화하지 않는 검사 항목»이 된다. 남기는 쪽이 안전해 보이지만
#    그것이 이 저장소가 여러 번 만든 항등 지표다.
#
# 남은 것은 두 갈래이고 둘 다 실측에서 나왔다:
#   ① 축약 과거 (`되+었 → 됐`, `가+았 → 갔`, `올리+었 → 올렸` …) — 표에 없어 안 깎인다
#      실측: `보류됐습니다 → 보류됐` · `올라갔습니다 → 올라갔` · `올렸습니다 → 올렸`
#   ② 서술격/`ㅂ니다` 어간 (`입니다`·`립니다`) — `입`·`립`이 통째로 남는다
#      실측: `40명입니다 → 40명입` · `부탁드립니다 → 부탁드립` · `v2.4입니다 → v24입`
RESIDUAL_TAIL = ("됐", "갔", "졌", "혔", "왔", "췄", "렸", "겼", "뒀", "났", "셨",
                 "입", "립")


# ══════════════════════════════════════════════════════════════════════
# 적재
# ══════════════════════════════════════════════════════════════════════

def load(name):
    """
    `precision.load()`를 못 쓴다 — 그 함수는 `eval/` 경로를 **리터럴로** 들고 있다
    (`precision.py:148-152`). 고치지 않기로 했으므로(A8·무변경 규약) 같은 세 파일을
    **같은 순서로** 여기서 연다. 반환 형태는 `precision.load()`와 같다.
    """
    c = CORPORA[name]
    corpus = [json.loads(l) for l in
              open(os.path.join(ROOT, c["corpus"]), encoding="utf-8")]
    with open(os.path.join(ROOT, c["ledger"]), encoding="utf-8") as f:
        ledger = yaml.safe_load(f)
    with open(os.path.join(ROOT, c["questions"]), encoding="utf-8") as f:
        qs = yaml.safe_load(f)["qa_questions"]
    return corpus, ledger, qs


def build(name, corpus, ledger, tag="probe"):
    """`soak.seed` + `soak.ingest`를 **무변경**으로 부른다. DB는 코퍼스마다 따로."""
    dbf = os.path.join(ROOT, "prototype", f".corpus2-{name}-{tag}.db")
    if os.path.exists(dbf):
        os.remove(dbf)
    m = Memory(dbf)
    seed(m)
    ingest(m, corpus, ledger, timed=False)
    return m, dbf


def ledger_items(ledger):
    """채점기에 먹이는 **항목 텍스트**. `soak.qa_eval`/`precision.key_index`가
    쓰는 것과 같은 출처(`facts[*].text` + `events[*].text`)."""
    return ([f["text"] for f in ledger.get("facts", [])] +
            [e["text"] for e in ledger.get("events", [])])


def index_rows(m):
    return [dict(r) for r in m.db.execute(
        "SELECT event_id, summary, importance, emotional_weight FROM event"
        " WHERE chat_id=? AND user_deleted=0 ORDER BY event_id", (CHAT,))]


def rule(title=""):
    print("\n" + "=" * W)
    if title:
        print(title)
        print("=" * W)


def two_col(header, rows):
    """열 제목에 **코퍼스 이름을 박는** 표. 화살표를 쓰지 않는다."""
    print(f"  {header:<44} {NAMES[0]:>18} {NAMES[1]:>18}")
    print("  " + "-" * (44 + 38))
    for label, a, b in rows:
        print(f"  {label:<44} {a:>18} {b:>18}")


# ══════════════════════════════════════════════════════════════════════
# 0. 축 ① 검사 — 이름이 정말 갈렸는가
# ══════════════════════════════════════════════════════════════════════

def axis1_check(corpora):
    """
    🔴 **이 검사가 실패하면 2절 전체가 무의미하다.** `UBIQUITOUS = {"지우"}`가
    이 코퍼스에서 무엇을 하는지 보려면 «지우가 없다»가 먼저 참이어야 한다.
    조용히 넘어가지 않고 여기서 죽는다 (P5).
    """
    corpus, ledger, qs = corpora["eval2"]
    blob = "\n".join([r["text"] for r in corpus] +
                     ledger_items(ledger) +
                     [q["ask"] for q in qs] +
                     [yaml.safe_dump(ledger.get("character", {}),
                                     allow_unicode=True),
                      yaml.safe_dump(ledger.get("user_persona", {}),
                                     allow_unicode=True)])
    hits = {n: blob.count(n) for n in BANNED_IN_EVAL2}
    if any(hits.values()):
        raise AssertionError(
            f"축 ① 위반 — eval2에 금지 이름이 있다: {hits}. "
            f"이 상태에서는 UBIQUITOUS 관측이 성립하지 않는다.")
    return hits


# ══════════════════════════════════════════════════════════════════════
# 1. 게이트
# ══════════════════════════════════════════════════════════════════════

def gate_breakdown(m, corpus):
    """
    `Memory.gate`를 **무변경**으로 부른다. 분모는 `soak.replay`와 같은 정의 —
    `role == "user"`인 턴 (`soak.py:112`).
    """
    from collections import Counter
    reasons = Counter()
    fired = 0
    n = 0
    for r in corpus:
        if r["role"] != "user":
            continue
        n += 1
        ok, why = m.gate(r["text"])
        reasons[why] += 1
        fired += bool(ok)
    return n, fired, reasons


def gate_by_kind(m, corpus):
    """
    게이트 통과를 **턴의 종류별로** 가른다.

    🔴 이것이 게이트의 «정밀도»에 해당한다. 심긴 항목 턴에서 통과하는 것은
    일이고, 순수 노이즈에서 통과하는 것은 헛일이다. 발화율 하나만 보면 그 둘이
    섞인다 — 분모를 종류별로 갈라야 «게이트가 무엇을 아끼는가»가 보인다.
    분류는 코퍼스 자신의 `kind`/`planted_id` 필드를 쓴다(양쪽 스키마가 같다).
    """
    out = {}
    for r in corpus:
        if r["role"] != "user":
            continue
        grp = ("심긴 항목" if r["planted_id"] else
               "하드 네거티브" if r["kind"].startswith("hard_neg") else "순수 노이즈")
        ok, _ = m.gate(r["text"])
        d = out.setdefault(grp, [0, 0])
        d[0] += 1
        d[1] += bool(ok)
    return out


def past_ref_source(m, corpus):
    """
    «과거 참조 표현»으로 통과한 턴이 **심긴 항목 턴인가 아닌가.**

    🔴 왜 이걸 세는가: `gen_corpus.render`가 사실을 `"{text}. 말했었나?"`로 찍고,
    그 `말했`이 게이트의 정규식에 그대로 걸린다. 즉 eval의 «과거 참조 표현»
    발화 중 상당수는 **언어 현상이 아니라 생성 템플릿의 산물**이다.
    eval2의 템플릿은 `"{text}. 이거 맞죠?"`이고 그것은 이 레인이 골랐다.
    → 두 코퍼스의 이 줄을 «자연 발생 빈도의 차이»로 읽으면 안 된다.
    """
    planted = other = 0
    for r in corpus:
        if r["role"] != "user":
            continue
        ok, why = m.gate(r["text"])
        if ok and why == "과거 참조 표현":
            if r["planted_id"]:
                planted += 1
            else:
                other += 1
    return planted, other


def vocab_curve(name, corpus, ledger, points=6):
    """
    `|_recall_vocab|`가 자라는 곡선.

    🔴 **행을 하나씩 INSERT하지 않는다.** 그러면 `soak.ingest`의 삽입 SQL을 이
    파일이 **다시 적게** 되고, 그 사본이 원본과 갈라지는 것이 이 저장소의 F12다.
    대신 전량 적재한 뒤 `user_deleted`를 1로 눕히고 `occurred_at` 순서로 다시
    세운다 — `_recall_vocab` 자신이 `user_deleted=0`만 읽으므로(`memory.py:1036`)
    이것이 «그때까지 저장된 것»과 같은 상태다.

    함께 찍는 게이트 발화율의 분모는 **언제나 전체 user 턴**이다 (부분 색인에서도
    같은 분모) — 분모가 같이 움직이면 곡선이 무엇의 함수인지 갈리지 않는다.
    """
    m, dbf = build(name, corpus, ledger, tag="curve")
    ids = [r["event_id"] for r in m.db.execute(
        "SELECT event_id FROM event WHERE chat_id=? ORDER BY occurred_at, event_id",
        (CHAT,))]
    m.db.execute("UPDATE event SET user_deleted=1 WHERE chat_id=?", (CHAT,))
    m.db.commit()
    total = len(ids)
    marks = sorted({0} | {round(total * i / points) for i in range(1, points + 1)})
    out, seen = [], 0
    for mk in marks:
        while seen < mk:
            m.db.execute("UPDATE event SET user_deleted=0 WHERE event_id=?",
                         (ids[seen],))
            seen += 1
        m.db.commit()
        n_user, fired, _ = gate_breakdown(m, corpus)
        out.append((seen, len(m._recall_vocab), fired, n_user))
    m.db.close()
    os.remove(dbf)
    return out


# ══════════════════════════════════════════════════════════════════════
# 2. UBIQUITOUS
# ══════════════════════════════════════════════════════════════════════

def ubiquitous_effect(ledger):
    """
    `scoring.UBIQUITOUS`가 이 코퍼스의 항목에서 **실제로 걷어내는 어근 수**.

    `scoring._clean_roots`를 그대로 부르고, 같은 항목에 대해 «편재 어근 제외»만
    뺀 집합과 비교한다. 차이가 0이면 그 상수는 이 코퍼스에서 **아무것도 안 한다.**
    """
    items = ledger_items(ledger)
    removed = 0
    items_touched = 0
    for it in items:
        raw = {r for r in Memory._roots(it) if len(r) > 1}
        clean = SC._clean_roots(it)
        d = len(raw) - len(clean)
        removed += d
        items_touched += bool(d)
    # `UBIQUITOUS`가 담고 있는 어근이 항목 몇 개에 실제로 나오는가
    hits = {u: sum(1 for it in items if u in Memory._roots(it))
            for u in SC.UBIQUITOUS}
    return len(items), items_touched, removed, hits


def induce_ubiquitous(ledger, min_frac=0.40, top=6):
    """
    **이 코퍼스에서 편재 어근을 유도하면 무엇이 나오는가.**

    정의: 어근 r의 항목 빈도 df(r) = |{항목 : r ∈ _roots(항목), len(r) > 1}|.
    `UBIQUITOUS`에 들어갈 후보는 df/|항목| ≥ `min_frac`인 것.

    🔴 `min_frac`의 출처를 값 옆에 둔다 (G15): `eval`에서 `지우`의 df 비율이
    기준선이다. 그 비율 **이상**인 어근만 «편재»라고 부른다 — 문턱을 이
    코퍼스에서 새로 고르면 그것은 유도가 아니라 취향이다.
    """
    from collections import Counter
    items = ledger_items(ledger)
    df = Counter()
    for it in items:
        for r in {x for x in Memory._roots(it) if len(x) > 1}:
            df[r] += 1
    n = len(items)
    # 🔄 **동점을 어근으로 깬다** (wave2 · T3). 여기 있던 것은 `df.most_common(top)`
    #    이었고, 그 동점 순서는 삽입 순서다 — 그런데 위 루프가 **집합**을 돌며 `df`를
    #    채우므로 삽입 순서가 `PYTHONHASHSEED`의 함수였다. eval2의 df=3은 **7종**
    #    공동인데 칸은 5개라, 여섯째 줄의 정체가 실행마다 `PG사`·`번째`·`미팅`으로
    #    갈렸다(앞 레인이 세 번 돌려 세 번 다름을 봤다). `retrieve()`의 동점 조항이
    #    `(-s, event_id)`로 푼 것과 같은 정신이다 — **더 나은 순위가 아니라 재현 가능한
    #    순위**다. 칸이 동점 한가운데서 잘리는 것 자체는 안 고친다: 그 사실은 호출부가
    #    `tie_cut()`으로 **찍는다.**
    ordered = sorted(df.items(), key=lambda kv: (-kv[1], kv[0]))
    ranked = [(r, c, c / n) for r, c in ordered[:top]]
    induced = {r for r, c, f in [(r, c, c / n) for r, c in df.items()]
               if f >= min_frac}
    return n, ranked, induced


def tie_cut(ledger, ranked):
    """
    `ranked`의 마지막 칸이 **동점 한가운데서 잘렸는가** — 잘렸다면 칸 밖으로 밀린
    같은 df의 어근들(정렬해서). 안 잘렸으면 `(df, [])`.

    칸 수(`top`)는 표의 모양이지 모집단의 경계가 아니다. 잘린 동점을 안 찍으면
    «상위 6»이 «이 6개가 나머지보다 위»로 읽힌다 — 실제로는 같은 자리에 더 있다.
    """
    if not ranked:
        return None, []
    _, full, _ = induce_ubiquitous(ledger, min_frac=0.0, top=10 ** 6)
    last = ranked[-1][1]
    shown = {r for r, _, _ in ranked}
    return last, sorted(r for r, c, _ in full if c == last and r not in shown)


def rescore_with(ledger, ubiq, digs):
    """
    다른 편재 집합으로 **다시 채점**한다.

    🔴 **`scoring.py`를 고치지 않는다.** 모듈 전역을 재바인딩하고 `try/finally`로
    되돌린다 — `gate_sweep.py:168-169`이 `THETA_RELEVANCE`에 쓰는 것과 같은 G13
    패턴이다. `UBIQUITOUS`는 `_clean_roots` 안에서 **이름으로** 읽히므로
    재바인딩이 그대로 먹는다.

    ⚠️ `digs`를 **반드시 넘겨야 한다.** 기본 다이제스트를 모듈 상태로 숨겨두면
       «어느 다이제스트로 잰 숫자인가»가 호출부에서 사라진다.
    """
    saved = SC.UBIQUITOUS
    try:
        SC.UBIQUITOUS = set(ubiq)
        return score_all(ledger, digs=digs)
    finally:
        SC.UBIQUITOUS = saved
        assert SC.UBIQUITOUS is saved, "G13 — 재바인딩이 되돌려지지 않았다"


# ══════════════════════════════════════════════════════════════════════
# 3. `_roots` · `_stem`이 깨지는 자리
# ══════════════════════════════════════════════════════════════════════

def words_of(corpus, ledger, qs):
    """코퍼스·대장·문항에 실제로 나온 **어절**(공백 단위) 전부."""
    texts = ([r["text"] for r in corpus] + ledger_items(ledger) +
             [q["ask"] for q in qs])
    out = []
    for t in texts:
        out += t.split()
    return out


def root_of(word):
    """`Memory._roots`를 **어절 하나**에 적용한 결과 (0개 또는 1개)."""
    r = Memory._roots(word)
    return next(iter(r)) if r else None


def breakage(corpus, ledger, qs):
    """
    깨진 자리를 **세 종류**로 나눠 센다. 분모는 **서로 다른 어절 수**다 (G15).

      ① 길이 1 탈락 : `_roots`가 `len(w) < 2`에서 `continue`로 버린 어절
      ② 잔여 표지    : `습니다`를 뗀 뒤 어근이 `RESIDUAL_TAIL`로 끝나 더 안 깎이는 것
      ③ 영문·숫자   : 한글이 없는 어절이 어근이 됐을 때 그 모양

    ⚠️ ②의 판정은 **규칙이지 정답이 아니다.** `RESIDUAL_TAIL`의 두 갈래(축약 과거 ·
       `입/립`)만 세고, 그 밖의 깨짐은 안 센다. **과소계수 쪽으로** 틀리게 골랐다 —
       상수 정의부의 주석이 무엇을 왜 뺐는지의 정본이다.
    """
    seen = {}
    for w in words_of(corpus, ledger, qs):
        seen.setdefault(w, root_of(w))
    dropped = {w for w, r in seen.items() if r is None}
    residual = {w: r for w, r in seen.items()
                if r and r.endswith(RESIDUAL_TAIL) and "니다" in w}
    nonhan = {w: r for w, r in seen.items()
              if r and not re.search(r"[가-힣]", r)}
    return seen, dropped, residual, nonhan


def pair_probe(pairs):
    """«같은 것을 가리키는 두 표현»이 `_roots`로 만나는가. 실물 대조."""
    out = []
    for a, b in pairs:
        ra, rb = Memory._roots(a), Memory._roots(b)
        out.append((a, b, sorted(ra & rb), sorted(ra ^ rb)))
    return out


# ══════════════════════════════════════════════════════════════════════
# 4. 세 채점기
# ══════════════════════════════════════════════════════════════════════

def digests(corpus, ledger):
    """
    세션마다 **추출식 다이제스트** 하나.

    🔴 **이것은 LLM 요약이 아니다.** 규칙은 *"그 세션에서 심긴 항목의 텍스트를
    순서대로 잇고 `DIGEST_CHARS`자에서 자른다"*이고, 두 코퍼스에 **같은 규칙**을
    쓴다. 그러므로 여기 숫자는 실험 19/20(Gemini·로컬 LLM 요약)의 숫자와
    **같은 것이 아니다** — 그 표와 나란히 놓지 않는다. 여기서 보는 것은 오직
    ***세 채점기가 이 코퍼스에서도 같은 순서인가***뿐이다.

    LLM을 안 쓰는 이유는 `eval2/README.md` §3과 같다 — 재생성이 결정적이어야
    G11이 산다.
    """
    by_s = {}
    for r in corpus:
        if r["planted_id"]:
            by_s.setdefault(r["session"], []).append(r["text"])
    return {s: " ".join(v)[:DIGEST_CHARS] for s, v in sorted(by_s.items())}


def score_all(ledger, digs):
    """세 채점기를 **무변경**으로 (다이제스트 × 전체 항목)에 돌린다."""
    items = ledger_items(ledger)
    n_pairs = len(digs) * len(items)
    fr = v2 = v3 = un2 = un3 = 0
    v2_sets, v3_sets, fr_sets = [], [], []
    for s, text in digs.items():
        f = SC.survived_frozen(text, items)
        a = SC.survived_v2(text, items)
        b = SC.survived_v3(text, items)
        fr += len(f); v2 += len(a.survived); v3 += len(b.survived)
        un2 += len(a.unscorable); un3 += len(b.unscorable)
        fr_sets.append((s, set(f)))
        v2_sets.append((s, set(a.survived), set(a.unscorable)))
        v3_sets.append((s, set(b.survived), set(b.unscorable)))
    return dict(n_digests=len(digs), n_items=len(items), n_pairs=n_pairs,
                frozen=fr, v2=v2, v3=v3, un2=un2, un3=un3,
                fr_sets=fr_sets, v2_sets=v2_sets, v3_sets=v3_sets)


def invariants(res):
    """`scoring.py`가 **문서로 주장하는 것**이 이 코퍼스에서도 참인가.

      · `v3.survived ⊆ v2.survived`   (survived_v3 독스트링)
      · `v3.unscorable == v2.unscorable` (같은 곳 — "분모가 갈라지지 않는다")
    """
    subset = all(c <= b for (_, b, _), (_, c, _)
                 in zip(res["v2_sets"], res["v3_sets"]))
    same_den = all(u2 == u3 for (_, _, u2), (_, _, u3)
                   in zip(res["v2_sets"], res["v3_sets"]))
    return subset, same_den


def frozen_only_examples(res, k=3):
    """`frozen`이 생존이라 했는데 `v2`가 뺀 항목 — 위양성 실물."""
    out = []
    for (s, f), (_, a, u) in zip(res["fr_sets"], res["v2_sets"]):
        for it in sorted(f - a):
            out.append((s, it, "판정불가" if it in u else "비생존"))
    return out[:k], len(out)


def v2_only_examples(res, k=3):
    """
    🔴 **반대 방향** — `v2`가 생존이라 했는데 `frozen`은 아니라고 한 항목.

    `scoring.py`의 서술은 *"`survived_v2`는 그 구현의 **위양성 3건**을 잡는다"*이고,
    그 문장은 «v2 ⊆ frozen»으로 읽힌다. **그런 보장은 코드에 없다.**
    `_clean_roots`가 항목 쪽 어근도 깎으므로 분모 `len(ir)`이 줄고, 그러면
    같은 교집합이 더 높은 비율이 된다 — 즉 v2가 frozen보다 **더 많이** 생존시킬 수
    있다. 이 함수는 그 일이 실제로 일어나는지를 실물로 찍는다.
    """
    out = []
    for (s, f), (_, a, _u) in zip(res["fr_sets"], res["v2_sets"]):
        for it in sorted(a - f):
            fr, cr = Memory._roots(it), SC._clean_roots(it)
            out.append((s, it, len(fr), len(cr)))
    return out[:k], len(out)


# ══════════════════════════════════════════════════════════════════════
# 5. θ · τ
# ══════════════════════════════════════════════════════════════════════

def tau_cut(rows):
    # 🔄 인용 위생 — 본래 여기 쓴 닻은 retrieve()였고, 감사기가 «가장 좁은 닻»으로
    #    그것을 골라 `def retrieve`(:1464)를 가리키며 의심을 냈다. 인용이 겨누는
    #    것은 함수가 아니라 그 안의 **한 줄**이므로 닻을 그 줄의 이름으로 바꾼다.
    """retrieve()의 2단계 하드 게이트와 **같은 식** — `memory.py:1166-1168`의 `TAU_IMPORTANCE` 비교."""
    imps = [max(r["importance"] or 0, r["emotional_weight"] or 0) for r in rows]
    cut = [i for i in imps if i < M.TAU_IMPORTANCE]
    return len(imps), len(cut), imps


def rel_population(qs, ledger, rows):
    """
    REL := { coverage(bigrams(ask), bigrams(summary)) : ask ∈ 채점문항, summary ∈ 색인 }

    🔴 `retrieve()`의 `lexical` 분기와 **같은 두 함수**를 쓴다
    (`coverage`를 부르는 자리는 `memory.py:1175`). 척도를 여기서 다시 쓰면 그것은 다른 실험이다.
    채점 대상의 정의는 `precision.partition`을 그대로 쓴다.
    """
    key_of = P.key_index(ledger)
    scored, excluded = P.partition(qs, key_of)
    vals = []
    for q in scored:
        qb = set(M.bigrams(q["ask"]))
        for r in rows:
            vals.append(M.coverage(qb, set(M.bigrams(r["summary"]))))
    return scored, excluded, vals


# ══════════════════════════════════════════════════════════════════════
# 6. 계측기 자신이 코퍼스에 붙어 있는 자리
# ══════════════════════════════════════════════════════════════════════

def instrument_coupling(m):
    """`soak.ingest`가 사실의 **주어**를 무엇으로 넣었는가 · 무효화가 돌았는가."""
    subs = [r[0] for r in m.db.execute(
        "SELECT DISTINCT subject FROM fact WHERE chat_id=?", (CHAT,))]
    sup = m.db.execute(
        "SELECT COUNT(*) FROM fact WHERE chat_id=? AND superseded_by IS NOT NULL",
        (CHAT,)).fetchone()[0]
    preds = [r[0] for r in m.db.execute(
        "SELECT DISTINCT predicate FROM fact WHERE chat_id=?", (CHAT,))]
    known = [p for p in preds if p in Memory.PREDICATE_CARDINALITY]
    return subs, sup, len(preds), known


# ══════════════════════════════════════════════════════════════════════
# 본문
# ══════════════════════════════════════════════════════════════════════

def main():
    data = {n: load(n) for n in NAMES}
    hits = axis1_check(data)

    built = {}
    for n in NAMES:
        c, l, q = data[n]
        m, dbf = build(n, c, l)
        built[n] = (m, dbf, index_rows(m))

    print("=" * W)
    print("두 번째 코퍼스 — 기존 계측기를 고치지 않고 그대로 통과시킨다")
    print("=" * W)
    print("🔴 두 열을 **나란히** 놓는다. 화살표는 그리지 않는다 — 모집단이 다르다.")
    print("   축을 선언하고 만든 코퍼스이므로 «그 축에서 다르다»는 관측이 아니라 전제다.")
    print(f"\n축 ① 검사 — eval2에서 {BANNED_IN_EVAL2} 출현: {hits} (0이어야 통과)")

    rows = []
    for lab, f in [
        ("턴 수 (JSONL 행)", lambda c, l, q: len(c)),
        ("  그중 user 턴 (게이트 분모)",
         lambda c, l, q: sum(1 for r in c if r["role"] == "user")),
        ("세션 수", lambda c, l, q: len({r["session"] for r in c})),
        ("심은 항목 (planted_id 있는 행)",
         lambda c, l, q: sum(1 for r in c if r["planted_id"])),
        ("대장 항목 (facts + events)", lambda c, l, q: len(ledger_items(l))),
        ("문항 (qa_questions)", lambda c, l, q: len(q)),
    ]:
        rows.append((lab, f(*data[NAMES[0]]), f(*data[NAMES[1]])))
    rows.append(("event 색인 행 (user_deleted=0)",
                 len(built[NAMES[0]][2]), len(built[NAMES[1]][2])))
    rule("0. 규모 — 각 열은 **다른 모집단**이다")
    two_col("", rows)

    # ── 1. 게이트 ─────────────────────────────────────────────────
    rule("1. 🔴 `Memory.gate` — 발화율과 이유별 분해 (두 코퍼스 나란히)")
    print("  계측기: `Memory.gate` 무변경 · 분모 = `role == \"user\"`인 턴"
          " (`soak.replay`와 같은 정의)")
    gb = {}
    for n in NAMES:
        m = built[n][0]
        gb[n] = gate_breakdown(m, data[n][0])
    a, b = gb[NAMES[0]], gb[NAMES[1]]
    two_col("", [
        ("게이트 통과 (건 / user 턴)",
         f"{a[1]}/{a[0]} = {a[1]/a[0]*100:.1f}%",
         f"{b[1]}/{b[0]} = {b[1]/b[0]*100:.1f}%"),
    ])
    print()
    all_reasons = sorted(set(a[2]) | set(b[2]))
    print(f"  {'이유 (Memory.gate의 반환 문자열)':<44} {NAMES[0]:>18} {NAMES[1]:>18}")
    print("  " + "-" * (44 + 38))
    for why in all_reasons:
        ca, cb = a[2].get(why, 0), b[2].get(why, 0)
        print(f"  {why:<44} {ca:>7} ({ca/a[0]*100:5.1f}%) "
              f"{cb:>7} ({cb/b[0]*100:5.1f}%)")

    print("\n  ⚠️ «과거 참조 표현» 줄은 **자연 발생 빈도의 차이가 아니다.**")
    print("     이 줄로 통과한 턴이 심긴 항목 턴인가 (생성 템플릿의 산물인가):")
    for n in NAMES:
        pl, ot = past_ref_source(built[n][0], data[n][0])
        print(f"     [{n}] 심긴 항목 턴 {pl}건 · 그 밖의 턴 {ot}건")
    print("     eval의 `gen_corpus.render`는 사실을 `\"{text}. 말했었나?\"`로 찍고")
    print("     그 `말했`이 게이트 정규식에 그대로 걸린다. eval2의 템플릿은")
    print("     `\"{text}. 이거 맞죠?\"`이고 **그것은 이 레인이 골랐다.**")

    print("\n  🔴 게이트 통과를 **턴 종류별로** 가른다 (분모가 종류마다 다르다):")
    gk = {n: gate_by_kind(built[n][0], data[n][0]) for n in NAMES}
    kinds = ["심긴 항목", "하드 네거티브", "순수 노이즈"]
    print(f"  {'턴 종류':<44} {NAMES[0]:>18} {NAMES[1]:>18}")
    print("  " + "-" * (44 + 38))
    for k in kinds:
        cells = []
        for n in NAMES:
            tot, fire = gk[n].get(k, [0, 0])
            cells.append(f"{fire}/{tot} = {fire/tot*100:.1f}%" if tot else "-")
        print(f"  {k:<44} {cells[0]:>18} {cells[1]:>18}")

    rule("1-b. `|_recall_vocab|`가 자라는 곡선 — **색인 행 수의 함수로** 본다")
    print("  🔴 턴 축이 아니라 **색인 행 수 축**이다. 두 코퍼스의 심은 항목 밀도가")
    print("     다르므로(eval 3.8% / eval2 13.0% — README §4) 턴 축에서는 «축의")
    print("     효과»와 «밀도의 효과»가 섞인다. 밀도는 같게 두려 했으나 못 뒀다.")
    for n in NAMES:
        c, l, q = data[n]
        cur = vocab_curve(n, c, l)
        print(f"\n  [{n}]  색인행 → |_recall_vocab| · 게이트 통과/user 턴")
        for k, v, fired, nu in cur:
            print(f"    색인 {k:>3}행   |vocab| {v:>4}   "
                  f"게이트 {fired:>4}/{nu} = {fired/nu*100:5.1f}%")

    # ── 2. UBIQUITOUS ────────────────────────────────────────────
    rule("2. 🔴 `scoring.UBIQUITOUS = {\"지우\"}`가 각 코퍼스에서 하는 일")
    ub = {n: ubiquitous_effect(data[n][1]) for n in NAMES}
    two_col("", [
        ("대장 항목 수 (분모)", ub[NAMES[0]][0], ub[NAMES[1]][0]),
        ("UBIQUITOUS가 어근을 걷어낸 항목 수", ub[NAMES[0]][1], ub[NAMES[1]][1]),
        ("걷어낸 어근 총 개수", ub[NAMES[0]][2], ub[NAMES[1]][2]),
        ("`지우`의 항목 빈도 df", ub[NAMES[0]][3].get("지우", 0),
         ub[NAMES[1]][3].get("지우", 0)),
    ])
    base_n, base_rank, _ = induce_ubiquitous(data["eval"][1], min_frac=0.0)
    jw = next((f for r, c, f in base_rank if r == "지우"), None)
    if jw is None:
        _, all_rank, _ = induce_ubiquitous(data["eval"][1], min_frac=0.0, top=999)
        jw = next((f for r, c, f in all_rank if r == "지우"), 0.0)
    print(f"\n  문턱의 출처 (G15): eval에서 `지우`의 df 비율 = {jw:.3f}."
          f"  이 비율 이상을 «편재»로 부른다.")
    for n in NAMES:
        ni, ranked, induced = induce_ubiquitous(data[n][1], min_frac=jw)
        print(f"\n  [{n}] 항목 {ni}개에서 어근 df 상위 (어근 · df · df/항목):")
        for r, c, f in ranked:
            mark = " ←편재" if f >= jw else ""
            print(f"    {r:<16} {c:>3}  {f*100:5.1f}%{mark}")
        cut_df, cut_rest = tie_cut(data[n][1], ranked)
        if cut_rest:
            print(f"    ⚠️ 마지막 칸이 동점 한가운데서 잘렸다 — df={cut_df} 공동이"
                  f" {len(cut_rest)}종 더 있다: {' · '.join(cut_rest)}"
                  f" (칸 안은 어근 코드포인트 순)")
        print(f"    → 이 코퍼스에서 유도된 편재 집합: "
              f"{sorted(induced) if induced else '∅ (없음)'}")

    print("\n  🔴 **상수를 비워보면 채점이 달라지는가** — `UBIQUITOUS`를 ∅로")
    print("     재바인딩하고(G13 · try/finally) 4절과 같은 다이제스트로 다시 잰다.")
    print("     달라지는 건수가 0이면 그 상수는 이 코퍼스에서 **비용도 효과도 없다.**")
    print(f"  {'':<44} {NAMES[0]:>18} {NAMES[1]:>18}")
    print("  " + "-" * (44 + 38))
    cells_v2, cells_un = [], []
    for n in NAMES:
        c, l, q = data[n]
        dg = digests(c, l)
        cur = score_all(l, dg)
        emp = rescore_with(l, set(), digs=dg)
        cells_v2.append(f"{cur['v2']} / {emp['v2']}")
        cells_un.append(f"{cur['un2']} / {emp['un2']}")
    print(f"  {'survived_v2 생존 (현행 상수 / ∅)':<44} "
          f"{cells_v2[0]:>18} {cells_v2[1]:>18}")
    print(f"  {'v2 판정불가 (현행 상수 / ∅)':<44} "
          f"{cells_un[0]:>18} {cells_un[1]:>18}")

    # ── 3. _roots · _stem ─────────────────────────────────────────
    rule("3. `Memory._roots` · `_stem`이 깨지는 자리 — 실물")
    brk = {n: breakage(*data[n]) for n in NAMES}
    two_col("", [
        ("서로 다른 어절 수 (분모)",
         len(brk[NAMES[0]][0]), len(brk[NAMES[1]][0])),
        ("① `len(w) < 2`로 버려진 어절",
         len(brk[NAMES[0]][1]), len(brk[NAMES[1]][1])),
        ("② `습니다` 뗀 뒤 잔여 표지로 끝나는 어근",
         len(brk[NAMES[0]][2]), len(brk[NAMES[1]][2])),
        ("③ 한글이 없는 어근 (영문·숫자)",
         len(brk[NAMES[0]][3]), len(brk[NAMES[1]][3])),
    ])
    for n in NAMES:
        seen, dropped, residual, nonhan = brk[n]
        print(f"\n  [{n}] ① 길이 1 탈락 실물: "
              f"{sorted(dropped)[:12] if dropped else '없음'}")
        # 두 갈래를 **따로** 찍는다. 한 덩어리로 정렬하면 숫자로 시작하는
        # `입/립` 갈래가 앞을 다 차지해 축약 과거 갈래가 화면에서 사라진다.
        past = sorted((w, r) for w, r in residual.items()
                      if not r.endswith(("입", "립")))
        cop = sorted((w, r) for w, r in residual.items()
                     if r.endswith(("입", "립")))
        print(f"  [{n}] ② 잔여 표지 실물 (어절 → 어근):")
        print(f"      [{n}] ①축약 과거 ({len(past)}개): " +
              ("없음" if not past else
               " · ".join(f"{w} → {r}" for w, r in past[:5])))
        print(f"      [{n}] ②서술격 `입/립` ({len(cop)}개): " +
              ("없음" if not cop else
               " · ".join(f"{w} → {r}" for w, r in cop[:5])))
        print(f"  [{n}] ③ 비한글 어근 실물:")
        ex = sorted(nonhan.items())[:10]
        print(f"      [{n}] " + ("없음" if not ex else
                                 " · ".join(f"{w} → {r}" for w, r in ex)))

    print("\n  🔴 «같은 것을 가리키는 두 표현»이 `_roots`로 만나는가 (eval2 실물):")
    for a_, b_, inter, diff in pair_probe([
            ("첫 번째 PG사 미팅은 수수료 이견으로 보류됐습니다", "PG사 미팅 보류"),
            ("세 번째 PG사 미팅에서 계약을 체결했습니다",
             "세 번째 PG사 미팅에서 뭐가 정해졌는지 알려주세요"),
            ("보안 감사에서 지적 12건을 받았습니다", "보안 감사 지적이 몇 건이었죠"),
            ("사내 교육 정원은 40명입니다", "사내 교육 정원이 몇 명이었죠"),
            ("결제 API 운영 버전이 v3.0으로 올라갔습니다",
             "결제 API 운영 버전이 지금 뭐죠")]):
        print(f"    A: {a_}")
        print(f"    B: {b_}")
        print(f"       공통 어근 {inter}")
        print(f"       한쪽에만  {diff[:10]}")

    # ── 4. 세 채점기 ──────────────────────────────────────────────
    rule("4. `survived_frozen` / `survived_v2` / `survived_v3` — 순서가 같은가")
    print(f"  다이제스트: **추출식 규칙**(세션의 심긴 항목 텍스트를 잇고 "
          f"{DIGEST_CHARS}자에서 자름).")
    print("  🔴 LLM 요약이 아니다. 실험 19/20의 숫자와 **같은 것이 아니고**, 그 표와")
    print("     나란히 놓지 않는다. 여기서 보는 것은 **세 채점기의 순서**뿐이다.")
    sc = {}
    for n in NAMES:
        c, l, q = data[n]
        sc[n] = score_all(l, digs=digests(c, l))
    A, B = sc[NAMES[0]], sc[NAMES[1]]
    two_col("", [
        ("다이제스트 수 × 항목 수 = 판정 쌍 (분모)",
         f"{A['n_digests']}×{A['n_items']} = {A['n_pairs']}",
         f"{B['n_digests']}×{B['n_items']} = {B['n_pairs']}"),
        ("survived_frozen 생존 (건)", A["frozen"], B["frozen"]),
        ("survived_v2 생존 (건)", A["v2"], B["v2"]),
        ("survived_v3 생존 (건)", A["v3"], B["v3"]),
        ("v2 판정불가 (건)", A["un2"], B["un2"]),
        ("v3 판정불가 (건)", A["un3"], B["un3"]),
    ])
    print()
    for n in NAMES:
        r = sc[n]
        order = (f"frozen {r['frozen']} ≥ v2 {r['v2']} ≥ v3 {r['v3']}"
                 if r["frozen"] >= r["v2"] >= r["v3"]
                 else f"🔴 순서 깨짐: frozen {r['frozen']} / v2 {r['v2']}"
                      f" / v3 {r['v3']}")
        sub, den = invariants(r)
        print(f"  [{n}] 크기 순서: {order}")
        print(f"  [{n}] scoring.py가 주장하는 불변식: "
              f"v3.survived ⊆ v2.survived = {sub} · "
              f"v3.unscorable == v2.unscorable = {den}")
        ex, n_fo = frozen_only_examples(r)
        rev, n_vo = v2_only_examples(r)
        print(f"  [{n}] 두 방향의 크기: frozen만 {n_fo}건 · v2만 {n_vo}건"
              f"  (합계 차 {n_vo - n_fo:+d} = v2 {r['v2']} − frozen {r['frozen']})")
        print(f"  [{n}] frozen이 잡고 v2가 뺀 실물 (위양성 제거) "
              f"{'— 없음' if not ex else ''}")
        for s, it, why in ex:
            print(f"        [{s}] {it}   ({why})")
        print(f"  [{n}] 🔴 **반대 방향** — v2가 잡고 frozen이 놓친 실물 "
              f"{'— 없음' if not rev else ''}")
        for s, it, nf, nc in rev:
            print(f"        [{s}] {it}")
            print(f"              분모: _roots {nf}개 · _clean_roots {nc}개 "
                  f"(길이 1 어근이 빠지며 분모가 줄어 비율이 올라간다)")

    # ── 5. θ · τ ─────────────────────────────────────────────────
    rule("5. 🔴 θ · τ가 각 코퍼스에서 자르는 것")
    tt = {n: tau_cut(built[n][2]) for n in NAMES}
    two_col("", [
        (f"τ = TAU_IMPORTANCE = {M.TAU_IMPORTANCE} — 색인 행 (분모)",
         tt[NAMES[0]][0], tt[NAMES[1]][0]),
        ("  τ 미만이라 하드 게이트에서 잘리는 행",
         f"{tt[NAMES[0]][1]} = {tt[NAMES[0]][1]/tt[NAMES[0]][0]*100:.1f}%",
         f"{tt[NAMES[1]][1]} = {tt[NAMES[1]][1]/tt[NAMES[1]][0]*100:.1f}%"),
    ])
    print("\n  ⚠️ τ가 자르는 양은 대장의 `importance`/`emotional_weight` 배정에")
    print("     직접 매달려 있고, 그 배정은 **이 레인이 손으로 했다.** 그러므로")
    print("     이 줄은 «τ가 업무 코퍼스에서 더/덜 자른다»의 근거가 **아니다.**")

    print(f"\n  θ — 어휘 척도(`coverage`)의 REL 분포. 척도·모집단 정의는"
          f" `retrieve()`의 lexical 분기와 같다.")
    for n in NAMES:
        c, l, q = data[n]
        scored, excluded, vals = rel_population(q, l, built[n][2])
        zero = sum(1 for v in vals if v == 0.0) / len(vals)
        c05 = RD.actual_cut(vals, 0.05)
        c0001 = RD.actual_cut(vals, 0.0001)
        print(f"\n  [{n}] 채점문항 {len(scored)} × 색인 {len(built[n][2])}행"
              f" = n {len(vals)}쌍   (제외 {len(excluded)}문항: "
              f"{[e[0] for e in excluded]})")
        print(f"        rel == 0 의 원자           {zero*100:5.1f}%")
        print(f"        θ=0.05   실제 컷           {c05*100:5.1f}%")
        print(f"        θ=0.0001 실제 컷           {c0001*100:5.1f}%")
        same = "**같다** — θ는 임계 컷이 아니라 «겹침이 0인 것만 버린다»" \
               if abs(c05 - c0001) < 1e-12 else \
               "**다르다** — θ=0.05가 0이 아닌 값도 자른다"
        print(f"        두 컷이 {same}")
        print(f"        등컷 f=0.80 → θ_at {RD.theta_at(vals, 0.80):.6f}"
              f" (실제 컷 {RD.actual_cut(vals, RD.theta_at(vals, 0.80))*100:.1f}%)")

    # ── 6. 계측기 자신 ────────────────────────────────────────────
    rule("6. 계측기 자신이 코퍼스 하나에 붙어 있는 자리 (덤으로 나온 것)")
    ic = {n: instrument_coupling(built[n][0]) for n in NAMES}
    two_col("", [
        ("`soak.ingest`가 넣은 fact.subject",
         ",".join(ic[NAMES[0]][0]), ",".join(ic[NAMES[1]][0])),
        ("superseded_by가 채워진 fact 행", ic[NAMES[0]][1], ic[NAMES[1]][1]),
        ("대장이 쓴 서로 다른 술어 수", ic[NAMES[0]][2], ic[NAMES[1]][2]),
        ("  그중 PREDICATE_CARDINALITY에 있는 것",
         len(ic[NAMES[0]][3]), len(ic[NAMES[1]][3])),
    ])
    print(f"\n  eval2에서 표에 있는 술어: {ic[NAMES[1]][3] or '없음'}")

    for n in NAMES:
        m, dbf, _ = built[n]
        m.db.close()
        os.remove(dbf)

    rule("🔴 이 프로브가 말할 수 없는 것")
    print("  · eval2도 **합성**이고 **저자가 하나**다. 두 번째 코퍼스가 «실제 사용»이 아니다.")
    print("  · «다르게 만들었으니 다르다»는 순환이다. 축을 선언했으므로 그 축에서")
    print("    두 코퍼스가 다른 것은 전제다. 말할 수 있는 것은 «그 축 위에서")
    print("    휴리스틱이 어떻게 반응하는가»뿐이다.")
    print("  · n이 작다 — 6세션 192턴. 어느 비율도 소수점 둘째 자리를 주장하지 않는다.")
    print("  · 심은 항목 밀도를 같게 두지 못했다 (3.8% / 13.0%). 게이트·vocab 곡선의")
    print("    턴 축 해석은 그만큼 오염돼 있고, 그래서 색인 행 수 축으로 찍었다.")
    print("  · 4절의 다이제스트는 추출식 규칙이라 LLM 요약 품질을 대신하지 않는다.")
    print("=" * W)


if __name__ == "__main__":
    main()
