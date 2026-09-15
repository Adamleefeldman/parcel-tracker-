---
name: presigned-upload-flow
description: Use when designing or reviewing file-upload functionality in a backend API — PDF uploads, image uploads, document attachments, profile pictures, BL / invoice / receipt uploads, video uploads, any user-supplied binary content. Triggers on phrases like "file upload", "S3 upload", "R2 upload", "presigned URL", "direct-to-storage upload", "client uploads to bucket", "multipart upload", "the API is serving as a proxy for file bytes", or when you see an endpoint accepting `UploadFile` and forwarding it byte-by-byte to object storage. Also use when the user mentions storage providers like S3, R2, GCS, MinIO, Backblaze B2, Wasabi, or any S3-compatible store.
---

# Presigned-URL upload — the server never touches the bytes

The wrong way: client POSTs the file to your API, your API streams it to object storage, your API responds. You pay the bandwidth twice, your worker process is blocked the whole upload duration, and a 200MB upload makes your `--workers 4` Gunicorn cluster effectively `--workers 3` for ten seconds.

The right way: the API hands the client a short-lived presigned PUT URL, the client uploads directly to storage, then POSTs a tiny confirmation to the API. The API HEADs the object to verify it actually exists with the size and MIME type it expected, then records the metadata row. Bytes never enter the application server.

This pattern works the same against S3, R2, GCS, MinIO, Backblaze B2 — they're all S3-compatible enough for `boto3`. The "R2 is S3-compatible" footnote applies here: if your code says `boto3.client("s3", endpoint_url=...)`, that's correct against R2, not a leftover.

## The three-step contract

1. **`POST /uploads/presign`** → client sends `{file_name, mime_type, entity_type, entity_id}`. Server validates mime against an allowlist, generates a deterministic-but-collision-resistant key, returns `{file_key, upload_url, expires_in}`.
2. **`PUT <upload_url>`** → client uploads bytes directly to storage. Storage accepts because the URL is signed for exactly this `(bucket, key, content-type)` tuple. Server is not involved at all.
3. **`POST /uploads/confirm`** → client sends `{file_key}`. Server HEADs the object, verifies it exists, verifies the stored `ContentType` matches what was declared at presign time, records `(entity_id, file_key, size, etag)` in the DB. The client is never trusted to claim the size or content-type — only the storage HEAD response is authoritative.

A 4th step (`GET /uploads/<file_key>/download`) issues a short-lived presigned GET URL for retrieval — same idea in reverse.

## Canonical template

```python
# app/services/storage_service.py

import uuid
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from app.core.config import get_settings


class StorageObjectNotFound(Exception):
    """HEAD against the bucket couldn't find the expected key."""


class StorageMimeMismatch(Exception):
    """Storage's stored ContentType differs from the type declared at presign."""


_s3 = None
def get_s3():
    global _s3
    if _s3 is None:
        s = get_settings()
        _s3 = boto3.client(
            "s3",
            endpoint_url=s.STORAGE_ENDPOINT_URL,
            aws_access_key_id=s.STORAGE_ACCESS_KEY_ID,
            aws_secret_access_key=s.STORAGE_SECRET_ACCESS_KEY,
            region_name=s.STORAGE_REGION,
            config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
        )
    return _s3


class StorageService:
    UPLOAD_EXPIRY = 300       # 5 min for upload URL
    DOWNLOAD_EXPIRY = 900     # 15 min for download URL
    MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024

    ALLOWED_MIME_TYPES: frozenset[str] = frozenset({
        "application/pdf",
        "image/jpeg", "image/png", "image/webp",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # xlsx
        "application/vnd.ms-excel",  # xls
    })

    @staticmethod
    def generate_file_key(entity_type: str, entity_id: uuid.UUID, file_name: str) -> str:
        """Deterministic + collision-resistant: <entity_type>/<entity_id>/<uuid>_<safe_name>"""
        safe_name = file_name.replace(" ", "_")
        return f"{entity_type}/{entity_id}/{uuid.uuid4()}_{safe_name}"

    @staticmethod
    def get_upload_url(file_key: str, mime_type: str) -> str:
        if mime_type not in StorageService.ALLOWED_MIME_TYPES:
            raise ValueError(
                f"Unsupported MIME type '{mime_type}'. "
                f"Allowed: {', '.join(sorted(StorageService.ALLOWED_MIME_TYPES))}"
            )
        s = get_settings()
        return get_s3().generate_presigned_url(
            "put_object",
            Params={"Bucket": s.STORAGE_BUCKET, "Key": file_key, "ContentType": mime_type},
            ExpiresIn=StorageService.UPLOAD_EXPIRY,
        )

    @staticmethod
    def get_download_url(file_key: str) -> str:
        s = get_settings()
        return get_s3().generate_presigned_url(
            "get_object",
            Params={"Bucket": s.STORAGE_BUCKET, "Key": file_key},
            ExpiresIn=StorageService.DOWNLOAD_EXPIRY,
        )

    @staticmethod
    def verify_upload(file_key: str, expected_content_type: str | None = None) -> dict:
        """HEAD the object. Returns {size, etag, content_type} from storage.

        Raises StorageObjectNotFound if the key isn't there.
        Raises StorageMimeMismatch if the stored ContentType differs from what
        the client declared at presign time — guards against a client that
        presigned for image/png and PUT a different MIME.
        """
        s = get_settings()
        try:
            resp = get_s3().head_object(Bucket=s.STORAGE_BUCKET, Key=file_key)
        except ClientError as exc:
            err = exc.response.get("Error", {})
            code = str(err.get("Code", ""))
            status = str(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", ""))
            if code in {"404", "NoSuchKey", "NotFound"} or status == "404":
                raise StorageObjectNotFound(f"object not found: {file_key}") from exc
            raise

        actual = resp.get("ContentType") or "application/octet-stream"
        if expected_content_type is not None and actual != expected_content_type:
            raise StorageMimeMismatch(
                f"uploaded ContentType '{actual}' != declared '{expected_content_type}'"
            )
        return {
            "size": int(resp["ContentLength"]),
            "etag": resp["ETag"].strip('"'),
            "content_type": actual,
        }
```

