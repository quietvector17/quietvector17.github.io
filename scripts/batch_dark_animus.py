import os
import sys
import argparse
import re
from typing import Iterable, List, Optional, Tuple

import dark_animus


def iter_lines_from_path_or_stdin(path: Optional[str]) -> Iterable[str]:
    if path:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                yield line
        return

    for line in sys.stdin:
        yield line


def parse_input_line(line: str) -> Optional[Tuple[str, Optional[int]]]:
    raw = (line or "").strip()
    if not raw:
        return None
    if raw.startswith("#"):
        return None

    # Common header rows (from fetch_dark_animus_rankings.py or prior runs).
    upper = raw.upper()
    if upper.startswith("RANK\t") or upper.startswith("REPORT\t") or "REPORT_ID" in upper:
        return None

    # Accept either:
    #   <reportID>
    #   <reportID> <fightID>
    #   <rank> <reportID> <reportURL> <fightID> <duration>
    parts = raw.split()
    if not parts:
        return None

    report_id: Optional[str] = None
    fight_id: Optional[int] = None

    # If any token looks like a report URL, extract the code.
    for p in parts:
        if "/reports/" in p:
            try:
                report_id = p.split("/reports/", 1)[1].split("/", 1)[0]
            except Exception:
                report_id = None
            break

    # Otherwise assume first non-rank token is report code.
    if report_id is None:
        # If first token is an int rank, skip it.
        start = 1 if (parts and parts[0].isdigit()) else 0

        # Prefer an alphanumeric-looking report code (WCL codes are base62-ish).
        for p in parts[start:]:
            if re.fullmatch(r"[A-Za-z0-9]{8,}", p) and not p.isdigit():
                report_id = p
                break

    if report_id is None:
        return None

    # Fight id: first int token on the line.
    for p in parts:
        if p.isdigit():
            v = int(p)
            # Heuristic: report IDs are alphanumeric; fight IDs are ints, usually > 0.
            if v > 0:
                fight_id = v
                break

    return report_id, fight_id


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Run dark_animus.py analysis across many reports. "
            "Input lines can be report IDs, or report IDs + fight IDs, or the table output from fetch_dark_animus_rankings.py."
        )
    )
    ap.add_argument("input", nargs="?", help="Path to a text file with report IDs (one per line). If omitted, reads stdin.")
    ap.add_argument("--strict", action="store_true", help="Only match exact actor name 'Anima Golem' (exclude Large/Massive)")
    ap.add_argument("--sleep", type=float, default=0.0, help="Sleep seconds between reports (default: 0)")
    ap.add_argument("--include-missing", action="store_true", help="Print rows for reports with no Dark Animus kill")
    args = ap.parse_args()

    token = dark_animus.get_token(dark_animus.CLIENT_ID, dark_animus.CLIENT_SECRET)
    headers = {"Authorization": f"Bearer {token}"}

    items: List[Tuple[str, Optional[int]]] = []
    for line in iter_lines_from_path_or_stdin(args.input):
        parsed = parse_input_line(line)
        if parsed is None:
            continue
        items.append(parsed)

    if not items:
        raise SystemExit("No report IDs found in input.")

    print("REPORT\tDURATION\tGOLEMS_DMG\tGOLEM_DEATHS\tSTRAT_10M")
    sys.stdout.flush()

    import time

    for idx, (report_code, fight_id) in enumerate(items):
        if idx and args.sleep and args.sleep > 0:
            time.sleep(args.sleep)

        report_url = f"{dark_animus.REPORT_BASE_URL}/{report_code}"
        try:
            _title, fights, actors = dark_animus.fetch_report(headers, report_code)
            actor_by_id = dark_animus.build_actor_by_id(actors)
            player_ids = dark_animus.build_player_id_set(actors)

            pulls = dark_animus.pick_pulls(fights, dark_animus.DEFAULT_FIGHT_NAME, kills_only=True)
            if fight_id is not None:
                pulls = [f for f in pulls if f.get("id") == fight_id]

            if not pulls:
                if args.include_missing:
                    print(f"{report_url}\t-\t0")
                continue

            for f in pulls:
                dur = dark_animus.mmss_from_ms(int(f["endTime"] - f["startTime"]))
                golem_entities, _golems_by_name, _stream = dark_animus.count_anima_golems_that_damage_players(
                    headers,
                    report_code,
                    f,
                    player_ids,
                    actor_by_id,
                    strict=bool(args.strict),
                )

                deaths_count: Optional[int] = None
                if len(golem_entities) <= 12:
                    killed_entities, _k_by_name, _ = dark_animus.count_anima_golems_killed(
                        headers,
                        report_code,
                        f,
                        actor_by_id,
                        strict=bool(args.strict),
                    )
                    deaths_count = len(killed_entities)

                strat_yes = (len(golem_entities) <= 12) and (deaths_count is not None and deaths_count <= 12)
                deaths_out = str(deaths_count) if deaths_count is not None else "-"
                print(f"{report_url}\t{dur}\t{len(golem_entities)}\t{deaths_out}\t{'YES' if strat_yes else 'NO'}")
        except Exception as e:
            # Keep going so a single bad report doesn't stop the batch.
            if args.include_missing:
                print(f"{report_url}\tERROR\t0")
            else:
                print(f"{report_url}\tERROR\t0\t{type(e).__name__}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
