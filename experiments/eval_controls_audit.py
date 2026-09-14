# -*- coding: utf-8 -*-
"""
eval_controls_audit.py — ADR-009의 통제 조건을 **코드와 조립 출력**으로 대조한다. (API 불필요 · LLM 0회)

## 왜

[docs/17](../docs/17-gap-disposition.md) 검기타-6이 ADR-009 통제 조건 중 셋을 «확인하지 못했다»(❔3–❔5)고
남겼다 — 예산 4,000이 arm별로 다르다 · κ 교정 0건 · A3 Random-K가 검색 시뮬에만.
확인한 둘(반복 1회 · seed 없음)도 산문으로만 있었다. 산문은 다음 편집이 조건을 어겨도 울지 않는다.

## 무엇을 하나

1. 요구 목록을 **ADR 본문에서 뽑는다**(② 표의 arm ID · ③ 표의 예산·반복 · ④의 κ 표본).
   못 뽑으면 예외로 멈춘다 — 요구가 비면 모든 검사가 조용히 통과하기 때문이다.
2. 각 요구를 `quality_run.py`(실험 13의 하니스)와 `experiments/*.py` 전체에 대조한다.
   정적 검사는 **주석·문자열을 뺀 코드 토큰**만 본다(주석에 `4000`을 적어 통과하는 길을 막는다).
3. 예산·최근 턴은 **조립해서 잰다** — `build_arms`를 `%TEMP%` DB로 돌려 문항마다 프롬프트를
   만들고 글자수와 최근 턴 줄 수를 센다. 생성은 부르지 않는다.
4. 결과를 `KNOWN`(이 파일이 기록한 상태)과 비교해 **다르면 종료 1** — 새 위반도 울고,
   고쳐진 위반도 운다(ADR의 «미해결»을 고치라는 신호다).

## 실행

    PYTHONIOENCODING=utf-8 python -B experiments/eval_controls_audit.py
    PYTHONIOENCODING=utf-8 python -B experiments/eval_controls_audit.py --no-assemble   # 정적 검사만
    PYTHONIOENCODING=utf-8 python -B experiments/eval_controls_audit.py --exp-dir DIR --adr FILE  # 심은 위반용

⚠️ `quality_run.build_arms`는 DB를 `ROOT/prototype/.quality.db`에 만든다. 여기서는 모듈 전역
`ROOT`를 임시 디렉터리로 재바인딩하고 `finally`에서 되돌린다 — `prototype/`에 파일을 만들지 않는다.
"""
import argparse
import ast
import importlib.util
import io
import json
import os
import re
import shutil
import statistics
import sys
import tempfile
import tokenize
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "prototype"))
sys.stdout.reconfigure(encoding="utf-8")
W = 78

ADR_PATH = ROOT / "docs" / "adr" / "ADR-009-evaluation-design.md"

# 무작위 arm의 이름 — `arms_sim.py`가 쓰는 두 철자와 그 변형
RANDOM_ARM = re.compile(r"Random-K|arm_random|random_k", re.I)
# LLM 생성을 **실제로 부르는** 파일. `gen_corpus.generate`(템플릿)는 LLM이 아니라 뺐다.
GEN_CALL = re.compile(
    r"generateContent|/api/generate|/api/chat|\b(?:llm|LLM)\.(?:(?:raw_)?generate|measure_prompt)\("
    r"|from quality_run import[^\n]*\bgenerate\b|from llm import[^\n]*(?:generate|measure_prompt)")
