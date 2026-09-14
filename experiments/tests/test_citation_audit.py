# -*- coding: utf-8 -*-
"""
test_citation_audit.py — **위반을 일부러 심어 감사기가 우는지** 본다.

🔴 이 저장소는 지난 라운드에만 *"발화할 수 없는 검사"*를 **셋** 만들었다.
엉뚱한 정규식으로도 통과하는 시험 · 이름 둘을 못 보는 복원 단언 ·
파이프라인에 리터럴 `\\n`이 들어가 항상 0을 돌려주던 가드레일 명령.
**열거는 검증이 아니다**(G18). 그래서 이 시험은 감사기를 *돌려보는* 것이 아니라
**틀린 인용 네 종류를 손으로 만들어 심고, 각각이 보고되는지**를 본다.

심는 것 (네 개의 음성 대조):
  (a) 엉뚱한 줄을 가리키는 인용
  (b) 없는 파일을 가리키는 인용
  (c) **끝**이 밀린 범위 인용
  (d) 표류한 **맨 `:NNN`** 자기파일 인용

그리고 반대쪽도 함께 본다 — 옳은 인용이 `확인`으로 나오는가. **무조건 우는
검사도 무조건 안 우는 검사만큼 쓸모없다.**

⚠️ 이 파일은 **틀린 인용을 일부러 담고 있으므로** 감사 대상에서 스스로 빠진다.
   아래 표식이 그 선언이고, 감사기는 빠져나간 파일의 **이름을 출력에 찍는다.**
   citation-audit: 합성 인용
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import citation_audit as CA                                # noqa: E402

# 시험용 대상 파일. 줄 번호가 **시험의 전제**이므로 여기서 못 박는다.
#   :5  CONST_A = 1        :8  def beta        :12 def alpha (블록 끝 :15)
#   :18 def gamma          :21 맨 `:5` 자기파일 인용 (음성 대조 d)
THING = """\
# -*- coding: utf-8 -*-
\"\"\"thing.py — 시험용.\"\"\"
import os

CONST_A = 1


def beta():
    return CONST_A


def alpha(x):
    y = x + 1
    z = y * 2
    return z


def gamma():
    return 0


# (d) 폭 제약: `:5`가 `def alpha`를 연다.   <- 틀렸다. :12다
"""

# 같은 파일에서 (d)만 뺀 것. **깨끗한 트리는 정말로 깨끗해야** 종료 0 시험이
# 뜻을 갖는다 — 심어 둔 위반이 남아 있으면 그 시험은 무엇도 증명하지 못한다.
THING_CLEAN = THING.rsplit("\n\n#", 1)[0] + "\n"

# (a)(b)(c) + 양성 대조 + 해석 불가.
NOTES = """\
# 시험 문서

- (a) `def alpha`의 자리는 `prototype/thing.py:5`다.
- (b) `def nothing`은 `prototype/ghost.py:12`에 있다.
- (c) `def alpha` 본문은 `prototype/thing.py:12-18`이다.
- (양성) `def gamma`는 `prototype/thing.py:18`에 있다.
- (해석 불가) 자세한 것은 `prototype/thing.py:13`을 보라.
- (e) `def alpha` 블록은 `prototype/thing.py:9-16`이다.
- (양성2) `def gamma` 블록은 `prototype/thing.py:18-19`이다.
- (양성3) `def alpha`보다 `def beta`가 먼저다 — `prototype/thing.py:7-16`.
"""

# 옳은 것만 있는 트리 — 종료 코드 0이 나와야 한다.
CLEAN = """\
# 깨끗한 문서

