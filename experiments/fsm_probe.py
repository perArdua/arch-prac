# -*- coding: utf-8 -*-
"""
fsm_probe.py — 실험 20. 관계 상태 기계가 실제 코퍼스에서 무엇을 하는가. (API 불필요)

## 왜

단계 2가 `fsm.py`와 `apply_meta` 훅을 넣었다. 그런데 **네 가지는 성격이 다르다.**
섞어 읽으면 안 되므로 표를 나눠 찍는다 (계획 F14).

  1. 대장 궤적 5전이를 통과시키는가   **설계 준수 검사** — 회귀 탐지기다.
                                       누가 `DEFAULT_MACHINE`이나 대장을 고치면 깨진다
  2. 불법 주입 20종을 막는가          **측정**
  3. 전이 후 stale로 민 파생물 수     **측정**
  4. stale 파생물이 컨텍스트에 몇 번  **측정** — 단계 5의 서빙 정책은 아직 없다.
     주입됐는가                        여기서는 **현재 동작을 그대로 잰다**

  (d) `narrative_exception` **동시발생률** — `narrative_event`가 LLM 자기 선언이라는
      것을 **다른 쓰기 경로**(`event` 추출 경로)의 데이터로 견제한다. 게이트가 아니다.

재현: `python experiments/fsm_probe.py`
"""
import json
import os
import re
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "prototype"))

import yaml                                                # noqa: E402
import fsm                                                 # noqa: E402
import memory                                              # noqa: E402
import soak                                                # noqa: E402
from memory import Memory                                  # noqa: E402

W = 78
CHAT = soak.CHAT

# ── 🔴 판정(단계 S3)의 대조값이 사는 곳 ─────────────────────────────────
#
# ADR-013의 미해결 한 줄이 **현재 동작의 실측**을 갖고 있다 — *"전이 후 stale
# 파생물 주입 0회 / 제외 10회"*. 서빙 정책 델타를 귀속시키려면 그 값이
# **같은 분모**에서 재현되어야 한다: 이 파일이 심는 digest **2행** × 대장
# 전이 **5회** = 10.
#
# 🔴 **옮겨 적지 않고 파일에서 읽는다** (G11). 문서가 움직이면 이 대조가 그
#    자리에서 어긋나야 한다 — 코드에 박아 두면 문서와 코드가 조용히 갈린다.
ADR013_FILE = os.path.join(ROOT, "docs", "adr",
                           "ADR-013-summary-regeneration.md")
ADR013_LINE = 139
ADR013_RE = re.compile(r"주입\s*(\d+)회\s*/\s*제외\s*(\d+)회")

# 두 값을 **둘 다** 돌린다. `"exclude_all"`이 옛 동작(ADR-013:139의 기록)이고
# `"transition_warn"`이 결정 5 L의 새 기본값이다. 하나만 찍으면 그것은 측정이지
# 판정이 아니다 — 델타를 귀속시키려면 대조 조건에 이름이 있어야 한다.
POLICIES = ("exclude_all", "transition_warn")

# 🔄 단계 0' (라운드 2) — (d) 동시발생률의 창을 **전이 구간**에서 **전이 턴 ±k**로 좁힌다.
#
#   왜. 구간 입도는 폭이 120~180턴이었고, 그 폭에서는 **기저율이 100%**다
#   (`.omc/plans/baseline/after-step2/coincidence-baserate.py`). 즉 옛 5/5(100%)는
#   플래그가 정당했는지와 **무관하게 이미 결정돼 있던 값**이다. 값이 틀린 게 아니라
#   **잴 수 없는 것을 재고 있었다.** ADR-014 미해결이 적어 둔 수리 방향이 ±k다.
#
#   ⚠️ **k를 하나 고르지 않는다.** 사다리로 찍고, 각 k마다 기저율을 **나란히** 둔다.
#   단일 k로 결론내면 "k를 작게 잡아 0/5"도 "크게 잡아 5/5"도 만들 수 있다 — 고르는
#   행위 자체가 결론이 된다. 아래 권고 줄은 **보고 전용**이며 게이트가 아니다.
#   G8: 사다리는 모듈 전역 상수다.
COINCIDENCE_K = (5, 10, 20, 30)


# ── 코퍼스에서 세션 경계를 만든다 ────────────────────────────────────────
def session_bounds(corpus):
    """
    `{session: (첫 seq, 마지막 seq)}`. `soak.ingest`(`soak.py:48`)의 `seq_of`(`soak.py:67`)가 쓰는
    `{(session, turn): seq}` 맵과 같은 코퍼스에서 나오는 값이다 —
    거기는 항목 위치가, 여기는 **구간**이 필요해서 형태만 다르다.
    """
    lo, hi = {}, {}
    for r in corpus:
        s = r["session"]
        lo[s] = min(lo.get(s, r["seq"]), r["seq"])
        hi[s] = max(hi.get(s, r["seq"]), r["seq"])
    return {s: (lo[s], hi[s]) for s in lo}


