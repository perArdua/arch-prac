"""
전체 실험 러너 — 모든 실험을 순서대로 돌리고 출력을 한 파일로 모은다.

문서 여러 곳에 숫자를 옮겨 적으면 어긋난다(실제로 3곳이 어긋나 있었다).
이 파일이 **단일 출처**다. 문서의 수치가 의심되면 여기와 대조한다.

실행: python experiments/run_all.py [--quick]
출력: experiments/data/RESULTS.txt

## 🆕 `--quick` (라운드 2 단계 1 작업 7)

🔴 **이 플래그는 여태 존재하지 않았다.** 여러 계획의 수용 기준이
`python experiments/run_all.py --quick`을 적어 뒀는데, 이 파일에는 **argv 처리가
아예 없어서** 모르는 인자를 조용히 삼켰다 — 즉 `--quick`을 적은 수용 기준은
**전량 실행과 같은 것을 돌리고 통과했다.** 인자를 삼키는 러너는 *"이 명령을
돌렸다"*는 증거를 **만들어내지 못하는데 만들어낸 것처럼 보인다.**

    --quick    격자(`retrieval_sweep.py`)를 뺀다. 그것이 빼는 것의 **전부**다
    (없는 인자) 종료 2 — 조용히 삼키지 않는다

🔄 **라운드 2 단계 4 (레인 E) — 이제 격자가 있다.** 단계 2-L이 F38 정정으로 PASS가
되면서 R2b가 재개됐고, `retrieval_sweep.py`가 `STEPS`에 들어왔다. 그래서 `--quick`은
**처음으로 실제로 무언가를 뺀다.** 뺀 것이 없던 시절의 출력 분기(*"뺀 것은 0건이다"*)는
그대로 남긴다 — 격자가 다시 빠지는 라운드가 오면 그 문장이 다시 참이 되고, 그때도
*"뺀 것이 없다"*와 *"플래그가 무시됐다"*는 여전히 다른 사건이기 때문이다.

## 🆕 감사 지적 vs 실행 실패 (레인 N 권고 B안)

`citation_audit.py`는 **옳게 동작하면서 영구히 빨갛다.** 살아 있는 계획서에
의심 인용이 125건 남아 있고, 그것을 다시 닻 내리면 이동 대장·rev 로그가
기록한 *"그때 그랬다"*를 지우게 된다(레인 J). 그래서 그 종료 1은 버그가
아니라 **관측**이다.

🔴 **그런데 그것을 `실패 1건`으로 계속 찍는 것은 이 러너의 버그다.** 매 실행이
빨간 줄 하나로 시작하면, 진짜로 새로 깨진 것이 그 줄에 섞여 안 보인다.
독자가 *"어느 실패가 예상된 것이었는지"*를 기억해야 하는 상태 — 알람 피로가
이 저장소의 여덟 번째 사고를 만드는 방식이다.

고친 것은 **종료 규칙이 아니라 보고 어휘**다. `citation_audit.py`의 종료 1은
그대로고(게이트를 약화시키지 않는다), 러너가 그것을 `감사 지적` 열에 따로
센다. 알려진 상태(`AUDIT_KNOWN_RED`)를 옆에 찍으므로 **1 → 2로 뛰면 그것이
곧 새 사건**이다.

⚠️ `consistency_audit.py`는 **일부러 감사로 표시하지 않았다.** 그쪽은 오늘
지적 0건이고, 거기가 빨개지면 그것은 새로 깨진 것이다 — 즉 `실패`가 맞는
어휘다. 이 다섯 번째 원소는 *"감사 도구인가"*가 아니라 *"알려진 지적이 서
있는 단계인가"*를 뜻한다.
"""

import subprocess
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "RESULTS.txt"

sys.path.insert(0, str(HERE.parent / "prototype"))
import embedding as E                                      # noqa: E402

# ⭐ 종료 코드 77 = SKIP. **통과가 아니다** (G1).
#
# 임베딩 캐시가 비었는데 ollama도 없으면 그 실험은 이 환경에서 **재현할 수 없다.**
# 그때 0을 돌려주면 "돌았다"는 거짓말이고, 1을 돌려주면 "깨졌다"는 거짓말이다.
# 77은 세 번째 답 — *"여기서는 못 잰다"* — 이고, 이 러너는 그것을 실패와 **따로** 센다.
SKIP_CODE = 77

