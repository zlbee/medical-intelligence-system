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

    model_config = SettingsConfigDict(
        env_prefix="MIS_",
        case_sensitive=False,
        extra="ignore",
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
