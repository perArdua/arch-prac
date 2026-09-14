# -*- coding: utf-8 -*-
"""
test_e2e_deletion_roundtrip.py — 끝-끝 삭제 왕복. (w25e · Fable 수리 계획 묶음 E · 결정 Q1=(a) · Q3=M+1 · Q4=A)

한 방에서 쓰기 → 경계 1 → 삭제 → 전이 → 경계 2 → 서빙 → 전이 둘째 → 상한 뒤 유령(7), 그리고 같은 길을
6′까지 간 새 방에서 갈라지는 재등장 대역(8). 삭제 수리는 모듈 셋에 흩어져 있다 —
`summarize`(지운 원본 턴 가리기 · 재등장 검사 · 지운 원본 재등록 제외 · lifetime 재료에서 stale 세션 제외) ·
`regen_job`(첫 lifetime · 재료 키 집합 기준) · `memory`(밀려난 키의 흔적 셋 · 전이 스위치). 모듈마다 시험이
이미 있다(`test_regen_deletion` · `test_regen_k1_c9` · `test_digest_cap`). **이 파일이 보는 것은 합성이다** —
한 모듈만 되돌려도 다른 모듈 몫의 단계가 우는가.

## 🔴 제품 경로만

삭제는 `delete_item`, 전이는 `apply_meta`, 경계는 `regen_job.run`, 서빙은 `build_context`다. stale 표를
손으로 채우는 도우미도, stale 표에 직접 넣는 행도, 전이 전파 메서드를 직접 부르는 줄도 없다. 고정물은
소크 시드 + `add_turn` · `upsert_fact` · 사실마다 색인 복사본(`add_event` + `record_derivation` — 소크가
사실을 검색에 싣는 모양)이다. 대역은 `llm.generate`를 갈아 끼운다 — **LLM 생성 0회.**
대역은 **재료를 보존하는 요약기**다: 세션 요약은 재료의 유저 발화를, lifetime은 재료의 세션 요약 본문을
그대로 옮긴다. 8단계만 «지운 사실을 다른 표면으로 돌려주는» 요약기로 간다.

⚠️ `recent`(원본 턴 창)와 `utterance`(질의 자신)는 «지운 사실 없음» 단언에서 뺀다 — 원본 턴을 지우지
   않는 것이 ADR-010 ②의 설계이고, 이 파일이 지키는 것은 **파생물**(요약 · 상시 사실 · 검색 복사본)이다.

## 단계 (계획 «묶음 E»의 1~8 · 기대값은 w24a가 정한 기준으로)

  1 쓰기       턴 1–12(세션 둘) · 사실 셋 — 지울 것 둘(«마케팅 회사 대리» 턴 3 · «수영 강습» 턴 1) ·
               안 지울 것 하나(«고양이 나비» 턴 5). 값의 어근은 서로 안 겹친다(`test_deletion.py` 규약).
  2 경계1      세션 요약 S01 · lifetime 없음(재료 1 < `LIFETIME_MIN_SESSIONS`) · 비밀이 세션 요약 ·
               [알고 있는 것] · 검색 블록에 **있다**(대조의 바닥 — 이것이 없으면 뒤의 «0회»는 발화할 수 없다).
  3 삭제       비밀이 어느 블록에도 없다 · provenance에 `stale`(기본값에서 살아 있는 유일한 분기).
  4 전이       비밀 없음 · 경고 주입·만료 0회 — **스위치 두 값 모두.** 이 시점의 digest 키는 삭제로
               stale인 S01 하나이고, 삭제 사유는 전이가 덮지 않는다(wave2) — 스위치를 켜도 갈 곳이 없다.
  5 경계2      S01 재생성 성공 · 첫 lifetime `created`(Q3 — ②가 아니라 ③이 만든다) · 재생성 프롬프트 전부에
               비밀 0 · digest stale 0 · 지운 원본을 적은 파생 등록 0 · `regen_failed` 0.
  6 서빙       비밀 없음 · `digest:lifetime` 블록 · 조용한 사실이 lifetime에 있다.
  6q 조용한 쪽 조용한 사실이 [알고 있는 것] · 검색 블록 · 세션 요약 S01 본문에 있다.
  6′ 전이 둘째  신선한 요약이 선 뒤의 전이 — **기본값은 경고 주입·만료 0회(누적) · 스위치를 켜면 경고
               주입 ≥ 1.** 발견 3(서빙 3분기 휴면 · Q4=A)의 기계 단언이 여기서 갈린다.
  7 상한 뒤 유령 세션을 N+1까지 밀어 S01이 밀려난 뒤 S01의 «수영 강습»을 지운다 → 밀려난 키의 stale 0 ·
               파생 등록 0 · 재생성 실패 0 · 흐름 전체 `regen_failed` 0.
  7q 조용한 쪽 조용한 사실은 끝까지 [알고 있는 것] · 검색 블록에 있다(요약 층에서는 N 상한이 S01을 밀어
               낸다 — 설계된 망각이라 7에서는 요약을 안 본다).
  8 재등장 대역 6′까지 간 새 방에서 «수영 강습»을 지우고, S01 요약기가 비밀을 재서술해 돌려준다 → S01 저장
               0(재등장) · stale 유지 · lifetime은 S01을 빼고 다시 써진다(`lifetime_material_excluded` 1) ·
               서빙에 지운 사실 둘 다 없음.
  8q 조용한 쪽 조용한 사실은 [알고 있는 것] · 검색 블록에 있다(S01 거부의 대가로 요약 층에서는 빠진다 —
               Q1 (b) 자동 후퇴의 비용).

## 🔄 w33k — 단계 9 ~ 11 (Fable 계획 2 묶음 K · 결정 2 Q8 (a) · 새 방 · 스위치 두 값)

  고정물: 턴 1 조용한 사실(«고양이 나비») · 턴 3 비밀(«마케팅 회사 대리») · 턴 5 **안 지운** 발화가 비밀의 어근을
  통째로 품는다(«마케팅 회사 대리 일이 요즘 힘들다» · 그 사실 «대리 일 줄이기») — 재료 보존 대역에서 재등장
  거부가 결정적이다(w26final P4). 이름 · 사유는 w31f가 정한 것(`summarize` 파일 끝 절 · `.omc/notepads/w31f/`).
  9   ① 거부 → 표지  경계 전 비밀 삭제 → S01 첫 요약 거부(재등장) · 같은 경계 재시도 0 · 표지 행(본문 "" · 1–6) ·
                    사유 «미완: … · 시도 1/2» · `missing` True · 서빙에 S01 블록 0(«제외» 분기 기록 1) · 비밀 0.
  9′  전이          두 스위치 모두 표지 사유 그대로 · 경고 주입 0 — 켬 쪽은 표지 행이 전이의 과녁이지만 wave2의
                    «`전이:`만 덮는다»가 막는다(이 레인이 더한 단계 — 스위치가 갈리는 유일한 자리).
  10a 경계 2        S02 정상 · S01 재시도 LLM 1 · 거부 · 사유 «… · 시도 2/2 · 포기» · `regen_abandoned` 1 · lifetime 없음.
  10b 경계 3        포기 뒤 S01 LLM 0 · 그 키의 재생성 계열 provenance 증가 0 · stale 유지(N5).
  10c 경계 4        S03 정상 · 첫 lifetime(재료 {S02, S03} · 표지 제외 기록 1) · S01 LLM 0 · 서빙에 S01 0(M=1이라 후보에도
                    안 오른다 — 계획의 «stale 기록 1»은 표지가 최신인 9단계에서만 참).
  11a 새 삭제       턴 5의 사실 삭제 → 표지 키에 닿고(lifetime에는 안 닿음) 사유가 «fact:N 삭제됨»으로 새로 써진다.
  11b 경계 5        S01 LLM 1 · **성공** — 본문은 조용한 턴 1뿐 · stale 0 · 표지 0 · lifetime 재작성(재료 {S01, S02, S03}) ·
                    서빙에서 S01은 lifetime 블록으로 돌아온다(M=1 · 계획의 «서빙 S01 블록»은 이 방에서 불가).
  11q 조용한 쪽     «고양이 나비»가 [알고 있는 것] · 검색 블록에 · 지운 둘은 [알고 있는 것]에 0.
  경계마다 subTest를 나눴다 — 한 subTest 안에서 멈추면 뒤 경계가 안 돌아 다음 단계가 연쇄로 운다.

단계마다 `subTest(switch=…, step=…)` — 한 단계가 울어도 뒤 단계가 이어서 돈다(합성 검출이 목적이다).

## 심은 위반 (w25e 레인이 사본에서 심어 우는 단계를 표로 적었다 — `.omc/notepads/w25e/`)

  재생성 가리기 제거(지운 원본 턴 집합이 늘 빔)          → 5 · 6 · 7 · 8
  lifetime 재료의 stale 제외 제거                        → 8
  밀려난 키의 파생 등록 DELETE 제거                      → 7
  첫 lifetime 방아쇠 제거(호출부)                        → 5 · 6 · 8 (켬 쪽은 6′도)
  전이 스위치 기본값을 켬                                 → 6′ · 7 (기본값 쪽 — 경고 주입 누적 0 → 2)
  재등장 검사 호출 제거 → 8 · 재등록 필터 제거 → 5 · 과잉 가리기(조용한 쪽 발화 확인) → 2 · 6 · 6q

## 🔄 심은 위반 — 9 ~ 11 (w33k 레인이 사본에서 심었다 — `.omc/notepads/w33k/mutate.py` → `mutate_out2.txt`)

  수리 전 판(묶음 F 착수 사본)에 이 파일만 얹음        → 9 · 10a · 10b · 10c · 11a · 11b (1~8 조용)
  표지 행 안 남김(① 실패 뒤 표지 호출 제거)            → 9 · 10a · 10b · 10c · 11a · 11b
  상한 끔(연속 실패 상한을 아주 크게)                   → 9(사유 «시도 1/2» 글자) · 10a · 10b · 10c
  상한 끔(포기 판정만 제거 · 사유 글자는 그대로)         → 10a · 10b · 10c    (표식: 경계 3 S01 호출 0 → 1)
  포기 필터 제거(재생성이 «포기» 키도 부름)             → 10b · 10c
  재설정 안 함 — 포기를 «포기 기록 유무»로 판정          → 11b               (표식: 경계 5 S01 호출 1 → 0)
  재설정 안 함 — 새 삭제가 «포기» 사유를 안 덮음         → 11a · 11b
  재설정 안 함 — 시도 수를 실패 기록 수로 셈             → 조용(11b의 첫 재시도가 성공한다) — `test_regen_deletion`의
                                                         `test_new_deletion_resets_the_episode_and_can_succeed`가 운다
  표지의 파생 등록 0(계획 원안)                         → 11a · 11b
  표지를 요약으로 셈                                    → 9
  lifetime 재료 비교를 집합 대신 기수로                  → 7만(11b는 재료 수 3 ≠ 2라 조용) — 단위 N7 시험이 운다
  w25e 판 재실행(위 표) — 1~8의 우는 단계는 한 칸도 안 바뀌었다. 9~11에서 더 우는 것: 가리기 제거 → 9 · 11b ·
  K1 제외 제거 → 10c · 11a · 11b · 첫 lifetime 방아쇠 제거 → 10c · 11b · 재등장 검사 제거 → 9 · 9′ · 10a~11b ·
  재등록 필터 제거 → 9 · 11b · 과잉 가리기 → 9 · 9′ · 10a~11b · 밀려난 키 derivation · 전이 스위치 켬 → 9~11 조용.
  모듈 되돌림: `regen_job.py`만 → 9 · 10a~11b · `summarize.py`만 → 같음(9는 오류 — 새 호출부가 부르는 표지 함수가 없다).
  9′은 표지가 서빙에 나오는 변이(재등장 검사 제거 · 과잉 가리기)에서만 운다 — 전후 사유가 같은지를 보는 단계다.

⚠️ 변이는 `python -B`로 돌린다(낡은 `.pyc`가 생존자를 만든다). DB는 전부 `tempfile`(= `%TEMP%`) 아래에 만든다.
"""
import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import llm                                                  # noqa: E402
import memory                                               # noqa: E402
import regen_job                                            # noqa: E402
import soak                                                 # noqa: E402
import summarize                                            # noqa: E402
from memory import Memory                                   # noqa: E402

