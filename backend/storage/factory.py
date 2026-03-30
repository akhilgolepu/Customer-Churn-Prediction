from pathlib import Path

from core.settings import get_settings
from storage.adapters import AzureBlobObjectStorage, LocalObjectStorage, ObjectStorage, S3ObjectStorage


def build_object_storage() -> ObjectStorage | None:
    settings = get_settings()
    provider = settings.object_storage_provider.lower()

    if provider == "none":
        return None
    if provider == "local":
        return LocalObjectStorage(base_dir=Path(settings.object_storage_local_path))
    if provider == "s3":
        if not settings.object_storage_bucket:
            raise RuntimeError("object_storage_bucket is required for S3 storage provider")
        return S3ObjectStorage(bucket=settings.object_storage_bucket, prefix=settings.object_storage_prefix)
    if provider == "azure":
        if not settings.azure_blob_account_url or not settings.object_storage_bucket:
            raise RuntimeError("azure_blob_account_url and object_storage_bucket are required for Azure provider")
        return AzureBlobObjectStorage(
            account_url=settings.azure_blob_account_url,
            container=settings.object_storage_bucket,
            credential=settings.azure_blob_credential,
            prefix=settings.object_storage_prefix,
        )

    raise RuntimeError(f"Unsupported object storage provider: {settings.object_storage_provider}")
