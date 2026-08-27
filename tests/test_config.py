from __future__ import annotations

from pathlib import Path

import pytest

from resume_ops_api.core.config import Settings, get_settings


# ---------------------------------------------------------------------------
# Helper: construct Settings without loading any .env file or external env
# ---------------------------------------------------------------------------


def _clean_settings(**overrides: object) -> Settings:
    """Build a Settings instance ignoring any .env file.

    Explicit overrides take precedence.  Callers should still supply the
    exact defaults they expect when the host environment may carry
    conflicting OS-level environment variables.
    """
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


class TestSettingsDefaults:
    """Verify default values are sensible and match the documented configuration."""

    def test_default_app_name(self) -> None:
        settings = _clean_settings()
        assert settings.app_name == "resume-ops-api"

    def test_default_host_and_port(self) -> None:
        settings = _clean_settings()
        assert settings.host == "0.0.0.0"
        assert settings.port == 8000

    def test_default_log_level(self) -> None:
        settings = _clean_settings()
        assert settings.log_level == "INFO"

    def test_default_data_dir(self) -> None:
        # Explicit default to guard against host env vars
        settings = _clean_settings(data_dir=Path("/data"))
        assert settings.data_dir == Path("/data")

    def test_default_database_url_is_none(self) -> None:
        # Explicit None to guard against host env vars
        settings = _clean_settings(database_url=None)
        assert settings.database_url is None

    def test_default_model_names(self) -> None:
        # Explicit defaults to guard against host env vars
        settings = _clean_settings(
            strategy_model="openai/gpt-4o-mini",
            work_model="openai/gpt-4o-mini",
            education_model="openai/gpt-4o-mini",
            skills_model="openai/gpt-4o-mini",
            projects_model="openai/gpt-4o-mini",
            optional_sections_model="openai/gpt-4o-mini",
            certificates_model="openai/gpt-4o-mini",
            basics_model="openai/gpt-4o-mini",
        )
        assert settings.strategy_model == "openai/gpt-4o-mini"
        assert settings.work_model == "openai/gpt-4o-mini"
        assert settings.education_model == "openai/gpt-4o-mini"
        assert settings.skills_model == "openai/gpt-4o-mini"
        assert settings.projects_model == "openai/gpt-4o-mini"
        assert settings.optional_sections_model == "openai/gpt-4o-mini"
        assert settings.certificates_model == "openai/gpt-4o-mini"
        assert settings.basics_model == "openai/gpt-4o-mini"

    def test_default_theme_and_allowed_themes(self) -> None:
        settings = _clean_settings()
        assert settings.default_theme == "jsonresume-theme-folio"
        assert settings.allowed_themes == [
            "jsonresume-theme-folio",
            "jsonresume-theme-folio-concise",
            "jsonresume-theme-stackoverflow",
        ]

    def test_default_max_concurrent_jobs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MAX_CONCURRENT_JOBS", raising=False)
        settings = _clean_settings()
        assert settings.max_concurrent_jobs == 2

    def test_default_callback_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CALLBACK_TIMEOUT_SECONDS", raising=False)
        settings = _clean_settings()
        assert settings.callback_timeout_seconds == 5

    def test_default_llm_cache(self) -> None:
        settings = _clean_settings()
        assert settings.llm_cache is False


    def test_default_api_keys_are_none(self) -> None:
        # Explicit None to guard against host env vars
        settings = _clean_settings(
            openai_api_key=None,
            anthropic_api_key=None,
            gemini_api_key=None,
        )
        assert settings.openai_api_key is None
        assert settings.anthropic_api_key is None
        assert settings.gemini_api_key is None

    def test_default_openai_base_url_is_none(self) -> None:
        # Explicit None to guard against host env vars
        settings = _clean_settings(openai_base_url=None)
        assert settings.openai_base_url is None


