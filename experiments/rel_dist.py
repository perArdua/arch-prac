# -*- coding: utf-8 -*-
"""
rel_dist.py — `rel` 척도의 분포와 **등컷(equi-cut) θ 유도**. (라운드 2 단계 2)

## 왜 이 파일이 있나

`THETA_RELEVANCE = 0.05`는 `gate_sweep.py`가 찾은 무릎값이고, **어휘 척도에서만**
의미가 있다. 그런데 검색 모드를 코사인으로 바꾸면 같은 `0.05`가 **아무것도 자르지
않는다**(코사인 최솟값 0.241 > 0.05 — `embed_vs_bigram.py`). 숫자를 척도 간에
옮겨 적으면 게이트가 조용히 사라진다.

    θ를 **값**으로 지정하지 않는다. **자르는 비율(f)**로 지정한다.

그러면 척도가 달라도 같은 실험이 된다 — 라고 말하고 싶지만 **그것도 사실이 아니다**.
0에 원자가 있는 척도에서는 요청한 `f`를 달성할 수 없고, 달성된 컷이 `f`를 넘는다.
그래서 이 스크립트는 **`요청 f`와 `실제 컷`을 언제나 나란히 찍는다**(G15).
등컷은 문제를 없앤 것이 아니라 **θ-공간에서 f-공간으로 옮긴 것**이다.

## 모집단 (G12 — θ는 모집단 없이 쓸 수 없다)

    REL_mode := { score_mode(q.ask, s) : q ∈ 채점 18문항, s ∈ event 색인(user_deleted=0) }
              → n = 18 × 21 = **378쌍**

`embed_vs_bigram.py`의 270쌍(심긴 문서 27 × 프로브 10)은 **다른 실험**이고 그대로
둔다(P1). 두 모집단은 다르다 — 270쌍의 후보는 "심긴 문서"뿐이지만 검색기가 실제로
보는 것은 **색인 전체**다.

## 캐시 정책

임베딩 39개(문항 18 + 색인 21)는 **`experiments/data/REL_CACHE.json`**에 쓴다.
🔴 **`EMBED_CACHE.json`에는 쓰지 않는다.** 그 파일은 `embed_vs_bigram`의 재현성을
떠받치고 있고(37 텍스트 / 513,948 B), 39개를 더하면 그 실험의 캐시 히트/미스 경로가
바뀐다. **다른 실험의 캐시에 얹지 않는다.**

실행:
    python experiments/rel_dist.py              # 분포와 사다리 (ollama 없으면 77)
    python experiments/rel_dist.py --latency    # 임베딩 지연 게이트 (단계 2-L)
"""
import json
import math
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "prototype"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import memory as M                                         # noqa: E402
from memory import Memory                                  # noqa: E402
import embedding as EMB                                    # noqa: E402
from soak import seed, ingest, ROOT, CHAT                  # noqa: E402
from embed_vs_bigram import bigrams2                       # noqa: E402
import precision as P                                      # noqa: E402

W = 78

# ── 모듈 전역 상수 (G8) ────────────────────────────────────────────────
# 🔴 `EMBED_CACHE.json`이 아니다. 위 "캐시 정책" 참조.
REL_CACHE = os.path.join(ROOT, "experiments", "data", "REL_CACHE.json")

# 등컷 사다리. `0.915`가 기준인 이유: 어휘 척도의 현행 컷이 90.7%이고 그 **바로 위**
# 눈금이라 "현행보다 조금 조인 쪽"의 첫 점이 된다. 여는 방향은 어휘에 존재하지 않는다
# (0의 원자가 90.7%라 어떤 θ도 그보다 적게 자를 수 없다 — F27).
LADDER = [0.80, 0.915, 0.97]

# 현행값과의 대조표. `0.0001`이 있는 이유가 이 표의 전부다 — `0.05`와 **같은 비율**을
# 자르면 현행 θ는 임계 컷이 아니라 *"겹침이 정확히 0인 것만 버린다"*는 규칙이다.
THETA_TABLE = [0.0001, 0.05, 0.111, 0.15, 0.2]

