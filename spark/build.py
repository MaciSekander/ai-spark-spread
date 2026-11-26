"""Build the monthly panel from the committed history and write the website's data file.

No network access: everything comes from files in data/. Missing layers are left empty (no synthetic data
on the site); the JSON lists what is missing so the page can say so.
"""
import datetime as dt
import json
import math

import numpy as np
import pandas as pd

from . import config as C
from .common import load_manual


def _period(s):
    return pd.PeriodIndex(pd.to_datetime(s), freq="M")


def power_cost(months):
    eia = load_manual(C.EIA_HISTORY)
    if eia.empty:
        return pd.DataFrame(index=months, columns=C.GPUS, dtype=float), None
    s = eia[(eia.stateid == C.POWER_STATE) & (eia.sectorid == C.POWER_SECTOR)].copy()
    s["month"] = pd.PeriodIndex(s["month"], freq="M")
    usd_kwh = (s.groupby("month")["cents_per_kwh"].mean() / 100)
    latest = {"month": str(usd_kwh.index.max()), "usd_per_kwh": float(usd_kwh.iloc[-1])}
    usd_kwh = usd_kwh.reindex(months).interpolate(limit_direction="both")
    pue = C.PUE_SCENARIOS[C.PUE_CASE]
    df = pd.DataFrame({g: usd_kwh * C.kw_per_gpu(g) * C.LOAD_FACTOR * pue for g in C.GPUS})
    return df, latest


def rental_obs():
    frames = []
    lp = load_manual(C.MANUAL / "gpu_list_prices.csv")
    if len(lp):
        lp = lp[lp.pricing_type.fillna("on-demand").eq("on-demand")]
        frames.append(lp.assign(month=_period(lp["date"]), source="list")
                      [["month", "gpu", "price_usd_per_gpu_hr", "source"]])
    # Provider list prices: archived (Wayback) and collected daily, same definition
    for f in (C.PROC / "wayback_gpu_prices.csv", C.LIST_PRICE_HISTORY):
        wb = load_manual(f)
        if len(wb):
            frames.append(wb.assign(month=_period(wb["date"]), source="list")
                          [["month", "gpu", "price_usd_per_gpu_hr", "source"]])
    vast = load_manual(C.VAST_HISTORY)
    if len(vast):
        vast = vast.dropna(subset=["gpu"])
        frames.append(vast.assign(month=_period(vast.snapshot_date), source="vast")
                      .rename(columns={"usd_per_gpu_hr": "price_usd_per_gpu_hr"})
                      [["month", "gpu", "price_usd_per_gpu_hr", "source"]])
    if not frames:
        return pd.DataFrame(columns=["month", "gpu", "price_usd_per_gpu_hr", "source"])
    out = pd.concat(frames, ignore_index=True)
    out["price_usd_per_gpu_hr"] = pd.to_numeric(out["price_usd_per_gpu_hr"], errors="coerce")
    return out


def token_obs():
    frames = []
    manual = load_manual(C.MANUAL / "token_prices_history.csv")
    if len(manual):
        frames.append(manual.assign(source=manual.get("source", "manual")))
    # OpenRouter headline price: archived (Wayback) and collected daily, same definition
    for f in (C.PROC / "wayback_token_prices.csv", C.OPENROUTER_LISTED_HISTORY):
        wb = load_manual(f)
        if len(wb):
            frames.append(wb[["date", "model", "usd_per_m_input", "usd_per_m_output", "source"]])
    orr = load_manual(C.OPENROUTER_HISTORY)
    if len(orr):
        frames.append(orr[["date", "model", "provider", "usd_per_m_input", "usd_per_m_output", "source"]])
    if not frames:
        return pd.DataFrame(columns=["date", "model", "series", "usd_per_m_input", "usd_per_m_output", "month"])
    t = pd.concat(frames, ignore_index=True)
    t["series"] = t["model"].map(C.lineage_map()).fillna(t["model"])
    for c in ["usd_per_m_input", "usd_per_m_output"]:
        t[c] = pd.to_numeric(t[c], errors="coerce")
    t["month"] = _period(t["date"])
    t["blended"] = t["usd_per_m_output"] + C.INPUT_PER_OUTPUT * t["usd_per_m_input"]
    return t


def throughput():
    parts = [p for p in (load_manual(C.MANUAL / "throughput.csv"), load_manual(C.THROUGHPUT_DERIVED)) if len(p)]
    if not parts:
        return pd.DataFrame()
    t = pd.concat(parts, ignore_index=True)
    t["series"] = t["model"].map(C.lineage_map()).fillna(t["model"])
    t["date"] = pd.to_datetime(t["date"])
    t["output_tok_s_per_gpu"] = pd.to_numeric(t["output_tok_s_per_gpu"], errors="coerce")
    return t.sort_values("date")


def throughput_by_month(tput, gpu, series, months):
    t = tput[(tput.gpu == gpu) & (tput.series == series)] if len(tput) else tput
    if t.empty:
        return pd.Series(np.nan, index=months)
    left = pd.DataFrame({"ts": months.to_timestamp()})
    m = pd.merge_asof(left, t[["date", "output_tok_s_per_gpu"]], left_on="ts", right_on="date", direction="backward")
    m["output_tok_s_per_gpu"] = m["output_tok_s_per_gpu"].fillna(t["output_tok_s_per_gpu"].iloc[0])
    return pd.Series(m["output_tok_s_per_gpu"].values, index=months)


