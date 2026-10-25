"use strict";

// Each Claude family gets its own color. Any other family is gray.
const CLAUDE_FAMILIES = ["Fable", "Opus", "Sonnet", "Haiku"];
const SLOT_LABEL = { medium: "med" };
const METRICS = {
  acc: { label: "accuracy", format: v => pct(v), log: false },
  cost: { label: "$/problem", format: v => dollars(v), log: true },
  tok_out: { label: "output tok", format: v => count(v), log: true },
  ms: { label: "latency", format: v => duration(v), log: true },
};

const state = {
  data: null,
  ds: "main",
  matrixMetric: "acc",
  scatterX: "cost",
  minN: "10",
  hidden: new Set(),
  selected: null,
  hovered: null,
  sort: { key: "acc", dir: -1 },
};

// formatting

function pct(v, digits = 1) {
  return v == null ? "–" : `${(v * 100).toFixed(digits)}%`;
}

function dollars(v) {
  if (v == null) return "–";
  if (v >= 100) return `$${v.toFixed(0)}`;
  if (v >= 1) return `$${v.toFixed(2)}`;
  if (v >= 0.01) return `$${v.toFixed(3)}`;
  return `$${v.toPrecision(2)}`;
}

function count(v) {
  if (v == null) return "–";
  if (v >= 1e4) return `${(v / 1e3).toFixed(0)}k`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}k`;
  return v.toFixed(0);
}

function duration(ms) {
  if (ms == null) return "–";
  if (ms >= 6e4) return `${(ms / 6e4).toFixed(1)}m`;
  return `${(ms / 1e3).toFixed(ms < 1e4 ? 1 : 0)}s`;
}

function wilson(k, n, z = 1.96) {
  if (!n) return [0, 0];
  const p = k / n, d = 1 + z * z / n;
  const center = (p + z * z / (2 * n)) / d;
  const half = (z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d;
  return [Math.max(0, center - half), Math.min(1, center + half)];
}

// DOM

const $ = sel => document.querySelector(sel);
const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const isDark = () => getComputedStyle(document.documentElement).colorScheme === "dark";

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "style") Object.assign(el.style, v);
    else if (v != null && v !== false) el.setAttribute(k, v === true ? "" : v);
  }
  el.append(...children.flat().filter(c => c != null && c !== false));
  return el;
}

function svg(tag, attrs = {}, text) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  if (text != null) el.textContent = text;
  return el;
}

function saved(key, fallback) {
  try {
    const v = localStorage.getItem(`vpct.${key}`);
    return v == null ? fallback : JSON.parse(v);
  } catch {
    return fallback;
  }
}

function save(key, value) {
  try {
    localStorage.setItem(`vpct.${key}`, JSON.stringify(value));
  } catch {}
}

// data

const keyOf = (model, level) => `${model.id}|${level.key}`;
const shownModels = () => state.data.models.filter(m => m.planned);
const visibleModels = () => shownModels().filter(m => !state.hidden.has(m.id));
const families = () => [...new Set(shownModels().map(m => m.family))];

function familyColor(family) {
  return css(CLAUDE_FAMILIES.includes(family) ? `--${family.toLowerCase()}` : "--other");
}

function totalProblems(ds) {
  const sets = state.data.datasets;
  return ds === "pooled" ? Object.values(sets).reduce((n, ps) => n + ps.length, 0) : (sets[ds] || []).length;
}

// Results for each model and level. "pooled" adds main and redux together.
function cellsFor(ds) {
  const out = new Map();
  for (const c of state.data.cells) {
    if (ds !== "pooled" && c.dataset !== ds) continue;
    const key = `${c.model}|${c.level}`;
    const prev = out.get(key);
    if (!prev) {
      out.set(key, { ...c });
      continue;
    }
    const n = prev.n + c.n;
    const weighted = f => (prev[f] == null ? c[f] : c[f] == null ? prev[f] : (prev[f] * prev.n + c[f] * c.n) / n);
    out.set(key, {
      ...prev,
      n,
      correct: prev.correct + c.correct,
      tok_in: weighted("tok_in"),
      tok_out: weighted("tok_out"),
      tok_think: weighted("tok_think"),
      cost: weighted("cost"),
      ms: weighted("ms"),
      ms_p50: null,
      cost_total: prev.cost_total + c.cost_total,
      cost_cli_total: prev.cost_cli_total + c.cost_cli_total,
    });
  }
  for (const c of out.values()) {
    c.acc = c.n ? c.correct / c.n : null;
    [c.lo, c.hi] = wilson(c.correct, c.n);
  }
  return out;
}

function points(ds, minN = +state.minN) {
  const cells = cellsFor(ds);
  const pts = [];
  for (const model of visibleModels()) {
    for (const level of model.levels) {
      const cell = cells.get(keyOf(model, level));
      if (cell && cell.n >= Math.max(1, minN)) pts.push({ model, level, cell, key: keyOf(model, level) });
    }
  }
  return pts;
}

// tooltip

const tip = $("#tip");

function showTip(content, ev) {
  tip.replaceChildren(...content);
  tip.hidden = false;
  const box = tip.getBoundingClientRect();
  let x = ev.clientX + 14, y = ev.clientY + 14;
  if (x + box.width > innerWidth - 8) x = ev.clientX - box.width - 14;
  if (y + box.height > innerHeight - 8) y = ev.clientY - box.height - 14;
  tip.style.left = `${Math.max(8, x)}px`;
  tip.style.top = `${Math.max(8, y)}px`;
}

const hideTip = () => { tip.hidden = true; };

function tipTable(title, rows) {
  return [
    h("div", { class: "t" }, title),
    h("table", {}, rows.map(([k, v, extra]) => h("tr", {}, h("td", {}, k), h("td", {}, v, extra ? h("span", { class: "k" }, ` ${extra}`) : null)))),
  ];
}

function levelLabel(model, level) {
  return `${model.label} · ${level.mtt > 0 ? `${level.key} budget` : level.key}`;
}

function configTip(model, level, cell, ds) {
  const rows = [];
  if (cell && cell.n) {
    rows.push(["accuracy", pct(cell.acc), `${pct(cell.lo, 0)}–${pct(cell.hi, 0)}`]);
    rows.push(["n", `${cell.n}/${totalProblems(ds)}`]);
    rows.push(["output tok", count(cell.tok_out), `think ${count(cell.tok_think)}`]);
    rows.push(["input tok", count(cell.tok_in)]);
    rows.push(["$/problem", dollars(cell.cost)]);
    rows.push(["Σ $", dollars(cell.cost_total), `cli ${dollars(cell.cost_cli_total)}`]);
    rows.push(["latency", duration(cell.ms), cell.ms_p50 ? `p50 ${duration(cell.ms_p50)}` : null]);
  } else {
    rows.push(["n", `0/${totalProblems(ds)}`]);
  }
  const setting = level.mtt === 0 ? "thinking off" : level.mtt ? `budget ${level.mtt}` : `effort ${level.effort}`;
  rows.push(["config", setting]);
  return tipTable(levelLabel(model, level), rows);
}

// Each family also gets its own marker shape, so color isn't the only way to tell them apart.

function shapePath(family, x, y, r) {
  switch (family) {
    case "Opus":
      return `M${x - r},${y}a${r},${r} 0 1,0 ${2 * r},0a${r},${r} 0 1,0 ${-2 * r},0`;
    case "Sonnet": {
      const s = r * 0.88;
      return `M${x - s},${y - s}h${2 * s}v${2 * s}h${-2 * s}z`;
    }
    case "Haiku": {
      const s = r * 1.15;
      return `M${x},${y - s}L${x + s},${y + s * 0.8}L${x - s},${y + s * 0.8}z`;
    }
    case "Fable": {
      const s = r * 1.2;
      return `M${x},${y - s}L${x + s},${y}L${x},${y + s}L${x - s},${y}z`;
    }
    default: {
      const a = r * 1.1, w = r * 0.42;
      return `M${x - w},${y - a}h${2 * w}v${a - w}h${a - w}v${2 * w}h${w - a}v${a - w}h${-2 * w}v${w - a}h${w - a}v${-2 * w}h${a - w}z`;
    }
  }
}

function shapeIcon(family, size = 12) {
  const el = svg("svg", { width: size, height: size, viewBox: `0 0 ${size} ${size}`, "aria-hidden": "true" });
  el.append(svg("path", { d: shapePath(family, size / 2, size / 2, size * 0.36), fill: familyColor(family) }));
  return el;
}

// controls

function segmented(container, key, onChange) {
  const el = typeof container === "string" ? $(container) : container;
  el.setAttribute("role", "radiogroup");
  const buttons = [...el.querySelectorAll("button")];
  const sync = () => buttons.forEach(b => b.setAttribute("aria-checked", String(b.dataset.v === state[key])));
  for (const b of buttons) {
    b.setAttribute("role", "radio");
    b.addEventListener("click", () => {
      state[key] = b.dataset.v;
      save(key, state[key]);
      sync();
      onChange();
    });
  }
  sync();
}

function setHidden(ids) {
  state.hidden = new Set(ids);
  save("hidden", [...state.hidden]);
  renderAll();
}

function renderFilters() {
  const chips = [];
  for (const family of families()) {
    const models = shownModels().filter(m => m.family === family);
    const anyOn = models.some(m => !state.hidden.has(m.id));
    const allOn = models.every(m => !state.hidden.has(m.id));
    chips.push(h("button", {
      class: "chip fam", "aria-pressed": String(anyOn),
      onclick: () => setHidden(allOn ? [...state.hidden, ...models.map(m => m.id)]
                                     : [...state.hidden].filter(id => !models.some(m => m.id === id))),
    }, shapeIcon(family), family));

    for (const model of models) {
      let timer;
      chips.push(h("button", {
        class: "chip", "aria-pressed": String(!state.hidden.has(model.id)), title: model.id,
        // click hides or shows the model; double-click shows only it, double-click again shows all
        onclick: () => {
          clearTimeout(timer);
          timer = setTimeout(() => {
            const next = new Set(state.hidden);
            next.has(model.id) ? next.delete(model.id) : next.add(model.id);
            setHidden(next);
          }, 220);
        },
        ondblclick: () => {
          clearTimeout(timer);
          const solo = shownModels().every(m => (m.id === model.id) !== state.hidden.has(m.id));
          setHidden(solo ? [] : shownModels().filter(m => m.id !== model.id).map(m => m.id));
        },
      }, model.version));
    }
  }
  const minN = h("div", { class: "seg small minn", "aria-label": "Minimum problems" },
    ["1", "10", "50"].map(v => h("button", { "data-v": v }, `n ≥ ${v}`)));
  $("#filters").replaceChildren(...chips, minN);
  segmented(minN, "minN", renderAll);
}

function renderUsage() {
  const { usage, projection } = state.data;
  const planned = new Set(shownModels().map(m => m.id));
  const done = state.data.cells.reduce((n, c) => n + (planned.has(c.model) ? c.n : 0), 0);
  const parts = [];
  if (usage) parts.push(["5h ", pct(usage.five_hour, 0), " · 7d ", pct(usage.seven_day, 0)]);
  parts.push([done.toLocaleString(), " done · ", projection.remaining.toLocaleString(), " left"]);
  if (projection.cost_api) {
    const share = projection.seven_day_pct ? ` · ≈${projection.seven_day_pct}% of 7d` : "";
    parts.push([`≈${dollars(projection.cost_api)} list${share}`]);
  }
  $("#usage").replaceChildren(...parts.flatMap((p, i) => [i ? "  ·  " : "", ...p]));
}

// matrix

function rampColors() {
  return [0, 1, 2, 3, 4, 5, 6].map(i => css(`--q${i}`));
}

function inkOn(bin) {
  if (isDark()) return bin >= 4 ? "#0b0b0b" : "#f0efec";
  return bin >= 3 ? "#ffffff" : "#0b0b0b";
}

function scaleFor(metric, values) {
  if (metric === "acc") {
    return { lo: 1 / 3, hi: 1, bin: v => Math.max(0, Math.min(6, Math.floor(((v - 1 / 3) / (2 / 3)) * 7))) };
  }
  const vs = values.filter(v => v != null && v > 0);
  if (!vs.length) return { lo: null, hi: null, bin: () => 0 };
  const lo = Math.log(Math.min(...vs)), hi = Math.log(Math.max(...vs));
  return {
    lo: Math.exp(lo), hi: Math.exp(hi),
    bin: v => (hi === lo ? 3 : Math.max(0, Math.min(6, Math.floor(((Math.log(v) - lo) / (hi - lo)) * 6.999)))),
  };
}

function renderMatrix() {
  const metric = METRICS[state.matrixMetric];
  const cells = cellsFor(state.ds);
  const total = totalProblems(state.ds);
  const models = visibleModels();
  const ramp = rampColors();
  const scale = scaleFor(state.matrixMetric, models.flatMap(m => m.levels.map(l => cells.get(keyOf(m, l))?.[state.matrixMetric])));
  const slots = state.data.slots.map((_, i) => i).filter(i => models.some(m => m.levels.some(l => l.slot === i)));

  const grid = h("div", { class: "mx", style: { gridTemplateColumns: `minmax(110px, auto) repeat(${slots.length}, minmax(64px, 1fr))` } },
    h("div"), slots.map(i => h("div", { class: "hd" }, SLOT_LABEL[state.data.slots[i]] || state.data.slots[i])));

  for (const family of families()) {
    const rows = models.filter(m => m.family === family);
    if (!rows.length) continue;
    grid.append(h("div", { class: "fam" }, family));
    for (const model of rows) {
      grid.append(h("div", { class: "name", title: model.id }, shapeIcon(family), model.label));
      for (const slot of slots) {
        const level = model.levels.find(l => l.slot === slot);
        if (!level) {
          grid.append(h("div", { class: "cell na" }));
          continue;
        }
        const key = keyOf(model, level);
        const cell = cells.get(key);
        const tag = level.mtt > 0 ? h("span", { class: "tag" }, level.key) : null;
        const el = h("div", {
          class: `cell${cell && cell.n ? "" : " todo"}${state.selected === key ? " sel" : ""}`,
          onmousemove: ev => showTip(configTip(model, level, cell, state.ds), ev),
          onmouseleave: hideTip,
          onclick: () => select(key),
        }, tag);
        if (cell && cell.n) {
          const value = cell[state.matrixMetric];
          const bin = value == null ? 0 : scale.bin(value);
          el.style.background = ramp[bin];
          el.style.color = inkOn(bin);
          const sub = cell.n < total ? `${cell.n}/${total}`
                    : state.matrixMetric === "acc" ? `±${((cell.hi - cell.lo) * 50).toFixed(0)}` : pct(cell.acc, 0);
          el.append(h("span", { class: "v" }, metric.format(value)), h("span", { class: "s" }, sub));
        } else {
          el.append(h("span", { class: "s" }, "–"));
        }
        grid.append(el);
      }
    }
  }

  const legend = h("div", { class: "scale" },
    h("span", {}, `${metric.format(scale.lo)}${state.matrixMetric === "acc" ? " (chance)" : ""}`),
    h("span", { class: "ramp" }, ramp.map(c => h("span", { style: { background: c } }))),
    h("span", {}, metric.format(scale.hi)));
  $("#matrix").replaceChildren(grid, legend);
}

// charts

function logTicks(lo, hi) {
  const ticks = [];
  for (let e = Math.floor(Math.log10(lo)); e <= Math.ceil(Math.log10(hi)); e++) {
    for (const m of [1, 2, 5]) {
      const v = m * 10 ** e;
      if (v >= lo && v <= hi) ticks.push(v);
    }
  }
  return ticks;
}

function linearTicks(lo, hi, step) {
  const ticks = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) ticks.push(+v.toFixed(6));
  return ticks;
}

function chart(container, width, height, margin) {
  const root = svg("svg", { viewBox: `0 0 ${width} ${height}`, role: "img" });
  container.replaceChildren(root);
  return { root, width, height, m: margin, iw: width - margin.l - margin.r, ih: height - margin.t - margin.b };
}

function emptyChart(container, message) {
  const c = chart(container, Math.max(280, container.clientWidth), 200, { l: 0, r: 0, t: 0, b: 0 });
  c.root.append(svg("text", { x: c.width / 2, y: 100, "text-anchor": "middle" }, message));
}

function drawMarks(root, pts, xy) {
  const surface = css("--surface"), ink = css("--ink");
  for (const p of pts) {
    const [x, y] = xy(p);
    const selected = state.selected === p.key;
    root.append(svg("path", {
      d: shapePath(p.model.family, x, y, selected ? 6 : 4.5),
      fill: familyColor(p.model.family),
      stroke: selected ? ink : surface,
      "stroke-width": 2,
      opacity: state.hovered && state.hovered !== p.model.id ? 0.25 : 1,
    }));
  }
}

function nearest(pts, xy, x, y, radius = 28) {
  let best = null, bestD = radius * radius;
  for (const p of pts) {
    const [px, py] = xy(p);
    const d = (px - x) ** 2 + (py - y) ** 2;
    if (d < bestD) {
      bestD = d;
      best = p;
    }
  }
  return best;
}

function hover(root, pts, xy, rerender, tipFor) {
  const local = ev => {
    const box = root.getBoundingClientRect(), vb = root.viewBox.baseVal;
    return [((ev.clientX - box.left) * vb.width) / box.width, ((ev.clientY - box.top) * vb.height) / box.height];
  };
  root.addEventListener("mousemove", ev => {
    const p = nearest(pts, xy, ...local(ev));
    const model = p ? p.model.id : null;
    if (model !== state.hovered) {
      state.hovered = model;
      rerender();
      return;
    }
    p ? showTip(tipFor(p), ev) : hideTip();
  });
  root.addEventListener("mouseleave", () => {
    hideTip();
    if (state.hovered) {
      state.hovered = null;
      rerender();
    }
  });
  root.addEventListener("click", ev => {
    const p = nearest(pts, xy, ...local(ev));
    if (p) select(p.key);
  });
}

function renderScatter() {
  const container = $("#scatter");
  const x = state.scatterX;
  $("#sc-xlabel").textContent = x === "cost" ? "cost" : METRICS[x].label;
  const pts = points(state.ds).filter(p => p.cell[x] > 0);
  if (!pts.length) return emptyChart(container, "no data");

  const c = chart(container, Math.max(320, container.clientWidth), 400, { l: 44, r: 28, t: 10, b: 34 });
  const xs = pts.map(p => p.cell[x]);
  const x0 = Math.min(...xs) / 1.4, x1 = Math.max(...xs) * 1.4;
  const y0 = Math.max(0, Math.floor(Math.min(1 / 3, ...pts.map(p => p.cell.lo)) * 10) / 10);
  const X = v => c.m.l + ((Math.log(v) - Math.log(x0)) / (Math.log(x1) - Math.log(x0))) * c.iw;
  const Y = v => c.m.t + (1 - (v - y0) / (1 - y0)) * c.ih;
  const xy = p => [X(p.cell[x]), Y(p.cell.acc)];
  const bottom = c.m.t + c.ih, right = c.m.l + c.iw;

  for (const t of linearTicks(y0, 1, 0.1)) {
    c.root.append(svg("line", { x1: c.m.l, x2: right, y1: Y(t), y2: Y(t), class: "gridl" }));
    c.root.append(svg("text", { x: c.m.l - 6, y: Y(t) + 4, "text-anchor": "end" }, `${(t * 100).toFixed(0)}%`));
  }
  for (const t of logTicks(x0, x1)) {
    c.root.append(svg("line", { x1: X(t), x2: X(t), y1: bottom, y2: bottom + 4, class: "axisl" }));
    c.root.append(svg("text", { x: X(t), y: bottom + 17, "text-anchor": "middle" }, METRICS[x].format(t)));
  }
  c.root.append(svg("line", { x1: c.m.l, x2: right, y1: bottom, y2: bottom, class: "axisl" }));
  if (1 / 3 >= y0) {
    c.root.append(svg("line", { x1: c.m.l, x2: right, y1: Y(1 / 3), y2: Y(1 / 3), class: "ref" }));
    c.root.append(svg("text", { x: right, y: Y(1 / 3) - 4, "text-anchor": "end" }, "chance"));
  }

  // line through the best accuracy you can get at each cost
  let best = -1, path = "";
  for (const p of [...pts].sort((a, b) => a.cell[x] - b.cell[x])) {
    if (p.cell.acc <= best) continue;
    const [px, py] = xy(p);
    path += path ? `H${px}V${py}` : `M${px},${py}`;
    best = p.cell.acc;
  }
  c.root.append(svg("path", { d: `${path}H${right}`, class: "front" }));

  const byModel = new Map();
  for (const p of pts) byModel.set(p.model.id, [...(byModel.get(p.model.id) || []), p]);
  for (const [id, ps] of byModel) {
    ps.sort((a, b) => a.level.slot - b.level.slot);
    const dim = state.hovered && state.hovered !== id;
    const color = familyColor(ps[0].model.family);
    for (const p of ps) {
      const [px] = xy(p);
      c.root.append(svg("line", { x1: px, x2: px, y1: Y(p.cell.lo), y2: Y(p.cell.hi), stroke: color, "stroke-width": 1, opacity: dim ? 0.05 : 0.22 }));
    }
    if (ps.length > 1) {
      c.root.append(svg("polyline", {
        points: ps.map(p => xy(p).join(",")).join(" "), fill: "none", stroke: color,
        "stroke-width": state.hovered === id ? 2 : 1.5, opacity: dim ? 0.12 : 0.6, "stroke-linejoin": "round",
      }));
    }
  }
  drawMarks(c.root, pts, xy);
  for (const [id, ps] of byModel) {
    if (state.hovered && state.hovered !== id) continue;
    const last = ps[ps.length - 1], [px, py] = xy(last);
    c.root.append(svg("text", { x: px + 8, y: py + 4, class: "lbl" }, last.model.version));
  }
  hover(c.root, pts, xy, renderScatter, p => configTip(p.model, p.level, p.cell, state.ds));
}

function renderLegend() {
  const frontier = svg("svg", { width: 18, height: 10, "aria-hidden": "true" });
  frontier.append(svg("path", { d: "M1,8H9V2H17", class: "front" }));
  $("#legend").replaceChildren(...families().map(f => h("span", {}, shapeIcon(f), f)), h("span", {}, frontier, "frontier"));
}

function renderSplit() {
  const container = $("#split");
  const main = cellsFor("main"), redux = cellsFor("redux");
  const minN = Math.max(1, +state.minN);
  const pts = [];
  for (const model of visibleModels()) {
    for (const level of model.levels) {
      const key = keyOf(model, level), a = main.get(key), b = redux.get(key);
      if (a?.n >= minN && b?.n >= minN) pts.push({ model, level, key, cell: a, redux: b });
    }
  }
  if (!pts.length) return emptyChart(container, "no data");

  const width = Math.max(280, container.clientWidth);
  const c = chart(container, width, Math.min(400, width), { l: 44, r: 12, t: 10, b: 34 });
  const lo = Math.max(0, Math.floor(Math.min(1 / 3, ...pts.flatMap(p => [p.cell.acc, p.redux.acc])) * 10) / 10);
  const X = v => c.m.l + ((v - lo) / (1 - lo)) * c.iw;
  const Y = v => c.m.t + (1 - (v - lo) / (1 - lo)) * c.ih;
  const xy = p => [X(p.cell.acc), Y(p.redux.acc)];
  const bottom = c.m.t + c.ih;

  for (const t of linearTicks(lo, 1, 0.1)) {
    c.root.append(svg("line", { x1: c.m.l, x2: c.m.l + c.iw, y1: Y(t), y2: Y(t), class: "gridl" }));
    c.root.append(svg("text", { x: c.m.l - 6, y: Y(t) + 4, "text-anchor": "end" }, `${(t * 100).toFixed(0)}%`));
    c.root.append(svg("text", { x: X(t), y: bottom + 17, "text-anchor": "middle" }, `${(t * 100).toFixed(0)}%`));
  }
  c.root.append(svg("line", { x1: X(lo), y1: Y(lo), x2: X(1), y2: Y(1), class: "ref" }));
  c.root.append(svg("line", { x1: c.m.l, x2: c.m.l + c.iw, y1: bottom, y2: bottom, class: "axisl" }));
  c.root.append(svg("text", { x: c.m.l + c.iw, y: bottom + 30, "text-anchor": "end" }, "main →"));
  c.root.append(svg("text", { x: c.m.l + 4, y: c.m.t + 10 }, "↑ redux"));
  drawMarks(c.root, pts, xy);
  hover(c.root, pts, xy, renderSplit, p => tipTable(levelLabel(p.model, p.level), [
    ["main", pct(p.cell.acc), `n ${p.cell.n}`],
    ["redux", pct(p.redux.acc), `n ${p.redux.n}`],
    ["Δ", `${((p.redux.acc - p.cell.acc) * 100).toFixed(1)} pt`],
  ]));
}

// problems grid

function renderProblems() {
  const container = $("#problems");
  container.replaceChildren();
  const sets = state.ds === "pooled" ? Object.keys(state.data.datasets) : [state.ds];
  for (const ds of sets) {
    const problems = state.data.datasets[ds] || [];
    const preds = state.data.outcomes[ds] || {};
    const rows = points(ds).filter(p => preds[p.key]).map(p => ({ ...p, preds: preds[p.key] }));
    if (!rows.length) continue;
    rows.sort((a, b) => b.cell.acc - a.cell.acc);
    // easiest problems first, problems nobody has run yet last
    const cols = problems.map((problem, i) => {
      const ran = rows.filter(r => r.preds[i] != null);
      const right = ran.filter(r => r.preds[i] === problem.answer).length;
      return { i, problem, ran: ran.length, solved: ran.length ? right / ran.length : -1 };
    }).sort((a, b) => b.solved - a.solved || a.problem.id - b.problem.id);

    const canvas = h("canvas");
    container.append(h("div", { class: "ds" }, ds), canvas);
    const labelW = 128, cellW = Math.max(4, Math.floor((Math.max(480, container.clientWidth) - labelW) / cols.length));
    const cellH = 9, gap = 2, width = labelW + cols.length * cellW, height = rows.length * (cellH + gap) + 2;
    const dpr = devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    ctx.font = `10px ${css("--font")}`;
    ctx.textBaseline = "middle";
    const colors = { right: css("--ok"), wrong: css("--bad"), none: css("--warn"), label: css("--ink-2"), selected: css("--ink") };
    rows.forEach((row, r) => {
      const y = r * (cellH + gap);
      ctx.fillStyle = row.key === state.selected ? colors.selected : colors.label;
      ctx.fillText(`${row.model.label} ${row.level.key}`, 0, y + cellH / 2 + 0.5);
      cols.forEach((col, c) => {
        const pred = row.preds[col.i];
        if (pred == null) return;
        ctx.fillStyle = pred === 0 ? colors.none : pred === col.problem.answer ? colors.right : colors.wrong;
        ctx.fillRect(labelW + c * cellW, y, cellW - gap, cellH);
      });
    });

    const at = ev => {
      const box = canvas.getBoundingClientRect();
      const c = Math.floor((ev.clientX - box.left - labelW) / cellW);
      const r = Math.floor((ev.clientY - box.top) / (cellH + gap));
      return c >= 0 && c < cols.length ? { col: cols[c], row: rows[r] } : null;
    };
    canvas.addEventListener("mousemove", ev => {
      const hit = at(ev);
      if (!hit) return hideTip();
      const { col, row } = hit;
      const pred = row?.preds[col.i];
      const result = pred == null ? "not run" : pred === 0 ? "no answer" : `${pred} ${pred === col.problem.answer ? "✓" : "✗"}`;
      showTip(tipTable(`${ds} #${col.problem.id} · answer ${col.problem.answer}`, [
        row ? [`${row.model.label} ${row.level.key}`, result] : null,
        ["solved by", col.ran ? pct(col.solved, 0) : "–", `of ${col.ran}`],
      ].filter(Boolean)), ev);
    });
    canvas.addEventListener("mouseleave", hideTip);
    canvas.addEventListener("click", ev => {
      const hit = at(ev);
      if (hit) openProblem(ds, hit.col.problem, hit.col.i, rows);
    });
  }
  if (!container.children.length) container.append(h("span", { class: "muted" }, "no data"));
}

