# -*- coding: utf-8 -*-
"""
transition_regen_probe.py — **관계 단계 전이가 다이제스트를 다시 만들 이유가 있는가.**

## 무엇을 재나

`_propagate_transition`은 전이 한 번에 digest 키 **전량**(`lifetime` + `session:*`)을
`전이:` 사유로 stale에 민다(I5). 그러면 다음 세션 경계의 `regenerate_stale`이 그
전부를 다시 만든다 — 세션 요약은 **원본 턴**에서, lifetime은 세션 요약에서.
그런데 두 생성 함수 어느 쪽도 `stage`를 입력으로 받지 않는다(`summarize.py`에 그
낱말이 0건). 입력이 같고 `temperature 0 · seed 고정`이면 재생성은 **같은 바이트를
다시 만드는 비용**일 수 있다. **그것을 추정하지 않고 잰다.**

  A  세션 요약 24건(S01–S24) + lifetime 1건을 만든다 — **lifetime이 재료와 맞는 상태**
  ↓  대장 궤적의 첫 합법 전이를 `apply_meta`로 낸다
  B  `regenerate_stale` 1회 — 🔴 **B의 호출은 전부 라이브여야 한다** (캐시 적중이면
     바이트 동일이 공짜로 나온다 — 그 실행은 무효로 멈춘다)
  대조  키마다 **본문 바이트**와 **프롬프트 바이트**를 따로 본다. 본문이 달라도
        프롬프트가 같으면 차이의 자리는 `stage`가 아니라 생성기다 — 그 둘을 한
        열로 뭉개면 «무엇이 달랐나»를 못 적는다.

## 🔴 사전 등록은 값을 보기 전에 박았다 — 첫 화면에 찍는다

`PREREG`는 오케스트레이터 문장 그대로다. 판정 규칙은 그것 하나이고, 위 «프롬프트
대조»는 **판정을 바꾸지 않는다** — 다르면 «다른 자리가 무엇인가»를 적는 재료다.

## 체크포인트

A의 생성은 `%TEMP%`의 캐시에 남긴다(정지로 죽어도 앞 생성을 안 잃는다). B는 캐시를
**안 쓴다** — `regenerate_stale`은 태그를 안 넘기고, 그래서 캐시를 탈 수 없다.
결과는 `TRANSITION_REGEN.json`에 남고, 그 파일이 있으면 **ollama 0회**로 같은 표를
다시 찍는다(대조를 그 기록에서 다시 계산한다). 없고 ollama도 없으면 **77(SKIP)** —
통과가 아니다(G1).

재현: `PYTHONIOENCODING=utf-8 python -B experiments/transition_regen_probe.py`
      (`--live`면 기록이 있어도 다시 잰다)
"""
import json
import os
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "prototype"))
sys.path.insert(0, HERE)

import yaml                                                # noqa: E402
import llm                                                 # noqa: E402
import memory                                              # noqa: E402
import soak                                                # noqa: E402
import summarize                                           # noqa: E402
from memory import Memory, session_kind                    # noqa: E402

W = 78
SKIP_CODE = 77
CHAT = soak.CHAT

# ── 🔴 사전 등록 (값 보기 전 · 문장 그대로) ─────────────────────────────
PREREG = ("재생성 결과가 바이트 동일하면 «전이 → 다이제스트 전파»는 오늘의 구현에서"
          " 근거가 없다. 한 자리라도 다르면 근거가 있고, 그 다른 자리가 무엇인지가"
          " 이 라운드의 결과다.")

# 설계 상수 — 값 보기 전에 고정했다. N과 같은 수를 쓰는 이유: «24세션이면 전이당
# N+1회»가 이 저장소가 적은 산술이고, 그 산술을 **그 규모에서** 실측으로 바꾼다.
N_SESSIONS = memory.DIGEST_KEEP_SESSIONS
RESULT_PATH = os.path.join(HERE, "data", "TRANSITION_REGEN.json")
GEN_CACHE = os.path.join(tempfile.gettempdir(), "omc-w2-t1-genA.json")