CHAT = soak.CHAT

SWIM = "요즘 수영 강습 다니는 중이야"          # 7 · 8단계에서 지우는 사실의 턴(1)
SECRET = "나 사실 마케팅 회사 대리로 일해"      # 3단계에서 지우는 사실의 턴(3)
QUIET = "고양이 나비가 요즘 밥을 잘 먹어"       # 끝까지 안 지우는 사실의 턴(5)
TURNS = [(1, "user", SWIM), (2, "character", "오 좋네"),
         (3, "user", SECRET), (4, "character", "그랬구나"),
         (5, "user", QUIET), (6, "character", "다행이네"),
         (7, "user", "오늘 동아리 모임 있어"), (8, "character", "재밌게 놀다 와"),
         (9, "user", "밖에 비 온다"), (10, "character", "우산 챙겨"),
         (11, "user", "편의점 들렀다 갈게"), (12, "character", "조심히 와")]
# 사실 셋 — (술어, 값, 색인 복사본 문장, 원본 턴). 술어는 셋 다 상시 술어다([알고 있는 것]에 선다).
FACTS = {"secret": ("직업", "마케팅 회사 대리", "지우는 마케팅 회사 대리로 일한다", 3),
         "swim": ("선호", "수영 강습", "지우는 수영 강습을 다닌다", 1),
         "quiet": ("반려동물_이름", "고양이 나비", "지우가 고양이 나비를 키운다", 5)}
