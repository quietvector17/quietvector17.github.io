import os
import requests
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Tuple

REPORT_CODE = "vFYGaXZgdTk9P6tz"
CLIENT_ID = os.getenv("WCL_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("WCL_CLIENT_SECRET", "")

API_URL = "https://classic.warcraftlogs.com/api/v2/client"
TOKEN_URL = "https://classic.warcraftlogs.com/oauth/token"

TORTOS_FIGHT_NAME = "Tortos"
SHELL_NAME = "Shell Concussion"

AURA_TYPES = {
    "applydebuff", "applydebuffstack", "refreshdebuff", "refreshdebuffstack", "removedebuff",
    "applybuff", "applybuffstack", "refreshbuff", "refreshbuffstack", "removebuff",
}
#!/usr/bin/env python3
"""
Tortos – Shell Concussion uptime/applications from a Warcraft Logs Classic report.

Fixes vs your current version:
- Uses translate: true so ability names populate reliably
- Defaults to dataType=Debuffs (still works with All, but Debuffs is cleaner)
- Robust ability extraction (name + id + guid fallbacks)
- If Shell Concussion still shows 0, prints a small SANITY sample of debuff/aura events on Tortos
- Reads WCL credentials from environment variables (do NOT hardcode secrets)

Usage (PowerShell):
  $env:WCL_CLIENT_ID="..."
  $env:WCL_CLIENT_SECRET="..."
  py tortos.py

Optional overrides:
  $env:WCL_REPORT_CODE="vFYGaXZgdTk9P6tz"
  $env:WCL_FIGHT_NAME="Tortos"
  $env:WCL_AURA_NAME="Shell Concussion"
"""

import os
import requests
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ---- Config (defaults can be overridden by env vars) ----
REPORT_CODE = os.getenv("WCL_REPORT_CODE", "vFYGaXZgdTk9P6tz")
SHELL_ABILITY_ID = 136431

API_URL = "https://classic.warcraftlogs.com/api/v2/client"
TOKEN_URL = "https://classic.warcraftlogs.com/oauth/token"

TORTOS_FIGHT_NAME = os.getenv("WCL_FIGHT_NAME", "Tortos")
SHELL_NAME = os.getenv("WCL_AURA_NAME", "Shell Concussion")

# If you want to hard-force matching by spell id(s) instead of name:
# Put comma-separated IDs in env var, e.g. $env:WCL_AURA_IDS="12345,67890"
SHELL_ABILITY_IDS_ENV = os.getenv("WCL_AURA_IDS", "").strip()
SHELL_ABILITY_IDS: Optional[set[int]] = None
if SHELL_ABILITY_IDS_ENV:
    try:
        SHELL_ABILITY_IDS = {int(x.strip()) for x in SHELL_ABILITY_IDS_ENV.split(",") if x.strip()}
    except ValueError:
        raise SystemExit("WCL_AURA_IDS must be comma-separated integers.")

AURA_TYPES = {
    "applydebuff", "applydebuffstack", "refreshdebuff", "refreshdebuffstack", "removedebuff",
    "applybuff", "applybuffstack", "refreshbuff", "refreshbuffstack", "removebuff",
}


def get_token(client_id: str, client_secret: str) -> str:
    if not client_id or not client_secret:
        raise SystemExit(
            "Missing WCL_CLIENT_ID / WCL_CLIENT_SECRET environment variables.\n"
            "PowerShell example:\n"
            '  $env:WCL_CLIENT_ID="..."\n'
            '  $env:WCL_CLIENT_SECRET="..."\n'
        )
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

def mmss_since_pull(ts: int, pull_start: int) -> str:
    return mmss_from_ms(ts - pull_start)


def _norm(s: str) -> str:
    return (s or "").lower().replace("’", "'")


def iter_events(
    headers: Dict[str, str],
    code: str,
    fight_id: int,
    fight_start: int,
    fight_end: int,
    data_type: str = "Debuffs",
    hostility_type: str = "Enemies",
) -> Iterable[Dict[str, Any]]:
    """
    Correct paging:
      - startTime is ONLY the paging cursor
      - endTime is fixed (fight_end)
    IMPORTANT:
      - translate: true makes ability names reliable
      - hostilityType Enemies is required to see boss auras consistently
    """
    query = """
    query(
      $code: String!,
      $fightID: Int!,
      $pageStart: Float!,
      $end: Float!,
      $hostility: HostilityType!,
      $dt: EventDataType!
    ) {
      reportData {
        report(code: $code) {
          events(
            fightIDs: [$fightID]
            startTime: $pageStart
            endTime: $end
            dataType: $dt
            hostilityType: $hostility
            translate: true
            limit: 5000
          ) {
            data
            nextPageTimestamp
          }
        }
      }
    }
    """

    page_start = fight_start
    while True:
        data = gql(
            headers,
            query,
            {
                "code": code,
                "fightID": fight_id,
                "pageStart": page_start,
                "end": fight_end,
                "hostility": hostility_type,
                "dt": data_type,
            },
        )
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

    def score(a: Dict[str, Any]) -> Tuple[int, int]:
        t = _norm(str(a.get("type") or ""))
        st = _norm(str(a.get("subType") or ""))
        is_player = (t == "player") or (st == "player")
        # Prefer non-player (boss/NPC) and shorter exact-looking names
        return (1 if is_player else 0, len(_norm(a.get("name") or "")))

    hits.sort(key=score)
    return hits


def get_ability(e: Dict[str, Any]) -> Tuple[Optional[str], Optional[int]]:
    """
    Returns (ability_name, ability_id) with lots of fallbacks.
    """
    ab = e.get("ability")
    if isinstance(ab, dict):
        name = ab.get("name")
        abid = ab.get("id")
        if isinstance(name, str) and name:
            return name, abid if isinstance(abid, int) else None
        # sometimes different key names show up
        for nk in ("abilityName", "spellName", "name"):
            v = ab.get(nk)
            if isinstance(v, str) and v:
                return v, abid if isinstance(abid, int) else None

    # fallbacks on top-level fields
    for nk in ("abilityName", "spellName", "name"):
        v = e.get(nk)
        if isinstance(v, str) and v:
            # ID might be elsewhere
            for ik in ("abilityGameID", "abilityID", "spellID", "guid"):
                iv = e.get(ik)
                if isinstance(iv, int):
                    return v, iv
            return v, None

    # last-ditch id-only
    for ik in ("abilityGameID", "abilityID", "spellID", "guid"):
        iv = e.get(ik)
        if isinstance(iv, int):
            return None, iv

    return None, None


def get_target_id(e: Dict[str, Any]) -> Optional[int]:
    tid = e.get("targetID")
    if isinstance(tid, int):
        return tid
    target = e.get("target")
    if isinstance(target, dict):
        tid2 = target.get("id")
        return tid2 if isinstance(tid2, int) else None
    if isinstance(target, int):
        return target
    return None


def shell_stats_from_all_enemies(
    headers: Dict[str, str],
    code: str,
    fight: Dict[str, Any],
    tortos_ids: List[int],
) -> Tuple[int, int, float, int, List[int]]:
    fight_id = fight["id"]
    start = fight["startTime"]
    end = fight["endTime"]
    fight_len = end - start

    tortos_set = set(tortos_ids)
    rows: List[Tuple[int, str]] = []

    # Use Debuffs by default; Shell Concussion is a debuff.
    for e in iter_events(headers, code, fight_id, start, end, data_type="Debuffs", hostility_type="Enemies"):
        et = (e.get("type") or "").lower()
        if et not in AURA_TYPES:
            continue

        tid = get_target_id(e)
        ts = e.get("timestamp")
        if not isinstance(tid, int) or tid not in tortos_set:
            continue
        if not isinstance(ts, int):
            continue

        ab_id = get_ability_id(e)

        if ab_id != SHELL_ABILITY_ID:
            continue

        rows.append((ts, et))

    rows.sort(key=lambda x: x[0])

    active = False
    active_start: Optional[int] = None
    uptime_ms = 0
    applications = 0
    application_times: List[int] = []

    def is_apply(t: str) -> bool:
        return t in {"applydebuff", "applydebuffstack", "applybuff", "applybuffstack"}

    def is_refresh(t: str) -> bool:
        return t in {"refreshdebuff", "refreshdebuffstack", "refreshbuff", "refreshbuffstack"}

    def is_remove(t: str) -> bool:
        return t in {"removedebuff", "removebuff"}

    for ts, et in rows:
        if is_apply(et):
            if not active:
                applications += 1
                application_times.append(ts)
                active = True
                active_start = ts
        elif is_refresh(et):
            if not active:
                applications += 1
                application_times.append(ts)
                active = True
                active_start = ts
        elif is_remove(et):
            if active and active_start is not None:
                uptime_ms += max(0, ts - active_start)
            active = False
            active_start = None

    if active and active_start is not None:
        uptime_ms += max(0, end - active_start)

    uptime_pct = (uptime_ms / fight_len * 100.0) if fight_len > 0 else 0.0
    return applications, uptime_ms, uptime_pct, len(rows), application_times


def discover_auras_on_tortos_enemies(
    headers: Dict[str, str],
    code: str,
    fight: Dict[str, Any],
    tortos_ids: List[int],
    top_n: int = 30,
) -> List[Tuple[str, int]]:
    fight_id = fight["id"]
    start = fight["startTime"]
    end = fight["endTime"]
    tortos_set = set(tortos_ids)

    c: Counter[str] = Counter()

    for e in iter_events(headers, code, fight_id, start, end, data_type="Debuffs", hostility_type="Enemies"):
        et = (e.get("type") or "").lower()
        if et not in AURA_TYPES:
            continue

        tid = get_target_id(e)
        if not isinstance(tid, int) or tid not in tortos_set:
            continue

        ab_name, ab_id = get_ability(e)
        name = ab_name or "<?>"
        key = f"{name} (id={ab_id})"
        c[key] += 1

    return c.most_common(top_n)


def sanity_print_some_tortos_auras(
    headers: Dict[str, str],
    code: str,
    fight: Dict[str, Any],
    tortos_ids: List[int],
    limit: int = 12,
) -> None:
    """
    Prints a small sample of aura/debuff events targeting Tortos to prove
    we’re actually seeing the stream and what the event schema looks like.
    """
    fight_id = fight["id"]
    start = fight["startTime"]
    end = fight["endTime"]
    tortos_set = set(tortos_ids)

    shown = 0
    for e in iter_events(headers, code, fight_id, start, end, data_type="Debuffs", hostility_type="Enemies"):
        et = (e.get("type") or "").lower()
        if et not in AURA_TYPES:
            continue

        tid = get_target_id(e)
        if tid not in tortos_set:
            continue

        ab_name, ab_id = get_ability(e)
        ts = e.get("timestamp")
        print(f"  SANITY: {et:<18s} ts={ts}  ability={ab_name!r} id={ab_id}")
        shown += 1
        if shown >= limit:
            break

    if shown == 0:
        print("  SANITY: saw ZERO Debuffs aura events targeting Tortos in Enemies stream.")
        print("          That usually means the targetID you think is Tortos isn't the one in this fight,")
        print("          or the report is segmented such that this actor id isn't present for this fight.")


def get_ability_id(e: Dict[str, Any]) -> Optional[int]:
    """
    Robustly extract an ability/spell ID from a WCL event.
    Works even when ability.name is missing (common on Classic).
    """
    ab = e.get("ability")
    if isinstance(ab, dict):
        abid = ab.get("id")
        if isinstance(abid, int):
            return abid

    # Common Classic fallbacks
    for k in ("abilityGameID", "abilityID", "spellID", "guid"):
        v = e.get(k)
        if isinstance(v, int):
            return v

    return None


def main():
    token = get_token(CLIENT_ID, CLIENT_SECRET)
    headers = {"Authorization": f"Bearer {token}"}

    title, fights, actors = fetch_report(headers, REPORT_CODE)
    print(f"\nReport: {title} ({REPORT_CODE})\n")

    tortos_kills = [
        f for f in fights
        if isinstance(f, dict) and f.get("name") == TORTOS_FIGHT_NAME and f.get("kill") is True
    ]
    if not tortos_kills:
        print(f"No '{TORTOS_FIGHT_NAME}' kills found.")
        return

    tortos_hits = find_actor_ids_fuzzy(actors, ["tortos"])
    tortos_ids = [h["id"] for h in tortos_hits if isinstance(h.get("id"), int)]

    # print("Matched Tortos actor IDs (fuzzy):")
    # if tortos_hits:
    #     print("  " + ", ".join(f"{h.get('name')}#{h.get('id')}" for h in tortos_hits[:8]))
    # else:
    #     print("  (none)")
    # print()

    if not tortos_ids:
        print("Could not find any Tortos actor IDs from masterData.actors.")
        return

    print("Tortos — Shell Concussion stats (KILLS ONLY)")
    print("--------------------------------------------")
    # if SHELL_ABILITY_IDS is not None:
    #     print(f"(Matching by ability ID(s): {sorted(SHELL_ABILITY_IDS)})")
    # else:
    #     print(f"(Matching by ability ID: {SHELL_ABILITY_ID}  [{SHELL_NAME}])")

    for f in tortos_kills:
        dur = mmss_from_ms(f["endTime"] - f["startTime"])
        applies, uptime_ms, uptime_pct, matched, app_times = shell_stats_from_all_enemies(headers, REPORT_CODE, f, tortos_ids)

        print(f"\nKill duration: {dur}   (fight id {f.get('id')})")

        if matched == 0:
            print(f"  Found 0 matching aura events on Tortos (Enemies/Debuffs stream).")
            print("  SANITY sample of Debuffs aura events targeting Tortos:")
            sanity_print_some_tortos_auras(headers, REPORT_CODE, f, tortos_ids, limit=12)

            print("\n  Top aura names applied to Tortos (Enemies/Debuffs stream):")
            tops = discover_auras_on_tortos_enemies(headers, REPORT_CODE, f, tortos_ids, top_n=25)
            if not tops:
                print("    (none)")
            else:
                for name, cnt in tops:
                    print(f"    {name:<45s}  {cnt}")
            continue

        times_str = ", ".join(mmss_since_pull(t, f["startTime"]) for t in app_times)
        print(f"  Applications: {applies} ({times_str})")

        print(f"  Uptime      : {mmss_from_ms(uptime_ms)} ({uptime_pct:.1f}%)")
        # print(f"  Matched aura events: {matched}")


if __name__ == "__main__":
    main()
