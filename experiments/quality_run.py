# -*- coding: utf-8 -*-
"""
quality_run.py — 유일하게 비어 있던 축(응답 품질)을 잰다. Gemini 무료 티어용.

이 검토 내내 회상·비용·지연은 실측했지만 **응답 품질은 한 번도 못 쟀다.**
5축 중 가장 중요한 축이 비어 있었고, 그게 최대 한계였다.

## 왜 무료 티어로 되는가

[eval/README §7](../eval/README.md)의 Step 0 —
  "A1 Oracle arm만 돌려 L3 실패율 측정  ← 나머지 순서를 정한다"

이건 **LLM 심판이 필요 없다.** 정답이 문자열이라 규칙으로 채점된다.
심판이 필요한 건 행동 프로브(PPR·페르소나)인데, 그건 [05 §7.2](../docs/05-cost-latency-reality.md)에서
**"생성 모델과 다른 벤더"**로 정해뒀다. Gemini 하나만 있으면 자기선호 편향이 생기므로
**여기서는 QA만 돌리고 프로브는 안 돌린다.** 편향된 숫자를 내느니 없는 게 낫다.

## 무엇을 가르나 — L1/L2/L3 분해

    Oracle(정답 근거를 확실히 주입)에서도 틀림   → L3 활용 실패
    Oracle은 맞는데 실제 arm이 틀림 + 근거 미도달 → L2 검색 실패
    Oracle은 맞는데 근거가 애초에 저장 안 됨      → L1 저장 실패

**L3가 크면 메모리 구조를 아무리 고쳐도 상한이 낮다.** 그래서 이게 Step 0이다.

## 실행

    python experiments/quality_run.py --self-test    # 채점기 검증  (키 불필요)
    python experiments/quality_run.py --dry-run      # 프롬프트 조립 점검 (키 불필요)

    $env:GEMINI_API_KEY="..."                        # 본인 터미널에서
    python experiments/quality_run.py

키는 환경변수 GEMINI_API_KEY, 없으면 루트의 .gemini_key 파일에서 읽는다.
**스크립트는 키를 출력하지 않는다.** .gemini_key는 커밋하지 말 것.

⚠️ 키를 남의 셸(어시스턴트가 실행하는 셸 포함)에 `set`으로 넣지 말 것 —
   그 명령이 로그·대화 기록에 평문으로 남는다. 본인 터미널에서 돌리는 게 가장 깨끗하다.

무료 키: https://aistudio.google.com/apikey
⚠️ 무료 티어는 입력이 **구글 제품 개선에 사용**된다. 이 코퍼스는 전부 합성이라 무방하지만,
   실유저 대화로는 절대 돌리면 안 된다.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "prototype"))
sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://generativelanguage.googleapis.com/v1beta"
W = 78

PERSONA = (
    "너는 강서준. 27살, 대학 2년 선배. 무뚝뚝하고 툴툴대지만 챙기는 건 다 챙긴다.\n"
    "말투: 반말 / 1인칭 '나' / 어미 ~냐 ~다 ~지 / 존댓말·이모지 금지.\n"
    "상대는 지우. 연인 사이다."
)

RULES = (
    "\n[기억 사용 규칙]\n"
    "· 위는 재료다. 억지로 쓰지 마라. 안 써도 된다.\n"
    "· 위에 없는 건 모른다. 지어내지 마라. \"기억이 잘 안 나\"라고 말해도 된다.\n"
    "· 지우가 위 내용과 다르게 말하면 정정하라. 동조하지 마라.\n"
    "· 캐릭터로서 한두 문장으로 짧게 답하라.\n"
)


# ── Gemini 호출 (표준 라이브러리만) ──────────────────────────────────
def _post(url, payload, timeout=60):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def list_models(key):
    with urllib.request.urlopen(f"{API}/models?key={key}", timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    out = []
    for m in data.get("models", []):
        if "generateContent" in m.get("supportedGenerationMethods", []):
            out.append(m["name"].replace("models/", ""))
    return out


def generate(key, model, prompt, *, rpm_delay, max_retry=5):
    """429(무료 티어 쿼터)는 지수 백오프로 재시도한다."""
    url = f"{API}/models/{model}:generateContent?key={key}"
    # 🔴 여기서 하마터면 가짜 결과를 낼 뻔했다.
    #
    # maxOutputTokens=200에 thinking 기본값으로 돌렸더니 응답이 12~14자에서
    # 잘렸다 — "네 고양이 이름도 잊어". **모델은 답을 알고 있었는데
    # 사고 토큰이 예산을 다 먹고 본문이 중간에 끊긴 것**이다.
    # 그대로 채점했으면 L3(활용 실패) 50%라는 **완전히 틀린 숫자**가 나왔다.
    #
    # 사고를 끄려고 thinkingConfig=0을 보냈더니 이 모델이 400으로 거부했다.
    # -> 대신 예산을 넉넉히(2048) 줘서 사고 뒤에도 본문이 남게 한다.
    #    응답 자체는 짧게 나오므로(프롬프트에서 한두 문장 지시) 실제 비용은 작다.
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2048},
    }
    for attempt in range(max_retry):
        try:
            r = _post(url, payload)
            cands = r.get("candidates", [])
            if not cands:
                return "", r.get("promptFeedback", {})
            parts = cands[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts).strip()
            time.sleep(rpm_delay)
            return text, r.get("usageMetadata", {})
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:200]
            if e.code in (429, 503):
                wait = min(60, 5 * (2 ** attempt))
                print(f"    [{e.code}] 쿼터/과부하 — {wait}s 대기 후 재시도 "
                      f"({attempt+1}/{max_retry})")
                time.sleep(wait)
                continue
            raise RuntimeError(f"HTTP {e.code}: {body}") from None
    raise RuntimeError("재시도 한도 초과 — 무료 티어 일일 쿼터가 소진됐을 수 있다")


# ── 채점 — 규칙 기반. LLM 심판을 쓰지 않는다 ─────────────────────────
def _norm(s):
    return re.sub(r"[\s·,.!?~\"'\-]", "", s)


# 수량 표현 정규화 — "한 명"과 "하나"는 같은 답이다.
# 🔴 첫 판은 "명/개"만 다뤄서 **"세 번" vs "3번"을 못 맞췄다.**
#    Oracle이 "세 번 봤잖아"로 정답을 말했는데 오답 처리됐다 — 상한이 깎였다.
_NUM = [(r"(하나|한\s*[명개번회]|1\s*[명개번회])", "①"),
        (r"(둘|두\s*[명개번회]|2\s*[명개번회])", "②"),
        (r"(셋|세\s*[명개번회]|3\s*[명개번회])", "③"),
        (r"(넷|네\s*[명개번회]|4\s*[명개번회])", "④")]


# 프로토타입 _stem은 **비대칭**이다:  민감하다 -> 민감하   민감해서 -> 민감
# 그래서 같은 낱말이 gold와 응답에서 다른 어근으로 남는다.
# _stem 자체를 고치면 실험 11·12의 검색 결과가 바뀌므로 건드리지 않고,
# **채점기 쪽에만** 한 겹 더 씌워 어근을 맞춘다. (하다형 용언이 매우 흔하다)
_TAIL = re.compile(r"(하|해|한|히|잖|스럽|롭)+$")


def _root(w):
    from memory import _stem
    w = _stem(w)
    prev = None
    while prev != w and len(w) > 1:
        prev, w = w, _TAIL.sub("", w)
    return w


def _canon(s):
    """어미를 벗기고 수량 표현을 통일한다."""
    s = str(s)
    for pat, rep in _NUM:
        s = re.sub(pat, rep, s)
    return "".join(_root(re.sub(r"[^\w가-힣①②③④]", "", w)) for w in s.split())


def _content_tokens(gold):
    """gold를 내용 토큰으로 쪼갠다. 조사·수량사는 위에서 이미 통일됐다."""
    for pat, rep in _NUM:
        gold = re.sub(pat, rep, str(gold))
    toks = [_root(re.sub(r"[^\w가-힣①②③④]", "", w)) for w in gold.split()]
    return [t for t in toks if len(t) >= 1 and t not in ("안", "은", "는", "이", "가")]


def score(qtype, gold, answer):
    """
    반환: (정답 여부 | None, 근거).  **None은 "사람이 봐야 함"이다.**

    gold는 "안 된다 / 카페인 민감하다"처럼 **대안 표기**를 담는다.
    하나라도 맞으면 정답. abstention/coverage는 반대로 **모른다고 해야** 정답이다.

    ⚠️ 여기서 제 검색기와 똑같은 함정에 빠졌었다.
       단순 부분문자열로 채점하니 `민감하다` ≠ `민감하잖아`라서 **정답이 오답 처리**됐다.
       [FP-4](../docs/03-architecture-modules.md)의 교착어 문제가 이번엔 **채점기에서** 재현된 것이다.
       -> 어미 정규화(_stem)와 수량 표현 통일을 넣었다.

    그래도 어휘 채점은 의역을 못 잡는다. 그래서 **부분 일치는 자동 오답이 아니라
    '확인필요'로 뺀다.** 조용히 깎아내리느니 사람이 보는 게 낫다 — 26문항뿐이다.
    """
    a = _canon(answer)
    abstained = bool(re.search(
        r"(기억이?(잘)?안나|모르(겠|겠어|겠는)|기억안나|그런적없|말한적없|안했)",
        _norm(answer)))

    if qtype in ("abstention", "coverage"):
        # 🔴 여기를 정규식으로 자동 채점하려던 게 잘못이었다. 두 방향으로 틀렸다:
        #   "흰색 셔츠 입고 있었잖아. 기억 안 나냐?"  -> 지어냈는데 '회피'로 오인 (정답 처리)
        #   "너 강아지 안 키우잖아"                  -> 올바른 정정인데 오답 처리
        #   "그걸 내가 어떻게 기억하냐"               -> 인정인데 오답 처리
        # 되묻는 말투와 무지 인정을 어휘로 가를 수 없다. **전부 사람이 본다.**
        # abstention 4 + coverage 2 = 6문항뿐이라 읽는 비용이 작다.
        return None, "abstention/coverage — **사람이 판정** (지어냈나 vs 인정·정정했나)"

    if not gold:
        return None, "gold 없음 — 확인 필요"

    alts = [g for g in re.split(r"\s*/\s*", str(gold)) if g.strip()]
    best = 0.0
    for g in alts:
        if _canon(g) and _canon(g) in a:
            return True, f"'{g}' 포함"
        toks = _content_tokens(g)
        if toks:
            hit = sum(1 for t in toks if t in a)
            best = max(best, hit / len(toks))

    if best == 1.0:
        return True, "내용어 전부 일치"
    if best > 0:
        # 부분 일치는 **전부** 사람에게 넘긴다.
        # 약어("PM" = 프로덕트 매니저)나 의역은 어휘 채점으로 원리적으로 못 가른다.
        # 자동 오답 처리하면 시스템이 실제보다 나빠 보인다 — 26문항이니 눈으로 본다.
        return None, f"내용어 {best*100:.0f}% 일치 — **확인 필요**"
    if abstained:
        return False, "모른다고 회피 (근거는 있었는데 못 씀)"
    return False, "정답 없음"


# ── arm 구성 ────────────────────────────────────────────────────────
def build_arms(corpus, ledger, qs):
    """
    각 arm이 같은 질문에 대해 **어떤 컨텍스트를 주는지**만 다르다.
    생성 모델·온도·프롬프트 틀은 동일하게 고정한다.
    """
    from memory import Memory
    import soak

    text_of = {}
    for f in ledger.get("facts", []):
        text_of[f["id"]] = f.get("text") or f.get("object")
    for e in ledger.get("events", []):
        text_of[e["id"]] = e["text"]

    # 🔴 처음엔 G1에만 [장기 요약]을 넣고 제안안에는 안 넣었다 — **교란이었다.**
    #    이 요약은 Q06·Q09·Q12·Q14·Q15·Q16의 답을 직접 담고 있어서,
    #    G1이 6문항을 요약만으로 맞히고 제안안보다 높게 나왔다.
    #    비교가 성립하지 않는다 -> **두 arm에 같은 요약을 준다.**
    #    (프로토타입 build_context는 digest를 이미 지원한다. seed가 안 넣었을 뿐이다)
    LIFETIME = (
        "4월 대학 선후배로 다시 연락. 6월 썸, 7월 연인. "
        "7월 지우 반려묘 나비가 응급실. 8월 이직 문제로 다퉜다 화해. "
        "지우는 스타트업으로 이직해 한 달째."
    )

    # 제안안 — 프로토타입의 실제 읽기 경로
    dbf = os.path.join(ROOT, "prototype", ".quality.db")
    if os.path.exists(dbf):
        os.remove(dbf)
    m = Memory(dbf)
    soak.seed(m)
    soak.ingest(m, corpus, ledger, timed=False)
    m.db.execute("INSERT OR REPLACE INTO digest VALUES (?,?,?,?,?)",
                 (soak.CHAT, "lifetime", LIFETIME, corpus[-1]["seq"], None))
    m.db.commit()
    last = corpus[-1]["seq"]

    recent = [r for r in corpus if r["seq"] > last - 30]
    window = "\n".join(f"{r['role']}: {r['text']}" for r in recent)

    def arm_no_memory(q):
        # ⚠️ 규칙 블록이 없다. A0R와 짝을 이뤄 **규칙의 효과를 분리**한다.
        return f"{PERSONA}\n\n지우: {q['ask']}\n서준:"

    def arm_rules_only(q):
        # 🔴 A0가 abstention 6문항을 **전부 지어내는** 걸 보고 추가했다.
        #    없는 강아지 '뭉치', 없는 '그 형', 공항 사건, 전공, 옷차림까지.
        #    그런데 A0에는 기억도 없고 [기억 사용 규칙]도 없었다 — **교란이다.**
        #    A2(윈도우)는 규칙이 있었고 6문항을 전부 정직하게 회피했다.
        #
        #    그러면 차이를 만든 게 **기억인가 규칙인가?** 이 arm이 가른다.
        #    기억은 안 주고 **규칙만** 준다.
        #
        #    L3(활용 실패)가 지배적이라는 결과가 맞다면, 프롬프트 한 블록이
        #    환각을 크게 줄여야 한다 — 그게 "배치·프롬프트부터"의 직접 증거다.
        return f"{PERSONA}\n{RULES}\n지우: {q['ask']}\n서준:"

    # G1 현행 재현 — [arms_sim.py](arms_sim.py)의 arm_current_guess를 프롬프트로 옮긴다.
    #   계층 메모리(장기 요약) + **전 턴 RAG top-k** + 최근 10턴.
    #   제안안과의 차이는 **없는 것**으로 정의된다:
    #     · 상시 사실의 결정적 주입 없음 ([알고 있는 것] 없음)
    #     · 하드 게이트(τ) 없음 · 임계 컷(θ) 없음 · importance 가중 없음
    #     · 검색 게이팅 없음 (항상 검색)
    #   즉 **관련도만으로 뽑아 그대로 넣는다.**
    raw_docs = [r["text"] for r in corpus]

    def _topk_raw(query, k=5):
        """전 턴에 대한 bigram 중첩 top-k. 임계도 게이트도 없다."""
        from memory import bigrams
        qb = set(bigrams(query))
        scored = []
        for t in raw_docs:
            db = set(bigrams(t))
            if not db:
                continue
            scored.append((len(qb & db) / max(len(qb), 1), t))
        scored.sort(key=lambda x: -x[0])
        return [t for _, t in scored[:k]]

    def arm_current(q):
        hits = "\n".join(f"· {t}" for t in _topk_raw(q["ask"]))
        recent = "\n".join(f"{r['role']}: {r['text']}" for r in corpus[-10:])
        return (f"{PERSONA}\n\n[장기 요약]\n{LIFETIME}\n\n"
                f"[검색된 기억]\n{hits}\n\n[최근 대화]\n{recent}\n{RULES}\n"
                f"지우: {q['ask']}\n서준:")

    def arm_oracle(q):
        ev = [text_of[e] for e in q.get("evidence", []) if e in text_of]
        block = "\n".join(f"· {t}" for t in ev) or "· (해당 없음)"
        return (f"{PERSONA}\n\n[알고 있는 것]\n{block}\n{RULES}\n"
                f"지우: {q['ask']}\n서준:")

    def arm_window(q):
        return (f"{PERSONA}\n\n[최근 대화]\n{window}\n{RULES}\n"
                f"지우: {q['ask']}\n서준:")

    def arm_proposed(q):
        ctx = m.build_context(soak.CHAT, q["ask"], last)
        return f"{ctx.render()}\n{RULES}\n지우: {q['ask']}\n서준:"

    # ⭐ 순서 = 가치 순. 무료 쿼터가 중간에 죽어도 **가장 값진 것부터** 남는다.
    #    L3(활용 실패)는 Oracle만으로 나오고, L2는 Oracle+제안안이면 나온다.
    #    A2·A0는 있으면 좋은 대조군이다.
    return [
        ("A1 Oracle (상한)", arm_oracle),
        ("C  제안안 (프로토타입)", arm_proposed),
        ("G1 현행 재현(추정)", arm_current),
        ("A2 최근 30턴", arm_window),
        ("A0 기억없음 (바닥)", arm_no_memory),
        ("A0R 기억없음+규칙만", arm_rules_only),
    ], m, dbf


SELF_TEST_CASES = [
    # (유형, gold, 응답, 기대)  — 채점기가 조용히 틀리면 모든 숫자가 무의미해진다
    ("single_hop", "나비", "나비잖아. 벌써 잊었냐.", True),
    ("single_hop", "나비", "글쎄, 기억이 잘 안 나는데.", False),
    ("single_hop", "안 된다 / 카페인 민감하다",
     "너 카페인 민감하잖아. 마시지 마라.", True),          # 어미 차이 흡수
    ("single_hop", "안 된다 / 카페인 민감하다", "마셔도 되지 뭐.", False),
    ("single_hop", "여동생 한 명", "여동생 하나 있다고 했지.", True),  # 수량 표현 통일
    ("single_hop", "스타트업 프로덕트 매니저",
     "스타트업에서 PM 하잖아.", None),                     # 약어 -> 사람이 판정
    # abstention/coverage는 **의도적으로 None**(사람 판정)이다.
    # 되묻는 말투와 무지 인정을 어휘로 못 가른다는 걸 실측에서 확인했다.
    ("abstention", None, "그런 적 없는데?", None),
    ("abstention", None, "아 그거 재밌었지.", None),
    ("coverage", None, "초반은 기억이 잘 안 나.", None),
]


def read_key():
    """
    키를 읽는다. **절대 출력하지 않는다.**

    두 경로를 둔 이유:
      1) 환경변수 GEMINI_API_KEY — 본인 터미널에서 직접 돌릴 때
      2) 파일 .gemini_key       — 어시스턴트가 대신 돌려야 할 때

    (2)가 필요한 이유: 환경변수를 어시스턴트가 실행하는 셸에 넣으려면
    `set KEY=...` 같은 명령을 어시스턴트가 실행해야 하고, 그러면
    **키가 대화 기록에 평문으로 남는다.** 파일로 두면 값이 오가지 않는다.

    .gemini_key는 커밋하지 말 것. 값이 필요 없어지면 파일을 지우면 된다.
    """
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    if k:
        return k
    f = os.path.join(ROOT, ".gemini_key")
    if os.path.exists(f):
        with open(f, encoding="utf-8") as fh:
            return fh.read().strip()
    return ""


def self_test():
    """채점기 검증. 여기가 틀리면 나머지 숫자가 전부 의미 없다."""
    bad = 0
    print("채점기 검증 — 규칙 채점이 한국어 어미·수량 표현을 견디는가\n")
    for qtype, gold, ans, exp in SELF_TEST_CASES:
        ok, why = score(qtype, gold, ans)
        mark = "OK  " if ok == exp else "FAIL"
        bad += ok != exp
        print(f"  [{mark}] 기대={str(exp):<5} 실제={str(ok):<5} "
              f"{why[:32]:<34} <- {ans[:24]}")
    print("\n" + ("통과 — 채점기를 신뢰할 수 있다" if not bad
                  else f"🔴 {bad}건 불일치. 고치기 전에는 실행하지 말 것"))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemini-2.5-flash")
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="키 없이 프롬프트 조립과 채점만 점검")
    ap.add_argument("--rpm", type=int, default=10,
                    help="분당 요청 수 상한 (무료 티어 기본 10)")
    ap.add_argument("--limit", type=int, default=0, help="문항 수 제한 (시험용)")
    ap.add_argument("--self-test", action="store_true",
                    help="채점기만 검증한다 (키 불필요)")
    ap.add_argument("--rescore", action="store_true",
                    help="저장된 응답을 다시 채점한다 (API 호출 없음)")
    ap.add_argument("--repeat", type=int, default=1,
                    help="같은 arm을 N회 반복 실행해 **잡음 폭**을 잰다")
    ap.add_argument("--only", default="",
                    help="이 문자열로 시작하는 arm만 돌린다 (쉼표 구분)")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    if args.rescore:
        # 저장된 응답을 **다시 채점**한다. API 호출이 없으므로 공짜이고,
        # 쿼터가 소진돼도 채점 규칙을 얼마든지 고쳐 다시 돌릴 수 있다.
        # -> 응답 원문을 저장해둔 것이 여기서 값을 한다.
        ck = f"{ROOT}/experiments/QUALITY_RESULTS.json"
        with open(ck, encoding="utf-8") as f:
            res = json.load(f)
        changed = 0
        for aname, rows in res.items():
            for r in rows:
                ok, why = score(r.get("type"), r.get("gold"), r.get("ans", ""))
                if ok != r.get("ok"):
                    changed += 1
                r["ok"], r["why"] = ok, why
        with open(ck, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        print(f"재채점 완료 — {changed}건의 판정이 바뀌었다.\n")
        for aname, rows in res.items():
            n = sum(1 for r in rows if r["ok"] is True)
            fl = sum(1 for r in rows if r["ok"] is False)
            u = sum(1 for r in rows if r["ok"] is None)
            print(f"  {aname:<26} 정답 {n:>2}  오답 {fl:>2}  **사람판정 {u:>2}**")
        return 0

    key = read_key()
    if args.list_models:
        if not key:
            print("GEMINI_API_KEY 환경변수가 필요하다."); return 1
        for n in list_models(key):
            print(" ", n)
        return 0
    if not key and not args.dry_run:
        print("키를 못 찾았다. 둘 중 하나로 넣는다:")
        print("  1) 본인 터미널:  $env:GEMINI_API_KEY=\"...\"  후 직접 실행  (권장)")
        print("  2) 파일:        프로젝트 루트에 .gemini_key 파일로 저장")
        print("무료 발급: https://aistudio.google.com/apikey")
        print("점검만 하려면: python experiments/quality_run.py --dry-run")
        return 1

    import yaml
    corpus = [json.loads(l) for l in
              open(f"{ROOT}/eval/corpus/corpus.jsonl", encoding="utf-8")]
    with open(f"{ROOT}/eval/fact-ledger.yaml", encoding="utf-8") as f:
        ledger = yaml.safe_load(f)
    with open(f"{ROOT}/eval/questions.yaml", encoding="utf-8") as f:
        qs = yaml.safe_load(f)["qa_questions"]
    if args.limit:
        qs = qs[:args.limit]

    arms, mem, dbf = build_arms(corpus, ledger, qs)
    delay = 60.0 / max(args.rpm, 1)

    print("=" * W)
    print("응답 품질 실측 — 비어 있던 5번째 축")
    print("=" * W)
    print(f"\n모델 {args.model} · 문항 {len(qs)} · arm {len(arms)} "
          f"· 총 {len(qs)*len(arms)}콜 · 분당 {args.rpm}")
    print("채점은 **규칙 기반**이다 — LLM 심판을 쓰지 않으므로 자기선호 편향이 없다.\n")

    # 🔴 무료 티어는 **하루 20~ 건**짜리 모델이 있다(gemini-3.6-flash가 그랬다).
    #    첫 실행에서 7콜 만에 429가 났고 크래시하면서 **진행분을 통째로 잃었다.**
    #    -> 매 콜마다 체크포인트에 쌓고, 재실행하면 **이미 받은 응답은 건너뛴다.**
    #       쿼터가 죽어도 진행분은 남고, 내일 이어서 채울 수 있다.
    ckpt = f"{ROOT}/experiments/QUALITY_RESULTS.json"
    done = {}
    if os.path.exists(ckpt) and not args.dry_run:
        try:
            with open(ckpt, encoding="utf-8") as f:
                for a, rows in json.load(f).items():
                    for r in rows:
                        if r.get("model") == args.model:
                            done[(a, r["id"])] = r
        except Exception:
            done = {}
    if done:
        print(f"체크포인트에서 {len(done)}건 복구 — 그만큼 호출을 아낀다.\n")

    def save(res):
        # 🔴 처음엔 res를 그대로 덮어썼다. --only/--repeat로 일부 arm만 돌리면
        #    **나머지 arm의 기존 결과가 통째로 지워진다.** 병합해야 한다.
        prev = {}
        if os.path.exists(ckpt):
            try:
                with open(ckpt, encoding="utf-8") as f:
                    prev = json.load(f)
            except Exception:
                prev = {}
        prev.update({k: v for k, v in res.items() if v})
        with open(ckpt, "w", encoding="utf-8") as f:
            json.dump(prev, f, ensure_ascii=False, indent=2)

    results = {a: [] for a, _ in arms}
    exhausted = False
    # --repeat: 같은 프롬프트를 여러 번 돌려 **run-to-run 흔들림**을 잰다.
    # temperature 0.7이라 같은 입력도 다른 답이 나온다. 1회 실행으로 낸 2문항 차가
    # 실재하는 차이인지 표집 잡음인지는 **이걸 재봐야만** 안다.
    only = [t.strip() for t in args.only.split(",") if t.strip()]
    if only:
        arms = [(n, f) for n, f in arms if any(n.startswith(t) for t in only)]
    if args.repeat > 1:
        arms = [(f"{n} #r{i}", f) for i in range(1, args.repeat + 1)
                for n, f in arms]
        results = {n: [] for n, _ in arms}

    for aname, fn in arms:          # arm 순서 = 가치 순서. 쿼터가 죽어도 앞부터 남는다
        rows = results[aname]
        print(f"── {aname} " + "─" * (W - len(aname) - 4))
        for q in qs:
            if (aname, q["id"]) in done:
                rows.append(done[(aname, q["id"])])
                continue
            if exhausted:
                continue
            prompt = fn(q)
            if args.dry_run:
                ans, ok, why = "[dry-run]", None, "미실행"
            else:
                try:
                    ans, _ = generate(key, args.model, prompt, rpm_delay=delay)
                except RuntimeError as e:
                    print(f"\n  🔴 중단: {e}")
                    print( "     여기까지는 체크포인트에 저장됐다. 쿼터가 회복되면")
                    print(f"     같은 명령을 다시 돌리면 **이어서** 진행한다.\n")
                    exhausted = True
                    continue
                ok, why = score(q.get("type"), q.get("gold"), ans)
            rows.append(dict(id=q["id"], type=q.get("type"), ok=ok, why=why,
                             ans=ans, gold=q.get("gold"), model=args.model))
            if not args.dry_run:
                save(results)
            mark = "  ?" if ok is None else ("  ✓" if ok else "  ✗")
            print(f"{mark} {q['id']} {str(q.get('type')):<18} {ans[:44]}")
        if not args.dry_run and rows:
            n = sum(1 for r in rows if r["ok"] is True)
            print(f"    → 정답 {n}/{len(rows)}"
                  f"{'  ⚠️ 미완' if len(rows) < len(qs) else ''}\n")

    mem.db.close()
    os.remove(dbf)

    if args.dry_run:
        print("\n" + "=" * W)
        print("dry-run 완료 — 프롬프트 조립과 채점 경로가 정상이다.")
        print("키를 넣고 다시 돌리면 실제 숫자가 나온다.")
        print("=" * W)
        return 0

    # ── L1/L2/L3 분해 ────────────────────────────────────────────────
    print("=" * W)
    print("결과")
    print("=" * W)
    print(f"\n  {'arm':<26}{'정답':>10}")
    print("  " + "-" * 38)
    for aname, rows in results.items():
        n = sum(1 for r in rows if r["ok"])
        print(f"  {aname:<26}{n:>5}/{len(rows)} = {n/len(rows)*100:3.0f}%")

    oracle = {r["id"]: r for r in results.get("A1 Oracle (상한)", [])}
    prop = {r["id"]: r for r in results.get("C  제안안 (프로토타입)", [])}
    if not oracle:
        print("\n  Oracle arm이 비어 있어 L1/L2/L3 분해를 할 수 없다.")
        print("  쿼터가 회복되면 같은 명령으로 이어서 돌릴 것.")
        return 0
    l3 = [i for i in oracle if oracle[i]["ok"] is False]
    l2 = [i for i in prop if prop[i]["ok"] is False and oracle.get(i, {}).get("ok") is True]

    print("\n" + "-" * W)
    print("⭐ L1/L2/L3 분해 — 이 검토가 가장 알고 싶어 한 숫자")
    print("-" * W)
    if len(oracle) < len(qs):
        print(f"  ⚠️ Oracle {len(oracle)}/{len(qs)}문항만 완료 — 아래는 **부분 결과**다\n")
    print(f"  L3 활용 실패 : {len(l3)}/{len(oracle)} = {len(l3)/len(oracle)*100:.0f}%")
    print( "     근거를 확실히 줬는데도 못 쓴 경우. **메모리 구조로는 못 고친다.**")
    if l3:
        print("     " + ", ".join(l3))
    dn = len(prop) or 1
    print(f"\n  L2 검색 실패 : {len(l2)}/{dn} = {len(l2)/dn*100:.0f}%"
          + ("  (제안안 arm 미완)" if len(prop) < len(oracle) else ""))
    print( "     Oracle은 맞는데 제안안이 틀림. **메모리 구조로 고칠 수 있는 몫.**")
    if l2:
        print("     " + ", ".join(l2))

    print("\n" + "-" * W)
    print("읽는 법")
    print("-" * W)
    print("  L3가 크면 → 배치·프롬프트부터 손대야 한다. 검색을 고쳐도 상한에 막힌다")
    print("  L2가 크면 → 메모리 구조 개선의 여지가 실제로 크다")
    print("  A1과 C의 격차가 곧 **구조 개선으로 얻을 수 있는 최대치**다")

    out = f"{ROOT}/experiments/QUALITY_RESULTS.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n  원본 응답 저장: {out}")

    print("\n" + "-" * W)
    print("⚠️ 이 실험이 말할 수 없는 것")
    print("-" * W)
    print("  · **행동 프로브 18개를 안 돌렸다.** 심판이 필요한데 같은 벤더뿐이라")
    print("    자기선호 편향이 생긴다. PPR·페르소나 유지는 여전히 미측정이다")
    print("  · 규칙 채점은 **표현이 다른 정답을 놓칠 수 있다.** 원본 응답을 같이 저장하니")
    print("    QUALITY_RESULTS.json을 눈으로 확인할 것")
    print("  · 문항 26개. 1건이 3.8%p다")
    print("  · 합성 코퍼스다. 절대 성능이 아니라 **arm 간 순위**로만 읽어야 한다")
    print("\n" + "=" * W)
    return 0


if __name__ == "__main__":
    sys.exit(main())