# 🔴 바닥 (2026-09-11) — `digest_budget`이 `llm.raw_generate` 대신 `llm.measure_prompt`를 부르게 바뀌자
#    위 패턴이 그 파일을 못 물어 «생성 호출 파일»이 10 → 9로 **조용히** 줄었다. 판정(R2 교집합 없음)은
#    초록 그대로라 아무도 못 봤다 — 모집단이 줄어도 우는 검사가 없었다. 그래서 바닥을 둔다: 이보다
#    적으면 «못 봄»(패턴이 새 호출 이름을 못 문다)으로 떨어져 `KNOWN`과 달라지고 종료 1이다.
GEN_FILES_MIN = 10
KAPPA_NAME = re.compile(r"kappa|cohen|fleiss", re.I)
BUDGET_NAME = re.compile(r"budget", re.I)
ARM_ID = re.compile(r"^(A\d+R?|G\d+|C)\b")
A0_FAMILY = re.compile(r"^A0")         # ADR ③ «전 arm 동일, `A0` 제외»

# 이 파일이 기록한 상태 (2026-09-10 첫 실행의 출력). 바뀌면 종료 1.
KNOWN = {
    "R1 baseline 5종": "위반",
    "R2 Random-K는 검색 시뮬에만": "참",
    "R3 예산 동일": "위반",
    "R4a temperature 동일": "충족",
    "R4b seed 동일": "위반",
    "R5 최근 턴 수 동일": "위반",
    "R6 반복 3회": "위반",
    "R7 κ 계산 0건": "참",
}


# ── 요구 목록 — ADR 본문에서 뽑는다 ─────────────────────────────────
def _section(text, head, stop=r"^###? "):
    lines = text.splitlines()
    out, on = [], False
    for ln in lines:
        if ln.startswith(head):
            on = True
            continue
        if on and re.match(stop, ln):
            break
        if on:
            out.append(ln)
    return out


def adr_requirements(text):
    """요구가 하나라도 안 뽑히면 ValueError — 빈 요구는 검사를 항등 통과로 만든다."""
    arms = []
    for ln in _section(text, "### ② 통제 baseline"):
        m = re.match(r"^\|\s*\**`(\w+)`\**\s*\|", ln)
        if m:
            arms.append(m.group(1))
    budget = repeat = kappa = None
    for ln in _section(text, "### ③ 통제 조건"):
        if "컨텍스트 토큰 예산" in ln:
            m = re.search(r"(\d[\d,]*)", ln.split("|")[2])
            budget = int(m.group(1).replace(",", "")) if m else None
        if ln.startswith("| 반복"):
            m = re.search(r"(\d+)회", ln)
            repeat = int(m.group(1)) if m else None
    for ln in _section(text, "### ④ 심판 편향 통제"):
        m = re.search(r"표본\s*(\d+)~(\d+)건", ln)
        if m:
            kappa = (int(m.group(1)), int(m.group(2)))
    req = dict(arms=arms, budget=budget, repeat=repeat, kappa=kappa)
    missing = [k for k, v in req.items() if not v]
    if missing:
        raise ValueError(f"ADR-009에서 요구를 못 뽑았다: {missing}")
    return req


# ── 정적 검사 도구 ───────────────────────────────────────────────────
def code_tokens(src):
    """
    NAME·NUMBER 토큰만. 주석·문자열(f-문자열의 글자 조각 포함)은 이 두 타입을 내지 않으므로
    주석에 적은 `4000`이 검사를 속이지 못한다. 🔄 첫 판은 COMMENT·STRING을 따로 빼는 집합을
    두었는데, 변이 시험에서 그 집합의 COMMENT를 지워도 **아무 시험도 안 울었다**(등가 변이) —
    방어는 처음부터 이 타입 필터 하나였다. 죽은 방어를 방어처럼 두지 않으려고 걷어냈다.
    """
    return [(t.type, t.string, t.start[0])
            for t in tokenize.generate_tokens(io.StringIO(src).readline)
            if t.type in (tokenize.NAME, tokenize.NUMBER)]


def check_repeat(src, need):
    """`--repeat`의 argparse 기본값."""
    for node in ast.walk(ast.parse(src)):
        if (isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "add_argument"
                and node.args and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "--repeat"):
            for kw in node.keywords:
                if kw.arg == "default" and isinstance(kw.value, ast.Constant):
                    v = kw.value.value
                    return ("충족" if v >= need else "위반",
                            f"quality_run.py:{node.lineno} `--repeat` 기본값 {v} (요구 {need})")
    return "못 봄", "`--repeat` 인자를 찾지 못했다"


