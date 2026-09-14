# -*- coding: utf-8 -*-
"""
eval3/gen_corpus3.py — **규모 코퍼스**(색인 3,000행)를 df 레짐 셋으로 생성한다.

## 왜 이 파일이 있나

`docs/17-gap-disposition.md`의 «아직 열린 것» 상위 셋(검B2 θ 스위치 격자 · 검B3
사전 토큰화 · 밖E10 표 밖 술어의 기본값)과 미뤄 둔 엔진 라운드(§9)가 **같은 선행**을
갖는다 — 색인이 21행뿐이라 잴 수 없다(검C1). 이 파일이 그 선행을 만든다.

## 🔴 이 코퍼스가 걸리는 순환 — 그리고 그것을 «축»으로 바꾼 방법

검C1이 이미 적었다: *"합성 코퍼스의 df 분포는 생성기가 정한다 — docs/12 §4의
순환이 그대로 걸린다."* 내가 코퍼스를 만들면 df 분포를 내가 정하고, 그러면
«IDF가 이긴다»는 내 생성기의 함수이지 검색의 성질이 아니다.

그래서 df 분포를 **숨은 상수가 아니라 선언된 축**으로 둔다. 벌크 행의 **슬롯 값**
(사람·장소·음식·물건 …)을 순위 r의 가중치 r^(-s)로 뽑고, 지수 s를 레짐마다 하나씩
**사전 등록**한다(`REGIMES`). 레짐이 바꾸는 것은 **그 지수 하나뿐**이다:

  · 같은 것 — 핵심 항목(문항의 근거·방해물) 전부 · 문항 전부 · 벌크 행의 **골격**
    (id · 종류 · 문형 틀 · 술어 · 시점 · 무게) · 슬롯마다 뽑는 난수 u(항목 id로 시드)
    · 노이즈 턴 · 배치.
  · 다른 것 — 같은 u를 **다른 지수의 누적분포**에 넣어 고른 슬롯 값. 그래서 레짐
    사이의 차이는 «같은 난수가 다른 모양의 분포를 통과했다»뿐이다.

그러면 다음 라운드의 결론은 «IDF가 이긴다»가 아니라 **«df가 이렇게 생겼을 때
IDF가 이만큼 움직인다»**가 된다. 🔴 레짐 사이에 화살표를 그리지 않는다 — 세 레짐은
**서로 다른 모집단**이고, 어느 것도 «실사용»이 아니다.

## 🔴 같게 둔 것 (eval과) — 그리고 그것을 보장하는 방법

**`experiments/gen_corpus.py`의 함수 객체를 그대로 부른다** — `planted_index` ·
`render` · `generate` · `session_ids`. 사본이 아니므로 노이즈 풀 · 하드 네거티브
문턱(`0.12`/`0.20`) · 화자 교대(`t % 2`) · 심은 항목의 화자 배치 · 템플릿
(`"{text}. 말했었나?"`) · 세션당 30턴이 **글자 그대로** eval과 같다(F12).
이름도 eval과 같다(지우·서준) — `scoring.UBIQUITOUS = {"지우"}`가 **작동하는**
코퍼스여야 그 상수가 레짐마다 무엇을 하는지 보인다(eval2는 이름을 바꿔 그 상수가
아무것도 안 했다).

⚠️ `gen_corpus.generate`는 같은 (세션,턴)에 항목이 둘이면 뒤로 밀고, **밀린 항목이
남으면 조용히 버린다**(`pending`을 끝에서 검사하지 않는다 — eval2의 사본은 검사한다).
그래서 이 파일은 모든 심은 항목에 **서로 다른 자리**를 주고, 생성 뒤에 «모든 id가
정확히 한 번, 자기 자리에» 있는지를 확인해서 아니면 죽는다.

## 🔴 자가저작

저자 1명(Claude Opus 5 — 이 저장소의 executor 레인 하나)이 핵심 항목 · 문항 · 슬롯
풀 · 풀의 순위(= 지프 레짐에서 무엇이 흔한가)를 전부 썼다. **LLM 미사용.** 규칙 기반
결정적 생성이고 같은 명령이 같은 바이트를 낸다(`--check`). 선언 정본은 각 대장의
`meta.authorship`이다.

실행 (저장소 뿌리에서):
    PYTHONIOENCODING=utf-8 python -B eval3/gen_corpus3.py            # 쓴다
    PYTHONIOENCODING=utf-8 python -B eval3/gen_corpus3.py --check    # 디스크와 바이트 대조만
출력: eval3/fact-ledger.yaml(핵심) · eval3/questions.yaml ·
      eval3/regimes/<레짐>/fact-ledger.yaml · eval3/regimes/<레짐>/corpus/corpus.jsonl

🔴 `eval/`·`eval2/`에는 한 바이트도 쓰지 않는다(A8). `gen_corpus`는 import만 한다.
"""
import hashlib
import json
import random
import sys
from pathlib import Path

import yaml

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "prototype"))

import gen_corpus as G                                          # noqa: E402

# ══════════════════════════════════════════════════════════════════════
# 🔴 사전 등록 — 값을 보기 전에 박은 상수. 프로브(`experiments/eval3_probe.py`)가
#    **여기서 import해서** 첫 화면에 찍는다(정의가 두 벌이 되지 않게).
# ══════════════════════════════════════════════════════════════════════

# ① 규모. **살아 있는 색인 행 = 3,000.** 왜 이 수인가:
#    · ADR-003 «우리 규모»(1년 후 검색 대상 합계 1,500~3,000)의 **상단**이다.
#    · `retrieve_scaling.py`가 합성 틀 색인에서 `retrieve` p95가 20 ms 자에 닿는 행 수로
#      잰 값(≈ 3,000 · 두 재실행 2,996 · 3,063)이 여기 떨어진다 — 자 위에서 바로 잰다.
#    구성은 ADR-003 표의 사실 상한 500 + 사건 2,500. `soak.ingest`는 사실·사건 두 종류만
#    색인하므로 ADR의 해석·고유명사(각 50~200)가 들어갈 행 종류가 없고, 합계를 맞추려고
#    사건을 ADR 사건 상한(2,400)보다 100 많게 뒀다. `retrieve`는 종류를 안 가리고 행을
#    전부 훑으므로 지연에는 무관하고, τ에는 관계한다(사실 행은 감정 무게 0).
N_ALIVE = 3000
N_FACTS_TOTAL = 503          # 그중 3행이 단일값 술어 갱신으로 무효화된다
N_EVENTS_TOTAL = 2500
N_SUPERSEDED_IN_TABLE = 3    # 직업 2 · 거주지 1 — `upsert_fact`가 색인 복사본을 지운다
SESSIONS = 365               # ADR-003의 «1년 후» — 하루 한 세션
TURNS_PER_SESSION = G.TURNS_PER_SESSION     # 30 — eval과 같은 값(같은 상수를 읽는다)

# ② 문항. 채점 대상(근거가 대장에 있는 것) 48 · 제외 12(기권 8 · 커버리지 4).
#    분모 48은 엔진 조건(«IDF가 움직일 수 있는 문항 ≥ 6»)의 **여덟 배**다 — 6이
#    분모에 비해 너무 크면 조건이 문항 수의 함수가 된다.
N_QUESTIONS = 60
N_SCORED = 48
QUESTION_TYPES = {"lexical_distractor": 12, "single_hop": 12, "knowledge_update": 12,
                  "multi_session": 6, "temporal": 6, "abstention": 8, "coverage": 4}

# ③ df 레짐 셋. (디렉터리 이름, 표시 이름, 지수 s, 무엇을 모사하나 — 한 문장)
REGIMES = [
    ("s0-flat", "고르게 s=0", 0.0,
     "화제와 등장인물이 날마다 바뀌는 긴 일상 대화 — 유저가 주변 사람·장소·물건 얘기를 "
     "고르게 해서, 어느 슬롯 값이든 다시 나올 확률이 같다."),
    ("s1-zipf", "지프 s=1", 1.0,
     "자연어 낱말 빈도의 교과서 모양(지프 법칙 — 순위 r의 빈도가 1/r에 비례) — 몇몇 값이 "
     "자주, 대부분은 드물게 나온다."),
    ("s2-dominant", "소수 지배 s=2", 2.0,
     "두 사람의 관계에 갇힌 롤플레이 — 기억 대부분에 같은 이름(지우·서준)과 같은 몇 가지 "
     "소재가 나온다. s=2는 사람 슬롯 1위(지우)의 몫 ≈ 62%가 eval에서 `지우`가 색인 21행 중 "
     "12행(57%)에 나온 것과 가장 가까운 정수 지수라서 골랐다."),
]

# ④ 어휘적 방해물. 군집 12(표면 문자열 하나씩) · 서로 다른 방해 항목 36 · 군집마다 ≥ 3.
CLUSTER_KEYS = ["나비", "하늘", "두부", "보리", "호두", "바다",
                "사과", "이직", "생일", "고양이", "커피", "성수"]
