"""
컨텍스트 배치 순서가 프롬프트 캐시 적중률과 비용에 미치는 영향 시뮬레이션.

검증 대상: docs/adr/ADR-007-context-packing-cache.md
  주장 1) 가변 블록을 뒤로 보내면 캐시 적중률이 크게 오른다
  주장 2) 정렬 기준은 "변경 빈도"가 아니라 "공유 범위 × 변경 빈도"다

LLM 호출이 필요 없다. 캐시는 접두사 일치 문제이므로 토큰 회계만으로 결정된다.
근거: causal mask 때문에 위치 i의 K,V는 앞쪽 토큰에만 의존한다 (docs/03 FP-2).

실행: python experiments/cache_sim.py
"""

from dataclasses import dataclass
from typing import List, Optional
import sys

# Windows 기본 콘솔 인코딩(cp949)에서 한글/기호 출력 보장
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── Gemini 3.7 Flash 공식 단가 (2026-09 확인, USD per 1M tokens) ──────────
PRICE_IN = 0.75
PRICE_CACHED = 0.075      # 입력가의 10%
PRICE_OUT = 3.75

OUTPUT_TOKENS = 400       # 한국어 롤플레이 응답 평균 (docs/05 §3.1)
TURNS_PER_MONTH = 10_000  # 헤비 유저 (docs/04 §2)


@dataclass
class Block:
    name: str
    tokens: int
    change_every: Optional[int]   # None = 불변, N = N턴마다 내용이 바뀜
    scope: str                    # global | character | chat
    slides: bool = False          # 슬라이딩 윈도우인가 (앞에서 밀려남)

    def content_id(self, turn: int, window_chunk: int = 1) -> str:
        """이 턴에서 이 블록의 내용을 식별하는 값. 같으면 캐시 재사용 가능."""
        if self.slides:
            # 슬라이딩 윈도우: 앞에서 밀려나면 접두사가 깨진다.
            # window_chunk 단위로 밀면 chunk 턴 동안은 안정적.
            return f"{self.name}:w{turn // window_chunk}"
        if self.change_every is None:
            return f"{self.name}:const"
        return f"{self.name}:v{turn // self.change_every}"


# ── 블록 정의 (docs/06 §5 주입 예산) ────────────────────────────────────
def blocks():
    return {
        "system":    Block("system", 200, None, "global"),
        "persona":   Block("persona", 700, None, "character"),
        "speech":    Block("speech_rules", 120, None, "character"),
        "state":     Block("relationship(L2)", 150, 15, "chat"),
        "charmem":   Block("character_memory(L8)", 150, 30, "chat"),
        "scene":     Block("scene(L3)", 50, 5, "chat"),
        "digest_lt": Block("digest_lifetime(L4)", 400, 50, "chat"),
        "digest_s":  Block("digest_session(L4)", 300, 10, "chat"),
        "debt":      Block("debt(L9)", 100, 25, "chat"),
        "recent":    Block("recent_turns(L0)", 1500, None, "chat", slides=True),
        "memory":    Block("retrieved(L5/L6)", 400, 1, "chat"),   # 매 턴 교체
        "current":   Block("current_utterance", 80, 1, "chat"),
    }


# ── 배치 레이아웃 ───────────────────────────────────────────────────────
B = blocks()

LAYOUTS = {
    # K1: 검색된 기억이 앞쪽 — 매 턴 바뀌므로 뒤쪽 전부가 무효화된다
    "K1_기억_앞": [
        B["system"], B["persona"], B["speech"],
        B["memory"],                                    # ← 매 턴 교체
        B["state"], B["charmem"], B["scene"],
        B["digest_lt"], B["digest_s"], B["debt"],
        B["recent"], B["current"],
    ],
    # K2: 의미 단위로 묶은 순서 (직관적이지만 빈도순이 아니다)
    #     ⚠️ scene(5턴마다)이 digest_s(10턴)·state(15턴)보다 앞에 있다 → 상한을 낮춘다
    "K2_의미순": [
        B["system"], B["persona"], B["speech"],
        B["state"], B["charmem"],
        B["digest_lt"], B["digest_s"],
        B["debt"], B["scene"],
        B["recent"],
        B["memory"], B["current"],
    ],
    # K3: 엄밀하게 변경 빈도 오름차순 — 가장 자주 바뀌는 것을 뒤로
    "K3_엄밀_빈도순": [
        B["system"], B["persona"], B["speech"],         # 불변
        B["digest_lt"],                                 # 50턴
        B["charmem"],                                   # 30턴
        B["debt"],                                      # 25턴
        B["state"],                                     # 15턴
        B["digest_s"],                                  # 10턴
        B["scene"],                                     # 5턴  ← K2에서 너무 앞이었다
        B["recent"],                                    # 슬라이딩
        B["memory"], B["current"],                      # 매 턴
    ],
}


