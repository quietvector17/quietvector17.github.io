const form = document.getElementById("wa-form");
const fileInput = document.getElementById("wa-file");
const inputEl = document.getElementById("wa-input");
const outputEl = document.getElementById("wa-output");
const parseBtn = document.getElementById("parse-btn");
const clearBtn = document.getElementById("clear-btn");
const statusEl = document.getElementById("wa-status");
const groupListEl = document.getElementById("wa-group-list");
const searchEl = document.getElementById("wa-search");

const autoParseEl = document.getElementById("auto-parse");
const rootOnlyEl = document.getElementById("root-only");
const includeAncestorsEl = document.getElementById("include-ancestors");
const includeDescendantsEl = document.getElementById("include-descendants");

const selectAllBtn = document.getElementById("select-all");
const selectNoneBtn = document.getElementById("select-none");
const generateBtn = document.getElementById("generate-btn");
const downloadBtn = document.getElementById("download-btn");
const copyBtn = document.getElementById("copy-btn");

let lastParsed = null;
let downloadUrl = null;
let parseTimer = null;
let selectedGroupNames = new Set();

function setStatus(text) {
  statusEl.textContent = text;
}

function stripLuaStrings(text) {
  // Returns a string with the same length as `text` where characters inside
  // Lua double-quoted strings are replaced with spaces (preserves indices).
  let out = "";
  let inStr = false;
  let esc = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (inStr) {
      if (esc) {
        esc = false;
        out += " ";
        continue;
      }
      if (ch === "\\") {
        esc = true;
        out += " ";
        continue;
      }
      if (ch === '"') {
        inStr = false;
      }
      out += " ";
      continue;
    }
    if (ch === '"') {
      inStr = true;
      out += " ";
      continue;
    }
    out += ch;
  }
  return out;
}

function findDisplaysBounds(src) {
  const stripped = stripLuaStrings(src);
  const m = stripped.match(/\["displays"\]\s*=\s*\{/);
  if (!m) return null;
  const openBraceIdx = (m.index || 0) + m[0].lastIndexOf("{");
  let depth = 0;
  let started = false;
  for (let i = openBraceIdx; i < stripped.length; i++) {
    const ch = stripped[i];
    if (ch === "{") {
      depth += 1;
      started = true;
    } else if (ch === "}") {
      depth -= 1;
      if (started && depth === 0) {
        return {
          openBraceIdx,
          innerStart: openBraceIdx + 1,
          closeBraceIdx: i,
          innerEnd: i,
        };
      }
    }
  }
  return null;
}

function parseTopLevelDisplayEntries(src, bounds) {
  // Returns entries with exact source slices, plus inferred fields.
  const stripped = stripLuaStrings(src);

  const entries = [];
  let i = bounds.innerStart;
  let depth = 1; // we're inside displays
  let entryStart = null;
  let entryDepthStart = null;
  let entryName = null;

  // Match ["Name"] = { at depth==1.
  const reKeyedOpen = /\["([^"]+)"\]\s*=\s*\{/y;

  while (i < bounds.innerEnd) {
    const ch = stripped[i];

    if (entryStart == null && depth === 1) {
      reKeyedOpen.lastIndex = i;
      const m = reKeyedOpen.exec(stripped);
      if (m) {
        entryStart = m.index;
        entryName = m[1];
        // The brace for this entry is the last character matched.
        entryDepthStart = depth + 1; // depth after consuming this '{'
        i = reKeyedOpen.lastIndex;
        depth += 1;
        continue;
      }
    }

    if (ch === "{") {
      depth += 1;
    } else if (ch === "}") {
      depth -= 1;
      if (entryStart != null && depth === 1) {
        // Entry closed. Include trailing comma/newlines after the closing brace.
        let end = i + 1;
        while (end < bounds.innerEnd) {
          const c = src[end];
          if (c === ",") {
            end += 1;
            break;
          }
          if (c === "\n" || c === "\r" || c === "\t" || c === " ") {
            end += 1;
            continue;
          }
          break;
        }

        const slice = src.slice(entryStart, end);
        const regionTypeMatch = slice.match(/\["regionType"\]\s*=\s*"([^"]+)"/);
        const parentMatch = slice.match(/\["parent"\]\s*=\s*"([^"]+)"/);
        const idMatch = slice.match(/\["id"\]\s*=\s*"([^"]+)"/);

        entries.push({
          name: entryName,
          start: entryStart,
          end,
          text: slice,
          regionType: regionTypeMatch ? regionTypeMatch[1] : null,
          parent: parentMatch ? parentMatch[1] : null,
          id: idMatch ? idMatch[1] : null,
        });

        entryStart = null;
        entryDepthStart = null;
        entryName = null;
      }
    }

    i += 1;
  }

  return entries;
}

