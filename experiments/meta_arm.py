# -*- coding: utf-8 -*-
"""
meta_arm.py — **동기 층(`apply_meta`)이 턴마다 도는 팔을 하나 세우고, 무엇이 채워지는가를 잰다.**

## 🔴 모의 `<meta>` — 자가저작 선언

이 파일의 `<meta>`는 **LLM이 만든 것이 아니다.** 아래 네 규칙(`MOCK_RULES`)이 대장·코퍼스
에서 결정적으로 만든 **모의 출력**이고, 규칙을 쓴 것은 이 레인이다. 그래서 이 파일이
찍는 **건수는 전부 모의 규칙의 함수**다 — 부채 행이 4인 것은 대장에 부채가 4개라서이고,
`surfaced_count`의 합은 «주입된 기억을 전부 썼다고 선언한다»는 상한 규칙의 결과다.

**이 파일이 재는 것은 «배관이 도는가»와 «돌 때 무엇이 비어 있는가»뿐이다.** 추출 품질
(모델이 `<meta>`를 얼마나 잘 쓰는가)에 대해서는 아무 수도 만들지 않는다. 출력 머리와
요약 줄에 이 선언을 박는다 — 표만 떼어 옮겨도 선언이 따라가게.

## 왜 이 팔이 필요한가

`apply_meta`(ADR-004 동기 층)를 턴 단위로 부르는 경로가 이 저장소에 **없었다.**
`soak`·`precision`·격자는 안 부른다. 실험 20(`fsm_probe.py`)이 부르지만 **합성
`state_delta` 5개와 공격 21개**만 넣는다 — 그래서 `used_memories`(→ `surfaced_count`)와
`new_debt`(→ `debt`)는 **어떤 계측 경로에서도 한 번도 안 돌았고**, 실험 10B의
«페널티 무릎 0.1»은 시뮬 값으로만 남아 있었다.

## 🔴 팔 분리 — 기본 경로는 한 줄도 안 움직인다 (사전 등록)

이 파일은 `soak.py`·`memory.py`를 **고치지 않고 import해서 부른다.** 팔은 셋이고 서로
**한 요인씩만** 다르다:

  A0   `soak.seed` 그대로(연인/84) · `<meta>` 없음  — 🔴 **앵커: `soak.replay`와 수가 같아야 한다**
  A0′  대장 궤적 출발점(아는사이/20) · `<meta>` 없음 — 대조군 (A0과 관계 행 하나만 다름)
  A1   A0′ + 모의 `<meta>`를 character 턴마다 `apply_meta`로 — 이 팔

A0이 `soak.replay`를 재현하지 못하면 **종료 1** — 이 루프가 기본 경로와 같은 길이라는
근거가 사라지기 때문이다. A1 대 A0′의 차이는 `apply_meta` **하나**에 귀속된다.

## 🔄 wave4 — 넷째 팔 A2 (부채 절만 읽는다)

  A2   A1 + 세션이 끝날 때마다 `digest_session` 한 행(내용은 대역) — 요약 층이 남기는 경계

부채 백오프가 이제 **세션 경계**로 세고, 경계를 세는 유일한 자리가 `digest_session`의
행 수다(`session_boundaries_since`). 소크는 요약 층을 안 돌리므로 A1에서 그 수는 늘 0이다 —
그래서 A1은 «요약 층이 없을 때»를, A2는 «경계 행이 있을 때(설계 경로)»를 보인다. A2 대
A1의 차이는 경계 행 **하나**에 귀속된다. 대역 행은 요약 블록으로 주입되므로 A2의 토큰은
다른 팔과 대지 않는다.

재현: `PYTHONIOENCODING=utf-8 python -B experiments/meta_arm.py` (ollama 0회 · 임시 DB는 `%TEMP%`)
"""
import json
import os
import shutil
import sys
import tempfile
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "prototype"))

import yaml                                                # noqa: E402
import memory                                              # noqa: E402
import soak                                                # noqa: E402
from memory import Memory                                  # noqa: E402

W = 78
CHAT = soak.CHAT

