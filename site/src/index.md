---
title: Today's spread
---

```js
import {COLORS, MODEL_COLORS, GPU_COLORS, usd, pct, num, tokenRevenue, breakEvenTps} from "./components/shared.js";
const data = FileAttachment("data/spark.json").json();
```

```js
const GPUS = Object.keys(data.gpus);
const MODELS = data.models;
const latest = data.latest;
const modelColor = {domain: MODELS, range: MODEL_COLORS};
const gpuColor = {domain: GPUS, range: GPU_COLORS};
```

<div class="hero">
  <h1>The AI Spark Spread</h1>
  <p class="lede">Power traders watch the <em>spark spread</em>: what electricity sells for minus what the fuel to make it costs. This is the same idea for one hour of AI compute: the electricity, the GPU rental, and the tokens it can sell. Who keeps the money?</p>
  <p class="muted small">${data.latest_month ? html`Latest month: <b>${data.latest_month}</b> · prices collected daily since ${data.tracking_since} (${data.days_tracked} ${data.days_tracked === 1 ? "day" : "days"}) · updated ${data.generated_at.replace("T", " ")} UTC` : "No data yet."}</p>
</div>

```js
if (data.missing.length) display(html`<div class="warning" label="Missing data">Some layers have no data yet and are left out: ${data.missing.join(", ")}.</div>`);
```

```js
const gpu = view(Inputs.radio(GPUS, {value: GPUS[0], label: "GPU"}));
```

```js
const L = latest.filter((d) => d.gpu === gpu);
const r0 = L[0];
const best = d3.greatest(L, (d) => d.token_rev);
const worst = d3.least(L, (d) => d.token_rev);
```

<div class="headline">
Of every <b>${usd(r0.rental)}</b> an ${gpu} rents for per hour, electricity costs <b class="c-power">${usd(r0.power)}</b> and the GPU owner keeps <b class="c-owner">${usd(r0.compute_spread)}</b>. Renting it to sell tokens earns back <b>${usd(best.token_rev)}</b> an hour with ${best.model}, and only <b>${usd(worst.token_rev)}</b> with ${worst.model}.
</div>

<div class="grid grid-cols-4">
  <div class="card"><h2>Rental price</h2><span class="big">${usd(r0.rental)}</span><span class="muted">per GPU hour · median of ${num(r0.rental_observations)} offers</span></div>
  <div class="card"><h2>Electricity</h2><span class="big c-power">${usd(r0.power)}</span><span class="muted">${pct(r0.power_pct_of_rental)} of the rental price</span></div>
  <div class="card"><h2>GPU owner keeps</h2><span class="big c-owner">${usd(r0.compute_spread)}</span><span class="muted">rental minus electricity</span></div>
  <div class="card"><h2>Token seller, best case</h2><span class="big ${best.inference_spread >= 0 ? "c-seller" : "c-loss"}">${usd(best.inference_spread)}</span><span class="muted">per hour with ${best.model}</span></div>
</div>

## One GPU hour, three prices

What an hour of ${gpu} costs in electricity, what it rents for, and what it earns selling each model's tokens. Any model whose bar falls short of the dashed rental line loses money for whoever rents the GPU to serve it.

```js
const chainRows = [
  {label: "Electricity", value: r0.power, color: COLORS.power},
  {label: "Rental price", value: r0.rental, color: "var(--theme-foreground)"},
  ...L.map((d) => ({label: d.model, value: d.token_rev, color: MODEL_COLORS[MODELS.indexOf(d.model)]}))
];
display(Plot.plot({
  width, height: 340, marginBottom: 40,
  x: {label: null, domain: chainRows.map((d) => d.label), tickSize: 0},
  y: {label: "$ per GPU hour", grid: true, nice: true},
  marks: [
    Plot.barY(chainRows, {x: "label", y: "value", fill: "color", tip: {format: {fill: false}}, title: (d) => `${d.label}: ${usd(d.value)} per GPU hour`}),
    Plot.text(chainRows, {x: "label", y: "value", text: (d) => usd(d.value), dy: -8, fontSize: 12}),
    Plot.ruleY([r0.rental], {stroke: "var(--theme-foreground)", strokeDasharray: "4,3", strokeOpacity: 0.7}),
    Plot.ruleY([0])
  ]
}));
```

