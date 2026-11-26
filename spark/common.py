import re
import time
from pathlib import Path

import pandas as pd
import requests

HTTP = requests.Session()
HTTP.headers["User-Agent"] = "spark-spread-research/0.1 (personal research project)"


def redact(text):
    # Never let an API key reach a log (EIA puts it in the URL, which shows up in HTTP error messages).
    return re.sub(r"(api_key=)[^&\s]+", r"\1***", str(text))


def get_json(url, params=None, headers=None, timeout=60, retries=3):
    last = None
    for attempt in range(1, retries + 1):
        try:
            r = HTTP.get(url, params=params, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:   # noqa: BLE001 - retry anything, report a redacted message
            last = e
            time.sleep(2 * attempt)
    raise RuntimeError(redact(f"{type(last).__name__}: {last}"))


def append_snapshot(df, path, key_cols=None):
    # Append rows to a running CSV, dropping exact duplicates (re-running on the same day is harmless).
    path = Path(path)
    if path.exists():
        old = pd.read_csv(path)
        df = pd.concat([old, df], ignore_index=True)
    df = df.drop_duplicates(subset=key_cols)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return df


def load_manual(path):
    path = Path(path)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path).dropna(how="all")