function imageUrl(ds, id) {
  if (state.data.images === "local") return `img/${ds}/${id}.png`;
  return `https://huggingface.co/datasets/${state.data.image_repos[ds]}/resolve/main/sim_${id}_initial.png`;
}

function openProblem(ds, problem, index, rows) {
  const answered = { 1: [], 2: [], 3: [], 0: [] };
  for (const row of rows) {
    const pred = row.preds[index];
    if (pred != null) answered[pred].push(row);
  }
  const ran = Object.values(answered).reduce((n, rs) => n + rs.length, 0) || 1;
  const buckets = [1, 2, 3, 0].filter(b => b || answered[0].length);
  $("#panel-body").replaceChildren(
    h("h3", {}, `${ds} #${problem.id} · answer ${problem.answer}`),
    h("img", { alt: `${ds} problem ${problem.id}`, src: imageUrl(ds, problem.id) }),
    h("div", { class: "bars" }, buckets.flatMap(b => [
      h("span", {}, b === 0 ? "none" : `bucket ${b}`),
      h("span", { class: `b${b === problem.answer ? " ans" : ""}`, style: { width: `${(answered[b].length / ran) * 100}%` } }),
      h("span", {}, String(answered[b].length)),
    ])),
    buckets.filter(b => answered[b].length).flatMap(b => [
      h("h3", {}, b === 0 ? "no answer" : `said ${b}${b === problem.answer ? " ✓" : ""}`),
      h("div", { class: "who" }, answered[b].map(r => h("div", {}, `${r.model.label} ${r.level.key}`))),
    ]),
  );
  $("#panel").hidden = false;
}

