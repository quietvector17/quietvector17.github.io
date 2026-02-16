import os
import requests

REPORT_CODE = "vFYGaXZgdTk9P6tz"
CLIENT_ID = os.getenv("WCL_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("WCL_CLIENT_SECRET", "")

API_URL = "https://classic.warcraftlogs.com/api/v2/client"
TOKEN_URL = "https://classic.warcraftlogs.com/oauth/token"


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


def mmss_from_ms(ms: int) -> str:
    s = ms // 1000
    m, s = divmod(s, 60)
    return f"{m}:{s:02d}"


def gql(headers: dict, query: str, variables: dict) -> dict:
    r = requests.post(API_URL, json={"query": query, "variables": variables}, headers=headers, timeout=30)
    r.raise_for_status()
    payload = r.json()
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload["data"]


def fetch_report_fights_and_player_ids(headers: dict, code: str):
    query = """
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
          masterData {
            actors {
              id
              type
              subType
            }
          }
        }
      }
    }
    """
    data = gql(headers, query, {"code": code})
    report = data["reportData"]["report"]

    player_ids = {
        a["id"]
        for a in report["masterData"]["actors"]
        if isinstance(a, dict)
        and ((a.get("type") or "").lower() == "player"
             or (a.get("subType") or "").lower() == "player")
    }

    return report["title"], report["fights"], player_ids


def get_deaths(headers: dict, code: str, fight_id: int, player_ids: set[int]) -> int:
    query = """
    query($code: String!, $fightID: Int!, $startTime: Float) {
      reportData {
        report(code: $code) {
          events(dataType: Deaths, fightIDs: [$fightID], startTime: $startTime) {
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
        data = gql(headers, query, {"code": code, "fightID": fight_id, "startTime": start})
        ev = data["reportData"]["report"]["events"]

        for e in ev.get("data") or []:
            tid = e.get("targetID")
            if tid is None:
                target = e.get("target")
                tid = target.get("id") if isinstance(target, dict) else target
            if isinstance(tid, int) and tid in player_ids:
                count += 1

        start = ev.get("nextPageTimestamp")
        if not start:
            break

    return count


def get_heroism_timestamp(headers: dict, code: str, fight_id: int):
    query = """
    query($code: String!, $fightID: Int!) {
      reportData {
        report(code: $code) {
          events(fightIDs: [$fightID], dataType: Casts, abilityID: 32182) {
            data
          }
        }
      }
    }
    """
    data = gql(headers, query, {"code": code, "fightID": fight_id})
    events = [
        e for e in data["reportData"]["report"]["events"].get("data") or []
        if isinstance(e, dict) and isinstance(e.get("timestamp"), int)
    ]
    if not events:
        return None
    return min(e["timestamp"] for e in events)


def main():
    token = get_token(CLIENT_ID, CLIENT_SECRET)
    headers = {"Authorization": f"Bearer {token}"}

    title, fights, player_ids = fetch_report_fights_and_player_ids(headers, REPORT_CODE)
    print(f"\nReport: {title} ({REPORT_CODE})\n")

    kills = []
    total_wipes = 0

    for i, f in enumerate(fights):
        if not f["kill"]:
            continue

        boss = f["name"]
        fight_id = f["id"]
        duration_ms = f["endTime"] - f["startTime"]

        wipes = sum(1 for prev in fights[:i] if prev["name"] == boss and not prev["kill"])
        if boss == "Ji-Kun":
            wipes = max(0, wipes - 1)

        deaths = get_deaths(headers, REPORT_CODE, fight_id, player_ids)

        hero_ts = get_heroism_timestamp(headers, REPORT_CODE, fight_id)
        lust_at_ms = hero_ts - f["startTime"] if hero_ts else None

        total_wipes += wipes
        kills.append({
            "boss": boss,
            "fight_id": fight_id,
            "duration_ms": duration_ms,
            "wipes": wipes,
            "deaths": deaths,
            "lust_at_ms": lust_at_ms,
        })

    kills.sort(key=lambda x: x["fight_id"])

    boss_w = max(12, min(32, max(len(k["boss"]) for k in kills)))
    print(
        f"{'Boss':{boss_w}s}  {'Dur':>6s}  {'Wipes':>5s}  "
        f"{'Deaths':>6s}  {'Lust @':>6s}  {'FightID':>6s}"
    )
    print("-" * (boss_w + 35))

    for k in kills:
        lust_at = mmss_from_ms(k["lust_at_ms"]) if isinstance(k["lust_at_ms"], int) else "-"
        print(
            f"{k['boss']:{boss_w}s}  "
            f"{mmss_from_ms(k['duration_ms']):>6s}  "
            f"{k['wipes']:>5d}  "
            f"{k['deaths']:>6d}  "
            f"{lust_at:>6s}  "
            f"{k['fight_id']:>6d}"
        )

    print(f"\nTotal kills: {len(kills)} | Total wipes (before kills): {total_wipes}\n")


if __name__ == "__main__":
    main()
