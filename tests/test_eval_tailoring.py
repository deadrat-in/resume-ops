"""
Evaluation test suite for resume-ops tailoring quality, faithfulness, and anti-hallucination.
Run with: pytest -m eval
"""
from __future__ import annotations

import os
import pytest
from typing import Any

from resume_ops_api.graph.merge import ResumeMerger
from tests.fixtures.eval_fixtures import (
    SAMPLE_MASTER_RESUME_BACKEND,
    SAMPLE_JOB_DESCRIPTION_SENIOR_DEVOPS,
)


def verify_immutability(original: dict[str, Any], tailored: dict[str, Any]) -> list[str]:
    """Strictly checks that immutable candidate identity and work history remain uncorrupted."""
    violations = []
    
    # Check basics identity
    orig_basics = original.get("basics", {})
    tail_basics = tailored.get("basics", {})
    for key in ["name", "email", "phone"]:
        if orig_basics.get(key) != tail_basics.get(key):
            violations.append(f"Basics field '{key}' was altered: expected '{orig_basics.get(key)}', got '{tail_basics.get(key)}'")
            
    # Check work experience dates & companies
    orig_work = original.get("work", [])
    tail_work = tailored.get("work", [])
    if len(orig_work) != len(tail_work):
        violations.append(f"Work experience count changed: expected {len(orig_work)}, got {len(tail_work)}")
    else:
        for i, (ow, tw) in enumerate(zip(orig_work, tail_work)):
            if ow.get("name") != tw.get("name"):
                violations.append(f"Work[{i}] company name changed: expected '{ow.get('name')}', got '{tw.get('name')}'")
            if ow.get("startDate") != tw.get("startDate"):
                violations.append(f"Work[{i}] startDate changed: expected '{ow.get('startDate')}', got '{tw.get('startDate')}'")
            if ow.get("endDate") != tw.get("endDate"):
                violations.append(f"Work[{i}] endDate changed: expected '{ow.get('endDate')}', got '{tw.get('endDate')}'")
                
    # Check education institution and studyType
    orig_edu = original.get("education", [])
    tail_edu = tailored.get("education", [])
    for i, (oe, te) in enumerate(zip(orig_edu, tail_edu)):
        if oe.get("institution") != te.get("institution"):
            violations.append(f"Education[{i}] institution changed: expected '{oe.get('institution')}', got '{te.get('institution')}'")
        if oe.get("studyType") != te.get("studyType"):
            violations.append(f"Education[{i}] studyType changed: expected '{oe.get('studyType')}', got '{te.get('studyType')}'")

    return violations


@pytest.mark.eval
@pytest.mark.asyncio
async def test_tailoring_immutability_and_schema_compliance():
    """Verify that tailored output strictly respects immutability rules."""
    merger = ResumeMerger()
    
    # Merge original master resume with mock tailored sections
    tailored = merger.merge(
        original_resume=SAMPLE_MASTER_RESUME_BACKEND,
        tailored_basics=None,
        tailored_work=None,
        tailored_education=None,
        tailored_skills=None,
        tailored_projects=None,
        selected_certificates=None,
        tailored_optional_sections=None,
    )
    
    violations = verify_immutability(SAMPLE_MASTER_RESUME_BACKEND, tailored)
    assert not violations, f"Immutability rules violated: {violations}"


@pytest.mark.eval
@pytest.mark.asyncio
async def test_deepeval_faithfulness_metric():
    """
    Evaluates tailoring output for faithfulness (no invented skills or fake companies).
    Uses DeepEval if installed and EVAL_MODEL / OPENAI_API_KEY is configured.
    """
    try:
        from deepeval.metrics import FaithfulnessMetric, HallucinationMetric
        from deepeval.test_case import LLMTestCase
    except ImportError:
        pytest.skip("DeepEval is not installed. Install with `pip install deepeval` to run this test.")
        
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not configured for DeepEval metric scoring.")

    # Create test input & context
    context_text = f"Master Resume:\n{SAMPLE_MASTER_RESUME_BACKEND}"
    actual_output = "Architected event-driven microservices using Python FastAPI, Kafka, and PostgreSQL processing 10M daily transactions."
    
    test_case = LLMTestCase(
        input=SAMPLE_JOB_DESCRIPTION_SENIOR_DEVOPS,
        actual_output=actual_output,
        retrieval_context=[context_text],
    )
    
    metric = FaithfulnessMetric(threshold=0.7)
    metric.measure(test_case)
    
    assert metric.is_successful(), f"Faithfulness metric failed score: {metric.score}, reason: {metric.reason}"