# 지운 사실이 돌아왔나를 보는 낱말 — 원문 턴 · 사실 값 · 색인 복사본 · 8단계 재서술이 모두 품는다.
MARK = {"secret": "마케팅", "swim": "수영"}
# 질의 — 과거 참조 표현이라 게이트를 늘 통과한다(검색 블록까지 본다).
ASK = {"secret": "그때 마케팅 회사 얘기 기억나?", "swim": "그때 수영 강습 얘기 기억나?",
       "quiet": "그때 고양이 나비 얘기 기억나?", "echo": "그때 대리 일 얘기 기억나?"}
# 8단계 대역이 S01 요약 끝에 붙이는 문장 — 원문과 표면이 다르고 지운 값의 어근은 다 든다.
PARAPHRASE = "지우는 마케팅 회사에서 대리로 일한다"
SWITCHES = (("기본값", None), ("전이 전파 켬", True))

# 9 ~ 11단계의 새 방 — 턴 5는 **안 지운** 발화인데 지운 값(«마케팅 회사 대리»)의 어근을 통째로 품는다
# (w26final P4 모양). 재료 보존 대역에서 재등장 거부가 결정적으로 난다 — 원인이 안 지운 턴에 있다.
HOLD_ECHO = "마케팅 회사 대리 일이 요즘 힘들다"
HOLD_TURNS = [(1, "user", QUIET), (2, "character", "다행이네"),
              (3, "user", SECRET), (4, "character", "그랬구나"),
              (5, "user", HOLD_ECHO), (6, "character", "힘내라")] + TURNS[6:] + [
              (13, "user", "주말에 영화 봤어"), (14, "character", "뭐 봤냐"),
              (15, "user", "액션 영화였어"), (16, "character", "재밌었겠네"),
              (17, "user", "이제 잘게"), (18, "character", "잘 자")]
# 사실 셋 — 조용한 것(턴 1) · 지울 것(턴 3) · 턴 5의 사실(11단계에서 지우면 턴 5가 가려져 원인이 사라진다).
HOLD_FACTS = {"quiet": ("반려동물_이름", "고양이 나비", "지우가 고양이 나비를 키운다", 1),
              "secret": ("직업", "마케팅 회사 대리", "지우는 마케팅 회사 대리로 일한다", 3),
              "echo": ("선호", "대리 일 줄이기", "지우는 대리 일을 줄이고 싶어 한다", 5)}

SESSION_HEAD = summarize._SESSION_MATERIAL_HEADER.split("{")[0]    # «[대화 — 세션 »
LIFE_HEAD = summarize._LIFETIME_MATERIAL_HEADER.split("{")[0]      # «[재료 — 세션 요약 »
LIFE_TAIL = "\n\n[다시 쓴 요약]"


def _session_of(prompt):
    """세션 요약 프롬프트면 그 키(`session:S01`), 아니면 None."""
    if SESSION_HEAD not in prompt:
        return None
    return prompt.split(SESSION_HEAD, 1)[1].split(" · ", 1)[0]


class _Summarizer:
    """
    `llm.generate` 대역 — **재료 보존 요약기.** 프롬프트를 전부 적는다.

    세션 요약 → 재료의 유저 발화를 ` / `로 이어 붙인다. lifetime → 재료의 세션 요약 본문을 이어 붙인다.
    `revive={키: 문장}`이면 그 세션 요약 끝에 문장을 덧붙인다 — 지운 사실을 **다른 표면으로** 되살리는
    요약기(8단계). 제품 코드의 진행 출력(토큰 보고 · 실패 알림)은 삼켜 `log`에 둔다.
    """

    def __init__(self, revive=None):
        self.revive = dict(revive or {})
        self.prompts = []
        self.log = io.StringIO()

    def __enter__(self):
        self._saved = (llm.generate, llm.last_usage)
        self._quiet = contextlib.redirect_stdout(self.log)
        self._quiet.__enter__()
        stub = self

        def gen(prompt):
            stub.prompts.append(prompt)
            key = _session_of(prompt)
            if key:
                body = " / ".join(line.split("] ", 1)[1]
                                  for line in prompt.splitlines() if "[user]" in line)
                return body + (f" / {stub.revive[key]}" if key in stub.revive else "")
            material = prompt.split(LIFE_HEAD, 1)[1].split("\n", 1)[1].split(LIFE_TAIL)[0]
            return " / ".join(line for line in material.splitlines()
                              if line.strip() and not line.startswith("[session:"))

        llm.generate = gen
        llm.last_usage = lambda: {"prompt_eval_count": 100}
        return self

    def __exit__(self, *exc):
        llm.generate, llm.last_usage = self._saved
        self._quiet.__exit__(*exc)
        return False

    def session_prompts(self, key):
        return [p for p in self.prompts if _session_of(p) == key]

    def lifetime_prompts(self):
        return [p for p in self.prompts if LIFE_HEAD in p]


