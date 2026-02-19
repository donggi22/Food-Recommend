"""FastAPI app: context + candidates → 룰 랭커 → LLM → JSON."""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.models import Candidate, RecommendRequest, ReasonResponse, TopKResponse
from app.llm import call_llm
from app.logging_config import setup_logging, log_reason_call
from app.ranker import rule_based_top_k

setup_logging()
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent

# 수정 전 (OpenAI)
# _api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
# if _api_key:
#     logger.info("OPENAI_API_KEY 로드됨 (끝 4자리: ...%s)", _api_key[-4:] if len(_api_key) >= 4 else "****")
# else:
#     logger.warning("OPENAI_API_KEY 없음 → fallback 응답 사용.")

# 수정 후 (Vertex AI/GCP 기준)
_gcp_project = (os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
if _gcp_project:
    logger.info("Vertex AI 활성화됨 (프로젝트 ID: %s)", _gcp_project)
else:
    logger.error("GOOGLE_CLOUD_PROJECT 설정 없음! Vertex AI 기능을 사용할 수 없습니다.")

app = FastAPI(title="Recommendation API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _map_top_k_to_candidates(top_k: list[int], candidates: list[Candidate]) -> list[Candidate]:
    id_to_candidate = {c.menu_id: c for c in candidates}
    return [id_to_candidate[mid] for mid in top_k if mid in id_to_candidate]


@app.post("/v1/top-k", response_model=TopKResponse)
def top_k(req: RecommendRequest) -> TopKResponse:
    """룰 랭커만: context + candidates → 상위 K개 menu_id. LLM 호출 없음."""
    ids = rule_based_top_k(req.context, req.candidates, k=req.k)
    return TopKResponse(top_k=ids)


@app.post("/v1/recommend", response_model=ReasonResponse)
def recommend(req: RecommendRequest) -> ReasonResponse:
    """context + candidates → 룰 랭커(top_k) → LLM(1개 선택 + 사유) → JSON."""
    top_k_ids = rule_based_top_k(req.context, req.candidates, k=req.k)
    if not top_k_ids:
        raise HTTPException(status_code=400, detail="No candidates to rank")
    selected_candidates = _map_top_k_to_candidates(top_k_ids, req.candidates)
    response = call_llm(req.context, selected_candidates, top_k_ids)
    log_reason_call(req.context, top_k_ids, response)
    return ReasonResponse(
        selected_menu_id=response.selected_menu_id,
        reason_one_liner=response.reason_one_liner,
        reason_tags=response.reason_tags,
        top_k_used=top_k_ids,
    )


@app.get("/health")
def health():
    return {"status": "ok"}


def _read_json(path: Path):
    import json
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/v1/test-cases")
def get_test_cases():
    path = ROOT / "data" / "test_cases.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="test_cases.json not found")
    return _read_json(path)


@app.get("/v1/candidates")
def get_candidates():
    path = ROOT / "data" / "candidates.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="candidates.json not found")
    return _read_json(path)


def _load_index_html():
    """기동 시 index.html 내용을 읽어서 캐시 (경로 이슈 회피)."""
    for base in (ROOT, Path.cwd()):
        p = base / "frontend" / "index.html"
        if p.exists():
            try:
                return p.read_text(encoding="utf-8")
            except Exception:
                pass
    return None


_INDEX_HTML = _load_index_html()
frontend_dir = ROOT / "frontend"


def _serve_index():
    if _INDEX_HTML is not None:
        return HTMLResponse(_INDEX_HTML)
    raise HTTPException(
        status_code=404,
        detail="Frontend not found. Run from project root: cd ai_plus && uvicorn app.main:app --port 8000",
    )


@app.get("/")
def serve_index():
    return _serve_index()


@app.get("/index.html")
def serve_index_html():
    return _serve_index()


# 그 외 정적 자원(있을 경우)
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="frontend_static")
