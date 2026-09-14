# -*- coding: utf-8 -*-
"""
cache_state_repro.py — **같은 프롬프트가 같은 본문을 내는가는 서버 캐시 상태의 함수인가.** (F39)

## 무엇을 재나

`prototype/llm.py`는 `temperature 0 · seed 고정 · num_ctx 고정`으로 생성한다. 그
세 값이 같으면 본문이 같다고 이 저장소는 믿어 왔다. 앞 레인(wave2)의 전이 재생성
대조가 그 믿음과 맞지 않는 관측을 냈다 — 프롬프트 24/24 바이트 동일 · 본문 0/24.
이 파일은 그 관측을 **한 프롬프트 · 세 조건**으로 줄여 다시 뽑는다.

  A  웜    — 직전 요청이 **같은 프롬프트**다 (서버가 그 접두를 들고 있다)
  B  콜드  — 모델을 내린(`keep_alive=0`) 직후다 (서버가 아무것도 안 들고 있다)
  C  덮음  — 직전 요청이 **접두를 공유하지 않는 다른 프롬프트**다

프롬프트는 `TRANSITION_REGEN.json`에 기록된 세션 요약 프롬프트를 **바이트 그대로**
쓴다 — `summarize.session_digest`가 실제로 보낸 것이다. 생성 옵션은 `llm.py`의
기본값 그대로다(`raw_generate(prompt)`에 아무 옵션도 얹지 않는다). ⚠️ `qwen3`은
사고 모델이라 `num_predict`를 작게 주면 `<think>` 안에서 끝나 본문이 빈다 — 그래서
본문을 재는 호출에는 절대 주지 않는다. C의 «덮는» 요청만 1토큰으로 끊는다(그
요청은 본문이 아니라 서버 캐시를 바꾸려고 보낸다).

## 🔴 사전 등록 — 값 보기 전에 박았다 · 첫 화면에 찍는다

`PREREG`의 넷이 판정 규칙 전부다. 각 줄은 **기록의 어떤 필드를 세면 참/거짓이
되는지**를 같이 적는다 — 만족할 수 없는 조건을 등록하지 않으려고.

## 기록 · 재현

결과는 `CACHE_STATE_REPRO.json`에 남고, 그 파일이 있으면 **ollama 0회**로 판정을
기록에서 **다시 계산한다**(기록된 판정 문자열을 믿지 않는다). 기록 안의 본문에서
sha를 다시 뽑아 기록된 sha와 대조하고, 어긋나면 종료 1이다. 기록도 ollama도 없으면
77(SKIP) — 통과가 아니다(G1).

재현: `PYTHONIOENCODING=utf-8 python -B experiments/cache_state_repro.py`
      (`--live`면 기록이 있어도 다시 잰다 — 생성 11회 + 덮기 1회 · 언로드 6회)
"""
import hashlib
import json
import os
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "prototype"))

import llm                                                 # noqa: E402

W = 78
SKIP_CODE = 77
RESULT_PATH = os.path.join(HERE, "data", "CACHE_STATE_REPRO.json")
SOURCE_PATH = os.path.join(HERE, "data", "TRANSITION_REGEN.json")

# 이 측정은 **11434의 ollama 하나**만 본다. 같은 기기에 ollama가 모르는 llama
# 서버가 따로 떠 있을 수 있고, 그쪽으로 새면 «서버 캐시 상태»가 다른 서버의 것이
# 된다. `localhost`도 안 쓴다(F38 — 느린 거절 2초가 지연 열을 오염시킨다).
EXPECTED_HOST = "http://127.0.0.1:11434"

PREREG = (
    ("P1", "A·B·C 세 조건의 본문 sha가 **하나라도 다르다** — 기록의 `body_sha`를"
           " 세 호출(A1·B1·C1)에서 세어 서로 다른 값이 2개 이상이면 참"),
    ("P2", "그 세 호출의 `prompt_eval_count`는 **같다** — 세 값이 한 종류면 참"
           " (참이면 그 필드로는 이 차이를 못 본다)"),
    ("P3", "본문 sha는 «프롬프트 × `prompt_eval_cached_count`»의 함수다 — 같은 프롬프트"
           "·같은 적중 길이인 호출끼리 sha가 전부 같으면 참, 한 묶음에서라도 둘로 갈리면"
           " 거짓"),
    ("P4", "콜드 고정(매 생성 전 언로드)은 재현된다 — 언로드 직후 호출 셋(B1·B2·B3)의"
           " sha가 한 종류이고, 두 번째 프롬프트의 셋(B1′·B2′·B3′)도 한 종류면 참"),
)