<p class="small muted">Bars after the first two are token revenue: benchmark throughput × ${data.assumptions.token_load_factor} load factor × the median OpenRouter price, billing ${data.assumptions.input_per_output} input tokens per output token.</p>

## Who captures the money

Each bar splits one ${gpu} hour of token revenue by who keeps it. Electricity plus the owner's share always adds up to the rental price. When token revenue (black tick) is below rent, the token seller's share is a loss, drawn in red below zero.

```js
const parts = L.flatMap((d) => [
  {model: d.model, part: "Electricity", value: d.power},
  ...(data.assumptions.include_hardware ? [{model: d.model, part: "Hardware", value: d.hardware}] : []),
  {model: d.model, part: "GPU owner (compute spread)", value: d.compute_spread},
  {model: d.model, part: d.inference_spread >= 0 ? "Token seller (inference spread)" : "Token seller's loss", value: d.inference_spread}
]);
display(Plot.plot({
  width, height: 380,
  x: {label: null, domain: MODELS, tickSize: 0},
  y: {label: "$ per GPU hour", grid: true},
  color: {
    legend: true,
    domain: [...new Set(parts.map((d) => d.part))],
    range: [...new Set(parts.map((d) => d.part))].map((p) => ({"Electricity": COLORS.power, "Hardware": COLORS.hardware,
      "GPU owner (compute spread)": COLORS.owner, "Token seller (inference spread)": COLORS.seller, "Token seller's loss": COLORS.loss})[p])
  },
  marks: [
    Plot.barY(parts, {x: "model", y: "value", fill: "part", tip: true, title: (d) => `${d.model}\n${d.part}: ${usd(d.value)}`}),
    Plot.tickY(L, {x: "model", y: "token_rev", stroke: "var(--theme-foreground)", strokeWidth: 3, tip: true, title: (d) => `Token revenue: ${usd(d.token_rev)}`}),
    Plot.ruleY([0])
  ]
}));
```

## The spreads across GPUs and models

The GPU owner's spread (left) is the same for every model. The token seller's spread (right) depends on both the chip and the model. Above zero makes money; below zero loses it.

```js
const owner = GPUS.map((g) => latest.find((d) => d.gpu === g));
```

<div class="grid grid-cols-3">
<div class="card">

```js
display(Plot.plot({
  width: Math.min(width / 3, 360), height: 320, title: "GPU owner: rental − electricity",
  x: {label: null, tickSize: 0, domain: GPUS},
  y: {label: "$ per GPU hour", grid: true},
  color: gpuColor,
  marks: [
    Plot.barY(owner, {x: "gpu", y: "compute_spread", fill: "gpu", tip: true}),
    Plot.text(owner, {x: "gpu", y: "compute_spread", text: (d) => usd(d.compute_spread), dy: -8}),
    Plot.ruleY([0])
  ]
}));
```

</div>
<div class="card grid-colspan-2">

```js
display(Plot.plot({
  width: Math.min((width * 2) / 3, 760), height: 320, title: "Token seller: token revenue − rental",
  fx: {label: null, domain: MODELS},
  x: {axis: null, domain: GPUS},
  y: {label: "$ per GPU hour", grid: true},
  color: {...gpuColor, legend: true},
  marks: [
    Plot.barY(latest, {fx: "model", x: "gpu", y: "inference_spread", fill: "gpu", tip: true,
      title: (d) => `${d.gpu} · ${d.model}\nToken revenue ${usd(d.token_rev)} − rental ${usd(d.rental)} = ${usd(d.inference_spread)}`}),
    Plot.ruleY([0])
  ]
}));
```

