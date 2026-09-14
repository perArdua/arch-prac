# -*- coding: utf-8 -*-
"""
summarize.py — 요약 생성 경로: 세션 요약과 lifetime 재작성 (ADR-013 P4).

  session_digest(m, chat_id, sid)   그 세션의 원본 턴 → 세션 요약 한 건
  rewrite_lifetime(m, chat_id)      세션 요약만 → lifetime 요약
  regenerate_stale(m, chat_id)      stale 표시된 요약을 세션 → lifetime 순으로 다시 만든다

지키는 것:
  · `rewrite_lifetime`은 원본 턴을 읽지 않는다 — 읽으면 사슬 깊이가 2로 유계라는 P4가 깨진다.
    원본 턴에 닿는 헬퍼(`_turns`)를 부르지 않고, `_P4_FORBIDDEN_TABLES`로 시험이 감시한다.
  · lifetime 프롬프트에 «사실 우선» 지시를 넣지 않는다 — 구체적 사실은 사실 계층의 몫이고(docs/14 P4),
    실험 19의 우위는 재채점에서 사라졌다.
  · 토큰 단위를 섞지 않는다 — 추정 `ntok`(이 코퍼스에서 약 2.07배 과대계상)을 `num_ctx`로 나눈 백분율은 만들지 않는다.
  · ollama는 `num_ctx`를 넘는 프롬프트를 말없이 자른다(HTTP 200 · 예외 없음) — `_truncation_warning`이
    경고를 남긴다. 막지는 않는다.
  · 생성이 멈추면 재시도를 세어 찍고, 소진되면 예외를 올린다(빈 요약으로 삼키지 않는다).
  · 이 파일은 요약의 품질에 대한 수를 만들지 않는다 — 찍는 수는 토큰 회계와 건수뿐이다.
"""

import json
import os
import time

import llm
import memory
from memory import session_kind

# ── 상수 ────────────────────────────────────────────────────────────────

# 생성기 버전 — `digest_meta.generator_version`에 적힌다. 프롬프트를 고치면 올린다
# (옛 규칙과 새 규칙으로 만든 요약이 한 열에 섞이지 않게).
GENERATOR_VERSION = "P4/2026-09-10"

# lifetime 프롬프트의 `<N>토큰 이내` 자리. 측정된 값이 아니다 — docs/14 P4는 `<N>`을 비워 두었고
# 이 값을 튜닝할 품질 측정이 없다. 이름을 주고 한 곳에 둘 뿐이다.
LIFETIME_BUDGET_TOKENS = 400

# 재시도 횟수와 그동안 센 정지 횟수. 정지는 «예외 없이 오래 매달리는 것»이라
# 여기서는 `LLMError`(타임아웃 포함)로만 관측된다.
GEN_RETRIES = 3
GEN_RETRY_SLEEP = 3.0
STALL_COUNT = 0          # 프로세스 누적. 보고에 적는 수다

# 한 번의 생성에 허용하는 초. `None`이면 `llm.LLM_TIMEOUT`(600초) 그대로다.
# 재시도가 의미를 가지려면 첫 시도가 끝나야 한다(600초 × 3 = 30분) — 호출부(시험)가 줄일 수 있게 둔다.
GEN_TIMEOUT = None

# 생성 캐시 경로. 기본 `None` = 캐시 없음. 프로덕션에서 요약 캐시는 결함이다(재료가 바뀌었는데 옛 요약을
# 돌려준다) — 크래시가 앞의 생성을 잃지 않게 하는 시험·실험용 장치이고, 쓰는 쪽이 명시적으로 켠다.
CACHE_PATH = None

# ── docs/14-extraction-prompts.md 의 P4 절 ──────────────────────────────
# 한 글자도 고치지 않고 옮긴다(ADR-013의 선택지 P1~P4와 비교할 근거다). 문서와 다른 곳은 둘뿐이고
# 대조 시험(`test_template_is_byte_identical_to_doc14`)이 그 둘만 정규화한다:
#   ① `<N>` → `{budget}` — 문서가 비워 둔 자리
#   ② 마지막 줄의 `     ← 실험 19에서 추가` — 문서의 편집 이력이지 모델에게 주는 지시가 아니다
DOC14_ANNOTATION = "     ← 실험 19에서 추가"
# 문서의 «아래 대화 전체»는 실제 재료(세션 요약)와 어긋나지만 문구를 고치지 않는다 — 고치면
# «docs/14 그대로»가 거짓이 된다. 재료가 무엇인지는 `_LIFETIME_MATERIAL_HEADER`가 프롬프트 안에서 말한다.
P4_TEMPLATE = """아래 대화 전체를 다시 요약하라. 이전 요약은 참고하되 그대로 잇지 마라.

형식 (이 구조를 벗어나지 마라)
## 타임라인
- <시기>: <무슨 일>
## 관계 변화
- <시점>: <어떻게 변했나>

규칙
· {budget}토큰 이내
· **감정선과 디테일을 살려라.** 사건 나열이 아니다
· 유저가 직접 수정한 부분(<표시>)은 문장 그대로 보존한다
· 마지막에 다음 세션 첫 턴에 쓸 소재 한 줄: `## 다음에`
· 구체적 사실(이름·직업·체질·가족)은 **여기서 다루지 않는다.** 사실 계층이 담당한다.
  요약은 **언제 무엇이 있었고 관계가 어떻게 변했는지**만 쓴다"""