# `docs/05`의 TTFT 예산 (하한, 상한) ms. 단계 2-L의 게이트가 읽는 숫자다.
TTFT_BUDGET = (200, 400)

# 🔴 **여기 있던 `LATENCY_F38` 전사(轉寫) 블록을 지웠다.** (F38 정정)
#
#    그 블록은 F38이 잰 여섯 개 리터럴(콜드 2,111 · 웜 p50 2,082 · p95 2,099 ·
#    배치 2,074 · 개별 2,068 ms)을 옮겨 적고 `--latency`가 다시 재지 않게 막고
#    있었다. 그리고 그 값들은 **틀렸다** — 2,082 ms의 **97.1%가 ollama에 닿지도
#    못한 실패 connect**였고(기본 호스트가 `localhost`였다 — `embedding.py:24`),
#    순 연산은 **34.2 ms**다.
#
#    전사가 원인은 아니었다. 이 라운드의 재측정은 **전부 같은 래퍼·같은 기기**를
#    지났고, Critic의 독립 실측(2,073 ms)조차 0.4% 안에서 일치했다 —
#    **공유된 결함을 통과한 독립 재측정은 결함을 독립적으로 확인해 준다.**
#    그것을 깨는 것은 재측정이 아니라 **0-연산 대조**다(`_tags_ms`): 모델을 한 번도
#    돌리지 않는 호출이 같은 값을 내면, 그 숫자는 모델에 대한 것이 아니다.
#    그래서 `--latency`는 이제 **재고, 그 대조행을 같은 표에 찍는다.**
#
#    ⚠️ 두 번 판정하는 문제(원 주석의 걱정)는 남는다. 답은 전사가 아니라
#       **판정의 정의가 하나라는 것**이다: 게이트는 언제나 *지금 이 기기에서 잰*
#       웜 p50이고, 스냅샷의 값은 그때의 판정이지 오늘의 판정이 아니다.

# 배치 대조에 쓰는 건수. F38의 표본 정의를 유지한다(20건 한 번 vs 개별 20회).
BATCH_N = 20


# ── 등컷 규칙 (결정 D의 rev2 완결판) ───────────────────────────────────

def theta_at(rel_values, cut_fraction):
    """
    θ_mode(f) := min{ x ∈ REL_mode : |{v ∈ REL_mode : v < x}| / |REL_mode| ≥ f }

    🔴 **정의역을 관측값으로 제한한다.** 제한이 없으면 조건집합이 `(a, ∞)` 꼴의
       열린집합이라 `min`이 **존재하지 않는다.** 관측값으로 제한하면 유한집합의
       최소이므로 언제나 잘 정의된다.

    🔴 **그런 `x`가 없으면 `+∞`를 돌려준다.** 예외가 아니다. `f`가 이 모드에서
       달성 가능한 최대 컷을 넘었다는 뜻이고, 그것은 오류가 아니라 **관측**이다
       — 호출부는 `"전량 컷"`이라고 찍는다. (계획 rev1이 스스로 고른 시험 케이스
       U5-b가 정확히 이 경우였고, rev1에는 그때의 규약이 적혀 있지 않았다.)
    """
    vals = list(rel_values)
    n = len(vals)
    if n == 0:
        return math.inf
    for x in sorted(set(vals)):
        if sum(1 for v in vals if v < x) / n >= cut_fraction:
            return x
    return math.inf


def actual_cut(rel_values, theta):
    """
    `theta_at`이 돌려준 θ로 컷 비율을 **다시 센다.**

    `theta_at`의 내부 계산을 재사용하지 않는 것이 요점이다 — 요청 `f`와 실제 컷이
    같아야 할 이유가 없고, 같은지 다른지는 **독립적으로 세어야** 알 수 있다.
    θ = +∞면 전량 컷(1.0)이다.
    """
    vals = list(rel_values)
    if not vals:
        return 0.0
    if theta == math.inf:
        return 1.0
    return sum(1 for v in vals if v < theta) / len(vals)


