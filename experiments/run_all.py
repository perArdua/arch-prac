"""
전체 실험 러너 — 모든 실험을 순서대로 돌리고 출력을 한 파일로 모은다.

문서 여러 곳에 숫자를 옮겨 적으면 어긋난다(실제로 3곳이 어긋나 있었다).
이 파일이 **단일 출처**다. 문서의 수치가 의심되면 여기와 대조한다.

실행: python experiments/run_all.py
출력: experiments/RESULTS.txt
"""

import subprocess
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
OUT = HERE / "RESULTS.txt"

# (파일, 설명, 추가 의존성 필요 여부)
STEPS = [
    ("gen_corpus.py",    "코퍼스 생성 (선행 필수)",            False),
    ("cache_sim.py",     "실험 1  컨텍스트 배치와 캐시",        False),
    ("retrieval_sim.py", "실험 2  검색·쓰기정책·현저성",        False),
    ("arms_sim.py",      "실험 3·4  arm 비교 + 깊이별 교정",    False),
    ("vector_bench.py",  "실험 6  브루트포스 벡터 검색",        False),
    ("param_sweep.py",   "실험 7  파라미터 스윕 (τ·k·N)",      False),
    ("sensitivity.py",   "실험 8  깊이 분포 민감도",            False),
    ("guard_sim.py",     "실험 9  상태 가드",                  False),
    ("mechanism_sim.py", "실험 10 메커니즘 검증",              False),
    ("hybrid_sim.py",    "실험 5  BM25 vs Dense vs 하이브리드", True),
]


def main():
    parts = [
        "=" * 78,
        "실험 결과 스냅샷 — 이 파일이 수치의 단일 출처다",
        f"생성: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "재현: python experiments/run_all.py",
        "=" * 78,
    ]
    failed = []

    for fname, desc, needs_extra in STEPS:
        print(f"실행 중: {desc} ...", end=" ", flush=True)
        r = subprocess.run([sys.executable, str(HERE / fname)],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        if r.returncode == 0:
            print("✅")
            body = r.stdout
        else:
            note = " (추가 의존성 미설치로 보임)" if needs_extra else ""
            print(f"❌{note}")
            failed.append((fname, needs_extra))
            body = (f"[실행 실패{note}]\n"
                    f"{(r.stderr or '').strip()[-400:]}")
        parts += ["", "─" * 78, f"▶ {desc}   ({fname})",
                  "─" * 78, body.rstrip()]

    parts += ["", "=" * 78]
    if failed:
        parts.append("실행 실패: " + ", ".join(f for f, _ in failed))
        if any(x for _, x in failed):
            parts.append("  · hybrid_sim.py는 `pip install sentence-transformers`가 필요하다")
    else:
        parts.append("전체 실험 정상 실행")
    parts.append("=" * 78)

    OUT.write_text("\n".join(parts), encoding="utf-8")
    print(f"\n저장: {OUT}")
    print(f"  실행 {len(STEPS)}건 · 실패 {len(failed)}건")


if __name__ == "__main__":
    main()
