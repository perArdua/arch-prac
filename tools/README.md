# tools

코드를 고친 전후로 동작이 같은지 확인할 때 쓰는 스크립트입니다. 둘 다 저장소 루트에서 실행합니다.

## freeze_hash.py
낱말 자르기에 쓰는 네 가지(`_stem`, `_ENDINGS`, `_PARTICLE`, `Memory._roots`)의 해시를 출력합니다.
- 원문 해시: 소스 코드가 한 글자라도 바뀌면 달라집니다.
- 출력 해시: 정해 둔 입력에 대한 결과가 바뀔 때만 달라집니다.

```bash
PYTHONIOENCODING=utf-8 python -B tools/freeze_hash.py
```

## fp.py
기본 설정에서 검색과 게이트가 내는 결과를 JSON으로 저장합니다. 이 파일의 sha256을 기본 동작의 지문으로 씁니다.

```bash
PYTHONIOENCODING=utf-8 python -B tools/fp.py out.json
```

## 참고
- 폴더를 나누고 주석을 정리할 때 이 두 스크립트로 전후 결과가 같은지 확인했습니다.
- 기대값은 `_stem` 원문 해시 `d6563f46…`, 지문 `09c0f100f914…`입니다.
- 로컬 모델 서버는 꺼 둔 상태로 실행합니다(예: `OLLAMA_HOST=http://127.0.0.1:9`).
