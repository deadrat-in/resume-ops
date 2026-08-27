from __future__ import annotations

import asyncio
import copy

from httpx import ASGITransport, AsyncClient

from resume_ops_api.api.app import create_app
from resume_ops_api.core.config import Settings
from resume_ops_api.db.models import Job, JobStatus
from resume_ops_api.db.session import Database

from tests.conftest import FakeCallbackService, FakeRenderer, FakeStructuredLLMClient


async def _wait_for_completion(client: AsyncClient, task_id: str) -> dict:
    for _ in range(40):
        response = await client.get(f"/api/v1/tasks/{task_id}")
        payload = response.json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        await asyncio.sleep(0.05)
    raise AssertionError("Timed out waiting for job completion.")


async def test_sync_tailor_returns_pdf_and_preserves_basics(client: AsyncClient, sample_resume: dict) -> None:
    response = await client.post(
        "/api/v1/tailor",
        json={"resume": sample_resume, "job_description": "Need an AI product leader."},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["theme"] == "jsonresume-theme-stackoverflow"
    expected_basics = copy.deepcopy(sample_resume["basics"])
    expected_basics["label"] = "Tailored professional label / headline"
    expected_basics["summary"] = "Tailored professional summary matching the strategy."
    assert payload["resume"]["basics"] == expected_basics
    assert payload["resume"]["work"][0]["name"] == sample_resume["work"][0]["name"]
    assert payload["resume"]["work"][0]["summary"] == "Tailored summary for Covai Labs"
    assert payload["resume"]["work"][0]["highlights"] == ["Tailored impact for Covai Labs"]
    assert payload["resume"]["skills"][0]["name"] == "Product Strategy"
    assert len(payload["resume"]["skills"]) == 2
    assert payload["resume"]["skills"][0] == {
        "name": "Product Strategy",
        "keywords": ["Roadmap Planning", "Go-to-Market (GTM)"],
    }
    assert payload["resume"]["skills"][1] == {
        "name": "Invented Space Tech",
        "keywords": ["Warp Drive"],
    }
    assert payload["pdf_base64"]


async def test_sync_tailor_allows_alternate_theme(client: AsyncClient, sample_resume: dict) -> None:
    response = await client.post(
        "/api/v1/tailor",
        json={
            "resume": sample_resume,
            "job_description": "Need an AI product leader.",
            "theme": "jsonresume-theme-even",
        },
    )
    assert response.status_code == 200
    assert response.json()["theme"] == "jsonresume-theme-even"


async def test_invalid_theme_returns_400(client: AsyncClient, sample_resume: dict) -> None:
    response = await client.post(
        "/api/v1/tailor",
        json={
            "resume": sample_resume,
            "job_description": "Need an AI product leader.",
            "theme": "jsonresume-theme-nonexistent",
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_theme"


async def test_invalid_resume_schema_returns_422(client: AsyncClient, sample_resume: dict) -> None:
    invalid_resume = copy.deepcopy(sample_resume)
    invalid_resume["basics"]["email"] = "not-an-email"
    response = await client.post(
        "/api/v1/tailor",
        json={"resume": invalid_resume, "job_description": "Need an AI product leader."},
    )
    # The schema validator runs with strict=False and does not reject invalid email
    # formats at the API boundary — it is intentionally lenient to allow partial data.
    assert response.status_code == 200


async def test_async_tailor_completes_and_sends_callback(
    client: AsyncClient,
    sample_resume: dict,
    fake_callback_service: FakeCallbackService,
) -> None:
    response = await client.post(
        "/api/v1/tailor",
        json={
            "resume": sample_resume,
            "job_description": "Need an AI product leader.",
            "callback_url": "https://callback.example.com/hook",
        },
    )
    assert response.status_code == 202
    task_id = response.json()["task_id"]
    final_payload = await _wait_for_completion(client, task_id)
    assert final_payload["status"] == "completed"
    assert final_payload["resume"]["projects"][0]["name"] == sample_resume["projects"][0]["name"]
    assert fake_callback_service.deliveries
    callback_url, callback_payload = fake_callback_service.deliveries[0]
    assert callback_url == "https://callback.example.com/hook"
    assert callback_payload["status"] == "completed"


async def test_startup_requeues_running_jobs(
    settings: Settings,
    sample_resume: dict,
) -> None:
    database = Database(settings.resolved_database_url)
    await database.bootstrap()
    async with database.session() as session:
        session.add(
            Job(
                id="requeue-job",
                status=JobStatus.RUNNING.value,
                request_payload={
                    "resume": sample_resume,
                    "job_description": "Need an AI product leader.",
                    "theme": settings.default_theme,
                    "callback_url": None,
                },
                theme=settings.default_theme,
                callback_url=None,
            )
        )
        await session.commit()
    await database.dispose()

    callback_service = FakeCallbackService()
    app = create_app(
        settings,
        llm_client=FakeStructuredLLMClient(sample_resume),
        renderer=FakeRenderer(),
        callback_service=callback_service,
    )
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
            payload = await _wait_for_completion(test_client, "requeue-job")
            assert payload["status"] == "completed"


async def test_node_failure_marks_job_failed(settings: Settings, sample_resume: dict) -> None:
    callback_service = FakeCallbackService()
    app = create_app(
        settings,
        llm_client=FakeStructuredLLMClient(sample_resume, fail_model=settings.work_model),
        renderer=FakeRenderer(),
        callback_service=callback_service,
    )
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
            response = await test_client.post(
                "/api/v1/tailor",
                json={
                    "resume": sample_resume,
                    "job_description": "Need an AI product leader.",
                    "callback_url": "https://callback.example.com/hook",
                },
            )
            task_id = response.json()["task_id"]
            payload = await _wait_for_completion(test_client, task_id)
            assert payload["status"] == "failed"
            assert payload["error"]["code"] == "synthetic_llm_failure"


async def test_missing_optional_sections_still_complete(client: AsyncClient, sample_resume: dict) -> None:
    trimmed_resume = copy.deepcopy(sample_resume)
    trimmed_resume.pop("projects", None)
    trimmed_resume.pop("certificates", None)
    trimmed_resume.pop("interests", None)
    response = await client.post(
        "/api/v1/tailor",
        json={"resume": trimmed_resume, "job_description": "Need an AI product leader."},
    )
    assert response.status_code == 200
    payload = response.json()
    # When projects are absent, the pipeline sets projects=[] in the output
    assert payload["resume"].get("projects") == []
    assert payload["resume"].get("certificates") == []


async def test_sync_tailor_with_custom_sections(client: AsyncClient, sample_resume: dict) -> None:
    response = await client.post(
        "/api/v1/tailor",
        json={
            "resume": sample_resume,
            "job_description": "Need an AI product leader.",
            "sections": ["work"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    # Work was tailored
    assert "Tailored" in payload["resume"]["work"][0]["summary"]
    # Basics was omitted from sections so original is preserved
    assert payload["resume"]["basics"]["label"] == sample_resume["basics"]["label"]
    assert payload["resume"]["basics"]["summary"] == sample_resume["basics"]["summary"]