def q_at(v, p):
    """`embed_vs_bigram.py:202-204`과 **같은 분위수 규약**. 두 파일을 비교하려면
    같은 규약이어야 한다 — 규약이 다르면 p95가 다른 뜻이 된다."""
    v = sorted(v)
    return v[min(len(v) - 1, int(len(v) * p / 100))]


# ── 모집단 ─────────────────────────────────────────────────────────────

def population():
    """
    채점 18문항의 `ask`와 `event` 색인(`user_deleted=0`)의 요약을 돌려준다.

    `precision.partition`을 그대로 쓴다 — **채점 대상의 정의가 두 벌이 되면**
    378이라는 n이 어느 18문항의 것인지가 갈리지 않는다.
    """
    corpus, ledger, qs = P.load()
    key_of = P.key_index(ledger)
    scored, _ = P.partition(qs, key_of)
    dbf = f"{ROOT}/prototype/.reldist.db"
    if os.path.exists(dbf):
        os.remove(dbf)
    m = Memory(dbf)
    seed(m)
    ingest(m, corpus, ledger, timed=False)
    total = m.db.execute("SELECT COUNT(*) c FROM event WHERE chat_id=?",
                         (CHAT,)).fetchone()["c"]
    sums = [r["summary"] for r in m.db.execute(
        "SELECT summary FROM event WHERE chat_id=? AND user_deleted=0", (CHAT,))]
    m.db.close()
    os.remove(dbf)
    asks = [q["ask"] for q in scored]
    return asks, sums, total


def cos(a, b):
    d = sum(x * y for x, y in zip(a, M._same_dim(a, b)))  # 길이가 다르면 던진다 — `memory._cosine`의 검사 그대로(F12)
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return d / (na * nb)


