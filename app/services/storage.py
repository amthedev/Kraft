"""
Storage — integração com Cloudflare R2 / AWS S3.
Fallback: salva em disco local quando S3 não está configurado.
"""

import asyncio
from functools import partial
from pathlib import Path

from app.config import settings

_LOCAL_STORAGE_DIR = Path(settings.projects_workdir) / "_uploads"


def _storage_configured() -> bool:
    return bool(settings.storage_access_key and settings.storage_secret_key)


def _get_client():
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=settings.storage_endpoint_url or None,
        aws_access_key_id=settings.storage_access_key,
        aws_secret_access_key=settings.storage_secret_key,
    )


async def upload_asset(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """Faz upload de um asset e retorna a URL pública.
    Se S3/R2 não estiver configurado, salva localmente e retorna caminho relativo.
    """
    if not _storage_configured():
        # Fallback: salvar em disco local
        local_path = _LOCAL_STORAGE_DIR / key
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)
        return f"/uploads/{key}"

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
    """Gera URL pre-signed para acesso temporário (ou URL local)."""
    if not _storage_configured():
        return f"/uploads/{key}"

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
    if not _storage_configured():
        local_path = _LOCAL_STORAGE_DIR / key
        local_path.unlink(missing_ok=True)
        return

    client = _get_client()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        partial(client.delete_object, Bucket=settings.storage_bucket, Key=key),
    )
