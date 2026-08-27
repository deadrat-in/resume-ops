from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "resume-ops-api"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    data_dir: Path = Path("/data")
    database_url: str | None = None
    master_resume_path: Path | None = None
    
    default_model: str | None = None
    strategy_and_basics_model: str | None = None
    strategy_model: str | None = None
    work_model: str | None = None
    qualifications_model: str | None = None
    education_model: str | None = None
    skills_model: str | None = None
    projects_model: str | None = None
    certificates_model: str | None = None
    optional_sections_model: str | None = None
    basics_model: str | None = None

    tailor_sections: list[str] | str = Field(
        default_factory=lambda: [
            "basics",
            "work",
            "skills",
            "projects",
            "education",
            "certificates",
        ]
    )

    tailoring_style: str | None = None

    @model_validator(mode="after")
    def resolve_and_validate_models(self) -> Settings:
        # Fallback consolidated models from legacy fields if not explicitly provided
        if not self.strategy_and_basics_model or not self.strategy_and_basics_model.strip():
            self.strategy_and_basics_model = (
                self.strategy_model
                or self.basics_model
                or self.default_model
            )
        if not self.qualifications_model or not self.qualifications_model.strip():
            self.qualifications_model = (
                self.skills_model
                or self.certificates_model
                or self.education_model
                or self.default_model
            )

        model_fields = [
            "strategy_and_basics_model",
            "strategy_model",
            "work_model",
            "qualifications_model",
            "education_model",
            "skills_model",
            "projects_model",
            "certificates_model",
            "optional_sections_model",
            "basics_model",
        ]
        for field in model_fields:
            val = getattr(self, field)
            if val is None or not val.strip():
                if self.default_model and self.default_model.strip():
                    setattr(self, field, self.default_model)
                else:
                    setattr(self, field, None)
            else:
                setattr(self, field, val.strip())

        # Validate that required consolidated models are set
        required_fields = [
            "strategy_and_basics_model",
            "work_model",
            "qualifications_model",
            "projects_model",
        ]
        missing = [f.upper() for f in required_fields if getattr(self, f) is None]
        if missing:
            raise ValueError(
                f"Missing required model configurations. You must configure DEFAULT_MODEL "
                f"or configure each of the following in your environment/.env: {', '.join(missing)}"
            )
        return self
    default_theme: str = "jsonresume-theme-folio"
    allowed_themes: list[str] = Field(
        default_factory=lambda: [
            "jsonresume-theme-folio",
            "jsonresume-theme-folio-concise",
            "jsonresume-theme-stackoverflow",
        ]
    )
    max_concurrent_jobs: int = 2
    callback_timeout_seconds: int = 5
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    openai_base_url: str | None = None
    llm_rate_limit_requests: int | None = None
    llm_rate_limit_period: float = 60.0
    llm_max_concurrency: int | None = None
    llm_cache: bool = False
    llm_max_retries: int = 10
    llm_retry_min_wait_seconds: float = 3.0
    llm_retry_max_wait_seconds: float = 60.0
    llm_retry_multiplier: float = 3.0

    # Tracing & Evaluation Configuration
    enable_tracing: bool = False
    opik_api_key: str | None = None
    opik_project_name: str = "resume-ops"
    opik_workspace: str | None = None
    eval_model: str | None = None

    @field_validator("tailor_sections", mode="before")
    @classmethod
    def parse_tailor_sections(cls, value: object) -> list[str]:
        if value is None:
            return ["basics", "work", "skills", "projects", "education", "certificates"]
        if isinstance(value, str):
            return [item.strip().lower() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item).strip().lower() for item in value if str(item).strip()]
        raise ValueError("TAILOR_SECTIONS must be a comma-separated string or list.")

    @field_validator("allowed_themes", mode="before")
    @classmethod
    def parse_allowed_themes(cls, value: object) -> list[str]:
        if value is None:
            return ["jsonresume-theme-folio", "jsonresume-theme-folio-concise", "jsonresume-theme-stackoverflow"]
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        raise ValueError("ALLOWED_THEMES must be a comma-separated string or list.")

    @field_validator("default_theme")
    @classmethod
    def validate_default_theme(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("DEFAULT_THEME must not be empty.")
        return value.strip()

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite+aiosqlite:///{self.data_dir / 'resume_ops.db'}"

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def schema_path(self) -> Path:
        return Path(__file__).resolve().parent.parent / "resources" / "resume_schema.json"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