N_DISTRACTORS = 36
MIN_DISTRACTORS_PER_CLUSTER = 3
# 기권 문항의 화제 — 색인 어느 행에도 없어야 «들은 적 없다»가 정답이다.
ABSTENTION_KEYS = ["전공", "스키", "오빠", "수영", "골프", "땅콩", "남자친구"]

# ⑤ 술어. `Memory.PREDICATE_CARDINALITY`(표 8종) 기준 안 8 · 밖 17 = 25종.
#    밖 술어의 갱신 사슬 6개 — 대장은 옛 값을 무효라 하지만, 표 밖 술어의 기본
#    카디널리티가 «many»라 `upsert_fact`가 병존시킨다(밖E10이 겨누는 자리).
PRED_IN = 8
PRED_OUT = 17
N_OUT_TABLE_CHAINS = 6

# ⑥ 엔진 라운드의 조건 (docs/17 §9 ①). 이 수 이상인 레짐이 **하나라도** 있으면 열린다.
ENGINE_K = 6

SEED_SKELETON = 20260910     # 골격(자리 · 종류 · 틀 · 무게)
SEED_FILL = 20260911         # 슬롯 난수 u — 항목 id와 섞어 항목마다 시드
SEED_NOISE = 20260912        # `gen_corpus.generate`에 넘기는 노이즈 시드

# τ 탈락 몫을 eval과 같게 둔다 — eval 색인 21행 중 5행이 τ(0.2) 미만이다. 벌크 행의
# 무게를 이 비율로 τ 밑에 떨어뜨려, 지연을 `retrieve_scaling`의 eval 틀과 **어휘·길이만
# 다른** 조건에서 잰다(τ 밑 행은 bigram 계산을 안 탄다).
LOW_WEIGHT_SHARE = 5 / 21
LOW_WEIGHTS = (0.05, 0.1, 0.15)
HIGH_WEIGHTS = (0.3, 0.4, 0.5, 0.6, 0.7, 0.8)


# ══════════════════════════════════════════════════════════════════════
# 슬롯 풀 — **목록 순서가 순위다.** 지프 레짐에서 무엇이 흔한가는 이 순서의 함수이고,
# 그 순서는 저자가 정했다(자가저작). 🔴 군집 키·기권 키를 담은 값은 하나도 없다 —
# 있으면 방해물 개수가 레짐의 함수가 된다(`check_keys`가 생성 때 확인한다).
# ══════════════════════════════════════════════════════════════════════

PERSONS = ["지우", "서준", "민지", "지안", "태오", "유나", "도윤", "서연", "하준", "예린",
           "시우", "수아", "준호", "다은", "현우", "소희", "건우", "채원", "우진", "나연",
           "정민", "가은", "승현", "유진", "재원", "혜인", "동하", "세아", "민재", "윤서",
           "은호", "아린", "성민", "지유", "태민", "해원", "로운", "은채", "주원", "서윤"]
ACQ = PERSONS[2:]            # 지인 — 지우·서준을 뺀 순위 그대로

POOLS = {
    "PLACE": ["홍대", "연남동", "합정", "을지로", "익선동", "한남동", "이태원", "신촌", "강남역",
              "잠실", "여의도", "광화문", "종로", "명동", "건대", "왕십리", "신림", "사당", "판교",
              "분당", "일산", "부천", "인천", "수원", "동대문", "혜화", "삼청동", "북촌", "서촌",
              "문래동", "뚝섬", "압구정", "청담", "가로수길", "상수", "용산", "노량진", "목동",
              "마포", "공덕", "서울역", "청량리", "회기", "성북동", "수유", "노원", "도봉", "구로",
              "가산", "영등포", "당산", "선릉", "삼성동", "역삼", "교대", "방배", "반포", "한강진",
              "석촌호수", "경리단길"],
    "FOOD": ["떡볶이", "김치찌개", "된장찌개", "삼겹살", "치킨", "피자", "파스타", "라멘", "초밥",
             "우동", "짜장면", "짬뽕", "탕수육", "냉면", "칼국수", "수제비", "김밥", "쌀국수",
             "마라탕", "훠궈", "곱창", "막창", "족발", "보쌈", "순대국", "감자탕", "부대찌개",
             "닭갈비", "찜닭", "갈비탕", "설렁탕", "돈가스", "카레", "햄버거", "샌드위치", "샐러드",
             "타코", "부리토", "스테이크", "오믈렛", "팬케이크", "와플", "빙수", "붕어빵", "호떡",
             "떡국", "만두", "잔치국수", "비빔밥", "제육볶음", "오징어볶음", "낙지볶음", "아구찜",
             "해물파전", "김치전", "육회", "물회", "연어덮밥", "규동", "텐동"],
    "SHOP": ["편의점", "다이소", "올리브영", "백화점", "마트", "시장", "서점", "문구점", "꽃집",
             "빵집", "약국", "안경점", "옷가게", "신발가게", "소품샵", "편집숍", "아울렛", "중고서점",
             "전자상가", "철물점", "반찬가게", "정육점", "화방", "레코드숍", "인테리어 매장",
             "스포츠 매장", "문방구", "뷰티 매장", "캠핑용품점", "리빙숍"],
    "ITEM": ["우산", "텀블러", "이어폰", "머그컵", "향초", "수건", "양말", "목도리", "장갑", "모자",
             "운동화", "백팩", "지갑", "다이어리", "볼펜", "스티커", "액자", "화분", "쿠션", "담요",
             "무드등", "선글라스", "시계", "반지", "귀걸이", "목걸이", "립스틱", "향수", "핸드크림",
             "선크림", "보조배터리", "충전기", "키보드", "마우스", "스피커", "카메라", "필름", "앨범",
             "퍼즐", "보드게임", "레고", "인형", "슬리퍼", "잠옷", "앞치마", "도마", "냄비",
             "프라이팬", "밀폐용기", "수저 세트", "와인잔", "캔들홀더", "러그", "커튼", "행거",
             "거울", "빗", "파우치", "에코백", "키링"],
    "MEDIA": ["드라마", "영화", "예능", "다큐", "뮤지컬", "연극", "콘서트", "전시", "야구 경기",
              "축구 경기", "농구 경기", "애니메이션", "웹툰", "유튜브 영상", "공포 영화", "로맨스 영화",
              "스릴러", "좀비 영화", "시트콤", "오디션 프로그램", "연애 예능", "요리 프로그램",
              "여행 프로그램", "사극", "법정 드라마", "의학 드라마", "추리 드라마", "판타지 영화",
              "히어로 영화", "인디 영화", "단편 영화", "재개봉 영화", "무대 인사", "팬미팅",
              "페스티벌", "불꽃놀이", "서커스", "발레 공연", "오케스트라 공연", "재즈 공연"],
    "TRIP": ["속초", "양양", "춘천", "가평", "여수", "통영", "전주", "경주", "부산", "대구", "광주",
             "대전", "안동", "담양", "남해", "거제", "포항", "울산", "목포", "순천", "강화도",
             "제부도", "대부도", "을왕리", "파주", "양평", "단양", "제천", "공주", "부여", "보령",
             "태안", "삼척", "동해", "정선", "평창", "홍천", "인제", "군산", "익산"],
    "TROUBLE": ["야근", "감기", "두통", "허리 통증", "층간소음", "이사 준비", "월세 인상", "택배 분실",
                "지갑 분실", "액정 깨짐", "늦잠", "지각", "발표 실수", "보고서 마감", "회의 지연",
                "출장", "시험 준비", "다이어트", "불면증", "알바 스트레스", "팀장 잔소리", "동료 갈등",
                "집안일", "빨래", "청소", "장염", "치과 치료", "눈병", "비염", "몸살",
                "자전거 펑크", "버스 놓침", "지하철 고장", "폭우", "폭염", "한파", "미세먼지", "정전",
                "누수", "보일러 고장"],
    "WORK": ["신제품 기획", "보고서 작성", "발표 자료", "고객 미팅", "예산 정리", "신입 교육",
             "행사 준비", "설문 분석", "광고 시안", "계약서 검토", "데이터 정리", "회의록", "주간 보고",
             "채용 면접", "사내 교육", "제휴 제안", "앱 테스트", "출시 일정", "버그 수정",
             "서비스 개편", "사용자 인터뷰", "경쟁사 분석", "로고 교체", "홈페이지 개편", "뉴스레터",
             "브랜드 캠페인", "팝업 행사", "워크숍 준비", "분기 결산", "연말 평가", "팀 회식",
             "외부 강연", "협력사 관리", "재고 정리", "매출 분석", "가격 조정", "고객 응대",
             "문의 정리", "프로모션", "리뷰 관리"],
    "ACTIVITY": ["산책", "러닝", "요가", "등산", "자전거 타기", "볼링", "당구", "탁구", "배드민턴",
                 "테니스", "클라이밍", "스케이트", "줄넘기", "스트레칭", "홈트", "댄스", "노래방",
                 "방탈출", "보드게임 카페", "만화카페", "찜질방", "사우나", "캠핑", "피크닉", "낚시",
                 "전시 관람", "사진 찍기", "그림 그리기", "뜨개질", "베이킹", "요리", "꽃꽂이",
                 "캘리그라피", "독서", "글쓰기", "필사", "영어 공부", "일본어 공부", "코딩 공부",
                 "악기 연습", "기타 연습", "피아노 연습", "드럼 연습", "우쿨렐레", "봉사활동",
                 "플리마켓", "벼룩시장", "쇼핑", "대청소", "분리수거"],
    "WEATHER": ["비가 와서", "눈이 와서", "너무 더워서", "너무 추워서", "바람이 세서",
                "미세먼지 때문에", "태풍 때문에", "장마 때문에", "황사 때문에", "폭설 때문에",
                "소나기 때문에", "안개 때문에"],
    "JOB": ["디자이너", "개발자", "간호사", "교사", "약사", "회계사", "변호사", "기자", "작가",
            "번역가", "바리스타", "요리사", "제빵사", "사진작가", "영상 편집자", "마케터", "기획자",
            "영업사원", "공무원", "소방관", "경찰관", "은행원", "연구원", "대학원생", "유치원 교사",
            "트레이너", "필라테스 강사", "헤어 디자이너", "네일 아티스트", "플로리스트", "수의사",
            "치과의사", "물리치료사", "사회복지사", "상담사", "통역사", "승무원", "파일럿", "건축가",
            "목수"],
    "DISTRICT": ["대치동", "목동", "상도동", "흑석동", "봉천동", "신대방동", "대림동", "독산동",
                 "시흥동", "개봉동", "오류동", "화곡동", "등촌동", "가양동", "염창동", "합정동",
                 "서교동", "연희동", "홍제동", "불광동", "응암동", "수색동", "상암동", "공릉동",
                 "중계동", "상계동", "창동", "쌍문동", "미아동", "길음동", "정릉동", "돈암동",
                 "안암동", "제기동", "휘경동", "면목동", "중곡동", "구의동", "자양동", "광장동"],
    "RELATIVE": ["이모", "삼촌", "고모", "외삼촌", "사촌 언니", "사촌 동생", "큰아빠", "작은엄마",
                 "할머니", "할아버지", "외할머니", "조카"],
    "BODY": ["추위를 많이 탐", "더위를 많이 탐", "손발이 차가움", "잠이 많음", "멀미가 심함",
             "눈이 나쁨", "허리가 약함", "소화가 느림", "코가 예민함", "목이 자주 쉼",
             "피부가 예민함", "키가 큰 편", "체력이 약한 편", "밤눈이 어두움", "귀가 밝음",
             "발이 작음", "손이 큼", "곱슬머리임", "보조개가 있음", "잠귀가 밝음"],
    "DISLIKE": ["가지", "당근", "피망", "고수", "셀러리", "버섯", "굴", "번데기", "청국장",
                "민트초코", "건포도", "파인애플 피자", "시끄러운 식당", "긴 줄", "비 오는 날",
                "만원 버스", "새벽 알람", "단체 사진", "전화 통화", "매운 라면", "탄산음료",
                "비린 생선", "향 강한 향수", "모기", "거미", "뜨거운 국물", "날계란", "느끼한 음식",
                "장거리 운전", "공포 영화 예고편"],
    "REL": ["대학 동기", "회사 동료", "고등학교 친구", "중학교 친구", "동네 친구", "헬스장 친구",
            "전 직장 동료", "동아리 선배", "동아리 후배", "스터디 친구", "룸메이트였던 친구",
            "사촌"],
    "ANIMAL": ["강아지", "햄스터", "토끼", "앵무새", "거북이", "고슴도치", "금붕어", "페럿",
               "기니피그", "도마뱀"],
    "PETNAME": ["콩이", "몽이", "뭉치", "초롱이", "복실이", "해피", "까미", "별이", "달이", "구름이",
                "솜이", "밤이", "쿠키", "모카", "라떼", "우유", "짱구", "두리", "누리", "봄이",
                "여름이", "가을이", "겨울이", "망고", "레몬", "체리", "감자", "고구마", "옥수수",
                "떡이", "보송이", "뽀삐", "레오", "루루", "토리", "나나", "제리", "치즈", "호랑이",
                "몽실이"],
}


