# -*- coding: utf-8 -*-
"""
embedding.py — 로컬 ollama `/api/embed`(bge-m3) 래퍼 + DB 밖 파일 캐시.

캐시가 DB 밖에 있는 이유: `gate_sweep.py`는 셀마다 DB를 새로 만들고 지운다. 캐시를 `embedding` 테이블에만
두면 셀마다 사라져 격자 ~98셀 × 셀당 ~458개 ≈ 44,900회를 호출하고, DB 밖 파일이면 첫 셀의 458회뿐이다.
`embedding` 테이블은 런타임 서빙 캐시(단일 DB 수명)로만 쓰고, 두 경로는 `cache_key()` 하나를 공유한다.

실패는 예외가 아니라 `None`이다 — ollama가 없든 죽었든 `embed()`는 예외를 내지 않고, 호출부는 어휘 검색으로
강등한다. (`llm.generate()`는 반대로 예외를 낸다 — 생성은 강등할 대상이 없다.)
"""

import json
import os
import time
import urllib.request

# ── 모듈 전역 상수 — 시험이 재바인딩한다(몽키패치) ─────────────────────
# 기본값이 `localhost`가 아니라 `127.0.0.1`인 이유(`llm.py` 등이 이 주석을 참조한다):
#   `localhost`는 `[::1, 127.0.0.1]` 순으로 풀리는데 ollama는 IPv4에만 바인딩해 `::1`이 거절되고,
#   이 기기는 거절된 TCP connect를 표면화하는 데 ~2.02초를 쓴다(127.0.0.1 직접은 0.26 ms).
#   그래서 `localhost`는 호출마다 +2초를 붙였다(웜 p50 2,082 ms 중 순 연산은 34.2 ms).
#   원격 ollama는 `OLLAMA_HOST`로 덮어쓴다.
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
EMBED_MODEL = "bge-m3"
EMBED_TIMEOUT = 120          # 초. `embed_vs_bigram.py`와 같은 값
PROBE_TIMEOUT = 3            # 초. "ollama가 살아 있나"만 보는 짧은 조회

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)

# 스윕용 파일 캐시. `.gitignore` 대상이다(항목이 늘면 ~6.2 MB). 양자화로 줄이지 않는다 — 저장 공간 때문에
# 숫자를 바꾸는 것은 나쁜 교환이다. 재현성은 캐시가 아니라 `ensure_cached()`의 종료 코드 77이 말한다.
CACHE_PATH = os.path.join(ROOT, "experiments", "data", "EMBED_CACHE_SWEEP.json")

# 기존 캐시(텍스트 37개 · 513,948B). 읽기 전용이다 — 같은 `cache_key()`라 항목이 그대로 통하고, 쓰지 않는다.
LEGACY_CACHE_PATH = os.path.join(ROOT, "experiments", "data", "EMBED_CACHE.json")

# 크기 상한. 경고만 한다(`run_all.py`가 찍는다) — `EMBED_CACHE.json`이 이미 상한 근처라 실패로 만들면 곧장 깨진다.
MAX_CACHE_FILE_BYTES = 1 * 1024 * 1024
MAX_CACHE_TOTAL_BYTES = 2 * 1024 * 1024

_cache = None                # 스윕 캐시 (읽기·쓰기). 지연 로드
_legacy = None               # `EMBED_CACHE.json` (읽기 전용). 지연 로드


def cache_key(text: str) -> str:
    """
    파일 캐시와 `embedding` 테이블이 공유하는 키 — 원문 문자열 그대로다.
    기존 `EMBED_CACHE.json`이 원문을 키로 쓰므로 해시로 바꾸면 그 항목이 전부 고아가 된다.
    바꾸려면 이 함수 하나를 고친다(한 계층만 바뀌면 두 경로가 갈라진다).
    """
    return text


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}         # 없거나 깨졌으면 빈 캐시로 시작한다


def _cache_load():
    """
    두 dict를 합치지 않고 따로 들고 있는다 — 합쳐 저장하면 스윕 캐시가 기존 캐시의 벡터를
    두 벌로 들고 다닌다. 스윕 캐시에는 스윕이 새로 계산한 것만 남는다.
    """
    global _cache, _legacy
    if _cache is None:
        _cache = _load(CACHE_PATH)
    if _legacy is None:
        _legacy = _load(LEGACY_CACHE_PATH)
    return _cache, _legacy


def _lookup(k):
    """스윕 캐시 우선, 없으면 기존 캐시. 못 찾으면 `None`."""
    c, lg = _cache_load()
    v = c.get(k)
    return v if v is not None else lg.get(k)


def _cache_save():
    """스윕 캐시에만 쓴다. `EMBED_CACHE.json`은 건드리지 않는다."""
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_cache_load()[0], f)
    except OSError:
        pass              # 캐시 저장 실패는 계산 결과를 버릴 이유가 아니다


