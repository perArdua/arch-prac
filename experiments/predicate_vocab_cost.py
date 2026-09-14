# -*- coding: utf-8 -*-
"""
predicate_vocab_cost.py — 술어 어휘 «코드 8·9종 대 docs/14 표 25종»의 **대가**를 값으로 잰다. (API 불필요 · LLM 0회)

## 왜

[docs/17](../docs/17-gap-disposition.md) 검기타-5 · [ADR-004](../docs/adr/ADR-004-write-path.md) «미해결»이
«표 밖 술어는 기본값(`many`/`mid`)으로 떨어지고 상시 주입에서 빠진다»를 **문장**으로 적었다.
그 문장에는 수가 없다 — 몇 종이, 몇 행이, 무엇을 잃는가.

## 무엇을 재나

두 코퍼스(`eval`·`eval2`)의 대장을 `soak.seed` + `soak.ingest`로 **무변경** 적재하고(임시 DB),
대장이 실제로 쓰는 술어를 세고, 표 밖 술어 때문에 생기는 일을 센다:

  ⓐ 대장이 «갱신»(`superseded_by`)이라 적은 쌍이 런타임에서 **병존**으로 끝난 수
  ⓑ 유효한 사실 중 `[알고 있는 것]`(상시 주입)에 **안 실린** 수 — `build_context`를 실제로 불러 센다
  ⓒ `fact.superseded_by`가 채워진 행 수 (대장의 기대 수와 나란히)

그리고 **25종으로 넓히면** 무엇이 움직이는지를 `Memory`의 세 클래스 속성을 런타임에 재바인딩해
잰다(합집합 · 대체 두 팔). 재바인딩은 `try/finally`로 되돌리고 **되돌렸는지 객체 동일성으로
확인**한다(G13). `prototype/`의 파일은 한 글자도 안 바뀐다.

    PYTHONIOENCODING=utf-8 python -B experiments/predicate_vocab_cost.py
"""
import json
import os
import re
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "prototype"))
sys.stdout.reconfigure(encoding="utf-8")
W = 78

import yaml  # noqa: E402
import memory as M  # noqa: E402
from memory import Memory  # noqa: E402
import soak  # noqa: E402

DOC14 = ROOT / "docs" / "14-extraction-prompts.md"
CORPORA = ("eval", "eval2")
ATTRS = ("PREDICATE_CARDINALITY", "PREDICATE_MUTABILITY", "PREDICATE_STANDING")


# ── docs/14 표 ────────────────────────────────────────────────────────
def doc14_table(text):
    """`| 술어 | 카디널리티 | 가변성 | **상시성** | 예시 |` 표. 못 뽑으면 예외."""
    rows, on = {}, False
    for ln in text.splitlines():
        if re.match(r"^\|\s*술어\s*\|\s*카디널리티", ln):
            on = True
            continue
        if on:
            if not ln.startswith("|"):
                break
            cells = [c.strip() for c in ln.strip("|").split("|")]
            m = re.match(r"^`([^`]+)`$", cells[0])
            if not m:
                continue                                  # 구분선
            card = cells[1].strip("*")
            mut = cells[2].strip("*")
            rows[m.group(1)] = dict(card=card, mut=mut, standing="✅" in cells[3])
    if not rows:
        raise ValueError("docs/14에서 술어 표를 못 찾았다")
    return rows


def arms(doc):
    """세 팔의 (카디널리티, 가변성, 상시성). 현행은 **지금 클래스에 붙은 객체 그대로**."""
    cur = {a: getattr(Memory, a) for a in ATTRS}
    d_card = {p: r["card"] for p, r in doc.items()}
    d_mut = {p: r["mut"] for p, r in doc.items()}
    d_std = {p for p, r in doc.items() if r["standing"]}
    union = (dict(d_card, **cur["PREDICATE_CARDINALITY"]),     # 겹치면 코드 값이 이긴다
             dict(d_mut, **cur["PREDICATE_MUTABILITY"]),
             set(cur["PREDICATE_STANDING"]) | d_std)
    return {
        "현행 (코드 8·8·9)": None,
        "합집합 (코드 ∪ docs/14)": union,
        "대체 (docs/14 25만)": (d_card, d_mut, d_std),
    }