// table

const COLUMNS = [
  { key: "model", label: "model", value: p => p.model.label, sortValue: p => state.data.models.indexOf(p.model) },
  { key: "level", label: "level", value: p => p.level.key, sortValue: p => p.level.slot },
  { key: "n", label: "n", value: p => p.cell.n, format: String },
  { key: "acc", label: "acc", value: p => p.cell.acc, format: v => pct(v) },
  { key: "ci", label: "95% CI", value: p => p.cell.lo, format: (_, p) => `${pct(p.cell.lo, 0)}–${pct(p.cell.hi, 0)}` },
  { key: "tok_out", label: "out tok", value: p => p.cell.tok_out, format: count },
  { key: "tok_think", label: "think tok", value: p => p.cell.tok_think, format: count },
  { key: "tok_in", label: "in tok", value: p => p.cell.tok_in, format: count },
  { key: "cost", label: "$/problem", value: p => p.cell.cost, format: dollars },
  { key: "cost_total", label: "Σ $", value: p => p.cell.cost_total, format: dollars },
  { key: "ms", label: "s/problem", value: p => p.cell.ms, format: duration },
];

function renderTable() {
  const col = COLUMNS.find(c => c.key === state.sort.key) || COLUMNS[3];
  const sortValue = col.sortValue || col.value;
  const rows = points(state.ds).sort((a, b) => ((sortValue(a) ?? -Infinity) > (sortValue(b) ?? -Infinity) ? 1 : -1) * state.sort.dir);
  const head = h("tr", {}, COLUMNS.map(c => {
    const active = c.key === state.sort.key;
    return h("th", {
      "aria-sort": active ? (state.sort.dir > 0 ? "ascending" : "descending") : null,
      onclick: () => {
        const textual = c.key === "model" || c.key === "level";
        state.sort = { key: c.key, dir: active ? -state.sort.dir : textual ? 1 : -1 };
        renderTable();
      },
    }, c.label + (active ? (state.sort.dir > 0 ? " ↑" : " ↓") : ""));
  }));
  const body = rows.map(p => h("tr", { onclick: () => select(p.key) },
    COLUMNS.map(c => h("td", {}, c.format ? c.format(c.value(p), p) : c.value(p)))));
  $("#table").replaceChildren(h("thead", {}, head), h("tbody", {}, body));
}

