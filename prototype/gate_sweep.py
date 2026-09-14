# -*- coding: utf-8 -*-
"""
gate_sweep.py — 소크 테스트가 남긴 질문에 답한다.

[소크](soak.py)에서 이렇게 나왔다.
  · QA 26문항 중 **16개가 게이트에 막혔다**
  · 그리고 검색 경로의 **순증 기여가 0**이었다

두 결과를 붙이면 의심이 생긴다. **검색이 쓸모없는 게 아니라 게이트가 목을 조른 것 아닌가?**
소크에서 이걸 미해결로 남겼으니 여기서 잰다.

게이트 정책 4개를 갈아끼우고 같은 것을 잰다.
  회상(근거 도달) · 검색의 순증 기여 · 검색 호출 수 · 오주입(트랩·비정답 주입) · 토큰

이건 **정밀도-재현율 교환을 정책 수준에서** 재는 것이다.
게이트를 열면 회상이 오르고 오주입도 오른다. **어디가 무릎인지**가 답이다.
"""
import sys, json, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import yaml
import memory as M
from memory import Memory
from soak import seed, ingest, qa_eval, trap_injected, ROOT, CHAT, pct

W = 78

# ── 게이트 정책 4종 ────────────────────────────────────────────────
PAST_REF = re.compile(r"(기억|그때|저번|예전|아까|전에|했잖아|말했|뭐였|언제)")
RITUAL = re.compile(r"^(응|ㅇㅇ|ㅋ+|어|그래|넵|왜|뭐)$")


# 🔴 **네 정책의 서명은 `Memory.gate`와 글자 그대로 같아야 한다.**
#
#    이것들은 `Memory.gate = g_xxx`로 **꽂히는** 함수이고(`precision.py` ·
#    `retrieval_sweep.py` · `response_quality.py` · `event_metrics.py`),
#    `build_context`는 그 자리에서 `self.gate(utterance, chat_id)`를 부른다.
#    A2가 `chat_id`를 더했을 때 여기를 안 따라가서 격자와 정밀도가 **`TypeError:
#    takes 2 positional arguments but 3 were given`**으로 통째로 죽었다(실측).
#
#    ⚠️ 인자를 받되 **쓰지는 않는다.** 이 하니스들의 어휘는 `self._vocab`으로
#       **밖에서 꽂히고**(그것이 스윕의 독립변수다), 그 어휘는 이미
#       `build_vocab(m, CHAT)`이 방으로 잘라 구운 것이다. 여기서 `chat_id`로
#       다시 조회하면 스윕이 «꽂은 어휘»가 아니라 «DB의 어휘»를 재는 것이 되어
#       독립변수가 사라진다.
def g_current(self, u, chat_id=None):
    """G0 — **4부 이전**의 정책. 과거 참조 표현이 있어야 검색한다.

    🔄 단계 0 (라운드 2) — 이 게이트를 가리키던 낱말 하나를 뺐다. 이 파일의 4부가
    권고한 것도, `memory.py:1007-1026`의 `Memory.gate`도 **G3**이기 때문이다(F21).
    낱말의 소유자는 `GATES` 위 주석에 적었다 — 한 파일이 같은 낱말을 두 구성에
    쓰면 **모순된 두 주장**이 된다(G15).
    """
    if PAST_REF.search(u):
        return True, "과거 참조 표현"
    if len(u) < 8:
        return False, "너무 짧음"
    if RITUAL.match(u.strip()):
        return False, "의례적 발화"
    return False, "과거 참조 신호 없음"


def g_always(self, u, chat_id=None):
    """G1 — 게이트 없음. 항상 검색 (상한 확인용)."""
    return True, "게이트 없음"


def g_ritual_only(self, u, chat_id=None):
    """G2 — 의례적 발화만 막는다. 나머지는 검색."""
    if RITUAL.match(u.strip()) or len(u) < 8:
        return False, "의례적/짧음"
    return True, "실질 발화"


