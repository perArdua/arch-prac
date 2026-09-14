"""
프로토타입 데모 — 실제로 컨텍스트가 어떻게 조립되는지 보인다.

핵심은 **provenance 출력**이다. 무엇이 왜 들어갔고, 무엇이 왜 걸러졌는지.
docs/05 §5에서 "provenance를 1급 요구사항으로"라고 한 것의 구현.

실행: python prototype/demos/demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from memory import Memory, ntok, WINDOW_CHUNK  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CHAT = "eval-chat-001"


def seed(m: Memory):
    db = m.db
    db.execute("INSERT INTO character_version VALUES (?,?,?,?,?)", (
        "seojun", 1,
        "강서준 27. 대학 2년 선배. 무뚝뚝하고 툴툴대지만 챙기는 건 다 챙긴다. "
        "걱정을 직접 말하지 않고 다른 방식으로 표현한다.",
        "반말 / 1인칭 '나' / 어미 ~냐 ~다 ~지 ~거든 / 존댓말·이모지 금지",
        "유저의 가족사를 먼저 캐묻지 않는다"))
    db.execute("INSERT INTO chat VALUES (?,?,?,?)", (CHAT, "jiwoo", "seojun", 1))
    db.execute("INSERT INTO relationship VALUES (?,?,?,?,?,?,?,?)",
               (CHAT, "연인", "화해 직후", 84, "안도", "지우", 0, 690))
    db.execute("INSERT INTO scene VALUES (?,?,?,?,?)",
               (CHAT, "카톡", "지우,서준", "평범한 저녁 대화", 690))
    db.execute("INSERT INTO digest VALUES (?,?,?,?,?)", (
        CHAT, "lifetime",
        "4월 대학 선후배로 다시 연락. 6월 썸, 7월 연인. "
        "7월 지우 반려묘 나비가 응급실. 8월 이직 문제로 다퉜다 화해. "
        "지우는 스타트업으로 이직해 한 달째.", 690, None))
    db.execute("INSERT INTO digest VALUES (?,?,?,?,?)", (
        CHAT, "session", "오늘은 새 회사 적응 얘기로 시작했다.", 700, None))

    events = [
        ("나비가 갑자기 아파서 응급실에 감", 0.95, 0.9, "갈등", 570),
        ("이직 문제로 크게 다툼", 0.9, 0.85, "갈등", 600),
        ("최종 합격", 0.9, 0.9, "해소", 630),
        ("서준이 집 앞까지 데려다줌 (처음)", 0.9, 0.85, "전환점", 330),
        ("지우가 점심에 크로와상 먹고 아쉽다고 함", 0.05, 0.05, "일상", 210),
        ("봄나들이에서 나비(곤충)를 봄", 0.1, 0.1, "일상", 170),
    ]
    for s, ew, imp, role, seq in events:
        db.execute("INSERT INTO event (chat_id, summary, emotional_weight,"
                   " importance, narrative_role, source_from_seq)"
                   " VALUES (?,?,?,?,?,?)", (CHAT, s, ew, imp, role, seq))

    db.execute("INSERT INTO debt (chat_id, content, setup_turn_seq, trigger_kind,"
               " trigger_clock, emotional_stake) VALUES (?,?,?,?,?,?)",
               (CHAT, "서준이 자기 얘기를 해주기로 함", 170, "session_start",
                "session", 0.6))

    for a, b, res in ((1, 300, "digest"), (301, 600, "event"), (601, 720, "raw")):
        db.execute("INSERT INTO coverage VALUES (?,?,?,?)", (CHAT, a, b, res))

    for i in range(680, 700):
        m.add_turn(CHAT, i, "user" if i % 2 else "character", f"(이전 대화 {i})")
    db.commit()


def show(m: Memory, seq, utterance, session_start=False):
    ctx = m.build_context(CHAT, utterance, seq, session_start)
    print(f"\n{'━' * 76}")
    print(f"턴 {seq}  |  \"{utterance}\"" + ("   [세션 시작]" if session_start else ""))
    print("━" * 76)
    print(f"{'블록':<18}{'토큰':>7}{'공유범위':>12}{'변동성':>8}")
    print("─" * 76)
    for b in ctx.blocks:
        print(f"{b.name:<18}{b.tokens:>7}{b.scope:>12}{b.volatility:>8}")
    print("─" * 76)
    print(f"{'합계':<18}{ctx.tokens:>7}")
    print("\nprovenance — 무엇이 왜")
    for kind, item, reason in ctx.provenance:
        mark = {"gate": "🚪", "retrieved": "✅", "rejected": "🚫",
                "relationship": "📌", "debt": "📌"}.get(kind, "  ")
        it = item if len(item) <= 34 else item[:33] + "…"
        print(f"  {mark} {kind:<14}{it:<36}{reason}")
    return ctx


def main():
    m = Memory()
    seed(m)
    print("프로토타입 — docs/10 추천 구조 구현 (SQLite + 룰 기반, 표준 라이브러리만)")

    contexts = []
    contexts.append(show(m, 701, "오늘 어땠어", session_start=True))
    contexts.append(show(m, 702, "응"))
    contexts.append(show(m, 703, "나비 아팠던 거 기억나?"))
    contexts.append(show(m, 704, "마지막이라 아쉽다"))

    # ── 캐시 접두사 안정성 ────────────────────────────────────────
    print(f"\n{'━' * 76}")
    print("캐시 접두사 안정성 (docs/adr/ADR-007)")
    print("━" * 76)
    prev = None
    for i, c in enumerate(contexts):
        names = [b.name for b in c.blocks]
        stable = 0
        if prev:
            for a, b in zip(names, prev):
                if a != b:
                    break
                stable += 1
        toks = sum(b.tokens for b in c.blocks[:stable])
        print(f"  턴 {701+i}: 공통 접두사 {stable}블록 / {toks}토큰 "
              f"({toks/max(c.tokens,1)*100:.0f}%)")
        prev = names

    print(f"\n{'━' * 76}")
    print("이 데모가 보여주는 것")
    print("━" * 76)
    print("  · 관계 상태·부채는 **검색 없이** 들어간다 (📌)")
    print("  · 게이트가 짧거나 과거 참조 신호 없는 발화에서 검색을 **차단**한다 (🚪)")
    print("  · importance 0.05인 크로와상은 검색이 돌아도 하드 게이트에서 **탈락**한다 (🚫)")
    print("  · 블록이 변동성 오름차순으로 정렬되어 접두사가 안정된다")
    print()
    print("⚠️ 구현하면서 드러난 것 (docs/13 참조)")
    print("  1. 어미 정규화 없이는 '아팠던' vs '아파서'가 안 맞아 **정답이 탈락**했다")
    print("  2. 부채 블록이 나타났다 사라지면 **접두사가 깨진다** → 뒤쪽으로 옮김")
    print("  3. '마지막이라 아쉽다'에서 빵이 안 나온 건 하드 게이트가 아니라")
    print("     **게이트가 검색 자체를 막았기 때문**이다 — 두 방어선의 공을 구별해야 한다")


if __name__ == "__main__":
    main()