</div>
</div>

## What would it take?

The token seller's result hinges on throughput: how many output tokens a GPU produces per second. Pick a model and move the sliders. They start at today's values for the ${gpu} you chose above.

```js
const calcModel = view(Inputs.select(MODELS, {label: "Model", value: MODELS[0]}));
```

```js
const base = latest.find((d) => d.gpu === gpu && d.model === calcModel);
const knobs = view(Inputs.form({
  tps: Inputs.range([1, 20000], {label: "Throughput (output tok/s per GPU)", value: Math.round(base.tok_s_per_gpu), step: 1, transform: Math.log}),
  loadFactor: Inputs.range([0.1, 1], {label: "Token load factor", value: data.assumptions.token_load_factor, step: 0.05}),
  ratio: Inputs.range([0, 16], {label: "Input tokens per output token", value: data.assumptions.input_per_output, step: 0.5}),
  rental: Inputs.range([0.5, 20], {label: "Rental price ($/GPU-hr)", value: +base.rental.toFixed(2), step: 0.01}),
  usdIn: Inputs.number([0, 100], {label: "Input price ($/1M tokens)", value: +base.usd_in.toFixed(3), step: 0.001}),
  usdOut: Inputs.number([0, 100], {label: "Output price ($/1M tokens)", value: +base.usd_out.toFixed(3), step: 0.001})
}));
```

```js
const rev = tokenRevenue(knobs);
const spread = rev - knobs.rental;
const be = breakEvenTps(knobs);
const bench = base.tok_s_per_gpu;
```

<div class="grid grid-cols-3">
  <div class="card"><h2>Token revenue</h2><span class="big">${usd(rev)}</span><span class="muted">per GPU hour</span></div>
  <div class="card"><h2>Token seller's spread</h2><span class="big ${spread >= 0 ? "c-seller" : "c-loss"}">${usd(spread)}</span><span class="muted">${spread >= 0 ? "profit" : "loss"} per GPU hour after rent</span></div>
  <div class="card"><h2>Break-even throughput</h2><span class="big">${num(be)}</span><span class="muted">tok/s per GPU · ${be > bench ? `${num(be / bench, 1)}× the benchmark (${num(bench)})` : `below the benchmark (${num(bench)})`}</span></div>
</div>

```js
// Zoom the curve to the interesting range: a decade either side of the benchmark, break-even and current value
const pts = [bench, knobs.tps, ...(Number.isFinite(be) ? [be] : [])];
const lo = Math.max(1, d3.min(pts) / 10), hi = Math.min(20000, d3.max(pts) * 10);
const curve = d3.range(Math.log10(lo), Math.log10(hi) + 0.001, (Math.log10(hi) - Math.log10(lo)) / 200).map((e) => {
  const tps = 10 ** e;
  return {tps, spread: tokenRevenue({...knobs, tps}) - knobs.rental};
});
display(Plot.plot({
  width, height: 300,
  x: {type: "log", label: "Throughput (output tok/s per GPU) →", grid: true, domain: [lo, hi]},
  y: {label: "Token seller's spread ($/GPU-hr)", grid: true},
  marks: [
    Plot.areaY(curve, {x: "tps", y: "spread", fill: (d) => (d.spread >= 0 ? "gain" : "loss"), fillOpacity: 0.12, curve: "step"}),
    Plot.line(curve, {x: "tps", y: "spread", stroke: "var(--theme-foreground)"}),
    Plot.ruleY([0]),
    Plot.ruleX([bench], {stroke: "#888", strokeDasharray: "3,3"}),
    Plot.text([bench], {x: (d) => d, frameAnchor: "top", dy: 4, text: () => "benchmark", fill: "#888", textAnchor: "start", dx: 4}),
    ...(Number.isFinite(be) && be <= hi ? [Plot.dot([be], {x: (d) => d, y: 0, r: 5, fill: COLORS.seller}),
      Plot.text([be], {x: (d) => d, y: 0, dy: -12, text: () => `break-even ${num(be)}`, fill: COLORS.seller})] : []),
    Plot.dot([knobs.tps], {x: (d) => d, y: () => spread, r: 6, stroke: "var(--theme-foreground)", fill: spread >= 0 ? COLORS.seller : COLORS.loss})
  ],
  color: {domain: ["gain", "loss"], range: [COLORS.seller, COLORS.loss]}
}));
```