def conflicts(doc):
    """코드와 docs/14가 **같은 술어에 다른 값**을 주는 곳 — 합집합에서 어느 쪽이 이기나가 문제될 자리."""
    out = []
    for a, key in (("PREDICATE_CARDINALITY", "card"), ("PREDICATE_MUTABILITY", "mut")):
        for p, v in getattr(Memory, a).items():
            if p in doc and doc[p][key] != v:
                out.append((a, p, v, doc[p][key]))
    for p in Memory.PREDICATE_STANDING:
        if p in doc and not doc[p]["standing"]:
            out.append(("PREDICATE_STANDING", p, "상시", "—"))
    return out


# ── 한 코퍼스 × 한 팔 ────────────────────────────────────────────────
def load(name):
    base = ROOT / name
    with open(base / "corpus" / "corpus.jsonl", encoding="utf-8") as f:
        corpus = [json.loads(l) for l in f]
    with open(base / "fact-ledger.yaml", encoding="utf-8") as f:
        ledger = yaml.safe_load(f)
    with open(base / "questions.yaml", encoding="utf-8") as f:
        qs = yaml.safe_load(f).get("qa_questions") or []
    return corpus, ledger, qs


KNOWN_HEAD = re.compile(r"^\[알고 있는 것\]$")


def known_block(rendered):
    """렌더된 컨텍스트에서 `[알고 있는 것]` 블록의 줄들."""
    lines, on = [], False
    for ln in rendered.splitlines():
        if KNOWN_HEAD.match(ln):
            on = True
            continue
        if on:
            if ln.startswith("[") or not ln.strip():
                break
            lines.append(ln)
    return lines


def measure(name, arm_vals):
    corpus, ledger, qs = load(name)
    facts = ledger.get("facts", [])
    tmp = tempfile.mkdtemp(prefix="predcost_")
    saved = {a: getattr(Memory, a) for a in ATTRS}
    m = None
    try:
        if arm_vals is not None:                 # G13 — 재바인딩은 finally에서 되돌린다
            for a, v in zip(ATTRS, arm_vals):
                setattr(Memory, a, v)
        m = Memory(os.path.join(tmp, "p.db"))
        soak.seed(m)
        _, act = soak.ingest(m, corpus, ledger, timed=False)
        last = corpus[-1]["seq"]
        ctx = m.build_context(soak.CHAT, "오늘 좀 피곤하네", last)
        klines = known_block(ctx.render())
        rows = [dict(r) for r in m.db.execute(
            "SELECT fact_id, predicate, object, valid_until, superseded_by FROM fact"
            " WHERE chat_id=?", (soak.CHAT,)).fetchall()]
        std = set(Memory.PREDICATE_STANDING)
    finally:
        for a in ATTRS:
            setattr(Memory, a, saved[a])
        if m is not None:
            m.db.close()
        shutil.rmtree(tmp, ignore_errors=True)
    for a in ATTRS:                               # 되돌렸는가 — 값이 아니라 **객체**로 본다
        assert getattr(Memory, a) is saved[a], f"{a} 복원 실패"

    by_id = {f["id"]: f for f in facts}
    pairs = [(f["id"], f["superseded_by"]) for f in facts if f.get("superseded_by")]
    # ⓐ 대장이 «갱신»이라 한 쌍 — 새 쪽의 런타임 동작
    a_rows = [(old, new, by_id[new]["predicate"], act.get(new)) for old, new in pairs]
    # ⓑ 대장 기준 유효한 사실(무효화 표시 없음)이 상시 블록에 실렸나 — 블록의 줄은
    #    «· 지우의 {술어}: {값}»이라 (술어, 값)으로 대조한다
    shown = set()
    for ln in klines:
        mm = re.match(r"^· 지우의 (.+?): (.*)$", ln)
        if mm:
            shown.add((mm.group(1), mm.group(2)))
    valid = [f for f in facts if not f.get("invalidated_at")]
    b_rows = [(f["id"], f["predicate"], (f["predicate"], f.get("object", f["text"])) in shown)
              for f in valid]
    # ⓒ superseded_by가 채워진 행
    c_filled = sum(1 for r in rows if r["superseded_by"] is not None)
    # 곁가지: 대장이 무효화했다고 적은 옛 값이 런타임에서 아직 유효한가
    stale_alive = [f["id"] for f in facts if f.get("invalidated_at")
                   and any(r["predicate"] == f["predicate"] and r["object"] == f.get("object")
                           and r["valid_until"] is None for r in rows)]
    # 문항 쪽: 근거가 상시 블록에 **없는** 사실뿐인 문항(→ 검색으로만 닿는다)
    fact_ids = set(by_id)
    shown_ids = {fid for fid, _, ok in b_rows if ok}
    q_fact = [q for q in qs if set(q.get("evidence") or []) & fact_ids]
    q_retr_only = [q["id"] for q in q_fact
                   if not (set(q.get("evidence") or []) & shown_ids)]
    return dict(facts=facts, act=act, a=a_rows, b=b_rows, c=c_filled,
                c_expect=len(pairs), stale=stale_alive, klines=klines,
                q_fact=[q["id"] for q in q_fact], q_retr=q_retr_only, std=std,
                inject=M.INJECT_KNOWN_FACTS)


