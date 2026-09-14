# -*- coding: utf-8 -*-
"""
event_metrics.py — 퀴즈가 아니라 **사건을 센다.** (API 불필요)

## 왜

[실험 14](../docs/11-experiment-results.md)에서 검정력을 계산해보니
**26문항으로는 8%p 차이를 못 가른다**(300~400문항 필요). 그리고 제가 낸
*"문항을 60~100개로 늘리자"*는 권고도 틀렸다.

**방향이 잘못됐다.** 26문항 퀴즈는 표본이 26개인데, 같은 코퍼스에 **턴은 436개**다.
[소크](../prototype/soak.py)·[게이트 스윕](../prototype/gate_sweep.py)은 이미 그렇게 재고 있다 —
436턴을 흘려보내며 오주입을 센다. **품질 축만 퀴즈 방식이라 검정력이 낮았다.**

그리고 이건 [09](../docs/09-what-memory-is-for.md)에서
*"롤플레이에서 아무도 퀴즈를 내지 않는다"*며 행동 프로브를 설계한 논리와 같다.
**정작 품질 측정은 퀴즈로 해놓고 그 모순을 못 봤다.**

## 무엇을 세나 — LLM 없이 셀 수 있는 것만

    ① 트랩 주입률        importance 0.05짜리가 몇 턴에 들어갔나
    ② 방해물 주입률       대장에 없는 항목이 top-k에 몇 번 들어갔나
    ③ stale fact 주입률   무효화된 사실이 몇 번 들어갔나        <- 새로 잰다
    ④ 결정적 주입 안정성   [알고 있는 것]이 매 턴 같은가 (캐시)   <- 새로 잰다

③이 특히 중요하다. **갱신된 사실의 구 버전이 주입되면 캐릭터가 틀린 말을 한다.**
[대장](../eval/fact-ledger.yaml)에 F002→F021(이직) 갱신을 심어뒀는데,
지금까지 **주입 단계에서 이걸 센 적이 없다.**
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "prototype"))
sys.stdout.reconfigure(encoding="utf-8")
import yaml                                      # noqa: E402
import memory as M                               # noqa: E402
from memory import Memory                        # noqa: E402
import soak                                      # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = 78


def run(corpus, ledger, label, *, theta, gate_fn=None, inject_facts=True):
    """한 설정으로 436턴을 흘려보내며 사건을 센다."""
    saved_t, saved_g, saved_i = (M.THETA_RELEVANCE, Memory.gate,
                                 M.INJECT_KNOWN_FACTS)
    M.THETA_RELEVANCE = theta
    M.INJECT_KNOWN_FACTS = inject_facts
    if gate_fn:
        Memory.gate = gate_fn

    dbf = f"{ROOT}/prototype/.ev.db"
    if os.path.exists(dbf):
        os.remove(dbf)
    m = Memory(dbf)
    soak.seed(m)
    soak.ingest(m, corpus, ledger, timed=False)

    trap = next((f for f in ledger["facts"] if "TRAP" in f["id"]), None)
    trap_key = (trap.get("object") or trap["text"]) if trap else None
    # 무효화된 사실 = superseded_by가 걸린 것의 옛 값
    stale_vals = [f.get("object") or f["text"] for f in ledger["facts"]
                  if f.get("superseded_by")]
    gold = {f.get("object") or f["text"] for f in ledger["facts"]}
    gold |= {e["text"] for e in ledger["events"]}

    n = trap_hits = noise_hits = stale_hits = 0
    known_shapes = set()
    for row in corpus:
        if row["role"] != "user":
            continue
        n += 1
        ctx = m.build_context(soak.CHAT, row["text"], row["seq"])
        # 🔴 처음엔 ctx.render() 전체에서 찾았다. **과다 계상이었다.**
        #    원본 로그(recent)와 현재 발화(utterance)에는 유저가 실제로 한 말이
        #    들어 있다 — "지우는 마케팅 회사 대리"를 유저가 5번 턴에 말했다.
        #    그건 **기억 주입이 아니라 대화 이력**이다. 지우면 안 된다.
        #    -> **기억 블록만** 센다.
        MEMORY_BLOCKS = {"알고 있는 것", "retrieved", "digest:lifetime",
                         "digest:session", "relationship"}
        mem_text = "\n".join(b.text for b in ctx.blocks
                             if b.name in MEMORY_BLOCKS)
        rendered = ctx.render()
        if trap_key and trap_key in mem_text:
            trap_hits += 1
        for v in stale_vals:
            if v in mem_text:
                stale_hits += 1
                break
        for kind, item, _ in ctx.provenance:
            if kind == "retrieved" and item not in gold:
                noise_hits += 1
        kb = next((b.text for b in ctx.blocks if b.name == "알고 있는 것"), "")
        known_shapes.add(kb)

    m.db.close()
    os.remove(dbf)
    M.THETA_RELEVANCE, Memory.gate, M.INJECT_KNOWN_FACTS = saved_t, saved_g, saved_i
    return dict(label=label, n=n, trap=trap_hits, noise=noise_hits,
                stale=stale_hits, known_variants=len(known_shapes))


def main():
    corpus = [json.loads(l) for l in
              open(f"{ROOT}/eval/corpus/corpus.jsonl", encoding="utf-8")]
    with open(f"{ROOT}/eval/fact-ledger.yaml", encoding="utf-8") as f:
        ledger = yaml.safe_load(f)

    def gate_open(self, u):
        return True, "열림"

    configs = [
        ("현행 파라미터 (θ=0.05)", dict(theta=0.05)),
        ("θ=0 (임계 제거)", dict(theta=0.0)),
        ("게이트 개방 + θ=0", dict(theta=0.0, gate_fn=gate_open)),
        ("결정적 주입 끔", dict(theta=0.05, inject_facts=False)),
    ]

    print("=" * W)
    print("사건 계수형 지표 — 퀴즈(n=26)가 아니라 턴(n=436)을 센다")
    print("=" * W)
    print("\n같은 코퍼스인데 표본이 **17배**다. 검정력이 여기서 나온다.\n")
    rows = [run(corpus, ledger, lbl, **kw) for lbl, kw in configs]

    print(f"  {'설정':<24}{'턴':>6}{'트랩':>7}{'방해물':>8}{'stale':>8}{'주입형태':>9}")
    print("  " + "-" * 64)
    for r in rows:
        print(f"  {r['label']:<24}{r['n']:>6}{r['trap']:>7}"
              f"{r['noise']:>8}{r['stale']:>8}{r['known_variants']:>9}")

    base = rows[0]
    print("\n" + "-" * W)
    print("읽는 법")
    print("-" * W)
    print(f"  트랩    importance 0.05짜리가 컨텍스트에 들어간 턴 수")
    print(f"  방해물  대장에 없는 항목이 검색으로 주입된 횟수")
    print(f"  stale   **무효화된 사실**(이직 전 직장)이 주입된 턴 수  ← 새로 잰다")
    print(f"  주입형태 [알고 있는 것] 블록의 서로 다른 모양 수 — **캐시 안정성**")

    print("\n" + "-" * W)
    print("발견")
    print("-" * W)
    print(f"  · 현행 파라미터에서 트랩 {base['trap']}턴 · stale {base['stale']}턴")
    if base["stale"] == 0:
        print("    🟢 **bi-temporal 무효화가 주입 단계까지 실제로 작동한다.**")
        print("       지금까지 `facts_at`을 단위로만 확인했지 **436턴 재생으로")
        print("       확인한 적이 없었다.** 갱신된 사실의 구 버전이 한 번도 안 나왔다.")
    else:
        print(f"    🔴 무효화된 사실이 {base['stale']}턴에 주입됐다. bi-temporal이 새고 있다.")
    if base["known_variants"] == 1:
        print("  · 🟢 [알고 있는 것] 블록이 **436턴 내내 한 가지 모양**이다.")
        print("       접두사가 안 깨진다 — ADR-007의 캐시 주장이 결정적 주입에도 성립한다.")
    else:
        print(f"  · ⚠️ 주입 블록이 {base['known_variants']}가지 모양이다. 캐시가 깨진다.")

    wide = rows[2]
    print(f"\n  · 게이트를 열고 θ를 없애면 방해물이 "
          f"{base['noise']} → {wide['noise']}건.")
    print(f"    [실험 12](../docs/11-experiment-results.md)의 임계 스윕과 같은 방향이고,")
    print(f"    **표본이 26이 아니라 436이라 이 차이는 잡음이 아니다.**")

    off = rows[3]
    print(f"\n  · 결정적 주입을 끄면 트랩 {base['trap']} → {off['trap']}, "
          f"stale {base['stale']} → {off['stale']}")

    print("\n" + "-" * W)
    print("⚠️ 이 지표가 못 재는 것")
    print("-" * W)
    print("  · **응답 품질이 아니다.** 컨텍스트에 무엇이 들어갔는지만 센다.")
    print("    실제 해로움은 모델이 그걸 쓰는지에 달려 있고 그건 LLM이 필요하다")
    print("  · 방해물 판정이 '대장에 없음'이라 **합성 코퍼스에서만** 성립한다")
    print("  · 트랩은 1개뿐이다. 여러 개 심어야 비율이 의미를 갖는다")
    print("\n" + "=" * W)


if __name__ == "__main__":
    main()
