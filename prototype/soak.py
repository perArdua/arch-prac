# -*- coding: utf-8 -*-
"""
soak.py — 실제 구현을 실제 코퍼스에 통과시킨다.

여태까지 두 세계가 분리돼 있었다.
  experiments/*    : 순수 시뮬레이션. SQLite도, 실제 read path도 안 탄다
  prototype/*demo  : 실제 구현이지만 손으로 만든 3~5개 항목짜리 장난감

**둘을 붙여본 적이 없다.** 그래서 붙인다.
  eval/corpus/corpus.jsonl(720턴) + eval/fact-ledger.yaml -> prototype/memory.py

재는 것:
  1. 쓰기/읽기 경로 실측 지연 (시뮬레이션이 아닌 벽시계)
  2. 저장 증가율 (docs/06 §0의 "저장은 거의 공짜" 주장 검증)
  3. 컨텍스트 토큰 실측 (docs/05 예산 검증)
  4. 게이트 통과율 (ADR-006이 아낀다고 주장한 양)
  5. QA 26문항을 실제 read path로 통과 — 시뮬레이션 recall과 비교
"""
import sys, json, time, os, re
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import yaml
import memory as M
from memory import Memory

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHAT = "chat-soak"
W = 78


def seed(m):
    db = m.db
    db.execute("INSERT INTO character_version VALUES (?,?,?,?,?)", (
        "seojun", 1,
        "강서준 27. 대학 2년 선배. 무뚝뚝하고 툴툴대지만 챙기는 건 다 챙긴다.",
        "반말 / 1인칭 '나' / 어미 ~냐 ~다 ~지 / 존댓말·이모지 금지",
        "유저의 가족사를 먼저 캐묻지 않는다"))
    db.execute("INSERT INTO chat VALUES (?,?,?,?)", (CHAT, "jiwoo", "seojun", 1))
    db.execute("INSERT INTO relationship VALUES (?,?,?,?,?,?,?,?)",
               (CHAT, "연인", None, 84, "안도", "지우", 0, 0))
    db.execute("INSERT INTO scene VALUES (?,?,?,?,?)",
               (CHAT, "카톡", "지우,서준", "평범한 저녁 대화", 0))
    db.commit()


def ingest(m, corpus, ledger, timed=True):
    """
    쓰기 경로 — 720턴 + 대장 항목.

    timed=False면 커밋을 묶는다. §1에서 잰 4,000배가 여기 그대로 적용된다 —
    이 하니스가 DB를 13개 만드는데 턴마다 fsync하면 그것만 48초다.
    **실측 결과를 실측 도구에 적용한 것.**
    """
    wt = []
    if not timed:
        m.db.executemany(
            "INSERT OR REPLACE INTO turn VALUES (?,?,?,?,?,?,'pending')",
            [(CHAT, r["seq"], r["role"], r["text"], time.time(), 0) for r in corpus])
        m.db.commit()
    for row in (corpus if timed else []):
        t0 = time.perf_counter()
        m.add_turn(CHAT, row["seq"], row["role"], row["text"])
        wt.append((time.perf_counter() - t0) * 1000)

    seq_of = {(r["session"], r["turn"]): r["seq"] for r in corpus}

    # 대장 events -> event 테이블 (추출기가 이상적으로 동작했다고 가정)
    for e in ledger.get("events", []):
        at = e.get("at", {})
        s = seq_of.get((at.get("session"), at.get("turn")), 0)
        w = e.get("emotional_weight", 0.5)
        m.db.execute(
            "INSERT INTO event (chat_id, summary, occurred_at, emotional_weight,"
            " importance, narrative_role, source_from_seq) VALUES (?,?,?,?,?,?,?)",
            (CHAT, e["text"], s, w, e.get("importance", w),
             e.get("narrative_role"), s))

    # 대장 facts -> upsert_fact + event 색인
    fact_actions = {}
    for f in ledger.get("facts", []):
        at = f.get("at", {})
        s = seq_of.get((at.get("session"), at.get("turn")), 0)
        act, _ = m.upsert_fact(
            CHAT, "지우", f.get("predicate", "일상_사소"),
            f.get("object", f["text"]), realm=f.get("realm", "real"),
            seq=s, importance=f.get("importance", 0.5))
        fact_actions[f["id"]] = act
        # retrieve()는 event 테이블만 본다. 사실도 검색되려면 여기 들어와야 한다.
        cur = m.db.execute(
            "INSERT INTO event (chat_id, summary, occurred_at, emotional_weight,"
            " importance, narrative_role, source_from_seq) VALUES (?,?,?,?,?,?,?)",
            (CHAT, f["text"], s, 0.0, f.get("importance", 0.5), "사실", s))
        # ⭐ 색인 복사본을 **파생물로 등록**한다. 이걸 안 하면 사실이 무효화돼도
        #    색인이 남아 계속 검색된다 — event_metrics.py에서 23턴 누수로 잡혔다.
        fid = m.db.execute(
            "SELECT fact_id FROM fact WHERE chat_id=? AND predicate=? AND object=?",
            (CHAT, f.get("predicate", "일상_사소"),
             f.get("object", f["text"]))).fetchone()
        if fid:
            m.record_derivation(CHAT, "event", str(cur.lastrowid),
                                [("fact", fid["fact_id"])])
    m.db.commit()
    return wt, fact_actions


