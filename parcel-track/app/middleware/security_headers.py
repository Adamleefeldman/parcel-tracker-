"""
Security headers middleware.

Adds a baseline set of defensive HTTP headers to every response. These
protect against common browser-side attacks (clickjacking, MIME-sniffing,
XSS reflection) and tell search engines not to index the API.

Headers added:
    X-Content-Type-Options: nosniff
    X-Frame-Options: DENY
    Strict-Transport-Security: max-age=63072000; includeSubDomains
    Referrer-Policy: strict-origin-when-cross-origin
    X-XSS-Protection: 0            (modern best practice — rely on CSP, not the broken XSS auditor)
    X-Robots-Tag: noindex, nofollow
    Permissions-Policy: camera=(), microphone=(), geolocation=()

HSTS is only emitted in production — sending it over plain HTTP during local
dev would confuse browsers that honour it.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, is_production: bool = False) -> None:
        super().__init__(app)
        self.is_production = is_production

    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        if self.is_production:
            # 2 years, include subdomains. Only meaningful over TLS.
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"

        return response
