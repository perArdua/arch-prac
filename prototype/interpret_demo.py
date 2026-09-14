"""
L8 해석 누적 데모 — "3회 이상이면 해석 생성"을 실제로 구현하면 무엇이 필요한가.

수기 세션(S05→S13→S19)에서 "해석은 한 번에 안 생긴다"를 발견하고
docs/06 L8에 최소 근거 수 정책을 넣었다. 그런데 **핵심 질문에 답하지 않았다**:

    관찰 A와 관찰 B가 "같은 패턴"인지 어떻게 아는가?

3회를 세려면 무엇을 3회 셀지 정해야 한다. 구현하면 이게 바로 드러난다.

실행: python prototype/interpret_demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from memory import bigrams  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

MIN_EVIDENCE = 3
SIM_THRESHOLD = 0.30

# 수기 세션에서 뽑은 관찰 + 함정
OBSERVATIONS = [
    ("S05", "힘든 얘기 하다가 젤리 얘기로 화제를 돌렸다", "회피"),
    ("S08", "칭찬을 받자 화제를 돌렸다", "칭찬거부"),
    ("S13", "이직 스트레스를 물으니 케이크 얘기로 화제를 돌렸다", "회피"),
    ("S16", "잘했다고 하자 화제를 돌렸다", "칭찬거부"),
    ("S19", "나비 응급실 상황에서 회의 자료 얘기로 화제를 돌렸다", "회피"),
    ("S22", "힘든 얘기를 먼저 꺼내고 끝까지 했다", "회피_반증"),
]


def sim(a, b):
    """Jaccard on normalized bigrams — 어휘 유사도만 본다."""
    A, B = set(bigrams(a)), set(bigrams(b))
    return len(A & B) / max(len(A | B), 1)


def cluster(obs, threshold):
    """관찰을 어휘 유사도로 묶는다. 이게 '같은 패턴' 판정의 전부다."""
    clusters = []
    for sess, text, truth in obs:
        best, best_s = None, 0.0
        for c in clusters:
            s = max(sim(text, t) for _, t, _ in c)
            if s > best_s:
                best, best_s = c, s
        if best is not None and best_s >= threshold:
            best.append((sess, text, truth))
        else:
            clusters.append([(sess, text, truth)])
    return clusters


def report(threshold):
    cs = cluster(OBSERVATIONS, threshold)
    print(f"\n임계 {threshold:.2f} — 클러스터 {len(cs)}개")
    print("─" * 78)
    ok = True
    for i, c in enumerate(cs, 1):
        truths = {t for _, _, t in c}
        base = {t.replace("_반증", "") for t in truths}
        pure = len(base) == 1
        ok &= pure
        promo = "→ 해석 생성" if len(c) >= MIN_EVIDENCE else f"→ 보류 ({len(c)}/{MIN_EVIDENCE})"
        mark = "✅" if pure else "❌ 섞임"
        print(f"  클러스터 {i} [{', '.join(s for s, _, _ in c)}] "
              f"{mark:<8}{promo}")
        for _, t, truth in c:
            print(f"      · {t}  ({truth})")
    return ok, cs


def main():
    print("L8 해석 누적 — 관찰을 '같은 패턴'으로 묶을 수 있는가")
    print("=" * 78)
    print("정답 라벨: 회피 3건(S05·S13·S19) / 칭찬거부 2건(S08·S16) / 회피 반증 1건(S22)")
    print("→ 회피만 3회 모여 해석이 생성되고, 칭찬거부는 2회라 보류되어야 한다.")

    for th in (0.20, 0.30, 0.45):
        report(th)

    # ── 구조화 관찰로 다시 ────────────────────────────────────────
    print("\n" + "=" * 78)
    print("자유 서술 대신 (계기, 반응, 극성) 삼중항으로 저장하면")
    print("=" * 78)
    structured = [
        ("S05", "힘든_얘기", "화제전환", "부정"),
        ("S08", "칭찬",      "화제전환", "긍정"),
        ("S13", "힘든_얘기", "화제전환", "부정"),
        ("S16", "칭찬",      "화제전환", "긍정"),
        ("S19", "힘든_얘기", "화제전환", "부정"),
        ("S22", "힘든_얘기", "직면",     "부정"),   # ← 같은 계기, 다른 반응 = 반증
    ]
    groups = {}
    for sess, trig, resp, val in structured:
        groups.setdefault((trig, resp), []).append(sess)

    print(f"{'(계기, 반응)':<28}{'횟수':>6}  판정")
    print("─" * 78)
    for (trig, resp), sess in sorted(groups.items(), key=lambda x: -len(x[1])):
        # 같은 계기 + 다른 반응 = 반증
        counter = sum(len(v) for (t, r), v in groups.items()
                      if t == trig and r != resp)
        n = len(sess)
        if n >= MIN_EVIDENCE:
            conf = min(0.5 + 0.1 * (n - MIN_EVIDENCE), 0.9) - 0.15 * counter
            verdict = (f"→ 해석 생성  confidence {conf:.2f}"
                       + (f" (반증 {counter}건 반영)" if counter else ""))
        else:
            verdict = f"→ 보류 ({n}/{MIN_EVIDENCE})"
        print(f"{f'({trig}, {resp})':<28}{n:>6}  {verdict}   [{', '.join(sess)}]")
    print("─" * 78)
    print("  ✅ 계기가 다르면 반응이 같아도 안 뭉친다 — 회피와 칭찬거부가 갈린다")
    print("  ✅ 계기가 같고 반응이 다르면 **반증으로 셀 수 있다** — S22가 confidence를 깎는다")
    print("  → 자유 서술로는 불가능하던 것이 삼중항으로는 결정적으로 된다")

    print("\n" + "=" * 78)
    print("구현이 드러낸 것")
    print("=" * 78)
    print("① 🔴 표면 어휘로는 '같은 패턴'을 못 가른다")
    print("   회피와 칭찬거부가 **둘 다 '화제를 돌렸다'**로 끝난다.")
    print("   어휘 유사도를 낮추면 뭉치고, 높이면 같은 패턴끼리도 안 뭉친다.")
    print("   → 표면이 아니라 **맥락**이 패턴을 가른다: '무엇으로부터' 돌렸는가")
    print()
    print("② 🔴 관찰에 구조가 필요하다 — 자유 서술로는 안 된다")
    print("   docs/06 L8의 `content TEXT`만으로는 클러스터링이 불가능하다.")
    print("   → 관찰을 (계기, 반응, 맥락) 삼중항으로 저장해야 한다:")
    print("       (힘든 얘기,  화제 전환, 부정 감정)  → 회피")
    print("       (칭찬,       화제 전환, 긍정 감정)  → 칭찬거부")
    print("     같은 '화제 전환'이지만 계기가 다르다")
    print()
    print("③ 🔴 반증 관찰을 어떻게 셀지 정하지 않았다")
    print("   S22는 회피의 **반례**다. 어휘상 회피 클러스터에 붙지만 의미는 반대다.")
    print("   → confidence를 깎아야 하는데, docs/06 L8에 그 규칙이 없다.")
    print("     그리고 어휘 유사도로는 **반례인지 사례인지 구별 자체가 불가능**하다")
    print()
    print("→ 결론: **해석 누적은 LLM 없이 못 한다.** 이건 규칙으로 되는 일이 아니었다.")
    print("   docs/06 L8이 'Reflection이 만든다'고만 쓰고 넘어간 게 우연이 아니다.")
    print("   다만 **무엇을 LLM에게 시킬지**는 이제 명확하다 — 자유 서술이 아니라")
    print("   (계기, 반응, 맥락, 극성) 구조로 뽑게 해야 클러스터링이 가능하다.")


if __name__ == "__main__":
    main()