- `def gamma`는 `prototype/thing.py:18`에 있다.
- `def beta`는 `prototype/thing.py:8`에 있다.
- 자세한 것은 `prototype/thing.py:13`을 보라.
"""


def build(tmp: Path, notes: str, snapshot=False, thing=THING, plan=None):
    (tmp / "prototype").mkdir(parents=True, exist_ok=True)
    (tmp / "prototype" / "thing.py").write_text(thing, encoding="utf-8")
    (tmp / "docs").mkdir(exist_ok=True)
    (tmp / "docs" / "20-notes.md").write_text(notes, encoding="utf-8")
    if snapshot:
        snap = tmp / ".omc" / "plans" / "baseline" / "after-x"
        snap.mkdir(parents=True, exist_ok=True)
        (snap / "README.md").write_text(notes, encoding="utf-8")
    if plan is not None:
        # **살아 있는** 계획서. 이름이 계획서라는 이유로 빠지면 안 된다.
        p = tmp / ".omc" / "plans"
        p.mkdir(parents=True, exist_ok=True)
        (p / "ralplan-x.md").write_text(plan, encoding="utf-8")
    return tmp


class Harness(unittest.TestCase):

    def audit(self, notes=NOTES, snapshot=False, thing=THING, plan=None):
        self.tmp = Path(tempfile.mkdtemp(prefix="citaudit-"))
        build(self.tmp, notes, snapshot, thing, plan)
        cites, scanned, excluded, (recorded, _) = CA.audit(self.tmp)
        self.recorded = recorded
        return cites, scanned, excluded

    def find(self, cites, src_tail, label_tail):
        """`src`가 …로 끝나고 인용이 …인 것 하나."""
        hits = [c for c in cites if c.src.endswith(src_tail)
                and c.label.endswith(label_tail)]
        self.assertEqual(len(hits), 1,
                         f"{src_tail} -> {label_tail} 를 정확히 하나 못 찾았다: "
                         + repr([(c.src, c.label) for c in hits]))
        return hits[0]


class TestNegativeControls(Harness):
    """심은 위반 넷이 **전부** 보고되는가."""

    def test_a_wrong_line(self):
        """(a) `def alpha`를 :5라고 적었다. 실제는 :12."""
        cites, _, _ = self.audit()
        c = self.find(cites, "20-notes.md", "thing.py:5")
        self.assertEqual(c.verdict, "의심", c.reason)
        self.assertEqual(c.token, "def alpha")
        self.assertIn(":12", c.reason)          # 옮겨간 자리까지 짚는다

    def test_b_missing_file(self):
        """(b) `prototype/ghost.py`는 없다."""
        cites, _, _ = self.audit()
        c = self.find(cites, "20-notes.md", "ghost.py:12")
        self.assertEqual(c.verdict, "의심", c.reason)
        self.assertIn("저장소에 없다", c.reason)
        self.assertEqual(c.conf, 100)           # 가장 확실한 종류

    def test_c_range_end_drifted(self):
        """(c) `:12-18` — `def alpha`는 :15에서 끝난다."""
        cites, _, _ = self.audit()
        c = self.find(cites, "20-notes.md", "thing.py:12-18")
        self.assertEqual(c.verdict, "의심", c.reason)
        self.assertIn("끝 :15", c.reason)
        # 🔴 시작만 맞고 끝이 틀린 형태다. **양 끝을 따로 보지 않으면 통과한다** —
        #    `:12`에는 `def alpha`가 실제로 있기 때문이다 (설계 메모 ③).

    def test_d_bare_same_file_drifted(self):
        """(d) `thing.py:21`의 맨 `` `:5` `` — 자기 파일에 붙고, 틀렸다."""
        cites, _, _ = self.audit()
        c = self.find(cites, "thing.py", "thing.py:5")
        self.assertEqual(c.how, "맨:자기파일")
        self.assertEqual(c.verdict, "의심", c.reason)
        self.assertIn(":12", c.reason)

    def test_d_bare_is_invisible_to_a_filename_regex(self):
        """(d)의 전제: 파일 이름에 닻을 내린 정규식은 이것을 **못 본다.**

        verifier-r2-final:99가 지적한 그대로다. 이 단언이 깨지면 (d)는
        더 이상 음성 대조가 아니다 — 다른 검사가 이미 잡고 있다는 뜻이다.
        """
        line = "# (d) 폭 제약: `:5`가 `def alpha`를 연다.   <- 틀렸다. :12다"
        self.assertIsNone(CA.RE_PATH.search(line))
        self.assertIsNone(CA.RE_DOCS.search(line))
        self.assertIsNotNone(CA.RE_BARE.search(line))


class TestItDoesNotCryWolf(Harness):
    """무조건 우는 검사는 무조건 안 우는 검사만큼 쓸모없다."""

    def test_correct_citation_is_confirmed(self):
        cites, _, _ = self.audit()
        c = self.find(cites, "20-notes.md", "thing.py:18")
        self.assertEqual(c.verdict, "확인", c.reason)
        self.assertEqual(c.token, "def gamma")

    def test_no_token_is_not_a_failure(self):
        """산문이 닻을 안 주면 `해석 불가`다 — `확인`도 `의심`도 아니다."""
        cites, _, _ = self.audit()
        c = self.find(cites, "20-notes.md", "thing.py:13")
        self.assertEqual(c.verdict, "해석 불가", c.reason)

    def test_line_exists_is_never_enough(self):
        """🔴 이 저장소의 일곱 건을 통과시킨 검증을 재현하고, 거부되는지 본다.

        `thing.py:5`는 **존재하는 줄**이다. 존재만 보는 검사는 통과시킨다.
        이 감사기는 통과시키면 안 된다.
        """
        cites, _, _ = self.audit()
        c = self.find(cites, "20-notes.md", "thing.py:5")
        thing = (self.tmp / "prototype" / "thing.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(len(thing.splitlines()), 5)   # 줄은 있다
        self.assertNotEqual(c.verdict, "확인")                # 그래도 통과 아니다


class TestExclusions(Harness):
    """제외가 **실제로** 제외하는가, 그리고 **보이는가.**"""

    def test_snapshot_is_excluded(self):
        cites, scanned, excluded = self.audit(snapshot=True)
        snap = ".omc/plans/baseline/after-x/README.md"
        self.assertIn(snap, excluded)
        self.assertNotIn(snap, scanned)
        self.assertEqual([c for c in cites if c.src == snap], [])

    def test_exclusion_is_printed(self):
        """보이지 않는 제외가 지난 여섯 건이 살아남은 방식이다."""
        out = run(self.audit(snapshot=True) and self.tmp)
        self.assertIn("제외", out.stdout)
        self.assertIn("baseline", out.stdout)

    def test_optout_is_honoured_and_named(self):
        """표식으로 빠진 파일은 **이름이 찍혀야** 한다. 안 찍히면 구멍이다."""
        self.audit()
        bad = self.tmp / "docs" / "21-synthetic.md"
        bad.write_text("<!-- " + CA.OPTOUT + " -->\n\n`x`는 `p/q.py:9`다.\n",
                       encoding="utf-8")
        cites, scanned, excluded, (_, optout) = CA.audit(self.tmp)
        self.assertIn("docs/21-synthetic.md", optout)
        self.assertNotIn("docs/21-synthetic.md", scanned)
        self.assertEqual([c for c in cites if c.src.endswith("21-synthetic.md")], [])
        self.assertIn("docs/21-synthetic.md", run(self.tmp).stdout)

    def test_the_auditor_does_not_opt_itself_out(self):
        """`OPTOUT` 상수를 통째로 적으면 감사기가 **자기를 감사에서 뺀다.**

        조각내어 적은 이유가 그것이고, 이 단언이 그 이유를 지킨다.
        """
        src = Path(CA.__file__).read_text(encoding="utf-8")
        self.assertNotIn(CA.OPTOUT, src)


# ── 기록 표식 제외의 음성 대조 ─────────────────────────────────────────
# 🔴 제외 규칙은 **발화할 수 없는 검사를 만드는 가장 쉬운 길**이다.
#    그래서 아래는 규칙을 *설명*하지 않고 **위반을 심어 무슨 일이 일어나는지**
#    본다 — 눌리는 쪽과 안 눌리는 쪽 **양쪽 다.**
#
#   :5 는 `def alpha`의 자리가 **아니다**(:12다). 아래 고정물은 그 틀린 인용을
#   표식이 있는 자리와 없는 자리에 각각 놓는다.
RECORDED = """\
# 표식 있는 기록

