# 메타데이터 기반 추천 API (MVP) Vertex AI ver.

**현재 구현 플로우**

```
context (더미) + candidates (더미 20개)
    → 룰 랭커 (app/ranker.py)
    → top_k
    → LLM reason 생성
    → JSON 반환 (selected_menu_id, reason_one_liner, reason_tags)
```

**각 코드 역할·동작 순서:** [docs/코드_설명.md](docs/코드_설명.md)

## 요구 사항

- Python 3.10+(3.12 이하)
- (선택) `GOOGLE_APPLICATION_CREDENTIALS` — 없으면 모든 요청에 fallback 응답(selected=top_k[0], 템플릿 사유) 반환

## 설치

```bash
cd taste_mate
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 환경 변수 (선택)

| 변수 | 설명 | 예시 |
| :--- | :--- | :--- |
| `GOOGLE_APPLICATION_CREDENTIALS` | GCP 서비스 계정 키 JSON 절대 경로 | `C:/절대경로/key.json` |
| `GOOGLE_CLOUD_PROJECT` | Google Cloud 프로젝트 ID | `내-프로젝트-ID` |
| `GOOGLE_CLOUD_LOCATION` | Vertex AI 서비스 리전 | `us-central1` |
| `LLM_MODEL` | 사용할 모델명 (기본: `gemini-2.0-flash`) | `gemini-2.0-flash` |
| `LLM_TEMPERATURE` | 생성 온도 (낮을수록 일관된 답변 생성) | `0.3` |

`.env` 파일은 저장소에 포함되지 않습니다. 프로젝트 루트에 `.env`를 만들고 위 변수들을 넣으면 서버가 로드합니다. 예시는 `.env.example`을 참고하세요.

## 실행 방법

### 1. 서버 기동

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

코드 수정 후에는 서버를 재시작하거나 `--reload` 사용 시 자동 반영됩니다.

- API: `http://127.0.0.1:8000`
- 프론트: `http://127.0.0.1:8000/` → 케이스 선택 후 "추천 받기"
- `GET /health`, `POST /v1/recommend` (context + candidates → 랭커 → LLM → JSON)

### 2. 테스트 러너 실행

서버가 떠 있는 상태에서:

```bash
python scripts/run_eval.py
```

기본으로 `http://127.0.0.1:8000`을 호출합니다. 다른 URL은 `--base-url`로 지정:

```bash
python scripts/run_eval.py --base-url http://localhost:8000
```

결과는 다음에 저장됩니다.

- `output/eval_results.jsonl` — 호출별 전체 결과(검증 필드 포함)
- `output/eval_results.csv` — 요약 컬럼만 CSV

콘솔에는 케이스별 통과 여부와 마지막 요약(전체 통과 수, selected in top_k, 사유 길이, context 키워드 반영 수)이 출력됩니다.

### 3. 재현성 검증 (선택)

동일 케이스로 N회 호출해 selected_menu_id / reason_one_liner 일치율을 확인:

```bash
python scripts/run_reproducibility.py -n 5
```

- `-n 5`: 케이스당 5회 호출 (기본 5)
- `-c 1`: Case 1만 실행
- `--out output/reproducibility.json`: 결과 저장

재현성을 높이려면 `.env`에 `LLM_TEMPERATURE=0` 설정 후 서버 재시작.

## API 스펙

### `POST /v1/recommend`

- **Request:** `{ "context": { ... }, "candidates": [ ... ], "k": 5 }` (k 기본 5, 최대 20)
- **Response:** `{ "selected_menu_id": int, "reason_one_liner": str, "reason_tags": list[str], "top_k_used": list[int] }`

context 예시: `meal_slot`, `hunger_level`, `mood`, `company`, `effort_level`, `budget_range`, `recent_meals`, `weather`(선택).  
candidates: `menu_id`, `menu_name`, `category`, `tags`, `price_est`, `prep_time_est`.

## 프로젝트 구조

```
ai_plus/
├── app/
│   ├── main.py          # FastAPI 앱 (/v1/recommend, /health, 프론트·데이터용 GET)
│   ├── models.py        # Pydantic 요청/응답 모델
│   ├── llm.py           # LLM 호출 + 실패 시 fallback
│   ├── ranker.py        # 룰 기반 top-k 랭커 (context + candidates → top_k)
│   ├── logging_config.py # context 요약 + output 로그
│   └── __init__.py
├── data/
│   ├── candidates.json  # 메뉴 후보 20개
│   └── test_cases.json  # 테스트용 context 10개
├── prompts/
│   └── reason.txt       # LLM용 프롬프트 템플릿
├── frontend/
│   └── index.html       # 간이 프론트 (테스트 케이스 선택 → 추천 결과 확인)
├── scripts/
│   ├── run_eval.py      # 테스트 러너 (10케이스 호출 + 검증)
│   └── run_reproducibility.py # 동일 케이스 N회 호출 재현성 검증
├── output/              # run_eval / run_reproducibility 결과 (gitignore)
├── logs/                # reason_calls.jsonl (gitignore)
├── requirements.txt
├── .env.example         # 환경 변수 예시 (실제 키는 .env에, .env는 공유 금지)
└── README.md
```

## 테스트 러너 검증 항목

- `selected_menu_id`가 `top_k` 안에 있는지
- `reason_one_liner` 길이 25~45자
- `reason_one_liner`에 context 키워드(meal_slot, mood, company, effort_level 중) 2개 이상 포함 여부

## Fallback

LLM 호출 실패 또는 `GOOGLE_APPLICATION_CREDENTIALS` 미설정 시:

- `selected_menu_id`: `top_k[0]`
- `reason_one_liner`: `"선택한 메뉴가 현재 상황에 잘 맞습니다."`
- `reason_tags`: `["fallback"]`

## 로그

`POST /v1/recommend` 호출 시 `logs/reason_calls.jsonl`에 한 줄씩 추가 (context 요약, top_k, 결과).