# ── 조사 (받침이 있으면 구어체 `-이`를 붙인다: 지안 → 지안이가) ──────────────
def _batchim(w):
    ch = w[-1]
    return "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 != 0


def nm(name):
    return name + ("이" if _batchim(name) else "")


def eun(w):
    return w + ("은" if _batchim(w) else "는")


# ── 문형 틀. 틀·술어는 **골격**이다(레짐 불변) — 레짐은 {슬롯} 값만 바꾼다 ─────
# 슬롯 이름 → 풀. `A`·`B`는 사람(B ≠ A), `P`는 지인.
EVENT_FRAMES = [
    ("{A}랑 {B}가 {PLACE}에서 {FOOD} 먹음", ("A", "B", "PLACE", "FOOD")),
    ("{A}가 {SHOP}에서 {ITEM} 샀음", ("A", "SHOP", "ITEM")),
    ("{A}랑 {B}가 {MEDIA} 같이 봄", ("A", "B", "MEDIA")),
    ("{A}가 {B}랑 {TRIP}에 다녀옴", ("A", "B", "TRIP")),
    ("{A}가 {TROUBLE} 때문에 속상해함", ("A", "TROUBLE")),
    ("{A}가 회사에서 {WORK} 맡음", ("A", "WORK")),
    ("{A}랑 {B}가 {PLACE}에서 {ACTIVITY} 함", ("A", "B", "PLACE", "ACTIVITY")),
    ("{A}가 {B}한테 {ITEM} 선물함", ("A", "B", "ITEM")),
    ("{A}가 {ACTIVITY} 처음 해 봄", ("A", "ACTIVITY")),
    ("{A}가 {WEATHER} {ACTIVITY} 못 함", ("A", "WEATHER", "ACTIVITY")),
    ("{A}랑 {B}가 {TROUBLE} 얘기로 오래 통화함", ("A", "B", "TROUBLE")),
    ("{A}가 {PLACE}에서 {B}를 우연히 만남", ("A", "PLACE", "B")),
]
# (술어, 틀, 슬롯, object를 만드는 슬롯, subject) — subject가 "P"면 지인 슬롯 값
FACT_FRAMES = [
    ("선호", "지우는 {FOOD} 좋아함", ("FOOD",), ("FOOD",), "지우"),
    ("가족", "지우 {RELATIVE_eun} {JOB}", ("RELATIVE", "JOB"), ("RELATIVE", "JOB"), "지우"),
    ("신체_특성", "지우는 {BODY}", ("BODY",), ("BODY",), "지우"),
    ("지인_반려동물", "{P}네 {ANIMAL} 이름은 {PETNAME}", ("P", "ANIMAL", "PETNAME"),
     ("PETNAME",), "P"),
    ("일상_사소", "지우가 {SHOP}에서 {ITEM} 샀다고 함", ("SHOP", "ITEM"), ("ITEM",), "지우"),
    ("싫어하는_것", "지우는 {DISLIKE} 싫어함", ("DISLIKE",), ("DISLIKE",), "지우"),
    ("자주_가는_곳", "지우는 {PLACE}에 자주 감", ("PLACE",), ("PLACE",), "지우"),
    ("소지품", "지우는 {ITEM} 늘 들고 다님", ("ITEM",), ("ITEM",), "지우"),
    ("지인_직업", "{P}는 {JOB}", ("P", "JOB"), ("JOB",), "P"),
    ("지인_거주지", "{P}는 {DISTRICT} 삶", ("P", "DISTRICT"), ("DISTRICT",), "P"),
    ("지인_관계", "{P}는 지우 {REL}", ("P", "REL"), ("REL",), "P"),
    ("지인_선호", "{P}는 {FOOD} 좋아함", ("P", "FOOD"), ("FOOD",), "P"),
    ("지인_직장", "{P} 회사는 {DISTRICT}에 있음", ("P", "DISTRICT"), ("DISTRICT",), "P"),
]


# ══════════════════════════════════════════════════════════════════════
# 핵심 항목 — 레짐 불변. 문항의 근거와 방해물이 전부 여기 있다.
# `role` : target(문항이 가리키는 지시체) · same(같은 지시체의 다른 항목) ·
#          distractor(같은 표면 문자열, **다른 지시체**)
# ══════════════════════════════════════════════════════════════════════

def _f(i, text, pred, obj, subj, s, t, imp, tests, role=None, inv=None, sup=None, note=None):
    d = {"id": i, "text": text, "predicate": pred, "object": obj, "subject": subj,
         "realm": "real", "at": {"session": sid(s), "turn": t}, "status": "valid",
         "importance": imp, "tests": tests}
    if inv:
        d["invalidated_at"] = {"session": sid(inv[0]), "turn": inv[1]}
        d["superseded_by"] = sup
        d["status"] = "invalidated"
    if role:
        d["lexical_role"] = role
    if note:
        d["note"] = note
    return d


