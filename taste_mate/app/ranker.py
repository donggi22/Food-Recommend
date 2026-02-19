"""
룰 기반 Top-K 랭커.
context + 후보 메뉴 전체 → 휴리스틱 점수 합산 → 상위 K개 menu_id 반환.
데이터 없이 메타데이터만으로 동작.

용도: 지도 앱에서 가까운 식당을 불러온 뒤, 그 식당(메뉴) 중 추천. 주문/외식 위주라
실제 조리시간(prep_time)보다 거리·배달·분위기 등이 중요. prep_time은 거의 반영하지 않고,
effort_level은 "간단히 → 간편/빠른 메뉴", "제대로 → 분위기/데이트" 같은 태그 매칭으로만 사용.
"""
import re
from typing import List, Tuple

from app.models import Candidate, Context


# 점수 가중치 (나중에 튜닝 가능)
WEIGHT_MEAL_SLOT = 2.0
WEIGHT_WEATHER = 2.0
WEIGHT_EFFORT = 1.0   # 주문/외식 위주라 조리시간 대신 태그만 사용
WEIGHT_BUDGET = 1.5
WEIGHT_RECENT_PENALTY = -1.0
WEIGHT_MOOD = 0.5

# 시간대별 선호 태그
MEAL_SLOT_TAGS = {
    "아침": ["아침", "간편", "가벼운", "빠른"],
    "점심": ["간편", "든든한", "한그릇"],
    "저녁": ["든든한", "제대로", "면요리", "고기"],
    "야식": ["야식", "간편", "빠른"],
}

# 추울 때 선호 태그
COLD_TAGS = ["따뜻한", "국물", "구수한", "밥친구"]

# 더울 때 선호 태그
HOT_TAGS = ["가벼운", "담백", "건강", "다이어트", "야채"]

# 기분별 선호 태그 (보조)
MOOD_TAGS = {
    "스트레스": ["간편", "든든한", "매운맛"],
    "피곤": ["간편", "빠른", "가벼운"],
    "무기력": ["간편", "빠른"],
    "좋음": ["제대로", "분위기", "데이트"],
}


def _parse_budget_range(budget_range: str) -> Tuple[float, float]:
    """'5000~8000' 형태에서 (min, max) 추출. 파싱 실패 시 (0, 999999)."""
    if not budget_range or not isinstance(budget_range, str):
        return 0.0, 999999.0
    m = re.search(r"(\d+)\s*~\s*(\d+)", budget_range.replace(",", ""))
    if m:
        return float(m.group(1)), float(m.group(2))
    return 0.0, 999999.0


def _score_meal_slot(context: Context, c: Candidate) -> float:
    """시간대와 태그 매칭."""
    preferred = MEAL_SLOT_TAGS.get(context.meal_slot, [])
    if not preferred:
        return 0.0
    match = sum(1 for t in preferred if t in c.tags)
    return (match / len(preferred)) * WEIGHT_MEAL_SLOT if preferred else 0.0


def _score_weather(context: Context, c: Candidate) -> float:
    """날씨(추움/더움)와 태그 매칭."""
    if not context.weather:
        return 0.0
    cond = (context.weather.condition or "").lower()
    temp = context.weather.temp_c
    score = 0.0
    if temp < 10 or cond in ("rain", "snow"):
        match = sum(1 for t in COLD_TAGS if t in c.tags)
        score += (match / len(COLD_TAGS)) * WEIGHT_WEATHER if COLD_TAGS else 0.0
    if temp > 26:
        match = sum(1 for t in HOT_TAGS if t in c.tags)
        score += (match / len(HOT_TAGS)) * WEIGHT_WEATHER if HOT_TAGS else 0.0
    return score


# 주문/외식 추천용: effort는 "조리시간"이 아니라 "메뉴 성격(간편 vs 제대로)" 태그로만 매칭.
# 거리/배달시간은 후보에 route 정보가 생기면 그때 반영 예정.
EFFORT_TAGS = {
    "간단히": ["간편", "빠른", "한그릇", "배달"],
    "보통": ["간편", "든든한", "한그릇"],
    "제대로": ["제대로", "분위기", "데이트", "회식"],
}


def _score_effort(context: Context, c: Candidate) -> float:
    """노력 수준과 메뉴 태그 매칭. (주문/외식 위주라 prep_time은 사용하지 않음)"""
    preferred = EFFORT_TAGS.get(context.effort_level, [])
    if not preferred:
        return 0.0
    match = sum(1 for t in preferred if t in c.tags)
    return (match / len(preferred)) * WEIGHT_EFFORT if preferred else 0.0


def _score_budget(context: Context, c: Candidate) -> float:
    """예산 범위 안이면 만점, 밖이면 거리만큼 감점."""
    low, high = _parse_budget_range(context.budget_range)
    p = c.price_est
    if low <= p <= high:
        return WEIGHT_BUDGET
    if p < low:
        return WEIGHT_BUDGET * 0.8  # 예산 미만이면 약간만 감점
    # 초과 시 초과량에 비례 감점
    over = p - high
    return max(0.0, WEIGHT_BUDGET - over / 5000.0)


def _score_recent_penalty(context: Context, c: Candidate) -> float:
    """최근 먹은 카테고리와 같으면 다양성 위해 감점."""
    if not context.recent_meals:
        return 0.0
    recent_cats = {r.category for r in context.recent_meals}
    if c.category in recent_cats:
        return WEIGHT_RECENT_PENALTY
    return 0.0


def _score_mood(context: Context, c: Candidate) -> float:
    """기분과 태그 보조 매칭."""
    preferred = MOOD_TAGS.get(context.mood, [])
    if not preferred:
        return 0.0
    match = sum(1 for t in preferred if t in c.tags)
    return (match / len(preferred)) * WEIGHT_MOOD if preferred else 0.0


def score_candidate(context: Context, candidate: Candidate) -> float:
    """한 후보에 대한 총점 (높을수록 추천에 유리)."""
    return (
        _score_meal_slot(context, candidate)
        + _score_weather(context, candidate)
        + _score_effort(context, candidate)
        + _score_budget(context, candidate)
        + _score_recent_penalty(context, candidate)
        + _score_mood(context, candidate)
    )


def rule_based_top_k(
    context: Context,
    candidates: List[Candidate],
    k: int = 5,
) -> List[int]:
    """
    context + 후보 전체를 받아 휴리스틱 점수로 정렬한 뒤 상위 K개 menu_id 반환.
    """
    if not candidates:
        return []
    k = min(k, len(candidates))
    scored = [(c, score_candidate(context, c)) for c in candidates]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [c.menu_id for c, _ in scored[:k]]
