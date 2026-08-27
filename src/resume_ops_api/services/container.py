from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from resume_ops_api.core.config import Settings
from resume_ops_api.db.session import Database
from resume_ops_api.graph.merge import ResumeMerger
from resume_ops_api.graph.pipeline import ResumeGraph
from resume_ops_api.services.callbacks import CallbackService
from resume_ops_api.services.jobs import AsyncJobRunner
from resume_ops_api.services.llm import StructuredLLMClient
from resume_ops_api.services.orchestrator import TailorOrchestrator
from resume_ops_api.services.renderer import ResumeRenderer
from resume_ops_api.services.schema import ResumeSchemaValidator
from resume_ops_api.services.store import JobStore
from resume_ops_api.services.themes import ThemeService
from resume_ops_api.services.tracing import setup_tracing


@dataclass
class ServiceContainer:
    settings: Settings
    database: Database
    validator: ResumeSchemaValidator
    theme_service: ThemeService
    llm_client: StructuredLLMClient
    renderer: ResumeRenderer
    callback_service: CallbackService
    job_store: JobStore
    orchestrator: TailorOrchestrator
    job_runner: AsyncJobRunner
    _master_resume: dict[str, Any] | None = None

    @property
    def master_resume(self) -> dict[str, Any] | None:
        if self._master_resume is not None:
            return self._master_resume
            
        if not self.settings.master_resume_path or not self.settings.master_resume_path.exists():
            return None
            
        try:
            with open(self.settings.master_resume_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.validator.validate(data, context="master resume")
            self._master_resume = data
            return self._master_resume
        except Exception as e:
            logging.getLogger(__name__).error(f"Failed to load master resume from {self.settings.master_resume_path}: {e}")
            return None

    async def start(self) -> None:
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings.jobs_dir.mkdir(parents=True, exist_ok=True)
        await self.database.bootstrap()
        await self.job_runner.start()

    async def stop(self) -> None:
        await self.job_runner.stop()
        await self.database.dispose()


def build_container(settings: Settings, **overrides: Any) -> ServiceContainer:
    setup_tracing(settings)
    database = overrides.get("database") or Database(settings.resolved_database_url)
    validator = overrides.get("validator") or ResumeSchemaValidator(settings.schema_path)
    theme_service = overrides.get("theme_service") or ThemeService(settings.allowed_themes, settings.default_theme)
    llm_client = overrides.get("llm_client") or StructuredLLMClient(
        rate_limit_requests=settings.llm_rate_limit_requests,
        rate_limit_period=settings.llm_rate_limit_period,
        max_concurrency=settings.llm_max_concurrency,
        enable_cache=settings.llm_cache,
        max_retries=settings.llm_max_retries,
        retry_min_wait=settings.llm_retry_min_wait_seconds,
        retry_max_wait=settings.llm_retry_max_wait_seconds,
        retry_multiplier=settings.llm_retry_multiplier,
    )
    renderer = overrides.get("renderer") or ResumeRenderer()
    callback_service = overrides.get("callback_service") or CallbackService(settings.callback_timeout_seconds)
    merger = overrides.get("merger") or ResumeMerger()
    graph = overrides.get("graph") or ResumeGraph(
        llm_client=llm_client,
        merger=merger,
        renderer=renderer,
        validator=validator,
        strategy_and_basics_model=settings.strategy_and_basics_model,
        work_model=settings.work_model,
        qualifications_model=settings.qualifications_model,
        projects_model=settings.projects_model,
        style=settings.tailoring_style,
        default_sections=settings.tailor_sections,
    )
    orchestrator = overrides.get("orchestrator") or TailorOrchestrator(
        graph=graph,
        validator=validator,
        jobs_dir=settings.jobs_dir,
    )
    job_store = overrides.get("job_store") or JobStore(database)
    job_runner = overrides.get("job_runner") or AsyncJobRunner(
        store=job_store,
        orchestrator=orchestrator,
        callback_service=callback_service,
        max_concurrency=settings.max_concurrent_jobs,
    )
    return ServiceContainer(
        settings=settings,
        database=database,
        validator=validator,
        theme_service=theme_service,
        llm_client=llm_client,
        renderer=renderer,
        callback_service=callback_service,
        job_store=job_store,
        orchestrator=orchestrator,
        job_runner=job_runner,
    )

