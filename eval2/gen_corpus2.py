# -*- coding: utf-8 -*-
"""
eval2/gen_corpus2.py — **두 번째 코퍼스**를 대장에서 역방향 생성한다.

## 왜 이 파일이 `experiments/gen_corpus.py`의 사본이 아닌가

사상은 같다 — 대장을 먼저 확정하고 대화를 거기서 역방향으로 만든다.
**다른 것은 세 가지뿐이고 전부 사전 등록돼 있다** (`eval2/README.md` §1):

  ① 발화 풀     : 반말 롤플레이 → **존댓말 업무형**
  ② 하드 네거티브: 음식·아쉬움 → **비품·표기(숫자·영문·서수·버전)**
  ③ `render`    : `"~. 말했었나?"` → `"~. 이거 맞죠?"` 계열의 존댓말

🔴 **같게 둔 것** (§2): JSONL 일곱 키 · `role` 값역 · 세션/턴 표기 ·
   심은 항목의 화자 배치(fact·invalidation·event→user, debt_setup→character) ·
   하드 네거티브 문턱(`0.12` / `0.20`) · 노이즈 화자 교대 규칙(`t % 2`) ·
   같은 (세션,턴) 충돌 시 뒤 턴으로 밀어내는 규칙.
   이 목록이 «기존 계측기가 그대로 돈다»의 정의다.

🔴 **`eval/`에는 한 바이트도 쓰지 않는다** (A8). 출력은 `eval2/corpus/`뿐이다.

🔴 **자가저작.** 이 파일이 만드는 텍스트는 전부 한 저자(Claude Opus 5)가 쓴
   것이고 LLM 생성이 아니다. 선언은 `eval2/fact-ledger.yaml`의
   `meta.authorship`에 박혀 있다.

실행: PYTHONIOENCODING=utf-8 python -B eval2/gen_corpus2.py
출력: eval2/corpus/corpus.jsonl
"""

import json
import random
import sys
from pathlib import Path

import yaml

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
LEDGER = HERE / "fact-ledger.yaml"
OUT_DIR = HERE / "corpus"

SEED = 20260910
TURNS_PER_SESSION = 32

# ── 노이즈 발화 풀 ──────────────────────────────────────────────────────
#
# 🔴 축 ③ (문체) — 전부 존댓말이고 업무 맥락이다. 반말이 한 줄도 없다.
# 🔴 축 ③ (짧은 질의) — `"확인 부탁"`·`"네"`·`"OK"`는 **의도적으로 8자 미만**이다.
#    `Memory.gate`의 2번째 규칙(`len(utterance) < 8` → 차단)이 이 코퍼스에서
#    무엇을 하는지는 «짧은 발화가 실제로 있어야» 측정된다. eval의 발화는
#    거의 다 8자 이상이라 그 규칙이 잘 안 보였다.
NOISE_USER = [
    "오늘 일정 공유 부탁드립니다", "회의실 예약됐나요", "네 확인했습니다",
    "그 건은 보류하겠습니다", "메일 회신 부탁드려요", "슬랙 DM으로 주세요",
    "10분 뒤에 다시 보겠습니다", "링크 하나만 주세요", "오후에 시간 되세요",
    "우선순위 조정이 필요해 보입니다", "지금 자리 비웁니다",
    "확인 부탁", "네", "OK", "요약 부탁드려요",
    "Q3 목표 다시 볼까요", "PR 리뷰 부탁드립니다", "결재 라인 확인 부탁드립니다",
    "오늘은 여기까지 하겠습니다", "수고하셨습니다",
]
NOISE_CHAR = [
    "확인해서 알려드리겠습니다", "일정에 등록했습니다", "관련 문서 링크입니다",
    "담당자에게 전달했습니다", "아직 회신이 없습니다", "네, 반영했습니다",
    "오후 3시로 잡았습니다", "처리 완료했습니다", "확인 중입니다",
    "권한이 없어 조회가 안 됩니다", "5분 내로 정리해서 드리겠습니다",
    "네", "잠시만요", "해당 기록은 없습니다",
]

# ── 하드 네거티브 ──────────────────────────────────────────────────────
#
# eval에서 이 자리는 «음식 · 아쉬움»이었다. 여기서는 **트랩과 같은 소재군
# (비품·층·아깝다)**과 **표기(숫자·영문·서수·버전)**다. 트랩만 있고 경쟁
# 어휘가 없으면 검색기가 우연히 통과한다 — 그 설계 이유는 eval과 같다.
HARD_NEG_SUPPLY = [
    "3층 복합기 용지가 다 떨어졌습니다", "비품 신청서 올렸습니다",
    "토너 재고 확인 부탁드립니다", "A4 용지 2박스 주문했습니다",
    "마지막 한 장까지 다 썼네요", "버리기 아깝다고 하셔서 남겨뒀습니다",
]
# 🔴 축 ④ (표기) — 서수·버전·영문·퍼센트가 **노이즈에도** 깔린다.
#    `첫 번째 항목만`은 `scoring.survived_v3`의 서수 규칙과 정면으로 만난다.
HARD_NEG_NUM = [
    "버전 v1.9로 롤백했습니다", "PR #391 머지했습니다",
    "2차 검토는 다음 주입니다", "SLA는 99.5% 기준입니다",
    "AWS 비용이 12% 늘었습니다", "첫 번째 항목만 반영했습니다",
    "네 번째 줄이 잘못됐습니다",
]