- rev1의 `prototype/thing.py:5`가 `def alpha`였다.
"""

# 같은 **한 줄**에 표식 붙은 것과 안 붙은 것이 같이 있다.
# 표식이 줄 단위로 새면 뒤엣것도 함께 빠진다 — 그것을 잡는 대조다.
LEAK = """\
# 표식 누출 대조

- rev1의 `prototype/thing.py:5`는 틀렸고, `def alpha`는 `prototype/thing.py:9`다.
"""

# 표식 낱말이 줄에 **있기는 한데 인용에서 멀다.** 창이 좁다는 것을 못 박는다.
FAR = """\
# 창 폭 대조

- rev1은 이 절을 다시 썼고 그 과정에서 여러 값을 고쳤다. `def alpha`는 `prototype/thing.py:5`다.
"""

# 이름이 계획서인 파일. **표식이 없으면 그대로 감사한다.**
PLAN = """\
# 살아 있는 계획서

### 단계 1
- `def alpha`의 자리는 `prototype/thing.py:5`다.
"""


class TestRecordedMarker(Harness):
    """`RE_RECORDED` — 무엇을 눌렀고 무엇을 안 눌렀는가."""

    def test_marked_drift_is_knowingly_given_up(self):
        """🔴 **심은 진짜 표류가 표식 뒤에서 조용해진다 — 알고 포기한 것이다.**

        `:5`는 `def alpha`의 자리가 아니다. 표식이 없었다면 `의심`이고,
        `RECORDED`에서는 그것이 종료 코드에 안 실린다. **이것이 이 규칙의
        비용이고, 시험이 그 비용을 문장이 아니라 실행으로 적는다.**
        """
        cites, _, _ = self.audit(notes=RECORDED, thing=THING_CLEAN)
        c = self.find(cites, "20-notes.md", "thing.py:5")
        self.assertEqual(c.marker, "rev1의")
        self.assertEqual(c.verdict, "의심", c.reason)   # 판정은 그대로 내린다
        self.assertIn(c, self.recorded)
        # 그런데 게이트는 조용하다 — 포기가 실제로 일어난다.
        r = run(self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:])

    def test_the_marker_rule_is_load_bearing(self):
        """규칙을 끄면 같은 고정물이 **운다.** 안 울면 위 시험은 아무 뜻도 없다."""
        self.audit(notes=RECORDED, thing=THING_CLEAN)
        keep = CA.RE_RECORDED
        try:
            CA.RE_RECORDED = re.compile(r"(?!)")        # 아무것도 안 무는 규칙
            cites, _, _, (recorded, _) = CA.audit(self.tmp)
            self.assertEqual(recorded, [])
            c = self.find(cites, "20-notes.md", "thing.py:5")
            self.assertEqual(c.verdict, "의심", c.reason)
        finally:
            CA.RE_RECORDED = keep

    def test_marker_does_not_leak_to_the_rest_of_the_line(self):
        """🔴 **하중을 받는 대조.** 표식은 인용 하나에만 붙는다.

        줄 단위·표 행 단위·파일 단위로 새면 살아 있는 인용이 함께 숨는다 —
        그것이 파일 단위 제외를 거부한 이유 그 자체다.
        """
        cites, _, _ = self.audit(notes=LEAK, thing=THING_CLEAN)
        marked = self.find(cites, "20-notes.md", "thing.py:5")
        live = self.find(cites, "20-notes.md", "thing.py:9")
        self.assertEqual(marked.marker, "rev1의")
        self.assertEqual(live.marker, "")                # 같은 줄인데 안 샜다
        self.assertEqual(live.verdict, "의심", live.reason)
        self.assertEqual(run(self.tmp).returncode, 1)    # 게이트가 운다

    def test_a_distant_marker_does_not_exclude(self):
        """표식 낱말이 줄에 있어도 **인용에서 멀면** 제외하지 않는다."""
        cites, _, _ = self.audit(notes=FAR, thing=THING_CLEAN)
        c = self.find(cites, "20-notes.md", "thing.py:5")
        self.assertEqual(c.marker, "")
        self.assertEqual(c.verdict, "의심", c.reason)

    def test_the_end_anchor_is_what_carries_the_load(self):
        """🔴 **변이 시험이 고친 시험이다.**

        위 두 대조(`누출`·`먼 표식`)는 고정물로 도는데, 둘 다 `$` 닻과
        `앞 14자` 창 **양쪽**이 지운다. 그래서 **한쪽만 망가뜨리면 둘 다
        안 울었다** — 즉 그 대조들은 각 방어를 따로 잡지 못한다.
        여기서 `$`를 **정규식에 직접** 못 박아 그 구멍을 메운다.

        (창 폭은 `$`가 있는 한 **놀고 있다.** 그 사실은 `RE_RECORDED` 위에
         적어 뒀다 — *"좁아서 안전하다"*를 믿고 넓히는 다음 사람을 위해서다.)
        """
        self.assertIsNotNone(CA.RE_RECORDED.search("고쳤다**(이전 `"))
        # 표식과 인용 사이에 **다른 낱말**이 끼면 표식이 아니다.
        self.assertIsNone(CA.RE_RECORDED.search("rev1의 `x`는 틀렸고 `"))
        self.assertIsNone(CA.RE_RECORDED.search("이전 판에서 이것은 `"))
        self.assertIsNone(CA.RE_RECORDED.search("당시 상황을 적는다. 지금은 `"))

    def test_backtick_glue_regression(self):
        """🔴 반쯤 죽어 있던 규칙 — 백틱 때문에 경로 꼴에서 **한 번도 안 물었다.**

        `RE_PATH`는 백틱 **뒤**에서 매치를 시작하므로 앞 문맥이 `` ` ``로
        끝난다. 접착 문자를 허용하기 전에는 맨 `:NNN` 꼴에서만 발화했다.
        """
        self.assertIsNone(re.compile(r"(?:이전|원래|과거|before)\s*$")
                          .search("고쳤다**(이전 `"))
        self.assertIsNotNone(CA.RE_RECORDED.search("고쳤다**(이전 `"))
        self.assertIsNotNone(CA.RE_RECORDED.search(":30` | rev1의 `"))
        self.assertIsNotNone(CA.RE_RECORDED.search(") — 사전 조사 당시 `"))

    def test_a_living_plan_document_is_still_audited(self):
        """🔴 **파일 단위 제외를 거부한다는 것을 시험으로 못 박는다.**

        `.omc/plans/ralplan-*.md`는 살아 있는 계획서다. 그 안의 `§단계` 절은
        살아 있는 코드를 가리키고, 레인 D의 표류 일곱 건이 그런 자리에 살았다.
        이름이 계획서라는 이유로 빠지면 그 일곱 건이 다시 조용해진다.
        """
        cites, scanned, excluded = self.audit(
            notes=CLEAN, thing=THING_CLEAN, plan=PLAN)
        rel = ".omc/plans/ralplan-x.md"
        self.assertIn(rel, scanned)
        self.assertNotIn(rel, excluded)
        c = self.find(cites, "ralplan-x.md", "thing.py:5")
        self.assertEqual(c.marker, "")
        self.assertEqual(c.verdict, "의심", c.reason)
        self.assertEqual(run(self.tmp).returncode, 1)

    def test_every_marked_citation_is_printed_with_its_marker(self):
        """보이지 않는 제외가 지난 여섯 건이 살아남은 방식이다.

        개수만 찍는 것으로는 **어느 인용이 빠졌는지** 아무도 모른다.
        """
        self.audit(notes=RECORDED, thing=THING_CLEAN)
        out = run(self.tmp).stdout
        self.assertIn("기록 표식으로 뺀 인용 1개", out)
        self.assertIn("docs/20-notes.md:3", out)          # 어느 줄인지
        self.assertIn("thing.py:5", out)                  # 어느 인용인지
        self.assertIn("[표식: rev1의]", out)               # 무엇 때문에 빠졌는지
        self.assertIn("표식 없었다면: 의심", out)            # 무엇을 눌렀는지
        self.assertIn("1개가 표식이 없었다면 `의심`이었다", out)