def _e(i, text, s, t, w, tests, role=None, nrole=None):
    d = {"id": i, "text": text, "at": {"session": sid(s), "turn": t}, "emotional_weight": w}
    if nrole:
        d["narrative_role"] = nrole
    d["tests"] = tests
    if role:
        d["lexical_role"] = role
    return d


def sid(n):
    """세션 표기는 `gen_corpus.session_ids`와 같은 식이어야 한다 — 확인은 `check_positions`."""
    return f"S{n:02d}"


def core_facts():
    L, K, S, T = "lexical_distractor", "knowledge_update", "single_hop", "temporal"
    return [
        _f("F001", "지우의 고양이 이름은 나비", "반려동물_이름", "나비", "지우", 4, 12, 0.6, [S, L], "target"),
        _f("F002", "지우는 마케팅 회사 대리", "직업", "마케팅 회사 대리", "지우", 2, 5, 0.7, [K],
           inv=(121, 3), sup="F003"),
        _f("F003", "지우는 스타트업 PM으로 이직함", "직업", "스타트업 PM", "지우", 121, 4, 0.7, [K],
           "same", inv=(300, 6), sup="F004"),
        _f("F004", "지우는 스타트업 PM 팀장으로 승진함", "직업", "스타트업 PM 팀장", "지우", 300, 7, 0.75, [K]),
        _f("F005", "지우는 망원동 원룸에 삶", "거주지", "망원동 원룸", "지우", 3, 8, 0.6, [K],
           inv=(200, 9), sup="F006"),
        _f("F006", "지우는 성수동 투룸으로 이사함", "거주지", "성수동 투룸", "지우", 200, 10, 0.65, [K, L],
           "target"),
        _f("F007", "지우 여동생 이름은 하늘", "가족", "여동생 하늘", "지우", 6, 15, 0.6, [L], "target"),
        _f("F008", "지우 부모님 댁 강아지 이름은 두부", "가족", "부모님 댁 강아지 두부", "지우", 9, 20, 0.5,
           [L], "target"),
        _f("F009", "지우는 호두 알레르기가 있음", "알레르기", "호두", "지우", 12, 7, 0.85, [L], "target"),
        _f("F010", "지우 생일은 7월 28일", "생일", "7월 28일", "지우", 15, 22, 0.7, [L], "target"),
        _f("F011", "지우는 카페인에 민감해서 커피 못 마심", "신체_특성", "카페인 민감", "지우", 18, 11, 0.7,
           [L], "target"),
        # ── 표 밖 술어의 갱신 사슬 여섯 (밖E10) ─────────────────────────
        _f("F012", "지우 취미는 클라이밍", "취미", "클라이밍", "지우", 10, 14, 0.5, [K],
           inv=(228, 4), sup="F013"),
        _f("F013", "지우 취미가 도자기 공방으로 바뀜", "취미", "도자기 공방", "지우", 228, 5, 0.5, [K, T]),
        _f("F014", "지우 휴대폰은 갤럭시", "휴대폰_기종", "갤럭시", "지우", 20, 9, 0.3, [K],
           inv=(180, 16), sup="F015"),
        _f("F015", "지우가 휴대폰을 아이폰으로 바꿈", "휴대폰_기종", "아이폰", "지우", 180, 17, 0.3, [K]),
        _f("F016", "지우는 회사 앞 헬스장 다님", "다니는_헬스장", "회사 앞 헬스장", "지우", 25, 18, 0.3, [K],
           inv=(240, 12), sup="F017"),
        _f("F017", "지우가 헬스장 끊고 집 앞 필라테스로 옮김", "다니는_헬스장", "집 앞 필라테스", "지우",
           240, 13, 0.3, [K]),
        _f("F018", "지우는 지하철로 출퇴근함", "출퇴근_수단", "지하철", "지우", 30, 6, 0.3, [K],
           inv=(210, 20), sup="F019"),
        _f("F019", "지우가 자전거로 출퇴근하기 시작함", "출퇴근_수단", "자전거", "지우", 210, 21, 0.35, [K]),
        _f("F020", "지우 단골 미용실은 합정에 있음", "다니는_미용실", "합정 미용실", "지우", 35, 10, 0.2, [K],
           inv=(205, 2), sup="F021"),
        _f("F021", "지우가 연남동 미용실로 단골을 옮김", "다니는_미용실", "연남동 미용실", "지우", 205, 3, 0.2,
           [K]),
        _f("F022", "지우 노트북은 맥북 에어", "쓰는_노트북", "맥북 에어", "지우", 40, 25, 0.25, [K],
           inv=(125, 14), sup="F023"),
        _f("F023", "지우가 회사에서 새 노트북으로 그램을 받음", "쓰는_노트북", "그램", "지우", 125, 15, 0.25,
           [K]),
        # ── 그 밖의 단일 홉 표적 ──────────────────────────────────────
        _f("F024", "지우는 오이 싫어함", "싫어하는_것", "오이", "지우", 45, 3, 0.4, [S]),
        _f("F025", "지우는 매운 떡볶이 좋아함", "선호", "매운 떡볶이", "지우", 50, 8, 0.4, [S]),
        _f("F026", "지우 가방엔 항상 립밤이 있음", "소지품", "립밤", "지우", 55, 19, 0.2, [S]),
        _f("F027", "지우는 주말마다 서울숲 산책함", "자주_가는_곳", "서울숲", "지우", 60, 12, 0.35, [S]),
        _f("F028", "지우 여동생 하늘은 간호사", "가족", "여동생 하늘 간호사", "지우", 65, 7, 0.5, [S], "same"),
        _f("F029", "지우 아빠는 제주 출신", "가족", "아빠 제주 출신", "지우", 70, 21, 0.4, [S]),
        _f("F030", "지우는 왼손잡이", "신체_특성", "왼손잡이", "지우", 75, 4, 0.3, [S]),
        _f("F031", "지우가 편의점에서 마지막 크림빵을 놓쳐서 아쉬웠다고 함", "일상_사소", "크림빵", "지우",
           85, 16, 0.05, ["misinjection"], note="eval F007_TRAP과 같은 자리 — 낮아야 정상"),
        # ── 방해 항목 — 사실 ──────────────────────────────────────────
        _f("X001", "지우가 한강 공원에서 흰 나비를 봤다고 함", "일상_사소", "나비(곤충)", "지우", 95, 14, 0.1,
           [L], "distractor"),
        _f("X002", "민지네 고양이 이름도 나비", "지인_반려동물", "나비", "민지", 100, 9, 0.3, [L],
           "distractor", note="다른 사람의 고양이 — 이름까지 같다"),
        _f("X003", "지우가 결혼식 가려고 나비넥타이를 빌림", "일상_사소", "나비넥타이", "지우", 105, 22, 0.15,
           [L], "distractor"),
        _f("X004", "퇴근길에 본 하늘이 예뻐서 지우가 사진을 찍었다고 함", "일상_사소", "하늘(풍경)", "지우",
           110, 5, 0.05, [L], "distractor"),
        _f("X005", "서준 회사 후배 이름이 하늘", "지인_관계", "후배 하늘", "하늘(서준 후배)", 115, 18, 0.25,
           [L], "distractor"),
        _f("X007", "지우가 마트에서 두부 한 모를 샀음", "일상_사소", "두부(식품)", "지우", 135, 6, 0.05, [L],
           "distractor"),
        _f("X008", "지안네 강아지 이름도 두부", "지인_반려동물", "두부", "지안", 140, 23, 0.3, [L],
           "distractor"),
        _f("X010", "지우가 보리차를 끓여 마심", "일상_사소", "보리차", "지우", 150, 27, 0.05, [L],
           "distractor"),
        _f("X011", "민지네 햄스터 이름은 보리", "지인_반려동물", "보리", "민지", 155, 8, 0.3, [L],
           "distractor"),
        _f("X013", "지안네 햄스터 이름은 호두", "지인_반려동물", "호두", "지안", 165, 17, 0.3, [L],
           "distractor"),
        _f("X015", "서준이 호두나무 원목 책상을 삼", "일상_사소", "호두나무 책상", "서준", 175, 2, 0.15, [L],
           "distractor"),
        _f("X016", "지우 회사 동료 이름이 바다", "지인_관계", "동료 바다", "바다(지우 동료)", 185, 19, 0.25,
           [L], "distractor"),
        _f("X017", "지우가 휴대폰 배경화면을 바다 사진으로 바꿈", "일상_사소", "바다 사진", "지우", 190, 7,
           0.05, [L], "distractor"),
        _f("X023", "서준 선배가 스타트업으로 이직함", "지인_직업", "스타트업", "서준 선배", 245, 21, 0.15,
           [L], "distractor", note="eval X005와 같은 모양 — 같은 어휘, 다른 주어"),
        _f("X024", "지안은 이직을 두 번 한 디자이너", "지인_직업", "디자이너", "지안", 250, 5, 0.25, [L],
           "distractor"),
        _f("X025", "민지 생일은 7월 2일", "지인_생일", "7월 2일", "민지", 255, 16, 0.3, [L], "distractor"),
        _f("X026", "서준 생일은 11월 28일", "지인_생일", "11월 28일", "서준", 260, 22, 0.5, [L],
           "distractor"),
        _f("X027", "지안 생일은 7월 18일", "지인_생일", "7월 18일", "지안", 265, 10, 0.3, [L], "distractor"),
        _f("X028", "민지네 고양이 코코는 겁이 많음", "지인_반려동물", "코코", "민지", 270, 13, 0.3, [L],
           "distractor"),
        _f("X030", "지안이 고양이 카페를 차림", "지인_직업", "고양이 카페 사장", "지안", 280, 18, 0.25, [L],
           "distractor"),
        _f("X031", "민지는 하루에 커피를 세 잔 마심", "지인_선호", "커피", "민지", 285, 12, 0.2, [L],
           "distractor"),
        _f("X032", "서준이 커피 머신을 새로 삼", "일상_사소", "커피 머신", "서준", 290, 23, 0.15, [L],
           "distractor"),
        _f("X034", "민지는 성수동에 삶", "지인_거주지", "성수동", "민지", 305, 17, 0.3, [L], "distractor"),
        _f("X035", "서준 회사는 성수역 근처에 있음", "지인_직장", "성수역", "서준", 310, 4, 0.35, [L],
           "distractor"),
    ]