def _corpus():
    rows = [json.loads(l) for l in
            open(os.path.join(ROOT, "eval", "corpus", "corpus.jsonl"),
                 encoding="utf-8")]
    with open(os.path.join(ROOT, "eval", "fact-ledger.yaml"),
              encoding="utf-8") as f:
        ledger = yaml.safe_load(f)
    return rows, ledger


def _bounds(rows):
    out = {}
    for r in rows:
        a, b = out.get(r["session"], (r["seq"], r["seq"]))
        out[r["session"]] = (min(a, r["seq"]), max(b, r["seq"]))
    return out


class _Tap:
    """
    `summarize._generate`를 감싸 **논리 호출**을 적는다 — 프롬프트·본문·라이브 여부.

    `llm.generate`가 아니라 여기를 감싸는 이유: 캐시 적중은 `llm.generate`에 닿지
    않아서 거기서는 **프롬프트를 못 본다.** 그런데 A의 프롬프트가 있어야 B와 대조한다.
    물리 호출(재시도 포함)은 `llm.generate` 쪽 계수기가 따로 센다.
    """

    def __init__(self):
        self.phase, self.calls, self.physical = None, [], 0

    def __enter__(self):
        self._g, self._raw = summarize._generate, llm.generate
        tap = self

        def gen(prompt, tag=None):
            text, usage = tap._g(prompt, tag=tag)
            tap.calls.append({"phase": tap.phase, "prompt": prompt,
                              "text": text, "live": usage is not None,
                              "usage": usage})
            return text, usage

        def raw(prompt):
            tap.physical += 1
            return tap._raw(prompt)

        summarize._generate, llm.generate = gen, raw
        return self

    def __exit__(self, *e):
        summarize._generate, llm.generate = self._g, self._raw
        return False


def _key_of(prompt):
    """프롬프트 → digest 키. 세션 프롬프트는 머리에 키를 싣고, lifetime은 안 싣는다."""
    head = "[대화 — 세션 "
    if head in prompt:
        return prompt.split(head, 1)[1].split(" ·", 1)[0]
    return "lifetime"


def measure_live():
    """A → 전이 → B. 결과 dict를 돌려준다. ollama가 필요하다."""
    rows, ledger = _corpus()
    bounds = _bounds(rows)
    sids = sorted(bounds)[:N_SESSIONS]
    arc = ledger["relationship_arc"]
    first = arc[1]                                 # 대장 궤적의 첫 합법 전이
    t_seq = bounds[first["at"]][0]

    tmp = tempfile.mkdtemp(prefix="w2-t1-")
    saved = (summarize.CACHE_PATH, summarize.GEN_TIMEOUT)
    summarize.CACHE_PATH, summarize.GEN_TIMEOUT = GEN_CACHE, 300
    stalls0 = summarize.STALL_COUNT
    # 🔄 wave3 — 이 측정이 재는 것은 **옛 전파**(전이 → digest 전량 stale → 재생성)다.
    #    기본값은 이제 그것을 끈다(`memory.TRANSITION_PROPAGATES_DIGEST`). 켜지 않고
    #    다시 재면 B가 0건이 되어 «무효»로 끝난다 — 옛 경로를 이름으로 켜고, 되돌린다.
    saved_switch = memory.TRANSITION_PROPAGATES_DIGEST
    memory.TRANSITION_PROPAGATES_DIGEST = True
    try:
        m = Memory(os.path.join(tmp, "t1.db"))
        soak.seed(m)
        soak.ingest(m, rows, ledger, timed=False)
        m.db.execute("UPDATE relationship SET stage=?, affinity=? WHERE chat_id=?",
                     (arc[0]["stage"], arc[0]["affinity"], CHAT))
        m.db.commit()
        with _Tap() as tap:
            tap.phase = "A"
            for sid in sids:
                a, b = bounds[sid]
                summarize.session_digest(m, CHAT, sid, from_seq=a, to_seq=b,
                                         tag=f"w2-t1:A:{sid}")
            summarize.rewrite_lifetime(m, CHAT, tag="w2-t1:A:lifetime")
            phys_a = tap.physical

            m.apply_meta(CHAT, t_seq, {"state_delta": {"stage": first["stage"],
                                                       "affinity": first["affinity"]},
                                       "narrative_event": True})
            stale = [(r["derived_kind"], r["derived_key"], r["reason"])
                     for r in m.db.execute(
                         "SELECT derived_kind, derived_key, reason FROM stale"
                         " WHERE chat_id=? ORDER BY derived_kind, derived_key",
                         (CHAT,))]

            tap.phase = "B"
            out = summarize.regenerate_stale(m, CHAT)
            phys_b = tap.physical - phys_a
        m.db.close()
    finally:
        summarize.CACHE_PATH, summarize.GEN_TIMEOUT = saved
        memory.TRANSITION_PROPAGATES_DIGEST = saved_switch
        shutil.rmtree(tmp, ignore_errors=True)

    return {
        "runtime": llm.runtime_info(),
        "sessions": sids,
        "transition": {"from": arc[0]["stage"], "to": first["stage"], "seq": t_seq},
        "stale": stale,
        "regen": {"ok": out["ok"], "failed": [list(x) for x in out["failed"]]},
        "calls": [{k: c[k] for k in ("phase", "prompt", "text", "live", "usage")}
                  for c in tap.calls],
        "physical": {"A": phys_a, "B": phys_b},
        "stalls": summarize.STALL_COUNT - stalls0,
    }


