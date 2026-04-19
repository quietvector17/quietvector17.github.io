import os
import argparse
from typing import Any, Dict, List, Optional, Tuple

import requests


API_BASE = "https://classic.warcraftlogs.com"
REPORT_BASE_URL = f"{API_BASE}/reports"


def mmss_from_ms(ms: int) -> str:
    s = ms // 1000
    m, s = divmod(s, 60)
    return f"{m}:{s:02d}"


def fetch_rankings_page(
    api_key: str,
    encounter_id: int,
    metric: str,
    difficulty: int,
    partition: int,
    page: int,
) -> Dict[str, Any]:
    url = f"{API_BASE}/v1/rankings/encounter/{encounter_id}"
    params = {
        "api_key": api_key,
        "metric": metric,
        "difficulty": difficulty,
        "page": page,
    }
    if partition > 0:
        params["partition"] = partition
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch report IDs from WCL v1 encounter rankings (classic).")
    ap.add_argument("--api-key", dest="api_key", help="WCL v1 API key (or set WCL_V1_API_KEY)")
    ap.add_argument("--encounter", type=int, default=51576, help="Encounter ID (default: 51576 = Dark Animus)")
    ap.add_argument("--metric", default="speed", help="Rankings metric (default: speed)")
    ap.add_argument("--difficulty", type=int, default=4, help="Difficulty ID (default: 4)")
    ap.add_argument("--partition", type=int, default=0, help="Partition number (default: 0 = API default)")
    ap.add_argument("--count", type=int, default=100, help="How many ranking rows to fetch (default: 100)")
    ap.add_argument("--start-page", type=int, default=1, help="Start page (default: 1)")
    ap.add_argument("--reports-only", action="store_true", help="Only print report IDs (one per line)")
    args = ap.parse_args()

    api_key = (args.api_key or os.getenv("WCL_V1_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit("Missing v1 api key. Pass --api-key or set WCL_V1_API_KEY.")

    wanted = max(1, int(args.count))
    rows: List[Tuple[int, str, int, int]] = []
    # Tuple: (rank_index_1_based, report_id, fight_id, duration_ms)

    page = int(args.start_page)
    while len(rows) < wanted:
        payload = fetch_rankings_page(api_key, args.encounter, args.metric, args.difficulty, args.partition, page)
        rankings = payload.get("rankings") or []
        if not isinstance(rankings, list) or not rankings:
            break

        for entry in rankings:
            if not isinstance(entry, dict):
                continue
            report_id = entry.get("reportID")
            fight_id = entry.get("fightID")
            duration = entry.get("duration")
            if not isinstance(report_id, str) or not report_id:
                continue
            if not isinstance(fight_id, int):
                continue
            if not isinstance(duration, int):
                duration = 0

            rank = len(rows) + 1
            rows.append((rank, report_id, fight_id, duration))
            if len(rows) >= wanted:
                break

        has_more = bool(payload.get("hasMorePages"))
        if not has_more:
            break
        page += 1

    if args.reports_only:
        for _, report_id, _, _ in rows:
            print(report_id)
        return

    print("RANK\tREPORT_ID\tREPORT_URL\tFIGHT_ID\tDURATION")
    for rank, report_id, fight_id, dur_ms in rows:
        print(f"{rank}\t{report_id}\t{REPORT_BASE_URL}/{report_id}\t{fight_id}\t{mmss_from_ms(dur_ms)}")


if __name__ == "__main__":
    main()