function buildGraph(entries) {
  const byName = new Map(entries.map((e) => [e.name, e]));
  const children = new Map();
  for (const e of entries) {
    if (!e.parent) continue;
    if (!children.has(e.parent)) children.set(e.parent, new Set());
    children.get(e.parent).add(e.name);
  }
  return { byName, children };
}

function computeDepth(name, byName) {
  let d = 0;
  let cur = byName.get(name);
  const seen = new Set();
  while (cur && cur.parent && !seen.has(cur.parent)) {
    seen.add(cur.parent);
    d += 1;
    cur = byName.get(cur.parent);
  }
  return d;
}

function listGroups(entries) {
  return entries.filter((e) => e.regionType === "group" || e.regionType === "dynamicgroup");
}

function renderGroups(groups, graph) {
  const q = (searchEl.value || "").trim().toLowerCase();
  const rootOnly = rootOnlyEl.checked;

  groupListEl.innerHTML = "";
  const frag = document.createDocumentFragment();

  const sorted = [...groups].sort((a, b) => {
    const ap = a.parent || "";
    const bp = b.parent || "";
    if (ap !== bp) return ap.localeCompare(bp);
    return a.name.localeCompare(b.name);
  });

  let shown = 0;
  for (const g of sorted) {
    if (rootOnly && g.parent) continue;
    if (q && !g.name.toLowerCase().includes(q) && !(g.parent || "").toLowerCase().includes(q)) continue;

    const row = document.createElement("div");
    row.className = "wa-row";

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.id = `wa-g-${encodeURIComponent(g.name)}`;
    cb.checked = selectedGroupNames.has(g.name);
    cb.dataset.name = g.name;
    cb.addEventListener("change", () => {
      const name = cb.dataset.name;
      if (!name) return;
      if (cb.checked) selectedGroupNames.add(name);
      else selectedGroupNames.delete(name);

      if (lastParsed) {
        setStatus(`Selected ${selectedGroupNames.size} group(s).`);
      }
    });

    const label = document.createElement("label");
    label.htmlFor = cb.id;
    const depth = computeDepth(g.name, graph.byName);
    const indent = "\u00a0".repeat(Math.min(depth, 10) * 2);

    const title = document.createElement("div");
    title.className = "wa-name";
    title.textContent = `${indent}${g.name}`;

    const meta = document.createElement("div");
    meta.className = "wa-meta";
    meta.textContent = `${g.regionType}${g.parent ? `  parent: ${g.parent}` : ""}`;

    label.appendChild(title);
    label.appendChild(meta);

    row.appendChild(cb);
    row.appendChild(label);
    frag.appendChild(row);
    shown += 1;
  }

  groupListEl.appendChild(frag);
  setStatus(
    lastParsed
      ? `Parsed ${groups.length} group(s). Showing ${shown}. Selected ${selectedGroupNames.size}.`
      : "Paste a file to begin."
  );
}

function getSelectedGroupNames() {
  return Array.from(selectedGroupNames);
}

function closureSelected(entries, graph, selectedGroupNames, opts) {
  const includeAncestors = opts.includeAncestors;
  const includeDescendants = opts.includeDescendants;

  const selected = new Set(selectedGroupNames);
  const out = new Set(selectedGroupNames);

  if (includeAncestors) {
    for (const name of selected) {
      let cur = graph.byName.get(name);
      const seen = new Set([name]);
      while (cur && cur.parent && !seen.has(cur.parent)) {
        seen.add(cur.parent);
        out.add(cur.parent);
        cur = graph.byName.get(cur.parent);
      }
    }
  }

  if (includeDescendants) {
    const queue = [...out];
    const seen = new Set(queue);
    while (queue.length) {
      const n = queue.shift();
      const kids = graph.children.get(n);
      if (!kids) continue;
      for (const k of kids) {
        if (seen.has(k)) continue;
        seen.add(k);
        out.add(k);
        queue.push(k);
      }
    }
  }

  // Always include only entries that exist.
  const namesInFile = new Set(entries.map((e) => e.name));
  const finalNames = new Set();
  for (const n of out) {
    if (namesInFile.has(n)) finalNames.add(n);
  }
  return finalNames;
}

function generateFilteredFile(parsed) {
  const selectedGroups = getSelectedGroupNames();
  if (selectedGroups.length === 0) {
    throw new Error("No groups selected.");
  }

  const includedNames = closureSelected(parsed.entries, parsed.graph, selectedGroups, {
    includeAncestors: includeAncestorsEl.checked,
    includeDescendants: includeDescendantsEl.checked,
  });

  const includedEntries = parsed.entries
    .filter((e) => includedNames.has(e.name))
    .sort((a, b) => a.start - b.start)
    .map((e) => e.text.trimEnd());

  const inner = includedEntries.length ? `\n${includedEntries.join("\n\n")}\n` : "\n";
  const before = parsed.src.slice(0, parsed.bounds.innerStart);
  const after = parsed.src.slice(parsed.bounds.innerEnd);
  return before + inner + after;
}

