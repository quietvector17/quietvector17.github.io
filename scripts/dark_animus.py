import os
import argparse
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import requests

# https://classic.warcraftlogs.com/reports/TRJmy876bBCnFdwt
REPORT_CODE = "wXz2PqmhMcBk89Rt"
CLIENT_ID = os.getenv("WCL_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("WCL_CLIENT_SECRET", "")

API_URL = "https://classic.warcraftlogs.com/api/v2/client"
TOKEN_URL = "https://classic.warcraftlogs.com/oauth/token"
REPORT_BASE_URL = "https://classic.warcraftlogs.com/reports"

DEFAULT_FIGHT_NAME = "Dark Animus"


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


def mmss_from_ms(ms: int) -> str:
    s = ms // 1000
    m, s = divmod(s, 60)
    return f"{m}:{s:02d}"


def _norm(s: Any) -> str:
    return str(s or "").lower().replace("\u2019", "'")


def iter_events(
    headers: Dict[str, str],
    code: str,
    fight_id: int,
    fight_start: int,
    fight_end: int,
    data_type: str,
) -> Iterable[Dict[str, Any]]:
    """Correct paging: startTime is ONLY the paging cursor; endTime is fixed."""
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
    return rep["title"], (rep.get("fights") or []), (rep.get("masterData", {}).get("actors") or [])


def build_actor_by_id(actors: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for a in actors or []:
        if isinstance(a, dict) and isinstance(a.get("id"), int):
            out[a["id"]] = a
    return out


def build_player_id_set(actors: List[Dict[str, Any]]) -> Set[int]:
    out: Set[int] = set()
    for a in actors or []:
        if not isinstance(a, dict) or not isinstance(a.get("id"), int):
            continue
        t = _norm(a.get("type"))
        st = _norm(a.get("subType"))
        if t == "player" or st == "player":
            out.add(a["id"])
    return out


def get_target_id(e: Dict[str, Any]) -> Optional[int]:
    tid = e.get("targetID")
    if isinstance(tid, int):
        return tid
    target = e.get("target")
    if isinstance(target, dict) and isinstance(target.get("id"), int):
        return target["id"]
    if isinstance(target, int):
        return target
    return None


def get_source_id(e: Dict[str, Any]) -> Optional[int]:
    sid = e.get("sourceID")
    if isinstance(sid, int):
        return sid
    src = e.get("source")
    if isinstance(src, dict) and isinstance(src.get("id"), int):
        return src["id"]
    if isinstance(src, int):
        return src
    return None


def get_instance(e: Dict[str, Any], which: str) -> Optional[int]:
    # WCL often uses sourceInstance/targetInstance to distinguish identical adds.
    key = f"{which}Instance"
    v = e.get(key)
    if isinstance(v, int) and v > 0:
        return v
    obj = e.get(which)
    if isinstance(obj, dict):
        inst = obj.get("instance")
        if isinstance(inst, int) and inst > 0:
            return inst
    return None


def get_actor_name(actor_by_id: Dict[int, Dict[str, Any]], actor_id: int, e: Dict[str, Any], which: str) -> Optional[str]:
    a = actor_by_id.get(actor_id)
    if isinstance(a, dict) and isinstance(a.get("name"), str):
        return a["name"]
    obj = e.get(which)
    if isinstance(obj, dict) and isinstance(obj.get("name"), str):
        return obj["name"]
    return None


def is_anima_golem_name(name: str, strict: bool) -> bool:
    n = _norm(name)
    if strict:
        return n == "anima golem"
    # Includes "Large Anima Golem", "Massive Anima Golem", etc.
    return ("anima" in n) and ("golem" in n)


def _count_golem_targets_damaged_by_players(
    headers: Dict[str, str],
    code: str,
    fight: Dict[str, Any],
    player_ids: Set[int],
    actor_by_id: Dict[int, Dict[str, Any]],
    strict: bool,
) -> Tuple[Set[Tuple[int, int]], Dict[str, Set[Tuple[int, int]]], str]:
    fight_id = fight["id"]
    start = fight["startTime"]
    end = fight["endTime"]

    golem_entities: Set[Tuple[int, int]] = set()
    golems_by_name: Dict[str, Set[Tuple[int, int]]] = {}

    def ingest(data_type: str) -> Tuple[int, int]:
        """Returns (damage_events_seen, golem_entities_added)."""
        dmg_seen = 0
        before = len(golem_entities)

        for e in iter_events(headers, code, fight_id, start, end, data_type):
            if _norm(e.get("type")) != "damage":
                continue

            sid = get_source_id(e)
            if sid is None or sid not in player_ids:
                continue

            tid = get_target_id(e)
            if tid is None:
                continue

            amt = e.get("amount")
            absorbed = e.get("absorbed")
            if not isinstance(amt, int):
                continue
            if not isinstance(absorbed, int):
                absorbed = 0
            if amt + absorbed <= 0:
                continue

            dmg_seen += 1

            tgt_name = get_actor_name(actor_by_id, tid, e, "target")
            if not isinstance(tgt_name, str) or not tgt_name:
                continue

            if not is_anima_golem_name(tgt_name, strict=strict):
                continue

            inst = get_instance(e, "target")
            ent = (tid, inst if isinstance(inst, int) else 0)
            golem_entities.add(ent)
            golems_by_name.setdefault(tgt_name, set()).add(ent)

        return dmg_seen, len(golem_entities) - before

    # Prefer DamageDone (used elsewhere in this repo). Fall back to All if needed.
    dmg_seen, _ = ingest("DamageDone")
    stream_used = "DamageDone"
    if dmg_seen == 0:
        ingest("All")
        stream_used = "All"

    return golem_entities, golems_by_name, stream_used


def count_anima_golems_that_damage_players(
    headers: Dict[str, str],
    code: str,
    fight: Dict[str, Any],
    player_ids: Set[int],
    actor_by_id: Dict[int, Dict[str, Any]],
    strict: bool,
) -> Tuple[Set[Tuple[int, int]], Dict[str, Set[Tuple[int, int]]], str]:
    """Counts unique Anima Golem entities that deal damage to players.

    Important: this is based on *damage taken by players* (WCL dataType: DamageTaken).
    We count unique (sourceID, sourceInstance) where available.
    """
    fight_id = fight["id"]
    start = fight["startTime"]
    end = fight["endTime"]

    entities: Set[Tuple[int, int]] = set()
    by_name: Dict[str, Set[Tuple[int, int]]] = {}

    for e in iter_events(headers, code, fight_id, start, end, "DamageTaken"):
        if _norm(e.get("type")) != "damage":
            continue

        amt = e.get("amount")
        absorbed = e.get("absorbed")
        if not isinstance(amt, int):
            continue
        if not isinstance(absorbed, int):
            absorbed = 0
        if amt + absorbed <= 0:
            continue

        tid = get_target_id(e)
        if tid is None or tid not in player_ids:
            continue

        sid = get_source_id(e)
        if sid is None:
            continue

        src_name = get_actor_name(actor_by_id, sid, e, "source")
        if not isinstance(src_name, str) or not src_name:
            continue

        if not is_anima_golem_name(src_name, strict=strict):
            continue

        inst = get_instance(e, "source")
        ent = (sid, inst if isinstance(inst, int) else 0)
        entities.add(ent)
        by_name.setdefault(src_name, set()).add(ent)

    return entities, by_name, "DamageTaken"


def count_anima_golems_killed(
    headers: Dict[str, str],
    code: str,
    fight: Dict[str, Any],
    actor_by_id: Dict[int, Dict[str, Any]],
    strict: bool,
) -> Tuple[Set[Tuple[int, int]], Dict[str, Set[Tuple[int, int]]], str]:
    """Counts unique Anima Golem entities that die during the fight.

    We look for type in {death,destroy} in dataType: All.
    We count unique (targetID, targetInstance) where available.
    """
    fight_id = fight["id"]
    start = fight["startTime"]
    end = fight["endTime"]

    entities: Set[Tuple[int, int]] = set()
    by_name: Dict[str, Set[Tuple[int, int]]] = {}

    for e in iter_events(headers, code, fight_id, start, end, "All"):
        et = _norm(e.get("type"))
        if et not in {"death", "destroy"}:
            continue

        tid = get_target_id(e)
        if tid is None:
            continue

        tgt_name = get_actor_name(actor_by_id, tid, e, "target")
        if not isinstance(tgt_name, str) or not tgt_name:
            continue

        if not is_anima_golem_name(tgt_name, strict=strict):
            continue

        inst = get_instance(e, "target")
        ent = (tid, inst if isinstance(inst, int) else 0)
        entities.add(ent)
        by_name.setdefault(tgt_name, set()).add(ent)

    return entities, by_name, "All"


def count_anima_golems_active(
    headers: Dict[str, str],
    code: str,
    fight: Dict[str, Any],
    actor_by_id: Dict[int, Dict[str, Any]],
    strict: bool,
) -> Tuple[Set[Tuple[int, int]], Dict[str, Set[Tuple[int, int]]], str]:
    """Counts unique Anima Golem entities that are "active".

    Heuristic: a golem is active if it shows up as the source of any Casts or
    any outgoing DamageDone event (even if it never damages a player).

    We count unique (sourceID, sourceInstance) where available.
    """
    fight_id = fight["id"]
    start = fight["startTime"]
    end = fight["endTime"]

    entities: Set[Tuple[int, int]] = set()
    by_name: Dict[str, Set[Tuple[int, int]]] = {}

    def add_from_events(data_type: str, accepted_types: Set[str]) -> int:
        added = 0
        before = len(entities)
        for e in iter_events(headers, code, fight_id, start, end, data_type):
            et = _norm(e.get("type"))
            if et not in accepted_types:
                continue

            sid = get_source_id(e)
            if sid is None:
                continue

            src_name = get_actor_name(actor_by_id, sid, e, "source")
            if not isinstance(src_name, str) or not src_name:
                continue

            if not is_anima_golem_name(src_name, strict=strict):
                continue

            inst = get_instance(e, "source")
            ent = (sid, inst if isinstance(inst, int) else 0)
            entities.add(ent)
            by_name.setdefault(src_name, set()).add(ent)

        added = len(entities) - before
        return added

    # Prefer narrower streams first (much faster than All).
    add_from_events("Casts", {"cast", "begincast", "startcast"})
    add_from_events("DamageDone", {"damage"})

    stream_used = "Casts+DamageDone"

    # Fallback if nothing matched (some logs are weird): scan All.
    if not entities:
        add_from_events(
            "All",
            {
                "damage",
                "cast",
                "begincast",
                "startcast",
                "applybuff",
                "applybuffstack",
                "refreshbuff",
                "refreshbuffstack",
                "removebuff",
                "applydebuff",
                "applydebuffstack",
                "refreshdebuff",
                "refreshdebuffstack",
                "removedebuff",
            },
        )
        stream_used = "All"

    return entities, by_name, stream_used


def pick_pulls(fights: List[Dict[str, Any]], fight_name: str, kills_only: bool) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for f in fights or []:
        if not isinstance(f, dict):
            continue
        if f.get("name") != fight_name:
            continue
        if kills_only and f.get("kill") is not True:
            continue
        if not isinstance(f.get("id"), int):
            continue
        if not isinstance(f.get("startTime"), int) or not isinstance(f.get("endTime"), int):
            continue
        out.append(f)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Dark Animus analysis: counts unique Anima Golem entities that deal damage to players in each pull. "
            "Uses WCL v2 GraphQL (classic.warcraftlogs.com)."
        )
    )
    ap.add_argument("code", nargs="?", help="Warcraft Logs report code (e.g. vFYGaXZgdTk9P6tz)")
    ap.add_argument("--code", dest="code2", help="Same as positional code")
    ap.add_argument("--fight", default=DEFAULT_FIGHT_NAME, help=f"Fight name as it appears in WCL (default: {DEFAULT_FIGHT_NAME})")
    ap.add_argument("--fight-id", type=int, default=0, help="Only analyze this fight ID within the report")
    ap.add_argument("--strict", action="store_true", help="Only match exact actor name 'Anima Golem' (exclude Large/Massive)")
    ap.add_argument("--limit", type=int, default=0, help="Limit number of pulls printed (0 = no limit)")
    args = ap.parse_args()

    report_code = (args.code or args.code2 or REPORT_CODE).strip()
    if not report_code:
        raise SystemExit("Missing report code.")

    token = get_token(CLIENT_ID, CLIENT_SECRET)
    headers = {"Authorization": f"Bearer {token}"}

    title, fights, actors = fetch_report(headers, report_code)
    actor_by_id = build_actor_by_id(actors)
    player_ids = build_player_id_set(actors)

    pulls = pick_pulls(fights, args.fight, kills_only=True)
    if args.fight_id and args.fight_id > 0:
        pulls = [f for f in pulls if f.get("id") == args.fight_id]
    if not pulls:
        suffix = f" and fight id {args.fight_id}" if args.fight_id and args.fight_id > 0 else ""
        print(f"No kills found for fight name: {args.fight!r}{suffix}")
        return

    print(f"Report: {title} ({report_code})")
    print(f"Fight: {args.fight} | Kills: {len(pulls)} | Match: {'strict' if args.strict else 'contains(anima & golem)'}")
    print("")
    print("REPORT\tDURATION\tGOLEMS_DMG\tGOLEM_DEATHS\tSTRAT_10M")

    if args.limit and args.limit > 0:
        pulls = pulls[: args.limit]

    for f in pulls:
        # fight_id is only used to query events; we don't print it.
        fight_id = f["id"]
        dur = mmss_from_ms(int(f["endTime"] - f["startTime"]))

        report_url = f"{REPORT_BASE_URL}/{report_code}"
        golem_entities, _by_name, _stream_used = count_anima_golems_that_damage_players(
            headers,
            report_code,
            f,
            player_ids,
            actor_by_id,
            strict=bool(args.strict),
        )

        deaths_count: Optional[int] = None
        if len(golem_entities) <= 12:
            killed_entities, _k_by_name, _ = count_anima_golems_killed(
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


if __name__ == "__main__":
    main()
