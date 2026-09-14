# -*- coding: utf-8 -*-
"""
summary_prototype.py — **요약을 채점한다.** M1 형식 · M2 사건 · M3 순서 · M4 누출.
(실험 27 · 계획서 `.omc/plans/ralplan-summary-layer.md` §3.1·§3.2·§3.3·§3.4)

## 이 파일이 채우는 자리

[ADR-016](../docs/adr/ADR-016-summary-layer.md) §결과에 «비운 자리»라는 절이 있고
거기 이렇게 적혀 있다 — *"요약 품질에 대해 이 라운드는 아무 숫자도 내지 않는다."*
그 라운드가 **판정하지 않는 단계를 이름 그대로 부르고 잘라 냈기 때문**이고,
사양은 지우지 않고 §3.1~§3.4에 남겼다. 이 파일이 **그 사양 그대로** 그 자리를 채운다.

🔴 **새로 설계하지 않았다.** M1~M4의 정의도, 못 재는 것 X1~X6도, 아래 비교 규칙도
전부 계획서가 **실측으로 사서** 적어 둔 것이다. 이 파일이 하는 일은 그것을
**집행**하는 것이다.

## 🔴 §3.3의 비교 규칙 — 이 스크립트가 집행한다

1. 기준선(`summary_v2_recomputed.txt`)과 **직접 비교할 수 있는 것은 «같은 항목
   집합으로 재채점한 값» 하나뿐이다.** 그래서 이 라운드의 요약을 기준선의
   **혼합 11개 집합**(S01–S12 구간의 사실 8 + 사건 3)으로도 한 번 채점하고,
   **그 열에만** 기준선 화살표를 붙인다.
2. **M2(사건 10개) 열에는 화살표를 붙이지 않는다.** 비교 대상이 없다 —
   **없다고 적는다.**
3. 두 표는 **가로줄로 갈라** 놓고 각각 **항목 집합 이름과 구간을 제목에 박는다.**
   **분모 숫자만 적힌 열은 이 스크립트가 출력하지 않는다** (§3.1).
4. **채점기가 다르면 그것도 «다른 집합»이다** — 열 제목에 채점기 이름을 박는다.

이 넷은 산문이 아니라 `TitleRule`이 **종료 코드로** 집행한다. 규칙을 어기는 열을
만들면 표가 그려지기 전에 발화한다 — 음성 대조 ⓒ·ⓓ·ⓔ가 실제로 그것을 심는다.

🔴 **그리고 이 스크립트는 §3.3 ①보다 **한 칸 더** 좁게 간다.** 항목 집합이 같아도
**재료 구간과 거친 단계(깊이)가 다르면** 화살표를 안 건다. 그래서 화살표가 붙는
자리는 **한 행 하나뿐**이다 — 깊이 1 · S01–S12 · 혼합 11개. 나머지는 «참고»로
같은 표에 두고 **왜 화살표가 없는지**를 옆에 적는다.

## 🔴 M2를 v2로 잰다 — v3이 이 재료에서 **위음성**을 낸다

§3.4는 *"M2를 v2로 잴 것인가 v3으로 잴 것인가"*를 **실험 27의 결정**으로 남겼다.
이 실험이 그것을 실측으로 정했다.

  · 실험 26의 홀드아웃(v2 94.4% → v3 100%)은 **«사건 × 한 세션 요약»** 쌍에서 쟀다.
  · M2가 채점하는 것은 **«사건 × 24세션 이어붙임»**이다. 자를 검증한 기하와
    쓰는 기하가 다르다 — §3.3 ④가 경계하는 «분모가 아니라 자가 바뀐 것»이다.
  · 그리고 실제로 갈린다: `E004 첫 번째 면접 — 탈락`이 **재료 안에 있는데도**
    (`S14` 요약이 *"첫 면접에서 탈락했고"*라고 적는다) v3에서 죽는다. 이어붙인
    텍스트의 머리 `번째`가 S16·S18에서 `{두, 세}`를 모으는데 S14는 `번째`를 안
    써서, 머리 `면접`은 `{첫, 두, 세}`로 **합의하는데도** 머리 `번째`가 어긋난다.
  · 아래 §2-b가 그 귀속을 **출력에 찍는다** (`번째` 머리를 빼면 v2와 같아진다).

→ **주 열은 `survived_v2`. `survived_v3`은 같은 표에 이름을 달고 나란히 찍는다.**

🔴 **`survived_v3`을 고치지 않는다.** 고치면 그 **이름 아래 다른 채점기**가 서고,
실험 26의 표가 그 이름으로 값을 갖고 있다 — S16이 실측으로 배운 실패 모드 ②다.
🔄 **정정.** 이 파일의 첫 판은 *"고치면 실험 26의 13/13·18/18이 다른 채점기의 수가
된다"*고 적었다. **그 수리를 실제로 심어 보니 그 값은 한 자리도 안 움직인다.**
그래서 근거를 바꿔 적는다: 남는 근거는 «값이 같으니 괜찮다»가 **다음 코퍼스에서
성립하지 않는다**는 것이고, 그 문장은 `scoring.py`의 서수 절이 이미 갖고 있다.
**심어 보지 않았으면 틀린 근거를 그대로 출하했다.**
**결함은 고치는 것이 아니라 이름을 찍어 남기는 것이 이 라운드의 몫이다.**

## 재료 — 하나는 만들어야 한다

`SUMMARY_S2.json`에는 세션 요약 24개만 있고 **lifetime이 없다.** M1(형식 3표제)과
M4의 lifetime 쪽은 `docs/14` P4 형식으로 쓴 lifetime이 있어야 잰다. → 임시 DB에
24개를 `put_session_digest`로 넣고 `summarize.rewrite_lifetime`을 **1회** 부른다.
결과는 `LIFETIME_S27.json`에 남아 재실행이 **생성 0건**이 된다.

⚠️ **체크포인트는 «생존 확인»이 아니다.** 파일이 있다고 조건이 같은 것이 아니라서,
매 실행 `LLM_CHECKPOINT.json`의 다이제스트와 **문자열로** 대조하고 찍는다.

## 실행

    PYTHONIOENCODING=utf-8 python -B experiments/summary_prototype.py

ollama(`qwen3:8b`)가 없고 `LIFETIME_S27.json`도 없으면 **종료 77(SKIP)** —
통과가 아니라 미측정이다(G1).
"""
import json
import os
import re
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "prototype"))

import yaml                                                    # noqa: E402
import scoring                                                 # noqa: E402
import llm                                                     # noqa: E402
import summarize                                               # noqa: E402
from memory import Memory                                      # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

W = 78

LEDGER = os.path.join(ROOT, "eval", "fact-ledger.yaml")
SUMMARY_S2 = os.path.join(HERE, "data", "SUMMARY_S2.json")
SUMMARY_LOCAL = os.path.join(HERE, "data", "SUMMARY_LOCAL.json")
LIFETIME_CKPT = os.path.join(HERE, "data", "LIFETIME_S27.json")
LLM_CKPT = os.path.join(HERE, "data", "LLM_CHECKPOINT.json")
BASELINE_FILE = os.path.join(ROOT, "experiments", "data", "baseline",
                             "summary_v2_recomputed.txt")

# 기준선 표에서 이 실험이 읽는 두 행 — `(행 제목, 거친 단계, 재현 재료의 캐시 키)`.
# 🔴 **둘 다 이 실행이 다시 계산해서 대조한다.** 옮겨 적지 않는 이유는 G11이고,
#    다시 계산하는 이유는 그것과 다르다 — **재현되기 때문에 화살표를 그릴 수 있다.**
#    깊이 1은 세션 요약 12개를 이어붙인 것, 깊이 2는 그 12개를 한 번 더 압축한
#    `a:base`(2층 기본 지시)다.
BASELINE_ROWS = (("세션 요약 (전체 합침)", 1, None),
                 ("2층 · 기본 지시", 2, "qwen3:8b:a:base"))

# 기준선 구간. 이 수를 바꾸면 «같은 항목 집합»이 아니게 된다 —
# 음성 대조 ⓕ가 그것을 심어서 재현이 깨지는 것을 보인다.
BASELINE_SPAN = tuple("S%02d" % i for i in range(1, 13))

# `docs/14-extraction-prompts.md`의 P4 형식이 요구하는 표제 셋 (M1의 분모 3).
# 🔴 문자열을 여기 다시 적지 않고 `summarize.P4_TEMPLATE`에서 **뽑는다** —
#    사본을 두면 프롬프트가 바뀌었을 때 M1이 옛 형식을 계속 채점한다(F12).
M1_HEADINGS = tuple(re.findall(r"^## .+$", summarize.P4_TEMPLATE, re.M)
                    + re.findall(r"`(## [^`]+)`", summarize.P4_TEMPLATE))