_LIFETIME_MATERIAL_HEADER = "[재료 — 세션 요약 {k}건]"

# 세션 요약 지시. `experiments/summary_local.py`의 `SESSION_TOK`과 같은 문자열이다 — N=24를 유도할 때 쓴
# «세션 요약 1개 ≈ 108토큰»이 이 지시로 만든 값이라, 바꾸면 그 유도가 근거를 잃는다.
# 세션 층은 사실을 금지하지 않는다(사실 계층으로 가는 재료다). 사실 금지는 lifetime 층에만 있다.
SESSION_TEMPLATE = ("이번 세션 요약을 3문장 이내로 써라. "
                    "사실·사건·관계 변화만 남기고 잡담은 버려라.")

_SESSION_MATERIAL_HEADER = "[대화 — 세션 {sid} · 턴 {a}–{b}]"

# P4가 금지하는 테이블 — `rewrite_lifetime`의 재료 경로가 여기에 닿으면 P4가 깨진 것이다(시험이 감시한다).
_P4_FORBIDDEN_TABLES = ("turn",)

# ── 절단 감지 상수 ──────────────────────────────────────────────────────
# `ntok`을 실측 토큰으로 되돌리는 나눗셈. 이 코퍼스의 실측이다 — 세션 요약 12개가 0.7232 tok/글자라 `ntok`(글자 × 1.5)이
# 1.5/0.7232 = 2.074배 과대계상한다. 두 길이 회귀의 기울기 0.7189 tok/글자로 환산한 1.5/0.7189 = 2.087도 같은 값을 가리킨다.
# 모델이나 ollama 버전이 바뀌면 다시 잰다.
NTOK_OVERCOUNT = 2.07

# 실측이 추정의 이 비율 미만이면 «크게 못 미친다»로 본다.
TRUNC_SHORTFALL = 0.75

# 그리고 실측이 `num_ctx`의 이 비율 이상일 때만 경고한다 — 짧은 프롬프트는 추정이 크게 빗나가도
# 잘릴 수가 없으므로 이 조건이 오발화를 막는다. 잘린 호출은 창을 채웠으므로 반드시 이 조건을 만족한다.
TRUNC_NEAR_CAP = 0.4


# ── 생성 (재시도 · 정지 계수 · 캐시) ────────────────────────────────────

def _cache_load():
    if not CACHE_PATH:
        return {}
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _cache_store(tag, value):
    if not CACHE_PATH:
        return
    data = _cache_load()
    data[tag] = value
    tmp = CACHE_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CACHE_PATH)   # 크래시가 반쯤 쓴 캐시를 남기지 않게
    except OSError:
        pass                          # 캐시를 못 써도 생성 자체를 막을 이유는 없다


def _generate(prompt, tag=None):
    """
    `llm.generate` + 재시도 + 정지 계수 + (선택) 캐시.

    반환: `(text, usage)` — `usage`는 `llm.last_usage()`의 사본이고, 캐시 적중이면 `None`이다
    (그 호출에서 잰 값이 아니므로 없다고 말한다). 소진되면 예외를 올린다 — 빈 문자열을 돌려주면
    «요약이 비었다»와 «요약을 못 만들었다»가 구별되지 않는다.
    """
    global STALL_COUNT

    if tag is not None:
        hit = _cache_load().get(tag)
        if hit:
            print(f"    ↩ 캐시 적중 [{tag}] — 이 호출은 ollama를 안 불렀다"
                  " (사용량 없음)")
            return hit, None

    saved = llm.LLM_TIMEOUT
    if GEN_TIMEOUT is not None:
        llm.LLM_TIMEOUT = GEN_TIMEOUT
    try:
        last = None
        for attempt in range(1, GEN_RETRIES + 1):
            t0 = time.perf_counter()
            try:
                out = llm.generate(prompt)
            except llm.LLMError as e:                       # noqa: PERF203
                STALL_COUNT += 1
                last = e
                dt = time.perf_counter() - t0
                print(f"    ⚠️ 생성 정지/실패 {attempt}/{GEN_RETRIES}"
                      f" ({dt:.1f}s) — 누적 정지 {STALL_COUNT}회: {e}")
                if attempt < GEN_RETRIES:
                    time.sleep(GEN_RETRY_SLEEP)
                continue
            usage = llm.last_usage()
            if tag is not None:
                _cache_store(tag, out)
            return out, usage
    finally:
        llm.LLM_TIMEOUT = saved

    # 삼키지 않는다 — 여기까지 왔다면 `GEN_RETRIES`번 다 실패했다.
    raise llm.LLMError(
        f"{GEN_RETRIES}회 재시도가 전부 실패했다 (누적 정지 {STALL_COUNT}회)."
        f" 마지막 사유: {last}")


# ── 토큰 회계와 절단 경고 ─────────────────────────────────────────────────

