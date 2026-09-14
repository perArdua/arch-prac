"""
메모리 시스템 프로토타입 — 계층형 기억의 저장과 컨텍스트 조립.

  L0 turn          원본 (영구)
  L1 character     페르소나 + speech_rules (버전 고정)
  L2 relationship  관계 상태 — 항상 주입 (결정적)
  L3 scene         씬 — 항상 주입
  L4 digest        session / lifetime 2층
  L5 fact          bi-temporal
  L6 event         importance + surfaced_count
  L9 debt          트리거 + 백오프
  M  coverage      구간별 해상도

의존성: 표준 라이브러리(sqlite3, re, json) + 같은 폴더의 embedding · fsm.
"""

import json
import math
import re
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Optional

import embedding                             # 문서 벡터 저장소 (embed 모드)
import fsm                                   # 관계 상태 기계 (ADR-014)

# ── 스키마 ──────────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS turn (
  chat_id TEXT, seq INTEGER, role TEXT, text TEXT,
  created_at REAL, token_count INTEGER,
  extract_status TEXT DEFAULT 'pending',
  PRIMARY KEY (chat_id, seq));

CREATE TABLE IF NOT EXISTS character_version (
  character_id TEXT, version INTEGER,
  persona_text TEXT, speech_rules TEXT, taboos TEXT,
  PRIMARY KEY (character_id, version));

CREATE TABLE IF NOT EXISTS chat (
  chat_id TEXT PRIMARY KEY, user_id TEXT,
  character_id TEXT, character_version INTEGER);

CREATE TABLE IF NOT EXISTS relationship (
  chat_id TEXT PRIMARY KEY,
  stage TEXT, stage_note TEXT, affinity INTEGER,
  last_emotion TEXT, called_as TEXT,
  user_locked INTEGER DEFAULT 0,
  updated_by_turn INTEGER);

CREATE TABLE IF NOT EXISTS scene (
  chat_id TEXT PRIMARY KEY,
  place TEXT, present TEXT, situation TEXT, updated_by_turn INTEGER);

CREATE TABLE IF NOT EXISTS digest (
  chat_id TEXT, kind TEXT, content TEXT,
  covers_to_seq INTEGER, session_end_note TEXT,
  PRIMARY KEY (chat_id, kind));

CREATE TABLE IF NOT EXISTS fact (
  fact_id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT,
  subject TEXT, predicate TEXT, object TEXT, realm TEXT,
  valid_from REAL, valid_until REAL, source_turn_seq INTEGER,
  importance REAL, confidence REAL, mention_count INTEGER DEFAULT 1,
  superseded_by INTEGER, user_deleted INTEGER DEFAULT 0,
  UNIQUE (chat_id, source_turn_seq, predicate, object));

CREATE TABLE IF NOT EXISTS event (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT,
  summary TEXT, occurred_at REAL,
  emotional_weight REAL, importance REAL, narrative_role TEXT,
  source_from_seq INTEGER,
  retrieval_count INTEGER DEFAULT 0,
  surfaced_count INTEGER DEFAULT 0,
  user_pinned INTEGER DEFAULT 0, user_deleted INTEGER DEFAULT 0,
  mention_count INTEGER DEFAULT 1,
  dedup_key TEXT);          -- docs/16 §3 — 같은 사건의 반복 언급을 합친다

CREATE TABLE IF NOT EXISTS debt (
  debt_id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT,
  content TEXT, setup_turn_seq INTEGER,
  trigger_kind TEXT, trigger_spec TEXT, trigger_clock TEXT,
  status TEXT DEFAULT 'open', emotional_stake REAL,
  last_attempted_seq INTEGER, attempt_count INTEGER DEFAULT 0);

CREATE TABLE IF NOT EXISTS coverage (
  chat_id TEXT, from_seq INTEGER, to_seq INTEGER, resolution TEXT,
  PRIMARY KEY (chat_id, from_seq));

-- 파생 관계 — 무엇이 무엇에서 나왔나 (docs/16 §4)
--
-- 🔴 user_deleted는 fact/event에만 있었고 **파생물로 전파되지 않았다.**
--    사실 하나를 지워도 요약·해석에는 그대로 남는다. 개인정보 삭제를
--    이걸로 만족했다고 말할 수 없다.
--    별도 테이블로 둔 이유: digest에 컬럼을 더하면 기존 위치기반 INSERT가 깨진다.
CREATE TABLE IF NOT EXISTS derivation (
  chat_id TEXT, derived_kind TEXT, derived_key TEXT,   -- 예: ('digest','lifetime')
  source_kind TEXT, source_id TEXT);                   -- 예: ('fact','12')

CREATE TABLE IF NOT EXISTS stale (
  chat_id TEXT, derived_kind TEXT, derived_key TEXT,
  reason TEXT, marked_at REAL,
  PRIMARY KEY (chat_id, derived_kind, derived_key));

-- 스키마·생성기 버전 (docs/16 §7)
--
-- 🔴 docs/06에 schema_version·generator_version **필드는 있는데 절차가 없었다.**
--    추출 프롬프트를 고치면 이전 기억은 옛 규칙으로 만들어진 것이다.
--    섞어 쓰면 "같은 술어인데 의미가 다른" 데이터가 공존한다.
CREATE TABLE IF NOT EXISTS meta (
  k TEXT PRIMARY KEY, v TEXT);

CREATE TABLE IF NOT EXISTS provenance (
  chat_id TEXT, turn_seq INTEGER, kind TEXT, item TEXT, reason TEXT);

-- ── v4 신규 테이블 (단계 1) ─────────────────────────────────────────────
--
-- 🔴 기존 14개 테이블에는 **컬럼을 하나도 더하지 않는다** (G6). 그중 11개가
--    위치 기반 `INSERT ... VALUES (?,…)`를 받는다 — `turn`(:251)·`meta`(:230)·
--    `soak.py`·`demo.py`·`quality_run.py` 등 호출부가 흩어져 있어서, 컬럼을
--    하나 더하면 그 자리에서 조용히 어긋난다. 나머지 3개(`fact`·`event`·`debt`)는
--    컬럼 목록 INSERT라 이론상 가능하지만 **그래도 안 한다**: 예외를 하나 열면
--    다음 사람이 그것을 선례로 쓴다. 신규 상태는 전부 측면 테이블로 간다.

-- 관계 FSM의 캐릭터별 오버라이드. 키 형태는 `character_version`(:38)과 같다.
-- ⚠️ **시드하지 않는다** — 행이 없어야 `load_machine`의 폴백(DEFAULT_MACHINE)
--    분기를 `soak`·`gate_sweep`·기존 DB가 전부 실제로 탄다 (단계 2에서 쓴다).
CREATE TABLE IF NOT EXISTS stage_machine (
  character_id TEXT, version INTEGER, stages TEXT, transitions TEXT,
  affinity_bands TEXT, PRIMARY KEY (character_id, version));

-- 거부된 상태 전이·범위 위반·`narrative_exception` 감사 기록 (단계 2).
-- 위반을 예외로 던지지 않고 **데이터로 남긴다** — 예외율을 재야 규칙이
-- 의미 있는지 알 수 있다.
CREATE TABLE IF NOT EXISTS state_violation (
  chat_id TEXT, turn_seq INTEGER, field TEXT,
  from_value TEXT, to_value TEXT, reason TEXT, marked_at REAL);

-- 런타임 임베딩 서빙 캐시. **스윕은 이 테이블을 쓰지 않는다** —
-- `gate_sweep.py:288-292`가 셀마다 DB를 지우므로 캐시가 매번 증발한다.
-- 스윕용 캐시는 DB 밖 파일(`embedding.CACHE_PATH`)이고, 두 경로는
-- `embedding.cache_key()` **하나**를 공유한다.
-- 계획에 DDL이 없어 최소 형태로 둔다: 키는 (텍스트 키, 모델), 벡터는 JSON 문자열.
CREATE TABLE IF NOT EXISTS embedding (
  chat_id TEXT, key TEXT, model TEXT, vec TEXT,
  PRIMARY KEY (key, model));

-- digest의 메타데이터. `digest` 테이블에 컬럼을 더하는 대신 옆에 둔다 (G6).
-- 단계 2가 `stale_since_seq`를 쓰고 단계 5의 `stale_expired`가 읽는다.
CREATE TABLE IF NOT EXISTS digest_meta (
  chat_id TEXT, kind TEXT, generator_version TEXT,
  covers_from_seq INTEGER, covers_to_seq INTEGER,
  generated_at REAL, user_edited_at REAL, stale_since_seq INTEGER,
  PRIMARY KEY (chat_id, kind));

-- ── v5 신규 테이블 (단계 S1) ────────────────────────────────────────────
--
-- 세션 요약을 N세션분(`DIGEST_KEEP_SESSIONS`) 보존한다. 동결 14개에는 컬럼을
-- 하나도 더하지 않는다 (G6) — 새 행은 전부 이 신규 테이블에 있다.
--
-- 🔴 같은 결과를 `digest.kind`를 `"session:S07"`로 **인코딩**해서도 낼 수 있다.
--    그 안을 기각한 근거는 **가시성이 아니라 롤백이다.** 인코딩하면 동결 테이블에
--    24행이 남고, 코드를 v4로 되돌린 순간 상한 없는 전량 주입 루프가 그 24행을
--    매 턴 다 넣는다 — **되돌리기가 컨텍스트 폭발을 남긴다.** 측면 테이블이면
--    v4 코드는 이 테이블을 **읽는 곳이 없어서** 존재만 하고 아무 일도 안 한다
--    (§4.2의 3단계 · v5 DB를 v4 코드로 여는 것은 실측됐다 — S9).
--    ⚠️ *"DDL이 바뀌므로 눈에 띈다"*는 근거로 삼지 않는다. 이 라운드가 실제로
--       계약을 바꾸는 자리는 이 신규 테이블이 아니라 `stale`·`digest_meta`이고
--       (둘 다 digest 키 공간을 따라 행이 생긴다), DDL 가시성은 그 둘을
--       구조적으로 비켜 간다.
--
-- `kind`는 언제나 `session:<sid>` 형태다. 같은 키 문자열을 `stale`·`derivation`·
-- `digest_meta` 셋이 함께 쓰므로 **조립하는 곳을 하나로 둔다** — `session_kind()`.
-- 🔴 신규 테이블은 **처음부터 컬럼 목록 INSERT**를 받는다. 위치 기반 5-값 형태가
--    G6을 만든 원인이고, 그 원인을 새 테이블에서 반복하지 않는다.
CREATE TABLE IF NOT EXISTS digest_session (
  chat_id TEXT, kind TEXT, content TEXT,
  covers_from_seq INTEGER, covers_to_seq INTEGER,
  session_end_note TEXT, generated_at REAL,
  PRIMARY KEY (chat_id, kind));