# (파일, 설명, 추가 의존성 필요 여부, **격자인가**, **알려진 지적이 선 감사 단계인가**)
#
# 🔄 단계 2가 `fsm_probe.py`(실험 20)를 맨 끝에 덧붙였다. 단계 1에서 미뤄 둔
#    이유는 그때 그 파일이 없었기 때문이다 — 없는 파일을 넣으면 러너가 실패
#    1건을 찍고 G1이 그 자리에서 깨진다.
#
# 🆕 라운드 2 단계 1 작업 7 (G14 rev2) — **집행 기제를 배선한다.**
#    G14의 근거 문장은 *"사람만 읽는 경고는 `run_all.py`가 못 본다"*인데,
#    정작 `precision.py`도 `consistency_audit.py`도 `STEPS`에 **없었다** —
#    즉 그 종료 코드가 여기 도달한 적이 없고 앞으로도 없을 상태였다.
#    가드레일이 읽으라고 만든 종료 코드를 아무도 안 읽는 배선이었다.
#    (`rel_dist.py`는 단계 2가 만든 계측기다. ollama가 없으면 **77(SKIP)**을
#     내고, 아래 러너가 그것을 실패와 따로 센다 — G1.)
#
# 네 번째 원소 `grid` = 격자 실험인가. `--quick`이 **이것만** 뺀다.
STEPS = [
    ("gen_corpus.py",    "코퍼스 생성 (선행 필수)",            False, False, False),
    ("cache_sim.py",     "실험 1  컨텍스트 배치와 캐시",        False, False, False),
    ("retrieval_sim.py", "실험 2  검색·쓰기정책·현저성",        False, False, False),
    ("arms_sim.py",      "실험 3·4  arm 비교 + 깊이별 교정",    False, False, False),
    ("vector_bench.py",  "실험 6  브루트포스 벡터 검색",        False, False, False),
    ("param_sweep.py",   "실험 7  파라미터 스윕 (τ·k·N)",      False, False, False),
    ("sensitivity.py",   "실험 8  깊이 분포 민감도",            False, False, False),
    ("guard_sim.py",     "실험 9  상태 가드",                  False, False, False),
    ("mechanism_sim.py", "실험 10 메커니즘 검증",              False, False, False),
    ("hybrid_sim.py",    "실험 5  BM25 vs Dense vs 하이브리드", True,  False, False),
    ("fsm_probe.py",     "실험 20 FSM 준수·차단·stale·동시발생률", False, False, False),
    ("precision.py",     "지표 4종 · 분산 검정 (G14 집행)",     False, False, False),
    # 🆕 단계 S3 (ADR-016) — **G19′ 기수 계약의 집행 배선.** G14 rev2가 고친 것과
    #    같은 형태다: 가드레일이 읽으라고 만든 종료 코드를 아무도 안 읽으면 그
    #    가드레일은 없는 것이다. ①②③의 검사 대상이 S3에서 전부 실재하게 됐고,
    #    그래서 여기 등록한다.
    #    · `needs_extra=False` — G19′ 집행부는 **ollama를 한 번도 안 부른다.**
    #      (같은 파일의 저울 대조는 ollama 1토큰을 쓰지만, 없으면 그 부분만
    #       77(SKIP)로 끝난다. 77을 통과로 세지 않는 것은 이 러너의 일이다 — G1)
    #    · `grid=False` — 격자가 아니다.
    #    · 🔴 **다섯 번째 원소가 `False`인 것이 핵심이다.** 이 스크립트의 종료 1은
    #      「알려진 감사 지적」이 아니라 **계약 위반 = 실행 실패**다. `audit=True`로
    #      두면 위반이 `citation_audit.py`와 같은 열에 섞여 «원래 빨간 것»이 된다.
    ("digest_budget.py", "요약 예산 · G19′ 기수 계약 집행",      False, False, False),
    ("rel_dist.py",      "rel 분포 · 등컷 θ 유도 (378쌍)",      True,  False, False),
    ("consistency_audit.py", "문서 CLAIM 대조 (G4 집행)",       False, False, False),
    # 🆕 후속 11 (레인 H·J) — **인용 감사.** `consistency_audit.py`가 숫자를 보고
    #    이것이 `file:line`을 본다. 오프라인이고 API 키도 ollama도 안 쓰므로
    #    `needs_extra=False`이며 격자도 아니다.
    #    🔄 **다섯 번째 원소가 `True`인 유일한 항목이다** (레인 N · B안). 이 도구는
    #    종료 1로 끝나고 **그대로 둔다** — 살아 있는 계획서의 의심 125건은 옛
    #    번호가 정상인 기록물이 아니라, 되닻을 내리면 이동 대장이 지워지는
    #    자리다(레인 J). 레인 N이 제외 모델을 **인용 하나 단위**로 정했고
    #    (표식이 바로 옆에 붙은 인용 39개만 제외, 전부 이름을 찍는다), 그래도
    #    남는 125건은 진짜로 남는 것이다. **숨기지 않고 열을 나눈다.**
    ("citation_audit.py", "실험 23 인용 감사 (후속 11 · G18)",   False, False, True),
    # 🆕 하이브리드 재진입 조건 1의 계측기 (레인 I). ollama(bge-m3)가 필요하고
    #    없으면 **77(SKIP)**로 끝난다 — `hybrid_sim.py`·`rel_dist.py`와 같은
    #    `needs_extra=True` 자리다. 격자가 아니므로 `--quick`이 빼지 않는다.
    ("probe_types.py", "실험 22 유형 라벨 프로브 24개 (조건 1)", True,  False, False),
    # 🔄 실험 25 — 응답 수준 **재설계**(레인 M). 실험 24의 셀·문항을 부분집합으로
    #    품고 실행 중에 그것을 재현하지 못하면 멈춘다. 로컬 `qwen3:8b`가 필요하므로 `needs_extra=True`이고
    #    ollama가 없으면 **77(SKIP)**으로 끝난다(통과가 아니다 — G1).
    #    격자가 아니므로 `--quick`도 이것은 돌린다. 웜 체크포인트면 생성 0건이다.
    ("response_quality.py", "실험 25 응답 수준 교환비 재설계 (Q2-2)", True,  False, False),
    # 🆕 실험 26 — **채점기 검증**(결정 4 K · 미해결 U4). 사람 라벨 32개로 축자
    #    `survived_v2`와 임베딩(bge-m3)을 사전 등록된 홀드아웃에서 비교한다.
    #    · `needs_extra=True` — `probe_types.py`와 **같은 자리**다. 정상 환경에서는
    #      `EMBED_CACHE.json`의 34개로 **라이브 호출 0회**로 돌지만, 그 캐시는
    #      **추적되지 않는다.** 새로 받은 저장소에는 캐시가 없고 그때 ollama(bge-m3)가
    #      실제로 필요하다 — 없으면 **77(SKIP)**이고 러너가 실패와 따로 센다(G1).
    #      🔴 «내 기계에서 캐시가 차 있다»를 «의존성이 없다»로 적으면 다음 사람이
    #      받은 저장소에서 이 줄이 거짓말이 된다.
    #    · `grid=False` — 격자가 아니다. `--quick`도 이것은 돌린다.
    #    · 🔴 **다섯 번째 원소가 `False`인 것이 핵심이다.** 이 스크립트의 종료 1은
    #      「알려진 감사 지적」이 아니라 **음성 대조가 발화하지 않았다**는 실행
    #      실패다. `audit=True`로 두면 그 실패가 `citation_audit.py`와 같은 열에
    #      섞여 «원래 빨간 것»이 되고, 그때 이 실험은 검사가 아니라 장식이 된다.
    ("scorer_eval.py", "실험 26 채점기 검증 (라벨 32 · 홀드아웃)", True, False, False),
    # 🆕 실험 27 — **요약을 채점한다** (M1 형식 · M2 사건 · M3 순서 · M4 누출).
    #    ADR-016 §결과의 «비운 자리»를 채우는 실험이고, §3.3의 혼합집합 비교 규칙을
    #    **종료 코드로 집행**한다(제목에 항목 집합 이름이 없는 열은 못 만든다).
    #    · `needs_extra=True` — lifetime 요약을 만들려면 로컬 `qwen3:8b`가 필요하다.
    #      `LIFETIME_S27.json`이 있으면 **생성 0건**으로 돌지만 그 파일은 새로 받은
    #      저장소에 없고, 그때 ollama가 실제로 필요하다 — 없으면 **77(SKIP)**이다.
    #      🔴 «내 기계에 체크포인트가 있다»를 «의존성이 없다»로 적으면 다음 사람이
    #      받은 저장소에서 이 줄이 거짓말이 된다 (`scorer_eval.py`와 같은 자리).
    #    · `grid=False` — 격자가 아니다. `--quick`도 이것은 돌린다.
    #    · 🔴 **다섯 번째 원소가 `False`인 것이 핵심이다.** 이 스크립트의 종료 1은
    #      「알려진 감사 지적」이 아니라 **표 규율 위반 또는 음성 대조 발화 실패**,
    #      즉 실행 실패다. `audit=True`로 두면 그것이 `citation_audit.py`와 같은
    #      열에 섞여 «원래 빨간 것»이 되고, 그때 이 실험은 검사가 아니라 장식이 된다.
    ("summary_prototype.py", "실험 27 요약 채점 M1~M4 (혼합집합 비교 규칙)",
     True, False, False),
    # 🆕 실험 28 — **요인 분해.** 실험 27이 낸 «네 개의 0»이 「P4 지시 / 재압축 /
    #    재료 24세션」 중 무엇 탓인지 가른다. 요인을 **하나씩만** 움직인 팔 다섯을
    #    세우고 `FactorRule`이 «앵커와 정확히 한 요인»을 **종료 코드로** 집행한다.
    #    · `needs_extra=True` — 요약 셋을 만들려면 로컬 `qwen3:8b`가 필요하다.
    #      `ABLATION_S28.json`이 있으면 **생성 0건**으로 돌지만 그 파일은 새로 받은
    #      저장소에 없고, 그때 ollama가 실제로 필요하다 — 없으면 **77(SKIP)**이다.
    #      🔴 «내 기계에 체크포인트가 있다»를 «의존성이 없다»로 적으면 다음 사람이
    #      받은 저장소에서 이 줄이 거짓말이 된다 (`summary_prototype.py`와 같은 자리).
    #    · `grid=False` — 격자가 아니다. `--quick`도 이것은 돌린다.
    #    · 🔴 **다섯 번째 원소가 `False`인 것이 핵심이다.** 이 스크립트의 종료 1은
    #      「알려진 감사 지적」이 아니라 **요인 규율 위반 · 표 규율 위반 · 조립 앵커
    #      불일치 · 음성 대조 발화 실패**, 즉 실행 실패다. `audit=True`로 두면
    #      그것이 `citation_audit.py`와 같은 열에 섞여 «원래 빨간 것»이 된다.
    #    ⚠️ **`summary_prototype.py` 바로 뒤에 둔다.** 이 실험의 A0은 그 실험이 만든
    #      `LIFETIME_S27.json`이고, 그 파일이 없으면 여기서 만들게 된다 — 순서가
    #      바뀌면 «누가 그 생성을 했나»가 실행마다 달라진다.
    ("summary_ablation.py", "실험 28 요인 분해 (지시·재압축·재료 크기)",
     True, False, False),
    # 🆕 실험 29 — **게이트 포화.** 어휘(`_recall_vocab`)가 자라면 게이트 발화율이
    #    어디까지 오르는가, 그리고 순차 곡선이 평평한 것이 **휴리스틱의 성질인지
    #    코퍼스/추출기의 성질인지**를 가른다.
    #    · `needs_extra=False` — **ollama도 API 키도 한 번도 안 부른다.** 재료는
    #      `eval/corpus/corpus.jsonl`과 `eval/fact-ledger.yaml`뿐이고, 임시 DB는
    #      `%TEMP%`에 만들었다가 지운다. 새로 받은 저장소에서도 그대로 돈다 —
    #      `scorer_eval.py`·`summary_prototype.py`가 «캐시가 있으면 0회»라 적은
    #      자리와 **다르다.** 저기는 캐시가 없으면 의존성이 살아나고, 여기는 없다.
    #    · `grid=False` — 격자가 아니다. `--quick`도 이것은 돌린다.
    #    · 🔴 **다섯 번째 원소가 `False`인 것이 핵심이다.** 이 스크립트의 종료 1은
    #      「알려진 감사 지적」이 아니라 **앵커 불일치 · 단조성 위반 · 바닥값 이동 ·
    #      분모 어긋남 · N 미유도**, 즉 실행 실패다. `audit=True`로 두면 그것이
    #      `citation_audit.py`와 같은 열에 섞여 «원래 빨간 것»이 된다.
    ("gate_saturation.py", "실험 29 게이트 포화 (어휘 성장 · 발화율 극한)",
     False, False, False),
    # 🆕 실험 30 — **박힌 상수 감사.** 상수 31개를 «코퍼스 고유 / 언어 고유 / 도메인
    #    무관»으로 가르고, `UBIQUITOUS`를 여섯 대체 집합으로 갈아 끼워 실험
    #    19·20·26·27이 각각 얼마나 움직이는지 다시 잰다.
    #    · `needs_extra=False` — **ollama도 API 키도 한 번도 안 부른다.** 재료가
    #      전부 **캐시된 생성물**이다(`DRIFT_RESULTS.json` 28태그 ·
    #      `SUMMARY_LOCAL.json` 32태그 · `LIFETIME_S27.json` · `EMBED_CACHE.json`).
    #      ⚠️ 그래서 `gate_saturation.py`와 **같은 자리이되 이유가 다르다** — 저기는
    #      원자료(코퍼스·대장)만 읽어서 의존성이 없고, 여기는 앞선 실험들이 남긴
    #      체크포인트를 읽어서 없다. 🔴 **체크포인트가 지워지면 이 단계는 의존성이
    #      살아나는 것이 아니라 «못 돈다»** — `scorer_eval`·`summary_prototype`이
    #      «캐시가 없으면 생성한다»인 것과 반대다. 그때 종료 1이 나는 것이 옳다.
    #    · `grid=False` — 격자가 아니다.
    #    · 🔴 **다섯 번째 원소가 `False`인 것이 핵심이다.** 이 스크립트의 종료 1은
    #      「알려진 감사 지적」이 아니라 **앵커 31개 불일치 · 심은 위반 미발화 ·
    #      되돌림 실패**, 즉 실행 실패다.
    ("hardcoding_audit.py", "실험 30 박힌 상수 감사 (분류 · 유도 · 갈아 끼우기)",
     False, False, False),
    # 🆕 실험 31 — **두 번째 코퍼스.** `eval2/`(존댓말·업무·다화제 · 6세션 192턴)를
    #    계측기 무변경으로 통과시켜 게이트·어근·세 채점기·θ·τ가 어떻게 반응하는지
    #    **두 열로 나란히** 찍는다(화살표 없음 — 모집단이 다르다).
    #    · `needs_extra=False` — **LLM을 한 번도 안 부른다.** 코퍼스 생성도 채점도
    #      규칙 기반이고, 임시 DB는 만들었다 지운다. `eval2/`가 저장소 자산이므로
    #      새로 받은 저장소에서도 그대로 돈다.
    #    ⚠️ **`eval2/`를 다시 만들지 않는다.** 이 단계는 읽기만 하고, 재생성은
    #      `eval2/gen_corpus2.py`가 따로 한다(seed 20260910 · 바이트 동일). 러너가
    #      코퍼스를 다시 쓰면 «오늘의 실행이 오늘의 자료를 만든» 것이 된다.
    #    · `grid=False` · 다섯 번째 원소 `False` — 종료 1은 **축 ① 위반 · 화살표
    #      규약 위반 · 결정성 깨짐**, 즉 실행 실패다.
    ("corpus2_probe.py", "실험 31 두 번째 코퍼스 (eval2 · 계측기 무변경)",
     False, False, False),
    # 🆕 wave2 — **실험 번호가 없는 두 측정.** 번호를 안 붙인 근거는 `docs/11`의
    #    «wave2 부록» 머리에 있다(요약 계층 라운드의 «저울과 대조군» 부록과 같은 자리).
    #    · `transition_regen_probe.py` — 전이가 민 digest를 다시 만들면 바이트가 같은가
    #      (T1 · 사전 등록 판정). `needs_extra=True`: 기록(`TRANSITION_REGEN.json`)이
    #      있으면 **ollama 0회**로 같은 표를 다시 찍지만 그 기록은 추적되지 않는다 —
    #      없으면 로컬 `qwen3:8b`가 필요하고, 그것도 없으면 **77(SKIP)**이다.
    #    · `meta_arm.py` — `apply_meta`를 턴마다 태우는 팔(T2 · **모의 `<meta>`**).
    #      LLM을 한 번도 안 부른다. 종료 1은 **앵커 불일치(이 루프 ≠ `soak.replay`)·
    #      빈 채널·`surfaced_count` 합 ≠ 선언**, 즉 실행 실패다.
    #    · 둘 다 `grid=False` · 다섯 번째 원소 `False`.
    ("transition_regen_probe.py", "전이 → 다이제스트 재생성 바이트 대조 (wave2 T1 · 실험 아님)",
     True, False, False),
    ("meta_arm.py", "동기 층 팔 — 모의 <meta> (wave2 T2 · 실험 아님)",
     False, False, False),
    # 🆕 wave3 — F39 재현기(실험 아님). 기록(`CACHE_STATE_REPRO.json`)이 있으면 ollama 0회 · 없으면 77.
    ("cache_state_repro.py", "F39 서버 캐시 상태 → 본문 (wave3 · 실험 아님)",
     True, False, False),
    # 🆕 축 라운드 (레인 A·B가 만들고 마감 파도가 등록) — **실험 번호가 없는 네 측정.** 번호를
    #    안 붙인 근거와 다섯째(`retrieve_scaling.py`)를 **안** 올린 근거는 `docs/11` 끝 «축 라운드»
    #    부록 §G에 있다(지연은 실행마다 갈려서 이 러너의 출력을 단일 출처로 삼을 수 없다).
    #    · 넷 다 `needs_extra=False`(LLM도 ollama도 안 부른다) · `grid=False` · 다섯 번째 원소 `False`.
    #    · `eval_controls_audit.py` — ADR-009 통제 조건 여덟 칸이 `KNOWN`과 다르면 종료 1. 오늘 0이라
    #      «감사 지적»이 아니라 «실패» 어휘다(`consistency_audit.py`와 같은 자리).
    #    · `theta_position.py` — 스위치 기본값의 기준칸이 `BASE_EXPECT`와 다르면 종료 1 · 격자 캐시
    #      미스면 77(격자와 같은 캐시라 같은 이유로 `needs_extra=False`).
    #    · `predicate_vocab_cost.py` · `vecdim_ppr_probe.py` — 판정 없는 재현기(늘 0). 문서에 옮겨
    #      적힌 수를 다시 뽑는 자리로 올린다(G11).
    ("eval_controls_audit.py", "ADR-009 통제 조건 감사 (축 라운드 · 실험 아님)",
     False, False, False),
    ("predicate_vocab_cost.py", "술어 어휘 8·9 대 25의 대가 (축 라운드 · 실험 아님)",
     False, False, False),
    ("vecdim_ppr_probe.py", "벡터 차원 · PPR 축 태깅 (축 라운드 · 실험 아님)",
     False, False, False),
    ("theta_position.py", "θ의 위치 · recency — 격자 2단 (축 라운드 · 실험 아님)",
     False, False, False),
    # 🆕 실험 32 — 엔진 요인 분해(`engine_arms.py`). 컨테이너 둘(OpenSearch+nori · Postgres+pg_bigm)이 필요하다 →
    #    `needs_extra=True` · 없으면 **77(SKIP)**(통과가 아니다 — G1). LLM·ollama는 안 부른다. `grid=False` · 다섯 번째
    #    원소 `False`(종료 1 = 요인·화살표·제목·홀드아웃·G16·A0 등가 위반 = 실행 실패). 지연 절은 흔들리지만 종료 코드를 안 바꾼다. 🆕 실험 33 — θ 격자(`theta_grid.py` · w9close가 번호를 주고 등록 · 근거 docs/11 «실험 결과 (33)» §0). **키도 의존성도 안 쓴다**(LLM·임베딩·엔진 0회 · 소켓 연결 시도는 첫 회에 종료 1) → `needs_extra=False` · 격자 아님(`--quick`이 안 뺀다) · 다섯 번째 원소 `False`(종료 1 = 사전 등록 자기 대조 — 기본값 `BASE_EXPECT` · 빠른 길 · 페널티 영점 · 한 버전 · 불변 — 위반 = 실행 실패). ≈ 3분(열 단위 프로세스 병렬). 🔴 **같은 줄에 붙였다** — 줄을 늘리면 아래 `GRID_FILES` 주석의 이동 대장(자기 인용)과 `.omc/plans/**`의 옛 인용이 밀린다.
    ("engine_arms.py", "실험 32 엔진 요인 분해 (V1 순위 · V2 파이프라인 · 컨테이너 필요)", True, False, False), ("theta_grid.py", "실험 33 θ 격자 — 스위치를 켤지 가르는 격자 (보고 전용 · 판정 안 함)", False, False, False),
    # 🆕 라운드 2 단계 4 (레인 E) — **격자.** 네 번째 원소가 `True`인 유일한 항목이고
    #    `--quick`이 빼는 것의 전부다. `hybrid_sim`처럼 `needs_extra=True`로 두지
    #    **않는** 이유: 이 스윕은 ollama가 없어도 `REL_CACHE.json`의 39개 벡터로
    #    30셀을 전부 돌린다. 못 도는 경우는 캐시에 없는 텍스트가 필요할 때뿐이고,
    #    그때는 강등하지 않고 **77(SKIP)**로 끝난다 — 러너가 그것을 실패와 따로 센다.
    ("retrieval_sweep.py", "실험 21 검색 격자 30셀 (단계 4·5)", False, True, False),
]

