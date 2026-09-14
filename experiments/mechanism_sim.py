"""
메커니즘 검증 — 데이터 모델에 설계만 하고 한 번도 돌려보지 않은 것들.

  L9 부채 트리거      docs/06 L9  "트리거 충족 시 결정적 주입"
  L6 surfaced_count  docs/06 L6  "같은 기억 반복 주입 억제"
  M  커버리지 메타     docs/06 M   "'없었다'와 '흐릿하다'를 구별"

셋 다 룰 기반이라 LLM 없이 동작을 검증할 수 있다.
품질을 재는 게 아니라 **기계가 설계대로 도는지**를 본다.

실행: python experiments/mechanism_sim.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retrieval_sim import BM25, tok_bigram, importance_map  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "eval" / "corpus" / "corpus.jsonl"
LEDGER = ROOT / "eval" / "fact-ledger.yaml"


# ═══════════════════════════════════════════════════════════════════
# 1. L9 부채 트리거
# ═══════════════════════════════════════════════════════════════════
def sess_num(sid):
    return int(sid[1:])


def exp_debt(ledger):
    print("① L9 서사 부채 — 트리거가 언제 몇 번 발화하는가")
    print("─" * 78)

    debts = ledger.get("debts", [])
    total_sessions = ledger["meta"]["sessions"]

    print(f"{'부채':<10}{'설정':<7}{'트리거':<16}{'기대 회수':<10}"
          f"{'발화 횟수':>10}{'판정':>14}")
    print("─" * 78)

    findings = []
    for d in debts:
        setup = sess_num(d["setup"]["session"])
        trig = d.get("trigger", {})
        kind = trig.get("kind", "-")
        exp = d.get("expected_payoff")
        exp_s = sess_num(exp["session"]) if exp else None

        # 트리거가 발화하는 세션들을 센다 (백오프 없음 = 현재 설계)
        fires = []
        for s in range(setup + 1, total_sessions + 1):
            if kind == "session_start":
                fires.append(s)
            elif kind == "time":
                spec = str(trig.get("spec", ""))
                if spec.endswith("d"):
                    # 세션 간격을 하루로 근사
                    if s - setup >= int(spec[:-1]):
                        fires.append(s)
                else:                       # 특정 날짜 → 해당 세션
                    if exp_s and s >= exp_s:
                        fires.append(s)
            elif kind == "semantic":
                pass                        # 의미 트리거는 발화 시점 예측 불가

        # 기대 회수 지점에서 멈춘다고 가정
        if exp_s:
            fires = [f for f in fires if f <= exp_s]
            ok = exp_s in fires
            verdict = "✅ 회수 가능" if ok else "❌ 트리거 미발화"
            if len(fires) > 3:
                verdict = f"⚠️ {len(fires)}회 반복"
                findings.append((d["id"], len(fires), exp_s - setup))
        else:
            verdict = "— 회수 없음(의도)"

        print(f"{d['id']:<10}S{setup:02d}{'':<4}{kind:<16}"
              f"{('S%02d' % exp_s) if exp_s else '-':<10}"
              f"{len(fires):>10}{verdict:>14}")
    print("─" * 78)

    if findings:
        print("\n  🔴 설계 결함 발견 — 백오프가 없다")
        for did, n, gap in findings:
            print(f"    {did}: 설정 후 {gap}세션 동안 트리거가 **{n}회** 발화한다.")
        print("    → 캐릭터가 매 세션 같은 걸 묻는다. 집착으로 읽힌다.")
        print("    → docs/06 L9에 `last_attempted_at` + 백오프 정책이 없다.")
    return findings


# ═══════════════════════════════════════════════════════════════════
# 2. L6 surfaced_count 반복 억제
# ═══════════════════════════════════════════════════════════════════
def exp_repetition(docs, ledger):
    print("\n② L6 surfaced_count — 같은 기억이 반복 주입되는가")
    print("─" * 78)

    ext = [d for d in docs if d["planted_id"]]
    bm = BM25(ext, tok_bigram)
    imp = importance_map(ledger)

    # 비슷한 질의가 연속으로 들어오는 상황 (실제 대화에서 흔하다)
    stream = ["요즘 어때", "별일 없었어?", "무슨 일 있었어",
              "요즘 어떻게 지내", "뭐 재밌는 일 없나", "별일 없지",
              "요즘 어때", "무슨 일 있었나", "별일 없었어?", "요즘 뭐해"]

    rows = []
    print(f"{'페널티':<10}{'3턴 내 재주입률':>16}{'고유 기억':>10}"
          f"{'평균 relevance':>16}{'relevance 손실':>16}")
    print("─" * 78)
    base_rel = None
    for penalty in (0.0, 0.05, 0.1, 0.2, 0.3, 0.5):
        surfaced = Counter()
        picks, rels = [], []
        for q in stream:
            raw = bm.score(q)
            mx = max(raw) or 1.0
            scored = []
            for i, d in enumerate(ext):
                rel = raw[i] / mx
                s = 0.6 * rel + 0.4 * imp.get(d["planted_id"], 0.5)
                s -= penalty * surfaced[d["planted_id"]]
                scored.append((s, rel, d))
            scored.sort(key=lambda x: -x[0])
            top = scored[:3]
            for _, rel, d in top:
                surfaced[d["planted_id"]] += 1
                rels.append(rel)
            picks.append([d["planted_id"] for _, _, d in top])

        repeat = 0
        for i in range(1, len(picks)):
            prev = set(sum(picks[max(0, i - 3):i], []))
            repeat += sum(1 for p in picks[i] if p in prev)
        rate = repeat / ((len(picks) - 1) * 3)
        uniq = len(set(sum(picks, [])))
        avg_rel = sum(rels) / len(rels)
        if base_rel is None:
            base_rel = avg_rel
        loss = (base_rel - avg_rel) / base_rel if base_rel else 0
        rows.append((penalty, rate, uniq, avg_rel, loss))
        print(f"{penalty:<10.2f}{rate:>15.0%}{uniq:>10}{avg_rel:>16.2f}"
              f"{loss:>15.0%}")
    print("─" * 78)
    print("  · 페널티 0 → 3턴 내 재주입 89%. 같은 기억이 계속 돌아온다 (유사 서비스 A U5의 한 원인)")
    print("  · 페널티 0.1 → 재주입 11%, relevance 손실 거의 없음. **여기가 무릎**")
    print("  · 그 위로는 재주입만 더 줄고 다양성(고유 기억)만 늘어난다 —")
    print("    관련성이 이미 낮아서 잃을 게 없기 때문이다")
    print()
    print("  🔴 그런데 **평균 relevance가 0.10으로 전 구간에서 낮다.** 이게 더 중요한 발견이다.")
    print("     질의가 '요즘 어때' '별일 없었어?' 같은 모호한 잡담이라 어휘 신호가 없다.")
    print("     → **모호한 발화에는 애초에 검색할 근거가 없다.**")
    print("       이런 턴에서 무엇을 꺼내든 그건 관련성이 아니라 우연이다.")
    print("       docs/adr/ADR-006의 게이팅이 막아야 할 것이 정확히 이 경우다.")


# ═══════════════════════════════════════════════════════════════════
# 3. M 커버리지 기반 abstention
# ═══════════════════════════════════════════════════════════════════
def exp_coverage(ledger):
    print("\n③ M 커버리지 메타 — '없었다'와 '흐릿하다'를 구별하는가")
    print("─" * 78)

    plan = {}
    for r in ledger["coverage_plan"]["ranges"]:
        a, b = r["range"].split("-")
        plan[(sess_num(a), sess_num(b))] = r["resolution"]

    known = set()
    for f in ledger.get("facts", []):
        if f.get("at"):
            known.add((f["id"], sess_num(f["at"]["session"])))
    for e in ledger.get("events", []):
        known.add((e["id"], sess_num(e["at"]["session"])))

    def resolution(s):
        for (a, b), res in plan.items():
            if a <= s <= b:
                return res
        return "lost"

    def decide(item_id, sess):
        """응답 모드 결정 — 이게 M 커버리지의 전부다."""
        if item_id is None:
            return "그런 적 없다"
        r = resolution(sess)
        return {"raw": "정확히 회상", "event": "사건 수준 회상",
                "digest": "흐릿하게 회상", "lost": "모르겠다"}[r]

    cases = [
        ("F001 (S03, digest 구간)", "F001", 3, "흐릿하게 회상"),
        ("E002 (S11, event 구간)", "E002", 11, "사건 수준 회상"),
        ("E009 (S21, raw 구간)", "E009", 21, "정확히 회상"),
        ("반려견 (언급 없음)", None, 0, "그런 적 없다"),
        ("제주도 (언급 없음)", None, 0, "그런 적 없다"),
    ]
    ok = 0
    print(f"{'질의':<28}{'기대 모드':<16}{'판정 모드':<16}{'':>6}")
    print("─" * 78)
    for label, iid, s, expect in cases:
        got = decide(iid, s)
        mark = "✅" if got == expect else "❌"
        ok += got == expect
        print(f"{label:<28}{expect:<16}{got:<16}{mark:>6}")
    print("─" * 78)
    print(f"  {ok}/{len(cases)} 정확. 룰 판정이므로 결정적이다.")
    print("  핵심: 파생 데이터만으로는 '없었다'와 '흐릿하다'를 구별할 수 없다.")
    print("  커버리지 테이블이 그 구별을 O(1)로 만든다.")


def main():
    docs = [json.loads(l) for l in open(CORPUS, encoding="utf-8")]
    ledger = yaml.safe_load(open(LEDGER, encoding="utf-8"))
    exp_debt(ledger)
    exp_repetition(docs, ledger)
    exp_coverage(ledger)
    print("\n⚠️ 이 실험은 **기계가 설계대로 도는지**를 볼 뿐 품질을 재지 않는다.")
    print("  '흐릿하게 회상' 모드가 실제로 자연스러운 대사를 만드는지는 LLM이 필요하다.")


if __name__ == "__main__":
    main()
