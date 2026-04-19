# council_analysis_kills_only.py
import os
import requests
from typing import Any, Dict, Iterable, List, Optional, Tuple

REPORT_CODE = "vFYGaXZgdTk9P6tz"
CLIENT_ID = os.getenv("WCL_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("WCL_CLIENT_SECRET", "")

API_URL = "https://classic.warcraftlogs.com/api/v2/client"
TOKEN_URL = "https://classic.warcraftlogs.com/oauth/token"

COUNCIL_FIGHT_NAME = "Council of Elders"

ELDER_KEYS = {
    "Malakk": ["malakk"],
    "Mar'li": ["mar", "li"],
    "Kazra'jin": ["kazra"],
    "Sul": ["sul", "sand"],
}


def get_token(client_id: str, client_secret: str) -> str:
    if not client_id or not client_secret:
        raise SystemExit("Missing CLIENT_ID / CLIENT_SECRET.")
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


def mmss_from_ms(ms: int) -> str:
    s = ms // 1000
    m, s = divmod(s, 60)
    return f"{m}:{s:02d}"


def rel_mmss(ts_abs: int, fight_start: int) -> str:
    return mmss_from_ms(ts_abs - fight_start)


def _norm(s: str) -> str:
    return (s or "").lower().replace("’", "'")


def iter_events(
    headers: Dict[str, str],
    code: str,
    fight_id: int,
    fight_start: int,
    fight_end: int,
    data_type: str,
) -> Iterable[Dict[str, Any]]:
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

    page_start = fight_start
    while True:
        data = gql(headers, query, {"code": code, "fightID": fight_id, "pageStart": page_start, "end": fight_end})
        ev = data["reportData"]["report"]["events"]

        for e in ev.get("data") or []:
            if isinstance(e, dict):
                yield e

        nxt = ev.get("nextPageTimestamp")
        if not nxt:
            break
        page_start = nxt


def fetch_report(headers: Dict[str, str], code: str):
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

    # Prefer non-players
    def score(a: Dict[str, Any]) -> Tuple[int, int]:
        t = _norm(str(a.get("type") or ""))
        st = _norm(str(a.get("subType") or ""))
        is_player = (t == "player") or (st == "player")
        return (1 if is_player else 0, len(_norm(a.get("name") or "")))

    hits.sort(key=score)
    return hits


def build_elder_id_map(actors: List[Dict[str, Any]]) -> Dict[str, List[int]]:
    out: Dict[str, List[int]] = {}
    for label, subs in ELDER_KEYS.items():
        hits = find_actor_ids_fuzzy(actors, subs)
        out[label] = [h["id"] for h in hits if isinstance(h.get("id"), int)]
    return out


def council_death_times_for_kill(
    headers: Dict[str, str],
    code: str,
    fight: Dict[str, Any],
    elder_ids: Dict[str, List[int]],
) -> Dict[str, Optional[int]]:
    """
    Use dataType: All and filter event types for NPC deaths.
    This avoids cases where dataType: Deaths only returns player deaths.
    """
    start = fight["startTime"]
    end = fight["endTime"]
    fight_id = fight["id"]

    wanted = {i for ids in elder_ids.values() for i in ids}
    deaths: Dict[str, Optional[int]] = {k: None for k in elder_ids.keys()}

    if not wanted:
        return deaths

    for e in iter_events(headers, code, fight_id, start, end, "All"):
        et = (e.get("type") or "").lower()
        if et not in {"death", "destroy"}:
            continue

        ts = e.get("timestamp")
        tid = e.get("targetID")
        if not isinstance(ts, int) or not isinstance(tid, int):
            continue
        if tid not in wanted:
            continue

        for elder, ids in elder_ids.items():
            if tid in ids:
                cur = deaths[elder]
                if cur is None or ts < cur:
                    deaths[elder] = ts
                break

    return deaths


def main():
    token = get_token(CLIENT_ID, CLIENT_SECRET)
    headers = {"Authorization": f"Bearer {token}"}

    title, fights, actors = fetch_report(headers, REPORT_CODE)
    print(f"\nReport: {title} ({REPORT_CODE})\n")

    council_kills = [
        f for f in fights
        if isinstance(f, dict)
        and f.get("name") == COUNCIL_FIGHT_NAME
        and f.get("kill") is True
    ]
    if not council_kills:
        print("No Council of Elders kills found.")
        return

    elder_ids = build_elder_id_map(actors)

    print()
    print("Council of Elders — Elder death times (KILLS ONLY)")
    print("--------------------------------------------------")

    for f in council_kills:
        start = f["startTime"]
        dur = mmss_from_ms(f["endTime"] - start)

        deaths = council_death_times_for_kill(headers, REPORT_CODE, f, elder_ids)

        # Determine kill order (earliest death first)
        ordered = sorted(
            deaths.items(),
            key=lambda kv: kv[1] if isinstance(kv[1], int) else float("inf")
        )

        # Build header dynamically
        headers_row = ["Dur"] + [name for name, _ in ordered]
        widths = [6] + [max(7, len(name)) for name, _ in ordered]

        header_fmt = "  ".join(f"{{:>{w}s}}" for w in widths)
        row_fmt = "  ".join(f"{{:>{w}s}}" for w in widths)

        print(header_fmt.format(*headers_row))
        print("-" * (sum(widths) + 2 * (len(widths) - 1)))

        # Build row values
        def fmt(ts: Optional[int]) -> str:
            return rel_mmss(ts, start) if isinstance(ts, int) else "-"

        row = [dur] + [fmt(ts) for _, ts in ordered]
        print(row_fmt.format(*row))

if __name__ == "__main__":
    main()