def token_report(prompt, usage):
    """
    입력 토큰 세 값을 단위와 함께 한 줄로 만든다(순수 함수). 백분율은 실측 ÷ `num_ctx`(둘 다 tok)이고,
    추정 `ntok`은 나란히 적되 나눗셈에 넣지 않는다. 실측이 없으면 `?` — 추정으로 메우지 않는다.
    """
    est = memory.ntok(prompt)
    ctx = llm.LLM_NUM_CTX
    got = (usage or {}).get("prompt_eval_count")
    if got is None:
        return (f"입력 추정 {est} ntok · 실측 ? tok · num_ctx {ctx} tok"
                f" (실측이 없어 백분율 없음)")
    return (f"입력 추정 {est} ntok · 실측 {got} tok · num_ctx {ctx} tok"
            f" (실측 기준 {100.0 * got / ctx:.1f}%)")


def _truncation_warning(prompt, usage):
    """
    입력이 조용히 잘렸을 가능성을 문자열로 돌려준다. 아니면 `None`. 두 관측 조건의 논리곱이다:

      ① 실측이 추정에 크게 못 미친다 — `prompt_eval_count` < 추정 × `TRUNC_SHORTFALL`
         (추정 = `ntok / NTOK_OVERCOUNT`)
      ② 실측이 창의 상당 부분을 차지한다 — `prompt_eval_count` ≥ `num_ctx` × `TRUNC_NEAR_CAP`

    ②가 없으면 짧은 프롬프트(ASCII·마크다운은 글자당 토큰이 적다)에서 오발화한다.
    `num_ctx/2 + 2` 같은 버전 특이적 규칙에는 기대지 않는다.
    """
    got = (usage or {}).get("prompt_eval_count")
    if got is None:
        return None
    est_tok = memory.ntok(prompt) / NTOK_OVERCOUNT
    ctx = llm.LLM_NUM_CTX
    if got >= est_tok * TRUNC_SHORTFALL:
        return None
    if got < ctx * TRUNC_NEAR_CAP:
        return None
    return (f"입력이 잘렸을 가능성 — 실측 {got} tok이 추정 {est_tok:.0f} tok의"
            f" {100.0 * got / est_tok:.0f}%뿐이고, 그러면서 num_ctx {ctx} tok의"
            f" {100.0 * got / ctx:.0f}%를 차지한다. ollama는 창을 넘는 프롬프트를"
            f" 말없이 버린다 (HTTP 200 · 예외 없음). 이 요약은 재료의 일부만"
            f" 보고 만들어졌을 수 있다.")


# ── DB 접근 헬퍼 ────────────────────────────────────────────────────────

def _turns(m, chat_id, from_seq, to_seq, exclude=()):
    """
    원본 턴. `rewrite_lifetime`은 이 함수를 부르지 않는다(P4). `exclude`의 seq(지운 원본의 턴)는 뺀다.
    `_P4_FORBIDDEN_TABLES`가 여기서 여는 테이블 이름을 갖는다.
    """
    return m.db.execute(
        f"SELECT seq, role, text FROM {_P4_FORBIDDEN_TABLES[0]}"
        " WHERE chat_id=? AND seq BETWEEN ? AND ?" + _not_in(exclude) + " ORDER BY seq",
        (chat_id, from_seq, to_seq, *exclude)).fetchall()


def _session_sources(m, chat_id, from_seq, to_seq):
    """
    그 세션 구간에서 나온 `fact`/`event` id — `derivation`에 등록할 원본들. 지운 것(`user_deleted=1`)은
    다시 적지 않는다(적으면 같은 삭제가 또 stale을 민다). 사실은 `source_turn_seq`, 사건은
    `source_from_seq`로 턴을 가리키므로 두 번 묻는다.
    """
    src = [("fact", r["fact_id"]) for r in m.db.execute(
        "SELECT fact_id FROM fact WHERE chat_id=? AND user_deleted=0 AND source_turn_seq"
        " BETWEEN ? AND ? ORDER BY fact_id", (chat_id, from_seq, to_seq))]
    src += [("event", r["event_id"]) for r in m.db.execute(
        "SELECT event_id FROM event WHERE chat_id=? AND user_deleted=0 AND source_from_seq"
        " BETWEEN ? AND ? ORDER BY event_id", (chat_id, from_seq, to_seq))]
    return src


def _put_digest_meta(m, chat_id, kind, *, covers_from_seq, covers_to_seq):
    """
    `digest_meta` 한 행을 갱신하고 `stale_since_seq`를 지운다. `user_edited_at`은 건드리지 않는다
    (유저 편집을 존중하는 절차가 아직 없다 — 여기서 덮으면 그 미해결이 해결된 것처럼 보인다).
    """
    m.db.execute("INSERT OR IGNORE INTO digest_meta (chat_id, kind)"
                 " VALUES (?,?)", (chat_id, kind))
    m.db.execute(
        "UPDATE digest_meta SET generator_version=?, covers_from_seq=?,"
        " covers_to_seq=?, generated_at=?, stale_since_seq=NULL"
        " WHERE chat_id=? AND kind=?",
        (GENERATOR_VERSION, covers_from_seq, covers_to_seq, time.time(),
         chat_id, kind))


def _clear_stale(m, chat_id, kind):
    """재생성이 성공했을 때만 부른다. 실패하면 stale은 남는다."""
    m.db.execute(
        "DELETE FROM stale WHERE chat_id=? AND derived_kind='digest'"
        " AND derived_key=?", (chat_id, kind))