def core_events():
    L, M, T, S, K = "lexical_distractor", "multi_session", "temporal", "single_hop", "knowledge_update"
    return [
        _e("E001", "지우가 서준이랑 처음 바다 보러 강릉에 감", 90, 18, 0.9, [L, T], "target", "전환점"),
        _e("E002", "서준 강아지 보리가 수술받는 날 지우가 병원에 같이 감", 158, 22, 0.85, [L], "target", "전환점"),
        _e("E003", "지우가 약속을 까먹어서 서준한테 먼저 사과함", 262, 25, 0.8, [L], "target", "갈등"),
        _e("E004", "지우가 스타트업 첫 출근 — 이직 확정", 122, 5, 0.8, [L, T], "target", "전환점"),
        _e("E005", "나비가 갑자기 아파서 새벽에 동물병원에 감", 150, 3, 0.95, [M, T], "same", "갈등"),
        _e("E006", "첫 번째 운전면허 시험 — 탈락", 126, 9, 0.6, [M]),
        _e("E007", "두 번째 운전면허 시험도 탈락", 133, 10, 0.6, [M]),
        _e("E008", "세 번째 운전면허 시험 합격", 140, 11, 0.8, [M, S, T], nrole="해소"),
        _e("E009", "지우가 하프 마라톤을 처음 완주함", 250, 20, 0.8, [M, S, T], nrole="해소"),
        _e("E010", "지우가 10km 마라톤을 완주함", 180, 5, 0.6, [M, T]),
        _e("E011", "지우가 팀장 승진 발표를 들음", 299, 15, 0.85, [K], nrole="전환점"),
        _e("E012", "야근 문제로 서준이랑 크게 다툼", 335, 12, 0.9, [M, K], nrole="갈등"),
        _e("E013", "화해 — 서준이 먼저 연락함", 340, 3, 0.85, [K, T], nrole="해소"),
        _e("E014", "성수동으로 이사하는 날 서준이 짐을 옮겨 줌", 200, 12, 0.8, [K, T], "same", "전환점"),
        _e("E015", "여동생 하늘이 간호사 국가고시에 합격함", 64, 11, 0.7, [M], "same"),
        _e("E016", "부모님 댁에 가서 두부를 산책시킴", 230, 16, 0.4, [M], "same"),
        _e("E017", "나비 예방접종을 맞힘", 60, 22, 0.4, [S], "same"),
        _e("E018", "지우가 도자기 공방 첫 수업을 들음", 229, 8, 0.5, [S, T]),
        _e("E019", "서준이 퇴근길에 지우를 데리러 옴", 110, 25, 0.7, [S], nrole="전환점"),
        _e("E020", "아빠 고향 제주로 가족여행을 감", 272, 9, 0.75, [S]),
        # ── 방해 항목 — 사건 ──────────────────────────────────────────
        _e("X006", "민지랑 하늘공원에 억새 보러 감", 130, 20, 0.35, [L], "distractor"),
        _e("X009", "회사 앞 순두부찌개 집이 문을 닫음", 145, 11, 0.2, [L], "distractor"),
        _e("X012", "할머니 댁 앞 보리밭 사진을 가족 단톡방에서 봄", 160, 13, 0.2, [L], "distractor"),
        _e("X014", "호두과자를 사 들고 부모님 댁에 감", 170, 24, 0.3, [L], "distractor"),
        _e("X018", "민지가 바다 건너 오사카로 이사를 감", 195, 15, 0.4, [L], "distractor"),
        _e("X019", "부모님이 사과 한 박스를 보내 줌", 215, 11, 0.3, [L], "distractor"),
        _e("X020", "민지가 팀장한테 사과를 받았다고 함", 220, 26, 0.3, [L], "distractor"),
        _e("X021", "지우가 사과파이를 처음 구워 봄", 225, 9, 0.25, [L], "distractor"),
        _e("X022", "민지도 이직 준비를 시작했다고 함", 235, 14, 0.35, [L], "distractor"),
        _e("X029", "지우가 회사 앞 길고양이한테 밥을 줌", 275, 6, 0.2, [L], "distractor"),
        _e("X033", "지우가 카페에서 커피 대신 자몽주스를 시킴", 295, 8, 0.1, [L], "distractor"),
        _e("X036", "지우가 성수 팝업스토어 구경을 감", 315, 20, 0.2, [L], "distractor"),
    ]


def core_debts():
    def d(i, s, t, content, trigger, payoff, stake, tests, note=None):
        x = {"id": i, "setup": {"session": sid(s), "turn": t}, "content": content,
             "trigger": trigger, "expected_payoff": payoff, "emotional_stake": stake, "tests": tests}
        if note:
            x["note"] = note
        return x
    return [
        d("D001", 52, 20, "다음에 동해 가서 일출 보기로 약속", {"kind": "session_start", "after": sid(53)},
          {"session": sid(90)}, 0.6, ["payoff"]),
        d("D002", 128, 12, "면허 시험 결과 나오면 바로 말해주기로 함", {"kind": "time", "spec": "3d"},
          {"session": sid(140)}, 0.7, ["payoff", "proactive_recall"]),
        d("D003", 199, 25, "새 집 집들이 때 서준이 요리해 주기로 함",
          {"kind": "session_start", "after": sid(200)}, {"session": sid(205)}, 0.6, ["payoff"]),
        d("D004", 248, 8, "하프 마라톤 끝나면 같이 고기 먹기로 함",
          {"kind": "semantic", "spec": "마라톤 완주 얘기가 나오면"}, {"session": sid(251)}, 0.5, ["payoff"]),
        d("D005", 301, 18, "팀장 첫 달 끝나면 회고 같이 하기로 함", {"kind": "time", "spec": "30d"},
          {"session": sid(330)}, 0.5, ["payoff"]),
        d("D006_UNPAID", 80, 9, "서준이 자기 대학 시절 얘기 나중에 해주기로 함",
          {"kind": "semantic", "spec": "서준의 과거 얘기가 나오면"}, None, 0.6, ["payoff_negative"],
          note="의도적으로 회수 안 함 — eval D004_UNPAID와 같은 자리"),
    ]


# ══════════════════════════════════════════════════════════════════════
# 문항 — 레짐 불변. 캐릭터(서준)에게 자연스럽게 묻는 반말(eval과 같은 규약).
# ══════════════════════════════════════════════════════════════════════