def load_rel_cache():
    try:
        with open(REL_CACHE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def ensure_vectors(texts):
    """
    39개 텍스트의 벡터를 확보한다. `(vecs, 히트, 미스)` 또는 미확보 시 `(None, …)`.

    🔴 `EMB.embed(..., use_cache=False, save=False)`로 부른다. `embedding.py`의
       캐시 경로를 타면 `EMBED_CACHE_SWEEP.json`에 쓰게 되고, 그러면 이 실험의
       캐시가 **다른 실험의 캐시 파일 안에** 섞인다. 여기서 계산한 것은
       `REL_CACHE.json`에만 남는다.
    """
    cache = load_rel_cache()
    need = [t for t in texts if t not in cache]
    hit = len(texts) - len(need)
    if need:
        if not EMB.available():
            print(f"\n⚠️ 캐시 미스 {len(need)}건이고 ollama({EMB.OLLAMA_HOST})가 "
                  f"응답하지 않는다 — SKIP(77)으로 끝낸다.")
            for t in need:
                print(f"    없는 키: {t[:70]}")
            return None, hit, len(need)
        vecs = EMB.embed(need, use_cache=False, save=False)
        if vecs is None:
            print(f"\n⚠️ ollama가 {len(need)}건을 돌려주지 못했다 — SKIP(77).")
            return None, hit, len(need)
        cache.update(dict(zip(need, vecs)))
        with open(REL_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    return {t: cache[t] for t in texts}, hit, len(need)


# ── 출력 ───────────────────────────────────────────────────────────────

def dist_row(name, vals):
    pos = [v for v in vals if v > 0]
    atom0 = sum(1 for v in vals if v == 0) / len(vals) * 100
    print(f"  {name:<16}{len(vals):>6}{q_at(vals,50):>9.3f}{q_at(vals,75):>8.3f}"
          f"{q_at(vals,90):>8.3f}{q_at(vals,95):>8.3f}{max(vals):>8.3f}"
          f"{(min(pos) if pos else float('nan')):>11.4f}{atom0:>10.1f}%")


def ladder_rows(name, vals):
    """등컷 사다리 — **요청 f와 실제 컷을 나란히** 찍는다 (G15 rev2)."""
    atom0 = sum(1 for v in vals if v == 0) / max(len(vals), 1)
    print(f"\n  {name} 등컷 사다리  (0의 원자 {atom0:.1%})")
    print(f"    {'요청 f':>8}{'θ':>12}{'실제 컷':>10}{'통과 쌍':>9}   비고")
    out = []
    for f in LADDER:
        th = theta_at(vals, f)
        cut = actual_cut(vals, th)              # ← θ로부터 **독립적으로** 다시 센다
        passed = sum(1 for v in vals if v >= th) if th != math.inf else 0
        if th == math.inf:
            note = "🔴 전량 컷 (θ = +∞ — 이 모드에서 달성 불가능한 f다)"
        elif abs(cut - f) < 5e-4:
            note = "요청 f와 일치"
        elif atom0 >= f:
            # 0의 원자가 요청 f보다 크면 **어떤 θ도** f만큼만 자를 수 없다.
            note = (f"⚠️ 요청 f({f:.1%}) **초과** — 0의 원자({atom0:.1%}) 아래로 "
                    f"못 내려간다")
        else:
            # 원자가 아니어도 정의역이 **관측값**이라 눈금이 유한하다. 그 격자 탓이다.
            note = (f"⚠️ 요청 f({f:.1%}) **초과** {(cut - f) * 100:.1f}%p — "
                    f"관측값 격자 (원자 아님)")
        th_s = "+∞" if th == math.inf else f"{th:.4f}"
        print(f"    {f:>8.3f}{th_s:>12}{cut:>9.1%}{passed:>9}   {note}")
        out.append((f, th, cut))
    return out


def main():
    asks, sums, total_rows = population()
    n = len(asks) * len(sums)
    print("=" * W)
    print("rel 분포와 등컷 θ 유도 — 실제 검색 모집단 (라운드 2 단계 2)")
    print("=" * W)
    print(f"\n모집단: 채점 {len(asks)}문항 × event 색인 {len(sums)}행"
          f"(user_deleted=0 · 총 {total_rows}행) = **{n}쌍**")
    print(f"  ⚠️ `embed_vs_bigram.py`의 270쌍(심긴 문서 27 × 프로브 10)은 "
          f"**다른 모집단**이고 그대로 둔다 (P1).")

    lex = [len(set(M.bigrams(a)) & set(M.bigrams(s))) / max(len(set(M.bigrams(a))), 1)
           for a in asks for s in sums]
    fix = [len(set(bigrams2(a)) & set(bigrams2(s)))
           / max(len(set(bigrams2(a)) | set(bigrams2(s))), 1)
           for a in asks for s in sums]

    texts = asks + sums
    vecs, hit, miss = ensure_vectors(texts)
    print(f"\n임베딩 캐시 ({os.path.basename(REL_CACHE)}): "
          f"텍스트 {len(texts)}개 · 히트 {hit} · 미스 {miss}")
    if vecs is None:
        print("  → `embed` 모드를 잴 수 없다. **SKIP은 통과가 아니다** (G1).")
        return 77
    emb = [cos(vecs[a], vecs[s]) for a in asks for s in sums]

    modes = [("lexical", lex), ("lexical_fixed", fix), ("embed", emb)]

    print("\n" + "-" * W)
    print("분포 — 세 척도가 같은 378쌍을 어떻게 늘어놓는가")
    print("-" * W)
    print(f"  {'모드':<16}{'n':>6}{'중앙값':>9}{'p75':>8}{'p90':>8}{'p95':>8}"
          f"{'최대':>8}{'0초과 최솟값':>11}{'0의 원자':>10}")
    for name, v in modes:
        dist_row(name, v)
    # 🔄 레인 J — 레인 G가 오케스트레이터로 올린 세 건 중 셋째. 아래 출력 줄의
    #    인용이 memory.py:829에서 memory.py:914로 표류해 있었다. 출력 줄이라
    #    (rel_dist.txt:17) 레인 G의 *"여섯 스크립트 바이트 동일"* 수용 기준을
    #    밟지만, 그 기준은 레인 G의 것이었고 **표류한 인용을 출력에 남기는 쪽이
    #    더 비싸다.** 이 라운드의 스냅샷은 after-followups/이고 이 줄의 이동은
    #    그 README의 제외 목록에 적혀 있다.
    print("  lexical = 현행 `bigrams`의 덮기율 — `coverage(q, d)` (memory.py:1175) · "
          "lexical_fixed = 어절별 bigram + 자카드 · embed = bge-m3 코사인")

    # ── θ 대조표 — *"현행 θ는 게이트가 아니다"*를 출력이 말하게 한다 ──────
    print("\n" + "-" * W)
    print(f"θ 대조표 (lexical · n={n}) — 현행값이 무엇을 자르는가")
    print("-" * W)
    print(f"  {'θ':>10}{'자르는 비율':>12}{'통과 쌍':>9}")
    for th in THETA_TABLE:
        print(f"  {th:>10}{actual_cut(lex, th):>11.1%}"
              f"{sum(1 for v in lex if v >= th):>9}")
    same = actual_cut(lex, 0.0001) == actual_cut(lex, M.THETA_RELEVANCE)
    print(f"\n  🔴 θ=0.0001과 θ={M.THETA_RELEVANCE}가 **같은 비율을 자르는가**: "
          f"{'예 — 현행 θ는 임계 컷이 아니라 겹침 0만 버리는 규칙이다' if same else '아니오'}")

    # ── 등컷 사다리 ───────────────────────────────────────────────────
    print("\n" + "-" * W)
    print("등컷 θ 유도 — θ를 값이 아니라 **자르는 비율**로 지정한다 (결정 D)")
    print("-" * W)
    print("  ⚠️ `f`는 **요청이지 보증이 아니다.** 0에 원자가 있는 척도에서는 달성된 컷이")
    print("     요청한 `f`를 초과한다 — 그래서 두 값을 나란히 찍는다 (G15 rev2).")
    ladders = {name: ladder_rows(name, v) for name, v in modes}

    mismatch = sum(1 for rows in ladders.values() for f, _, c in rows
                   if abs(c - f) >= 5e-4)
    print(f"\n  요청 f ≠ 실제 컷 인 행: **{mismatch}행**")
    print("     어휘 두 모드에서 나오는 것이 정상이다. **0행이면 `theta_at`이 틀렸다.**")

    # ── 판정 두 줄 (§0.4의 부등식을 378쌍에서 다시 본다) ──────────────
    t = M.THETA_RELEVANCE
    lex_med, emb_min = q_at(lex, 50), min(emb)
    ok1, ok2 = lex_med < t, emb_min > t
    print("\n" + "-" * W)
    print(f"판정 — §0.4의 두 부등식이 378쌍에서도 성립하는가 (θ={t})")
    print("-" * W)
    print(f"  median(어휘) = {lex_med:.3f} < θ = {t}{'':<10}"
          f"{'PASS' if ok1 else 'FAIL':>10}")
    print(f"  min(코사인)  = {emb_min:.3f} > θ = {t}{'':<10}"
          f"{'PASS' if ok2 else 'FAIL':>10}")
    if ok1 and ok2:
        print("\n  → 270쌍에서 본 것이 실제 검색 모집단에서도 성립한다. "
              "**어휘에서 θ는 대부분을 자르고 코사인에서는 아무것도 안 자른다.**")
    else:
        print("\n  🔴 378쌍에서 부등식이 깨졌다. 270쌍은 '심긴 문서'만 후보였고 "
              "여기는 색인 전체다.")
        print("     **부검 시나리오 2와 §0.4를 다시 써야 한다.** 이 출력을 근거로 "
              "계획을 고칠 것.")
    print("=" * W)
    return 0


# ── 단계 2-L — 임베딩 지연 게이트 (결정 H · 🔴 **지금 잰다**) ────────────

def wiring_status():
    """
    문서 벡터 **배선 상태**를 지금 다시 센다 (작업 4 · F37).

    지연이 예산 안에 들어와도 이 둘이 0이면 `embed` 모드는 **읽기마다 색인 전체를
    재임베딩한다**: `(색인 행 + 쿼리 1) × 웜 p50`. 그 곱은 아래에서 **지금 잰
    p50으로** 계산한다 — 리터럴로 적으면 지연이 움직여도 숫자가 안 움직인다.
    지연 게이트가 PASS해도 남는 문제라서 같은 출력에 찍는다.
    """
    src = open(os.path.join(ROOT, "prototype", "memory.py"),
               encoding="utf-8").read()
    imports = len(re.findall(r"^\s*(?:import embedding|from embedding import)",
                             src, re.M))
    calls = len(re.findall(r"db_put_vec|db_get_vec", src))
    return imports, calls


def _tags_ms():
    """
    🔴 **0-연산 대조.** `GET /api/tags`는 설치된 모델 목록만 돌려준다 —
    **모델을 한 번도 돌리지 않는다.** 그래서 이 호출에 남는 시간은 전부
    클라이언트·연결·프로세스 경계 비용이다.

    이 한 줄이 F38을 뒤집었다. `localhost` 기본값에서 `/api/tags`가 **2,059.7 ms**
    였고 임베딩이 2,125.0 ms였다 — **차이가 65 ms**다. *연산이 텍스트당 2초를
    쓴다*는 F38의 진단은 그 순간 성립할 수 없다.

        연산을 안 하는 호출이 같은 값을 내면, 그 숫자는 모델에 대한 것이 아니다.
    """
    t0 = time.perf_counter()
    with urllib.request.urlopen(f"{EMB.OLLAMA_HOST}/api/tags",
                                timeout=EMB.EMBED_TIMEOUT) as r:
        r.read()
    return (time.perf_counter() - t0) * 1000


def _embed_ms(payload_text):
    """
    한 왕복의 벽시계 시간과 돌려받은 벡터 수. `payload_text`가 리스트면
    **한 번의 요청에 여러 텍스트**를 실어 보낸다 — 그것이 진짜 배치다.

    🔴 `EMB.embed()`를 쓰지 않는 이유가 이 실험의 핵심이다. 그 래퍼는
       `embedding.py:126`에서 **텍스트마다 따로** `_post`를 부른다 (`embed()` 안의 텍스트별 루프). 그래서
       래퍼로 잰 "배치"는 개별 호출 20번이고, F38이 본 *배치 이득 1.0배*는
       ollama의 성질이 아니라 **래퍼의 루프**였다.
    """
    t0 = time.perf_counter()
    r = EMB._post("/api/embed", {"model": EMB.EMBED_MODEL,
                                 "input": payload_text}, EMB.EMBED_TIMEOUT)
    return (time.perf_counter() - t0) * 1000, r.get("embeddings") or []


def latency_report():
    """
    🔴 **지금 잰다** (F38 정정 — `.omc/plans/verifier-f38-overturn.md`).

    이 함수는 F38의 값을 옮겨 적고 있었고, 그 값은 틀렸다. 절차는 F38 그대로다
    (콜드 1회를 떼고 개별 왕복 10회의 웜 p50 · 20건 배치 대조). 바뀐 것은 둘:

      1. **재측정한다.** 게이트의 판정은 언제나 *지금 이 기기에서 잰* 웜 p50이다.
      2. **0-연산 대조행을 같이 찍는다** — `GET /api/tags`. 그 행이 없었기 때문에
         2초의 97.1%가 실패한 connect라는 것을 아무도 못 봤다.

    ollama가 없으면 **77(SKIP)**이다. SKIP은 통과가 아니다 — 게이트를 판정할 수
    없다는 뜻이다.
    """
    lo, hi = TTFT_BUDGET
    print("=" * W)
    print(f"임베딩 호출당 지연 (prototype/embedding.py · {EMB.EMBED_MODEL} · 이 기기)")
    print("=" * W)
    info = EMB.checkpoint_info()
    if info["ollama"] is None:
        print("\n⚠️ ollama가 응답하지 않는다 — 지연을 잴 수 없다. SKIP(77).")
        print("   **SKIP은 통과가 아니다.** 게이트를 판정할 수 없으므로 R2b는 "
              "실행하지 않는다.")
        return 77
    # G15 — **어느 호스트로 쟀는지**가 이 측정의 일부다. `localhost`와
    # `127.0.0.1`이 이 기기에서 2,082 ms 대 55 ms로 갈린다.
    print(f"\n  현재 환경 확인: ollama {info['ollama']} · {info['model']} "
          f"digest {(info['digest'] or '?')[:16]}")
    print(f"  측정 호스트: {EMB.OLLAMA_HOST}"
          f"{'  (OLLAMA_HOST로 덮어씀)' if os.environ.get('OLLAMA_HOST') else ''}")
    print("  🔴 아래 수치는 **이번 실행이 지금 잰 값**이다 (F38의 전사가 아니다).")
    print("     절차: 콜드 1회를 떼고 개별 왕복 10회 · 20건 배치 대조 · "
          "0-연산 대조(`/api/tags`).")

    from embed_model_sweep import LATENCY_PROBES        # noqa: E402
    # 표본 정의를 **한 곳에서만** 읽는다. 두 벌이 되면 이 게이트와 후속 9의
    # 모델 스윕이 서로 다른 표본을 재면서 같은 이름으로 비교된다.

    cold_ms, vecs0 = _embed_ms(LATENCY_PROBES[0])
    if not vecs0:
        print("\n⚠️ ollama가 임베딩을 돌려주지 못했다 — SKIP(77).")
        return 77
    dim = len(vecs0[0])

    warm = []
    for t in LATENCY_PROBES:
        ms, v = _embed_ms(t)
        if not v:
            print("\n⚠️ 웜 측정 중 임베딩 실패 — SKIP(77).")
            return 77
        warm.append(ms)
    warm.sort()
    p50 = warm[len(warm) // 2] if len(warm) % 2 else \
        (warm[len(warm) // 2 - 1] + warm[len(warm) // 2]) / 2
    p95 = q_at(warm, 95)

    # 0-연산 대조 — 임베딩과 **같은 조건에서** 여러 번 재고 중앙값을 쓴다.
    tags = sorted(_tags_ms() for _ in range(5))
    tags_p50 = tags[len(tags) // 2]

    # 배치 대조. 같은 20개 텍스트를 (a) 한 요청에 실어서 (b) 20번 나눠서.
    _, sums, _ = population()
    batch_texts = (LATENCY_PROBES + sums)[:BATCH_N]
    batch_total, bvecs = _embed_ms(batch_texts)
    single_total = 0.0
    for t in batch_texts:
        ms, v = _embed_ms(t)
        if not v:
            print("\n⚠️ 배치 대조 중 임베딩 실패 — SKIP(77).")
            return 77
        single_total += ms
    n_b = len(batch_texts)
    batch_per = batch_total / n_b
    single_per = single_total / n_b
    gain = single_per / batch_per if batch_per else float("nan")

    print(f"\n  {'측정':<36}{'값':>34}")
    print("  " + "-" * (W - 2))
    print(f"  {'콜드 1회 (모델 적재 포함)':<36}"
          f"{f'{cold_ms:,.0f} ms · dim={dim}':>34}")
    print(f"  {'웜 p50 (n=' + str(len(warm)) + ' · 개별 왕복) ← 게이트':<36}"
          f"{f'{p50:,.0f} ms':>34}")
    print(f"  {'웜 p95 / min / max':<36}"
          f"{f'{p95:,.0f} / {warm[0]:,.0f} / {warm[-1]:,.0f} ms':>34}")
    print(f"  {'🔴 0-연산 대조 (GET /api/tags · n=5)':<36}"
          f"{f'{tags_p50:,.0f} ms':>34}")
    print(f"  {'   → 순 연산 (웜 p50 − 0-연산)':<36}"
          f"{f'{p50 - tags_p50:,.0f} ms':>34}")
    print(f"  {'배치 대조 (' + str(n_b) + '건 · 1요청)':<36}"
          f"{f'{batch_per:,.0f} ms/건 vs 개별 {single_per:,.0f} ms/건':>34}")
    print(f"  {'배치 이득':<36}{f'{gain:.1f}배':>34}")
    print(f"  {'docs/05 TTFT 예산':<36}{f'{lo} ~ {hi} ms':>34}")

    # 🔴 0-연산 대조를 **판정 앞에** 읽는다. 이 비율이 1에 가까우면 게이트가
    #    재고 있는 것은 모델이 아니라 클라이언트다 — F38이 정확히 그 경우였다.
    share = tags_p50 / p50 if p50 else 0.0
    print(f"\n  0-연산 대조 읽기")
    print(f"    웜 p50의 {share:.1%}가 **모델을 돌리지 않는 호출에서도** 든다.")
    if share >= 0.5:
        print("    🔴 절반 이상이다 — 이 숫자는 **모델에 대한 것이 아니다.** "
              "게이트를 판정하기 전에")
        print("       호스트·연결 경로를 먼저 본다 (F38이 여기서 뒤집혔다: "
              "97.1%가 실패한 connect였다).")
    else:
        print("    🟢 지배적이지 않다 — 웜 p50을 모델 비용으로 읽어도 된다.")

    passed = p50 <= hi
    print(f"\n  판정 (게이트 = 웜 p50 ≤ {hi} ms)")
    print(f"    쿼리 임베딩 1회 = {p50:,.0f} ms = 예산 상한({hi})의 {p50/hi:.2f}배 "
          f"· 하한({lo})의 {p50/lo:.2f}배")
    print(f"    → {'🟢 PASS' if passed else '🔴 FAIL'}")
    if passed:
        print("    🟢 지연은 더 이상 R2b를 막지 않는다. **남은 것은 배선이다** "
              "(아래) — 후속 9의 지연 조건은 닫혔고 배선 조건은 열려 있다.")
    else:
        print("    → **R2b(단계 3·4·5·6b) 미실행.** 재개 트리거는 이 측정을 그대로 "
              "반복해서 `웜 p50 ≤ 400 ms`가 나오는 것뿐이다 (후속 9).")

    # 작업 4 — 배선 상태. 지연이 통과해도 이 둘이 0이면 읽기마다 색인 전체를
    # 재임베딩한다. 그래서 **같은 출력에** 찍는다.
    imports, calls = wiring_status()
    per_query = (len(sums) + 1) * p50 / 1000
    per_query_batched = (len(sums) + 1) * batch_per / 1000
    print(f"\n  배선 상태 (prototype/memory.py — 지금 다시 셌다)")
    print(f"    `import embedding` {imports}건 · "
          f"`db_put_vec`/`db_get_vec` 호출부 {calls}건")
    if imports == 0 or calls == 0:
        print(f"    🔴 문서 벡터가 배선돼 있지 않다 — 이 상태로 `embed` 모드를 "
              f"읽기 경로에 넣으면 **읽기마다 색인 전체를 재임베딩**한다:")
        print(f"       ({len(sums)}행 + 쿼리 1) × {p50:,.0f} ms ≈ "
              f"{per_query:.2f}초 / 조회 (한 요청에 묶으면 "
              f"≈{per_query_batched:.2f}초).")
        print(f"       **지연 게이트가 PASS해도 남는 문제다** — 이제 후속 9에서 "
              f"살아 있는 것은 이 절반뿐이다.")
    print("=" * W)
    return 0


if __name__ == "__main__":
    if "--latency" in sys.argv:
        sys.exit(latency_report())
    sys.exit(main())