# 순서는 값 보기 전에 고정했다. (라벨, 직전 조치, 프롬프트 키)
#   조치 "unload" = 모델을 내리고 `/api/ps`에서 빠진 것을 확인한 뒤 보낸다
#   조치 "other"  = 접두를 공유하지 않는 프롬프트(lifetime)를 1토큰으로 한 번 보낸 뒤
#   조치 None     = 아무것도 안 하고 곧장 보낸다
PLAN = (
    ("B1", "unload", "session:S01"),
    ("A1", None, "session:S01"),
    ("A2", None, "session:S01"),
    ("A3", None, "session:S01"),
    ("C1", "other", "session:S01"),
    ("B2", "unload", "session:S01"),
    ("B3", "unload", "session:S01"),
    ("B1′", "unload", "session:S12"),
    ("B2′", "unload", "session:S12"),
    ("B3′", "unload", "session:S12"),
    ("A1′", None, "session:S12"),
)
OTHER_KEY = "lifetime"


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _post(path, obj, timeout=120):
    req = urllib.request.Request(f"{llm.OLLAMA_HOST}{path}",
                                 json.dumps(obj).encode("utf-8"),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _loaded():
    with urllib.request.urlopen(f"{llm.OLLAMA_HOST}/api/ps", timeout=10) as r:
        return [m.get("name") for m in json.loads(r.read()).get("models", [])]


def unload():
    """모델을 내리고 `/api/ps`에서 사라질 때까지 기다린다. 걸린 벽시계 ms를 돌려준다."""
    t0 = time.perf_counter()
    _post("/api/generate", {"model": llm.LLM_MODEL, "keep_alive": 0})
    for _ in range(120):
        if llm.LLM_MODEL not in _loaded():
            return round((time.perf_counter() - t0) * 1000)
        time.sleep(0.5)
    raise RuntimeError(f"{llm.LLM_MODEL}이 60초 안에 `/api/ps`에서 안 빠졌다")


def prompts():
    """기록된 A 단계 프롬프트 — `summarize`가 실제로 보낸 바이트."""
    with open(SOURCE_PATH, encoding="utf-8") as f:
        rec = json.load(f)
    head = "[대화 — 세션 "
    out = {}
    for c in rec["calls"]:
        if c["phase"] != "A":
            continue
        p = c["prompt"]
        out[p.split(head, 1)[1].split(" ·", 1)[0] if head in p else "lifetime"] = p
    return out


def measure_live():
    P = prompts()
    calls = []
    for label, pre, key in PLAN:
        row = {"label": label, "pre": pre, "key": key, "prompt_sha": sha(P[key])}
        if pre == "unload":
            row["unload_ms"] = unload()
        elif pre == "other":
            raw = llm.raw_generate(P[OTHER_KEY], num_predict=1)
            row["other_usage"] = {k: raw.get(k) for k in
                                  ("prompt_eval_count", "prompt_eval_cached_count")}
        t0 = time.perf_counter()
        raw = llm.raw_generate(P[key])
        row["wall_ms"] = round((time.perf_counter() - t0) * 1000)
        body = llm.strip_think(raw.get("response", ""))
        row.update({
            "body": body, "body_sha": sha(body),
            "raw_sha": sha(raw.get("response", "")),
            "usage": {k: raw.get(k) for k in
                      ("prompt_eval_count", "prompt_eval_cached_count", "eval_count",
                       "done_reason", "load_duration", "prompt_eval_duration",
                       "eval_duration", "total_duration")},
        })
        calls.append(row)
        u = row["usage"]
        print(f"  {label:<4} {key:<12} 적중 {u['prompt_eval_cached_count']!s:>4} / "
              f"{u['prompt_eval_count']} tok · eval {u['eval_count']} · 본문 {len(body)}자"
              f" · sha {row['body_sha'][:8]} · 벽시계 {row['wall_ms']} ms", flush=True)
    return {"runtime": llm.runtime_info(), "host": llm.OLLAMA_HOST,
            "options": {"temperature": llm.LLM_TEMPERATURE, "seed": llm.LLM_SEED,
                        "num_ctx": llm.LLM_NUM_CTX},
            "plan": [list(x) for x in PLAN], "calls": calls,
            "measured_at": time.strftime("%Y-%m-%d %H:%M:%S")}


def banner():
    print("=" * W)
    print("F39 — 같은 프롬프트의 본문은 서버 캐시 상태의 함수인가")
    print("=" * W)
    print("\n🔴 사전 등록 (값 보기 전 · 기록의 어떤 필드로 참/거짓이 되는가):")
    for k, s in PREREG:
        print(f"   {k}  {s}")


def verify_record(res):
    """기록 안의 본문에서 sha를 다시 뽑는다. 어긋나면 그 기록으로는 판정 못 한다."""
    bad = [c["label"] for c in res["calls"] if sha(c["body"]) != c["body_sha"]]
    P = prompts()
    moved = [c["label"] for c in res["calls"] if sha(P[c["key"]]) != c["prompt_sha"]]
    return bad, moved


def judge(res):
    """판정을 기록에서 **다시 계산한다.** 돌려주는 것: {P#: (참/거짓, 근거 문자열)}."""
    by = {c["label"]: c for c in res["calls"]}
    u = lambda lab, f: by[lab]["usage"][f]                      # noqa: E731
    abc = ("A1", "B1", "C1")
    out = {}
    shas = {by[x]["body_sha"] for x in abc}
    out["P1"] = (len(shas) >= 2,
                 " · ".join(f"{x} {by[x]['body_sha'][:8]}" for x in abc)
                 + f" → 서로 다른 값 {len(shas)}개")
    pec = {u(x, "prompt_eval_count") for x in abc}
    out["P2"] = (len(pec) == 1,
                 " · ".join(f"{x} {u(x, 'prompt_eval_count')}" for x in abc)
                 + f" → {len(pec)}종 (적중 길이는 "
                 + " · ".join(f"{x} {u(x, 'prompt_eval_cached_count')}" for x in abc) + ")")
    groups = {}
    for c in res["calls"]:
        groups.setdefault((c["key"], c["usage"]["prompt_eval_cached_count"]),
                          set()).add(c["body_sha"])
    split = {k: v for k, v in groups.items() if len(v) > 1}
    out["P3"] = (not split,
                 " · ".join(f"{k[0][-3:]}@{k[1]}→{len(v)}종"
                            for k, v in sorted(groups.items(), key=lambda kv: (kv[0][0], str(kv[0][1])))))
    b1 = {by[x]["body_sha"] for x in ("B1", "B2", "B3")}
    b2 = {by[x]["body_sha"] for x in ("B1′", "B2′", "B3′")}
    out["P4"] = (len(b1) == 1 and len(b2) == 1,
                 f"S01 콜드 3회 {len(b1)}종 · S12 콜드 3회 {len(b2)}종")
    return out


def cost(res):
    """콜드 고정의 대가 — 생성 한 번마다 모델을 다시 올리는 시간."""
    by = {c["label"]: c for c in res["calls"]}
    cold = [c for c in res["calls"] if c["pre"] == "unload"]
    warm = [c for c in res["calls"] if c["pre"] is None]
    ms = lambda ns: ns / 1e6                                     # noqa: E731
    med = lambda xs: sorted(xs)[len(xs) // 2]                    # noqa: E731
    return {
        "n_cold": len(cold), "n_warm": len(warm),
        "load_ms_cold": med([ms(c["usage"]["load_duration"]) for c in cold]),
        "load_ms_warm": med([ms(c["usage"]["load_duration"]) for c in warm]),
        "unload_ms": med([c["unload_ms"] for c in cold]),
        "prompt_ms_cold": med([ms(c["usage"]["prompt_eval_duration"]) for c in cold]),
        "prompt_ms_warm": med([ms(c["usage"]["prompt_eval_duration"]) for c in warm]),
        "wall_ms_cold": med([c["wall_ms"] + c["unload_ms"] for c in cold]),
        "wall_ms_warm": med([c["wall_ms"] for c in warm]),
        "eval_ms_per_tok": med([ms(c["usage"]["eval_duration"]) / c["usage"]["eval_count"]
                                for c in res["calls"]]),
        "_by": by,
    }


def report(res, source):
    print(f"\n출처: {source}")
    rt = res["runtime"]
    o = res["options"]
    print(f"생성기: ollama {rt.get('ollama')} · {rt.get('model')} · digest "
          f"{str(rt.get('digest'))[:12]}… · temperature {o['temperature']} · seed {o['seed']}"
          f" · num_ctx {o['num_ctx']} · 호스트 {res['host']} · {res.get('measured_at')}")

    bad, moved = verify_record(res)
    if bad:
        print(f"🔴 기록의 본문과 sha가 어긋난다: {bad} — 이 기록으로는 판정 못 한다.")
        return 1
    if moved:
        print(f"⚠️ 원천 프롬프트가 기록 뒤에 움직였다: {moved} — 판정은 기록 기준이다.")

    print("\n" + "-" * W)
    print("호출 (분모 = 생성 11회 · 같은 프롬프트 S01 7회 · S12 4회)")
    print("-" * W)
    print(f"  {'':<5}{'직전 조치':<9}{'키':<13}{'적중/프롬프트 tok':>18}{'eval':>6}"
          f"{'본문자':>7}  sha")
    for c in res["calls"]:
        u = c["usage"]
        pre = {"unload": "언로드", "other": "다른 것", None: "—"}[c["pre"]]
        print(f"  {c['label']:<5}{pre:<9}{c['key']:<13}"
              f"{u['prompt_eval_cached_count']!s:>9} / {u['prompt_eval_count']:<6}"
              f"{u['eval_count']:>6}{len(c['body']):>7}  {c['body_sha'][:12]}")

    print("\n" + "-" * W)
    print("판정 (사전 등록 · 기록에서 다시 계산)")
    print("-" * W)
    verdict = judge(res)
    for k, _ in PREREG:
        ok, why = verdict[k]
        print(f"  {k} {'참' if ok else '거짓'} — {why}")

    c = cost(res)
    print("\n" + "-" * W)
    print(f"콜드 고정의 대가 (중앙값 · 콜드 n={c['n_cold']} · 웜 n={c['n_warm']} · 단위 ms)")
    print("-" * W)
    print(f"  load_duration      콜드 {c['load_ms_cold']:>9.0f} · 웜 {c['load_ms_warm']:>7.0f}")
    print(f"  prompt_eval        콜드 {c['prompt_ms_cold']:>9.0f} · 웜 {c['prompt_ms_warm']:>7.0f}")
    print(f"  언로드 대기        {c['unload_ms']:>9.0f}")
    print(f"  벽시계(언로드 포함) 콜드 {c['wall_ms_cold']:>8.0f} · 웜 {c['wall_ms_warm']:>7.0f}"
          f"  ← 본문 길이(eval 토큰)가 호출마다 달라 이 줄은 생성 길이도 섞는다")
    print(f"  생성 속도          {c['eval_ms_per_tok']:.1f} ms/tok (11회 중앙값)")
    extra = (c["load_ms_cold"] - c["load_ms_warm"] + c["unload_ms"]
             + c["prompt_ms_cold"] - c["prompt_ms_warm"])
    print(f"  → 생성 1회당 더 드는 몫 ≈ 로드 {c['load_ms_cold'] - c['load_ms_warm']:.0f}"
          f" + 언로드 대기 {c['unload_ms']:.0f}"
          f" + 접두 재계산 {c['prompt_ms_cold'] - c['prompt_ms_warm']:.0f}"
          f" = {extra:.0f} ms (본문 길이와 무관한 몫만)")

    # C 조건이 실제로 세워졌는가. «다른 프롬프트»를 보냈어도 서버가 P의 접두를 따로
    # 들고 있으면 C는 A와 같은 조건이 된다 — 그때 C의 본문이 A와 같은 것은 «덮어도
    # 안 바뀐다»가 아니라 «덮이지 않았다»다. 적중 길이로 가른다.
    by = c["_by"]
    c_set = by["C1"]["usage"]["prompt_eval_cached_count"] != \
        by["A1"]["usage"]["prompt_eval_cached_count"]
    print(f"\n  C 조건이 세워졌는가: {'예' if c_set else '아니오'} — 덮기 요청 뒤 적중"
          f" {by['C1']['usage']['prompt_eval_cached_count']} tok (A1 "
          f"{by['A1']['usage']['prompt_eval_cached_count']} tok)."
          + ("" if c_set else " 서버가 P의 접두를 따로 들고 있었다 — **C는 이 실행에서 A와 같은"
             " 조건이었고, P1은 A↔B 한 쌍으로만 참이다.**"))
    cross_run(res)

    print("\n" + "=" * W)
    p1, p2, p3, p4 = (verdict[k][0] for k in ("P1", "P2", "P3", "P4"))
    print(f"F39 {'재현됨' if p1 else '재현 안 됨'} — 같은 프롬프트 · 같은 옵션에서 조건만 바꿔"
          f" 본문{'이 갈렸다' if p1 else '이 안 갈렸다'}."
          + (" `prompt_eval_count`는 그 차이를 못 본다. `prompt_eval_cached_count`는"
             " 한 실행 안의 콜드↔웜은 가르지만 실행을 건넌 차이(같은 적중 길이)는 못 가른다."
             if p2 else ""))
    print(f"콜드 고정: {'재현된다' if p4 else '재현 안 된다'}"
          + (f" — 대가는 생성 1회당 ≈ {extra / 1000:.1f}초" if p4 else ""))
    print("=" * W)
    return 0


def cross_run(res):
    """
    **사후 대조 — 판정이 아니다.** 값을 본 뒤에 세운 것이라 P3을 바꾸지 않는다.

    P3은 «한 실행 안에서» 적중 길이가 같으면 본문이 같은가를 물었다. 같은 프롬프트의
    본문이 앞 레인의 기록(`TRANSITION_REGEN.json`)에도 있으므로, **실행을 건너서도**
    그런가를 같은 기준으로 센다: (키, 적중 길이)가 같은 묶음에 기록 둘이 내놓은 본문이
    몇 종인가.
    """
    with open(SOURCE_PATH, encoding="utf-8") as f:
        w2 = json.load(f)
    head = "[대화 — 세션 "
    rows = []
    for ph in [c for c in w2["calls"] if head in c["prompt"]]:
        k = ph["prompt"].split(head, 1)[1].split(" ·", 1)[0]
        rows.append(("앞 레인", k, ph["usage"]["prompt_eval_cached_count"], sha(ph["text"])))
    for o in w2.get("control", {}).get("outputs", []):
        rows.append(("앞 레인", o["key"], o["usage"]["prompt_eval_cached_count"],
                     sha(o["text"])))
    for c in res["calls"]:
        rows.append(("이 기록", c["key"], c["usage"]["prompt_eval_cached_count"],
                     c["body_sha"]))
    mine = {(c["key"], c["usage"]["prompt_eval_cached_count"]) for c in res["calls"]}
    print("\n" + "-" * W)
    print("실행을 건넌 대조 (사후 · 판정 아님) — 앞 레인 기록과 (키, 적중 길이)가 같은 묶음")
    print("-" * W)
    for k, cached in sorted(mine, key=lambda x: (x[0], x[1])):
        grp = [r for r in rows if r[1] == k and r[2] == cached]
        src = {r[0] for r in grp}
        if len(src) < 2:
            continue
        kinds = {r[3] for r in grp}
        per = " · ".join(f"{s} {sum(1 for r in grp if r[0] == s)}회"
                         f" {sorted({r[3][:8] for r in grp if r[0] == s})}"
                         for s in ("앞 레인", "이 기록"))
        print(f"  {k} @ 적중 {cached:>3} tok → {len(kinds)}종  ({per})")
    print("  → 콜드(적중 0)는 두 실행이 같은 본문을 냈고, 웜(적중 = 길이−1)은 적중 길이가"
          " 같아도 실행마다 달랐다.")
    print("    본문은 적중 **길이**가 아니라 그 접두가 **어떻게 계산됐는가**(앞 요청의"
          " 모양)에 달린다 — 콜드만 그 경로가 하나다. ⚠️ 기제는 확인하지 않았다.")


def main(argv):
    banner()
    if "--live" not in argv and os.path.exists(RESULT_PATH):
        with open(RESULT_PATH, encoding="utf-8") as f:
            res = json.load(f)
        return report(res, f"기록 `{os.path.relpath(RESULT_PATH, ROOT).replace(os.sep, '/')}`"
                           " — ollama 0회")
    if llm.OLLAMA_HOST != EXPECTED_HOST:
        print(f"🔴 OLLAMA_HOST가 {llm.OLLAMA_HOST}다 — 이 측정은 {EXPECTED_HOST}만 쓴다.")
        return 1
    if llm.runtime_info().get("ollama") is None:
        print(f"⏭️ ollama가 {llm.OLLAMA_HOST}에 없고 기록도 없다 — **77(SKIP)**."
              " 통과가 아니라 미측정이다 (G1).")
        return SKIP_CODE
    print("\n라이브 측정:")
    res = measure_live()
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    return report(res, "라이브 측정 (이 실행)")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