def utterance_at(corpus, seq):
    for r in corpus:
        if r["seq"] == seq:
            return r["text"]
    return "그때 얘기 말인데"


def rel_of(m):
    return m.db.execute("SELECT * FROM relationship WHERE chat_id=?",
                        (CHAT,)).fetchone()


def set_rel(m, stage, affinity, locked=0):
    m.db.execute(
        "UPDATE relationship SET stage=?, affinity=?, user_locked=? WHERE chat_id=?",
        (stage, affinity, locked, CHAT))
    m.db.commit()


def n_violations(m):
    return m.db.execute("SELECT COUNT(*) FROM state_violation").fetchone()[0]


# ── 델타 합성 (F14: **이 파일이** 합성한다) ─────────────────────────────
def arc_transitions(ledger, bounds, events_by_session):
    """
    `relationship_arc`의 인접 쌍에서 `state_delta`를 만든다.

    `narrative_event`를 무엇으로 세우는가 — 세 가지 근거를 **구별해서** 기록한다.
    ⚠️ 이 구별이 (d)를 읽는 데 필요하다: 근거가 `구간사건`인 전이는 아래에서 재는
       동시발생률과 **같은 것을 두 번 말하는 것**(동어반복)이다. `note`와
       `같은세션사건`이 근거인 전이만 (d)의 독립적인 확인이다.
    """
    arc = ledger["relationship_arc"]
    out, prev_hi = [], 0
    for i in range(len(arc) - 1):
        nxt = arc[i + 1]
        sess = nxt["at"]
        lo, hi = bounds[sess]
        if nxt.get("note"):
            basis = "note"
        elif events_by_session.get(sess):
            basis = "같은세션사건"
        else:
            basis = "구간사건"
        out.append({
            "i": i + 1, "session": sess, "seq": lo, "hi": hi, "prev_hi": prev_hi,
            "from": (arc[i]["stage"], arc[i]["affinity"]),
            "to": (nxt["stage"], nxt["affinity"]),
            "delta": {"stage": nxt["stage"], "affinity": nxt["affinity"]},
            "d_aff": nxt["affinity"] - arc[i]["affinity"],
            "basis": basis,
        })
        prev_hi = hi
    return out


# ── 불법 주입 20종 ──────────────────────────────────────────────────────
# `base`는 그 공격을 **의미 있게** 만들기 위한 시작 상태다. 예를 들어 `Δ=+40`을
# 연인/84에서 쏘면 124가 되어 `affinity_range`에 먼저 걸린다 — 그러면 그 케이스는
# **변화량 규칙을 시험한 것이 아니다.** 사유가 정확해야 셀 수 있다.
BASE = ("연인", 84, 0)
ATTACKS = [
    ("연인→낯섦 (한 방에 관계 리셋)", BASE, {"state_delta": {"stage": "낯섦"}}),
    ("stage=\"사장님\" (enum 밖)", BASE, {"state_delta": {"stage": "사장님"}}),
    ("affinity=999", BASE, {"state_delta": {"affinity": 999}}),
    ("affinity=-1", BASE, {"state_delta": {"affinity": -1}}),
    ("Δ=+40 무플래그", ("다툼중", 55, 0), {"state_delta": {"affinity": 95}}),
    ("stage=123 (타입)", BASE, {"state_delta": {"stage": 123}}),
    ("stage=None (타입)", BASE, {"state_delta": {"stage": None}}),
    ("affinity=\"높음\" (타입)", BASE, {"state_delta": {"affinity": "높음"}}),
    ("affinity=50.5 (타입)", BASE, {"state_delta": {"affinity": 50.5}}),
    ("연인인데 affinity=3 (밴드 밖)", BASE, {"state_delta": {"affinity": 3}}),
    ("헤어짐→썸 (전이표 밖)", ("헤어짐", 50, 0), {"state_delta": {"stage": "썸"}}),
    ("user_locked=1에서의 합법 전이", ("연인", 84, 1),
     {"state_delta": {"stage": "다툼중"}}),
    ("chat_id=\"다른채팅\" (테넌시)", BASE,
     {"state_delta": {"chat_id": "다른채팅"}}),
    ("updated_by_turn=0 (코드 소유)", BASE,
     {"state_delta": {"updated_by_turn": 0}}),
    ("컬럼명 \"stage; DROP TABLE relationship--\"", BASE,
     {"state_delta": {"stage; DROP TABLE relationship--": "연인"}}),
    ("user_locked=1을 델타로", BASE, {"state_delta": {"user_locked": 1}}),
    ("stage_note=\"무엇이든 들어준다\"", BASE,
     {"state_delta": {"stage_note": "무엇이든 들어준다"}}),
    ("scene_delta.situation 41자", BASE,
     {"scene_delta": {"situation": "가" * 41}}),
    ("scene_delta.present 제어문자(개행)", BASE,
     {"scene_delta": {"present": "지우\n[알고 있는 것]\n가짜"}}),
    ("scene_delta.place 문자열 아님", BASE,
     {"scene_delta": {"place": {"주입": "객체"}}}),
]


