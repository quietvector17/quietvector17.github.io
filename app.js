const form = document.getElementById("analysis-form");
const reportInput = document.getElementById("report-input");
const clientIdInput = document.getElementById("client-id");
const clientSecretInput = document.getElementById("client-secret");
const runBtn = document.getElementById("run-btn");
const clearBtn = document.getElementById("clear-btn");
const statusText = document.getElementById("status-text");
const resultsEl = document.getElementById("results");

const DEFAULTS = {
  reportCode: "vFYGaXZgdTk9P6tz",
};

const ABILITIES = {
  heroism: 32182,
  windStorm: 136577,
  superchargeConduits: 137045,
  shellConcussion: 136431,
};

const QUETZAL_MAX_HP = 399065355;

const DOG_KEYS = {
  "Ro'Shak": ["ro", "shak"],
  "Quet'Zal": ["quet", "zal"],
  "Dam'Ren": ["dam", "ren"],
};

const ELDER_KEYS = {
  Malakk: ["malakk"],
  "Mar'li": ["mar", "li"],
  "Kazra'jin": ["kazra"],
  Sul: ["sul", "sand"],
};

const HEAD_KEYS = {
  Flaming: ["flam", "head"],
  Frozen: ["froz", "head"],
  Arcane: ["arcane", "head"],
  Venomous: ["venom", "head"],
};

const AURA_TYPES = new Set([
  "applydebuff",
  "applydebuffstack",
  "refreshdebuff",
  "refreshdebuffstack",
  "removedebuff",
  "applybuff",
  "applybuffstack",
  "refreshbuff",
  "refreshbuffstack",
  "removebuff",
]);

function setStatus(message) {
  statusText.textContent = message;
}

function clearResults() {
  resultsEl.innerHTML = "";
}

function addCard(title, description, bodyText) {
  const card = document.createElement("section");
  card.className = "card";
  const h2 = document.createElement("h2");
  h2.textContent = title;
  const p = document.createElement("p");
  p.textContent = description;
  const pre = document.createElement("pre");
  pre.textContent = bodyText || "(no output)";
  card.appendChild(h2);
  card.appendChild(p);
  card.appendChild(pre);
  resultsEl.appendChild(card);
}