"""

# ── 설정 (docs/11 실험 7 스윕 결과) ─────────────────────────────────────
TAU_IMPORTANCE = 0.2      # 하드 게이트 (0.2~0.4 둔감구간)
# θ: 검색기만 격리한 스윕(실험 7)의 최적은 0.15였지만, 시스템 전체(gate_sweep)에서는 정답 근거의
# 질문-요약 중첩이 대부분 0.00~0.11이라 정답이 컷 아래에 깔렸다 → 무릎 0.05.
# 0.05로 낮추면 회상 +2 · 오주입 +23(회상 1건당 12), 0.00까지 열면 1건당 188로 급증했다(실험 12 gate_sweep).
# 그 오주입 열은 뒤에 인공물로 정정됐다(질문별 정밀도로 대체) — 값은 유지했고 근거는 `experiments/precision.py`의 4셀이다.
# 이 값은 lexical 척도 전용이다 — 사실상 «겹침이 0인 것만 버린다»는 규칙이고, 코사인 척도로
# 옮기면 아무것도 안 자른다. 척도가 바뀌면 θ도 다시 유도한다(`THETA_BY_MODE`).
# 실측: 채점 18문항 × 색인 21행 = 378쌍에서 θ=0.0001과 똑같이 35쌍(9.3%)을 통과시킨다.
THETA_RELEVANCE = 0.05    # 임계 컷 (0.15 -> 0.05, gate_sweep 무릎)
TOP_K = 5
WINDOW_TURNS = 10         # 무릎 (실험 7C)
SURFACED_PENALTY = 0.1    # 무릎 (실험 10B)
WINDOW_CHUNK = 10         # 청크 축출 (실험 1)
MIN_EVIDENCE_FOR_INTERPRETATION = 3   # 수기 세션에서 도출

# ── 검색 모드 (ADR-015) ─────────────────────────────────────────────────
# 격자가 흔드는 손잡이를 이름 있는 전역으로 둔 것이다. 값은 전부 현행값 그대로다.
RETRIEVAL_MODE = "lexical"        # lexical | lexical_fixed | embed
W_REL, W_IMP = 0.6, 0.4           # 가중 정렬의 두 항 (유도 안 된 현행값)

# `embed` 모드의 벡터 공급자. 기본은 없음 — 스윕이 `M.EMBED_FN = ...`로 꽂고 `try/finally`로
# 되돌린다. 안 꽂혔거나 실패하면 `retrieve()`가 `lexical_fixed`로 강등한다.
# 이 파일은 `embedding`을 저장소로만 쓰고(`db_get_vec`/`db_put_vec`) 벡터는 만들지 않는다.
EMBED_FN = None

# 저장된 벡터에 붙는 모델 이름 = 캐시 무효화 키(`embedding` 테이블의 PK가 `(key, model)`).
# 모델이 바뀌면 `db_get_vec`이 `None`을 돌려주고 `retrieve()`가 다시 계산한다.
# 정본은 `embedding.EMBED_MODEL`이라 옮겨 적지 않는다. `EMBED_FN`에 다른 모델을 꽂으면 이것도 바꾼다.
EMBED_MODEL_NAME = embedding.EMBED_MODEL

# 모드별 θ와 그 유도 이력 — (theta, f, n, population_sig)
#   theta 임계 컷 · f 등컷 비율 · n 유도에 쓴 쌍 수
#   population_sig (event 색인 총 행 수, user_deleted=0 행 수)
# θ는 척도와 모집단의 함수다. `retrieve()`가 실행 시점의 서명과 대조해 다르면 provenance에
# `stale_theta`를 남긴다(값은 바꾸지 않는다). 유도: `experiments/rel_dist.py`의 등컷 규칙,
# n=378(채점 18문항 × 색인 21행), f=0.80(현행과 동치인 눈금).
# 스윕은 이 dict를 통째로 재바인딩한다 — 한 칸만 바꾸면 save/restore가 참조를 떠서 셀 사이로 샌다.
# `hybrid` 키는 일부러 없다 — 하이브리드는 기각됐다(ADR-015). 프로브 10개에서 α=0.5의 순위가 임베딩 단독과 같았고,
# 어휘가 잡는데 임베딩이 놓친 문항이 0건이라 섞을 이유가 없다.
THETA_BY_MODE = {
    # lexical은 유도값이 아니라 현행값이라 f·n·서명이 없다(대조도 안 한다).
    # 정본은 전역 `THETA_RELEVANCE` — 스윕이 그 전역을 흔들므로 `theta_for()`가 매번 다시 읽는다.
    "lexical":       (THETA_RELEVANCE, None, None, None),
    "lexical_fixed": (0.043478260869565216, 0.80, 378, (22, 21)),  # 실제 컷 89.7%
    "embed":         (0.4453392062031366, 0.80, 378, (22, 21)),    # 실제 컷 80.2%
}


def theta_for(mode: str) -> float:
    """모드의 θ. 유도되지 않은 모드(`None`)는 `RuntimeError` — θ 없이 돌면 게이트가 조용히 사라진다."""
    entry = THETA_BY_MODE.get(mode)
    if entry is None:
        raise RuntimeError(
            f"검색 모드 '{mode}'의 θ가 유도되지 않았다 — 기본값으로 세울 수 없다. "
            f"`experiments/rel_dist.py`의 등컷 사다리로 먼저 유도할 것 (결정 D).")
    # lexical만 전역을 다시 읽는다 — 스윕이 그 전역을 흔든다.
    return THETA_RELEVANCE if mode == "lexical" else entry[0]


def set_retrieval_mode(mode: str):
    """기본 검색 모드를 세운다. 유도된 θ가 없으면 `theta_for`가 던진다. 스윕은 `try/finally`로 되돌린다."""
    global RETRIEVAL_MODE
    theta_for(mode)
    RETRIEVAL_MODE = mode

# 사실은 검색할 것이 아니라 항상 있어야 하는 것이다 — "나 커피 마셔도 되나?"처럼 과거 참조
# 표현이 없는 질문은 게이트에 막히므로, 상시 속성은 [알고 있는 것]으로 결정적으로 주입한다.
INJECT_KNOWN_FACTS = True

# ── 요약 계층 (ADR-016) ─────────────────────────────────────────────────
# 아래 넷은 세는 대상이 다르다 — 하나로 합치면 lifetime 요약의 재료가 줄어든다.
#   DIGEST_KEEP_SESSIONS   행 수    `digest_session`에 저장하는 행 수
#   DIGEST_INJECT_MAX      블록 수  매 턴 주입하는 세션 요약 블록 수
#   STALE_EXPIRE_SESSIONS  경계 수  낡은 요약을 몇 번의 세션 경계까지 내보내나
#   STALE_SERVE_POLICY     이름     stale 요약의 처분

# 24를 구속하는 것은 코퍼스 하나다 — `eval/fact-ledger.yaml`의 `meta.sessions = 24`.
# 토큰은 구속하지 않는다(24개 합 ≈ 2,592토큰 = `llm.LLM_NUM_CTX` 8,192의 31.6%).
# 12로 줄이면 아끼는 것은 토큰이 아니라 재료다 — 초기 12세션이 재료에서 빠지는데, 대장 사건 10개 중 3개가 그 구간에 있다.
DIGEST_KEEP_SESSIONS = 24

# 1은 «좋은 값»이 아니라 «기존과 같은 값»이다 — lifetime 1 + 세션 1 = digest 블록 2개로
# 기존 컨텍스트 모양을 재현한다. 튜닝은 격자의 일이다.
DIGEST_INJECT_MAX = 1

# 행이 아니라 시간(세션 경계)을 센다. 설계 기록의 값 그대로 3 — 위의 24와 같을 이유가 없다.
STALE_EXPIRE_SESSIONS = 3

# `"transition_warn"` = 전이 사유(`전이:`)는 경고와 함께 주입, 삭제·무효화 사유는 제외.
# `"exclude_all"` = 옛 동작(전부 제외). 넷 중 이것만 동작을 바꾸므로 옛 동작을 이름 있는 값으로 남긴다.
STALE_SERVE_POLICY = "transition_warn"

# 낡은 요약 앞에 붙이는 한 줄. 현재 stage는 `relationship` 블록이 결정적으로 주입하므로 전이는
# 경고를 붙여 내보낼 수 있다. 삭제된 사실에는 정정해 줄 블록이 없어 제외뿐이다.
STALE_SERVE_NOTE = ("⚠️ 아래 요약은 최근 관계 변화 이전에 작성됐다."
                    " 현재 관계는 위 [relationship] 블록을 따른다.")


def session_kind(session_id) -> str:
    """
    세션 요약의 키 `session:<sid>`. 이 문자열을 조립하는 곳은 여기 하나다
    (`digest_session` · `stale` · `derivation` · `digest_meta`가 같은 키를 쓴다).
    이미 `session:`으로 들어온 값은 그대로 돌려준다.
    """
    s = str(session_id)
    return s if s.startswith("session:") else f"session:{s}"


# ── apply_meta 컬럼 화이트리스트 (ADR-004 동기 층) ──────────────────────
# `state_delta`의 키는 LLM 출력이다 — 그대로 컬럼명으로 쓰면 모델이 스키마 식별자를 고른다.
# chat_id(관계 행을 다른 채팅으로 옮길 수 있다)·updated_by_turn(코드가 채운다)은 뺀다.
STATE_COLS = {"stage", "affinity", "last_emotion", "called_as"}
SCENE_COLS = {"place", "present", "situation"}

# scene_delta 값은 형태만 가드한다(타입·길이·줄을 깨는 글자). 관계는 `fsm.py`가 enum과 전이까지
# 검증한다. 참여자 명부 대조는 하지 않는다 — `guard_sim.KNOWN_CHARS`는
# 평가용 하드코딩 2원소 집합이지 런타임 명부가 아니다.
SCENE_VALUE_MAXLEN = 40   # 글자 수 상한 (docs/16 씬 가드)


def ntok(t: str) -> int:
    """한국어 ≈ 1.5토큰/글자 (docs/05)."""
    return max(1, int(len(t) * 1.5))


# 한국어 어미 정규화 — 형태소 분석기(nori) 없이 쓰는 최소 대용.
# "아팠던"과 "아파서"가 매칭되지 않아 정답이 탈락한 뒤 추가됐다.
_ENDINGS = re.compile(
    r"(었|았|였|겠|시|으)?(다|는|은|을|던|서|고|며|지|나|냐|어|아|여|요|음|기|게|니|까|"
    r"습니다|합니다|했|한|할|해)$")


def _stem(w: str) -> str:
    prev = None
    while prev != w and len(w) > 1:
        prev, w = w, _ENDINGS.sub("", w)
    return w


def bigrams(t: str, normalize: bool = True):
    """어절별로 어미를 벗긴 뒤 bigram. normalize=False면 원문 그대로."""
    words = t.split()
    if normalize:
        words = [_stem(re.sub(r"[^\w가-힣]", "", w)) for w in words]
    s = "".join(words)
    return [s[i:i + 2] for i in range(len(s) - 1)] or [s]


# ── 고친 토크나이저 (lexical_fixed 척도 · ADR-015) ──────────────────────
# 위 토크나이저(`_stem`·`bigrams`)는 실험 기준선이라 고정해 두었고 기본 검색 경로가 쓴다.
# 아래는 옆에 둔 대안이다(`experiments/embed_vs_bigram.py`도 사본 없이 여기를 import한다).
# 조사 목록 — 위 토크나이저는 조사를 안 벗겨서 "나비가"가 "비가"를 만든다.
_PART = re.compile(r"(은|는|이|가|을|를|에게|에서|에|의|와|과|도|만|으로|로|부터|까지|께|한테)$")


def _fixed_word(w: str) -> str:
    """어미와 조사를 벗기되 2글자 밑으로는 안 깎는다 (강아지 -> 강 방지)."""
    prev = None
    while prev != w and len(w) > 2:
        prev = w
        w = _ENDINGS.sub("", w)
        if len(w) > 2:
            w = _PART.sub("", w)
    return w


def tokens_fixed(t: str):
    """어절마다 따로 자른다. 경계를 넘는 가짜 조각을 만들지 않는다."""
    out = []
    for w in t.split():
        w = _fixed_word(re.sub(r"[^\w가-힣]", "", w))
        if w:
            out += [w[i:i + 2] for i in range(len(w) - 1)] or [w]
    return out


def jaccard(q, d) -> float:
    """|교집합| / |합집합|. `tokens_fixed`와 짝인 `lexical_fixed` 척도의 `rel`이다."""
    q, d = set(q), set(d)
    return len(q & d) / max(len(q | d), 1)


def coverage(q, d) -> float:
    """질문 조각 중 문서가 덮는 비율. 현행 `lexical` 척도의 `rel`이 이 식이다."""
    q, d = set(q), set(d)
    return len(q & d) / max(len(q), 1)


def _embed_texts(texts):
    """
    주입된 공급자(`EMBED_FN`)로 벡터를 얻는다. 못 얻으면 `None` — 예외를 올리지 않는다.
    호출부(`retrieve`)가 `None`을 보고 `lexical_fixed`로 강등하고 provenance에 남기므로,
    여기서 터지면 강등 경로가 돌지 않는다.
    """
    if EMBED_FN is None:
        return None
    try:
        vecs = EMBED_FN(list(texts))
    except Exception:
        return None
    if not vecs or len(vecs) != len(texts) or any(not v for v in vecs):
        return None
    return vecs


def _cosine(a, b) -> float:
    """`embed` 척도의 `rel`(코사인). 길이가 다른 벡터면 `DimMismatch`를 던진다."""
    dot = sum(x * y for x, y in zip(a, _same_dim(a, b)))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


@dataclass
class Block:
    name: str
    text: str
    scope: str          # global | character | chat
    volatility: int     # 낮을수록 안정 — 배치 순서 결정 (docs/adr/ADR-007)

    @property
    def tokens(self):
        return ntok(self.text)


@dataclass
class Context:
    blocks: list = field(default_factory=list)
    provenance: list = field(default_factory=list)

    @property
    def tokens(self):
        return sum(b.tokens for b in self.blocks)

    def render(self):
        return "\n\n".join(f"[{b.name}]\n{b.text}" for b in self.blocks)


class Memory:
    # 스키마 버전 — 올릴 때마다 MIGRATIONS에 한 줄 추가한다
    SCHEMA_VERSION = 5
    #  1: 최초
    #  2: fact에 카디널리티·가변성·상시성 반영
    #  3: event.dedup_key + derivation/stale
    #  4: stage_machine · state_violation · embedding · digest_meta
    #  5: digest_session
    MIGRATIONS = {
        2: ["ALTER TABLE event ADD COLUMN mention_count INTEGER DEFAULT 1"],
        3: ["ALTER TABLE event ADD COLUMN dedup_key TEXT"],
        # v4·v5는 신규 테이블만 더한다 — `__init__`이 매번 `SCHEMA`(전부 `CREATE TABLE IF NOT EXISTS`)를
        # 실행하므로 여기엔 `ALTER`만 둔다. 빈 리스트는 누락이 아니라 결정이다.
        4: [],
        # v5에 `ALTER`를 넣으면 위험하다: v4로 롤백했다가 다시 올린 DB는 `schema_version`이 이미 '5'라
        # 아래 `range(have + 1, …)`가 비어 이 리스트를 조용히 건너뛴다.
        5: [],
    }

    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self._migrate()

    def _migrate(self):
        """
        스키마 버전을 맞춘다. 버전은 코드가 아니라 데이터(meta)에 적고, 올라갈 때만 적용하며
        (내려가는 마이그레이션은 없다), 실패하면 멈춘다 — 반쯤 된 마이그레이션이 최악이다.
        """
        cur = self.db.execute("SELECT v FROM meta WHERE k='schema_version'").fetchone()
        have = int(cur["v"]) if cur else 0
        if have == 0:                      # 새 DB — 현재 버전으로 표시만
            self.db.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version',?)",
                            (str(self.SCHEMA_VERSION),))
            self.db.commit()
            return []
        applied = []
        for v in range(have + 1, self.SCHEMA_VERSION + 1):
            for stmt in self.MIGRATIONS.get(v, []):
                try:
                    self.db.execute(stmt)
                except sqlite3.OperationalError as e:
                    if "duplicate column" not in str(e):
                        raise RuntimeError(
                            f"마이그레이션 v{v} 실패 — 중단한다: {e}") from None
            applied.append(v)
            self.db.execute("UPDATE meta SET v=? WHERE k='schema_version'", (str(v),))
        self.db.commit()
        return applied

    # ── 쓰기 경로 ───────────────────────────────────────────────────
    def add_turn(self, chat_id, seq, role, text):
        self.db.execute(
            "INSERT OR REPLACE INTO turn VALUES (?,?,?,?,?,?,'pending')",
            (chat_id, seq, role, text, time.time(), ntok(text)))
        self.db.commit()

    def _violation(self, chat_id, seq, field, from_value, to_value, reason):
        """거부·예외를 데이터로 남긴다 — 위반율을 세야 규칙이 의미 있는지 안다 (ADR-014)."""
        self.db.execute(
            "INSERT INTO state_violation VALUES (?,?,?,?,?,?,?)",
            (chat_id, seq, field,
             None if from_value is None else str(from_value),
             None if to_value is None else str(to_value),
             reason, time.time()))

    def _filter_cols(self, chat_id, seq, delta: dict, allowed: set, field: str):
        """
        화이트리스트 밖 키를 드롭하고 기록한다. `provenance`는 «이 턴의 컨텍스트가 왜 이렇게
        조립됐나»를, `state_violation`은 «규칙이 몇 번 막았나»를 읽는 곳이라 둘 다 남긴다.
        """
        out = {}
        for k, v in delta.items():
            if k in allowed:
                out[k] = v
            else:
                self._prov(chat_id, seq, "meta_rejected", f"{field}.{k}",
                           "화이트리스트 밖 컬럼")
                self._violation(chat_id, seq, f"{field}.{k}", None, v,
                                "화이트리스트 밖 컬럼")
        return out

    def _scene_value_ok(self, chat_id, seq, key, val, field="scene_delta"):
        """scene_delta 값 가드 — 형태만 본다(타입·길이·줄을 깨는 글자). 관계 행의 호칭·감정 칸도 탄다."""
        if not isinstance(val, str):
            reason = f"문자열 아님({type(val).__name__})"
        elif len(val) > SCENE_VALUE_MAXLEN:
            reason = f"{SCENE_VALUE_MAXLEN}자 초과({len(val)}자)"
        elif _LINE_BREAKERS.search(val):                 # 렌더 가드(_one_line)와 같은 글자 집합
            reason = "제어문자 포함"
        else:
            return True
        self._prov(chat_id, seq, "meta_rejected", f"{field}.{key}", reason)
        self._violation(chat_id, seq, f"{field}.{key}", None, val, reason)
        return False

    def apply_meta(self, chat_id, seq, meta: dict):
        """응답과 함께 온 구조화 출력을 반영 (ADR-004 동기 층) — 추가 LLM 호출 없이 갱신한다."""
        if d := meta.get("state_delta"):
            d = self._filter_cols(chat_id, seq, d, STATE_COLS, "state_delta")
            d = _guard_state_text(self, chat_id, seq, d)     # 호칭·감정 칸 형태 가드
            if d:
                self._apply_state_delta(chat_id, seq, d, meta)
        if s := meta.get("scene_delta"):
            s = self._filter_cols(chat_id, seq, s, SCENE_COLS, "scene_delta")
            s = {k: v for k, v in s.items()
                 if self._scene_value_ok(chat_id, seq, k, v)}
            if s:
                cols = ", ".join(f"{k}=?" for k in s)
                self.db.execute(
                    f"UPDATE scene SET {cols}, updated_by_turn=? WHERE chat_id=?",
                    (*s.values(), seq, chat_id))
        for eid in meta.get("used_memories", []):
            kind, _, rid = eid.partition(":")
            if kind == "event":
                _surface_event(self, chat_id, seq, rid)       # 이 방의 사건만
            elif kind == "debt":                              # 상환
                _pay_debt(self, chat_id, seq, rid)
        if (nd := meta.get("new_debt")) and _new_debt_ok(self, chat_id, seq, nd):
            self.db.execute(
                "INSERT INTO debt (chat_id, content, setup_turn_seq, trigger_kind,"
                " trigger_spec, trigger_clock, emotional_stake) VALUES (?,?,?,?,?,?,?)",
                (chat_id, nd["content"], seq, nd.get("trigger_kind", "session_start"),
                 nd.get("trigger_spec"), nd.get("trigger_clock", "session"),
                 nd.get("stake", 0.5)))
        self.db.commit()

    # ── 관계 FSM 훅 (ADR-014) ────────────────────────────────────────
    def _apply_state_delta(self, chat_id, seq, d: dict, meta: dict):
        """
        화이트리스트를 통과한 `state_delta`에 상태 기계를 얹는다 — stage enum · 전이 허용 · affinity 범위 · 변화량.

        `narrative_event`는 같은 LLM 호출의 자기 선언이라 독립 신호가 아니다. 그래서 교차 검증 대신
        전부 감사 행으로 남기고 예외율을 잰다(`fsm_probe.py`).
        """
        cur = self.db.execute("SELECT * FROM relationship WHERE chat_id=?",
                              (chat_id,)).fetchone()
        if cur is None:
            # 관계 행이 없으면 검증할 상태가 없다 — 무동작이되 기록한다.
            self._prov(chat_id, seq, "meta_rejected", "state_delta",
                       "관계 행 없음 — 검증 불가")
            return

        ch = self.db.execute("SELECT character_id, character_version FROM chat"
                             " WHERE chat_id=?", (chat_id,)).fetchone()
        machine = (fsm.load_machine(self.db, ch["character_id"],
                                    ch["character_version"])
                   if ch else fsm.DEFAULT_MACHINE)

        ok, new_state, reason = fsm.validate(
            machine, cur, d, narrative_event=bool(meta.get("narrative_event")))
        item = json.dumps(d, ensure_ascii=False)

        if not ok:
            self._violation(chat_id, seq, "state_delta",
                            f"{cur['stage']}/{cur['affinity']}", item, reason)
            self._prov(chat_id, seq, "meta_rejected", f"state_delta:{reason}",
                       f"{cur['stage']}/{cur['affinity']} → {item}")
            return

        cols = ", ".join(f"{k}=?" for k in d)
        self.db.execute(
            f"UPDATE relationship SET {cols}, updated_by_turn=? WHERE chat_id=?",
            (*d.values(), seq, chat_id))
        self._prov(chat_id, seq, "state_delta", item, "동기 구조화 출력")

        if reason == fsm.R_NARRATIVE:
            # 거부가 아니라 감사 기록 — 선언된 예외는 예외율로만 감시할 수 있다.
            self._violation(chat_id, seq, "affinity",
                            cur["affinity"], new_state["affinity"],
                            fsm.R_NARRATIVE)

        old, new = cur["stage"], new_state["stage"]
        if old != new:
            self._propagate_transition(chat_id, seq, old, new)

    def _propagate_transition(self, chat_id, seq, old, new):
        """
        stage 전이는 갱신이다 — 파생물을 따라간다(ADR-011 «삭제와 갱신은 같은 일»).
          ① `derivation`에 등록된 파생물
          ② 규칙 기반 직접 stale — 등록이 아직 없어도 동작해야 한다
        """
        # ① 등록된 파생물
        self._invalidate_derived(chat_id, "relationship", chat_id)

        # ② 규칙 기반. 사유는 `전이:` 접두사 — 서빙 정책이 이것으로 분기한다(삭제·무효화 사유는 접미사형).
        reason = f"전이:{old}→{new}"
        now = time.time()

        # 대상 키는 `digest`·`digest_session`의 실제 행을 열거한다(없는 요약은 stale로 밀지 않는다).
        # 기본값에서는 빈 목록이다(`TRANSITION_PROPAGATES_DIGEST`, 파일 끝): 요약 프롬프트가 `stage`를
        # 싣지 않아 재생성해도 새 정보가 없기 때문이다. 해석은 아래에서 그대로 민다.
        targets = [("digest", r["kind"]) for r in self.db.execute(
            "SELECT kind FROM digest WHERE chat_id=?"
            " UNION SELECT kind FROM digest_session WHERE chat_id=?",
            (chat_id, chat_id)).fetchall()] if TRANSITION_PROPAGATES_DIGEST else []
        # 해석(interpretation)은 아직 구현이 없어 와일드카드 한 행으로 남기고, 등록된 키가 있으면 함께 민다.
        targets.append(("interpretation", "*"))
        targets += [(r["derived_kind"], r["derived_key"]) for r in self.db.execute(
            "SELECT DISTINCT derived_kind, derived_key FROM derivation"
            " WHERE chat_id=? AND derived_kind='interpretation'", (chat_id,))]

        # 삭제·무효화 사유를 전이 사유로 덮지 않는다 — 덮으면 `transition_warn`이 지운 사실이 든
        # 요약을 경고와 함께 다시 내보낸다. 전이 → 전이는 새 사유로 덮는다.
        for kind, key in targets:
            self.db.execute(
                "INSERT INTO stale (chat_id, derived_kind, derived_key, reason,"
                " marked_at) VALUES (?,?,?,?,?) ON CONFLICT (chat_id, derived_kind,"
                " derived_key) DO UPDATE SET reason=excluded.reason,"
                " marked_at=excluded.marked_at WHERE stale.reason LIKE '전이:%'",
                (chat_id, kind, key, reason, now))

        # 첫 stale 시점(`stale_since_seq`)은 전이가 일어난 지금만 안다 — 이미 값이 있으면 덮지 않는다.
        for kind, key in targets:
            if kind != "digest":
                continue
            self.db.execute(
                "INSERT OR IGNORE INTO digest_meta (chat_id, kind) VALUES (?,?)",
                (chat_id, key))
            self.db.execute(
                "UPDATE digest_meta SET stale_since_seq=? WHERE chat_id=? AND"
                " kind=? AND stale_since_seq IS NULL", (seq, chat_id, key))
        self._prov(chat_id, seq, "stage_transition", f"{old}→{new}",
                   f"파생물 {len(targets)}건 stale")

    # ── L4 세션 요약 — 저장(N)과 주입 후보(M) (ADR-016) ───────────────────
    # 저장 쪽 절단과 주입 쪽 선택이 같은 정렬을 써야 지워지는 행과 주입되는 행이 어긋나지 않는다.
    _DIGEST_ORDER = " ORDER BY covers_to_seq DESC, kind DESC"

    def put_session_digest(self, chat_id, session_id, content, *,
                           covers_from_seq=None, covers_to_seq=None,
                           session_end_note=None, generated_at=None):
        """
        세션 요약 한 건을 `digest_session`에 저장하고 그 자리에서 N 상한을 강제한다
        (청소 작업에 맡기면 상한을 넘은 상태가 생긴다). 기존 DB의 legacy `digest.kind='session'`
        행은 건드리지 않는다.

        반환: 상한 때문에 지워진 키 목록(N+1번째 이후의 쓰기마다 하나).
        """
        kind = session_kind(session_id)
        self.db.execute(
            "INSERT OR REPLACE INTO digest_session"
            " (chat_id, kind, content, covers_from_seq, covers_to_seq,"
            "  session_end_note, generated_at) VALUES (?,?,?,?,?,?,?)",
            (chat_id, kind, content, covers_from_seq, covers_to_seq,
             session_end_note,
             time.time() if generated_at is None else generated_at))

        # 남길 것을 같은 정렬로 고르고 나머지를 지운다 — «오래된 것»의 정의가 주입 쪽과 갈라지지 않게.
        keep = ("SELECT kind FROM digest_session WHERE chat_id=?"
                + self._DIGEST_ORDER + " LIMIT ?")
        args = (chat_id, chat_id, DIGEST_KEEP_SESSIONS)
        dropped = [r["kind"] for r in self.db.execute(
            "SELECT kind FROM digest_session WHERE chat_id=?"
            f" AND kind NOT IN ({keep})", args).fetchall()]
        self.db.execute(
            "DELETE FROM digest_session WHERE chat_id=?"
            f" AND kind NOT IN ({keep})", args)

        # 밀려난 키의 흔적(stale · digest_meta · derivation)도 지운다 — 남기면 그 테이블들이 N에
        # 수렴하지 않고 세션 수만큼 늘어난다. `lifetime`과 legacy `kind='session'`은 대상이 아니다.
        for gone in dropped:
            _forget_digest_key(self, chat_id, gone)
        self.db.commit()
        return dropped

    def session_digests(self, chat_id, limit=None):
        """
        주입 후보 — 기본은 최신 M개(`DIGEST_INJECT_MAX`). `rewrite_lifetime`은 `limit=DIGEST_KEEP_SESSIONS`로
        부른다. 기본을 전량으로 두지 않는 이유: 읽기 경로가 기본값을 쓰므로 매 턴 24블록이 실린다.
        동률 tie-break(`kind DESC`)까지 고정해 블록 순서(= 캐시 접두사)가 흔들리지 않게 한다.
        """
        n = DIGEST_INJECT_MAX if limit is None else limit
        return self.db.execute(
            "SELECT * FROM digest_session WHERE chat_id=?"
            + self._DIGEST_ORDER + " LIMIT ?", (chat_id, n)).fetchall()

    # ── 요약 서빙 정책 (ADR-016) ────────────────────────────────────────

    def session_boundaries_since(self, chat_id, since_seq):
        """
        `since_seq` 이후에 끝난 세션 수 — `stale_expired` 판정과 부채 백오프의 경계 카운터.

        세션 경계가 남는 곳은 «끝난 세션마다 한 행이 생기는» `digest_session`뿐이다.
        한계: 요약이 한 번도 안 만들어지면(`regen_job`이 안 돌면) 이 수는 계속 0이다.
        """
        return self.db.execute(
            "SELECT COUNT(*) c FROM digest_session WHERE chat_id=?"
            " AND covers_to_seq > ?", (chat_id, since_seq)).fetchone()["c"]

    def _serve_digest(self, ctx, chat_id):
        """
        digest 주입 — 두 소스(`digest`의 lifetime·legacy session, `digest_session`)가 같은 3분기를 탄다.

          `…삭제됨`/`…무효화됨`           → 제외              ("stale", …)
          `전이:` 접두사                   → 경고와 함께 주입  ("stale_served", …)
          위 항목이 E회 세션 경계를 넘김   → 제외로 강등       ("stale_expired", …)

        `STALE_SERVE_POLICY == "exclude_all"`이면 전부 제외(옛 동작).
        `digest_session`에만 `DIGEST_INJECT_MAX`가 걸린다 — `digest`는 PK가 `(chat_id, kind)`라 상한이 스키마다.
        legacy `digest.kind='session'` 행도 서빙한다 — 빼면 기존 DB가 블록 하나를 잃고, 전이당 제외가 2건에서 1건으로
        줄어 ADR-013의 기록값(제외 10회)이 재현되지 않는다. 그 행이 새 세션 요약과 어긋날 때의 영향은 재지 않았다.
        """
        rows = [(r, 4 if r["kind"] == "lifetime" else 5) for r in self.db.execute(
            "SELECT * FROM digest WHERE chat_id=?", (chat_id,)).fetchall()]
        rows += [(r, 5) for r in self.session_digests(chat_id)]

        for d, vol in rows:
            kind, content = d["kind"], d["content"]
            st = self.stale_row(chat_id, "digest", kind)
            if st is not None:
                reason = st[0]
                transition = reason.startswith("전이:")
                if not transition or STALE_SERVE_POLICY != "transition_warn":
                    # 삭제·무효화 — 그리고 `exclude_all`에서는 전이도 여기 온다.
                    ctx.provenance.append(
                        ("stale", f"digest:{kind}", "삭제된 근거 포함 — 재생성 대기"))
                    continue
                since = self.db.execute(
                    "SELECT stale_since_seq FROM digest_meta WHERE chat_id=?"
                    " AND kind=?", (chat_id, kind)).fetchone()
                since = since["stale_since_seq"] if since else None
                # `stale_since_seq`가 없으면 «언제부터 낡았나»를 모른다. 모르는
                # 것을 만료로 읽지 않는다 — 경고와 함께 내보내고 그 사실을 적는다.
                crossed = (self.session_boundaries_since(chat_id, since)
                           if since is not None else None)
                if crossed is not None and crossed >= STALE_EXPIRE_SESSIONS:
                    ctx.provenance.append(
                        ("stale_expired", f"digest:{kind}",
                         f"{reason} · 세션 경계 {crossed}회 ≥"
                         f" STALE_EXPIRE_SESSIONS({STALE_EXPIRE_SESSIONS})"
                         " — 제외로 강등"))
                    continue
                ctx.provenance.append(
                    ("stale_served", f"digest:{kind}",
                     f"{reason} · 경고와 함께 주입 (세션 경계 "
                     f"{'미상' if crossed is None else crossed}회 <"
                     f" {STALE_EXPIRE_SESSIONS})"))
                content = f"{STALE_SERVE_NOTE}\n{content}"
            ctx.blocks.append(Block(f"digest:{kind}", content, "chat", vol))

    # ── L6 사건 중복 제거 ─────────────────────────────────────────────
    # 사실은 카디널리티로 중복을 막지만 사건에는 방어가 없어, 반복 언급이 쌓이면 후보가 늘어 정밀도가 떨어진다
    # (`experiments/longhorizon_sim.py`).
    # 같은 사건의 반복 언급을 합친다. 완벽한 판정은 불가능하므로 연속 구간의 반복만 잡는다 —
    # 시점 버킷(DEDUP_WINDOW)으로 후보를 좁히고 어근 집합의 Jaccard로 판정한다(정확 일치는
    # 낱말 하나만 달라도 못 잡았다: "나비가 갑자기 아파서…" / "나비가 아파서…").
    DEDUP_WINDOW = 20          # 이 턴 수 안의 같은 내용은 같은 사건 후보
    DEDUP_JACCARD = 0.6        # 어근 집합 겹침이 이 이상이면 같은 사건으로 본다

    # 조사 목록. `_stem`은 어미만 벗기고 조사는 모른다("응급실에" != "응급실").
    # 형태소 분석기가 없어서 쓰는 대용이다.
    _PARTICLE = re.compile(
        r"(으로서|으로써|에게서|한테서|으로|에서|에게|한테|께서|부터|까지|"
        r"이|가|은|는|을|를|에|의|와|과|도|만|로|께|랑|이랑)$")

    @classmethod
    def _roots(cls, text):
        out = set()
        for w in text.split():
            w = re.sub(r"[^\w가-힣]", "", w)
            if len(w) < 2:
                continue
            w = _stem(w)
            p = cls._PARTICLE.sub("", w)
            out.add(p if len(p) >= 2 else w)      # 과하게 깎이면 되돌린다
        return out

    def add_event(self, chat_id, summary, seq, *, emotional_weight=0.5,
                  importance=None, narrative_role=None):
        """사건 추가. 같은 시점 구간에 충분히 겹치는 사건이 있으면 새로 넣지 않고 강화한다."""
        bucket = seq // self.DEDUP_WINDOW
        r_new = self._roots(summary)
        imp = importance if importance is not None else emotional_weight
        for row in self.db.execute(
                "SELECT event_id, summary FROM event"
                " WHERE chat_id=? AND dedup_key=? AND user_deleted=0",
                (chat_id, str(bucket))).fetchall():
            r_old = self._roots(row["summary"])
            inter = len(r_new & r_old)
            union = len(r_new | r_old) or 1
            if inter / union >= self.DEDUP_JACCARD:
                self.db.execute(
                    "UPDATE event SET mention_count=mention_count+1,"
                    " emotional_weight=MAX(emotional_weight,?),"
                    " importance=MAX(importance,?) WHERE event_id=?",
                    (emotional_weight, imp, row["event_id"]))
                self.db.commit()
                return "merged", row["event_id"]
        cur = self.db.execute(
            "INSERT INTO event (chat_id, summary, occurred_at, emotional_weight,"
            " importance, narrative_role, source_from_seq, dedup_key)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (chat_id, summary, seq, emotional_weight, imp,
             narrative_role, seq, str(bucket)))
        self.db.commit()
        # 쓰기 경로 사전계산 — 요약이 색인에 들어오는 유일한 지점이다. 병합 분기는 요약 문자열이
        # 안 바뀌므로 기존 벡터가 유효하다. 기본 `lexical`에서는 즉시 되돌아온다.
        self._precompute_vec(chat_id, summary)
        return "created", cur.lastrowid

    # ── L5 사실 무효화 (bi-temporal) ────────────────────────────────
    # 충돌 판정에 스키마에 없던 결정이 필요했다: ① 술어의 카디널리티 · ② 누가 이기나 ·
    # ③ 유저가 틀리게 말할 때.
    PREDICATE_CARDINALITY = {           # ① 술어별 값 개수
        "직업": "one", "거주지": "one", "반려동물_이름": "one",
        "신체_특성": "many", "가족": "many", "선호": "many",
        "지인_반려동물": "many", "일상_사소": "many",
    }
    # ② "더 확신해야 덮는다"는 confidence 0.9에서 정당한 갱신도 영원히 막았다 → "덜 확신하면 못 덮는다".
    CONFIDENCE_FLOOR = 0.6              # 다중값 술어에 새 값을 추가할 최소 확신

    # ④ 가변성. 이직(세상이 변함)과 잘못 안 사실(유저 오류)은 둘 다 «다른 값»이라
    #    confidence만으로는 못 가른다 — 술어마다 허용 폭을 둔다.
    PREDICATE_MUTABILITY = {
        "직업": "high", "거주지": "high", "일상_사소": "high",
        "선호": "mid", "신체_특성": "low",
        "가족": "low", "반려동물_이름": "low", "지인_반려동물": "low",
    }
    _MUT_TOLERANCE = {"high": 0.25, "mid": 0.10, "low": -0.05}

    # ⑤ 상시성. importance(«중요한가»)와 다르다 — 체질·이름·직업 같은 속성만 [알고 있는 것]에
    #    상시 주입하고 사건은 검색으로 꺼낸다("발목을 삐었다"는 중요하지만 상시가 아니다).
    PREDICATE_STANDING = {
        "직업", "거주지", "반려동물_이름", "신체_특성", "가족",
        "선호", "지인_반려동물", "지인_직업", "관계_배경",
    }   # 여기 없는 술어(일상_사소 등)는 검색 경로로만 도달한다

    def upsert_fact(self, chat_id, subject, predicate, obj, *, realm="real",
                    seq=0, importance=0.5, confidence=0.8):
        """
        반환: (동작, 설명). 동작 ∈ {created, reinforced, superseded, held, coexist}
        """
        cur = self.db.execute(
            "SELECT * FROM fact WHERE chat_id=? AND subject=? AND predicate=?"
            " AND valid_until IS NULL AND user_deleted=0",
            (chat_id, subject, predicate)).fetchall()

        # 같은 값 → 강화 (반증이 아니라 재확인)
        for r in cur:
            if r["object"] == obj:
                self.db.execute(
                    "UPDATE fact SET mention_count=mention_count+1,"
                    " confidence=MIN(1.0, confidence+0.05) WHERE fact_id=?",
                    (r["fact_id"],))
                self.db.commit()
                return "reinforced", f"재확인 (mention {r['mention_count']+1})"

        card = self.PREDICATE_CARDINALITY.get(predicate, _unknown_pred(self, predicate)[0])  # 표 밖 술어는 정책 기본값

        # 다중값 술어 → 병존. 단 확신이 낮으면 병존도 막는다("오빠 1명"처럼 없는 사실이 들어온다).
        if card == "many" or not cur:
            if cur and confidence < self.CONFIDENCE_FLOOR:
                self._prov(chat_id, seq, "fact_held", f"{predicate}={obj}",
                           f"다중값이지만 확신 {confidence:.2f} < floor")
                self.db.commit()
                return "held", f"보류 — 확신 {confidence:.2f}이 낮다. 확인 필요"
            if _insert_fact(self, chat_id, subject, predicate, obj, realm, seq,
                            importance, confidence) == 0:                         # UNIQUE에 걸려 0행
                return "held", _unique_note(self, chat_id, seq, subject, predicate, obj)
            self.db.commit()
            return ("coexist" if cur else "created",
                    f"{card} 술어 — {'병존' if cur else '신규'}")

        # 단일값 술어 + 값이 다름 → 충돌
        old = cur[0]
        # ③ 덜 확신하는 진술은 더 확신하는 사실을 못 덮는다(유저의 틀린 말 방어). 허용 폭은 가변성별이다.
        mut = self.PREDICATE_MUTABILITY.get(predicate, _unknown_pred(self, predicate)[1])
        tol = self._MUT_TOLERANCE[mut]
        if confidence < old["confidence"] - tol:
            self._prov(chat_id, seq, "fact_held", f"{predicate}={obj}",
                       f"{mut} 가변성, 확신 {confidence:.2f} < "
                       f"{old['confidence'] - tol:.2f}")
            self.db.commit()
            return "held", (f"보류 — {mut} 가변성 술어. 확신 {confidence:.2f} < "
                            f"기준 {old['confidence'] - tol:.2f}. 확인 필요")

        if _same_turn_flip(self, chat_id, seq, predicate, obj):     # 어떤 UPDATE보다 앞에 검사
            return "held", _flip_note(self, chat_id, seq, subject, predicate, obj)
        now = _retire(self, old)                                   # 옛 행 무효화
        cursor = self.db.execute(
            "INSERT INTO fact (chat_id, subject, predicate, object, realm,"
            " valid_from, source_turn_seq, importance, confidence)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (chat_id, subject, predicate, obj, realm, now, seq, importance,
             confidence))
        self.db.execute("UPDATE fact SET superseded_by=? WHERE fact_id=?",
                        (cursor.lastrowid, old["fact_id"]))
        # 색인 복사본(event)도 무효화한다 — 사실만 무효화하면 이직 전 직장이 계속 검색됐다.
        # 원본이 바뀌면 파생물도 따라간다(삭제와 같은 경로, ADR-011).
        n = len(self._invalidate_derived(chat_id, "fact", old["fact_id"]))
        self._prov(chat_id, seq, "fact_superseded",
                   f"{predicate}: {old['object']} → {obj}",
                   f"단일값 술어 충돌 · 파생 색인 {n}건 무효화")
        self.db.commit()
        return "superseded", f"'{old['object']}' → '{obj}' 무효화"

    # ── 삭제와 그 전파 (ADR-011) ─────────────────────────────────────
    def record_derivation(self, chat_id, derived_kind, derived_key, sources):
        """파생물이 어떤 원본에서 나왔는지 기록한다. 요약·해석 생성 시 호출."""
        self.db.executemany(
            "INSERT INTO derivation VALUES (?,?,?,?,?)",
            [(chat_id, derived_kind, derived_key, k, str(i)) for k, i in sources])
        self.db.commit()

    def delete_item(self, chat_id, kind, item_id):
        """
        유저가 기억 하나를 지운다. 파생물까지 따라간다. 반환: 함께 무효화된 파생물 목록.

        파생물은 즉시 다시 쓸 수 없으므로(LLM 필요) 요약·해석은 stale로 표시해 재생성 전까지
        주입에서 뺀다. 재생성할 것이 없는 검색 색인 복사본(`event`)은 `user_deleted=1`로 즉시 뺀다 —
        `retrieve()`·`_recall_vocab_for()`는 `stale`을 보지 않으므로, 빼지 않으면 지운 사실의 색인
        문장이 계속 검색되고 게이트를 발화시킨다. 처분은 `_invalidate_derived` 하나가 한다.
        """
        table, col = _DELETE_TABLES[kind]
        if not _flag_deleted(self, chat_id, table, col, item_id):  # 원본 user_deleted=1 · 방 대조
            return _delete_rejected(self, chat_id, kind, item_id)
        # 파생물 처분은 갱신 경로와 같은 함수를 부른다 — 둘이 각자 적으면 한쪽만 고쳐진다.
        hit = self._invalidate_derived(chat_id, kind, item_id, reason="삭제됨")
        self._prov(chat_id, 0, "delete",
                   f"{kind}:{item_id}", f"파생물 {len(hit)}건 무효화")
        self.db.commit()
        return hit

    def _invalidate_derived(self, chat_id, source_kind, source_id,
                            reason="무효화됨"):
        """
        원본이 바뀌거나 지워졌을 때 파생물을 따라간다. 요약처럼 재생성이 필요한 것은 stale로 표시하고,
        색인 복사본(event)처럼 그냥 빼면 되는 것은 즉시 제외한다. 색인 복사본은 `record_derivation`으로
        원본 사실에 등록돼 있어야 한다 — 등록이 없으면 사실이 무효화돼도 검색에 남는다.

        반환: 처분한 파생물 `[(derived_kind, derived_key), …]`. `reason`은 `stale`에 남는 사유의
        뒷말이다(`삭제됨`/`무효화됨` — 서빙 정책이 사유로 처분을 가른다).
        """
        rows = self.db.execute(
            "SELECT derived_kind, derived_key FROM derivation"
            " WHERE chat_id=? AND source_kind=? AND source_id=?",
            (chat_id, source_kind, str(source_id))).fetchall()
        hit = []
        for r in rows:
            if r["derived_kind"] == "event":
                self.db.execute("UPDATE event SET user_deleted=1 WHERE event_id=?",
                                (r["derived_key"],))
            else:
                self.db.execute(
                    "INSERT OR REPLACE INTO stale VALUES (?,?,?,?,?)",
                    (chat_id, r["derived_kind"], r["derived_key"],
                     f"{source_kind}:{source_id} {reason}", time.time()))
            hit.append((r["derived_kind"], r["derived_key"]))
        return hit

    def is_stale(self, chat_id, derived_kind, derived_key):
        return self.db.execute(
            "SELECT 1 FROM stale WHERE chat_id=? AND derived_kind=? AND derived_key=?",
            (chat_id, derived_kind, derived_key)).fetchone() is not None

    def stale_row(self, chat_id, kind, key):
        """
        stale 사유까지 돌려준다 — `(reason, marked_at)` 또는 `None`. `is_stale`과 달리 서빙 정책이
        «왜 stale인가»로 분기할 수 있다(`전이:…`는 경고와 함께, `…삭제됨`은 제외).
        """
        r = self.db.execute(
            "SELECT reason, marked_at FROM stale"
            " WHERE chat_id=? AND derived_kind=? AND derived_key=?",
            (chat_id, kind, key)).fetchone()
        return (r["reason"], r["marked_at"]) if r else None

    def facts_at(self, chat_id, when=None):
        """특정 시점에 유효했던 사실 (bi-temporal 조회)."""
        if when is None:
            return self.db.execute(
                "SELECT * FROM fact WHERE chat_id=? AND valid_until IS NULL"
                " AND user_deleted=0 ORDER BY predicate", (chat_id,)).fetchall()
        return self.db.execute(
            "SELECT * FROM fact WHERE chat_id=? AND valid_from<=?"
            " AND (valid_until IS NULL OR valid_until>?) AND user_deleted=0"
            " ORDER BY predicate", (chat_id, when, when)).fetchall()

    def _prov(self, chat_id, seq, kind, item, reason):
        self.db.execute("INSERT INTO provenance VALUES (?,?,?,?,?)",
                        (chat_id, seq, kind, item, reason))

    # ── 읽기 경로 ───────────────────────────────────────────────────
    def gate(self, utterance: str, chat_id=None) -> tuple[bool, str]:
        """
        검색이 필요한 턴인가 (ADR-006). 룰 기반, ~0ms.

        과거 참조 표현(기억/그때/저번…)만 보면 "나 이직 준비하고 면접 몇 번 봤더라" 같은 자연스러운
        질문을 놓친다 — 그래서 저장된 내용어와의 접점(앞 2글자)도 신호로 쓴다. θ=0.05와 함께 바꿔야
        효과가 난다(게이트와 θ는 직렬이다).

        `chat_id`를 주면 그 대화방의 어휘만 본다. 생략하면 DB 전량(어휘를 밖에서 꽂는 계측 하니스).
        """
        if re.search(r"(기억|그때|저번|예전|아까|전에|했잖아|말했|뭐였|언제)", utterance):
            return True, "과거 참조 표현"
        if len(utterance) < 8:
            return False, "너무 짧음 — 신호 없음"
        if re.search(r"^(응|ㅇㅇ|ㅋ+|어|그래|넵|왜|뭐)$", utterance.strip()):
            return False, "의례적 발화"
        vocab = self._recall_vocab if chat_id is None else self._recall_vocab_for(chat_id)
        if any(w[:2] in vocab for w in re.findall(r"[가-힣]{2,}", utterance)):
            return True, "저장된 내용어와 접점"
        return False, "과거 참조 신호도 내용어 접점도 없음"

    def _recall_vocab_for(self, chat_id):
        """
        한 대화방의 사건 요약 앞 2글자 집합. 쓰기 때마다 바뀌므로 집합은 캐시하지 않는다.

        두 조건을 모두 건다: `chat_id`(격리 — 다른 방 얘기가 새면 안 된다)와 `user_deleted=0`
        (삭제 — 지운 사실의 색인 복사본이 게이트를 발화시키면 안 된다). `gate_sweep.build_vocab`도 같다.
        """
        v = set()
        sql = "SELECT summary FROM event WHERE user_deleted=0"
        args = ()
        if chat_id is not None:
            sql += " AND chat_id=?"
            args = (chat_id,)
        for r in self.db.execute(sql, args):
            # 요약 문자열이 키인 메모(파일 끝) — 조각만 기억하고 집합은 매번 새로 만든다.
            v |= _doc_heads(r["summary"])
        return v

    @property
    def _recall_vocab(self):
        """방을 안 가리는 어휘 — DB 전량. `_recall_vocab_for(None)`과 같다(방이 하나인 계측 하니스가 읽는다)."""
        return self._recall_vocab_for(None)

    def _population_sig(self, chat_id):
        """θ가 유도된 모집단과 지금 색인이 같은가를 보는 서명 — `rel_dist.population()`과 같은 정의."""
        r = self.db.execute(
            "SELECT COUNT(*) t, SUM(user_deleted=0) a FROM event WHERE chat_id=?",
            (chat_id,)).fetchone()
        return (r["t"], r["a"] or 0)

    # ── 문서 벡터 — `RETRIEVAL_MODE == "embed"`에서만 돈다 ──────────────────

    def _get_vec(self, text):
        """
        `embedding` 테이블에서 벡터 하나. 없으면 `None`.
        `db_get_vec`이 `(key, model)`로 조회하므로 모델이 다른 행도 `None`이다 — 모델을 갈면 옛 벡터는
        조회에서 빠지고 호출부가 다시 계산한다. 별도의 모델 비교 분기를 두지 않는 이유다.
        """
        try:
            return embedding.db_get_vec(self.db, text, EMBED_MODEL_NAME)
        except (sqlite3.Error, ValueError, TypeError):
            # 읽기 실패는 «벡터 없음»과 같게 다룬다 — 호출부가 할 일(다시 계산)이 같다.
            return None

    def _put_vec(self, chat_id, text, vec):
        """벡터 하나를 저장한다. 저장 실패는 검색을 죽일 이유가 아니다 — 다음 조회가 다시 계산한다."""
        try:
            embedding.db_put_vec(self.db, chat_id, text, vec, EMBED_MODEL_NAME)
        except sqlite3.Error:
            pass

    def _index_vectors(self, chat_id, query, rows, notes):
        """
        `embed` 모드의 벡터를 모은다. 반환: `(질의 벡터, rows 순서의 문서 벡터)` 또는 `None`(강등 신호).

        없는 벡터를 «안 맞음»으로 건너뛰지 않는다 — 그러면 그 행은 `rel`이 계산된 적도 없이 후보에서
        사라진다. 없는 것은 다시 계산해 저장하고 provenance에 남긴다. 질의와 미스는 한 요청으로 묶는다
        (배치 이득은 텍스트 수가 아니라 요청 수의 함수다).
        """
        cached = [self._get_vec(r["summary"]) for r in rows]
        # 같은 요약이 두 행에 있으면 한 번만 보낸다 (dedup 창 밖의 재발화가 그렇다)
        need = list(dict.fromkeys(r["summary"] for r, v in zip(rows, cached)
                                  if v is None))
        vecs = _embed_texts([query] + need)
        if vecs is None:
            return None
        fresh = dict(zip(need, vecs[1:]))
        if need:
            # 지연 재계산이 잦으면 쓰기 경로 사전계산이 안 돈다는 뜻이다 — 숫자에 안 보이므로 기록한다.
            notes.append((
                "lazy_embed", "embedding",
                f"문서 벡터 {len(need)}/{len(rows)}건이 없거나 모델이 달라 읽기 "
                f"경로에서 다시 계산해 저장했다 (모델 {EMBED_MODEL_NAME})"))
            for t in need:
                self._put_vec(chat_id, t, fresh[t])
        return _dims_agree(notes, vecs[0], [v if v is not None else fresh[r["summary"]]
                                            for r, v in zip(rows, cached)])  # 차원이 갈리면 None

    def _precompute_vec(self, chat_id, summary):
        """
        쓰기 경로 사전계산. 선언된 모드가 `embed`일 때만 돈다. 실패해도 조용하다 —
        `_index_vectors`의 지연 재계산이 다시 하고 그때 provenance에 남는다.
        """
        if RETRIEVAL_MODE != "embed":
            return
        v = _embed_texts([summary])
        if v is not None:
            self._put_vec(chat_id, summary, v[0])

    def retrieve(self, chat_id, query, now_seq, ext=None):
        """
        하드 게이트 → 가중 정렬 → 임계 컷 (ADR-005 4단계).

        `rel`의 척도는 `RETRIEVAL_MODE`, θ는 `THETA_BY_MODE`, 가중치는 `W_REL`/`W_IMP`.
        `ext`(`ExtRel`)를 주면 `rel`과 θ를 밖에서 꽂는다(엔진 비교 계측 전용).
        검색 경로의 계측 기록(강등·stale θ)은 `self._retrieval_notes`에 쌓이고 `build_context`가 provenance로 옮긴다.
        반환: `(상위 TOP_K의 (점수, 행), rejected)`. `ext.full`이면 상위 K로 자르지 않고 컷을 통과한 전부(같은 순서).
        """
        notes = self._retrieval_notes = []
        mode = RETRIEVAL_MODE
        # θ를 먼저 본다 — 유도 안 된 모드면 임베딩을 다 부른 뒤가 아니라 지금 실패한다.
        # 강등 뒤의 모드가 아니라 선언된 모드를 본다(강등 사실은 provenance가 남긴다).
        theta_for(mode)
        rows = self.db.execute(
            "SELECT event_id, summary, importance, emotional_weight, surfaced_count"
            " FROM event WHERE chat_id=? AND user_deleted=0", (chat_id,)).fetchall()
        if not rows:
            return [], []
        qv, dvecs = None, None
        if mode == "embed" and ext is None:
            # 쿼리 임베딩은 게이트 통과 시에만 불린다. 문서 벡터는 `embedding` 테이블에서 읽고
            # 없는 것만 질의와 함께 한 요청으로 계산한다.
            vecs = self._index_vectors(chat_id, query, rows, notes)
            if vecs is None:
                # 강등 — `embed`를 못 쓰면 어휘로 내려가되 provenance에 남긴다. 프로덕션 전용 규약이다:
                # 계측 하니스는 강등하지 않고 SKIP(77)한다(강등된 셀이 `embed` 라벨을 달면 안 된다).
                mode = "lexical_fixed"
                notes.append(("degraded", "embedding",
                              "벡터 공급자(EMBED_FN) 없음 또는 실패 — "
                              "lexical_fixed로 강등"))
            else:
                # `_index_vectors`는 이미 갈라진 (질의, 문서들) 쌍을 돌려준다.
                qv, dvecs = vecs
        theta = theta_for(mode) if ext is None else ext.theta  # 유도 안 된 모드면 RuntimeError
        # 읽기도 `[...]` 대신 `.get` — 제자리 변형 검사(`grep "THETA_BY_MODE\["`)가 읽기와 쓰기를 못 가른다.
        sig = THETA_BY_MODE.get(mode)[3]
        if sig is not None and ext is None:
            # θ가 유도된 모집단과 지금 색인이 다른가 — 비차단(값도 안 바꾸고 예외도 없다), 기록만 한다.
            # 서명이 없는 모드(lexical)는 건너뛴다.
            now_sig = self._population_sig(chat_id)
            if tuple(sig) != now_sig:
                notes.append(("stale_theta", mode,
                              f"θ가 유도된 모집단 {tuple(sig)}과 현재 색인 "
                              f"{now_sig}이 다르다"))
        qf = set(tokens_fixed(query)) if mode == "lexical_fixed" else None
        q = set(bigrams(query))
        scored, rejected = [], []
        for i, r in enumerate(rows):
            imp = max(r["importance"] or 0, r["emotional_weight"] or 0)
            if imp < TAU_IMPORTANCE:                       # 2단계 하드 게이트
                rejected.append((r["summary"], f"importance {imp:.2f} < τ"))
                continue
            d = _doc_grams(r["summary"])                   # 요약 문자열이 키인 메모 (파일 끝)
            # `q`·`d` 계산은 기본(lexical) 경로를 그대로 두려고 분기 밖에 있다 — 다른 모드에서는 `d`가 버려진다.
            if ext is not None:                            # 엔진 비교 계측 — `rel`만 갈아 끼운다
                rel = ext(query, rows, i)
            elif mode == "lexical":
                rel = coverage(q, d)                       # 3단계 관련도 — 현행 척도
            elif mode == "lexical_fixed":
                rel = jaccard(qf, tokens_fixed(r["summary"]))
            else:
                rel = _cosine(qv, dvecs[i])
            if rel < theta and not THETA_ON_SCORE:         # 4단계 임계 컷 (THETA_ON_SCORE면 최종 점수에서)
                rejected.append((r["summary"], f"relevance {rel:.2f} < θ"))
                continue
            s = W_REL * rel + W_IMP * imp - SURFACED_PENALTY * (r["surfaced_count"] or 0)
            _admit(self, r, s, theta, now_seq, scored, rejected)  # recency 항 · 최종 점수의 θ (파일 끝)
        # 동점은 `event_id` 오름차순으로 깬다 — 더 나은 순위가 아니라 재현 가능한 순위다. 점수 격자가
        # 성겨 정확 동점이 흔하고, 키가 점수뿐이면 SQLite의 반환 순서가 1등을 정한다.
        # 이 키로 바꾼 전후 격자와 스크립트 여섯의 지표(top1 4/10 · 회상 · 오주입 · pooled)가 한 자리도 안
        # 움직였다 — `event_id`가 곧 삽입 순서다.
        scored.sort(key=lambda x: (-x[0], x[1]["event_id"]))
        return (scored if ext is not None and ext.full else scored[:TOP_K]), rejected

    def due_debts(self, chat_id, now_seq, session_start=False, notes=None):
        """이번 턴에 주입할 부채. 한 행의 판정은 `_debt_verdict`(백오프 · 세션 시작 게이트 · 트리거 · 소멸)."""
        out = []
        for r in self.db.execute(
                "SELECT * FROM debt WHERE chat_id=? AND status='open'",
                (chat_id,)).fetchall():
            verdict = _debt_verdict(self, r, now_seq, session_start, notes)
            if verdict == "expire":
                self.db.execute("UPDATE debt SET status='expired' WHERE debt_id=?",
                                (r["debt_id"],))
            elif verdict == "due":
                out.append(r)
        # 나머지 셋("backoff"·"gate"·"trigger")은 이번 턴에 안 나간다 — 행은 open 그대로.
        return out

    # ── 계층별 실패 정책 ────────────────────────────────────────────
    #   L0 최근 턴   없으면 대화가 아니다                    -> 중단
    #   L2 관계      없으면 상태 위반이 확실하다 (연인인데 남처럼)  -> 중단
    #   L4 요약      품질 저하로 그친다                      -> 생략
    #   L5 사실      없는 걸 아는 척하면 환각                 -> 생략 + 명시
    #   L6 사건      검색 실패는 원래 흔하다                   -> 생략
    #   L9 부채      다음 턴에 다시 시도                      -> 생략
    # 사실 계층 실패만 «조용한 환각»을 만든다(모델이 지어낸다 — 실험 13) — 그래서 그 실패만 컨텍스트에 알린다.
    CRITICAL_LAYERS = {"turn", "relationship"}

    def _safe(self, layer, fn, default=None):
        """계층 조회를 감싼다. 필수 계층은 예외를 올리고, 나머지는 삼킨다."""
        try:
            return fn()
        except Exception as e:
            if layer in self.CRITICAL_LAYERS:
                raise RuntimeError(f"필수 계층 {layer} 조회 실패 — 응답 중단") from e
            self._degraded.append(layer)
            return default

    def build_context(self, chat_id, utterance, now_seq, session_start=False):
        """
        컨텍스트 조립 — 공유 범위 × 변경 빈도 오름차순 (docs/adr/ADR-007).
        volatility가 낮은 것부터. 검색된 기억은 맨 뒤.
        """
        self._degraded = []
        ctx = Context()
        ch = self.db.execute("SELECT * FROM chat WHERE chat_id=?", (chat_id,)).fetchone()
        cv = self.db.execute(
            "SELECT * FROM character_version WHERE character_id=? AND version=?",
            (ch["character_id"], ch["character_version"])).fetchone()

        ctx.blocks.append(Block("system", "너는 캐릭터를 연기한다. 설정을 벗어나지 마라.",
                                "global", 0))
        ctx.blocks.append(Block("persona", cv["persona_text"], "character", 1))
        ctx.blocks.append(Block("speech_rules", cv["speech_rules"], "character", 1))

        # [알고 있는 것] — 항상 주입, 검색 대상이 아니다. 관계 상태보다 덜 변하므로 그 앞(volatility 2.5)에 둔다.
        if INJECT_KNOWN_FACTS:
            known = self._safe("fact", lambda: [
                f for f in self.facts_at(chat_id)
                if f["predicate"] in self.PREDICATE_STANDING or _unknown_pred(self, f["predicate"])[2]], default=None)
            if known is None:
                # 사실 계층 실패는 조용히 넘기지 않는다 — 없으면 모델이 지어낸다.
                ctx.blocks.append(Block(
                    "알고 있는 것",
                    "(기억을 불러오지 못했다. 아는 척하지 말고 모른다고 말할 것)",
                    "chat", 2.5))
                ctx.provenance.append(
                    ("degraded", "fact", "조회 실패 — 회피 모드로 알림"))
            elif known:
                ctx.blocks.append(Block("알고 있는 것", "\n".join(
                    _known_line(f, ctx.provenance) for f in known),
                    "chat", 2.5))
                ctx.provenance.append(
                    ("known_facts", f"{len(known)}건", "결정적 주입 — 검색 안 함"))

            else:
                # 콜드 스타트: 블록을 생략하지 않고 «(아직 없음)»을 명시한다(실험 17 — 생략하면 첫 세션
                # 환각 83%, 명시하면 58%, 첫 대화임까지 알리면 33%).
                # 되묻기 지시까지 더하면 17%였으나 넣지 않았다 — 여기 구현은 33% 조건이다.
                first = self.db.execute(
                    "SELECT COUNT(*) c FROM turn WHERE chat_id=?",
                    (chat_id,)).fetchone()["c"] <= WINDOW_TURNS
                note = ("(아직 없음)\n이번이 첫 대화다. 이전 기록이 없다."
                        if first else "(아직 없음)")
                ctx.blocks.append(Block("알고 있는 것", note, "chat", 2.5))
                ctx.provenance.append(
                    ("known_facts", "0건",
                     "빈 블록 명시 — 생략하면 환각 83% (실험 17)"))
        rel = self.db.execute("SELECT * FROM relationship WHERE chat_id=?",
                              (chat_id,)).fetchone()
        # stage_note(자유 텍스트)는 결정적 주입에서 뺐다 — 매 턴 주입되는 자유 텍스트는 공격 표면이고,
        # 대화마다 바뀌어 캐시 접두사를 깬다(ADR-007). UI 표시·모순 검사용으로는 남긴다.
        ctx.blocks.append(Block("relationship",
            _one_line(f"단계={rel['stage']} 호감도={rel['affinity']} 호칭={rel['called_as']}", ctx.provenance, "relationship"),
            "chat", 3))
        ctx.provenance.append(("relationship", rel["stage"], "결정적 주입"))
        if rel["stage_note"]:
            ctx.provenance.append(
                ("excluded", f"stage_note: {rel['stage_note']}",
                 "자유 텍스트 — 결정적 주입 제외 (캐시 안정 + 공격 표면)"))

        # digest 주입(두 소스 · 사유별 3분기)은 `_serve_digest`가 한다.
        self._serve_digest(ctx, chat_id)

        # 부채는 결정적 주입이지만 있다 없다 하므로 앞쪽에 두면 캐시 접두사가 깨진다 — 뒤쪽에 둔다.
        debts = self.due_debts(chat_id, now_seq, session_start, ctx.provenance)
        if debts:
            ctx.blocks.append(Block("debt", "\n".join(
                f"- {_one_line(d['content'], ctx.provenance, 'debt')}" for d in debts), "chat", 8.5))
            for d in debts:
                ctx.provenance.append(("debt", d["content"], "트리거 충족 — 결정적 주입"))
                self.db.execute(
                    "UPDATE debt SET last_attempted_seq=?, attempt_count=attempt_count+1"
                    " WHERE debt_id=?", (now_seq, d["debt_id"]))

        sc = self.db.execute("SELECT * FROM scene WHERE chat_id=?", (chat_id,)).fetchone()
        if sc:
            ctx.blocks.append(Block("scene",
                _one_line(f"장소={sc['place']} 참여자={sc['present']} 상황={sc['situation']}", ctx.provenance, "scene"),
                "chat", 7))

        # 최근 턴 — 청크 축출 (실험 1: 1턴씩 밀면 캐시 전멸)
        anchor = (now_seq // WINDOW_CHUNK) * WINDOW_CHUNK
        recent = self.db.execute(
            "SELECT role, text FROM turn WHERE chat_id=? AND seq>? AND seq<?"
            " ORDER BY seq", (chat_id, anchor - WINDOW_TURNS, now_seq)).fetchall()
        if recent:
            ctx.blocks.append(Block("recent", "\n".join(
                f"{r['role']}: {r['text']}" for r in recent), "chat", 8))

        # 검색 — 게이트 통과 시에만, 맨 뒤(변경 빈도 최대). 이 방의 어휘만 본다.
        need, why = self.gate(utterance, chat_id)
        ctx.provenance.append(("gate", "통과" if need else "차단", why))
        if need:
            hits, rejected = self.retrieve(chat_id, utterance, now_seq)
            # 검색 경로의 계측 기록(강등 · stale θ). 기본 경로에서는 비어 있다.
            ctx.provenance.extend(self._retrieval_notes)
            for _, r in hits:
                self.db.execute(
                    "UPDATE event SET retrieval_count=retrieval_count+1"
                    " WHERE event_id=?", (r["event_id"],))
            if hits:
                ctx.blocks.append(Block("retrieved", "\n".join(
                    f"[기억] {_one_line(r['summary'], ctx.provenance, 'retrieved')}" for _, r in hits), "chat", 9))
            for s, r in hits:
                ctx.provenance.append(("retrieved", r["summary"], f"score {s:.2f}"))
            for summ, reason in rejected:
                ctx.provenance.append(("rejected", summ, reason))

        ctx.blocks.append(Block("utterance", utterance, "chat", 10))
        ctx.blocks.sort(key=lambda b: b.volatility)
        self.db.commit()
        return ctx


# ── 전이 → 다이제스트 전파 스위치 (ADR-013) ─────────────────────────────
# 이 절부터 파일 끝까지는 나중에 더한 스위치·헬퍼다. 당시 문서 인용 수십 곳과 박힌 상수 감사가 이 파일 앞쪽
# 줄 번호를 닻으로 삼고 있어, 줄을 밀지 않으려고 끝에 붙였다. 대가는 읽기 순서다(상수가 쓰이는 곳보다 뒤에 있다).
# 모듈 전역이라 호출 시점에 읽혀 동작은 어디 두든 같다.
#
# `False`(기본) = 관계 단계 전이가 `digest` 키를 stale로 밀지 않는다(해석은 민다).
# `True` = 옛 동작 — lifetime + legacy session + `session:*` 전량을 `전이:` 사유로 밀고 다음 경계가 다시 만든다.
# 끈 이유: 두 요약 프롬프트는 `stage`를 받지 않아 전이 전후 프롬프트가 바이트 동일하다 — 재생성해도
# 새 정보가 없고, 생성이 비결정적이면 요약만 표류한다. 요약 프롬프트가 전이를 알게 되면 되돌린다
# (`test_summarize.py`의 전이 전후 프롬프트 대조가 알린다).
TRANSITION_PROPAGATES_DIGEST = False


# ── 서사 부채의 판정 · 상환 (docs/06 L9) ────────────────────────────────
# 백오프는 턴이 아니라 세션 경계 1·3·7번이다(설계의 «1세션 → 3세션 → 7세션 → 만료»).
# 시계가 세션인 `time` 트리거 `Nd`는 N 경계로 센다(하루 = 한 세션 근사).
# 이 근사는 대장 D002(`3d` · 기대 회수 S15)를 기대보다 늦게 쏜다.
# 평가하지 못하는 트리거(벽시계 · 날짜 · spec 없음 · 의미 트리거)는 충족으로 보고 백오프만으로
# 판정하되 provenance에 남긴다 — 영영 안 나가는 쪽이 더 나쁜 실패다.
# 의미 트리거는 구현하지 않았다(문턱을 유도할 모집단이 없다). `emotional_stake`는 읽지 않는다.
# 설계(docs/06)는 «높을수록 오래 버틴다»뿐이고 수가 없다 — 넣으면 유도 안 된 상수가 하나 는다.
DEBT_BACKOFF_SESSIONS = (1, 3, 7)
DEBT_EXPIRE_ATTEMPTS = 3
_DAYS = re.compile(r"(\d+)d")


def _sessions_since(m, chat_id, seq, now_seq, session_start):
    """
    `seq`가 든 세션 뒤로 지난 경계 수와, 카운터가 뒤처졌는가.

    `seq`가 세션의 마지막 턴이면 그 세션은 거기서 끝났으므로 `seq - 1`을 넘긴다. 세션 첫 턴
    (`session_start`)에서는 최소 1이 확실하다 — 카운터가 0이면 요약 층이 이 경계를 아직 모른다.
    """
    n = m.session_boundaries_since(chat_id, seq - 1)
    floor = 1 if session_start and seq < now_seq else 0
    return max(n, floor), n < floor


def _debt_verdict(m, r, now_seq, session_start, notes=None):
    """부채 한 행 → "backoff" · "gate" · "trigger" · "expire" · "due" (이 순서로 판정)."""
    a, did = r["attempt_count"], r["debt_id"]
    last = r["last_attempted_seq"] or r["setup_turn_seq"]
    n, lag = _sessions_since(m, r["chat_id"], last, now_seq, session_start)
    if lag and notes is not None:
        notes.append(("degraded", f"debt:{did}", "세션 경계 카운터가 이 경계를 모른다"
                      " (digest_session 행 없음) — 최소 1로 센다"))
    if n < DEBT_BACKOFF_SESSIONS[min(a, len(DEBT_BACKOFF_SESSIONS) - 1)]:
        return "backoff"
    kind, spec, clock = r["trigger_kind"], r["trigger_spec"], r["trigger_clock"]
    if kind == "session_start" and not session_start:
        return "gate"
    days = _DAYS.fullmatch(spec or "") if kind == "time" else None
    # 세션 시계는 `digest_session`의 행으로 세는데 그 행은 `DIGEST_KEEP_SESSIONS`개까지만
    # 남는다 — 그보다 긴 `Nd`는 카운터가 영영 못 닿는다(조용히 죽는 자리라 강등으로 보낸다).
    countable = days and clock == "session" and int(days.group(1)) <= DIGEST_KEEP_SESSIONS
    why = None
    if countable:
        since_setup = _sessions_since(m, r["chat_id"], r["setup_turn_seq"], now_seq,
                                      session_start)[0]
        if since_setup < int(days.group(1)):
            return "trigger"
    elif kind == "time":
        why = (f"시각 트리거 {spec!r}를 {clock!r} 시계로 셀 수 없다"
               + (" — 세션 경계는 요약 보존 상한까지만 센다" if days and clock == "session"
                  else ""))
    elif kind == "semantic":
        why = "의미 트리거 — 평가 안 함 (wave4 ④)"
    elif kind != "session_start":
        why = f"모르는 trigger_kind {kind!r}"
    if a >= DEBT_EXPIRE_ATTEMPTS:
        return "expire"
    if why and notes is not None:
        notes.append(("degraded", f"debt:{did}", why + " — 백오프만으로 주입"))
    return "due"


def _pay_debt(m, chat_id, seq, rid):
    """
    `used_memories`의 `debt:N` → `paid`. 이 방의 열린 부채이고 한 번이라도 주입된 것만 받는다 —
    모델이 부채를 아는 길은 주입뿐이라, 주입된 적 없는 id는 지어낸 것이다.
    받지 않은 선언은 `_filter_cols`처럼 provenance와 위반 표에 남긴다.
    """
    row = m.db.execute("SELECT status, attempt_count FROM debt WHERE debt_id=?"
                       " AND chat_id=?", (rid, chat_id)).fetchone()
    reason = ("이 방에 없는 부채" if row is None
              else f"이미 {row['status']}" if row["status"] != "open"
              else "주입된 적 없는 부채" if not row["attempt_count"] else None)
    if reason:
        m._prov(chat_id, seq, "meta_rejected", f"used_memories.debt:{rid}", reason)
        m._violation(chat_id, seq, "used_memories.debt", None, rid, reason)
        return False
    m.db.execute("UPDATE debt SET status='paid' WHERE debt_id=?", (rid,))
    m._prov(chat_id, seq, "debt_paid", f"debt:{rid}", "used_memories 선언")
    return True


# 관계 행의 자유 텍스트 칸(호칭·감정)도 씬과 같은 형태 가드를 탄다 — 개행 하나로 관계 블록 안에
# 가짜 블록 머리를 만들 수 있었다. 감정 칸은 주입되지 않지만 문자열이 아니면 UPDATE가 터졌다.
STATE_TEXT_COLS = {"called_as", "last_emotion"}


def _guard_state_text(m, chat_id, seq, d):
    return {k: v for k, v in d.items() if k not in STATE_TEXT_COLS
            or m._scene_value_ok(chat_id, seq, k, v, "state_delta")}


# ── 검색의 두 스위치 — θ의 위치와 recency 항 (ADR-005) ────────────────
# 기본값은 둘 다 꺼짐 = 기존 동작(`_admit`은 `scored.append((s, r))`와 같다).
#
# THETA_ON_SCORE — `False` = θ가 `rel`에 걸리고 가중합은 컷 뒤에 계산된다.
#   `True` = ADR-005의 «최종 점수 < θ». θ 값은 그대로라 뜻이 달라진다 — lexical 0.05는 τ를 넘은
#   행의 최저 점수(0.08)보다 낮아 페널티가 없으면 아무것도 못 자른다. 재유도는 `experiments/theta_position.py`.
#
# W_REC · RECENCY_HALF_LIFE — penalty = 1 − 2^(−age / H), age = now_seq − source_from_seq (행 단위).
#   [0, 1) 범위라 `rel`·`imp`와 같은 척도이고, 나이만의 함수라 대화 길이가 다른 방끼리도 비교된다.
#   H = 240행(8세션)은 유도값이 아니라 코퍼스 고유다 — 색인 나이 88~718행을 0.22~0.87로 펴는 값이다.
#   병합은 `source_from_seq`를 갱신하지 않는다(첫 언급의 나이). 미래 행(age < 0)은 0으로 자른다.
THETA_ON_SCORE = False
W_REC = 0.0
RECENCY_HALF_LIFE = 240


def recency_penalty(now_seq, seq):
    """나이(행) → [0, 1). 위 절의 정의. 나이를 모르면 `None`."""
    if seq is None or now_seq is None:
        return None
    return 1 - 0.5 ** (max(now_seq - seq, 0) / RECENCY_HALF_LIFE)


def _admit(m, r, s, theta, now_seq, scored, rejected):
    """`retrieve` 루프의 마지막 두 단계 — recency 항과 (켜졌으면) 최종 점수의 θ 컷."""
    if W_REC:
        seq = m.db.execute("SELECT source_from_seq FROM event WHERE event_id=?",
                           (r["event_id"],)).fetchone()[0]
        p = recency_penalty(now_seq, seq)
        if p is None:
            m._retrieval_notes.append(("degraded", "recency",
                                       f"event {r['event_id']}: 나이를 모른다 — 페널티 0"))
        else:
            s -= W_REC * p
    if THETA_ON_SCORE and s < theta:
        rejected.append((r["summary"], f"최종 점수 {s:.2f} < θ"))
        return
    scored.append((s, r))


# ── 엔진 비교용 관련도 주입 ────────────────────────────────────────────
# `experiments/engine_arms.py`의 모든 팔이 점수식 사본 없이 이 파일의 `retrieve` 하나를 지나게 한다 —
# 팔이 바꾸는 것은 `rel`(과 그 척도의 θ)뿐이다. `full=True`면 상위 K로 자르지 않는다(순위 전체).
# 목록 길이가 행 수와 다르면 던진다 — 계측에서 강등은 결함이다.
class ExtRel:
    """검색 4단계의 `rel`을 밖에서 꽂는다. `rel_fn(질의, 요약 목록) → rel 목록`(같은 순서)."""

    def __init__(self, rel_fn, theta, full=False):
        self.rel_fn, self.theta, self.full = rel_fn, theta, full
        self._at = self._vals = None

    def __call__(self, query, rows, i):
        # 한 호출 안에서는 한 번만 센다(BM25는 색인 전체 통계가 필요하다). `rows`를 참조로 붙들어
        # `is`로 대조한다 — 목록 id가 재사용돼 옛 값을 쓰는 일이 없다.
        if self._at is None or self._at[0] is not rows or self._at[1] != query:
            vals = list(self.rel_fn(query, [r["summary"] for r in rows]))
            if len(vals) != len(rows):
                raise ValueError(f"외부 관련도 {len(vals)}개 ≠ 행 {len(rows)}개 — 조용히 어긋나지 않는다")
            self._at, self._vals = (rows, query), vals
        return self._vals[i]


# 벡터 차원 검사. `zip`은 짧은 쪽에서 조용히 끊는다 — 차원 축소(1024 → 256)를 한쪽에만 적용하면
# 앞 256차원만으로 그럴듯한 값이 나오고 θ가 그 위에서 자른다. 두 층으로 막는다:
#   ① `_cosine`은 던진다(0.0이나 NaN은 조용히 틀린다 — NaN은 θ를 통과한다).
#   ② 검색 경로는 코사인 전에 `_dims_agree`로 맞춰 보고 갈리면 강등한다(`dim_mismatch` 노트).
class DimMismatch(ValueError):
    """길이가 다른 두 벡터의 코사인."""


def _same_dim(a, b):
    if len(a) != len(b):
        raise DimMismatch(f"벡터 차원이 다르다: {len(a)} ≠ {len(b)}")
    return b


def _dims_agree(notes, qv, dvecs):
    """`(질의 벡터, 문서 벡터들)` — 차원이 하나로 모이면 그대로, 갈리면 노트를 남기고 `None`."""
    dims = sorted({len(qv)} | {len(v) for v in dvecs})
    if len(dims) == 1:
        return qv, dvecs
    notes.append(("dim_mismatch", "embedding",
                  f"벡터 차원이 {dims}로 갈렸다 (질의 {len(qv)}) — 코사인을 세지 않고 강등"))
    return None


# ── 내용 주소 메모 — 검색·게이트가 행마다 하던 토큰화 ──────────────────
# 키가 요약 문자열 그 자체라 낡을 수 없다(요약이 바뀌면 키가 바뀌고, 지운 행은 SQL이 거른다).
# 방별 어휘 집합은 캐시하지 않는다 — 그것은 무효화할 거리를 하나 더 만든다.
# 반환은 `frozenset` — 호출부가 변형하면 다음 호출이 오염된다.
# 한계: 콜드 첫 조회는 전부 계산하고, 서로 다른 요약이 `MEMO_ROWS`보다 많으면 LRU가 순차 훑기에서
# 거의 다 빗나간다(점진 저하가 아니라 절벽). 상한은 프로세스 전역이다(두 메모 합 항목당 ≈1.2 KB → 둘 다 차면 ≈38 MiB).
import functools  # noqa: E402 — 파일 끝에 붙인 절이라 import도 여기 있다

MEMO_ROWS = 16384


def _grams_raw(summary):
    return frozenset(bigrams(summary))


def _heads_raw(summary):
    return frozenset(w[:2] for w in re.findall(r"[가-힣]{2,}", summary))


_doc_grams = functools.lru_cache(maxsize=MEMO_ROWS)(_grams_raw)
_doc_heads = functools.lru_cache(maxsize=MEMO_ROWS)(_heads_raw)


# ── 표 밖 술어의 기본값 (ADR-004) ────────────────────────────────────
# 세 표(카디널리티 · 가변성 · 상시성) 모두에 없는 술어의 처분. 기본 "legacy" = 기존 동작
# (many / mid / 상시 아님). 켤지는 제품 결정이고 후보별 대가는 `experiments/predicate_default.py`가 잰다.
# 한 표에만 있는 술어는 기존 값 그대로다(예: `일상_사소`는 일부러 상시 표에 없다).
# 정책이 호출 가능하면 `술어 → (카디널리티, 가변성, 상시성)`으로 부른다(계측 전용).
UNKNOWN_PREDICATE_POLICY = "legacy"
UNKNOWN_PREDICATE_DEFAULTS = {
    "legacy": ("many", "mid", False),          # 기존 동작
    "one": ("one", "mid", False),              # 모르면 단일값 — 갱신이 무효화로 끝난다 · 다중값 사실이 덮인다
    "standing": ("many", "mid", True),         # 모르면 상시 주입 — 누락이 준다 · 상시 블록이 커진다
    "one+standing": ("one", "mid", True),
}


def _unknown_pred(m, predicate):
    """세 표 어디에도 없는 술어면 정책 값, 하나라도 있으면 기존 값 `("many", "mid", False)`."""
    if (predicate in m.PREDICATE_CARDINALITY or predicate in m.PREDICATE_MUTABILITY
            or predicate in m.PREDICATE_STANDING):
        return UNKNOWN_PREDICATE_DEFAULTS["legacy"]
    p = UNKNOWN_PREDICATE_POLICY
    return p(predicate) if callable(p) else UNKNOWN_PREDICATE_DEFAULTS[p]


# ── 쓰기 가드 · 방 대조 · 한 줄 렌더 ─────────────────────────────────
# 평가 코퍼스 경로에서는 아래의 거부·치환 분기가 발화하지 않는다 — 렌더 바이트가 기존과 같다.
# 부채 쓰기(INSERT)는 `apply_meta` 안에 둔다(부채 쓰기 자리가 한 곳임을 시험이 센다).

def _forget_digest_key(m, chat_id, key):
    """
    N 상한에 밀려난 세션 키의 흔적을 지운다 — stale · digest_meta · derivation.
    파생 등록이 남으면 옛 원본을 지울 때 없는 키가 stale로 찍혀 재생성이 경계마다 실패한다.
    이 키가 원본인 행(lifetime ← 세션 키)은 남긴다 — lifetime이 다시 쓰일 때 갈아 끼워진다.
    """
    m.db.execute("DELETE FROM stale WHERE chat_id=? AND derived_kind='digest'"
                 " AND derived_key=?", (chat_id, key))
    m.db.execute("DELETE FROM digest_meta WHERE chat_id=? AND kind=?", (chat_id, key))
    m.db.execute("DELETE FROM derivation WHERE chat_id=? AND derived_kind='digest'"
                 " AND derived_key=?", (chat_id, key))


# 렌더의 한 줄을 깨는 글자 — C0 제어문자 · DEL · C1 제어문자 · 줄/문단 구분자(U+2028 · U+2029).
# 파이썬의 줄 나누기가 줄 경계로 보는 글자(0x1c-0x1e · 0x85 포함)가 전부 여기 든다.
_LINE_BREAKERS = re.compile(r"[\x00-\x1f\x7f-\x9f" + chr(0x2028) + chr(0x2029) + "]")


def _one_line(text, notes=None, where=""):
    """
    자유 텍스트를 렌더의 한 줄로 — 줄을 깨는 글자를 공백으로 바꾼다(개행 하나로 가짜 블록 머리를
    세우지 못하게). 저장값은 건드리지 않는다. 바꾸면 `notes`에 `sanitized` 한 줄, 바꿀 것이 없으면
    입력을 그대로 돌려준다. 문자열이 아니면 그대로 돌려준다.
    """
    if not isinstance(text, str):
        return text
    out, n = _LINE_BREAKERS.subn(" ", text)
    if n and notes is not None:
        notes.append(("sanitized", where, f"줄을 깨는 글자 {n}개 → 공백 (한 줄 렌더)"))
    return out


def _known_line(f, notes=None):
    """
    `[알고 있는 것]`의 한 줄. 주어를 버리지 않는다 — 지인_직업처럼 남의 속성은 누구의 것인지
    모델이 알아야 한다. 주어가 «지우» · None · 빈 문자열이면 «지우의 …»로 박아 적던 기존 줄과 같다.
    """
    who = "지우" if f["subject"] in (None, "", "지우") else f["subject"]
    return _one_line(f"· {who}의 {f['predicate']}: {f['object']}", notes, "알고 있는 것")


def _surface_event(m, chat_id, seq, rid):
    """`used_memories`의 `event:N` → 표면화 계수 +1. 이 방의 사건만 받고, 아니면(없는 id 포함) 기록하고 거부한다."""
    cur = m.db.execute("UPDATE event SET surfaced_count=surfaced_count+1"
                       " WHERE event_id=? AND chat_id=?", (rid, chat_id))
    if cur.rowcount:
        return True
    m._prov(chat_id, seq, "meta_rejected", f"used_memories.event:{rid}", "이 방에 없는 사건")
    m._violation(chat_id, seq, "used_memories.event", None, rid, "이 방에 없는 사건")
    return False


def _new_debt_ok(m, chat_id, seq, nd):
    """
    새 부채 선언을 받을 것인가. 내용이 없거나 · 문자열이 아니거나 · 줄을 깨는 글자가 있으면
    드롭하고 기록한다(화이트리스트 처분과 같다). 부채는 자유 문장이라 길이 상한은 없다.
    """
    c = nd.get("content") if isinstance(nd, dict) else None
    reason = ("dict 아님" if not isinstance(nd, dict)
              else "content 없음" if c is None
              else f"문자열 아님({type(c).__name__})" if not isinstance(c, str)
              else "제어문자 포함" if _LINE_BREAKERS.search(c) else None)
    if reason is None:
        return True
    field = "new_debt.content"            # 위반 칸 이름 — `_filter_cols`의 «키.칸» 규약
    m._prov(chat_id, seq, "meta_rejected", field, reason)
    m._violation(chat_id, seq, field, None, c, reason)
    return False


# `delete_item`의 종류 → (테이블, id 칸). 모르는 종류는 KeyError로 멈춘다.
_DELETE_TABLES = {"fact": ("fact", "fact_id"), "event": ("event", "event_id")}


def _flag_deleted(m, chat_id, table, col, item_id):
    """원본 하나에 삭제 표시 — 이 방의 행일 때만. 반환: 표시한 행 수(0 또는 1)."""
    return m.db.execute(f"UPDATE {table} SET user_deleted=1 WHERE {col}=? AND chat_id=?",
                        (item_id, chat_id)).rowcount


def _delete_rejected(m, chat_id, kind, item_id):
    """
    다른 방(또는 없는) id의 삭제 요청 — 아무것도 안 지우고 기록한다. 반쯤 된 삭제(원본만 지워지고
    색인·요약은 사는 것)보다 안 된 삭제 + 기록이 낫다.
    """
    m._prov(chat_id, 0, "meta_rejected", f"delete.{kind}:{item_id}", "이 방에 없는 항목")
    m._violation(chat_id, 0, f"delete.{kind}", None, item_id, "이 방에 없는 항목")
    m.db.commit()
    return []


# ── 같은 턴 왕복 ─────────────────────────────────────────────────────

def _same_turn_flip(m, chat_id, seq, predicate, obj):
    """
    이 턴에 같은 (술어, 값) 행이 이미 있는가 — 있으면 새 행이 fact의 UNIQUE(방 · 턴 · 술어 · 값)에 걸린다.
    한 턴 안에서 A → B → A로 흔들리면 셋째 진술이 첫 A 행과 부딪친다. 그래서 어떤 UPDATE보다 앞에서
    검사한다(그러지 않으면 B를 무효화한 뒤 INSERT가 실패해 유효한 값이 0개가 된다).
    UNIQUE에 주어가 없어 다른 주어의 같은 (술어, 값)도 여기서 걸린다.
    """
    return m.db.execute(
        "SELECT 1 FROM fact WHERE chat_id=? AND source_turn_seq=? AND predicate=? AND object=?",
        (chat_id, seq, predicate, obj)).fetchone() is not None


def _flip_note(m, chat_id, seq, subject, predicate, obj):
    """
    같은 턴 왕복의 보류 — 확신 부족 보류와 같은 모양(provenance `fact_held` · 커밋 · 설명 «보류 — …»).
    한 턴에 값이 셋인 것은 추출기의 흔들림으로 보고 B를 유지한다.
    """
    who = m.db.execute(
        "SELECT subject FROM fact WHERE chat_id=? AND source_turn_seq=? AND predicate=? AND object=?",
        (chat_id, seq, predicate, obj)).fetchone()[0]
    why = "같은 턴 왕복" if who == subject else f"같은 턴 같은 값 — 다른 주어 «{who}»의 행"
    m._prov(chat_id, seq, "fact_held", f"{predicate}={obj}", f"{why} — 이 턴에 이미 물린 값")
    m.db.commit()
    return f"보류 — {why}. 셋째 진술은 덮지 않는다. 확인 필요"


def _retire(m, old):
    """단일값 충돌의 옛 행을 무효화하고 그 시각을 준다(새 행의 valid_from과 같은 값)."""
    now = time.time()
    m.db.execute("UPDATE fact SET valid_until=? WHERE fact_id=?", (now, old["fact_id"]))
    return now


# ── 신규/병존 INSERT의 UNIQUE 충돌 — 조용히 버리지 않고 보류로 기록한다 ─────────
# UNIQUE에 주어가 없는 것은 알려진 한계다(스키마는 그대로 둔다).

def _insert_fact(m, chat_id, subject, predicate, obj, realm, seq, importance, confidence):
    """
    신규/병존 사실 한 행(`INSERT OR IGNORE`). 반환: 넣은 행 수(0 또는 1).
    0은 UNIQUE(방 · 턴 · 술어 · 값)에 이미 행이 있다는 뜻이다 — 다른 주어의 행이거나,
    같은 주어가 같은 턴에 지운/무효화한 옛 행이다.
    """
    return m.db.execute(
        "INSERT OR IGNORE INTO fact (chat_id, subject, predicate, object,"
        " realm, valid_from, source_turn_seq, importance, confidence)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (chat_id, subject, predicate, obj, realm, time.time(), seq,
         importance, confidence)).rowcount


def _unique_note(m, chat_id, seq, subject, predicate, obj):
    """
    신규/병존 INSERT가 0행일 때의 보류(`_flip_note`와 같은 모양). 새 행은 없다 — 손실을 기록할 뿐이다.
    사유는 부딪친 행으로 가른다:
      다른 주어의 행           → «같은 턴 같은 (술어, 값) — 다른 주어 «X»의 행»
      같은 주어 · 지운 행      → «같은 턴에 지운 옛 행»
      같은 주어 · 무효화된 행  → «같은 턴에 무효화된 옛 행»
      같은 주어 · 유효한 행    → «같은 턴에 이미 있는 같은 행» (주어가 None — SQL `=`가 NULL을 못 찾는다)
    """
    who, deleted, retired = m.db.execute(
        "SELECT subject, user_deleted, valid_until IS NOT NULL FROM fact"
        " WHERE chat_id=? AND source_turn_seq=? AND predicate=? AND object=?",
        (chat_id, seq, predicate, obj)).fetchone()
    if who != subject:
        why = f"같은 턴 같은 (술어, 값) — 다른 주어 «{who}»의 행"
    elif deleted or retired:
        why = "같은 턴에 지운 옛 행" if deleted else "같은 턴에 무효화된 옛 행"
    else:
        why = "같은 턴에 이미 있는 같은 행"
    m._prov(chat_id, seq, "fact_held", f"{predicate}={obj}", f"{why} — 새 행은 UNIQUE에 걸린다")
    m.db.commit()
    return f"보류 — {why}. 재진술은 새 행이 못 된다. 확인 필요"
