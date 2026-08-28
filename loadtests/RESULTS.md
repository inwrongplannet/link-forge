# Load Testing Results

This document tracks the performance metrics achieved during our load testing iterations. It serves as evidence of meeting our performance goals (1000 RPS, p95 < 100ms, <1% error rate).

## Test Runs

| Date | Configuration (Users/Tool) | RPS Achieved | p50 Latency | p95 Latency | p99 Latency | Error Rate | Notes / Tuning |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| YYYY-MM-DD | 500 VUs, k6 | TBD | TBD | TBD | TBD | TBD | Initial baseline test |
| YYYY-MM-DD | 500 Users, Locust | TBD | TBD | TBD | TBD | TBD | Testing Read/Write ratio (9:1) |
| 2026-08-28 | 500 VUs, k6 (Run 1) | 50 | 9314.7ms | 10527.8ms | 11011.8ms | 0.00% | Uncapped Stress Test |
| 2026-08-28 | 500 VUs, k6 (Run 2) | 50 | 9349.3ms | 10415.5ms | 10881.1ms | 0.00% | Uncapped Stress Test |
| 2026-08-28 | 500 VUs, k6 (Run 3) | 49 | 9499.0ms | 10546.5ms | 11027.0ms | 0.00% | Uncapped Stress Test |
| 2026-08-28 | 500 VUs, k6 (Run 4) | 49 | 9506.3ms | 10454.4ms | 10931.1ms | 0.00% | Uncapped Stress Test |
## Performance Tuning Log

*Document any changes made to the infrastructure, database indexes, or application code here to see how they impact the metrics in the table above.*
