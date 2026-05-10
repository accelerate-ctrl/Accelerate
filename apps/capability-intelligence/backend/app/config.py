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
    google_application_credentials: str | None = None  # path to SA JSON

    # Firestore (MongoDB compatibility mode)
    firestore_database_id: str = "dma-assessor"
    firestore_mongo_uri: str | None = None
    firestore_mongo_db_name: str | None = None  # defaults to firestore_database_id

    # Local dev persistence (used when use_gcp=False) — JSON file
    local_repository_path: str = ".local-repo.json"

    # Where to look for the Pillar 1 (and later) catalogue files for local
    # ingestion when Drive isn't configured. Used in dev + tests.
    local_catalogue_dir: str | None = None

    # Where to look for SOW files locally (status subfolders: active|prospect|
    # inactive|archived). Falls back to test-data/SOWs/ if unset.
    local_sows_dir: str | None = None

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

    # When False (default in dev), all model adapters resolve to deterministic
    # canned responses keyed off the prompt+model+temperature. This keeps
    # tests hermetic and lets the entire 7-step consultant loop, gates,
    # adversarial review, and reasoning-chain logging run without hitting
    # any external API. Flip to True once Anthropic + Vertex creds are set.
    llm_live_mode: bool = False

    # Cost guardrails (Batch 4)
    daily_spend_ceiling_usd: float = 0.0  # 0 = disabled
    anthropic_weekly_budget_usd: float = 0.0
    cost_throttle_pct: float = 0.9  # at 90% of ceiling, refuse new calls

    # News + trends (Batch 4)
    local_news_dir: str | None = None    # falls back to test-data/news/
    local_trends_dir: str | None = None  # falls back to test-data/trends/
    news_feeds: list[str] = Field(default_factory=list)  # RSS URLs (live mode)

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