### Route layer

```python
@router.post("/uploads/presign", response_model=PresignOut)
async def presign(body: PresignIn, actor: User = Depends(get_current_user)):
    file_key = StorageService.generate_file_key(body.entity_type, body.entity_id, body.file_name)
    try:
        url = StorageService.get_upload_url(file_key, body.mime_type)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return PresignOut(file_key=file_key, upload_url=url, expires_in=StorageService.UPLOAD_EXPIRY)


@router.post("/uploads/confirm", response_model=DocumentOut)
async def confirm(body: ConfirmIn, db: AsyncSession = Depends(get_db),
                  actor: User = Depends(get_current_user)):
    try:
        meta = StorageService.verify_upload(body.file_key, expected_content_type=body.mime_type)
    except StorageObjectNotFound:
        raise HTTPException(400, "Upload not found in storage. Did the PUT succeed?")
    except StorageMimeMismatch as exc:
        raise HTTPException(400, str(exc))

    if meta["size"] > StorageService.MAX_FILE_SIZE_BYTES:
        # Belt-and-braces — storage may not enforce content-length. Delete the
        # over-large object so it doesn't sit in the bucket.
        StorageService.delete_file(body.file_key)
        raise HTTPException(400, "File too large")

    doc = Document(
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        file_key=body.file_key,
        file_name=body.file_name,
        size=meta["size"],
        etag=meta["etag"],
        content_type=meta["content_type"],
        uploaded_by=actor.id,
    )
    db.add(doc)
    await db.commit()
    return doc
```

## Design rules — and why they matter

### Rule 1: The server never proxies bytes

If your upload endpoint accepts `file: UploadFile = File(...)` and streams to storage, you've built the wrong pattern. Bandwidth doubles, your workers block, multipart edge cases bite you, and the latency budget for a 50MB upload is now in your application logs. Tear it out and replace with presigned PUT.

### Rule 2: The client is untrusted — storage is the source of truth

Don't accept `size` or `content_type` from the client's confirm payload. HEAD the object and use the values storage returns. The client can lie about everything in the request body; it cannot lie about what's actually in the bucket.

### Rule 3: Verify the MIME at confirm, not just at presign

At presign time the client *declares* `image/png`. The presigned URL is signed for `ContentType: image/png`. But a client that PUTs with a different `Content-Type` header will succeed — the signature only locks the *declared* type, not the actual bytes. Two defenses, both at confirm:

- HEAD the object and compare its stored `ContentType` to what was declared. Reject on mismatch.
- (Optional, stricter) Run a magic-byte / libmagic check on the first N bytes of the object. PDF starts with `%PDF`, PNG with `\x89PNG`, etc. Don't trust the MIME header — trust the bytes.

The MIME-mismatch check above is the cheap version; the magic-byte check is the expensive version. Pick based on threat model.

### Rule 4: Allowlist MIME types, don't blocklist extensions