# ── 출력 ──────────────────────────────────────────────────────────────
def vocab_table(name, facts, doc):
    card = Memory.PREDICATE_CARDINALITY
    std = Memory.PREDICATE_STANDING
    cnt = Counter(f["predicate"] for f in facts)
    out_card = {p: n for p, n in cnt.items() if p not in card}
    out_std = {p: n for p, n in cnt.items() if p not in std}
    out_doc = {p: n for p, n in cnt.items() if p not in doc}
    print(f"\n── {name}: 대장 사실 {len(facts)}행 · 서로 다른 술어 {len(cnt)}종 " + "─" * 20)
    print(f"  {'술어':<14}{'행':>3}  {'CARD/MUT(8)':<14}{'STANDING(9)':<13}{'docs/14(25)':<12}")
    for p, n in sorted(cnt.items(), key=lambda x: (-x[1], x[0])):
        dd = doc.get(p)
        print(f"  {p:<14}{n:>3}  {card.get(p, '—기본 many/mid'):<14}"
              f"{'상시' if p in std else '—':<13}"
              f"{(dd['card'] + '/' + dd['mut'] + ('/상시' if dd['standing'] else '')) if dd else '표에 없음':<12}")
    print(f"  → 코드 CARD/MUT 밖 {len(out_card)}/{len(cnt)}종 · {sum(out_card.values())}/{len(facts)}행"
          f"  |  STANDING 밖 {len(out_std)}/{len(cnt)}종 · {sum(out_std.values())}/{len(facts)}행"
          f"  |  docs/14 표 밖 {len(out_doc)}/{len(cnt)}종 · {sum(out_doc.values())}/{len(facts)}행")
    return out_card, out_std, out_doc