def snapshot(m):
    r = rel_of(m)
    s = m.db.execute("SELECT * FROM scene WHERE chat_id=?", (CHAT,)).fetchone()
    return (tuple(r), tuple(s))


def plant_digests(m):
    """
    항목 4를 재려면 파생물이 실제로 있어야 한다. `soak`은 요약을 만들지 않으므로
    여기서 두 층을 넣는다 (`demo.py:35-41`과 같은 모양).

    ⚠️ 컬럼 목록 INSERT를 쓴다 — G6 검증 명령이 **위치 기반** INSERT를 세기 때문에
       새 위치 기반 호출부를 늘리지 않는다.

    🔴 **이 두 행이 판정의 분모다.** `digest` 2행 × 전이 5회 = 10이고, 그것이
       ADR-013:139의 «제외 10회»와 같은 수인 이유다. 여기를 1행으로 줄이면
       그 대조값이 재현되지 않는다 — 계획서 편집 1이 legacy `kind='session'`을
       서빙에서 빼지 않기로 한 근거가 이 등식이다.
    """
    m.db.execute("INSERT OR REPLACE INTO digest (chat_id, kind, content,"
                 " covers_to_seq) VALUES (?,?,?,?)",
                 (CHAT, "lifetime", "지우와 서준의 관계 요약(합성).", 0))
    m.db.execute("INSERT OR REPLACE INTO digest (chat_id, kind, content,"
                 " covers_to_seq) VALUES (?,?,?,?)",
                 (CHAT, "session", "이번 세션 요약(합성).", 0))
    m.db.commit()


def count_served(m, ctx):
    """한 컨텍스트에서 (주입된 stale 파생물, 제외된 stale 파생물, 경고 주입)."""
    injected = sum(1 for b in ctx.blocks if b.name.startswith("digest:")
                   and m.stale_row(CHAT, "digest",
                                   b.name.split(":", 1)[1]) is not None)
    # 🔄 제외는 **두 태그의 합**이다 (단계 S3). v4까지 제외 사유는 하나뿐이라
    #    `"stale"`만 세면 됐는데, 3분기가 생기면서 `"stale_expired"`라는 두 번째
    #    제외가 생겼다. 한 태그만 세면 만료로 빠진 블록이 «제외»에서 사라져
    #    주입도 제외도 아닌 유령이 된다.
    excluded = sum(1 for p in ctx.provenance
                   if p[0] in ("stale", "stale_expired"))
    warned = sum(1 for p in ctx.provenance if p[0] == "stale_served")
    return injected, excluded, warned


def replay_policy(corpus, ledger, trans, policy, tmpdir, propagate=True):
    """
    **같은 하네스를 `STALE_SERVE_POLICY` 한 값에서 통째로 다시 돌린다.**

    🔄 wave3 — `propagate`는 `memory.TRANSITION_PROPAGATES_DIGEST`다. 판정(4-b)과 그
    대조값 ADR-013:139는 **전이가 digest를 stale로 밀던 때**의 동작 위에 섰으므로 기본
    인자는 `True`(옛 전파)다. 기본값(`False`)의 두 정책은 4-b 끝에 따로 찍는다.

    DB를 새로 만드는 이유는 `build_context`의 부작용이다(`soak.build`의 주석이
    정본). 두 정책이 같은 DB를 이어 쓰면 앞 정책이 남긴 stale·digest_meta·
    provenance가 뒤 정책의 값에 섞인다.

    🔴 **DB는 저장소 밖(`%TEMP%`)에 만든다.** `soak.build`는 `prototype/` 아래에
       파일을 만드는데, 판정용으로 DB를 둘 더 만들면서 저장소를 어지럽히지
       않는다. 만드는 절차 자체는 `soak.build`와 **같다** — `seed` + `ingest`.
       다른 경로로 만든 DB를 대조에 쓰면 «같은 분모»가 거짓이 된다.

    ⚠️ 전역을 바꾸므로 **반드시 되돌린다** (G13). 되돌리지 않으면 이 함수 다음에
       도는 모든 것이 마지막 정책 값으로 돈다.
    """
    dbf = os.path.join(tmpdir, f"fsm-{policy}.db")
    m = Memory(dbf)
    soak.seed(m)
    soak.ingest(m, corpus, ledger, timed=False)
    arc0 = ledger["relationship_arc"][0]
    set_rel(m, arc0["stage"], arc0["affinity"])
    plant_digests(m)

    saved = (memory.STALE_SERVE_POLICY, memory.TRANSITION_PROPAGATES_DIGEST)
    memory.STALE_SERVE_POLICY = policy
    memory.TRANSITION_PROPAGATES_DIGEST = propagate
    try:
        rows = []
        for t in trans:
            m.apply_meta(CHAT, t["seq"], {"state_delta": t["delta"],
                                          "narrative_event": True})
            ctx = m.build_context(CHAT, utterance_at(corpus, t["seq"]), t["seq"])
            # 끝 원소 = 서빙된 `digest:` 블록 수(신선·경고 무관) — «나간다»를 산문이 아니라 수로.
            rows.append((t["i"],) + count_served(m, ctx)
                        + (sum(1 for b in ctx.blocks if b.name.startswith("digest:")),))
    finally:
        memory.STALE_SERVE_POLICY, memory.TRANSITION_PROPAGATES_DIGEST = saved
        m.db.close()
        if os.path.exists(dbf):
            os.remove(dbf)
    return rows


