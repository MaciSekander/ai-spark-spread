"""Assumptions and paths. Keep these in step with section 1 of the notebook and log sources in sources.md."""
import datetime as dt
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW, PROC, MANUAL = DATA / "raw", DATA / "processed", DATA / "manual"
SITE_DATA = ROOT / "site" / "src" / "data"

# Live sources append here every day. These files are committed so history accumulates (see .gitignore).
VAST_HISTORY = RAW / "vast_snapshots.csv"
OPENROUTER_HISTORY = RAW / "openrouter_price_snapshots.csv"
EIA_HISTORY = RAW / "eia_retail_prices.csv"
THROUGHPUT_DERIVED = PROC / "inferencex_throughput.csv"

load_dotenv(ROOT / ".env")   # locally; in GitHub Actions the keys come from repository secrets
EIA_API_KEY = os.getenv("EIA_API_KEY")
VAST_API_KEY = os.getenv("VAST_API_KEY")

START = pd.Period("2023-01", "M")
TODAY = dt.date.today().isoformat()


def months():
    return pd.period_range(START, pd.Period(dt.date.today(), "M"), freq="M")


# ---- Hardware and power -------------------------------------------------------------------------
GPU_SPECS = {
    # gpu_kw: chip spec power. server_kw: 8-GPU server max power. capex: per 8-GPU server (v2).
    "H100": {"gpu_kw": 0.700, "server_kw": 10.2, "gpus_per_server": 8, "server_capex_usd": None},
    "B200": {"gpu_kw": 1.000, "server_kw": 14.3, "gpus_per_server": 8, "server_capex_usd": None},
}
GPUS = list(GPU_SPECS)
LOAD_FACTOR = 0.80
PUE_SCENARIOS = {"hyperscale": 1.10, "industry_avg": 1.56}
PUE_CASE = "industry_avg"
POWER_STATE, POWER_SECTOR = "US", "IND"
EIA_STATES = ["US", "VA", "TX", "GA", "AZ", "OR"]
EIA_SECTORS = ["IND", "COM"]

INCLUDE_HARDWARE = False
HW_LIFE_YEARS = 5
HW_UTILIZATION = 0.70


def kw_per_gpu(gpu):
    s = GPU_SPECS[gpu]
    return s["server_kw"] / s["gpus_per_server"]


# ---- Tokens ---------------------------------------------------------------------------------------
INPUT_PER_OUTPUT = 8.0      # input tokens billed per output token (8K/1K benchmark)
TOKEN_LOAD_FACTOR = 0.60    # average achieved throughput / benchmark throughput

MODELS = {
    "DeepSeek-V3":   r"^deepseek/deepseek-(chat|v3)",
    "DeepSeek-R1":   r"^deepseek/deepseek-r1(?!.*distill)",
    "gpt-oss-120b":  r"^openai/gpt-oss-120b",
    "Llama-3.3-70B": r"^meta-llama/llama-3\.3-70b-instruct",
}
MODEL_NAMES = list(MODELS)
MODEL_LINEAGE = {
    "Llama-3.3-70B": ["Llama-2-70B", "Llama-3-70B", "Llama-3.1-70B", "Llama-3.3-70B"],
    "DeepSeek-V3":   ["DeepSeek-V2", "DeepSeek-V2.5", "DeepSeek-V3"],
    "DeepSeek-R1":   ["DeepSeek-R1"],
    "gpt-oss-120b":  ["gpt-oss-120b"],
}


def lineage_map():
    return {old: new for new, olds in MODEL_LINEAGE.items() for old in olds}


# ---- Throughput (InferenceX) -------------------------------------------------------------------
TARGET_INTERACTIVITY = 50   # median output tok/s per user
INFERENCEX_HW = {"h100": "H100", "b200": "B200"}
INFERENCEX_MODELS = {
    "gpt-oss-120b": "gpt-oss-120b",
    "deepseek-r1-0528": "DeepSeek-R1",
    "llama-3.3-70b-instruct-fp8": "Llama-3.3-70B",
}
PRECISION_PREF = {"gpt-oss-120b": "fp4", "DeepSeek-R1": "fp8", "Llama-3.3-70B": "fp8"}
THROUGHPUT_PROXY = {"DeepSeek-V3": "DeepSeek-R1"}
ALLOW_SPEC_DECODING = False
FRAMEWORK_PREF = {"DeepSeek-R1": "dynamo-trt", "Llama-3.3-70B": "vllm", "gpt-oss-120b": "vllm"}
DEFAULT_FRAMEWORK = "vllm"
