"""Back-fill price history (2023 to now) from Wayback Machine snapshots, using the same price definitions the
daily collector records going forward.

    python -m spark.history

- Token prices: OpenRouter's headline ("listed") price per model, from archived copies of its models API.
- GPU rental: lowest listed on-demand price per GPU type on Lambda's pricing page, and RunPod's Secure Cloud price.

Up to SNAPSHOTS_PER_MONTH snapshots are read per month so the site can take the monthly median and flag months
where the price moved. Writes data/processed/wayback_token_prices.csv and data/processed/wayback_gpu_prices.csv
(committed; every row links to its snapshot). Downloads are cached in data/raw/wayback/.
"""
import gzip
import html
import json
import re
import time

import numpy as np
import pandas as pd

from . import config as C
from .common import HTTP

CACHE = C.RAW / "wayback"
CDX = "https://web.archive.org/cdx/search/cdx"
SNAPSHOTS_PER_MONTH = 4

# OpenRouter ids over time for each model line; the newest version listed wins.
TOKEN_HISTORY_IDS = {
    "Llama-2-70B": r"^meta-llama/llama-2-70b-chat$",
    "Llama-3-70B": r"^meta-llama/llama-3-70b-instruct$",
    "Llama-3.1-70B": r"^meta-llama/llama-3\.1-70b-instruct$",
    "Llama-3.3-70B": r"^meta-llama/llama-3\.3-70b-instruct$",
    "DeepSeek-V3": r"^deepseek/deepseek-(chat|v3)$",       # "deepseek-chat" was V2, then V2.5, then V3
    "DeepSeek-R1": r"^deepseek/deepseek-r1(-0528)?$",   # the original id was retired in late 2026
    "gpt-oss-120b": r"^openai/gpt-oss-120b$",
}
DEEPSEEK_V3_RELEASE = "2024-12-26"

ARCHIVED_RENTAL_PAGES = [
    ("Lambda", "lambdalabs.com/service/gpu-cloud"),
    ("Lambda", "lambda.ai/pricing"),
    ("RunPod", "www.runpod.io/pricing"),
]
LIVE_RENTAL_PAGES = [("Lambda", "lambda.ai/pricing"), ("RunPod", "www.runpod.io/pricing")]


# ---- Wayback access ------------------------------------------------------------------------------------
def _get(url, params=None, timeout=120):
    for attempt in range(3):
        try:
            r = HTTP.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception:   # noqa: BLE001
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))


def snapshots(url, per_month=SNAPSHOTS_PER_MONTH, start=C.START.year):
    """Up to `per_month` successful snapshot timestamps per month, spread across the month."""
    cache = CACHE / f"cdxd_{re.sub(r'[^a-z0-9]+', '_', url.lower())}.json"
    if cache.exists() and time.time() - cache.stat().st_mtime < 7 * 86400:
        daily = json.loads(cache.read_text())
    else:
        r = _get(CDX, params={"url": url, "from": start, "filter": "statuscode:200",
                              "collapse": "timestamp:8", "fl": "timestamp"}, timeout=120)
        daily = r.text.split()
        cache.write_text(json.dumps(daily))
    out = []
    for _, ts in pd.Series(daily, dtype=str).groupby(lambda i: daily[i][:6]):
        ts = ts.tolist()
        idx = sorted(set(np.linspace(0, len(ts) - 1, min(per_month, len(ts))).round().astype(int)))
        out += [ts[i] for i in idx]
    return out


def snapshot(ts, url):
    """Archived page as text (decompressed), cached."""
    f = CACHE / f"{ts}_{re.sub(r'[^a-z0-9]+', '_', url.lower())}"
    if not f.exists():
        f.write_bytes(_get(f"https://web.archive.org/web/{ts}id_/https://{url}").content)
        time.sleep(1)
    b = f.read_bytes()
    if b[:2] == b"\x1f\x8b":
        b = gzip.decompress(b)
    return b.decode("utf-8", "ignore")


def wayback_url(ts, url):
    return f"https://web.archive.org/web/{ts}/https://{url}"


def _date(ts):
    return f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"


# ---- Token prices: OpenRouter headline price -------------------------------------------------------------
def listed_prices(models, date):
    """OpenRouter's headline price for each tracked model, from a models-API response. Used for the archive
    and by the daily collector, so history and today share one definition."""
    found = {}
    for name, rx in TOKEN_HISTORY_IDS.items():
        for m in models:
            if re.search(rx, m["id"]):
                p = m.get("pricing", {})
                try:
                    usd_in, usd_out = float(p["prompt"]) * 1e6, float(p["completion"]) * 1e6
                except (KeyError, TypeError, ValueError):
                    continue
                if usd_out > 0:
                    found[name] = (m["id"], usd_in, usd_out)
    lineage = C.lineage_map()
    rows = []
    for series in C.MODEL_NAMES:
        versions = [v for v in C.MODEL_LINEAGE[series] if v in found]
        if not versions:
            continue
        v = versions[-1]
        mid, usd_in, usd_out = found[v]
        if v == "DeepSeek-V3" and date < DEEPSEEK_V3_RELEASE:
            v = "DeepSeek-V2.5"
        rows.append({"date": date, "model": v, "series": lineage.get(v, v), "openrouter_id": mid,
                     "usd_per_m_input": usd_in, "usd_per_m_output": usd_out})
    return rows


