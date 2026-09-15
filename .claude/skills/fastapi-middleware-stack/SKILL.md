---
name: fastapi-middleware-stack
description: Use when setting up a new FastAPI app, adding cross-cutting middleware to an existing one, or debugging issues like "CORS is broken", "security headers missing from error responses", "logs don't include the request ID", "TrustedHost is returning 400s without HSTS", or "what's the right order for these middlewares?". Triggers on phrases like "FastAPI middleware", "CORS", "TrustedHost", "security headers", "request logging", "request_id", "structured logging", "X-Request-ID", "app.add_middleware", "middleware order", or any task that involves wiring `CORSMiddleware`, `TrustedHostMiddleware`, `SecurityHeadersMiddleware`, or a request-logging middleware together.
---

# Canonical FastAPI middleware stack

Middleware order in FastAPI is *not* "the order they appear in your file". Starlette wraps each `app.add_middleware(...)` *around* the previous one — so the **last** one you add is the **first** one the request hits. That fact alone causes most of the bugs in this space: HSTS missing from 400 responses, request IDs missing from CORS preflights, security headers appearing on some responses and not others.

This skill prescribes a stack ordering that holds up under inspection: every response, including errors emitted by middleware itself, carries the headers and log lines you expect.

## The order (and why)

Mounted in this order (so request flow is outermost-to-innermost as listed):

```python
# 1. RequestLoggingMiddleware  ← OUTERMOST: sees everything, including
#                                 errors from the other middlewares
app.add_middleware(RequestLoggingMiddleware)

# 2. SecurityHeadersMiddleware ← so headers land on every response,
#                                 including 400s from TrustedHost
app.add_middleware(SecurityHeadersMiddleware, is_production=settings.is_production)

# 3. TrustedHostMiddleware     ← reject bad Host headers before they
#                                 reach CORS / app code
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts or ["*"])

# 4. CORSMiddleware            ← INNERMOST: handles preflights closest
#                                 to the app
app.add_middleware(CORSMiddleware, allow_origins=cors_origins, ...)
```

**Request flow:** RequestLogging → SecurityHeaders → TrustedHost → CORS → app.
**Response flow:** app → CORS → TrustedHost → SecurityHeaders → RequestLogging.

The key invariant: when TrustedHost rejects a request with a 400, the response still flows back through SecurityHeaders (so HSTS and security headers are applied) and RequestLogging (so the rejected request gets a log line and an X-Request-ID for debugging). That only works because those two are mounted *after* TrustedHost in the `add_middleware` call sequence, which puts them *outside* TrustedHost in the request lifecycle.

### Why these four, in this position

| Middleware | Position | Reason |
|---|---|---|
| RequestLogging | Outermost | Must see every request including those rejected by inner middlewares. Sets the `request_id` contextvar before anything else logs. |
| SecurityHeaders | After RequestLogging | Applies to every response, including 400s from TrustedHost. Strips no headers, only adds. |
| TrustedHost | After SecurityHeaders | Rejects requests with bad `Host` headers before they reach CORS or the app. Defense against Host-header injection. |
| CORS | Innermost (of these) | Preflight handling is close to the route; CORS adds response headers that the outer middlewares then pass through unchanged. |

Anything else (rate limiting, auth, etc.) is per-route, not global middleware — keep it that way.

## Request-ID propagation

The pattern is a single `ContextVar`, set by the outermost middleware, read by every logger via a logging filter.

```python
# app/core/logging.py
from contextvars import ContextVar
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


# app/middleware/request_logging.py
from app.core.logging import request_id_ctx

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path in {"/health", "/ready"}:
            return await call_next(request)

        rid = uuid.uuid4().hex
        request_id_ctx.set(rid)
        start = time.perf_counter()

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = rid

        log_level = logging.INFO
        if response.status_code >= 400: log_level = logging.WARNING
        if response.status_code >= 500: log_level = logging.ERROR

        logger.log(log_level, "%s %s %d %.1fms ip=%s",
                   request.method, request.url.path, response.status_code,
                   duration_ms, request.client.host if request.client else "unknown")
        return response
```

