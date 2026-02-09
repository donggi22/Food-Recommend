# Food Recommend MVP

간단한 **감정 기반 음식 추천 MVP**입니다.  
Flask + SQLite로 구성된 로컬 실행용 프로젝트입니다.

## 프로젝트 받기
```bash
# 원하는 폴더로 이동 (예: Desktop)
cd ~/Desktop

# 프로젝트 클론 (다운로드)
git clone https://github.com/donggi22/Food-Recommend-taste-mate
```

## 실행 방법

```bash
cd food_recommend

# 가상환경 생성 (처음 한 번만)
python -m venv .venv

# 가상환경 활성화
source .venv/bin/activate # Mac/Linux
.venv\Scripts\activate # Windows

# 프로젝트 의존성 설치
pip install -r requirements.txt

# flask 서버 실행
python app.py
```

브라우저에서 아래 주소로 접속합니다.
\
http://127.0.0.1:5000/

프로젝트 구조
```pgsql
foodrec_mvp/
├─ app.py
├─ requirements.txt
└─ templates/
   ├─ step1.html
   ├─ step2.html
   └─ results.html
```

- `app.py`
\
Flask 서버, 추천 로직, DB 초기화 및 이벤트 로그 처리

- `requirements.txt`
\
프로젝트 의존성 목록

- `templates/`
\
화면 렌더링용 HTML 템플릿

개요
- 사용자가 식사 무드/감정을 선택하면 음식 3개를 추천

- 추천 노출 및 선택 로그를 SQLite에 저장

- MVP 검증 및 추천 흐름 테스트 목적

