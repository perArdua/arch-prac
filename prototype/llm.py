# -*- coding: utf-8 -*-
"""
llm.py — 로컬 ollama `/api/generate`(qwen3:8b) 래퍼. 생성 경로의 유일한 입구.

실패하면 예외를 낸다(`embedding.embed()`가 `None`을 돌려주는 것과 정반대다). 임베딩은 강등할 대상(어휘
검색)이 있지만 생성에는 없다 — 빈 문자열을 돌려주면 «요약이 비었다»와 «요약을 못 만들었다»가 구별되지
않고, 그대로 `digest`에 저장돼 조용히 맥락을 지운다.

결정성: `temperature=0` · `seed` · `num_ctx`를 고정해도 결정적이지 않다(아래 서버 캐시 상태 절).
모델 빌드가 바뀌어도 숫자가 움직이므로 체크포인트 파일에 ollama 버전 + 모델 다이제스트를 적고,
다음 실행에서 다르면 경고한다(막지는 않는다 — 막으면 모델 갱신 때마다 실험이 멈춘다).

한계: `<think>` 블록을 지운 뒤 본문이 비면(모델이 그 안에서 답을 끝낸 경우) 실패로 보고 예외를 낸다.
"""

import json
import os
import re
import time
import urllib.request

# ── 모듈 전역 상수 ──────────────────────────────────────────────────
# `localhost`가 아니라 127.0.0.1인 이유: 이 기기에서 `localhost`는 ollama가 안 듣는 `::1`을 먼저 고르고
# 거절된 connect에 ~2초를 쓴다(`embedding.py`의 같은 주석).
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
LLM_MODEL = "qwen3:8b"
LLM_TEMPERATURE = 0
LLM_SEED = 20260908          # 계획 확정일. 바꾸면 모든 생성 결과가 움직인다
LLM_NUM_CTX = 8192
LLM_TIMEOUT = 600            # 초. 8B 로컬 모델은 느리다 — 임베딩보다 넉넉히 준다

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
CHECKPOINT_PATH = os.path.join(ROOT, "experiments", "data", "LLM_CHECKPOINT.json")

_THINK = re.compile(r"<think>.*?</think>\s*", re.S)

_checked = False             # 프로세스당 한 번만 대조·경고한다
_last_usage = None           # 마지막 `/api/generate` 응답의 사용량

# 응답 JSON에서 예산 계기로 쓰는 필드. `prompt_eval_count`가 본체다 — 프리픽스 캐시가 걸려도 프롬프트
# 전체 길이를 말한다(`prompt_eval_cached_count`는 그중 캐시 적중분). ollama는 `num_ctx` 초과분을
# 말없이 버리므로(예외도 `truncated` 필드도 없다) 이 필드들이 절단을 나중에 알아볼 유일한 흔적이다.
_USAGE_FIELDS = ("prompt_eval_count", "prompt_eval_cached_count",
                 "eval_count", "done_reason")


class LLMError(RuntimeError):
    """생성 실패. 잡아서 빈 문자열로 바꾸지 말 것 — 모듈 독스트링 참조."""


def _get(path, timeout=5):
    with urllib.request.urlopen(f"{OLLAMA_HOST}{path}", timeout=timeout) as r:
        return json.loads(r.read())


