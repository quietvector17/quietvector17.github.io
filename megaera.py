# megaera_head_deaths.py
import os
import requests
from typing import Any, Dict, Iterable, List, Optional, Tuple

REPORT_CODE = "vFYGaXZgdTk9P6tz"
CLIENT_ID = os.getenv("WCL_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("WCL_CLIENT_SECRET", "")

API_URL = "https://classic.warcraftlogs.com/api/v2/client"
TOKEN_URL = "https://classic.warcraftlogs.com/oauth/token"

MEGAERA_FIGHT_NAME = "Megaera"

# Fuzzy match substrings for each head type.
# (Heads sometimes show up with slightly different naming; this is resilient.)
HEAD_KEYS = {
    "Flaming": ["flam", "head"],
    "Frozen": ["froz", "head"],
    "Arcane": ["Arcane", "head"],
    "Venomous": ["venom", "head"],
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
    """
    Correct paging: startTime is ONLY the paging cursor; endTime fixed at fight_end.
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


def build_head_id_map(actors: List[Dict[str, Any]]) -> Dict[str, List[int]]:
    out: Dict[str, List[int]] = {}
    for label, subs in HEAD_KEYS.items():
        hits = find_actor_ids_fuzzy(actors, subs)
        out[label] = [h["id"] for h in hits if isinstance(h.get("id"), int)]
    return out


def megaera_head_deaths_for_kill(
    headers: Dict[str, str],
    code: str,
    fight: Dict[str, Any],
    head_ids: Dict[str, List[int]],
) -> Dict[str, List[int]]:
    """
    Returns list of death timestamps (absolute) for each head label during this pull.
    Uses dataType: All and filters death/destroy events by targetID.
    """
    start = fight["startTime"]
    end = fight["endTime"]
    fight_id = fight["id"]

    wanted = {i for ids in head_ids.values() for i in ids}
    deaths: Dict[str, List[int]] = {k: [] for k in head_ids.keys()}

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

        for label, ids in head_ids.items():
            if tid in ids:
                deaths[label].append(ts)
                break

    for k in deaths:
        deaths[k].sort()
    return deaths


def infer_next_head_by_damage(
    headers: Dict[str, str],
    code: str,
    fight_id: int,
    fight_start: int,
    fight_end: int,
    head_ids: Dict[str, List[int]],
    after_ts: int,
    window_ms: int = 10_000,
) -> Tuple[Optional[str], Dict[int, int]]:
    """
    Returns (label, damage_by_targetID) for the head taking the most damage
    in the window immediately after after_ts. If no damage observed, returns (None, ...).
    """
    wanted = {i for ids in head_ids.values() for i in ids}
    end = min(fight_end, after_ts + window_ms)

    dmg_by_tid: Dict[int, int] = {}

    # DamageTaken events: targetID is the victim (the head)
    for e in iter_events(headers, code, fight_id, after_ts, end, "DamageDone"):
        et = (e.get("type") or "").lower()
        if et != "damage":
            continue

        tid = e.get("targetID")
        if not isinstance(tid, int) or tid not in wanted:
            continue

        amt = e.get("amount")
        if not isinstance(amt, int):
            continue

        absorbed = e.get("absorbed")
        if not isinstance(absorbed, int):
            absorbed = 0

        dmg_by_tid[tid] = dmg_by_tid.get(tid, 0) + amt + absorbed

    if not dmg_by_tid:
        return None, dmg_by_tid

    best_tid = max(dmg_by_tid.items(), key=lambda kv: kv[1])[0]

    # Map targetID -> label
    best_label = None
    for label, ids in head_ids.items():
        if best_tid in ids:
            best_label = label
            break

    return best_label, dmg_by_tid


def main():
    token = get_token(CLIENT_ID, CLIENT_SECRET)
    headers = {"Authorization": f"Bearer {token}"}

    title, fights, actors = fetch_report(headers, REPORT_CODE)
    print("\nReport: {} ({})\n".format(title, REPORT_CODE))

    megaera_kills = [
        f for f in fights
        if isinstance(f, dict)
        and f.get("name") == MEGAERA_FIGHT_NAME
        and f.get("kill") is True
    ]
    if not megaera_kills:
        print("No Megaera kills found.")
        return

    head_ids = build_head_id_map(actors)

    # Show what we matched (helps immediately if something is off)
    # print("Matched head actor IDs (fuzzy):")
    # for label, subs in HEAD_KEYS.items():
    #     hits = find_actor_ids_fuzzy(actors, subs)
    #     top = hits[:6]
    #     if not top:
    #         print("  {:8s}: (no matches for substrings {})".format(label, subs))
    #     else:
    #         printable = ", ".join("{}#{}".format(h.get("name"), h.get("id")) for h in top)
    #         print("  {:8s}: {}".format(label, printable))
    # print()

    print("Megaera — head death times (KILLS ONLY)")
    print("--------------------------------------")

    for f in megaera_kills:
        start = f["startTime"]
        dur = mmss_from_ms(f["endTime"] - start)
        end = f["endTime"]
        fight_id = f["id"]
        deaths = megaera_head_deaths_for_kill(headers, REPORT_CODE, f, head_ids)

        # Print per-head lists
        print("\nKill duration: {}   (fight id {})".format(dur, f.get("id")))
        # for label in ["Flaming", "Arcane", "Frozen", "Venomous"]:
        #     times = [rel_mmss(ts, start) for ts in deaths.get(label, [])]
        #     if not times:
        #         print("  {:8s}: -".format(label))
        #     else:
        #         print("  {:8s}: {}".format(label, ", ".join(times)))

        # Also print overall death order (merged)
        merged: List[Tuple[int, str]] = []
        for label, ts_list in deaths.items():
            for ts in ts_list:
                merged.append((ts, label))
        merged.sort(key=lambda x: x[0])

        # if merged:
        #     pretty = ", ".join("{} {}".format(label, rel_mmss(ts, start)) for ts, label in merged)
        #     pretty += ", Frozen " + str(dur)
        #     print("  Order   : {}".format(pretty))
        # else:
        #     print("  Order   : -")

        if merged:
            pretty = ", ".join("{} {}".format(label, rel_mmss(ts, start)) for ts, label in merged)

            last_death_ts = merged[-1][0]
            inferred_label, dmg_map = infer_next_head_by_damage(
                headers=headers,
                code=REPORT_CODE,
                fight_id=fight_id,
                fight_start=start,
                fight_end=end,
                head_ids=head_ids,
                after_ts=last_death_ts,
                window_ms=10_000,
            )

            # Only append an inferred "final" head if it isn't already the last recorded label
            if inferred_label and inferred_label != merged[-1][1]:
                pretty += ", {} {}".format(inferred_label, rel_mmss(end, start))
                # (optional) show debug:
                # print("  Debug dmg:", {k: v for k, v in sorted(dmg_map.items(), key=lambda x: -x[1])[:5]})

            print("  Order   : {}".format(pretty))
        else:
            print("  Order   : -")



if __name__ == "__main__":
    main()
