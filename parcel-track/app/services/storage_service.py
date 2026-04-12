import uuid

import boto3
from botocore.exceptions import ClientError

from app.core.config import get_settings

settings = get_settings()

_s3_client = None


def get_s3():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            endpoint_url=settings.STORAGE_ENDPOINT_URL,
            aws_access_key_id=settings.STORAGE_ACCESS_KEY_ID,
            aws_secret_access_key=settings.STORAGE_SECRET_ACCESS_KEY,
            region_name=settings.STORAGE_REGION,
        )
    return _s3_client


class StorageService:
    UPLOAD_EXPIRY = 300  # 5 minutes for upload URL
    DOWNLOAD_EXPIRY = 900  # 15 minutes for download URL

    @staticmethod
    def generate_file_key(entity_type: str, entity_id: uuid.UUID, file_name: str) -> str:
        """Deterministic, collision-resistant key: entity_type/entity_id/random_uuid_filename"""
        safe_name = file_name.replace(" ", "_")
        return f"{entity_type}/{entity_id}/{uuid.uuid4()}_{safe_name}"

    @staticmethod
    def get_upload_url(file_key: str, mime_type: str) -> str:
        """Pre-signed PUT URL. Client uploads directly to storage — never through the API server."""
        s3 = get_s3()
        url = s3.generate_presigned_url(
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
        url = s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.STORAGE_BUCKET,
                "Key": file_key,
            },
            ExpiresIn=StorageService.DOWNLOAD_EXPIRY,
        )
        return url

    @staticmethod
    def delete_file(file_key: str) -> None:
        s3 = get_s3()
        try:
            s3.delete_object(Bucket=settings.STORAGE_BUCKET, Key=file_key)
        except ClientError:
            pass  # log but don't fail — file may already be gone
