# -*- coding: utf-8 -*-
"""
regen_job.py — 세션 경계에서 요약 계층을 돌리는 호출자 (ADR-016).

`summarize`의 셋(`session_digest` · `rewrite_lifetime` · `regenerate_stale`)은 무엇을 할지는 알지만
언제 할지는 모른다 — 답은 «세션 경계에서»다. 경계의 정의는 `soak.py`와 같은
`session_start=(row["turn"] == 1)` 하나다(두 번째 정의를 만들지 않는다).

`soak.py`는 이 모듈을 import하지 않는다 — import하면 `summarize` → `llm` → ollama 의존이 따라 들어와
720턴 회귀 게이트가 외부 서비스에 매달린다. 실서비스 스케줄러는 프로토타입 범위 밖이고, 여기서는
«부를 수 있는 것»을 만들어 시험이 부른다.

세션이 지났는데 요약이 0건이면 `("regen_missing", session_id, 사유)`를 provenance에 남긴다 —
막지는 않는다(첫 세션에는 언제나 참이다).
"""
import memory
import summarize

# 첫 lifetime의 문턱. 최신 M개(`DIGEST_INJECT_MAX`)는 세션 블록이 이미 덮으므로, 세션 블록이 못 덮는
# 첫 세션이 생기는 M+1번째에 만든다 — 그 전에 만들면 같은 재료가 두 블록으로 두 번 나간다.
# (이 유도가 없애는 것은 첫 경계의 중복뿐이다 — 둘째 경계부터 lifetime은 최신 세션 블록의 재료를 품는다.)
# 세는 것은 재료(stale 아닌 세션 요약 — `summarize.lifetime_material_keys`)다.
# 행 수로 세면 `rewrite_lifetime`의 재료(stale 제외)와 갈라진다.
LIFETIME_MIN_SESSIONS = memory.DIGEST_INJECT_MAX + 1


def run(m, chat_id, *, now_seq, ended_session_id=None,
        from_seq=None, to_seq=None, make_digest=True):
    """
    세션 경계 한 번. 세 가지를 순서대로 한다.

      ① `ended_session_id`가 주어지면 그 세션의 요약을 만든다 (`session_digest`)
      ② stale 표시된 digest를 재생성한다 (`regenerate_stale`)
      ③ lifetime이 없고 재료가 문턱에 닿았으면 처음 만들고(`lifetime_due_first`),
         있고 재료가 바뀌었으면 다시 쓴다(`lifetime_behind`) — 둘 다 `rewrite_lifetime`

    ①이 lifetime의 재료를 갱신하므로 `rewrite_lifetime`은 그 뒤에 와야 새 재료로 쓴다.
    stale이 0건이고 ③의 조건이 거짓이고 `make_digest=False`면 LLM을 한 번도 부르지 않는다.

    반환: `{"session": (kind, dropped) · ("failed", 사유) · None, "regen": {...},
            "lifetime": None · "created" · "rewritten" · "failed: …", "missing": bool}`.

    ①이 도는 경계는 구간(`from_seq`·`to_seq`)을 준다 — 없으면 `ValueError`(구간을 추측하면 앞 경계의
    요약이 실패한 뒤 두 세션이 한 키로 묶인다). ①의 실패는 잡아서 `regen_failed`로 남기고 ②③과 침묵
    탐지는 계속 간다. 실패한 세션은 ②③ 뒤에 표지 행으로 남긴다(`summarize.hold_session`) — 다음
    경계의 ②가 재시도하고, 같은 경계에서 곧바로 다시 부르지 않는다.
    """
    out = {"session": None, "regen": None, "lifetime": None, "missing": False}
    held = None                                 # ①의 실패 — ②③ 뒤에 표지로 남긴다

    if make_digest and ended_session_id is not None:
        if from_seq is None or to_seq is None:
            raise ValueError(
                f"{ended_session_id}: 요약을 만드는 경계에 구간이 없다"
                f" (from_seq={from_seq}, to_seq={to_seq}). 경계를 아는 호출부는"
                f" 구간을 준다 — 추측하면 앞 세션이 실패한 뒤 두 세션이 한 키로 묶인다.")
        try:
            kind, _, dropped = summarize.session_digest(
                m, chat_id, ended_session_id, from_seq=from_seq, to_seq=to_seq)
            out["session"] = (kind, dropped)
        except Exception as e:                              # noqa: BLE001
            m._prov(chat_id, now_seq, "regen_failed",
                    memory.session_kind(ended_session_id), str(e))
            out["session"] = ("failed", str(e))
            held = e
            print(f"  🔴 세션 요약 실패 ({ended_session_id} · 턴 {from_seq}–{to_seq})"
                  f" — ②③은 계속 간다: {e}")

    # ② 낡은 것을 푼다. 실패하면 `stale`을 유지한다 — `regenerate_stale`의 계약.
    out["regen"] = summarize.regenerate_stale(m, chat_id)

    # ③ lifetime 새로고침·첫 생성. 전이는 digest를 stale로 밀지 않으므로(`memory.TRANSITION_PROPAGATES_DIGEST`)
    #    재료가 바뀐 경계에서 여기서 쓴다. stale로 찍지 않고 곧장 쓴다 — 뒤처진 lifetime은 틀린 것이
    #    아니라 덜 된 것이다. stale로 찍고 재작성이 실패하면 서빙에서 빠져, 한 세션 늦은 것에 삭제·무효화와
    #    같은 처분을 주게 된다. 실패하면 옛 lifetime을 그대로 둔다. ②가 lifetime을 이미 시도했으면 건너뛴다.
    tried = {k for k in out["regen"]["ok"]} | {k for k, _ in out["regen"]["failed"]}
    if "lifetime" not in tried:
        first = lifetime_due_first(m, chat_id)
        if first or lifetime_behind(m, chat_id):
            try:
                summarize.rewrite_lifetime(m, chat_id)
                out["lifetime"] = "created" if first else "rewritten"
            except Exception as e:                          # noqa: BLE001
                m._prov(chat_id, now_seq, "regen_failed", "lifetime", str(e))
                out["lifetime"] = f"failed: {e}"
                print(f"  🔴 lifetime {'첫 생성' if first else '새로고침'} 실패"
                      f" ({'행 없음 유지' if first else '옛 lifetime 유지'}) — {e}")

    # ①의 실패를 표지로 남긴다 — ②③ 뒤라 이 경계에서는 재시도하지 않는다.
    if held is not None:
        summarize.hold_session(m, chat_id, ended_session_id, from_seq, to_seq, held)

    # 침묵 탐지 — ①을 돌린 뒤에 센다. 표지 행(본문 "")은 요약이 아니다.
    n = _live_digest_count(m, chat_id)
    if n == 0:
        holds = m.db.execute("SELECT COUNT(*) c FROM digest_session WHERE chat_id=?",
                             (chat_id,)).fetchone()["c"]
        why = ("세션 경계를 지났는데 `digest_session`이 0행이다." if not holds else
               f"세션 경계를 지났는데 `digest_session`에 요약이 0건이다(표지 행 {holds}건은"
               f" 요약이 아니다 — 재시도 대기 또는 포기).")
        why += (" 요약 없이 도는 중 — `build_context`는 정상 모양으로 조립되고"
                " 없는 것은 없는 채로 지나간다")
        m._prov(chat_id, now_seq, "regen_missing",
                str(ended_session_id), why)
        out["missing"] = True
        print(f"  ⚠️ regen_missing — {why}")

    m.db.commit()
    return out