class TestExitCode(Harness):
    """종료 코드 규칙: 의심이 하나라도 있으면 1, 아니면 0."""

    def test_dirty_tree_exits_nonzero(self):
        self.audit()
        self.assertEqual(run(self.tmp).returncode, 1)

    def test_clean_tree_exits_zero(self):
        """🔴 이것이 없으면 위 시험은 *"항상 1"*로도 통과한다."""
        self.audit(notes=CLEAN, thing=THING_CLEAN)
        r = run(self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:])
        self.assertIn("의심 0건", r.stdout)


class TestRangeStart(Harness):
    """
    🆕 **다섯 번째 실명 기제 — 범위 인용의 «시작»은 검사되지 않았다.**

    옛 창은 `[a-NEAR, b+NEAR]`라 **범위 전체를 덮는 그물**이었다. 24줄 범위는
    28줄 그물이고, 닻이 그 **어디에** 있어도 통과한다. 그래서 `docs/10`의
    `memory.py:1311-1334`(실제 `Memory.gate`는 이전 그 자리가 아니다)가
    **길이만 맞고 시작이 +22 밀린 채** 초록으로 통과했다 — 레인 D의 일괄
    오프셋과 같은 지문이다. 그리고 유일한 끝 검사 `block_end()`는 **시작 줄이
    블록을 열 때만** 발화하므로 **하나의 틀림이 두 방어를 동시에 껐다.**

    **심을 위반 — 이 셋이 서로를 가린다.**
      ⓐ 시작 창 검사(`lo_a`/`hi_a`)를 지우면 → `test_shifted_start_is_suspect` 발화
      ⓑ 기각을 **미루지 않고** 첫 후보에서 바로 `의심`으로 내면
         → `test_deferred_rejection_does_not_false_fire` 발화 (**오발화 = 결함**)
         🔴 이것이 실측으로 잡힌 자리다: `memory.py:1053-1062`(`_roots`)는 **옳은데**
         옆 산문의 `_PARTICLE`(범위 안)이 먼저 걸려 기각되면 시작에 맞는 닻
         `_roots`를 **시도조차 안 한다.**
      ⛔ **단일 줄 인용에 대한 시험은 안 만든다.** `c.b`가 없으면 `[lo,hi]`와
         `[lo_a,hi_a]`가 **정의상 같은 구간**이라 가드를 지워도 결과가 안 바뀐다 —
         시험이 원리적으로 구별할 수 없다. 심어 보고 알았고(변이가 아무것도
         실패시키지 않았다), **논증이지 시험이 아니므로 여기 적기만 한다.**
         🔴 이것을 시험으로 두면 그것이 «발화할 수 없는 검사»의 아홉 번째다.
    """

    def test_shifted_start_is_suspect(self):
        """
        (e) `def alpha`는 :12인데 범위를 :9부터 적었다 — 길이는 그럴듯하다.

        ⚠️ :9를 고른 것이 규정의 일부다. :8은 `def beta():`라 **기존 끝 검사가
        먼저 물어** 새 검사를 시험하지 못한다 — 심어 보고 알았다. :9는 블록을
        안 열어 끝 검사가 꺼지고 **시작 검사만 하중을 받는다.**
        """
        cites, _, _ = self.audit()
        c = self.find(cites, "20-notes.md", "thing.py:9-16")
        self.assertEqual(c.verdict, "의심", c.reason)
        self.assertIn("시작", c.reason)
        self.assertIn(":12", c.reason)     # 범위 «안»에는 있다는 것까지 짚는다

    def test_correct_range_still_passes(self):
        """(양성2) 시작이 맞으면 그대로 `확인`이다 — 이 검사는 재현율을 안 판다."""
        cites, _, _ = self.audit()
        c = self.find(cites, "20-notes.md", "thing.py:18-19")
        self.assertEqual(c.verdict, "확인", c.reason)

    def test_deferred_rejection_does_not_false_fire(self):
        """
        🔴 (양성3) **오발화 대조.** 산문에 후보가 둘이고, 하나(`def alpha` :12)는
        범위 안이지만 시작에서 멀다. 다른 하나(`def beta` :8)는 시작 근처다.
        **첫 후보에서 기각하면 여기가 빨개진다** — 정상 경로가 빨개지는 것은
        «발화할 수 없는 검사»의 쌍둥이이고 P5가 세는 결함이다.
        """
        cites, _, _ = self.audit()
        c = self.find(cites, "20-notes.md", "thing.py:7-16")
        self.assertEqual(c.verdict, "확인", c.reason)



