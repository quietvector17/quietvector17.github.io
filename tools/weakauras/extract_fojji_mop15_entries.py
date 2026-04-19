import re


URL = "https://wago.io/FojjiRogueUI-MoP/15"
INPUT_PATH = "weakauras"
OUTPUT_PATH = "fojji_mop15_displays_extract.lua"


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
    displays_depth = None
    stack = []
    # Each stack entry: dict(depth_before:int, key:str|None, is_displays:bool, is_aura:bool, aura_name:str|None, start_line:int)

    # Track aura entries that contain the URL.
    matched = set()  # aura names
    aura_ranges = {}  # aura name -> (start_line, end_line)
    aura_order = []  # aura names in file order

    re_keyed_open = re.compile(r'^\s*\["([^"]+)"\]\s*=\s*\{\s*$')
    url_needle = f'["url"] = "{URL}"'

    with open(INPUT_PATH, "r", encoding="utf-8", errors="replace") as f:
        for line_no, line in enumerate(f, start=1):
            stripped_for_depth = _strip_lua_strings(line)
            # Detect a keyed table open on this line (common pattern in this file).
            m = re_keyed_open.match(line)
            keyed_open_key = m.group(1) if m else None

            i = 0
            while i < len(stripped_for_depth):
                ch = stripped_for_depth[i]
                if ch == "{":
                    depth_before = len(stack)
                    is_displays = keyed_open_key == "displays" and line.rstrip().endswith("{")
                    if is_displays and displays_depth is None:
                        displays_depth = depth_before + 1

                    is_aura = False
                    aura_name = None
                    if (
                        displays_depth is not None
                        and keyed_open_key is not None
                        and depth_before == displays_depth
                        and line.rstrip().endswith("{")
                    ):
                        is_aura = True
                        aura_name = keyed_open_key
                        if aura_name not in aura_ranges:
                            aura_ranges[aura_name] = (line_no, None)
                            aura_order.append(aura_name)

                    stack.append(
                        {
                            "depth_before": depth_before,
                            "key": keyed_open_key,
                            "is_displays": is_displays,
                            "is_aura": is_aura,
                            "aura_name": aura_name,
                            "start_line": line_no,
                        }
                    )
                elif ch == "}":
                    if stack:
                        popped = stack.pop()
                        if popped.get("is_aura"):
                            name = popped.get("aura_name")
                            if name in matched:
                                start, end = aura_ranges.get(name, (None, None))
                                if end is None:
                                    aura_ranges[name] = (start, line_no)
                i += 1

            if url_needle in line:
                # Find the currently-open aura table (nearest open aura on the stack).
                for entry in reversed(stack):
                    if entry.get("is_aura"):
                        matched.add(entry["aura_name"])
                        break

    # Finalize: keep only matched aura entries with closed ranges.
    matched_ranges = []
    for name in aura_order:
        if name not in matched:
            continue
        start, end = aura_ranges.get(name, (None, None))
        if start is None or end is None:
            continue
        matched_ranges.append((start, end, name))

    matched_ranges.sort(key=lambda t: t[0])
    if not matched_ranges:
        raise SystemExit(f"No aura entries found containing {URL!r}.")

    # Second pass: write extracted aura tables.
    with open(INPUT_PATH, "r", encoding="utf-8", errors="replace") as f_in, open(
        OUTPUT_PATH, "w", encoding="utf-8", newline="\n"
    ) as f_out:
        f_out.write("-- Auto-extracted from 'weakauras'\n")
        f_out.write(f"-- Match: [\"url\"] = \"{URL}\"\n\n")
        f_out.write("WeakAurasSaved_Extract = {\n")
        f_out.write("[\"displays\"] = {\n")

        # Iterate file once and emit requested ranges.
        next_idx = 0
        current = matched_ranges[next_idx]
        start, end, name = current

        for line_no, line in enumerate(f_in, start=1):
            if line_no < start:
                continue

            if line_no == start:
                f_out.write(f"-- {name}\n")

            if start <= line_no <= end:
                f_out.write(line)

            if line_no == end:
                f_out.write("\n")
                next_idx += 1
                if next_idx >= len(matched_ranges):
                    break
                start, end, name = matched_ranges[next_idx]

        f_out.write("},\n")
        f_out.write("}\n")

    print(f"Wrote {len(matched_ranges)} aura entries to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
