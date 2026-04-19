import argparse
import re
import shutil


def _strip_lua_strings(line: str) -> str:
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


def _find_table_block(lines: list[str], start_pred) -> tuple[int, int]:
    start_idx = None
    for i, ln in enumerate(lines):
        if start_pred(ln):
            start_idx = i
            break
    if start_idx is None:
        raise SystemExit("Couldn't find table start")

    depth = 0
    found_open = False
    for j in range(start_idx, len(lines)):
        stripped = _strip_lua_strings(lines[j])
        for ch in stripped:
            if ch == "{":
                depth += 1
                found_open = True
            elif ch == "}":
                depth -= 1
        if found_open and depth == 0:
            return start_idx, j

    raise SystemExit("Couldn't find matching table end")


def _extract_displays_inner(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    start_idx, end_idx = _find_table_block(
        lines,
        lambda ln: ln.strip().startswith('["displays"]') and "{" in ln and "=" in ln,
    )

    # Return inner lines between the opening line and the closing brace line.
    return lines[start_idx + 1 : end_idx]


def _split_top_level_entries(displays_inner: list[str]) -> list[tuple[str, list[str]]]:
    # Split the content inside displays into top-level entries.
    re_keyed_open = re.compile(r'^\s*\["([^"]+)"\]\s*=\s*\{\s*$')

    entries: list[tuple[str, list[str]]] = []
    cur_name = None
    cur_lines: list[str] = []
    depth = 0
    in_entry = False

    for ln in displays_inner:
        m = re_keyed_open.match(ln)
        if not in_entry and m and depth == 0:
            in_entry = True
            cur_name = m.group(1)
            cur_lines = [ln]
        elif in_entry:
            cur_lines.append(ln)

        stripped = _strip_lua_strings(ln)
        for ch in stripped:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1

        # When an entry closes, we're back at depth 0.
        if in_entry and depth == 0:
            entries.append((cur_name, cur_lines))
            in_entry = False
            cur_name = None
            cur_lines = []

    return entries


def _existing_top_level_names(displays_inner: list[str]) -> set[str]:
    return {name for name, _ in _split_top_level_entries(displays_inner)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default="weakauras2")
    ap.add_argument("--source", required=True, help="lua file containing ['displays'] entries")
    ap.add_argument("--backup", default=None)
    args = ap.parse_args()

    with open(args.dest, "r", encoding="utf-8", errors="replace") as f:
        dest_lines = f.readlines()

    displays_start, displays_end = _find_table_block(
        dest_lines,
        lambda ln: ln.strip() == '["displays"] = {',
    )
    dest_inner = dest_lines[displays_start + 1 : displays_end]
    dest_names = _existing_top_level_names(dest_inner)

    src_inner = _extract_displays_inner(args.source)
    src_entries = _split_top_level_entries(src_inner)

    to_add = []
    added = 0
    for name, lines in src_entries:
        if name in dest_names:
            continue
        to_add.extend(lines)
        if not lines[-1].endswith("\n"):
            to_add.append("\n")
        to_add.append("\n")
        added += 1

    if added == 0:
        print("No new displays entries to add (all already present).")
        return 0

    backup = args.backup or f"{args.dest}.bak_append"
    shutil.copyfile(args.dest, backup)

    # Insert just before the displays closing brace line.
    new_dest_lines = dest_lines[:displays_end] + to_add + dest_lines[displays_end:]

    with open(args.dest, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(new_dest_lines)

    print(f"Added {added} displays entries into {args.dest} (backup at {backup})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
