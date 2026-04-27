#!/usr/bin/env python3
"""
Smoke test for Cloudflare R2 round-trip.

Runs the full presigned-URL flow against the real bucket configured in
``.env``: generate file_key → presigned PUT → upload bytes → HEAD via
``StorageService.verify_upload`` → presigned GET → download bytes → assert
content matches → delete the smoke object.

Usage:

    uv run python scripts/smoke_r2.py

Exits 0 on full round-trip success, 1 on any failure (the failing step is
printed to stderr). This is intentionally thin so it can be wired into a
deploy gate later without dragging in pytest.
"""

from __future__ import annotations

import asyncio
import sys
import uuid

import httpx

from app.services.storage_service import (
    StorageObjectNotFound,
    StorageService,
)

# 32-byte payload; small enough to be cheap, unique per run so we never
# false-positive on a stale object lingering in the bucket.
_PAYLOAD = b"parceltrack smoke " + uuid.uuid4().bytes
_MIME = "application/pdf"


async def _round_trip() -> None:
    file_key = StorageService.generate_file_key("smoke", uuid.uuid4(), "test.pdf")
    upload_url = StorageService.get_upload_url(file_key, _MIME)

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. PUT bytes directly to R2 via the presigned URL.
        put = await client.put(upload_url, content=_PAYLOAD, headers={"Content-Type": _MIME})
        put.raise_for_status()

        # 2. Confirm the object is really there and the size matches.
        meta = StorageService.verify_upload(file_key)
        if meta["size"] != len(_PAYLOAD):
            raise AssertionError(
                f"size mismatch: bucket reports {meta['size']}, payload was {len(_PAYLOAD)}"
            )

        # 3. GET it back via the presigned download URL.
        download_url = StorageService.get_download_url(file_key)
        got = await client.get(download_url)
        got.raise_for_status()
        if got.content != _PAYLOAD:
            raise AssertionError("content round-trip mismatch")

    # 4. Tidy up. delete_file logs but never raises — best-effort cleanup.
    StorageService.delete_file(file_key)
    print(f"OK — round-tripped {len(_PAYLOAD)} bytes key={file_key} etag={meta['etag']}")


def main() -> int:
    try:
        asyncio.run(_round_trip())
    except (StorageObjectNotFound, AssertionError, httpx.HTTPError) as exc:
        print(f"FAIL — {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
