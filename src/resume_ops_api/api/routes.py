from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from resume_ops_api.api.deps import get_container
from resume_ops_api.api.models import (
    HealthResponse,
    MasterResumeStatus,
    QueuedTaskResponse,
    TailorRequest,
    TailorResponse,
    TaskError,
    TaskStatusResponse,
    ThemeListResponse,
)
from resume_ops_api.services.ats_text import json_to_ats_text
from resume_ops_api.services.container import ServiceContainer

router = APIRouter()



@router.get("/healthz", response_model=HealthResponse)
async def healthcheck() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=HealthResponse)
async def readyz(container: ServiceContainer = Depends(get_container)) -> HealthResponse:
    await container.database.ping()
    return HealthResponse(status="ready")


@router.get("/api/v1/master-resume/status", response_model=MasterResumeStatus)
async def get_master_resume_status(container: ServiceContainer = Depends(get_container)) -> MasterResumeStatus:
    if not container.settings.master_resume_path:
        return MasterResumeStatus(configured=False, exists=False, valid=False, message="No master resume configured")
    if not container.settings.master_resume_path.exists():
        return MasterResumeStatus(configured=True, exists=False, valid=False, message="Master resume file not found")
    if not container.master_resume:
        return MasterResumeStatus(configured=True, exists=True, valid=False, message="Master resume is invalid")
    return MasterResumeStatus(configured=True, exists=True, valid=True, message="Master resume loaded successfully")


@router.get("/api/v1/themes", response_model=ThemeListResponse)
async def list_themes(container: ServiceContainer = Depends(get_container)) -> ThemeListResponse:
    return ThemeListResponse(
        default_theme=container.theme_service.default_theme,
        allowed_themes=container.theme_service.allowed_themes,
    )


@router.post(
    "/api/v1/tailor",
    response_model=TailorResponse | QueuedTaskResponse,
    status_code=status.HTTP_200_OK,
)
async def tailor_resume(
    payload: TailorRequest,
    response: Response,
    container: ServiceContainer = Depends(get_container),
) -> TailorResponse | QueuedTaskResponse:
    if payload.resume is None:
        if not container.master_resume:
            raise HTTPException(status_code=400, detail="No resume provided and no master resume configured or valid")
        resume_data = container.master_resume
    else:
        resume_data = payload.resume

    # Create a new payload with the resolved resume to pass to the async job runner if needed
    effective_payload = TailorRequest(
        resume=resume_data,
        job_description=payload.job_description,
        theme=payload.theme,
        callback_url=payload.callback_url,
        sections=payload.sections,
    )

    theme = container.theme_service.resolve(payload.theme)
    if payload.callback_url:
        task_id = await container.job_runner.submit(effective_payload, theme)
        response.status_code = status.HTTP_202_ACCEPTED
        return QueuedTaskResponse(task_id=task_id, status="queued")

    result = await container.orchestrator.run(
        resume=resume_data,
        job_description=payload.job_description,
        theme=theme,
        sections=payload.sections,
    )
    return TailorResponse(resume=result.resume, pdf_base64=result.pdf_base64, theme=result.theme, plain_text=result.plain_text)


@router.get("/api/v1/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    container: ServiceContainer = Depends(get_container),
) -> TaskStatusResponse:
    job = await container.job_store.get_or_raise(task_id)
    error = None
    if job.error_code and job.error_message:
        error = TaskError(code=job.error_code, message=job.error_message)
    pdf_base64 = None
    if job.result_pdf_path:
        pdf_base64 = await container.orchestrator.encode_pdf(job.result_pdf_path)
    plain_text = None
    if job.result_resume_json:
        plain_text = json_to_ats_text(job.result_resume_json)
    return TaskStatusResponse(
        task_id=job.id,
        status=job.status,
        created_at=job.created_at,
        updated_at=job.updated_at,
        resume=job.result_resume_json,
        pdf_base64=pdf_base64,
        plain_text=plain_text,
        error=error,
        theme=job.theme,
    )

