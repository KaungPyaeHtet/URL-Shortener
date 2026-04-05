#!/usr/bin/env python3
"""
Run Locust headless, export CSV, and write loadtests/BASELINE_AUTO.md (latency + error rate).

Prerequisites: API running (e.g. uv run run.py), dev deps (uv sync --group dev).

  uv run python scripts/record_load_baseline.py
  uv run python scripts/record_load_baseline.py --host http://127.0.0.1:5000 --users 50 --run-time 60s
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCUSTFILE = ROOT / "loadtests" / "locustfile.py"
RESULTS_DIR = ROOT / "loadtests" / "results"
OUT_MD = ROOT / "loadtests" / "BASELINE_AUTO.md"


def _int(row: dict, key: str) -> int:
    v = row.get(key, "") or "0"
    return int(float(v))


def _float(row: dict, key: str) -> float:
    v = row.get(key, "") or "0"
    return float(v)


def parse_stats_csv(path: Path) -> tuple[dict, list[dict]]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    agg = None
    endpoints: list[dict] = []
    for row in rows:
        name = (row.get("Name") or "").strip()
        if name == "Aggregated":
            agg = row
        else:
            if name and _int(row, "Request Count") > 0:
                endpoints.append(row)
    if agg is None and rows:
        agg = rows[-1]
    if agg is None:
        raise SystemExit(f"No stats in {path}")
    return agg, endpoints


def error_rate_pct(row: dict) -> float:
    n = _int(row, "Request Count")
    if n == 0:
        return 0.0
    return 100.0 * _int(row, "Failure Count") / n


def render_md(
    *,
    agg: dict,
    endpoints: list[dict],
    host: str,
    users: int,
    spawn_rate: int,
    run_time: str,
    csv_path: Path,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    total_req = _int(agg, "Request Count")
    total_fail = _int(agg, "Failure Count")
    er = error_rate_pct(agg)

    lines = [
        "# Auto-generated load baseline",
        "",
        f"_Generated: {now}_",
        "",
        "## Run parameters",
        "",
        f"| Parameter | Value |",
        f"|-----------|-------|",
        f"| Host | `{host}` |",
        f"| Concurrent users | {users} |",
        f"| Spawn rate | {spawn_rate} |",
        f"| Duration | {run_time} |",
        f"| Locustfile | `loadtests/locustfile.py` |",
        f"| Raw CSV | `{csv_path.relative_to(ROOT)}` |",
        "",
        "## Latency & error rate (aggregated)",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total requests | {total_req:,} |",
        f"| Failures | {total_fail} |",
        f"| **Error rate** | **{er:.2f}%** |",
        f"| Avg response time (ms) | {_float(agg, 'Average Response Time'):.0f} |",
        f"| Median (ms) | {_float(agg, 'Median Response Time'):.0f} |",
        f"| Min (ms) | {_float(agg, 'Min Response Time'):.0f} |",
        f"| Max (ms) | {_float(agg, 'Max Response Time'):.0f} |",
        f"| Requests/s | {_float(agg, 'Requests/s'):.2f} |",
        "",
    ]

    pct_order = [
        "50%",
        "66%",
        "75%",
        "80%",
        "90%",
        "95%",
        "98%",
        "99%",
        "99.9%",
        "99.99%",
        "100%",
    ]
    pct_rows = [(k, agg[k]) for k in pct_order if k in agg and str(agg[k]).strip() not in ("", "N/A")]
    if pct_rows:
        lines.extend(["### Response time percentiles (aggregated, ms)", "", "| Percentile | ms |", "|------------|----|"])
        for k, v in pct_rows:
            try:
                val = float(v)
            except (TypeError, ValueError):
                continue
            lines.append(f"| {k} | {val:.0f} |")
        lines.append("")

    if endpoints:
        lines.extend(
            [
                "## Per endpoint",
                "",
                "| Name | Requests | Failures | Error % | Avg ms | RPS |",
                "|------|----------|----------|---------|--------|-----|",
            ]
        )
        for row in endpoints:
            lines.append(
                f"| `{row.get('Name', '')}` | {_int(row, 'Request Count'):,} | "
                f"{_int(row, 'Failure Count')} | {error_rate_pct(row):.2f}% | "
                f"{_float(row, 'Average Response Time'):.0f} | {_float(row, 'Requests/s'):.2f} |"
            )
        lines.append("")

    p95_txt = "—"
    if "95%" in agg:
        try:
            p95_txt = f"{float(agg['95%']):.0f}"
        except (TypeError, ValueError):
            pass
    lines.extend(
        [
            "## One-liner (submission blurb)",
            "",
            f"> {total_req:,} requests, **{er:.2f}% errors**, avg **{_float(agg, 'Average Response Time'):.0f} ms**, "
            f"p95 **{p95_txt} ms**.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Locust and write BASELINE_AUTO.md from CSV stats.")
    parser.add_argument("--host", default="http://127.0.0.1:5000", help="Target base URL")
    parser.add_argument("--users", type=int, default=50, help="Concurrent users")
    parser.add_argument("--spawn-rate", type=int, default=50, help="Users started per second")
    parser.add_argument("--run-time", default="60s", help="Locust --run-time, e.g. 60s")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=OUT_MD,
        help=f"Markdown output (default: {OUT_MD})",
    )
    args = parser.parse_args()

    if not LOCUSTFILE.is_file():
        raise SystemExit(f"Missing {LOCUSTFILE}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    csv_base = str(RESULTS_DIR / f"baseline_{stamp}")

    cmd = [
        sys.executable,
        "-m",
        "locust",
        "-f",
        str(LOCUSTFILE),
        "--host",
        args.host,
        "--users",
        str(args.users),
        "--spawn-rate",
        str(args.spawn_rate),
        "--run-time",
        args.run_time,
        "--headless",
        f"--csv={csv_base}",
    ]
    print("Running:", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)

    stats_path = Path(csv_base + "_stats.csv")
    if not stats_path.is_file():
        raise SystemExit(f"Expected Locust CSV at {stats_path}")

    agg, endpoints = parse_stats_csv(stats_path)
    md = render_md(
        agg=agg,
        endpoints=endpoints,
        host=args.host,
        users=args.users,
        spawn_rate=args.spawn_rate,
        run_time=args.run_time,
        csv_path=stats_path,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(md, encoding="utf-8")
    print(f"Wrote {args.output}", flush=True)


if __name__ == "__main__":
    main()
