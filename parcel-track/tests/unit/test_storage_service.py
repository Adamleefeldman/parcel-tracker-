"""
Unit tests for ``StorageService.verify_upload``.

Pure boto3 stubbing — no real network. Drives the success and error paths of
the new HEAD-based verification helper without spinning up the whole app.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError

from app.services.storage_service import StorageObjectNotFound, StorageService


def _client_error(code: str, http_status: int) -> ClientError:
    """Build a ClientError shaped like the ones boto3 actually raises."""
    return ClientError(
        error_response={
            "Error": {"Code": code, "Message": "test"},
            "ResponseMetadata": {"HTTPStatusCode": http_status},
        },
        operation_name="HeadObject",
    )


class _FakeS3:
    """Minimal stand-in for the boto3 S3 client returned by ``get_s3()``."""

    def __init__(self, *, head_object_return=None, head_object_raises=None):
        self._return = head_object_return
        self._raises = head_object_raises

    def head_object(self, **_kwargs):
        if self._raises is not None:
            raise self._raises
        return self._return


def test_verify_upload_returns_metadata_on_hit():
    fake = _FakeS3(
        head_object_return={
            "ContentLength": 12_345,
            "ETag": '"abc123def"',
            "ContentType": "application/pdf",
        }
    )
    with patch("app.services.storage_service.get_s3", return_value=fake):
        meta = StorageService.verify_upload("some/key.pdf")

    assert meta == {
        "size": 12_345,
        "etag": "abc123def",  # quotes stripped
        "content_type": "application/pdf",
    }


def test_verify_upload_defaults_content_type_when_missing():
    fake = _FakeS3(
        head_object_return={
            "ContentLength": 1,
            "ETag": '"x"',
            # ContentType deliberately omitted — R2 may not populate it
        }
    )
    with patch("app.services.storage_service.get_s3", return_value=fake):
        meta = StorageService.verify_upload("k")

    assert meta["content_type"] == "application/octet-stream"


@pytest.mark.parametrize(
    "code,status",
    [
        ("404", 404),
        ("NoSuchKey", 404),
        ("NotFound", 404),
        ("", 404),  # bare 404 with no Code — still treated as missing
    ],
)
def test_verify_upload_raises_storage_object_not_found_on_404(code, status):
    fake = _FakeS3(head_object_raises=_client_error(code, status))
    with patch("app.services.storage_service.get_s3", return_value=fake):
        with pytest.raises(StorageObjectNotFound) as exc_info:
            StorageService.verify_upload("missing/key")
    assert "missing/key" in str(exc_info.value)


def test_verify_upload_reraises_other_client_errors():
    """Auth / config failures must surface — we never silently treat them as 'not found'."""
    fake = _FakeS3(head_object_raises=_client_error("AccessDenied", 403))
    with patch("app.services.storage_service.get_s3", return_value=fake):
        with pytest.raises(ClientError):
            StorageService.verify_upload("k")