# ── 대조 — 다른 자리가 «전이»가 아니라 «생성기»인지 가른다 ─────────────
#
# 판정은 위 사전 등록 하나로 끝났다. 이 대조는 판정을 바꾸지 않고, 사전 등록이
# 요구한 «그 다른 자리가 무엇인가»를 적는 재료다. **값 보기 전에 고정한 순서:**
#   C1  S01 프롬프트를 **연달아 세 번**      — 서버의 접두 캐시가 통째로 맞는 조건
#   C2  S02 프롬프트 한 번 → S01 프롬프트 한 번 — 캐시가 다른 프롬프트로 덮인 조건
# 프롬프트는 기록(A)의 것을 바이트 그대로 쓴다. `summarize`를 거치지 않으므로 DB도
# 캐시도 없다 — `llm.generate`를 곧장 부른다.
CONTROL_PLAN = (("C1-1", "session:S01"), ("C1-2", "session:S01"),
                ("C1-3", "session:S01"), ("C2-pre", "session:S02"),
                ("C2", "session:S01"))


# C1·C2를 보고 **한 번 더** 고정한 대조(값을 본 뒤라 판정이 아니라 설명이다):
#   C1·C2가 전부 B와 같고 A만 다르며, 기록의 `prompt_eval_cached_count`가 A는 3~50 tok ·
#   B는 «프롬프트 길이 − 1» tok이었다 — 즉 A는 콜드 prefill, B는 웜 캐시였다.
#   C3  모델을 내려(`keep_alive=0`) 캐시를 비운 뒤 S01 한 번 — **A와 같으면** 본문은
#       «프롬프트 × 서버 캐시 상태»의 함수이고, 셋째 값이 나오면 그 설명은 틀렸다.
def unload_model():
    import urllib.request
    body = json.dumps({"model": llm.LLM_MODEL, "keep_alive": 0}).encode("utf-8")
    req = urllib.request.Request(f"{llm.OLLAMA_HOST}/api/generate", body,
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read()).get("done_reason")


def measure_control3(res):
    a = {_key_of(c["prompt"]): c for c in res["calls"] if c["phase"] == "A"}
    why = unload_model()
    text = llm.generate(a["session:S01"]["prompt"])
    return {"label": "C3", "key": "session:S01", "unload": why, "text": text,
            "usage": llm.last_usage()}


def measure_control(res):
    a = {_key_of(c["prompt"]): c for c in res["calls"] if c["phase"] == "A"}
    out = []
    for label, key in CONTROL_PLAN:
        text = llm.generate(a[key]["prompt"])
        out.append({"label": label, "key": key, "text": text,
                    "usage": llm.last_usage()})
    return {"plan": [list(x) for x in CONTROL_PLAN], "outputs": out,
            "runtime": llm.runtime_info()}