def runtime_info():
    """ollama 버전 + `qwen3:8b` 다이제스트. 체크포인트에 적히는 내용 그대로."""
    info = {"ollama": None, "model": LLM_MODEL, "digest": None}
    try:
        info["ollama"] = _get("/api/version").get("version")
    except Exception:
        pass
    try:
        for m in _get("/api/tags").get("models", []):
            if m.get("name", "").split(":")[0] == LLM_MODEL.split(":")[0]:
                info["digest"] = m.get("digest")
                break
    except Exception:
        pass
    if info["digest"] is None:      # `/api/tags`가 안 되면 `/api/show`로
        try:
            req = urllib.request.Request(
                f"{OLLAMA_HOST}/api/show",
                json.dumps({"model": LLM_MODEL}).encode("utf-8"),
                {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as r:
                d = json.loads(r.read())
            info["digest"] = (d.get("details") or {}).get("parent_model") or None
        except Exception:
            pass
    return info


def checkpoint(verbose=True):
    """
    체크포인트를 읽어 대조하고, 없으면 쓴다. 돌려주는 것은 현재 실행 정보다.
    다르면 경고만 한다 — «같은 스크립트인데 숫자가 다르다»를 나중에 설명할 수 있게.
    """
    now = runtime_info()
    old = None
    try:
        with open(CHECKPOINT_PATH, encoding="utf-8") as f:
            old = json.load(f)
    except (OSError, ValueError):
        pass

    if old and verbose:
        for k in ("ollama", "digest"):
            if old.get(k) and now.get(k) and old[k] != now[k]:
                print(f"⚠️ 체크포인트 불일치 — {k}: 기록 {old[k]} vs 현재 {now[k]}. "
                      f"이 실행의 숫자는 이전 실행과 **같은 조건이 아니다.**")
    if old is None:
        rec = dict(now, first_seen=time.strftime("%Y-%m-%d %H:%M:%S"))
        try:
            with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False, indent=2)
        except OSError:
            pass          # 체크포인트를 못 써도 생성 자체를 막을 이유는 없다
    return now


def strip_think(text: str) -> str:
    """qwen3의 추론 블록을 지운다. 닫히지 않은 `<think>`는 뒤를 전부 버린다."""
    text = _THINK.sub("", text)
    if "<think>" in text:
        text = text.split("<think>", 1)[0]
    return text.strip()


def last_usage():
    """
    마지막 `raw_generate()`/`generate()` 호출의 사용량 사본. 없으면 `None`.
    `ntok()`은 `len × 1.5`짜리 추정이라(이 코퍼스에서 2.07배 과대계상) 실측 저울이 따로 필요하다.
    사본을 돌려주는 이유: 다음 호출이 덮어쓴 전역을 자기 호출의 값으로 읽지 않게.
    """
    return dict(_last_usage) if _last_usage is not None else None


def raw_generate(prompt: str, **options) -> dict:
    """
    `/api/generate` 응답 전체를 돌려준다. 사용량은 `last_usage()`에 남는다.
    예산 계기가 필요한 호출부는 여기서 `prompt_eval_count`를 얻고, `generate()`의 `str -> str` 계약은 그대로다.
    `options`는 모듈 기본값 위에 얹는다(예: 프롬프트만 재려고 `num_predict=1`). 실패하면 여기서도 예외를 낸다.
    """
    global _checked, _last_usage
    if not _checked:
        _guard_regen(checkpoint())   # run_all 아래에서 기록≠런타임이면 생성 전에 77
        _checked = not _MEASURING    # 측정 호출은 검사를 «소비»하지 않는다 — 다음 진짜 생성이 다시 검사받는다

    _last_usage = None        # 실패한 호출 뒤에 앞 호출의 사용량이 남지 않게
    opts = {"temperature": LLM_TEMPERATURE, "seed": LLM_SEED,
            "num_ctx": LLM_NUM_CTX}
    opts.update(options)
    body = json.dumps({
        "model": LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": opts,
    }).encode("utf-8")
    req = urllib.request.Request(f"{OLLAMA_HOST}/api/generate", body,
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as r:
            raw = json.loads(r.read())
    except Exception as e:                                  # noqa: BLE001
        raise LLMError(f"{LLM_MODEL} 생성 실패 ({OLLAMA_HOST}): {e}") from None

    # 빈 응답으로 터지는 경우에도 사용량은 남긴다 — 무엇을 보냈길래 비었는지 볼 수 있게.
    _last_usage = {k: raw.get(k) for k in _USAGE_FIELDS}
    return raw


def generate(prompt: str) -> str:
    """`str -> str`. 실패하면 `LLMError`를 낸다 — 호출부가 이 예외를 삼키면 안 된다."""
    out = strip_think(raw_generate(prompt).get("response", ""))
    if not out:
        raise LLMError(
            f"{LLM_MODEL}이 빈 응답을 냈다 — `<think>` 제거 후 본문이 없다. "
            f"빈 문자열을 돌려주면 '요약이 비었다'와 구별되지 않는다.")
    return out


# ── 결정성은 «같은 요청 + 같은 서버 캐시 상태»에서만 성립한다 ──────────────────
# 같은 프롬프트 · 같은 옵션이라도 서버가 그 접두를 어떻게 계산해 들고 있었나에 따라 본문이 갈린다
# (`experiments/cache_state_repro.py` 실측: 모델을 내린 직후의 콜드 생성끼리는 같고, 연달아 보낸 웜 생성은
# 콜드와 다르며, 실행이 다르면 적중 길이가 같아도 다를 수 있다). `prompt_eval_count`로는 이 차이가 안 보인다.
# 그래서 기록값은 결정성이 아니라 생성물 체크포인트로 지킨다(재채점만 한다). 매 생성마다 모델을
# 내리면 재현되지만(생성당 ≈2.7초) 프로덕션 지연을 사는 결정이라 켜지 않았다(docs/12 · ADR-016).


# ── 기록과 런타임이 다르면 재생성하지 않는다 ─────────────────────────────
# ollama가 자동 업데이트되자(0.33.3 → 0.34.0) 응답 캐시 키가 전부 빗나가 `run_all`이 기록값을 말없이
# 다시 생성해 덧썼다. «두 런타임의 답을 섞지 않는다»와 «빗나가면 다시 만든다»는 다른 결정이다.
# `run_all`이 자식에게 `MEMARCH_FORBID_REGEN`을 넘기면, 첫 라이브 생성 직전에 `LLM_CHECKPOINT.json`의
# 기록(ollama·digest)과 지금 런타임을 대조하고 다르면 77(SKIP)로 끝낸다. 캐시 적중만으로 끝나는
# 단계는 여기까지 오지 않는다. 손으로 돌리면(변수 없음) 경고만 한다.
FORBID_REGEN_ENV = "MEMARCH_FORBID_REGEN"


def _guard_regen(now):
    if not os.environ.get(FORBID_REGEN_ENV):
        return now
    try:
        with open(CHECKPOINT_PATH, encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError):
        return now                      # 기록이 없으면 대조할 것도 없다
    diff = [k for k in ("ollama", "digest")
            if rec.get(k) and now.get(k) and rec[k] != now[k]]
    if diff:
        what = " · ".join(f"{k} 기록 {rec[k]} vs 현재 {now[k]}" for k in diff)
        if _MEASURING:
            print(f"ℹ️ {FORBID_REGEN_ENV} — {what}. 측정 호출(체크포인트를 안 채운다)이라 "
                  f"막지 않는다 — 이 값은 **현재 판**({now.get('ollama')})에서 잰 것이다.",
                  flush=True)
            return now
        print(f"⏭️ {FORBID_REGEN_ENV} — {what}. 라이브 생성을 하지 않는다(77): "
              f"체크포인트를 덧쓰면 기록값이 조용히 바뀐다(F39).", flush=True)
        raise SystemExit(77)
    return now


# ── 재채점은 기록 판 키로 · 측정은 막지 않는다 ─────────────────────────────
# 판 차이는 캐시 키에만 걸린다(기록값은 옛 답 텍스트의 재채점이고 그때 ollama는 불리지 않는다).
# `run_all` 아래에서는 키를 기록 판으로 만들어 옛 답을 찾고(`key_runtime`), 빗나가면 생성으로 가서
# `_guard_regen`이 실제 런타임으로 대조해 77로 멈춘다 — 대체한 키로 새 답이 저장되는 일은 없다.
# 체크포인트를 채우지 않는 1토큰 측정(`measure_prompt`)은 가드가 막지 않되 검사를 소비하지 않는다.
_MEASURING = False


def measure_prompt(prompt: str, **options) -> dict:
    """체크포인트를 채우지 않는 측정 호출 — 예: `num_predict=1`로 `prompt_eval_count`만 읽기."""
    global _MEASURING
    _MEASURING = True
    try:
        return raw_generate(prompt, **options)
    finally:
        _MEASURING = False


def key_runtime(now: dict) -> dict:
    """
    캐시 키에 쓸 런타임. `run_all` 아래(`MEMARCH_FORBID_REGEN`)에서는 기록 판을, 손으로 돌리면 `now` 그대로.
    키 전용이다 — 생성 허가는 `_guard_regen`이 `checkpoint()`의 실제 런타임으로 판단한다.
    """
    if not os.environ.get(FORBID_REGEN_ENV):
        return now
    try:
        with open(CHECKPOINT_PATH, encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError):
        return now
    out = dict(now)
    for k in ("ollama", "digest"):
        if rec.get(k):
            out[k] = rec[k]
    return out
