"""LLM client for recommendation reason generation with fallback."""
import json
import logging
import os
from pathlib import Path
from google import genai
from pydantic import ValidationError

from app.models import Candidate, Context, ReasonResponse

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "prompts" / "reason.txt"
FALLBACK_REASON = "선택한 메뉴가 현재 상황에 잘 맞습니다."

def _load_prompt_template() -> str:
    with open(PROMPT_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return f.read()

def _format_candidates(candidates: list[Candidate]) -> str:
    lines = []
    for c in candidates:
        lines.append(
            f"- menu_id={c.menu_id}, {c.menu_name} ({c.category}), "
            f"태그={c.tags}, 예상가격={c.price_est}원, 예상조리시간={c.prep_time_est}분"
        )
    return "\n".join(lines)

def _build_prompt(context: Context, candidates: list[Candidate]) -> str:
    template = _load_prompt_template()
    candidates_text = _format_candidates(candidates)
    context_data = context.model_dump() if hasattr(context, "model_dump") else context.dict()
    context_str = json.dumps(context_data, ensure_ascii=False)
    # JSON 출력을 명시적으로 요구하는 지시어 추가
    return (
        f"{template.format(candidates_text=candidates_text)}\n\n"
        f"## 현재 상황(JSON)\n{context_str}\n\n"
        f"결과는 반드시 JSON 형식으로만 응답하세요."
    )

def call_llm(context: Context, candidates: list[Candidate], top_k: list[int]) -> ReasonResponse:
    """Vertex AI Gemini를 호출하여 메뉴 선택 및 이유 생성."""
    prompt = _build_prompt(context, candidates)
    
    # 환경 변수 로드
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    model_name = os.getenv("LLM_MODEL", "gemini-2.0-flash")

    if not project_id:
        logger.warning("GOOGLE_CLOUD_PROJECT가 설정되지 않음. fallback 사용")
        return _fallback(top_k)

    try:
        # 1. 클라이언트 생성 (이 부분이 빠져있었습니다)
        client = genai.Client(
            vertexai=True,
            project=project_id,
            location=location
        )

        # 2. Gemini 호출
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config={
                "response_mime_type": "application/json", # JSON으로 달라고 강제함
                "temperature": 0.3
            }
        )

        # 3. response.text가 비어있는지 먼저 확인
        if not response.text:
            logger.error("Gemini가 빈 응답을 반환했습니다.")
            return _fallback(top_k)

        # 4. JSON 파싱 및 마크다운 제거
        clean_text = response.text.strip()
        if clean_text.startswith("```"):
            # 앞뒤 마크다운 태그 (```json ... ```) 제거
            clean_text = clean_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        
        data = json.loads(clean_text)

        # 5. 데이터 추출 및 반환
        result = ReasonResponse(
            selected_menu_id=int(data.get("selected_menu_id", top_k[0])),
            reason_one_liner=data.get("reason_one_liner", FALLBACK_REASON),
            reason_tags=list(data.get("reason_tags", ["추천"])),
        )
        
        logger.info("Gemini 성공: selected_menu_id=%s", result.selected_menu_id)
        return result

    except Exception as e:
        # 에러 발생 시 response 객체가 존재할 때만 text를 찍도록 안전하게 처리
        res_text = response.text if 'response' in locals() else "No Response"
        logger.error(f"파싱 에러 발생! 원본 데이터: {res_text}")
        logger.exception("Gemini 호출 또는 파싱 실패: %s", e)
        return _fallback(top_k)

def _fallback(top_k: list[int]) -> ReasonResponse:
    selected = top_k[0] if top_k else 0
    return ReasonResponse(
        selected_menu_id=selected,
        reason_one_liner=FALLBACK_REASON,
        reason_tags=["fallback"],
    )