from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from resume_ops_api.api.app import create_app
from resume_ops_api.core.config import Settings
from resume_ops_api.core.exceptions import AppError


class FakeStructuredLLMClient:
    def __init__(self, resume: dict[str, Any], *, fail_model: str | None = None) -> None:
        self.resume = resume
        self.fail_model = fail_model

    async def generate_structured(self, *, model: str, system_prompt: str, user_prompt: str, response_model: type, **kwargs):
        if self.fail_model == model:
            raise AppError("Synthetic LLM failure.", code="synthetic_llm_failure", status_code=502)
        if response_model.__name__ == "StrategyOutput":
            return response_model(
                target_narrative="Match product and platform leadership roles.",
                priority_keywords=["Product Strategy", "AI", "Platform"],
                section_rules=["Preserve protected fields."],
                red_lines=["Do not invent facts."],
            )
        if response_model.__name__ == "StrategyAndBasicsOutput":
            return response_model(
                target_narrative="Match product and platform leadership roles.",
                priority_keywords=["Product Strategy", "AI", "Platform"],
                section_rules=["Preserve protected fields."],
                red_lines=["Do not invent facts."],
                label="Tailored professional label / headline",
                summary="Tailored professional summary matching the strategy.",
            )
        if response_model.__name__ == "QualificationsTailoringOutput":
            skills = [
                {
                    "name": "Product Strategy",
                    "keywords": ["Roadmap Planning", "Go-to-Market (GTM)"],
                },
                {
                    "name": "Invented Space Tech",
                    "keywords": ["Warp Drive"],
                },
            ]
            certificates = [item["name"] for item in self.resume.get("certificates", [])[:2]]
            education = [
                {"courses": [f"{item.get('studyType', 'Degree')} coursework aligned to target role"]}
                for item in self.resume.get("education", [])
            ]
            return response_model(
                skills=skills,
                certificates=certificates,
                education=education,
            )
        if response_model.__name__ == "BasicsTailoringOutput":
            return response_model(
                label="Tailored professional label / headline",
                summary="Tailored professional summary matching the strategy.",
            )
        if response_model.__name__ == "WorkTailoringOutput":
            return response_model(
                work=[
                    {
                        "summary": f"Tailored summary for {item['name']}",
                        "highlights": [f"Tailored impact for {item['name']}"],
                    }
                    for item in self.resume.get("work", [])
                ]
            )
        if response_model.__name__ == "EducationTailoringOutput":
            return response_model(
                education=[
                    {"courses": [f"{item['studyType']} coursework aligned to target role"]} for item in self.resume.get("education", [])
                ]
            )
        if response_model.__name__ == "SkillsTailoringOutput":
            return response_model(
                skills=[
                    {
                        "name": "Product Strategy",
                        "keywords": ["Roadmap Planning", "Go-to-Market (GTM)"],
                    },
                    {
                        "name": "Invented Space Tech",
                        "keywords": ["Warp Drive"],
                    },
                ]
            )
        if response_model.__name__ == "ProjectsTailoringOutput":
            projects = self.resume.get("projects", [])[:2]
            return response_model(
                projects=[
                    {
                        "name": project["name"],
                        "description": f"Tailored: {project.get('description', project['name'])}",
                        "highlights": ["Tailored project evidence"],
                    }
                    for project in projects
                ]
            )
        if response_model.__name__ == "CertificatesSelectionOutput":
            return response_model(certificates=[item["name"] for item in self.resume.get("certificates", [])[:2]])
        if response_model.__name__ == "OptionalSectionsOutput":
            return response_model(
                interests=[
                    {
                        "name": item["name"],
                        "keywords": [f"Relevant: {item['name']}"],
                    }
                    for item in self.resume.get("interests", [])
                ]
            )
        raise AssertionError(f"Unsupported response model: {response_model.__name__}")


class FakeRenderer:
    async def render(self, *, resume: dict, theme: str, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = output_dir / "output.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n% Fake test PDF\n")
        return pdf_path


class FakeCallbackService:
    def __init__(self) -> None:
        self.deliveries: list[tuple[str, dict[str, Any]]] = []

    async def deliver(self, callback_url: str, payload: dict[str, Any]) -> None:
        self.deliveries.append((callback_url, payload))


@pytest.fixture
def sample_resume() -> dict[str, Any]:
    return json.loads(Path(".local/master-resume.json").read_text(encoding="utf-8"))


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        allowed_themes=["jsonresume-theme-stackoverflow", "jsonresume-theme-even"],
        default_theme="jsonresume-theme-stackoverflow",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'resume_ops.db'}",
        default_model="openai/gpt-4o-mini",
    )


@pytest.fixture
def fake_callback_service() -> FakeCallbackService:
    return FakeCallbackService()


@pytest_asyncio.fixture
async def client(
    settings: Settings,
    sample_resume: dict[str, Any],
    fake_callback_service: FakeCallbackService,
) -> AsyncClient:
    app = create_app(
        settings,
        llm_client=FakeStructuredLLMClient(sample_resume),
        renderer=FakeRenderer(),
        callback_service=fake_callback_service,
    )
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
            yield test_client
