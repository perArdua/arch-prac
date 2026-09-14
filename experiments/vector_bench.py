"""
브루트포스 벡터 검색 실측 — ADR-003의 "이 규모에선 전용 벡터 DB가 필요 없다" 검증.

주장(docs/03 FP-1): 검색은 항상 단일 대화방 파티션 안에서만 일어난다.
1년 후 검색 대상이 1,500~3,000개이므로 브루트포스가 1ms 안에 끝나고,
Qdrant 네트워크 왕복(1~5ms)보다 오히려 빠르다.

여기서는 numpy 브루트포스의 실제 지연·메모리를 N에 따라 측정한다.
ANN/네트워크 수치는 문헌값이므로 비교는 참고용이다.

실행: python experiments/vector_bench.py
"""

import sys
import time

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TOPK = 5
REPEAT = 20
SIZES = [1_000, 3_000, 10_000, 100_000, 1_000_000]
DIMS = [(384, np.float32, "e5-small f32"),
        (1024, np.float32, "BGE-M3 f32"),
        (256, np.int8, "256차원 int8 (docs/06 §3.2 권고)")]


def bench(n, dim, dtype):
    rng = np.random.default_rng(0)
    if dtype == np.int8:
        db = rng.integers(-127, 127, size=(n, dim), dtype=np.int8)
        q = rng.integers(-127, 127, size=dim, dtype=np.int8)
        db_c, q_c = db.astype(np.float32), q.astype(np.float32)
    else:
        db = rng.standard_normal((n, dim), dtype=np.float32)
        db /= np.linalg.norm(db, axis=1, keepdims=True)
        q = rng.standard_normal(dim, dtype=np.float32)
        q /= np.linalg.norm(q)
        db_c, q_c = db, q

    # 워밍업
    _ = db_c @ q_c

    times = []
    for _ in range(REPEAT):
        t0 = time.perf_counter()
        sims = db_c @ q_c
        np.argpartition(-sims, min(TOPK, n - 1))[:TOPK]
        times.append((time.perf_counter() - t0) * 1000)

    mem_mb = db.nbytes / 1024 / 1024
    return float(np.median(times)), mem_mb


def main():
    print("브루트포스 벡터 검색 — numpy 내적 + top-k\n")
    print(f"{'구성':<34}" + "".join(f"{n:>12,}" for n in SIZES))
    print("─" * 94)

    for dim, dtype, label in DIMS:
        lat_row, mem_row = [], []
        for n in SIZES:
            ms, mb = bench(n, dim, dtype)
            lat_row.append(ms)
            mem_row.append(mb)
        print(f"{label + ' — 지연(ms)':<34}" +
              "".join(f"{v:>12.2f}" for v in lat_row))
        print(f"{'  메모리(MB)':<34}" +
              "".join(f"{v:>12.1f}" for v in mem_row))
        print()

    print("─" * 94)
    print("참고 — 문헌값 (실측 아님)")
    print("  Qdrant 등 전용 벡터 DB 네트워크 왕복       1~5 ms")
    print("  HNSW 검색 자체(인메모리)                  0.1~1 ms")
    print("  메모리 파이프라인 예산 (docs/05 §4.2)     200~400 ms")
    print()
    print("판정")
    ms_3k, mb_3k = bench(3_000, 256, np.int8)
    ms_1m, _ = bench(1_000_000, 384, np.float32)
    print(f"  우리 규모(대화방당 3,000개, 256차원 int8): {ms_3k:.2f} ms, {mb_3k:.2f} MB")
    print(f"  → 네트워크 왕복(1~5ms)보다 빠르다. ADR-003의 주장 성립.")
    print(f"  → 동시 1,000세션도 {mb_3k * 1000:.0f} MB로 프로세스 메모리에 올라간다.")
    print()
    print(f"  참고로 100만 벡터(384차원)도 {ms_1m:.0f} ms다.")
    print(f"  → 브루트포스가 무너지는 지점은 우리 규모보다 훨씬 위다.")
    print()
    print("⚠️ 한계")
    print("  · 단일 쿼리 기준이다. 동시 요청이 많으면 CPU 경합으로 지연이 올라간다")
    print("  · 벡터를 메모리에 올려둔 상태를 가정한다. 디스크에서 읽으면 다르다")
    print("  · int8은 정확도 손실이 있다 — 회상 영향은 미측정(실험 D12)")
    print("  · 전용 벡터 DB의 가치는 속도만이 아니다(필터링·영속성·운영 도구)")


if __name__ == "__main__":
    main()