def owned_hw_per_gpu_hr(gpu):
    """Server price spread over its life, per GPU per hour of use."""
    capex = C.GPU_SPECS[gpu]["server_capex_usd"]
    if not capex:
        return np.nan
    return capex / C.GPU_SPECS[gpu]["gpus_per_server"] / (C.HW_LIFE_YEARS * 8760 * C.HW_UTILIZATION)


def hw_cost_per_gpu_hr(gpu):
    hw = owned_hw_per_gpu_hr(gpu)
    return hw if C.INCLUDE_HARDWARE and np.isfinite(hw) else 0.0


def _live_first(obs, key, value, live, months, cols):
    """Monthly median; months with live daily data use only that, earlier months use the archived prices."""
    def monthly(df):
        return df.groupby(["month", key])[value].median().unstack(key).reindex(index=months, columns=cols)
    is_live = obs["source"].eq(live)
    out = monthly(obs[is_live]).combine_first(monthly(obs[~is_live]))
    return out.interpolate(limit=3, limit_area="inside")


def build_panel():
    months = C.months()
    pw, power_latest = power_cost(months)
    ro = rental_obs()
    rental = _live_first(ro, "gpu", "price_usd_per_gpu_hr", live="vast", months=months, cols=C.GPUS)
    to = token_obs()
    token_price = _live_first(to, "series", "blended", live="openrouter", months=months, cols=C.MODEL_NAMES)
    tput = throughput()

    rows = []
    for g in C.GPUS:
        for s in C.MODEL_NAMES:
            tps = throughput_by_month(tput, g, s, months)
            df = pd.DataFrame({"power": pw[g], "rental": rental[g], "token_price_blended": token_price[s],
                               "tok_s_per_gpu": tps})
            df["token_rev"] = df.tok_s_per_gpu * C.TOKEN_LOAD_FACTOR * 3600 / 1e6 * df.token_price_blended
            df["hardware"] = hw_cost_per_gpu_hr(g)
            df["own_cost"] = df.power + owned_hw_per_gpu_hr(g)   # electricity + hardware when you own the GPU
            df["gpu"], df["model"] = g, s
            rows.append(df.rename_axis("month").reset_index())
    panel = pd.concat(rows, ignore_index=True).dropna(subset=["rental"])
    panel["compute_spread"] = panel.rental - panel.power - panel.hardware
    panel["inference_spread"] = panel.token_rev - panel.rental
    panel["own_spread"] = panel.token_rev - panel.own_cost   # selling tokens on a GPU you own
    panel["power_pct_of_rental"] = panel.power / panel.rental
    return panel, dict(power_latest=power_latest, rental_obs=ro, token_obs=to, tput=tput)


def _clean(o):
    # JSON-safe: NaN/inf -> null, numpy scalars -> Python, rounded to keep the file small.
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return None if not math.isfinite(o) else round(float(o), 5)
    if isinstance(o, (pd.Period, pd.Timestamp, dt.date)):
        return str(o)[:10]
    return o


def records(df):
    return [_clean(r) for r in df.to_dict(orient="records")]


LISTED_SOURCES = ("openrouter (wayback)", "openrouter listed")
FLAG_RATIO = 1.25   # a month is flagged when its highest headline price is >25% above its lowest


def _q(p):
    return lambda x: x.quantile(p)


def _rental_history(ro):
    """Per month and GPU: provider list price (archived + daily) and the Vast.ai marketplace median and range."""
    if not len(ro):
        return pd.DataFrame()
    lst = (ro[ro.source.eq("list")].groupby(["month", "gpu"])["price_usd_per_gpu_hr"]
           .agg(list="median", list_n="size"))
    vast = (ro[ro.source.eq("vast")].groupby(["month", "gpu"])["price_usd_per_gpu_hr"]
            .agg(vast="median", vast_p25=_q(0.25), vast_p75=_q(0.75), vast_n="size"))
    return lst.join(vast, how="outer").reset_index()


def _token_history(to):
    """Per month and model: OpenRouter's headline price (median of every snapshot that month, flagged when it
    moved a lot within the month) and, where collected, the live median and range across providers."""
    if not len(to):
        return pd.DataFrame()
    listed = (to[to.source.isin(LISTED_SOURCES)].sort_values("date").groupby(["month", "series"])
              .agg(listed=("blended", "median"), listed_lo=("blended", "min"), listed_hi=("blended", "max"),
                   listed_n=("blended", "size"), model=("model", "last")))
    listed["flagged"] = listed.listed_hi > FLAG_RATIO * listed.listed_lo
    live = (to[to.source.eq("openrouter")].groupby(["month", "series"])["blended"]
            .agg(median="median", p25=_q(0.25), p75=_q(0.75), providers="size"))
    return listed.join(live, how="outer").reset_index()