def check_generation_config(src):
    """`generationConfig` 딕셔너리 리터럴 — 개수(=arm 공통 여부)와 seed 키."""
    cfgs = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and k.value == "generationConfig" \
                        and isinstance(v, ast.Dict):
                    keys = [kk.value for kk in v.keys if isinstance(kk, ast.Constant)]
                    cfgs.append((k.lineno, keys))      # 바깥 dict가 아니라 키의 줄
    if not cfgs:
        return ("못 봄", "`generationConfig` 없음"), ("못 봄", "`generationConfig` 없음")
    line, keys = cfgs[0]
    t = ("충족" if len(cfgs) == 1 and "temperature" in keys else "위반",
         f"`generationConfig` {len(cfgs)}곳(quality_run.py:{line}) — 모든 arm이 같은 "
         f"`generate`를 부른다 · 키 {keys}")
    s = ("충족" if all("seed" in k for _, k in cfgs) else "위반",
         f"quality_run.py:{line}의 키 {keys} — `seed` {'있음' if 'seed' in keys else '없음'}")
    return t, s


def check_budget_static(src, budget):
    toks = code_tokens(src)
    nums = [ln for tp, s, ln in toks if tp == tokenize.NUMBER
            and s.replace("_", "").isdigit() and int(s.replace("_", "")) == budget]
    names = [ln for tp, s, ln in toks if tp == tokenize.NAME and BUDGET_NAME.search(s)]
    return nums, names


# 이 감사와 그 시험은 패턴을 문자열로 **들고 있어서** 스스로를 문다(첫 실행에서 R2·R7이
# 자기 파일 때문에 거짓이 됐다). 그래서 이름으로 빼고, 뺀 것을 출력에 찍는다.
SELF = {"eval_controls_audit.py", "test_eval_controls_audit.py"}


def scan_dir(exp_dir):
    """파일마다 (생성 호출?, 무작위 arm 적중 줄, κ 계산 식별자 줄, κ 언급 줄(주석·문자열))."""
    rows = {}
    for p in sorted(Path(exp_dir).glob("*.py")):
        if p.name in SELF:
            continue
        src = p.read_text(encoding="utf-8")
        gen = bool(GEN_CALL.search(src))
        rnd = [i for i, ln in enumerate(src.splitlines(), 1) if RANDOM_ARM.search(ln)]
        try:
            toks = code_tokens(src)
        except (tokenize.TokenError, SyntaxError):
            toks = []
        kcode = sorted({ln for tp, s, ln in toks if tp == tokenize.NAME and KAPPA_NAME.search(s)})
        kment = [i for i, ln in enumerate(src.splitlines(), 1)
                 if "κ" in ln or KAPPA_NAME.search(ln)]
        rows[p.name] = dict(gen=gen, rnd=rnd, kcode=kcode, kment=kment)
    return rows


def check_random_k(rows):
    hit = {f for f, r in rows.items() if r["rnd"]}
    gen = {f for f, r in rows.items() if r["gen"]}
    both = sorted(hit & gen)
    if not hit:
        # 적중 0이면 «검색 시뮬에만»도 «어디에도 없다»도 이 패턴으로는 못 가른다
        return "못 봄", "무작위 arm 패턴 적중 파일 0 — 패턴이 낡았을 수 있다"
    if len(gen) < GEN_FILES_MIN:
        return "못 봄", (f"생성 호출 파일 {len(gen)}개 < 바닥 {GEN_FILES_MIN} — "
                        f"`GEN_CALL`이 새 호출 이름을 못 무는지 보라 {sorted(gen)}")
    return ("참" if not both else "거짓",
            f"패턴 적중 {sorted(hit)} · 생성 호출 파일 {len(gen)}개 {sorted(gen)}와의 "
            f"교집합 {both or '없음'}")


