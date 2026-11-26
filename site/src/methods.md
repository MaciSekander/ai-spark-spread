---
title: Methods & sources
---

```js
import {usd, num} from "./components/shared.js";
const data = FileAttachment("data/spark.json").json();
```

# Methods & sources

The chain has three layers, each in dollars per GPU hour, calculated per month for every GPU and model pair.

## The math

| Layer | Formula |
|---|---|
| **Electricity** | kW per GPU × server load factor × PUE × $/kWh |
| **Rental price** | median asking price across offers that month |
| **Token revenue** | output tok/s per GPU × token load factor × 3,600 ÷ 1,000,000 × blended $ per 1M output tokens |
| **Blended token price** | output price + (input tokens per output token × input price) |
| **GPU owner's spread** (compute spread) | rental − electricity${data.assumptions.include_hardware ? " − hardware" : ""} |
| **Token seller's spread** (inference spread) | token revenue − rental |
| **Cost to own** | electricity + server price ÷ 8 GPUs ÷ (life in years × 8,760 hours × utilization) |
| **Owning and selling tokens** | token revenue − cost to own |

## Assumptions in use

```js
const a = data.assumptions;
display(Inputs.table([
  {assumption: "kW per GPU, H100 (8-GPU server ÷ 8)", value: num(data.gpus.H100?.kw_per_gpu, 3)},
  {assumption: "kW per GPU, B200 (8-GPU server ÷ 8)", value: num(data.gpus.B200?.kw_per_gpu, 3)},
  {assumption: "Server load factor", value: a.load_factor},
  {assumption: `PUE (${a.pue_case.replace("_", " ")})`, value: a.pue},
  {assumption: "Electricity price", value: `EIA retail, ${a.power_state} ${a.power_sector === "IND" ? "industrial" : "commercial"}: ${usd(data.power?.usd_per_kwh, 4)}/kWh (${data.power?.month})`},
  {assumption: "Input tokens billed per output token", value: a.input_per_output},
  {assumption: "Token load factor (achieved ÷ benchmark throughput)", value: a.token_load_factor},
  {assumption: "Benchmark speed per user", value: `${a.target_interactivity} output tok/s`},
  {assumption: "8-GPU server price, H100 / B200 (estimates)", value: `${usd(data.gpus.H100?.server_capex_usd, 0)} / ${usd(data.gpus.B200?.server_capex_usd, 0)}`},
  {assumption: "Server life and utilization (cost to own)", value: `${a.hw_life_years} years at ${a.hw_utilization * 100}%`}
], {select: false, header: {assumption: "Assumption", value: "Value"}, layout: "auto"}));
```

## Sources

- **Electricity:** [U.S. EIA API v2](https://www.eia.gov/opendata/), electricity retail sales, monthly average price by state and sector. EIA publishes with a lag of about two months; the latest published month is carried forward.
- **GPU rental:** [Vast.ai](https://vast.ai) marketplace, on-demand offers for H100 (SXM, NVL, PCIe) and B200, priced per GPU, collected daily. Hand-checked list prices from provider pricing pages (via the Wayback Machine) are added when available.
- **Token prices:** [OpenRouter](https://openrouter.ai) per-provider input and output prices for each model, collected daily; the median across providers is used.
- **Throughput:** [SemiAnalysis InferenceX](https://github.com/SemiAnalysisAI/InferenceX) benchmark runs, the best output tokens per second per GPU at ${data.assumptions.target_interactivity} tok/s per user. DeepSeek-V3 uses DeepSeek-R1's runs (same architecture). Speculative decoding is excluded.

```js
display(Inputs.table(data.latest.map((d) => ({gpu: d.gpu, model: d.model, tps: d.tok_s_per_gpu, date: d.tput_date, source: d.tput_source, run: d.tput_url})), {
  select: false, layout: "auto",
  header: {gpu: "GPU", model: "Model", tps: "Output tok/s per GPU", date: "Benchmark date", source: "Source", run: "Run"},
  format: {tps: (v) => num(v, 1), run: (v) => v ? html`<a href="${v}">link</a>` : ""}
}));
```

## Caveats

- **Asking prices, not settled trades.** Rental and token prices are public list or asking prices. What buyers actually pay can differ, especially for reserved and long-term contracts.
- **Thin markets.** The B200 rental price comes from relatively few marketplace offers and may not represent the wider market.
- **Throughput drives the token seller's result.** Benchmarks vary 5–10× with serving setup and speed per user; the calculator on the main page lets you test this.
- **Hardware cost is ${data.assumptions.include_hardware ? "included" : "not yet included"}** in the GPU owner's spread${data.assumptions.include_hardware ? "" : ", so their margin is before paying for the GPUs themselves"}.

## Data

```js
display(html`<p>Every figure on this site comes from one file, rebuilt daily: <a href="${FileAttachment("data/spark.json").href}" download="spark.json">spark.json</a>. Last built ${data.generated_at.replace("T", " ")} UTC.</p>`);
```
