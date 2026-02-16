import os
import sys
import requests
from typing import Any, Dict, Iterable, List, Optional, Tuple
import argparse


# Substring-based fuzzy match. We intentionally avoid punctuation dependency.



REPORT_CODE = "vFYGaXZgdTk9P6tz"
CLIENT_ID = os.getenv("WCL_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("WCL_CLIENT_SECRET", "")

API_URL = "https://classic.warcraftlogs.com/api/v2/client"
TOKEN_URL = "https://classic.warcraftlogs.com/oauth/token"

MEGAERA_FIGHT_NAME = "Iron Qon"
DOG_KEYS: Dict[str, List[str]] = {
    "Ro'Shak":  ["ro", "shak"],
    "Quet'Zal": ["quet", "zal"],
    "Dam'Ren":  ["dam", "ren"],
}
IRON_QON_KEYS = ["iron", "qon"]
WIND_STORM_ID = 136577



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


def build_dog_id_map(actors: List[Dict[str, Any]]) -> Dict[str, List[int]]:
    out: Dict[str, List[int]] = {}
    for label, subs in DOG_KEYS.items():
        hits = find_actor_ids_fuzzy(actors, subs)
        out[label] = [h["id"] for h in hits if isinstance(h.get("id"), int)]
    return out


def iron_qon_dog_deaths_for_kill(
    headers: Dict[str, str],
    code: str,
    fight: Dict[str, Any],
    dog_ids: Dict[str, List[int]],
) -> Dict[str, List[int]]:
    """
    Returns absolute death timestamps for each dog label during this pull.
    Looks for type in {"death","destroy"} in dataType: All, filtering by targetID.
    """
    start = fight["startTime"]
    end = fight["endTime"]
    fight_id = fight["id"]

    wanted = {i for ids in dog_ids.values() for i in ids}
    deaths: Dict[str, List[int]] = {k: [] for k in dog_ids.keys()}

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

        for label, ids in dog_ids.items():
            if tid in ids:
                deaths[label].append(ts)
                break

    for k in deaths:
        deaths[k].sort()
    return deaths


def build_actor_by_id(actors: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for a in actors:
        if isinstance(a, dict) and isinstance(a.get("id"), int):
            out[a["id"]] = a
    return out


def is_player_actor(actor: Optional[Dict[str, Any]]) -> bool:
    if not actor:
        return False
    t = _norm(str(actor.get("type") or ""))
    st = _norm(str(actor.get("subType") or ""))
    return (t == "player") or (st == "player")


def find_single_actor_id_fuzzy(actors: List[Dict[str, Any]], subs: List[str]) -> Optional[int]:
    hits = find_actor_ids_fuzzy(actors, subs)
    for h in hits:
        hid = h.get("id")
        if isinstance(hid, int):
            return hid
    return None

def roshak_first_25pct_time(
    headers: Dict[str, str],
    code: str,
    fight: Dict[str, Any],
    roshak_ids: List[int],
) -> Optional[int]:
    """
    Returns abs timestamp of first moment Ro'Shak is <= 25% HP.
    Tries:
      1) type="health" events (hitPoints/maxHitPoints)
      2) type="resource(s)" events for health snapshots (amount/max) if present
    """
    if not roshak_ids:
        return None

    start = fight["startTime"]
    end = fight["endTime"]
    fight_id = fight["id"]

    # ---- Pass 1: health events ----
    for e in iter_events(headers, code, fight_id, start, end, "All"):
        if (e.get("type") or "").lower() != "health":
            continue
        tid = e.get("targetID")
        if not isinstance(tid, int) or tid not in roshak_ids:
            continue

        ts = e.get("timestamp")
        hp = e.get("hitPoints")
        mhp = e.get("maxHitPoints")
        if not (isinstance(ts, int) and isinstance(hp, int) and isinstance(mhp, int) and mhp > 0):
            continue

        if hp * 4 <= mhp:   # hp/mhp <= 0.25 without floats
            return ts

    # ---- Pass 2: resources events (health snapshots) ----
    for e in iter_events(headers, code, fight_id, start, end, "All"):
        et = (e.get("type") or "").lower()
        if et not in {"resource", "resources"}:
            continue

        tid = e.get("targetID")
        if not isinstance(tid, int) or tid not in roshak_ids:
            continue

        # WCL commonly uses resourceType 0 for health in these snapshots
        rt = e.get("resourceType")
        if isinstance(rt, int) and rt != 0:
            continue

        ts = e.get("timestamp")
        amt = e.get("amount")
        mx = e.get("max")
        if not (isinstance(ts, int) and isinstance(amt, int) and isinstance(mx, int) and mx > 0):
            continue

        if amt * 4 <= mx:
            return ts

    return None

def find_single_actor_id_fuzzy(actors: List[Dict[str, Any]], subs: List[str]) -> Optional[int]:
    hits = find_actor_ids_fuzzy(actors, subs)
    for h in hits:
        hid = h.get("id")
        if isinstance(hid, int):
            return hid
    return None

def target_hp_pct_at_time(
    headers: Dict[str, str],
    code: str,
    fight: Dict[str, Any],
    target_ids: List[int],
    ts_abs: int,
    lookback_ms: int = 60_000,
) -> Optional[float]:
    """
    Returns HP% (0-100) for target at ts_abs using the latest snapshot <= ts_abs.
    Tries 'health' then 'resource(s)' snapshots within [ts_abs - lookback_ms, ts_abs].
    """
    if not target_ids or not isinstance(ts_abs, int):
        return None

    fight_id = fight["id"]
    fight_start = fight["startTime"]
    fight_end = fight["endTime"]

    start = max(fight_start, ts_abs - lookback_ms)
    end = min(fight_end, ts_abs)

    wanted = set(target_ids)

    best_ts = -1
    best_pct: Optional[float] = None

    # Pull a tight window of All-events and keep the latest snapshot <= ts_abs.
    for e in iter_events(headers, code, fight_id, fight_start, fight_end, "All", start_override=start, end_override=end):
        tid = e.get("targetID")
        if not isinstance(tid, int) or tid not in wanted:
            continue

        et = (e.get("type") or "").lower()
        ts = e.get("timestamp")
        if not isinstance(ts, int):
            continue

        if et == "health":
            hp = e.get("hitPoints")
            mhp = e.get("maxHitPoints")
            if isinstance(hp, int) and isinstance(mhp, int) and mhp > 0:
                if ts > best_ts:
                    best_ts = ts
                    best_pct = (hp / mhp) * 100.0

        elif et in {"resource", "resources"}:
            rt = e.get("resourceType")
            if isinstance(rt, int) and rt != 0:
                continue  # usually 0 == health
            amt = e.get("amount")
            mx = e.get("max")
            if isinstance(amt, int) and isinstance(mx, int) and mx > 0:
                if ts > best_ts:
                    best_ts = ts
                    best_pct = (amt / mx) * 100.0

    return best_pct


def quetzal_hp_pct_at_windstorm_by_damage(
    headers: Dict[str, str],
    code: str,
    fight: Dict[str, Any],
    quet_ids: List[int],
    wind_ts_abs: int,
    max_hp: int,
) -> Optional[float]:
    """
    Approx HP% at windstorm timestamp by summing DamageDone to Quet'Zal up to wind_ts_abs.
    Uses amount only (absorbed doesn't reduce HP).
    """
    if not quet_ids or not isinstance(wind_ts_abs, int) or not isinstance(max_hp, int) or max_hp <= 0:
        return None

    start = fight["startTime"]
    end = min(fight["endTime"], wind_ts_abs)
    fight_id = fight["id"]
    wanted = set(quet_ids)

    dmg = 0
    for e in iter_events(headers, code, fight_id, start, end, "DamageDone"):
        if (e.get("type") or "").lower() != "damage":
            continue
        tid = e.get("targetID")
        if not isinstance(tid, int) or tid not in wanted:
            continue
        amt = e.get("amount")
        if isinstance(amt, int) and amt > 0:
            dmg += amt

    # clamp
    if dmg < 0:
        dmg = 0
    if dmg > max_hp:
        dmg = max_hp

    return 100.0 * (1.0 - (dmg / max_hp))


def first_damage_to_targets(
    headers: Dict[str, str],
    code: str,
    fight: Dict[str, Any],
    target_ids: List[int],
) -> Optional[int]:
    if not target_ids:
        return None

    start = fight["startTime"]
    end = fight["endTime"]
    fight_id = fight["id"]
    wanted = set(target_ids)

    for e in iter_events(headers, code, fight_id, start, end, "DamageDone"):
        if (e.get("type") or "").lower() != "damage":
            continue

        tid = e.get("targetID")
        ts = e.get("timestamp")
        amt = e.get("amount")

        if not (isinstance(tid, int) and isinstance(ts, int) and isinstance(amt, int)):
            continue
        if tid not in wanted:
            continue
        if amt <= 0:
            continue

        return ts

    return None



def first_wind_storm_application(
    headers: Dict[str, str],
    code: str,
    fight: Dict[str, Any],
    actor_by_id: Dict[int, Dict[str, Any]],
) -> Optional[Tuple[int, int]]:
    """
    Returns (timestamp_abs, targetID) for the FIRST applydebuff of Wind Storm (136577) on ANY player.
    """
    start = fight["startTime"]
    end = fight["endTime"]
    fight_id = fight["id"]

    first: Optional[Tuple[int, int]] = None

    for e in iter_events(headers, code, fight_id, start, end, "Debuffs"):
        if (e.get("type") or "").lower() != "applydebuff":
            continue

        # robust ability id extraction
        ability_id = e.get("abilityGameID")
        if not isinstance(ability_id, int):
            ab = e.get("ability")
            if isinstance(ab, dict) and isinstance(ab.get("gameID"), int):
                ability_id = ab["gameID"]

        if ability_id != WIND_STORM_ID:
            continue

        ts = e.get("timestamp")
        tid = e.get("targetID")
        if not (isinstance(ts, int) and isinstance(tid, int)):
            continue

        # ONLY care if target is a player
        if not is_player_actor(actor_by_id.get(tid)):
            continue

        first = (ts, tid)
        break  # first instance only

    return first



def pick_fight_ids(fights: List[Dict[str, Any]], fight_name: str) -> List[Dict[str, Any]]:
    return [
        f for f in fights
        if isinstance(f, dict)
        and (f.get("name") == fight_name)
        and (f.get("kill") is True)
        and isinstance(f.get("startTime"), int)
        and isinstance(f.get("endTime"), int)
        and isinstance(f.get("id"), int)
    ]


def main() -> None:
    ap = argparse.ArgumentParser(description="Iron Qon dog death timing (Ro'Shak/Quet'Zal/Dam'Ren) from WCL report.")
    ap.add_argument("code", nargs="?", help="Warcraft Logs report code (e.g. vFYGaXZgdTk9P6tz)")
    ap.add_argument("--code", dest="code2", help="Same as positional code")
    ap.add_argument("--fight", default="Iron Qon", help="Fight name as it appears in WCL (default: Iron Qon)")
    args = ap.parse_args()
    report_code = REPORT_CODE
    if not report_code:
        raise SystemExit("Missing report code. Example: py iron_qon_dog_deaths.py vFYGaXZgdTk9P6tz")

    client_id = CLIENT_ID
    client_secret = CLIENT_SECRET

    token = get_token(client_id, client_secret)
    headers = {"Authorization": f"Bearer {token}"}

    title, fights, actors = fetch_report(headers, report_code)
    actor_by_id = build_actor_by_id(actors)
    iron_qon_id = find_single_actor_id_fuzzy(actors, IRON_QON_KEYS)  # optional; used only for debug/printing if you want

    print(f"\nReport: {title} ({report_code})\n")

    kills = pick_fight_ids(fights, args.fight)
    if not kills:
        # helpful hint: show unique fight names containing 'qon' if name mismatch
        names = sorted({str(f.get("name")) for f in fights if isinstance(f, dict) and isinstance(f.get("name"), str)})
        sugg = [n for n in names if "qon" in _norm(n)]
        print(f"No kills found for fight name: {args.fight!r}")
        if sugg:
            print("Fight names containing 'qon' in this report:")
            for n in sugg:
                print("  -", n)
        return

    dog_ids = build_dog_id_map(actors)

    # print("Matched dog actor IDs (fuzzy):")
    # for label, subs in DOG_KEYS.items():
    #     hits = find_actor_ids_fuzzy(actors, subs)[:6]
    #     if not hits:
    #         print(f"  {label:8s}: (no matches for substrings {subs})")
    #     else:
    #         printable = ", ".join(f"{h.get('name')}#{h.get('id')}" for h in hits)
    #         print(f"  {label:8s}: {printable}")
    # print()

    # print("Iron Qon — dog death times (KILLS ONLY)")
    # print("---------------------------------------")

    for f in kills:
        fight_id = f["id"]
        start = f["startTime"]
        end = f["endTime"]
        dur = mmss_from_ms(end - start)
        # Ro'Shak 25% time
        # ro25_ts = roshak_first_25pct_time(headers, report_code, f, dog_ids.get("Ro'Shak", []))
        ro25_ts = first_damage_to_targets(
            headers, report_code, f,
            [iron_qon_id] if isinstance(iron_qon_id, int) else []
        )


        # First Wind Storm application
        wind = first_wind_storm_application(headers, report_code, f, actor_by_id)
        QUETZAL_MAX_HP = 399_065_355

        quet_hp = None
        if wind is not None:
            wind_ts, _ = wind
            quet_hp = quetzal_hp_pct_at_windstorm_by_damage(
                headers, report_code, f,
                dog_ids.get("Quet'Zal", []),
                wind_ts,
                QUETZAL_MAX_HP
            )




        deaths = iron_qon_dog_deaths_for_kill(headers, report_code, f, dog_ids)
        print(f"\nKill duration: {dur}   (fight id {fight_id})")

        if ro25_ts is None:
            print("  Ro25%   : -")
        else:
            print(f"  Ro25%   : {rel_mmss(ro25_ts, start)}")

        if wind is None:
            print("  Wind1st : -")
        else:
            wind_ts, wind_tid = wind
            print(f"  Windstorm : {rel_mmss(wind_ts, start)}")

        print("  Quetzal HP @ Windstorm : " + ("-" if quet_hp is None else f"{quet_hp:.1f}% (approx)"))


        for label in ["Ro'Shak", "Quet'Zal", "Dam'Ren"]:
            times = [rel_mmss(ts, start) for ts in deaths.get(label, [])]
            print(f"  {label:8s}: " + ("-" if not times else ", ".join(times)))

        merged: List[Tuple[int, str]] = []
        for label, ts_list in deaths.items():
            for ts in ts_list:
                merged.append((ts, label))
        merged.sort(key=lambda x: x[0])

        if merged:
            pretty = ", ".join(f"{label} {rel_mmss(ts, start)}" for ts, label in merged)
            pretty += f", Iron Qon {dur}"
            print(f"  Order   : {pretty}")
        else:
            print("  Order   : -")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