def replay(m, corpus):
    """읽기 경로 — 매 턴 컨텍스트를 실제로 조립한다."""
    rt, toks, gated, hits = [], [], 0, 0
    for row in corpus:
        if row["role"] != "user":
            continue
        t0 = time.perf_counter()
        ctx = m.build_context(CHAT, row["text"], row["seq"],
                              session_start=(row["turn"] == 1))
        rt.append((time.perf_counter() - t0) * 1000)
        toks.append(ctx.tokens)
        g = [p for p in ctx.provenance if p[0] == "gate"]
        if g and g[0][1] == "통과":
            gated += 1
            if any(p[0] == "retrieved" for p in ctx.provenance):
                hits += 1
    return rt, toks, gated, hits


def qa_eval(m, qs, ledger, last_seq):
    """
    QA 문항을 실제 read path로 통과시킨다.

    채점 기준은 "답을 담은 문자열이 컨텍스트에 도달했는가"다.

    ⚠️ 여기서 채점 버그를 한 번 만들었다. 처음엔 사실의 정답을 `object`
    하나로만 봤는데(F021 -> "스타트업 프로덕트 매니저"), **검색 경로는
    사실을 `text`로 색인한다**("지우는 스타트업으로 이직함").
    즉 검색이 정답 항목을 찾아와도 문자열이 안 맞아 오답 처리됐다.
    → "검색 순증 0"이라는 결론이 **채점 방식의 산물**이었다.

    그래서 근거 하나당 **허용 문자열 집합**을 만들고 하나라도 도달하면 인정한다.
    저장 형식이 경로마다 다른 것은 검색기의 잘못이 아니다.
    """
    key_of = {}
    for f in ledger.get("facts", []):
        key_of[f["id"]] = {k for k in (f.get("object"), f.get("text")) if k}
    for e in ledger.get("events", []):
        key_of[e["id"]] = {e["text"]}
    rows = []
    for q in qs:
        ctx = m.build_context(CHAT, q["ask"], last_seq)
        rendered = ctx.render()
        want = [key_of[e] for e in q.get("evidence", []) if e in key_of]
        found = [ks for ks in want if any(k in rendered for k in ks)]
        g = [p for p in ctx.provenance if p[0] == "gate"]
        via_facts = any(b.name == "알고 있는 것"
                        and any(k in b.text for ks in want for k in ks)
                        for b in ctx.blocks)
        rows.append({
            "id": q["id"], "type": q.get("type", "-"),
            "gate": g[0][1] if g else "-",
            "n_want": len(want), "n_found": len(found),
            "ok": bool(want) and len(found) == len(want),
            "via_facts": via_facts,
            "tokens": ctx.tokens,
        })
    return rows


def build(corpus, ledger, tag):
    """설정마다 DB를 새로 만든다 — build_context에 부작용이 있어 공유하면 오염된다."""
    dbf = f"{ROOT}/prototype/.soak-{tag}.db"
    if os.path.exists(dbf):
        os.remove(dbf)
    m = Memory(dbf)
    seed(m)
    wt, fa = ingest(m, corpus, ledger, timed=False)
    return m, dbf, wt, fa


def trap_injected(m, ledger, last_seq):
    """평범한 발화에 트랩이 딸려오는가 (유사 서비스 A '빵 유언' 재현 검사)."""
    trap = next((f for f in ledger["facts"] if "TRAP" in f["id"]), None)
    if not trap:
        return None, None
    key = trap.get("object") or trap["text"]
    ctx = m.build_context(CHAT, "오늘 좀 피곤하네", last_seq)
    return trap, [b.name for b in ctx.blocks if key in b.text]


