from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_env: str = "development"
    app_secret_key: str = "dev-secret-key"
    app_title: str = "Kraft"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # Banco
    database_url: str = "postgresql+asyncpg://kraft:kraft@localhost:5432/kraft"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080  # 7 dias

    # IA
    anthropic_api_key: str = ""

    # Storage
    storage_endpoint_url: str = ""
    storage_access_key: str = ""
    storage_secret_key: str = ""
    storage_bucket: str = "kraft-assets"
    storage_public_url: str = ""

    # Godot
    godot_binary: str = "/usr/local/bin/godot4"
    godot_export_template_dir: str = ""

    # Blender
    blender_binary: str = "/usr/bin/blender"

    # Projetos
    projects_workdir: str = "/tmp/kraft_projects"

    # Marketplace
    platform_commission_percent: int = 15

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


settings = Settings()
