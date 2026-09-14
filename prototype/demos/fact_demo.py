"""
L5 사실 무효화 데모 — bi-temporal이 실제로 어떻게 도는가.

스키마에 superseded_by를 넣어놓고 탐지 로직은 없었다.
구현하려니 문서에 없던 결정 세 개가 필요했고, 그게 이 데모의 내용이다.

실행: python prototype/demos/fact_demo.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from memory import Memory  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CHAT = "c1"

# (턴, 주어, 술어, 값, 신뢰도, 설명)
STREAM = [
    (10,  "유저", "직업", "마케팅 회사 대리", 0.9, "S01 최초 진술"),
    (60,  "유저", "반려동물_이름", "나비", 0.9, "S03 고양이 소개"),
    (95,  "유저", "신체_특성", "카페인 민감", 0.9, "S04"),
    (240, "유저", "가족", "여동생 1명", 0.85, "S08"),
    (250, "유저", "직업", "마케팅 회사 대리", 0.9, "재언급 — 강화되어야"),
    (390, "친구", "지인_반려동물", "코코", 0.8, "다중값 술어"),
    (630, "유저", "직업", "스타트업 프로덕트 매니저", 0.95, "S21 이직 — 무효화되어야"),
    (700, "유저", "가족", "오빠 1명", 0.4, "🔴 U10 — 유저가 잘못 말함"),
    (705, "유저", "반려동물_이름", "코코", 0.5, "🔴 친구 고양이와 혼동"),
]


def main():
    m = Memory()
    m.db.execute("INSERT INTO chat VALUES (?,?,?,?)", (CHAT, "u", "c", 1))

    print("사실 스트림 처리")
    print("─" * 84)
    print(f"{'턴':<6}{'술어':<16}{'값':<22}{'동작':<12}{'설명'}")
    print("─" * 84)
    for seq, subj, pred, obj, conf, note in STREAM:
        action, why = m.upsert_fact(CHAT, subj, pred, obj, seq=seq, confidence=conf)
        mark = {"created": "  ", "reinforced": "🔁", "superseded": "🔄",
                "held": "🛑", "coexist": "➕"}[action]
        print(f"{seq:<6}{pred:<16}{obj[:20]:<22}{mark} {action:<9}{why}")
    print("─" * 84)

    print("\n현재 유효한 사실")
    print("─" * 84)
    for f in m.facts_at(CHAT):
        print(f"  {f['predicate']:<16}{f['object']:<24}"
              f"conf {f['confidence']:.2f}  mention {f['mention_count']}")

    print("\n무효화 이력 (superseded_by 체인)")
    print("─" * 84)
    rows = m.db.execute(
        "SELECT a.predicate, a.object AS old, b.object AS new"
        " FROM fact a JOIN fact b ON a.superseded_by=b.fact_id").fetchall()
    for r in rows:
        print(f"  {r['predicate']:<16}{r['old']}  →  {r['new']}")
    if not rows:
        print("  (없음)")

    print("\n보류된 것 (provenance)")
    print("─" * 84)
    for p in m.db.execute(
            "SELECT * FROM provenance WHERE kind='fact_held'").fetchall():
        print(f"  {p['item']:<28}{p['reason']}")

    print("\n" + "═" * 84)
    print("구현이 강제한 스키마 결정 네 개 — 전부 문서에 없었다")
    print("═" * 84)
    print("① 술어의 카디널리티 (one / many)")
    print("   '직업'은 하나, '가족'은 여럿. 없으면 무효화할지 병존할지 못 정한다")
    print()
    print("② 다중값 술어에도 confidence floor가 필요하다")
    print("   첫 구현은 many면 무조건 병존시켰다 → 없는 '오빠'가 그냥 들어갔다")
    print("   카디널리티 방어는 단일값만 지킨다")
    print()
    print("③ 덜 확신하는 진술이 더 확신하는 사실을 덮으면 안 된다")
    print("   첫 규칙('margin만큼 더 확신해야 덮는다')은 실행하자마자 깨졌다 —")
    print("   기존이 0.9면 1.05를 요구하는데 최대가 1.0이라 **정당한 갱신도 영원히 보류**된다")
    print()
    print("④ 🔴 술어의 **가변성**이 필요하다 — 가장 깊은 결정")
    print("   재확인이 confidence를 올리자 이번엔 이직 갱신이 막혔다. 강화가 사실을 화석화한다.")
    print("   근본 원인: '갱신'과 '모순'을 구별할 축이 없었다.")
    print("     이직 = 세상이 변한 것    → 허용해야 한다")
    print("     오빠 = 유저가 잘못 안 것  → 막아야 한다")
    print("   둘 다 '기존과 다른 값'이라 **confidence만으로는 구별 불가능**하다.")
    print("   → 직업은 자주 변하고 가족은 거의 안 변한다. 술어마다 가변성을 선언한다")
    print()
    print("   이게 U10에 대한 **데이터 계층의 방어선**이다. 프롬프트만으로는 부족하다.")


if __name__ == "__main__":
    main()
