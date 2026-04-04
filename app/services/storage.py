"""
Storage — integração com Cloudflare R2 / AWS S3.
"""

import asyncio
from functools import partial

import boto3
from botocore.exceptions import ClientError

from app.config import settings


def _get_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.storage_endpoint_url or None,
        aws_access_key_id=settings.storage_access_key or None,
        aws_secret_access_key=settings.storage_secret_key or None,
    )


async def upload_asset(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """Faz upload de um asset e retorna a URL pública."""
    client = _get_client()

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        partial(
            client.put_object,
            Bucket=settings.storage_bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        ),
    )

    if settings.storage_public_url:
        return f"{settings.storage_public_url.rstrip('/')}/{key}"
    return f"https://{settings.storage_bucket}.s3.amazonaws.com/{key}"


async def get_asset_url(key: str, expires_in: int = 3600) -> str:
    """Gera URL pre-signed para acesso temporário."""
    client = _get_client()

    loop = asyncio.get_event_loop()
    url = await loop.run_in_executor(
        None,
        partial(
            client.generate_presigned_url,
            "get_object",
            Params={"Bucket": settings.storage_bucket, "Key": key},
            ExpiresIn=expires_in,
        ),
    )
    return url


async def delete_asset(key: str) -> None:
    client = _get_client()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        partial(client.delete_object, Bucket=settings.storage_bucket, Key=key),
    )