SESSION_LEN = 50    # 세션당 턴 수 (docs/08 D1: 일 두세 시간 ÷ 턴당 30초)


def simulate(layout: List[Block], n_turns: int, window_chunk: int = 1,
             popular_character: bool = False, session_len: int = SESSION_LEN):
    """
    턴별 (uncached, cached) 토큰을 계산한다.

    세션 경계에서 유저 자신의 캐시는 만료된다(몇 시간 자리를 비우므로).
    그런데 인기 캐릭터라면 다른 유저들이 같은 접두사를 계속 때리고 있어서
    global/character 스코프 블록은 여전히 따뜻하다. 이게 유저 간 공유의 실체다.
    """
    prev_ids = None
    total_uncached = total_cached = 0

    # 유저 간에 공유되는 접두사 = 레이아웃 맨 앞의 연속된 global/character 블록
    shared = 0
    for b in layout:
        if b.scope in ("global", "character"):
            shared += b.tokens
        else:
            break

    for turn in range(n_turns):
        ids = [b.content_id(turn, window_chunk) for b in layout]

        # 세션 경계: 유저 자신의 캐시 만료
        if turn % session_len == 0:
            prev_ids = None

        common = 0
        if prev_ids:
            for a, b_ in zip(ids, prev_ids):
                if a != b_:
                    break
                common += 1

        cached = sum(b.tokens for b in layout[:common])
        uncached = sum(b.tokens for b in layout[common:])

        # 인기 캐릭터면 공유 접두사는 세션이 끊겨도 살아있다
        if popular_character and cached < shared:
            delta = min(shared - cached, uncached)
            cached += delta
            uncached -= delta

        total_uncached += uncached
        total_cached += cached
        prev_ids = ids

    return total_uncached, total_cached


def cost(uncached, cached, n_turns):
    """월 비용 (USD). n_turns를 TURNS_PER_MONTH로 스케일."""
    scale = TURNS_PER_MONTH / n_turns
    c_in = (uncached * PRICE_IN + cached * PRICE_CACHED) / 1e6 * scale
    c_out = OUTPUT_TOKENS * n_turns * PRICE_OUT / 1e6 * scale
    return c_in, c_out


def report(title, rows):
    print(f"\n{title}")
    print("─" * 78)
    print(f"{'구성':<34}{'캐시적중':>9}{'입력$/월':>11}{'출력$/월':>11}{'합계':>11}")
    print("─" * 78)
    for name, (unc, cac, n) in rows.items():
        hit = cac / (unc + cac) * 100
        c_in, c_out = cost(unc, cac, n)
        print(f"{name:<34}{hit:>8.1f}%{c_in:>11.2f}{c_out:>11.2f}{c_in + c_out:>11.2f}")
    print("─" * 78)