function setDownload(text) {
  if (downloadUrl) URL.revokeObjectURL(downloadUrl);
  const blob = new Blob([text], { type: "text/plain" });
  downloadUrl = URL.createObjectURL(blob);
  downloadBtn.disabled = false;
  copyBtn.disabled = false;
}

function parseNow() {
  const src = inputEl.value || "";
  outputEl.value = "";
  downloadBtn.disabled = true;
  copyBtn.disabled = true;
  if (downloadUrl) {
    URL.revokeObjectURL(downloadUrl);
    downloadUrl = null;
  }

  if (!src.trim()) {
    lastParsed = null;
    groupListEl.innerHTML = "";
    setStatus("Paste a file to begin.");
    return;
  }

  const bounds = findDisplaysBounds(src);
  if (!bounds) {
    lastParsed = null;
    groupListEl.innerHTML = "";
    setStatus('Could not find a ["displays"] table in the pasted text.');
    return;
  }

  const entries = parseTopLevelDisplayEntries(src, bounds);
  const graph = buildGraph(entries);
  const groups = listGroups(entries);

  // Default selection: all groups.
  selectedGroupNames = new Set(groups.map((g) => g.name));

  lastParsed = { src, bounds, entries, graph, groups };
  renderGroups(groups, graph);
}

function scheduleAutoParse() {
  if (!autoParseEl.checked) return;
  if (parseTimer) window.clearTimeout(parseTimer);
  parseTimer = window.setTimeout(() => {
    parseTimer = null;
    parseNow();
  }, 450);
}

fileInput.addEventListener("change", async () => {
  const file = fileInput.files && fileInput.files[0];
  if (!file) return;
  const text = await file.text();
  inputEl.value = text;
  parseNow();
});

inputEl.addEventListener("input", scheduleAutoParse);
searchEl.addEventListener("input", () => {
  if (!lastParsed) return;
  renderGroups(lastParsed.groups, lastParsed.graph);
});
rootOnlyEl.addEventListener("change", () => {
  if (!lastParsed) return;
  renderGroups(lastParsed.groups, lastParsed.graph);
});

form.addEventListener("submit", (e) => {
  e.preventDefault();
  parseNow();
});

clearBtn.addEventListener("click", () => {
  fileInput.value = "";
  inputEl.value = "";
  outputEl.value = "";
  groupListEl.innerHTML = "";
  searchEl.value = "";
  lastParsed = null;
  selectedGroupNames = new Set();
  downloadBtn.disabled = true;
  copyBtn.disabled = true;
  if (downloadUrl) {
    URL.revokeObjectURL(downloadUrl);
    downloadUrl = null;
  }
  setStatus("Cleared.");
});

selectAllBtn.addEventListener("click", () => {
  const inputs = groupListEl.querySelectorAll('input[type="checkbox"][data-name]');
  inputs.forEach((cb) => {
    cb.checked = true;
    if (cb.dataset.name) selectedGroupNames.add(cb.dataset.name);
  });
  if (lastParsed) setStatus(`Selected ${selectedGroupNames.size} group(s).`);
});

selectNoneBtn.addEventListener("click", () => {
  const inputs = groupListEl.querySelectorAll('input[type="checkbox"][data-name]');
  inputs.forEach((cb) => {
    cb.checked = false;
    if (cb.dataset.name) selectedGroupNames.delete(cb.dataset.name);
  });
  if (lastParsed) setStatus(`Selected ${selectedGroupNames.size} group(s).`);
});

generateBtn.addEventListener("click", () => {
  if (!lastParsed) {
    setStatus("Paste a file and parse it first.");
    return;
  }
  try {
    const text = generateFilteredFile(lastParsed);
    outputEl.value = text;
    setDownload(text);
    setStatus("Generated filtered file.");
  } catch (err) {
    setStatus(err && err.message ? err.message : String(err));
  }
});

downloadBtn.addEventListener("click", () => {
  if (!outputEl.value || !downloadUrl) return;
  const a = document.createElement("a");
  a.href = downloadUrl;
  a.download = "WeakAuras.filtered.lua";
  document.body.appendChild(a);
  a.click();
  a.remove();
});

copyBtn.addEventListener("click", async () => {
  if (!outputEl.value) return;
  try {
    await navigator.clipboard.writeText(outputEl.value);
    setStatus("Copied output to clipboard.");
  } catch {
    setStatus("Copy failed (browser blocked clipboard). Use manual copy from Output.");
  }
});

// Best-effort: if a page restore brings content back, parse it.
window.addEventListener("pageshow", () => {
  if (inputEl.value.trim()) parseNow();
});