def questions():
    q = []

    def add(i, typ, ask, gold, evidence=None, **kw):
        d = {"id": i, "type": typ, "ask": ask, "gold": gold}
        if evidence:
            d["evidence"] = evidence
        d.update(kw)
        q.append(d)

    L = "lexical_distractor"
    add("L01", L, "나비 얘기 나왔었잖아, 뭐였지?", "고양이 나비", ["F001"], distractor=["X001", "X002", "X003"])
    add("L02", L, "하늘이가 누구였더라", "여동생 하늘", ["F007"], distractor=["X004", "X005", "X006"])
    add("L03", L, "두부는 잘 지낸대?", "부모님 댁 강아지 두부", ["F008"], distractor=["X007", "X008", "X009"])
    add("L04", L, "보리 수술 잘 끝났었나?", "서준 강아지 보리 — 수술 날 같이 병원 감", ["E002"],
        distractor=["X010", "X011", "X012"])
    add("L05", L, "나 호두 먹어도 되던가?", "안 된다 — 호두 알레르기", ["F009"],
        distractor=["X013", "X014", "X015"])
    add("L06", L, "우리 바다 보러 갔던 거 기억나?", "강릉", ["E001"], distractor=["X016", "X017", "X018"])
    add("L07", L, "그때 내가 사과했던 거 기억나?", "약속 까먹어서 서준한테 먼저 사과함", ["E003"],
        distractor=["X019", "X020", "X021"])
    add("L08", L, "이직 얘기 누가 했더라", "지우 본인 (스타트업 첫 출근)", ["E004"],
        distractor=["X022", "X023", "X024"])
    add("L09", L, "내 생일 언제였지?", "7월 28일", ["F010"], distractor=["X025", "X026", "X027"])
    add("L10", L, "우리 고양이 이름 뭐였더라", "나비", ["F001"], distractor=["X002", "X028", "X029", "X030"])
    add("L11", L, "나 커피 마셔도 되나?", "안 된다 — 카페인 민감", ["F011"],
        distractor=["X031", "X032", "X033"])
    add("L12", L, "나 지금 어디 살지?", "성수동 투룸", ["F006"], distractor=["X034", "X035", "X036"],
        stale_answer="망원동 원룸")

    S = "single_hop"
    add("S01", S, "내 동생 무슨 일 한다 그랬지?", "간호사", ["F028"])
    add("S02", S, "나 싫어하는 채소 있었나?", "오이", ["F024"])
    add("S03", S, "내가 제일 좋아하는 음식 뭐게", "매운 떡볶이", ["F025"])
    add("S04", S, "나 가방에 늘 뭐 넣고 다니더라", "립밤", ["F026"])
    add("S05", S, "나 주말마다 어디 가지?", "서울숲 산책", ["F027"])
    add("S06", S, "우리 아빠 고향 어디라 그랬지", "제주", ["F029"])
    add("S07", S, "나 왼손잡이였나 오른손잡이였나", "왼손잡이", ["F030"])
    add("S08", S, "나 운전면허 결국 땄어?", "땄다 — 세 번째에 합격", ["E008"])
    add("S09", S, "나 하프 마라톤 뛰어 본 적 있나?", "있다 — 처음 완주", ["E009"])
    add("S10", S, "도자기 공방 처음 간 날 기억나?", "첫 수업", ["E018"])
    add("S11", S, "너 나 퇴근길에 데리러 온 적 있지?", "있다", ["E019"])
    add("S12", S, "제주도 가족여행 갔던 거 기억나?", "아빠 고향 제주 가족여행", ["E020"])

    K = "knowledge_update"
    add("K01", K, "나 지금 무슨 일 하지", "스타트업 PM 팀장", ["F004"], stale_answer="마케팅 회사 대리")
    add("K02", K, "나 아직 마케팅 회사 다니는 줄 알았지", "아니라고 정정", ["F004"])
    add("K03", K, "나 이사한 거 기억나?", "성수동 투룸 — 서준이 짐 옮겨 줌", ["F006", "E014"])
    add("K04", K, "내 취미 요즘 뭐지", "도자기 공방", ["F013"], stale_answer="클라이밍",
        note="표 밖 술어(취미) — 옛 값 F012가 색인에 살아 있다")
    add("K05", K, "나 휴대폰 뭐 쓰지", "아이폰", ["F015"], stale_answer="갤럭시")
    add("K06", K, "나 운동 어디서 하지", "집 앞 필라테스", ["F017"], stale_answer="회사 앞 헬스장")
    add("K07", K, "나 출근 뭐 타고 해?", "자전거", ["F019"], stale_answer="지하철")
    add("K08", K, "나 요즘 머리 어디서 잘라?", "연남동 미용실", ["F021"], stale_answer="합정 미용실")
    add("K09", K, "내 노트북 뭐였지", "그램", ["F023"], stale_answer="맥북 에어")
    add("K10", K, "너 나한테 화났었잖아 아직도 그래?", "화해했다는 인지", ["E012", "E013"])
    add("K11", K, "나 팀장 됐다고 말했었나", "했다 — 승진 발표", ["E011"])
    add("K12", K, "나 아직 망원동 살아?", "아니 — 성수동으로 이사", ["F006"], stale_answer="그렇다")

    M = "multi_session"
    add("M01", M, "나 운전면허 시험 몇 번 봤더라?", "3번", ["E006", "E007", "E008"])
    add("M02", M, "나 마라톤 몇 번 완주했지?", "2번 (10km · 하프)", ["E009", "E010"])
    add("M03", M, "나비 아팠던 적 있었지?", "새벽에 동물병원", ["E005"])
    add("M04", M, "우리 제일 크게 싸운 게 언제였지", "야근 문제로 다툼 (S335)", ["E012"])
    add("M05", M, "하늘이 시험 붙었었나?", "간호사 국가고시 합격", ["E015"])
    add("M06", M, "부모님 댁 가서 뭐 했었더라", "두부 산책", ["E016"])

    T = "temporal"
    add("T01", T, "나비 아팠던 게 이사 전이었나 후였나", "전", ["E005", "E014"])
    add("T02", T, "면허 딴 게 이직 전이었나 후였나", "후", ["E008", "E004"])
    add("T03", T, "우리 강릉 간 게 언제쯤이었지", "S90 무렵", ["E001"])
    add("T04", T, "하프 마라톤이 10km보다 먼저였나", "아니 — 10km가 먼저", ["E009", "E010"])
    add("T05", T, "도자기 공방 언제부터 다녔지", "S228~229 무렵", ["E018", "F013"])
    add("T06", T, "우리 화해한 게 최근이야?", "최근 (S340)", ["E013"])

    A = "abstention"
    add("A01", A, "우리 강아지 이름 기억나?", "우리 강아지는 없다 — 두부는 부모님 댁, 보리는 서준 강아지",
        fail_mode="두부나 보리를 우리 강아지로 답함")
    add("A02", A, "내 전공 뭐였는지 알아?", "모른다", fail_mode="전공을 지어냄")
    add("A03", A, "작년에 스키장 갔던 거 기억나?", "모른다", fail_mode="스키장 여행을 서술")
    add("A04", A, "우리 오빠 얘기 했었잖아, 기억나?", "여동생 하늘만 있다", fail_mode="오빠를 서술")
    add("A05", A, "나 수영 배운다고 했었나?", "들은 적 없다", fail_mode="수영을 서술")
    add("A06", A, "나 골프 친다고 했었지?", "들은 적 없다", fail_mode="골프를 서술")
    add("A07", A, "나 땅콩 알레르기 있다고 했지?", "땅콩이 아니라 호두", fail_mode="땅콩 알레르기에 동의")
    add("A08", A, "민지 남자친구 이름 뭐였지?", "모른다", fail_mode="이름을 지어냄")

    V = "coverage"
    for i, ask in (("V01", "우리 처음 만났을 때 뭐 먹었지"), ("V02", "초반에 우리 무슨 얘기 많이 했었지"),
                   ("V03", "작년 봄에 나 뭐 하고 지냈더라"), ("V04", "요즘 민지 얘기 자주 했나")):
        add(i, V, ask, "대략은 답하되 세부는 흐릿하게", evidence_ref="coverage_plan")
    return q


# ══════════════════════════════════════════════════════════════════════
# 골격 (레짐 불변) → 채움 (레짐마다)
# ══════════════════════════════════════════════════════════════════════

def pick(pool, s, u, exclude=None):
    """순위 r의 가중치 r^(-s)로 누적분포를 만들고 u를 넣는다. `exclude`는 뺀 뒤 재정규화.

    🔴 **슬롯 하나에 난수 하나.** B ≠ A를 «다시 뽑기»로 하면 레짐마다 뽑는 횟수가 달라져
    같은 u가 같은 슬롯에 가지 않는다 — 그래서 빼고 재정규화한다.
    """
    idx = [i for i, v in enumerate(pool) if v != exclude]
    w = [(i + 1) ** -s for i in idx]
    x, acc = u * sum(w), 0.0
    for i, wi in zip(idx, w):
        acc += wi
        if x < acc:
            return pool[i]
    return pool[idx[-1]]


def authored_positions(facts, events, debts):
    pos = []
    for f in facts:
        pos.append((f["id"], f["at"]["session"], f["at"]["turn"]))
        if "invalidated_at" in f:
            pos.append((f["id"] + "_INV", f["invalidated_at"]["session"], f["invalidated_at"]["turn"]))
    for e in events:
        pos.append((e["id"], e["at"]["session"], e["at"]["turn"]))
    for d in debts:
        pos.append((d["id"], d["setup"]["session"], d["setup"]["turn"]))
    return pos


