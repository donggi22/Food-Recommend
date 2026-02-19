#!/usr/bin/env python3
"""
테스트 러너: test_cases 10개로 POST /v1/recommend 호출 후 검증·저장.
"""
import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Union

import httpx

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"

CONTEXT_KEYS = ("meal_slot", "mood", "company", "effort_level")
MIN_REASON_LEN = 25
MAX_REASON_LEN = 45


def load_json(path: Path) -> Union[list, dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_one(client: httpx.Client, base_url: str, case_id: int, context: dict, candidates: list) -> dict:
    resp = client.post(
        f"{base_url}/v1/recommend",
        json={"context": context, "candidates": candidates, "k": 5},
        timeout=30.0,
    )
    resp.raise_for_status()
    result = resp.json()
    result["_case_id"] = case_id
    result["_context"] = context
    result["_top_k"] = result.get("top_k_used") or []
    return result


def check_selected_in_top_k(top_k: list, selected_menu_id: int) -> bool:
    return top_k and selected_menu_id in top_k


def check_reason_length(reason: str) -> tuple[bool, int]:
    n = len(reason)
    return MIN_REASON_LEN <= n <= MAX_REASON_LEN, n


# 날씨 condition → 한글 (사유에 이렇게 나올 수 있음)
WEATHER_KO = {"clear": "맑", "rain": "비", "snow": "눈", "cloudy": "흐림"}


def check_context_keywords(context: dict, reason: str) -> tuple[bool, list[str]]:
    found = []
    for key in CONTEXT_KEYS:
        val = context.get(key)
        if val and str(val) in reason:
            found.append(key)
    # 날씨: condition/한글 또는 추운/더운/따뜻 등 체감 표현이 사유에 포함되면 인정
    weather = context.get("weather")
    if weather and isinstance(weather, dict):
        cond = (weather.get("condition") or "").lower()
        temp = weather.get("temp_c")
        if cond in reason or (WEATHER_KO.get(cond) and WEATHER_KO[cond] in reason) or "날씨" in reason:
            found.append("weather")
        elif temp is not None:
            if temp < 10 and ("추운" in reason or "춥" in reason or "쌀쌀" in reason or "한파" in reason):
                found.append("weather")
            elif temp > 26 and ("더운" in reason or "더움" in reason or "더워" in reason or "무더" in reason):
                found.append("weather")
            elif 15 <= temp <= 25 and ("따뜻" in reason or "선선" in reason or "시원" in reason):
                found.append("weather")
    return len(found) >= 2, found


def main():
    parser = argparse.ArgumentParser(description="Run evaluation: POST /v1/recommend with test_cases")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument("--out-jsonl", default=None, help="Output JSONL path (default: output/eval_results.jsonl)")
    parser.add_argument("--out-csv", default=None, help="Output CSV path (default: output/eval_results.csv)")
    args = parser.parse_args()

    candidates_path = DATA_DIR / "candidates.json"
    test_cases_path = DATA_DIR / "test_cases.json"
    if not candidates_path.exists() or not test_cases_path.exists():
        print("data/candidates.json 또는 data/test_cases.json 이 없습니다.", file=sys.stderr)
        sys.exit(1)

    candidates = load_json(candidates_path)
    test_cases = load_json(test_cases_path)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_jsonl = args.out_jsonl or (OUTPUT_DIR / "eval_results.jsonl")
    out_csv = args.out_csv or (OUTPUT_DIR / "eval_results.csv")

    results = []
    summary_ok = 0
    summary_fail = 0
    checks = {"selected_in_top_k": 0, "reason_length_ok": 0, "context_keywords_ok": 0}

    with httpx.Client() as client:
        for i, tc in enumerate(test_cases):
            case_id = i + 1
            context = tc["context"]
            try:
                row = run_one(client, args.base_url, case_id, context, candidates)
            except Exception as e:
                print(f"Case {case_id}: API 오류 - {e}")
                summary_fail += 1
                continue

            top_k = row.get("_top_k") or []
            in_top_k = check_selected_in_top_k(top_k, row["selected_menu_id"])
            len_ok, reason_len = check_reason_length(row["reason_one_liner"])
            kw_ok, keywords_found = check_context_keywords(context, row["reason_one_liner"])

            if in_top_k:
                checks["selected_in_top_k"] += 1
            if len_ok:
                checks["reason_length_ok"] += 1
            if kw_ok:
                checks["context_keywords_ok"] += 1

            row["_check_selected_in_top_k"] = in_top_k
            row["_check_reason_length_ok"] = len_ok
            row["_reason_len"] = reason_len
            row["_check_context_keywords_ok"] = kw_ok
            row["_context_keywords_found"] = keywords_found
            all_ok = in_top_k and len_ok and kw_ok
            if all_ok:
                summary_ok += 1
            else:
                summary_fail += 1

            results.append(row)
            print(
                f"Case {case_id}: selected={row['selected_menu_id']} in_top_k={in_top_k} "
                f"len={reason_len}({'OK' if len_ok else 'FAIL'}) keywords={keywords_found}({'OK' if kw_ok else 'FAIL'})"
            )

    # JSONL 저장 (검증용 필드 제외한 출력만 저장할 수도 있음; 여기서는 전부 저장)
    with open(out_jsonl, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n저장: {out_jsonl}")

    # CSV 저장 (요약 컬럼)
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "case_id",
                "selected_menu_id",
                "reason_one_liner",
                "reason_tags",
                "reason_len",
                "selected_in_top_k",
                "reason_length_ok",
                "context_keywords_ok",
                "context_keywords_found",
            ]
        )
        for r in results:
            w.writerow(
                [
                    r["_case_id"],
                    r["selected_menu_id"],
                    r["reason_one_liner"],
                    "|".join(r["reason_tags"]),
                    r["_reason_len"],
                    r["_check_selected_in_top_k"],
                    r["_check_reason_length_ok"],
                    r["_check_context_keywords_ok"],
                    "|".join(r["_context_keywords_found"]),
                ]
            )
    print(f"저장: {out_csv}")

    # 콘솔 요약
    n = len(results)
    print("\n========== 요약 ==========")
    print(f"총 케이스: {len(test_cases)}, 성공 호출: {n}")
    print(f"전체 통과(3항목 모두 OK): {summary_ok} / {n}")
    print(f"selected_menu_id in top_k: {checks['selected_in_top_k']} / {n}")
    print(f"reason_one_liner 길이 25~45자: {checks['reason_length_ok']} / {n}")
    print(f"context 키워드 2개 이상 반영: {checks['context_keywords_ok']} / {n}")


if __name__ == "__main__":
    main()