# ── 🔴 모의 규칙 (자가저작 · 값 보기 전에 고정) ─────────────────────────
MOCK_RULES = (
    ("used_memories", "직전 user 턴 컨텍스트에 주입된 검색 기억(`event:`)과 부채(`debt:`)를"
                      " **전부** 썼다고 선언 — 상한 규칙"),
    ("new_debt",      "대장 `debts`의 setup (세션, 턴)인 character 턴에서 대장 내용·트리거"
                      " 그대로 — 4건"),
    ("state_delta",   "대장 `relationship_arc` 전이 세션의 첫 character 턴에서 그 델타 +"
                      " `narrative_event=True` — 실험 20과 같은 합성 · 5건"),
    ("scene_delta",   "세션마다 첫 character 턴에서 `situation` = 그 세션 첫 user 발화 **원문**"
                      " — 가드가 실제 길이 분포를 보게 · 24건"),
)
MOCK_BANNER = ("🔴 모의 `<meta>` — 자가저작. 아래 건수는 모의 규칙의 함수이고, 재는 것은"
               " «배관이 도는가»이지 «추출 품질»이 아니다.")

# ── 🔴 wave4 사전 등록 (값 보기 전 · 코드 변경 전에 `.omc/notepads/wave4`에 먼저 적었다) ──
PREREG_W4 = (
    "T1·T2·T3은 기본 경로의 기록값을 한 칸도 안 움직인다.",
    "관측: run_all 전후 RESULTS.txt를 R1~R5로 가리고 줄 대조 — 부채를 스스로 심는 두 자리"
    "(이 파일 · digest_budget.py 5절)와 러너 머리·인용 감사·지연 표(실험 6·21)를 뺀 나머지의"
    " 차이 줄이 0이면 참, 1줄이라도 있으면 거짓(그 줄이 결과다).",
    "전제(이 파일이 A0에서 센다): 기본 경로 debt 0행 · 기본 경로 called_as = 시드 값 ·"
    " 씬 후보 값 40자 초과 0 (절 5-b).",
)

# 세션 첫 user 발화 — 모의 규칙이 `situation`에 넣는 값. 두 코퍼스 모두에서 센다(T3).
CORPORA = (("eval", os.path.join(ROOT, "eval", "corpus", "corpus.jsonl")),
           ("eval2", os.path.join(ROOT, "eval2", "corpus", "corpus.jsonl")))


def load():
    corpus = [json.loads(l) for l in
              open(os.path.join(ROOT, "eval", "corpus", "corpus.jsonl"),
                   encoding="utf-8")]
    with open(os.path.join(ROOT, "eval", "fact-ledger.yaml"), encoding="utf-8") as f:
        ledger = yaml.safe_load(f)
    return corpus, ledger


def make_db(tmp, tag, corpus, ledger, start=None):
    """`soak.build`와 같은 절차(`seed` + `ingest(timed=False)`) — DB만 `%TEMP%`에 둔다."""
    m = Memory(os.path.join(tmp, f"meta-{tag}.db"))
    soak.seed(m)
    soak.ingest(m, corpus, ledger, timed=False)
    if start is not None:
        m.db.execute("UPDATE relationship SET stage=?, affinity=? WHERE chat_id=?",
                     (start[0], start[1], CHAT))
        m.db.commit()
    return m


class Mock:
    """모의 `<meta>` 공급자. 규칙은 `MOCK_RULES`의 네 줄이 전부다."""

    def __init__(self, corpus, ledger):
        first_char, first_user = {}, {}
        for r in corpus:
            if r["role"] == "user":
                first_user.setdefault(r["session"], r["text"])
            else:
                first_char.setdefault(r["session"], r["seq"])
        self.scene_at = {first_char[s]: first_user[s] for s in first_char
                         if s in first_user}
        arc = ledger["relationship_arc"]
        self.state_at = {first_char[b["at"]]: {"stage": b["stage"],
                                               "affinity": b["affinity"]}
                         for b in arc[1:]}
        seq_of = {(r["session"], r["turn"]): r["seq"] for r in corpus}
        self.debt_at = {}
        for d in ledger.get("debts", []):
            s = seq_of[(d["setup"]["session"], d["setup"]["turn"])]
            trig = d.get("trigger") or {}
            spec = trig.get("spec", trig.get("after"))
            self.debt_at[s] = {"content": d["content"],
                               "trigger_kind": trig.get("kind", "session_start"),
                               "trigger_spec": None if spec is None else str(spec),
                               "stake": d.get("emotional_stake", 0.5)}

    def meta_for(self, seq, last_used):
        meta = {}
        if last_used:
            meta["used_memories"] = list(last_used)
        if seq in self.debt_at:
            meta["new_debt"] = dict(self.debt_at[seq])
        if seq in self.state_at:
            meta["state_delta"] = dict(self.state_at[seq])
            meta["narrative_event"] = True
        if seq in self.scene_at:
            meta["scene_delta"] = {"situation": self.scene_at[seq]}
        return meta


