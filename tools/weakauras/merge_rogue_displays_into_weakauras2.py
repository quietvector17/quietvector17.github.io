import shutil


SRC_EXTRACT = "fojji_mop15_displays_extract.lua"
DEST = "weakauras2"
BACKUP = "weakauras2.bak"


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


def _extract_displays_inner(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    start = None
    for i, line in enumerate(lines):
        if '["displays"]' in line and "{" in line and "=" in line:
            # Prefer the canonical savedvars line.
            if line.strip().startswith('["displays"]') and line.strip().endswith("{"):
                start = i
                break
    if start is None:
        raise SystemExit(f"Couldn't find displays table in {path}")

    # Track brace depth starting at the opening '{' on the displays line.
    depth = 0
    found_open = False
    inner: list[str] = []

    for i in range(start, len(lines)):
        line = lines[i]
        stripped = _strip_lua_strings(line)
        for ch in stripped:
            if ch == "{":
                depth += 1
                found_open = True
            elif ch == "}":
                depth -= 1
        if i == start:
            # Don't include the ['displays'] = { line itself.
            continue
        if not found_open:
            continue
        if depth == 0:
            # We've consumed the closing '}' for displays; stop without including this line.
            break
        inner.append(line)

    if not inner:
        raise SystemExit(f"No inner displays content extracted from {path}")
    return inner


def main() -> int:
    rogue_inner = _extract_displays_inner(SRC_EXTRACT)

    with open(DEST, "r", encoding="utf-8", errors="replace") as f:
        dest_lines = f.readlines()

    # Find destination displays open/close.
    open_idx = None
    for i, line in enumerate(dest_lines):
        if line.strip() == '["displays"] = {':
            open_idx = i
            break
    if open_idx is None:
        raise SystemExit(f"Couldn't find ['displays'] table start in {DEST}")

    close_idx = None
    for i in range(open_idx + 1, len(dest_lines)):
        if dest_lines[i].strip() == "},":
            close_idx = i
            break
    if close_idx is None:
        raise SystemExit(f"Couldn't find displays table end in {DEST}")

    # Replace the body of displays with the extracted content.
    new_lines = dest_lines[: open_idx + 1] + rogue_inner + dest_lines[close_idx:]

    shutil.copyfile(DEST, BACKUP)
    with open(DEST, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(new_lines)

    print(f"Updated {DEST} (backup at {BACKUP})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