def check_kappa(rows):
    code = {f: r["kcode"] for f, r in rows.items() if r["kcode"]}
    ment = {f: r["kment"] for f, r in rows.items() if r["kment"]}
    return ("참" if not code else "거짓",
            f"코드 토큰의 `kappa|cohen|fleiss` {sum(map(len, code.values()))}곳 {code or ''}"
            f" · 주석·문자열 언급 {sum(map(len, ment.values()))}줄 {sorted(ment)}")


# ── 동적 검사 — 조립만 한다 ──────────────────────────────────────────
def load_eval():
    import yaml
    with open(ROOT / "eval" / "corpus" / "corpus.jsonl", encoding="utf-8") as f:
        corpus = [json.loads(l) for l in f]
    with open(ROOT / "eval" / "fact-ledger.yaml", encoding="utf-8") as f:
        ledger = yaml.safe_load(f)
    with open(ROOT / "eval" / "questions.yaml", encoding="utf-8") as f:
        qs = yaml.safe_load(f)["qa_questions"]
    return corpus, ledger, qs


def assemble(qr_path):
    """arm마다 문항별 (글자수, 최근 턴 줄 수). DB는 `%TEMP%`에서 만들고 지운다."""
    spec = importlib.util.spec_from_file_location("_qr_audit", qr_path)
    qr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(qr)
    corpus, ledger, qs = load_eval()
    roles = sorted({r["role"] for r in corpus})
    turn_line = re.compile(r"^(?:%s): " % "|".join(map(re.escape, roles)))
    tmp = tempfile.mkdtemp(prefix="evalctl_")
    os.makedirs(os.path.join(tmp, "prototype"))
    old, mem = qr.ROOT, None
    try:
        qr.ROOT = tmp                       # G13 — 재바인딩은 finally에서 되돌린다
        arms, mem, _ = qr.build_arms(corpus, ledger, qs)
        out = {}
        for name, fn in arms:
            ps = [fn(q) for q in qs]
            out[name] = dict(chars=[len(p) for p in ps],
                             turns=[sum(1 for ln in p.splitlines() if turn_line.match(ln))
                                    for p in ps])
    finally:
        qr.ROOT = old
        if mem is not None:
            mem.db.close()
        shutil.rmtree(tmp, ignore_errors=True)
    return out, len(qs)


def verdict_budget(asm):
    med = {a: statistics.median(v["chars"]) for a, v in asm.items()
           if not A0_FAMILY.match(a)}
    ratio = max(med.values()) / max(min(med.values()), 1)
    return ratio, med


def verdict_recent(asm):
    return {a: statistics.median(v["turns"]) for a, v in asm.items() if not A0_FAMILY.match(a)}


# ── 본체 ─────────────────────────────────────────────────────────────
def run(exp_dir=HERE, adr=ADR_PATH, do_assemble=True):
    req = adr_requirements(Path(adr).read_text(encoding="utf-8"))
    qr_path = Path(exp_dir) / "quality_run.py"
    src = qr_path.read_text(encoding="utf-8")
    res, notes = {}, []

    res["R6 반복 3회"] = check_repeat(src, req["repeat"])
    res["R4a temperature 동일"], res["R4b seed 동일"] = check_generation_config(src)

    nums, names = check_budget_static(src, req["budget"])
    static_ok = bool(nums or names)
    notes.append(f"예산 정적: 코드 토큰의 `{req['budget']}` {len(nums)}곳 · `budget` 식별자 "
                 f"{len(names)}곳 (주석·문자열 제외)")

    rows = scan_dir(exp_dir)
    res["R2 Random-K는 검색 시뮬에만"] = check_random_k(rows)
    res["R7 κ 계산 0건"] = check_kappa(rows)

    if do_assemble:
        asm, nq = assemble(qr_path)
        ids = {m.group(1) for a in asm if (m := ARM_ID.match(a))}
        miss = [a for a in req["arms"] if a not in ids]
        res["R1 baseline 5종"] = ("충족" if not miss else "위반",
                                 f"요구 {req['arms']} · `build_arms` {sorted(ids)} · 없음 {miss}")
        ratio, med = verdict_budget(asm)
        res["R3 예산 동일"] = ("충족" if static_ok and ratio <= 1.10 else "위반",
                             f"코드에 예산 {'있음' if static_ok else '없음'} · A0 계열 제외 "
                             f"arm 글자수 중앙값 max/min {ratio:.2f}배 (기준 1.10)")
        rec = verdict_recent(asm)
        res["R5 최근 턴 수 동일"] = ("충족" if len(set(rec.values())) == 1 else "위반",
                                  "A0 계열 제외 arm의 최근 턴 줄 수 중앙값 "
                                  + " · ".join(f"{a.split()[0]} {v:g}" for a, v in rec.items()))
        return req, res, notes, (asm, nq)
    return req, res, notes, None


