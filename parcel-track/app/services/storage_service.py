import logging
import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import get_settings

logger = logging.getLogger("parceltrack.storage")

settings = get_settings()

_s3_client = None


class StorageObjectNotFound(Exception):
    """Raised when a HEAD against the configured bucket can't find the expected key."""


class StorageMimeMismatch(Exception):
    """Raised when R2's stored ContentType differs from the type declared at presign time."""


def get_s3():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            endpoint_url=settings.STORAGE_ENDPOINT_URL,
            aws_access_key_id=settings.STORAGE_ACCESS_KEY_ID,
            aws_secret_access_key=settings.STORAGE_SECRET_ACCESS_KEY,
            region_name=settings.STORAGE_REGION,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "virtual"},
            ),
        )
    return _s3_client


class StorageService:
    UPLOAD_EXPIRY = 300  # 5 minutes for upload URL
    DOWNLOAD_EXPIRY = 900  # 15 minutes for download URL
    MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB

    ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
        {
            "application/pdf",
            "image/jpeg",
            "image/png",
            "image/webp",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # xlsx
            "application/vnd.ms-excel",  # xls
        }
    )

    @staticmethod
    def generate_file_key(entity_type: str, entity_id: uuid.UUID, file_name: str) -> str:
        """Deterministic, collision-resistant key: entity_type/entity_id/random_uuid_filename"""
        safe_name = file_name.replace(" ", "_")
        return f"{entity_type}/{entity_id}/{uuid.uuid4()}_{safe_name}"

    @staticmethod
    def get_upload_url(file_key: str, mime_type: str) -> str:
        """Pre-signed PUT URL. Client uploads directly to storage — never through the API server."""
        if mime_type not in StorageService.ALLOWED_MIME_TYPES:
            raise ValueError(
                f"Unsupported MIME type '{mime_type}'. "
                f"Allowed: {', '.join(sorted(StorageService.ALLOWED_MIME_TYPES))}"
            )
        s3 = get_s3()
        # boto3 is untyped — annotate the local so callers see a real str.
        url: str = s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.STORAGE_BUCKET,
                "Key": file_key,
                "ContentType": mime_type,
            },
            ExpiresIn=StorageService.UPLOAD_EXPIRY,
        )
        return url

    @staticmethod
    def get_download_url(file_key: str) -> str:
        """Pre-signed GET URL. Time-limited — regenerated on each request."""
        s3 = get_s3()
        url: str = s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.STORAGE_BUCKET,
                "Key": file_key,
            },
            ExpiresIn=StorageService.DOWNLOAD_EXPIRY,
        )
        return url

    @staticmethod
    def verify_upload(file_key: str, expected_content_type: str | None = None) -> dict:
        """
        HEAD the object in R2 to confirm a presigned PUT actually completed.

        Returns ``{"size": int, "etag": str, "content_type": str}`` describing
        the real object as stored. Callers must use these values rather than
        whatever the client claimed in the confirm payload — the client is
        untrusted, only R2 is the source of truth.

        If ``expected_content_type`` is provided, raises ``StorageMimeMismatch``
        when R2's stored ContentType differs — guards against a client that PUTs
        a different MIME than the one it declared at presign time.

        Raises ``StorageObjectNotFound`` when the key is absent (HTTP 404 /
        ``NoSuchKey`` / ``NotFound``). Other ``ClientError``s are re-raised so
        operational failures (auth, network) surface loudly.
        """
        s3 = get_s3()
        try:
            resp = s3.head_object(Bucket=settings.STORAGE_BUCKET, Key=file_key)
        except ClientError as exc:
            error = exc.response.get("Error", {})
            code = str(error.get("Code", ""))
            status = str(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", ""))
            if code in {"404", "NoSuchKey", "NotFound"} or status == "404":
                raise StorageObjectNotFound(f"object not found in storage: {file_key}") from exc
            raise
        actual_content_type = resp.get("ContentType") or "application/octet-stream"
        if expected_content_type is not None and actual_content_type != expected_content_type:
            raise StorageMimeMismatch(
                f"uploaded ContentType '{actual_content_type}' does not match "
                f"declared type '{expected_content_type}'"
            )
        return {
            "size": int(resp["ContentLength"]),
            "etag": resp["ETag"].strip('"'),
            "content_type": actual_content_type,
        }

    @staticmethod
    def delete_file(file_key: str) -> None:
        s3 = get_s3()
        try:
            s3.delete_object(Bucket=settings.STORAGE_BUCKET, Key=file_key)
        except ClientError:
            logger.error("Failed to delete S3 object %s", file_key, exc_info=True)
