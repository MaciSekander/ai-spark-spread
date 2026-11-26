# Sources log

Log every source with the date you accessed it. Anything marked **verify** is an assumption in the notebook that still needs a citation.

## Assumptions to verify
| Assumption | Value in notebook | Where to confirm | Accessed | Confirmed value |
|---|---|---|---|---|
| H100 SXM chip power | 700 W | NVIDIA H100 datasheet | | |
| B200 chip power | 1,000 W | NVIDIA B200 / DGX B200 datasheet | | |
| DGX H100 max system power | 10.2 kW | NVIDIA DGX H100 user guide | | |
| DGX B200 max system power | 14.3 kW | NVIDIA DGX B200 datasheet | | |
| Server load factor | 0.80 | working assumption; look for measured data center draw studies | | |
| PUE, industry average | 1.56 | Uptime Institute Global Data Center Survey (latest year) | | |
| PUE, hyperscale | 1.10 | Google Environmental Report / Meta Sustainability Report | | |
| Input:output token ratio | 3:1 | Artificial Analysis "blended 3:1" convention; OpenRouter usage stats | | |
| Token load factor | 0.60 | working assumption | | |

## Power layer
- EIA API v2, electricity/retail-sales — https://www.eia.gov/opendata/ — accessed:
- ERCOT market prices (optional) — https://www.ercot.com/mktinfo/prices — accessed:
- PJM Data Miner (optional) — https://dataminer2.pjm.com — accessed:

## Compute layer
- Wayback Machine snapshots (list each provider + snapshot URL in data/manual/gpu_list_prices.csv)
- Vast.ai marketplace API — https://vast.ai — snapshot dates in data/raw/vast_snapshots.csv
- Epoch AI, Data on Machine Learning Hardware — https://epoch.ai/data — accessed:
- Cross-check only (credited, not used as inputs): Ornn OCPI — https://ornn.com/product/data — accessed: ; Silicon Data — accessed:

## Token layer
- OpenRouter models + endpoints API — https://openrouter.ai/api/v1/models — snapshot dates in data/raw/openrouter_price_snapshots.csv
- Artificial Analysis API — https://artificialanalysis.ai — accessed:
- Epoch AI, LLM inference price trends — https://epoch.ai/data — accessed:
- SemiAnalysis InferenceX (throughput) — record each configuration's URL in data/manual/throughput.csv — accessed:
