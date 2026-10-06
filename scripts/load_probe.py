"""Run a bounded HTTP health load probe; dry-run unless --run is supplied."""

from __future__ import annotations

import argparse
import concurrent.futures
import statistics
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class _Result:
    """Store one request result."""

    elapsed_ms: float
    status: int


def _probe(url: str, timeout: float) -> _Result:
    """Issue one GET request."""
    started = time.perf_counter()
    request = urllib.request.Request(url, headers={"User-Agent": "infdrawing-load-probe/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    return _Result((time.perf_counter() - started) * 1000, status)


def _percentile(values: list[float], fraction: float) -> float:
    """Return a nearest-rank percentile."""
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def _main() -> int:
    """Parse arguments, enforce limits, and optionally execute the probe."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1/healthz")
    parser.add_argument("--requests", type=int, default=10)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--run", action="store_true", help="required to send requests")
    args = parser.parse_args()

    if not 1 <= args.requests <= 100:
        parser.error("--requests must be between 1 and 100")
    if not 1 <= args.concurrency <= 10:
        parser.error("--concurrency must be between 1 and 10")
    if args.concurrency > args.requests:
        parser.error("--concurrency cannot exceed --requests")

    print(
        f"Plan: GET {args.url}; requests={args.requests}; "
        f"concurrency={args.concurrency}; timeout={args.timeout}s"
    )
    if not args.run:
        print("Dry run only. Add --run after confirming the target and authorization.")
        return 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        results = list(
            executor.map(lambda _: _probe(args.url, args.timeout), range(args.requests))
        )

    elapsed = [result.elapsed_ms for result in results]
    succeeded = sum(200 <= result.status < 400 for result in results)
    print(
        f"success={succeeded}/{len(results)} "
        f"mean={statistics.fmean(elapsed):.1f}ms "
        f"p50={_percentile(elapsed, 0.50):.1f}ms "
        f"p95={_percentile(elapsed, 0.95):.1f}ms "
        f"max={max(elapsed):.1f}ms"
    )
    return 0 if succeeded == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(_main())
