"""Daily collection: fetch today's live prices and append them to the history files.

Each source is independent: if one fails, the others still run and the old history is kept.
Exit code is 1 only if every source failed.
"""
import json
import re
import sys
import time

import pandas as pd

from . import config as C
from .common import HTTP, append_snapshot, get_json, redact


def collect_vast():
    q = {"gpu_name": {"in": ["H100 SXM", "H100 NVL", "H100 PCIE", "B200"]},
         "rentable": {"eq": True}, "rented": {"eq": False}, "type": "on-demand", "limit": 1000}
    headers = {"Authorization": f"Bearer {C.VAST_API_KEY}"} if C.VAST_API_KEY else None
    data = get_json("https://console.vast.ai/api/v0/bundles/", params={"q": json.dumps(q)}, headers=headers)
    df = pd.json_normalize(data.get("offers", []))
    if df.empty:
        raise RuntimeError("Vast.ai returned no offers")
    keep = ["id", "gpu_name", "num_gpus", "dph_total", "geolocation", "reliability2", "verification"]
    df = df[[c for c in keep if c in df.columns]].copy()
    df["usd_per_gpu_hr"] = df["dph_total"] / df["num_gpus"]
    df["gpu"] = df["gpu_name"].str.extract(r"(H100|B200)")[0]
    df["snapshot_date"] = C.TODAY
    allrows = append_snapshot(df, C.VAST_HISTORY, key_cols=["id", "snapshot_date"])
    return f"{len(df)} offers today, {allrows.snapshot_date.nunique()} days on file"


def collect_openrouter():
    models = get_json("https://openrouter.ai/api/v1/models")["data"]
    rows = []
    for name, rx in C.MODELS.items():
        for mid in [m["id"] for m in models if re.search(rx, m["id"])]:
            try:
                ep = get_json(f"https://openrouter.ai/api/v1/models/{mid}/endpoints")["data"]
            except Exception as e:   # noqa: BLE001
                print(f"    endpoints failed for {mid}: {e}")
                continue
            for e in ep.get("endpoints", []):
                pr = e.get("pricing", {})
                rows.append({"date": C.TODAY, "model": name, "openrouter_id": mid,
                             "provider": e.get("provider_name"), "quantization": e.get("quantization"),
                             "usd_per_m_input": float(pr.get("prompt", "nan")) * 1e6,
                             "usd_per_m_output": float(pr.get("completion", "nan")) * 1e6,
                             "source": "openrouter"})
            time.sleep(0.3)
    if not rows:
        raise RuntimeError("OpenRouter returned no endpoints for our models")
    allrows = append_snapshot(pd.DataFrame(rows), C.OPENROUTER_HISTORY)
    return f"{len(rows)} provider prices today, {allrows.date.nunique()} days on file"


EIA_REFRESH_DAYS = 7   # EIA publishes monthly; no need to hit its slow API every day


EIA_STAMP = C.EIA_HISTORY.with_suffix(".refreshed")   # committed; file mtimes don't survive a git checkout


def collect_eia(force=False):
    if C.EIA_HISTORY.exists() and EIA_STAMP.exists() and not force:
        age_days = (pd.Timestamp(C.TODAY) - pd.Timestamp(EIA_STAMP.read_text().strip())).days
        if age_days < EIA_REFRESH_DAYS:
            last = pd.read_csv(C.EIA_HISTORY, usecols=["month"]).month.max()
            return f"skipped, refreshed {age_days} days ago (data through {last}); use --eia to force"
    if not C.EIA_API_KEY:
        raise RuntimeError("EIA_API_KEY is not set")
    url = "https://api.eia.gov/v2/electricity/retail-sales/data/"
    frames = []
    for state in C.EIA_STATES:
        for sector in C.EIA_SECTORS:
            params = [("api_key", C.EIA_API_KEY), ("frequency", "monthly"), ("data[0]", "price"),
                      ("facets[stateid][]", state), ("facets[sectorid][]", sector),
                      ("start", str(C.START)), ("sort[0][column]", "period"),
                      ("sort[0][direction]", "asc"), ("length", 5000)]
            try:
                frames.append(pd.DataFrame(get_json(url, params=params, timeout=90)["response"]["data"]))
            except Exception as e:   # noqa: BLE001
                print(f"    EIA {state} {sector} failed: {e}")
            time.sleep(0.5)
    if not frames:
        raise RuntimeError("No EIA data returned")
    df = pd.concat(frames, ignore_index=True)
    df["cents_per_kwh"] = pd.to_numeric(df["price"], errors="coerce")
    df["month"] = pd.PeriodIndex(df["period"], freq="M").astype(str)
    df = df[["month", "stateid", "sectorid", "cents_per_kwh"]]
    # EIA revises recent months, so fresh rows replace old ones. Series that failed this time keep their old rows.
    failed = len(C.EIA_STATES) * len(C.EIA_SECTORS) - len(frames)
    if C.EIA_HISTORY.exists():
        old = pd.read_csv(C.EIA_HISTORY)
        got = set(zip(df.stateid, df.sectorid))
        old = old[[k not in got for k in zip(old.stateid, old.sectorid)]]
        df = pd.concat([df, old], ignore_index=True)
    df = df.sort_values(["month", "stateid", "sectorid"])
    df.to_csv(C.EIA_HISTORY, index=False)
    if not failed:
        EIA_STAMP.write_text(C.TODAY + "\n")   # partial refresh: retry on the next run
    return f"{len(df)} rows, through {df.month.max()}" + (f" ({failed} series kept from before)" if failed else "")


def main():
    ok = 0
    force_eia = "--eia" in sys.argv
    for name, fn in [("Vast.ai", collect_vast), ("OpenRouter", collect_openrouter),
                     ("EIA", lambda: collect_eia(force=force_eia))]:
        try:
            print(f"{name}: {fn()}")
            ok += 1
        except Exception as e:   # noqa: BLE001
            print(f"{name}: FAILED, keeping existing history ({redact(e)})")
    HTTP.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