def report_control(res):
    ctl = res.get("control")
    print("\n" + "-" * W)
    print("대조 — 같은 프롬프트를 다시 보내면 같은 바이트가 오는가 (S01 · 판정과 무관)")
    print("-" * W)
    if not ctl:
        print("  (기록 없음 — `--control`로 잰다)")
        return
    a = {_key_of(c["prompt"]): c for c in res["calls"] if c["phase"] == "A"}
    b = {_key_of(c["prompt"]): c for c in res["calls"] if c["phase"] == "B"}
    seq = ([("A", a["session:S01"]["text"]), ("B", b["session:S01"]["text"])]
           + [(o["label"], o["text"]) for o in ctl["outputs"]
              if o["key"] == "session:S01"])
    names = [n for n, _ in seq]
    print("  " + " " * 7 + "".join(f"{n:>7}" for n in names))
    for n1, t1 in seq:
        print(f"  {n1:<7}" + "".join(f"{('=' if t1 == t2 else '≠'):>7}" for _, t2 in seq))
    distinct = len({t for _, t in seq})
    cached = [o["usage"].get("prompt_eval_cached_count") if o["usage"] else None
              for o in ctl["outputs"]]
    print(f"  S01 본문 {len(seq)}개 중 서로 다른 것 {distinct}개 · 대조 호출의"
          f" prompt_eval_cached_count {cached}")

    def span(ph):
        v = [c["usage"].get("prompt_eval_cached_count") for c in res["calls"]
             if c["phase"] == ph and c["usage"] and _key_of(c["prompt"]) != "lifetime"]
        gap = [c["usage"]["prompt_eval_count"] - c["usage"]["prompt_eval_cached_count"]
               for c in res["calls"] if c["phase"] == ph and c["usage"]
               and _key_of(c["prompt"]) != "lifetime"]
        return min(v), max(v), min(gap), max(gap)
    a_lo, a_hi, a_glo, a_ghi = span("A")
    b_lo, b_hi, b_glo, b_ghi = span("B")
    print(f"  세션 24키의 서버 접두 캐시 적중: A {a_lo}–{a_hi} tok (새로 계산 {a_glo}–{a_ghi} tok)"
          f" · B {b_lo}–{b_hi} tok (새로 계산 {b_glo}–{b_ghi} tok)")
    print("  → 같은 프롬프트라도 **캐시 적중 길이가 다르면 본문이 달랐다.** 적중 길이가 같은"
          " 호출끼리는(B·C1·C2) 전부 같았고, 적중 3 tok(A)과 0 tok(C3)은 서로도 다르다.")
    print("    ⚠️ S01 한 키 · 7회의 관측이다 — 기제(부동소수 경로)는 확인하지 않았다.")


def compare(res):
    """기록에서 대조를 **다시 계산한다** — 기록된 판정을 믿지 않는다."""
    a = {_key_of(c["prompt"]): c for c in res["calls"] if c["phase"] == "A"}
    b = {_key_of(c["prompt"]): c for c in res["calls"] if c["phase"] == "B"}
    rows = []
    for k in sorted(set(a) | set(b), key=lambda x: (x == "lifetime", x)):
        ca, cb = a.get(k), b.get(k)
        if ca is None or cb is None:
            rows.append((k, None, None, None, None))
            continue
        same_p = ca["prompt"] == cb["prompt"]
        same_t = ca["text"] == cb["text"]
        first_diff = None
        if not same_t:
            first_diff = next((i for i, (x, y) in enumerate(zip(ca["text"], cb["text"]))
                               if x != y), min(len(ca["text"]), len(cb["text"])))
        rows.append((k, same_p, same_t, first_diff,
                     (len(ca["text"]), len(cb["text"]))))
    return rows, a, b


def banner():
    """**값보다 먼저** 찍는다 — 라이브 실행에서는 생성 로그가 이 뒤에 나온다."""
    print("=" * W)
    print("T1 — 관계 단계 전이가 다이제스트를 다시 만들 이유가 있는가")
    print("=" * W)
    print("\n🔴 사전 등록 (값 보기 전 · 문장 그대로):")
    print(f"   «{PREREG}»\n")