# M3가 숫자를 만들기 위한 **최소 매칭 사건 수.** k(k−1)/2 쌍이므로 k=1이면 쌍이
# 0이고 «일치 비율»이라는 말 자체가 성립하지 않는다.
# 🔴 이 상수가 가드의 **유일한 자리**다 — 음성 대조 ⓐ가 이것을 0으로 내려
#    가짜 100%(그리고 1/0)가 나오는 것을 실제로 돌려 보인다.
M3_MIN_MATCHES = 2

# 세션당 턴 수. 임시 DB의 `covers_*_seq`를 만드는 데만 쓴다 — 720턴 24세션.
# ⚠️ 이 수는 **요약의 내용에 영향을 주지 않는다.** `rewrite_lifetime`은 재료로
#    세션 요약만 읽고 구간은 메타로만 쓴다(ADR-013 P4).
TURNS_PER_SESSION = 30

CHAT = "eval-chat-001"


# ── 0. 재료 ─────────────────────────────────────────────────────────────

def load_ledger():
    """대장. **읽기만** 한다 (A8)."""
    with open(LEDGER, encoding="utf-8") as f:
        return yaml.safe_load(f)


def round_summaries():
    """이 라운드 재료 — `summarize.session_digest`가 만든 24세션 요약."""
    with open(SUMMARY_S2, encoding="utf-8") as f:
        rec = json.load(f)
    return ([(sid, rec["summaries"][sid]) for sid in sorted(rec["summaries"])],
            rec["meta"])


def archive_raw():
    """12세션 기록물 캐시 전체 — 깊이 1도 깊이 2도 여기서 나온다."""
    with open(SUMMARY_LOCAL, encoding="utf-8") as f:
        return json.load(f)


def archive_summaries(raw=None):
    """기록물의 깊이-1 세션 요약 — `digest_budget.py` 절 3이 쓰는 그 목록."""
    d = raw if raw is not None else archive_raw()
    ks = sorted(k for k in d if k.startswith("qwen3:8b:s:S"))
    return [(k.rsplit(":", 1)[1], d[k]) for k in ks]


def join(sums):
    """세션 요약들을 하나의 텍스트로.

    ⚠️ **이 이음 방식이 값을 움직이지 않는다** — 실측으로 확인했다(접두 있음/없음·
       개행 하나/둘 세 형태에서 기준선 행이 전부 같은 수였다). 어근 집합 채점이라
       구분자가 어근이 되지 않기 때문이다. 그래도 **한 곳에서만** 만든다.
    """
    return "\n".join(f"[{sid}] {t}" for sid, t in sums)


def mixed_items(led, span=None):
    """
    기준선의 **혼합 항목 집합** — S01–S12 구간의 `facts` + `events`.

    🔴 `/11`·`/10`이라는 모양이 `events` 10과 같아서 이 저장소가 한 번 속았다
       (S16). 그래서 이 함수는 **구간으로 재구성하고**, 아래 `baseline_anchor`가
       그 재구성이 기준선 파일의 수를 실제로 재현하는지 확인한다.
       재현되지 않으면 화살표를 그릴 근거가 없으므로 **종료 1**이다.
    """
    sp = set(BASELINE_SPAN if span is None else span)
    return ([f for f in led["facts"] if f["at"]["session"] in sp]
            + [e for e in led["events"] if e["at"]["session"] in sp])


# ── 1. 채점 — `scoring`을 **그대로 부른다** (사본 금지 · F12) ────────────

SCORERS = (("frozen", scoring.survived_frozen),
           ("v2", scoring.survived_v2),
           ("v3", scoring.survived_v3))
SCORER_NAMES = tuple(n for n, _ in SCORERS)


def score_all(text, items):
    """`{채점기 이름: (생존 수, 채점 가능 수, 판정불가 수, 생존 항목 id)}`."""
    out = {}
    texts = [it["text"] for it in items]
    for name, fn in SCORERS:
        r = fn(text, texts)
        if isinstance(r, list):                 # `survived_frozen`은 리스트다
            surv, uns = r, []
        else:
            surv, uns = r.survived, r.unscorable
        out[name] = (len(surv), len(texts) - len(uns), len(uns),
                     [it["id"] for it in items if it["text"] in surv])
    return out


def cell(got, name):
    return f"{got[name][0]}/{got[name][1]}"


# ── 2. 🔴 표 규율 — §3.1·§3.3을 종료 코드로 집행한다 ────────────────────

class Col:
    """
    표의 한 열. **항목 집합 이름과 채점기 이름 없이는 만들 수 없다.**

    🔴 이 클래스가 있는 이유는 하나다: rev2가 재측정 중에 산 것(S16) —
       *"분모가 같은 모양인데 항목 집합이 다른 것"* 이 이 저장소가 네 번 겪은
       실패 모드 ②의 가장 순수한 형태다. 산문으로 «제목에 박아라»라고 적으면
       다음 사람이 한 열에서 잊는다. **못 만들게 한다.**

    `arrow`는 기준선 화살표이고 **어느 행에 붙는지까지** 들고 있어야 한다
    (`(행 라벨, 기준선 값, 이번 값)`). 행 이름 없는 화살표는 표 전체에 붙은 것처럼
    읽히는데, 실제로 비교 가능한 것은 **행 하나**다.
    """

    def __init__(self, name, item_set, span, scorer,
                 same_item_set_as_baseline=False, arrow=None):
        self.name = name
        self.item_set = item_set          # 항목 집합의 **이름**(«events 10» 등)
        self.span = span                  # 항목 집합의 구간(«S01–S24»)
        self.scorer = scorer              # 채점기 이름 — 제목에 박힌다
        self.same = same_item_set_as_baseline
        self.arrow = arrow                # (행 라벨, 기준선 값, 이번 값) 또는 None

    def title(self):
        return f"{self.name} — {self.item_set} · {self.span} · **{self.scorer}**"


class TitleRule:
    """
    §3.1·§3.3의 **집행부**. 위반 목록을 돌려준다 — 비어 있어야 한다.

      ① 제목에 항목 집합 이름이 없다 (분모 숫자만 적힌 열) — §3.1
      ② 같은 이름이 **다른 항목 집합/구간** 둘을 가리킨다 — X6 / U1-b
      ③ 기준선 화살표가 «같은 항목 집합» 아닌 열에 붙었다 — §3.3 ②
      ④ 제목에 채점기 이름이 없다 — §3.3 ④ («자가 바뀐 것»은 표에 안 남는다)
      ⑤ 행 라벨이 분모 숫자뿐이거나 둘이 같은 이름이다 — X6 / U1-b
    """

    # 낱말이 하나도 없이 숫자(또는 `n/m`)만 있는 제목을 잡는다. `10`·`x/10`처럼
    # **분모만 적힌** 열이 정확히 이 모양이다.
    BARE = re.compile(r"^[^가-힣A-Za-z]*\d+(?:\s*/\s*\d+)?[^가-힣A-Za-z]*$")

    def audit(self, cols):
        bad = []
        by_name = {}
        for c in cols:
            if not c.item_set or self.BARE.match(c.item_set.strip()):
                bad.append(f"①«{c.name}» 제목의 항목 집합이 «{c.item_set}» —"
                           f" 분모 숫자만 적힌 열은 출력하지 않는다 (§3.1)")
            if not c.scorer:
                bad.append(f"④«{c.name}» 제목에 채점기 이름이 없다 (§3.3 ④)")
            if c.arrow and not c.same:
                bad.append(f"③«{c.name}»에 기준선 화살표가 붙었다 —"
                           f" 항목 집합이 기준선과 다르다 (§3.3 ②)")
            key = (c.item_set, c.span)
            prev = by_name.setdefault(c.name, key)
            if prev != key:
                bad.append(f"②«{c.name}»이 서로 다른 둘을 가리킨다:"
                           f" {prev} vs {key} — X6/U1-b")
        return bad

    def audit_rows(self, labels):
        """행 라벨도 이름이다. 두 재료를 같은 이름으로 부르면 X6의 재발이다."""
        bad = []
        for lab in labels:
            if not lab.strip() or self.BARE.match(lab.strip()):
                bad.append(f"⑤행 라벨 «{lab}»이 이름이 아니라 숫자다")
        dup = {l for l in labels if labels.count(l) > 1}
        for l in sorted(dup):
            bad.append(f"⑤행 라벨 «{l}»이 두 재료를 가리킨다 — X6/U1-b")
        return bad


