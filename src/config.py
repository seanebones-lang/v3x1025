"""
Configuration management for the Dealership RAG system.
Loads environment variables and provides typed configuration objects.
"""

import os
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Main application settings loaded from environment variables with validation."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        validate_default=True
    )
    
    # API Keys - LLM & Embeddings
    anthropic_api_key: str = Field(default="", description="Anthropic API key for Claude")
    voyage_api_key: str = Field(default="", description="Voyage AI API key for embeddings")
    cohere_api_key: str = Field(default="", description="Cohere API key for re-ranking")
    
    # Vector Database
    pinecone_api_key: str = Field(default="", description="Pinecone API key")
    pinecone_environment: str = Field(default="us-east-1-aws", description="Pinecone environment")
    pinecone_index_name: str = Field(default="dealership-rag", description="Pinecone index name")
    
    # DMS Integration
    cdk_api_key: str = Field(default="", description="CDK Global API key")
    cdk_api_url: str = Field(default="https://api.cdkglobal.com/v1", description="CDK API URL")
    reynolds_api_key: str = Field(default="", description="Reynolds & Reynolds API key")
    reynolds_api_url: str = Field(default="https://api.reyrey.com/v1", description="Reynolds API URL")
    dms_adapter: Literal["cdk", "reynolds", "mock"] = Field(default="mock", description="DMS adapter to use")
    
    # Redis Cache
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_password: str = Field(default="", description="Redis password")
    redis_db: int = Field(default=0, description="Redis database number")
    
    # Celery Task Queue
    celery_broker_url: str = Field(default="redis://localhost:6379/1", description="Celery broker URL")
    celery_result_backend: str = Field(default="redis://localhost:6379/2", description="Celery result backend")
    
    # Application Settings
    api_secret_key: str = Field(default="dev-secret-change-in-production", description="Secret key for API authentication")
    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Application environment"
    )
    log_level: str = Field(default="INFO", description="Logging level")
    
    # Observability
    langsmith_api_key: str = Field(default="", description="LangSmith API key")
    langsmith_project: str = Field(default="dealership-rag", description="LangSmith project name")
    langsmith_tracing: bool = Field(default=True, description="Enable LangSmith tracing")
    sentry_dsn: str = Field(default="", description="Sentry DSN for error tracking")
    
    # Performance Tuning
    chunk_size: int = Field(default=1000, description="Text chunk size for splitting")
    chunk_overlap: int = Field(default=200, description="Text chunk overlap")
    top_k_retrieval: int = Field(default=20, description="Top K documents to retrieve")
    top_k_rerank: int = Field(default=5, description="Top K documents after re-ranking")
    max_tokens_generation: int = Field(default=1000, description="Max tokens for LLM generation")
    query_timeout_seconds: int = Field(default=30, description="Query timeout in seconds")
    
    # Rate Limiting
    rate_limit_per_minute: int = Field(default=100, description="Rate limit per minute")
    rate_limit_burst: int = Field(default=20, description="Rate limit burst size")
    
    # Database
    database_url: str = Field(default="sqlite:///./dealership_rag.db", description="Database URL")
    
    @property
    def redis_url(self) -> str:
        """Construct Redis URL from components."""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == "development"


# Global settings instance
settings = Settings()


# Configure LangSmith if enabled
if settings.langsmith_tracing and settings.langsmith_api_key:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project


async def validate_api_keys_at_startup():
    """
    Validate API keys at startup to fail-fast if misconfigured.
    Quick ping to each service to ensure connectivity.
    """
    import asyncio
    import logging
    
    logger = logging.getLogger(__name__)
    validation_errors = []
    
    # Validate Voyage API
    if settings.voyage_api_key:
        try:
            import voyageai
            client = voyageai.Client(api_key=settings.voyage_api_key)
            # Quick test embedding
            await asyncio.to_thread(client.embed, ["test"], model="voyage-3.5-large")
            logger.info(" Voyage API key validated")
        except Exception as e:
            validation_errors.append(f"Voyage API key invalid: {str(e)[:100]}")
    
    # Validate Anthropic API
    if settings.anthropic_api_key:
        try:
            from anthropic import AsyncAnthropic
            client = AsyncAnthropic(api_key=settings.anthropic_api_key)
            # Quick test call
            await client.messages.create(
                model="claude-4.5-sonnet-20241022",
                max_tokens=10,
                messages=[{"role": "user", "content": "test"}]
            )
            logger.info(" Anthropic API key validated")
        except Exception as e:
            validation_errors.append(f"Anthropic API key invalid: {str(e)[:100]}")
    
    # Validate Pinecone API
    if settings.pinecone_api_key:
        try:
            from pinecone import Pinecone
            pc = Pinecone(api_key=settings.pinecone_api_key)
            pc.list_indexes()
            logger.info(" Pinecone API key validated")
        except Exception as e:
            validation_errors.append(f"Pinecone API key invalid: {str(e)[:100]}")
    
    if validation_errors:
        logger.error(f"API key validation failed: {', '.join(validation_errors)}")
        if settings.is_production:
            raise RuntimeError(f"API key validation failed in production: {validation_errors}")
    
    return len(validation_errors) == 0

