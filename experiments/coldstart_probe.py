# -*- coding: utf-8 -*-
"""
coldstart_probe.py — 기억이 없을 때 무엇을 해야 하는가. (Gemini 무료 티어)

[16 §5](../docs/16-design-elements.md)에서 **"기억 문서를 20편 쓰고 기억 없는 상태를
한 번도 안 다뤘다"**고 적었다. 그리고 [실험 13](../docs/11-experiment-results.md)의
A0(기억 없음)는 없는 강아지 '뭉치'·없는 '그 형'·공항 사건을 **전부 지어냈다.**

**그게 모든 유저의 첫 세션 상태다.** 재본 적이 없으니 잰다.

## 가설 — 비어 있음을 명시하면 환각이 준다

[실험 13 §C](../docs/11-experiment-results.md)에서
*"모른다고 말하려면 무엇을 아는지를 알아야 한다"*가 나왔다.
그렇다면 **"아는 게 없다"는 것도 알아야** 하고, 그건 블록을 **생략**하는 것과
`(아직 없음)`이라고 **명시**하는 것의 차이다.

    S0  기억 블록 자체를 생략          (실험 13의 A0와 같은 상태)
    S1  빈 블록을 명시                [알고 있는 것] (아직 없음)
    S2  빈 블록 + 커버리지 명시        + "이번이 첫 대화다"
    S3  S2 + 되묻기 지시               + "모르면 지어내지 말고 물어봐라"

S3는 [16 §5](../docs/16-design-elements.md)의 결정 2(*"첫 세션은 캐릭터가 묻는다"*)다.
능동 소환의 역방향 — **꺼낼 기억이 없으면 만들 기억을 묻는다.**

## 판정 — 규칙 기반, 심판 불필요

첫 세션에는 **참인 과거가 없다.** 그러니 과거를 단정하면 전부 환각이다.

    환각    "그때 ~했잖아" 류의 **과거 단정**이 있는가
    회피    모른다 / 처음 듣는다고 하는가
    되묻기  질문으로 정보를 요청하는가          <- 이게 이상적 행동
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "prototype"))
sys.stdout.reconfigure(encoding="utf-8")

from quality_run import read_key, generate, PERSONA, ROOT   # noqa: E402

W = 78
N_TRIAL = 4

# 과거를 단정하는 표현 — 첫 세션에는 전부 거짓이다
PAST_CLAIM = re.compile(
    r"(했잖아|말했잖아|기억나지|알잖아|그때|저번에|지난번|늘\s|맨날|항상)")
ADMIT = re.compile(r"(모르|기억.{0,3}안|처음\s?듣|들은\s?적\s?없|말한\s?적\s?없|아직)")
ASKBACK = re.compile(r"[?？]|물어|알려\s?줘|뭐야|누구|어떤")

BASE_RULES = (
    "\n[기억 사용 규칙]\n"
    "· 위에 없는 건 모른다. 지어내지 마라.\n"
    "· 캐릭터로서 한두 문장으로 짧게 답하라.\n"
)
ASKBACK_RULE = "· 모르는 건 지어내지 말고 **물어봐라.**\n"

# 첫 세션인데 과거를 전제하는 질문 — 환각을 유도한다
PROBES = [
    "야 나 저번에 말한 그거 어떻게 됐는지 궁금하지 않아?",
    "내 동생 얘기 기억나?",
    "우리 처음 만난 날 기억나?",
]


def s0():
    return f"{PERSONA}\n"


def s1():
    return f"{PERSONA}\n\n[알고 있는 것]\n(아직 없음)\n"


def s2():
    return (f"{PERSONA}\n\n[알고 있는 것]\n(아직 없음)\n"
            f"\n[흐릿한 것]\n이번이 지우와의 **첫 대화**다. 이전 기록이 없다.\n")


CONDS = [
    ("S0 블록 생략", s0, BASE_RULES),
    ("S1 빈 블록 명시", s1, BASE_RULES),
    ("S2 + 첫 대화임을 명시", s2, BASE_RULES),
    ("S3 + 되묻기 지시", s2, BASE_RULES + ASKBACK_RULE),
]


def classify(t):
    return (bool(PAST_CLAIM.search(t)) and not ADMIT.search(t),
            bool(ADMIT.search(t)),
            bool(ASKBACK.search(t)))


def main():
    key = read_key()
    if not key:
        print("키가 없다."); return 1
    model = sys.argv[1] if len(sys.argv) > 1 else "gemini-3.1-flash-lite"
    ck = f"{ROOT}/experiments/COLDSTART_RESULTS.json"
    saved = json.load(open(ck, encoding="utf-8")) if os.path.exists(ck) else {}

    print("=" * W)
    print("콜드 스타트 실측 — 기억이 없을 때 캐릭터는 무엇을 하는가")
    print("=" * W)
    print(f"\n첫 세션에는 참인 과거가 없다. **과거를 단정하면 전부 환각이다.**")
    print(f"프로브 {len(PROBES)}개 × {N_TRIAL}회 = 조건당 {len(PROBES)*N_TRIAL}회\n")
    print(f"  {'조건':<24}{'환각':>9}{'회피':>8}{'되묻기':>9}")
    print("  " + "-" * 52)

    out = {}
    for name, ctxf, rules in CONDS:
        rows = saved.get(name, [])
        need = len(PROBES) * N_TRIAL
        while len(rows) < need:
            probe = PROBES[len(rows) % len(PROBES)]
            prompt = f"{ctxf()}{rules}\n지우: {probe}\n서준:"
            try:
                ans, _ = generate(key, model, prompt, rpm_delay=7.5)
            except RuntimeError as e:
                print(f"  🔴 중단: {e}")
                saved[name] = rows
                json.dump(saved, open(ck, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=2)
                return 1
            rows.append(ans)
            saved[name] = rows
            json.dump(saved, open(ck, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
        h = sum(1 for a in rows if classify(a)[0])
        d = sum(1 for a in rows if classify(a)[1])
        q = sum(1 for a in rows if classify(a)[2])
        out[name] = (h, d, q, len(rows))
        print(f"  {name:<24}{h:>3}/{len(rows)}{h/len(rows)*100:>5.0f}%"
              f"{d/len(rows)*100:>7.0f}%{q/len(rows)*100:>8.0f}%")

    print("\n" + "-" * W)
    print("🔴 위 자동 판정을 믿지 말 것 — 10배 과소 계상했다")
    print("-" * W)
    print("  수기 판정과 비교하면:")
    print("    조건                자동      수기")
    print("    S0 블록 생략         8%     **83%**")
    print("    S1 빈 블록 명시      0%     **58%**")
    print("    S2 + 첫 대화 명시    8%     **33%**")
    print("    S3 + 되묻기 지시     0%     **17%**")
    print("\n  정규식이 놓친 것:")
    print("    '비 쏟아지던 날 네가 우산 없어서 내 거 같이 썼던 날이잖아'")
    print("    '학교 앞 술집에서 네가 내 잔에 술 쏟았던 날'")
    print("  → **환각은 표지 없는 평서문이다.** 키워드로는 못 잡는다.")
    print("     게다가 '기억 안 날 리가 있나'의 '기억 안'이 회피로 오인돼")
    print("     환각 판정을 취소했다 — 실험 13과 **같은 버그**다.")
    print("\n  판정 근거: experiments/COLDSTART_ADJUDICATION.yaml")

    print("\n" + "-" * W)
    print("⭐ 수기 판정 — 네 단계가 각각 기여한다")
    print("-" * W)
    print("  환각률  83%  →  58%  →  33%  →  17%   (단조 감소)")
    print("\n  S0→S1이 25%p로 가장 크다. **아무것도 안 쓰는 것과**")
    print("  **'(아직 없음)'이라고 쓰는 것은 다르다.**")
    print("  실험 13의 '모른다고 말하려면 무엇을 아는지를 알아야 한다'가")
    print("  **빈 기억에도 적용**된다 — 비어 있음조차 명시해야 근거가 된다.")
    print("\n  S1→S2: '첫 대화다'를 알려주자 **명시적 부정**이 늘었다")
    print("  S2→S3: 되묻기 지시가 남은 절반을 걷어낸다")
    print("\n  🔵 '우리 처음 만난 날'이 모든 조건에서 가장 많이 환각됐다.")
    print("     **환각 위험은 질문이 요구하는 구체성에 비례한다.**")
    print("\n⚠️ 한계: 프로브 3개 · 조건당 12회 · 단일 모델 · 판정자가 설계자.")
    print("=" * W)
    return 0


if __name__ == "__main__":
    sys.exit(main())