# `--quick`이 빼는 것의 전부. 🔄 **더 이상 비어 있지 않다** — 단계 4가 격자를 만들었고
# 위 `STEPS`의 마지막 항목이 그것이다. `retrieval_sweep.py`가 `experiments/` 아래에
# 있어야 한다는 제약은 `:365`의 `subprocess.run([sys.executable, str(HERE / fname)])`가
# (🔄 이동 대장 — `STEPS`에 항목이 늘 때마다 밀린다: `:258` → `:277`(실험 28)
#  → `:292`(실험 29) → `:324`(실험 30·31 · 32줄) → `:326`(대장 밖 2줄) → `:340`(wave2 · 14줄) → `:343`(wave3 · 3줄) → `:361`(축 라운드 · 18줄) → `:365`(실험 32 · 4줄).
#  **지우지 않고 칸을 붙인다** — 되닻을 내리면 «언제부터 그랬나»가 사라진다.
#  ⚠️ 이 줄을 미는 편집은 `.omc/plans/**`의 인용 4개도 함께 민다 — 실험 29
#  라운드가 그것을 고치지 못하고 «의심»으로 남겼고, 이 라운드가 접으면서 고쳤다.)
# `HERE`(= `experiments/`) 아래에서만 이름을 푸는 데서 온다.
GRID_FILES = {"retrieval_sweep.py"}

