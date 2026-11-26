# The AI Spark Spread

Power traders track the spark spread: the gap between what electricity sells for and what the gas to make it costs.
This project builds the AI version for one GPU hour: **power cost → rental price → token revenue**, and tracks
which layer captures the money from 2023 to today, for the NVIDIA H100 and B200.

## Setup
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add your EIA key (and optionally Artificial Analysis)
jupyter lab notebooks/01_spark_spread_research.ipynb
```

## Layout
```
notebooks/       research notebook
spark/           daily pipeline used by the website (same math as the notebook)
site/            the website (Observable Framework)
data/raw/        cached API downloads (not committed), except the daily price history files
data/manual/     hand-collected, hand-checked CSVs (committed)
data/processed/  outputs: spark_spread_panel.csv, inferencex_throughput.csv, Wayback price candidates
figures/         saved charts
sources.md       every source and assumption, with access dates
```

## Website
A static site rebuilt every day by GitHub Actions (`.github/workflows/update-site.yml`):

1. `python -m spark.collect` fetches today's Vast.ai and OpenRouter prices (and EIA weekly) and appends them to
   `data/raw/vast_snapshots.csv`, `data/raw/openrouter_price_snapshots.csv` and `data/raw/eia_retail_prices.csv`.
   The workflow commits these, so the price history grows by one day per run.
2. `python -m spark.build` computes the panel and writes `site/src/data/spark.json`.
3. The site is built and deployed to GitHub Pages. API keys live in repository secrets (`EIA_API_KEY`, optional
   `VAST_API_KEY`) and never reach the site.

Run it locally:
```bash
python -m spark.collect        # optional: fetch today's prices (add --eia to force an EIA refresh)
python -m spark.build          # write site/src/data/spark.json
cd site && npm install && npm run dev    # preview at http://127.0.0.1:3000
```

Price history before daily collection comes from Wayback Machine snapshots: run `python -m spark.history` now and then
and commit `data/processed/wayback_*.csv` (every row links to its snapshot; check new rows before committing).

Throughput comes from InferenceX exports you download by hand into `data/raw/inferencex/` (not committed).
After adding new exports, run `python -m spark.throughput` and commit `data/processed/inferencex_throughput.csv`.

Assumptions live in `spark/config.py` for the site and in section 1 of the notebook; keep them in step.

## Status
Layers without real data run on clearly labeled synthetic placeholder data, and charts built on them are stamped `SYNTHETIC`.
Section 8 of the notebook shows which layers are still synthetic.

## Credits
Ornn's OCPI and Silicon Data's indexes are used only as a cross-check and are credited; they are not inputs.
