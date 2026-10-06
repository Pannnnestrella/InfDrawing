"""Run non-destructive production smoke checks with the Python standard library."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class _Check:
    """Describe one HTTP smoke check."""

    name: str
    path: str
    authenticated: bool = False


def _request_json(base_url: str, check: _Check, api_key: str | None, timeout: float) -> object:
    """Request and decode one JSON endpoint."""
    headers = {"Accept": "application/json", "User-Agent": "infdrawing-smoke/1.0"}
    if check.authenticated and api_key:
        headers["X-API-Key"] = api_key
    request = urllib.request.Request(f"{base_url.rstrip('/')}{check.path}", headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError(f"HTTP {response.status}")
        body = response.read().decode("utf-8")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return body.strip()


def _main() -> int:
    """Parse arguments and run safe read-only checks."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1")
    parser.add_argument("--api-key", default=os.getenv("INFDRAWING_API_KEY"))
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument(
        "--include-contract",
        action="store_true",
        help="also check authenticated production contract endpoints",
    )
    args = parser.parse_args()

    checks = [
        _Check("proxy", "/healthz"),
        _Check("api", "/health"),
        _Check("capabilities", "/api/v1/system/capabilities", authenticated=True),
    ]
    if args.include_contract:
        checks.append(_Check("readiness", "/ready"))

    failed = 0
    for check in checks:
        if check.authenticated and not args.api_key:
            print(f"SKIP {check.name}: set INFDRAWING_API_KEY or --api-key")
            continue
        try:
            payload = _request_json(args.base_url, check, args.api_key, args.timeout)
            print(f"PASS {check.name}: {json.dumps(payload, ensure_ascii=False)[:200]}")
        except (urllib.error.URLError, TimeoutError, ValueError, RuntimeError) as exc:
            failed += 1
            print(f"FAIL {check.name}: {exc}", file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
