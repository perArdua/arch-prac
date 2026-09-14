# -*- coding: utf-8 -*-
"""
동결 넷(`_stem` · `_ENDINGS` · `_PARTICLE` · `Memory._roots`)의 해시.

두 벌을 찍는다:
  · **원문 해시** — `inspect.getsource`/`.pattern`의 바이트. 글자가 바뀌면 움직인다.
  · **닫힌 해시** — 고정 입력에 대한 출력 집합. 철자가 바뀌어도 «받아들이는 언어»가
    같으면 안 움직인다. 둘을 나란히 두는 이유는 이 저장소가 실험 30에서
    «동작 0칸인데 닫힌 해시가 움직인다»를 실측했기 때문이다(prov 레인 §놀란 것).

닫힌 입력은 **정렬된 리스트**로 고정한다 — `repr(set)`은 `PYTHONHASHSEED`의 함수다.
"""
import hashlib
import inspect
import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "prototype"))
sys.stdout.reconfigure(encoding="utf-8")

import memory as M                                              # noqa: E402
from memory import Memory                                       # noqa: E402

# 닫힌 해시의 고정 입력 — 어미·조사·경계·1글자·비한글을 고루 건드린다.
PROBE = [
    "아팠던", "아파서", "민감하다", "민감해서", "응급실에", "응급실",
    "나비가", "강아지", "지우는", "서준한테서", "회사에서", "마케팅",
    "했잖아", "먹었습니다", "이직", "면접을", "그때", "a", "가",
    "카페에서 만났다", "지우가 회사에서 크게 깨지고 새벽에 연락함",
    "지우는 마케팅 회사 대리로 일한다", "고양이 나비랑 놀았어요",
]


def h(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def main():
    src = {
        "_stem":            inspect.getsource(M._stem),
        "_ENDINGS":         M._ENDINGS.pattern,
        "_PARTICLE":        Memory._PARTICLE.pattern,
        "Memory._roots":    inspect.getsource(Memory._roots.__func__),
    }
    closed = {
        "_stem":         repr([M._stem(w) for w in PROBE]),
        "_ENDINGS":      repr([M._ENDINGS.sub("", w) for w in PROBE]),
        "_PARTICLE":     repr([Memory._PARTICLE.sub("", w) for w in PROBE]),
        "Memory._roots": repr([sorted(Memory._roots(t)) for t in PROBE]),
    }
    print(f"{'':<16}{'원문':<68}닫힌")
    for k in src:
        print(f"{k:<16}{h(src[k]):<68}{h(closed[k])}")


if __name__ == "__main__":
    main()