def render(title, cols, rows, note=None):
    """표 하나. `cols`는 `Col`(= 채점기 축)이고 `rows`는 `(재료 라벨, [값…])`."""
    print(f"\n  {title}")
    widths = [34] + [14] * len(cols)
    print("  " + "".join(h.ljust(w) for h, w in
                         zip(["재료 / 행"] + [c.scorer for c in cols], widths)))
    print("  " + "-" * sum(widths))
    for label, vals in rows:
        print("  " + label.ljust(widths[0])
              + "".join(str(v).ljust(w) for v, w in zip(vals, widths[1:])))
    print()
    for c in cols:
        print(f"     · {c.title()}")
        if c.arrow:
            print(f"       🔁 기준선 화살표 — 행 «{c.arrow[0]}»만:"
                  f" **{c.arrow[1]} → {c.arrow[2]}**")
        elif c.same:
            print("       ⛔ 기준선 화살표: **없다** — 항목 집합은 같지만 이 채점기의"
                  " 기준선 값이 파일에 없다")
        else:
            print("       ⛔ 기준선 화살표: **없다 — 비교 대상이 없다** (§3.3 ②)")
    if note:
        print(f"\n{note}")


# ── 3. 기준선 앵커 ──────────────────────────────────────────────────────

def read_baseline_rows():
    """기준선 파일의 두 행을 **읽는다.** 옮겨 적지 않는다 (G11)."""
    with open(BASELINE_FILE, encoding="utf-8") as f:
        lines = f.read().splitlines()
    out = {}
    for row, depth, key in BASELINE_ROWS:
        got = None
        for line in lines:
            if line.startswith(row):
                nums = re.findall(r"(\d+)/(\d+)", line)
                if len(nums) >= 2:
                    got = {"frozen": f"{nums[0][0]}/{nums[0][1]}",
                           "v2": f"{nums[1][0]}/{nums[1][1]}"}
                break
        if got is None:
            raise AssertionError(
                f"기준선 파일에서 «{row}» 행의 두 값을 못 읽었다: {BASELINE_FILE}")
        out[row] = (depth, key, got)
    return out


def baseline_anchor(led, raw, span=None):
    """
    기준선의 두 행을 **다시 계산해서** 기록과 맞는지 본다.

    🔴 **재현되기 때문에 화살표를 그릴 수 있다.** 재현이 안 되면 두 수는 같은
       분모의 것이 아니고, 그때 화살표는 실패 모드 ②다. `fsm_probe.py`가
       ADR-013의 기록값에 대해 하는 것과 같은 형태다.

    반환: `[(행, 깊이, 기록 dict, 재계산 dict, 일치 여부), …]`
    """
    items = mixed_items(led, span)
    d1 = join(archive_summaries(raw))
    out = []
    for row, (depth, key, rec) in read_baseline_rows().items():
        text = d1 if key is None else raw[key]
        got = score_all(text, items)
        same = all(cell(got, s) == rec[s] for s in ("frozen", "v2"))
        out.append((row, depth, rec, got, same))
    return out


# ── 4. lifetime 생성 (또는 체크포인트) ──────────────────────────────────

def _build_db(path, sums):
    """임시 DB에 세션 요약 24개를 넣는다. `turn` 테이블은 **비어 있다.**

    비어 있어도 되는 것이 ADR-013 P4의 계약이다 — `rewrite_lifetime`은 원본 턴을
    안 읽는다. 여기서 그 계약이 **실행으로** 확인된다: 턴이 0건인 DB에서 lifetime이
    나오면 그것은 세션 요약만 읽었다는 뜻이다.
    """
    m = Memory(path)
    for i, (sid, text) in enumerate(sums, start=1):
        m.put_session_digest(
            CHAT, sid, text,
            covers_from_seq=(i - 1) * TURNS_PER_SESSION + 1,
            covers_to_seq=i * TURNS_PER_SESSION)
    return m


def make_lifetime(sums):
    """
    lifetime 요약 한 건. 체크포인트가 있으면 **생성 0건**.

    반환: `(content, meta, 이번 실행이 생성했는가)` 또는 `(None, None, False)` —
    ollama도 체크포인트도 없을 때.
    """
    if os.path.exists(LIFETIME_CKPT):
        with open(LIFETIME_CKPT, encoding="utf-8") as f:
            rec = json.load(f)
        return rec["lifetime"], rec["meta"], False

    info = llm.runtime_info()
    if not info.get("ollama"):
        return None, None, False

    tmp = tempfile.mkdtemp(prefix="exp27-")
    dbp = os.path.join(tmp, "lifetime.db")
    t0 = time.perf_counter()
    stall0 = summarize.STALL_COUNT
    m = _build_db(dbp, sums)
    try:
        content, usage, warn = summarize.rewrite_lifetime(m, CHAT)
    finally:
        m.db.close()
    wall = time.perf_counter() - t0

    meta = {
        "model": llm.LLM_MODEL, "ollama": info.get("ollama"),
        "digest": info.get("digest"),
        "temperature": llm.LLM_TEMPERATURE, "seed": llm.LLM_SEED,
        "num_ctx": llm.LLM_NUM_CTX,
        "generator_version": summarize.GENERATOR_VERSION,
        "k_session_digests": len(sums),
        "n_generated": 1,
        "retries_used": 1 + (summarize.STALL_COUNT - stall0),
        "wall_s": round(wall, 1),
        "stalls": summarize.STALL_COUNT - stall0,
        "prompt_eval_count": (usage or {}).get("prompt_eval_count"),
        "truncation_warning": warn,
        "source": "prototype/summarize.py::rewrite_lifetime (사본 없음 — F12)",
        "material": "experiments/data/SUMMARY_S2.json (세션 요약 24건)",
    }
    with open(LIFETIME_CKPT, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "lifetime": content}, f,
                  ensure_ascii=False, indent=2)
    return content, meta, True


def digest_compare(meta):
    """
    🔴 **문자열 대조다. «생존 확인»이 아니다.**

    체크포인트 파일이 있다는 것은 «전에 돌았다»이지 «같은 조건이다»가 아니다.
    `LLM_CHECKPOINT.json`의 다이제스트와 이 재료의 다이제스트를 **글자로** 맞춰
    보고, 다르면 숫자 옆에 그것을 적는다. 막지는 않는다 (`llm.checkpoint`의 규약).
    """
    with open(LLM_CKPT, encoding="utf-8") as f:
        ck = json.load(f)
    now = llm.runtime_info()
    return [(k, ck.get(k), meta.get(k), now.get(k))
            for k in ("ollama", "digest")]


# ── 5. M1 형식 ──────────────────────────────────────────────────────────

def m1(lifetime):
    """`docs/14` P4 형식의 표제 셋이 다 있는가. 분모 **3**."""
    hits = [(h, h in lifetime) for h in M1_HEADINGS]
    return sum(1 for _, ok in hits if ok), len(hits), hits


# ── 6. M3 순서 ──────────────────────────────────────────────────────────

class M3Result:
    def __init__(self, k, pairs, hit, ties, lost, pos=None, reason=None):
        self.k, self.pairs, self.hit = k, pairs, hit
        self.ties, self.lost, self.reason = ties, lost, reason
        self.pos = pos or {}


def first_pos(text, item_text):
    """
    항목이 요약에서 **처음 나타나는 위치**(글자 오프셋).

    겹친 어근 중 **문자 그대로** 텍스트에 있는 것들의 최소 인덱스다. 어근은
    `Memory._roots`가 어미·조사를 깎은 것이라 표면형과 다를 수 있고, 그런 어근은
    위치를 못 준다 — **추측하지 않고 그 항목을 M3에서 뺀다.** 뺀 수를 찍는다.

    ⚠️ **두 항목이 같은 낱말로만 찾히면 위치가 같아진다.** 그때 두 항목의 순서는
       이 규칙으로 **갈 수 없고**, 아래 `m3`가 그것을 동률로 세어 따로 찍는다.
       (실측: `E004`·`E005`·`E006`이 `면접` 하나로 찾혀 같은 오프셋을 받는다)
    """
    shared = scoring._clean_roots(item_text) & scoring._clean_roots(text)
    ps = [p for p in (text.find(r) for r in shared) if p >= 0]
    return min(ps) if ps else None


