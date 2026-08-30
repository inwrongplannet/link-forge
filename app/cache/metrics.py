from prometheus_client import Counter, Histogram

cache_hits = Counter("linkforge_cache_hits_total", "Redirect cache hits")
cache_misses = Counter("linkforge_cache_misses_total", "Redirect cache misses")

clicks_buffered = Counter(
    "linkforge_clicks_buffered_total", "Click events buffered in Redis"
)
clicks_flushed = Counter(
    "linkforge_clicks_flushed_total", "Click events flushed to Postgres"
)
flush_cycles = Counter(
    "linkforge_flush_cycles_total", "Flush worker cycles completed"
)
flush_errors = Counter(
    "linkforge_flush_errors_total", "Flush worker cycles that failed"
)
redirect_latency = Histogram(
    "linkforge_redirect_duration_seconds",
    "Redirect request latency (seconds)",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)