class _Room:
    """한 흐름의 상태 — DB · 사실 id · 서빙 누적 계수 · 표식(변이 러너가 읽는다)."""

    def __init__(self, tmp):
        self.m = Memory(os.path.join(tmp, "t.db"))
        self.ids = {}
        self.served = {"stale_served": 0, "stale_expired": 0}
        self.marks = {}


def _leaks(ctx, word):
    """
    `word`가 선 자리 — `recent`·`utterance`를 뺀 블록 이름과 provenance 종류.
    provenance까지 보는 이유: 검색 후보(`retrieved` · `rejected`)는 본문을 provenance에 옮겨 적는다.
    """
    out = [b.name for b in ctx.blocks if b.name not in ("recent", "utterance") and word in b.text]
    out += [p[0] for p in ctx.provenance if any(word in str(x) for x in p[1:])]
    return out


def _blocks(ctx):
    return {b.name: b.text for b in ctx.blocks}


class _Flow(unittest.TestCase):
    """흐름 도우미. 스위치 두 값마다 새 방 하나 — 기본값 쪽은 모듈 값을 **건드리지 않는다**."""

    def setUp(self):
        self._saved = (summarize.GEN_RETRIES, summarize.GEN_RETRY_SLEEP,
                       memory.TRANSITION_PROPAGATES_DIGEST)
        summarize.GEN_RETRIES, summarize.GEN_RETRY_SLEEP = 1, 0.0
        self.tmps = []
        self.rooms = {}

    def tearDown(self):
        (summarize.GEN_RETRIES, summarize.GEN_RETRY_SLEEP,
         memory.TRANSITION_PROPAGATES_DIGEST) = self._saved
        for room in self.rooms.values():
            room.m.db.close()
        for d in self.tmps:
            shutil.rmtree(d, ignore_errors=True)

    def each_switch(self):
        """
        `(라벨, 방)`을 차례로 — 스위치 값마다 새 방. 켬 쪽은 그 흐름 동안만 스위치를 켠다.
        실패는 단계마다 `step`의 subTest가 받는다 — 여기서는 스위치만 되돌린다(`tearDown`도 되돌린다).
        """
        for label, value in SWITCHES:
            self.tmps.append(tempfile.mkdtemp())
            room = self.rooms[label] = _Room(self.tmps[-1])
            memory.TRANSITION_PROPAGATES_DIGEST = (self._saved[2] if value is None else value)
            try:
                yield label, room
            finally:
                memory.TRANSITION_PROPAGATES_DIGEST = self._saved[2]

    def step(self, label, name):
        return self.subTest(switch=label, step=name)

    # ── 조회 ───────────────────────────────────────────────────────────
    def serve(self, room, who, seq):
        ctx = room.m.build_context(CHAT, ASK[who], seq)
        kinds = [p[0] for p in ctx.provenance]
        for k in room.served:
            room.served[k] += kinds.count(k)
        return ctx

    def stale_digest(self, room):
        return sorted(r[0] for r in room.m.db.execute(
            "SELECT derived_key FROM stale WHERE chat_id=? AND derived_kind='digest'", (CHAT,)))

    def prov(self, room, kind):
        return [tuple(r) for r in room.m.db.execute(
            "SELECT item, reason FROM provenance WHERE chat_id=? AND kind=?", (CHAT, kind))]

    def body(self, room, key):
        r = room.m.db.execute("SELECT content FROM digest_session WHERE chat_id=? AND kind=?",
                              (CHAT, key)).fetchone()
        return None if r is None else r[0]

    def sources_of(self, room, key):
        return [tuple(r) for r in room.m.db.execute(
            "SELECT source_kind, source_id FROM derivation WHERE chat_id=?"
            " AND derived_kind='digest' AND derived_key=?", (CHAT, key))]

    def deleted_sources(self, room):
        """digest 키의 파생 등록 중 원본이 `user_deleted=1`인 행 — 재생성이 지운 원본을 다시 적었나."""
        return [tuple(r) for r in room.m.db.execute(
            "SELECT d.derived_key, d.source_kind, d.source_id FROM derivation d"
            " LEFT JOIN fact f ON d.source_kind='fact' AND f.fact_id=CAST(d.source_id AS INTEGER)"
            " LEFT JOIN event e ON d.source_kind='event' AND e.event_id=CAST(d.source_id AS INTEGER)"
            " WHERE d.chat_id=? AND d.derived_kind='digest'"
            " AND COALESCE(f.user_deleted, e.user_deleted, 0)=1", (CHAT,))]

    def stage(self, room):
        return room.m.db.execute("SELECT stage FROM relationship WHERE chat_id=?",
                                 (CHAT,)).fetchone()[0]

    # ── 9 ~ 11 도우미 (w33k) ──────────────────────────────────────────
    def plant(self, room, pred, obj, copy, seq):
        """사실 하나 + 소크 모양의 색인 복사본 — `play_through_6`의 1단계와 같은 모양."""
        m = room.m
        m.upsert_fact(CHAT, "지우", pred, obj, seq=seq, importance=0.8)
        fid = m.db.execute("SELECT fact_id FROM fact WHERE chat_id=? AND object=?",
                           (CHAT, obj)).fetchone()[0]
        _, ev = m.add_event(CHAT, copy, seq, emotional_weight=0.0, importance=0.8, narrative_role="사실")
        m.record_derivation(CHAT, "event", str(ev), [("fact", fid)])
        return fid

    def reason(self, room, key="session:S01"):
        row = room.m.stale_row(CHAT, "digest", key)
        return None if row is None else row[0]

    def covers(self, room, key):
        r = room.m.db.execute("SELECT covers_from_seq, covers_to_seq FROM digest_session"
                              " WHERE chat_id=? AND kind=?", (CHAT, key)).fetchone()
        return None if r is None else tuple(r)

    def holds(self, room):
        """본문이 빈 `digest_session` 행(표지)의 수."""
        return room.m.db.execute("SELECT COUNT(*) FROM digest_session WHERE chat_id=? AND content=''",
                                 (CHAT,)).fetchone()[0]

    def bare_holds(self, room):
        """stale 없는 표지 행 — 빈 본문이 서빙되는 상태. 제품 경로에서 늘 0이다(DB 불변)."""
        return [r[0] for r in room.m.db.execute(
            "SELECT kind FROM digest_session d WHERE chat_id=? AND content=''"
            " AND NOT EXISTS (SELECT 1 FROM stale s WHERE s.chat_id=d.chat_id"
            " AND s.derived_kind='digest' AND s.derived_key=d.kind)", (CHAT,))]

    def regen_trail(self, room, key="session:S01"):
        """그 키의 재생성 계열 provenance 행 수(`regen_failed` · `regen_masked` · `regen_abandoned` …)."""
        return room.m.db.execute("SELECT COUNT(*) FROM provenance WHERE chat_id=? AND item=?"
                                 " AND kind LIKE 'regen%'", (CHAT, key)).fetchone()[0]

    def lifetime_keys(self, room):
        return sorted(r[0] for r in room.m.db.execute(
            "SELECT source_id FROM derivation WHERE chat_id=? AND derived_kind='digest'"
            " AND derived_key='lifetime' AND source_kind='digest'", (CHAT,)))

    # ── 1 ~ 6′ (두 시험이 같이 간다) ─────────────────────────────────────
    def play_through_6(self, label, room):
        m = room.m
        with self.step(label, "1 쓰기"):
            soak.seed(m)
            for seq, role, text in TURNS:
                m.add_turn(CHAT, seq, role, text)
            copies = set()
            for who, (pred, obj, copy, seq) in FACTS.items():
                m.upsert_fact(CHAT, "지우", pred, obj, seq=seq, importance=0.8)
                fid = m.db.execute("SELECT fact_id FROM fact WHERE chat_id=? AND object=?",
                                   (CHAT, obj)).fetchone()[0]
                _, ev = m.add_event(CHAT, copy, seq, emotional_weight=0.0, importance=0.8,
                                    narrative_role="사실")
                m.record_derivation(CHAT, "event", str(ev), [("fact", fid)])
                room.ids[who] = fid
                copies.add(ev)
            m.db.commit()
            self.assertEqual(len(copies), 3, "색인 복사본이 서로 합쳐졌다 — 사실마다 하나여야 한다")

        with self.step(label, "2 경계1"):
            with _Summarizer() as st:
                out = regen_job.run(m, CHAT, now_seq=7, ended_session_id="S01", from_seq=1, to_seq=6)
            ctx = self.serve(room, "secret", 8)
            b = _blocks(ctx)
            self.assertEqual(out["session"], ("session:S01", []))
            self.assertIsNone(out["lifetime"], "재료 1개로 lifetime을 만들었다 — Q3(M+1)")
            self.assertEqual(len(st.prompts), 1)
            # 대조의 바닥 — 삭제 전에는 비밀이 세 파생물에 **있다.**
            self.assertEqual(b["digest:session:S01"].count(SECRET), 1)
            self.assertIn("마케팅 회사 대리", b["알고 있는 것"])
            self.assertIn(FACTS["secret"][2], b.get("retrieved", ""))
            self.assertIn(("fact", str(room.ids["secret"])), self.sources_of(room, "session:S01"))

        with self.step(label, "3 삭제"):
            hit = m.delete_item(CHAT, "fact", room.ids["secret"])
            ctx = self.serve(room, "secret", 9)
            self.assertIn(("digest", "session:S01"), hit)
            self.assertEqual(self.stale_digest(room), ["session:S01"])
            self.assertEqual(_leaks(ctx, MARK["secret"]), [], "삭제 뒤 파생물에 지운 사실")
            self.assertIn(("stale", "digest:session:S01"), [p[:2] for p in ctx.provenance])

        with self.step(label, "4 전이"):
            before = dict(room.served)
            m.apply_meta(CHAT, 9, {"state_delta": {"stage": "다툼중", "affinity": 80}})
            ctx = self.serve(room, "secret", 10)
            self.assertEqual(self.stage(room), "다툼중", "전이가 일어나지 않았다 — 대조의 바닥")
            self.assertEqual(_leaks(ctx, MARK["secret"]), [], "전이 뒤 파생물에 지운 사실")
            self.assertEqual(room.served, before, "전이 직후 경고 주입·만료 — 삭제 사유를 전이가 덮었다")
            self.assertTrue(m.stale_row(CHAT, "digest", "session:S01")[0].endswith("삭제됨"))

        with self.step(label, "5 경계2"):
            with _Summarizer() as st:
                out = regen_job.run(m, CHAT, now_seq=13, ended_session_id="S02", from_seq=7, to_seq=12)
            room.marks["5 재생성 프롬프트 속 비밀"] = sum(p.count(MARK["secret"]) for p in st.prompts)
            room.marks["5 lifetime 행"] = m.db.execute(
                "SELECT COUNT(*) FROM digest WHERE chat_id=? AND kind='lifetime'", (CHAT,)).fetchone()[0]
            self.assertEqual(out["session"], ("session:S02", []))
            self.assertEqual(room.marks["5 재생성 프롬프트 속 비밀"], 0,
                             "지운 사실이 재생성 재료로 갔다 — 발견 1")
            self.assertEqual(out["regen"], {"ok": ["session:S01"], "failed": []})
            # 계획 문구 «ok == [session:S01, lifetime]»은 Q3 이전 모양이다 — 첫 lifetime은 ②가 아니라
            # ③이 만든다(`.omc/notepads/w24a/prereg.md` §2).
            self.assertEqual(out["lifetime"], "created", "경계 2가 첫 lifetime을 만들지 않았다 — 발견 2")
            self.assertNotIn("\n3. [user] ", st.session_prompts("session:S01")[0])
            self.assertEqual(self.stale_digest(room), [])
            self.assertEqual(self.deleted_sources(room), [], "재생성이 지운 원본을 파생 등록에 다시 적었다")
            self.assertEqual(self.prov(room, "regen_failed"), [])

        with self.step(label, "6 서빙"):
            ctx_s, ctx_q = self.serve(room, "secret", 14), self.serve(room, "quiet", 14)
            self.assertEqual(_leaks(ctx_s, MARK["secret"]) + _leaks(ctx_q, MARK["secret"]), [],
                             "경계 2 뒤 파생물에 지운 사실")
            self.assertIn("digest:lifetime", _blocks(ctx_q), "lifetime 블록이 없다 — 발견 2")
            self.assertIn(QUIET, _blocks(ctx_q)["digest:lifetime"])

        with self.step(label, "6q 조용한 쪽"):
            b = _blocks(self.serve(room, "quiet", 14))
            self.assertIn("고양이 나비", b["알고 있는 것"])
            self.assertIn(FACTS["quiet"][2], b.get("retrieved", ""))
            self.assertIn(QUIET, self.body(room, "session:S01"))
            self.assertIn("수영 강습", b["알고 있는 것"])            # 아직 안 지운 것도 그대로

        with self.step(label, "6′ 전이 둘째"):
            m.apply_meta(CHAT, 14, {"state_delta": {"stage": "연인", "affinity": 84}})
            ctx = self.serve(room, "quiet", 15)
            here = [p[1] for p in ctx.provenance if p[0] == "stale_served"]
            room.marks["6′ 경고 주입(누적)"] = room.served["stale_served"]
            self.assertEqual(self.stage(room), "연인", "전이가 일어나지 않았다 — 대조의 바닥")
            self.assertEqual(_leaks(ctx, MARK["secret"]), [])
            if label == "기본값":
                # 발견 3 휴면(Q4=A)의 기계 단언 — 기본값 제품 경로에서 경고 주입·만료는 한 번도 안 난다.
                self.assertEqual(room.served, {"stale_served": 0, "stale_expired": 0},
                                 "기본값에서 서빙 3분기가 살아 있다 — 전이가 digest를 밀었다")
            else:
                self.assertGreaterEqual(len(here), 1, "스위치를 켰는데 경고 주입이 없다 — 이 단계는 갈리지 않는다")
                self.assertIn("digest:lifetime", here)
                self.assertEqual(room.served["stale_expired"], 0)


