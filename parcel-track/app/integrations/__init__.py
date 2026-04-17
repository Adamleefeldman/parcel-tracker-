"""Outbound integrations with third-party HTTP APIs.

All network traffic to external providers goes through `app.integrations._http.build_client`,
which enforces per-provider timeouts, retries, and a Redis-backed circuit breaker.
Typed exceptions from `app.integrations._exceptions` give callers a stable contract
independent of the underlying transport.
"""