def _has_lifetime(m, chat_id):
    return m.db.execute("SELECT 1 FROM digest WHERE chat_id=? AND kind='lifetime'",
                        (chat_id,)).fetchone() is not None


def _live_digest_count(m, chat_id):
    """
    요약인 `digest_session` 행의 수 — 표지 행(본문 "")은 세지 않는다.
    stale 사유(`미완:`)가 아니라 본문으로 가른다 — 그 구간의 새 삭제가 사유를 새로 쓰면 빈 표지가 요약으로
    세어진다. 생성된 요약은 비지 않는다(`llm.generate`는 빈 응답이면 예외). NULL 본문 행은 센다.
    """
    return m.db.execute("SELECT COUNT(*) c FROM digest_session WHERE chat_id=?"
                        " AND content IS NOT ''", (chat_id,)).fetchone()["c"]


def lifetime_behind(m, chat_id):
    """
    lifetime이 있고, 지금의 재료 키 집합(`summarize.lifetime_material_keys`)이 lifetime이 지난번에 쓴
    재료 키 집합(`summarize.lifetime_written_keys`)과 다른가. 같으면 다시 써도 프롬프트가 같다(호출 0).
    다르면 새 세션이 생겼거나, N 상한이 하나를 밀어냈거나, 빠졌던 세션이 재생성으로 돌아왔다.
    덮는 끝(seq)으로 비교하지 않는 이유: stale 세션이 재료에서 빠지면 끝과 재료가 갈라진다.
    본문 갱신 시각은 보지 않는다 — 제품 경로에서 재료 세션의 본문이 바뀌는 길은 stale → 재생성뿐이고, 그 원본이
    지워지면 lifetime도 같은 삭제로 stale이 되어 `run`의 ②가 다시 쓴다(`rewrite_lifetime`이 원본을 평탄화해 등록한다).
    재료가 0이면 거짓이다(다시 쓸 수 없다).
    """
    if not _has_lifetime(m, chat_id):
        return False
    now = summarize.lifetime_material_keys(m, chat_id)
    return bool(now) and now != summarize.lifetime_written_keys(m, chat_id)


def lifetime_due_first(m, chat_id):
    """
    lifetime 행이 없고 재료가 `LIFETIME_MIN_SESSIONS`개 이상인가 — 첫 생성 방아쇠.
    `lifetime_behind`와 합치지 않는 이유: `run`의 반환이 «처음 만들었다»와 «다시 썼다»를 가른다.
    """
    if _has_lifetime(m, chat_id):
        return False
    return len(summarize.lifetime_material_keys(m, chat_id)) >= LIFETIME_MIN_SESSIONS


def boundary(m, chat_id, *, now_seq, session_start, **kw):
    """`soak.py`가 계산하는 `session_start` 불리언을 그대로 받는 얇은 껍질 — «경계란 무엇인가»를 한 곳에 둔다."""
    if not session_start:
        return None
    return run(m, chat_id, now_seq=now_seq, **kw)


# 세션 경계에서 보존하는 요약 수를 이름으로 적기 위한 별칭(값과 이름 규칙은 `memory.py`가 소유한다).
KEEP = memory.DIGEST_KEEP_SESSIONS