# 🔴 `--quick`을 실제로 모는 것은 `STEPS`의 네 번째 원소이고 `GRID_FILES`는 그것을
#    사람이 읽는 이름으로 적어 둔 것이다. **둘이 갈라지면 이 목록은 거짓말이 된다** —
#    그래서 import 시점에 대조한다. 항등이 아니다: 한쪽만 고치면 여기서 터진다.
assert {s[0] for s in STEPS if s[3]} == GRID_FILES, (
    f"GRID_FILES와 STEPS의 격자 표시가 다르다: "
    f"{ {s[0] for s in STEPS if s[3]} } vs {GRID_FILES}")


# 🆕 레인 N B안 — **감사 지적**으로 세는 단계와, 오늘 알려진 지적 수.
#
# `GRID_FILES`와 같은 이유로 사람이 읽는 이름을 따로 적고 import 시점에 대조한다.
# 항등이 아니다: `STEPS`의 표시만 지우거나 여기만 지우면 그 자리에서 터진다.
AUDIT_FILES = {"citation_audit.py"}

# 🔴 **오늘 빨간 감사 단계의 수.** 이 숫자를 요약 줄에 나란히 찍는 것이 B안의
#    전부다 — `감사 지적 1건 (알려진 상태 1건)`이면 어제와 같다는 뜻이고,
#    `2건 (알려진 상태 1건)`이면 **새 감사가 빨개졌다**는 뜻이다.
#    이 상수를 줄이려면 지적을 실제로 없애야 한다. 늘리려면 이유를 적어야 한다.
AUDIT_KNOWN_RED = 1

