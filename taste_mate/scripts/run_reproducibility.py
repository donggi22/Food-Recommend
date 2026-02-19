#!/usr/bin/env python3
"""
재현성 검증: 동일 테스트 케이스로 N회 호출 후, selected_menu_id / reason_one_liner 일치율 확인.
- 같은 입력으로 여러 번 호출했을 때 LLM이 같은 선택·같은 사유를 내는지 확인.
- 서버에서 temperature=0 에 가깝게 두면 재현성이 높아짐 (app/llm.py 의 temperature 참고).
"""
import argparse
import json
import sys
from pathlib import Path
from collections import Counter

import httpx

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_one(client: httpx.Client, base_url: str, context: dict, candidates: list) -> dict:
    resp = client.post(
        f"{base_url}/v1/recommend",
        json={"context": context, "candidates": candidates, "k": 5},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser(description="재현성 검증: 동일 케이스 N회 호출 후 일치율 출력")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument("--repeat", "-n", type=int, default=5, help="케이스당 호출 횟수 (기본 5)")
    parser.add_argument("--case", "-c", type=int, default=None, help="특정 케이스만 (1~10). 없으면 전체")
    parser.add_argument("--out", default=None, help="결과 저장 JSON 경로 (선택)")
    args = parser.parse_args()

    candidates_path = DATA_DIR / "candidates.json"
    test_cases_path = DATA_DIR / "test_cases.json"
    if not candidates_path.exists() or not test_cases_path.exists():
        print("data/candidates.json 또는 data/test_cases.json 이 없습니다.", file=sys.stderr)
        sys.exit(1)

    candidates = load_json(candidates_path)
    test_cases = load_json(test_cases_path)

    if args.case is not None:
        idx = args.case - 1
        if idx < 0 or idx >= len(test_cases):
            print(f"--case는 1~{len(test_cases)} 사이여야 합니다.", file=sys.stderr)
            sys.exit(1)
        test_cases = [test_cases[idx]]
        case_indices = [args.case]
    else:
        case_indices = list(range(1, len(test_cases) + 1))

    n = args.repeat
    all_results = []

    with httpx.Client() as client:
        for case_idx, tc in zip(case_indices, test_cases):
            context = tc["context"]
            responses = []
            for _ in range(n):
                try:
                    r = run_one(client, args.base_url, context, candidates)
                    responses.append(r)
                except Exception as e:
                    print(f"Case {case_idx} 호출 실패: {e}", file=sys.stderr)
                    responses.append({"selected_menu_id": None, "reason_one_liner": None, "reason_tags": []})

            selected_ids = [r["selected_menu_id"] for r in responses if r.get("selected_menu_id") is not None]
            reasons = [r.get("reason_one_liner") or "" for r in responses]

            selected_counter = Counter(selected_ids)
            reason_counter = Counter(reasons)
            most_common_selected = selected_counter.most_common(1)
            most_common_reason = reason_counter.most_common(1)

            same_selected_count = most_common_selected[0][1] if most_common_selected else 0
            same_reason_count = most_common_reason[0][1] if most_common_reason else 0
            selected_mode = most_common_selected[0][0] if most_common_selected else None
            reason_mode = most_common_reason[0][0] if most_common_reason else ""

            summary = {
                "case_id": case_idx,
                "repeat": n,
                "same_selected_count": same_selected_count,
                "same_reason_count": same_reason_count,
                "selected_mode": selected_mode,
                "reason_mode": reason_mode,
                "selected_distribution": dict(selected_counter),
            }
            all_results.append(summary)

            print(f"Case {case_idx}: 호출 {n}회")
            print(f"  selected_menu_id 동일: {same_selected_count}/{n} (최빈값: {selected_mode})")
            print(f"  reason_one_liner 동일: {same_reason_count}/{n}")
            if len(selected_counter) > 1:
                print(f"  selected 분포: {dict(selected_counter)}")
            print()

    if args.out:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = Path(args.out)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"repeats": n, "results": all_results}, f, ensure_ascii=False, indent=2)
        print(f"저장: {out_path}")

    # 전체 요약
    total = len(all_results)
    perfect_selected = sum(1 for r in all_results if r["same_selected_count"] == n)
    perfect_reason = sum(1 for r in all_results if r["same_reason_count"] == n)
    print("========== 재현성 요약 ==========")
    print(f"케이스 수: {total}, 케이스당 호출: {n}")
    print(f"selected_menu_id 전회 동일한 케이스: {perfect_selected}/{total}")
    print(f"reason_one_liner 전회 동일한 케이스: {perfect_reason}/{total}")
    print("(재현성 높이려면 서버 쪽 LLM temperature를 0에 가깝게 두세요.)")


if __name__ == "__main__":
    main()