def m3(text, matched, min_matches=None):
    """
    M2가 **그 텍스트에서** 매칭한 사건들의 **첫 등장 순서**가 `at.session` 순서와
    맞는 쌍의 비율.

    🔴 **`matched`는 그 텍스트에 대한 M2의 출력이어야 한다.** 다른 텍스트의 매칭을
       넣으면 «M2가 안 잡은 사건의 순서»를 재게 되고 그것은 M3의 정의가 아니다.

    🔴 **`k < 2`면 숫자를 만들지 않는다.** 쌍이 0개이고, 0쌍의 «일치 비율»은
       존재하지 않는다. 여기서 «위반 0건이니 100%»라고 적으면 그것이 이 저장소가
       세는 «발화할 수 없는 검사»의 쌍둥이다 — 음성 대조 ⓐ가 이 가드를 실제로
       제거해 가짜 100%와 1/0을 둘 다 보인다.
    """
    lim = M3_MIN_MATCHES if min_matches is None else min_matches
    pos, lost = {}, []
    for e in matched:
        p = first_pos(text, e["text"])
        if p is None:
            lost.append(e["id"])            # 위치를 **추측하지 않는다**
        else:
            pos[e["id"]] = p
    k = len(pos)
    if k < lim:
        return M3Result(k, None, None, 0, lost, pos,
                        reason=f"판정 불가 — 매칭 사건 {k}건")
    ids = sorted(pos, key=lambda i: pos[i])
    sess = {e["id"]: e["at"]["session"] for e in matched}
    hit = pairs = ties = 0
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            i, j = ids[a], ids[b]
            pairs += 1
            if pos[i] == pos[j]:
                ties += 1                   # 갈 수 없다 — **불일치로 센다**
                continue
            hit += (pos[i] < pos[j]) == (sess[i] < sess[j])
    return M3Result(k, pairs, hit, ties, lost, pos)


def m3_fmt(r):
    """🔴 `pairs`가 0이면 여기서 **터진다.** 그것이 가드가 있는 이유다."""
    return f"{r.hit}/{r.pairs} = {100.0 * r.hit / r.pairs:.1f}%"


# ── 7. 음성 대조 — 심을 위반. **전부 실제로 돌린다** ────────────────────

def negative_controls(led, raw, live_quiet, live_fired):
    """
    여섯 개. 각각 **위반을 심어 발화를 확인**하고, 넷은 **오발화 대조**를 함께 낸다.

    🔴 *"열거는 검증이 아니다"* — 이 저장소가 **열 번** 깨뜨린 규율이고 가장 최근
       둘이 «홀드아웃 감사가 새 이름으로 열려 통과한 것»과 «축자 수리가 음성 대조를
       증상에 매인 형태로 깨뜨린 것»이다. 그래서 여기 있는 것은 전부 **돌아간다.**

    `live_quiet`·`live_fired`는 **오늘의 실제 입력**에서 각각 조용했던 M3와 울었던
    M3다. 둘을 다 받는 이유는 ⓑ에 있다.
    """
    print("\n" + "=" * W)
    print("음성 대조 — 심을 위반 여섯. 검사가 **발화하는지** 본다")
    print("=" * W)
    ok, rule = [], TitleRule()
    events = led["events"]

    # ── ⓐ §3.4가 지정한 실행 검사: `k<2` 가드 ────────────────────────
    print("\n  ⓐ **매칭 사건이 1건뿐인 입력** — 음성 경로가 실제로 도는가")
    one = [e for e in events if e["id"] == "E007"]
    tiny = "나비가 응급실에 갔다."
    r1 = m3(tiny, one)
    print(f"       입력 «{tiny}» · 항목 {one[0]['id']} 1건 (매칭 k={r1.k})")
    print(f"       → 출력: **{r1.reason}**"
          f"   · M3 숫자: {'없다' if r1.pairs is None else r1.pairs}")
    said = r1.reason == "판정 불가 — 매칭 사건 1건" and r1.pairs is None
    print(f"       {'✅ 음성 경로가 돌았다' if said else '🔴 안 돌았다'}")

    print("       ─ 심을 위반: `k<2` 가드를 **제거한다** (`min_matches=0`)")
    r0 = m3(tiny, one, min_matches=0)
    try:
        m3_fmt(r0)
        blew, why = False, "🔴 아무 일도 안 났다"
    except ZeroDivisionError as e:
        blew, why = True, (f"`ZeroDivisionError` — 찍히는 분수가"
                           f" **{r0.hit}/{r0.pairs}**이다: {e}")
    print(f"       → {why}")
    print(f"       → 그리고 흔한 방어 관용구(`hit/pairs if pairs else 1.0`)를 쓰면"
          f" **100.0%**가 찍힌다 — 쌍이 0개인데 «위반 0건»으로 읽힌다")
    fired = said and blew and r0.pairs == 0
    print(f"       {'✅ 발화' if fired else '🔴 발화 실패'}")
    ok.append(fired)

    # ── ⓑ 오발화 대조 (P5) — 같은 가드가 **양쪽으로** 갈리는가 ───────
    print("\n  ⓑ **오발화 대조** — 같은 가드가 오늘의 실제 입력 둘에서 갈리는가")
    print(f"       실제 입력 ①(이어붙임)  매칭 k={live_quiet.k}"
          f" → 사유 {live_quiet.reason or '없다'} · 쌍 {live_quiet.pairs}")
    print(f"       실제 입력 ②(lifetime) 매칭 k={live_fired.k}"
          f" → 사유 {live_fired.reason or '없다'} · 쌍 {live_fired.pairs}")
    quiet = live_quiet.reason is None and live_quiet.pairs
    loud = live_fired.reason is not None and live_fired.pairs is None
    print(f"       → ①에서 조용하고 ②에서 운다:"
          f" {'✅ 무조건 발화도 아니고 발화 불가도 아니다' if (quiet and loud) else '🔴 한쪽으로 쏠렸다'}")
    print("       🔴 **울지 않는 검사는 발화 증명이 없다**는 것도 함께 적는다 —"
          " ⓐ가 심은 발화이고")
    print("          ②가 **실제 입력에서의** 발화이며 ①이 그 반대쪽이다."
          " 셋이 있어야 한 짝이다.")
    ok.append(bool(quiet and loud))

    # ── ⓒ 제목 규율 ① — 분모 숫자만 적힌 열 ──────────────────────────
    print("\n  ⓒ **분모 숫자만 적힌 열**을 심는다 (§3.1이 금지한 것)")
    good = [Col("M2 사건", "events 10", "S01–S24", "v2")]
    # 🔴 셋을 심는 이유: «분모만»의 모양이 하나가 아니다. 맨 수 · 슬래시로 시작하는
    #    것 · 공백이 낀 분수 — 정규식 하나가 셋 다 물어야 규칙이 규칙이다.
    #    ⚠️ `x/10` 같은 **글자가 섞인** 자리표는 일부러 넣지 않았다. 이 검사는
    #       «낱말이 하나도 없다»를 보므로 `x`가 낱말로 세어지고, 그것을 잡으려면
    #       «어떤 글자가 이름인가»를 판정해야 한다 — 알고 포기한 자리다.
    for planted in ("10", "/10", " 8 / 11 "):
        bad = [Col("M2 사건", planted, "S01–S24", "v2")]
        v_bad = rule.audit(bad)
        print(f"       심은 제목  «{planted}» → 위반 {len(v_bad)}건"
              f"  {'✅' if v_bad else '🔴'}")
        for b in v_bad:
            print(f"          {b}")
        ok.append(bool(v_bad))
    v_good = rule.audit(good)
    print(f"       정상 제목  «{good[0].item_set}» → 위반 {len(v_good)}건"
          f"  {'✅ 조용하다 (오발화 대조)' if not v_good else '🔴 오발화'}")
    ok.append(not v_good)

    # ── ⓓ 제목 규율 ③ — M2 열에 기준선 화살표 ────────────────────────
    print("\n  ⓓ **M2(사건 10개) 열에 기준선 화살표**를 붙인다 (§3.3 ②가 금지)")
    bad = [Col("M2 사건", "events 10", "S01–S24", "v2",
               same_item_set_as_baseline=False,
               arrow=("이 라운드 재료 상한", "6/10", "8/10"))]
    okc = [Col("기준선 재채점", "혼합 8사실+3사건", "S01–S12", "v2",
               same_item_set_as_baseline=True,
               arrow=("R27 깊이1 S01–S12", "6/10", "6/10"))]
    v_bad, v_ok = rule.audit(bad), rule.audit(okc)
    print(f"       같은 항목 집합인 열의 화살표 → 위반 {len(v_ok)}건"
          f"  {'✅ 조용하다 (오발화 대조)' if not v_ok else '🔴 오발화'}")
    print(f"       M2 열의 화살표             → 위반 {len(v_bad)}건")
    for b in v_bad:
        print(f"          {b}")
    fired = bool(v_bad) and not v_ok
    print(f"       {'✅ 발화' if fired else '🔴 발화 실패'}")
    ok.append(fired)

    # ── ⓔ 제목/행 규율 ②⑤ — X6의 두 값을 **같은 이름**으로 ──────────
    print("\n  ⓔ **기록물 상한과 이 라운드 재료 상한을 같은 이름으로** 부른다"
          " (X6 · U1-b)")
    bad = [Col("M2 상한", "events 10", "S01–S12", "v2"),
           Col("M2 상한", "events 10", "S01–S24", "v2")]
    okc = [Col("M2 기록물 상한", "events 10", "S01–S12", "v2"),
           Col("M2 이 라운드 재료 상한", "events 10", "S01–S24", "v2")]
    v_bad, v_ok = rule.audit(bad), rule.audit(okc)
    print(f"       다른 이름 둘 (열) → 위반 {len(v_ok)}건"
          f"  {'✅ 조용하다 (오발화 대조)' if not v_ok else '🔴 오발화'}")
    print(f"       같은 이름 둘 (열) → 위반 {len(v_bad)}건")
    for b in v_bad:
        print(f"          {b}")
    r_bad = rule.audit_rows(["M2 상한", "M2 상한"])
    r_ok = rule.audit_rows(["기록물 상한 (12세션)", "이 라운드 재료 상한 (24세션)"])
    print(f"       같은 이름 둘 (행) → 위반 {len(r_bad)}건"
          f"  {'✅' if r_bad else '🔴'}   ·   다른 이름 둘 (행) → {len(r_ok)}건"
          f" {'✅' if not r_ok else '🔴'}")
    for b in r_bad:
        print(f"          {b}")
    fired = bool(v_bad) and not v_ok and bool(r_bad) and not r_ok
    print(f"       {'✅ 발화' if fired else '🔴 발화 실패'}")
    ok.append(fired)

    # ── ⓕ 기준선 앵커 ────────────────────────────────────────────────
    print("\n  ⓕ **항목 집합을 흔든다** — 재현이 깨지면 화살표를 못 그린다")
    normal = baseline_anchor(led, raw)
    print(f"       정상 구간 {BASELINE_SPAN[0]}–{BASELINE_SPAN[-1]}"
          f" (항목 {len(mixed_items(led))}개):")
    for row, depth, rec, got, same in normal:
        print(f"          «{row}» 기록 {rec['frozen']}·{rec['v2']}"
              f" vs 재계산 {cell(got, 'frozen')}·{cell(got, 'v2')}"
              f"  {'✅ 재현' if same else '🔴'}")
    shrunk = BASELINE_SPAN[:-1]                 # S01–S11 — 사건 E003(S12)이 빠진다
    mut = baseline_anchor(led, raw, span=shrunk)
    print(f"       심은 위반: 구간을 {shrunk[0]}–{shrunk[-1]}로 줄인다"
          f" (항목 {len(mixed_items(led, shrunk))}개 — 같은 «혼합»인데 다른 집합):")
    for row, depth, rec, got, same in mut:
        print(f"          «{row}» 기록 {rec['frozen']}·{rec['v2']}"
              f" vs 재계산 {cell(got, 'frozen')}·{cell(got, 'v2')}"
              f"  {'🔴 통과시켰다' if same else '✅ 재현 실패로 잡았다'}")
    fired = (all(s for *_, s in normal) and not any(s for *_, s in mut))
    print(f"       {'✅ 발화' if fired else '🔴 발화 실패'}")
    ok.append(fired)

    return all(ok), ok