def _replace_derivation(m, chat_id, key, sources):
    """
    한 파생 키의 `derivation` 행을 통째로 갈아 끼운다. `record_derivation`은 더하기만 하므로, 그냥 부르면
    이미 재료에서 빠진 원본이 남아 그것이 지워질 때 이 요약이 다시 stale이 된다.
    """
    m.db.execute("DELETE FROM derivation WHERE chat_id=? AND derived_kind='digest'"
                 " AND derived_key=?", (chat_id, key))
    if sources:
        m.record_derivation(chat_id, "digest", key, sources)


# ── (1) 세션 요약 ───────────────────────────────────────────────────────

def session_digest(m, chat_id, session_id, *, from_seq=None, to_seq=None,
                   tag=None):
    """
    그 세션의 원본 턴에서 세션 요약 한 건을 만들어 `put_session_digest`로 저장하고 `derivation`을 등록한다.
    반환: `(kind, content, dropped)` — `dropped`는 N 상한에 밀려 지워진 키들이다.

    구간 기본값은 DB에서 유도한다(끝 = `turn`의 최대 seq, 시작 = 저장된 세션 요약의 최대 `covers_to_seq` + 1)
    — 세션을 순서대로 요약한다고 가정한다. 경계를 아는 호출부(`regen_job`)와 재생성은 구간을 직접 준다.
    지운 원본의 턴은 가린다.
    """
    kind = session_kind(session_id)
    if to_seq is None:
        r = m.db.execute("SELECT MAX(seq) AS s FROM turn WHERE chat_id=?",
                         (chat_id,)).fetchone()
        to_seq = (r["s"] if r and r["s"] is not None else 0)
    if from_seq is None:
        r = m.db.execute("SELECT MAX(covers_to_seq) AS s FROM digest_session"
                         " WHERE chat_id=?", (chat_id,)).fetchone()
        from_seq = (r["s"] + 1) if r and r["s"] is not None else 1

    rows = _masked_turns(m, chat_id, kind, from_seq, to_seq)   # 지운 원본의 턴은 뺀다
    if not rows:
        # 재료가 없는데 요약을 만드는 것이 이 계층의 가장 조용한 실패다 — 빈 요약을 저장하지 않고 터진다.
        raise ValueError(
            f"{kind}: 턴 {from_seq}–{to_seq} 구간에 원본 턴이 0건이다."
            f" 요약할 재료가 없다.")

    body = "\n".join(f"{r['seq']}. [{r['role']}] {r['text']}" for r in rows)
    prompt = (SESSION_TEMPLATE + "\n\n"
              + _SESSION_MATERIAL_HEADER.format(sid=kind, a=from_seq, b=to_seq)
              + "\n" + body + "\n\n[세션 요약]\n")

    content, usage = _generate(prompt, tag=tag)
    print(f"  · {kind} · 턴 {from_seq}–{to_seq} ({len(rows)}턴) — "
          + token_report(prompt, usage))
    warn = _truncation_warning(prompt, usage)
    if warn:
        print(f"    🔴 {warn}")
        m._prov(chat_id, to_seq, "llm_truncated", kind, warn)
    _refuse_reappearance(m, chat_id, kind, from_seq, to_seq, content)   # 저장 앞에 검사
    dropped = m.put_session_digest(
        chat_id, session_id, content,
        covers_from_seq=from_seq, covers_to_seq=to_seq)
    _replace_derivation(m, chat_id, kind,
                        _session_sources(m, chat_id, from_seq, to_seq))
    _put_digest_meta(m, chat_id, kind,
                     covers_from_seq=from_seq, covers_to_seq=to_seq)
    _clear_stale(m, chat_id, kind)
    m.db.commit()
    return kind, content, dropped


# ── (2) lifetime 재작성 — 세션 요약만 읽는다 ─────────────────────────────