<p class="small muted">Benchmark throughput for ${gpu} · ${calcModel}: ${num(bench, 1)} tok/s per GPU at ${data.assumptions.target_interactivity} tok/s per user, ${base.tput_source} (${base.tput_date})${base.tput_url ? html`, <a href="${base.tput_url}">run</a>` : ""}. Prices are this month's median across OpenRouter providers.</p>

## Price history

```js
const rentalDaily = data.daily_rental.map((d) => ({...d, date: new Date(d.date)}));
const tokenDaily = data.daily_tokens.map((d) => ({...d, date: new Date(d.date)}));
const fewDays = data.days_tracked < 7;
```

Daily snapshots began on ${data.tracking_since}. ${fewDays ? "With only a few days so far these charts are mostly dots; they fill in as the daily job runs." : ""}

<div class="grid grid-cols-2">
<div class="card">

```js
display(Plot.plot({
  width: Math.min(width / 2, 640), height: 280, title: "GPU rental, median Vast.ai asking price",
  x: {type: "utc", label: null},
  y: {label: "$ per GPU hour", grid: true, zero: true},
  color: {...gpuColor, legend: true},
  marks: [
    ...(fewDays ? [Plot.ruleX(rentalDaily, {x: "date", y1: "p25", y2: "p75", stroke: "gpu", strokeWidth: 6, strokeOpacity: 0.25})]
      : [Plot.areaY(rentalDaily, {x: "date", y1: "p25", y2: "p75", fill: "gpu", fillOpacity: 0.15})]),
    Plot.lineY(rentalDaily, {x: "date", y: "median", stroke: "gpu"}),
    Plot.dot(rentalDaily, {x: "date", y: "median", fill: "gpu", r: 4}),
    Plot.tip(rentalDaily, Plot.pointerX({x: "date", y: "median", title: (d) => `${d.gpu} · ${d.date.toISOString().slice(0, 10)}\nmedian ${usd(d.median)} (${d.offers} offers)`}))
  ]
}));
```

</div>
<div class="card">

```js
display(Plot.plot({
  width: Math.min(width / 2, 640), height: 280, title: `Token price per 1M output tokens, incl. ${data.assumptions.input_per_output}M input`,
  x: {type: "utc", label: null},
  y: {label: "$ per 1M output tokens (blended)", grid: true, zero: true},
  color: {...modelColor, legend: true},
  marks: [
    Plot.lineY(tokenDaily, {x: "date", y: "blended", stroke: "model"}),
    Plot.dot(tokenDaily, {x: "date", y: "blended", fill: "model", r: 4}),
    Plot.tip(tokenDaily, Plot.pointerX({x: "date", y: "blended", title: (d) => `${d.model} · ${d.date.toISOString().slice(0, 10)}\n${usd(d.blended)} (${d.providers} provider prices)`}))
  ]
}));
```

</div>
</div>

```js
if (data.months_of_rental_data >= 3) {
  const panel = data.panel.filter((d) => d.gpu === gpu && d.token_rev != null).map((d) => ({...d, date: new Date(d.month + "-01")}));
  display(html`<h3>Token seller's spread by month, ${gpu}</h3>`);
  display(Plot.plot({
    width, height: 300, x: {type: "utc", label: null}, y: {label: "$ per GPU hour", grid: true},
    color: {...modelColor, legend: true},
    marks: [Plot.ruleY([0]), Plot.lineY(panel, {x: "date", y: "inference_spread", stroke: "model", marker: "circle", tip: true})]
  }));
}
```

