from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from resume_ops_api.graph.models import (
    CertificatesSelectionOutput,
    EducationTailoringOutput,
    OptionalSectionsOutput,
    ProjectsTailoringOutput,
    QualificationsTailoringOutput,
    SkillsTailoringOutput,
    StrategyAndBasicsOutput,
    StrategyOutput,
    WorkTailoringOutput,
    BasicsTailoringOutput,
)


class ResumeGraphState(TypedDict, total=False):
    original_resume: dict[str, Any]
    job_description: str
    theme: str
    job_id: str
    output_dir: Path
    sections: list[str]
    strategy: StrategyOutput
    strategy_and_basics: StrategyAndBasicsOutput
    tailored_basics: BasicsTailoringOutput
    tailored_work: WorkTailoringOutput
    tailored_education: EducationTailoringOutput
    tailored_skills: SkillsTailoringOutput
    tailored_qualifications: QualificationsTailoringOutput
    tailored_projects: ProjectsTailoringOutput
    selected_certificates: CertificatesSelectionOutput
    tailored_optional_sections: OptionalSectionsOutput
    final_resume: dict[str, Any]
    pdf_path: str