def rewrite_lifetime(m, chat_id, *, tag=None):
    """
    세션 요약 전량(K = N, stale 제외)에서 lifetime 요약을 다시 쓴다 (ADR-013 P4).
    원본 턴에 접근하지 않는다 — 본문에 `_turns` 호출이 없는 것이 계약이다.
    반환: `(content, usage, warn)`.

    `digest` 테이블에 쓰는 유일한 프로덕션 지점이다. `INSERT OR REPLACE`가 아니라
    `ON CONFLICT … DO UPDATE`인 이유: `OR REPLACE`는 행을 지우고 다시 넣어 `session_end_note`를 NULL로 만든다.
    """
    rows = _lifetime_material(m, chat_id)      # stale 세션 요약은 뺀다
    if not rows:
        raise ValueError(
            f"{chat_id}: `digest_session`이 비어 있다. P4는 세션 요약에서만"
            f" 재작성하므로 재료가 0건이면 만들 것이 없다."
            f" (원본 턴으로 대신 만들면 그것은 P4가 아니라 기각된 P1이다)")

    # 오래된 것부터 — lifetime은 시간 순서를 쓰는 글이다. `session_digests`는
    # 주입용 정렬(`covers_to_seq DESC`)로 돌려주므로 여기서 뒤집는다.
    ordered = list(rows)[::-1]
    material = "\n\n".join(
        f"[{r['kind']} · 턴 {r['covers_from_seq']}–{r['covers_to_seq']}]\n"
        f"{r['content']}" for r in ordered)
    prompt = (P4_TEMPLATE.format(budget=LIFETIME_BUDGET_TOKENS) + "\n\n"
              + _LIFETIME_MATERIAL_HEADER.format(k=len(ordered)) + "\n"
              + material + "\n\n[다시 쓴 요약]\n")

    content, usage = _generate(prompt, tag=tag)

    # 호출마다 입력 토큰 세 값을 단위와 함께 찍는다.
    print(f"  · lifetime ← 세션 요약 {len(ordered)}건 — "
          + token_report(prompt, usage))
    warn = _truncation_warning(prompt, usage)

    covers_from = min((r["covers_from_seq"] or 0) for r in ordered)
    covers_to = max((r["covers_to_seq"] or 0) for r in ordered)
    if warn:
        print(f"    🔴 {warn}")
        m._prov(chat_id, covers_to, "llm_truncated", "lifetime", warn)

    m.db.execute(
        "INSERT INTO digest (chat_id, kind, content, covers_to_seq)"
        " VALUES (?,?,?,?)"
        " ON CONFLICT(chat_id, kind) DO UPDATE SET content=excluded.content,"
        " covers_to_seq=excluded.covers_to_seq",
        (chat_id, "lifetime", content, covers_to))

    # lifetime에도 재료 세션 요약들의 fact/event 원본을 등록한다. 참된 계보는 lifetime ← session:*
    # (깊이 2)이지만 `_invalidate_derived`는 `derivation`을 한 홉만 따라가므로, 등록하지 않으면 사실을
    # 지워도 lifetime은 그대로 서빙된다. 읽는 것은 색인뿐이라 P4 위반이 아니다(프롬프트에는 세션 요약만).
    keys = [r["kind"] for r in ordered]
    marks = ",".join("?" * len(keys))
    sources = [(r["source_kind"], r["source_id"]) for r in m.db.execute(
        "SELECT DISTINCT source_kind, source_id FROM derivation"
        f" WHERE chat_id=? AND derived_kind='digest' AND derived_key IN ({marks})"
        " ORDER BY source_kind, source_id", (chat_id, *keys))]
    _replace_derivation(m, chat_id, "lifetime",
                        [("digest", k) for k in keys] + sources)
    _put_digest_meta(m, chat_id, "lifetime",
                     covers_from_seq=covers_from, covers_to_seq=covers_to)
    _clear_stale(m, chat_id, "lifetime")
    m.db.commit()
    return content, usage, warn


# ── (3) stale 재생성 ────────────────────────────────────────────────────

def _stale_digest_keys(m, chat_id):
    """stale 표시된 `digest` 키들. 세션 → lifetime 순서로 돌려준다."""
    keys = _retryable_keys(m, chat_id)   # «포기»한 키는 뺀다
    # 포기한 키도 stale로 남으므로 서빙 제외는 그대로다 — 멈추는 것은 재시도(LLM 호출)뿐이다.
    sess = [k for k in keys if k.startswith("session:")]
    rest = [k for k in keys if not k.startswith("session:")]
    return sess, rest


def regenerate_stale(m, chat_id):
    """
    stale 표시된 digest를 세션 → lifetime 순서로 다시 만든다. lifetime의 재료가 세션 요약이므로
    세션을 먼저 고치지 않으면 낡은 재료로 새 lifetime을 쓰게 된다.
    반환: `{"ok": [키…], "failed": [(키, 사유)…]}`.

    실패하면 `stale`을 유지하고 `regen_failed`를 남긴다 — 실패를 성공처럼 지우면 낡은 요약이
    «신선하다»는 표시를 달고 계속 주입된다.
    """
    sess, rest = _stale_digest_keys(m, chat_id)
    ok, failed = [], []

    for key in sess:
        row = m.db.execute(
            "SELECT covers_from_seq, covers_to_seq FROM digest_session"
            " WHERE chat_id=? AND kind=?", (chat_id, key)).fetchone()
        try:
            if row is None:
                # 키는 stale인데 행이 없다 — N 상한에 밀려 나갔거나 애초에
                # 만들어진 적이 없다. 구간을 추측하지 않는다.
                raise ValueError(
                    f"{key}: `digest_session`에 행이 없어 덮을 턴 구간을 모른다."
                    f" 구간을 추측해 다시 만들면 그 요약이 무엇을 덮는지"
                    f" 아무도 모르게 된다.")
            session_digest(m, chat_id, key,
                           from_seq=row["covers_from_seq"],
                           to_seq=row["covers_to_seq"])
            ok.append(key)
        except Exception as e:                              # noqa: BLE001
            failed.append((key, str(e)))
            _note_failure(m, chat_id, key, e)   # regen_failed + 시도 계수 · K회면 «포기»
            print(f"  🔴 재생성 실패 (stale 유지) — {key}: {e}")

    for key in rest:
        try:
            if key != "lifetime":
                # legacy `digest.kind='session'`(콜론 없음)이 여기 온다. 새 세션 요약은 전부
                # `digest_session`으로 가므로 이 키는 재생성할 수 없다 — stale을 유지하고 사유를 남긴다.
                raise ValueError(
                    f"{key}: v5는 `digest.kind='{key}'`에 쓰지 않는다 (I3)."
                    f" legacy 행이므로 재생성 대상이 아니다.")
            rewrite_lifetime(m, chat_id)
            ok.append(key)
        except Exception as e:                              # noqa: BLE001
            failed.append((key, str(e)))
            m._prov(chat_id, 0, "regen_failed", key, str(e))
            print(f"  🔴 재생성 실패 (stale 유지) — {key}: {e}")

    m.db.commit()
    return {"ok": ok, "failed": failed}