`.exe` is the obvious one to block; `.svg` is the one most blocklists forget (XSS via embedded JS). Allowlist by MIME at presign time. The list is small and explicit: `application/pdf`, `image/jpeg`, `image/png`, `image/webp`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`. Add to it deliberately.

### Rule 5: Deterministic, collision-resistant keys

`<entity_type>/<entity_id>/<uuid>_<safe_filename>` — the entity prefix makes "find all documents for booking X" a `prefix=` listing, and the UUID makes collisions astronomically unlikely. Don't use the filename alone — duplicate uploads will overwrite each other. Don't use a sequential ID — it leaks information about upload volume.

### Rule 6: Short upload TTL, short download TTL

5 minutes for upload is generous — the URL is one-shot, and once the upload completes the URL is dead anyway (well, replayable until expiry, which is why short is right). 15 minutes for download is enough for a user to click a link and start the download in a tab. Don't issue 24-hour URLs and let them leak via Slack screenshots.

### Rule 7: Size check at confirm, with cleanup on reject

The storage provider's content-length enforcement is best-effort — some accept arbitrary sizes for presigned PUTs. After HEAD, check size against your max. If over, DELETE the object before raising the 400 — otherwise the over-large file sits in your bucket forever.

### Rule 8: Use a non-public bucket; serve downloads via presigned GETs

A public bucket bypasses your authz entirely — anyone with the key URL has the file. Keep the bucket private; every download goes through `GET /documents/<id>/url` → server checks authz → server issues a presigned GET → client redirects there. Bytes still don't transit your server.

### Rule 9: One global S3 client, lazy-initialized

`boto3.client("s3", ...)` is moderately heavy. Initialize it once at first call and reuse. Don't create a client per request.

### Rule 10: Catch `ClientError` carefully

Botocore's error shape varies by provider. R2 returns `404` HTTP status; AWS returns `NoSuchKey`; some return `NotFound`. Match against the union (`{"404", "NoSuchKey", "NotFound"}`) and raise a typed `StorageObjectNotFound` so callers don't have to deal with the boto3 idiosyncrasies.

## Common attack patterns (and how this pattern blunts them)

| Attack | Defense |
|---|---|
| Upload an `.exe` disguised as `image/png` | MIME-mismatch check + magic-byte check at confirm |
| Upload a 50GB file to fill the bucket | Size check at confirm, delete-on-over |
| Replay an old presigned URL | Short TTL on PUT; URL is one-shot per spec, won't replay through the server |
| Read another user's file | Private bucket + presigned GET via authz'd endpoint |
| Slurp the file_key from logs and download | Authz check on download endpoint; presigned URLs short-lived |
| SSRF via uploaded SVG | Allowlist excludes SVG, or you sanitize SVG separately before serving |

## Reviewing a PR that touches uploads

- [ ] Does any endpoint accept `UploadFile = File(...)` and stream bytes to storage? Replace with presign + confirm.
- [ ] Is the confirm endpoint reading `size` or `content_type` from the request body? Replace with HEAD-from-storage values.
- [ ] Is the MIME allowlist checked at presign? Is the mismatch checked at confirm?
- [ ] Are file keys deterministic and unique (UUID component)?
- [ ] Is the bucket public? It shouldn't be.
- [ ] Are presigned URL TTLs reasonable (single-digit minutes for upload, low-double-digit for download)?
- [ ] If the size check rejects, is the over-large object being deleted?
- [ ] Are storage errors caught and re-raised as typed exceptions, or leaking `botocore.exceptions.ClientError`?

## Common failure modes

| Symptom | Likely cause |
|---|---|
| Workers stuck during big uploads | Server is proxying bytes; switch to presigned PUT |
| Bucket full of mystery files no DB row references | No confirm step, or confirm doesn't HEAD-verify, or orphan-sweeper task doesn't exist |
| Client uploads `image/png` but the stored object is something else | No MIME-mismatch check at confirm |
| Files served from a public bucket can be enumerated | Make the bucket private; serve via presigned GETs |
| 404 on download for new uploads | Confirm step recorded the row before the PUT completed; HEAD-verify at confirm prevents this |
| `botocore.exceptions.ClientError` leaks into HTTP 500s | Catch in the service, raise typed `StorageObjectNotFound` / `StorageMimeMismatch` |

## Orphan sweep (optional)

If a client presigns a PUT and never uploads (or uploads and never confirms), you get an orphan — an object in storage with no DB row. Two ways to handle:

- **Lifecycle rule on the bucket**: delete objects under a `pending/` prefix after 24 hours.
- **Periodic Celery task**: list objects older than 24 hours, check which lack a DB row, delete.

The first is much cheaper and harder to misconfigure. Prefer it.

## Companion skills

- **`production-config-validation`** — the storage credentials and HTTPS-only endpoint URL are validated there.
- **`integration-resilience`** — if you do call out to storage in a hot path (HEAD on confirm), wrap it with the integration helper. boto3 won't do that for you.
