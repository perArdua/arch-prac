# -*- coding: utf-8 -*-
"""
quality_report.py — 자동 채점 + 수기 판정을 합쳐 최종 표를 낸다. (API 호출 없음)

자동 채점만으로는 안 되는 이유가 [QUALITY_ADJUDICATION.yaml](QUALITY_ADJUDICATION.yaml)에 적혀 있다.
요지: gold의 상당수가 문자열이 아니라 **채점 기준**이고, abstention은
"되묻는 말투"와 "무지 인정"을 어휘로 못 가른다.
"""
import json, os, sys
sys.stdout.reconfigure(encoding="utf-8")
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = 78
ORACLE, PROP = "A1 Oracle (상한)", "C  제안안 (프로토타입)"


def main():
    with open(f"{ROOT}/experiments/data/QUALITY_RESULTS.json", encoding="utf-8") as f:
        res = json.load(f)
    with open(f"{ROOT}/experiments/data/QUALITY_ADJUDICATION.yaml", encoding="utf-8") as f:
        adj = yaml.safe_load(f)

    final, why = {}, {}
    for arm, rows in res.items():
        final[arm], why[arm] = {}, {}
        a = adj.get(arm, {}) or {}
        for r in rows:
            qid = r["id"]
            if qid in a:
                final[arm][qid] = a[qid]["ok"]
                why[arm][qid] = "수기: " + a[qid]["why"]
            else:
                final[arm][qid] = r["ok"] is True
                why[arm][qid] = "자동: " + str(r["why"])

    print("=" * W)
    print("응답 품질 — 최종 (자동 채점 + 수기 판정)")
    print("=" * W)
    print(f"\n모델 gemini-3.1-flash-lite · 26문항 · 104콜 · 규칙 채점 + 수기 판정")

    print(f"\n  {'arm':<26}{'정답':>12}")
    print("  " + "-" * 40)
    for arm in res:
        n = sum(1 for v in final[arm].values() if v)
        t = len(final[arm])
        star = "  ⭐" if arm in (ORACLE, PROP) else ""
        print(f"  {arm:<26}{n:>4}/{t} ={n/t*100:4.0f}%{star}")

    o, p = final[ORACLE], final[PROP]
    ids = [r["id"] for r in res[ORACLE]]
    l3 = [i for i in ids if not o[i]]
    l2 = [i for i in ids if o[i] and not p[i]]
    beat = [i for i in ids if p[i] and not o[i]]

    print("\n" + "-" * W)
    print("⭐ L2/L3 분해 — 이 검토가 가장 알고 싶어 한 숫자")
    print("-" * W)
    print(f"\n  L3 활용 실패 : {len(l3)}/{len(ids)} = {len(l3)/len(ids)*100:.0f}%")
    print( "     근거를 확실히 줬는데도 못 쓴 경우. **메모리 구조로는 못 고친다.**")
    print( "     " + ", ".join(l3))
    print(f"\n  L2 검색 실패 : {len(l2)}/{len(ids)} = {len(l2)/len(ids)*100:.0f}%")
    print( "     Oracle은 맞는데 제안안이 틀림. **메모리 구조로 고칠 수 있는 몫.**")
    print( "     " + ", ".join(l2))

    print("\n" + "-" * W)
    print("🔵 예상 못 한 것 — 제안안이 Oracle을 이긴 문항")
    print("-" * W)
    print(f"  {len(beat)}건: " + ", ".join(beat))
    print( "  전부 **abstention·정정** 유형이다. 왜 그런가:")
    print( "    Oracle은 정답 근거만 준다. abstention 문항은 근거가 '(해당 없음)'이라")
    print( "    모델이 **아는 게 없는 상태에서 지어냈다** ('초코잖아', '경영학과잖아').")
    print( "    제안안은 [알고 있는 것] 블록이 통째로 들어가서")
    print( "    '고양이는 나비고 강아지는 없다'를 **알기 때문에 부정할 수 있었다.**")
    print( "\n  → **모른다고 말하려면 무엇을 아는지를 알아야 한다.**")
    print( "     부정 지식은 정답 근거가 아니라 **경계 정보**에서 나온다.")
    print( "     Oracle(정답만 주입)은 abstention에서 상한이 아니다 — 평가 설계의 교훈이다.")
    print( "     그리고 이건 [docs/15](../docs/15-read-path-prompt.md)의 [흐릿한 것] 구획을 지지한다.")

    # ── 제안안 vs 현행 재현 ──────────────────────────────────────
    g = final.get("G1 현행 재현(추정)", {})
    if g:
        pw = [i for i in ids if p[i] and not g[i]]
        gw = [i for i in ids if g[i] and not p[i]]
        both = [i for i in ids if not g[i] and not p[i]]
        print("\n" + "-" * W)
        print("⭐ 제안안 vs 현행 재현(G1) — 5축 표의 마지막 빈칸")
        print("-" * W)
        print(f"  제안안 {sum(p.values())}/{len(ids)}  vs  G1 {sum(g.values())}/{len(ids)}"
              f"   (차이 {sum(p.values())-sum(g.values())}문항)")
        print(f"\n  제안안만 맞힘: {', '.join(pw)}")
        print( "     **전부 사실 회상·귀속이다** — 여동생 · 직업 · 누가 말했나.")
        print( "     정확히 [알고 있는 것] 결정적 주입이 담당하는 영역이다.")
        print( "     G1은 '누가 스타트업 얘기를 했나'에서 **'내가 했었지'로 화자를 뒤바꿨다.**")
        print(f"\n  G1만 맞힘: {', '.join(gw) or '없음'}")
        print(f"  둘 다 실패: {', '.join(both)}")
        print( "     다중세션·시간추론·갱신반영. **둘 다 못 푸는 L3 영역**이다.")
        print( "\n  ⚠️ 차이가 2문항이다. **26문항에서 이건 잡음 범위**다.")
        print( "     방향은 제안안 쪽이고 이유도 설명되지만 **우열을 단정하면 안 된다.**")
        print( "     기억 정확도에서 두 arm이 96% 동률이던 것과 일관된다 —")
        print( "     제안안의 이득은 회상량이 아니라 **정밀도와 결정성**에 있다.")

    # ── Oracle 명칭 정정 ────────────────────────────────────────
    if sum(p.values()) > sum(o.values()):
        print("\n" + "-" * W)
        print("🔴 'Oracle = 상한'이라는 이름이 틀렸다")
        print("-" * W)
        print(f"  제안안({sum(p.values())})이 Oracle({sum(o.values())})을 넘었다. 상한이 아래일 수 없다.")
        print( "  Oracle은 **정답 근거만** 준다 — 장기 요약도, 상시 사실도, 관계 상태도 없다.")
        print( "  그래서 abstention 문항(근거가 '없음')에서 **아는 게 없어 지어냈다.**")
        print( "  → Oracle은 **L3 활용 실패를 재는 데는 유효하지만 성능 상한은 아니다.**")
        print( "    상한을 재려면 '정답 + 전체 맥락'을 줘야 한다. 평가 설계의 교훈이다.")

    # ── 규칙 vs 기억 ────────────────────────────────────────────
    a0 = final.get("A0 기억없음 (바닥)", {})
    a0r = final.get("A0R 기억없음+규칙만", {})
    ab = [r["id"] for r in res[ORACLE] if r["type"] in ("abstention", "coverage")]
    if a0 and a0r:
        print("\n" + "-" * W)
        print("🔵 규칙 블록만으로는 환각이 안 막힌다 — 가설 반박")
        print("-" * W)
        print(f"  abstention·coverage {len(ab)}문항")
        print(f"    A0    규칙X 기억X : {sum(1 for i in ab if a0.get(i))}/{len(ab)}")
        print(f"    A0R   규칙O 기억X : {sum(1 for i in ab if a0r.get(i))}/{len(ab)}")
        print(f"    제안안 규칙O 기억O : {sum(1 for i in ab if p.get(i))}/{len(ab)}")
        print( "\n  **가설은 '규칙 블록이 차이를 만든다'였고, 반박됐다.**")
        print( "  규칙만 주면 없는 강아지 '루이' · '미술 전공' · '흰색 니트'를 여전히 지어낸다.")
        print( "  규칙이 살려낸 건 관계 설정만으로 반박되는 것뿐이었다('오빠가 어디 있다고').")
        print( "  → **환각 방어의 주된 힘은 규칙이 아니라 기억(경계 정보)에서 온다.**")
        print( "\n  ⚠️ A2(윈도우)의 abstention 성적은 액면대로 읽으면 안 된다.")
        print( "     A2는 **사실 문항도 거의 전부 회피**했다. '항상 모른다'는 퇴화 전략은")
        print( "     abstention에서 자동 만점이다. 진짜 실력은 답할 땐 답하는 것이다.")

    print("\n" + "-" * W)
    print("읽는 법")
    print("-" * W)
    print(f"  L3({len(l3)/len(ids)*100:.0f}%)가 L2({len(l2)/len(ids)*100:.0f}%)보다 크다.")
    print( "  → **메모리 구조를 완벽히 고쳐도 상한이 낮다.** 배치·프롬프트·생성 제어가 먼저다.")
    print( "  이건 유사 서비스 이용자들의 «재생성하면 대부분 다시 기억한다»는 후기와 같은 방향의 증거다.")

    print("\n" + "-" * W)
    print("⚠️ 이 숫자를 얼마나 믿어야 하나")
    print("-" * W)
    print("  · **판정자가 설계자와 같다.** 자기 제안에 유리하게 볼 유인이 있다.")
    print("    문항별 근거를 QUALITY_ADJUDICATION.yaml에 전부 적어 반박 가능하게 했다.")
    print("  · 26문항. 1건이 3.8%p다. **순위만 읽고 백분율은 신뢰하지 말 것**")
    print("  · Q09는 **근거가 gold를 뒷받침하지 않는다** — 평가 설계 결함이다")
    print("  · 합성 코퍼스 · 단일 모델 · 1회 실행(temperature 0.7이라 재현 시 흔들린다)")
    print("  · 행동 프로브 18개(PPR·페르소나)는 **여전히 미측정**이다")
    print("\n" + "=" * W)


if __name__ == "__main__":
    main()
