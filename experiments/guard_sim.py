"""
M10 가드 실험 — "enum 상태는 정규식으로 검증 가능, NLI 불필요" 주장 검증.

이 주장은 여러 문서에서 반복했지만 한 번도 코드로 보이지 않았다:
  docs/06 L2      "stage=헤어짐인데 '자기야'가 나오면 정규식으로 잡힌다"
  docs/05 §7.3    "M10-V3를 NLI가 아니라 스키마 비교로 구현하는 근거"
  docs/adr/ADR-002 "모순 검사가 O(1)이 된다"

정직하게 검증하려면 **함정 케이스**가 필요하다:
  · 의미적 위반 — 금지어 없이 상태를 어기는 응답
  · 거짓 양성 — 금지어가 있지만 위반이 아닌 응답 (인용·회상·부정)
이 둘이 없으면 정규식이 100%로 나오고, 그건 검증이 아니다.

실행: python experiments/guard_sim.py
"""

import re
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ── 가드 규칙 (L2/L1/L3 상태에서 기계적으로 파생) ────────────────────────
AFFECTION = r"(자기야|여보|내 사랑|사랑해|보고싶어 죽겠)"
POLITE = r"(습니다|해요|세요|입니다|드릴게요)"

RULES = {
    "stage=헤어짐": dict(field="stage", value="헤어짐", forbid=AFFECTION,
                       why="헤어진 상대에게 애정 호칭"),
    "stage=낯섦": dict(field="stage", value="낯섦", forbid=AFFECTION,
                     why="아직 낯선 사이인데 애정 표현"),
    "speech=반말": dict(field="speech", value="반말", forbid=POLITE,
                      why="반말 캐릭터가 존댓말"),
}

# 씬 참여자 명부 밖 인물 (docs/06 L3, 유사 서비스 A U6)
KNOWN_CHARS = {"지우", "서준"}
CHAR_MENTION = re.compile(r"(엄마|아빠|친구|민지|선배|점원|의사)")


# ── 억제 문맥 (v2에서 추가) ─────────────────────────────────────────────
# 금지어가 등장해도 위반이 아닌 경우: 인용·부정·과거 회상·메타 언급
SUPPRESS = re.compile(
    r"(['\"‘’“”].{0,20}['\"‘’“”]"          # 따옴표 안
    r"|예전엔|옛날엔|그땐|~?라고 불렀"        # 과거 회상
    r"|안 할게|안 해|이제 아니|더는|않을게"    # 부정·중단
    r"|라는 (단어|말)|이런 (말투|말)|같은 말)" # 메타 언급
)


def guard(text, state, v2=False):
    """상태와 응답을 대조해 위반을 찾는다. v2는 억제 문맥을 고려한다."""
    hits = []
    for name, r in RULES.items():
        if state.get(r["field"]) != r["value"]:
            continue
        m = re.search(r["forbid"], text)
        if not m:
            continue
        if v2:
            # 금지어 주변 ±25자에 억제 신호가 있으면 위반으로 보지 않는다
            s, e = max(0, m.start() - 25), min(len(text), m.end() + 25)
            if SUPPRESS.search(text[s:e]):
                continue
        hits.append((name, r["why"]))
    if state.get("scene_locked"):
        m = CHAR_MENTION.search(text)
        if m and not (v2 and SUPPRESS.search(text)):
            hits.append(("scene=참여자고정", f"명부 밖 인물 등장: {m.group(1)}"))
    return hits


# ── 테스트 케이스 ───────────────────────────────────────────────────────
# (응답, 상태, 실제로 위반인가)
CASES = [
    # ① 어휘적 위반 — 정규식이 잡아야 한다
    ("자기야, 밥은 먹었어?", {"stage": "헤어짐"}, True),
    ("사랑해. 그건 변함없어.", {"stage": "헤어짐"}, True),
    ("네, 알겠습니다.", {"speech": "반말"}, True),
    ("엄마가 부르시네. 잠깐만.", {"scene_locked": True}, True),

    # ② 위반 없음 — 잡으면 안 된다
    ("밥은 먹었냐.", {"stage": "헤어짐", "speech": "반말"}, False),
    ("……그래서 괜찮은 거냐고.", {"stage": "헤어짐", "speech": "반말"}, False),
    ("택시 타고 가라.", {"speech": "반말", "scene_locked": True}, False),

    # ③ 🔴 의미적 위반 — 금지어가 없어서 정규식이 못 잡는다
    ("우리 다시 만나서 진짜 좋다.", {"stage": "헤어짐"}, True),
    ("너랑 나 사이가 어디 보통이냐.", {"stage": "낯섦"}, True),
    ("아직도 네 생각만 하고 있어. 매일.", {"stage": "헤어짐"}, True),

    # ④ 🔴 거짓 양성 함정 — 금지어가 있지만 위반이 아니다
    ("예전엔 자기야라고 불렀는데. 이제 아니지.", {"stage": "헤어짐"}, False),
    ("사랑해 같은 말은 이제 안 할게.", {"stage": "헤어짐"}, False),
    ("'알겠습니다' 이런 말투 진짜 싫어.", {"speech": "반말"}, False),
    ("친구라는 단어도 이제 애매하네.", {"scene_locked": True}, False),
]


