from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import Settings


class Storage:
    def __init__(self, settings: Settings):
        self._bucket = settings.s3_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name="us-east-1",
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self._bucket)

    def upload_file(self, path: Path, key: str, content_type: str) -> None:
        self._client.upload_file(str(path), self._bucket, key, ExtraArgs={"ContentType": content_type})

    def upload_bytes(self, data: bytes, key: str, content_type: str) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)

    def download_file(self, key: str, path: Path) -> None:
        self._client.download_file(self._bucket, key, str(path))
