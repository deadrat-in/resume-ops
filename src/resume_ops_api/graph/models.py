from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator, ValidationInfo


class StrategyOutput(BaseModel):
    target_narrative: str
    priority_keywords: list[str] = Field(default_factory=list)
    section_rules: list[str] = Field(default_factory=list)
    red_lines: list[str] = Field(default_factory=list)


class StrategyAndBasicsOutput(BaseModel):
    target_narrative: str
    priority_keywords: list[str] = Field(default_factory=list)
    section_rules: list[str] = Field(default_factory=list)
    red_lines: list[str] = Field(default_factory=list)
    label: str | None = Field(default=None, description="Tailored professional title / headline matching the strategy.")
    summary: str | None = Field(
        default=None,
        description="Tailored professional summary paragraph matching the strategy. Keep it concise, writing a single punchy paragraph aiming for under 100 words."
    )


class WorkEntryTailoring(BaseModel):
    summary: str | None = None
    highlights: list[str] = Field(default_factory=list)


class WorkTailoringOutput(BaseModel):
    work: list[WorkEntryTailoring] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_work_count(self, info: ValidationInfo) -> "WorkTailoringOutput":
        context = info.context
        if context and "original_resume" in context:
            expected_count = len(context["original_resume"].get("work", []))
            if len(self.work) != expected_count:
                raise ValueError(
                    f"The number of work items returned ({len(self.work)}) must align 1:1 "
                    f"with the master resume ({expected_count})."
                )
        return self


class EducationEntryTailoring(BaseModel):
    courses: list[str] = Field(default_factory=list)


class EducationTailoringOutput(BaseModel):
    education: list[EducationEntryTailoring] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_education_count(self, info: ValidationInfo) -> "EducationTailoringOutput":
        context = info.context
        if context and "original_resume" in context:
            expected_count = len(context["original_resume"].get("education", []))
            if len(self.education) != expected_count:
                raise ValueError(
                    f"The number of education items returned ({len(self.education)}) must align 1:1 "
                    f"with the master resume ({expected_count})."
                )
        return self


class SkillEntry(BaseModel):
    name: str = Field(..., description="The name of the skill category (e.g., Frontend Development).")
    keywords: list[str] = Field(
        default_factory=list,
        min_length=1,
        max_length=8,
        description="List of 3 to 8 keywords/technologies for this skill category."
    )


class SkillsTailoringOutput(BaseModel):
    skills: list[SkillEntry] = Field(
        default_factory=list,
        min_length=1,
        max_length=6,
        description="List of 4 to 6 skill categories tailored to the job description."
    )


class QualificationsTailoringOutput(BaseModel):
    skills: list[SkillEntry] = Field(
        default_factory=list,
        min_length=0,
        max_length=6,
        description="List of 4 to 6 skill categories tailored to the job description."
    )
    certificates: list[str] = Field(
        default_factory=list,
        description="List of relevant certificate names selected verbatim from the master resume."
    )
    education: list[EducationEntryTailoring] = Field(
        default_factory=list,
        description="Tailored education courses aligned 1:1 with education entries in the master resume."
    )

    @model_validator(mode="after")
    def validate_qualifications(self, info: ValidationInfo) -> "QualificationsTailoringOutput":
        context = info.context
        if context and "original_resume" in context:
            if self.education:
                expected_edu_count = len(context["original_resume"].get("education", []))
                if len(self.education) != expected_edu_count:
                    raise ValueError(
                        f"The number of education items returned ({len(self.education)}) must align 1:1 "
                        f"with the master resume ({expected_edu_count})."
                    )
            if self.certificates:
                original_certs = {
                    c.get("name", "").strip().lower()
                    for c in context["original_resume"].get("certificates", [])
                    if isinstance(c, dict) and c.get("name")
                }
                if original_certs:
                    for cert in self.certificates:
                        if cert.strip().lower() not in original_certs:
                            raise ValueError(
                                f"Certificate '{cert}' does not exist in the master resume. "
                                f"Allowed certificates: {', '.join(sorted(original_certs))}"
                            )
        return self


class ProjectEntryTailoring(BaseModel):
    name: str = Field(..., description="The name of the project, matching the master resume verbatim.")
    description: str | None = Field(default=None, description="Tailored description of the project.")
    highlights: list[str] | None = Field(
        default=None,
        max_length=3,
        description="At most 3 key highlights or accomplishments for this project."
    )
    keywords: list[str] = Field(
        default_factory=list,
        max_length=6,
        description="At most 6 relevant technologies/keywords used in this project."
    )


class ProjectsTailoringOutput(BaseModel):
    projects: list[ProjectEntryTailoring] = Field(
        default_factory=list,
        max_length=4,
        description="List of at most 4 tailored projects that are most relevant to the target job description."
    )

    @model_validator(mode="after")
    def validate_project_names(self, info: ValidationInfo) -> "ProjectsTailoringOutput":
        context = info.context
        if context and "original_resume" in context:
            original_names = {
                p.get("name", "").strip().lower()
                for p in context["original_resume"].get("projects", [])
                if p.get("name")
            }
            for project in self.projects:
                if project.name.strip().lower() not in original_names:
                    raise ValueError(
                        f"Project name '{project.name}' does not match any project name in the master resume verbatim. "
                        f"Allowed project names: {', '.join(sorted(original_names))}"
                    )
        return self


class CertificatesSelectionOutput(BaseModel):
    certificates: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_certificate_names(self, info: ValidationInfo) -> "CertificatesSelectionOutput":
        context = info.context
        if context and "original_resume" in context:
            original_certs = {
                c.get("name", "").strip().lower()
                for c in context["original_resume"].get("certificates", [])
                if isinstance(c, dict) and c.get("name")
            }
            for cert in self.certificates:
                if cert.strip().lower() not in original_certs:
                    raise ValueError(
                        f"Certificate '{cert}' does not exist in the master resume. "
                        f"Allowed certificates: {', '.join(sorted(original_certs))}"
                    )
        return self


class InterestTailoring(BaseModel):
    name: str
    keywords: list[str] = Field(default_factory=list)


class OptionalSectionsOutput(BaseModel):
    interests: list[InterestTailoring] = Field(default_factory=list)


class BasicsTailoringOutput(BaseModel):
    label: str | None = Field(default=None, description="Tailored professional title / headline matching the strategy.")
    summary: str | None = Field(
        default=None,
        description="Tailored professional summary paragraph matching the strategy. Keep it concise, writing a single punchy paragraph aiming for under 100 words."
    )


class TailorResult(BaseModel):
    resume: dict[str, Any]
    pdf_path: str
    pdf_base64: str
    theme: str
    plain_text: str