The `ContextVar` works because each request is its own asyncio Task and `ContextVar` is task-local. The `_RequestIdFilter` automatically appends the current request_id to every log record produced anywhere during the request.

## Security headers

```python
# app/middleware/security_headers.py

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, is_production: bool = False):
        super().__init__(app)
        self.is_production = is_production

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "0"   # modern best practice
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if self.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response
```

**HSTS only in production.** Sending it over plain HTTP during local dev confuses browsers that honour it — they pin your localhost to HTTPS and you spend an afternoon figuring out why nothing connects. Gate it on `is_production`.

**`X-XSS-Protection: 0`** is the current best practice. The legacy `1; mode=block` value has been broken in past browsers (introducing new XSS vectors). Modern defense is CSP, not the XSS auditor.

**No CSP here.** Content-Security-Policy is per-application — a single header value tuned to your front-end's loading patterns. Add it as a constant in the middleware *if* you have a stable policy, otherwise keep it on the response of the HTML route that serves the SPA.

## TrustedHost

```python
allowed_hosts = settings.allowed_hosts if settings.allowed_hosts else ["*"]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
```

The wildcard fallback is for local dev. In production, `production-config-validation` rejects boot if `ALLOWED_HOSTS` is empty — so the wildcard is unreachable in production. Healthcheck quirk: many platforms (Railway, Render, Fly, etc.) probe via a synthetic `Host` header. **Add the platform's healthcheck host to the allowlist** or your deploys will fail with 400s. Example: `ALLOWED_HOSTS="api.example.com,healthcheck.railway.app"`.

## CORS — two branches, one decision

```python
cors_origins = settings.cors_origins
if cors_origins:
    app.add_middleware(CORSMiddleware,
        allow_origins=cors_origins, allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"])
else:
    # Dev fallback: wildcard origin, no credentials.
    # The CORS spec forbids '*' with allow_credentials=True; we drop creds
    # rather than silently misconfiguring the browser.
    app.add_middleware(CORSMiddleware,
        allow_origins=["*"], allow_credentials=False,
        allow_methods=["*"], allow_headers=["*"])
```

The two branches exist because `allow_origins=["*"]` and `allow_credentials=True` are mutually exclusive *by spec*. Browsers will reject the combination. The dev fallback keeps wide-open access for local testing; production goes through the validator-enforced explicit allowlist.

## Logging configuration

```python
# Production: JSON, Dev: human-readable, both: include request_id

def setup_logging() -> None:
    settings = get_settings()
    level = settings.LOG_LEVEL.upper()

    if settings.is_production:
        formatter_cfg = {
            "class": "pythonjsonlogger.json.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s",
        }
    else:
        formatter_cfg = {
            "format": "%(asctime)s %(levelname)-8s [%(name)s] %(message)s (rid=%(request_id)s)",
            "datefmt": "%H:%M:%S",
        }

    logging.config.dictConfig({
        "version": 1, "disable_existing_loggers": False,
        "filters": {"request_id": {"()": _RequestIdFilter}},
        "formatters": {"default": formatter_cfg},
        "handlers": {"console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "filters": ["request_id"],
            "stream": "ext://sys.stdout",
        }},
        "loggers": {
            "myapp": {"level": level, "handlers": ["console"], "propagate": False},
            "uvicorn.access": {
                "level": "WARNING" if settings.is_production else level,
                "handlers": ["console"], "propagate": False,
            },
        },
        "root": {"level": level, "handlers": ["console"]},
    })
```

`uvicorn.access` gets pinned to WARNING in production because the request-logging middleware already logs every request — uvicorn's own access log is a duplicate. Drop it.

## Design rules — and why they matter

### Rule 1: The order in `add_middleware` is reversed at runtime

This is the single most important fact. The *last* `add_middleware` call is the *first* middleware on the request path. Treat the file as "outermost on top" and accept that this is the opposite of intuition.

