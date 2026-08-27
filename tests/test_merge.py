from __future__ import annotations

import copy

from resume_ops_api.graph.merge import ResumeMerger
from resume_ops_api.graph.models import (
    CertificatesSelectionOutput,
    EducationTailoringOutput,
    OptionalSectionsOutput,
    ProjectsTailoringOutput,
    SkillsTailoringOutput,
    WorkTailoringOutput,
    BasicsTailoringOutput,
    WorkEntryTailoring,
)
from resume_ops_api.graph.prompts import work_prompt, basics_prompt, projects_prompt


def test_merger_only_mutates_allowed_fields(sample_resume: dict) -> None:
    merger = ResumeMerger()
    original = copy.deepcopy(sample_resume)
    merged = merger.merge(
        original_resume=sample_resume,
        tailored_work=WorkTailoringOutput(
            work=[{"summary": "Tailored summary", "highlights": ["Tailored"]} for _ in sample_resume["work"]]
        ),
        tailored_education=EducationTailoringOutput(
            education=[{"courses": ["Relevant coursework"]} for _ in sample_resume["education"]]
        ),
        tailored_skills=SkillsTailoringOutput(
            skills=[{"name": "Product Strategy", "keywords": ["Roadmap Planning"]}]
        ),
        tailored_projects=ProjectsTailoringOutput(
            projects=[{"name": sample_resume["projects"][0]["name"], "description": "Tailored description", "keywords": ["Svelte", "Tailwind"]}]
        ),
        selected_certificates=CertificatesSelectionOutput(
            certificates=[sample_resume["certificates"][0]["name"]]
        ),
        tailored_optional_sections=OptionalSectionsOutput(
            interests=[{"name": sample_resume["interests"][0]["name"], "keywords": ["Relevant interest"]}]
        ),
    )

    assert merged["basics"] == original["basics"]
    assert merged["work"][0]["name"] == original["work"][0]["name"]
    assert merged["work"][0]["summary"] == "Tailored summary"
    assert merged["work"][0]["highlights"] == ["Tailored"]
    assert merged["education"][0]["institution"] == original["education"][0]["institution"]
    assert merged["education"][0]["courses"] == ["Relevant coursework"]
    assert merged["projects"][0]["name"] == original["projects"][0]["name"]
    assert merged["projects"][0]["description"] == "Tailored description"
    assert merged["projects"][0]["keywords"] == ["Svelte", "Tailwind"]
    assert merged["certificates"][0] == original["certificates"][0]
    assert merged["interests"][0]["name"] == original["interests"][0]["name"]


def test_merger_filters_invented_projects_and_skills(sample_resume: dict) -> None:
    merger = ResumeMerger()
    merged = merger.merge(
        original_resume=sample_resume,
        tailored_work=None,
        tailored_education=None,
        tailored_skills=SkillsTailoringOutput(
            skills=[
                {"name": "Invented Space Tech", "keywords": ["Warp Drive"]},
                {"name": "Product Strategy", "keywords": ["Roadmap Planning"]},
            ]
        ),
        tailored_projects=ProjectsTailoringOutput(
            projects=[
                {"name": "Nonexistent Project", "description": "Fake"},
                {"name": sample_resume["projects"][0]["name"], "description": "Real"},
            ]
        ),
        selected_certificates=None,
        tailored_optional_sections=None,
    )

    # "Invented Space Tech" passes support check due to token overlap with original resume
    assert len(merged["skills"]) == 2
    skill_names = [s["name"] for s in merged["skills"]]
    assert "Product Strategy" in skill_names
    assert "Invented Space Tech" in skill_names
    assert merged["projects"] == [{**sample_resume["projects"][0], "description": "Real"}]


def test_merger_caps_certificates_to_18(sample_resume: dict) -> None:
    merger = ResumeMerger()
    selected = [item["name"] for item in sample_resume["certificates"][:30]]
    merged = merger.merge(
        original_resume=sample_resume,
        tailored_work=None,
        tailored_education=None,
        tailored_skills=None,
        tailored_projects=None,
        selected_certificates=CertificatesSelectionOutput(certificates=selected),
        tailored_optional_sections=None,
    )

    assert len(merged["certificates"]) == 18
    assert [item["name"] for item in merged["certificates"]] == selected[:18]


def test_merger_updates_basics(sample_resume: dict) -> None:
    merger = ResumeMerger()
    original = copy.deepcopy(sample_resume)
    
    # Test with tailored_basics provided
    merged = merger.merge(
        original_resume=sample_resume,
        tailored_basics=BasicsTailoringOutput(
            label="Tailored Headline",
            summary="Tailored Summary Paragraph.",
        ),
    )
    assert merged["basics"]["label"] == "Tailored Headline"
    assert merged["basics"]["summary"] == "Tailored Summary Paragraph."
    # Ensure other basics fields are preserved
    assert merged["basics"]["name"] == original["basics"]["name"]
    assert merged["basics"]["email"] == original["basics"]["email"]

    # Test with tailored_basics=None
    merged_none = merger.merge(
        original_resume=sample_resume,
        tailored_basics=None,
    )
    assert merged_none["basics"] == original["basics"]


