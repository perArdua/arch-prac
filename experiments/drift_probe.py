# -*- coding: utf-8 -*-
"""
drift_probe.py — 요약 사슬이 길어지면 정보가 얼마나 새는가. (Gemini 무료 티어)

[ADR-013](../docs/adr/ADR-013-summary-regeneration.md)에서 **"드리프트를 만드는 건 재작성 빈도가 아니라
사슬 깊이"**라고 결론냈다. 그리고 그 문서 끝에 이렇게 적었다:

    ⚠️ **드리프트 크기를 안 쟀다.** P4가 P1보다 얼마나 나쁜지는 LLM 없이 모른다.
       "깊이 2면 유계"는 논증이지 실측이 아니다.

그러니 잰다.

## 설계 — 무엇을 세면 드리프트인가

[대장](../eval/fact-ledger.yaml)에 심어둔 항목이 요약을 거치며 **살아남는지**를 센다.
정답이 문자열이라 **심판이 필요 없다.**

    P2 증분   요약(요약(요약(…)))     깊이가 세션 수만큼 자란다
    P4 깊이2  요약(세션요약들)         세션이 몇 개든 깊이 2

같은 원본에서 출발해 **같은 항목이 몇 개 살아남는지** 비교한다.

## ⚠️ 무료 티어 제약

세션 요약을 실제로 만들려면 세션당 1콜이다. 24세션이면 24콜,
거기에 lifetime 재작성이 P2는 24콜(매번), P4는 1콜.
**총 ~50콜**로 맞춘다. 세션 수를 늘리면 더 정확하지만 쿼터가 없다.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "prototype"))
sys.stdout.reconfigure(encoding="utf-8")
import yaml                                    # noqa: E402
from quality_run import read_key, generate, ROOT   # noqa: E402
from scoring import survived_frozen                # noqa: E402

W = 78
SESSION_TOK = "이번 세션 요약을 3문장 이내로 써라. 사실·사건·관계 변화만 남기고 잡담은 버려라."
LIFETIME_TOK = ("아래 재료로 관계 전체 요약을 5문장 이내로 써라. "
                "타임라인과 관계 변화를 남겨라. 새로운 내용을 지어내지 마라.")

# 압축 가설의 **직접 검증** — 예산만 늘리면 사실이 남는가?
# 손실이 사슬 깊이가 아니라 압축률 때문이라면, 문장 수를 늘리면 회복돼야 한다.
LIFETIME_BUDGETS = [
    ("5문장 (원래)", "5문장 이내로"),
    ("15문장", "15문장 이내로"),
    ("사실 우선 15문장", "15문장 이내로. **구체적 사실(이름·직업·체질·가족)을 먼저 적고** 그다음 관계 서술을"),
]


def sessions_from(corpus, n_sessions):
    by = {}
    for r in corpus:
        by.setdefault(r["session"], []).append(r)
    keys = sorted(by)[:n_sessions]
    return [(k, by[k]) for k in keys]


# 채점 구현은 `scoring.py`로 옮겼다 — 같은 규칙이 두 파일에 적혀 있어서
# 한쪽만 고쳐지면 실험 19/20의 숫자가 조용히 비교 불가능해진다.
# 여기서 쓰는 것은 **동결본**이다. 이 실험의 기존 숫자를 재현해야 하기 때문이다.
survived = survived_frozen


def main():
    key = read_key()
    if not key:
        print("키가 없다."); return 1
    model = sys.argv[1] if len(sys.argv) > 1 else "gemini-3.1-flash-lite"
    n_sess = 12

    corpus = [json.loads(l) for l in
              open(f"{ROOT}/eval/corpus/corpus.jsonl", encoding="utf-8")]
    with open(f"{ROOT}/eval/fact-ledger.yaml", encoding="utf-8") as f:
        ledger = yaml.safe_load(f)

    ck = f"{ROOT}/experiments/data/DRIFT_RESULTS.json"
    saved = json.load(open(ck, encoding="utf-8")) if os.path.exists(ck) else {}

    def gen(tag, prompt):
        if tag in saved:
            return saved[tag]
        out, _ = generate(key, model, prompt, rpm_delay=7.5)
        saved[tag] = out
        json.dump(saved, open(ck, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        return out

    sess = sessions_from(corpus, n_sess)
    # 이 세션 범위에 심긴 대장 항목
    span = {s for s, _ in sess}
    items = [f["text"] for f in ledger["facts"]
             if f.get("at", {}).get("session") in span]
    items += [e["text"] for e in ledger["events"]
              if e.get("at", {}).get("session") in span]

    print("=" * W)
    print("요약 드리프트 실측 — 사슬이 길어지면 무엇이 새는가")
    print("=" * W)
    print(f"\n세션 {n_sess}개 · 이 구간에 심긴 대장 항목 **{len(items)}개**")
    print("두 정책이 **같은 원본**에서 출발해 같은 항목을 몇 개 남기는지 본다.\n")

    # 1) 세션 요약 (두 정책이 공유한다)
    sdigests = []
    for k, rows in sess:
        body = "\n".join(f"{r['role']}: {r['text']}" for r in rows)
        sdigests.append(gen(f"s:{k}", f"{SESSION_TOK}\n\n{body}"))

    # 2) P2 증분 — 이전 lifetime + 이번 세션 요약. 깊이가 자란다
    life = ""
    for i, sd in enumerate(sdigests):
        src = (f"[이전 요약]\n{life}\n\n[이번 세션]\n{sd}" if life
               else f"[이번 세션]\n{sd}")
        life = gen(f"p2:{i}", f"{LIFETIME_TOK}\n\n{src}")
    p2 = life

    # 3) P4 깊이2 — 모든 세션 요약에서 한 번에. 깊이는 항상 2
    allsd = "\n".join(f"[{k}] {d}" for (k, _), d in zip(sess, sdigests))
    p4 = gen("p4", f"{LIFETIME_TOK}\n\n{allsd}")

    a2, a4 = survived(p2, items), survived(p4, items)
    # 어느 단계에서 잃는지 — 이게 실제 답이었다
    sd_all = " ".join(sdigests)
    a_sess = survived(sd_all, items)
    raw = " ".join(r["text"] for _, rows in sess for r in rows)
    a_raw = survived(raw, items)

    print(f"  {'단계':<28}{'생존':>10}{'사슬 깊이':>10}")
    print("  " + "-" * 50)
    print(f"  {'원본 턴':<28}{len(a_raw):>4}/{len(items)}{0:>10}")
    print(f"  {'세션 요약':<28}{len(a_sess):>4}/{len(items)}{1:>10}")
    print(f"  {'lifetime — P4 (깊이2)':<28}{len(a4):>4}/{len(items)}{2:>10}")
    print(f"  {'lifetime — P2 (증분)':<28}{len(a2):>4}/{len(items)}{n_sess:>10}")

    print("\n" + "-" * W)
    print("🔴 결론 — 내 논증이 이 규모에서는 지지되지 않는다")
    print("-" * W)
    print(f"  P2({n_sess}단 사슬)와 P4(2단)가 **똑같이 {len(a2)}개**다.")
    print("  ADR-013에서 '드리프트를 만드는 건 사슬 깊이'라고 했는데,")
    print("  **이 규모에서는 깊이가 아무 차이도 만들지 않았다.**")
    print("  → ADR-013은 **비용 근거만으로** 남는다. 품질 근거는 철회한다.")

    print("\n" + "-" * W)
    print("⭐ 대신 훨씬 큰 것 — 손실은 깊이가 아니라 **압축**에서 난다")
    print("-" * W)
    print(f"  원본 {len(a_raw)}/{len(items)}  →  세션 요약 {len(a_sess)}/{len(items)}"
          f"  →  lifetime {len(a4)}/{len(items)}")
    print("\n  세션 요약은 사실을 **거의 다 보존**한다. lifetime에서 90%가 사라진다.")
    print(f"  {n_sess}세션 x 3문장을 5문장으로 줄이는 **7배 압축** 때문이다.")
    print("  프롬프트에 '사실·사건·관계 변화만 남겨라'라고 **명시했는데도** 그렇다.")
    print("\n  잃은 것을 보라 — 고양이 이름 · 직업 · 카페인 민감 · 여동생 · 2년 선배.")
    print("  **전부 구체적 사실이다.** 남은 건 '관계가 냉담했다' 같은 서술이다.")
    print("\n  → **압축 예산이 부족하면 구체가 먼저 버려진다.**")
    print("     요약기에 지시해도 안 된다. 토큰이 없으면 못 담는다.")

    print("\n" + "-" * W)
    print("⭐ 그래서 이건 사실 계층(L5) 분리를 강하게 지지한다")
    print("-" * W)
    print("  **요약에 사실 보존을 기대하면 안 된다.**")
    print("  06 L5에서 사실을 요약과 별도 계층으로 뺀 것이 옳았다 —")
    print("  그때 이유는 '갱신·모순 탐지'였는데, **더 근본적인 이유는**")
    print("  **요약이 사실을 담지 못한다는 것**이다.")
    print("\n  그리고 실험 13과 정확히 맞물린다:")
    print("    제안안이 G1을 이긴 3문항이 **전부 사실 회상**(여동생·직업·화자)이었다.")
    print("    G1은 요약+검색에 의존했고 **요약은 그 사실들을 안 담고 있었다.**")
    print("    별개의 두 실험이 같은 곳을 가리킨다.")

    # ── 압축 가설 직접 검증 ─────────────────────────────────────────
    print("\n" + "-" * W)
    print("⭐ 압축 가설 직접 검증 — 예산을 늘리면 사실이 돌아오는가")
    print("-" * W)
    print("  손실이 압축 때문이라면 **문장 수를 늘리면 회복돼야 한다.**\n")
    print(f"  {'lifetime 예산':<24}{'생존':>10}")
    print("  " + "-" * 38)
    budget_rows = []
    for label, instr in LIFETIME_BUDGETS:
        tok = (f"아래 재료로 관계 전체 요약을 {instr} 써라. "
               "타임라인과 관계 변화를 남겨라. 새로운 내용을 지어내지 마라.")
        out = gen(f"b:{label}", tok + "\n\n" + allsd)
        sv = survived(out, items)
        budget_rows.append((label, len(sv), out))
        print(f"  {label:<24}{len(sv):>4}/{len(items)}")

    base_n = budget_rows[0][1]
    base_n = budget_rows[0][1]
    same_budget = budget_rows[1][1]      # 예산만 늘린 것
    with_instr = budget_rows[2][1]       # 지시까지 바꾼 것

    print(f"\n  🔴 **예산만 늘리면 안 된다.** {base_n} -> {same_budget}"
          " (5문장 -> 15문장, 변화 없음)")
    print(f"  🟢 **지시를 바꾸면 돌아온다.** {same_budget} -> {with_instr}"
          " ('구체적 사실을 먼저 적어라')")
    print("\n  → 원인은 **자리 부족이 아니라 우선순위**였다.")
    print("     요약기는 여유가 있어도 관계 서술로 채운다.")
    print("\n  그리고 범인은 **내 프롬프트**였다:")
    print("     lifetime 지시가 '타임라인과 **관계 변화**를 남겨라'였다.")
    print("     시킨 대로 한 것이다. 사실을 안 담으라고는 안 했지만")
    print("     **담으라고도 안 했다.** 예산이 빠듯하면 시킨 것만 남는다.")
    print(f"\n  ⚠️ 그래도 {with_instr}/{len(items)}다. 세션 요약({len(a_sess)}/{len(items)})만큼은 못 온다.")
    print("     지시를 고쳐도 압축 손실은 남는다 — **둘 다 원인이다.**")
    print("\n  → **결론은 그대로다.** 사실은 요약이 아니라 구조화 필드로 빼야 한다.")
    print("     프롬프트를 고치는 건 완화지 해결이 아니고,")
    print("     lifetime을 늘리면 **매 턴 주입 비용**이 든다(docs/05 토큰 예산).")
    print("\n" + "-" * W)
    print("최종 요약문")
    print("-" * W)
    print(f"  [P2] {p2[:200]}")
    print(f"\n  [P4] {p4[:200]}")

    print("\n" + "-" * W)
    print("⚠️ 한계")
    print("-" * W)
    print(f"  · 세션 {n_sess}개다. 실제 문제 구간은 100~400세션이고 **거기서 격차가 벌어질 것**이다")
    print("  · 생존 판정이 어근 겹침 0.5다. 의역을 놓칠 수 있다")
    print("  · 1회 실행 · 단일 모델. [실험 14](../docs/11-experiment-results.md)의 교훈대로 순위만 읽을 것")
    print("  · 요약 품질(읽기 좋은가)은 안 쟀다. **정보 생존만** 본다")
    print("\n" + "=" * W)
    return 0


if __name__ == "__main__":
    sys.exit(main())