// wiring

function select(key) {
  state.selected = state.selected === key ? null : key;
  renderAll();
}

function renderAll() {
  if (!state.data) return;
  renderFilters();
  renderUsage();
  renderMatrix();
  renderScatter();
  renderLegend();
  renderSplit();
  renderProblems();
  renderTable();
}

async function load() {
  try {
    const data = await (await fetch("data.json", { cache: "no-store" })).json();
    if (!state.data || data.generated !== state.data.generated || data.n_records !== state.data.n_records) {
      state.data = data;
      renderAll();
    }
  } catch {
    if (!state.data) $("main").replaceChildren(h("p", { class: "muted" }, "could not load data.json"));
  }
}

state.ds = saved("ds", state.ds);
state.matrixMetric = saved("matrixMetric", state.matrixMetric);
state.scatterX = saved("scatterX", state.scatterX);
state.minN = saved("minN", state.minN);
state.hidden = new Set(saved("hidden", []));
const theme = new URLSearchParams(location.search).get("theme") || saved("theme", null);
if (theme) document.documentElement.dataset.theme = theme;

segmented("#ds-seg", "ds", renderAll);
segmented("#mx-metric", "matrixMetric", renderMatrix);
segmented("#sc-x", "scatterX", renderScatter);
$("#theme").addEventListener("click", () => {
  const next = isDark() ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  save("theme", next);
  renderAll();
});
$("#panel-close").addEventListener("click", () => { $("#panel").hidden = true; });
addEventListener("keydown", e => { if (e.key === "Escape") $("#panel").hidden = true; });
let resizeTimer;
addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(renderAll, 150);
});

load();
setInterval(load, 20000);
