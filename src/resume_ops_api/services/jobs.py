from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import suppress

from resume_ops_api.api.models import TailorRequest
from resume_ops_api.core.exceptions import AppError
from resume_ops_api.services.callbacks import CallbackService
from resume_ops_api.services.orchestrator import TailorOrchestrator
from resume_ops_api.services.store import JobStore


class AsyncJobRunner:
    def __init__(
        self,
        *,
        store: JobStore,
        orchestrator: TailorOrchestrator,
        callback_service: CallbackService,
        max_concurrency: int,
    ) -> None:
        self.store = store
        self.orchestrator = orchestrator
        self.callback_service = callback_service
        self.max_concurrency = max_concurrency
        self.logger = logging.getLogger(__name__)
        self._event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._loop_task: asyncio.Task | None = None
        self._running_tasks: set[asyncio.Task] = set()

    async def start(self) -> None:
        await self.store.requeue_running()
        self._loop_task = asyncio.create_task(self._loop())
        self._event.set()

    async def stop(self) -> None:
        self._stop_event.set()
        self._event.set()
        if self._loop_task:
            self._loop_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._loop_task
        if self._running_tasks:
            for task in list(self._running_tasks):
                task.cancel()
            await asyncio.gather(*self._running_tasks, return_exceptions=True)

    async def submit(self, request: TailorRequest, theme: str) -> str:
        job_id = uuid.uuid4().hex
        await self.store.create(
            job_id=job_id,
            payload=request.model_dump(mode="json"),
            theme=theme,
            callback_url=str(request.callback_url) if request.callback_url else None,
        )
        self._event.set()
        return job_id

    async def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._schedule_available_jobs()
                try:
                    await asyncio.wait_for(self._event.wait(), timeout=1.0)
                except TimeoutError:
                    pass
                self._event.clear()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.logger.exception("Job loop error: %s", exc)
                await asyncio.sleep(1)

    async def _schedule_available_jobs(self) -> None:
        self._running_tasks = {task for task in self._running_tasks if not task.done()}
        while len(self._running_tasks) < self.max_concurrency:
            job = await self.store.claim_next_queued()
            if not job:
                break
            task = asyncio.create_task(self._run_job(job.id))
            self._running_tasks.add(task)

    async def _run_job(self, job_id: str) -> None:
        job = await self.store.get_or_raise(job_id)
        try:
            result = await self.orchestrator.run(
                resume=job.request_payload["resume"],
                job_description=job.request_payload["job_description"],
                theme=job.theme,
                task_id=job.id,
                sections=job.request_payload.get("sections"),
            )
            await self.store.mark_completed(job_id=job.id, resume=result.resume, pdf_path=result.pdf_path)
            if job.callback_url:
                await self.callback_service.deliver(
                    job.callback_url,
                    {
                        "task_id": job.id,
                        "status": "completed",
                        "result": {
                            "resume": result.resume,
                            "pdf_base64": result.pdf_base64,
                            "theme": result.theme,
                        },
                    },
                )
        except Exception as exc:
            if isinstance(exc, AppError):
                error_code = exc.code
                error_message = exc.message
            else:
                error_code = "job_execution_failed"
                error_message = str(exc)
            await self.store.mark_failed(job_id=job.id, error_code=error_code, error_message=error_message)
            if job.callback_url:
                try:
                    await self.callback_service.deliver(
                        job.callback_url,
                        {
                            "task_id": job.id,
                            "status": "failed",
                            "error": {"code": error_code, "message": error_message},
                        },
                    )
                except Exception as callback_exc:
                    self.logger.exception("Callback delivery failed for job %s: %s", job.id, callback_exc)

