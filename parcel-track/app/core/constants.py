"""
Application-wide constants.

Centralises rate-limit strings so they are referenced by name rather than
scattered as magic literals across the route decorators.
"""

# ── Rate limits ───────────────────────────────────────────────────────────────

RATE_LIMIT_INVITE = "10/minute"  # invite + accept-invite endpoints
RATE_LIMIT_AUTH = "5/minute"  # login (brute-force sensitive)
RATE_LIMIT_REFRESH = "20/minute"  # token refresh + logout