# ── (4) lifetime 재료 — stale 세션 요약을 뺀다 ──────────────────────────

def _lifetime_material(m, chat_id):
    """
    `rewrite_lifetime`의 재료 = 세션 요약 전량(K = N) 중 stale이 아닌 것.

    삭제는 그 사실을 원본으로 둔 세션 요약을 stale로 민다. 그 세션의 재생성이 실패했거나 아직 안 돌았을 때
    stale 본문을 재료로 쓰면 lifetime이 지운 사실을 되살린다. 사유는 가리지 않는다.
    뺀 것이 있으면 `lifetime_material_excluded`를 남기고, 전부 빠지면 `ValueError`다.
    stale이 없으면 `session_digests`의 반환을 그대로 돌려준다(프롬프트 바이트 동일).
    """
    rows, stale = _split_material(m, chat_id)
    if not stale:
        return rows
    m._prov(chat_id, 0, "lifetime_material_excluded", "lifetime",
            f"stale 세션 요약 {len(stale)}건을 재료에서 뺐다 — {', '.join(stale)}")
    rows = [r for r in rows if r["kind"] not in stale]
    if not rows:
        raise ValueError(
            f"{chat_id}: 세션 요약 {len(stale)}건이 전부 stale이라 재료에서 뺐다 —"
            f" 재료 0건. stale 본문으로 다시 쓰면 지운 사실이 lifetime으로 돌아온다.")
    return rows


def _split_material(m, chat_id):
    """재료 후보(세션 요약 전량 K = N)와 그중 stale인 키. 재료의 정의가 사는 한 곳이다."""
    rows = m.session_digests(chat_id, limit=memory.DIGEST_KEEP_SESSIONS)
    stale = [r["kind"] for r in rows
             if m.stale_row(chat_id, "digest", r["kind"]) is not None]
    return rows, stale


def lifetime_material_keys(m, chat_id):
    """
    `_lifetime_material`이 지금 돌려줄 재료의 키 집합 — 부작용 없음(provenance 0 · 예외 0).
    `regen_job`의 두 방아쇠가 이것을 본다 — 재료를 따로 세면 «재료가 바뀌었나»와 «재료로 쓰나»가 갈라진다.
    """
    rows, stale = _split_material(m, chat_id)
    return {r["kind"] for r in rows} - set(stale)


def lifetime_written_keys(m, chat_id):
    """
    lifetime이 지난번에 쓴 재료의 키 집합 — `rewrite_lifetime`이 `derivation`에 적은 `("digest", 세션 키)` 행.
    행이 없는 lifetime(legacy · 이 파일 밖에서 쓴 행)은 빈 집합이다.
    """
    return {r["source_id"] for r in m.db.execute(
        "SELECT source_id FROM derivation WHERE chat_id=? AND derived_kind='digest'"
        " AND derived_key='lifetime' AND source_kind='digest'", (chat_id,))}


# ── (5) 지운 원본 — 재생성이 지운 사실을 되살리지 않는다 ─────────────────────
# 삭제는 세션 요약을 stale로 밀고 재생성은 원본 턴에서 다시 쓴다. 원본 턴은 지우지 않으므로(ADR-010)
# 지운 사실을 말한 턴이 그대로 재료로 간다. 처분 셋:
#   ① 그 턴을 가린다  ② 새 본문에 지운 항목의 어근이 통째로 있으면 저장하지 않는다(stale 유지)
#   ③ 지운 원본은 파생 등록에 다시 적지 않는다(`_session_sources`)
# 한계: 가리기의 단위는 턴 하나다(사실은 `source_turn_seq`, 사건은 `source_from_seq`). 다시 언급한 턴은
# ②만 막고, 의역(어근이 안 겹치는 재서술)은 못 막는다.

def _deleted_rows(m, chat_id, from_seq, to_seq):
    """
    구간 안에서 유저가 지운 원본 — `[(라벨, 턴 seq, 본문)]`.

    사건은 색인 복사본(`derivation`의 `derived_kind='event'` 대상)을 뺀다 — 복사본의 `user_deleted=1`은
    사실이 바뀌어도 찍히므로(«무효화됨»), 지운 원본으로 세면 사실 갱신이 옛 값을 말한 턴을 가린다.
    복사본의 원본 사실이 지워졌으면 그 사실의 턴이 이미 여기 든다.
    """
    rows = [(f"fact:{r[0]}", r[1], r[2] or "") for r in m.db.execute(
        "SELECT fact_id, source_turn_seq, object FROM fact WHERE chat_id=?"
        " AND user_deleted=1 AND source_turn_seq BETWEEN ? AND ?"
        " ORDER BY fact_id", (chat_id, from_seq, to_seq))]
    rows += [(f"event:{r[0]}", r[1], r[2] or "") for r in m.db.execute(
        "SELECT event_id, source_from_seq, summary FROM event WHERE chat_id=?"
        " AND user_deleted=1 AND source_from_seq BETWEEN ? AND ?"
        " AND CAST(event_id AS TEXT) NOT IN (SELECT derived_key FROM derivation"
        "  WHERE chat_id=? AND derived_kind='event')"
        " ORDER BY event_id", (chat_id, from_seq, to_seq, chat_id))]
    return rows


