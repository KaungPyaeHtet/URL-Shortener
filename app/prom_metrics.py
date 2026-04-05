"""Prometheus instrumentation for the Flask app.

Exposes metrics at GET /prom — the existing JSON /metrics endpoint is kept
for human-readable system stats.

Metrics exported:
  http_requests_total          (counter)  requests by method/path/status
  http_request_duration_seconds (histogram) latency by method/path
  http_requests_in_flight      (gauge)    concurrent requests in progress
  system_cpu_percent           (gauge)    host CPU %
  system_memory_percent        (gauge)    host RAM %
  process_resident_memory_bytes (gauge)   process RSS
"""

import time

import psutil
from flask import Flask, Response, request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# ── Metric definitions ─────────────────────────────────────────────────────────

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

REQUESTS_IN_FLIGHT = Gauge(
    "http_requests_in_flight",
    "HTTP requests currently being processed",
)

CPU_GAUGE = Gauge("system_cpu_percent", "Host CPU usage percent")
MEM_GAUGE = Gauge("system_memory_percent", "Host memory usage percent")
PROC_RSS = Gauge("process_resident_memory_bytes", "Process resident memory (RSS) bytes")


def _refresh_system_gauges() -> None:
    CPU_GAUGE.set(psutil.cpu_percent())
    mem = psutil.virtual_memory()
    MEM_GAUGE.set(mem.percent)
    try:
        proc = psutil.Process()
        PROC_RSS.set(proc.memory_info().rss)
    except psutil.NoSuchProcess:
        pass


# ── Flask wiring ───────────────────────────────────────────────────────────────

def _normalise_path(path: str) -> str:
    """Replace numeric path segments to avoid high cardinality."""
    import re
    return re.sub(r"/\d+", "/<id>", path)


def init_prom_metrics(app: Flask) -> None:
    """Register before/after request hooks and the /prom scrape endpoint."""

    @app.before_request
    def _start_timer():
        request._prom_start = time.perf_counter()
        REQUESTS_IN_FLIGHT.inc()

    @app.after_request
    def _record_metrics(response):
        REQUESTS_IN_FLIGHT.dec()
        endpoint = _normalise_path(request.path)
        elapsed = time.perf_counter() - getattr(request, "_prom_start", time.perf_counter())
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=endpoint,
            status=str(response.status_code),
        ).inc()
        REQUEST_LATENCY.labels(method=request.method, endpoint=endpoint).observe(elapsed)
        return response

    @app.route("/prom")
    def prometheus_metrics():
        _refresh_system_gauges()
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)
