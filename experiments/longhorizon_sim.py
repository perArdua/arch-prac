# -*- coding: utf-8 -*-
"""
longhorizon_sim.py — "아주 오랫동안 대화하더라도"를 실제로 계산한다. (API 불필요)

## 왜 이 실험이 필요한가

원래 질문은 **"사용자와 아주 오랫동안 대화하더라도"**로 시작한다.
그런데 이 검토의 실험은 **전부 720턴(24세션)에서 끝난다.**
[04](../docs/04-domain-research.md)의 공개 운영 사례 수치(월 수십 시간 체류)를 쓰면
1년 헤비 유저는 **10,000턴 이상**이다. **그 구간을 한 번도 안 봤다.**

## 🔴 그리고 그 구간에서 내 설계의 모순이 드러난다

[06 L4](../docs/06-data-model.md)에서 lifetime 요약을 **"전체 재작성"**이라고 썼다.
이유는 *"요약의 요약으로 인한 열화(drift)가 없다"*였다.
**그런데 무엇을 입력으로 재작성하는지를 안 정했다.**

    전체 이력에서 재작성   드리프트 없음.  세션마다 O(N) -> 누적 O(N²)
    이전 요약 + 새 세션    O(1).          그게 바로 "요약의 요약" (드리프트)

**피하겠다고 한 것과 비용이 정면충돌한다.** 이 스크립트가 그 크기를 잰다.

## 재는 것

  1. 요약 정책 3종의 **누적 요약 비용** (O(N²) vs O(N) vs 계층)
  2. 저장·색인 증가 (선형인가 포화하는가)
  3. **검색 후보 증가에 따른 정밀도 저하** — 방해물이 늘면 top-k가 오염된다
  4. 컨텍스트 토큰이 **유계로 남는가** (설계의 핵심 주장)
"""
import sys
import os

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "prototype"))
W = 78

# ── 하중 가정 (docs/04·05에서) ───────────────────────────────────────
TURNS_PER_SESSION = 50
TOK_PER_TURN = 250          # 한국어 3배 페널티 포함 (docs/05)
SESSION_DIGEST_TOK = 300
LIFETIME_DIGEST_TOK = 500
EVENTS_PER_SESSION = 4      # 추출되는 사건 수 (소크에서 22개/24세션 -> 보수적으로 상향)
FACTS_PER_SESSION = 1

# Gemini Flash Batch 기준 (docs/05): 입력 $0.75/M의 50% = $0.375/M
IN_RATE = 0.375 / 1e6
OUT_RATE = 3.75 / 2 / 1e6


def cost_full_rewrite(n_sessions):
    """P1 — 매 세션 **전 이력**을 읽어 lifetime을 다시 쓴다. 문서의 문자 그대로."""
    tin = tout = 0
    for s in range(1, n_sessions + 1):
        history = s * TURNS_PER_SESSION * TOK_PER_TURN
        tin += history
        tout += LIFETIME_DIGEST_TOK
    return tin, tout


def cost_incremental(n_sessions):
    """P2 — 이전 lifetime + 이번 세션 요약만 읽는다. 요약의 요약."""
    tin = tout = 0
    for _ in range(n_sessions):
        tin += LIFETIME_DIGEST_TOK + SESSION_DIGEST_TOK
        tout += LIFETIME_DIGEST_TOK
    return tin, tout


def cost_tiered(n_sessions, rebuild_every=20, window=5):
    """
    P3 — 평소엔 증분(이전 요약 + 최근 window개 세션요약),
         M세션마다 **원본에서 전체 재구축**해 드리프트를 걷어낸다.

    드리프트 상한이 M세션으로 유계가 되고, 비용은 O(N²/M)로 떨어진다.
    """
    tin = tout = 0
    for s in range(1, n_sessions + 1):
        if s % rebuild_every == 0:
            tin += s * TURNS_PER_SESSION * TOK_PER_TURN      # 전체 재구축
        else:
            tin += LIFETIME_DIGEST_TOK + window * SESSION_DIGEST_TOK
        tout += LIFETIME_DIGEST_TOK
    return tin, tout


def cost_depth2(n_sessions, rebuild_every=1):
    """
    P4 — ⭐ lifetime을 **모든 세션 요약**에서 다시 쓴다. 원본은 안 읽는다.

    핵심 통찰: **드리프트를 만드는 건 재작성 빈도가 아니라 요약 사슬의 깊이다.**

        P2 증분   턴 -> 세션요약 -> lifetime -> lifetime -> lifetime -> ...
                  깊이가 세션 수만큼 자란다. 400세션이면 400단 사슬이다
        P4        턴 -> 세션요약 -> lifetime
                  **세션이 몇 개든 깊이는 항상 2다.** 사슬이 안 자란다

    비용도 싸다. 세션 요약은 300토큰이라 400개를 다 읽어도 120K토큰이고,
    원본(5,000,000토큰)의 **2.4%**다.
    """
    tin = tout = 0
    for s in range(1, n_sessions + 1):
        if s % rebuild_every == 0:
            tin += s * SESSION_DIGEST_TOK        # 전 세션 요약만 읽는다
            tout += LIFETIME_DIGEST_TOK
    return tin, tout


