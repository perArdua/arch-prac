# -*- coding: utf-8 -*-
"""
deletion_demo.py — 기억 하나를 지우면 어디까지 사라지는가. (API 불필요)

[16 §4](../docs/16-design-elements.md)에서 지적한 구멍을 구현하고 확인한다.

    유저가 사실을 지운다  →  user_deleted = 1  →  **끝인가?**

    fact(직업=마케팅 대리)  삭제됨
       ├─ lifetime digest   "마케팅 회사에서 스타트업으로"   ← 남아 있다
       ├─ interpretation    "일 얘기에 위축된다"            ← 근거가 사라졌다
       └─ event             "회사에서 크게 깨짐"            ← 남아 있다

원본을 지워도 파생물에 남는다. **개인정보 삭제를 이걸로 만족했다고 말할 수 없다.**
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from memory import Memory   # noqa: E402

CHAT = "chat-del"
W = 78


def seed(m):
    db = m.db
    db.execute("INSERT INTO character_version VALUES (?,?,?,?,?)",
               ("seojun", 1, "강서준 27.", "반말", ""))
    db.execute("INSERT INTO chat VALUES (?,?,?,?)", (CHAT, "jiwoo", "seojun", 1))
    db.execute("INSERT INTO relationship VALUES (?,?,?,?,?,?,?,?)",
               (CHAT, "연인", None, 84, "안도", "지우", 0, 0))
    db.execute("INSERT INTO scene VALUES (?,?,?,?,?)",
               (CHAT, "카톡", "지우,서준", "저녁", 0))
    db.execute("INSERT INTO digest VALUES (?,?,?,?,?)", (
        CHAT, "lifetime",
        "4월 재연락, 7월 연인. 지우는 마케팅 회사 대리였다가 스타트업으로 이직했다.",
        100, None))
    db.commit()

    act, _ = m.upsert_fact(CHAT, "지우", "직업", "마케팅 회사 대리",
                           seq=5, importance=0.7)
    fid = m.db.execute("SELECT fact_id FROM fact WHERE object=?",
                       ("마케팅 회사 대리",)).fetchone()["fact_id"]
    m.db.execute(
        "INSERT INTO event (chat_id, summary, occurred_at, emotional_weight,"
        " importance, narrative_role, source_from_seq) VALUES (?,?,?,?,?,?,?)",
        (CHAT, "지우가 회사에서 크게 깨지고 새벽에 연락함", 20, 0.8, 0.8, "갈등", 20))
    m.db.commit()

    # ⭐ 파생 관계를 기록한다 — 요약이 이 사실에서 나왔다
    m.record_derivation(CHAT, "digest", "lifetime", [("fact", fid)])
    return fid


def show(m, label):
    ctx = m.build_context(CHAT, "오늘 어땠어", 120)
    names = [b.name for b in ctx.blocks]
    has_digest = any(n.startswith("digest") for n in names)
    known = next((b.text for b in ctx.blocks if b.name == "알고 있는 것"), "(없음)")
    dig = next((b.text for b in ctx.blocks if b.name.startswith("digest")), "(주입 안 됨)")
    print(f"\n  ── {label}")
    print(f"     [알고 있는 것]  {known.strip() or '(비어 있음)'}")
    print(f"     [장기 요약]     {dig[:62]}")
    stale = [p for p in ctx.provenance if p[0] == "stale"]
    for _, item, why in stale:
        print(f"     ⚠️ {item} — {why}")
    return has_digest


def main():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".del.db")
    if os.path.exists(p):
        os.remove(p)
    m = Memory(p)
    fid = seed(m)

    print("=" * W)
    print("삭제 전파 — 사실 하나를 지우면 어디까지 사라지는가")
    print("=" * W)

    before = show(m, "삭제 전")

    print("\n  >> 유저가 '직업=마케팅 회사 대리'를 지운다")
    hit = m.delete_item(CHAT, "fact", fid)
    print(f"     함께 무효화된 파생물: {hit}")

    after = show(m, "삭제 후")

    print("\n" + "-" * W)
    print("무엇이 달라졌나")
    print("-" * W)
    print("  · 사실은 [알고 있는 것]에서 즉시 빠진다 (user_deleted 필터)")
    if before and not after:
        print("  · 🟢 **그 사실로 만든 요약도 주입에서 빠진다** — 이게 이번에 추가한 것이다")
        print("       전에는 요약에 '마케팅 회사 대리였다가'가 그대로 남아 주입됐다")
    else:
        print("  · 🔴 요약이 여전히 주입된다 — 전파가 안 됐다")

    print("\n" + "-" * W)
    print("설계 판단 — 왜 '재생성'이 아니라 '주입 제외'인가")
    print("-" * W)
    print("  파생물을 즉시 다시 쓰려면 LLM이 필요하고, 그건 배치 경로다(수분~24h).")
    print("  그 사이에 계속 주입하면 **지운 정보가 계속 노출된다.**")
    print("  → stale로 표시하고 **재생성 전까지는 뺀다.** 안전한 기본값은 '빼는 것'이다.")
    print("\n  대가: 그동안 장기 맥락이 없어져 품질이 떨어진다.")
    print("        [실험 13](../docs/11-experiment-results.md)에서 요약이 6문항의 답을 담고 있었으니")
    print("        작지 않은 손실이다. **삭제는 공짜가 아니다.**")

    print("\n" + "-" * W)
    print("⚠️ 아직 안 된 것")
    print("-" * W)
    print("  · **재생성 잡이 없다.** stale로 표시만 하고 다시 쓰지 않는다")
    print("  · 파생 관계를 **요약 생성 시 기록해야** 하는데, 지금은 데모에서 수동으로 넣었다.")
    print("    실제로는 요약기가 자기 입력을 record_derivation으로 남겨야 한다")
    print("  · **L0 원본은 그대로 남는다.** 법적 삭제 요구는 별도 경로가 필요하다")
    print("  · interpretation 전파는 미구현 (evidence 필드는 있다)")
    print("\n" + "=" * W)
    m.db.close()
    os.remove(p)


if __name__ == "__main__":
    main()