# ── 8. 못 재는 것 X1~X6 ─────────────────────────────────────────────────

def print_unmeasured(m2_round, m2_archive, m2_life, r_life, r_cat, m4_diff):
    print("\n" + "=" * W)
    print("🔴 못 잰 것 — X1~X6. **못 잰다고 적는 것이 정답이다** (계획서 §3.2)")
    print("=" * W)
    print("""
  X1  **의역·추론된 사건.** 채점기는 어근 겹침이라 **의역을 놓치고**(위음성)
      **어근 둘만 겹쳐도 잡는다**(위양성). M2가 재는 것은 «요약이 사건을
      담았는가»가 아니라 **«요약이 대장과 낱말을 나눠 쓰는가»**다.
      🔴 이 라운드가 그 위음성의 **새 갈래** 하나를 얻었다 — §2-b의 `E004`.
      어근이 아니라 **서수 머리**가 만든 위음성이라 X1의 옛 두 갈래(의역
      누락 · 어근 위양성) 어디에도 안 들어간다. 그리고 위양성 쪽도 그대로다:
      `E010`(S22)이 `서준`·`연락` 둘로 잡히고, 그 오프셋이 **S01 블록**에
      떨어져 아래 M3의 순서까지 흔든다.

  X2  **관계 전이 라벨 커버리지.** 코퍼스에 stage 라벨(`썸`·`연인`·…)이 0회
      등장하고 `Memory._roots('썸')`가 빈 집합이다. **원리적으로** 규칙 채점 불가.

  X3  **요약이 읽을 만한가 / 관계 서술이 정확한가.** 심판이 필요하고 자기 채점은
      금지다(P3). 이 저장소에 검증된 심판이 없다. 사람 채점은 n=1 자기저작이다.
      → 그래서 «P4가 실행 가능해졌다»와 «세션 요약 소실이 사라졌다» 옆에는
      이 실험 **뒤에도** 숫자가 없다. 이 실험이 잰 것은 «담겼는가»의 축자
      대리 지표이고 «읽을 만한가»가 아니다.

  X4  **환각(재료 밖 내용).** 규칙 기반 자동 판정을 믿을 근거가 없다 —
      `docs/16-design-elements.md`의 콜드 스타트 절이 자동 판정의 **10배 과소
      계상**을 기록해 뒀다. 같은 종류의 검사를 새로 만들면 같은 실수를 반복한다.

  X5  **400세션 규모의 드리프트.** 코퍼스가 24세션이다. ADR-013이 적은 한계
      그대로이고 이 라운드도 못 바꿨다.""")
    print(f"""
  X6  **이 라운드 재료의 M2 상한과 기록물의 M2 상한은 다른 값이다.**
      🔴 **두 값을 다른 이름으로 나란히 찍는다** (U1-b):
        · M2 **기록물 상한**        (events 10 · 기록물 세션 요약 12 · v2) = {m2_archive}
        · M2 **이 라운드 재료 상한** (events 10 · R27 세션 요약 24 · v2) = {m2_round}
      같은 이름으로 부르면 그것이 곧 재발이다. **이 두 수 사이에도 화살표를
      그리지 않는다** — 재료가 다르면 다른 집합이고, 여기서 «올랐다»고 읽는
      순간 실패 모드 ②다. U1-b가 요구한 것은 «두 이름»이고 «화살표»가 아니다.""")
    print(f"""
  🔴 **M2와 M3는 독립 증거가 아니다** (§5 시나리오 3) — 이 라운드가 그것을
      **실측으로** 봤다. M3는 M2가 잡은 사건 위에서만 정의되고 둘이 같은 매칭을
      공유한다. 그래서 M2의 위양성 `E010`이 M3의 표본에 그대로 들어가고, 그
      한 항목이 오프셋 76(= S01 블록)에 떨어져 **이어붙임 M3를 혼자 7쌍 깎는다.**
      두 수가 나란히 좋아 보이는 것은 두 증거가 아니라 **한 증거를 두 번 본 것**
      이고, 나란히 나빠 보이는 것도 마찬가지다.
  🔴 **M3의 표본은 M2 상한이 정한다.** 매칭 k건이면 쌍은 k(k−1)/2이고,
      `k < {M3_MIN_MATCHES}`면 이 스크립트는 **숫자를 만들지 않는다.**
      오늘: 이어붙임 k={r_cat.k} → 쌍 {r_cat.pairs} ·
      lifetime k={r_life.k} → **{r_life.reason or '쌍 ' + str(r_life.pairs)}**.
      🔴 **즉 이 라운드의 M3는 lifetime에 대해 존재하지 않는다** — 그리고
      그것이 M2 lifetime = {m2_life}의 따름 결과다. 두 빈 자리는 하나다.
  🔴 **M4는 부호가 반대다** — 사실 누출은 **낮을수록 준수**이고, 이 실험이 읽는
      것은 절대값이 아니라 **세션 요약과 lifetime의 차이**({m4_diff:+d})뿐이다.
      ⚠️ **그런데 그 차이를 «지시가 작동했다»로 읽을 수 없다.** 같은 lifetime의
      M2도 {m2_life}다 — 사실도 사건도 0이면 «사실을 안 썼다»와 «아무것도 안
      남았다»가 **같은 관측**이고, M4 혼자서는 그 둘을 가르지 못한다. 이것이
      ⭐핵심 1(*"범인은 깊이가 아니라 새 재료 없이 재압축하는 것"*)이 M4의
      해석에 다시 나타난 자리다.""")


