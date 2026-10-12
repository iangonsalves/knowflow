"""Private object-storage port and S3-compatible implementation."""

from functools import lru_cache
from typing import BinaryIO, Protocol

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings, get_settings


class ObjectStorageError(RuntimeError):
    """The configured private storage service could not complete an operation."""


class StoredObjectNotFound(ObjectStorageError):
    """A requested private object does not exist in storage."""


class ObjectStorage(Protocol):
    """Small storage contract used by the document application service."""

    def put_file(
        self, key: str, stream: BinaryIO, size: int, sha256: str, content_type: str
    ) -> None: ...

    def get_file(self, key: str) -> tuple[BinaryIO, int]: ...

    def delete_file(self, key: str) -> None: ...


class S3ObjectStorage:
    """S3 API adapter configured for MinIO locally and private S3-compatible storage."""

    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.object_storage_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.object_storage_endpoint_url,
            aws_access_key_id=settings.object_storage_access_key,
            aws_secret_access_key=settings.object_storage_secret_key,
            region_name=settings.object_storage_region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                connect_timeout=5,
                read_timeout=60,
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )

    def _ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code not in {"404", "NoSuchBucket", "NotFound"} and status != 404:
                raise ObjectStorageError("Private document storage is unavailable") from error
            try:
                self.client.create_bucket(Bucket=self.bucket)
            except ClientError as create_error:
                # Another API instance may have created the bucket concurrently.
                try:
                    self.client.head_bucket(Bucket=self.bucket)
                except (BotoCoreError, ClientError):
                    raise ObjectStorageError("Private document storage is unavailable") from (
                        create_error
                    )
        except BotoCoreError as error:
            raise ObjectStorageError("Private document storage is unavailable") from error

    def put_file(
        self, key: str, stream: BinaryIO, size: int, sha256: str, content_type: str
    ) -> None:
        self._ensure_bucket()
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=stream,
                ContentLength=size,
                ContentType=content_type,
                Metadata={"sha256": sha256},
            )
        except (BotoCoreError, ClientError) as error:
            raise ObjectStorageError("Private document storage is unavailable") from error

    def get_file(self, key: str) -> tuple[BinaryIO, int]:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"], int(response["ContentLength"])
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code in {"NoSuchKey", "404", "NotFound"} or status == 404:
                raise StoredObjectNotFound("Stored document is missing") from error
            raise ObjectStorageError("Private document storage is unavailable") from error
        except BotoCoreError as error:
            raise ObjectStorageError("Private document storage is unavailable") from error

    def delete_file(self, key: str) -> None:
        try:
            # S3 DeleteObject is idempotent, which also makes repeated DELETE calls safe.
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except (BotoCoreError, ClientError) as error:
            raise ObjectStorageError("Private document storage is unavailable") from error


@lru_cache(maxsize=1)
def get_object_storage() -> ObjectStorage:
    return S3ObjectStorage(get_settings())
