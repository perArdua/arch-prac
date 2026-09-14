# -*- coding: utf-8 -*-
"""
summary_local.py — 요약을 어떻게 쓰고 어떻게 쌓을 것인가. (로컬 ollama)

## 왜 로컬인가

[실험 19](../docs/11-experiment-results.md)에서 요약이 사실을 1/11만 남긴다는 걸 봤다.
원인을 더 파려면 **프롬프트를 여러 벌 만들어 비교**해야 하는데, 그건 호출이 수십 번이다.
무료 티어로는 못 돌린다. 그리고 요약은 배치 경로라 **지연이 상관없으므로**,
로컬 모델로 충분하면 이 비용은 0이 된다. 그것 자체가 검증할 값어치가 있다.

## 무엇을 비교하나

A. 요약 지시    기본 / 사실 우선 / Chain of Density 2회 / 3회
B. 쌓는 방식    2층(세션->전체) / 3층(세션->구간->전체) / 증분(깊이가 자람)

채점은 [실험 19](drift_probe.py)와 **같은 함수**를 쓴다. 그래야 Gemini 결과와 직접 비교된다.

## 자료구조에 대해 이 실험이 말하려는 것

조사해보니 트리에도 두 종류가 있었다.
  RAPTOR식   의미가 비슷한 것끼리 묶는다. 시간 순서가 뭉개지고, 내용이 바뀌면 전체 재계산
  세그먼트   시간이 이어진 구간끼리 묶는다. 순서가 남고 해당 가지만 고치면 된다
대화는 시간 순서가 의미의 일부이므로 후자다. 그리고 **세션 경계가 구간을 공짜로 준다.**
지금의 2층 구조는 이미 깊이 2짜리 세그먼트 트리다. B는 거기에 층을 하나 얹어보는 것이다.
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "prototype"))
sys.stdout.reconfigure(encoding="utf-8")
import yaml                                              # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scoring import survived_frozen                      # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# `localhost`가 아닌 이유는 `prototype/embedding.py:24`의 주석이 정본이다 —
# 이 기기는 거절된 connect에 ~2.02초를 쓰고, `localhost`는 `::1`을 먼저 고른다.
HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
CK = f"{ROOT}/experiments/data/SUMMARY_LOCAL.json"
W = 78
N_SESS = 12
GROUP = 4          # 3층에서 몇 세션씩 묶을 것인가

SESSION_TOK = "이번 세션 요약을 3문장 이내로 써라. 사실·사건·관계 변화만 남기고 잡담은 버려라."

# ── A. 요약 지시 네 가지 ────────────────────────────────────────────────
BASE = ("아래 재료로 관계 전체 요약을 5문장 이내로 써라. "
        "타임라인과 관계 변화를 남겨라. 새로운 내용을 지어내지 마라.")
FACT_FIRST = ("아래 재료로 관계 전체 요약을 5문장 이내로 써라. "
              "구체적 사실(이름·직업·체질·가족·관계)을 **먼저** 적고 그다음 관계 서술을 써라. "
              "새로운 내용을 지어내지 마라.")
# Chain of Density: 길이를 고정한 채 빠진 항목만 채워 넣는다.
# 자리를 만들려면 기존 문장을 압축해야 하므로 모델이 스스로 우선순위를 푼다.
COD_STEP = ("위 요약에서 **빠진 구체적 사실 1~3개**를 재료에서 찾아 넣어라. "
            "길이는 그대로 5문장을 유지하고, 자리가 없으면 덜 중요한 서술을 압축해라. "
            "재료에 없는 내용을 지어내지 마라.\n\n"
            "[재료]\n{src}\n\n[현재 요약]\n{cur}\n\n[다시 쓴 요약]")


def call(model: str, prompt: str, tag: str, saved: dict) -> str:
    """ollama 한 번 호출. 결과는 체크포인트에 남겨 재실행을 공짜로 만든다."""
    if tag in saved:
        return saved[tag]
    body = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        # 재현성을 위해 온도를 0으로 둔다. 실험 13은 0.7이라 1회 실행이 못 미더웠다
        "options": {"temperature": 0, "seed": 20260908, "num_ctx": 8192},
    }).encode()
    req = urllib.request.Request(f"{HOST}/api/generate", body,
                                 {"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        out = json.loads(r.read())["response"].strip()
    # <think> 블록을 뱉는 모델이 있다. 요약만 남긴다
    if "</think>" in out:
        out = out.split("</think>", 1)[1].strip()
    saved[tag] = out
    saved[f"_ms:{tag}"] = int((time.time() - t0) * 1000)
    json.dump(saved, open(CK, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return out


# 채점 구현은 `scoring.py`로 옮겼다. 실험 19와 **같은 함수 객체**를 쓰므로
# "같은 기준이라 숫자가 비교된다"가 이제 규약이 아니라 사실이다.
survived = survived_frozen


def load():
    corpus = [json.loads(l) for l in
              open(f"{ROOT}/eval/corpus/corpus.jsonl", encoding="utf-8")]
    ledger = yaml.safe_load(open(f"{ROOT}/eval/fact-ledger.yaml", encoding="utf-8"))
    by = {}
    for r in corpus:
        by.setdefault(r["session"], []).append(r)
    sess = [(k, by[k]) for k in sorted(by)[:N_SESS]]
    span = {s for s, _ in sess}
    items = [f["text"] for f in ledger["facts"]
             if f.get("at", {}).get("session") in span]
    items += [e["text"] for e in ledger["events"]
              if e.get("at", {}).get("session") in span]
    return sess, items


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "qwen3:8b"
    saved = json.load(open(CK, encoding="utf-8")) if os.path.exists(CK) else {}
    sess, items = load()
    P = f"{model}:"                       # 모델별로 체크포인트를 분리한다

    print("=" * W)
    print(f"요약 설계 실측 — 지시와 층 수를 바꿔가며 (모델 {model})")
    print("=" * W)
    print(f"\n세션 {N_SESS}개 · 이 구간에 심긴 대장 항목 **{len(items)}개**")
    print("채점은 실험 19와 같은 함수다. 그래서 Gemini 결과와 그대로 비교된다.\n")

    # ── 세션 요약. 모든 조건이 이것을 공유한다 ─────────────────────────
    print("세션 요약 만드는 중...", end="", flush=True)
    sd = []
    for k, rows in sess:
        body = "\n".join(f"{r['role']}: {r['text']}" for r in rows)
        sd.append(call(model, f"{SESSION_TOK}\n\n{body}", f"{P}s:{k}", saved))
        print(".", end="", flush=True)
    print(" 완료")
    allsd = "\n".join(f"[{k}] {d}" for (k, _), d in zip(sess, sd))

    rows = []
    keep = lambda t: len(survived(t, items))

    # 세션 요약 자체는 얼마나 남기나 — 손실이 어느 단계에서 나는지 가른다
    rows.append(("세션 요약 (전체 합침)", keep(allsd), 1))

    # ── A. 요약 지시 ───────────────────────────────────────────────────
    base = call(model, f"{BASE}\n\n{allsd}", f"{P}a:base", saved)
    rows.append(("2층 · 기본 지시", keep(base), 2))

    ff = call(model, f"{FACT_FIRST}\n\n{allsd}", f"{P}a:ff", saved)
    rows.append(("2층 · 사실 우선", keep(ff), 2))

    cur = base
    for i in (1, 2):
        cur = call(model, COD_STEP.format(src=allsd, cur=cur), f"{P}a:cod{i}", saved)
        rows.append((f"2층 · 밀도 올리기 {i}회", keep(cur), 2))

    # ── B. 쌓는 방식 ───────────────────────────────────────────────────
    # 3층: 세션 요약을 GROUP개씩 시간순 구간으로 묶고, 구간 요약을 다시 묶는다
    mids = []
    for g in range(0, len(sd), GROUP):
        chunk = "\n".join(f"[{k}] {d}" for (k, _), d in zip(sess[g:g+GROUP], sd[g:g+GROUP]))
        mids.append(call(model, f"{BASE}\n\n{chunk}", f"{P}b:mid{g}", saved))
    l3 = call(model, f"{BASE}\n\n" + "\n".join(mids), f"{P}b:l3", saved)
    rows.append(("3층 · 세션→구간→전체", keep(l3), 3))

    # 증분: 이전 요약에 새 세션을 계속 덧붙인다. 깊이가 세션 수만큼 자란다
    life = ""
    for i, d in enumerate(sd):
        src = f"[이전 요약]\n{life}\n\n[이번 세션]\n{d}" if life else f"[이번 세션]\n{d}"
        life = call(model, f"{BASE}\n\n{src}", f"{P}b:inc{i}", saved)
    rows.append((f"증분 · 깊이가 {len(sd)}까지 자람", keep(life), len(sd)))

    # ── 표 ─────────────────────────────────────────────────────────────
    print(f"\n{'방식':<26}{'살아남은 항목':>14}{'거친 단계':>10}")
    print("-" * W)
    for name, n, depth in rows:
        bar = "█" * n + "·" * (len(items) - n)
        print(f"{name:<26}{n:>7}/{len(items)}  {bar:<12}{depth:>8}")
    print("-" * W)

    ms = [v for k, v in saved.items() if k.startswith("_ms:") and P in k]
    if ms:
        print(f"\n호출 {len(ms)}회 · 중앙값 {sorted(ms)[len(ms)//2]/1000:.1f}초 "
              f"· 합계 {sum(ms)/1000/60:.1f}분")
    print(f"체크포인트 {os.path.basename(CK)} — 다시 돌리면 캐시에서 읽는다")
    print("\n⚠️ 이 실험이 말할 수 없는 것")
    print("  · 요약이 좋아졌는지가 아니라 **심어둔 항목이 남았는지**만 센다")
    print("  · 어근 겹침 채점이라 뜻은 살았는데 말이 바뀐 경우를 놓친다")
    print("  · 세션 12개짜리다. 층 효과는 더 긴 구간에서 달라질 수 있다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