assert {s[0] for s in STEPS if s[4]} == AUDIT_FILES, (
    f"AUDIT_FILES와 STEPS의 감사 표시가 다르다: "
    f"{ {s[0] for s in STEPS if s[4]} } vs {AUDIT_FILES}")
assert AUDIT_KNOWN_RED <= len(AUDIT_FILES), (
    f"알려진 빨간 감사 {AUDIT_KNOWN_RED}건이 감사 단계 {len(AUDIT_FILES)}건보다 많다")


USAGE = ("사용법: python experiments/run_all.py [--quick]\n"
         "  --quick   격자(retrieval_sweep.py)를 뺀다. 그 외에는 전량과 같다\n"
         "  (모르는 인자는 **조용히 삼키지 않는다** — 종료 2)")


def parse_args(argv):
    """
    🆕 단계 1 작업 7 — argv를 **실제로** 읽는다.

    🔴 여태 이 파일에는 argv 처리가 없었다. `--quick`은 무시됐고, 그것을 적은
    수용 기준은 전량 실행을 보고 통과했다. **모르는 인자에 종료 2로 끝내는 것이
    이 함수의 절반**이다 — 삼키면 다음 사람도 같은 방식으로 속는다.
    """
    quick = False
    for a in argv:
        if a == "--quick":
            quick = True
        elif a in ("-h", "--help"):
            print(USAGE)
            raise SystemExit(0)
        else:
            print(f"모르는 인자: {a!r}\n{USAGE}")
            raise SystemExit(2)
    return quick


