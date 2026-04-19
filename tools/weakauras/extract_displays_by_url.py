import argparse
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


def extract_display_entry_ranges(input_path: str, url: str) -> list[tuple[int, int, str]]:
    displays_depth = None
    stack = []

    matched = set()  # aura names
    aura_ranges: dict[str, tuple[int, int | None]] = {}
    aura_order: list[str] = []

    re_keyed_open = re.compile(r'^\s*\["([^"]+)"\]\s*=\s*\{\s*$')
    url_needle = f'["url"] = "{url}"'

    with open(input_path, "r", encoding="utf-8", errors="replace") as f:
        for line_no, line in enumerate(f, start=1):
            stripped_for_depth = _strip_lua_strings(line)
            m = re_keyed_open.match(line)
            keyed_open_key = m.group(1) if m else None

            for ch in stripped_for_depth:
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
                            "is_aura": is_aura,
                            "aura_name": aura_name,
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

            if url_needle in line:
                for entry in reversed(stack):
                    if entry.get("is_aura"):
                        matched.add(entry["aura_name"])
                        break

    matched_ranges = []
    for name in aura_order:
        if name not in matched:
            continue
        start, end = aura_ranges.get(name, (None, None))
        if start is None or end is None:
            continue
        matched_ranges.append((start, end, name))

    matched_ranges.sort(key=lambda t: t[0])
    return matched_ranges


def write_extract_file(
    input_path: str,
    output_path: str,
    ranges: list[tuple[int, int, str]],
    url: str,
    inject_url: bool,
) -> None:
    # Second pass: buffer each entry and write it out.
    with open(input_path, "r", encoding="utf-8", errors="replace") as f_in:
        src_lines = f_in.readlines()

    with open(output_path, "w", encoding="utf-8", newline="\n") as f_out:
        f_out.write("-- Auto-extracted from 'weakauras'\n")
        f_out.write(f"-- Match: [\"url\"] = \"{url}\"\n\n")
        f_out.write("WeakAurasSaved_Extract = {\n")
        f_out.write("[\"displays\"] = {\n")

        for start, end, name in ranges:
            entry_lines = src_lines[start - 1 : end]
            has_url = any('["url"]' in ln for ln in entry_lines)

            if inject_url and not has_url:
                # Insert right after the opening line: ["Name"] = {
                # Preserve the file's style (no indentation in this export).
                entry_lines = entry_lines[:1] + [f'["url"] = "{url}",\n'] + entry_lines[1:]

            f_out.write(f"-- {name}\n")
            for ln in entry_lines:
                f_out.write(ln)
            f_out.write("\n")

        f_out.write("},\n")
        f_out.write("}\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="weakauras")
    ap.add_argument("--output", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--inject-url", action="store_true")
    args = ap.parse_args()

    ranges = extract_display_entry_ranges(args.input, args.url)
    if not ranges:
        raise SystemExit(f"No displays entries found containing url {args.url!r} in {args.input}")

    write_extract_file(args.input, args.output, ranges, args.url, inject_url=args.inject_url)
    print(f"Wrote {len(ranges)} aura entries to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
