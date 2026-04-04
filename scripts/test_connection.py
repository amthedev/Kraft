#!/usr/bin/env python3
"""
Testa a conexão com o banco de dados PostgreSQL usando as configurações do .env.

Uso:
    python scripts/test_connection.py

Para SquareCloud com certificado de cliente:
    DB_SSL_CERT=certs/client.crt DB_SSL_KEY=certs/client.key DB_SSL_CA=certs/ca.crt \
    python scripts/test_connection.py
"""
import os
import sys

# Permite importar app.config sem instalar o pacote
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_sync():
    """Testa com psycopg2 (mesma configuração usada nas migrations)."""
    try:
        import psycopg2
    except ImportError:
        print("psycopg2 não instalado — execute: pip install psycopg2-binary")
        return False

    raw_url = os.environ.get("DATABASE_URL", "")
    if not raw_url:
        try:
            from app.config import settings
            raw_url = settings.database_url
        except Exception as e:
            print(f"Erro ao carregar settings: {e}")
            return False

    sync_url = (
        raw_url
        .replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgresql+asyncpg:", "postgresql:")
        .replace("?ssl=require", "?sslmode=require")
        .replace("&ssl=require", "&sslmode=require")
    )

    connect_args = {}
    cert = os.environ.get("DB_SSL_CERT", "")
    key = os.environ.get("DB_SSL_KEY", "")
    ca = os.environ.get("DB_SSL_CA", "")
    if cert and key:
        connect_args = {
            "sslcert": cert,
            "sslkey": key,
            "sslmode": "verify-full" if ca else "require",
        }
        if ca:
            connect_args["sslrootcert"] = ca
        print(f"Usando certificado cliente: {cert}")

    print(f"Conectando (psycopg2): {sync_url[:60]}...")
    try:
        conn = psycopg2.connect(sync_url, **connect_args)
        cur = conn.cursor()
        cur.execute("SELECT version();")
        version = cur.fetchone()[0]
        conn.close()
        print(f"OK — {version}")
        return True
    except Exception as e:
        print(f"ERRO: {e}")
        return False


def test_async():
    """Testa com asyncpg (mesma configuração usada pela app)."""
    try:
        import asyncio
        import asyncpg
    except ImportError:
        print("asyncpg não instalado")
        return False

    try:
        from app.config import settings
    except Exception as e:
        print(f"Erro ao carregar settings: {e}")
        return False

    async def _check():
        ssl_ctx = settings.ssl_context
        url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        print(f"Conectando (asyncpg): {url[:60]}...")
        try:
            conn = await asyncpg.connect(url, ssl=ssl_ctx)
            version = await conn.fetchval("SELECT version()")
            await conn.close()
            print(f"OK — {version}")
            return True
        except Exception as e:
            print(f"ERRO: {e}")
            return False

    return asyncio.run(_check())


if __name__ == "__main__":
    print("=== Teste de Conexão PostgreSQL ===\n")
    ok_sync = test_sync()
    print()
    ok_async = test_async()
    print()
    if ok_sync and ok_async:
        print("Tudo OK — banco acessível com ambos os drivers.")
    elif ok_sync:
        print("psycopg2 OK mas asyncpg falhou — verifique DATABASE_URL e configuração SSL.")
    elif ok_async:
        print("asyncpg OK mas psycopg2 falhou — migrations podem precisar de ajuste.")
    else:
        print(
            "Ambos falharam.\n\n"
            "Para SquareCloud, baixe os certificados no painel e execute:\n"
            "  DB_SSL_CERT=certs/client.crt \\\n"
            "  DB_SSL_KEY=certs/client.key \\\n"
            "  DB_SSL_CA=certs/ca.crt \\\n"
            "  python scripts/test_connection.py\n\n"
            "Para desenvolvimento local, suba o Docker:\n"
            "  docker compose up db redis -d\n"
            "  export DATABASE_URL=postgresql+asyncpg://kraft:kraft@localhost:5432/kraft\n"
            "  alembic upgrade head"
        )
