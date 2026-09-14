# -*- coding: utf-8 -*-
"""
consistency_audit.py — 문서 44편에 흩어진 숫자가 서로 어긋나지 않는가. (API 불필요)

## 왜

실험을 18개 돌렸고 그때마다 문서를 고쳤다. 같은 숫자가 **여러 문서에 인용**된다.
[실험 13](../docs/11-experiment-results.md)의 회상률은 한 번 54%였다가 73%가 됐고,
[실험 12](../docs/11-experiment-results.md)의 θ는 0.15였다가 0.05가 됐다.

**한 곳을 고치고 다른 곳을 안 고치면 문서가 서로 다른 말을 한다.**
링크 검사는 하고 있지만 **숫자 검사는 안 하고 있었다.**

## 방법

핵심 수치를 **정규식으로 전수 수집**하고, 같은 주장에 대해 **서로 다른 값**이 있으면 보고한다.
자동으로 고치지는 않는다 — 맥락에 따라 옛 값을 일부러 남긴 곳이 있다(🔄 정정 표시).
**사람이 봐야 할 곳을 좁혀주는 것**이 목적이다.
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
W = 78

# (주장 이름, 정규식, 기대값 또는 None)
# 기대값을 적어두면 **그것과 다른 것만** 보고한다.
# 🔴 첫 판은 정규식이 헐거워 **무관한 숫자를 잔뜩 잡았다.**
#    "Oracle 회상률"이 "100%"를, "L3"가 04문서의 인용구를 잡는 식이었다.
#    -> 주장은 **문맥까지 포함한 정확한 문자열**로만 찾는다.
#       느슨하게 많이 잡느니 **좁게 확실한 것만** 본다.
CLAIMS = [
    ("제안안 응답 품질", r"19/26", None),
    ("Oracle 응답 품질", r"17/26", None),
    ("L3 활용 실패", r"L3 활용 실패[^\n]{0,14}?(\d{1,2})%|L3\((\d{2})%\)", "35"),
    ("콜드스타트 환각 상한", r"83%", None),
    ("θ 임계 (현행)", r"θ\s*=\s*0\.05", None),
    ("주입 공격 성공", r"0/45", None),
    ("stale 누수 수정", r"23(?:턴)?\s*(?:→|->)\s*0", None),
]

# 세는 것 — 늘면 여러 곳을 같이 고쳐야 한다. **여기가 실제로 어긋난다.**
COUNTS = [
    ("실험 개수", r"실험\s*(\d+)개"),
    ("ADR 편수", r"(?:ADR|결정 기록)\s*(\d+)편"),
]


# 시간순 기록물은 **옛 값이 남아 있는 게 정상**이다.
#   PROGRESS.md   그때의 상태를 적은 로그다. "실험 10개"는 그 시점에 참이었다
#   docs/00·01    초기 계획서다. "ADR 6편 작성"은 계획이지 현황이 아니다
# 이걸 안 빼면 감사가 **정상인 것을 계속 빨갛게** 만들고, 그러면 아무도 안 본다.
TIMELINE = {"PROGRESS.md", "docs/00-research-briefing.md",
            "docs/01-problem-and-hypotheses.md"}


def main():
    root = Path(".")
    mds = [m for m in sorted(root.rglob("*.md"))
           if m.as_posix().lstrip("./") not in TIMELINE]
    print("=" * W)
    print("문서 정합성 감사 — 같은 주장에 다른 숫자가 있는가")
    print("=" * W)
    print(f"\n대상 {len(mds)}편. 링크는 따로 검사한다 — 여기서는 **숫자**만 본다.\n")

    issues = 0
    for name, pat, expect in CLAIMS:
        found = defaultdict(list)
        for md in mds:
            for m in re.finditer(pat, md.read_text(encoding="utf-8")):
                v = next((g for g in m.groups() if g), m.group(0))
                found[v].append(md.as_posix())
        if not found:
            print(f"  ⚠️ {name:<28} 어디에도 없음 — 정규식을 확인할 것")
            continue
        vals = sorted(found, key=lambda v: -len(found[v]))
        if expect and any(v != expect for v in vals if v.isdigit()):
            odd = {v: f for v, f in found.items() if v != expect}
            print(f"  🔴 {name:<28} 기대 {expect} · 다른 값 발견")
            for v, files in odd.items():
                shown = ", ".join(sorted(set(files))[:3])
                print(f"       {v:<8} {shown}")
            issues += 1
        else:
            n = sum(len(f) for f in found.values())
            print(f"  ✅ {name:<28} {vals[0]:<8} ({n}곳, 일치)")

    print("\n" + "-" * W)
    print("세는 값 — 늘어나면 여러 곳을 같이 고쳐야 한다")
    print("-" * W)
    for name, pat in COUNTS:
        found = defaultdict(set)
        for md in mds:
            for m in re.finditer(pat, md.read_text(encoding="utf-8")):
                v = next((g for g in m.groups() if g), None)
                if v:
                    found[v].add(md.as_posix())
        if len(found) > 1:
            print(f"  🔴 {name}: 서로 다른 값이 있다")
            for v in sorted(found, key=int, reverse=True):
                print(f"       {v:<4} {', '.join(sorted(found[v])[:3])}")
            issues += 1
        elif found:
            v = list(found)[0]
            print(f"  ✅ {name}: {v} (일치)")

    print("\n" + "-" * W)
    if issues:
        print(f"🔴 {issues}건을 사람이 확인해야 한다.")
        print("   ⚠️ 전부 오류는 아니다 — 🔄 정정 블록에서 **옛 값을 일부러 남긴** 곳이 있다.")
        print("      이 도구는 **볼 곳을 좁혀줄 뿐** 판단하지 않는다.")
    else:
        print("✅ 검사한 범위에서 숫자 불일치 없음.")
    print("-" * W)
    print("\n⚠️ 이 감사가 못 잡는 것")
    print("  · 정규식에 없는 주장. **목록을 손으로 유지해야 한다**")
    print("  · 숫자가 아닌 주장의 모순 (예: '검색이 기여한다' vs '기여 0')")
    print("  · 맥락이 달라 같은 숫자가 다른 뜻인 경우")
    print("=" * W)
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
