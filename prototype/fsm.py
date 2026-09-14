# -*- coding: utf-8 -*-
"""
fsm.py — 관계 상태 기계 (ADR-014).

`apply_meta`의 컬럼 화이트리스트는 «어느 컬럼에 쓰는가»만 본다. 여기서는 «그 값이 말이 되는가»를 본다 —
stage enum · 전이 허용 · affinity 범위 · 한 턴 변화량(`연인 → 낯섦` 한 방으로 관계가 리셋되지 않게).

전이표는 모듈 상수(`DEFAULT_MACHINE`)를 폴백으로, `stage_machine` 테이블 행을 캐릭터별 오버라이드로 쓴다.
오버라이드 행은 시드하지 않는다 — 시드하면 실사용 DB가 타는 폴백 분기가 한 번도 실행되지 않는다.

한계: `narrative_event`는 LLM이 같은 구조화 출력에서 스스로 세우는 플래그라, 규칙이 «금지»에서
«선언된 예외 + 감사»로 약해진다. 그래서 예외를 전부 `state_violation`에 남겨 예외율을 잴 수 있게 한다.

의존성: 표준 라이브러리만 (json)
"""

import json

# ── 상수 — 전부 모듈 전역이다(시험·스윕이 몽키패치한다) ─────────────────

# 8 stage. docs/06 L2의 주석에만 있던 목록을 코드가 강제하는 enum으로 올린 것이다.
STAGES = ("낯섦", "아는사이", "친구", "썸", "연인", "다툼중", "헤어짐", "재회")

# 허용 전이. 자기 전이(stage 유지)는 항상 허용한다 — 대부분의 턴이 그렇다.
TRANSITIONS = {
    "낯섦":     ("아는사이",),
    "아는사이": ("친구",),
    "친구":     ("썸", "다툼중"),
    "썸":       ("연인", "친구"),
    "연인":     ("다툼중", "헤어짐"),
    "다툼중":   ("연인", "헤어짐", "친구"),
    "헤어짐":   ("재회",),
    "재회":     ("연인", "헤어짐"),
}

# stage별 affinity 유효 범위(양끝 포함). 넓게 잡는다 — «연인인데 호감도 3» 같은 명백한 모순만 잡는
# 안전망이고, 좁히면 서사적으로 정상인 궤적을 막아 예외 선언만 는다. `다툼중`은 어느 호감도에서도 일어난다.
AFFINITY_BANDS = {
    "낯섦":     (0, 40),
    "아는사이": (0, 60),
    "친구":     (10, 80),
    "썸":       (30, 95),
    "연인":     (40, 100),
    "다툼중":   (0, 100),
    "헤어짐":   (0, 70),
    "재회":     (20, 100),
}

AFFINITY_MIN = 0
AFFINITY_MAX = 100

# 한 턴에 호감도가 크게 튀면 대개 모델의 과장이지 관계의 변화가 아니다(docs/14) — 한 턴 상한 5.
AFFINITY_STEP_MAX = 5

DEFAULT_MACHINE = {
    "stages": STAGES,
    "transitions": TRANSITIONS,
    "affinity_bands": AFFINITY_BANDS,
}

# 거부·감사 사유 문자열 — `state_violation.reason`에 그대로 들어간다. 서빙 정책과 `fsm_probe.py`가
# 이 문자열로 분기하므로 상수로 둔다.
R_LOCKED = "user_locked"
R_STAGE_TYPE = "stage_type"
R_STAGE_UNKNOWN = "stage_unknown"
R_TRANSITION = "transition_forbidden"
R_AFFINITY_TYPE = "affinity_type"
R_AFFINITY_RANGE = "affinity_range"
R_AFFINITY_BAND = "affinity_band"
R_AFFINITY_JUMP = "affinity_jump"
R_NARRATIVE = "narrative_exception"