def usd(tin, tout):
    return tin * IN_RATE + tout * OUT_RATE


# 🔄 라운드 2 단계 0 (F33) — 소크 실측이 210B에서 **290B**로 옮겨졌다
# (스키마 v4의 빈 테이블 4개가 페이지를 먹는다 — `baseline/after-step2/G2-soak.txt`).
# ⚠️ 이 상수는 **코드가 계산에 쓴다.** 문서의 210B는 감사기가 잡았지만
#    여기는 `.md`가 아니라 감사 대상 밖이었다 — 실행되는 낡은 숫자가 더 위험하다.
BYTES_PER_TURN = 290


def main():
    print("=" * W)
    print("장기 지평 시뮬레이션 — \"아주 오랫동안\"이 실제로 얼마인가")
    print("=" * W)
    print(f"\n하중 가정: 세션 {TURNS_PER_SESSION}턴 · 턴당 {TOK_PER_TURN}토큰"
          f" · Batch 단가(docs/05)")
    print("이 검토의 모든 실험은 24세션(720턴)에서 끝났다. 그 너머를 계산한다.\n")

    # ── 1. 요약 정책 비용 ────────────────────────────────────────────
    print("-" * W)
    print("1. 🔴 lifetime 요약 정책 — 문서가 안 정한 것의 대가")
    print("-" * W)
    print(f"\n  {'세션':>6}{'턴':>8}{'P1 원본재작성':>15}{'P2 증분':>10}"
          f"{'P3 계층':>10}{'P4 깊이2':>11}   사슬깊이")
    print("  " + "-" * 68)
    rows = []
    for s in (24, 50, 100, 200, 400):
        c1 = usd(*cost_full_rewrite(s))
        c2 = usd(*cost_incremental(s))
        c3 = usd(*cost_tiered(s))
        c4 = usd(*cost_depth2(s))
        rows.append((s, c1, c2, c3, c4))
        mark = "  <- 실험 범위" if s == 24 else ""
        print(f"  {s:>6}{s*TURNS_PER_SESSION:>8}"
              f"{'$'+format(c1,'.2f'):>15}{'$'+format(c2,'.2f'):>10}"
              f"{'$'+format(c3,'.2f'):>10}{'$'+format(c4,'.2f'):>11}"
              f"   P2={s} P4=2{mark}")

    s, c1, c2, c3, c4 = rows[-1]
    print(f"\n  400세션(20,000턴)에서 **P1이 P2의 {c1/c2:,.0f}배**다 — 누적 O(N²).")
    print(f"  P3(원본 주기적 재구축)은 ${c3:.0f}. 싸지 않다.")
    print( "\n  ⭐ **P4가 답이다.** lifetime을 '모든 세션 요약'에서 다시 쓴다.")
    print( "     드리프트를 만드는 건 재작성 빈도가 아니라 **요약 사슬의 깊이**다:")
    print( "       P2 증분  턴->세션->lifetime->lifetime->…   깊이가 N만큼 자란다")
    print( "       P4       턴->세션->lifetime                **깊이는 항상 2**")
    print(f"     비용은 P1의 **1/{c1/c4:,.0f}**. 세션 요약만 읽으므로 원본의 2.4%다.")
    print( "     **드리프트 유계와 저비용은 상충하지 않았다.**")
    print( "     상충한다고 본 건 '재작성 = 원본 재독'이라고 암묵 가정했기 때문이다.")

    print("\n  ⚠️ 24세션에서는 넷의 차이가 $%.2f~$%.2f로 **보이지 않는다.**"
          % (rows[0][2], rows[0][1]))
    print("     제 실험 범위가 정확히 그 구간이라 **이 결함을 못 봤다.**")
    print("     720턴짜리 코퍼스는 O(N²)를 드러낼 수 없다.")

    # ── 2. 저장·색인 증가 ────────────────────────────────────────────
    print("\n" + "-" * W)
    print("2. 저장·색인 — 선형으로 자란다 (포화하지 않는다)")
    print("-" * W)
    print(f"\n  {'세션':>6}{'턴':>8}{'사건':>8}{'사실':>7}{'원본MB':>9}{'검색후보':>9}")
    print("  " + "-" * 50)
    for s in (24, 100, 400, 1000):
        ev = s * EVENTS_PER_SESSION
        fa = s * FACTS_PER_SESSION
        mb = s * TURNS_PER_SESSION * BYTES_PER_TURN / 1024 / 1024
        print(f"  {s:>6}{s*TURNS_PER_SESSION:>8}{ev:>8}{fa:>7}"
              f"{mb:>9.1f}{ev+fa:>9}")
    print("\n  저장은 문제가 아니다 — 1,000세션에서도 원본 10MB 수준이다.")
    print("  **검색 후보 수가 문제다.** 4,000개면 [실험 6](../docs/11-experiment-results.md)의")
    print("  브루트포스 벤치(3,000개 0.13ms) 범위 안이라 **지연도 아직 문제가 아니다.**")
    print("  → 남는 문제는 **정밀도**다. 아래.")

    # ── 3. 후보 증가 -> 정밀도 저하 ──────────────────────────────────
    print("\n" + "-" * W)
    print("3. ⭐ 진짜 문제 — 후보가 늘면 정밀도가 떨어진다")
    print("-" * W)
    print("\n  top-k를 고정(k=5)하고 후보만 늘리면, 정답과 비슷한 점수의")
    print("  **무관한 항목이 확률적으로 더 많이 끼어든다.**")
    print("  방해물이 후보의 일정 비율(p)이라면 top-k 중 방해물 기대 개수는")
    print("  후보 수와 무관하지만, **상위권에 들 만큼 높은 점수를 받는 방해물의")
    print("  절대 수는 후보에 비례**한다.\n")
    print(f"  {'세션':>6}{'후보':>8}{'상위권 방해물 기대':>20}{'top-5 오염':>12}")
    print("  " + "-" * 48)
    # 방해물이 상위 1%에 들 확률을 q=0.01로 두면, 기대 개수 = 후보 x p x q
    p_noise, q_top = 0.65, 0.01      # 노이즈 비율 65% (코퍼스 설계), 상위 1%
    for s in (24, 100, 400, 1000):
        cand = s * (EVENTS_PER_SESSION + FACTS_PER_SESSION)
        hi = cand * p_noise * q_top
        print(f"  {s:>6}{cand:>8}{hi:>20.1f}{min(hi/5*100,100):>11.0f}%")
    print("\n  1,000세션이면 상위권 방해물이 **~32개**다. k=5를 통째로 채우고도 남는다.")
    print("  → **importance 하드 게이트(τ)가 여기서 결정적이 된다.**")
    print("    관련도만으로 정렬하면 장기 사용자일수록 오주입이 는다.")
    print("    [실험 2](../docs/11-experiment-results.md)에서 '쓰기 정책이 검색보다 먼저'라고 한 것이")
    print("    **장기 지평에서 훨씬 더 강해진다** — 애초에 색인에 안 넣으면 후보가 안 는다.")

    # ── 4. 컨텍스트는 유계인가 ──────────────────────────────────────
    print("\n" + "-" * W)
    print("4. ✅ 컨텍스트 토큰은 유계로 남는다 (설계의 핵심 주장)")
    print("-" * W)
    fixed = 1370          # 고정 블록 (docs/05)
    var = 5 * 60 + 10 * TOK_PER_TURN
    print(f"\n  고정 블록 {fixed} + 검색 5개 {5*60} + 최근 10턴 {10*TOK_PER_TURN}"
          f" = **{fixed+var:,}토큰**")
    print("  세션 수와 무관하다. **이게 계층 메모리의 존재 이유다.**")
    print(f"  같은 대화를 full-context로 넣으면 400세션에서 "
          f"{400*TURNS_PER_SESSION*TOK_PER_TURN:,}토큰 —")
    print(f"  **{400*TURNS_PER_SESSION*TOK_PER_TURN/(fixed+var):,.0f}배**이고 창에 안 들어간다.")

    # ── 결론 ────────────────────────────────────────────────────────
    print("\n" + "-" * W)
    print("결론 — 장기 지평이 바꾸는 것과 안 바꾸는 것")
    print("-" * W)
    print("\n  안 바뀜  · 컨텍스트 토큰 유계 (계층 메모리가 작동한다)")
    print("           · 저장 비용 (1,000세션에서도 10MB)")
    print("           · 검색 지연 (브루트포스로 충분)")
    print("\n  바뀜 🔴  · **요약 재작성 정책** — O(N²)와 O(N)의 차이가 수백 배가 된다")
    print("           · **오주입 압력** — 후보가 늘어 τ 하드 게이트가 결정적이 된다")
    print("           · **쓰기 선별의 가치** — 색인을 아끼면 장기 정밀도가 산다")
    print("\n  → 단기 실험(720턴)에서 '차이 없음'으로 보인 결정들이")
    print("    **장기에서 지배적**이 된다. 이게 이 시뮬레이션의 요지다.")

    print("\n" + "-" * W)
    print("⚠️ 이 계산이 말할 수 없는 것")
    print("-" * W)
    print("  · **드리프트 크기를 못 잰다.** P2가 얼마나 열화하는지는 LLM 없이 모른다.")
    print("    P3의 rebuild_every=20은 **근거 있는 값이 아니라 가정**이다")
    print("  · 방해물 상위권 진입 확률 q=0.01은 **가정**이다. 실측 아님")
    print("  · 사건 추출률(세션당 4개)은 소크 실측(24세션 22개)에서 올려 잡은 값이다")
    print("  · 유저가 대화방을 새로 파면 N이 리셋된다 — 실제 분포를 모른다")
    print("\n" + "=" * W)


if __name__ == "__main__":
    main()