def report(res, source):
    print(f"\n출처: {source}")
    rt = res["runtime"]
    print(f"생성기: ollama {rt.get('ollama')} · {rt.get('model')} · digest "
          f"{str(rt.get('digest'))[:12]}… · temperature {llm.LLM_TEMPERATURE}"
          f" · seed {llm.LLM_SEED} · num_ctx {llm.LLM_NUM_CTX}")
    t = res["transition"]
    print(f"재료: 세션 {len(res['sessions'])}개 ({res['sessions'][0]}–"
          f"{res['sessions'][-1]}) · 전이 {t['from']}→{t['to']} @ seq {t['seq']}")

    # ── B가 라이브였는가 — 아니면 이 대조는 무효다 ──
    b_calls = [c for c in res["calls"] if c["phase"] == "B"]
    dead = [c for c in b_calls if not c["live"]]
    print(f"\nB 논리 호출 {len(b_calls)}건 · 그중 캐시 적중 {len(dead)}건"
          f" · 물리 호출(재시도 포함) A {res['physical']['A']} / B {res['physical']['B']}"
          f" · 정지 {res['stalls']}회")
    if dead or not b_calls:
        print("🔴 B에 캐시 적중이 있다 — 바이트 동일이 공짜로 나오는 실행이다. **무효.**")
        return 1

    dg = [s for s in res["stale"] if s[0] == "digest"]
    other = [s for s in res["stale"] if s[0] != "digest"]
    print(f"\n전이가 stale로 민 것: digest {len(dg)}키 · 그 밖 {len(other)}키"
          f" ({', '.join(f'{k}:{v}' for k, v, _ in other)})")
    print(f"regenerate_stale: ok {len(res['regen']['ok'])} · failed "
          f"{len(res['regen']['failed'])}")

    rows, a, b = compare(res)
    sess = [r for r in rows if r[0] != "lifetime"]
    life = [r for r in rows if r[0] == "lifetime"]

    def line(tag, rs):
        n = len(rs)
        p = sum(1 for r in rs if r[1])
        t = sum(1 for r in rs if r[2])
        print(f"  {tag:<10} 프롬프트 바이트 동일 {p}/{n} · 본문 바이트 동일 {t}/{n}")

    print("\n" + "-" * W)
    print("🔴 재생성 전후 바이트 대조 (분모 = 전이가 민 digest 키 중 A·B 둘 다 있는 것)")
    print("-" * W)
    line("세션", sess)
    line("lifetime", life)
    for k, sp, st, fd, ln in rows:
        if st is False or sp is False:
            print(f"    ✗ {k:<12} 프롬프트 {'같음' if sp else '다름'} · 본문 다름 · "
                  f"길이 A {ln[0]} / B {ln[1]}자 · 첫 차이 {fd}번째 글자")
            ta, tb = a[k]["text"], b[k]["text"]
            lo = max(0, fd - 12)
            print(f"        A …{ta[lo:fd + 24]!r}")
            print(f"        B …{tb[lo:fd + 24]!r}")
        if st is None:
            print(f"    ? {k:<12} A 또는 B에 없다 — 대조 불가")

    all_same = rows and all(r[2] for r in rows)
    report_control(res)
    print("\n" + "-" * W)
    print("전이당 LLM 호출 수 (이 실행에서 센 값)")
    print("-" * W)
    print(f"  B 논리 호출 {len(b_calls)}회 = 세션 {sum(1 for r in sess)}"
          f" + lifetime {len(life)} · 분모: 전이 **1회** · stale digest {len(dg)}키"
          f" (legacy `session` 키 0 — 이 DB에 없다)")

    print("\n" + "=" * W)
    if all_same:
        print("판정 (wave2 사전 등록): **바이트 동일** — «전이 → 다이제스트 전파»는 오늘의"
              " 구현에서 근거가 없다.")
    else:
        print("판정 (wave2 사전 등록): **한 자리 이상 다르다** — 근거가 있다. 다른 자리는 위 ✗"
              " 줄이다. **고치지 않는다.**")
        same_prompt_diff_text = sum(1 for r in sess if r[1] and r[2] is False)
        print(f"  다른 자리의 이름: 세션 {same_prompt_diff_text}/{len(sess)}키가 **프롬프트는"
              f" 바이트 동일하고 본문만 다르다** — `stage`는 입력에 없고(프롬프트 동일),")
        print("  차이를 만든 것은 생성기다. lifetime은 재료(세션 요약)가 바뀌어 프롬프트부터"
              " 다르다. 위 대조가 생성기 쪽을 한 칸 더 가른다.")
    print("  🔄 wave3: 이 사전 등록은 **발화할 수 없는 조건**이었다 — 본문 바이트 동일은 서버 캐시"
          " 상태가 같을 때만 나오고(F39 · `cache_state_repro.py`), 재생성은 정의상 캐시 상태가"
          " 다르다. 아래가 관측 가능한 기준으로 다시 박은 판정이다.")
    code = rejudge(rows)
    print("=" * W)
    return code