def load_machine(db, character_id, character_version):
    """
    캐릭터·버전별 오버라이드를 읽는다. 행이 없으면 `DEFAULT_MACHINE`.
    키 형태는 `character_version` 테이블과 같다. 이 저장소에는 `stage_machine` 행이 없으므로
    폴백이 실사용 경로이고, 행이 있는 분기는 단위 시험에서만 실행된다.
    """
    row = db.execute(
        "SELECT stages, transitions, affinity_bands FROM stage_machine"
        " WHERE character_id=? AND version=?",
        (character_id, character_version)).fetchone()
    if row is None:
        return DEFAULT_MACHINE
    # 저장 형식은 JSON 문자열 3개. transitions는 {stage: [허용 목적지]},
    # affinity_bands는 {stage: [lo, hi]}.
    return {
        "stages": tuple(json.loads(row["stages"])),
        "transitions": {k: tuple(v)
                        for k, v in json.loads(row["transitions"]).items()},
        "affinity_bands": {k: tuple(v)
                           for k, v in json.loads(row["affinity_bands"]).items()},
    }


def _as_int(v):
    """`True`는 `int`의 인스턴스다 — 여기서는 정수로 받으면 안 된다."""
    if isinstance(v, bool) or not isinstance(v, int):
        return None
    return v


def validate(machine, cur, delta, *, narrative_event=False):
    """
    상태 전이 검증. 반환 `(ok, new_state, reason)`.

    `cur`   현재 `relationship` 행 (dict 또는 `sqlite3.Row` — `stage`·`affinity`·`user_locked`를 읽는다)
    `delta` 화이트리스트를 이미 통과한 `state_delta` (`Memory._filter_cols`)

    `ok=True`인데 `reason='narrative_exception'`인 경우가 있다 — 거부가 아니라 감사 기록이다.
    호출부는 UPDATE를 하고 `state_violation`에도 남긴다.
    """
    stages = machine["stages"]
    transitions = machine["transitions"]
    bands = machine["affinity_bands"]

    old_stage = cur["stage"]
    old_aff = cur["affinity"]
    new_state = {"stage": old_stage, "affinity": old_aff}

    # ① 유저가 잠근 관계는 아무것도 못 바꾼다. 다른 검사보다 먼저다 — 유저 의사가 가장 강한 거부 사유다.
    if cur["user_locked"]:
        return False, new_state, R_LOCKED

    # ② stage — 타입 → enum → 전이 순. 순서가 곧 오류 메시지의 구체성 순이다.
    if "stage" in delta:
        s = delta["stage"]
        if not isinstance(s, str):
            return False, new_state, R_STAGE_TYPE
        if s not in stages:
            return False, new_state, R_STAGE_UNKNOWN
        if s != old_stage and s not in transitions.get(old_stage, ()):
            return False, new_state, R_TRANSITION
        new_state["stage"] = s

    # ③ affinity — 타입 → 절대 범위 → stage별 밴드 → 변화량. 절대 범위를 먼저 보는 이유:
    #    `affinity=999`는 밴드 이탈이 아니라 그냥 값이 아니다. 사유가 정확해야 셀 수 있다.
    if "affinity" in delta:
        a = _as_int(delta["affinity"])
        if a is None:
            return False, new_state, R_AFFINITY_TYPE
        if not (AFFINITY_MIN <= a <= AFFINITY_MAX):
            return False, new_state, R_AFFINITY_RANGE
        lo, hi = bands.get(new_state["stage"], (AFFINITY_MIN, AFFINITY_MAX))
        if not (lo <= a <= hi):
            return False, new_state, R_AFFINITY_BAND
        new_state["affinity"] = a

        # ④ 변화량 규칙. 셋 중 하나로 끝난다.
        if abs(a - (old_aff or 0)) > AFFINITY_STEP_MAX:
            if not narrative_event:
                return False, new_state, R_AFFINITY_JUMP
            # 선언된 예외 — 통과시키되 반드시 감사 행을 남긴다.
            return True, new_state, R_NARRATIVE

    # ⑤ 밴드는 결과 상태의 불변식이다. stage만 담긴 델타도 새 stage의 밴드를 본다 — 안 보면
    #    `연인/84 → 헤어짐/84`(헤어짐 밴드 0~70 밖)가 통과하고, 그 뒤 정상적인 작은 변화가 전부
    #    `affinity_band`로 거부되어 행이 «선언된 예외로만 나갈 수 있는 상태»에 갇힌다.
    #    델타에 affinity가 있으면 ③이 이미 같은 밴드를 봤다.
    if "stage" in delta and "affinity" not in delta:
        lo, hi = bands.get(new_state["stage"], (AFFINITY_MIN, AFFINITY_MAX))
        if not (lo <= (new_state["affinity"] or 0) <= hi):
            return False, new_state, R_AFFINITY_BAND

    return True, new_state, None
