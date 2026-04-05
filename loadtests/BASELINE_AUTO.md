# Auto-generated load baseline

_Generated: 2026-04-05 08:34:28 UTC_

## Run parameters

| Parameter | Value |
|-----------|-------|
| Host | `http://127.0.0.1:5000` |
| Concurrent users | 5 |
| Spawn rate | 5 |
| Duration | 3s |
| Locustfile | `loadtests/locustfile.py` |
| Raw CSV | `loadtests/results/baseline_20260405_083425_stats.csv` |

## Latency & error rate (aggregated)

| Metric | Value |
|--------|-------|
| Total requests | 34 |
| Failures | 0 |
| **Error rate** | **0.00%** |
| Avg response time (ms) | 49 |
| Median (ms) | 39 |
| Min (ms) | 21 |
| Max (ms) | 115 |
| Requests/s | 17.23 |

### Response time percentiles (aggregated, ms)

| Percentile | ms |
|------------|----|
| 50% | 40 |
| 66% | 43 |
| 75% | 53 |
| 80% | 64 |
| 90% | 110 |
| 95% | 110 |
| 98% | 110 |
| 99% | 110 |
| 99.9% | 110 |
| 99.99% | 110 |
| 100% | 110 |

## Per endpoint

| Name | Requests | Failures | Error % | Avg ms | RPS |
|------|----------|----------|---------|--------|-----|
| `GET /` | 7 | 0 | 0.00% | 50 | 3.55 |
| `GET /health` | 27 | 0 | 0.00% | 48 | 13.68 |

## One-liner (submission blurb)

> 34 requests, **0.00% errors**, avg **49 ms**, p95 **110 ms**.
