"""Prometheus instrumentation for the Flask app.

Exposes metrics at GET /prom — the existing JSON /metrics endpoint is kept
for human-readable system stats.

Metrics are bound to a dedicated CollectorRegistry (not the global default) so
we never collide with prometheus_client's built-in process collectors or with
a second import of this module during pytest collection.

Metrics exported:
  http_requests_total          (counter)  requests by method/path/status
  http_request_duration_seconds (histogram) latency by method/path
  http_requests_in_flight      (gauge)    concurrent requests in progress
  system_cpu_percent           (gauge)    host CPU %
  system_memory_percent        (gauge)    host RAM %
  app_process_resident_memory_bytes (gauge) process RSS (prefixed to avoid name clashes)
"""

import time
from typing import Any

import psutil
from flask import Flask, Response, request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

_state: dict[str, Any] | None = None


def _metrics() -> dict[str, Any]:
    """Create metrics once per process on a private registry."""
    global _state
    if _state is not None:
        return _state

    reg = CollectorRegistry()
    _state = {
        "registry": reg,
        "REQUEST_COUNT": Counter(
            "http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status"],
            registry=reg,
        ),
        "REQUEST_LATENCY": Histogram(
            "http_request_duration_seconds",
            "HTTP request latency",
            ["method", "endpoint"],
            buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
            registry=reg,
        ),
        "REQUESTS_IN_FLIGHT": Gauge(
            "http_requests_in_flight",
            "HTTP requests currently being processed",
            registry=reg,
        ),
        "CPU_GAUGE": Gauge(
            "system_cpu_percent",
            "Host CPU usage percent",
            registry=reg,
        ),
        "MEM_GAUGE": Gauge(
            "system_memory_percent",
            "Host memory usage percent",
            registry=reg,
        ),
        "PROC_RSS": Gauge(
            "app_process_resident_memory_bytes",
            "Process resident memory (RSS) bytes",
            registry=reg,
        ),
    }
    return _state


def _refresh_system_gauges(m: dict[str, Any]) -> None:
    m["CPU_GAUGE"].set(psutil.cpu_percent())
    mem = psutil.virtual_memory()
    m["MEM_GAUGE"].set(mem.percent)
    try:
        proc = psutil.Process()
        m["PROC_RSS"].set(proc.memory_info().rss)
    except psutil.NoSuchProcess:
        pass


def _normalise_path(path: str) -> str:
    """Replace numeric path segments to avoid high cardinality."""
    import re

    return re.sub(r"/\d+", "/<id>", path)


def init_prom_metrics(app: Flask) -> None:
    """Register before/after request hooks and the /prom scrape endpoint."""
    if getattr(app, "_prom_metrics_attached", False):
        return
    app._prom_metrics_attached = True

    m = _metrics()

    @app.before_request
    def _start_timer():
        request._prom_start = time.perf_counter()
        m["REQUESTS_IN_FLIGHT"].inc()

    @app.after_request
    def _record_metrics(response):
        m["REQUESTS_IN_FLIGHT"].dec()
        endpoint = _normalise_path(request.path)
        elapsed = time.perf_counter() - getattr(request, "_prom_start", time.perf_counter())
        m["REQUEST_COUNT"].labels(
            method=request.method,
            endpoint=endpoint,
            status=str(response.status_code),
        ).inc()
        m["REQUEST_LATENCY"].labels(method=request.method, endpoint=endpoint).observe(elapsed)
        return response

    @app.route("/prom")
    def prometheus_metrics():
        _refresh_system_gauges(m)
        return Response(
            generate_latest(m["registry"]),
            mimetype=CONTENT_TYPE_LATEST,
        )
