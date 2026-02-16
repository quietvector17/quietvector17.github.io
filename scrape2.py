import os
import requests

REPORT_CODE = "vFYGaXZgdTk9P6tz"

CLIENT_ID = os.getenv("WCL_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("WCL_CLIENT_SECRET", "")

if not CLIENT_ID or not CLIENT_SECRET:
    raise SystemExit("Set WCL_CLIENT_ID and WCL_CLIENT_SECRET environment variables first.")

def get_token():
    r = requests.post(
        "https://classic.warcraftlogs.com/oauth/token",
        data={"grant_type": "client_credentials"},
        auth=(CLIENT_ID, CLIENT_SECRET),
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]

def mmss(ms: int) -> str:
    s = ms // 1000
    m, s = divmod(s, 60)
    return f"{m}:{s:02d}"

token = get_token()
headers = {"Authorization": f"Bearer {token}"}

# -------------------------
# Fetch fights
# -------------------------
fights_query = """
query($code: String!) {
  reportData {
    report(code: $code) {
      title
      fights {
        id
        name
        kill
        startTime
        endTime
      }
    }
  }
}
"""


# -------------------------
# Fetch player actor IDs (used to classify death events)
# -------------------------
players_query = """
query($code: String!) {
  reportData {
    report(code: $code) {
      masterData {
        actors {
          id
          type
          subType
          name
        }
      }
    }
  }
}
"""

resp2 = requests.post(
    "https://classic.warcraftlogs.com/api/v2/client",
    json={"query": players_query, "variables": {"code": REPORT_CODE}},
    headers=headers,
    timeout=30,
)
resp2.raise_for_status()

actors = resp2.json()["data"]["reportData"]["report"]["masterData"]["actors"]

PLAYER_IDS = set()
for a in actors:
    if not isinstance(a, dict):
        continue
    t = (a.get("type") or "").lower()
    st = (a.get("subType") or "").lower()
    # Classic often uses type="Player", sometimes subtype
    if t == "player" or st == "player":
        PLAYER_IDS.add(a["id"])


resp = requests.post(
    "https://classic.warcraftlogs.com/api/v2/client",
    json={"query": fights_query, "variables": {"code": REPORT_CODE}},
    headers=headers,
    timeout=30,
)
resp.raise_for_status()
report = resp.json()["data"]["reportData"]["report"]

print(f"\nReport: {report['title']} ({REPORT_CODE})\n")

fights = report["fights"]




def mmss_from_ms(ms: int) -> str:
    s = int(ms) // 1000
    m, s = divmod(s, 60)
    return f"{m}:{s:02d}"


LUST_CAST_NAMES = {
    "Heroism",
    "Time Warp",
    "Bloodlust",
    "Ancient Hysteria",
    "Drums of Rage",
    "Drums of Fury",
    "Drums of War",
}

# “You can’t benefit from lust again” debuffs (very reliable signal)
LUST_LOCKOUT_DEBUFFS = {
    "Sated",
    "Exhaustion",
    "Temporal Displacement",
    "Insanity",
}



def _scan_events_first_match(fight_id: int, data_type: str, allowed_names: set, allowed_event_types: set):
    query = f"""
    query($code: String!, $fightID: Int!, $startTime: Float) {{
      reportData {{
        report(code: $code) {{
          events(
            dataType: {data_type}
            fightIDs: [$fightID]
            startTime: $startTime
          ) {{
            data
            nextPageTimestamp
          }}
        }}
      }}
    }}
    """

    start = None
    best = None  # (timestamp, spell_name, source_name)

    while True:
        r = requests.post(
            "https://classic.warcraftlogs.com/api/v2/client",
            json={"query": query, "variables": {"code": REPORT_CODE, "fightID": fight_id, "startTime": start}},
            headers=headers,
            timeout=30,
        )
        r.raise_for_status()

        ev = r.json()["data"]["reportData"]["report"]["events"]
        data = ev.get("data") or []

        for e in data:
            if not isinstance(e, dict):
                continue

            et = (e.get("type") or "").lower()
            if allowed_event_types and et not in allowed_event_types:
                continue

            ability = e.get("ability")
            spell = ability.get("name") if isinstance(ability, dict) else (ability if isinstance(ability, str) else None)
            if spell not in allowed_names:
                continue

            ts = e.get("timestamp")
            if not isinstance(ts, int):
                continue

            src = e.get("source")
            src_name = src.get("name") if isinstance(src, dict) else None

            cand = (ts, spell, src_name)
            if best is None or cand[0] < best[0]:
                best = cand

        nxt = ev.get("nextPageTimestamp")
        if not nxt:
            break
        start = nxt

    return best

LUST_CAST_IDS = {
  32182,  # Heroism
  2825,   # Bloodlust
  80353,  # Time Warp
  90355,  # Ancient Hysteria (hunter pet)
  146555, # Drums of Rage
}

events_casts_query = """
query($code: String!, $fightID: Int!, $start: Float!, $end: Float!) {
  reportData {
    report(code: $code) {
      events(fightIDs: [$fightID], startTime: $start, endTime: $end, dataType: Casts) {
        data
        nextPageTimestamp
      }
    }
  }
}
"""

HEROISM_QUERY = """
query($code: String!, $fightID: Int!) {
  reportData {
    report(code: $code) {
      events(
        fightIDs: [$fightID]
        dataType: Casts
        abilityID: 32182
      ) {
        data
      }
    }
  }
}
"""

def get_heroism_cast(fight_id: int):
    r = requests.post(
        "https://classic.warcraftlogs.com/api/v2/client",
        json={
            "query": HEROISM_QUERY,
            "variables": {
                "code": REPORT_CODE,
                "fightID": fight_id,
            }
        },
        headers=headers,
        timeout=30,
    )
    r.raise_for_status()

    events = (
        r.json()
        ["data"]["reportData"]["report"]["events"]["data"]
    )

    if not events:
        return None

    e = events[0]  # earliest Heroism cast
    return {
        "timestamp": e["timestamp"],
        "sourceID": e.get("sourceID"),
        "abilityGameID": e.get("abilityGameID"),
    }

# -------------------------
# Helper: deaths in a fight
# -------------------------
def get_deaths(fight_id: int) -> int:
    """
    Count PLAYER deaths in the successful pull using Death events.
    We classify players by mapping targetID -> report masterData actors.
    """
    deaths_query = """
    query($code: String!, $fightID: Int!, $startTime: Float) {
      reportData {
        report(code: $code) {
          events(
            dataType: Deaths
            fightIDs: [$fightID]
            startTime: $startTime
          ) {
            data
            nextPageTimestamp
          }
        }
      }
    }
    """

    start = None
    count = 0

    while True:
        r = requests.post(
            "https://classic.warcraftlogs.com/api/v2/client",
            json={"query": deaths_query, "variables": {"code": REPORT_CODE, "fightID": fight_id, "startTime": start}},
            headers=headers,
            timeout=30,
        )
        r.raise_for_status()

        ev = r.json()["data"]["reportData"]["report"]["events"]
        data = ev.get("data") or []

        for e in data:
            if not isinstance(e, dict):
                continue

            # Most reliable field is targetID (int)
            tid = e.get("targetID")

            # Fallbacks if WCL returns nested target object
            if tid is None:
                target = e.get("target")
                if isinstance(target, dict):
                    tid = target.get("id")
                elif isinstance(target, int):
                    tid = target

            if isinstance(tid, int) and tid in PLAYER_IDS:
                count += 1

        nxt = ev.get("nextPageTimestamp")
        if not nxt:
            break
        start = nxt

    return count

# -------------------------
# Build kill list
# -------------------------
kills = []

for i, f in enumerate(fights):
    if not f["kill"]:
        continue

    # Count wipes on this boss before this kill
    wipes = sum(
        1
        for prev in fights[:i]
        if prev["name"] == f["name"] and not prev["kill"]
    )
    if f["name"] == "Ji-Kun":
        wipes = max(0, wipes - 1)

    deaths = get_deaths(f["id"])
    duration = f["endTime"] - f["startTime"]

    hero = get_heroism_cast(f["id"])

    if hero:
        t_ms = hero["timestamp"] - f["startTime"]
        lust_str = t_ms
    else:
        lust_str = "No lust"

    kills.append({
        "id": f["id"],
        "name": f["name"],
        "duration": duration,
        "wipes": wipes,
        "deaths": deaths,
        "lust_t_ms": lust_str,
    })

    

# Sort by fight id (chronological)
kills.sort(key=lambda x: x["id"])

# -------------------------
# Output
# -------------------------
total_wipes = 0

for k in kills:

    lust_str = "No lust"
    if k["lust_t_ms"] is not None:
        lust_str = f"{mmss_from_ms(k['lust_t_ms'])}"
    total_wipes += k['wipes']
    print(
        f"{k['name']:30s} "
        f"{mmss(k['duration'])}  "
        f"Wipes: {k['wipes']:2d}  "
        f"Deaths (kill): {k['deaths']:2d}  "
        f"Lust: {lust_str:25s} "
        f"(fight id {k['id']})"
    )

print(f"\nTotal kills: {len(kills)} - Total Wipes: {total_wipes}")

