"""Rebuild data/processed/inferencex_throughput.csv from InferenceX CSV exports in data/raw/inferencex/.

The raw exports are downloaded by hand from the InferenceX table view and are not committed; the derived
table (a handful of numbers with source URLs) is committed and is what the build uses.
"""
import numpy as np
import pandas as pd

from . import config as C


def add_output_per_gpu(df):
    # InferenceX divides output throughput by decode chips only for disaggregated setups.
    # Convert to output tok/s per GPU across all chips so it compares with non-split setups.
    df = df.copy()
    out = df["Output Token Throughput per Chip (tok/s/chip)"].astype(float)
    disagg = df["Disaggregated"].astype(str).str.lower().eq("true")
    pre = pd.to_numeric(df["Num Prefill Chips"], errors="coerce")
    dec = pd.to_numeric(df["Num Decode Chips"], errors="coerce")
    df["output_tok_s_per_gpu_all"] = np.where(disagg & pre.notna() & dec.notna(), out * dec / (pre + dec), out)
    return df


def at_interactivity(df, target):
    # Best output tok/s per GPU at `target` tok/s/user on the Pareto frontier, log-interpolated.
    pts = df[["Median Interactivity (tok/s/user)", "output_tok_s_per_gpu_all", "Concurrency", "Run URL"]].dropna()
    pts = pts.sort_values("Median Interactivity (tok/s/user)", ascending=False)
    frontier, best_y = [], -np.inf
    for _, r in pts.iterrows():
        if r["output_tok_s_per_gpu_all"] > best_y:
            frontier.append(r)
            best_y = r["output_tok_s_per_gpu_all"]
    f = pd.DataFrame(frontier).sort_values("Median Interactivity (tok/s/user)")
    x = f["Median Interactivity (tok/s/user)"].to_numpy(float)
    y = f["output_tok_s_per_gpu_all"].to_numpy(float)
    if len(f) < 2 or not (x.min() <= target <= x.max()):
        return None
    val = float(np.exp(np.interp(np.log(target), np.log(x), np.log(y))))
    i = int(np.searchsorted(x, target))
    near = f.iloc[[max(i - 1, 0), min(i, len(f) - 1)]]
    return {"output_tok_s_per_gpu": val, "frontier_points": len(f),
            "concurrency": f"{int(near['Concurrency'].iloc[0])}-{int(near['Concurrency'].iloc[1])}",
            "source_url": near["Run URL"].iloc[-1]}


def build(target=C.TARGET_INTERACTIVITY):
    files = sorted((C.RAW / "inferencex").glob("*.csv"))
    if not files:
        raise SystemExit("No InferenceX exports in data/raw/inferencex/")
    ix = pd.concat([pd.read_csv(f, comment="#") for f in files], ignore_index=True).drop_duplicates()
    ix = add_output_per_gpu(ix)
    if not C.ALLOW_SPEC_DECODING and "Spec Decoding" in ix.columns:
        ix = ix[ix["Spec Decoding"].fillna("none").astype(str).str.lower().eq("none")]
    rows = []
    for (model, hw, fw, prec, isl, osl, date), g in ix.groupby(["Model", "Hardware", "Framework", "Precision", "ISL", "OSL", "Date"]):
        m, h = C.INFERENCEX_MODELS.get(str(model).lower()), C.INFERENCEX_HW.get(str(hw).lower())
        if not m or not h or str(fw).lower() != C.FRAMEWORK_PREF.get(m, C.DEFAULT_FRAMEWORK):
            continue
        if m in C.PRECISION_PREF and str(prec).lower() != C.PRECISION_PREF[m]:
            continue
        b = at_interactivity(g, target)
        if b is None:
            print(f"  {model} {hw} {fw} {date}: no config reaches {target} tok/s/user, skipped")
            continue
        rows.append({"date": date, "gpu": h, "model": m, "precision": prec, "framework": fw,
                     "input_len": isl, "output_len": osl, "concurrency": b["concurrency"],
                     "frontier_points": b["frontier_points"], "spec_decoding": "none" if not C.ALLOW_SPEC_DECODING else "any",
                     "output_tok_s_per_gpu": b["output_tok_s_per_gpu"], "tok_s_per_user": target,
                     "source": "InferenceX (SemiAnalysis)", "source_url": b["source_url"]})
    out = pd.DataFrame(rows)
    for model, donor in C.THROUGHPUT_PROXY.items():
        if len(out) and model not in set(out.model) and donor in set(out.model):
            out = pd.concat([out, out[out.model == donor].assign(
                model=model, source=f"InferenceX (SemiAnalysis), {donor} used as proxy")], ignore_index=True)
    out.to_csv(C.THROUGHPUT_DERIVED, index=False)
    print(f"Wrote {len(out)} rows to {C.THROUGHPUT_DERIVED.relative_to(C.ROOT)}")
    return out


if __name__ == "__main__":
    build()