def run_arm(m, corpus, mock=None, boundaries=False):
    """
    `soak.replay`와 **같은 순서·같은 인자**로 user 턴마다 `build_context`를 부른다.
    `mock`이 있으면 character 턴마다 `apply_meta`를 더 부른다 — 차이는 그것뿐이다.
    `boundaries`면 새 세션의 첫 행 **앞에서** 끝난 세션의 `digest_session` 행을 쓴다(A2).
    """
    ev_id = {r["summary"]: r["event_id"] for r in m.db.execute(
        "SELECT event_id, summary FROM event WHERE chat_id=?", (CHAT,))}
    toks, gated, hits, per_turn, emitted = [], 0, 0, [], Counter()
    open_max, last_used, degraded = 0, [], Counter()
    cur = None                                    # (세션, 첫 seq, 끝 seq)
    for row in corpus:
        if boundaries:
            if cur and cur[0] != row["session"]:
                m.put_session_digest(CHAT, cur[0], "(경계 대역 — 요약 아님)",
                                     covers_from_seq=cur[1], covers_to_seq=cur[2])
                cur = None
            cur = (row["session"], cur[1] if cur else row["seq"], row["seq"])
        if row["role"] != "user":
            if mock is not None:
                meta = mock.meta_for(row["seq"], last_used)
                for k in ("new_debt", "state_delta", "scene_delta"):
                    emitted[k] += k in meta
                for i in meta.get("used_memories", []):
                    emitted["used_" + i.partition(":")[0]] += 1
                # ⚠️ 선언은 **다음 character 턴에만** 붙는다 — user 턴이 연달아 오면
                #    앞 턴의 주입분은 응답을 못 받았으므로 덮인다(모의 규칙 그대로).
                last_used = []
                if meta:
                    m.apply_meta(CHAT, row["seq"], meta)
                open_max = max(open_max, m.db.execute(
                    "SELECT COUNT(*) FROM debt WHERE chat_id=? AND status='open'",
                    (CHAT,)).fetchone()[0])
            continue
        ctx = m.build_context(CHAT, row["text"], row["seq"],
                              session_start=(row["turn"] == 1))
        toks.append(ctx.tokens)
        g = [p for p in ctx.provenance if p[0] == "gate"]
        ret = [ev_id[p[1]] for p in ctx.provenance if p[0] == "retrieved"]
        if g and g[0][1] == "통과":
            gated += 1
            if ret:
                hits += 1
        debt_ids = [r["debt_id"] for p in ctx.provenance if p[0] == "debt"
                    for r in m.db.execute("SELECT debt_id FROM debt WHERE chat_id=?"
                                          " AND content=?", (CHAT, p[1]))]
        per_turn.append((row["seq"], tuple(ret), tuple(debt_ids)))
        last_used = [f"event:{i}" for i in ret] + [f"debt:{i}" for i in debt_ids]
        for p in ctx.provenance:
            if p[0] == "degraded" and p[1].startswith("debt:"):
                degraded[(p[1], p[2])] += 1
    return dict(toks=toks, gated=gated, hits=hits, per_turn=per_turn,
                emitted=emitted, open_max=open_max, degraded=degraded)


def q(m, sql, *a):
    return m.db.execute(sql, a).fetchall()