# ── 🔴 wave3 재판정 — 관측 가능한 기준 (값 보기 전에 `.omc/notepads/wave3`에 박았다) ──
PREREG_W3 = ("재생성 프롬프트가 바이트 동일하면 재생성에 새 정보가 0이다. 새 정보가 0인데"
             " 본문이 바뀌면 그것은 «갱신»이 아니라 표류다.")


def rejudge(rows):
    """
    판정 규칙: 세션 키 **전부**의 프롬프트가 동일하면 새 정보 0 → 전파에서 뺀다(표류 수를
    센다). 한 키라도 다르면 그 키에는 새 정보가 있다 → 빼지 않는다. 이 조건은 프롬프트
    바이트로 참/거짓이 된다 — 요약 프롬프트가 `stage`를 싣게 되면 «다름»으로 발화한다.
    """
    sess = [r for r in rows if r[0] != "lifetime" and r[1] is not None]
    same_p = sum(1 for r in sess if r[1])
    drift = sum(1 for r in sess if r[1] and r[2] is False)
    print(f"\n판정 (wave3 사전 등록): «{PREREG_W3}»")
    print(f"  세션 프롬프트 동일 {same_p}/{len(sess)} · 그중 본문이 바뀐 것(표류) {drift}")
    remove = bool(sess) and same_p == len(sess)
    print("  → 규칙: " + ("**새 정보 0 — 다이제스트를 전이 전파에서 뺀다.**" if remove else
                         "새 정보가 있는 키가 있다 — 이 규칙으로는 **빼지 않는다.**"))
    now = digest_keys_pushed_now()
    default = memory.TRANSITION_PROPAGATES_DIGEST
    print(f"  지금 코드에서 전이 1회가 stale로 미는 digest 키 (ollama 0회 · 대역 DB 세션 {N_SESSIONS}"
          f" + lifetime 1): 기본값(`TRANSITION_PROPAGATES_DIGEST = {default}`) **{now[default]}키**"
          f" · 스위치 켬 {now[True]}키 · 끔 {now[False]}키")
    print(f"  → 전이당 LLM 호출 — 옛 전파 {now[True]}회 / 지금 기본값 **{now[default]}회**"
          " (lifetime은 세션 경계가 새로고친다 — `regen_job.run` ③)")
    # 🔴 규칙과 코드가 어긋나면 운다 — 규칙이 «뺀다»인데 기본값이 아직 밀거나, 그 반대.
    if remove != (now[default] == 0):
        print("  🔴 **규칙과 기본값이 어긋난다** — 판정이 코드에 반영되지 않았다(또는 되돌려야 한다).")
        return 1
    return 0