class TestDeletionRoundTrip(_Flow):

    def test_roundtrip_through_the_cap(self):
        """
        1 → 6′ → 7. 7단계는 세션을 N+1까지 밀어 S01이 상한에 밀려난 뒤 S01의 사실을 지운다 — 밀려난 키가
        옛 원본의 삭제로 다시 stale이 되면(행 없는 유령) 재생성이 경계마다 실패를 남긴다(발견 4).
        조용한 쪽(7q)은 끝까지 [알고 있는 것]·검색 블록에 있다.
        """
        for label, room in self.each_switch():
            self.play_through_6(label, room)
            m, n = room.m, memory.DIGEST_KEEP_SESSIONS
            with self.step(label, "7 상한 뒤 유령"):
                seq, outs = 12, []
                with _Summarizer():
                    for s in range(3, n + 2):
                        a = seq + 1
                        m.add_turn(CHAT, a, "user", f"세션 {s} 잡담 — 별일 없었어")
                        m.add_turn(CHAT, a + 1, "character", "그래")
                        seq = a + 1
                        outs.append(regen_job.run(m, CHAT, now_seq=seq + 1, ended_session_id=f"S{s:02d}",
                                                  from_seq=a, to_seq=seq))
                self.assertEqual(outs[-1]["session"][1], ["session:S01"], "N+1번째 경계가 S01을 밀어내지 않았다")
                self.assertIn("수영 강습", _blocks(self.serve(room, "swim", seq + 1))["알고 있는 것"])  # 대조의 바닥
                hit = m.delete_item(CHAT, "fact", room.ids["swim"])
                with _Summarizer():
                    out = regen_job.run(m, CHAT, now_seq=seq + 2, make_digest=False)
                room.marks["7 유령 stale"] = len(self.stale_digest(room))
                room.marks["7 regen_failed(흐름 전체)"] = len(self.prov(room, "regen_failed"))
                ctx_w, ctx_s = self.serve(room, "swim", seq + 3), self.serve(room, "secret", seq + 3)
                self.assertEqual([o["regen"]["failed"] for o in outs if o["regen"]["failed"]], [])
                self.assertEqual(self.sources_of(room, "session:S01"), [])
                self.assertEqual([h for h in hit if h[0] == "digest"], [], "밀려난 키가 삭제로 다시 stale")
                self.assertEqual(self.stale_digest(room), [])
                self.assertEqual(out["regen"], {"ok": [], "failed": []})
                self.assertEqual(room.marks["7 regen_failed(흐름 전체)"], 0)
                for ctx in (ctx_w, ctx_s):
                    self.assertEqual(_leaks(ctx, MARK["swim"]) + _leaks(ctx, MARK["secret"]), [])
                if label == "기본값":
                    self.assertEqual(room.served, {"stale_served": 0, "stale_expired": 0})

            with self.step(label, "7q 조용한 쪽"):
                b = _blocks(self.serve(room, "quiet", seq + 3))
                self.assertIn("고양이 나비", b["알고 있는 것"])
                self.assertIn(FACTS["quiet"][2], b.get("retrieved", ""))

    def test_reviving_summarizer_after_step_6(self):
        """
        1 → 6′ → 8. 6′까지 간 방에서 «수영 강습»(S01)을 지우고, S01 요약기가 앞서 지운 비밀을 재서술해
        돌려준다 → S01은 저장되지 않고(재등장 · stale 유지), lifetime은 S01을 **빼고** 다시 써진다 —
        S01의 옛 본문에는 방금 지운 «수영 강습»이 들어 있으므로 빼지 않으면 lifetime이 되살린다(K1).
        조용한 쪽(8q)은 [알고 있는 것]·검색 블록에 있다.
        """
        for label, room in self.each_switch():
            self.play_through_6(label, room)
            m = room.m
            with self.step(label, "8 재등장 대역"):
                old = self.body(room, "session:S01")
                hit = m.delete_item(CHAT, "fact", room.ids["swim"])
                with _Summarizer(revive={"session:S01": PARAPHRASE}) as st:
                    out = regen_job.run(m, CHAT, now_seq=16, make_digest=False)
                ctxs = [self.serve(room, who, 17) for who in ("swim", "secret", "quiet")]
                s01 = st.session_prompts("session:S01")
                room.marks["8 lifetime 재료 속 지운 사실"] = sum(
                    p.count(w) for p in st.lifetime_prompts() for w in MARK.values())
                room.marks["8 S01 재생성 프롬프트 속 지운 원문"] = sum(
                    p.count(SECRET) + p.count(SWIM) for p in s01)
                room.marks["8 서빙 속 지운 사실"] = sum(len(_leaks(c, w)) for c in ctxs for w in MARK.values())
                self.assertIn(("digest", "session:S01"), hit)
                self.assertIn(("digest", "lifetime"), hit)
                self.assertEqual(len(s01), 1)
                self.assertEqual(room.marks["8 S01 재생성 프롬프트 속 지운 원문"], 0)
                self.assertEqual([k for k, _ in out["regen"]["failed"]], ["session:S01"])
                self.assertIn("재등장", out["regen"]["failed"][0][1])
                self.assertIn("lifetime", out["regen"]["ok"])
                self.assertEqual(self.stale_digest(room), ["session:S01"])
                self.assertEqual(self.body(room, "session:S01"), old, "거부했는데 행이 바뀌었다")
                self.assertEqual(room.marks["8 lifetime 재료 속 지운 사실"], 0,
                                 "stale인 S01 본문이 lifetime 재료로 갔다 — K1")
                self.assertEqual(len(self.prov(room, "lifetime_material_excluded")), 1)
                self.assertEqual(room.marks["8 서빙 속 지운 사실"], 0)

            with self.step(label, "8q 조용한 쪽"):
                b = _blocks(self.serve(room, "quiet", 17))
                self.assertIn("고양이 나비", b["알고 있는 것"])
                self.assertIn(FACTS["quiet"][2], b.get("retrieved", ""))
                self.assertNotIn("수영 강습", b["알고 있는 것"])

    def test_first_generation_refused_then_retried_abandoned_and_reset(self):
        """
        9 → 11 (w33k · Fable 계획 2 묶음 K · 결정 2 Q8 (a)). 새 방에서 경계 **전에** 비밀을 지우면 첫 요약(①)이
        턴 5(안 지운 발화 · 같은 낱말) 때문에 재등장으로 거부된다 → 표지 행이 남고(N1) · 다음 경계가 한 번
        재시도하고 · 연속 2회면 포기해 그 뒤 경계는 LLM 0 · provenance 0(N5) · 턴 5의 사실을 지우면 사유가 새로
        써져 다시 시도하고 성공한다(재설정). 9′은 표지 사유를 전이가 덮지 않는가(스위치가 갈리는 자리)다.
        우는 단계 표는 모듈 독스트링 «심은 위반» 끝 절(w33k).
        """
        for label, room in self.each_switch():
            m = room.m
            with self.step(label, "9 ① 거부 → 표지"):
                soak.seed(m)
                for seq, role, text in HOLD_TURNS:
                    m.add_turn(CHAT, seq, role, text)
                for who, (pred, obj, copy, seq) in HOLD_FACTS.items():
                    room.ids[who] = self.plant(room, pred, obj, copy, seq)
                m.db.commit()
                self.assertIn("마케팅 회사 대리", _blocks(self.serve(room, "echo", 7))["알고 있는 것"])  # 대조의 바닥
                m.delete_item(CHAT, "fact", room.ids["secret"])                  # 경계 전에 지움
                with _Summarizer() as st:
                    out = regen_job.run(m, CHAT, now_seq=7, ended_session_id="S01", from_seq=1, to_seq=6)
                s01 = st.session_prompts("session:S01")
                room.marks["9 경계1 S01 LLM"] = len(s01)
                room.marks["9 표지 행"] = self.holds(room)
                self.assertEqual(len(s01), 1)
                self.assertEqual(s01[0].count(SECRET), 0, "지운 턴이 첫 요약의 재료로 갔다")
                self.assertEqual(out["session"][0], "failed")
                self.assertIn("재등장", out["session"][1])
                self.assertEqual(out["regen"], {"ok": [], "failed": []}, "같은 경계에서 표지를 다시 불렀다")
                self.assertEqual(self.body(room, "session:S01"), "",
                                 "첫 요약이 거부됐는데 표지 행이 없다 — 다음 경계가 구간을 모른다 (N1)")
                self.assertEqual(self.covers(room, "session:S01"), (1, 6))
                self.assertTrue(self.reason(room).startswith("미완: "), self.reason(room))
                self.assertTrue(self.reason(room).endswith(" · 시도 1/2"), self.reason(room))
                self.assertTrue(out["missing"], "표지 행을 요약으로 셌다")
                self.assertEqual(len(self.prov(room, "regen_failed")), 1)
                self.assertEqual(self.bare_holds(room), [])
                self.assertEqual(self.deleted_sources(room), [], "표지가 지운 원본을 파생 등록에 적었다")
                ctx = self.serve(room, "echo", 8)
                b = _blocks(ctx)
                self.assertNotIn("digest:session:S01", b)
                # 표지가 최신 세션이라 서빙 후보에 오르고 «제외» 분기가 거른다(3분기 첫 행 · 경고 주입 아님).
                self.assertEqual([p[1] for p in ctx.provenance if p[0] == "stale"], ["digest:session:S01"])
                self.assertEqual(_leaks(ctx, MARK["secret"]), [], "첫 요약 거부 뒤 파생물에 지운 사실")
                self.assertIn("대리 일 줄이기", b["알고 있는 것"])
                self.assertIn("고양이 나비", b["알고 있는 것"])

            with self.step(label, "9′ 전이"):
                before, reason = dict(room.served), self.reason(room)
                m.apply_meta(CHAT, 8, {"state_delta": {"stage": "다툼중", "affinity": 80}})
                ctx = self.serve(room, "echo", 9)
                self.assertEqual(self.stage(room), "다툼중", "전이가 일어나지 않았다 — 대조의 바닥")
                self.assertEqual(self.reason(room), reason, "전이가 표지 사유를 덮었다 — 시도 수가 사라진다")
                self.assertEqual(room.served, before, "표지가 경고와 함께 서빙됐다")
                self.assertNotIn("digest:session:S01", _blocks(ctx))

            # 10 · 11은 경계마다 subTest를 나눈다 — 앞 경계의 단언이 울어도 뒤 경계가 **돈다**(한 subTest 안에서
            # 멈추면 뒤 단계의 방 상태가 달라져 연쇄로 운다 — 그 울음은 검출이 아니다).
            with self.step(label, "10a 경계2 재시도 → 포기"):
                with _Summarizer() as st:
                    out = regen_job.run(m, CHAT, now_seq=13, ended_session_id="S02", from_seq=7, to_seq=12)
                room.marks["10a 경계2 S01 LLM"] = len(st.session_prompts("session:S01"))
                self.assertEqual(out["session"], ("session:S02", []))
                self.assertEqual(room.marks["10a 경계2 S01 LLM"], 1, "표지가 있는데 다음 경계가 재시도하지 않았다 (N1)")
                self.assertEqual([k for k, _ in out["regen"]["failed"]], ["session:S01"])
                self.assertIn("재등장", out["regen"]["failed"][0][1])
                self.assertIsNone(out["lifetime"], "재료 하나(S02)로 lifetime을 만들었다 — Q3")
                self.assertTrue(self.reason(room).endswith(" · 시도 2/2 · 포기"), self.reason(room))
                self.assertEqual([i for i, _ in self.prov(room, "regen_abandoned")], ["session:S01"])

            with self.step(label, "10b 경계3 포기 뒤 호출 0"):
                trail = self.regen_trail(room)
                with _Summarizer() as st:
                    out = regen_job.run(m, CHAT, now_seq=14, make_digest=False)
                room.marks["10b 경계3 S01 LLM"] = len(st.session_prompts("session:S01"))
                room.marks["10b 경계3 S01 provenance 증가"] = self.regen_trail(room) - trail
                self.assertEqual(room.marks["10b 경계3 S01 LLM"], 0, "포기한 키를 또 불렀다 (N5)")
                self.assertEqual(room.marks["10b 경계3 S01 provenance 증가"], 0)
                self.assertEqual(out["regen"], {"ok": [], "failed": []})
                self.assertIsNotNone(self.reason(room), "포기가 stale을 지웠다 — 서빙 제외가 풀린다")

            with self.step(label, "10c 경계4 첫 lifetime"):
                with _Summarizer() as st:
                    out = regen_job.run(m, CHAT, now_seq=19, ended_session_id="S03", from_seq=13, to_seq=18)
                ctx = self.serve(room, "echo", 20)
                life = st.lifetime_prompts()
                room.marks["10c 경계4 S01 LLM"] = len(st.session_prompts("session:S01"))
                room.marks["10c 서빙 stale(S01)"] = [p[1] for p in ctx.provenance
                                                   if p[0] == "stale"].count("digest:session:S01")
                self.assertEqual(out["session"], ("session:S03", []))
                self.assertEqual(room.marks["10c 경계4 S01 LLM"], 0)
                self.assertEqual(out["regen"], {"ok": [], "failed": []})
                self.assertEqual(out["lifetime"], "created", "재료 {S02, S03}에서 첫 lifetime이 안 생겼다")
                self.assertEqual(self.lifetime_keys(room), ["session:S02", "session:S03"])
                self.assertEqual(len(life), 1)
                self.assertEqual(life[0].count(MARK["secret"]), 0)
                self.assertEqual(len(self.prov(room, "lifetime_material_excluded")), 1)
                self.assertNotIn("digest:session:S01", _blocks(ctx))
                # M=1이면 서빙 후보는 최신(S03) 하나라 표지 S01은 후보에도 안 오른다 — «stale» 기록 0(9단계는 1).
                self.assertEqual(room.marks["10c 서빙 stale(S01)"], 0)
                self.assertEqual(_leaks(ctx, MARK["secret"]), [])
                self.assertEqual(len(self.prov(room, "regen_failed")), 2)          # ① 1 + ② 1
                self.assertEqual(self.bare_holds(room), [])

            with self.step(label, "11a 새 삭제 → 사유 재설정"):
                hit = m.delete_item(CHAT, "fact", room.ids["echo"])
                self.assertIn(("digest", "session:S01"), hit, "턴 5의 삭제가 표지 키에 닿지 않았다 — 재설정 길이 없다")
                self.assertNotIn(("digest", "lifetime"), hit)
                self.assertEqual(self.reason(room), f"fact:{room.ids['echo']} 삭제됨",
                                 "새 삭제가 사유를 새로 쓰지 않았다 — 포기가 풀리지 않는다")

            with self.step(label, "11b 경계5 재시도 → 성공"):
                trail = self.regen_trail(room)
                with _Summarizer() as st:
                    out = regen_job.run(m, CHAT, now_seq=20, make_digest=False)
                s01 = st.session_prompts("session:S01")
                body = self.body(room, "session:S01")
                room.marks["11b 경계5 S01 LLM"] = len(s01)
                room.marks["11b 표지 행"] = self.holds(room)
                self.assertEqual(len(s01), 1, "재설정 뒤 재시도가 없다")
                self.assertEqual(out["regen"], {"ok": ["session:S01"], "failed": []})
                self.assertEqual(body, QUIET, "재시도 본문 — 지운 턴 둘만 가리고 조용한 턴 1은 남아야 한다")
                for w in ("마케팅", "대리"):
                    self.assertEqual(sum(p.count(w) for p in st.prompts), 0, f"재시도 프롬프트에 «{w}»")
                self.assertEqual(self.stale_digest(room), [])
                self.assertEqual(room.marks["11b 표지 행"], 0)
                self.assertEqual(self.regen_trail(room) - trail, 1)                # regen_masked 1 · 실패 0
                self.assertEqual(out["lifetime"], "rewritten", "S01이 돌아왔는데 lifetime이 다시 안 써졌다")
                self.assertEqual(self.lifetime_keys(room), ["session:S01", "session:S02", "session:S03"])
                self.assertFalse(out["missing"])
                self.assertEqual(self.deleted_sources(room), [])
                ctx = self.serve(room, "echo", 21)
                self.assertIn(QUIET, _blocks(ctx)["digest:lifetime"])              # S01은 lifetime으로 돌아온다(M=1)
                for w in ("마케팅", "대리"):
                    self.assertEqual(_leaks(ctx, w), [], f"재설정 뒤 파생물에 «{w}»")

            with self.step(label, "11q 조용한 쪽"):
                b = _blocks(self.serve(room, "quiet", 21))
                self.assertIn("고양이 나비", b["알고 있는 것"])
                self.assertIn(HOLD_FACTS["quiet"][2], b.get("retrieved", ""))
                self.assertNotIn("대리", b["알고 있는 것"])


if __name__ == "__main__":
    unittest.main()
