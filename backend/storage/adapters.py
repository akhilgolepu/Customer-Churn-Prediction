from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Protocol
import uuid


class ObjectStorage(Protocol):
    def upload_bytes(self, key: str, payload: bytes, content_type: str = "application/octet-stream") -> str: ...

    def download_bytes(self, uri: str) -> bytes: ...

    def download_to_path(self, uri: str, suffix: str = "") -> Path: ...


class LocalObjectStorage:
    def __init__(self, base_dir: Path, uri_prefix: str = "file://") -> None:
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._uri_prefix = uri_prefix

    def upload_bytes(self, key: str, payload: bytes, content_type: str = "application/octet-stream") -> str:
        del content_type
        target = (self._base_dir / key).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return f"{self._uri_prefix}{target.as_posix()}"

    def download_bytes(self, uri: str) -> bytes:
        path = self._to_path(uri)
        return path.read_bytes()

    def download_to_path(self, uri: str, suffix: str = "") -> Path:
        payload = self.download_bytes(uri)
        fd, path = tempfile.mkstemp(suffix=suffix)
        Path(path).write_bytes(payload)
        Path(path).chmod(0o600)
        return Path(path)

    def _to_path(self, uri: str) -> Path:
        if uri.startswith("file://"):
            return Path(uri.replace("file://", "", 1))
        return Path(uri)


class S3ObjectStorage:
    def __init__(self, bucket: str, prefix: str = "") -> None:
        try:
            import boto3
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("boto3 is required for S3ObjectStorage") from exc
        self._client = boto3.client("s3")
        self._bucket = bucket
        self._prefix = prefix.strip("/")

    def _object_key(self, key: str) -> str:
        if self._prefix:
            return f"{self._prefix}/{key.lstrip('/')}"
        return key.lstrip("/")

    def upload_bytes(self, key: str, payload: bytes, content_type: str = "application/octet-stream") -> str:
        object_key = self._object_key(key)
        self._client.put_object(Bucket=self._bucket, Key=object_key, Body=payload, ContentType=content_type)
        return f"s3://{self._bucket}/{object_key}"

    def download_bytes(self, uri: str) -> bytes:
        bucket, key = parse_s3_uri(uri)
        response = self._client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    def download_to_path(self, uri: str, suffix: str = "") -> Path:
        payload = self.download_bytes(uri)
        fd, path = tempfile.mkstemp(suffix=suffix)
        Path(path).write_bytes(payload)
        Path(path).chmod(0o600)
        return Path(path)


class AzureBlobObjectStorage:
    def __init__(self, account_url: str, container: str, credential: str | None = None, prefix: str = "") -> None:
        try:
            from azure.storage.blob import BlobServiceClient
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("azure-storage-blob is required for AzureBlobObjectStorage") from exc

        self._container = container
        self._prefix = prefix.strip("/")
        service = BlobServiceClient(account_url=account_url, credential=credential)
        self._container_client = service.get_container_client(container)

    def _blob_name(self, key: str) -> str:
        if self._prefix:
            return f"{self._prefix}/{key.lstrip('/')}"
        return key.lstrip("/")

    def upload_bytes(self, key: str, payload: bytes, content_type: str = "application/octet-stream") -> str:
        blob_name = self._blob_name(key)
        self._container_client.upload_blob(name=blob_name, data=payload, overwrite=True, content_type=content_type)
        return f"az://{self._container}/{blob_name}"

    def download_bytes(self, uri: str) -> bytes:
        container, blob_name = parse_az_uri(uri)
        if container != self._container:
            raise RuntimeError("Azure container mismatch for configured storage adapter")
        downloader = self._container_client.download_blob(blob_name)
        return downloader.readall()

    def download_to_path(self, uri: str, suffix: str = "") -> Path:
        payload = self.download_bytes(uri)
        fd, path = tempfile.mkstemp(suffix=suffix)
        Path(path).write_bytes(payload)
        Path(path).chmod(0o600)
        return Path(path)


def parse_s3_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise ValueError(f"Invalid S3 URI: {uri}")
    remainder = uri.replace("s3://", "", 1)
    bucket, _, key = remainder.partition("/")
    if not bucket or not key:
        raise ValueError(f"Invalid S3 URI: {uri}")
    return bucket, key


def parse_az_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("az://"):
        raise ValueError(f"Invalid Azure URI: {uri}")
    remainder = uri.replace("az://", "", 1)
    container, _, blob_name = remainder.partition("/")
    if not container or not blob_name:
        raise ValueError(f"Invalid Azure URI: {uri}")
    return container, blob_name


def random_object_key(prefix: str, extension: str) -> str:
    normalized = prefix.strip("/")
    name = f"{uuid.uuid4()}{extension}"
    if normalized:
        return f"{normalized}/{name}"
    return name
