"""
Configuration for Layer 6 — Orchestration

This module provides configuration settings for the synchronous and asynchronous
execution planes of the CAD manufacturability analysis system.
"""

import os
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

class RedisConfig(BaseModel):
    """Redis configuration for job storage and task brokering."""
    host: str = Field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    port: int = Field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    db_broker: int = Field(default_factory=lambda: int(os.getenv("REDIS_DB_BROKER", "1")))
    db_backend: int = Field(default_factory=lambda: int(os.getenv("REDIS_DB_BACKEND", "2")))
    password: Optional[str] = Field(default_factory=lambda: os.getenv("REDIS_PASSWORD"))
    ttl_seconds: int = Field(default=3600, description="Job result TTL in seconds")

    @property
    def broker_url(self) -> str:
        """Redis URL for Celery broker."""
        auth = f":{self.password}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db_broker}"

    @property
    def backend_url(self) -> str:
        """Redis URL for Celery result backend."""
        auth = f":{self.password}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db_backend}"

class CeleryConfig(BaseModel):
    """Celery configuration for asynchronous task execution."""
    broker_url: str = Field(default_factory=lambda: os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1"))
    result_backend: str = Field(default_factory=lambda: os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2"))
    task_serializer: str = "json"
    accept_content: list = ["json"]
    result_serializer: str = "json"
    timezone: str = "UTC"
    enable_utc: bool = True
    task_track_started: bool = True
    task_time_limit: int = 3600  # 1 hour
    task_soft_time_limit: int = 3300  # 55 minutes
    worker_prefetch_multiplier: int = 1
    task_acks_late: bool = True
    task_reject_on_worker_lost: bool = True

class FastAPIConfig(BaseModel):
    """FastAPI configuration for the synchronous request plane."""
    host: str = Field(default_factory=lambda: os.getenv("FASTAPI_HOST", "0.0.0.0"))
    port: int = Field(default_factory=lambda: int(os.getenv("FASTAPI_PORT", "8000")))
    workers: int = Field(default_factory=lambda: int(os.getenv("FASTAPI_WORKERS", "1")))
    reload: bool = Field(default_factory=lambda: os.getenv("FASTAPI_RELOAD", "false").lower() == "true")

class PrefectConfig(BaseModel):
    """Prefect configuration for workflow orchestration."""
    api_url: str = Field(default_factory=lambda: os.getenv("PREFECT_API_URL", "http://localhost:4200/api"))
    server_host: str = Field(default_factory=lambda: os.getenv("PREFECT_SERVER_HOST", "localhost"))
    server_port: int = Field(default_factory=lambda: int(os.getenv("PREFECT_SERVER_PORT", "4200")))
    ui_url: str = Field(default_factory=lambda: os.getenv("PREFECT_UI_URL", "http://localhost:4200"))

class FileStorageConfig(BaseModel):
    """File storage configuration for uploads and results."""
    upload_dir: str = Field(default_factory=lambda: os.getenv("UPLOAD_DIR", "/tmp/cad_analysis_uploads"))
    results_dir: str = Field(default_factory=lambda: os.getenv("RESULTS_DIR", "/tmp/analysis_results"))
    max_file_size_mb: int = Field(default=100, description="Maximum file size in MB")
    allowed_extensions: list = [".stl", ".step", ".stp", ".obj", ".off"]

class OrchestrationConfig(BaseModel):
    """Main configuration for the orchestration layer."""
    redis: RedisConfig = Field(default_factory=RedisConfig)
    celery: CeleryConfig = Field(default_factory=CeleryConfig)
    fastapi: FastAPIConfig = Field(default_factory=FastAPIConfig)
    prefect: PrefectConfig = Field(default_factory=PrefectConfig)
    storage: FileStorageConfig = Field(default_factory=FileStorageConfig)

    # Derived properties
    @property
    def celery_broker_url(self) -> str:
        """Get Celery broker URL from Redis config."""
        return self.redis.broker_url

    @property
    def celery_backend_url(self) -> str:
        """Get Celery backend URL from Redis config."""
        return self.redis.backend_url

# Global configuration instance
config = OrchestrationConfig()

# Environment variable overrides for easy deployment
def load_from_env():
    """Load configuration from environment variables."""
    global config
    config = OrchestrationConfig()

# Export for use in other modules
__all__ = ['config', 'OrchestrationConfig', 'load_from_env']