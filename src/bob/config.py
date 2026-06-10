"""
IBM Bob - Configuration Management
Centralized configuration using Pydantic Settings
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment
    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"

    # Neo4j Configuration
    neo4j_uri: str = Field(default="bolt://localhost:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str = Field(default="bobpassword123")

    # Weaviate Configuration
    weaviate_url: str = Field(default="http://localhost:8080")
    weaviate_api_key: str | None = None

    # PostgreSQL Configuration
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432)
    postgres_user: str = Field(default="bob")
    postgres_password: str = Field(default="bobpassword123")
    postgres_db: str = Field(default="bob_registry")

    # Redis Configuration
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_password: str | None = Field(default="bobpassword123")
    redis_db: int = Field(default=0)

    # GitHub Configuration
    github_app_id: str | None = None
    github_app_private_key_path: str | None = None
    github_webhook_secret: str | None = None

    # LLM Configuration
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    llm_provider: Literal["openai", "gemini"] = "openai"
    embedding_model: str = "text-embedding-3-small"

    # Security - JWT
    jwt_secret_key: str = Field(default="your-secret-key-change-in-production")
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7

    # Security - Encryption
    encryption_key: str | None = None

    # Security - API Keys
    api_key_prefix_live: str = "bob_live_"
    api_key_prefix_test: str = "bob_test_"
    api_key_length: int = 32

    # Security - Rate Limiting
    rate_limit_enabled: bool = True
    default_rate_limit_tier: str = "free"

    # Security - CORS
    cors_origins: list[str] = Field(default=["http://localhost:3000"])
    cors_allow_credentials: bool = True

    # Security - Audit Logging
    audit_log_retention_days: int = 90

    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    grpc_port: int = 50052
    api_workers: int = 4
    rate_limit_per_minute: int = 500
    rate_limit_burst: int = 1000

    # Observability
    otel_exporter_otlp_endpoint: str = "http://localhost:4318"
    otel_service_name: str = "bob-api"
    enable_tracing: bool = True
    enable_metrics: bool = True

    # Indexing Configuration
    max_concurrent_indexing_jobs: int = 5
    indexing_timeout_seconds: int = 600
    incremental_update_timeout_seconds: int = 60
    max_repo_size_kloc: int = 500

    # Query Configuration
    query_timeout_seconds: int = 10
    semantic_search_default_k: int = 10
    max_graph_traversal_hops: int = 5
    cache_ttl_seconds: int = 300

    # Performance
    file_cache_ttl_seconds: int = 3600
    convention_cache_ttl_seconds: int = 86400
    query_result_cache_ttl_seconds: int = 300

    @property
    def postgres_dsn(self) -> str:
        """Build PostgreSQL connection string"""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        """Build Redis connection URL"""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def is_development(self) -> bool:
        """Check if running in development mode"""
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode"""
        return self.environment == "production"


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    Uses lru_cache to ensure settings are loaded only once.
    """
    return Settings()


# Convenience export
settings = get_settings()

# Made with Bob
