import argparse
import json
import re


def _strip_lua_strings(line: str) -> str:
    # Removes Lua-style double-quoted strings so braces inside strings
    # don't affect brace depth tracking.
    out = []
    in_str = False
    escape = False
    for ch in line:
        if in_str:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_str = False
            continue
        else:
            if ch == '"':
                in_str = True
                continue
            out.append(ch)
    return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="List WeakAuras display entries that are groups (regionType=group/dynamicgroup)."
    )
    ap.add_argument("--input", default="weakauras2", help="WeakAuras SavedVariables file")
    ap.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )
    ap.add_argument(
        "--root-only",
        action="store_true",
        help="Only list groups with no parent",
    )
    args = ap.parse_args()

    # We parse only the top-level displays entries: ["Name"] = { ... }
    # and then scan within each entry for regionType.
    re_displays_open = re.compile(r'^\s*\["displays"\]\s*=\s*\{\s*$')
    re_keyed_open = re.compile(r'^\s*\["([^"]+)"\]\s*=\s*\{\s*$')
    re_region_type = re.compile(r'\["regionType"\]\s*=\s*"([^"]+)"')
    re_id = re.compile(r'\["id"\]\s*=\s*"([^"]+)"')
    re_parent = re.compile(r'\["parent"\]\s*=\s*"([^"]+)"')

    in_displays = False
    displays_depth = None
    stack = []

    cur = None
    # cur: dict(name:str, start_line:int, regionType:str|None, id:str|None, parent:str|None)
    groups = []

    def finalize_current(end_line: int) -> None:
        nonlocal cur
        if not cur:
            return
        rt = cur.get("regionType")
        if rt in ("group", "dynamicgroup"):
            groups.append(
                {
                    "name": cur["name"],
                    "regionType": rt,
                    "id": cur.get("id"),
                    "parent": cur.get("parent"),
                    "startLine": cur.get("start_line"),
                    "endLine": end_line,
                }
            )
        cur = None

    with open(args.input, "r", encoding="utf-8", errors="replace") as f:
        for line_no, line in enumerate(f, start=1):
            if not in_displays:
                if re_displays_open.match(line):
                    in_displays = True
                    displays_depth = len(stack) + 1
                # Maintain stack depth even before displays in case file is nested oddly.
            
            stripped = _strip_lua_strings(line)
            m_key = re_keyed_open.match(line)
            keyed_open_key = m_key.group(1) if m_key else None

            # If we're at top-level inside displays and see a new entry open, start capturing.
            # Note: at the moment we see '{', stack depth is depth_before.
            for ch in stripped:
                if ch == "{":
                    depth_before = len(stack)

                    is_displays_open = keyed_open_key == "displays" and line.rstrip().endswith("{")
                    if is_displays_open and not in_displays:
                        in_displays = True
                        displays_depth = depth_before + 1

                    is_top_display_entry = (
                        in_displays
                        and displays_depth is not None
                        and keyed_open_key is not None
                        and depth_before == displays_depth
                        and line.rstrip().endswith("{")
                    )

                    if is_top_display_entry:
                        # Close previous entry if any (shouldn't happen unless malformed).
                        finalize_current(line_no - 1)
                        cur = {
                            "name": keyed_open_key,
                            "start_line": line_no,
                            "regionType": None,
                            "id": None,
                            "parent": None,
                        }

                    stack.append(
                        {
                            "key": keyed_open_key,
                            "is_display_entry": is_top_display_entry,
                        }
                    )
                elif ch == "}":
                    if stack:
                        popped = stack.pop()
                        if popped.get("is_display_entry"):
                            finalize_current(line_no)

            # While inside a current entry, scan for fields.
            if cur is not None:
                if cur.get("regionType") is None:
                    m = re_region_type.search(line)
                    if m:
                        cur["regionType"] = m.group(1)
                if cur.get("id") is None:
                    m = re_id.search(line)
                    if m:
                        cur["id"] = m.group(1)
                if cur.get("parent") is None:
                    m = re_parent.search(line)
                    if m:
                        cur["parent"] = m.group(1)

    # In case file ends mid-entry.
    finalize_current(line_no if "line_no" in locals() else 0)

    # Stable sort by parent then name.
    groups.sort(key=lambda g: ((g.get("parent") or ""), g["name"]))

    if args.root_only:
        groups = [g for g in groups if not g.get("parent")]

    if args.format == "json":
        print(json.dumps(groups, indent=2))
    else:
        for g in groups:
            parent = g.get("parent")
            parent_part = f" parent={parent!r}" if parent else ""
            print(f"{g['regionType']}: {g['name']}{parent_part}")

        print(f"\nTotal groups: {len(groups)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