def main(argv=None):
    quick = parse_args(sys.argv[1:] if argv is None else argv)
    steps = [s for s in STEPS if not (quick and s[3])]
    dropped = [s[0] for s in STEPS if quick and s[3]]
    mode = "--quick (격자 제외)" if quick else "전량"
    parts = [
        "=" * 78,
        "실험 결과 스냅샷 — 이 파일이 수치의 단일 출처다",
        f"생성: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"재현: python experiments/run_all.py{' --quick' if quick else ''}",
        f"모드: {mode} · 실행 대상 {len(steps)}건"
        + (f" · 제외 {dropped}" if dropped else
           (" · 제외 0건 (--quick인데 뺄 격자가 없다)" if quick else
            f" · 제외 0건 (전량 모드 — 격자 {sorted(GRID_FILES)}도 돈다)")),
        "=" * 78,
    ]
    print(f"모드: {mode} · 실행 대상 {len(steps)}건 / 전체 {len(STEPS)}건")
    if quick and not dropped:
        # 🔄 단계 4 이후로 이 가지는 **도달하지 않는다** (격자가 `STEPS`에 있다).
        #    지우지 않는 이유는 격자가 다시 빠지는 라운드가 오면 그때 다시 참이
        #    되기 때문이고, *"뺀 것이 없다"*와 *"플래그가 무시됐다"*는 그때도
        #    다른 사건이기 때문이다.
        print("  ⚠️ --quick이 뺀 것은 **0건**이다 (`STEPS`에 격자가 없다). "
              "플래그가 무시된 것이 아니라 뺄 것이 없다.")
    # 🆕 레인 N B안 — `failed`(실행 실패)와 `audited`(감사 지적)를 **따로** 센다.
    #    같은 리스트에 넣으면 요약 줄이 다시 거짓말을 한다.
    failed, skipped, audited = [], [], []

    for fname, desc, needs_extra, _grid, is_audit in steps:
        print(f"실행 중: {desc} ...", end=" ", flush=True)
        r = subprocess.run([sys.executable, str(HERE / fname)],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=CHILD_ENV)   # 🔄 재생성 금지를 자식에게 (파일 끝 절)
        if r.returncode == 0:
            print("✅")
            body = r.stdout
        elif r.returncode == SKIP_CODE:
            # 실패로 세지 않는다. 하지만 **통과로도 세지 않는다** — 목록에 남긴다.
            print("⏭️ SKIP(77)")
            skipped.append((fname, _skip_reason(r)))   # 🔄 자식이 찍은 이유 줄과 함께 (파일 끝 절)
            body = (f"[건너뜀 — 종료 코드 {SKIP_CODE}: 이 환경에서 재현 불가]\n"
                    f"{r.stdout.rstrip()}\n{(r.stderr or '').strip()[-400:]}")
        elif is_audit:
            # 🔄 감사 단계의 0이 아닌 종료는 **실행 실패가 아니라 지적**이다.
            #    종료 코드는 손대지 않았다 — 이 러너가 어휘만 나눈다.
            #    stdout을 통째로 싣는다: 지적의 내용이 곧 이 단계의 산출물이다.
            print("🔍 감사 지적")
            audited.append(fname)
            body = (f"[감사 지적 — 종료 코드 {r.returncode}. "
                    f"실행은 정상이고 검사가 지적을 냈다]\n"
                    f"{r.stdout.rstrip()}")
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
            parts.append("  · hybrid_sim.py는 `pip install sentence-transformers`가 "
                         "필요하고, rel_dist.py·probe_types.py는 ollama(bge-m3)가 필요하다")
    elif not skipped and not audited:
        parts.append("전체 실험 정상 실행")
    if audited:
        parts.append(f"감사 지적: {', '.join(audited)}  "
                     f"(알려진 상태 {AUDIT_KNOWN_RED}건)")
        parts.append("  · **실행 실패가 아니다.** 검사가 옳게 동작하고 지적을 "
                     "냈다는 뜻이며, 지적의 전문이 위 절에 그대로 실려 있다")
        if len(audited) > AUDIT_KNOWN_RED:
            parts.append(f"  🔴 알려진 상태보다 {len(audited) - AUDIT_KNOWN_RED}건 "
                         "많다 — **새로 빨개진 감사가 있다**")
    if skipped:
        parts.append("건너뜀(77): " + ", ".join(f for f, _ in skipped))
        parts += ["  · **통과가 아니라 미측정이다.** 이유는 자식이 찍은 줄 그대로:"] + [f"    {f}: {why}" for f, why in skipped]   # 🔄 고정 문구였다 (파일 끝 절)
    parts.append("=" * 78)

    OUT.write_text("\n".join(parts), encoding="utf-8")
    print(f"\n저장: {OUT}")
    print(f"  실행 {len(steps)}건 · 실패 {len(failed)}건 · "
          f"감사 지적 {len(audited)}건 (알려진 상태 {AUDIT_KNOWN_RED}건) · "
          f"SKIP {len(skipped)}건")
    if len(audited) > AUDIT_KNOWN_RED:
        print(f"  🔴 감사 지적이 알려진 상태보다 "
              f"{len(audited) - AUDIT_KNOWN_RED}건 많다 — 새로 빨개진 감사가 있다")

    # 캐시 크기는 **경고만** 한다 (rev2). 실패시키지 않는 이유: `EMBED_CACHE.json`이
    # 이미 상한 근처이고, 여기서 실패로 만들면 G1이 즉시 깨진다. 상한은
    # "이 파일이 커지고 있다"를 눈에 띄게 하려는 것이지 게이트가 아니다.
    for w in E.cache_size_warnings():
        print(f"  {w}")