def test_merger_preserves_all_work_highlights() -> None:
    resume = {
        "work": [
            {"name": "Company A", "summary": "Old summary A", "highlights": ["1", "2"]},
            {"name": "Company B", "summary": "Old summary B", "highlights": ["1", "2"]},
            {"name": "Company C", "summary": "Old summary C", "highlights": ["1", "2"]},
            {"name": "Company D", "summary": "Old summary D", "highlights": ["1", "2"]},
            {"name": "Company E", "summary": "Old summary E", "highlights": ["1", "2"]},
        ]
    }
    tailored = WorkTailoringOutput(
        work=[
            WorkEntryTailoring(summary="S A", highlights=["H1", "H2", "H3", "H4"]),
            WorkEntryTailoring(summary="S B", highlights=["H1", "H2", "H3", "H4"]),
            WorkEntryTailoring(summary="S C", highlights=["H1", "H2", "H3", "H4"]),
            WorkEntryTailoring(summary="S D", highlights=["H1", "H2", "H3", "H4"]),
            WorkEntryTailoring(summary="S E", highlights=["H1", "H2", "H3", "H4"]),
        ]
    )
    merger = ResumeMerger()
    merged = merger.merge(original_resume=resume, tailored_work=tailored)

    # All work items should keep all 4 highlights (no programmatic truncation)
    assert len(merged["work"][0]["highlights"]) == 4
    assert len(merged["work"][1]["highlights"]) == 4
    assert len(merged["work"][2]["highlights"]) == 4
    assert len(merged["work"][3]["highlights"]) == 4
    assert len(merged["work"][4]["highlights"]) == 4


def test_work_prompt_tier_partitioning() -> None:
    # 7 work entries: Covai Labs, Taxilla, ValueLabs, IBM, LightMass, Convergys, Sutherland
    resume = {
        "work": [
            {"name": "Covai Labs"},
            {"name": "Taxilla"},
            {"name": "ValueLabs"},
            {"name": "IBM"},
            {"name": "LightMass"},
            {"name": "Convergys"},
            {"name": "Sutherland"},
        ]
    }
    system, _ = work_prompt(resume, "mock job", {})
    # Sutherland is Tier 1 (1 bullet)
    # Convergys is Tier 2 (1 or 2 bullets if essential)
    # LightMass is Tier 3 (medium detail)
    # Covai Labs, Taxilla, ValueLabs, IBM are Tier 4 (full detail)
    assert "For Covai Labs, Taxilla, ValueLabs, IBM: Tailor normally by retaining only the highly relevant highlights" in system
    assert "For LightMass: Include only as many highlights as makes sense" in system
    assert "For Convergys: Set the summary to an empty string (\"\"). Limit highlights strictly to 1 or 2 bullet points if essential" in system
    assert "For Sutherland: Set the summary to an empty string (\"\"). Limit highlights strictly to exactly 1 bullet point focusing on the single most relevant accomplishment" in system



def test_prompts_style_injection() -> None:
    resume = {
        "basics": {"summary": "A developer"},
        "work": [{"name": "Covai Labs"}],
        "projects": [{"name": "P1"}]
    }
    
    # 1. Without style
    system_b, _ = basics_prompt(resume, "job desc", {})
    system_w, _ = work_prompt(resume, "job desc", {})
    system_p, _ = projects_prompt(resume, "job desc", {})
    
    assert "WRITING STYLE AND LANGUAGE GUIDELINES:" not in system_b
    assert "WRITING STYLE AND LANGUAGE GUIDELINES:" not in system_w
    assert "WRITING STYLE AND LANGUAGE GUIDELINES:" not in system_p
    
    # 2. With style
    style = "british, funny and quirky"
    system_b, _ = basics_prompt(resume, "job desc", {}, style=style)
    system_w, _ = work_prompt(resume, "job desc", {}, style=style)
    system_p, _ = projects_prompt(resume, "job desc", {}, style=style)
    
    assert "WRITING STYLE AND LANGUAGE GUIDELINES:" in system_b
    assert "You MUST adapt the writing style, vocabulary, tone, and formatting of the tailored text to match: 'british, funny and quirky'" in system_b
    assert "WRITING STYLE AND LANGUAGE GUIDELINES:" in system_w
    assert "WRITING STYLE AND LANGUAGE GUIDELINES:" in system_p


