import os, textwrap, pathlib

import argparse
import os
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests


# -------------------- CONFIG --------------------

API_URL = "https://www.warcraftlogs.com/api/v2/client"
TOKEN_URL = "https://www.warcraftlogs.com/oauth/token"

REPORT_CODE = "jDYLdFghJPqbXWCa"
CLIENT_ID = os.getenv("WCL_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("WCL_CLIENT_SECRET", "")

# Fight naming / boss matching
DEFAULT_FIGHT_NAME = "Lei Shen"
LEI_SHEN_KEYS = ["lei", "shen"]



# Fight naming / boss matching
DEFAULT_FIGHT_NAME = "Lei Shen"
LEI_SHEN_KEYS = ["lei", "shen"]

# Intermission marker
SUPERCHARGE_CONDUITS_ID = 137045


# -------------------- HTTP / GQL --------------------

def get_token(client_id: str, client_secret: str) -> str:
    if not client_id or not client_secret:
        raise SystemExit("Missing WCL_CLIENT_ID / WCL_CLIENT_SECRET environment variables.")
    r = requests.post(
        TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def gql(headers: Dict[str, str], query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.post(API_URL, json={"query": query, "variables": variables}, headers=headers, timeout=30)
    r.raise_for_status()
    payload = r.json()
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload["data"]


# -------------------- TIME HELPERS --------------------

def mmss_from_ms(ms: int) -> str:
    s = ms // 1000
    m, s = divmod(s, 60)
    return f"{m}:{s:02d}"


def rel_mmss(ts_abs: int, fight_start: int) -> str:
    return mmss_from_ms(ts_abs - fight_start)


# -------------------- STRING / ACTOR MATCHING --------------------

def _norm(s: str) -> str:
    return (s or "").lower().replace("’", "'")


def fetch_report(headers: Dict[str, str], code: str) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
    query = """
    query($code: String!) {
      reportData {
        report(code: $code) {
          title
          fights { id name kill startTime endTime }
          masterData { actors { id name type subType } }
        }
      }
    }
    """
    data = gql(headers, query, {"code": code})
    rep = data["reportData"]["report"]
    return rep["title"], (rep["fights"] or []), (rep["masterData"]["actors"] or [])


def find_actor_ids_fuzzy(actors: List[Dict[str, Any]], required_substrings: List[str]) -> List[Dict[str, Any]]:
    req = [_norm(x) for x in required_substrings]
    hits: List[Dict[str, Any]] = []

    for a in actors:
        if not isinstance(a, dict):
            continue
        name = a.get("name")
        if not isinstance(name, str):
            continue

        n = _norm(name)
        if all(r in n for r in req):
            hits.append(a)

    # Prefer non-players; then shorter names
    def score(a: Dict[str, Any]) -> Tuple[int, int]:
        t = _norm(str(a.get("type") or ""))
        st = _norm(str(a.get("subType") or ""))
        is_player = (t == "player") or (st == "player")
        return (1 if is_player else 0, len(_norm(a.get("name") or "")))

    hits.sort(key=score)
    return hits


def find_single_actor_id_fuzzy(actors: List[Dict[str, Any]], subs: List[str]) -> Optional[int]:
    hits = find_actor_ids_fuzzy(actors, subs)
    for h in hits:
        hid = h.get("id")
        if isinstance(hid, int):
            return hid
    return None


# -------------------- EVENT ITERATION (PAGED) --------------------

def iter_events(
    headers: Dict[str, str],
    code: str,
    fight_id: int,
    fight_start: int,
    fight_end: int,
    data_type: str,
    start_override: Optional[int] = None,
    end_override: Optional[int] = None,
) -> Iterable[Dict[str, Any]]:
    """
    Correct paging: startTime is ONLY the paging cursor; endTime fixed.
    """
    query = f"""
    query($code: String!, $fightID: Int!, $pageStart: Float!, $end: Float!) {{
      reportData {{
        report(code: $code) {{
          events(
            fightIDs: [$fightID]
            startTime: $pageStart
            endTime: $end
            dataType: {data_type}
            limit: 5000
          ) {{
            data
            nextPageTimestamp
          }}
        }}
      }}
    }}
    """

    page_start = start_override if isinstance(start_override, int) else fight_start
    fixed_end = end_override if isinstance(end_override, int) else fight_end

    while True:
        data = gql(headers, query, {"code": code, "fightID": fight_id, "pageStart": page_start, "end": fixed_end})
        ev = data["reportData"]["report"]["events"]

        for e in ev.get("data") or []:
            if isinstance(e, dict):
                yield e

        nxt = ev.get("nextPageTimestamp")
        if not nxt:
            break
        page_start = nxt


# -------------------- INTERMISSION DETECTION --------------------

def lei_shen_intermission_casts(
    headers: Dict[str, str],
    code: str,
    fight: Dict[str, Any],
    ability_id: int = SUPERCHARGE_CONDUITS_ID,
) ->  List[int]:
    """
    Returns [(timestamp_abs, sourceID), ...] for begin-cast/cast of ability_id.
    DOES NOT filter sourceID (because WCL may attribute this cast to conduits/encounter actors).
    """
    start = fight["startTime"]
    end = fight["endTime"]
    fight_id = fight["id"]

    out: List[Tuple[int, int]] = []

    # Try Casts stream first
    for e in iter_events(headers, code, fight_id, start, end, "Casts"):
        et = (e.get("type") or "").lower()
        if et != "startcast":
            continue

        # robust ability id extraction
        abid = e.get("abilityGameID")
        if not isinstance(abid, int):
            ab = e.get("ability")
            if isinstance(ab, dict) and isinstance(ab.get("gameID"), int):
                abid = ab["gameID"]

        if abid != ability_id:
            continue

        ts = e.get("timestamp")
        sid = e.get("sourceID")
        if isinstance(ts, int) and isinstance(sid, int):
            out.append(ts)

    # If still nothing, fall back to All (some logs are funky)
    if not out:
        for e in iter_events(headers, code, fight_id, start, end, "All"):
            et = (e.get("type") or "").lower()
            if et not in {"begincast", "cast"}:
                continue

            abid = e.get("abilityGameID")
            if not isinstance(abid, int):
                ab = e.get("ability")
                if isinstance(ab, dict) and isinstance(ab.get("gameID"), int):
                    abid = ab["gameID"]

            if abid != ability_id:
                continue

            ts = e.get("timestamp")
            sid = e.get("sourceID")
            if isinstance(ts, int) and isinstance(sid, int):
                out.append(ts)

    out.sort()
    return out


# -------------------- FIGHT SELECTION --------------------

def pick_kills(fights: List[Dict[str, Any]], fight_name: str) -> List[Dict[str, Any]]:
    return [
        f for f in fights
        if isinstance(f, dict)
        and (f.get("name") == fight_name)
        and (f.get("kill") is True)
        and isinstance(f.get("startTime"), int)
        and isinstance(f.get("endTime"), int)
        and isinstance(f.get("id"), int)
    ]


# -------------------- MAIN --------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Lei Shen intermission timing via Supercharge Conduits cast (137045).")
    ap.add_argument("code", nargs="?", help="Warcraft Logs report code (e.g. vFYGaXZgdTk9P6tz)")
    ap.add_argument("--code", dest="code2", help="Same as positional code")
    ap.add_argument("--fight", default=DEFAULT_FIGHT_NAME, help=f"Fight name as it appears in WCL (default: {DEFAULT_FIGHT_NAME})")
    ap.add_argument("--ability", type=int, default=SUPERCHARGE_CONDUITS_ID, help="Ability gameID to detect (default: 137045)")
    args = ap.parse_args()

    report_code = (args.code or args.code2 or REPORT_CODE).strip()
    if not report_code:
        raise SystemExit("Missing report code. Example: py lei_shen_intermissions.py vFYGaXZgdTk9P6tz")

    token = get_token(CLIENT_ID, CLIENT_SECRET)
    headers = {"Authorization": f"Bearer {token}"}

    title, fights, actors = fetch_report(headers, report_code)

    lei_id = find_single_actor_id_fuzzy(actors, LEI_SHEN_KEYS)
    lei_ids = [lei_id] if isinstance(lei_id, int) else []

    print(f"\nReport: {title} ({report_code})\n")

    kills = pick_kills(fights, args.fight)
    if not kills:
        names = sorted({str(f.get("name")) for f in fights if isinstance(f, dict) and isinstance(f.get("name"), str)})
        sugg = [n for n in names if "lei" in _norm(n) or "shen" in _norm(n)]
        print(f"No kills found for fight name: {args.fight!r}")
        if sugg:
            print("Fight names containing 'lei'/'shen' in this report:")
            for n in sugg:
                print("  -", n)
        return

    if not lei_ids:
        print("WARNING: Could not find Lei Shen actor id via fuzzy match. Try adjusting LEI_SHEN_KEYS.\n")

    print("Lei Shen — intermission times (KILLS ONLY)")
    print("-----------------------------------------")
    print(f"Marker: cast ability {args.ability} (Supercharge Conduits)")
    print()

    for f in kills:
        fight_id = f["id"]
        start = f["startTime"]
        end = f["endTime"]
        dur = mmss_from_ms(end - start)

        casts = lei_shen_intermission_casts(headers, report_code, f, ability_id=args.ability)
        
        marks = casts[::2]   # take index 0, 2, 4, ...

        if len(marks) >= 1:
            print(f"  Intermission 1: {rel_mmss(marks[0], start)}")
        else:
            print("  Intermission 1: -")

        if len(marks) >= 2:
            print(f"  Intermission 2: {rel_mmss(marks[1], start)}")
        else:
            print("  Intermission 2: -")

        if len(marks) > 2:
            extra = ", ".join(rel_mmss(ts, start) for ts in marks[2:])
            print(f"  Extra intermissions: {extra}")


        print()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