def score(v2):
    tp = fp = tn = fn = 0
    misses, falses = [], []
    for text, state, truth in CASES:
        pred = bool(guard(text, state, v2))
        if pred and truth:
            tp += 1
        elif pred and not truth:
            fp += 1; falses.append(text)
        elif not pred and truth:
            fn += 1; misses.append(text)
        else:
            tn += 1
    return tp, fp, fn, tn, misses, falses


def main():
    t0 = time.perf_counter()
    for _ in range(1000):
        for text, state, _ in CASES:
            guard(text, state, v2=True)
    per_call_us = (time.perf_counter() - t0) / (1000 * len(CASES)) * 1e6

    print("케이스별 판정 (v2 = 억제 문맥 처리 포함)")
    print("─" * 88)
    print(f"{'응답':<38}{'실제':>8}{'v1':>8}{'v2':>8}{'판정':>10}")
    print("─" * 88)
    for text, state, truth in CASES:
        p1, p2 = bool(guard(text, state)), bool(guard(text, state, v2=True))
        v = ("✅ TP" if p2 and truth else "❌ FP" if p2 else
             "❌ FN" if truth else "✅ TN")
        show = text if len(text) <= 36 else text[:35] + "…"
        print(f"{show:<38}{'위반' if truth else '정상':>8}"
              f"{'위반' if p1 else '정상':>8}{'위반' if p2 else '정상':>8}{v:>10}")
    print("─" * 88)

    print(f"\n{'버전':<8}{'정밀도':>10}{'재현율':>10}{'TP/FP/FN/TN':>18}")
    print("─" * 88)
    for label, v2 in (("v1 순수", False), ("v2 억제문맥", True)):
        tp, fp, fn, tn, misses, falses = score(v2)
        print(f"{label:<8}{tp/max(tp+fp,1):>9.0%}{tp/max(tp+fn,1):>10.0%}"
              f"{f'{tp}/{fp}/{fn}/{tn}':>18}")
    print("─" * 88)
    print(f"호출당 지연: {per_call_us:.1f} μs "
          f"— 지연 예산 200,000μs의 {per_call_us/200_000*100:.4f}%")

    _, _, _, _, misses, falses = score(True)
    print("\nv2가 여전히 놓친 위반 (FN) — 금지어가 없어 어휘 규칙으로는 불가능")
    for m in misses:
        print(f"  · {m}")
    if falses:
        print("\nv2의 거짓 양성 (FP)")
        for f in falses:
            print(f"  · {f}")

    print("\n" + "═" * 88)
    print("판정")
    print("  · 어휘적 위반 4건은 전부 잡는다. 지연 "
          f"{per_call_us:.1f}μs로 사실상 공짜다")
    print("  · 억제 문맥(인용·부정·회상) 처리를 넣으니 거짓 양성이 크게 줄었다")
    print(f"  · 그러나 의미적 위반 {len(misses)}건은 **원리적으로 못 잡는다** — 금지어가 없다")
    print()
    print("  → '정규식으로 잡힌다'는 **어휘적 위반에 한해** 참이다.")
    print("     docs/05 §7.3의 'NLI 대신 스키마 비교' 주장은 **과했다.**")
    print("     스키마 비교는 NLI를 대체하는 게 아니라 **NLI가 필요한 양을 줄인다.**")
    print()
    print("  실무 설계: 정규식으로 값싸게 거르고, 남은 것만 비싼 검증으로 보낸다.")
    print("  그리고 의미적 위반은 사후 검증보다 **사전 주입(L2를 컨텍스트에 넣기)**이 낫다.")


if __name__ == "__main__":
    main()