class TestSettingsEnvironmentOverrides:
    """Verify settings load correctly from environment variables.

    Uses _env_file=None to prevent the local .env file from interfering.
    """

    def test_app_name_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_NAME", "my-custom-app")
        settings = _clean_settings()
        assert settings.app_name == "my-custom-app"

    def test_host_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOST", "127.0.0.1")
        settings = _clean_settings()
        assert settings.host == "127.0.0.1"

    def test_port_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PORT", "9000")
        settings = _clean_settings()
        assert settings.port == 9000

    def test_log_level_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        settings = _clean_settings()
        assert settings.log_level == "DEBUG"

    def test_data_dir_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATA_DIR", "/custom/data")
        settings = _clean_settings()
        assert settings.data_dir == Path("/custom/data")

    def test_database_url_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/db")
        settings = _clean_settings()
        assert settings.database_url == "postgresql+asyncpg://user:pass@localhost/db"

    def test_model_names_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("STRATEGY_MODEL", "anthropic/claude-3-opus")
        monkeypatch.setenv("WORK_MODEL", "anthropic/claude-3-sonnet")
        settings = _clean_settings()
        assert settings.strategy_model == "anthropic/claude-3-opus"
        assert settings.work_model == "anthropic/claude-3-sonnet"

    def test_default_theme_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEFAULT_THEME", "jsonresume-theme-even")
        # pydantic-settings expects JSON arrays for list types in env vars
        monkeypatch.setenv("ALLOWED_THEMES", '["jsonresume-theme-even", "jsonresume-theme-stackoverflow"]')
        settings = _clean_settings()
        assert settings.default_theme == "jsonresume-theme-even"

    def test_allowed_themes_from_json_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """pydantic-settings decodes list types as JSON from env vars."""
        monkeypatch.setenv(
            "ALLOWED_THEMES",
            '["jsonresume-theme-even", "jsonresume-theme-stackoverflow", "jsonresume-theme-onepage"]',
        )
        settings = _clean_settings()
        assert settings.allowed_themes == [
            "jsonresume-theme-even",
            "jsonresume-theme-stackoverflow",
            "jsonresume-theme-onepage",
        ]

    def test_allowed_themes_from_single_json_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALLOWED_THEMES", '["jsonresume-theme-even"]')
        settings = _clean_settings()
        assert settings.allowed_themes == ["jsonresume-theme-even"]

    def test_max_concurrent_jobs_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MAX_CONCURRENT_JOBS", "4")
        settings = _clean_settings()
        assert settings.max_concurrent_jobs == 4

    def test_callback_timeout_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CALLBACK_TIMEOUT_SECONDS", "10")
        settings = _clean_settings()
        assert settings.callback_timeout_seconds == 10

    def test_api_keys_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-test-key")
        monkeypatch.setenv("GEMINI_API_KEY", "gem-test-key")
        settings = _clean_settings()
        assert settings.openai_api_key == "sk-test-key"
        assert settings.anthropic_api_key == "ant-test-key"
        assert settings.gemini_api_key == "gem-test-key"

    def test_openai_base_url_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_BASE_URL", "https://proxy.example.com/v1")
        settings = _clean_settings()
        assert settings.openai_base_url == "https://proxy.example.com/v1"

    def test_llm_cache_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_CACHE", "true")
        settings = _clean_settings()
        assert settings.llm_cache is True


class TestSettingsFieldValidators:
    """Verify custom field validators work correctly.

    Uses _clean_settings to avoid interference from the local .env file.
    """

    def test_parse_allowed_themes_from_list(self) -> None:
        settings = _clean_settings(allowed_themes=["theme-a", "theme-b"])
        assert settings.allowed_themes == ["theme-a", "theme-b"]

    def test_parse_allowed_themes_from_string(self) -> None:
        settings = _clean_settings(allowed_themes="theme-a, theme-b , theme-c")
        assert settings.allowed_themes == ["theme-a", "theme-b", "theme-c"]

    def test_parse_allowed_themes_handles_empty_elements(self) -> None:
        settings = _clean_settings(allowed_themes="theme-a,, theme-b ,   ")
        assert settings.allowed_themes == ["theme-a", "theme-b"]

    def test_parse_allowed_themes_from_none_returns_default(self) -> None:
        settings = _clean_settings(allowed_themes=None)  # type: ignore[arg-type]
        assert settings.allowed_themes == [
            "jsonresume-theme-folio",
            "jsonresume-theme-folio-concise",
            "jsonresume-theme-stackoverflow",
        ]

    def test_default_theme_strips_whitespace(self) -> None:
        settings = _clean_settings(default_theme="  jsonresume-theme-even  ")
        assert settings.default_theme == "jsonresume-theme-even"

    def test_default_theme_empty_string_raises_error(self) -> None:
        with pytest.raises(ValueError, match="DEFAULT_THEME must not be empty"):
            _clean_settings(default_theme="   ")

    def test_default_theme_empty_string_after_strip_raises_error(self) -> None:
        with pytest.raises(ValueError, match="DEFAULT_THEME must not be empty"):
            _clean_settings(default_theme="")


