// Shared formatting, colours and the spread math (mirrors spark/build.py).

export const COLORS = {
  power: "#E07B39",
  hardware: "#8C8C8C",
  owner: "#3A6EA5",      // compute spread: kept by the GPU owner
  seller: "#4C9A6A",     // inference spread: kept by the token seller
  loss: "#C0392B",       // negative inference spread
  rental: "currentColor"
};

export const MODEL_COLORS = ["#6A4C93", "#1982C4", "#2A9D8F", "#E63946", "#F4A261", "#8D99AE"];
export const GPU_COLORS = ["#4C8BF5", "#E9A23B", "#9C6644", "#2A9D8F"];   // readable on light and dark

export function usd(v, digits = 2) {
  if (v == null || !Number.isFinite(v)) return "n/a";
  const sign = v < -0.5 * 10 ** -digits ? "−" : "";
  return `${sign}$${Math.abs(v).toLocaleString("en-US", {minimumFractionDigits: digits, maximumFractionDigits: digits})}`;
}

export function pct(v, digits = 0) {
  return v == null || !Number.isFinite(v) ? "n/a" : `${(v * 100).toFixed(digits)}%`;
}

export function num(v, digits = 0) {
  return v == null || !Number.isFinite(v) ? "n/a" : v.toLocaleString("en-US", {maximumFractionDigits: digits});
}

// $ earned per GPU hour from selling tokens
export function tokenRevenue({tps, loadFactor, ratio, usdIn, usdOut}) {
  return tps * loadFactor * 3600 / 1e6 * (usdOut + ratio * usdIn);
}

// Throughput (output tok/s per GPU) at which token revenue equals the rental price
export function breakEvenTps({rental, loadFactor, ratio, usdIn, usdOut}) {
  const perTps = loadFactor * 3600 / 1e6 * (usdOut + ratio * usdIn);
  return perTps > 0 ? rental / perTps : Infinity;
}