def digest_keys_pushed_now():
    """지금 `memory.py`로 전이 1회를 내고 stale로 밀린 digest 키를 센다 — 스위치 두 값."""
    out = {}
    saved = memory.TRANSITION_PROPAGATES_DIGEST
    tmp = tempfile.mkdtemp(prefix="w3-keys-")
    try:
        for flag in (False, True):
            memory.TRANSITION_PROPAGATES_DIGEST = flag
            m = Memory(os.path.join(tmp, f"k{int(flag)}.db"))
            m.db.execute("INSERT INTO digest (chat_id, kind, content, covers_to_seq)"
                         " VALUES (?,?,?,?)", (CHAT, "lifetime", "요약", 0))
            for i in range(1, N_SESSIONS + 1):
                m.put_session_digest(CHAT, f"S{i:02d}", "요약",
                                     covers_from_seq=i * 10 - 9, covers_to_seq=i * 10)
            m._propagate_transition(CHAT, 10, "아는사이", "친구")
            out[flag] = m.db.execute(
                "SELECT COUNT(*) FROM stale WHERE chat_id=? AND derived_kind='digest'",
                (CHAT,)).fetchone()[0]
            m.db.close()
    finally:
        memory.TRANSITION_PROPAGATES_DIGEST = saved
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def main(argv):
    live = "--live" in argv
    banner()
    if "--control3" in argv:
        with open(RESULT_PATH, encoding="utf-8") as f:
            res = json.load(f)
        res["control"]["outputs"].append(measure_control3(res))
        with open(RESULT_PATH, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        return report(res, f"기록 `{os.path.relpath(RESULT_PATH, ROOT).replace(os.sep, '/')}` + 대조 C3 라이브")
    if "--control" in argv:
        # 기록 위에 대조만 더한다 — A·B는 다시 안 잰다.
        with open(RESULT_PATH, encoding="utf-8") as f:
            res = json.load(f)
        res["control"] = measure_control(res)
        with open(RESULT_PATH, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        return report(res, f"기록 `{os.path.relpath(RESULT_PATH, ROOT).replace(os.sep, '/')}` + 대조 라이브")
    if "--record" in argv:
        # 다른 기록을 같은 표로 다시 찍는다 (예: wave3의 재측정 `TRANSITION_REGEN_W3.json`).
        path = argv[argv.index("--record") + 1]
        with open(path, encoding="utf-8") as f:
            res = json.load(f)
        return report(res, f"기록 `{path}` — ollama 0회")
    if not live and os.path.exists(RESULT_PATH):
        with open(RESULT_PATH, encoding="utf-8") as f:
            res = json.load(f)
        code = report(res, f"기록 `{os.path.relpath(RESULT_PATH, ROOT).replace(os.sep, '/')}` — ollama 0회")
        w3 = os.path.join(HERE, "data", "TRANSITION_REGEN_W3.json")
        if os.path.exists(w3):
            # wave3가 **다시 뽑은** 기록 — 같은 대조를 다른 날의 생성에서. 전문은 `--record`.
            with open(w3, encoding="utf-8") as f:
                rows, _, _ = compare(json.load(f))
            s = [r for r in rows if r[0] != "lifetime"]
            print(f"\n다시 뽑은 기록 `experiments/data/TRANSITION_REGEN_W3.json` (wave3): 세션 프롬프트 동일"
                  f" {sum(1 for r in s if r[1])}/{len(s)} · 본문 동일 {sum(1 for r in s if r[2])}/{len(s)}"
                  f" · 표류 {sum(1 for r in s if r[1] and r[2] is False)}"
                  f"  (전문: `--record experiments/data/TRANSITION_REGEN_W3.json`)")
        return code
    if llm.runtime_info().get("ollama") is None:
        print(f"⏭️ ollama가 {llm.OLLAMA_HOST}에 없고 기록도 없다 — **77(SKIP)**."
              " 통과가 아니라 미측정이다 (G1).")
        return SKIP_CODE
    res = measure_live()
    # `--out 경로`면 기록을 **거기에** 쓴다 — 다시 재도 `run_all`이 읽는 기록과
    # 그 위에 선 대조(`cache_state_repro.py`의 프롬프트 · 실행을 건넌 대조)를 안 덮는다.
    out = argv[argv.index("--out") + 1] if "--out" in argv else RESULT_PATH
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    # A의 크래시 대비 캐시는 **성공한 뒤에** 지운다 — 남겨 두면 다음 `--live`의 A가
    # 캐시를 타서 «첫 생성»이 아니게 된다(대조 표의 A 칸이 뜻을 잃는다).
    if os.path.exists(GEN_CACHE):
        os.remove(GEN_CACHE)
    return report(res, "라이브 측정 (이 실행)")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
