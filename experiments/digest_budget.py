# -*- coding: utf-8 -*-
"""
digest_budget.py — 요약을 넣기 전에 **저울부터 고친다.** (계획서 §7 단계 S0)

## 왜 이 파일이 저 계획의 첫 단계인가

이 라운드의 모든 판정이 *"토큰이 기준선×1.2를 넘는가"*에 매달려 있는데,
그 토큰을 재던 자ㅡ`memory.ntok()` = `len × 1.5`ㅡ가 이 코퍼스에서 **2.07배
과대계상**한다. 저울을 고치기 전에 잰 값 위에 계획을 세우면, 그 위의 모든
결론이 저울과 함께 움직인다. 그래서 여기가 먼저다.

이 파일이 찍는 것은 셋이다.

  1. **토큰 기준선** — 축은 `b`(주입된 `digest:` 블록 **개수**)다. 손잡이가
     아니라 **관측량**이다. `DIGEST_INJECT_MAX`도 `digest_session`도 이
     단계에는 없으므로(계획서 S22), 오늘 코드로 잴 수 있는 축은 `b` 하나다.
     `digest`의 PK가 `(chat_id, kind)`라 임의 `kind`를 심으면 `build_context`의
     주입 루프가 그만큼 블록을 만든다 — **주입 상한 코드에 의존하지 않고**
     "블록이 하나 늘면 컨텍스트가 얼마나 커지는가"를 잰다.
  2. **저울 대조** — `ntok` 추정과 실측 `prompt_eval_count`를 나란히 놓고 배율.
  3. **M2 상한 대조군** — `survived_v2`를 **세 열**로 가른다. 한 수로 압축하는
     것이 이 저장소가 네 번 겪은 실패(*"숫자는 맞는데 이름이 틀림"*)다.

## 🔴 여기서 하지 않는 것

**G19′ ①②③은 켜지 않는다.** 검사 대상이 이 시점에 하나도 없다. 없는 함수의
`DELETE`는 지울 수 없고, *"아직 없는 것을 검사한다"*고 적힌 수용 기준은
*"실행 전에 알 수 없는 값을 기대 출력으로 못박은 것"*의 사촌이다. 검사 함수는
`g19_prime_counts()`로 **정의만** 해 두고, 그 사실을 출력 첫 줄에 적는다.

**발화점을 예언하지 않는다 (G14 · R6).** 어느 `b`에서 «b=2 기준선»×1.2를
넘는지는 **출력이 말한다.** 어느 `b`에서도 안 넘으면 그 게이트는 폐기하고
그 사실을 적는다. 여기에 기대 출력을 미리 적으면 그것이 곧 결함이다.

## 단위 (G15)

`ctx.tokens`는 `Block.tokens` = `ntok()`의 합이므로 **`ntok` 단위**다.
🔴 **`ntok`을 `LLM_NUM_CTX`로 나누지 않는다** — 단위가 섞인 수가 된다.
`LLM_NUM_CTX`와 나란히 놓는 것은 **실측 `prompt_eval_count`**뿐이다.

## 격리

DB는 **저장소 밖**(`%TEMP%`)에 만든다. `build_context`에 부작용이 있어
설정마다 새 DB가 필요하고(`soak.build`의 주석이 정본), 병렬 레인이 같은
파일을 열면 결과가 오염된다.
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prototype"))
sys.stdout.reconfigure(encoding="utf-8")

import yaml                                                   # noqa: E402
import llm                                                    # noqa: E402
import memory                                                 # noqa: E402
import scoring                                                # noqa: E402
import soak                                                   # noqa: E402
from memory import Memory, ntok                               # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
W = 78
CHAT = soak.CHAT

# ── 비교 기준 — **계산에 쓰지 않는다** ───────────────────────────────────
# 🔴 상수로 박으면 그 순간 이 스크립트는 저울이 아니라 **저울의 기억**이 된다.
#    아래 둘은 "이번 실행이 지난번과 같은 조건인가"를 묻는 데만 쓴다.
REC_RATIO = 2.074      # 계획서 S13: ntok 2,688 / 실측 1,296 (요약 12개 단순비)
REC_TOK_PER_CHAR = 0.7189   # 계획서 S23: 두 길이 회귀의 **한계** 비율
RATIO_BAND = 0.10      # 이만큼 넘게 어긋나면 경고를 찍는다 (막지는 않는다)

# ⚠️ 절편 주의 (계획서 S23 · U10). 위 배율은 **비례상수가 아니다.**
#    두 길이(981글자 → 713 tok · 1,792글자 → 1,296 tok)로 회귀를 뜨면
#      한계 비율 = 583/811 = 0.7189 tok/글자 · 절편 = 713 − 981×0.7189 ≈ 7.8 tok
#    이고, 점이 **둘뿐이라 잔차가 없다** — 적합은 항상 정확하고 비선형성을
#    탐지할 수 없다. 그래서 그 7.8을 "템플릿·BOS 몫"이라 부르지 않는다.
#    정확한 이름은 **«고정 오버헤드 + 문자수 대비 토큰화의 곡률 ≲ 8토큰»**이다.
#    단순비 2.074는 그 절편을 내용에 섞어 넣어 0.6% 과대추정하며,
#    **편향 방향이 N 유도에 안전한 쪽**이다(실제 내용 토큰은 더 적다).

# 계획서 §7 S0이 동일성 대조 대상으로 지정한 고정물.
BASELINE_FILE = os.path.join(ROOT, "experiments", "data", "baseline",
                             "G2-soak.txt")
BASELINE_LINE = 35

# ── `digest`에 심을 행 ───────────────────────────────────────────────────
# `kind`는 PK의 한 축이므로 서로 달라야 한다. 앞 둘이 **오늘의 컨텍스트
# 모양**(lifetime + session)이고, 그래서 `b=2`가 기준선이다.
# 나머지 셋은 계획서 S1이 말한 키 값 규약(`session:S07` 꼴)을 그대로 쓴다 —
# 스키마를 안 바꾸고 행 수만 늘리는 그 틈이 이 표가 재는 대상이다.
PLANT_KINDS = ["lifetime", "session", "session:S03", "session:S04",
               "session:S05"]
B_AXIS = [0, 1, 2, 3, 4, 5]
B_BASE = 2             # 이후 모든 ≤20% 판정의 **분모** (G15 — 이름을 붙여 둔다)
GATE = 1.2

EXPECT_DIGEST = "500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41"


# ── G19′ — 🔄 **S3에서 켰다** (계획서 편집 3) ────────────────────────────
def g19_prime_counts(db, chat_id, keep_sessions):
    """
    G19′ ①②③의 카운트 셋 — 🔄 w24d가 넷째 수(`derivation`)를 붙였다.

    🔄 **S0에서는 정의만 되어 있었다.** 검사 대상이 그 시점에 하나도 없었기
       때문이다 — ①의 `put_session_digest`는 S1, ②의 `_serve_digest`는 S3,
       ③의 I5(`targets` 열거)는 S3이고, ②가 세는 `digest_session` 테이블
       **자체가 S1에서 생겼다.** S3이 그 셋을 전부 실재하게 만들었으므로
       여기서 **호출하고 종료 코드로 가른다.**

    반쯤 켜진 배선은 *"일부는 도는 줄 알았다"*를 만들기 때문에, 셋을 **함께**
    켜고 `run_all.STEPS` 등록과 음성 대조 넷을 같은 단계에서 시연한다.
    """
    q = lambda sql, *a: db.execute(sql, a).fetchone()[0]      # noqa: E731
    return {
        # ① 저장 상한 — `digest_session` 행 수는 N에 수렴한다
        "digest_session": q("SELECT COUNT(*) FROM digest_session"
                            " WHERE chat_id=?", chat_id),
        # ③ 파급 상한 — 두 수는 **같아야** 한다(같은 `targets`를 돈다)
        "stale_digest": q("SELECT COUNT(*) FROM stale WHERE chat_id=?"
                          " AND derived_kind='digest'", chat_id),
        "digest_meta": q("SELECT COUNT(*) FROM digest_meta WHERE chat_id=?",
                         chat_id),
        # ①′ 파생 — 🔄 w24d (Fable 발견 4 · G19′ 확장). `derivation`도 digest 키를 따라 행이
        #    생긴다(요약기가 키마다 원본을 등록한다). G19′가 «늘어나는 자리 전부»라며 위 셋만
        #    셌고 이 테이블을 빠뜨렸다 — 밀려난 키의 등록이 남아 유령 stale을 낳았다(w20b 수리).
        "derivation_digest": q("SELECT COUNT(DISTINCT derived_key) FROM derivation"
                               " WHERE chat_id=? AND derived_kind='digest'", chat_id),
        # 상한의 정본: `lifetime` 1 + legacy `kind='session'` 1 + `session:S*` N
        "cap": keep_sessions + 2,
    }


# ── G19′ 집행 (단계 S3) ─────────────────────────────────────────────────
#
# 🔴 **여기가 러너에 배선되는 자리다.** G14 rev2가 적어 둔 교훈 — *"가드레일이
#    읽으라고 만든 종료 코드를 아무도 안 읽는 배선이었다"* — 이전 상태로
#    태어나지 않기 위해, 이 함수의 판정이 `main()`의 종료 코드에 직접 들어가고
#    이 파일이 `run_all.STEPS`에 있다.
#
# ⚠️ **ollama보다 먼저 돈다.** 이 검사는 ollama를 한 번도 안 부르므로, ollama가
#    없어 저울·상한 대조가 77(SKIP)로 끝나는 환경에서도 **계약은 집행된다.**
#    뒤에 두면 «ollama 없는 기계에서는 G19′가 안 돈다»가 되고, 그것이 곧
#    "발화할 수 없는 검사"다.

# 집행용 픽스처의 chat_id. 기준선 replay와 **다른 이름**을 쓴다 — 같은 이름이면
# 두 절이 같은 DB를 쓰는 줄로 읽힌다(실제로는 각자 임시 DB를 만든다).
G19_CHAT = "chat-g19"


def _g19_db(tmpdir, name):
    """집행 픽스처 한 벌. `build_context`가 도는 최소 상태만 넣는다."""
    m = Memory(os.path.join(tmpdir, name))
    db = m.db
    db.execute("INSERT INTO character_version (character_id, version,"
               " persona_text, speech_rules, taboos) VALUES (?,?,?,?,?)",
               ("seojun", 1, "페르소나", "반말", "금기"))
    db.execute("INSERT INTO chat (chat_id, user_id, character_id,"
               " character_version) VALUES (?,?,?,?)",
               (G19_CHAT, "jiwoo", "seojun", 1))
    db.execute("INSERT INTO relationship (chat_id, stage, affinity, called_as,"
               " user_locked, updated_by_turn) VALUES (?,?,?,?,?,?)",
               (G19_CHAT, "연인", 84, "지우", 0, 0))
    db.execute("INSERT OR REPLACE INTO digest (chat_id, kind, content,"
               " covers_to_seq) VALUES (?,?,?,?)",
               (G19_CHAT, "lifetime", "인생 요약", 0))
    db.commit()
    return m


def _b_of(m):
    """`b` — 조립된 컨텍스트의 `digest:` 블록 수. **관측량이다.**"""
    ctx = m.build_context(G19_CHAT, "그때 얘기 말인데", 2)
    return sum(1 for b in ctx.blocks if b.name.startswith("digest:"))


def _g19_store(tmpdir):
    """
    ①·①′·③이 함께 쓰는 DB — **제품 경로로 채운다.** `put_session_digest`를 N+3회, 매번 그 뒤에
    `record_derivation`을 부른다(`summarize.session_digest`의 순서 — 저장 → 파생 등록). lifetime의
    등록 한 벌은 `summarize.rewrite_lifetime`이 남기는 자리다. 🔄 w24d — 전에는 저장만 했다.

    🔴 **왜 N+3회인가 — ①′가 발화할 수 있으려면.** 상한 N+2에는 여유가 둘이고 lifetime이 하나를
       차지한다. 밀려난 키의 등록이 남는 코드에서 이 DB의 키는 lifetime 1 + 세션 N+3 = N+4라
       N+2를 넘는다. N+1회였다면 N+2 ≤ N+2 — **밀려난 키가 하나 남아도 조용하다.**
    """
    n = memory.DIGEST_KEEP_SESSIONS
    m = _g19_db(tmpdir, "g19-store.db")
    m.record_derivation(G19_CHAT, "digest", "lifetime", [("fact", "0")])
    for i in range(1, n + 4):                       # N+3개를 넣는다
        m.put_session_digest(G19_CHAT, f"S{i:02d}", "요약",
                             covers_from_seq=i * 10 - 9, covers_to_seq=i * 10)
        m.record_derivation(G19_CHAT, "digest", memory.session_kind(f"S{i:02d}"),
                            [("fact", str(i))])
    return m


def enforce_g19(tmpdir):
    """
    G19′ ①②③을 실제로 세고 위반 목록을 돌려준다.

    상한은 **모든 DB에서 참인 수**여야 한다. 그래서 ②는 상한식
    `b ≤ |digest 행| + M ≤ 2 + M`으로 걸고, **정확값은 이름 있는 고정물
    둘**(새 DB `b`=2 · legacy DB `b`=3)에서만 못박는다. *"정확히 2"* 하나로
    적으면 **마이그레이션이 대상으로 삼는 바로 그 DB에서 정상 경로가 빨개진다.**
    """
    n = memory.DIGEST_KEEP_SESSIONS
    cap = n + 2
    bad, lines = [], []

    print("\n" + "-" * W)
    print("4. G19′ 집행 — digest 키 공간의 기수 계약 (단계 S3에서 켠다)")
    print("-" * W)
    print(f"  이름: `DIGEST_KEEP_SESSIONS` = {n} · `DIGEST_INJECT_MAX` ="
          f" {memory.DIGEST_INJECT_MAX} · 상한 N+2 = {cap}")
    print(f"  적용 대상 다섯: digest · digest_session · stale(G6 동결) · digest_meta · derivation")
    print(f"  DB는 저장소 밖: {tmpdir}  ·  **ollama 0회**\n")

    # ── ① 저장 상한 ──
    m = _g19_store(tmpdir)
    c = g19_prime_counts(m.db, G19_CHAT, n)
    ok1 = c["digest_session"] == n
    lines.append(f"  ① 저장  `digest_session` {c['digest_session']}행"
                 f" (N+3={n + 3}개 삽입 후) == N({n})?"
                 f"   {'✅' if ok1 else '🔴 발화'}")
    if not ok1:
        bad.append(f"G19′① 저장 상한: digest_session {c['digest_session']} != {n}")

    # ── ①′ 파생 상한 — 같은 DB (🔄 w24d · Fable 발견 4의 G19′ 확장) ──
    ok1p = c["derivation_digest"] <= cap
    lines.append(f"  ①′ 파생  `derivation`(digest) 키 {c['derivation_digest']}개"
                 f" (같은 DB · 등록 lifetime 1 + 세션 N+3={n + 3}개) ≤ N+2({cap})?"
                 f"   {'✅' if ok1p else '🔴 발화'}")
    if not ok1p:
        bad.append(f"G19′①′ 파생 상한: derivation digest 키"
                   f" {c['derivation_digest']} > {cap}")

    # ── ③ 파급 상한 — 같은 DB에서 전이를 낸다 ──
    # 🔄 wave3 — 기본값에서 전이는 digest를 stale로 밀지 않는다(`memory.py` 끝의 스위치).
    #    그대로 재면 두 수가 0이라 «≤ N+2 이고 서로 같다»가 **공허하게 참**이 된다 —
    #    발화할 수 없는 검사다. 상한이 지키는 것은 **옛 전파 경로**이므로 그 경로를
    #    이름으로 켜고 잰다(되돌리는 날 그 경로가 이 상한을 다시 지게 된다).
    saved_switch = memory.TRANSITION_PROPAGATES_DIGEST
    memory.TRANSITION_PROPAGATES_DIGEST = True
    try:
        m._propagate_transition(G19_CHAT, 10, "연인", "다툼중")
        for i in range(n + 4, n + 7):               # 상한 넘겨 더 밀어 넣는다
            m.put_session_digest(G19_CHAT, f"S{i:02d}", "요약",
                                 covers_from_seq=i * 10 - 9, covers_to_seq=i * 10)
            m._propagate_transition(G19_CHAT, 10 + i, "다툼중", "연인")
    finally:
        memory.TRANSITION_PROPAGATES_DIGEST = saved_switch
    c = g19_prime_counts(m.db, G19_CHAT, n)
    # 기본값의 같은 전이 — 산문으로 적지 않고 잰다.
    md = _g19_db(tmpdir, "g19-default.db")
    for i in range(1, 4):
        md.put_session_digest(G19_CHAT, f"S{i:02d}", "요약",
                              covers_from_seq=i * 10 - 9, covers_to_seq=i * 10)
    md._propagate_transition(G19_CHAT, 40, "연인", "다툼중")
    pushed_default = g19_prime_counts(md.db, G19_CHAT, n)["stale_digest"]
    md.db.close()
    ok3 = (c["stale_digest"] <= cap and c["digest_meta"] <= cap
           and c["stale_digest"] == c["digest_meta"])
    lines.append(f"  ③ 파급  `stale`(digest) {c['stale_digest']}행 ·"
                 f" `digest_meta` {c['digest_meta']}행  ≤ N+2({cap})"
                 f" 이고 서로 같은가?   {'✅' if ok3 else '🔴 발화'}"
                 f"   (옛 전파 경로 · 기본값의 같은 전이는 세션 3행 DB에서"
                 f" digest {pushed_default}행을 민다)")
    if not ok3:
        bad.append(f"G19′③ 파급 상한: stale {c['stale_digest']} ·"
                   f" digest_meta {c['digest_meta']} · 상한 {cap}")
    m.db.close()

    # ── ② 주입 상한 — 고정물 **둘** ──
    m2 = _g19_db(tmpdir, "g19-new.db")
    for i in range(1, 6):
        m2.put_session_digest(G19_CHAT, f"S{i:02d}", "요약",
                              covers_from_seq=i * 10 - 9, covers_to_seq=i * 10)
    b_new = _b_of(m2)
    m2.db.close()

    m3 = _g19_db(tmpdir, "g19-legacy.db")
    m3.db.execute("INSERT OR REPLACE INTO digest (chat_id, kind, content,"
                  " covers_to_seq) VALUES (?,?,?,?)",
                  (G19_CHAT, "session", "옛 세션 요약 (legacy)", 0))
    m3.db.commit()
    for i in range(1, 6):
        m3.put_session_digest(G19_CHAT, f"S{i:02d}", "요약",
                              covers_from_seq=i * 10 - 9, covers_to_seq=i * 10)
    b_legacy = _b_of(m3)
    m3.db.close()

    ceil_new = 1 + memory.DIGEST_INJECT_MAX
    ceil_leg = 2 + memory.DIGEST_INJECT_MAX
    ok2 = (b_new == ceil_new and b_legacy == ceil_leg)
    lines.append(f"  ② 주입  ⓐ 새 DB `b`={b_new} == {ceil_new}"
                 f" · ⓑ legacy DB `b`={b_legacy} == {ceil_leg}"
                 f"   (상한식 `b ≤ 2+M` = {2 + memory.DIGEST_INJECT_MAX})"
                 f"   {'✅' if ok2 else '🔴 발화'}")
    if not ok2:
        bad.append(f"G19′② 주입 상한: 새 DB b={b_new}(기대 {ceil_new}) ·"
                   f" legacy DB b={b_legacy}(기대 {ceil_leg})")

    for ln in lines:
        print(ln)
    print("\n  🔴 ②의 상한이 `digest` 행 수에 기댄다 — 그 수를 묶는 것은"
          " **G17′-a**(동결 테이블 쓰기: `memory.py` 0 · 제품 전체 1 = `lifetime` 한 키)다.")
    print("     두 검사를 한 파일에서 함께 돌려 그 의존을 눈에 보이게 둔다.")
    # ⚠️ **그 grep의 정규식을 여기 산문으로 옮겨 적지 않는다** — 적으면 그 줄
    #    자체가 매치가 되어 G17′-d의 건수를 늘린다(`test_migrate.py`가 같은
    #    함정을 실측으로 적어 뒀다). 패턴이 사는 곳은 아래 함수 **한 곳**이다.
    line, bad_a = _g17a_check()
    print(line)
    bad += bad_a

    # ── ⑤ U5의 롤백 지뢰 — 막지 않는다. 찍는다 (§5 시나리오 4) ──
    n_mig = len(Memory.MIGRATIONS.get(5, []))
    print(f"\n  ⑤ `len(MIGRATIONS[5])` = {n_mig}")
    if n_mig > 0:
        print("  ⚠️ **경고 발화** — `MIGRATIONS[5]`가 비어 있지 않다. 롤백을 겪은")
        print("     DB(`schema_version='5'`, 코드 v4)를 다시 v5로 올리면")
        print("     `range(6,6)`이 빈 범위라 **이 마이그레이션이 조용히")
        print("     건너뛰어진다.** §4.2를 읽어라. (막지 않는다 — U5)")
        print("     ⚠️ 이 경고가 못 하는 것: 실제로 갈라진 DB를 찾아내지는")
        print("        못한다. 그것은 `PRAGMA table_info` 대조이고 이 라운드 밖이다.")
    else:
        print("     비어 있다 — 정상 경로에서는 안 발화한다. 그래서 이 검사의")
        print("     발화 증명은 **심을 위반 하나뿐**이다 (§5 시나리오 4-3).")
    return bad


def _count_prod_digest_insert(root=None):
    """
    G17′-a의 grep을 코드로 센다 — 동결 `digest` 쓰기가 **어느 파일 · 어느 함수**에 있는가.

    🔴 **패턴 문자열이 사는 곳은 여기 한 곳이다.** 산문에 한 번 더 적으면 그
       줄이 G17′-d의 grep에 걸려 «동결 테이블에 쓰는 곳»의 건수가 코드가 아니라
       주석 때문에 늘어난다. 세는 대상과 세는 도구를 갈라 두는 자리다.

    🔄 w24d (Fable C5 집행 확장) — 전에는 `memory.py`만 셌다. 그래서 «0»은 memory.py에 대해서만
       참이었고 «프로덕션 쓰기 0건»이라는 계약 문장은 틀렸다(`summarize.rewrite_lifetime`이 쓴다).
       이제 `prototype/` 바로 아래 `*.py` 전부를 센다. **빼는 것 둘 — 규칙은 여기 한 곳:**
       시험(`test_*.py`)과 데모(`demo.py` · `*_demo.py` — 독립 실행해 픽스처 행을 심는 스크립트).
       둘 다 제품 쓰기 경로가 아니다. 뺀 건수도 돌려준다 — 보이지 않는 제외가 되지 않게 출력에 찍는다.

    반환: `({파일: [감싸는 함수 이름, …]}, {"시험": 건수, "데모": 건수})` — 제품 쪽은 건마다 한 이름.
    """
    import ast
    import re
    pat = re.compile(r"INTO digest\b")
    d = os.path.join(root or ROOT, "prototype")
    prod, skipped = {}, {"시험": 0, "데모": 0}
    for name in sorted(os.path.relpath(os.path.join(a, b), d).replace(os.sep, "/") for a, _, fs in os.walk(d) for b in fs):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(d, name), encoding="utf-8") as f:
            src = f.read()
        hits = [src.count("\n", 0, mt.start()) + 1 for mt in pat.finditer(src)]
        if os.path.basename(name).startswith("test_"):
            skipped["시험"] += len(hits)
        elif os.path.basename(name) == "demo.py" or name.endswith("_demo.py"):
            skipped["데모"] += len(hits)
        elif hits:
            try:
                defs = [x for x in ast.walk(ast.parse(src))
                        if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))]
            except SyntaxError:                 # 반쯤 쓴 파일 — 이름을 못 붙인다 · 계약과 갈린다
                defs = []
            # `ast.walk`는 바깥부터 돈다 — 마지막으로 감싸는 것이 가장 안쪽 함수다.
            prod[name] = [([x.name for x in defs if x.lineno <= ln <= x.end_lineno]
                           or ["<모듈>"])[-1] for ln in hits]
    return prod, skipped


# G17′-a의 계약 — `memory.py` 0 · `prototype/` 제품 전체 1(이 한 자리). 다른 모양이면 종료 1.
G17A_EXPECT = ["summarize.py:rewrite_lifetime"]


def _g17a_check(root=None):
    """G17′-a 판정 — (출력 한 줄, 위반 목록). `memory.py` 0과 제품 전체를 **따로** 가른다."""
    prod, skipped = _count_prod_digest_insert(root)
    n_mem = len(prod.get("memory.py", []))
    where = sorted(f"{f}:{fn}" for f, fns in prod.items() for fn in fns)
    bad = []
    if n_mem != 0:
        bad.append(f"G17′-a: prototype/memory.py의 digest INSERT {n_mem}건 (계약 0)")
    if where != G17A_EXPECT:
        bad.append(f"G17′-a: prototype/ 제품의 digest INSERT {where} (계약 {G17A_EXPECT})")
    line = (f"  G17′-a  동결 digest 쓰기 — `prototype/memory.py` {n_mem}건 (계약 0) ·"
            f" `prototype/` 제품 {len(where)}건 {where} (계약 1) · 뺀 것: 시험"
            f" {skipped['시험']}건 · 데모 {skipped['데모']}건   {'✅' if not bad else '🔴 발화'}")
    return line, bad


# ── 재료 ─────────────────────────────────────────────────────────────────
def summaries():
    """`SUMMARY_LOCAL.json`의 깊이-1 세션 요약 — `(sid, text)`를 sid 순으로."""
    with open(os.path.join(HERE, "data", "SUMMARY_LOCAL.json"), encoding="utf-8") as f:
        d = json.load(f)
    ks = sorted(k for k in d if k.startswith("qwen3:8b:s:S"))
    return [(k.rsplit(":", 1)[1], d[k]) for k in ks]


def baseline_line():
    """계획서가 지정한 고정물의 그 줄. **읽는다 — 옮겨 적지 않는다** (G11)."""
    with open(BASELINE_FILE, encoding="utf-8") as f:
        return f.read().splitlines()[BASELINE_LINE - 1].strip()


# ── 1. 토큰 기준선 ───────────────────────────────────────────────────────
def plant(m, n, sums):
    """`digest`에 요약 `n`행을 심는다. 심은 `kind` 목록을 돌려준다.

    컬럼 목록을 적는다 — 위치 기반 5-값 INSERT가 이 저장소에서 여섯 곳에
    있고(계획서 S5), 그것이 G6이 컬럼 추가를 막는 이유다. 새로 쓰는 자리를
    같은 함정에 넣지 않는다.
    """
    rows = PLANT_KINDS[:n]          # ← 음성 대조 ①이 여기의 `n`을 `2`로 바꾼다
    for i, kind in enumerate(rows):
        m.db.execute(
            "INSERT INTO digest (chat_id, kind, content, covers_to_seq,"
            " session_end_note) VALUES (?,?,?,?,?)",
            (CHAT, kind, sums[i][1], 0, None))
    m.db.commit()
    return rows


def run_b(corpus, ledger, n, sums, tmpdir):
    """`b = n`짜리 DB를 새로 만들어 720턴을 replay한다.

    쓰기 경로는 `soak.ingest(timed=True)` 그대로다 — 기준선(`b=0`)이 그
    경로로 만들어졌고, **다른 경로로 잰 값은 동일성 대조에 못 쓴다.**
    """
    dbf = os.path.join(tmpdir, f"digest-budget-b{n}.db")
    m = Memory(dbf)
    soak.seed(m)
    soak.ingest(m, corpus, ledger)
    kinds = plant(m, n, sums)
    _, toks, _, _ = soak.replay(m, corpus)
    blocks = _observed_blocks(m, corpus)
    m.db.close()
    os.remove(dbf)
    return toks, kinds, blocks


def _observed_blocks(m, corpus):
    """`b`는 손잡이가 아니라 **관측량**이다. 심은 수가 아니라 **착지값**을 센다.

    ⚠️ 이것은 **replay가 끝난 뒤의** 착지값이다. replay 도중 관계 전이가 나면
       `_propagate_transition`이 `digest` 키를 stale로 찍고 그 블록이 주입에서
       빠지므로, 심은 수와 여기가 갈릴 수 있다. **갈리면 그것이 신호다** —
       p50이 심은 행 수를 안 따라간 이유를 여기서 먼저 본다.
       (replay 전에 재면 `build_context`의 부작용이 replay를 오염시킨다.)
    """
    row = next(r for r in corpus if r["role"] == "user")
    ctx = m.build_context(CHAT, row["text"], row["seq"])
    return sum(1 for b in ctx.blocks if b.name.startswith("digest:"))


def token_baseline(corpus, ledger, sums, tmpdir):
    print("-" * W)
    print("1. 토큰 기준선 — 축은 `b`(주입된 `digest:` 블록 개수) · 단위 **ntok**")
    print("-" * W)
    print("  🔴 `ctx.tokens`는 `Block.tokens` = `ntok()`의 합이라 **ntok 단위**다.")
    print("     `LLM_NUM_CTX`로 나눈 백분율은 여기에 **없다** — 단위가 섞인 수다 (G15).")
    print("  재현: PYTHONIOENCODING=utf-8 python -B experiments/digest_budget.py")
    print(f"  DB는 저장소 밖: {tmpdir}\n")

    rows = []
    for n in B_AXIS:
        toks, kinds, obs = run_b(corpus, ledger, n, sums, tmpdir)
        rows.append(dict(b=n, obs=obs, kinds=kinds,
                         p50=soak.pct(toks, 50), p95=soak.pct(toks, 95),
                         mx=max(toks), n=len(toks)))

    print(f"  {'심은 행':>7} {'관측 b':>7} {'p50':>8} {'p95':>8} {'max':>8}"
          f"   심은 kind")
    print("  " + "-" * 68)
    for r in rows:
        note = "  ← b=2 기준선 (lifetime + session = 오늘의 모양)" \
            if r["b"] == B_BASE else ""
        print(f"  {r['b']:>7} {r['obs']:>7} {r['p50']:>6} ntok {r['p95']:>6} ntok"
              f" {r['mx']:>6} ntok   {','.join(r['kinds']) or '(없음)'}{note}")
    print(f"\n  분모는 턴 {rows[0]['n']}개(user)의 `ctx.tokens` 분포다 (G15).")

    base = next(r for r in rows if r["b"] == B_BASE)["p50"]
    print(f"\n  **b=2 기준선 p50 = {base} ntok** — 이후 모든 ≤20% 판정의 분모다.")

    # ── 동일성 대조 (b=0) ──
    b0 = next(r for r in rows if r["b"] == 0)
    ref = baseline_line()
    print("\n  ── b=0 동일성 대조 ──")
    print(f"  이번 실행 : p50 {b0['p50']}tok · p95 {b0['p95']}tok · max {b0['mx']}tok")
    print(f"  고정물    : {ref}")
    print("             `experiments/data/baseline/G2-soak.txt:35`")
    mine = f"p50 {b0['p50']}tok · p95 {b0['p95']}tok · max {b0['mx']}tok"
    same = (mine == ref)
    print(f"  → {'✅ 일치' if same else '🔴 불일치'} — soak의 `digest`는 0행이므로"
          " b=0이 곧 기준선이다.")
    if not same:
        print("     🔴 기준선이 재현되지 않았다. 이 표의 나머지 값은 그 기준선을")
        print("        분모로 쓰므로 **함께 의심해야 한다.**")

    # ── 음성 대조 ① — 인접 차이 ≠ 0 ──
    five = [r for r in rows if r["b"] >= 1]
    diffs = [five[i + 1]["p50"] - five[i]["p50"] for i in range(len(five) - 1)]
    print("\n  ── 인접 차이 (음성 대조 ①이 겨냥하는 검사) ──")
    for i, d in enumerate(diffs):
        print(f"  b={five[i]['b']} → b={five[i+1]['b']} : {d:+} ntok"
              f"   {'🔴 차이 0' if d == 0 else 'ok'}")
    flat = [d for d in diffs if d == 0]
    if flat:
        print(f"  🔴 **발화** — 인접 차이가 0인 구간이 {len(flat)}개다. `b`가 축으로")
        print("     움직이지 않았다는 뜻이고, 그러면 이 표는 게이트에 대해")
        print("     아무 말도 하지 못한다. (심는 행 수가 무시되면 이렇게 된다)")
    else:
        print("  ✅ 다섯 값이 서로 다르다 — `b`가 실제로 움직이는 축이다.")

    # ── 게이트: 예언하지 않는다 ──
    print(f"\n  ── 게이트: p50 > b=2 기준선 × {GATE} = {base * GATE:.1f} ntok ──")
    print("  🔴 어느 `b`에서 넘는지는 **출력이 말한다.** 미리 적지 않았다 (R6).")
    over = []
    for r in rows:
        if r["b"] <= B_BASE:
            continue
        ratio = r["p50"] / base
        hit = ratio > GATE
        over.append(hit)
        print(f"  b={r['b']}: p50 {r['p50']} ntok / {base} ntok = {ratio:.3f}배"
              f"   {'🔴 넘는다' if hit else '안 넘는다'}")
    first = next((r for r in rows
                  if r["b"] > B_BASE and r["p50"] / base > GATE), None)
    if first:
        print(f"  → **처음 넘는 지점은 b={first['b']}이다.** 게이트는 상수가 아니고,")
        print("     이 축 위에서 실제로 판정을 한다.")
    else:
        print("  → **b=5까지 어느 값도 1.2배를 넘지 않는다.**")
        print("     그러면 이 게이트는 이 축 위에서 **항등 지표**다 —")
        print("     게이트를 폐기하고 그 사실을 적는다 (G14).")

    _gate_verdict(rows, base, first, diffs)
    return rows, same, bool(flat)


def _gate_verdict(rows, base, first, diffs):
    """
    🔴 **S0이 남긴 관측을 판정한다 (단계 S3).**

    S0은 «어느 `b`에서 넘는지»까지 재고 멈췄다. 그 값과 **오늘의 기본 설정**을
    나란히 놓으면 한 줄이 더 나온다 — `b`는 손잡이가 아니라 M의 상(像)이고
    (`b ≤ |digest 행| + M ≤ 2 + M`, G19′②), M=1이면 `b`는 3을 못 넘는다.
    **처음 넘는 지점이 4라면 기본 설정에서 이 게이트는 무조건 초록이다.**

    시나리오 1이 예언한 «무조건 빨강»의 거울상이고, P5가 **같은 무게로** 세는
    결함이다: *"발화할 수 없는 검사와 무조건 발화하는 검사를 둘 다 결함으로 센다."*
    """
    print("\n  ── 🔴 게이트 판정 — S0이 남긴 관측 (단계 S3) ──")
    m_now = memory.DIGEST_INJECT_MAX
    b_max = 2 + m_now                     # |digest 행| ≤ 2 (G17′-a가 묶는다)
    print(f"  `b`는 손잡이가 아니라 M의 상이다: `b ≤ |digest 행| + M ≤ 2 + M`"
          f" (G19′②)")
    print(f"  오늘 `DIGEST_INJECT_MAX` = {m_now} → **기본 설정에서 `b` ≤ {b_max}**")
    if first is None:
        print("  이 실행에서는 어느 `b`도 문턱을 안 넘었다 — 위 G14 분기가 답이다.")
        return
    m_need = first["b"] - 2
    reachable = first["b"] <= b_max
    print(f"  처음 넘는 지점 b={first['b']} → 그 지점에 닿으려면"
          f" **M ≥ {m_need}**가 필요하다")
    if reachable:
        print(f"  → ✅ 기본 설정에서 이 게이트는 **도달 가능**하다 (M={m_now} ≥"
              f" {m_need}). 판정할 것이 없다.")
        return

    span = sorted(diffs)[len(diffs) // 2] if diffs else 0
    head = base * GATE - base
    print(f"  → 🔴 **기본 설정에서 이 게이트는 발화할 수 없다.** M={m_now} <"
          f" {m_need}이므로 `b`가 {first['b']}에 닿는 경로가 없다.")
    print(f"     여유는 {head:.1f} ntok이고 블록 하나의 한계 비용은"
          f" 중앙값 {span} ntok이다 → **여유 = {head / span:.2f}블록**.")
    print("       ⚠️ 이것은 «무조건 빨강»의 거울상이고 P5가 **같은 무게로** 센다.")
    print("     판정 — 셋 중 하나를 고른다. **통과하도록 고르지 않는다.**")
    print("       ⛔ 폐기: 안 한다. 이 게이트는 **축 위에서는 실제로 발화한다**"
          f"(b={first['b']}에서). 항등이 아니라 «오늘의 M이 닿지 않는» 것이다.")
    print("       ⛔ 문턱 재유도: 안 한다. 1.2에 유도가 없고, 발화하도록 문턱을")
    print("          고르는 것이 P5가 이름으로 금지한 바로 그 행위다.")
    print(f"       ✅ **M을 축에 올린다** — 게이트의 주어를 `b`에서 **M**으로")
    print(f"          바꿔 적는다. 이 표가 실제로 산 값은 «블록 하나의 한계 비용»")
    print(f"          {span} ntok이고, 거기서 나오는 계약은 **M ≤ {m_need - 1}**이다")
    print(f"          (M={m_need}부터 b={first['b']}가 되어 1.2배를 넘는다).")
    print("     🔴 그래서 **기본 설정의 토큰 계약을 실제로 지는 것은 이 1.2배 줄이")
    print("        아니라 G19′②(`b ≤ 2+M`)다** — 그쪽은 심을 위반이 있고 발화한다.")
    print(f"     🔓 이 게이트가 살아나는 조건: `DIGEST_INJECT_MAX ≥ {m_need}`.")
    print("        그 값을 올리는 사람이 이 줄을 다시 읽는다.")


# ── 2. 저울 대조 ─────────────────────────────────────────────────────────
def scale_check(sums):
    print("\n" + "-" * W)
    print("2. 저울 대조 — `ntok` 추정 vs 실측 `prompt_eval_count`")
    print("-" * W)
    joined = "\n".join(f"[{sid}] {txt}" for sid, txt in sums)
    est = ntok(joined)

    probe = joined                # ← 음성 대조 ②가 여기를 **반으로 자른다**

    print("  재현: 이 스크립트. ollama 생성 **1토큰 1회**"
          f" (`num_predict=1` · `num_ctx={llm.LLM_NUM_CTX}` ·"
          f" `temperature={llm.LLM_TEMPERATURE}` · `seed={llm.LLM_SEED}`)")
    print(f"        호스트 {llm.OLLAMA_HOST} — `localhost`가 아니다 (F38)\n")

    raw = llm.measure_prompt(probe, num_predict=1)   # 🔄 측정 — 체크포인트를 안 채운다 · F40 가드가 막지 않는다
    use = llm.last_usage()
    meas = use.get("prompt_eval_count")
    if not meas:
        print("  🔴 `prompt_eval_count`가 응답에 없다. 저울을 못 만든다.")
        print(f"     응답 사용량: {use}")
        return None

    n = len(sums)
    print(f"  세션요약 {n}개: 글자 {len(probe):,} · ntok 추정 {est:,} ntok"
          f" · 실측 prompt_eval_count {meas:,} tok")
    if len(probe) != len(joined):
        print(f"  ⚠️ 저울에 실제로 보낸 문자열이 원본과 다르다 —"
              f" 보낸 글자 {len(probe):,} vs 원본 {len(joined):,}")
    ratio = est / meas
    print(f"  → 배율 = {est:,} ntok / {meas:,} tok = **{ratio:.3f}**"
          f"   (`ntok`이 이만큼 과대계상한다)")
    bare = sum(ntok(t) for _, t in sums) / n
    print(f"  세션요약 1개: 실측 {meas / n:.0f} tok / 추정 {est / n:.0f} ntok"
          f" (이은 문자열 ÷ {n})")
    # ⚠️ 같은 양에 두 수가 있다. 이은 문자열은 `[S01] ` 접두와 줄바꿈을 포함하므로
    #    나눈 값이 **맨 요약의 평균보다 크다.** 계획서 S3의 213 ntok은 맨 요약
    #    쪽이다. 두 수를 나란히 찍는다 — 하나만 찍으면 다음 사람이 다른 쪽
    #    기록과 비교하고 «저울이 움직였다»고 읽는다.
    print(f"                맨 요약 ntok 평균 {bare:.0f} ntok"
          " (접두·줄바꿈 없음 — 계획서 S3이 적은 쪽)")
    print(f"  글자당: 실측 {meas / len(joined):.4f} tok/글자"
          f" (`ntok`의 가정은 1.5)")
    print(f"  캐시: prompt_eval_cached_count = {use.get('prompt_eval_cached_count')}"
          " — 캐시가 걸려도 `prompt_eval_count`는 **프롬프트 전체 길이**다 (S13-b)")
    print(f"  done_reason = {use.get('done_reason')!r} · eval_count ="
          f" {use.get('eval_count')}")

    # N=24 합 — 🔴 실측끼리만 나눈다 (G15)
    per = meas / n
    n24 = per * 24
    print(f"\n  N=24(`DIGEST_KEEP_SESSIONS`) 합: 실측 {n24:,.0f} tok"
          f" = `LLM_NUM_CTX` {llm.LLM_NUM_CTX:,} tok 의"
          f" {n24 / llm.LLM_NUM_CTX * 100:.1f}%"
          f" (여유 {100 - n24 / llm.LLM_NUM_CTX * 100:.0f}%)")
    print("  🔴 이 나눗셈의 분자·분모는 **둘 다 실측 tok**이다. `ntok` 판본을")
    print("     `LLM_NUM_CTX`로 나누는 줄은 이 파일 어디에도 없다 (G15 · S17).")

    # 비교 기준과의 대조 — 계산에는 안 쓴다
    dev = abs(ratio / REC_RATIO - 1)
    print(f"\n  ── 기록({REC_RATIO})과의 대조 — 밴드 ±{RATIO_BAND * 100:.0f}% ──")
    print(f"  이번 배율 {ratio:.3f} vs 기록 {REC_RATIO} → 이탈 {dev * 100:.1f}%")
    if dev > RATIO_BAND:
        print(f"  ⚠️ **경고 발화** — 배율이 기록과 {dev * 100:.1f}% 어긋난다.")
        print("     같은 코퍼스·같은 모델이면 이만큼 움직일 이유가 없다. 저울에")
        print("     들어간 것이 기록과 **같은 문자열인지** 먼저 의심하라.")
        print("     (막지는 않는다 — 이 줄이 숫자 옆에 붙는 것이 이 검사의 전부다)")
    else:
        print("  ✅ 밴드 안. 이 실행의 저울은 기록과 같은 조건이다.")

    print(f"\n  ⚠️ 절편 주의 (S23 · U10): 이 배율은 **비례상수가 아니다.**")
    print(f"     두 길이 회귀로는 한계 비율 {REC_TOK_PER_CHAR} tok/글자 +"
          " **고정 오버헤드와 곡률의 합 ≲ 8토큰**이고,")
    print("     점이 둘이면 잔차가 없어 비선형성을 탐지할 수 없다. 단순비는 그")
    print("     절편을 내용에 섞어 0.6% 과대추정하며 **편향이 N 유도에 안전한 쪽**이다.")
    print("     🔴 그래서 이 수를 코드에 상수로 박지 않는다 — 위 둘은 비교 기준일 뿐이다.")
    return dict(ratio=ratio, meas=meas, est=est, chars=len(probe),
                fired=dev > RATIO_BAND, raw=raw)


# ── 3. M2 상한 대조군 ────────────────────────────────────────────────────
def m2_control(sums, ledger):
    print("\n" + "-" * W)
    print("3. M2 상한 대조군 — `survived_v2`를 **세 열**로 (ollama 0회)")
    print("-" * W)
    text = "\n".join(f"[{sid}] {t}" for sid, t in sums)
    sids = {sid for sid, _ in sums}
    events = ledger["events"]

    inside = [e for e in events if (e.get("at") or {}).get("session") in sids]
    outside = [e for e in events if e not in inside]
    t_in = [e["text"] for e in inside]
    t_out = [e["text"] for e in outside]
    t_all = [e["text"] for e in events]

    v_in = scoring.survived_v2(text, t_in)
    v_out = scoring.survived_v2(text, t_out)
    v_all = scoring.survived_v2(text, t_all)
    f_all = scoring.survived_frozen(text, t_all)
    heavy = [e["text"] for e in events if e.get("emotional_weight", 0) >= 0.8]
    v_heavy = scoring.survived_v2(text, heavy)

    span = f"{min(sids)}–{max(sids)}"
    print(f"  재료 = `SUMMARY_LOCAL.json`의 깊이-1 세션 요약 {len(sums)}개"
          f" (구간 {span})")
    print(f"  항목 = `eval/fact-ledger.yaml`의 `events` {len(events)}개 (읽기만 — A8)")
    print("  재현: 이 스크립트. **ollama 0회**\n")

    print(f"  ① 재료 안 회수      : {len(v_in.survived)}/{len(t_in)}"
          f"   (구간 {span} 안의 사건 {len(t_in)}개)")
    for e in inside:
        mark = "생존" if e["text"] in v_in.survived else "비생존"
        print(f"       [{mark}] {e['id']} {e['at']['session']} {e['text']}")
    print(f"  ② 재료 밖 위양성    : {len(v_out.survived)}건"
          f"   (구간 밖 사건 {len(t_out)}개 중)")
    for e in outside:
        if e["text"] not in v_out.survived:
            continue
        roots = scoring._clean_roots(e["text"])
        shared = roots & scoring._clean_roots(text)
        print(f"       🔴 {e['id']} {e['at']['session']} {e['text']}")
        print(f"          정제 어근 {sorted(roots)} 중 겹친 것"
              f" {sorted(shared)} → {len(shared)}/{len(roots)}"
              f" = {len(shared) / len(roots) * 100:.0f}% ≥ 50%")
        print(f"          `UBIQUITOUS` = {sorted(scoring.UBIQUITOUS)} 는 두 화자 중"
              " 하나만 뺀다 — 나머지 하나로도 통과한다")
    print(f"  ③ 참고: 전체 {len(t_all)}개 기준: v2 {len(v_all.survived)}/{len(t_all)}"
          f" · frozen {len(f_all)}/{len(t_all)}"
          f" · 판정불가 {len(v_all.unscorable)}"
          f" · w≥0.8 부분집합 {len(v_heavy.survived)}/{len(heavy)}")

    tot = len(v_all.survived)
    print(f"\n  🔴 이 {tot}/{len(t_all)}은 «채점기 상한»도 «재료 커버리지»도 아니다"
          " — **서로 다른 두 양의 합**이다:")
    print(f"     재료 안 회수 {len(v_in.survived)}/{len(t_in)}"
          f" + 재료 밖 어휘 위양성 {len(v_out.survived)}/{len(t_out)}"
          f" = {tot}.")
    print("     ②의 생존자는 **구성상** 재료에 없던 사건이다 — 회수가 아니다.")
    print("     커버리지는 재료 안의 수를 예측하지, 재료 밖 생존자를 예측하지 못한다.")
    print(f"  🔴 이 값은 **{len(sums)}세션 기록물의 것**이다. 이 라운드 재료"
          " (24세션)의 상한이 **아니다** — X6.")
    print("     24세션을 덮는 요약이 생기면 사건 10개가 전부 재료 안에 들어오고,")
    print("     그 조건의 상한은 그 요약이 존재해야만 잴 수 있다.")
    print("  🔴 채점기가 재는 것은 «요약이 사건을 담았는가»가 아니라")
    print("     «요약이 대장과 낱말을 나눠 쓰는가»다 — 의역은 놓치고(위음성),")
    print("     어근 둘만 겹쳐도 잡는다(위양성). 위 ②가 그 실례다.")
    return dict(inside=len(v_in.survived), n_in=len(t_in),
                fp=len(v_out.survived), n_out=len(t_out), total=tot)


# ── 4. 부채 예산 — U6이 «한 번도 안 쟀다»고 적은 자리 ────────────────────
#
# G19′가 이 자리를 **이름으로 지목**했다: *"전량 주입되는 테이블은 ① 채팅당 행
# 수 상한이 코드에 있고 ② 주입 상한이 저장 상한과 **별개 이름**이어야 한다."*
# 전량 주입 자리는 둘(`digest`·`debt`)이고 위 1·4절이 `digest` 쪽이다.
# 이 절이 **`debt` 쪽을 처음으로 잰다.**
#
# 🔴 **재는 것이지 고치는 것이 아니다.** ADR-016 §미해결 U6은 *"이 라운드는 안
#    고친다"*이고, 그래서 `prototype/memory.py`는 한 줄도 안 건드린다. 여기서
#    나오는 것은 «상한»이 아니라 «상한을 걸 자리의 실측»이다.
#    🔄 **wave4가 `memory.py`의 부채 판정을 고쳤다** — 백오프가 세션 경계로 세지고,
#       `trigger_kind`가 갈리고, `paid`로 가는 길이 생겼다. **행 수 상한은 여전히 없다**
#       (이 절이 재는 축). 그래서 이 절은 여전히 측정이고, 바뀐 것은 셋이다: 그림자가
#       새 판정을 따라가고, 경계 행을 쓰고(백오프가 그것을 센다), 대장의 spec을 심는다.
#
# 앞선 검증자가 적은 것 — *"`debt`는 «상한이 없는 테이블»이 아니라 «다른 종류의
# 상한을 가진 테이블»이다"* — 은 `due_debts`를 읽으면 참이다. 셋이 있다:
# 백오프 창 · `session_start` 게이트 · `attempt_count ≥ 3` 소멸.
# 🔴 **그런데 셋 다 «행 하나가 얼마나 자주 주입되는가»의 상한이고, «행이 몇 개인가»
#    의 상한이 아니다.** G19′가 요구한 축은 후자다. 이 절이 그 둘을 갈라 잰다.

DEBT_CHAT = "chat-debt"          # 위 `G19_CHAT`과 같은 이유로 이름을 가른다
DEBT_K_AXIS = [1, 2, 5, 10, 50, 100]
DEBT_U6_COND = 5                 # ADR-016 U6이 적은 «열리는 조건»의 수


def _debt_db(tmpdir, name):
    """`build_context`가 도는 최소 상태. `digest` 행은 **안 넣는다** — 이 절의
    관측량은 `debt` 블록 하나뿐이고, 요약 블록은 잡음이다.
    🔄 wave4: 세션 경계 행(`_end_session`)은 넣는다 — 부채 백오프가 그 행을 센다.
    그 행이 만드는 요약 블록은 이 절이 안 본다(`_debt_lines`는 `debt` 블록만 센다)."""
    m = Memory(os.path.join(tmpdir, name))
    db = m.db
    db.execute("INSERT INTO character_version (character_id, version,"
               " persona_text, speech_rules, taboos) VALUES (?,?,?,?,?)",
               ("seojun", 1, "페르소나", "반말", "금기"))
    db.execute("INSERT INTO chat (chat_id, user_id, character_id,"
               " character_version) VALUES (?,?,?,?)",
               (DEBT_CHAT, "jiwoo", "seojun", 1))
    db.execute("INSERT INTO relationship (chat_id, stage, affinity, called_as,"
               " user_locked, updated_by_turn) VALUES (?,?,?,?,?,?)",
               (DEBT_CHAT, "연인", 84, "지우", 0, 0))
    db.commit()
    return m


def _plant_debt(m, content, setup_seq, kind, spec=None, stake=0.5):
    """`apply_meta`의 `new_debt` 분기와 **같은 컬럼 목록**으로 심는다."""
    m.db.execute(
        "INSERT INTO debt (chat_id, content, setup_turn_seq, trigger_kind,"
        " trigger_spec, trigger_clock, emotional_stake) VALUES (?,?,?,?,?,?,?)",
        (DEBT_CHAT, content, setup_seq, kind, spec, "session", stake))


def _end_session(m, k, first_seq, last_seq):
    """세션 k가 끝났다 — 요약 층이 남기는 한 행(내용은 대역). 부채 백오프가 이 행을 센다."""
    m.put_session_digest(DEBT_CHAT, f"S{k:02d}", "(경계 대역)",
                         covers_from_seq=first_seq, covers_to_seq=last_seq)


def _debt_lines(ctx):
    """주입된 **행 수**. 🔴 블록 수가 아니다.

    `build_context`의 부채 주입부는 `"\\n".join(...)`으로 **행이 몇이든 블록을
    하나** 만든다. 그래서 `digest` 쪽에서 쓰던 «블록 수»(`_b_of`)를 그대로
    가져오면 이 축은 언제나 1이고 **증가를 볼 수 없다.** 같은 이름의 관측량이
    두 테이블에서 다른 것을 세는 자리다 — G15가 이름을 붙이라고 한 이유.
    """
    return sum(len(b.text.splitlines()) for b in ctx.blocks if b.name == "debt")


def _debt_ntok(ctx):
    return sum(b.tokens for b in ctx.blocks if b.name == "debt")


# ── 그림자 판정기 ────────────────────────────────────────────────────────
#
# 🔴 `due_debts`의 **어느 분기가 발화했는지**는 반환값에 안 남는다 — `continue`
#    셋이 전부 «빈 손»으로 같아 보인다. 계측을 위해 `memory.py`를 고치는 것은
#    U6이 금지한 수리이므로, 대신 **같은 술어를 실험 쪽에서 다시 판정**하고
#    그림자가 실제 경로와 매 턴 **같은 집합을 내는지 대조**한다.
#    → 카운트는 그림자에서 나오고, **그림자의 자격은 대조가 준다.**
#    대조가 0이 아니면 카운트는 폐기한다 (그 아래 심을 위반 셋이 이 대조를
#    실제로 발화시킨다 — «발화할 수 없는 검사»로 태어나지 않기 위해).

def _debt_shadow(m, rows, now_seq, session_start,
                 backoff_tab=(1, 3, 7), gate_on=True, expire_at=3, trigger_on=True):
    """`due_debts`의 분기를 그대로 다시 판정한다. (통과 content 목록, 카운트).

    🔄 wave4 — 백오프는 **세션 경계**로 세고(옛: `now_seq - last`를 `WINDOW_TURNS` 배수와
    비교), 게이트와 소멸 사이에 **트리거 조건**(`time`의 `Nd` · 세션 시계)이 들어갔다.
    경계 수의 원천은 실 경로와 같은 `Memory.session_boundaries_since`다 — 원천까지
    그림자에 옮기면 두 쪽이 같은 오류를 따로 갖는다. 그림자가 다시 판정하는 것은 분기다.
    """
    import re
    c = dict(backoff=0, gate=0, trigger=0, expire=0, passed=0)
    out = []

    def since(seq):
        n = m.session_boundaries_since(DEBT_CHAT, seq - 1)
        return max(n, 1 if session_start and seq < now_seq else 0)

    for r in rows:
        b = backoff_tab[min(r["attempt_count"], 2)]
        last = r["last_attempted_seq"] or r["setup_turn_seq"]
        if since(last) < b:
            c["backoff"] += 1
            continue
        if gate_on and r["trigger_kind"] == "session_start" and not session_start:
            c["gate"] += 1
            continue
        days = (re.fullmatch(r"(\d+)d", r["trigger_spec"] or "")
                if r["trigger_kind"] == "time" else None)
        if (trigger_on and days and r["trigger_clock"] == "session"
                and int(days.group(1)) <= memory.DIGEST_KEEP_SESSIONS
                and since(r["setup_turn_seq"]) < int(days.group(1))):
            c["trigger"] += 1
            continue
        if r["attempt_count"] >= expire_at:
            c["expire"] += 1
            continue
        c["passed"] += 1
        out.append(r["content"])
    return out, c


def _ledger_debts(ledger, corpus):
    """대장의 `debts` 넷을 `(content, setup_seq, kind, spec)`로. 좌표 변환은 `soak.ingest`와 같다.
    🔄 wave4: spec도 옮긴다(`meta_arm.Mock`과 같은 규칙 — `spec`이 없으면 `after`) — 이제 판정이
    spec을 읽는다. 전에는 안 읽었으므로 옮기지 않아도 값이 같았다."""
    seq_of = {(r["session"], r["turn"]): r["seq"] for r in corpus}
    out = []
    for d in ledger.get("debts", []):
        s = d.get("setup") or {}
        t = d.get("trigger") or {}
        spec = t.get("spec", t.get("after"))
        out.append((d["content"], seq_of.get((s.get("session"), s.get("turn")), 0),
                    t.get("kind", "session_start"), None if spec is None else str(spec)))
    return out


def _debt_replay(tmpdir, tag, corpus, seeds, late=0, **shadow_kw):
    """720턴을 지나며 저장·주입·분기 카운트를 함께 모은다.
    🔄 wave4: 끝난 세션의 경계 행을 새 세션의 `late`번째 행 **앞에서** 쓴다 — 0이면 첫 행
    앞(요약 층이 제때 돈다), 1이면 한 행 늦게(세션 첫 턴에는 카운터가 그 경계를 모른다)."""
    m = _debt_db(tmpdir, f"debt-{tag}.db")
    for content, seq, kind, spec in seeds:
        _plant_debt(m, content, seq, kind, spec)
    m.db.commit()

    tot = dict(backoff=0, gate=0, trigger=0, expire=0, passed=0)
    opens, lines, mismatch, stuck = [], [], 0, 0
    sess, first, prev, pending, into = 0, None, None, None, 0
    for r in corpus:
        if r["turn"] == 1 and first is not None:
            sess += 1
            pending, first, into = (sess, first, prev), None, 0
        if pending and into >= late:
            _end_session(m, *pending)
            pending = None
        first = r["seq"] if first is None else first
        prev, into = r["seq"], into + 1
        if r["role"] != "user":
            continue
        ss = (r["turn"] == 1)
        rows = m.db.execute("SELECT * FROM debt WHERE chat_id=? AND status='open'",
                            (DEBT_CHAT,)).fetchall()
        opens.append(len(rows))
        # 🔴 «소멸에 걸렸어야 하는데 아직 open인» 행-턴. 소멸 분기가 백오프·게이트
        #    **뒤에** 있어서 생기는 양이다. 소멸 발화 횟수와 나란히 놓는다.
        stuck += sum(1 for x in rows if x["attempt_count"] >= 3)
        pred, c = _debt_shadow(m, rows, r["seq"], ss, **shadow_kw)
        for k in tot:
            tot[k] += c[k]
        ctx = m.build_context(DEBT_CHAT, r["text"], r["seq"], session_start=ss)
        got = [ln[2:] for b in ctx.blocks if b.name == "debt"
               for ln in b.text.splitlines()]
        lines.append(len(got))
        if got != pred:
            mismatch += 1
    final = dict(m.db.execute(
        "SELECT status, COUNT(*) FROM debt WHERE chat_id=? GROUP BY status",
        (DEBT_CHAT,)).fetchall())
    m.db.close()
    return dict(tot=tot, opens=opens, lines=lines, mismatch=mismatch,
                stuck=stuck, final=final, n=len(opens))


def _debt_write_path(corpus, ledger, tmpdir):
    """ⓐ 코퍼스 경로에서 `debt` 행이 실제로 몇 개 생기나."""
    import inspect
    import re

    sig = list(inspect.signature(Memory.add_turn).parameters)
    has_meta = "meta" in sig
    src = inspect.getsource(Memory.apply_meta)
    in_apply = len(re.findall(r"INSERT INTO debt\b", src))
    with open(os.path.join(ROOT, "prototype", "memory.py"), encoding="utf-8") as f:
        in_file = len(re.findall(r"INSERT INTO debt\b", f.read()))

    dbf = os.path.join(tmpdir, "debt-soak.db")
    m = Memory(dbf)
    soak.seed(m)
    soak.ingest(m, corpus, ledger, timed=False)
    _, toks, _, _ = soak.replay(m, corpus)
    n_rows = m.db.execute("SELECT COUNT(*) FROM debt").fetchone()[0]
    n_open = m.db.execute("SELECT COUNT(*) FROM debt WHERE status='open'").fetchone()[0]
    m.db.close()
    os.remove(dbf)
    return dict(sig=sig, has_meta=has_meta, in_apply=in_apply, in_file=in_file,
                rows=n_rows, open=n_open, n=len(toks),
                ledger_debts=len(ledger.get("debts", [])))


def debt_budget(corpus, ledger, tmpdir, base_p50):
    print("\n" + "-" * W)
    print("5. 부채 예산 — `debt`의 «행 수»를 처음 잰다 (U6 · ollama 0회)")
    print("-" * W)
    print("  🔴 **측정이다. 수리가 아니다.** 이 절은 상한을 걸지 않고, **상한을 걸 자리의")
    print("     수**를 종료 코드와 무관하게 찍는다. 🔄 wave4가 `memory.py`의 부채 **판정**을")
    print("     고쳤다(백오프 = 세션 경계 · 트리거 분기 · `paid`) — **행 수 상한은 여전히 없다.**")
    print("  재현: PYTHONIOENCODING=utf-8 python -B experiments/digest_budget.py")
    print(f"  DB는 저장소 밖: {tmpdir}\n")

    # ── ⓐ 쓰기 경로 ──
    w = _debt_write_path(corpus, ledger, tmpdir)
    print("  ⓐ 코퍼스 경로 — 소크와 **같은 쓰기 경로**로 720턴을 통과시킨다")
    print(f"     `Memory.add_turn` 인자 = {w['sig']}"
          f" → `meta` 있는가? {'예' if w['has_meta'] else '**아니오**'}")
    print(f"     `INSERT INTO debt` — `prototype/memory.py` 전체 {w['in_file']}곳 ·"
          f" 그중 `apply_meta` 안 {w['in_apply']}곳")
    print(f"     → 유일한 쓰기 경로가 `apply_meta`인데 `soak.ingest`는 그것을"
          " 부르지 않는다")
    print(f"     실측: 720턴 ingest + {w['n']}개(user) replay 후"
          f" `debt` 전체 {w['rows']}행 · `status='open'` {w['open']}행")
    print(f"     대장 `eval/fact-ledger.yaml`의 `debts` = {w['ledger_debts']}개 —"
          " **하나도 테이블에 안 들어간다**")
    dead = (w["rows"] == 0)
    print(f"\n     🔴 그래서 U6이 적은 열리는 조건 — «soak 완주 시 열린 `debt`"
          f" 행의 최댓값이 {DEBT_U6_COND}를 넘는 순간» — 은")
    print(f"        {'**발화할 수 없다**' if dead else '발화 가능하다'}."
          f" 분자가 {w['rows']}이고, 그 {w['rows']}은 코퍼스가 작아서가 아니라")
    print("        **하니스에 부채를 만드는 호출이 없어서**다. 코퍼스를 720턴에서")
    print("        72,000턴으로 늘려도 이 수는 0이다 — 표본이 아니라 구조다.")

    # ── ⓑ·ⓒ 대장 넷을 심고 720턴 ──
    seeds = _ledger_debts(ledger, corpus)
    r = _debt_replay(tmpdir, "ledger", corpus, seeds)
    n = r["n"]
    ev = sum(r["tot"].values())
    print(f"\n  ⓑ 대장의 부채 {len(seeds)}개를 **심고** 같은 720턴을 지난다"
          f" (분모: user턴 {n}개)")
    print(f"     (kind, spec) = {[(k, s) for _, _, k, s in seeds]} · 세션 경계 행 = 세션마다 1")
    print(f"     저장 `status='open'` 행 수 : p50 {soak.pct(r['opens'], 50)} ·"
          f" p95 {soak.pct(r['opens'], 95)} · max {max(r['opens'])}   (n={n} 턴)")
    print(f"     주입 **행** 수            : max {max(r['lines'])} ·"
          f" 합 {sum(r['lines'])}행 / 주입된 턴 {sum(1 for x in r['lines'] if x)}개"
          f" (n={n})")
    print(f"     주입 **블록** 수          : max"
          f" {1 if max(r['lines']) else 0} — 🔴 행이 몇이든 블록은 하나다")
    print(f"     replay 종료 시 상태 = {r['final']}")
    print(f"\n     🔴 저장 max {max(r['opens'])}행 ≠ 주입 max {max(r['lines'])}행."
          " **두 수가 실제로 다르다** — G19′②가 «주입 상한과 저장 상한은")
    print("        별개 이름이어야 한다»고 적은 이유가 여기서 실측으로 보인다.")
    print(f"     🔴 그리고 max {max(r['opens'])}는 **{len(seeds)}개를 심었을 때의 값**이다."
          f" 심은 수의 상한이 아니라 심은 수 그 자체다 (n={n}, 심은 수"
          f" {len(seeds)}). 표본의 성질이지 구조의 성질이 아니다.")

    print(f"\n  ⓒ 세 상한이 실제로 문 횟수 — 분모는 **행-턴 평가** {ev}회"
          f" (open 행 × 그 턴, user턴 {n}개 위에서)")
    print(f"     ① 백오프 `{memory.DEBT_BACKOFF_SESSIONS}` **세션 경계**      "
          f" : {r['tot']['backoff']}회 / {ev}"
          f" = {r['tot']['backoff'] / ev * 100:.1f}%")
    print(f"     ② `trigger_kind=='session_start'` 게이트  "
          f" : {r['tot']['gate']}회 / {ev}"
          f" = {r['tot']['gate'] / ev * 100:.1f}%")
    print(f"     ②′ 트리거 조건 (`time`의 `Nd` · 세션 시계)  "
          f" : {r['tot']['trigger']}회 / {ev}"
          f" = {r['tot']['trigger'] / ev * 100:.1f}%   🔄 wave4 새 분기")
    print(f"     ③ `attempt_count >= 3` 소멸               "
          f" : {r['tot']['expire']}회 / {ev}"
          f" = {r['tot']['expire'] / ev * 100:.1f}%")
    print(f"     ④ 통과 → 주입                             "
          f" : {r['tot']['passed']}회 / {ev}"
          f" = {r['tot']['passed'] / ev * 100:.1f}%")
    print(f"     그림자 ↔ 실제 경로 불일치 : {r['mismatch']} / {n} 턴"
          f"   {'✅ 그림자가 실 경로와 같다' if not r['mismatch'] else '🔴 발화'}")
    # 🔄 wave4 — 경계 행이 제때 오면 게이트는 한 번도 안 문다(아래 설명). 그 분기를 재려면
    #    경계가 늦게 오는 판이 따로 있어야 하고, ⓓ의 게이트 위반도 거기서만 발화할 수 있다.
    rl = _debt_replay(tmpdir, "late", corpus, seeds, late=1)
    evl = sum(rl["tot"].values())
    print(f"     ⓒ′ 경계 행이 **한 행 늦게** 올 때 (행-턴 {evl}회): ① {rl['tot']['backoff']}"
          f" · ② 게이트 {rl['tot']['gate']} · ②′ {rl['tot']['trigger']}"
          f" · ③ {rl['tot']['expire']} · ④ {rl['tot']['passed']}"
          f" · 불일치 {rl['mismatch']}/{rl['n']}")
    print("        🔴 제때 오는 경계에서 게이트가 0회인 이유 — 백오프를 경계 행으로 세므로 백오프가")
    print("           풀리는 첫 평가가 곧 새 세션의 첫 턴이다. 게이트가 무는 것은 경계 행이")
    print("           세션 **중에** 쓰일 때(요약 층 지연)뿐이다. 🔄 옛 판정(턴)에서는 40회였다.")
    zero = [k for k in ("backoff", "gate", "trigger", "expire")
            if r["tot"][k] == 0 and rl["tot"][k] == 0]
    if zero:
        print(f"     🔴 한 번도 안 문 상한: {zero} — «있다»고 말할 수 없다")
    else:
        print("     ✅ 넷 다 이 코퍼스에서 실제로 물었다")
    print(f"\n     🔴 ③은 {r['tot']['expire']}회인데, «`attempt_count ≥ 3`인데 아직"
          f" `open`»인 행-턴은 **{r['stuck']}회**다 ({r['stuck'] / ev * 100:.1f}%).")
    print("        소멸 분기가 백오프·게이트 **뒤에** 있어서 생기는 간극이다 —")
    print("        `continue` 둘이 먼저 걸리면 그 턴은 소멸에 **도달하지 못한다.**")
    print("        즉 ③은 «즉시 소멸»이 아니라 «다음에 평가에 도달하면 소멸»이다.")

    # ── ⓓ 심을 위반 — 그림자 대조가 실제로 발화하는가 ──
    print("\n  ⓓ 심을 위반 — 그림자의 네 분기를 하나씩 흔들면 위 대조가 발화하는가")
    print("     (🔴 조용한 쪽을 위에 두었다: 흔들지 않은 판이 0/%d다 — P5)" % n)
    plants = [
        ("① 백오프를 `[1,1,1]`로", dict(backoff_tab=(1, 1, 1))),
        ("② 게이트 제거 (경계 한 행 늦게)", dict(gate_on=False, late=1)),
        ("②′ 트리거 조건 제거", dict(trigger_on=False)),
        ("③ 소멸 문턱 3 → 4", dict(expire_at=4)),
    ]
    fired = 0
    # ⚠️ 태그는 **인덱스**로 만든다. 라벨의 한 글자를 쓰면 셋이 같은 파일명이
    #    되고, 두 번째 판이 첫 판의 DB를 다시 열어 UNIQUE로 죽는다 (실제로 겪었다).
    for i, (label, kw) in enumerate(plants):
        p = _debt_replay(tmpdir, f"v{i}", corpus, seeds, **kw)
        hit = p["mismatch"] > 0
        fired += hit
        print(f"     {label:<28} 불일치 {p['mismatch']:>3}/{n}"
              f"   {'🔴 발화' if hit else '✅ 조용 — **이것이 결함이다**'}")
    ok_d = (fired == len(plants) and r["mismatch"] == 0 and rl["mismatch"] == 0)
    print(f"     → 심은 위반 {fired}/{len(plants)}개가 발화하고, 안 심은 판은"
          f" {r['mismatch']}건 · 늦은 판 {rl['mismatch']}건이다."
          f"   {'✅ 이 대조는 발화할 수 있다' if ok_d else '🔴 검사 자격 미달'}")

    # ── ⓔ 최악 경우 — K를 올리면 주입이 따라 오르는가 ──
    print("\n  ⓔ 최악 경우 — 행 수 K를 올리면 **주입**이 따라 오르는가"
          " (한 턴, `session_start=False`)")
    print("     내용은 대장 부채 넷을 돌려 쓴다 — 합성 문자열이면 한계 비용이")
    print("     내용 길이의 산물이 되고, 그 수로 K를 유도할 수 없다.")
    print("     🔄 wave4: 첫 턴 앞에 경계 행 하나를 둔다 — 백오프가 세션 경계로 세서, 없으면")
    print("        K가 몇이든 0행이 나간다(재는 것이 주입 비용이지 백오프가 아니다).")
    texts = [c for c, _, _, _ in seeds] or ["부채"]
    krows = []
    for K in DEBT_K_AXIS:
        m = _debt_db(tmpdir, f"debt-k{K}.db")
        for i in range(K):
            _plant_debt(m, texts[i % len(texts)], 0, "time")
        _end_session(m, 1, 1, 99)
        m.db.commit()
        ctx = m.build_context(DEBT_CHAT, "오늘 좀 피곤하네", 100,
                              session_start=False)
        krows.append(dict(K=K, blocks=sum(1 for b in ctx.blocks if b.name == "debt"),
                          lines=_debt_lines(ctx), tok=_debt_ntok(ctx)))
        m.db.close()
    print(f"\n     {'K(심은 행)':>10} {'블록':>5} {'주입 행':>8} {'debt 블록':>11}")
    print("     " + "-" * 44)
    for k in krows:
        print(f"     {k['K']:>10} {k['blocks']:>5} {k['lines']:>8}"
              f" {k['tok']:>7} ntok")
    grows = all(krows[i + 1]["lines"] > krows[i]["lines"]
                for i in range(len(krows) - 1))
    capped = any(k["lines"] < k["K"] for k in krows)
    print(f"\n     주입 행이 K를 따라 단조증가하는가? {'**예**' if grows else '아니오'}"
          f"  ·  어디서든 K보다 작아지는가(=상한)? "
          f"{'예' if capped else '**아니오**'}")
    marg = ((krows[-1]["tok"] - krows[0]["tok"])
            / max(krows[-1]["K"] - krows[0]["K"], 1))
    print(f"     한계 비용 = ({krows[-1]['tok']} − {krows[0]['tok']}) ntok /"
          f" ({krows[-1]['K']} − {krows[0]['K']}) 행 = **{marg:.1f} ntok/행**")
    head = base_p50 * (GATE - 1)
    k_gate = head / marg if marg else float("inf")
    print(f"     1절의 `b=2` 기준선 p50 = {base_p50} ntok · ×{GATE} 여유 ="
          f" {head:.1f} ntok")
    print(f"     → **부채 {k_gate:.1f}행이면 그 여유를 전부 먹는다.**"
          f" 오늘 코드에 이 수를 막는 것은 없다.")

    # ── ⓕ 시도되지 않는 부채는 소멸하는가 ──
    print("\n  ⓕ «시도되지 않는 부채»는 소멸하는가 —"
          " `session_start`가 영영 안 오는 채팅")
    m = _debt_db(tmpdir, "debt-never.db")
    _plant_debt(m, "다음에 그 카페 같이 가기로 약속", 0, "session_start")
    m.db.commit()
    NEVER = 2000
    for seq in range(1, NEVER + 1):
        m.build_context(DEBT_CHAT, "그냥 얘기", seq, session_start=False)
    row = m.db.execute("SELECT status, attempt_count FROM debt").fetchone()
    m.db.close()
    immortal = (row["status"] == "open")
    print(f"     {NEVER}턴을 `session_start=False`로 지난 뒤:"
          f" status={row['status']!r} · attempt_count={row['attempt_count']}"
          f"   (분모 {NEVER}턴)")
    print(f"     → 소멸이 `attempt_count`에 걸려 있고 `attempt_count`는 **주입될"
          " 때만** 오른다. 게이트가 주입을 막으면 시도가 0으로 고정되고,")
    print("        🔄 wave4: 이 채팅엔 세션 경계도 안 온다 — 그래서 지금 먼저 막는 것은 게이트가")
    print("        아니라 **백오프**(경계 0)다. 경계가 와도 세션 시작이 안 오면 게이트가 막는다.")
    print(f"        {'**그 행은 영원히 open이다.**' if immortal else '소멸했다.'}"
          " ③은 «시도된 부채»의 상한이지 «부채»의 상한이 아니다.")

    # ── 이 절의 판정 ──
    print("\n  ── 🔴 이 절의 판정 ──")
    print(f"  세 상한은 실재하고 실제로 문다"
          f" (①{r['tot']['backoff']}·②{r['tot']['gate']}·③{r['tot']['expire']}회"
          f" / {ev} 행-턴 · 🔄 wave4 ②′ 트리거 {r['tot']['trigger']}회)."
          " 앞선 검증자의 관찰은 참이다.")
    print("  🔴 **그러나 셋은 «행 하나가 얼마나 자주 주입되는가»의 상한이고,**")
    print("     **G19′가 요구한 축 — «행이 몇 개인가» · «한 번에 몇 행이 주입되는가»**")
    print("     **— 위에는 아무것도 없다.** ⓔ가 그 축에서 K=100까지 단조증가를 보인다.")
    print(f"  그리고 «이 코퍼스에서 max {max(r['opens'])}»는 상한이 아니다 —"
          f" 심은 수가 {len(seeds)}이었을 뿐이고(ⓑ),")
    print("  안 심으면 0이다(ⓐ). **max는 표본의 성질이다.**")
    print("  ⓕ가 그 위에 하나 더 얹는다: 시도되지 않는 부채는 소멸 경로에")
    print("  도달하지 못하므로, 셋 중 ③조차 모든 행에 대해 참이 아니다.")
    print("\n  🔴 이 절은 **종료 코드를 바꾸지 않는다.** U6이 «안 고친다»이므로")
    print("     집행할 계약이 아직 없고, 없는 계약을 종료 코드로 지키는 척하는")
    print("     것이 이 저장소가 이름으로 금지한 «발화할 수 없는 검사»다.")
    print("     발화하는 쪽은 ⓓ(그림자 대조)와 `test_digest_budget.py`다.")
    return dict(open_max=max(r["opens"]), open_p50=soak.pct(r["opens"], 50),
                open_p95=soak.pct(r["opens"], 95), inj_max=max(r["lines"]),
                n=n, ev=ev, tot=r["tot"], stuck=r["stuck"],
                write_rows=w["rows"], seeds=len(seeds), marg=marg,
                k_gate=k_gate, grows=grows, capped=capped,
                immortal=immortal, plants_fired=fired, shadow_ok=ok_d)


# ── main ─────────────────────────────────────────────────────────────────
def main():
    print("🔄 G19′ ①②③ 집행을 **켰다** (단계 S3). S0에서는 검사 대상이 없어"
          " 정의만 했다 (put_session_digest=S1 · _serve_digest=S3 · I5=S3).")
    print("=" * W)
    print("요약 예산 · G19′ 기수 계약 집행 (계획서 §7 단계 S0 + S3)")
    print("=" * W)

    # 🔴 이 기준선이 성립하는 **조건**이다. 병렬 레인이 이 값을 4 → 5로 올리는
    #    중이므로, 어느 시점에 쟀는지가 숫자의 일부다.
    print(f"\n측정 시점의 `memory.SCHEMA_VERSION` = {Memory.SCHEMA_VERSION}"
          "   ← 이 기준선의 조건")

    # 🔴 **집행을 ollama보다 먼저 돌린다.** 아래 저울·상한 대조는 ollama가 없으면
    #    77(SKIP)로 끝나는데, 계약 집행이 그 뒤에 있으면 «ollama 없는 기계에서는
    #    G19′가 안 돈다»가 된다 — 그것이 곧 발화할 수 없는 검사다.
    g19_dir = tempfile.mkdtemp(prefix="digest-budget-g19-")
    try:
        violations = enforce_g19(g19_dir)
    finally:
        shutil.rmtree(g19_dir, ignore_errors=True)
    if violations:
        print("\n" + "=" * W)
        print("🔴 G19′ 위반 — **실행 실패다. «알려진 감사 지적»이 아니다.**")
        for v in violations:
            print(f"  · {v}")
        print("종료 코드 1")
        print("=" * W)
        return 1

    try:
        info = llm.checkpoint()
    except Exception as e:                                    # noqa: BLE001
        print(f"\n🔴 ollama에 닿지 못했다: {e}")
        print("   ⚠️ G19′ 집행은 **위에서 이미 돌았고 통과했다** — 아래 저울·상한")
        print("      대조만 미측정이다. 77은 통과가 아니라 «여기서는 못 잰다»다.")
        return 77
    if info.get("ollama") is None:
        print(f"\n⏭️ ollama가 {llm.OLLAMA_HOST}에서 안 돈다 — 종료 77 (SKIP)."
              "  **통과로 세지 않는다.**")
        print("   ⚠️ G19′ 집행은 위에서 이미 돌았고 통과했다.")
        return 77
    stamp = ""
    print(f"\nollama {info['ollama']} · {info['model']} · digest {info['digest']}")
    if info["digest"] != EXPECT_DIGEST:
        stamp = (f"⚠️ 모델 다이제스트가 계획서 기록과 다르다"
                 f" (기록 {EXPECT_DIGEST[:16]}… vs 현재"
                 f" {str(info['digest'])[:16]}…)")
        print(stamp)
        print("   → 막지 않는다. 대신 **이 실행의 모든 숫자 옆에 이 사실이 붙는다.**")
    else:
        print("   ✅ 계획서가 못박은 다이제스트와 같다 (생존 확인이 아니라 다이제스트로).")

    corpus = [json.loads(l) for l in
              open(os.path.join(ROOT, "eval", "corpus", "corpus.jsonl"),
                   encoding="utf-8")]
    with open(os.path.join(ROOT, "eval", "fact-ledger.yaml"),
              encoding="utf-8") as f:
        ledger = yaml.safe_load(f)
    sums = summaries()

    tmpdir = tempfile.mkdtemp(prefix="digest-budget-")
    try:
        print()
        rows, same, flat = token_baseline(corpus, ledger, sums, tmpdir)
        sc = scale_check(sums)
        m2 = m2_control(sums, ledger)
        # 🔴 **위 세 절 뒤에 둔다.** 이 절은 종료 코드를 안 바꾸므로 앞에 끼우면
        #    기존 절의 출력만 밀어내고 얻는 것이 없다. 1절의 `b=2` 기준선을
        #    분모로 받아 «부채 몇 행이 그 여유를 먹는가»를 같은 화폐로 적는다.
        debt_budget(corpus, ledger, tmpdir,
                    next(r for r in rows if r["b"] == B_BASE)["p50"])
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print("\n" + "=" * W)
    print("판정")
    print("=" * W)
    print(f"  b=0 동일성        : {'✅ 일치' if same else '🔴 불일치'}")
    print(f"  인접 차이 ≠ 0     : {'🔴 발화 (차이 0 있음)' if flat else '✅ 통과'}")
    print(f"  저울 배율 경고    : {'⚠️ 발화' if (sc and sc['fired']) else '✅ 밴드 안'}"
          "   (경고는 종료 코드를 바꾸지 않는다)")
    print(f"  M2 세 열          : 재료 안 {m2['inside']}/{m2['n_in']}"
          f" · 재료 밖 위양성 {m2['fp']}건 · 참고 전체 {m2['total']}/10")
    print("  G19′ ①②③        : ✅ 통과 (ollama 앞에서 이미 돌았다)")
    if stamp:
        print(f"  {stamp}")
    bad = (not same) or flat or sc is None
    print(f"\n종료 코드 {1 if bad else 0}"
          " — 가르는 것은 G19′ 위반 · b=0 동일성 · 인접 차이 · 저울 부재다.")
    print("🔴 이 종료 1은 «알려진 감사 지적»이 아니라 **계약 위반**이다 —"
          " 그래서 `run_all.STEPS`의 다섯 번째 원소가 `False`다.")
    print("=" * W)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
