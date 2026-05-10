from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Service identity
    app_name: str = "capability-intelligence"
    env: Literal["dev", "staging", "prod"] = "dev"
    log_level: str = "INFO"

    # HTTP
    host: str = "0.0.0.0"
    port: int = 8080
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://localhost:8080"])

    # Auth
    auth_mode: Literal["dev", "firebase"] = "dev"
    auth_allowed_domain: str = "zennify.com"
    firebase_project_id: str | None = None

    # GCP — all optional in dev, required in prod
    use_gcp: bool = False
    gcp_project_id: str | None = None
    gcp_region: str = "us-central1"

    # Emulator endpoints (for local docker-compose)
    firestore_emulator_host: str | None = None  # e.g. "firestore:8200"
    pubsub_emulator_host: str | None = None     # e.g. "pubsub:8085"
    storage_emulator_host: str | None = None    # e.g. "http://gcs:4443"

    # Storage
    bucket_sows_raw: str | None = None
    bucket_sows_redacted: str | None = None
    bucket_snapshots: str | None = None
    bucket_reports: str | None = None
    bucket_jira_raw: str | None = None
    bucket_news_raw: str | None = None

    # BigQuery
    bq_dataset_capability_catalogue: str = "capability_catalogue"
    bq_dataset_continuous_validation: str = "continuous_validation"
    bq_dataset_benchmarks: str = "benchmarks"
    bq_dataset_lifecycle: str = "lifecycle"
    bq_dataset_vendor_intel: str = "vendor_intel"
    bq_dataset_evals: str = "evals"
    bq_dataset_evidence_index: str = "evidence_index"
    bq_dataset_reasoning_chains: str = "reasoning_chains"
    bq_dataset_cost_tracking: str = "cost_tracking"

    # LLM (Batch 4 wires these)
    anthropic_api_key: str | None = None
    anthropic_model_sonnet: str = "claude-sonnet-4-6"
    anthropic_model_opus: str = "claude-opus-4-7"
    vertex_region: str = "us-central1"
    vertex_embedding_model: str = "text-embedding-005"
    gemini_model_flash: str = "gemini-2.5-flash"
    gemini_model_pro: str = "gemini-2.5-pro"

    # Cost guardrails (Batch 4)
    daily_spend_ceiling_usd: float = 0.0  # 0 = disabled
    anthropic_weekly_budget_usd: float = 0.0

    # Drive (Batch 1) and Jira (Batch 3)
    drive_pillars_folder_id: str | None = None
    drive_sows_folder_id: str | None = None
    jira_base_url: str | None = None
    jira_email: str | None = None
    jira_api_token: str | None = None
    jira_project_keys: list[str] = Field(default_factory=list)


@lru_cache
def get_settings() -> Settings:
    return Settings()
