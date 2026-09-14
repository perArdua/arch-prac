"""
메모리 시스템 프로토타입 — docs/10 추천 구조를 실제로 구현한다.

목적은 성능이 아니라 **설계가 놓친 것을 드러내는 것**이다.
수기 세션을 쓰다가 U10과 해석 형성 정책이 나왔듯이, 구현하면 또 나온다.

구현 범위 (docs/06 데이터 모델의 부분집합):
  L0 turn          원본 (영구)
  L1 character     페르소나 + speech_rules (버전 고정)
  L2 relationship  관계 상태 — 항상 주입 (결정적)
  L3 scene         씬 — 항상 주입
  L4 digest        session / lifetime 2층
  L5 fact          bi-temporal
  L6 event         importance + surfaced_count
  L9 debt          트리거 + 백오프
  M  coverage      구간별 해상도

의존성: 표준 라이브러리만 (sqlite3, re, json)
"""

import json
import re
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Optional

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
"""

# ── 설정 (docs/11 실험 7 스윕 결과) ─────────────────────────────────────
TAU_IMPORTANCE = 0.2      # 하드 게이트 (0.2~0.4 둔감구간)
# θ는 원래 0.15였다 ([실험 7 스윕](../docs/11-experiment-results.md)).
# 그런데 그 스윕은 **검색기만 격리해서** 최적화한 값이다.
# [gate_sweep.py](gate_sweep.py)에서 시스템 전체로 재보니 정답 근거의
# 질문-요약 중첩이 대부분 0.00~0.11이라 **정답이 임계 아래에 깔려 있었다.**
# 0.05로 낮추면 회상 +2건에 오주입 +23건(1건당 12). 0.00까지 열면 1건당 188로 급증.
# → 무릎은 0.05. **부품에 최적인 값이 시스템에서는 최악에 가까웠다.**
THETA_RELEVANCE = 0.05    # 임계 컷 (0.15 -> 0.05, gate_sweep 무릎)
TOP_K = 5
WINDOW_TURNS = 10         # 무릎 (실험 7C)
SURFACED_PENALTY = 0.1    # 무릎 (실험 10B)
WINDOW_CHUNK = 10         # 청크 축출 (실험 1)
MIN_EVIDENCE_FOR_INTERPRETATION = 3   # 수기 세션에서 도출

# 🔴 소크 테스트(prototype/soak.py)에서 드러난 것.
#
# docs/15에서 컨텍스트를 [알고 있는 것] / [꺼낼 만한 것]로 나눠 설계해놓고,
# **build_context는 [꺼낼 만한 것]만 구현했다.** facts_at()은 fact_demo에서만
# 호출됐고 읽기 경로에는 연결된 적이 없다. 데모가 사실을 별도 스크립트로
# 확인하는 바람에 **읽기 경로에 구멍이 있다는 걸 아무도 못 봤다.**
#
# 결과: "나 커피 마셔도 되나?" 같은 질문은 과거 참조 표현이 없어 게이트에
# 막히고, 게이트를 통과해도 사실은 애초에 주입 대상이 아니었다.
# 사실은 **검색할 것이 아니라 항상 있어야 하는 것**이다 (docs/06 P4 결정적 주입).
INJECT_KNOWN_FACTS = True


def ntok(t: str) -> int:
    """한국어 ≈ 1.5토큰/글자 (docs/05 §2)"""
    return max(1, int(len(t) * 1.5))


# 한국어 어미 정규화 — 형태소 분석기(nori) 없이 쓰는 최소 대용
# 프로토타입에서 "아팠던" vs "아파서"가 매칭 안 돼 정답이 탈락한 뒤 추가됨.
# docs/03 FP-4가 말한 교착어 문제가 구현에서 그대로 재현됐다.
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
    SCHEMA_VERSION = 3
    #  1: 최초
    #  2: fact에 카디널리티·가변성·상시성 반영 (13 발견 4·8)
    #  3: event.dedup_key + derivation/stale (16 §3·§4)
    MIGRATIONS = {
        2: ["ALTER TABLE event ADD COLUMN mention_count INTEGER DEFAULT 1"],
        3: ["ALTER TABLE event ADD COLUMN dedup_key TEXT"],
    }

    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self._migrate()

    def _migrate(self):
        """
        스키마 버전을 맞춘다 (docs/16 §7).

        SQLite는 ALTER가 제한적이라 실제 서비스라면 도구를 쓴다.
        여기서 보이려는 건 **절차**다:
          · 버전을 데이터에 적어둔다 (코드가 아니라)
          · 올라갈 때만 적용한다. 내려가는 마이그레이션은 안 만든다
          · **실패하면 멈춘다.** 반쯤 마이그레이션된 상태가 최악이다
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

    def apply_meta(self, chat_id, seq, meta: dict):
        """
        응답과 함께 온 구조화 출력을 반영 (docs/adr/ADR-004 동기 층).
        추가 LLM 호출 없이 상태를 갱신하는 경로.
        """
        if d := meta.get("state_delta"):
            cols = ", ".join(f"{k}=?" for k in d)
            self.db.execute(
                f"UPDATE relationship SET {cols}, updated_by_turn=? WHERE chat_id=?",
                (*d.values(), seq, chat_id))
            self._prov(chat_id, seq, "state_delta", json.dumps(d, ensure_ascii=False),
                       "동기 구조화 출력")
        if s := meta.get("scene_delta"):
            cols = ", ".join(f"{k}=?" for k in s)
            self.db.execute(
                f"UPDATE scene SET {cols}, updated_by_turn=? WHERE chat_id=?",
                (*s.values(), seq, chat_id))
        for eid in meta.get("used_memories", []):
            kind, _, rid = eid.partition(":")
            if kind == "event":
                self.db.execute(
                    "UPDATE event SET surfaced_count=surfaced_count+1 WHERE event_id=?",
                    (rid,))
        if nd := meta.get("new_debt"):
            self.db.execute(
                "INSERT INTO debt (chat_id, content, setup_turn_seq, trigger_kind,"
                " trigger_spec, trigger_clock, emotional_stake) VALUES (?,?,?,?,?,?,?)",
                (chat_id, nd["content"], seq, nd.get("trigger_kind", "session_start"),
                 nd.get("trigger_spec"), nd.get("trigger_clock", "session"),
                 nd.get("stake", 0.5)))
        self.db.commit()

    # ── L6 사건 중복 제거 (docs/16 §3) ──────────────────────────────
    #
    # 사실은 카디널리티로 중복을 막지만 **사건에는 방어가 없었다.**
    # 같은 사건이 여러 턴에 걸쳐 언급되면 각각 저장된다.
    # 장기 지평에서 이건 후보 증가 = 정밀도 저하로 직결된다
    # (experiments/longhorizon_sim.py §3).
    #
    # 완벽한 중복 판정은 불가능하다(다른 표현의 같은 사건). 그래서 목표를 낮춘다:
    # **연속 구간의 반복 언급만 잡는다.** 그게 대부분이고 값싸다.
    DEDUP_WINDOW = 20          # 이 턴 수 안의 같은 내용은 같은 사건 후보
    DEDUP_JACCARD = 0.6        # 어근 집합 겹침이 이 이상이면 같은 사건으로 본다

    # 🔴 처음엔 **어근 집합의 정확 일치**를 키로 썼다. 어순은 흡수했지만
    #    낱말 하나만 빠져도 못 잡았다 —
    #      "나비가 갑자기 아파서 응급실에 갔다"
    #      "나비가 아파서 응급실 갔다"           <- '갑자기' 하나 차이로 별개 저장
    #    실제 반복 언급이 똑같은 문구일 리 없으니 정확 일치는 쓸모가 없다.
    #    -> 시점 버킷으로 **후보를 좁히고**, 어근 집합의 겹침(Jaccard)으로 판정한다.
    #
    #    [13 발견 5](../docs/13-prototype.md)에서 해석 클러스터링이 어휘 유사도로
    #    실패했던 것과 같은 문제인데, 여기서는 **시점 버킷이 후보를 좁혀줘서**
    #    훨씬 쉽다. 20턴 안의 같은 어근 뭉치는 대개 같은 사건이다.

    # 🔴 교착어 문제가 **세 번째로** 물었다.
    #      ① 검색:   아팠던 != 아파서        (13 발견 1)
    #      ② 채점:   민감하다 != 민감해서     (실험 13)
    #      ③ 중복제거: 응급실에 != 응급실     <- 지금
    #    _stem은 **어미(용언)**만 벗긴다. 조사(체언)는 모른다.
    #    매번 그 자리에서 땜질하고 있다는 뜻이고, **형태소 분석기를 인프라로
    #    두는 것이 옳다**는 근거가 하나 더 늘었다. 여기서는 조사 목록으로 때운다.
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
        """사건 추가. 같은 시점 구간에 충분히 겹치는 사건이 있으면 **강화**한다."""
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
        return "created", cur.lastrowid

    # ── L5 사실 무효화 (bi-temporal) ────────────────────────────────
    #
    # 스키마에 superseded_by를 넣어놓고 **탐지 로직은 없었다.**
    # 구현하려니 문서에 없는 결정 세 개가 필요했다:
    #   ① 술어의 카디널리티 — 직업은 하나, 친구는 여럿. 스키마에 없었다
    #   ② 충돌 시 누가 이기나 — 최신? 신뢰도? 언급 횟수?
    #   ③ 유저가 틀리게 말하면(U10) 그것도 사실이 되나
    PREDICATE_CARDINALITY = {           # ① 문서에 없던 것 — 여기서 처음 정의
        "직업": "one", "거주지": "one", "반려동물_이름": "one",
        "신체_특성": "many", "가족": "many", "선호": "many",
        "지인_반려동물": "many", "일상_사소": "many",
    }
    # ② 첫 규칙("기존보다 margin만큼 더 확신해야 덮는다")은 실행하자마자 깨졌다:
    #    기존 confidence가 0.9면 0.9+0.15=1.05 > 1.0이라 **정당한 갱신도 영원히 보류**된다.
    #    → 규칙을 뒤집는다. "더 확신해야 덮는다"가 아니라 "덜 확신하면 못 덮는다".
    CONFIDENCE_FLOOR = 0.6              # 다중값 술어에 새 값을 추가할 최소 확신

    # ④ 두 번째 규칙도 깨졌다. 재확인이 confidence를 올리니 **정당한 이직 갱신이 막혔다.**
    #    강화가 무한하면 사실이 화석화된다.
    #
    #    근본 원인: "갱신"과 "모순"을 구별할 축이 없었다.
    #      이직  = 세상이 변한 것       → 허용해야 한다
    #      오빠  = 유저가 잘못 안 것     → 막아야 한다
    #    둘 다 "기존과 다른 값"이라 confidence만으로는 구별 불가능하다.
    #
    #    → 술어에 **가변성(mutability)**이 필요하다. 스키마에 없던 네 번째 필드.
    PREDICATE_MUTABILITY = {
        "직업": "high", "거주지": "high", "일상_사소": "high",
        "선호": "mid", "신체_특성": "low",
        "가족": "low", "반려동물_이름": "low", "지인_반려동물": "low",
    }
    _MUT_TOLERANCE = {"high": 0.25, "mid": 0.10, "low": -0.05}

    # ⑤ 다섯 번째로 필요해진 축 — 상시성(standing).
    #
    # [알고 있는 것]을 구현하자마자 트랩(크로와상, importance 0.05)이
    # 평범한 턴에도 항상 들어갔다. 검색 경로에는 하드 게이트 τ가 있는데
    # **결정적 주입 경로에는 채택 기준이 아예 없었다.**
    #
    # importance로 거르면 될 것 같지만 틀렸다. importance는 "이 기억이
    # 중요한가"를 재는데, 여기서 필요한 건 "이게 캐릭터가 **항상** 알고
    # 있어야 하는 종류인가"다. 둘은 다르다 —
    #   "지우가 어제 발목을 삐었다"  importance 높음 · 상시 아님 (곧 낫는다)
    #   "지우는 카페인에 민감하다"    importance 중간 · 상시  (체질이다)
    #
    # 사건은 검색으로 꺼내고, 체질·이름·직업 같은 **속성**만 상시 주입한다.
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

        card = self.PREDICATE_CARDINALITY.get(predicate, "many")

        # 다중값 술어 → 병존. 단 확신이 낮으면 병존도 막는다.
        # ③ 첫 구현은 다중값이면 무조건 병존시켰다. 그래서 "오빠 1명"(confidence 0.4,
        #    실제로 없음)이 그냥 들어갔다 — 카디널리티 방어가 단일값만 지킨다.
        if card == "many" or not cur:
            if cur and confidence < self.CONFIDENCE_FLOOR:
                self._prov(chat_id, seq, "fact_held", f"{predicate}={obj}",
                           f"다중값이지만 확신 {confidence:.2f} < floor")
                self.db.commit()
                return "held", f"보류 — 확신 {confidence:.2f}이 낮다. 확인 필요"
            self.db.execute(
                "INSERT OR IGNORE INTO fact (chat_id, subject, predicate, object,"
                " realm, valid_from, source_turn_seq, importance, confidence)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (chat_id, subject, predicate, obj, realm, time.time(), seq,
                 importance, confidence))
            self.db.commit()
            return ("coexist" if cur else "created",
                    f"{card} 술어 — {'병존' if cur else '신규'}")

        # 단일값 술어 + 값이 다름 → 충돌
        old = cur[0]
        # ③ **덜 확신하는 진술은 더 확신하는 사실을 못 덮는다.** U10 방어선.
        #    첫 구현은 mention>=2를 요구해서, 1회만 언급된 참인 사실이
        #    confidence 0.5짜리 거짓 진술에 무방비였다.
        mut = self.PREDICATE_MUTABILITY.get(predicate, "mid")
        tol = self._MUT_TOLERANCE[mut]
        if confidence < old["confidence"] - tol:
            self._prov(chat_id, seq, "fact_held", f"{predicate}={obj}",
                       f"{mut} 가변성, 확신 {confidence:.2f} < "
                       f"{old['confidence'] - tol:.2f}")
            self.db.commit()
            return "held", (f"보류 — {mut} 가변성 술어. 확신 {confidence:.2f} < "
                            f"기준 {old['confidence'] - tol:.2f}. 확인 필요")

        now = time.time()
        self.db.execute("UPDATE fact SET valid_until=? WHERE fact_id=?",
                        (now, old["fact_id"]))
        cursor = self.db.execute(
            "INSERT INTO fact (chat_id, subject, predicate, object, realm,"
            " valid_from, source_turn_seq, importance, confidence)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (chat_id, subject, predicate, obj, realm, now, seq, importance,
             confidence))
        self.db.execute("UPDATE fact SET superseded_by=? WHERE fact_id=?",
                        (cursor.lastrowid, old["fact_id"]))
        # 🔴 [사건 계수 실험](../experiments/event_metrics.py)에서 잡힌 누수.
        #
        # fact 행은 valid_until·superseded_by로 정상 무효화되는데,
        # **검색용 색인 복사본(event)은 그대로 남아 계속 검색됐다.**
        # 436턴 재생에서 **23턴에 이직 전 직장이 주입**됐다.
        #
        # docs/16 §4의 삭제 전파와 **같은 문제**인데, 그때는 '삭제'만 다루고
        # **'갱신'은 빠뜨렸다.** 원본이 바뀌면 파생물도 따라가야 한다 —
        # 지우든 바꾸든 마찬가지다.
        n = self._invalidate_derived(chat_id, "fact", old["fact_id"])
        self._prov(chat_id, seq, "fact_superseded",
                   f"{predicate}: {old['object']} → {obj}",
                   f"단일값 술어 충돌 · 파생 색인 {n}건 무효화")
        self.db.commit()
        return "superseded", f"'{old['object']}' → '{obj}' 무효화"

    # ── 삭제와 그 전파 (docs/16 §4) ─────────────────────────────────
    def record_derivation(self, chat_id, derived_kind, derived_key, sources):
        """파생물이 어떤 원본에서 나왔는지 기록한다. 요약·해석 생성 시 호출."""
        self.db.executemany(
            "INSERT INTO derivation VALUES (?,?,?,?,?)",
            [(chat_id, derived_kind, derived_key, k, str(i)) for k, i in sources])
        self.db.commit()

    def delete_item(self, chat_id, kind, item_id):
        """
        유저가 기억 하나를 지운다. **파생물까지 따라간다.**

        반환: 함께 무효화된 파생물 목록.

        원칙: 파생물을 즉시 다시 쓸 수는 없다(LLM이 필요하다).
              그래서 **stale로 표시하고 그때까지 주입에서 제외**한다.
              재생성 전에 계속 쓰면 지운 정보가 계속 노출된다 —
              안전한 기본값은 '빼는 것'이다.
        """
        table = {"fact": "fact", "event": "event"}[kind]
        col = {"fact": "fact_id", "event": "event_id"}[kind]
        self.db.execute(f"UPDATE {table} SET user_deleted=1 WHERE {col}=?",
                        (item_id,))
        rows = self.db.execute(
            "SELECT derived_kind, derived_key FROM derivation"
            " WHERE chat_id=? AND source_kind=? AND source_id=?",
            (chat_id, kind, str(item_id))).fetchall()
        hit = []
        for r in rows:
            self.db.execute(
                "INSERT OR REPLACE INTO stale VALUES (?,?,?,?,?)",
                (chat_id, r["derived_kind"], r["derived_key"],
                 f"{kind}:{item_id} 삭제됨", time.time()))
            hit.append((r["derived_kind"], r["derived_key"]))
        self._prov(chat_id, 0, "delete",
                   f"{kind}:{item_id}", f"파생물 {len(hit)}건 무효화")
        self.db.commit()
        return hit

    def _invalidate_derived(self, chat_id, source_kind, source_id):
        """
        원본이 바뀌거나 지워졌을 때 **파생물을 따라간다.**

        요약처럼 재생성이 필요한 것은 stale로 표시하고,
        색인 복사본(event)처럼 **그냥 빼면 되는 것은 즉시 제외**한다.
        """
        rows = self.db.execute(
            "SELECT derived_kind, derived_key FROM derivation"
            " WHERE chat_id=? AND source_kind=? AND source_id=?",
            (chat_id, source_kind, str(source_id))).fetchall()
        n = 0
        for r in rows:
            if r["derived_kind"] == "event":
                self.db.execute("UPDATE event SET user_deleted=1 WHERE event_id=?",
                                (r["derived_key"],))
            else:
                self.db.execute(
                    "INSERT OR REPLACE INTO stale VALUES (?,?,?,?,?)",
                    (chat_id, r["derived_kind"], r["derived_key"],
                     f"{source_kind}:{source_id} 무효화됨", time.time()))
            n += 1
        return n

    def is_stale(self, chat_id, derived_kind, derived_key):
        return self.db.execute(
            "SELECT 1 FROM stale WHERE chat_id=? AND derived_kind=? AND derived_key=?",
            (chat_id, derived_kind, derived_key)).fetchone() is not None

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
    def gate(self, utterance: str) -> tuple[bool, str]:
        """
        검색이 필요한 턴인가 (docs/adr/ADR-006). 룰 기반, ~0ms.

        🔄 [gate_sweep.py](gate_sweep.py) 4부에서 조합 탐색으로 교체했다.
        원래는 "과거 참조 표현(기억/그때/저번…)이 있는가"만 봤는데,
        *"나 이직 준비하고 면접 몇 번 봤더라"* 같은 **자연스러운 질문에는
        그 표현이 없다.** 그런데 `면접`은 저장돼 있다.

        → 신호를 **질문의 형태**가 아니라 **저장소와의 접점**에서 찾는다.
          무엇이 저장돼 있는지는 우리가 이미 알고 있으니 공짜에 가깝다.

        θ=0.05와 **함께** 바꿔야 효과가 난다 (게이트와 θ는 직렬이라
        하나만 열면 다른 하나가 막는다 — gate_sweep 3부의 상호작용).
        """
        if re.search(r"(기억|그때|저번|예전|아까|전에|했잖아|말했|뭐였|언제)", utterance):
            return True, "과거 참조 표현"
        if len(utterance) < 8:
            return False, "너무 짧음 — 신호 없음"
        if re.search(r"^(응|ㅇㅇ|ㅋ+|어|그래|넵|왜|뭐)$", utterance.strip()):
            return False, "의례적 발화"
        if any(w[:2] in self._recall_vocab for w in re.findall(r"[가-힣]{2,}", utterance)):
            return True, "저장된 내용어와 접점"
        return False, "과거 참조 신호도 내용어 접점도 없음"

    @property
    def _recall_vocab(self):
        """저장된 사건 요약의 앞 2글자 집합. 쓰기 때 갱신되므로 캐시하지 않는다."""
        v = set()
        for r in self.db.execute("SELECT summary FROM event WHERE user_deleted=0"):
            for w in re.findall(r"[가-힣]{2,}", r["summary"]):
                v.add(w[:2])
        return v

    def retrieve(self, chat_id, query, now_seq):
        """하드 게이트 → 가중 정렬 → 임계 컷 (docs/adr/ADR-005 4단계)."""
        rows = self.db.execute(
            "SELECT event_id, summary, importance, emotional_weight, surfaced_count"
            " FROM event WHERE chat_id=? AND user_deleted=0", (chat_id,)).fetchall()
        if not rows:
            return [], []
        q = set(bigrams(query))
        scored, rejected = [], []
        for r in rows:
            imp = max(r["importance"] or 0, r["emotional_weight"] or 0)
            if imp < TAU_IMPORTANCE:                       # 2단계 하드 게이트
                rejected.append((r["summary"], f"importance {imp:.2f} < τ"))
                continue
            d = set(bigrams(r["summary"]))
            rel = len(q & d) / max(len(q), 1)
            if rel < THETA_RELEVANCE:                      # 4단계 임계 컷
                rejected.append((r["summary"], f"relevance {rel:.2f} < θ"))
                continue
            s = 0.6 * rel + 0.4 * imp - SURFACED_PENALTY * (r["surfaced_count"] or 0)
            scored.append((s, r))
        scored.sort(key=lambda x: -x[0])
        return scored[:TOP_K], rejected

    def due_debts(self, chat_id, now_seq, session_start=False):
        """트리거 충족 + 백오프 (docs/06 L9 — 실측으로 추가된 정책)."""
        out = []
        for r in self.db.execute(
                "SELECT * FROM debt WHERE chat_id=? AND status='open'",
                (chat_id,)).fetchall():
            backoff = [1, 3, 7][min(r["attempt_count"], 2)]
            last = r["last_attempted_seq"] or r["setup_turn_seq"]
            if now_seq - last < backoff * WINDOW_TURNS:
                continue
            if r["trigger_kind"] == "session_start" and not session_start:
                continue
            if r["attempt_count"] >= 3:
                self.db.execute("UPDATE debt SET status='expired' WHERE debt_id=?",
                                (r["debt_id"],))
                continue
            out.append(r)
        return out

    # ── 계층별 실패 정책 (docs/16 §6) ───────────────────────────────
    #
    # 읽기 경로는 DB를 6번 조회한다. **하나가 실패하면 응답 전체가 실패하는가?**
    # 설계에 이 답이 없었다. 계층마다 답이 다르다:
    #
    #   L0 최근 턴   없으면 대화가 아니다                    -> 중단
    #   L2 관계      없으면 상태 위반이 확실하다 (연인인데 남처럼)  -> 중단
    #   L4 요약      품질 저하로 그친다                      -> 생략
    #   L5 사실      🔴 없는 걸 아는 척하면 환각               -> 생략 + **명시**
    #   L6 사건      검색 실패는 원래 흔하다                   -> 생략
    #   L9 부채      다음 턴에 다시 시도                      -> 생략
    #
    # 핵심은 **사실 계층 실패만 "조용한 환각"을 만든다**는 것이다.
    # 검색이 실패하면 아무것도 안 나오지만, 사실이 없으면 모델이 **지어낸다**
    # (docs/11 실험 13의 A0가 그 증거 — 없는 강아지·없는 형·공항 사건).
    # 그래서 사실 계층만은 **실패를 컨텍스트에 알린다.**
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

        # [알고 있는 것] — 항상 주입. 검색 대상이 아니다 (docs/15 §2).
        # 사실은 관계 상태보다 덜 변하므로 앞(volatility 2.5)에 둔다.
        if INJECT_KNOWN_FACTS:
            known = self._safe("fact", lambda: [
                f for f in self.facts_at(chat_id)
                if f["predicate"] in self.PREDICATE_STANDING], default=None)
            if known is None:
                # 🔴 사실 계층 실패는 **조용히 넘어가면 안 된다.**
                # 없으면 모델이 지어낸다. 모른다는 것을 알려야 한다.
                ctx.blocks.append(Block(
                    "알고 있는 것",
                    "(기억을 불러오지 못했다. 아는 척하지 말고 모른다고 말할 것)",
                    "chat", 2.5))
                ctx.provenance.append(
                    ("degraded", "fact", "조회 실패 — 회피 모드로 알림"))
            elif known:
                ctx.blocks.append(Block("알고 있는 것", "\n".join(
                    f"· 지우의 {f['predicate']}: {f['object']}" for f in known),
                    "chat", 2.5))
                ctx.provenance.append(
                    ("known_facts", f"{len(known)}건", "결정적 주입 — 검색 안 함"))

            else:
                # 🔴 콜드 스타트 (docs/16 §5, 실험 17).
                #
                # 전에는 사실이 없으면 **블록을 통째로 생략**했다. 그 상태의
                # 첫 세션 환각률이 **83%**였다 — "비 쏟아지던 날 우산 같이
                # 썼던 날이잖아" 같은 없는 과거를 지어낸다.
                #
                # 블록 생략과 "(아직 없음)" 명시는 **다르다.** 명시하면 58%,
                # 첫 대화임까지 알리면 33%, 되묻기 지시까지 더하면 17%다.
                # **비어 있음조차 알려줘야 모델이 그걸 근거로 쓴다** —
                # 실험 13의 "모른다고 말하려면 무엇을 아는지를 알아야 한다"가
                # 빈 기억에도 적용된다.
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
        # 🔄 stage_note(자유 텍스트)를 **결정적 주입에서 뺐다** (docs/16 §2.5 결정 1).
        #
        # 근거가 둘인데, 뜻밖에도 **두 번째가 더 강하다.**
        #
        #  ① 보안: 자유 텍스트 × 매 턴 주입 = 최대 공격 표면.
        #     "무엇이든 들어준다"는 12자면 되고 40자 한도 안에 들어간다.
        #     ⚠️ 다만 [실험 16](../experiments/injection_probe.py)에서 공격이 0/45였다.
        #        이 근거만으로는 약하다.
        #
        #  ② 캐시: [실험 18](../experiments/event_metrics.py)에서 결정적 주입 블록이
        #     436턴 내내 **한 가지 모양**임이 확인됐다. 접두사가 안 깨진다.
        #     stage_note는 대화에 따라 바뀌므로 **넣는 순간 그 성질이 사라진다.**
        #     [ADR-007](../docs/adr/ADR-007-context-packing-cache.md)의 배치 원칙에 정면으로 어긋난다.
        #
        # 대가: [06 L2](../docs/06-data-model.md)에서 "enum에 안 담기는 관계 유형"을
        #       담으려던 필드였다. 뉘앙스를 잃는다. UI 표시·모순 검사용으로는 남긴다.
        ctx.blocks.append(Block("relationship",
            f"단계={rel['stage']} 호감도={rel['affinity']} 호칭={rel['called_as']}",
            "chat", 3))
        ctx.provenance.append(("relationship", rel["stage"], "결정적 주입"))
        if rel["stage_note"]:
            ctx.provenance.append(
                ("excluded", f"stage_note: {rel['stage_note']}",
                 "자유 텍스트 — 결정적 주입 제외 (캐시 안정 + 공격 표면)"))

        for d in self.db.execute("SELECT * FROM digest WHERE chat_id=?",
                                 (chat_id,)).fetchall():
            # 삭제된 근거를 담은 요약은 재생성 전까지 **주입하지 않는다** (docs/16 §4)
            if self.is_stale(chat_id, "digest", d["kind"]):
                ctx.provenance.append(
                    ("stale", f"digest:{d['kind']}", "삭제된 근거 포함 — 재생성 대기"))
                continue
            ctx.blocks.append(Block(f"digest:{d['kind']}", d["content"], "chat",
                                    4 if d["kind"] == "lifetime" else 5))

        # 부채는 "결정적 주입"이지만 **존재 자체가 조건부**다.
        # 앞쪽에 두면 나타났다 사라질 때마다 접두사가 깨진다 (프로토타입에서 발견).
        # → 결정적 주입 ≠ 앞쪽 배치. 뒤쪽에 둔다 (lost-in-the-middle상 끝도 고주목 위치).
        debts = self.due_debts(chat_id, now_seq, session_start)
        if debts:
            ctx.blocks.append(Block("debt", "\n".join(
                f"- {d['content']}" for d in debts), "chat", 8.5))
            for d in debts:
                ctx.provenance.append(("debt", d["content"], "트리거 충족 — 결정적 주입"))
                self.db.execute(
                    "UPDATE debt SET last_attempted_seq=?, attempt_count=attempt_count+1"
                    " WHERE debt_id=?", (now_seq, d["debt_id"]))

        sc = self.db.execute("SELECT * FROM scene WHERE chat_id=?", (chat_id,)).fetchone()
        if sc:
            ctx.blocks.append(Block("scene",
                f"장소={sc['place']} 참여자={sc['present']} 상황={sc['situation']}",
                "chat", 7))

        # 최근 턴 — 청크 축출 (실험 1: 1턴씩 밀면 캐시 전멸)
        anchor = (now_seq // WINDOW_CHUNK) * WINDOW_CHUNK
        recent = self.db.execute(
            "SELECT role, text FROM turn WHERE chat_id=? AND seq>? AND seq<?"
            " ORDER BY seq", (chat_id, anchor - WINDOW_TURNS, now_seq)).fetchall()
        if recent:
            ctx.blocks.append(Block("recent", "\n".join(
                f"{r['role']}: {r['text']}" for r in recent), "chat", 8))

        # 검색 — 게이팅 통과 시에만. 맨 뒤 (변경 빈도 최대)
        need, why = self.gate(utterance)
        ctx.provenance.append(("gate", "통과" if need else "차단", why))
        if need:
            hits, rejected = self.retrieve(chat_id, utterance, now_seq)
            for _, r in hits:
                self.db.execute(
                    "UPDATE event SET retrieval_count=retrieval_count+1"
                    " WHERE event_id=?", (r["event_id"],))
            if hits:
                ctx.blocks.append(Block("retrieved", "\n".join(
                    f"[기억] {r['summary']}" for _, r in hits), "chat", 9))
            for s, r in hits:
                ctx.provenance.append(("retrieved", r["summary"], f"score {s:.2f}"))
            for summ, reason in rejected:
                ctx.provenance.append(("rejected", summ, reason))

        ctx.blocks.append(Block("utterance", utterance, "chat", 10))
        ctx.blocks.sort(key=lambda b: b.volatility)
        self.db.commit()
        return ctx