# ── 9. main ─────────────────────────────────────────────────────────────

def main():
    print("=" * W)
    print("실험 27 — 요약을 채점한다 (M1 형식 · M2 사건 · M3 순서 · M4 누출)")
    print("=" * W)
    print("  사양: `.omc/plans/ralplan-summary-layer.md` §3.1·§3.2·§3.3·§3.4")
    print("  채우는 자리: `docs/adr/ADR-016-summary-layer.md` §결과의 «비운 자리»")

    led = load_ledger()
    sums24, s2meta = round_summaries()
    raw = archive_raw()
    archive = archive_summaries(raw)
    rule = TitleRule()

    # ── 0. 재료 ──
    print("\n" + "-" * W)
    print("0. 재료 — 셋. **하나는 이 실험이 만든다**")
    print("-" * W)
    print(f"  이 라운드   `SUMMARY_S2.json` 세션 요약 **{len(sums24)}건**"
          f" (S01–S24) · `summarize.session_digest` (사본 없음 · F12)")
    print(f"  기록물      `SUMMARY_LOCAL.json` 세션 요약 **{len(archive)}건**"
          f" (S01–S12) — `digest_budget.py` 절 3이 쓰는 그 파일")
    print(f"  대장        `eval/fact-ledger.yaml` facts **{len(led['facts'])}**"
          f" · events **{len(led['events'])}** (읽기만 — A8)")
    print(f"  다이제스트  {s2meta['digest'][:16]}…  seed {s2meta['seed']}"
          f" · temperature {s2meta['temperature']} · num_ctx {s2meta['num_ctx']}")

    # ── 1. lifetime ──
    print("\n" + "-" * W)
    print("1. lifetime 요약 — `summarize.rewrite_lifetime` (ADR-013 P4)")
    print("-" * W)
    lifetime, lmeta, fresh = make_lifetime(sums24)
    if lifetime is None:
        print(f"  🔴 ollama({llm.OLLAMA_HOST})도 `LIFETIME_S27.json`도 없다."
              f" **종료 77 (SKIP)** — 통과가 아니라 미측정이다 (G1)")
        return 77
    print(f"  생성 건수 **{lmeta['n_generated']}건** · 벽시계"
          f" **{lmeta['wall_s']}초** · 정지 **{lmeta['stalls']}회**"
          f" · 시도 {lmeta.get('retries_used', '?')}회"
          f"   ({'방금 생성했다' if fresh else '체크포인트에서 읽었다 — 이 실행의 생성 0건'})")
    print(f"  재료 K = 세션 요약 **{lmeta['k_session_digests']}건**"
          f" (= N, ADR-013 P4의 «깊이 2») · 임시 DB의 `turn` 테이블은 **비어 있다**")
    print("     🔴 턴이 0건인 DB에서 lifetime이 나왔다는 것이 P4의 계약이"
          " **실행으로** 확인된 것이다")
    pe = lmeta.get("prompt_eval_count")
    if pe:
        print(f"  입력 실측 **{pe} tok** · num_ctx {lmeta['num_ctx']} tok"
              f" (실측 기준 {100.0 * pe / lmeta['num_ctx']:.1f}%)"
              f"   — U3의 방아쇠 5,734 tok의"
              f" {100.0 * pe / 5734:.0f}%, **안 당겨진다**")
    else:
        print("  입력 실측 ? tok — 기록에 없다. **추정으로 메우지 않는다**")
    print(f"  절단 경고: {lmeta.get('truncation_warning') or '없다'}")
    print("\n  🔴 다이제스트 **문자열 대조** (생존 확인이 아니다):")
    for key, rec, mine, now in digest_compare(lmeta):
        same = rec == mine == now
        print(f"     {key:<8} 기록 {str(rec)[:16]}…"
              f" · 이 재료 {str(mine)[:16]}…"
              f" · 지금 {str(now)[:16]}…   {'✅ 같다' if same else '⚠️ 다르다'}")
    print(f"\n  [lifetime 본문 {len(lifetime)}글자]")
    for line in lifetime.strip().splitlines():
        print(f"     | {line.rstrip()}")

    # ── 2. M1 ──
    print("\n" + "-" * W)
    print("2. M1 형식 준수 — `docs/14` P4의 표제 셋 (분모 3)")
    print("-" * W)
    hit1, tot1, hits = m1(lifetime)
    for h, okh in hits:
        print(f"  {'✅' if okh else '🔴'} `{h}`")
    print(f"\n  **M1 = {hit1}/{tot1}**  (항목 집합: `docs/14` P4 표제 3 ·"
          f" 재료: 이 라운드 lifetime · 채점기: 문자열 포함)")
    print("  ⚠️ **위생 검사이지 판정이 아니다** (§3.1). 표제가 있다는 것은 형식을")
    print("     지켰다는 뜻이지 내용이 옳다는 뜻이 아니다 — X3. 아래 M2가 그 lifetime")
    print("     에서 사건 0건을 찾는다는 사실이 이 3/3과 **모순이 아니다.**")
    print("  ⚠️ 세션 요약에는 M1을 적용하지 않는다 — 세션 층의 지시"
          " (`SESSION_TEMPLATE`)는")
    print("     형식을 요구하지 않고, 없는 계약을 채점하면 그 0은 결함이 아니다.")

    # ── 2-b. 채점기 결정 ──
    print("\n" + "-" * W)
    print("2-b. 🔴 §3.4가 남긴 결정 — M2를 **v2로** 잰다")
    print("-" * W)
    T24 = join(sums24)
    ev_all = led["events"]
    g24 = score_all(T24, ev_all)
    only_v2 = sorted(set(g24["v2"][3]) - set(g24["v3"][3]))
    print(f"  같은 재료·같은 항목에서 v2 {cell(g24, 'v2')}"
          f" · v3 {cell(g24, 'v3')}  — 갈리는 사건: **{only_v2 or '없다'}**")
    th = scoring._ordinal_heads(T24)
    for eid in only_v2:
        e = next(x for x in ev_all if x["id"] == eid)
        ih = scoring._ordinal_heads(e["text"])
        conflict = [h for h, o in ih.items() if th.get(h) and not (o & th[h])]
        agree = [h for h, o in ih.items() if th.get(h) and (o & th[h])]
        print(f"     {eid} «{e['text']}» — **재료 안**({e['at']['session']})이고"
              f" 그 세션 요약이 그것을 적는다")
        print(f"        항목 서수 머리 {ih}")
        print(f"        본문 서수 머리 "
              f"{ {h: sorted(th[h]) for h in ih if h in th} }")
        print(f"        합의하는 머리 {agree} · **어긋나는 머리 {conflict}**"
              f" → 겹침 비율과 무관하게 비생존")
    orig = scoring._ordinal_heads
    try:
        scoring._ordinal_heads = lambda t: {
            h: o for h, o in orig(t).items() if h != scoring._ORDINAL_MARKER}
        no_marker = scoring.survived_v3(T24, [e["text"] for e in ev_all])
    finally:
        scoring._ordinal_heads = orig
    print(f"  귀속: 머리 `{scoring._ORDINAL_MARKER}`를 빼고 다시 재면 v3 ="
          f" **{len(no_marker.survived)}/{g24['v3'][1]}**"
          f"  {'= v2 (귀속됐다)' if len(no_marker.survived) == g24['v2'][0] else '≠ v2'}")
    print("     🔴 **진단이지 수리가 아니다.** 고치면 `survived_v3`이라는 **같은"
          " 이름** 아래")
    print("     다른 채점기가 서고, 실험 26의 표가 그 이름으로 값을 갖고 있다"
          " (S16 실패 모드 ②).")
    print("     🔄 **정정 — 이 레인이 그 수리를 실제로 심어 보고 값을 쟀다:** 실험"
          " 26의 홀드아웃은")
    print("     **한 자리도 안 움직인다**(여전히 13/13 · 18/18). 그러니까 근거는"
          " «기록값이 깨진다»가")
    print("     아니라 **«값이 같으니 괜찮다»가 다음 코퍼스에서 성립하지 않는다**"
          "이고, 그 문장은")
    print("     `scoring.py`의 서수 절이 이미 적어 둔 것이다. 처음에 «기록값이"
          " 다른 수가 된다»고")
    print("     적었는데 **그것은 이 코퍼스에서 거짓이었다** — 심어 보지 않았으면"
          " 그대로 출하됐다.")
    print("  🔴 **근거 셋:**")
    print("     ① 실험 26의 홀드아웃은 «사건 × **한 세션** 요약» 쌍에서 쟀고 M2는")
    print("        «사건 × **24세션 이어붙임**»을 잰다. 자를 검증한 기하와 쓰는"
          " 기하가 다르고,")
    print("        §3.3 ④가 «분모가 아니라 자가 바뀐 것»을 가장 알아채기 어려운"
          " 형태라 적었다.")
    print("     ② 이 재료에서 v3의 **유일한** 차이가 위음성이다 (위 E004).")
    print("        v3이 실험 26에서 고친 것은 위양성 셋이었다 — 여기서는 방향이"
          " 반대다.")
    print("     ③ `digest_budget.py` 절 3의 기록물 대조군이 `survived_v2`라는"
          " 이름으로 서 있다.")
    print("        M2를 v2에 두면 X6의 두 값이 **재료 하나만** 다르다 —"
          " 변수가 둘이면 귀속이 안 된다.")
    print("  ⚠️ **v3을 버리는 것이 아니다.** 아래 모든 표에 `v3` 열이 이름을 달고"
          " 함께 선다.")
    print("     그리고 이 결정은 **이 기하에 한정된다** — 쌍 단위 채점에서는 실험"
          " 26의 판정이 그대로다.")

    # ── 3. 기준선 앵커 ──
    print("\n" + "-" * W)
    print("3. 기준선 앵커 — **재현되기 때문에 화살표를 그릴 수 있다**")
    print("-" * W)
    items_mixed = mixed_items(led)
    anchors = baseline_anchor(led, raw)
    print(f"  고정물 `{os.path.relpath(BASELINE_FILE, ROOT).replace(os.sep, '/')}`"
          f" — 이 실험이 읽는 행 **{len(anchors)}개**")
    nfact = len({f["id"] for f in led["facts"]} & {i["id"] for i in items_mixed})
    print(f"  항목 집합 재구성: 사실 {nfact} + 사건 {len(items_mixed) - nfact}"
          f" = **{len(items_mixed)}개** (구간 {BASELINE_SPAN[0]}–{BASELINE_SPAN[-1]})")
    print(f"     {[i['id'] for i in items_mixed]}")
    for row, depth, rec, got, same in anchors:
        print(f"  «{row}» (깊이 {depth})  기록 frozen **{rec['frozen']}**"
              f" · v2 **{rec['v2']}**  ← 파일에서 **읽었다**")
        print(f"       재계산 frozen {cell(got, 'frozen')} · v2 {cell(got, 'v2')}"
              f" · 판정불가 {got['v2'][2]}   {'✅ 재현' if same else '🔴 재현 실패'}")
    if not all(s for *_, s in anchors):
        print("  🔴 재현이 안 됐다. **화살표를 그릴 근거가 없다** — 종료 1")
        return 1
    A = {row: (depth, rec, got) for row, depth, rec, got, _ in anchors}
    B1, B2 = BASELINE_ROWS[0][0], BASELINE_ROWS[1][0]

    # ── 4. 표 A — 기준선과 **같은 항목 집합** ──
    print("\n" + "-" * W)
    print("4. 결과 — 🔴 **두 표를 가로줄로 가른다** (§3.3 ③)")
    print("-" * W)
    T12 = join(sums24[:len(BASELINE_SPAN)])
    a12, a24 = score_all(T12, items_mixed), score_all(T24, items_mixed)
    alife = score_all(lifetime, items_mixed)

    ARROW_ROW = "R27 깊이1 · 세션 요약 S01–S12"
    cols_a = [Col("기준선 재채점", "혼합 8사실+3사건 (판정불가 1 → 10)",
                  "S01–S12", s, same_item_set_as_baseline=True,
                  arrow=((ARROW_ROW, A[B1][1][s], cell(a12, s))
                         if s in A[B1][1] else None))
              for s in SCORER_NAMES]
    rows_a = [
        (ARROW_ROW, [cell(a12, s) for s in SCORER_NAMES]),
        ("R27 깊이1 · 세션 요약 S01–S24 †", [cell(a24, s) for s in SCORER_NAMES]),
        ("R27 깊이2 · lifetime ‡", [cell(alife, s) for s in SCORER_NAMES]),
        (f"기준선 «{B1}» (깊이 1) §",
         [A[B1][1].get(s, "—") for s in SCORER_NAMES]),
        (f"기준선 «{B2}» (깊이 2) §",
         [A[B2][1].get(s, "—") for s in SCORER_NAMES]),
    ]
    render("표 A — 기준선과 **같은 항목 집합**(혼합 11 · S01–S12)으로 재채점",
           cols_a, rows_a,
           note=("  † 항목 집합은 같지만 **재료 구간이 다르다**(24세션) — 참고로만"
                 " 두고 화살표를 안 건다.\n"
                 "  ‡ 깊이도 재료 구간도 다르다. 기준선 «" + B2 + "»가 같은 깊이"
                 "이지만 **재료 12세션 · 다른 지시**라\n"
                 "    두 변수가 함께 움직인다 — 그래서 같은 표에 두고도"
                 " **화살표는 안 건다.**\n"
                 "  § 기준선 두 행은 파일에서 **읽은** 값이고, `v3` 열은 파일에"
                 " 없다(그 채점기가 없던 때다).\n"
                 "    위 §3이 두 행을 같은 재료로 **다시 계산해 대조했고**,"
                 " 재현됐기 때문에 화살표를 건다."))

    print("\n  " + "─" * (W - 4))
    print("  🔴 **위 표와 아래 표 사이에 화살표를 그리지 않는다.** 분모가 둘 다"
          " `/10`이지만")
    print("     항목 집합이 다르다 — 이것이 실패 모드 ②의 가장 순수한 형태다(S16).")
    print("  " + "─" * (W - 4))

    # ── 5. 표 B — M2 (사건 10개) ──
    b12 = score_all(T12, ev_all)
    barc = score_all(join(archive), ev_all)
    blife = score_all(lifetime, ev_all)
    heavy = [e for e in ev_all if e.get("emotional_weight", 0) >= 0.8]
    bh = score_all(T24, heavy)

    cols_b = [Col("M2 사건", "events 10", "S01–S24", s) for s in SCORER_NAMES]
    rows_b = [
        ("이 라운드 재료 상한 (R27 24세션)", [cell(g24, s) for s in SCORER_NAMES]),
        ("R27 깊이2 · lifetime", [cell(blife, s) for s in SCORER_NAMES]),
        ("기록물 상한 (기록물 12세션)", [cell(barc, s) for s in SCORER_NAMES]),
        ("참고: R27 세션 요약 S01–S12", [cell(b12, s) for s in SCORER_NAMES]),
        (f"부분집합 w≥0.8 (events {len(heavy)} · R27 24세션)",
         [cell(bh, s) for s in SCORER_NAMES]),
    ]
    render("표 B — **M2 사건(events 10 · S01–S24)** — ⛔ 기준선 화살표 없음",
           cols_b, rows_b,
           note=(f"  판정불가: v2 {g24['v2'][2]} · v3 {g24['v3'][2]}"
                 f" (분모가 안 갈라진다 — `v3.unscorable`은 v2와 늘 같다)\n"
                 f"  생존(v2): {', '.join(g24['v2'][3]) or '없다'}\n"
                 f"  생존(v3): {', '.join(g24['v3'][3]) or '없다'}\n"
                 f"  lifetime 생존(v2): {', '.join(blife['v2'][3]) or '**없다**'}"))
    print("  🔴 **이 표에 기준선 화살표가 없는 이유는 «없다»이다** — 기준선의 혼합"
          " 11개 집합은")
    print("     사건 10개 집합이 아니고 `x/10`이라는 모양만 같다(§3.3 ②).")
    print(f"  🔴 **기록물 상한 {cell(barc, 'v2')}은 `digest_budget.py` 절 3의"
          f" 값과 같은 수다** — 같은 재료·")
    print("     같은 항목·같은 채점기이므로 그래야 한다. **두 값에 다른 이름을"
          " 준 것이 X6의 요구다.**")

    # ── 6. M3 ──
    print("\n" + "-" * W)
    print("6. M3 시간 순서 — 🔴 **M2가 그 텍스트에서 잡은 사건 위에서만** 정의된다")
    print("-" * W)
    cases = [("세션 요약 이어붙임 (R27 S01–S24)", T24, g24),
             ("lifetime (R27 깊이2)", lifetime, blife)]
    res = {}
    for label, text, got in cases:
        matched = [e for e in ev_all if e["id"] in got["v2"][3]]
        r = m3(text, matched)
        res[label] = r
        print(f"\n  {label}")
        print(f"    M2(v2)가 잡은 사건 **{len(matched)}건** → 위치를 얻은 것"
              f" **k={r.k}건** · 위치 불명 {len(r.lost)}건"
              f"{' ' + str(r.lost) if r.lost else ''}")
        print(f"    쌍 수 **{r.pairs if r.pairs is not None else '—'}**"
              f" (= k(k−1)/2)")
        if r.reason:
            print(f"    → **{r.reason}** — 숫자를 만들지 않는다")
            continue
        print(f"    → **M3 = {m3_fmt(r)}**  (항목 집합: M2(v2)가 매칭한 사건"
              f" {r.k} · 재료: {label} ·")
        print(f"       채점기: 첫 등장 오프셋 대 `at.session`)")
        print(f"       동률 위치 **{r.ties}쌍** — **불일치로 셌다**(이 규칙으로 갈"
              f" 수 없다).")
        if r.pairs - r.ties:
            print(f"       동률을 분모에서 빼면 {r.hit}/{r.pairs - r.ties} ="
                  f" {100.0 * r.hit / (r.pairs - r.ties):.1f}% — **두 수를 다"
                  f" 찍는다**(G15)")
        order = sorted((p, i) for i, p in r.pos.items())
        sess = {e["id"]: e["at"]["session"] for e in matched}
        print(f"       요약 내 순서: {[f'{i}@{p}' for p, i in order]}")
        print(f"       대장   순서: "
              f"{[i for _, i in sorted(order, key=lambda x: sess[x[1]])]}")
    r_cat = res[cases[0][0]]
    r_life = res[cases[1][0]]
    print("\n  🔴 **이어붙임의 53%대를 «요약이 순서를 잃었다»로 읽으면 틀린다.**")
    print("     처음엔 이 열이 거의 항등일 것이라 적었다 — 재료를 세션 순서로"
          " 붙였으므로")
    print("     오프셋이 세션 순서를 따라갈 것이라고. **출력이 그것을 반박했다.**")
    print("     범인 둘이 다 M2 쪽이다: ① 위양성 `E010`(S22)이 `서준`·`연락`으로")
    print("     **S01 블록**에 찍혀 7쌍을 혼자 깎는다 ② `E004`·`E005`·`E006`이"
          " `면접`")
    print("     하나로만 찾혀 **같은 오프셋**을 받아 3쌍이 갈 수 없다.")
    print("     🔴 즉 M3가 잰 것의 대부분은 **M2의 결함**이다 — §5 시나리오 3이")
    print("     예언한 «M2의 결함을 M3가 확인해 주는 형태»가 부호만 바꿔 나타났다.")

    # ── 7. M4 ──
    print("\n" + "-" * W)
    print("7. M4 사실 누출 — 🔴 **부호가 반대다. 낮을수록 준수**")
    print("-" * W)
    facts = led["facts"]
    f_sess, f_life = score_all(T24, facts), score_all(lifetime, facts)
    cols_m4 = [Col("M4 사실 누출",
                   f"facts {len(facts)}"
                   f" (판정불가 {f_sess['v2'][2]} → {f_sess['v2'][1]})",
                   "S01–S24", s) for s in SCORER_NAMES]
    rows_m4 = [
        ("R27 세션 요약 24 (사실 금지 **안 함**)",
         [cell(f_sess, s) for s in SCORER_NAMES]),
        ("R27 lifetime (사실 금지 **함**)",
         [cell(f_life, s) for s in SCORER_NAMES]),
        ("차이 (lifetime − 세션)",
         [f"{f_life[s][0] - f_sess[s][0]:+d}" for s in SCORER_NAMES]),
    ]
    render("표 C — **M4 사실 누출(facts 12 → 11)** — ⛔ 기준선 화살표 없음",
           cols_m4, rows_m4,
           note=(f"  판정불가 1건은 «지우에게 여동생이 한 명 있음» — 어근이 2개"
                 f" 미만이라 v2·v3이 같이 뺀다.\n"
                 f"  누출 항목(세션 요약 · v2): {', '.join(f_sess['v2'][3])}"))
    d2 = f_life["v2"][0] - f_sess["v2"][0]
    print(f"  **이 실험이 읽는 것은 차이 하나다: v2 기준 {d2:+d}.**")
    print("  `docs/14` P4가 사실을 금지하는 것은 **lifetime 층**이고 세션 층은 사실")
    print(f"  계층으로 가는 재료다. 그래서 세션 요약의 {cell(f_sess, 'v2')}은 위반이"
          f" 아니다 — **비교의 기준선**이다.")
    print("  🔴 **그런데 이 차이를 «지시가 작동했다»로 읽을 수 없다.**"
          f" 같은 lifetime의 M2도")
    print(f"     {cell(blife, 'v2')}다. 사실도 사건도 0이면 «사실을 안 썼다»와"
          f" «아무것도 안 남았다»가")
    print("     **같은 관측**이고 M4 혼자서는 그 둘을 가르지 못한다. ⭐핵심 1이"
          " M4의 해석에")
    print("     다시 나타난 자리다 — 그래서 이 −8 옆에 «준수»라는 낱말을 쓰지 않는다.")

    # ── 8. 표 규율 감사 ──
    print("\n" + "-" * W)
    print("8. 표 규율 감사 — §3.1·§3.3을 종료 코드로")
    print("-" * W)
    all_cols = cols_a + cols_b + cols_m4
    all_rows = ([r[0] for r in rows_a] + [r[0] for r in rows_b]
                + [r[0] for r in rows_m4])
    viol = rule.audit(all_cols) + rule.audit_rows(all_rows)
    print(f"  열 {len(all_cols)}개 · 행 라벨 {len(all_rows)}개 · 위반"
          f" **{len(viol)}건**  {'✅' if not viol else '🔴'}")
    for v in viol:
        print(f"     {v}")

    # ── 9. X1~X6 ──
    print_unmeasured(f"**{cell(g24, 'v2')}**", f"**{cell(barc, 'v2')}**",
                     f"**{cell(blife, 'v2')}**", r_life, r_cat, d2)

    # ── 10. 음성 대조 ──
    good, each = negative_controls(led, raw, r_cat, r_life)

    print("\n" + "=" * W)
    print(f"  M1 형식               : {hit1}/{tot1}"
          f"  (lifetime · `docs/14` P4 표제 3)")
    print(f"  M2 이 라운드 재료 상한 : {cell(g24, 'v2')}"
          f"  (events 10 · R27 24세션 · **v2**)   [v3 {cell(g24, 'v3')}]")
    print(f"  M2 기록물 상한        : {cell(barc, 'v2')}"
          f"  (events 10 · 기록물 12세션 · **v2**) ← 다른 이름, 화살표 없음")
    print(f"  M2 lifetime          : {cell(blife, 'v2')}"
          f"  (events 10 · R27 lifetime · **v2**)")
    print(f"  M3 이어붙임           : {m3_fmt(r_cat)}"
          f"  (동률 {r_cat.ties}쌍 포함)")
    print(f"  M3 lifetime          : {r_life.reason}")
    print(f"  M4 차이(v2)           : {d2:+d}"
          f"  (lifetime − 세션 · 낮을수록 준수 · **귀속 안 됨**)")
    print(f"  기준선 화살표          : 표 A의 «{ARROW_ROW}» 행 하나뿐")
    print(f"  표 규율 위반           : {len(viol)}건")
    print(f"  음성 대조 여섯 갈래     : 검사 {len(each)}건 —"
          f" {'✅ 전부 발화' if good else '🔴 발화 실패 ' + str(each)}")
    print(f"  lifetime 생성          : {lmeta['n_generated']}건 ·"
          f" {lmeta['wall_s']}초 · 정지 {lmeta['stalls']}회 ·"
          f" 이번 실행 {'1건' if fresh else '0건 (체크포인트)'}")
    print("=" * W)
    return 0 if (good and not viol) else 1


if __name__ == "__main__":
    sys.exit(main())