class TestSettingsComputedProperties:
    """Verify computed properties derive correct values."""

    def test_resolved_database_url_when_explicit(self) -> None:
        settings = _clean_settings(database_url="postgresql+asyncpg://localhost/test")
        assert settings.resolved_database_url == "postgresql+asyncpg://localhost/test"

    def test_resolved_database_url_defaults_to_sqlite(self, tmp_path: Path) -> None:
        settings = _clean_settings(data_dir=tmp_path)
        expected = f"sqlite+aiosqlite:///{tmp_path / 'resume_ops.db'}"
        assert settings.resolved_database_url == expected

    def test_resolved_database_url_uses_data_dir_without_database_url(self, tmp_path: Path) -> None:
        settings = _clean_settings(data_dir=tmp_path / "nested", database_url=None)
        expected = f"sqlite+aiosqlite:///{tmp_path / 'nested' / 'resume_ops.db'}"
        assert settings.resolved_database_url == expected

    def test_jobs_dir_derives_from_data_dir(self, tmp_path: Path) -> None:
        settings = _clean_settings(data_dir=tmp_path)
        assert settings.jobs_dir == tmp_path / "jobs"

    def test_schema_path_exists_and_is_json(self) -> None:
        settings = _clean_settings()
        assert settings.schema_path.exists()
        assert settings.schema_path.suffix == ".json"
        assert settings.schema_path.name == "resume_schema.json"


class TestGetSettings:
    """Verify the cached settings factory."""

    def test_get_settings_returns_settings_instance(self) -> None:
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_get_settings_is_cached(self) -> None:
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_get_settings_respects_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Clear the lru_cache before testing
        get_settings.cache_clear()
        monkeypatch.setenv("APP_NAME", "env-cached-app")
        try:
            settings = get_settings()
            assert settings.app_name == "env-cached-app"
        finally:
            get_settings.cache_clear()

    def test_get_settings_ignores_unknown_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("UNKNOWN_SETTING", "should-be-ignored")
        # Ensure model is defined for test context so it doesn't fail model validation
        settings = Settings(default_model="openai/gpt-4o-mini")
        assert not hasattr(settings, "unknown_setting")


class TestSettingsModelResolution:
    """Verify that models resolve dynamically from default_model or fail fast."""

    @pytest.fixture(autouse=True)
    def clear_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for var in [
            "DEFAULT_MODEL",
            "STRATEGY_MODEL",
            "WORK_MODEL",
            "EDUCATION_MODEL",
            "SKILLS_MODEL",
            "PROJECTS_MODEL",
            "CERTIFICATES_MODEL",
            "OPTIONAL_SECTIONS_MODEL",
            "BASICS_MODEL",
        ]:
            monkeypatch.delenv(var, raising=False)

    def test_resolve_from_default_model(self) -> None:
        # If only default_model is set, all section models should resolve to it
        settings = Settings(
            _env_file=None,
            default_model="openai/gpt-4o-mini",
        )
        assert settings.strategy_model == "openai/gpt-4o-mini"
        assert settings.work_model == "openai/gpt-4o-mini"
        assert settings.certificates_model == "openai/gpt-4o-mini"
        assert settings.basics_model == "openai/gpt-4o-mini"

    def test_resolve_with_specific_override(self) -> None:
        # If a specific section model is set, it overrides default_model
        settings = Settings(
            _env_file=None,
            default_model="openai/gpt-4o-mini",
            strategy_model="anthropic/claude-3-opus",
        )
        assert settings.strategy_model == "anthropic/claude-3-opus"
        assert settings.work_model == "openai/gpt-4o-mini"
        assert settings.certificates_model == "openai/gpt-4o-mini"
        assert settings.basics_model == "openai/gpt-4o-mini"

    def test_fail_validation_when_no_model_set(self) -> None:
        # If neither default nor specific models are set, it must fail validation
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="Missing required model configurations"):
            Settings(_env_file=None)


class TestSettingsTailorSections:
    """Verify TAILOR_SECTIONS configuration parsing and defaults."""

    def test_default_tailor_sections(self) -> None:
        settings = Settings(_env_file=None, default_model="openai/gpt-4o-mini")
        assert settings.tailor_sections == ["basics", "work", "skills", "projects", "education", "certificates"]

    def test_tailor_sections_from_comma_separated_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAILOR_SECTIONS", "work, skills, projects")
        settings = Settings(default_model="openai/gpt-4o-mini")
        assert settings.tailor_sections == ["work", "skills", "projects"]

    def test_tailor_sections_from_list(self) -> None:
        settings = Settings(
            _env_file=None,
            default_model="openai/gpt-4o-mini",
            tailor_sections=["work", "basics"],
        )
        assert settings.tailor_sections == ["work", "basics"]

    def test_consolidated_models_resolve(self) -> None:
        settings = Settings(
            _env_file=None,
            default_model="openai/gpt-4o-mini",
            strategy_and_basics_model="anthropic/claude-3-5-sonnet",
            qualifications_model="google/gemini-2.0-flash",
        )
        assert settings.strategy_and_basics_model == "anthropic/claude-3-5-sonnet"
        assert settings.qualifications_model == "google/gemini-2.0-flash"
        assert settings.work_model == "openai/gpt-4o-mini"
        assert settings.projects_model == "openai/gpt-4o-mini"