def main():
    corpus, ledger = load()
    arc0 = ledger["relationship_arc"][0]
    tmp = tempfile.mkdtemp(prefix="meta-arm-")
    print("=" * W)
    print("동기 층 팔 — `apply_meta`를 character 턴마다 부르면 무엇이 채워지는가")
    print("=" * W)
    print(MOCK_BANNER)
    print("\n🔴 wave4 사전 등록 (값 보기 전):")
    for ln in PREREG_W4:
        print(f"  · {ln}")
    print("\n모의 규칙 (값 보기 전 고정):")
    for k, why in MOCK_RULES:
        print(f"  · {k:<14} {why}")
    try:
        # ── 앵커: A0 = soak.replay ──
        m_ref = make_db(tmp, "ref", corpus, ledger)
        _, ref_toks, ref_gated, ref_hits = soak.replay(m_ref, corpus)
        m_ref.db.close()
        m0 = make_db(tmp, "A0", corpus, ledger)
        a0 = run_arm(m0, corpus)
        # 사전 등록의 전제 둘 — 기본 경로(= A0)에서 센다. 값을 고치는 자리가 아니다.
        pre_debt = q(m0, "SELECT COUNT(*) FROM debt")[0][0]
        pre_called = q(m0, "SELECT called_as FROM relationship WHERE chat_id=?", CHAT)[0][0]
        m0.db.close()
        anchor = (a0["toks"], a0["gated"], a0["hits"]) == (ref_toks, ref_gated, ref_hits)
        print("\n" + "-" * W)
        print("0. 앵커 — 이 루프(A0)가 `soak.replay`와 같은 길인가")
        print("-" * W)
        print(f"  soak.replay : 턴 {len(ref_toks)} · 게이트 통과 {ref_gated} · 주입 {ref_hits}"
              f" · 토큰 p50 {soak.pct(ref_toks, 50)} ntok")
        print(f"  A0          : 턴 {len(a0['toks'])} · 게이트 통과 {a0['gated']} ·"
              f" 주입 {a0['hits']} · 토큰 p50 {soak.pct(a0['toks'], 50)} ntok")
        print(f"  → 턴별 토큰 {len(ref_toks)}개 전부 {'✅ 같다' if anchor else '🔴 다르다'}")
        print(f"  사전 등록 전제 (A0 = 기본 경로): `debt` {pre_debt}행 · 호칭 {pre_called!r}"
              f" ({len(pre_called)}자 · `apply_meta` 호출 0) · 부채 강등 기록"
              f" {sum(a0['degraded'].values())}건")
        if not anchor:
            print("  🔴 앵커 실패 — 이 루프는 기본 경로가 아니다. 아래 수는 귀속할 수 없다.")
            return 1

        m1c = make_db(tmp, "A0p", corpus, ledger, (arc0["stage"], arc0["affinity"]))
        a0p = run_arm(m1c, corpus)
        m1 = make_db(tmp, "A1", corpus, ledger, (arc0["stage"], arc0["affinity"]))
        a1 = run_arm(m1, corpus, Mock(corpus, ledger))
        m2 = make_db(tmp, "A2", corpus, ledger, (arc0["stage"], arc0["affinity"]))
        a2 = run_arm(m2, corpus, Mock(corpus, ledger), boundaries=True)

        n_user = len(a1["toks"])
        em = a1["emitted"]
        print("\n" + "-" * W)
        print(f"1. 모의 `<meta>`가 낸 것 (A1 · character 턴 {len(corpus) - n_user}개 중)")
        print("-" * W)
        inj_ev = sum(len(t[1]) for t in a1["per_turn"])
        inj_db = sum(len(t[2]) for t in a1["per_turn"])
        print(f"  used_memories  event {em['used_event']:>3}건 · debt {em['used_debt']:>3}건"
              f"  (user 턴에 주입된 것 event {inj_ev} · debt {inj_db} 중 **바로 뒤에"
              f" character 턴이 온** 것만)")
        for k in ("new_debt", "state_delta", "scene_delta"):
            print(f"  {k:<14} {em[k]:>4}건")

        # ── ① surfaced_count ──
        ev = q(m1, "SELECT event_id, surfaced_count, user_deleted FROM event"
                   " WHERE chat_id=? ORDER BY event_id", CHAT)
        sc = [r["surfaced_count"] for r in ev]
        n_ev_used = sum(1 for x in sc if x > 0)
        print("\n" + "-" * W)
        print("2. `used_memories` → `surfaced_count` — 실제로 오르는가")
        print("-" * W)
        print(f"  `event:` id 선언 {em['used_event']}건"
              f" → `surfaced_count` 합 {sum(sc)} · 0보다 큰 행 {n_ev_used}/{len(ev)}"
              f" (event 행 전체) · 최댓값 {max(sc)}"
              f"   {'✅ 선언 = 합' if sum(sc) == em['used_event'] else '🔴 선언 ≠ 합'}")
        print(f"  A0′(대조)의 `surfaced_count` 합: "
              f"{sum(r[0] for r in q(m1c, 'SELECT surfaced_count FROM event WHERE chat_id=?', CHAT))}")
        # 페널티가 검색을 바꾸는가 — A1 대 A0′, user 턴마다 주입된 id 목록(순서 포함)
        diff_order = sum(1 for x, y in zip(a1["per_turn"], a0p["per_turn"]) if x[1] != y[1])
        diff_set = sum(1 for x, y in zip(a1["per_turn"], a0p["per_turn"])
                       if set(x[1]) != set(y[1]))
        both = sum(1 for x, y in zip(a1["per_turn"], a0p["per_turn"]) if x[1] or y[1])
        print(f"  페널티(`SURFACED_PENALTY`={memory.SURFACED_PENALTY})가 검색을 바꾼 턴:"
              f" 순서 포함 {diff_order} · 집합 {diff_set} / 어느 팔이든 주입이 있던 턴 {both}"
              f" (user 턴 {n_user})")
        print(f"  게이트 통과 A0′ {a0p['gated']} · A1 {a1['gated']}   주입 턴 A0′"
              f" {a0p['hits']} · A1 {a1['hits']}")

        # ── ② debt ── (🔄 wave4: A1과 A2를 나란히 — 경계 행이 백오프를 움직이는가)
        seq_sess = {r["seq"]: r["session"] for r in corpus}
        print("\n" + "-" * W)
        print("3. `new_debt` → `debt` — 행이 생기는가, 무엇이 그 행을 읽는가, 갚아지는가")
        print("-" * W)
        paid_by = {}
        for tag, mm, a in (("A1 (경계 행 없음)", m1, a1), ("A2 (경계 행 있음)", m2, a2)):
            dr = q(mm, "SELECT debt_id, content, trigger_kind, trigger_spec, trigger_clock,"
                       " status, attempt_count, setup_turn_seq FROM debt WHERE chat_id=?"
                       " ORDER BY debt_id", CHAT)
            inj = Counter(i for t in a["per_turn"] for i in t[2])
            first_inj = {}
            for seq, _, ds in a["per_turn"]:
                for i in ds:
                    first_inj.setdefault(i, seq)
            paid_at = {int(r["item"].split(":")[1]): r["turn_seq"] for r in q(
                mm, "SELECT turn_seq, item FROM provenance WHERE chat_id=? AND kind='debt_paid'",
                CHAT)}
            paid_by[tag] = len(paid_at)
            print(f"  [{tag}] 행 {len(dr)} (선언 {a['emitted']['new_debt']}) · 한 채팅의"
                  f" `open` 최댓값 {a['open_max']} · 끝 상태"
                  f" {dict(sorted(Counter(r['status'] for r in dr).items()))}")
            print(f"    {'id':<4}{'trigger_kind':<15}{'spec':<14}{'setup':>9}{'첫 주입':>10}"
                  f"{'주입':>5}{'시도':>5}{'paid':>10}  상태")
            for r in dr:
                d, s0 = r["debt_id"], r["setup_turn_seq"]
                fi, pa = first_inj.get(d), paid_at.get(d)
                cell = lambda x: "—" if x is None else f"{x}·{seq_sess.get(x, '?')}"
                print(f"    {d:<4}{r['trigger_kind']:<15}{str(r['trigger_spec'])[:12]:<14}"
                      f"{cell(s0):>9}{cell(fi):>10}{inj[d]:>5}{r['attempt_count']:>5}"
                      f"{cell(pa):>10}  {r['status']}")
            print(f"    `debt:` id 선언 {a['emitted']['used_debt']}건 → `paid` {len(paid_at)}건")
            deg = Counter()
            for (_, why), c in a["degraded"].items():
                deg[why] += c
            for why, c in sorted(deg.items()):
                print(f"    강등 기록 {c:>3}건 — {why}")
        print(f"  A0′(대조)의 `debt` 행: "
              f"{q(m1c, 'SELECT COUNT(*) FROM debt WHERE chat_id=?', CHAT)[0][0]}")
        print("  🔴 D004(`semantic`)는 대장이 **일부러 안 갚는** 부채다(`expected_payoff: null`)."
              " 의미 트리거를")
        print("     평가하지 않으므로 백오프만 지나면 나가고, 모의 규칙(«주입된 것을 전부 썼다»)이"
              " 그것을 갚는다 —")
        print("     «평가하지 않는다»의 값이다(`memory.py` 끝 절 ④). 모델이 실제로 안 쓰면 안"
              " 갚아진다.")

        # ── ③ state_delta ──
        sv = q(m1, "SELECT field, reason FROM state_violation WHERE chat_id=?"
                   " ORDER BY rowid", CHAT)
        applied = q(m1, "SELECT item FROM provenance WHERE chat_id=? AND kind='state_delta'", CHAT)
        rejected = q(m1, "SELECT item FROM provenance WHERE chat_id=? AND kind='meta_rejected'"
                         " AND item LIKE 'state_delta%'", CHAT)
        trans = q(m1, "SELECT item, reason FROM provenance WHERE chat_id=?"
                      " AND kind='stage_transition' ORDER BY rowid", CHAT)
        stale = q(m1, "SELECT derived_kind, derived_key FROM stale WHERE chat_id=?"
                      " ORDER BY derived_kind, derived_key", CHAT)
        rel = q(m1, "SELECT stage, affinity FROM relationship WHERE chat_id=?", CHAT)[0]
        print("\n" + "-" * W)
        print("4. `state_delta` → FSM 검증기(`fsm.validate`)를 타는가")
        print("-" * W)
        print(f"  선언 {em['state_delta']} → 적용 {len(applied)} · 거부 {len(rejected)}"
              f" · `state_violation` {len(sv)}행 "
              f"{dict(sorted(Counter(r['reason'] for r in sv).items()))}")
        print(f"  전이 {len(trans)}회: " + " · ".join(t["item"] for t in trans))
        print(f"  끝 상태 {rel['stage']}/{rel['affinity']} · 전이가 남긴 stale "
              f"{[f'{r[0]}:{r[1]}' for r in stale]}")

        # ── ④ scene_delta ──
        sr = q(m1, "SELECT item, reason FROM provenance WHERE chat_id=? AND"
                   " kind='meta_rejected' AND item LIKE 'scene_delta%'", CHAT)
        scene = q(m1, "SELECT place, present, situation, updated_by_turn FROM scene"
                      " WHERE chat_id=?", CHAT)[0]
        lens = sorted(len(v) for v in Mock(corpus, ledger).scene_at.values())
        print("\n" + "-" * W)
        print("5. `scene_delta` → 값 가드(`_scene_value_ok`)가 걸리는가")
        print("-" * W)
        print(f"  선언 {em['scene_delta']} → 거부 {len(sr)} · 적용 {em['scene_delta'] - len(sr)}"
              f" · 사유 {dict(sorted(Counter(r['reason'] for r in sr).items()))}")
        print(f"  모의 값 길이(글자) min {lens[0]} · p50 {lens[len(lens) // 2]} · max {lens[-1]}"
              f" · 한도 `SCENE_VALUE_MAXLEN`={memory.SCENE_VALUE_MAXLEN}")
        print(f"  끝 scene: 장소={scene['place']} · 상황={scene['situation']!r}"
              f" · updated_by_turn={scene['updated_by_turn']}")

        # ── ④-b 씬 한도 40(코드) vs 60(docs/06 L3) — 두 코퍼스의 후보 값을 센다 (wave4 T3) ──
        cap, doc_cap = memory.SCENE_VALUE_MAXLEN, 60
        print(f"\n  5-b. 한도 {cap}(코드) vs {doc_cap}(docs/06 L3 `situation`) — 두 코퍼스의 후보"
              " 값 (단위: 글자)")
        print("     🔴 코퍼스에 씬 칸은 없다. 후보 셋: ① 모의 규칙의 값(세션 첫 user 발화)"
              " ② 전 발화(값이 발화를")
        print("        그대로 옮겨 올 때의 상한) ③ `eval/sessions/*.md`의 수기 «씬» 머리")
        over = 0
        for name, path in CORPORA:
            rows = [json.loads(l) for l in open(path, encoding="utf-8")]
            first = {}
            for r in rows:
                if r["role"] == "user":
                    first.setdefault(r["session"], r["text"])
            fl = [len(t) for t in first.values()]
            al = [len(r["text"]) for r in rows]
            over += sum(x > cap for x in fl)
            print(f"     {name:<6} ① {sum(x > cap for x in fl)}/{len(fl)} > {cap} ·"
                  f" {sum(x > doc_cap for x in fl)}/{len(fl)} > {doc_cap} · max {max(fl)}"
                  f"   ② {sum(x > cap for x in al)}/{len(al)} > {cap} ·"
                  f" {sum(x > doc_cap for x in al)}/{len(al)} > {doc_cap} · max {max(al)}")
            for r in rows:
                if len(r["text"]) > cap:
                    print(f"            ② {r['session']}:{r['seq']} {r['role']} {len(r['text'])}자"
                          f" {r['text']!r}")
        heads = []
        for f in sorted(os.listdir(os.path.join(ROOT, "eval", "sessions"))):
            for ln in open(os.path.join(ROOT, "eval", "sessions", f), encoding="utf-8"):
                if "**씬**" in ln:
                    heads.append(len(ln.split("**씬**", 1)[1].strip()))
        print(f"     eval   ③ {sum(x > cap for x in heads)}/{len(heads)} > {cap} · max"
              f" {max(heads)}")
        print(f"     → 사전 등록 전제(①이 {cap}자를 넘는 값): {over}개")

        # ── 비용 ──
        print("\n" + "-" * W)
        print("6. 컨텍스트 토큰 (ntok) — A0′ 대 A1")
        print("-" * W)
        for tag, a in (("A0′", a0p), ("A1", a1)):
            print(f"  {tag:<4} p50 {soak.pct(a['toks'], 50)} · p95 {soak.pct(a['toks'], 95)}"
                  f" · max {max(a['toks'])} ntok (user 턴 {len(a['toks'])})")

        # 🔴 **발화할 수 없는 팔을 막는다.** 채널 하나라도 0건이면 그 배관은 이 팔에서
        #    안 돌았고, 그 채널의 «무엇이 채워지는가»는 아무것도 안 잰 것이다. 그리고
        #    `surfaced_count`의 합이 선언과 다르면 배관이 새거나 셈이 틀렸다.
        vacuous = [k for k in ("used_event", "used_debt", "new_debt", "state_delta",
                               "scene_delta") if em[k] == 0]
        if sum(sc) != em["used_event"]:
            vacuous.append("surfaced_count 합 ≠ event 선언")
        # 🔄 wave4 — 상환 배관. 설계 경로(A2)에서 `debt:` 선언이 있는데 `paid`가 0이면
        #    `open → paid`가 안 돈 것이다(wave2까지의 상태가 정확히 그것이었다).
        if a2["emitted"]["used_debt"] and not paid_by["A2 (경계 행 있음)"]:
            vacuous.append("A2 debt 선언 > 0 인데 paid 0")
        # 두 팔이 정말 «경계 행 하나»만큼 다른가 — A2에서 카운터가 경계를 몰랐다는 기록이
        # 나오면 경계 행이 안 쓰인 것이고, A1에서 안 나오면 A1이 «요약 층 없음»이 아니다.
        lag = {t: sum(c for (_, why), c in a["degraded"].items() if "카운터" in why)
               for t, a in (("A1", a1), ("A2", a2))}
        if lag["A2"] or not lag["A1"]:
            vacuous.append(f"경계 카운터 강등 기록 A1 {lag['A1']} · A2 {lag['A2']}"
                           " (A1 > 0 · A2 = 0이어야 한다)")
        n_debt = q(m1, "SELECT COUNT(*) FROM debt WHERE chat_id=?", CHAT)[0][0]
        print("\n" + "=" * W)
        print(MOCK_BANNER)
        if vacuous:
            print(f"🔴 배관이 안 돌았거나 샌다: {vacuous} — **무효.**")
            return 1
        print(f"  surfaced 합 {sum(sc)} · debt 행 {n_debt} (open 최댓값 {a1['open_max']})"
              f" · state 적용 {len(applied)}/{em['state_delta']}"
              f" · scene 거부 {len(sr)}/{em['scene_delta']}"
              f" · paid A1 {paid_by['A1 (경계 행 없음)']} · A2 {paid_by['A2 (경계 행 있음)']}")
        print("=" * W)
        m1.db.close()
        m1c.db.close()
        m2.db.close()
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