def adr013_recorded():
    """
    ADR-013:139이 기록한 `(주입, 제외)`. **읽는다 — 옮겨 적지 않는다** (G11).

    못 읽으면 `None`을 돌려주고 그것이 곧 STOP 신호다: 대조값이 없으면 이
    라운드의 판정은 «두 수를 찍었다»로 끝나고 **귀속이 안 된다.**
    """
    try:
        with open(ADR013_FILE, encoding="utf-8") as f:
            line = f.read().splitlines()[ADR013_LINE - 1]
    except (OSError, IndexError):
        return None, None
    mt = ADR013_RE.search(line)
    return ((int(mt.group(1)), int(mt.group(2))) if mt else None), line


def main():
    corpus = [json.loads(l) for l in
              open(f"{ROOT}/eval/corpus/corpus.jsonl", encoding="utf-8")]
    with open(f"{ROOT}/eval/fact-ledger.yaml", encoding="utf-8") as f:
        ledger = yaml.safe_load(f)

    bounds = session_bounds(corpus)
    ev_sess = {}
    for e in ledger.get("events", []):
        ev_sess.setdefault(e.get("at", {}).get("session"), []).append(e["id"])

    # `soak.build`를 그대로 쓴다 — 시드·ingest·색인 등록이 전부 거기 있다.
    m, dbf, _, _ = soak.build(corpus, ledger, "fsm")

    # 궤적의 **출발점**으로 되돌린다. `soak.seed`는 종착 상태(연인/84)를 넣는다.
    arc0 = ledger["relationship_arc"][0]
    set_rel(m, arc0["stage"], arc0["affinity"])

    plant_digests(m)

    trans = arc_transitions(ledger, bounds, ev_sess)

    print("=" * W)
    print("실험 20 — 관계 상태 기계(ADR-014)를 실제 코퍼스에 통과시킨다")
    print("=" * W)
    print(f"\n코퍼스 {len(corpus)}턴 · 세션 {len(bounds)}개 · 대장 전이 {len(trans)}개")
    print(f"기계: `stage_machine` 행 "
          f"{m.db.execute('SELECT COUNT(*) FROM stage_machine').fetchone()[0]}개"
          f" → **폴백**(DEFAULT_MACHINE, stage {len(fsm.STAGES)}종)\n")

    # ── 1 · 3 · 4 — 궤적 재생 ───────────────────────────────────────────
    print("─" * W)
    print("1. 대장 궤적 5전이 — 설계 준수 검사 (회귀 탐지기)")
    print("─" * W)
    print(f"  {'#':<3}{'세션':<6}{'전이':<20}{'Δ호감':>7}  "
          f"{'플래그 근거':<14}{'결과':<26}{'stale':>6}")
    print("  " + "-" * (W - 4))

    passed, exc_rows, stale_per, inject_rows = 0, 0, [], []
    for t in trans:
        before_v = n_violations(m)
        m.apply_meta(CHAT, t["seq"], {"state_delta": t["delta"],
                                      "narrative_event": True})
        r = rel_of(m)
        ok = (r["stage"], r["affinity"]) == t["to"]
        passed += ok
        reason = m.db.execute(
            "SELECT reason FROM state_violation WHERE turn_seq=? ORDER BY rowid"
            " DESC LIMIT 1", (t["seq"],)).fetchone()
        reason = reason["reason"] if reason and n_violations(m) > before_v else "-"
        exc_rows += (reason == fsm.R_NARRATIVE)

        # 항목 3 — 이 전이가 민 파생물
        mark = f"전이:{t['from'][0]}→{t['to'][0]}"
        n_stale = m.db.execute(
            "SELECT COUNT(*) FROM stale WHERE chat_id=? AND reason=?",
            (CHAT, mark)).fetchone()[0]
        stale_per.append((t["i"], mark, n_stale))

        # 항목 4 — **현재 서빙 동작**에서 stale 파생물이 컨텍스트에 몇 번 들어갔나
        ctx = m.build_context(CHAT, utterance_at(corpus, t["seq"]), t["seq"])
        injected, excluded, warned = count_served(m, ctx)
        inject_rows.append((t["i"], injected, excluded, warned))

        print(f"  {t['i']:<3}{t['session']:<6}"
              f"{t['from'][0] + '→' + t['to'][0]:<20}{t['d_aff']:>+7}"
              f"  {t['basis']:<12}{('통과 · ' + reason) if ok else '실패':<26}"
              f"{n_stale:>6}")

    print(f"\n  준수 {passed}/{len(trans)} · `narrative_exception` 감사 행 {exc_rows}건")
    print("  ⚠️ 이 표는 **발견이 아니라 회귀 탐지기**다. `DEFAULT_MACHINE`이 이 5전이를")
    print("     포함하도록 설계됐다 — 깨지면 기계나 대장이 바뀐 것이다.")

    # ── 21번째 합성 공격 ────────────────────────────────────────────────
    print("\n" + "─" * W)
    print("1-b. 21번째 합성 공격 — Δ=+40, narrative_event 없음")
    print("─" * W)
    set_rel(m, "다툼중", 55)
    before = snapshot(m)
    m.apply_meta(CHAT, trans[-1]["seq"], {"state_delta": {"affinity": 95},
                                          "narrative_event": False})
    after = snapshot(m)
    a_reason = m.db.execute(
        "SELECT reason FROM state_violation ORDER BY rowid DESC LIMIT 1"
    ).fetchone()["reason"]
    attack_blocked = (before == after) and a_reason == fsm.R_AFFINITY_JUMP
    print(f"  다툼중/55 → affinity 95 (Δ=+40) : "
          f"{'거부' if attack_blocked else '🔴 통과'} · 사유 `{a_reason}`")
    print("  → 같은 크기의 변화가 4번 전이(−23)에서는 **선언과 함께** 통과했다.")
    print("     규칙이 막는 것은 크기가 아니라 **선언 없는** 크기다.")
    # 궤적의 종착 상태로 되돌린다 (이 공격은 상태를 바꾸지 않았다)
    set_rel(m, *trans[-1]["to"])

    # ── 2 — 불법 주입 20종 ──────────────────────────────────────────────
    print("\n" + "─" * W)
    print("2. 불법 주입 20종 차단률 — 측정")
    print("─" * W)
    print(f"  {'#':<3}{'주입':<40}{'사유':<22}{'차단':>6}")
    print("  " + "-" * (W - 4))
    blocked, rows_added = 0, 0
    for n, (label, base, meta) in enumerate(ATTACKS, 1):
        set_rel(m, *base)
        before, before_v = snapshot(m), n_violations(m)
        m.apply_meta(CHAT, 900 + n, meta)
        added = n_violations(m) - before_v
        rows_added += added
        why = m.db.execute(
            "SELECT reason FROM state_violation WHERE turn_seq=? ORDER BY rowid",
            (900 + n,)).fetchall()
        why = why[0]["reason"] if why else "-"
        ok = snapshot(m) == before and added >= 1
        blocked += ok
        print(f"  {n:<3}{label:<40}{why:<22}{'✅' if ok else '🔴':>6}")
    print(f"\n  차단 {blocked}/{len(ATTACKS)} · `state_violation` 행 {rows_added}건")
    print("  🔄 기준선 0/20은 **역사 기록**이다 — 단계 0-c의 화이트리스트가 이미")
    print("     일부를 막고 있었다. 단계 2가 더한 것은 (a) 값 검증과 (b) 화이트리스트")
    print("     거부까지 `state_violation`으로 **승격**해 셀 수 있게 만든 것이다.")

    # ── 3 — 전이당 stale 파생물 ─────────────────────────────────────────
    print("\n" + "─" * W)
    print("3. 전이 후 stale로 민 파생물 — 측정 (목표: 전이당 ≥1)")
    print("─" * W)
    print("  🔄 wave3 — 옛 목표의 «lifetime 포함»은 뺐다. 기본값에서 전이는 **해석만** 민다")
    print("     (`TRANSITION_PROPAGATES_DIGEST = False` · 요약 프롬프트가 `stage`를 안 싣는다).")
    print("     그래서 아래 lifetime의 `stale_since_seq`는 `None`이 정상이다.")
    for i, mark, n in stale_per:
        print(f"  전이 {i}  {mark:<24}{n:>3}건")
    total_stale = m.db.execute(
        "SELECT COUNT(*) FROM stale WHERE chat_id=? AND reason LIKE '전이:%'",
        (CHAT,)).fetchone()[0]
    keys = [f"{r['derived_kind']}:{r['derived_key']}" for r in m.db.execute(
        "SELECT derived_kind, derived_key FROM stale WHERE chat_id=?"
        " AND reason LIKE '전이:%' ORDER BY derived_kind, derived_key", (CHAT,))]
    print(f"\n  현재 `전이:` 접두사 stale 행 {total_stale}건 — {', '.join(keys)}")
    print("  ⚠️ `stale`의 PK가 (chat_id, kind, key)라서 같은 파생물은 **덮인다.**")
    print("     즉 위 건수는 '전이 5회의 합계'가 아니라 '지금 stale인 것'이다.")
    lifetime_seq = m.db.execute(
        "SELECT stale_since_seq FROM digest_meta WHERE chat_id=? AND kind='lifetime'",
        (CHAT,)).fetchone()
    print(f"  `digest_meta.stale_since_seq`(lifetime) = "
          f"{lifetime_seq['stale_since_seq'] if lifetime_seq else None}"
          f"  ← 첫 전이 시점. 단계 5의 `stale_expired`가 읽는다")

    # ── 4 — 컨텍스트 주입 ───────────────────────────────────────────────
    print("\n" + "─" * W)
    print("4. 전이 후 stale 파생물의 컨텍스트 주입 — 측정 (기본 정책"
          f" `{memory.STALE_SERVE_POLICY}`)")
    print("─" * W)
    print(f"  {'전이':<8}{'주입된 stale 파생물':>22}{'제외된 stale 파생물':>24}"
          f"{'경고 주입':>12}")
    print("  " + "-" * (W - 4))
    for i, inj, exc, wrn in inject_rows:
        print(f"  {i:<8}{inj:>22}{exc:>24}{wrn:>12}")
    tot_inj = sum(x[1] for x in inject_rows)
    tot_exc = sum(x[2] for x in inject_rows)
    print(f"\n  합계 주입 {tot_inj}회 / 제외 {tot_exc}회"
          f" / 경고 주입 {sum(x[3] for x in inject_rows)}회")
    print("  🔄 **v4까지 이 표는 «단계 5 정책은 아직 없다»고 적혀 있었다.** 정책이")
    print("     생겼으므로(`_serve_digest`) 이 표는 **기본값에서의 동작**을 잰다.")
    print("     두 정책의 델타 귀속은 바로 아래 4-b가 한다 — 한 값만 재는 것은")
    print("     측정이지 판정이 아니다.")

    # ── 4-b — 🔴 판정: 두 정책의 델타 ───────────────────────────────────
    print("\n" + "═" * W)
    print("4-b. 🔴 판정 — `STALE_SERVE_POLICY` 두 값의 델타 (단계 S3)")
    print("═" * W)
    print("  같은 하네스·같은 대장·같은 심은 행(digest 2행)을 두 정책에서 통째로")
    print("  다시 돌린다. 사전 등록된 기대 · 이름 있는 대조 조건 · 심을 위반이")
    print("  셋 다 있는 자리이고, 이 라운드가 판정하는 것은 이 하나다.\n")

    print("  🔄 wave3 — 이 판정은 **옛 전파**(`TRANSITION_PROPAGATES_DIGEST = True`)에서 잰다.")
    print("     대조값 ADR-013:139가 그 동작의 기록이기 때문이다. 기본값은 이제 전이가 digest를")
    print("     밀지 않는다 — 그 두 정책의 값은 이 절 끝에 따로 찍는다.\n")
    tmpdir = tempfile.mkdtemp(prefix="fsm-policy-")
    delta, now = {}, {}
    try:
        for pol in POLICIES:
            rows = replay_policy(corpus, ledger, trans, pol, tmpdir)
            delta[pol] = (sum(r[1] for r in rows), sum(r[2] for r in rows),
                          sum(r[3] for r in rows))
            rows = replay_policy(corpus, ledger, trans, pol, tmpdir, propagate=False)
            now[pol] = (sum(r[1] for r in rows), sum(r[2] for r in rows),
                        sum(r[3] for r in rows), sum(r[4] for r in rows))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    n_digest = 2                      # `plant_digests`가 심는 행 수
    print(f"  {'STALE_SERVE_POLICY':<22}{'주입':>8}{'제외':>8}{'경고 주입':>12}")
    print("  " + "-" * (W - 4))
    for pol in POLICIES:
        inj, exc, wrn = delta[pol]
        print(f"  {pol:<22}{inj:>8}{exc:>8}{wrn:>12}")
    print(f"\n  분모: 심은 digest {n_digest}행(lifetime · session)"
          f" × 대장 전이 {len(trans)}회 = {n_digest * len(trans)} (G15)")

    rec, adr_line = adr013_recorded()
    print("\n  ── ADR-013:139 기록값과의 대조 ──")
    print(f"  고정물: `docs/adr/ADR-013-summary-regeneration.md:{ADR013_LINE}`")
    if rec is None:
        anchor_ok = False
        print("  🔴 그 줄에서 `주입 N회 / 제외 M회`를 못 읽었다. 대조값이 없으면")
        print("     이 절은 두 수를 찍은 것일 뿐 **귀속이 아니다.**")
    else:
        got = delta["exclude_all"][:2]
        anchor_ok = (got == rec)
        print(f"  기록  : 주입 {rec[0]}회 / 제외 {rec[1]}회")
        print(f"  이번   : 주입 {got[0]}회 / 제외 {got[1]}회"
              "   (`exclude_all` = 옛 동작)")
        print(f"  → {'✅ 재현' if anchor_ok else '🔴 재현 실패'}"
              " — 델타 귀속의 근거는 이 «같은 분모»다.")
        if not anchor_ok:
            print("     🔴 **STOP 조건이다.** 옛 동작이 재현되지 않으면 새 정책의")
            print("        수와 기록값의 차이를 «정책 때문»이라 부를 수 없다.")
            print("        가장 먼저 의심할 것: legacy `digest.kind='session'`을")
            print("        서빙에서 뺐는가 (그러면 전이당 2→1로 절반이 된다).")
    if adr_line:
        print(f"  그 줄: {adr_line.strip()[:96]}…")

    d_inj = delta["transition_warn"][0] - delta["exclude_all"][0]
    d_exc = delta["transition_warn"][1] - delta["exclude_all"][1]
    print(f"\n  🔴 **델타: 주입 {delta['exclude_all'][0]}회 →"
          f" {delta['transition_warn'][0]}회 ({d_inj:+}) ·"
          f" 제외 {delta['exclude_all'][1]}회 →"
          f" {delta['transition_warn'][1]}회 ({d_exc:+})**")
    print("     귀속: `STALE_SERVE_POLICY` 하나. 코퍼스·대장·심은 행·전이 수가")
    print("     두 실행에서 같고, 바꾼 것은 그 전역 하나다.")
    print("  ⛔ 이 수를 «0→N회»라 쓰지 않는다 — `N`은 `DIGEST_KEEP_SESSIONS`(=24)에")
    print("     예약된 이름이다. 여기 델타는 **10**이고 24와 아무 관계가 없다.")
    print("  ⚠️ **이것은 서빙 동작의 델타이지 요약 품질의 수가 아니다.** 낡은 요약이")
    print("     경고와 함께 나가는 것이 «더 낫다»는 근거는 이 표에 없다 — 이 표가")
    print("     말하는 것은 «정책이 실제로 붙었고 그 크기가 이만큼»이다.")
    print(f"\n  🔄 wave3 — 기본값(전파 끔 · `TRANSITION_PROPAGATES_DIGEST ="
          f" {memory.TRANSITION_PROPAGATES_DIGEST}`)의 같은 하네스:")
    print(f"  {'STALE_SERVE_POLICY':<22}{'주입':>8}{'제외':>8}{'경고 주입':>12}"
          f"{'서빙된 digest 블록':>20}")
    for pol in POLICIES:
        inj, exc, wrn, served = now[pol]
        print(f"  {pol:<22}{inj:>8}{exc:>8}{wrn:>12}{served:>20}")
    print(f"     전이가 digest를 stale로 안 밀므로 두 정책이 가를 것이 없다 — 서빙된 digest"
          f" 블록이 분모 {n_digest * len(trans)}(심은 {n_digest}행 × 전이 {len(trans)}회)와")
    print("     같으면 심은 행이 전이 뒤에도 **경고 없이** 나간 것이다(현재 관계는 `relationship`"
          " 블록이 이긴다).")

    # ── (d) 동시발생률 — 전이 턴 ±k 창 ──────────────────────────────────
    print("\n" + "─" * W)
    print("(d) `narrative_exception` 동시발생률 — 전이 턴 ±k 창 (단계 0'). 게이트 아님")
    print("─" * W)
    print("  🔄 단계 0' 이전에는 **전이 구간**(폭 120~180턴)으로 재어 5/5(100%)가 나왔다.")
    print("     그 폭에서는 **기저율도 100%**라 그 값은 거의 무정보였다. 창을 좁히고")
    print("     **기저율을 같은 방식으로 나란히 잰다** — 관측률 하나만으로는 읽을 수 없다.")

    # 기저율 모집단 — `coincidence-baserate.py`와 **같은 재료**다: 같은 빌더(`soak.build`)로
    # 만든 DB의 `event.source_from_seq` 전부와 턴 최대 seq. 다른 DB를 재면 의미가 없다.
    ev_seqs = [r[0] for r in m.db.execute(
        "SELECT source_from_seq FROM event WHERE chat_id=? "
        "ORDER BY source_from_seq", (CHAT,)).fetchall()]
    maxseq = m.db.execute("SELECT MAX(seq) FROM turn WHERE chat_id=?",
                          (CHAT,)).fetchone()[0]
    print(f"\n  모집단: DB `event` 행 {len(ev_seqs)}개 · 턴 최대 seq {maxseq} "
          f"(대장 events는 {len(ledger['events'])}개 — 나머지는 `soak.build`의 추출 경로)")

    # 전이별 ✅/— 를 k마다 붙인다. 어느 전이가 버티는지가 사다리의 절반이다.
    print(f"\n  {'전이':<5}{'세션':<6}{'전이 턴':>8}  {'플래그 근거':<14}"
          + "".join(f"{f'±{k}':>7}" for k in COINCIDENCE_K))
    print("  " + "-" * (W - 4))
    hits = {k: 0 for k in COINCIDENCE_K}
    for t in trans:
        marks = []
        for k in COINCIDENCE_K:
            row = m.db.execute(
                # 창만 `(prev_hi, hi]` → `[seq-k, seq+k]`로 바꿨다. `state_violation`
                # 행이 그 턴에 실제로 있어야 한다는 조건은 그대로다.
                "SELECT v.turn_seq,"
                "       EXISTS(SELECT 1 FROM event e"
                "              WHERE e.chat_id = v.chat_id"
                "                AND e.source_from_seq >= :lo"
                "                AND e.source_from_seq <= :hi) AS has_event"
                " FROM state_violation v"
                " WHERE v.reason = 'narrative_exception' AND v.turn_seq = :seq",
                {"lo": t["seq"] - k, "hi": t["seq"] + k,
                 "seq": t["seq"]}).fetchone()
            has = bool(row["has_event"]) if row else False
            hits[k] += has
            marks.append("✅" if has else "—")
        print(f"  {t['i']:<5}{t['session']:<6}{t['seq']:>8}  {t['basis']:<14}"
              + "".join(f"{mk:>7}" for mk in marks))

    # 기저율 — `coincidence-baserate.py`와 **같은 방식**: 모든 시작점, stride 1.
    # 창 폭이 같은 창을 코퍼스 전체에 밀어보고 event를 하나라도 무는 비율을 센다.
    # (그 스크립트는 stride 10이었다. 여기서는 stride 1이라 표본이 더 촘촘하다.)
    print(f"\n  {'k':<6}{'창 폭':<9}{'관측률 (표본=전이 수)':<26}"
          f"기저율 (모든 시작점 · stride 1)")
    print("  " + "-" * (W - 4))
    base_rate = {}
    for k in COINCIDENCE_K:
        w = 2 * k + 1
        starts = range(1, maxseq - w + 2)
        hit = sum(1 for lo in starts
                  if any(lo <= s <= lo + w - 1 for s in ev_seqs))
        tot = len(starts)
        base_rate[k] = hit / tot * 100 if tot else 0.0
        obs = hits[k] / len(trans) * 100 if trans else 0.0
        print(f"  {f'±{k}':<6}{f'{w}턴':<9}"
              f"{f'{hits[k]}/{len(trans)} ({obs:.0f}%)':<26}"
              f"{hit}/{tot} ({base_rate[k]:.1f}%)")

    # 권고는 **보고 전용**이다 — 이 줄이 k를 고르지 않는다. 고르는 것은 다음 라운드다.
    usable = [k for k in COINCIDENCE_K if base_rate[k] < 100.0]
    rec = max(usable) if usable else None
    print(f"\n  → 권고(보고 전용): **기저율이 100%가 아닌 가장 큰 k** = "
          f"{f'{rec} (창 {2 * rec + 1}턴 · 기저율 {base_rate[rec]:.1f}%)' if rec else '없음 — 사다리 전 구간에서 기저율 100%'}")
    print("     ⚠️ 이 줄은 **권고이지 채택이 아니다.** k를 고정하는 것은 이 라운드의 일이 아니다.")

    indep = sum(1 for t in trans if t["basis"] != "구간사건")
    print(f"\n  예외율 {exc_rows}/{len(trans)} (100%)")
    print("  ⚠️ **여전히 상한 추정치다.** 창을 좁혀도 '가까이 있었다'가 '그 사건 때문'을")
    print("     뜻하지는 않는다. 낮게 나오면 확실한 신호이고, 높게 나와도 결백의 증거는 아니다.")
    print(f"  ⚠️ 그리고 이 하니스에서는 {len(trans) - indep}건이 **동어반복**이다 —")
    print("     플래그 근거가 `구간사건`인 전이는 여기서 재는 것과 같은 것을 두 번")
    print(f"     말한다. 독립적인 확인은 {indep}/{len(trans)}건(`note`·`같은세션사건`)이다.")
    print("  → 실사용에서 이 값이 **낮으면** LLM이 사건 없이 예외를 선언한다는 뜻이고,")
    print("     그때 규칙은 무의미하다 (ADR-014 후속 8 — 별도 판정자).")

    # ── 요약 ────────────────────────────────────────────────────────────
    print("\n" + "=" * W)
    print(f"  준수 {passed}/{len(trans)} · 차단 {blocked}/{len(ATTACKS)}"
          f" (행 {rows_added}건) · 21번째 "
          f"{'거부' if attack_blocked else '🔴 통과'} · stale {total_stale}"
          f" · narrative_exception {exc_rows} · 동시발생률 ±k "
          + "·".join(f"{k}:{hits[k]}/{len(trans)}" for k in COINCIDENCE_K))
    print(f"  🔴 판정 — 주입 {delta['exclude_all'][0]}회(exclude_all) →"
          f" {delta['transition_warn'][0]}회(transition_warn) ·"
          f" 제외 {delta['exclude_all'][1]} → {delta['transition_warn'][1]} ·"
          f" ADR-013:{ADR013_LINE} 대조 {'✅' if anchor_ok else '🔴'}")
    print("=" * W)

    m.db.close()
    if os.path.exists(dbf):
        os.remove(dbf)

    # 🔄 `anchor_ok`를 생존 조건에 넣는다 (단계 S3). 대조값이 재현되지 않으면
    #    이 파일이 찍은 델타는 귀속할 수 없는 두 수이고, 그것을 초록으로 넘기면
    #    다음 사람이 «판정했다»고 읽는다.
    alive = (passed == len(trans) and blocked == len(ATTACKS)
             and rows_added == len(ATTACKS) and attack_blocked
             and total_stale > 0 and exc_rows == len(trans) and anchor_ok)
    return 0 if alive else 1


if __name__ == "__main__":
    sys.exit(main())
