"""Back-fill monthly price history (2023 to now) from Wayback Machine snapshots.

    python -m spark.history

- Token prices: archived copies of OpenRouter's own models API (JSON), one per month.
- GPU rental: archived Lambda and RunPod pricing pages, lowest listed on-demand price per GPU type.

Writes data/processed/wayback_token_prices.csv and data/processed/wayback_gpu_prices.csv (committed; every row
links to the snapshot it came from so it can be checked). Downloads are cached in data/raw/wayback/.
Run it by hand now and then; the daily pipeline only reads its output.
"""
import gzip
import html
import json
import re
import time

import pandas as pd

from . import config as C
from .common import HTTP

CACHE = C.RAW / "wayback"
CDX = "https://web.archive.org/cdx/search/cdx"

# OpenRouter ids over time for each model line; the newest version listed that month wins.
TOKEN_HISTORY_IDS = {
    "Llama-2-70B": r"^meta-llama/llama-2-70b-chat$",
    "Llama-3-70B": r"^meta-llama/llama-3-70b-instruct$",
    "Llama-3.1-70B": r"^meta-llama/llama-3\.1-70b-instruct$",
    "Llama-3.3-70B": r"^meta-llama/llama-3\.3-70b-instruct$",
    "DeepSeek-V3": r"^deepseek/deepseek-(chat|v3)$",       # "deepseek-chat" was V2, then V2.5, then V3
    "DeepSeek-R1": r"^deepseek/deepseek-r1$",
    "gpt-oss-120b": r"^openai/gpt-oss-120b$",
}

RENTAL_PAGES = [
    ("Lambda", "lambdalabs.com/service/gpu-cloud"),
    ("Lambda", "lambda.ai/pricing"),
    ("RunPod", "www.runpod.io/pricing"),
]


def monthly_snapshots(url, start=C.START.year):
    """One successful snapshot timestamp per month."""
    cache = CACHE / f"cdx_{re.sub(r'[^a-z0-9]+', '_', url.lower())}.json"
    if cache.exists() and time.time() - cache.stat().st_mtime < 7 * 86400:
        return json.loads(cache.read_text())
    for attempt in range(3):
        try:
            r = HTTP.get(CDX, params={"url": url, "from": start, "filter": "statuscode:200",
                                      "collapse": "timestamp:6", "fl": "timestamp"}, timeout=90)
            r.raise_for_status()
            break
        except Exception:   # noqa: BLE001
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))
    ts = r.text.split()
    cache.write_text(json.dumps(ts))
    return ts


def snapshot(ts, url):
    """Raw archived bytes (decompressed), cached."""
    f = CACHE / f"{ts}_{re.sub(r'[^a-z0-9]+', '_', url.lower())}"
    if not f.exists():
        for attempt in range(3):
            try:
                r = HTTP.get(f"https://web.archive.org/web/{ts}id_/https://{url}", timeout=120)
                r.raise_for_status()
                break
            except Exception:   # noqa: BLE001
                if attempt == 2:
                    raise
                time.sleep(5 * (attempt + 1))
        f.write_bytes(r.content)
        time.sleep(1)
    b = f.read_bytes()
    if b[:2] == b"\x1f\x8b":
        b = gzip.decompress(b)
    return b.decode("utf-8", "ignore")


def wayback_url(ts, url):
    return f"https://web.archive.org/web/{ts}/https://{url}"


# ---- Token prices ------------------------------------------------------------------------------------
def token_history():
    url = "openrouter.ai/api/v1/models"
    rows = []
    for ts in monthly_snapshots(url):
        try:
            models = json.loads(snapshot(ts, url))["data"]
        except Exception as e:   # noqa: BLE001
            print(f"  OpenRouter {ts}: skipped ({type(e).__name__})")
            continue
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
        for series in C.MODEL_NAMES:
            versions = [v for v in C.MODEL_LINEAGE[series] if v in found]
            if not versions:
                continue
            v = versions[-1]   # newest version listed that month
            mid, usd_in, usd_out = found[v]
            if v == "DeepSeek-V3" and ts < "20241226":
                v = "DeepSeek-V2.5"   # "deepseek-chat" served V2 / V2.5 before V3's release on 2024-12-26
            rows.append({"date": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}", "model": v, "series": lineage.get(v, v),
                         "openrouter_id": mid, "usd_per_m_input": usd_in, "usd_per_m_output": usd_out,
                         "source": "openrouter (wayback)", "source_url": wayback_url(ts, url)})
    return pd.DataFrame(rows)


# ---- GPU rental ---------------------------------------------------------------------------------------
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
            out.append((m.group(1), min(prices)))
    return out


def rental_history():
    rows = []
    for provider, url in RENTAL_PAGES:
        parse = parse_runpod if provider == "RunPod" else parse_lambda
        for ts in monthly_snapshots(url):
            try:
                found = parse(page_text(snapshot(ts, url)))
            except Exception as e:   # noqa: BLE001
                print(f"  {provider} {ts}: skipped ({type(e).__name__})")
                continue
            best = {}
            for variant, price in found:
                v = re.sub(r"\s+", " ", variant.strip()).upper().replace("PCIE", "PCIe")
                v = "B200" if v.startswith("B200") else v
                if 0.5 <= price <= 30:   # sanity range for $/GPU-hr
                    best[v] = min(price, best.get(v, price))
            for v, price in best.items():
                rows.append({"date": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}", "provider": provider,
                             "gpu": "B200" if "B200" in v else "H100", "variant": v,
                             "price_usd_per_gpu_hr": round(price, 4), "pricing_type": "on-demand",
                             "source_url": wayback_url(ts, url)})
    df = pd.DataFrame(rows)
    # Lambda moved domains; keep one snapshot per provider per month
    if len(df):
        df["month"] = df.date.str[:7]
        last = df.groupby(["provider", "month"]).date.transform("max")
        df = df[df.date == last].drop(columns="month")
    return df


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    t = token_history()
    t.to_csv(C.PROC / "wayback_token_prices.csv", index=False)
    print(f"Token prices: {len(t)} rows, {t.date.str[:7].nunique()} months, {t.date.min()} to {t.date.max()}")
    r = rental_history()
    r.to_csv(C.PROC / "wayback_gpu_prices.csv", index=False)
    print(f"GPU rental:   {len(r)} rows, {r.date.str[:7].nunique()} months, {r.date.min()} to {r.date.max()}")
    HTTP.close()


if __name__ == "__main__":
    main()