def _post(path, payload, timeout):
    req = urllib.request.Request(
        f"{OLLAMA_HOST}{path}", json.dumps(payload).encode("utf-8"),
        {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def available() -> bool:
    """ollama가 응답하는가. 짧은 타임아웃 — 판정용이지 대기용이 아니다."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/version",
                                    timeout=PROBE_TIMEOUT) as r:
            json.loads(r.read())
        return True
    except Exception:
        return False


def embed(texts, *, use_cache: bool = True, save: bool = True):
    """
    `list[str] -> list[list[float]] | None`. 캐시에 있으면 호출하지 않는다.
    하나라도 실패하면 전체를 `None`으로 돌려준다 — 일부만 채운 리스트는 호출부가 길이만 보고 성공으로 착각한다.
    `use_cache=False`·`save=False`는 라이브 재계산 대조용이다.
    """
    out, dirty = [], False
    try:
        for t in texts:
            k = cache_key(t)
            hit = _lookup(k) if use_cache else None
            if hit is not None:
                out.append(hit)
                continue
            r = _post("/api/embed", {"model": EMBED_MODEL, "input": t},
                      EMBED_TIMEOUT)
            v = r["embeddings"][0]
            if not v:
                return None
            if use_cache:
                _cache_load()[0][k] = v
                dirty = True
            out.append(v)
    except Exception:
        # 연결 거부·타임아웃·JSON 깨짐·키 없음이 전부 «임베딩을 못 얻었다»는 같은 뜻이다.
        return None
    if dirty and save:
        _cache_save()
    return out


def missing_keys(texts):
    """캐시에 없는 키만 돌려준다. `ensure_cached()`가 나열하는 목록이다."""
    return [t for t in texts if _lookup(cache_key(t)) is None]


def ensure_cached(texts) -> int:
    """
    종료 코드 3분기:
        캐시 히트            -> 0
        미스 + ollama 있음   -> 계산 후 0
        미스 + ollama 없음   -> 77 (SKIP) + 없는 키를 나열한다
    77은 «통과»가 아니라 «이 환경에서는 재현할 수 없다»는 신고다 — `run_all.py`가 건너뜀으로 집계한다.
    """
    need = missing_keys(texts)
    if not need:
        return 0
    if not available():
        print(f"⚠️ 캐시 미스 {len(need)}건이고 ollama({OLLAMA_HOST})가 응답하지 않는다 "
              f"— SKIP(77)으로 끝낸다.")
        for t in need:
            print(f"    없는 키: {t[:70]}")
        return 77
    return 0 if embed(need) is not None else 77


def cache_size_warnings():
    """상한 초과 경고 문자열 목록. 판단하지 않고 찍기만 한다 — 호출부(`run_all.py`)는 종료 코드를 바꾸지 않는다."""
    warns, total = [], 0
    for p in (LEGACY_CACHE_PATH, CACHE_PATH):
        try:
            n = os.path.getsize(p)
        except OSError:
            continue
        total += n
        if n > MAX_CACHE_FILE_BYTES:
            warns.append(f"⚠️ 캐시 파일 상한 초과: {os.path.basename(p)} "
                         f"{n:,}B > {MAX_CACHE_FILE_BYTES:,}B")
    if total > MAX_CACHE_TOTAL_BYTES:
        warns.append(f"⚠️ 캐시 합계 상한 초과: {total:,}B > "
                     f"{MAX_CACHE_TOTAL_BYTES:,}B")
    return warns


# ── `embedding` 테이블 경로 (런타임 서빙 캐시) ──────────────────────────
# 파일 캐시와 같은 `cache_key()`를 쓴다. 스윕은 이 경로를 타지 않는다(셀마다 DB가 삭제된다).

def db_get_vec(db, text, model=EMBED_MODEL):
    row = db.execute("SELECT vec FROM embedding WHERE key=? AND model=?",
                     (cache_key(text), model)).fetchone()
    return json.loads(row["vec"]) if row else None


def db_put_vec(db, chat_id, text, vec, model=EMBED_MODEL):
    db.execute("INSERT OR REPLACE INTO embedding VALUES (?,?,?,?)",
               (chat_id, cache_key(text), model, json.dumps(vec)))
    db.commit()


def model_digest(model=EMBED_MODEL):
    """`/api/tags`에서 모델 다이제스트를 찾는다. 못 찾으면 `None`."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags",
                                    timeout=PROBE_TIMEOUT) as r:
            for m in json.loads(r.read()).get("models", []):
                if m.get("name", "").split(":")[0] == model.split(":")[0]:
                    return m.get("digest")
    except Exception:
        return None
    return None


def checkpoint_info():
    """
    ollama 버전 + `bge-m3` 다이제스트. 같은 캐시라도 다른 모델 빌드로 만든 것이면 숫자가 움직이므로
    그 출처를 숫자 옆에 같이 적는다.
    """
    ver = None
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/version",
                                    timeout=PROBE_TIMEOUT) as r:
            ver = json.loads(r.read()).get("version")
    except Exception:
        pass
    return {"ollama": ver, "model": EMBED_MODEL, "digest": model_digest(),
            "at": time.strftime("%Y-%m-%d %H:%M:%S")}
