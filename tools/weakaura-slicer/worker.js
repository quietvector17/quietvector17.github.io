function scanMatchingBrace(src, openBraceIdx) {
  // Scans forward from `openBraceIdx` (which must be a '{') and returns the
  // index of the matching '}' while ignoring braces inside double-quoted strings.
  let depth = 0;
  let inStr = false;
  let esc = false;

  for (let i = openBraceIdx; i < src.length; i++) {
    const ch = src[i];

    if (inStr) {
      if (esc) {
        esc = false;
        continue;
      }
      if (ch === "\\") {
        esc = true;
        continue;
      }
      if (ch === '"') {
        inStr = false;
      }
      continue;
    }

    if (ch === '"') {
      inStr = true;
      continue;
    }

    if (ch === "{") depth += 1;
    else if (ch === "}") {
      depth -= 1;
      if (depth === 0) return i;
    }
  }
  return null;
}

function isWs(ch) {
  return ch === " " || ch === "\n" || ch === "\r" || ch === "\t";
}

function findDisplaysBounds(src) {
  // Find the `["displays"] = { ... }` table bounds.
  let inStr = false;
  let esc = false;

  for (let i = 0; i < src.length; i++) {
    const ch = src[i];

    if (inStr) {
      if (esc) {
        esc = false;
        continue;
      }
      if (ch === "\\") {
        esc = true;
        continue;
      }
      if (ch === '"') inStr = false;
      continue;
    }

    if (ch === '"') {
      inStr = true;
      continue;
    }

    if (ch !== "[") continue;
    if (src.slice(i, i + 12) !== '["displays"]') continue;

    let j = i + 12;
    while (j < src.length && isWs(src[j])) j += 1;
    if (src[j] !== "=") continue;
    j += 1;
    while (j < src.length && isWs(src[j])) j += 1;
    if (src[j] !== "{") continue;

    const openBraceIdx = j;
    const closeBraceIdx = scanMatchingBrace(src, openBraceIdx);
    if (closeBraceIdx == null) return null;
    return {
      openBraceIdx,
      innerStart: openBraceIdx + 1,
      closeBraceIdx,
      innerEnd: closeBraceIdx,
    };
  }

  return null;
}

function parseTopLevelDisplayEntries(src, bounds) {
  const entries = [];
  let depth = 1;
  let inStr = false;
  let esc = false;
  let entryStart = null;
  let entryName = null;

  function tryParseKeyedOpen(at) {
    // Parses ["Name"] = { starting at index `at`.
    if (src[at] !== "[") return null;
    if (src[at + 1] !== '"') return null;
    let k = at + 2;
    let name = "";
    let keyEsc = false;
    for (; k < bounds.innerEnd; k++) {
      const c = src[k];
      if (keyEsc) {
        keyEsc = false;
        name += c;
        continue;
      }
      if (c === "\\") {
        keyEsc = true;
        name += c;
        continue;
      }
      if (c === '"') break;
      name += c;
    }
    if (k >= bounds.innerEnd || src[k] !== '"') return null;
    if (src[k + 1] !== "]") return null;
    k += 2;
    while (k < bounds.innerEnd && isWs(src[k])) k += 1;
    if (src[k] !== "=") return null;
    k += 1;
    while (k < bounds.innerEnd && isWs(src[k])) k += 1;
    if (src[k] !== "{") return null;
    return { name, nextIdxAfterBrace: k + 1 };
  }

  function extractStringField(key, start, end) {
    const needle = `["${key}"]`;
    const idx = src.indexOf(needle, start);
    if (idx === -1 || idx >= end) return null;
    let j = idx + needle.length;
    while (j < end && isWs(src[j])) j += 1;
    if (src[j] !== "=") return null;
    j += 1;
    while (j < end && isWs(src[j])) j += 1;
    if (src[j] !== '"') return null;
    j += 1;
    let out = "";
    let esc2 = false;
    for (; j < end; j++) {
      const c = src[j];
      if (esc2) {
        esc2 = false;
        out += c;
        continue;
      }
      if (c === "\\") {
        esc2 = true;
        out += c;
        continue;
      }
      if (c === '"') break;
      out += c;
    }
    return out;
  }

  for (let i = bounds.innerStart; i < bounds.innerEnd; i++) {
    const ch = src[i];

    if (inStr) {
      if (esc) {
        esc = false;
        continue;
      }
      if (ch === "\\") {
        esc = true;
        continue;
      }
      if (ch === '"') inStr = false;
      continue;
    }

    if (ch === '"') {
      inStr = true;
      continue;
    }

    if (entryStart == null && depth === 1) {
      const opened = tryParseKeyedOpen(i);
      if (opened) {
        entryStart = i;
        entryName = opened.name;
        depth += 1;
        i = opened.nextIdxAfterBrace - 1;
        continue;
      }
    }

    if (ch === "{") depth += 1;
    else if (ch === "}") {
      depth -= 1;
      if (entryStart != null && depth === 1) {
        let end = i + 1;
        while (end < bounds.innerEnd) {
          const c = src[end];
          if (c === ",") {
            end += 1;
            break;
          }
          if (isWs(c)) {
            end += 1;
            continue;
          }
          break;
        }

        entries.push({
          name: entryName,
          start: entryStart,
          end,
          regionType: extractStringField("regionType", entryStart, end),
          parent: extractStringField("parent", entryStart, end),
          id: extractStringField("id", entryStart, end),
        });

        entryStart = null;
        entryName = null;
      }
    }
  }

  return entries;
}

self.onmessage = (ev) => {
  const msg = ev.data;
  if (!msg || msg.type !== "parse") return;
  const { parseId, src } = msg;

  try {
    const bounds = findDisplaysBounds(src);
    if (!bounds) {
      self.postMessage({ type: "parsed", parseId, error: 'Could not find a ["displays"] table.' });
      return;
    }
    const entries = parseTopLevelDisplayEntries(src, bounds);
    self.postMessage({ type: "parsed", parseId, bounds, entries });
  } catch (err) {
    self.postMessage({
      type: "parsed",
      parseId,
      error: err && err.message ? err.message : String(err),
    });
  }
};
