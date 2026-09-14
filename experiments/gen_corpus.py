"""
사실 대장에서 평가용 한국어 롤플레이 코퍼스를 역방향 생성한다.

목적: 검색 실험(evidence_recall@k, 빵 함정)에 쓸 데이터.
      좋은 산문이 필요 없다 — 사실 배치와 어휘 분포만 맞으면 된다.
      (품질 평가용 코퍼스는 LLM 생성이 필요하다. eval/README.md §6)

핵심 설계: 하드 네거티브를 의도적으로 심는다.
  F007_TRAP(크로와상 + "아쉽다")이 감정 장면에서 안 끌려오는지 보려면,
  노이즈에도 음식·아쉬움 어휘가 충분히 깔려 있어야 한다.
  네거티브 없이 트랩만 있으면 검색기가 우연히 통과한다.

실행: python experiments/gen_corpus.py
출력: eval/corpus/corpus.jsonl
"""

import json
import random
import sys
from pathlib import Path

import yaml

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "eval" / "fact-ledger.yaml"
OUT_DIR = ROOT / "eval" / "corpus"

SEED = 20260903
TURNS_PER_SESSION = 30

# ── 노이즈 발화 풀 ──────────────────────────────────────────────────────
# 대장에 없는 잡담. 65%를 채운다.
NOISE_USER = [
    "오늘 진짜 피곤하다", "야 뭐해", "나 방금 일어남", "밥 먹었어?",
    "회의 세 개 연속으로 함 ㅜ", "지하철 사람 너무 많아", "비 온다",
    "주말에 뭐 할까", "요즘 볼 만한 거 없나", "나 어제 밤새 게임함",
    "머리 자를까 고민중", "카톡 왜 안 봐", "아 짜증나", "오늘은 좀 괜찮아",
    "출근하기 싫다", "점심 뭐 먹지", "너 지금 어디야", "잠깐 나갔다 옴",
    "택배 왔다", "나 감기 걸린 듯", "책 한 권 다 읽었어", "운동 시작할까봐",
]
NOISE_CHAR = [
    "밥은 먹었냐", "그래서 어쩌라고", "……", "알아서 해라",
    "쉬어라 좀", "그거 별로던데", "나도 방금 일어났다", "택시 타고 가",
    "왜 또", "그래", "심심하면 나와라", "무리하지 말고",
    "됐고, 자라", "니가 알아서 잘하겠지", "춥다 옷 챙겨입고",
]

# ── 하드 네거티브 ──────────────────────────────────────────────────────
# F007_TRAP과 어휘가 겹치는 발화들. 검색 난이도를 만든다.
HARD_NEG_FOOD = [
    "점심에 파스타 먹었어", "어제 라면 먹고 잤다", "빵집 새로 생겼더라",
    "커피 대신 주스 마심", "디저트 먹고 싶다", "저녁 뭐 먹을지 모르겠어",
    "케이크 반 남겼어", "샌드위치로 때웠다",
]
HARD_NEG_REGRET = [
    "좀 아쉽네", "더 하고 싶었는데", "마지막이라 그런가 좀 그래",
    "아까 그거 못 해서 아쉬워", "다음엔 더 잘할게", "놓친 것 같아서",
]


def load_ledger():
    with open(LEDGER, encoding="utf-8") as f:
        return yaml.safe_load(f)


def planted_index(ledger):
    """(session, turn) -> [{id, text, kind}] 인덱스를 만든다."""
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
                f"[{f['text']}]가 더 이상 사실이 아님", "invalidation")

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
    """심은 항목을 대사로 변환. 산문 품질보다 어휘 정확성이 목적."""
    kind, text = item["kind"], item["text"]
    if kind == "fact":
        return "user", f"{text}. 말했었나?"
    if kind == "invalidation":
        return "user", f"아 참, {text}"
    if kind == "event":
        return "user", text
    if kind == "debt_setup":
        return "character", f"{text}. 잊지 마라"
    return "user", text


def generate(ledger, seed=SEED):
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
                # 같은 (세션,턴)에 여러 항목이 걸리면 뒤 턴으로 밀어낸다.
                # 밀지 않으면 조용히 소실되고 Oracle arm의 상한이 깨진다.
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

            # 노이즈. 하드 네거티브를 일정 비율로 섞는다.
            r = rng.random()
            if r < 0.12:
                text, role = rng.choice(HARD_NEG_FOOD), "user"
                kind = "hard_neg_food"
            elif r < 0.20:
                text, role = rng.choice(HARD_NEG_REGRET), "user"
                kind = "hard_neg_regret"
            elif t % 2 == 1:
                text, role, kind = rng.choice(NOISE_USER), "user", "noise"
            else:
                text, role, kind = rng.choice(NOISE_CHAR), "character", "noise"

            turns.append({
                "seq": seq, "session": sid, "turn": t,
                "role": role, "text": text,
                "planted_id": None, "kind": kind,
            })

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
    print(f"생성 완료: {out}")
    print(f"  총 턴          {n}")
    print(f"  심은 항목      {planted}  ({planted / n * 100:.1f}%)")
    print(f"  하드 네거티브  {hard_neg}  ({hard_neg / n * 100:.1f}%)")
    print(f"  순수 노이즈    {n - planted - hard_neg}  ({(n - planted - hard_neg) / n * 100:.1f}%)")
    print()
    print("⚠️ 이 코퍼스는 검색 실험 전용이다. 산문 품질이 낮아 응답 품질 평가에는 못 쓴다.")
    print("   품질 평가용 코퍼스는 LLM 생성이 필요하다 (eval/README.md §6).")


if __name__ == "__main__":
    main()