### Rule 2: RequestLogging is always outermost

Set the request_id contextvar before anything else logs. If RequestLogging is inner, logs from outer middleware miss the correlation id.

### Rule 3: SecurityHeaders is outside TrustedHost

So that a TrustedHost rejection (400) still gets security headers applied. If you put SecurityHeaders inside TrustedHost, your error responses leak insecurely-configured browsers.

### Rule 4: CORS is innermost (of the four)

CORS deals in preflight + simple-request mechanics that are closest to the route. Keep it adjacent to the app; let TrustedHost and SecurityHeaders wrap around it.

### Rule 5: Don't catch exceptions in middleware unless you have to

A try/except in a middleware swallows information from the global exception handler. Let exceptions bubble up to the FastAPI handler chain. The only middleware that should catch is RequestLogging, and only to ensure the response gets logged before re-raising.

### Rule 6: Skip the health-check paths in RequestLogging

`/health` and `/ready` are probed every few seconds. Logging them drowns the signal in noise. Bypass logging for these paths — but still let them flow through CORS and SecurityHeaders (cheap, no harm).

### Rule 7: HSTS only in production

It pins your domain to HTTPS for the configured `max-age`. If you ship HSTS from a dev server over plain HTTP, the browser remembers and refuses HTTP-only access until the pin expires (up to 2 years with `includeSubDomains`).

### Rule 8: Wildcard CORS *or* credentials — never both

The browser will refuse. Fork the configuration: explicit-origins branch with credentials, wildcard branch without.

### Rule 9: One ContextVar, one filter, one configuration

Don't sprinkle `request_id` extraction into individual log calls. The filter takes care of it for every log record produced anywhere during the request — that's the whole point of contextvars.

### Rule 10: `BaseHTTPMiddleware` for these, not ASGI middleware classes

`BaseHTTPMiddleware` is the simpler Starlette base class — receives Request, returns Response. ASGI-level middleware (`async def __call__(scope, receive, send)`) is more powerful but more error-prone. For these four jobs (logging, headers, host check, CORS) `BaseHTTPMiddleware` is right.

## Reviewing a PR that touches middleware

- [ ] If new middleware is being added, what's its position? Is the file ordered outermost-on-top?
- [ ] Does the new middleware catch exceptions? Push back unless absolutely necessary.
- [ ] Does it set headers on the request side or the response side? (Almost always response side.)
- [ ] If it logs, does it use the module logger so the request_id filter applies?
- [ ] Does it have a path-skip list for health/metrics paths if appropriate?
- [ ] Is HSTS gated on production?
- [ ] CORS — does the change risk wildcard + credentials? (Browsers reject this combo.)
- [ ] Are new TrustedHost entries being added to allow a new platform / domain?

## Common failure modes

| Symptom | Likely cause |
|---|---|
| `X-Request-ID` missing from some responses | RequestLogging isn't outermost |
| Security headers missing from 400 responses | SecurityHeaders is inside TrustedHost |
| Browser rejects CORS preflight with credentials | `allow_origins=["*"]` is set with `allow_credentials=True` |
| Deploy fails with 400 on healthcheck | Platform's healthcheck host not in `ALLOWED_HOSTS` |
| Browser pinned to HTTPS on localhost forever | HSTS shipped in dev; clear browser HSTS cache and gate on `is_production` |
| Request IDs are correlated wrong (one request shows another's id) | `ContextVar` mutated outside the per-request middleware; check for stray `request_id_ctx.set()` calls in code |
| `uvicorn.access` produces duplicate request logs | Default logging config; pin `uvicorn.access` to WARNING in production |

## Companion skills

- **`production-config-validation`** — `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `TRUSTED_PROXIES` are validated there.
- **`audit-log-pattern`** — pulls `request_id` from the contextvar this skill sets, for cross-row correlation.
- **`integration-resilience`** — outbound HTTP logs benefit from the same request_id; the filter applies automatically because both use the project logger.