def print_report(req, res, notes, asm_pack):
    print("=" * W)
    print("ADR-009 통제 조건 감사 — 요구 목록 대 코드 (LLM 0회)")
    print("=" * W)
    print(f"\n요구 (ADR-009 본문에서 뽑음): arm {req['arms']} · 예산 {req['budget']:,} "
          f"(A0 제외 전 arm 동일) · 반복 {req['repeat']}회 · κ 표본 {req['kappa'][0]}~"
          f"{req['kappa'][1]}건\n")
    if asm_pack:
        asm, nq = asm_pack
        print(f"조립 실측 — 문항 {nq}개 × arm {len(asm)}개 · 글자수(프롬프트 전체) · "
              f"최근 턴 줄 수 · `memory.ntok`(글자×1.5) 추정")
        print(f"  {'arm':<24}{'글자 min':>9}{'중앙값':>8}{'max':>7}{'ntok 중앙값':>12}{'최근 턴':>8}")
        import memory
        for a, v in asm.items():
            c = sorted(v["chars"])
            med = statistics.median(c)
            print(f"  {a:<24}{c[0]:>9}{med:>8g}{c[-1]:>7}{memory.ntok('x' * int(med)):>12}"
                  f"{statistics.median(v['turns']):>8g}")
        print("  ⚠️ ntok은 qwen3에서 2.07배 과대계상으로 실측된 추정이고 Gemini 토크나이저는 "
              "안 쟀다 — 판정은 **글자수의 비**로만 한다(척도 무관).\n")
    for n in notes + [f"스캔에서 뺀 파일(패턴을 문자열로 든 자기 자신): {sorted(SELF)}"]:
        print("  · " + n)
    print()
    diff = []
    print(f"  {'검사':<30}{'상태':<6}{'기록':<6} 근거")
    for k in sorted(res):
        st, why = res[k]
        kn = KNOWN.get(k, "—")
        flag = "" if st == kn else "  🔴 기록과 다르다"
        if st != kn:
            diff.append(k)
        print(f"  {k:<30}{st:<6}{kn:<6} {why}{flag}")
    lost = [k for k in KNOWN if k not in res]
    return diff, lost


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp-dir", default=str(HERE))
    ap.add_argument("--adr", default=str(ADR_PATH))
    ap.add_argument("--no-assemble", action="store_true")
    a = ap.parse_args(argv)
    req, res, notes, asm = run(a.exp_dir, a.adr, not a.no_assemble)
    diff, lost = print_report(req, res, notes, asm)
    if a.no_assemble:
        lost = [k for k in lost if k not in ("R1 baseline 5종", "R3 예산 동일", "R5 최근 턴 수 동일")]
    print()
    if diff or lost:
        print(f"🔴 종료 1 — 기록(KNOWN)과 다른 검사 {diff} · 안 돈 검사 {lost}")
        print("   새 위반이면 고쳐라. 위반이 고쳐졌으면 KNOWN과 ADR-009 «미해결»을 함께 고쳐라.")
        return 1
    print("✅ 종료 0 — 기록된 상태 그대로다 (위반 목록이 줄지도 늘지도 않았다)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