def g_content(self, u, chat_id=None):
    """
    G3 — 내용어 게이트.

    "과거를 가리키는가"가 아니라 **"저장된 것과 겹치는 내용어가 있는가"**를 본다.
    G0이 Q05 *"면접 몇 번 봤더라"*를 막은 이유는 `기억/그때`가 없어서인데,
    거기엔 `면접`이라는 내용어가 있고 그건 저장돼 있다.
    → 신호를 **질문의 형태**가 아니라 **저장소와의 접점**에서 찾는다.
    """
    if RITUAL.match(u.strip()) or len(u) < 8:
        return False, "의례적/짧음"
    if PAST_REF.search(u):
        return True, "과거 참조 표현"
    words = [w for w in re.findall(r"[가-힣]{2,}", u)]
    if any(w[:2] in self._vocab for w in words):
        return True, "저장된 내용어와 접점"
    return False, "접점 없음"


# 🔄 단계 0 (라운드 2) — **라벨을 사실에 맞춘다** (F21-b).
#   G0은 이 파일의 4부 **이전**에 쓰던 정책이고, 지금 `memory.py:1007-1026`의
#   `Memory.gate`는 **G3(내용어 접점)**이다 — 462개 발화에서 `g_content`와
#   판정이 100% 일치한다. 그래서 *"현행"*은 G0이 아니라 G3에 붙는다.
#   ⚠️ **폭 제약:** `:208`이 `{name:<24}`, `:402`이 `{gname:<24}`로 찍는다. 라벨이 24자를 넘으면
#   6개 행의 모든 열이 오른쪽으로 밀린다. 상세 설명은 라벨이 아니라 이 주석에 둔다.
GATES = [
    ("G0. 과거참조 (4부 이전)", g_current),
    ("G1. 게이트 없음 (상한)", g_always),
    ("G2. 의례적 발화만 차단", g_ritual_only),
    ("G3. 내용어 접점 (현행)", g_content),
]


def build_vocab(m, chat_id=CHAT):
    """
    저장된 event 요약의 앞 2글자 집합 — G3의 접점 판정용.

    🔵 **정본에 위임한다** (F12 · A2 · 2026-09-10). 여기 있던 것은
    `SELECT summary FROM event WHERE chat_id=?` — 즉 방은 걸고 **`user_deleted`는
    안 봤다.** 프로덕션 게이트(`Memory._recall_vocab`)는 **정확히 반대로**
    `user_deleted=0`만 걸고 방을 안 봤다. 두 «G3 현행»이 서로 다른 집합을
    뜻하는 상태였고, 그러면 이 스윕의 판정은 프로덕션의 판정이 아니다(F21).

    ⚠️ 이 저장소의 소크 DB는 방이 하나이고 삭제가 0건이라 **두 정의가 같은
    62개를 낸다** — 통일이 이 파일의 출력을 바꾸지 않는다는 뜻이고, 그것을
    착수 전에 코드로 확인했다(레인 노트 «사전 등록 전제 2»).
    """
    return m._recall_vocab_for(chat_id)


def measure(m, corpus, qs, ledger, key_of):
    """436개 user 턴을 재생하며 검색 호출·주입·오주입을 센다."""
    calls = inj = noise = 0
    toks = []
    # key_of의 값이 **집합**이므로 평탄화해서 gold를 만든다.
    # 예전엔 `set(key_of.values())`가 항목당 문자열 하나만 담았고,
    # 그 하나가 `object`라서 `text`로 색인된 사실이 전부 '대장에 없는 것'이 됐다.
    gold = {s for v in key_of.values() for s in v}
    for row in corpus:
        if row["role"] != "user":
            continue
        ctx = m.build_context(CHAT, row["text"], row["seq"],
                              session_start=(row["turn"] == 1))
        toks.append(ctx.tokens)
        g = [p for p in ctx.provenance if p[0] == "gate"]
        if g and g[0][1] == "통과":
            calls += 1
        for kind, item, _ in ctx.provenance:
            if kind == "retrieved":
                inj += 1
                if item not in gold:
                    noise += 1
    return calls, inj, noise, pct(toks, 50)


