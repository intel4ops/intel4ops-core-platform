from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        correlation_id = request.headers.get("X-Correlation-ID") or request_id
        request.state.gateway_transport_context = {
            "request_id": request_id,
            "correlation_id": correlation_id,
            "client_code": request.headers.get("X-Intel4Ops-Client", "intel4ops-web"),
            "locale": request.headers.get("Accept-Language", "en-US").split(",")[0],
            "requested_currency": request.headers.get("X-Reporting-Currency"),
            "timestamp": datetime.now(UTC),
        }
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = correlation_id
        return response