class TestResolution(Harness):
    """맨 `:NNN`을 **어디에** 붙이는가 — 붙이는 규칙 자체를 못 박는다."""

    def test_bare_glues_to_adjacent_path(self):
        line = "`prototype/thing.py:8-9`·`:12-15`는 둘 다 함수다."
        tmp = Path(tempfile.mkdtemp(prefix="citaudit-"))
        build(tmp, "# x\n\n- " + line + "\n")
        cites, _, _, _ = CA.audit(tmp)
        c = [x for x in cites if x.a == 12][0]
        self.assertEqual(c.how, "맨:옆경로")
        self.assertEqual(c.path, "prototype/thing.py")

    def test_bare_far_from_path_in_md_is_unresolved(self):
        """줄 이동 대장 표의 맨 번호를 앞 칸 파일에 붙이면 **조용히 틀린다.**"""
        line = "| `prototype/thing.py:8` | `:1325` | **`:1333`** | 옛/새 |"
        tmp = Path(tempfile.mkdtemp(prefix="citaudit-"))
        build(tmp, "# x\n\n" + line + "\n")
        cites, _, _, _ = CA.audit(tmp)
        c = [x for x in cites if x.a == 1325][0]
        self.assertEqual(c.how, "맨:대상불명")
        self.assertEqual(c.verdict, "해석 불가")


def run(root: Path):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return subprocess.run(
        [sys.executable, os.path.join(here, "citation_audit.py"), str(root)],
        capture_output=True, text=True, encoding="utf-8", env=env)


if __name__ == "__main__":
    unittest.main(verbosity=2)