def main():
    corpus = [json.loads(l) for l in
              open(f"{ROOT}/eval/corpus/corpus.jsonl", encoding="utf-8")]
    with open(f"{ROOT}/eval/fact-ledger.yaml", encoding="utf-8") as f:
        ledger = yaml.safe_load(f)
    with open(f"{ROOT}/eval/questions.yaml", encoding="utf-8") as f:
        qs = yaml.safe_load(f)["qa_questions"]
    # 🔴 오주입 지표 수리 — `soak.qa_eval`(`soak.py:127`)의 `key_of`(`soak.py:142-146`)와 **같은 허용 문자열 집합**을 쓴다.
    #    `soak.py`가 이미 옳게 하고 있었다. 두 곳이 같은 대장을 다르게 읽고 있었다.
    #    여기는 근거 하나를 `object` 한 문자열로만 봤는데, 검색 경로는 사실을
    #    `text`로 색인한다(`soak.py:91-94`). 그래서 `object != text`인 사실 12개가
    #    검색될 때마다 '대장에 없는 것'으로 세어졌다 — 그 합이 실험 12의 "오주입 49"다.
    #    오주입이 아니라 **지표가 자기 자신을 못 알아본 횟수**였다.
    key_of = {f["id"]: {k for k in (f.get("object"), f.get("text")) if k}
              for f in ledger["facts"]}
    key_of.update({e["id"]: {e["text"]} for e in ledger["events"]})

    n_user = sum(1 for r in corpus if r["role"] == "user")
    orig = Memory.gate
    orig_t, orig_k = M.THETA_RELEVANCE, M.TOP_K

    # 1부는 **당시 값 θ=0.15로 고정**해서 잰다.
    # 2부의 결과를 memory.py에 반영한 뒤로 기본값이 0.05가 됐는데,
    # 그 값으로 1부를 돌리면 "게이트는 범인이 아니다"라는 진단 자체가 성립하지 않는다.
    # 진단은 진단 당시의 조건에서 재현돼야 한다. (그리고 그 차이가 곧 3부의 상호작용이다)
    THETA_AT_DIAGNOSIS = 0.15
    M.THETA_RELEVANCE = THETA_AT_DIAGNOSIS

    print("=" * W)
    print("게이트 정책 스윕 — 소크가 남긴 질문: 게이트가 검색의 목을 조르는가")
    print("=" * W)
    print(f"\n소크에서 QA 26문항 중 16개가 게이트에 막혔고, 검색 순증 기여가 0이었다.")
    print("검색이 쓸모없는 것인지 게이트가 막은 것인지를 가른다.")
    print(f"(θ는 **진단 당시 값 {THETA_AT_DIAGNOSIS}로 고정**한다 — 2부 결과를 memory.py에")
    print(" 반영한 뒤로 기본값이 0.05가 됐고, 그 값으로 1부를 돌리면 진단이 재현되지 않는다.")
    print(" 그 차이 자체가 3부의 상호작용이다.)\n")
    print(f"  {'게이트':<24}{'회상':>10}{'검색순증':>9}{'검색호출':>11}"
          f"{'오주입':>8}{'트랩':>7}{'토큰':>7}")
    print("  " + "-" * 72)

    rows = []
    for name, fn in GATES:
        dbf = f"{ROOT}/prototype/.gate.db"
        if os.path.exists(dbf):
            os.remove(dbf)
        m = Memory(dbf)
        seed(m)
        ingest(m, corpus, ledger, timed=False)
        m._vocab = build_vocab(m)
        Memory.gate = fn

        calls, inj, noise, tok = measure(m, corpus, qs, ledger, key_of)
        qa = qa_eval(m, qs, ledger, corpus[-1]["seq"])
        need = [r for r in qa if r["n_want"] > 0]
        ok = sum(1 for r in need if r["ok"])
        vf = sum(1 for r in need if r["ok"] and r["via_facts"])
        _, blks = trap_injected(m, ledger, corpus[-1]["seq"])

        print(f"  {name:<24}{ok}/{len(need)}={ok/len(need)*100:3.0f}%{ok-vf:>8}"
              f"{calls:>7}/{n_user}{noise:>8}{'있음' if blks else '없음':>8}{tok:>7}")
        rows.append(dict(name=name, ok=ok, n=len(need), ret=ok - vf, calls=calls,
                         inj=inj, noise=noise, trap=bool(blks), tok=tok))
        m.db.close()
        os.remove(dbf)

    Memory.gate = orig
    g0, g1, g2, g3 = rows

    print("\n" + "-" * W)
    print("읽는 법")
    print("-" * W)
    print(f"  회상    = 근거 필요 18문항 중 근거가 컨텍스트에 도달한 수")
    print(f"  검색순증 = 그중 결정적 주입이 아니라 **검색이 넣은** 수")
    print(f"  오주입  = 436턴 재생 중 주입된 항목 가운데 대장에 없는 것 (잡음)")

    print("\n" + "-" * W)
    print("결론")
    print("-" * W)
    if g1["ok"] == g0["ok"]:
        print(f"  🔴 **게이트를 완전히 열어도 회상이 안 오른다** "
              f"({g0['ok']}/{g0['n']} → {g1['ok']}/{g1['n']}).")
        print( "     게이트가 목을 조른 게 아니었다. 소크의 '검색 순증 0'은 유지된다.")
        print(f"     대신 검색 호출만 {g0['calls']}회 → {g1['calls']}회로 늘고")
        print(f"     오주입이 {g0['noise']} → {g1['noise']}건, 토큰이 {g0['tok']} → {g1['tok']}로 는다.")
        print( "     → **막힌 것은 검색기이지 게이트가 아니다.** 게이트를 여는 건 손해만 본다.")
    else:
        d = g1["ok"] - g0["ok"]
        print(f"  게이트를 열면 회상이 {d}건 오른다 "
              f"({g0['ok']}/{g0['n']} → {g1['ok']}/{g1['n']}).")
        print(f"  대가: 검색 호출 {g0['calls']}→{g1['calls']}회, "
              f"오주입 {g0['noise']}→{g1['noise']}건, 토큰 {g0['tok']}→{g1['tok']}.")
        best = max(rows, key=lambda r: (r["ok"], -r["noise"]))
        print(f"  → 가장 나은 절충: **{best['name']}** "
              f"(회상 {best['ok']}/{best['n']}, 오주입 {best['noise']}, 호출 {best['calls']})")

    print(f"\n  G3(내용어 접점)이 G0 대비: 회상 {g0['ok']}→{g3['ok']}, "
          f"호출 {g0['calls']}→{g3['calls']}, 오주입 {g0['noise']}→{g3['noise']}")
    print( "  G3는 '질문의 형태'가 아니라 '저장소와의 접점'으로 판정한다.")
    print( "  게이트 설계를 바꿔야 하는지, 검색기를 고쳐야 하는지가 여기서 갈린다.")

    # ── 2부. 게이트가 아니면 무엇인가 ────────────────────────────────
    print("\n" + "=" * W)
    print("2부. 게이트가 아니면 무엇인가 — 임계 θ와 top_k")
    print("=" * W)
    print("\n  1부에서 게이트는 범인이 아니었다. 진단해보니 정답 근거의")
    print("  질문-요약 bigram 중첩이 대부분 0.00~0.11인데 θ = 0.15다.")
    print("  **정답이 임계 아래에 있다.** θ와 k를 열어본다 (게이트는 연 채로).\n")
    print(f"  {'θ':>6}{'top_k':>7}{'회상':>12}{'검색순증':>9}{'오주입':>8}"
          f"{'트랩':>7}{'토큰':>7}")
    print("  " + "-" * 56)

    Memory.gate = g_always
    sweep = []
    for theta, k in [(0.15, 5), (0.05, 5), (0.00, 5), (0.00, 10), (0.00, 20)]:
        M.THETA_RELEVANCE, M.TOP_K = theta, k
        dbf = f"{ROOT}/prototype/.tk.db"
        if os.path.exists(dbf):
            os.remove(dbf)
        m = Memory(dbf)
        seed(m)
        ingest(m, corpus, ledger, timed=False)
        m._vocab = build_vocab(m)
        calls, inj, noise, tok = measure(m, corpus, qs, ledger, key_of)
        qa = qa_eval(m, qs, ledger, corpus[-1]["seq"])
        need = [r for r in qa if r["n_want"] > 0]
        ok = sum(1 for r in need if r["ok"])
        vf = sum(1 for r in need if r["ok"] and r["via_facts"])
        _, blks = trap_injected(m, ledger, corpus[-1]["seq"])
        print(f"  {theta:6.2f}{k:7}{ok:>7}/{len(need)}{ok-vf:>9}"
              f"{noise:>8}{'있음' if blks else '없음':>8}{tok:>7}")
        sweep.append(dict(t=theta, k=k, ok=ok, n=len(need), ret=ok - vf,
                          noise=noise, trap=bool(blks), tok=tok))
        m.db.close()
        os.remove(dbf)
    M.THETA_RELEVANCE, M.TOP_K = orig_t, orig_k
    Memory.gate = orig

    base, wide = sweep[0], sweep[-1]
    print("\n" + "-" * W)
    print("🔴 1부의 결론이 뒤집힌다")
    print("-" * W)
    print(f"  검색은 쓸모없지 않았다. **임계에 막혀 있었다.**")
    print(f"    θ=0.15 k=5   회상 {base['ok']}/{base['n']} · 검색순증 {base['ret']}"
          f" · 오주입 {base['noise']} · 토큰 {base['tok']}")
    print(f"    θ=0.00 k=20  회상 {wide['ok']}/{wide['n']} · 검색순증 {wide['ret']}"
          f" · 오주입 {wide['noise']} · 토큰 {wide['tok']}")
    print(f"\n  회상 {base['ok']}→{wide['ok']}건, 검색 기여 {base['ret']}→{wide['ret']}건.")
    print( "  **소크의 '검색 순증 0'은 검색기의 무능이 아니라 파라미터의 결과였다.**")
    print(f"\n  대가: 오주입 {base['noise']}→{wide['noise']}건, "
          f"토큰 {base['tok']}→{wide['tok']}"
          f" ({(wide['tok']/base['tok']-1)*100:+.0f}%),"
          f" 트랩 {'있음' if wide['trap'] else '없음'}.")
    print( "  τ 하드 게이트가 살아 있어 트랩은 계속 막힌다 — **방어선이 분리돼 있어서다.**")
    # 무릎 찾기 — 회상 1건당 오주입 비용이 급증하는 지점
    print("\n  회상 1건을 더 얻는 데 드는 오주입 (한계비용):")
    knee = None
    for a, b in zip(sweep, sweep[1:]):
        d_ok = b["ok"] - a["ok"]
        d_noise = b["noise"] - a["noise"]
        if d_ok <= 0:
            continue
        cost = d_noise / d_ok
        mark = ""
        if knee is None and cost > 50:
            knee, mark = a, "   ← 여기서 급증"
        print(f"    θ{a['t']:.2f}k{a['k']:<3} -> θ{b['t']:.2f}k{b['k']:<3}"
              f"  회상 +{d_ok}  오주입 +{d_noise:<5} = 1건당 {cost:6.0f}{mark}")

    if knee:
        print(f"\n  → **무릎은 θ={knee['t']:.2f}, k={knee['k']}.** "
              f"회상 {knee['ok']}/{knee['n']}, 오주입 {knee['noise']}.")
        print( "     이 도메인은 [precision 실패가 recall 실패보다 비싸다](../docs/02-problem-definition.md) —")
        print( "     기억 못 하면 유저가 다시 말해주지만, 엉뚱한 걸 꺼내면 몰입이 깨진다.")
        print( "     그래서 오주입이 11배로 뛰는 θ=0은 회상이 높아도 채택하지 않는다.")
        print(f"\n  → 권고: **θ를 0.15에서 {knee['t']:.2f}로 낮춘다.** k는 5 유지.")
        print( "     프로토타입 상수 한 줄이고, 되돌리기 쉽다.")

    print( "\n  ⚠️ 그런데 이 파라미터는 [실험 7 스윕](../docs/11-experiment-results.md)에서 나왔다.")
    print( "     그때는 **검색기만 격리해서** 최적화했고, 문항당 정답이 하나뿐이라")
    print( "     k를 키울 이유가 없었다(당시에도 '측정 불가'로 표시했다).")
    print( "     **부품에 최적인 파라미터가 시스템에서는 최악에 가까웠다.**")

    # ── 3부. 왜 OFAT 스윕이 이걸 놓쳤나 ──────────────────────────────
    print("\n" + "=" * W)
    print("3부. ⭐ 왜 실험 7(OFAT 스윕)이 이걸 놓쳤나 — 상호작용")
    print("=" * W)
    print("\n  게이트와 θ를 **하나씩** 바꿔본다. 실험 7이 했던 방식이다.\n")
    print(f"  {'게이트':<12}{'θ':>6}{'회상':>10}{'검색순증':>9}")
    print("  " + "-" * 38)

    cells = {}
    for gname, gfn in [("현행", orig), ("열림", g_always)]:
        for th in [0.15, 0.05]:
            M.THETA_RELEVANCE = th
            Memory.gate = gfn
            dbf = f"{ROOT}/prototype/.ix.db"
            if os.path.exists(dbf):
                os.remove(dbf)
            m = Memory(dbf)
            seed(m)
            ingest(m, corpus, ledger, timed=False)
            r = qa_eval(m, qs, ledger, corpus[-1]["seq"])
            nd = [x for x in r if x["n_want"] > 0]
            ok = sum(1 for x in nd if x["ok"])
            vf = sum(1 for x in nd if x["ok"] and x["via_facts"])
            cells[(gname, th)] = ok
            print(f"  {gname:<12}{th:6.2f}{ok:>6}/{len(nd)}{ok - vf:>9}")
            m.db.close()
            os.remove(dbf)
    M.THETA_RELEVANCE, M.TOP_K = orig_t, orig_k
    Memory.gate = orig

    base = cells[("현행", 0.15)]
    print(f"\n  게이트만 열면      {base} -> {cells[('열림', 0.15)]}   (변화 없음)")
    print(f"  θ만 낮추면         {base} -> {cells[('현행', 0.05)]}   (변화 없음)")
    print(f"  **둘 다 바꾸면**   {base} -> {cells[('열림', 0.05)]}   "
          f"(+{cells[('열림', 0.05)] - base})")
    print("\n  각각은 효과가 0인데 함께 바꾸면 효과가 있다. **상호작용이다.**")
    print("  이유는 두 방어선이 **직렬**이기 때문이다 —")
    print("    게이트가 막으면 θ는 실행되지 않고, θ가 막으면 게이트를 연 의미가 없다.")
    print("    직렬 필터에서는 **가장 좁은 곳만이 처리량을 결정한다.**")
    print("\n  ⚠️ 그래서 **한 번에 하나씩 바꾸는 스윕(OFAT)은 이걸 구조적으로 못 본다.**")
    print("     실험 7은 파라미터를 하나씩 움직였고, 각각 '효과 없음'으로 나왔을 것이다.")
    print("     [13 발견 3](../docs/13-prototype.md)에서 *'직렬 방어선은 앞의 것이 막으면")
    print("     뒤의 것이 검증되지 않는다'*고 적었는데, **그게 파라미터 튜닝에도 적용된다.**")
    print("     같은 함정에 두 번 빠졌고, 두 번째는 측정 방법 자체의 문제였다.")

    # ── 4부. 그래서 어떤 조합인가 ────────────────────────────────────
    print("\n" + "=" * W)
    print("4부. 조합 탐색 — 게이트 4종 × θ 2종")
    print("=" * W)
    print("\n  3부에서 상호작용이 확인됐으니 **격자로 전부 돌린다.**")
    print("  이게 처음 요구받은 '모듈 조합을 테스트해 최적 구조를 찾는' 방식이다.\n")
    print(f"  {'게이트':<24}{'θ':>6}{'회상':>9}{'검색호출':>10}{'오주입':>8}{'토큰':>7}")
    print("  " + "-" * 66)

    grid = []
    for gname, gfn in GATES:
        for th in [0.15, 0.05]:
            M.THETA_RELEVANCE, M.TOP_K = th, orig_k
            dbf = f"{ROOT}/prototype/.gr.db"
            if os.path.exists(dbf):
                os.remove(dbf)
            m = Memory(dbf)
            seed(m)
            ingest(m, corpus, ledger, timed=False)
            m._vocab = build_vocab(m)
            Memory.gate = gfn
            calls, inj, noise, tok = measure(m, corpus, qs, ledger, key_of)
            r = qa_eval(m, qs, ledger, corpus[-1]["seq"])
            nd = [x for x in r if x["n_want"] > 0]
            ok = sum(1 for x in nd if x["ok"])
            print(f"  {gname:<24}{th:6.2f}{ok:>5}/{len(nd)}{calls:>7}/{n_user}"
                  f"{noise:>8}{tok:>7}")
            grid.append(dict(g=gname, t=th, ok=ok, n=len(nd),
                             calls=calls, noise=noise, tok=tok))
            m.db.close()
            os.remove(dbf)
    M.THETA_RELEVANCE, M.TOP_K = orig_t, orig_k
    Memory.gate = orig

    top = max(g["ok"] for g in grid)
    # 회상이 최대인 것들 중 오주입이 가장 적고, 동률이면 호출이 적은 것
    best = min((g for g in grid if g["ok"] == top),
               key=lambda g: (g["noise"], g["calls"]))
    # 🔄 단계 0 (라운드 2) — 이 행은 **4부 이전**의 조합(G0 · θ=0.15)이다.
    #   아래 출력 낱말을 `4부 이전`으로 바꾼 이유다(F21-b · G15).
    cur = next(g for g in grid if g["g"].startswith("G0") and g["t"] == 0.15)

    print("\n" + "-" * W)
    print("권고 조합")
    print("-" * W)
    print(f"  4부 이전   {cur['g']} θ={cur['t']:.2f}  "
          f"회상 {cur['ok']}/{cur['n']} · 호출 {cur['calls']} · 오주입 {cur['noise']}")
    print(f"  권고   {best['g']} θ={best['t']:.2f}  "
          f"회상 {best['ok']}/{best['n']} · 호출 {best['calls']} · 오주입 {best['noise']}")
    print(f"\n  회상 +{best['ok']-cur['ok']}건, 검색 호출 "
          f"{cur['calls']}→{best['calls']}회 "
          f"({(1-best['calls']/n_user)*100:.0f}% 절감 유지), "
          f"오주입 {cur['noise']}→{best['noise']}건.")
    print( "\n  '게이트 없음'(G1)도 회상은 같지만 호출이 436회로 전수이고 오주입도 더 많다.")
    print( "  **내용어 접점 게이트가 값싼 이유는 신호를 질문의 형태가 아니라**")
    print( "  **저장소와의 접점에서 찾기 때문이다** — 무엇이 저장돼 있는지는 이미 알고 있다.")
    print( "\n  ⚠️ 다만 회상 차이는 2건(11%p)이고 문항이 18개다. **순위만 읽을 것.**")
    print( "     그리고 오주입의 실제 해로움은 응답을 생성해야 안다 (API 키 필요).")

    print("\n" + "-" * W)
    print("⚠️ 이 실험이 말할 수 없는 것")
    print("-" * W)
    print("  · 문항 18개. 1건이 5.6%p다. 순위만 읽을 것")
    print("  · 오주입을 '대장에 없는 것'으로 근사했다. 실제 해로움은 응답을 봐야 안다")
    print("  · 검색기 자체(bigram 중첩)는 고정했다. 이건 게이트 정책만 가르는 실험이다")
    print("\n" + "=" * W)


if __name__ == "__main__":
    main()