def token_history():
    url = "openrouter.ai/api/v1/models"
    rows = []
    for ts in snapshots(url):
        try:
            models = json.loads(snapshot(ts, url))["data"]
        except Exception as e:   # noqa: BLE001
            print(f"  OpenRouter {ts}: skipped ({type(e).__name__})")
            continue
        for r in listed_prices(models, _date(ts)):
            rows.append({**r, "source": "openrouter (wayback)", "source_url": wayback_url(ts, url)})
    return pd.DataFrame(rows)


# ---- GPU rental: provider list prices -------------------------------------------------------------------
def page_text(raw):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"\s+", " ", t)


GPU_RX = r"(H100 (?:SXM\d?|PCIe|NVL)|B200(?: SXM\d?)?)"


def parse_lambda(text):
    # Skip the reserved / cluster tables: on lambda.ai the self-serve prices come after "Instances pricing"
    i = text.find("Instances pricing")
    if i >= 0:
        text = text[i:]
    per_gpu_header = "PRICE/GPU/HR" in text.upper()
    out = []
    rx = re.compile(r"(?:(\d)x )?NVIDIA (?:HGX )?" + GPU_RX + r"\b(?:(?!NVIDIA|\$).){0,160}\$\s?(\d+(?:\.\d+)?)\s*(/ ?GPU ?/ ?hr|/hr/GPU|/ ?hr)?",
                    re.I)
    for m in rx.finditer(text):
        n, variant, price, unit = m.group(1), m.group(2), float(m.group(3)), (m.group(4) or "")
        context = (text[max(0, m.start() - 80):m.start()] + m.group(0)).lower()
        if re.search(r"reserved|contact|as low as|commit|\byears?\b|\bterm\b", context):   # not on-demand list prices
            continue
        per_gpu = "gpu" in unit.lower() or (per_gpu_header and not unit)
        if not per_gpu:
            if not n:
                continue
            price = price / int(n)
        out.append((variant, price))
    return out


def parse_runpod(text):
    out = []
    rx = re.compile(GPU_RX + r"\b((?:(?!H100|H200|B200|A100|\bL40|RTX).){0,200})", re.I)
    for m in rx.finditer(text):
        card = re.split(r"starting from", m.group(2), flags=re.I)[0]   # "Starting from $x" belongs to the next card
        prices = [float(p) for p in re.findall(r"\$\s?(\d+\.\d\d)\s*/\s?hr", card)]
        if prices:
            out.append((m.group(1), prices[0]))   # first price on a card is Secure Cloud (Community Cloud follows)
    return out


def list_prices(provider, raw_html, date, source_url):
    """Lowest listed on-demand price per GPU variant on one pricing page. Used for the archive and daily."""
    parse = parse_runpod if provider == "RunPod" else parse_lambda
    best = {}
    for variant, price in parse(page_text(raw_html)):
        v = re.sub(r"\s+", " ", variant.strip()).upper().replace("PCIE", "PCIe")
        v = "B200" if v.startswith("B200") else v
        if 0.5 <= price <= 30:   # sanity range for $/GPU-hr
            best[v] = min(price, best.get(v, price))
    return [{"date": date, "provider": provider, "gpu": "B200" if "B200" in v else "H100", "variant": v,
             "price_usd_per_gpu_hr": round(p, 4), "pricing_type": "on-demand", "source_url": source_url}
            for v, p in best.items()]


def rental_history():
    rows = []
    for provider, url in ARCHIVED_RENTAL_PAGES:
        for ts in snapshots(url):
            try:
                rows += list_prices(provider, snapshot(ts, url), _date(ts), wayback_url(ts, url))
            except Exception as e:   # noqa: BLE001
                print(f"  {provider} {ts}: skipped ({type(e).__name__})")
    return pd.DataFrame(rows)


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    t = token_history()
    t.to_csv(C.PROC / "wayback_token_prices.csv", index=False)
    print(f"Token prices: {len(t)} rows from {t.date.nunique()} snapshots, {t.date.str[:7].nunique()} months")
    r = rental_history()
    r.to_csv(C.PROC / "wayback_gpu_prices.csv", index=False)
    print(f"GPU rental:   {len(r)} rows from {r.date.nunique()} snapshot days, {r.date.str[:7].nunique()} months")
    HTTP.close()


if __name__ == "__main__":
    main()