def main():
    doc = doc14_table(DOC14.read_text(encoding="utf-8"))
    print("=" * W)
    print("술어 어휘 8·9 대 25 — 대가를 값으로 (LLM 0회 · 임시 DB · prototype 무변경)")
    print("=" * W)
    print(f"\ndocs/14 표 {len(doc)}행 (상시 ✅ {sum(r['standing'] for r in doc.values())}) · "
          f"코드 CARDINALITY {len(Memory.PREDICATE_CARDINALITY)} · MUTABILITY "
          f"{len(Memory.PREDICATE_MUTABILITY)} · STANDING {len(Memory.PREDICATE_STANDING)}")
    only_code = sorted(set(Memory.PREDICATE_STANDING) - set(doc))
    print(f"코드에만 있고 표에 없는 술어: {only_code} · 표 25 중 코드 CARD에 있는 것 "
          f"{sum(1 for p in doc if p in Memory.PREDICATE_CARDINALITY)}")
    cf = conflicts(doc)
    print(f"코드와 표가 같은 술어에 다른 값을 주는 곳: {len(cf)} {cf or ''}")

    AR = arms(doc)
    res = {}
    for name in CORPORA:
        corpus, ledger, _ = load(name)
        vocab_table(name, ledger.get("facts", []), doc)
        res[name] = {an: measure(name, av) for an, av in AR.items()}

    print("\n" + "=" * W)
    print("대가 ⓐⓑⓒ — 코퍼스 × 팔 (분모를 옆에)")
    print("=" * W)
    for name in CORPORA:
        base = res[name]["현행 (코드 8·8·9)"]
        print(f"\n── {name}  (상시 주입 스위치 INJECT_KNOWN_FACTS={base['inject']})")
        print(f"  현행 `[알고 있는 것]` 블록 그대로: {base['klines']}")
        for an, r in res[name].items():
            a_co = [x for x in r["a"] if x[3] != "superseded"]
            b_miss = [x for x in r["b"] if not x[2]]
            print(f"  [{an}]")
            print(f"    ⓐ 대장 «갱신» 쌍 중 병존 등(≠superseded)으로 끝남 {len(a_co)}/{len(r['a'])}"
                  f"  {[(o, n, p, act) for o, n, p, act in r['a']]}")
            print(f"    ⓑ 유효 사실 중 상시 블록에 안 실림 {len(b_miss)}/{len(r['b'])}"
                  f"  술어별 {dict(Counter(p for _, p, _ in b_miss))}")
            print(f"       상시 블록 {len(r['klines'])}줄 · 근거가 사실인 문항 {len(r['q_fact'])}개 중 "
                  f"근거가 상시 블록에 하나도 없는 문항 {len(r['q_retr'])}개 {r['q_retr']}")
            print(f"    ⓒ superseded_by 채워진 행 {r['c']} (대장이 기대하는 수 {r['c_expect']})"
                  f"  · 대장이 무효화한 옛 값이 런타임에서 아직 유효 {r['stale']}")

    print("\n" + "=" * W)
    print("25종으로 넓히면 무엇이 움직이나 — 현행 대비 차")
    print("=" * W)
    for name in CORPORA:
        base = res[name]["현행 (코드 8·8·9)"]
        for an, r in res[name].items():
            if r is base:
                continue
            da = sum(x[3] != "superseded" for x in r["a"]) - sum(x[3] != "superseded" for x in base["a"])
            db = sum(not x[2] for x in r["b"]) - sum(not x[2] for x in base["b"])
            dc = r["c"] - base["c"]
            moved = [fid for fid in r["act"] if r["act"][fid] != base["act"].get(fid)]
            print(f"  {name:<6}{an:<24} Δⓐ {da:+d} · Δⓑ {db:+d} · Δⓒ {dc:+d} · "
                  f"upsert 동작이 바뀐 사실 {moved or '없음'} · 상시 블록 "
                  f"{len(base['klines'])}→{len(r['klines'])}줄")
    print("\n⚠️ ⓑ의 «안 실림»에는 설계상 상시가 아닌 술어(docs/14 상시 — 표시)도 들어 있다 — "
          "술어별 칸으로 가른다.")
    print("⚠️ `soak.ingest`는 모든 사실의 주어를 «지우»로 넣는다(eval2도) — 술어 동작에는 무관하다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
