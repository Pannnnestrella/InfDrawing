"""Prometheus HTTP metrics for the production API."""

from __future__ import annotations

import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

HTTP_REQUESTS = Counter(
    "infdrawing_http_requests_total",
    "Total HTTP requests handled by the API.",
    ("method", "route", "status"),
)
HTTP_DURATION = Histogram(
    "infdrawing_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "route"),
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record bounded-cardinality request counts and latency."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        route = request.scope.get("route")
        route_path = getattr(route, "path", "unmatched")
        labels = (request.method, route_path)
        HTTP_REQUESTS.labels(*labels, str(response.status_code)).inc()
        HTTP_DURATION.labels(*labels).observe(time.perf_counter() - started)
        return response


def metrics_response() -> Response:
    """Return the current Prometheus exposition payload."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