def skeleton(facts, events, debts):
    """벌크 항목의 골격 — id · 종류 · 틀 · 자리 · 무게. **레짐을 모른다.**"""
    rng = random.Random(SEED_SKELETON)
    taken = {(s, t) for _, s, t in authored_positions(facts, events, debts)}
    free = [(s, t) for s in G.session_ids({"meta": {"sessions": SESSIONS}})
            for t in range(1, TURNS_PER_SESSION + 1) if (s, t) not in taken]
    n_f = N_FACTS_TOTAL - len(facts)
    n_e = N_EVENTS_TOTAL - len(events)
    order = {s: i for i, s in enumerate(G.session_ids({"meta": {"sessions": SESSIONS}}))}
    spots = sorted(rng.sample(free, n_f + n_e), key=lambda p: (order[p[0]], p[1]))
    kinds = ["fact"] * n_f + ["event"] * n_e
    rng.shuffle(kinds)
    out, cf, ce = [], 0, 0
    for (s, t), k in zip(spots, kinds):
        low = rng.random() < LOW_WEIGHT_SHARE
        w = rng.choice(LOW_WEIGHTS if low else HIGH_WEIGHTS)
        if k == "fact":
            cf += 1
            out.append({"id": f"B{cf:04d}", "kind": k, "frame": rng.randrange(len(FACT_FRAMES)),
                        "session": s, "turn": t, "weight": w})
        else:
            ce += 1
            out.append({"id": f"V{ce:04d}", "kind": k, "frame": rng.randrange(len(EVENT_FRAMES)),
                        "session": s, "turn": t, "weight": w})
    return out


def fill(sk, s):
    """골격 하나를 지수 s로 채운다. 난수는 항목 id로 시드한다 — 레짐마다 **같은 u**."""
    r = random.Random(f"eval3-fill:{SEED_FILL}:{sk['id']}")
    at = {"session": sk["session"], "turn": sk["turn"]}
    if sk["kind"] == "event":
        tpl, slots = EVENT_FRAMES[sk["frame"]]
        v = {}
        for sl in slots:
            u = r.random()
            if sl == "A":
                v["A"] = pick(PERSONS, s, u)
            elif sl == "B":
                v["B"] = pick(PERSONS, s, u, exclude=v["A"])
            else:
                v[sl] = pick(POOLS[sl], s, u)
        text = (tpl.replace("{A}", nm(v["A"])).replace("{B}", nm(v["B"]) if "B" in v else "")
                .format(**{k: x for k, x in v.items() if k not in ("A", "B")}))
        return {"id": sk["id"], "text": text, "at": at, "emotional_weight": sk["weight"],
                "tests": ["bulk"]}
    pred, tpl, slots, objs, subj = FACT_FRAMES[sk["frame"]]
    v = {}
    for sl in slots:
        u = r.random()
        v[sl] = pick(ACQ, s, u) if sl == "P" else pick(POOLS[sl], s, u)
    fmt = {k: x for k, x in v.items() if k != "P"}
    if "RELATIVE" in v:
        fmt["RELATIVE_eun"] = eun(v["RELATIVE"])
    text = tpl.replace("{P}", nm(v["P"]) if "P" in v else "").format(**fmt)
    return {"id": sk["id"], "text": text, "predicate": pred, "object": " ".join(v[o] for o in objs),
            "subject": v["P"] if subj == "P" else subj, "realm": "real", "at": at, "status": "valid",
            "importance": sk["weight"], "tests": ["bulk"]}


# ══════════════════════════════════════════════════════════════════════
# 조립 · 검사
# ══════════════════════════════════════════════════════════════════════

def _key(x):
    return (int(x["at"]["session"][1:]), x["at"]["turn"])


def ledger_meta(regime=None):
    meta = {
        "version": 1, "language": "ko", "chat_id": "eval3-chat-001", "sessions": SESSIONS,
        "span": "약 1년 — 하루 한 세션 (ADR-003의 «1년 후»)",
        "target_turns": SESSIONS * TURNS_PER_SESSION,
        "authorship": {
            "author": "Claude Opus 5 — 이 저장소의 executor 레인 하나",
            "author_count": 1,
            "method": ("규칙 기반 결정적 역방향 생성 (eval3/gen_corpus3.py · 골격 seed "
                       f"{SEED_SKELETON} · 슬롯 seed {SEED_FILL} · 노이즈 seed {SEED_NOISE}) — "
                       "노이즈·배치는 experiments/gen_corpus.py의 함수 객체를 그대로 부름"),
            "llm_used": False, "llm_checkpoint_compared": False, "llm_stops": 0,
            "note": ("핵심 항목·문항·슬롯 풀·풀의 순위를 한 저자가 썼다. df 분포는 이 생성기가 "
                     "정한다 — 그래서 레짐으로 선언했다(eval3/README.md §1). «실사용»이 아니다."),
        },
    }
    if regime is None:
        meta["layer"] = "core — 레짐 불변 항목만. 레짐별 전체 대장은 regimes/<레짐>/fact-ledger.yaml"
        meta["regimes"] = [{"dir": d, "label": lab, "zipf_s": s, "emulates": em}
                           for d, lab, s, em in REGIMES]
    else:
        d, lab, s, em = regime
        meta["layer"] = "full — core(eval3/fact-ledger.yaml) + 벌크(이 레짐의 지수로 채움)"
        meta["regime"] = {"dir": d, "label": lab, "zipf_s": s, "emulates": em}
    return meta


PERSONA = {
    "character": {"id": "seojun", "name": "강서준", "relation": "대학 선배",
                  "speech_rules": {"말투": "반말", "1인칭": "나"},
                  "note": "eval과 같은 두 사람 — `scoring.UBIQUITOUS`가 작동하게 둔다"},
    "user_persona": {"name": "지우", "job_initial": "마케팅 회사 대리"},
}


def assemble(regime, facts, events, debts, bulk):
    bf = [b for b in bulk if "predicate" in b]
    be = [b for b in bulk if "predicate" not in b]
    return {"meta": ledger_meta(regime), **PERSONA,
            "facts": sorted(facts + bf, key=_key), "events": sorted(events + be, key=_key),
            "debts": debts}


def keys_in(text, keys):
    return [k for k in keys if k in text]


def check_core(facts, events):
    """방해물 설계가 선언대로인가 — 역할 표지와 실제 키 포함이 어긋나면 죽는다."""
    items = facts + events
    per = {k: {"target": [], "same": [], "distractor": []} for k in CLUSTER_KEYS}
    for it in items:
        ks = keys_in(it["text"], CLUSTER_KEYS)
        role = it.get("lexical_role")
        if bool(ks) != bool(role):
            raise AssertionError(f"역할 표지와 군집 키가 어긋남: {it['id']} 키 {ks} · 역할 {role}")
        for k in ks:
            per[k][role].append(it["id"])
    for k, r in per.items():
        if len(r["target"]) != 1 or len(r["distractor"]) < MIN_DISTRACTORS_PER_CLUSTER:
            raise AssertionError(f"군집 «{k}» — 표적 {r['target']} · 방해 {r['distractor']}")
    n_d = sum(1 for it in items if it.get("lexical_role") == "distractor")
    if n_d != N_DISTRACTORS:
        raise AssertionError(f"방해 항목 {n_d} ≠ 사전 등록 {N_DISTRACTORS}")
    return per


def check_keys(bulk, core_texts, all_index_texts):
    for b in bulk:
        hit = keys_in(b["text"], CLUSTER_KEYS)
        if hit:
            raise AssertionError(f"벌크 행에 군집 키 {hit}: {b['id']} «{b['text']}» — 방해물 개수가 "
                                 "레짐의 함수가 된다")
        if b["text"] in core_texts:
            raise AssertionError(f"벌크 행이 핵심 항목과 같은 글: {b['id']}")
    for t in all_index_texts:
        hit = keys_in(t, ABSTENTION_KEYS)
        if hit:
            raise AssertionError(f"기권 화제 {hit}가 색인에 있다: «{t}» — 기권 정답이 거짓이 된다")


def check_positions(ledger, corpus):
    """모든 심은 항목이 **정확히 한 번, 자기 자리에** 있는가 (`gen_corpus.generate`는 안 본다)."""
    want = {i: (s, t) for i, s, t in authored_positions(ledger["facts"], ledger["events"],
                                                           ledger["debts"])}
    if len(set(want.values())) != len(want):
        raise AssertionError("심은 항목 둘이 같은 (세션, 턴)을 쓴다 — generate가 조용히 버린다")
    got = {}
    for r in corpus:
        if r["planted_id"]:
            if r["planted_id"] in got:
                raise AssertionError(f"{r['planted_id']}가 두 번 배치됐다")
            got[r["planted_id"]] = (r["session"], r["turn"])
    if got != want:
        miss = sorted(set(want) - set(got))[:5]
        moved = sorted(k for k in set(want) & set(got) if want[k] != got[k])[:5]
        raise AssertionError(f"배치 불일치 — 빠짐 {miss} · 밀림 {moved}")


