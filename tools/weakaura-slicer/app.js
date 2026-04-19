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
// UI now lists only root groups and always includes descendants on export.

const selectAllBtn = document.getElementById("select-all");
const selectNoneBtn = document.getElementById("select-none");
const generateBtn = document.getElementById("generate-btn");
const downloadBtn = document.getElementById("download-btn");
const copyBtn = document.getElementById("copy-btn");

let lastParsed = null;
let downloadUrl = null;
let parseTimer = null;
let selectedGroupNames = new Set();
let parseRunId = 0;
let renderRunId = 0;

let worker = null;
let workerBusy = false;

function ensureWorker() {
  if (worker) return worker;
  worker = new Worker("./worker.js");
  worker.onmessage = (ev) => {
    const msg = ev.data;
    if (!msg || msg.type !== "parsed") return;
    const { parseId, bounds, entries, error } = msg;
    if (parseId !== parseRunId) return;
    workerBusy = false;

    if (error) {
      lastParsed = null;
      groupListEl.innerHTML = "";
      setStatus(error);
      return;
    }

    const graph = buildGraph(entries);
    const groups = listGroups(entries);
    const sortedGroups = [...groups].sort((a, b) => {
      const ap = a.parent || "";
      const bp = b.parent || "";
      if (ap !== bp) return ap.localeCompare(bp);
      return a.name.localeCompare(b.name);
    });
    const rootGroups = sortedGroups.filter((g) => !g.parent);
    selectedGroupNames = new Set(groups.map((g) => g.name));

    // Cache depths so rendering doesn't repeatedly walk parents.
    const depthByName = new Map();
    const getDepth = (name) => {
      if (depthByName.has(name)) return depthByName.get(name);
      let d = 0;
      let cur = graph.byName.get(name);
      const seen = new Set([name]);
      while (cur && cur.parent && !seen.has(cur.parent)) {
        seen.add(cur.parent);
        d += 1;
        cur = graph.byName.get(cur.parent);
      }
      depthByName.set(name, d);
      return d;
    };
    for (const g of groups) getDepth(g.name);

    // Default selection: all root groups.
    selectedGroupNames = new Set(rootGroups.map((g) => g.name));

    lastParsed = {
      src: lastParsed ? lastParsed.src : "",
      bounds,
      entries,
      graph,
      groups,
      sortedGroups,
      rootGroups,
      depthByName,
    };
    renderGroups(rootGroups, graph);
  };

  worker.onerror = () => {
    workerBusy = false;
    setStatus("Worker error while parsing.");
  };
  return worker;
}

function setStatus(text) {
  statusEl.textContent = text;
}

function isWs(ch) {
  return ch === " " || ch === "\n" || ch === "\r" || ch === "\t";
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
  // Kept for compatibility; we typically use lastParsed.depthByName now.
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

  const thisRender = ++renderRunId;

  groupListEl.innerHTML = "";

  const filtered = [];
  for (const g of groups) {
    if (q && !g.name.toLowerCase().includes(q)) continue;
    filtered.push(g);
  }

  const depthByName = lastParsed && lastParsed.depthByName ? lastParsed.depthByName : null;

  let idx = 0;
  let shown = 0;
  const chunk = 250;

  function step() {
    if (thisRender !== renderRunId) return;

    const frag = document.createDocumentFragment();
    const end = Math.min(filtered.length, idx + chunk);
    for (; idx < end; idx++) {
      const g = filtered[idx];

      const row = document.createElement("div");
      row.className = "wa-row";

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = selectedGroupNames.has(g.name);
      cb.dataset.name = g.name;

      const label = document.createElement("label");
      const depth = depthByName ? depthByName.get(g.name) || 0 : computeDepth(g.name, graph.byName);
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
        ? `Parsed ${groups.length} group(s). Showing ${shown}/${filtered.length}. Selected ${selectedGroupNames.size}.`
        : "Paste a file to begin."
    );

    if (idx < filtered.length) {
      window.requestAnimationFrame(step);
    }
  }

  window.requestAnimationFrame(step);

  return;
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
    includeAncestors: true,
    includeDescendants: true,
  });

  const includedEntries = parsed.entries
    .filter((e) => includedNames.has(e.name))
    .sort((a, b) => a.start - b.start)
    .map((e) => parsed.src.slice(e.start, e.end).trimEnd());

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

  const runId = ++parseRunId;
  setStatus("Parsing...");

  // If a parse is already running, kill the worker so it doesn't chew CPU.
  if (workerBusy && worker) {
    worker.terminate();
    worker = null;
    workerBusy = false;
  }

  // Keep src on the main thread for slicing during export.
  lastParsed = { src };

  const w = ensureWorker();
  workerBusy = true;
  w.postMessage({ type: "parse", parseId: runId, src });
}

function scheduleAutoParse() {
  if (!autoParseEl.checked) return;
  if (parseTimer) window.clearTimeout(parseTimer);
  const delay = (inputEl.value || "").length > 1_500_000 ? 1200 : 450;
  const schedule = (cb) => {
    if (typeof window.requestIdleCallback === "function") {
      window.requestIdleCallback(cb, { timeout: Math.max(1500, delay + 600) });
      return;
    }
    window.setTimeout(cb, 0);
  };
  parseTimer = window.setTimeout(() => {
    parseTimer = null;
    schedule(() => parseNow());
  }, delay);
}

// Event delegation: avoid one listener per checkbox row.
groupListEl.addEventListener("change", (e) => {
  const target = e.target;
  if (!target || target.tagName !== "INPUT" || target.type !== "checkbox") return;
  const name = target.dataset.name;
  if (!name) return;
  if (target.checked) selectedGroupNames.add(name);
  else selectedGroupNames.delete(name);
  if (lastParsed) setStatus(`Selected ${selectedGroupNames.size} group(s).`);
});

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
  renderGroups(lastParsed.rootGroups || lastParsed.sortedGroups || lastParsed.groups, lastParsed.graph);
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