def commit_bench(corpus):
    """같은 INSERT를 커밋만 묶어서 재본다 — 쓰기 지연이 일인지 fsync인지 가른다."""
    import sqlite3
    from memory import SCHEMA
    p = f"{ROOT}/prototype/.bench.db"
    if os.path.exists(p):
        os.remove(p)
    db = sqlite3.connect(p)
    db.executescript(SCHEMA)
    ts = []
    for r in corpus:
        t0 = time.perf_counter()
        db.execute("INSERT OR REPLACE INTO turn VALUES (?,?,?,?,?,?,'pending')",
                   (CHAT, r["seq"], r["role"], r["text"], time.time(), 0))
        ts.append((time.perf_counter() - t0) * 1000)
    db.commit()
    db.close()
    os.remove(p)
    return pct(ts, 50), pct(ts, 95)


def pct(v, p):
    if not v:
        return 0.0
    v = sorted(v)
    return v[min(len(v) - 1, int(len(v) * p / 100))]


def main():
    corpus = [json.loads(l) for l in
              open(f"{ROOT}/eval/corpus/corpus.jsonl", encoding="utf-8")]
    with open(f"{ROOT}/eval/fact-ledger.yaml", encoding="utf-8") as f:
        ledger = yaml.safe_load(f)
    with open(f"{ROOT}/eval/questions.yaml", encoding="utf-8") as f:
        qs = yaml.safe_load(f)["qa_questions"]

    dbf = f"{ROOT}/prototype/.soak.db"
    if os.path.exists(dbf):
        os.remove(dbf)
    m = Memory(dbf)
    seed(m)

    wt, fact_actions = ingest(m, corpus, ledger)
    size = os.path.getsize(dbf)
    rt, toks, gated, hits = replay(m, corpus)
    n_user = sum(1 for r in corpus if r["role"] == "user")
    qa = qa_eval(m, qs, ledger, corpus[-1]["seq"])

    n_ev = m.db.execute("SELECT COUNT(*) FROM event").fetchone()[0]
    n_fa = m.db.execute("SELECT COUNT(*) FROM fact").fetchone()[0]

    print("=" * W)
    print("소크 테스트 — 실제 구현 x 실제 코퍼스 (720턴)")
    print("=" * W)
    print(f"\n턴 {len(corpus)}개 (user {n_user}) · event {n_ev}개 · fact {n_fa}개")

    print("\n" + "-" * W)
    print("1. 실측 지연 (SQLite, 단일 프로세스, 벽시계)")
    print("-" * W)
    print(f"  쓰기 add_turn       p50 {pct(wt,50):7.3f}ms   p95 {pct(wt,95):7.3f}ms")
    print(f"  읽기 build_context  p50 {pct(rt,50):7.3f}ms   p95 {pct(rt,95):7.3f}ms")
    print(f"\n  docs/05의 TTFT 예산은 200~400ms. 메모리 조립은 p95 기준 그 중")
    print(f"  {pct(rt,95)/200*100:.1f}%를 쓴다. 병목은 메모리가 아니라 LLM 호출이다.")

    # 쓰기가 읽기보다 6배 느리다. INSERT 한 줄이 SELECT 여러 번보다 느릴 리 없다.
    # -> 일을 재는 게 아니라 fsync를 재고 있다. 분리해서 확인한다.
    b50, b95 = commit_bench(corpus)
    print(f"\n  그런데 쓰기가 읽기보다 {pct(wt,50)/pct(rt,50):.0f}배 느리다.")
    print(f"  INSERT 한 줄이 SELECT 여러 번보다 느릴 리 없다. commit을 분리해 재보면:")
    print(f"    턴마다 commit   p50 {pct(wt,50):.3f}ms")
    print(f"    묶어서 commit   p50 {b50:.3f}ms   ({pct(wt,50)/max(b50,1e-6):.0f}배 차이)")
    print( "  쓰기 지연은 전부 fsync다. 디스크에 도달했음을 보장하는 비용이지")
    print( "  일의 비용이 아니다. -> 설계 함의: **무엇이 내구성을 필요로 하는가.**")
    print( "  L0 원본 턴은 유실되면 유저 발화가 사라지므로 즉시 커밋해야 한다.")
    print( "  반면 사실·사건·요약은 **L0에서 재생성 가능하다**(docs/06 FP-7).")
    print( "  파생 계층까지 턴마다 fsync할 이유가 없다 — 묶어서 커밋한다.")

    print("\n" + "-" * W)
    print("2. 저장 비용 (docs/06 §0 '저장은 거의 공짜' 검증)")
    print("-" * W)
    print(f"  DB {size/1024:.1f}KB / {len(corpus)}턴 = 턴당 {size/len(corpus):.0f}B")
    print(f"  월 300턴 유저 -> {size/len(corpus)*300/1024:.0f}KB/월")

    print("\n" + "-" * W)
    print("3. 컨텍스트 토큰 (docs/05 예산)")
    print("-" * W)
    print(f"  p50 {pct(toks,50)}tok · p95 {pct(toks,95)}tok · max {max(toks)}tok")

    print("\n" + "-" * W)
    print("4. 게이트 (ADR-006이 아낀다고 주장한 양)")
    print("-" * W)
    print(f"  통과 {gated}/{n_user} = {gated/n_user*100:.1f}%   그중 실제 주입 {hits}건")
    print(f"  -> 검색 호출의 {100-gated/n_user*100:.1f}%를 안 한다.")

    print("\n" + "-" * W)
    print("5. 🔴 QA를 실제 read path로 — 설정 3가지를 자동으로 비교")
    print("-" * W)
    print("  각 설정마다 DB를 새로 만들고 720턴을 다시 넣는다.")
    print("  근거가 필요한 문항만 센다 (abstention·coverage 8개 제외).\n")

    ALL_PRED = {f.get("predicate") for f in ledger["facts"]} | M.Memory.PREDICATE_STANDING
    # A~C는 **발견 당시 파라미터(θ=0.15, 과거참조 게이트)로 고정**한다.
    # 이후 [실험 12](gate_sweep.py)가 θ와 게이트를 바꿔서 기본값이 달라졌는데,
    # 새 기본값으로 A~C를 돌리면 **발견 자체가 재현되지 않는다.**
    # D는 그 이후 상태를 같은 잣대로 보여준다.
    configs = [
        ("A. 검색만 (원래 구현)", False, set(), 0.15, True),
        ("B. + [알고 있는 것] 전량", True, ALL_PRED, 0.15, True),
        ("C. + 상시성(standing) 필터", True, M.Memory.PREDICATE_STANDING, 0.15, True),
        ("D. + 실험 12 (θ·게이트)", True, M.Memory.PREDICATE_STANDING, None, False),
    ]
    saved = M.Memory.PREDICATE_STANDING
    saved_theta = M.THETA_RELEVANCE
    saved_gate = Memory.gate

    def _legacy_gate(self, u):
        """발견 당시의 게이트 — 과거 참조 표현만 본다 (내용어 접점 없음)."""
        if re.search(r"(기억|그때|저번|예전|아까|전에|했잖아|말했|뭐였|언제)", u):
            return True, "과거 참조 표현"
        if len(u) < 8:
            return False, "너무 짧음"
        if re.match(r"^(응|ㅇㅇ|ㅋ+|어|그래|넵|왜|뭐)$", u.strip()):
            return False, "의례적 발화"
        return False, "과거 참조 신호 없음"
    stat = {}
    print(f"  {'설정':<26} {'근거도달':>10} {'검색기여':>8} {'트랩':>6} {'p50토큰':>8}")
    print("  " + "-" * 62)
    detail = None
    for name, inject, preds, theta, legacy in configs:
        M.INJECT_KNOWN_FACTS = inject
        M.Memory.PREDICATE_STANDING = preds
        M.THETA_RELEVANCE = theta if theta is not None else saved_theta
        Memory.gate = _legacy_gate if legacy else saved_gate
        mc, dbc, _, _ = build(corpus, ledger, name[0])
        rows = qa_eval(mc, qs, ledger, corpus[-1]["seq"])
        nd = [r for r in rows if r["n_want"] > 0]
        o = sum(1 for r in nd if r["ok"])
        vf = sum(1 for r in nd if r["ok"] and r["via_facts"])
        _, blks = trap_injected(mc, ledger, corpus[-1]["seq"])
        tk = pct([r["tokens"] for r in rows], 50)
        print(f"  {name:<26} {o}/{len(nd)} = {o/len(nd)*100:3.0f}% "
              f"{o-vf:>7} {'주입됨' if blks else '없음':>7} {tk:>8}")
        stat[name[0]] = dict(ok=o, n=len(nd), ret=o - vf, trap=bool(blks), tok=tk)
        if name.startswith("C"):
            detail = rows
        mc.db.close()
        os.remove(dbc)
    M.INJECT_KNOWN_FACTS = True
    M.Memory.PREDICATE_STANDING = saved
    M.THETA_RELEVANCE = saved_theta
    Memory.gate = saved_gate

    A, B, C, D = stat["A"], stat["B"], stat["C"], stat["D"]
    r = lambda d: d["ok"] / d["n"] * 100
    print("\n  읽는 법 — 각 줄이 다른 것을 말한다.")
    print(f"  A->B  docs/15에서 [알고 있는 것] / [꺼낼 만한 것]으로 나눠 설계해놓고,")
    print(f"        build_context는 [꺼낼 만한 것]만 구현했다. facts_at()은")
    print(f"        fact_demo에서만 불렸고 읽기 경로에 연결된 적이 없다.")
    print(f"        10줄 추가로 회상 {r(A):.0f}% -> {r(B):.0f}%. "
          f"토큰은 {A['tok']} -> {B['tok']}.")
    print(f"  B     그런데 트랩(크로와상 importance 0.05)이 평범한 턴에도 들어간다.")
    print(f"        검색 경로에는 하드 게이트 τ가 있는데 **결정적 주입 경로에는")
    print(f"        채택 기준이 아예 없었다.** 게이트를 우회하는 길을 뚫은 것이다.")
    print(f"  B->C  importance로 거르면 될 것 같지만 틀렸다. 필요한 축은")
    print(f"        '중요한가'가 아니라 '항상 알고 있어야 하는 종류인가'다.")
    print(f"        술어에 다섯 번째 속성 standing을 추가했다. 트랩이 빠지고")
    print(f"        토큰도 {B['tok']} -> {C['tok']}. 회상 {B['ok']-C['ok']}건 손실은")
    print(f"        일상_사소 술어 문항이고, 그건 검색이 맡아야 할 몫이다.")
    print(f"  C->D  [실험 12](gate_sweep.py)가 θ(0.15->0.05)와 게이트(과거참조->내용어"
          f" 접점)를")
    print(f"        **함께** 바꿨다. 회상 {r(C):.0f}% -> {r(D):.0f}%,  검색 기여 {C['ret']} -> {D['ret']}.")
    print( "        하나씩 바꾸면 둘 다 효과가 0이다 — 두 방어선이 직렬이라서다.")
    print(f"\n  ⚠️ 검색 기여: A에서 {A['ret']}건 -> B·C에서 {B['ret']}·{C['ret']}건.")
    print( "     검색이 찾아내던 것을 결정적 주입이 전부 포함해버렸다.")
    print( "     아키텍처 복잡도의 대부분(BM25/dense/hybrid·importance 가중·θ·top-k)이")
    print(f"     C 구성에서 그 경로의 **순증 기여는 {C['ret']}건**이었다.")
    print(f"     다만 D에서 {D['ret']}건으로 돌아온다 — **검색이 무능했던 게 아니라**")
    print( "     **임계값이 정답을 깔고 앉아 있었다**(실험 12). 순증 0은 파라미터의 결과였다.")
    print( "     시뮬레이션은 검색기를 격리해서 쟀기 때문에 이걸 볼 수 없었다.\n")

    for r in detail:
        mark = ("FACT" if r["ok"] and r["via_facts"] else
                "OK  " if r["ok"] else
                "GATE" if r["gate"] != "통과" else "MISS")
        print(f"   [{mark}] {r['id']} {r['type']:<18} gate={r['gate']:<4}"
              f" 근거 {r['n_found']}/{r['n_want']}  {r['tokens']}tok")
    print("\n   FACT=결정적 주입 / OK=검색으로 주입")
    print("   MISS=게이트 통과했으나 검색 실패 / GATE=게이트가 차단")
    print("\n  남은 실패는 대부분 게이트다. multi_session·temporal·knowledge_update는")
    print("  '과거 참조 표현'이 없는 자연스러운 질문이라 게이트가 막는다.")
    print("  게이트를 열면 검색이 살아나는지는 experiments/param_sweep.py의")
    print("  τ·θ 스윕과 함께 봐야 한다 — 이 소크는 게이트가 지금 병목임을 보인다.")

    print("\n" + "-" * W)

    print("6. upsert_fact 실제 동작 분포")
    print("-" * W)
    for act, n in Counter(fact_actions.values()).most_common():
        print(f"  {act:<12} {n}")
    sup = m.db.execute(
        "SELECT COUNT(*) FROM fact WHERE superseded_by IS NOT NULL").fetchone()[0]
    print(f"  무효화된 사실 {sup}건 (대장이 의도한 것은 F002->F021 1건)")

    m.db.close()
    os.remove(dbf)
    print("\n" + "=" * W)


if __name__ == "__main__":
    main()