def site_payload(panel, parts):
    ro, to, tput = parts["rental_obs"], parts["token_obs"], parts["tput"]
    vast = load_manual(C.VAST_HISTORY).dropna(subset=["gpu"]) if C.VAST_HISTORY.exists() else pd.DataFrame()
    orr = load_manual(C.OPENROUTER_HISTORY)

    daily_rental = pd.DataFrame()
    if len(vast):
        q = vast.groupby(["snapshot_date", "gpu"])["usd_per_gpu_hr"]
        daily_rental = pd.DataFrame({"median": q.median(), "p25": q.quantile(0.25), "p75": q.quantile(0.75),
                                     "offers": q.size()}).reset_index().rename(columns={"snapshot_date": "date"})
    daily_tokens = pd.DataFrame()
    if len(orr):
        o = orr.copy()
        o["blended"] = o.usd_per_m_output + C.INPUT_PER_OUTPUT * o.usd_per_m_input
        q = o.groupby(["date", "model"])
        daily_tokens = pd.DataFrame({"usd_in": q.usd_per_m_input.median(), "usd_out": q.usd_per_m_output.median(),
                                     "blended": q.blended.median(), "providers": q.size()}).reset_index()

    latest_month = panel.dropna(subset=["token_rev"]).month.max() if len(panel) else None
    latest = panel[panel.month == latest_month].copy() if latest_month is not None else panel.iloc[0:0]
    # Separate input / output medians for the latest month (the calculator re-blends them at any ratio)
    tm = to[to.month == latest_month].groupby("series")[["usd_per_m_input", "usd_per_m_output"]].median()
    latest["usd_in"] = latest.model.map(tm["usd_per_m_input"]) if len(tm) else np.nan
    latest["usd_out"] = latest.model.map(tm["usd_per_m_output"]) if len(tm) else np.nan
    rn = ro[ro.month == latest_month].groupby("gpu").size()
    latest["rental_observations"] = latest.gpu.map(rn)
    if len(tput):
        last_t = tput.groupby(["gpu", "series"]).tail(1).set_index(["gpu", "series"])
        idx = list(zip(latest.gpu, latest.model))
        for col, src in [("tput_date", "date"), ("tput_source", "source"), ("tput_url", "source_url"),
                         ("tput_concurrency", "concurrency")]:
            latest[col] = [last_t[src].get(k) if src in last_t else None for k in idx]

    missing = []
    if parts["power_latest"] is None:
        missing.append("power")
    for g in C.GPUS:
        if g not in set(ro.gpu):
            missing.append(f"rental:{g}")
    for s in C.MODEL_NAMES:
        if s not in set(to.series):
            missing.append(f"tokens:{s}")
        for g in C.GPUS:
            if not len(tput) or not ((tput.gpu == g) & (tput.series == s)).any():
                missing.append(f"throughput:{g}:{s}")

    return _clean({
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "latest_month": latest_month,
        "months_of_rental_data": int(panel.month.nunique()) if len(panel) else 0,
        "tracking_since": vast.snapshot_date.min() if len(vast) else None,
        "days_tracked": int(vast.snapshot_date.nunique()) if len(vast) else 0,
        "missing": missing,
        "assumptions": {
            "load_factor": C.LOAD_FACTOR, "pue_case": C.PUE_CASE, "pue": C.PUE_SCENARIOS[C.PUE_CASE],
            "pue_scenarios": C.PUE_SCENARIOS, "input_per_output": C.INPUT_PER_OUTPUT,
            "token_load_factor": C.TOKEN_LOAD_FACTOR, "target_interactivity": C.TARGET_INTERACTIVITY,
            "power_state": C.POWER_STATE, "power_sector": C.POWER_SECTOR, "include_hardware": C.INCLUDE_HARDWARE,
            "hw_life_years": C.HW_LIFE_YEARS, "hw_utilization": C.HW_UTILIZATION,
        },
        "gpus": {g: {"gpu_kw": s["gpu_kw"], "server_kw": s["server_kw"], "kw_per_gpu": C.kw_per_gpu(g),
                     "server_capex_usd": s["server_capex_usd"], "hw_per_gpu_hr": owned_hw_per_gpu_hr(g)}
                 for g, s in C.GPU_SPECS.items()},
        "models": C.MODEL_NAMES,
        "power": parts["power_latest"],
        "latest": records(latest),
        "panel": records(panel),
        "daily_rental": records(daily_rental),
        "daily_tokens": records(daily_tokens),
        "rental_history": records(_rental_history(ro)),
        "token_history": records(_token_history(to)),
    })


def main():
    panel, parts = build_panel()
    C.PROC.mkdir(parents=True, exist_ok=True)
    panel.to_csv(C.PROC / "spark_spread_panel.csv", index=False)
    payload = site_payload(panel, parts)
    C.SITE_DATA.mkdir(parents=True, exist_ok=True)
    out = C.SITE_DATA / "spark.json"
    out.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"Panel: {len(panel)} rows, latest month {payload['latest_month']}, "
          f"{payload['days_tracked']} days of Vast snapshots. Missing: {payload['missing'] or 'none'}")
    print(f"Wrote {out.relative_to(C.ROOT)} ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
