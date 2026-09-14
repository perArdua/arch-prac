# -*- coding: utf-8 -*-
"""
quality_variance.py — "2문항 차"가 실재하는 차이인지 표집 잡음인지 가른다. (API 호출 없음)

[실험 13](../docs/11-experiment-results.md)에서 제안안 73% vs G1 65%가 나왔다.
26문항에서 2문항 차다. **그런데 1회 실행이고 temperature 0.7이다.**
같은 입력에 같은 답이 안 나온다는 뜻이고, 그러면 2문항은 그냥 흔들림일 수 있다.

**그걸 모르면 어떤 arm 비교도 해석할 수 없다.** 그래서 같은 arm을 3번 돌렸다.

재는 것:
  1. arm별 3회 점수의 **범위(min~max)** — 이게 잡음 폭이다
  2. **문항별 뒤집힘** — 3회 중 정답/오답이 갈린 문항 수
  3. arm 간 차이가 잡음 폭보다 큰가 — **크지 않으면 우열을 말할 수 없다**

⚠️ 여기서는 **자동 채점만** 쓴다. 수기 판정은 반복분에 적용하지 않았다.
   절대 점수는 낮게 나오지만, **뒤집힘 비율은 채점기와 무관하게 유효**하다 —
   같은 채점기로 같은 arm을 재는 것이므로 편향이 상쇄된다.
"""
import json
import os
import re
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = 78


def main():
    with open(f"{ROOT}/experiments/QUALITY_RESULTS.json", encoding="utf-8") as f:
        res = json.load(f)

    # "<arm> #rN" 형태만 모은다
    runs = defaultdict(dict)          # base arm -> {run_idx: {qid: ok}}
    for key, rows in res.items():
        m = re.match(r"^(.*) #r(\d+)$", key)
        if not m:
            continue
        base, idx = m.group(1), int(m.group(2))
        runs[base][idx] = {r["id"]: (r["ok"] is True) for r in rows}

    if not runs:
        print("반복 실행 결과가 없다. 먼저 --repeat 로 돌릴 것:")
        print("  python experiments/quality_run.py --repeat 3 --only \"C  제안안,G1\"")
        return 1

    print("=" * W)
    print("반복 실행 분산 — \"2문항 차\"는 실재하는가")
    print("=" * W)

    stats = {}
    for base, by_run in sorted(runs.items()):
        idxs = sorted(by_run)
        qids = sorted(set().union(*(set(v) for v in by_run.values())))
        scores = [sum(by_run[i].get(q, False) for q in qids) for i in idxs]
        flips = [q for q in qids
                 if len({by_run[i].get(q, False) for i in idxs}) > 1]
        stats[base] = dict(scores=scores, n=len(qids), flips=flips)

    print(f"\n  {'arm':<26}{'3회 점수':>16}{'범위':>7}{'뒤집힌 문항':>12}")
    print("  " + "-" * 64)
    for base, st in stats.items():
        sc = st["scores"]
        print(f"  {base:<26}{str(sc):>16}{max(sc)-min(sc):>7}"
              f"{len(st['flips']):>8}/{st['n']}")

    # ── 해석 ────────────────────────────────────────────────────────
    print("\n" + "-" * W)
    print("해석")
    print("-" * W)

    spread = max(max(st["scores"]) - min(st["scores"]) for st in stats.values())
    print(f"  **한 arm 안에서 3회 점수가 최대 {spread}문항 흔들린다.**")

    if len(stats) >= 2:
        keys = list(stats)
        means = {k: sum(stats[k]["scores"]) / len(stats[k]["scores"]) for k in keys}
        hi, lo = max(means, key=means.get), min(means, key=means.get)
        gap = means[hi] - means[lo]
        print(f"  arm 간 평균 차이는 {gap:.1f}문항 ({hi} > {lo}).")
        print()
        if gap <= spread:
            print(f"  🔴 **arm 간 차이({gap:.1f})가 arm 내 흔들림({spread})보다 작거나 같다.**")
            print( "     즉 **한 번 더 돌리면 순위가 뒤집힐 수 있다.**")
            print( "     -> 실험 13의 '제안안 73% vs G1 65%'로 **우열을 주장하면 안 된다.**")
            print( "        방향성 참고까지가 이 데이터가 허용하는 최대치다.")
        else:
            print(f"  🟢 arm 간 차이({gap:.1f})가 arm 내 흔들림({spread})보다 크다.")
            print( "     순위가 표집 잡음만으로 뒤집히기는 어렵다. 다만 문항 수가 작다.")

    allflips = sorted(set().union(*(set(st["flips"]) for st in stats.values())))
    print(f"\n  3회 중 판정이 갈린 문항: {len(allflips)}개 — {', '.join(allflips)}")
    print( "  같은 프롬프트·같은 모델인데 답이 달라진 문항이다.")
    print( "  **이 문항들은 어떤 arm 비교에서도 신호가 아니라 잡음으로 봐야 한다.**")

    print("\n" + "-" * W)
    print("그래서 무엇을 해야 하나")
    print("-" * W)
    print("  ① **문항을 늘린다.** 26문항에서 2문항 차는 원리적으로 안 갈린다")
    print("  ② **temperature를 낮춘다.** 롤플레이 품질과 재현성이 상충하므로,")
    print("     평가용은 0, 서비스용은 0.7처럼 나눠야 한다")
    print("  ③ **반복 실행을 기본값으로 한다.** 1회 실행 숫자를 표에 넣으면")
    print("     읽는 사람이 그걸 확정값으로 받아들인다")

    print("\n" + "-" * W)
    print("⚠️ 이 분석의 한계")
    print("-" * W)
    print("  · **자동 채점만 썼다.** 수기 판정을 반복분에 적용하지 않아 절대 점수가 낮다.")
    print("    뒤집힘 비율은 유효하지만 점수 자체는 실험 13의 표와 비교하면 안 된다")
    print("  · 3회는 분산 추정에 적은 횟수다. 범위는 보되 표준편차로 읽지 말 것")
    print("\n" + "=" * W)
    return 0


if __name__ == "__main__":
    sys.exit(main())