def load_ledger():
    with open(LEDGER, encoding="utf-8") as f:
        return yaml.safe_load(f)


def planted_index(ledger):
    """(session, turn) -> [{id, text, kind}] 인덱스. `gen_corpus.py`와 같은 규칙."""
    idx = {}

    def put(sid, turn, item_id, text, kind):
        idx.setdefault((sid, turn), []).append(
            {"id": item_id, "text": text, "kind": kind})

    for f in ledger.get("facts", []):
        at = f.get("at")
        if at:
            put(at["session"], at["turn"], f["id"], f["text"], "fact")
        inv = f.get("invalidated_at")
        if inv:
            put(inv["session"], inv["turn"], f["id"] + "_INV",
                f"[{f['text']}]는 더 이상 유효하지 않습니다", "invalidation")

    for e in ledger.get("events", []):
        at = e["at"]
        put(at["session"], at["turn"], e["id"], e["text"], "event")

    for d in ledger.get("debts", []):
        s = d["setup"]
        put(s["session"], s["turn"], d["id"], d["content"], "debt_setup")

    return idx


def session_ids(ledger):
    return [f"S{i:02d}" for i in range(1, ledger["meta"]["sessions"] + 1)]


def render(item):
    """
    심은 항목을 대사로 변환.

    🔴 **화자 배치는 `gen_corpus.render`와 같다** — fact·invalidation·event는
       `user`, debt_setup은 `character`. 게이트 분모(=user 턴)의 구성이
       달라지면 두 코퍼스의 게이트 발화율을 나란히 놓을 수 없다.
       **바뀐 것은 어미뿐이다** (축 ③).
    """
    kind, text = item["kind"], item["text"]
    if kind == "fact":
        return "user", f"{text}. 이거 맞죠?"
    if kind == "invalidation":
        return "user", f"정정드립니다. {text}"
    if kind == "event":
        return "user", text
    if kind == "debt_setup":
        return "character", f"{text}. 기억해 두겠습니다"
    return "user", text


def generate(ledger, seed=SEED):
    """
    🔴 문턱 `0.12` / `0.20`과 화자 교대 규칙 `t % 2 == 1`은 `gen_corpus.generate`와
       **같은 값**이다. 노이즈 난이도를 축으로 삼지 않기 위해서다 (README §2).
    """
    rng = random.Random(seed)
    idx = planted_index(ledger)
    turns = []
    seq = 0

    pending = []
    for sid in session_ids(ledger):
        for t in range(1, TURNS_PER_SESSION + 1):
            seq += 1
            planted = pending.pop(0) if pending else idx.get((sid, t))

            if planted:
                # 같은 (세션,턴)에 여럿이면 뒤 턴으로 밀어낸다 — 안 밀면 조용히 소실된다.
                if len(planted) > 1:
                    pending.extend([[x] for x in planted[1:]])
                item = planted[0]
                role, text = render(item)
                turns.append({
                    "seq": seq, "session": sid, "turn": t,
                    "role": role, "text": text,
                    "planted_id": item["id"], "kind": item["kind"],
                })
                continue

            r = rng.random()
            if r < 0.12:
                text, role = rng.choice(HARD_NEG_SUPPLY), "user"
                kind = "hard_neg_supply"
            elif r < 0.20:
                text, role = rng.choice(HARD_NEG_NUM), "user"
                kind = "hard_neg_num"
            elif t % 2 == 1:
                text, role, kind = rng.choice(NOISE_USER), "user", "noise"
            else:
                text, role, kind = rng.choice(NOISE_CHAR), "character", "noise"

            turns.append({
                "seq": seq, "session": sid, "turn": t,
                "role": role, "text": text,
                "planted_id": None, "kind": kind,
            })

    if pending:
        # 밀어낸 항목이 마지막 세션 끝을 넘어가면 **조용히 사라진다.**
        # 사라진 채로 계측하면 대장과 색인이 어긋나므로 여기서 죽는다.
        raise RuntimeError(
            f"밀어낸 항목 {len(pending)}개가 배치되지 못했다 — 대장의 at 위치를 "
            f"조정할 것: {[p[0]['id'] for p in pending]}")
    return turns


def main():
    ledger = load_ledger()
    turns = generate(ledger)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "corpus.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for t in turns:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")

    n = len(turns)
    planted = sum(1 for t in turns if t["planted_id"])
    hard_neg = sum(1 for t in turns if t["kind"].startswith("hard_neg"))
    banned = [t for t in turns if "지우" in t["text"] or "서준" in t["text"]]
    print(f"생성 완료: {out}")
    print(f"  총 턴          {n}")
    print(f"  심은 항목      {planted}  ({planted / n * 100:.1f}%)")
    print(f"  하드 네거티브  {hard_neg}  ({hard_neg / n * 100:.1f}%)")
    print(f"  순수 노이즈    {n - planted - hard_neg}  "
          f"({(n - planted - hard_neg) / n * 100:.1f}%)")
    print(f"  🔴 축 ① 검사   '지우'·'서준' 출현 {len(banned)}회 (0이어야 한다)")
    print()
    print("🔴 자가저작: 저자 1명(Claude Opus 5) · LLM 미사용 · 결정적 생성(seed "
          f"{SEED}).")
    print("   선언 정본은 eval2/fact-ledger.yaml의 meta.authorship이다.")
    print("⚠️ 이 코퍼스도 **합성**이다. '두 번째 코퍼스'는 '실제 사용'이 아니다.")


if __name__ == "__main__":
    main()