def main():
    N = 2000

    # ── 실험 1: 배치 순서 ────────────────────────────────────────────
    rows = {}
    for name, layout in LAYOUTS.items():
        rows[name] = (*simulate(layout, N), N)
    report("실험 1 — 배치 순서 (슬라이딩 1턴, 비인기 캐릭터)", rows)
    print("  K1→K2: 가변 블록(retrieved)을 앞에 두면 그 뒤 전부가 매 턴 무효화된다.")
    print("  K2→K3: '의미 단위로 묶기'는 직관적이지만 빈도순이 아니다.")
    print("         scene(5턴)이 state(15턴)·digest_s(10턴)보다 앞에 있으면")
    print("         그 뒤는 전부 5턴마다 무효화된다 — 가장 자주 바뀌는 블록이 상한을 정한다.")

    # ── 실험 2: 슬라이딩 윈도우 청크 ─────────────────────────────────
    rows = {}
    for chunk in (1, 5, 10, 25):
        unc, cac = simulate(LAYOUTS["K3_엄밀_빈도순"], N, window_chunk=chunk)
        rows[f"K3 + 윈도우 {chunk}턴 단위 축출"] = (unc, cac, N)
    report("실험 2 — 슬라이딩 윈도우가 캐시를 깨는 정도 (K3)", rows)
    print("  최근 N턴을 1턴씩 밀면 append가 아니라 evict라서 접두사가 매 턴 깨진다.")
    print("  청크 축출로 안정화되지만, 그 위 블록(scene 5턴)이 상한을 만든다.")

    # ── 실험 3: 유저 간 공유 (docs/07 A3) ────────────────────────────
    rows = {}
    for label, pop in (("비인기 캐릭터 (공유 없음)", False),
                       ("인기 캐릭터 (접두사 상시 warm)", True)):
        unc, cac = simulate(LAYOUTS["K3_엄밀_빈도순"], N, window_chunk=10,
                            popular_character=pop)
        rows[label] = (unc, cac, N)
    report("실험 3 — 유저 간 접두사 공유 (K3 + 청크 10, 세션 50턴)", rows)
    print("  세션 경계에서 유저 자신의 캐시는 만료된다(몇 시간 자리를 비우므로).")
    print("  인기 캐릭터는 다른 유저들이 같은 접두사를 계속 때려서 여전히 따뜻하다.")
    print("  → 롱테일 캐릭터가 구조적으로 비싸다 (docs/adr/ADR-008).")

    # ── 실험 4: 세션 길이가 유저 간 공유 이득을 좌우한다 ──────────────
    print("\n실험 4 — 세션 길이별 유저 간 공유 이득 (K3 + 청크 10)")
    print("─" * 78)
    print(f"{'세션 길이':<14}{'비인기 $/월':>14}{'인기 $/월':>14}{'절감':>10}")
    print("─" * 78)
    for slen in (5, 10, 25, 50, 100):
        a = cost(*simulate(LAYOUTS["K3_엄밀_빈도순"], N, 10, False, slen), N)
        b = cost(*simulate(LAYOUTS["K3_엄밀_빈도순"], N, 10, True, slen), N)
        ta, tb = sum(a), sum(b)
        print(f"{slen:>5}턴{'':<8}{ta:>14.2f}{tb:>14.2f}{(1 - tb / ta) * 100:>9.1f}%")
    print("─" * 78)
    print("  세션이 짧을수록 캐시 만료가 잦아 유저 간 공유 이득이 커진다.")
    print("  → 짧게 자주 들어오는 유저가 많은 서비스일수록 접두사 공유 설계가 중요하다.")

    # ── 종합 ─────────────────────────────────────────────────────────
    worst = simulate(LAYOUTS["K1_기억_앞"], N, window_chunk=1)
    best = simulate(LAYOUTS["K3_엄밀_빈도순"], N, window_chunk=10,
                    popular_character=True)
    w_in, w_out = cost(*worst, N)
    b_in, b_out = cost(*best, N)
    print(f"\n{'═' * 78}")
    print(f"최악(K1, 1턴 슬라이딩, 공유 없음) : ${w_in + w_out:.2f}/월  (입력 ${w_in:.2f})")
    print(f"최선(K2, 10턴 청크, 공유 있음)    : ${b_in + b_out:.2f}/월  (입력 ${b_in:.2f})")
    print(f"입력 비용 절감                     : {(1 - b_in / w_in) * 100:.1f}%")
    print(f"총 비용 절감                       : {(1 - (b_in + b_out) / (w_in + w_out)) * 100:.1f}%")
    print(f"\n※ 출력 비용 ${w_out:.2f}는 배치와 무관하게 고정 — '출력 비용 바닥' (docs/05 §3.2)")
    print(f"  메모리 아키텍처가 건드릴 수 있는 건 총비용의 일부뿐이다.")
    print("═" * 78)


if __name__ == "__main__":
    main()