def _deleted_source_seqs(m, chat_id, from_seq, to_seq):
    """가릴 턴 — 구간 안 지운 원본이 가리키는 `seq` 집합."""
    return {seq for _, seq, _ in _deleted_rows(m, chat_id, from_seq, to_seq)}


def _deleted_terms(m, chat_id, from_seq, to_seq):
    """지운 항목마다 어근 집합 — `[(라벨, frozenset)]`. 어근은 `Memory._roots`(읽기만)."""
    return [(label, frozenset(memory.Memory._roots(text)))
            for label, _, text in _deleted_rows(m, chat_id, from_seq, to_seq)]


def _reappeared(content, terms):
    """
    새 본문에 어근 집합이 통째로 든 지운 항목의 라벨들. 부분 겹침은 세지 않는다 — «마케팅» 한 낱말로
    울면 그 낱말을 쓰는 요약이 전부 영영 stale이 된다. 어근이 0개인 항목은 건너뛴다.
    """
    have = memory.Memory._roots(content)
    return [label for label, roots in terms if roots and roots <= have]


def _not_in(exclude):
    """`_turns`의 SQL 조각. 비면 빈 문자열(삭제가 없는 구간의 SQL은 그대로)."""
    return (" AND seq NOT IN (" + ",".join("?" * len(exclude)) + ")") if exclude else ""


def _masked_turns(m, chat_id, kind, from_seq, to_seq):
    """
    `session_digest`의 재료 — 원본 턴에서 지운 원본의 턴을 뺀 것. 가린 턴이 있으면 `regen_masked`를
    남긴다(개수와 seq만 — 지운 내용은 옮겨 적지 않는다). 가리고 나니 0턴이면 그 사유로 `ValueError`다.
    """
    seqs = sorted(_deleted_source_seqs(m, chat_id, from_seq, to_seq))
    rows = _turns(m, chat_id, from_seq, to_seq, exclude=seqs)
    if seqs:
        m._prov(chat_id, to_seq, "regen_masked", kind,
                f"지운 원본의 턴 {len(seqs)}개(seq {', '.join(map(str, seqs))})를 재료에서 뺐다")
        if not rows:
            raise ValueError(
                f"{kind}: 턴 {from_seq}–{to_seq} 구간의 원본 턴이 전부 지운 원본의 턴이라"
                f" 가렸다 — 재료 0건. 가리지 않고 쓰면 지운 사실이 요약으로 돌아온다.")
    return rows


def _refuse_reappearance(m, chat_id, kind, from_seq, to_seq, content):
    """
    저장 앞의 재등장 검사. 걸리면 `ValueError` — 행을 쓰지 않았으므로 stale은 그대로고
    `regenerate_stale`의 `except`가 `regen_failed`로 남긴다. 사유에는 라벨만 적는다(지운 내용의 사본을 만들지 않는다).
    """
    hit = _reappeared(content, _deleted_terms(m, chat_id, from_seq, to_seq))
    if hit:
        raise ValueError(
            f"{kind}: 지운 사실이 새 요약에 재등장 — 저장하지 않고 stale 유지"
            f" ({', '.join(hit)})")


# ── (6) 표지 행과 재시도 상한 ─────────────────────────────────────────
# 첫 요약(`regen_job.run` ①)이 실패하면 행이 없어 stale도 구간도 없고, 아무도 다시 만들지 않는다.
# 그리고 원인이 결정적이면 재시도가 경계마다 끝없이 반복된다. 처분:
#   ① 실패는 표지 행(본문 "" · 구간 있음)과 stale «미완:»을 남긴다
#   ② 실패마다 사유 꼬리에 시도 수를 적고, 연속 `REGEN_MAX_ATTEMPTS`회면 «포기»로 적고 더 부르지 않는다
# 계수는 `stale.reason` 꼬리에 산다(스키마 변경 없음) — 새 삭제·무효화가 사유를 새로 쓰면 계수도 되돌아간다.
# lifetime · legacy `kind='session'`의 실패는 계수 밖이다 — lifetime에는 재등장 검사가 없고(지운 사실은 stale 재료를
# 빼는 것으로 막는다), legacy 키는 재생성할 수 없어 경계마다 실패를 남기는 채로 둔다.

import re                                                   # noqa: E402 — 나중에 붙인 절이라 import도 여기 있다

# 연속 실패 상한(첫 시도 + 재시도 1). 유도된 값이 아니다 — 같은 프롬프트도 본문이 갈릴 수 있다는
# 관측이 재시도 한 번의 근거이고, 적정 횟수는 잰 적이 없다.
REGEN_MAX_ATTEMPTS = 2