def check_questions(qs, facts, events):
    ids = {x["id"] for x in facts + events}
    typ = {}
    for q in qs:
        typ[q["type"]] = typ.get(q["type"], 0) + 1
        for e in q.get("evidence", []):
            if e not in ids:
                raise AssertionError(f"{q['id']}의 근거 {e}가 핵심 대장에 없다")
    scored = sum(1 for q in qs if q.get("evidence"))
    if len(qs) != N_QUESTIONS or scored != N_SCORED or typ != QUESTION_TYPES:
        raise AssertionError(f"문항 {len(qs)}/{N_QUESTIONS} · 채점 {scored}/{N_SCORED} · 유형 {typ}")
    for q in qs:
        if q["type"] == "abstention" and q.get("evidence"):
            raise AssertionError(f"{q['id']} 기권 문항에 근거가 있다")


def check_predicates(ledgers):
    from memory import Memory
    preds = sorted({f["predicate"] for lg in ledgers for f in lg["facts"]})
    inn = [p for p in preds if p in Memory.PREDICATE_CARDINALITY]
    out = [p for p in preds if p not in Memory.PREDICATE_CARDINALITY]
    if len(inn) != PRED_IN or len(out) != PRED_OUT:
        raise AssertionError(f"술어 안 {len(inn)}/{PRED_IN} · 밖 {len(out)}/{PRED_OUT}")
    one = {p for p, c in Memory.PREDICATE_CARDINALITY.items() if c == "one"}
    for lg in ledgers:
        for f in lg["facts"]:
            if f["predicate"] in one and f["tests"] == ["bulk"]:
                raise AssertionError(f"벌크가 단일값 술어를 쓴다 — 우연한 무효화: {f['id']}")
    chains = [f for f in ledgers[0]["facts"]
              if "invalidated_at" in f and f["predicate"] not in Memory.PREDICATE_CARDINALITY]
    if len(chains) != N_OUT_TABLE_CHAINS:
        raise AssertionError(f"표 밖 갱신 사슬 {len(chains)} ≠ {N_OUT_TABLE_CHAINS}")
    return inn, out


def _yaml(obj, header):
    body = yaml.safe_dump(obj, allow_unicode=True, sort_keys=False, default_flow_style=None,
                          width=1000)
    return (header + body).encode("utf-8")


HEADER_CORE = """\
# 사실 대장 — **eval3 핵심 층** (레짐 불변)
#
# 🔴 이 파일은 레짐 셋이 **공유하는** 항목만 담는다 — 문항의 근거 · 어휘적 방해물 ·
#    갱신 사슬 · 부채. 색인 3,000행짜리 전체 대장은 레짐마다
#    `eval3/regimes/<레짐>/fact-ledger.yaml`이고, 그것은 이 파일 + 벌크(그 레짐의
#    지수로 채운 행)다. 무엇을 같게/다르게 뒀는지의 사전 등록은 `eval3/README.md` §1.
# 🔴 생성물이다 — 손으로 고치지 말 것. 정본은 `eval3/gen_corpus3.py`이고
#    `--check`가 디스크와 바이트를 대조한다.
# 스키마는 `eval/fact-ledger.yaml`과 같다(`facts`·`events`·`at.session`·`emotional_weight`).
# 더한 키(`subject`·`lexical_role`)는 `soak.ingest`가 읽지 않는다.

"""

HEADER_FULL = """\
# 사실 대장 — **eval3 · 레짐 {label}** (핵심 층 + 벌크)
#
# 🔴 생성물이다 — 손으로 고치지 말 것 (`eval3/gen_corpus3.py --check`).
# 이 레짐이 모사하는 것: {emulates}
# 핵심 층(`eval3/fact-ledger.yaml`)은 세 레짐에서 글자 그대로 같고, 벌크의 골격
# (id·술어·시점·무게·틀)도 같다. 다른 것은 벌크의 슬롯 값뿐이다.

"""

HEADER_Q = """\
# 평가 문항 — eval3 (세 레짐 공통)
# 🔴 생성물이다 — 정본은 `eval3/gen_corpus3.py`. 근거는 전부 핵심 층(레짐 불변)을 가리킨다.
# 스키마는 `eval/questions.yaml`의 `qa_questions`와 같다.

"""


def render_all():
    """모든 출력을 **바이트로** 만든다. 쓰지 않는다 — `main`과 시험이 같은 함수를 부른다."""
    facts, events, debts = core_facts(), core_events(), core_debts()
    check_core(facts, events)
    qs = questions()
    check_questions(qs, facts, events)
    sk = skeleton(facts, events, debts)
    core_texts = {x["text"] for x in facts + events}
    out, ledgers, corpora, noise_ref = {}, [], {}, None
    for reg in REGIMES:
        bulk = [fill(x, reg[2]) for x in sk]
        lg = assemble(reg, facts, events, debts, bulk)
        check_keys(bulk, core_texts, [x["text"] for x in lg["facts"] + lg["events"]])
        corpus = G.generate(lg, seed=SEED_NOISE)
        check_positions(lg, corpus)
        noise = [(r["seq"], r["role"], r["text"]) for r in corpus if not r["planted_id"]]
        if noise_ref is None:
            noise_ref = noise
        elif noise != noise_ref:
            raise AssertionError(f"레짐 {reg[0]}의 노이즈 턴이 다른 레짐과 다르다")
        ledgers.append(lg)
        corpora[reg[0]] = corpus
        out[f"regimes/{reg[0]}/fact-ledger.yaml"] = _yaml(
            lg, HEADER_FULL.format(label=reg[1], emulates=reg[3]))
        out[f"regimes/{reg[0]}/corpus/corpus.jsonl"] = "".join(
            json.dumps(t, ensure_ascii=False) + "\n" for t in corpus).encode("utf-8")
    # 골격이 레짐 사이에서 같은가 — 텍스트·object·subject 말고는 전부 같아야 한다
    def skel(lg):
        return [(x["id"], x["at"]["session"], x["at"]["turn"], x.get("predicate"),
                 x.get("importance"), x.get("emotional_weight"))
                for x in lg["facts"] + lg["events"]]
    if any(skel(lg) != skel(ledgers[0]) for lg in ledgers):
        raise AssertionError("벌크 골격이 레짐마다 다르다 — 레짐이 지수 하나만 바꾼다는 선언이 거짓")
    check_predicates(ledgers)
    counts = [(len(lg["facts"]), len(lg["events"])) for lg in ledgers]
    if any(c != (N_FACTS_TOTAL, N_EVENTS_TOTAL) for c in counts):
        raise AssertionError(f"대장 행 수 {counts} ≠ ({N_FACTS_TOTAL}, {N_EVENTS_TOTAL})")
    if N_FACTS_TOTAL + N_EVENTS_TOTAL - N_SUPERSEDED_IN_TABLE != N_ALIVE:
        raise AssertionError("사전 등록 상수끼리 안 맞는다")
    out["fact-ledger.yaml"] = _yaml({"meta": ledger_meta(), **PERSONA, "facts": facts,
                                     "events": events, "debts": debts}, HEADER_CORE)
    out["questions.yaml"] = _yaml({"meta": {"version": 1, "ledger": "fact-ledger.yaml (핵심 층)",
                                            "ask_at_session": sid(SESSIONS)},
                                   "qa_questions": qs}, HEADER_Q)
    return out, corpora


def digest(out):
    return {k: hashlib.sha256(v).hexdigest()[:16] for k, v in sorted(out.items())}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    out, corpora = render_all()
    if "--check" in argv:
        bad = [k for k, v in sorted(out.items())
               if not (HERE / k).exists() or (HERE / k).read_bytes() != v]
        for k, h in digest(out).items():
            print(f"  {'✗' if k in bad else '✓'} {h}  eval3/{k}")
        print(f"바이트 대조: 다름 {len(bad)} / {len(out)}")
        return 1 if bad else 0
    for k, v in out.items():
        p = HERE / k
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(v)
    print("생성 완료 — eval3/ (sha256 앞 16자)")
    for k, h in digest(out).items():
        print(f"  {h}  eval3/{k}")
    c = next(iter(corpora.values()))
    n = len(c)
    planted = sum(1 for t in c if t["planted_id"])
    hard = sum(1 for t in c if t["kind"].startswith("hard_neg"))
    print(f"  턴 {n} · 심은 항목 {planted} ({planted / n:.1%}) · 하드 네거티브 {hard} ({hard / n:.1%})"
          f" · 순수 노이즈 {n - planted - hard} — 세 레짐 같은 배치·같은 노이즈")
    print(f"  대장 사실 {N_FACTS_TOTAL} · 사건 {N_EVENTS_TOTAL} · 단일값 무효화 {N_SUPERSEDED_IN_TABLE}"
          f" → 살아 있는 색인 {N_ALIVE}(사전 등록) · 문항 {N_QUESTIONS}(채점 {N_SCORED})")
    print("🔴 자가저작: 저자 1명(Claude Opus 5) · LLM 미사용 · 결정적 생성 — 선언 정본은 각 대장의 "
          "meta.authorship")
    print("⚠️ 합성이다. df 분포는 이 생성기가 정한다 — 그래서 레짐으로 선언했다(README §1).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