function mmssFromMs(ms) {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}:${String(rem).padStart(2, "0")}`;
}

function relMmss(tsAbs, start) {
  return mmssFromMs(tsAbs - start);
}

function norm(text) {
  return String(text || "").toLowerCase().replace("\u2019", "'");
}

function parseReportCode(input) {
  const raw = (input || "").trim();
  if (!raw) return "";
  const match = raw.match(/reports\/([A-Za-z0-9]+)/);
  if (match) return match[1];
  return raw;
}

function parseBaseUrl(input) {
  try {
    const url = new URL(input);
    if (url.host.includes("classic.warcraftlogs.com")) {
      return "https://classic.warcraftlogs.com";
    }
    return "https://www.warcraftlogs.com";
  } catch (err) {
    return "https://classic.warcraftlogs.com";
  }
}

async function fetchToken(clientId, clientSecret, baseUrl) {
  const response = await fetch(`${baseUrl}/oauth/token`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      Authorization: "Basic " + btoa(`${clientId}:${clientSecret}`),
    },
    body: "grant_type=client_credentials",
  });
  if (!response.ok) {
    throw new Error("Token request failed. Check client credentials.");
  }
  const data = await response.json();
  return data.access_token;
}

async function gql(baseUrl, token, query, variables) {
  const response = await fetch(`${baseUrl}/api/v2/client`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ query, variables }),
  });
  if (!response.ok) {
    throw new Error("GraphQL request failed.");
  }
  const payload = await response.json();
  if (payload.errors) {
    throw new Error(payload.errors.map((e) => e.message || String(e)).join("\n"));
  }
  return payload.data;
}

async function fetchEventsPagedSimple(baseUrl, token, code, fightID, start, end, dataType, abilityID) {
  const query = `
    query($code: String!, $fightID: Int!, $pageStart: Float!, $end: Float!, $dt: EventDataType!, $abilityID: Int) {
      reportData {
        report(code: $code) {
          events(
            fightIDs: [$fightID]
            startTime: $pageStart
            endTime: $end
            dataType: $dt
            abilityID: $abilityID
            limit: 5000
          ) {
            data
            nextPageTimestamp
          }
        }
      }
    }
  `;

  let pageStart = start;
  const events = [];
  while (true) {
    const data = await gql(baseUrl, token, query, {
      code,
      fightID,
      pageStart,
      end,
      dt: dataType,
      abilityID: abilityID || null,
    });
    const ev = data.reportData.report.events;
    if (Array.isArray(ev.data)) {
      events.push(...ev.data.filter((e) => e && typeof e === "object"));
    }
    if (!ev.nextPageTimestamp) break;
    pageStart = ev.nextPageTimestamp;
  }
  return events;
}

async function fetchEventsPagedHostile(baseUrl, token, code, fightID, start, end, dataType, hostility, translate) {
  const query = `
    query($code: String!, $fightID: Int!, $pageStart: Float!, $end: Float!, $dt: EventDataType!, $hostility: HostilityType!, $translate: Boolean) {
      reportData {
        report(code: $code) {
          events(
            fightIDs: [$fightID]
            startTime: $pageStart
            endTime: $end
            dataType: $dt
            hostilityType: $hostility
            translate: $translate
            limit: 5000
          ) {
            data
            nextPageTimestamp
          }
        }
      }
    }
  `;

  let pageStart = start;
  const events = [];
  while (true) {
    const data = await gql(baseUrl, token, query, {
      code,
      fightID,
      pageStart,
      end,
      dt: dataType,
      hostility,
      translate,
    });
    const ev = data.reportData.report.events;
    if (Array.isArray(ev.data)) {
      events.push(...ev.data.filter((e) => e && typeof e === "object"));
    }
    if (!ev.nextPageTimestamp) break;
    pageStart = ev.nextPageTimestamp;
  }
  return events;
}

async function fetchReport(baseUrl, token, code) {
  const query = `
    query($code: String!) {
      reportData {
        report(code: $code) {
          title
          fights { id name kill startTime endTime }
          masterData { actors { id name type subType } }
        }
      }
    }
  `;
  const data = await gql(baseUrl, token, query, { code });
  return data.reportData.report;
}

function findActorIdsFuzzy(actors, requiredSubstrings) {
  const req = requiredSubstrings.map(norm);
  const hits = [];
  for (const actor of actors || []) {
    if (!actor || typeof actor !== "object") continue;
    const name = actor.name;
    if (typeof name !== "string") continue;
    const n = norm(name);
    if (req.every((r) => n.includes(r))) {
      hits.push(actor);
    }
  }
  hits.sort((a, b) => {
    const aType = norm(a.type || "");
    const bType = norm(b.type || "");
    const aSub = norm(a.subType || "");
    const bSub = norm(b.subType || "");
    const aIsPlayer = aType === "player" || aSub === "player";
    const bIsPlayer = bType === "player" || bSub === "player";
    if (aIsPlayer !== bIsPlayer) return aIsPlayer ? 1 : -1;
    const aName = norm(a.name || "");
    const bName = norm(b.name || "");
    return aName.length - bName.length;
  });
  return hits;
}

function buildActorById(actors) {
  const out = new Map();
  for (const a of actors || []) {
    if (a && typeof a.id === "number") {
      out.set(a.id, a);
    }
  }
  return out;
}

function isPlayerActor(actor) {
  if (!actor) return false;
  const t = norm(actor.type || "");
  const st = norm(actor.subType || "");
  return t === "player" || st === "player";
}

function getAbilityId(event) {
  const ability = event.ability;
  if (ability && typeof ability === "object") {
    if (typeof ability.id === "number") return ability.id;
    if (typeof ability.gameID === "number") return ability.gameID;
  }
  const keys = ["abilityGameID", "abilityID", "spellID", "guid"];
  for (const k of keys) {
    const v = event[k];
    if (typeof v === "number") return v;
  }
  return null;
}

function getAbilityName(event) {
  const ability = event.ability;
  if (ability && typeof ability === "object" && typeof ability.name === "string") {
    return ability.name;
  }
  const keys = ["abilityName", "spellName", "name"];
  for (const k of keys) {
    const v = event[k];
    if (typeof v === "string") return v;
  }
  return null;
}

function getTargetId(event) {
  if (typeof event.targetID === "number") return event.targetID;
  const target = event.target;
  if (target && typeof target === "object" && typeof target.id === "number") return target.id;
  if (typeof target === "number") return target;
  return null;
}

async function getDeaths(baseUrl, token, code, fight, playerIds) {
  const events = await fetchEventsPagedSimple(
    baseUrl,
    token,
    code,
    fight.id,
    fight.startTime,
    fight.endTime,
    "Deaths"
  );
  let count = 0;
  for (const e of events) {
    const tid = getTargetId(e);
    if (typeof tid === "number" && playerIds.has(tid)) count += 1;
  }
  return count;
}

async function getHeroismTimestamp(baseUrl, token, code, fight) {
  const events = await fetchEventsPagedSimple(
    baseUrl,
    token,
    code,
    fight.id,
    fight.startTime,
    fight.endTime,
    "Casts",
    ABILITIES.heroism
  );
  const timestamps = events
    .map((e) => e.timestamp)
    .filter((ts) => typeof ts === "number");
  if (!timestamps.length) return null;
  return Math.min(...timestamps);
}

async function buildOverall(baseUrl, token, code, report, playerIds) {
  const kills = [];
  let totalWipes = 0;

  for (let i = 0; i < report.fights.length; i += 1) {
    const fight = report.fights[i];
    if (!fight.kill) continue;
    const boss = fight.name;
    let wipes = report.fights
      .slice(0, i)
      .filter((f) => f.name === boss && !f.kill).length;
    if (boss === "Ji-Kun") wipes = Math.max(0, wipes - 1);
    const deaths = await getDeaths(baseUrl, token, code, fight, playerIds);
    const heroTs = await getHeroismTimestamp(baseUrl, token, code, fight);
    const lustAt = typeof heroTs === "number" ? heroTs - fight.startTime : null;
    totalWipes += wipes;
    kills.push({
      boss,
      fightId: fight.id,
      duration: fight.endTime - fight.startTime,
      wipes,
      deaths,
      lustAt,
    });
  }

  kills.sort((a, b) => a.fightId - b.fightId);

  const bossWidth = Math.max(12, Math.min(32, ...kills.map((k) => k.boss.length)));
  const header = `${"Boss".padEnd(bossWidth)}  ${"Dur".padStart(6)}  ${"Wipes".padStart(5)}  ${"Deaths".padStart(6)}  ${"Lust @".padStart(6)}  ${"FightID".padStart(6)}`;
  const line = "-".repeat(bossWidth + 35);
  const rows = kills.map((k) => {
    const lust = typeof k.lustAt === "number" ? mmssFromMs(k.lustAt) : "-";
    return `${k.boss.padEnd(bossWidth)}  ${mmssFromMs(k.duration).padStart(6)}  ${String(k.wipes).padStart(5)}  ${String(k.deaths).padStart(6)}  ${lust.padStart(6)}  ${String(k.fightId).padStart(6)}`;
  });
  const footer = `\nTotal kills: ${kills.length} | Total wipes (before kills): ${totalWipes}`;
  return [header, line, ...rows, footer].join("\n");
}

async function buildCouncil(baseUrl, token, code, report) {
  const councilKills = report.fights.filter(
    (f) => f.name === "Council of Elders" && f.kill
  );
  if (!councilKills.length) {
    return "No Council of Elders kills found.";
  }
  const elderIds = {};
  for (const [label, subs] of Object.entries(ELDER_KEYS)) {
    const hits = findActorIdsFuzzy(report.masterData.actors, subs);
    elderIds[label] = hits.map((h) => h.id).filter((id) => typeof id === "number");
  }

  const lines = ["Council of Elders - Elder death times (KILLS ONLY)", "--------------------------------------------------"];

  for (const fight of councilKills) {
    const deaths = {};
    for (const label of Object.keys(elderIds)) deaths[label] = null;
    const events = await fetchEventsPagedSimple(
      baseUrl,
      token,
      code,
      fight.id,
      fight.startTime,
      fight.endTime,
      "All"
    );
    for (const e of events) {
      const et = norm(e.type || "");
      if (et !== "death" && et !== "destroy") continue;
      const ts = e.timestamp;
      const tid = e.targetID;
      if (typeof ts !== "number" || typeof tid !== "number") continue;
      for (const [label, ids] of Object.entries(elderIds)) {
        if (ids.includes(tid)) {
          const cur = deaths[label];
          if (cur === null || ts < cur) deaths[label] = ts;
          break;
        }
      }
    }

    const ordered = Object.entries(deaths).sort((a, b) => {
      const aVal = typeof a[1] === "number" ? a[1] : Infinity;
      const bVal = typeof b[1] === "number" ? b[1] : Infinity;
      return aVal - bVal;
    });
    const headers = ["Dur", ...ordered.map((o) => o[0])];
    const widths = [6, ...ordered.map((o) => Math.max(7, o[0].length))];
    const fmtRow = (cells) => cells.map((c, i) => String(c).padStart(widths[i])).join("  ");
    lines.push("\n" + fmtRow(headers));
    lines.push("-".repeat(widths.reduce((a, b) => a + b, 0) + 2 * (widths.length - 1)));
    const dur = mmssFromMs(fight.endTime - fight.startTime);
    const values = [dur, ...ordered.map((o) => (typeof o[1] === "number" ? relMmss(o[1], fight.startTime) : "-"))];
    lines.push(fmtRow(values));
  }

  return lines.join("\n");
}

async function buildMegaera(baseUrl, token, code, report) {
  const kills = report.fights.filter((f) => f.name === "Megaera" && f.kill);
  if (!kills.length) return "No Megaera kills found.";

  const headIds = {};
  for (const [label, subs] of Object.entries(HEAD_KEYS)) {
    const hits = findActorIdsFuzzy(report.masterData.actors, subs);
    headIds[label] = hits.map((h) => h.id).filter((id) => typeof id === "number");
  }

  const lines = ["Megaera - head death times (KILLS ONLY)", "--------------------------------------"];

  for (const fight of kills) {
    const deaths = {};
    for (const label of Object.keys(headIds)) deaths[label] = [];
    const events = await fetchEventsPagedSimple(
      baseUrl,
      token,
      code,
      fight.id,
      fight.startTime,
      fight.endTime,
      "All"
    );
    for (const e of events) {
      const et = norm(e.type || "");
      if (et !== "death" && et !== "destroy") continue;
      const ts = e.timestamp;
      const tid = e.targetID;
      if (typeof ts !== "number" || typeof tid !== "number") continue;
      for (const [label, ids] of Object.entries(headIds)) {
        if (ids.includes(tid)) {
          deaths[label].push(ts);
          break;
        }
      }
    }
    for (const label of Object.keys(deaths)) {
      deaths[label].sort((a, b) => a - b);
    }
    const merged = [];
    for (const [label, tsList] of Object.entries(deaths)) {
      for (const ts of tsList) merged.push([ts, label]);
    }
    merged.sort((a, b) => a[0] - b[0]);

    const dur = mmssFromMs(fight.endTime - fight.startTime);
    lines.push(`\nKill duration: ${dur}   (fight id ${fight.id})`);

    if (merged.length) {
      let pretty = merged.map(([ts, label]) => `${label} ${relMmss(ts, fight.startTime)}`).join(", ");
      const lastDeath = merged[merged.length - 1][0];
      const windowEnd = Math.min(fight.endTime, lastDeath + 10000);
      const dmgEvents = await fetchEventsPagedSimple(
        baseUrl,
        token,
        code,
        fight.id,
        lastDeath,
        windowEnd,
        "DamageDone"
      );
      const dmgByTarget = new Map();
      for (const e of dmgEvents) {
        const et = norm(e.type || "");
        if (et !== "damage") continue;
        const tid = e.targetID;
        if (typeof tid !== "number") continue;
        const amount = typeof e.amount === "number" ? e.amount : 0;
        const absorbed = typeof e.absorbed === "number" ? e.absorbed : 0;
        dmgByTarget.set(tid, (dmgByTarget.get(tid) || 0) + amount + absorbed);
      }
      if (dmgByTarget.size) {
        const [bestTid] = [...dmgByTarget.entries()].sort((a, b) => b[1] - a[1])[0];
        let inferred = null;
        for (const [label, ids] of Object.entries(headIds)) {
          if (ids.includes(bestTid)) {
            inferred = label;
            break;
          }
        }
        if (inferred && inferred !== merged[merged.length - 1][1]) {
          pretty += `, ${inferred} ${relMmss(fight.endTime, fight.startTime)}`;
        }
      }
      lines.push(`  Order   : ${pretty}`);
    } else {
      lines.push("  Order   : -");
    }
  }

  return lines.join("\n");
}

async function buildIronQon(baseUrl, token, code, report, actorById) {
  const kills = report.fights.filter((f) => f.name === "Iron Qon" && f.kill);
  if (!kills.length) return "No Iron Qon kills found.";

  const dogIds = {};
  for (const [label, subs] of Object.entries(DOG_KEYS)) {
    const hits = findActorIdsFuzzy(report.masterData.actors, subs);
    dogIds[label] = hits.map((h) => h.id).filter((id) => typeof id === "number");
  }
  const ironQonHits = findActorIdsFuzzy(report.masterData.actors, ["iron", "qon"]);
  const ironQonId = ironQonHits.find((h) => typeof h.id === "number")?.id || null;

  const lines = [];

  for (const fight of kills) {
    const dur = mmssFromMs(fight.endTime - fight.startTime);
    lines.push(`\nKill duration: ${dur}   (fight id ${fight.id})`);

    let ro25 = null;
    if (ironQonId) {
      const dmgEvents = await fetchEventsPagedSimple(
        baseUrl,
        token,
        code,
        fight.id,
        fight.startTime,
        fight.endTime,
        "DamageDone"
      );
      for (const e of dmgEvents) {
        const et = norm(e.type || "");
        if (et !== "damage") continue;
        const tid = e.targetID;
        const ts = e.timestamp;
        const amt = e.amount;
        if (typeof tid !== "number" || typeof ts !== "number" || typeof amt !== "number") continue;
        if (tid === ironQonId && amt > 0) {
          ro25 = ts;
          break;
        }
      }
    }
    lines.push(`  Ro25%   : ${ro25 ? relMmss(ro25, fight.startTime) : "-"}`);

    let wind = null;
    const debuffs = await fetchEventsPagedSimple(
      baseUrl,
      token,
      code,
      fight.id,
      fight.startTime,
      fight.endTime,
      "Debuffs"
    );
    for (const e of debuffs) {
      const et = norm(e.type || "");
      if (et !== "applydebuff") continue;
      const abilityId = getAbilityId(e);
      if (abilityId !== ABILITIES.windStorm) continue;
      const ts = e.timestamp;
      const tid = e.targetID;
      if (typeof ts !== "number" || typeof tid !== "number") continue;
      if (!isPlayerActor(actorById.get(tid))) continue;
      wind = [ts, tid];
      break;
    }
    lines.push(`  Windstorm : ${wind ? relMmss(wind[0], fight.startTime) : "-"}`);

    let quetHp = null;
    if (wind) {
      const windTs = wind[0];
      const quetIds = dogIds["Quet'Zal"] || [];
      if (quetIds.length) {
        const dmgEvents = await fetchEventsPagedSimple(
          baseUrl,
          token,
          code,
          fight.id,
          fight.startTime,
          windTs,
          "DamageDone"
        );
        let dmg = 0;
        for (const e of dmgEvents) {
          const et = norm(e.type || "");
          if (et !== "damage") continue;
          const tid = e.targetID;
          if (!quetIds.includes(tid)) continue;
          const amt = e.amount;
          if (typeof amt === "number" && amt > 0) dmg += amt;
        }
        dmg = Math.max(0, Math.min(dmg, QUETZAL_MAX_HP));
        quetHp = 100 * (1 - dmg / QUETZAL_MAX_HP);
      }
    }
    lines.push(`  Quetzal HP @ Windstorm : ${quetHp === null ? "-" : `${quetHp.toFixed(1)}% (approx)`}`);

    const deathEvents = await fetchEventsPagedSimple(
      baseUrl,
      token,
      code,
      fight.id,
      fight.startTime,
      fight.endTime,
      "All"
    );
    const deaths = {};
    for (const label of Object.keys(dogIds)) deaths[label] = [];
    for (const e of deathEvents) {
      const et = norm(e.type || "");
      if (et !== "death" && et !== "destroy") continue;
      const ts = e.timestamp;
      const tid = e.targetID;
      if (typeof ts !== "number" || typeof tid !== "number") continue;
      for (const [label, ids] of Object.entries(dogIds)) {
        if (ids.includes(tid)) {
          deaths[label].push(ts);
          break;
        }
      }
    }
    for (const label of Object.keys(deaths)) {
      const times = deaths[label].sort((a, b) => a - b).map((ts) => relMmss(ts, fight.startTime));
      lines.push(`  ${label.padEnd(8)}: ${times.length ? times.join(", ") : "-"}`);
    }
    const merged = [];
    for (const [label, tsList] of Object.entries(deaths)) {
      for (const ts of tsList) merged.push([ts, label]);
    }
    merged.sort((a, b) => a[0] - b[0]);
    if (merged.length) {
      let pretty = merged.map(([ts, label]) => `${label} ${relMmss(ts, fight.startTime)}`).join(", ");
      pretty += `, Iron Qon ${dur}`;
      lines.push(`  Order   : ${pretty}`);
    } else {
      lines.push("  Order   : -");
    }
  }

  return lines.join("\n");
}

async function buildLeiShen(baseUrl, token, code, report) {
  const kills = report.fights.filter((f) => f.name === "Lei Shen" && f.kill);
  if (!kills.length) return "No Lei Shen kills found.";
  const lines = ["Lei Shen - intermission times (KILLS ONLY)", "-----------------------------------------", "Marker: cast ability 137045 (Supercharge Conduits)", ""];

  for (const fight of kills) {
    const casts = await fetchEventsPagedSimple(
      baseUrl,
      token,
      code,
      fight.id,
      fight.startTime,
      fight.endTime,
      "Casts",
      ABILITIES.superchargeConduits
    );
    const times = casts
      .filter((e) => norm(e.type || "") === "startcast")
      .map((e) => e.timestamp)
      .filter((ts) => typeof ts === "number")
      .sort((a, b) => a - b);
    const marks = times.filter((_, idx) => idx % 2 === 0);
    lines.push(`Kill duration: ${mmssFromMs(fight.endTime - fight.startTime)}   (fight id ${fight.id})`);
    lines.push(`  Intermission 1: ${marks[0] ? relMmss(marks[0], fight.startTime) : "-"}`);
    lines.push(`  Intermission 2: ${marks[1] ? relMmss(marks[1], fight.startTime) : "-"}`);
    if (marks.length > 2) {
      const extra = marks.slice(2).map((ts) => relMmss(ts, fight.startTime)).join(", ");
      lines.push(`  Extra intermissions: ${extra}`);
    }
    lines.push("");
  }
  return lines.join("\n");
}

async function buildTortos(baseUrl, token, code, report) {
  const kills = report.fights.filter((f) => f.name === "Tortos" && f.kill);
  if (!kills.length) return "No 'Tortos' kills found.";

  const tortosHits = findActorIdsFuzzy(report.masterData.actors, ["tortos"]);
  const tortosIds = tortosHits.map((h) => h.id).filter((id) => typeof id === "number");
  if (!tortosIds.length) {
    return "Could not find any Tortos actor IDs from masterData.actors.";
  }

  const lines = ["Tortos - Shell Concussion stats (KILLS ONLY)", "--------------------------------------------"];

  for (const fight of kills) {
    const events = await fetchEventsPagedHostile(
      baseUrl,
      token,
      code,
      fight.id,
      fight.startTime,
      fight.endTime,
      "Debuffs",
      "Enemies",
      true
    );

    const rows = [];
    for (const e of events) {
      const et = norm(e.type || "");
      if (!AURA_TYPES.has(et)) continue;
      const tid = getTargetId(e);
      if (!tortosIds.includes(tid)) continue;
      const ts = e.timestamp;
      if (typeof ts !== "number") continue;
      const abilityId = getAbilityId(e);
      if (abilityId !== ABILITIES.shellConcussion) continue;
      rows.push([ts, et]);
    }
    rows.sort((a, b) => a[0] - b[0]);

    let active = false;
    let activeStart = null;
    let uptime = 0;
    let applications = 0;
    const appTimes = [];

    const isApply = (t) => ["applydebuff", "applydebuffstack", "applybuff", "applybuffstack"].includes(t);
    const isRefresh = (t) => ["refreshdebuff", "refreshdebuffstack", "refreshbuff", "refreshbuffstack"].includes(t);
    const isRemove = (t) => ["removedebuff", "removebuff"].includes(t);

    for (const [ts, et] of rows) {
      if (isApply(et)) {
        if (!active) {
          applications += 1;
          appTimes.push(ts);
          active = true;
          activeStart = ts;
        }
      } else if (isRefresh(et)) {
        if (!active) {
          applications += 1;
          appTimes.push(ts);
          active = true;
          activeStart = ts;
        }
      } else if (isRemove(et)) {
        if (active && activeStart !== null) {
          uptime += Math.max(0, ts - activeStart);
        }
        active = false;
        activeStart = null;
      }
    }
    if (active && activeStart !== null) {
      uptime += Math.max(0, fight.endTime - activeStart);
    }

    const fightLen = fight.endTime - fight.startTime;
    const uptimePct = fightLen > 0 ? (uptime / fightLen) * 100 : 0;

    lines.push(`\nKill duration: ${mmssFromMs(fightLen)}   (fight id ${fight.id})`);
    if (!rows.length) {
      lines.push("  Found 0 matching aura events on Tortos (Enemies/Debuffs stream).");
      lines.push("  SANITY sample of Debuffs aura events targeting Tortos:");
      let shown = 0;
      for (const e of events) {
        const et = norm(e.type || "");
        if (!AURA_TYPES.has(et)) continue;
        const tid = getTargetId(e);
        if (!tortosIds.includes(tid)) continue;
        const abName = getAbilityName(e) || "<?>";
        const abId = getAbilityId(e);
        lines.push(`  SANITY: ${et.padEnd(18)} ts=${e.timestamp}  ability='${abName}' id=${abId}`);
        shown += 1;
        if (shown >= 12) break;
      }
      if (shown === 0) {
        lines.push("  SANITY: saw ZERO Debuffs aura events targeting Tortos in Enemies stream.");
      }

      const counter = new Map();
      for (const e of events) {
        const et = norm(e.type || "");
        if (!AURA_TYPES.has(et)) continue;
        const tid = getTargetId(e);
        if (!tortosIds.includes(tid)) continue;
        const name = getAbilityName(e) || "<?>";
        const id = getAbilityId(e);
        const key = `${name} (id=${id})`;
        counter.set(key, (counter.get(key) || 0) + 1);
      }
      lines.push("\n  Top aura names applied to Tortos (Enemies/Debuffs stream):");
      const top = [...counter.entries()].sort((a, b) => b[1] - a[1]).slice(0, 25);
      if (!top.length) {
        lines.push("    (none)");
      } else {
        for (const [name, cnt] of top) {
          lines.push(`    ${name.padEnd(45)}  ${cnt}`);
        }
      }
      continue;
    }

    const timesStr = appTimes.map((t) => relMmss(t, fight.startTime)).join(", ");
    lines.push(`  Applications: ${applications} (${timesStr})`);
    lines.push(`  Uptime      : ${mmssFromMs(uptime)} (${uptimePct.toFixed(1)}%)`);
  }

  return lines.join("\n");
}

async function runAnalysis() {
  clearResults();
  const rawReport = reportInput.value.trim();
  const clientId = clientIdInput.value.trim();
  const clientSecret = clientSecretInput.value.trim();
  const reportCode = parseReportCode(rawReport) || DEFAULTS.reportCode;
  if (!reportCode) {
    setStatus("Enter a report URL or code.");
    return;
  }
  if (!clientId || !clientSecret) {
    setStatus("Client ID and Client Secret are required.");
    return;
  }

  runBtn.disabled = true;
  setStatus("Requesting access token...");
  const baseUrl = parseBaseUrl(rawReport);

  try {
    const token = await fetchToken(clientId, clientSecret, baseUrl);
    setStatus("Fetching report data...");
    const report = await fetchReport(baseUrl, token, reportCode);
    const actors = report.masterData?.actors || [];
    const playerIds = new Set(
      actors
        .filter((a) => a && (norm(a.type) === "player" || norm(a.subType) === "player"))
        .map((a) => a.id)
        .filter((id) => typeof id === "number")
    );
    const actorById = buildActorById(actors);

    setStatus("Generating outputs...");
    const overall = await buildOverall(baseUrl, token, reportCode, report, playerIds);
    addCard("Overall", `Report: ${report.title} (${reportCode})`, overall);

    const council = await buildCouncil(baseUrl, token, reportCode, report);
    addCard("Council of Elders", "Death order for elder bosses on kill pulls.", council);

    const megaera = await buildMegaera(baseUrl, token, reportCode, report);
    addCard("Megaera", "Head death order and inferred final head.", megaera);

    const ironQon = await buildIronQon(baseUrl, token, reportCode, report, actorById);
    addCard("Iron Qon", "Dog death timing and windstorm markers.", ironQon);

    const leiShen = await buildLeiShen(baseUrl, token, reportCode, report);
    addCard("Lei Shen", "Intermission timing from Supercharge Conduits casts.", leiShen);

    const tortos = await buildTortos(baseUrl, token, reportCode, report);
    addCard("Tortos", "Shell Concussion applications and uptime.", tortos);

    setStatus("Done.");
  } catch (err) {
    setStatus(err.message || "Something went wrong.");
  } finally {
    runBtn.disabled = false;
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  runAnalysis();
});

clearBtn.addEventListener("click", () => {
  reportInput.value = "";
  clientIdInput.value = "";
  clientSecretInput.value = "";
  clearResults();
  setStatus("Ready to analyze a report.");
});