# 🔴 2026-09-11 — 자식 단계는 **기록과 런타임이 다르면 라이브로 다시 만들지 않는다.**
#    ollama 자동 업데이트(0.33.3 → 0.34.0) 뒤 이 러너가 `response_quality.py`를 통해 체크포인트에
#    153건을 덧쓴 일이 있다(되돌렸다). 판정은 `prototype/llm.py`의 `_guard_regen`이 하고, 걸리면
#    그 단계는 77(SKIP)이다 — **통과가 아니다**(G1). 요약 줄의 «건너뜀(77)» 목록에 남는다.
import os                                                    # noqa: E402
CHILD_ENV = dict(os.environ, MEMARCH_FORBID_REGEN="1")


# 🔄 2026-09-11 (w10record) — SKIP 요약의 이유를 **자식이 찍은 줄**로 싣는다.
#    요약의 설명은 «임베딩 캐시 미스 + ollama 부재» 한 줄로 고정돼 있었다 — F40 가드의 77
#    (`llm._guard_regen`)이나 컨테이너가 없는 실험 32의 77에는 틀린 이유였다. 이유를 아는 것은
#    자식뿐이라 러너는 고르지 않고 옮긴다: 자식 출력에서 SKIP을 알리는 마지막 줄(`SKIP_MARKS`)을,
#    없으면 마지막 비어 있지 않은 줄을. 둘 다 없으면 «찍지 않았다»고 적는다 — 빈칸으로 두지 않는다.
#    루프와 요약의 세 줄은 같은 수의 줄로 바꿨다(위 이동 대장이 가리키는 `subprocess.run` 줄을
#    밀지 않으려고). 함수는 `main`이 불리기 전에 정의돼야 해서 `__main__` 가지 앞에 둔다.
#    지키는 시험: `experiments/tests/test_run_all_skip_reason.py`.
SKIP_MARKS = ("⏭️", "SKIP", "(77)", "종료 77")


def _skip_reason(r, width=240):
    lines = [s.strip() for s in f"{r.stdout or ''}\n{r.stderr or ''}".splitlines() if s.strip()]
    marked = [s for s in lines if any(m in s for m in SKIP_MARKS)]
    why = (marked or lines or ["(자식이 이유 줄을 찍지 않았다)"])[-1]
    return why if len(why) <= width else why[:width - 1] + "…"


if __name__ == "__main__":
    main()
