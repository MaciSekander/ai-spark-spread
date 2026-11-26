"""The AI Spark Spread pipeline.

    python -m spark.collect     fetch today's live data (Vast.ai, OpenRouter, EIA) and append it to the history files
    python -m spark.throughput  rebuild data/processed/inferencex_throughput.csv from InferenceX exports in data/raw/inferencex/
    python -m spark.build       compute the panel and write site/src/data/spark.json for the website

The math and assumptions mirror notebooks/01_spark_spread_research.ipynb.
"""