HOLD_REASON_PREFIX = "미완: "          # 표지 행의 stale 사유 머리
ABANDON_TAIL = " · 포기"                # 연속 K회 실패 — `_retryable_keys`가 이 꼬리를 거른다
_ATTEMPT_TAIL = re.compile(r" · 시도 (\d+)/(\d+)$")


def _first_clause(exc):
    """
    예외 메시지의 첫 절 — 표지 사유에는 여기까지만 적는다(첫 « — » 앞 · 첫 «. » 앞).
    생성기 오류 메시지가 무엇을 실을지 모르므로, 지운 내용이 사유로 새지 않게 한다.
    """
    return str(exc).split(" — ", 1)[0].split(". ", 1)[0]


def hold_session(m, chat_id, session_id, from_seq, to_seq, exc):
    """
    `regen_job.run` ①이 실패한 세션에 표지 행을 남긴다 — 본문 "" · 구간 · stale «미완: … · 시도 1/K».

    다음 경계의 `regenerate_stale`이 그 행의 구간으로 다시 만든다. 표지는 stale이라 서빙과 lifetime
    재료에서 빠지고, 침묵 탐지(`regen_job._live_digest_count`)도 요약으로 세지 않는다.
      - 파생 등록은 한다 — 그 구간의 새 삭제·무효화가 사유를 새로 써서 재시도 계수를 되돌리게.
      - `_put_digest_meta`는 안 부른다 — 표지는 생성이 아니다.
      - 그 키에 행이 이미 있으면 아무것도 안 한다(있는 본문을 빈 표지로 덮지 않는다).
      - stale을 행보다 먼저 쓴다 — 사이에서 멈춰도 빈 본문이 서빙되는 상태가 안 생긴다.
    반환: 표지를 쓴 키 또는 `None`.
    """
    kind = session_kind(session_id)
    if m.db.execute("SELECT 1 FROM digest_session WHERE chat_id=? AND kind=?",
                    (chat_id, kind)).fetchone() is not None:
        return None
    # 알려진 한계: `_replace_derivation` → `record_derivation`이 스스로 커밋하므로 그 뒤 · stale 앞에서
    # 멈추면 «행도 stale도 없는 파생 등록»이 남는다(원본이 없으면 창도 없다). 한 트랜잭션으로 묶는 것은
    # 동작 변경이라 그대로 두었다.
    _replace_derivation(m, chat_id, kind, _session_sources(m, chat_id, from_seq, to_seq))
    m.db.execute("INSERT OR REPLACE INTO stale VALUES (?,?,?,?,?)",
                 (chat_id, "digest", kind,
                  f"{HOLD_REASON_PREFIX}{_first_clause(exc)} · 시도 1/{REGEN_MAX_ATTEMPTS}",
                  time.time()))
    m.put_session_digest(chat_id, session_id, "",
                         covers_from_seq=from_seq, covers_to_seq=to_seq)   # 커밋 · N 상한
    m.db.commit()
    return kind


def _attempts(reason):
    """`(꼬리를 뗀 사유, 시도 수)` — 꼬리가 없으면 `(reason, 0)`. 계수를 읽는 곳은 여기 하나다."""
    hit = _ATTEMPT_TAIL.search(reason)
    return (reason[:hit.start()], int(hit.group(1))) if hit else (reason, 0)


def _note_failure(m, chat_id, key, exc):
    """
    `regenerate_stale`의 세션 키 실패 — `regen_failed` + 사유 꼬리 « · 시도 n/K».
    n이 `REGEN_MAX_ATTEMPTS`에 닿으면 « · 포기»를 덧붙이고 `regen_abandoned`를 한 번 남긴다 — 그 뒤
    `_retryable_keys`가 그 키를 건너뛴다. stale은 그대로라 서빙 제외도 그대로다.
    `전이:` 사유는 계수 밖이다(옛 전파를 켠 측정의 재생성 수를 바꾸지 않게).
    """
    m._prov(chat_id, 0, "regen_failed", key, str(exc))
    st = m.stale_row(chat_id, "digest", key)
    if st is None or st[0].startswith("전이:"):
        return
    base, n = _attempts(st[0])
    n += 1
    reason = f"{base} · 시도 {n}/{REGEN_MAX_ATTEMPTS}"
    if n >= REGEN_MAX_ATTEMPTS:
        reason += ABANDON_TAIL
        m._prov(chat_id, 0, "regen_abandoned", key,
                f"연속 {REGEN_MAX_ATTEMPTS}회 실패 — 새 삭제·무효화가 이 키를 다시 stale로 밀 때까지"
                f" 재시도 안 함")
    m.db.execute("UPDATE stale SET reason=? WHERE chat_id=? AND derived_kind='digest'"
                 " AND derived_key=?", (reason, chat_id, key))


def _retryable_keys(m, chat_id):
    """stale digest 키 전부(키 순서)에서 «포기» 사유를 뺀 것. 포기가 없으면 전부다."""
    return [r["derived_key"] for r in m.db.execute(
        "SELECT derived_key FROM stale WHERE chat_id=? AND derived_kind='digest'"
        " AND reason NOT LIKE ?"
        " ORDER BY derived_key", (chat_id, "%" + ABANDON_TAIL))]
