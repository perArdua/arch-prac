# docs

설계 문서와 결정 기록을 모아 둔 폴더입니다.

- `00`~`19`: 설계 문서입니다. 읽는 순서는 루트 [`README.md`](../README.md)에 있습니다.
- [`adr/`](adr/): 결정 기록(ADR)입니다. 결정마다 대안과 근거를 적었습니다.
- [`decisions/`](decisions/): 사용자가 내린 결정 기록입니다.
  - [`decisions-0911.md`](decisions/decisions-0911.md): θ, 검색 엔진, ollama 버전에 관한 결정
  - [`decisions-0912-pending.md`](decisions/decisions-0912-pending.md): 수리 계획 Q1~Q11에 관한 결정
  - 결정마다 고른 안, 이유, 버린 안의 대가를 적었습니다.

## 문서에 나오는 `.omc/` 경로
문서 곳곳에 `.omc/plans/...`, `.omc/notepads/...`, `.omc/handoff/NEXT.md` 같은 경로가 나옵니다. 작업할 때 쓰던 로컬 폴더(작업 메모와 계획서 초안)라서 저장소에는 올리지 않았고, 링크를 눌러도 열리지 않습니다.

공개가 필요한 것만 저장소로 옮겨 두었습니다.
- 결정 기록: `docs/decisions/`
- 실험을 돌릴 때 필요한 기준값 파일: `experiments/data/baseline/`
- 검증 스크립트: `tools/`
