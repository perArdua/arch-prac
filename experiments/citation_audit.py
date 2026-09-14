# -*- coding: utf-8 -*-
"""
citation_audit.py — `file:line` 인용이 아직도 그 줄을 가리키는가. (API 불필요 · 후속 11)

## 왜

이 저장소는 표류한 `file:line`을 **일곱 번** 출하했다.
`memory.py:115`→`:157` · `docs/14:132`→`:139`(세 곳) · 레인 B의 `+9` 일괄 표류 ·
그리고 레인 D의 인용 수리가 **오프셋을 8줄 작게** 잡아 만든 일곱 개.
마지막 것은 **검증을 통과한 뒤에** 마감 레인에서 발견됐다 — 그 검증이 본 것은
*"줄이 존재하는가"*뿐이었기 때문이다.

`consistency_audit.py`는 `*.md`에서 CLAIM 정규식으로 **숫자**를 뜬다.
`file:line`은 **애초에 보지 않는다**(G18). 그래서 이 방어는 다섯 번 사람에게
맡겨졌고 다섯 번 다 사람이 **우연히** 발견했다. 이것이 그 기계화 가능한 절반이다.

## 방법

인용을 열거하지 않는다 — **연다.**

1. `*.md`·`*.py`에서 `path.py:NNN` / `path.py:NNN-MMM` / `docs/NN:NNN` /
   백틱 안의 **맨 `:NNN`**(같은 파일 또는 같은 줄 앞의 경로에 붙인다)을 찾는다.
2. 인용 **주변 산문**에서 기대 토큰을 뽑는다 — 백틱 안의 식별자·리터럴,
   그리고 그로부터 만든 `def name`/`class Name`. **자동 추론은 오탐이 많으므로**
   (설계 메모 ①) 백틱 안에 있고 대상 파일에 **실제로 존재하는** 토큰만 쓴다.
3. 그 토큰이 인용된 줄 근처에 있으면 `확인`, 파일 안 다른 곳에 있으면
   `의심`(어디로 옮겼는지 함께 찍는다), 뽑을 토큰이 없으면 `해석 불가`.

**`확인`은 "이 줄에 그 토큰이 있다"는 뜻이지 "인용이 옳다"는 뜻이 아니다.**
파일은 인용이 무엇을 주장했는지 기록하지 않는다. 이 도구는 그것을 모른다.
🔴 **줄이 존재한다는 것만 확인하고 `확인`으로 찍는 일은 하지 않는다** — 그것이
정확히 레인 D의 일곱 건을 통과시킨 검증이다.

## 무엇을 제외하는가 — 그리고 왜 파일 단위가 아닌가

제외는 두 층이다. **파일 층**(스냅샷·마감된 레인 보고서·TIMELINE·`eval/`)은
*"이 파일 전체가 얼어 있다"*가 참인 곳만이고, **인용 층**(`RE_RECORDED`)은
*"이 인용 하나가 그때의 값이다"*가 인용 **바로 앞 표식**으로 선언된 곳만이다.

🔴 **살아 있는 계획서(`ralplan-*` · `open-questions*`)는 파일 층에 넣지 않는다.**
그것이 이 설계의 전부다. 그 파일들의 `§단계`·`§사전 조사` 절은 **살아 있는
코드를 가리키고**, 레인 D의 표류 일곱 건이 정확히 그런 자리에 살았다.
실측으로도 계획서의 의심 131건 중 **125건이 표식 없는 살아 있는 인용**이다 —
파일 단위 규칙은 그 125건을 전부 숨긴다. **모양(표 행 49 / 산문 83)으로도 못
가른다**: 양쪽에 기록과 살아 있는 주장이 섞여 있다.

그 대가는 **종료 코드가 계속 1**이라는 것이고, 이 도구는 그것을 감춘 적이 없다.
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
W = 78

# 인용된 줄에서 이만큼 안에 토큰이 있으면 맞은 것으로 본다.
# 산문은 블록의 **첫 줄**을 인용하는 버릇이 있고(`memory.py:735-758`),
# 그 첫 줄이 데코레이터/주석이면 실제 이름은 한두 줄 아래다.
NEAR = 2

# 식별자 토큰이 대상 파일에 이보다 자주 나오면 **닻이 아니다.**
# `name`·`data` 같은 것이 아무 줄에나 있어 `확인`을 공짜로 만든다.
# 리터럴(`{name:<24}` 꼴)은 그 자체로 좁으므로 상한이 더 느슨하다.
MAX_IDENT_HITS = 12
MAX_LITERAL_HITS = 40

# 범위 인용의 끝이 `def`/`class` 끝을 이만큼 넘는 것은 봐준다 (꼬리 빈 줄).
END_SLACK = 2

# ── 인용 형태 ────────────────────────────────────────────────────────────
# ① 확장자가 붙은 경로. G18 §기계적 검사 ①의 정규식을 그대로 쓴다.
RE_PATH = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"([A-Za-z_0-9./-]+\.(?:py|md|txt|json|jsonl|yaml|sql))"
    r":(\d+)(?:-(\d+))?")
# ② 이 저장소가 실제로 쓰는 **축약형** — `docs/14:143` · `docs/adr/ADR-010:55`.
#    확장자가 없어서 ①이 못 본다. 다섯 사례 중 셋이 이 형태였다.
RE_DOCS = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(docs/(?:adr/ADR-\d+|\d{2})[A-Za-z0-9_-]*)"
    r":(\d+)(?:-(\d+))?")
# ③ 맨 `:NNN`. **백틱 안에 있는 것만** 받는다 — 그러지 않으면 시각(`12:30`)과
#    비(`4:1`)와 표 구분자를 잔뜩 문다. verifier-r2-final:99가 지적한
#    `gate_sweep.py:85`의 `` `:170`·`:352` ``가 이 형태이고,
#    **파일 이름에 닻을 내린 정규식에게는 구조적으로 보이지 않는다.**
RE_BARE = re.compile(r"`:(\d+)(?:-(\d+))?`")
# 같은 줄 **앞쪽**의 경로 낱말 — 맨 `:NNN`이 붙을 곳.
# 백틱 **안 어디든** 본다. 통째로 경로인 span만 보면
# `` `git diff -U0 prototype/memory.py` `` 안의 경로를 놓치고, 그러면 맨 `:NNN`이
# 그 줄의 **엉뚱한 파일**에 붙는다 (실측: open-questions-r2.md:255).
RE_PATHTOK = re.compile(r"[A-Za-z_0-9./-]+\.(?:py|md|txt|json|jsonl|yaml|sql)"
                        r"(?::\d+(?:-\d+)?)?")
# 맨 `:NNN`이 앞 경로에 붙으려면 **바로 옆**이어야 한다 — 실측 예는
# `prototype/embedding.py:12`이다. 이 저장소의 `.md`에는 **줄 이동 대장 표**가
# 있고(`ralplan-retrieval-summary.md:2223` 꼴의 행), 거기서는 맨 번호가 앞 칸의
# 파일이 아니라 **제3의 파일**의 옛/새 번호다.
# 사이에 글자·숫자가 끼거나 3자를 넘으면 붙이지 않는다.
RE_GLUE = re.compile(r"^[^\w\n]{0,3}$")

RE_BACKTICK = re.compile(r"`([^`\n]{1,80})`")
RE_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
# 백틱 안이 **쉘 명령**이면 그 안의 낱말은 대상 파일의 닻이 아니다.
SHELL_WORDS = {"grep", "rg", "python", "python3", "git", "ls", "cat", "sed",
               "awk", "head", "tail", "wc", "diff", "find", "sqlite3", "echo",
               "pytest", "chmod", "mkdir", "rm", "cp", "mv", "sort", "uniq"}
# 예약어와 확장자는 닻이 아니다 — 대상 파일 어디에나 있다.
STOP_TOKENS = {"with", "for", "if", "else", "elif", "def", "class", "try",
               "except", "return", "import", "from", "and", "not", "None",
               "True", "False", "self", "str", "int", "dict", "list", "set",
               "print", "open", "file", "line", "text", "data", "name",
               ".md", ".py", "*.md", "*.py", ".txt", ".json"}


# ── 제외 ─────────────────────────────────────────────────────────────────
# `consistency_audit.py`의 TIMELINE 논리를 인용에 그대로 적용한다.
# 정상인 것을 빨갛게 만들면 아무도 감사를 안 본다.
#   baseline/**   **그때의 저장소를 얼려 둔 스냅샷**이다. 그 안의 인용은
#                 *"그때 그것이 어떠했는가"*이고 **낡는 것이 정상**이다.
#                 재-앵커링하면 스냅샷이 스냅샷이 아니게 된다 (설계 메모 ②).
#   notepads/**   레인이 작업 중에 적은 메모다. 같은 이유 (설계 메모 ②).
#   레인 보고서   `executor-*`·`verifier-*`·`critic-*`·`architect-*`·`planner-*`는
#                 **마감된 레인이 그 시점에 본 것**을 적은 보고서다. 고칠 대상이
#                 아니다 — 고치면 그 레인이 무엇을 봤는지가 지워진다.
#   TIMELINE      `consistency_audit.py:97-98`의 목록 그대로. 시간순 기록물.
#   eval/         A8으로 불변이다. 인용을 고치는 것도 편집이다.
EXCLUDE_DIRS = (".git/", "__pycache__/", "eval/",
                ".omc/plans/baseline/", ".omc/notepads/", ".omc/state/")
EXCLUDE_PREFIX = (".omc/plans/executor-", ".omc/plans/verifier-",
                  ".omc/plans/critic-", ".omc/plans/architect-",
                  ".omc/plans/planner-")
TIMELINE = {"PROGRESS.md", "docs/00-research-briefing.md",
            "docs/01-problem-and-hypotheses.md", "REPORT.md"}
EXCLUDE_SUFFIX = (".backup.md",)

# 파일 스스로 빠지는 표식. **합성 인용**을 담은 파일이 필요하다 —
# 이 감사기의 시험이 그것이다: 틀린 인용을 일부러 넣어야 감사기가 우는지 볼 수 있고,
# 그 인용들이 감사 대상이 되면 시험 파일이 영구 적자가 된다.
# 🔴 표식은 **빠져나가는 구멍**이므로 쓴 파일의 **이름을 전부 찍는다.**
#    보이지 않는 제외가 지난 여섯 건이 살아남은 방식이다.
# ⚠️ 조각내어 적는 것이 규정의 일부다 — 통째로 적으면 이 파일이 자기를 뺀다.
OPTOUT = "citation-" + "audit: 합성 인용"

EXCLUDE_WHY = [
    (".omc/plans/baseline/**", "얼려 둔 스냅샷 — 낡는 것이 정상이다 (설계 메모 ②)"),
    (".omc/notepads/**", "레인 작업 메모 — 같은 이유 (설계 메모 ②)"),
    (".omc/plans/{executor,verifier,critic,architect,planner}-*",
     "마감된 레인 보고서 — 그 시점에 본 것이고, 고치면 그것이 지워진다"),
    (".omc/state/** · __pycache__/** · .git/**", "생성물"),
    ("eval/**", "A8 불변 — 인용을 고치는 것도 편집이다"),
    ("PROGRESS.md · REPORT.md · docs/00 · docs/01",
     "시간순 기록물 — `consistency_audit.py:97-98`의 TIMELINE 그대로"),
    ("*.backup.md", "백업본"),
]

# ── 기록 표식 — 인용 **하나**를 빼는 유일한 규칙 ────────────────────────
# 이 저장소는 정정을 적을 때 낡은 번호를 `🔄 rev9 — 이전 `:NNN`` 꼴로
# **일부러 남긴다.** 그것은 표류가 아니라 기록이다.
# ⚠️ 아래 예시는 전부 `경로.py:NNN` 꼴로 적는다 — 이 파일도 감사 대상이라
#    **설명하려고 쓴 인용이 감사에 잡히면** 그것이 잡음이다.
#
# 🔴 **제외는 인용 하나에만 붙는다 — 파일에도 절에도 표 행에도 붙지 않는다.**
#    `consistency_audit.py`의 `TIMELINE`/`TIMELINE_PREFIX` 논리를 인용에 옮길 때
#    가장 쉬운 실수가 *"계획서니까 통째로 뺀다"*인데, 그것은 **진짜 표류를 숨긴다.**
#    실측: 계획서에 남은 의심 131건 중 **125건이 살아 있는 코드 인용**이고
#    (`§단계`·`§사전 조사`가 `prototype/**`·`experiments/**`를 가리키는 것들),
#    레인 D의 표류 일곱 건이 정확히 그런 자리에 살았다. 파일 단위 규칙은
#    그 125건을 전부 먹는다. **모양(표 행/산문)으로도 못 가른다** — 실측
#    49 표행 / 83 산문이고 양쪽에 기록과 살아 있는 주장이 섞여 있다.
#
# 그래서 가르는 것은 **인용 바로 앞에 붙은 표식** 하나뿐이다:
#   `이전`·`원래`·`과거`·`옛`·`당시`·`before`  — *"그때 그랬다"*
#   `rev1의`·`rev1은`·`rev1이`                — *"revN이 적은 인용"*
# ⚠️ `\s*[`*_(\[]{0,4}$`가 규정의 일부다. 이것이 **없던 판은 백틱이 낀
#    `이전 `경로.py:NNN`` 꼴을 한 번도 못 봤다** — `RE_PATH`는 백틱 **뒤**에서
#    매치를 시작하므로 앞 14자가 항상 `` ` ``로 끝나기 때문이다.
#    맨 `:NNN` 꼴(매치가 백틱을 포함한다)에서만 발화하던, 반쯤 죽은 규칙이었다.
#    🔴 이 저장소의 **일곱 번째** "발화할 수 없는 검사"였고, 고친 뒤 실제로
#       그 형태를 물었다(`ralplan-retrieval-summary.md`의 `번호만 고쳤다**(이전 …`).
# 🔴 **하중을 받는 것은 끝의 `$`다 — 앞 14자 창이 아니다.** 변이 시험이
#    그것을 드러냈다: 창을 `앞 14자`에서 `줄 앞 전체`로 넓혀도 **아무 시험도
#    울지 않고 실측 출력도 안 바뀐다.** `$`가 이미 *"표식이 인용에 붙어 있을
#    것"*을 요구하기 때문이다. `$`를 빼면 그때 누출이 일어난다(변이5).
#    → 창 폭은 **두 번째 방어이고, 지금은 놀고 있다.** 그렇게 적어 둔다.
#      *"좁아서 안전하다"*는 설명이 실은 다른 것이 지키고 있는 안전이면,
#      그 설명을 믿고 창을 넓히는 다음 사람이 조용히 누출을 연다.
# ⚠️ 그래도 창을 넓히지 않는다 — `$` 하나에 전부를 걸지 않는다.
#    넓히면 `rev1은 *"…"*고 적었다. **아니다.** `경로.py:NNN`가…` 처럼
#    revN을 **반박하는** 산문의 살아 있는 인용이 표식 하나 차이로 걸린다.
RE_RECORDED = re.compile(
    r"(?:이전|원래|과거|옛|당시|before|rev\d+\s*(?:의|은|이))"
    r"\s*[`*_(\[]{0,4}$")


def is_excluded(rel: str) -> bool:
    if rel in TIMELINE:
        return True
    if rel.endswith(EXCLUDE_SUFFIX):
        return True
    if any(seg in rel for seg in EXCLUDE_DIRS):
        return True
    return rel.startswith(EXCLUDE_PREFIX)


class Cite:
    """인용 하나. `verdict`는 확인 / 의심 / 해석 불가 셋 중 하나다."""

    def __init__(self, src, src_line, raw, path, a, b, how, before=""):
        self.src, self.src_line, self.raw = src, src_line, raw
        self.path, self.a, self.b, self.how = path, a, b, how
        # 낡은 번호를 **일부러** 남긴 자리는 표류가 아니라 기록이다.
        # 🔴 표식을 **문자열로 들고 있는다** — 세기만 하면 어느 인용이 빠졌는지
        #    아무도 모르고, 그것이 지난 여섯 건이 살아남은 방식이다.
        m = RE_RECORDED.search(before)
        self.marker = m.group(0).strip(" `*_([") if m else ""
        self.target = None
        self.verdict = "해석 불가"
        self.reason = ""
        self.token = ""
        self.conf = 0          # 높을수록 "틀렸다"에 대한 확신이 크다
        self.where = ""

    @property
    def label(self):
        rng = f"{self.a}-{self.b}" if self.b else f"{self.a}"
        return f"{self.path or '?'}:{rng}"


def collect(root: Path):
    """대상 파일에서 인용을 전부 긁는다. (긁는 것은 검증이 아니다 — 아래가 검증이다)"""
    cites, scanned, excluded, optout = [], [], [], []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix not in (".md", ".py"):
            continue
        rel = p.relative_to(root).as_posix()
        if is_excluded(rel):
            excluded.append(rel)
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if OPTOUT in text:
            optout.append(rel)
            continue
        scanned.append(rel)
        lines = text.splitlines()
        for i, line in enumerate(lines, 1):
            spans = []

            def pre(m, line=line):
                return line[max(0, m.start() - 14):m.start()]

            for m in RE_PATH.finditer(line):
                spans.append(m.span())
                cites.append(Cite(rel, i, m.group(0), m.group(1),
                                  int(m.group(2)),
                                  int(m.group(3)) if m.group(3) else None,
                                  "경로", pre(m)))
            for m in RE_DOCS.finditer(line):
                if any(s <= m.start() < e for s, e in spans):
                    continue          # 확장자 붙은 축약형을 두 번 세지 않는다
                spans.append(m.span())
                cites.append(Cite(rel, i, m.group(0), m.group(1),
                                  int(m.group(2)),
                                  int(m.group(3)) if m.group(3) else None,
                                  "축약", pre(m)))
            for m in RE_BARE.finditer(line):
                prev = [q for q in RE_PATHTOK.finditer(line)
                        if q.end() <= m.start()]
                glue = prev and RE_GLUE.match(line[prev[-1].end():m.start()])
                if glue:
                    tgt, how = prev[-1].group(0).split(":")[0], "맨:옆경로"
                elif p.suffix == ".py" and prev:
                    # 코드 주석은 문단이 짧고 대상이 하나다 — 같은 줄 앞 경로면 족하다.
                    tgt, how = prev[-1].group(0).split(":")[0], "맨:앞경로"
                elif p.suffix == ".py":
                    tgt, how = rel, "맨:자기파일"   # `gate_sweep.py:85`의 `:187`
                else:
                    # 🔴 `.md`에서 **바로 옆이 아닌** 맨 `:NNN`은 풀지 않는다.
                    #    이 저장소의 `.md`에서 그 형태는 대부분 **줄 이동 대장**의
                    #    옛/새 번호이거나 산문 한복판의 제3 파일 참조다.
                    #    붙여서 맞히기보다 **모른다고 말하는 쪽**이 옳다 —
                    #    틀린 앵커는 진짜 표류를 잡음에 묻는다.
                    c = Cite(rel, i, m.group(0), None, int(m.group(1)),
                             int(m.group(2)) if m.group(2) else None,
                             "맨:대상불명", pre(m))
                    c.reason = "바로 옆에 경로가 없어 무엇을 가리키는지 알 수 없다"
                    cites.append(c)
                    continue
                cites.append(Cite(rel, i, m.group(0), tgt, int(m.group(1)),
                                  int(m.group(2)) if m.group(2) else None,
                                  how, pre(m)))
    # 🔴 표식이 붙은 인용을 **여기서 버리지 않는다.** 예전 판은 버렸고, 그래서
    #    출력이 줄 수 있는 것이 개수 하나뿐이었다. 판정까지 받게 한 뒤
    #    따로 찍으면 독자가 *"무엇이 눌렸는가"*를 본다 — 그것이 제외를
    #    보이게 만드는 유일한 방법이다.
    recorded = [c for c in cites if c.marker]
    return cites, scanned, excluded, (recorded, optout)


def resolve(root: Path, src: str, path: str, index=None):
    """인용된 경로 -> 실제 파일.

    ⚠️ **제외 목록은 여기에 적용하지 않는다.** 제외는 인용을 *어디서 읽는가*의
    규칙이지 *어디를 가리키는가*의 규칙이 아니다. 스냅샷은 얼어 있으므로
    오히려 **가장 안전한 대상**이다.
    """
    if path is None:
        return None, "없음"
    if (root / path).is_file():
        return root / path, "ok"
    # ① 인용한 파일 옆 (`README.md` 꼴)
    sib = (root / src).parent / path
    if sib.is_file():
        return sib, "ok"
    # ② 꼬리 일치 — 저장소는 경로를 **짧게 줄여** 적는다
    #    (`baseline/after-step2/README.md` · 맨 `summary_local.py`).
    tail = [q for q in (index or []) if q.as_posix().endswith("/" + path)]
    if len(tail) > 1:
        # 스냅샷이 트리를 통째로 복제하므로 맨 파일 이름은 거의 항상 여럿을 문다.
        # 산문이 맨 이름을 쓸 때 뜻하는 것은 **살아 있는 파일**이다.
        live = [q for q in tail if not is_excluded(q.as_posix())]
        tail = live or tail
    if len(tail) == 1:
        return root / tail[0], "ok"
    if len(tail) > 1:
        return None, "모호"            # 고르지 않는다 — 판정하지 않는다
    # ③ 축약형 `docs/14` -> `docs/14-*.md`
    hits = sorted((root / path).parent.glob(Path(path).name + "-*.md"))
    if len(hits) == 1:
        return hits[0], "ok"
    return None, ("모호" if hits else "없음")


def candidates(line: str, raw: str):
    """인용 주변 산문에서 기대 토큰을 뽑는다. (설계 메모 ① — 백틱 안만 본다)

    반환: [(kind, text)] — 좁은 것부터.
    """
    out, seen = [], set()

    def add(kind, t):
        t = t.strip()
        if len(t) < 3 or t in seen or t in STOP_TOKENS:
            return
        if not re.search(r"[A-Za-z_]", t):    # 순수 한글/숫자는 닻이 아니다
            return
        seen.add(t)
        out.append((kind, t))

    for m in RE_BACKTICK.finditer(line):
        span = m.group(1).strip()
        if span in raw or RE_PATH.search(span) or RE_DOCS.search(span):
            continue                          # 인용 자신
        if re.fullmatch(r"[A-Za-z_0-9./-]+\.(?:py|md|txt|json|jsonl|yaml|sql)", span):
            continue                          # 그냥 파일 이름
        # 🔴 쉘 명령은 **닻이 아니다.** `` `grep -n "X" memory.py` ``에서 `grep`를
        #    뽑으면 그것이 대상 파일 어딘가에 있다는 이유로 엉뚱한 줄을 가리킨다
        #    (실측: `grep`가 `memory.py:888`을 물었다).
        if span.split()[0] in SHELL_WORDS or span.startswith("-"):
            continue
        # 리터럴은 **모양이 있는 것**만이다 (`{name:<24}` · `scored.sort` ·
        # `def gate`). 맨 낱말(`rel`)은 식별자 경로로 보내 밋밋함 검사를 받게 한다 —
        # 리터럴로 들어오면 그 검사를 우회해 `근처에 없다`를 공짜로 찍는다.
        if ((" " not in span or span.startswith(("def ", "class ")))
                and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", span)):
            add("리터럴", span)
        base = span.rstrip("()").split("(")[0]
        for ident in RE_IDENT.findall(base):
            # `Memory.gate`·`retrieve()` -> 파이썬 소스에 실제로 찍히는 형태로.
            # ⚠️ `Memory.gate`에서 `class Memory`를 만들면 **메서드를 가리킨 인용이
            #    클래스 선언 줄에서 어긋났다**고 보고한다. 대문자로 시작하는
            #    **낱개** 식별자일 때만 `class`를 만든다.
            if ident[0].isupper():
                if base == ident:
                    add("리터럴", f"class {ident}")
            else:
                add("리터럴", f"def {ident}")
            add("식별자", ident)
    return out


def occurrences(lines, kind, text):
    if kind == "식별자":
        pat = re.compile(r"\b" + re.escape(text) + r"\b")
        return [n for n, l in enumerate(lines, 1) if pat.search(l)]
    return [n for n, l in enumerate(lines, 1) if text in l]


def block_end(lines, a):
    """`a`가 **`def`/`class`를 여는 줄**이면 그것이 끝나는 줄. 아니면 None.

    범위 인용의 **끝 endpoint**를 볼 수 있는 유일한 구조 신호다 (설계 메모 ③).
    🔴 `if`/`for`/`with`는 **일부러 뺐다.** `gate_sweep.py:370-372`처럼
       *"이 세 줄"*을 가리키는 인용은 `if` 블록을 넘어가는 것이 정상이고,
       그것까지 물면 진짜 표류가 잡음에 묻힌다. 이름 붙은 단위(`def`·`class`)만
       *"여기서 끝난다"*고 말할 수 있다.
    """
    if not (1 <= a <= len(lines)):
        return None
    head = lines[a - 1]
    if not head.strip().endswith(":") or not re.match(r"\s*(def |class )", head):
        return None
    ind = len(head) - len(head.lstrip())
    end = a
    for n in range(a + 1, len(lines) + 1):
        l = lines[n - 1]
        if not l.strip():
            continue
        if len(l) - len(l.lstrip()) <= ind:
            break
        end = n
    return end


def judge(root: Path, c: Cite, cache: dict, index=None):
    """인용 하나를 판정한다. **줄이 존재하는지만 보고 확인으로 찍지 않는다.**"""
    if c.how == "맨:대상불명":
        return
    f, why = resolve(root, c.src, c.path, index)
    if why == "모호":
        # 같은 이름의 파일이 여럿이다. **고르면 조용히 틀린다** — 모른다고 말한다.
        c.reason = f"`{c.path}`가 저장소에 여럿 있어 어느 것인지 알 수 없다"
        return
    if f is None:
        c.verdict, c.conf = "의심", 100
        c.reason = "대상 파일이 저장소에 없다"
        return
    c.target = f.relative_to(root).as_posix()
    if c.target not in cache:
        cache[c.target] = f.read_text(encoding="utf-8").splitlines()
    lines = cache[c.target]
    n = len(lines)

    ends = [c.a] + ([c.b] if c.b else [])
    bad = [e for e in ends if not (1 <= e <= n)]
    if bad:
        c.verdict, c.conf = "의심", 90
        c.reason = f"줄 {', '.join(map(str, bad))}이 파일 끝({n}줄)을 넘는다"
        return
    if c.b and c.b < c.a:
        c.verdict, c.conf = "의심", 90
        c.reason = "범위가 거꾸로다"
        return

    # 범위 인용의 끝 endpoint — 시작이 블록을 여는 줄일 때만 볼 수 있다.
    tail = ""
    if c.b:
        e = block_end(lines, c.a)
        # SLACK: 마지막 빈 줄 하나쯤을 범위에 넣는 것은 표류가 아니다.
        if e is not None and c.b > e + END_SLACK:
            c.verdict, c.conf = "의심", 70
            c.reason = (f"범위 끝 :{c.b}이 `{lines[c.a - 1].strip()[:34]}`의 "
                        f"끝 :{e}을 넘는다")
            c.where = f"블록 {c.a}-{e}"
            return
        if e is not None:
            tail = f" · 끝 {'일치' if c.b == e else f'블록 안(:{e}까지)'}"

    src_line_here = c.src_line if c.target == c.src else None
    # 🆕 **다섯 번째 실명 기제 — 범위 인용의 «시작»은 검사되지 않았다.**
    #
    # 🔴 표본 측정이 실측으로 찾았다(`확인` 221건 중 118건을 손으로 열어 8건 오류).
    #    `docs/10`이 이전 `memory.py:1311-1334`로 `Memory.gate`를 가리킨다고 적었는데
    #    gate는 `prototype/memory.py:1007-1026`이다. **길이 24줄은 맞고 시작만 +22 밀렸다** — 레인 D의
    #    일괄 오프셋과 같은 지문이다. 그런데 옛 창 `[a-2, b+2]`는 범위 전체를 덮는
    #    **28줄짜리 그물**이라 `def gate`가 :1333에 있다는 사실이 두 범위를
    #    **구별하지 못한다.**
    #
    # 🔴 그리고 하나의 틀림이 두 방어를 동시에 끈다: 유일한 끝 검사 `block_end()`는
    #    **시작 줄이 블록을 열 때만** 발화하는데, 밀린 시작(이전 `:1311` = `r = self.db…`)은
    #    블록을 안 열어 `None`을 돌려주고 **끝 검사도 같이 꺼진다.**
    #
    # → **범위 인용은 닻이 시작 근처에도 있어야 한다.** 끝 근처에만 있으면 그것은
    #    「이 범위가 무엇을 여는가」를 말해 주지 않는다. 단일 줄 인용에는 영향이 없다
    #    (`c.b`가 없으면 두 창이 같다).
    lo, hi = (c.a - NEAR), ((c.b or c.a) + NEAR)
    lo_a, hi_a = (c.a - NEAR), (c.a + NEAR)      # 범위의 **시작** 창
    start_miss = None                           # 시작 근처에 닻이 없던 첫 후보
    best = None
    stem = Path(c.target).stem
    for kind, text in candidates(lines_of(root, c, cache), c.raw):
        if text == stem:
            continue          # 모듈 자기 이름 — 파일 어디에나 있고 닻이 아니다
        hits = occurrences(lines, kind, text)
        if src_line_here in hits:
            hits.remove(src_line_here)        # 인용을 적은 그 줄은 증거가 아니다
        cap = MAX_IDENT_HITS if kind == "식별자" else MAX_LITERAL_HITS
        if not hits or len(hits) > cap:
            continue
        # 🔴 여러 곳에 있는 **밋밋한** 식별자는 닻이 아니다. `rel`·`embed`가
        #    "근처에 없다"는 것은 아무 뜻도 없다 — 그것들은 파일 전체에 있다.
        #    구별되는 모양(`_` · 대문자 · 긴 이름)일 때만 여러 히트를 허용한다.
        if (kind == "식별자" and len(hits) > 1
                and "_" not in text and text.islower() and len(text) < 8):
            continue
        near = [h for h in hits if lo <= h <= hi]
        if near:                              # 하나라도 맞으면 맞은 것이다
            # 🆕 범위 인용이면 **시작 근처에도** 닻이 있어야 한다 (다섯 번째 기제).
            # 🔴 **첫 후보에서 기각하면 오발화한다 — 실측으로 잡았다.**
            #    `memory.py:781-790`(`_roots`)는 **옳은데**, 후보 루프가 옆 산문의
            #    `_PARTICLE`(범위 안 :1060)을 먼저 만나 그 자리에서 기각하면
            #    시작에 맞는 닻 `_roots`(:1053)를 **시도조차 안 한다.**
            #    → 기각을 **미루고** 다음 후보를 계속 본다.
            if c.b and not any(lo_a <= h <= hi_a for h in hits):
                if start_miss is None:
                    start_miss = (text, near[0], sorted(hits)[:4])
                continue
            c.verdict, c.token, c.conf = "확인", text, 0
            c.reason = f"`{text}`가 :{near[0]}에 있다{tail}"
            return
        # 닻이 여럿이면 **가장 좁은 것**을 보고한다 — 사람이 볼 것은 그것이다.
        rank = (len(hits), 0 if kind == "리터럴" else 1)
        if best is None or rank < best[2]:
            best = (text, hits, rank)
    # 🆕 후보를 다 봤는데 **시작 근처에 닻이 있는 것이 하나도 없었다** — 다섯 번째 기제.
    if start_miss is not None:
        text, hit, allhits = start_miss
        c.verdict, c.conf, c.token = "의심", 60, text
        c.reason = (f"`{text}`가 범위 안(:{hit})에는 있으나 "
                    f"**시작 :{c.a} 근처에는 없다** — 시작이 밀린 범위다")
        c.where = f"닻 {allhits}"
        return
    if best is None:
        c.reason = c.reason or "주변 산문에서 대상 파일에 있는 토큰을 못 뽑았다"
        return
    text, hits, _ = best
    c.verdict, c.token = "의심", text
    c.conf = 80 if len(hits) == 1 else 60
    c.where = ", ".join(f":{h}" for h in hits[:4])
    c.reason = f"`{text}`가 :{c.a} 근처에 없다 — {c.where}에 있다"


def lines_of(root: Path, c: Cite, cache: dict):
    """인용이 **적힌** 줄. 기대 토큰은 여기서 나온다."""
    key = "\0src:" + c.src
    if key not in cache:
        cache[key] = (root / c.src).read_text(encoding="utf-8").splitlines()
    src = cache[key]
    return src[c.src_line - 1] if c.src_line <= len(src) else ""


def audit(root="."):
    root = Path(root)
    cites, scanned, excluded, tail = collect(root)
    index = [q.relative_to(root) for q in root.rglob("*") if q.is_file()]
    cache = {}
    for c in cites:
        judge(root, c, cache, index)
    return cites, scanned, excluded, tail


def main(argv):
    root = Path(argv[1]) if len(argv) > 1 else Path(".")
    cites, scanned, excluded, (recorded, optout) = audit(root)
    print("=" * W)
    print("인용 감사 — `file:line`이 아직 그 줄을 가리키는가 (후속 11 · G18)")
    print("=" * W)
    print(f"\n대상 {len(scanned)}편에서 인용 {len(cites)}개 "
          f"(그중 기록 표식 {len(recorded)}개). "
          "숫자는 `consistency_audit.py`가 본다 — 여기서는 **인용**만 본다.\n")

    print("-" * W)
    print(f"제외 — 무엇을 왜 안 봤는가 ({len(excluded)}편)")
    print("  ⚠️ 보이지 않는 제외가 지난 여섯 건이 살아남은 방식이다. 그래서 찍는다.")
    print("-" * W)
    for pat, why in EXCLUDE_WHY:
        n = sum(1 for e in excluded if _matches(e, pat))
        print(f"  · {pat:<52} {n:>3}편  {why}")
    print(f"  · {'스스로 뺀 파일 (합성 인용 표식)':<52} {len(optout):>3}편  "
          "이름을 전부 찍는다:")
    for o in optout:
        print(f"        {o}")
    print("  ※ `.omc/plans/`의 **살아 있는** 계획서(ralplan·open-questions)는 본다 —")
    print("     G18 기계적 검사 ①이 겨냥하는 곳이 정확히 거기다. 아래 `의심`의")
    print("     대부분이 거기 있고, **그것을 파일 단위로 빼지 않는 것이 이 도구의")
    print("     설계다** — 그 절들은 살아 있는 코드를 가리키고, 레인 D의 표류")
    print("     일곱 건이 정확히 그런 자리에 살았다.")

    by = defaultdict(list)
    for c in cites:
        if c.marker:
            continue                          # 아래 '기록 표식' 절에서 따로 센다
        by[c.verdict].append(c)
    sus = sorted(by["의심"], key=lambda c: (-c.conf, c.src, c.src_line))

    # ── 인용 하나짜리 제외 — **전수로 찍는다** ───────────────────────────
    print("\n" + "-" * W)
    print(f"기록 표식으로 뺀 인용 {len(recorded)}개 — 하나씩 전부 찍는다")
    print("  이 제외는 **파일이 아니라 인용 하나**에 붙는다. 같은 줄·같은 표 행의")
    print("  다른 인용은 그대로 감사한다(`test_citation_audit.py`의 누출 대조).")
    print("  🔴 여기 있는 인용의 표류는 **알고 포기한 것**이다 — 표식이 곧 포기")
    print("     선언이고, `표식 없었다면` 열이 무엇을 포기했는지 말한다.")
    print("-" * W)
    if not recorded:
        print("  (없음)")
    hushed = 0
    for c in sorted(recorded, key=lambda c: (c.src, c.src_line)):
        if c.verdict == "의심":
            hushed += 1
        print(f"  · {c.src}:{c.src_line}  →  {c.label}"
              f"   [표식: {c.marker}]  표식 없었다면: {c.verdict}")
    print(f"  → 그중 {hushed}개가 표식이 없었다면 `의심`이었다. "
          "**그 수만큼 이 규칙이 눈을 감긴다.**")

    print("\n" + "-" * W)
    print(f"의심 {len(sus)}건 — 확신이 큰 것부터")
    print("-" * W)
    if not sus:
        print("  ✅ 없음.")
    for c in sus:
        print(f"  🔴 {c.src}:{c.src_line}  →  {c.label}   [{c.how}]")
        print(f"       {c.reason}")

    print("\n" + "-" * W)
    print(f"확인 {len(by['확인'])}건 · 해석 불가 {len(by['해석 불가'])}건")
    print("-" * W)
    print("  `확인` = 인용 주변 산문의 토큰이 그 줄(±%d)에 **실제로 있다.**" % NEAR)
    print("  🔴 `확인`은 **인용이 옳다는 뜻이 아니다** — 파일은 인용이 무엇을")
    print("     주장했는지 기록하지 않는다. `줄이 존재한다`만 보고 통과시키는 일은")
    print("     하지 않는다. 그것이 레인 D의 일곱 건을 통과시킨 검증이다.")
    print("  `해석 불가` = 뽑을 토큰이 없다. **틀렸다는 뜻도 옳다는 뜻도 아니다.**")

    print("\n" + "-" * W)
    print(f"종료 코드 — 의심 {len(sus)}건이므로 {1 if sus else 0}")
    print("  규칙: **의심이 하나라도 있으면 1**, 전부 `확인`/`해석 불가`면 0.")
    print("-" * W)
    print("\n⚠️ 이 감사가 못 잡는 것")
    print("  · **토큰이 안 뽑히는 인용.** 산문이 백틱 없이 한국어로만 설명하면")
    print("    닻이 없다. `해석 불가`로 남고, 그 수만큼 이 도구는 눈을 감고 있다")
    print("  · **줄이 움직였는데 그 줄에 토큰이 아직 있는 경우.** 같은 이름이")
    print("    여러 곳에 있으면 옮겨간 자리가 우연히 맞을 수 있다")
    print("  · **저장소 밖 파일 인용** — 여기서는 `대상 파일이 없다`로 나오고,")
    print("    그것이 표류인지 외부 참조인지 이 도구는 구별하지 못한다")
    print("  · **범위의 끝.** 시작 줄이 블록을 여는 줄일 때만 본다. **짧게 잘라 쓴**")
    print("    범위와 **끝이 밀린** 범위를 구별하지 못한다 (짧은 쪽은 통과시킨다)")
    print("  · **인용이 무엇을 주장했는가.** 파일에 없는 정보다. 토큰은 대리 지표다")
    print("  · 맨 `:NNN`은 **백틱 안**만 본다 — 백틱 없는 것은 시각·비와 구별 불가")
    print("  · `.md`의 **바로 옆이 아닌** 맨 `:NNN`. 줄 이동 대장 표를 잘못 물지")
    print("    않으려고 통째로 포기했다 — 정확도를 위해 재현율을 버린 자리다")
    print("  · **스스로 뺀 파일.** 표식 하나로 빠져나간다. 위에 이름을 찍는 것이")
    print("    유일한 방어다 — 목록이 늘어나면 그것 자체가 신호다")
    print("  · **기록 표식 뒤의 진짜 표류.** `이전 `경로.py:NNN``이라고 써 놓고")
    print("    그것이 실은 살아 있는 인용이면 이 도구는 **못 잡는다 — 알고 포기했다.**")
    print("    표식을 붙이는 것이 곧 *\"이 번호는 안 지켜도 된다\"*는 선언이기")
    print("    때문이다. 방어는 둘뿐이다: 위 목록을 전수로 찍는 것, 그리고")
    print("    표식이 **같은 줄의 다른 인용으로 새지 않는다**는 대조 시험")
    print("  · **표식 없는 기록.** 반대쪽 대가다 — *\"그때 그랬다\"*를 표식 없이")
    print("    적은 자리는 `의심`으로 남는다. 규칙을 넓혀 그것까지 물면 revN을")
    print("    **반박하는** 산문의 살아 있는 인용을 함께 먹는다(실측). 좁은 쪽을")
    print("    골랐고, 그래서 이 도구는 **정상인 것을 조금 빨갛게 한다**")
    print("=" * W)
    return 1 if sus else 0


def _matches(rel, pat):
    if pat.startswith("PROGRESS"):
        return rel in TIMELINE
    if pat.startswith("*.backup"):
        return rel.endswith(".backup.md")
    if pat.startswith(".omc/plans/{"):
        return rel.startswith(EXCLUDE_PREFIX)
    if pat.startswith(".omc/state"):
        return any(s in rel for s in (".omc/state/", "__pycache__/", ".git/"))
    if pat.startswith("eval/"):
        return "eval/" in rel
    return rel.startswith(pat.rstrip("*"))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