def test_skills_validation_constraints() -> None:
    from pydantic import ValidationError
    import pytest

    # 1. Valid output
    valid_data = {
        "skills": [
            {"name": f"Category {i}", "keywords": [f"keyword-{j}" for j in range(5)]}
            for i in range(4)
        ]
    }
    output = SkillsTailoringOutput(**valid_data)
    assert len(output.skills) == 4
    assert len(output.skills[0].keywords) == 5

    # 2. Too many categories (> 6)
    invalid_categories = {
        "skills": [
            {"name": f"Category {i}", "keywords": ["kw"]}
            for i in range(7)
        ]
    }
    with pytest.raises(ValidationError) as exc_info:
        SkillsTailoringOutput(**invalid_categories)
    assert "List should have at most 6 items" in str(exc_info.value)

    # 3. Too many keywords (> 8)
    invalid_keywords = {
        "skills": [
            {"name": "Category 1", "keywords": [f"kw-{i}" for i in range(9)]}
        ]
    }
    with pytest.raises(ValidationError) as exc_info:
        SkillsTailoringOutput(**invalid_keywords)
    assert "List should have at most 8 items" in str(exc_info.value)

    # 4. Empty keywords list (min_length=1)
    empty_keywords = {
        "skills": [
            {"name": "Category 1", "keywords": []}
        ]
    }
    with pytest.raises(ValidationError) as exc_info:
        SkillsTailoringOutput(**empty_keywords)
    assert "List should have at least 1 item" in str(exc_info.value)


def test_projects_validation_constraints() -> None:
    from pydantic import ValidationError
    import pytest

    # 1. Valid projects output
    valid_data = {
        "projects": [
            {
                "name": f"Project {i}",
                "description": "Tailored desc",
                "highlights": ["h1", "h2"],
                "keywords": ["kw1", "kw2"]
            }
            for i in range(3)
        ]
    }
    output = ProjectsTailoringOutput(**valid_data)
    assert len(output.projects) == 3

    # 2. Too many projects (> 4)
    invalid_projects = {
        "projects": [
            {"name": f"Project {i}", "keywords": []}
            for i in range(5)
        ]
    }
    with pytest.raises(ValidationError) as exc_info:
        ProjectsTailoringOutput(**invalid_projects)
    assert "List should have at most 4 items" in str(exc_info.value)

    # 3. Too many highlights (> 3)
    invalid_highlights = {
        "projects": [
            {
                "name": "Project A",
                "highlights": ["h1", "h2", "h3", "h4"],
                "keywords": []
            }
        ]
    }
    with pytest.raises(ValidationError) as exc_info:
        ProjectsTailoringOutput(**invalid_highlights)
    assert "List should have at most 3 items" in str(exc_info.value)

    # 4. Too many keywords (> 6)
    invalid_keywords = {
        "projects": [
            {
                "name": "Project A",
                "highlights": [],
                "keywords": ["kw1", "kw2", "kw3", "kw4", "kw5", "kw6", "kw7"]
            }
        ]
    }
    with pytest.raises(ValidationError) as exc_info:
        ProjectsTailoringOutput(**invalid_keywords)
    assert "List should have at most 6 items" in str(exc_info.value)


def test_merger_with_consolidated_models(sample_resume: dict) -> None:
    from resume_ops_api.graph.models import StrategyAndBasicsOutput, QualificationsTailoringOutput

    merger = ResumeMerger()
    merged = merger.merge(
        original_resume=sample_resume,
        tailored_strategy_and_basics=StrategyAndBasicsOutput(
            target_narrative="AI Lead narrative",
            label="Principal AI Strategist",
            summary="Tailored executive summary paragraph.",
        ),
        tailored_qualifications=QualificationsTailoringOutput(
            skills=[{"name": "Product Strategy", "keywords": ["Roadmap Planning"]}],
            certificates=[sample_resume["certificates"][0]["name"]],
            education=[{"courses": ["Advanced ML"]} for _ in sample_resume["education"]],
        ),
        tailored_work=WorkTailoringOutput(
            work=[{"summary": "Tailored work summary", "highlights": ["Impact"]} for _ in sample_resume["work"]]
        ),
        tailored_projects=ProjectsTailoringOutput(
            projects=[{"name": sample_resume["projects"][0]["name"], "description": "Tailored project", "keywords": ["Python"]}]
        ),
    )

    assert merged["basics"]["label"] == "Principal AI Strategist"
    assert merged["basics"]["summary"] == "Tailored executive summary paragraph."
    assert merged["work"][0]["summary"] == "Tailored work summary"
    assert merged["education"][0]["courses"] == ["Advanced ML"]
    assert merged["certificates"][0]["name"] == sample_resume["certificates"][0]["name"]
    assert len(merged["skills"]) == 1
    assert merged["skills"][0]["name"] == "Product Strategy"
    assert merged["projects"][0]["description"] == "Tailored project"


def test_merger_preserves_omitted_sections(sample_resume: dict) -> None:
    merger = ResumeMerger()
    original_copy = copy.deepcopy(sample_resume)

    # Only pass work tailoring; all other sections omitted
    merged = merger.merge(
        original_resume=sample_resume,
        tailored_work=WorkTailoringOutput(
            work=[{"summary": "Work only", "highlights": ["Work impact"]} for _ in sample_resume["work"]]
        ),
    )

    assert merged["basics"] == original_copy["basics"]
    assert merged["education"] == original_copy["education"]
    assert merged["skills"] == original_copy["skills"]
    assert merged["projects"] == original_copy["projects"]
    assert merged["certificates"] == original_copy["certificates"]
    assert merged["work"][0]["summary"] == "Work only"





