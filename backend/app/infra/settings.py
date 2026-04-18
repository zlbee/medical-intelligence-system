from functools import lru_cache
import json
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "Medical Intelligence System API"
    app_version: str = "0.1.0"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'data' / 'medical_intelligence.db').as_posix()}"
    report_output_dir: str = str(BACKEND_DIR / "reports")
    external_request_timeout_seconds: float = 30.0
    http_user_agent: str = "medical-intelligence-system/0.1.0"
    clinicaltrials_base_url: str = "https://clinicaltrials.gov/api/v2"
    pubmed_esearch_url: str = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    )
    pubmed_efetch_url: str = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    )
    ncbi_tool: str = "medical-intelligence-system"
    ncbi_email: str | None = None
    ncbi_api_key: str | None = None
    llm_provider: str = "openrouter"
    llm_api_key: str | None = None
    llm_default_model: str | None = None
    llm_request_timeout_seconds: float = 60.0
    llm_enable_response_healing: bool = True
    llm_openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_openrouter_site_url: str | None = None
    llm_openrouter_app_title: str = "Medical Intelligence System"
    fetch_clinicaltrials_max_records: int = 100
    fetch_pubmed_max_records: int = 100
    fetch_query_interval_seconds: float = 0.5
    analysis_llm_enrichment_full_scan: bool = True
    analysis_llm_enrichment_top_n: int = 20

    model_config = SettingsConfigDict(
        env_prefix="MIS_",
        case_sensitive=False,
        extra="ignore",
        env_file=str(BACKEND_DIR.parent / ".env"),
        env_file_encoding="utf-8",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            if value.strip().startswith("["):
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator(
        "fetch_clinicaltrials_max_records",
        "fetch_pubmed_max_records",
    )
    @classmethod
    def validate_fetch_record_caps(cls, value: int) -> int:
        if value < 1:
            raise ValueError("fetch record caps must be >= 1")
        return value

    @field_validator("fetch_query_interval_seconds")
    @classmethod
    def validate_fetch_query_interval_seconds(cls, value: float) -> float:
        if value < 0:
            raise ValueError("fetch_query_interval_seconds must be >= 0")
        return value

    @field_validator("analysis_llm_enrichment_top_n")
    @classmethod
    def validate_analysis_llm_enrichment_top_n(cls, value: int) -> int:
        if value < 0:
            raise ValueError("analysis_llm_enrichment_top_n must be >= 0")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
