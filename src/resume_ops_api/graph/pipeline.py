from __future__ import annotations

from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph

from resume_ops_api.core.exceptions import AppError
from resume_ops_api.graph import prompts
from resume_ops_api.graph.merge import ResumeMerger
from resume_ops_api.graph.models import (
    ProjectsTailoringOutput,
    QualificationsTailoringOutput,
    StrategyAndBasicsOutput,
    StrategyOutput,
    WorkTailoringOutput,
    BasicsTailoringOutput,
)
from resume_ops_api.graph.state import ResumeGraphState
from resume_ops_api.services.llm import StructuredLLMClient
from resume_ops_api.services.renderer import ResumeRenderer
from resume_ops_api.services.schema import ResumeSchemaValidator

DEFAULT_SECTIONS = ["basics", "work", "skills", "projects", "education", "certificates"]


class ResumeGraph:
    def __init__(
        self,
        *,
        llm_client: StructuredLLMClient,
        merger: ResumeMerger,
        renderer: ResumeRenderer,
        validator: ResumeSchemaValidator,
        strategy_and_basics_model: str | None = None,
        strategy_model: str | None = None,
        work_model: str | None = None,
        qualifications_model: str | None = None,
        education_model: str | None = None,
        skills_model: str | None = None,
        projects_model: str | None = None,
        certificates_model: str | None = None,
        optional_sections_model: str | None = None,
        basics_model: str | None = None,
        style: str | None = None,
        default_sections: list[str] | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.merger = merger
        self.renderer = renderer
        self.validator = validator
        self.strategy_and_basics_model = (
            strategy_and_basics_model
            or strategy_model
            or basics_model
            or "default"
        )
        self.work_model = work_model or "default"
        self.qualifications_model = (
            qualifications_model
            or skills_model
            or certificates_model
            or education_model
            or "default"
        )
        self.projects_model = projects_model or "default"
        self.style = style
        self.default_sections = default_sections or list(DEFAULT_SECTIONS)

        graph = StateGraph(ResumeGraphState)
        graph.add_node("strategy_and_basics", self.strategy_and_basics_node)
        graph.add_node("work_tailoring", self.work_node)
        graph.add_node("qualifications_tailoring", self.qualifications_node)
        graph.add_node("projects_tailoring", self.projects_node)
        graph.add_node("merge", self.merge_node)
        graph.add_node("render", self.render_node)

        graph.add_edge(START, "strategy_and_basics")
        # Fan-out: strategy_and_basics feeds all section nodes in parallel
        graph.add_edge("strategy_and_basics", "work_tailoring")
        graph.add_edge("strategy_and_basics", "qualifications_tailoring")
        graph.add_edge("strategy_and_basics", "projects_tailoring")
        # Fan-in: all section nodes feed into merge
        graph.add_edge("work_tailoring", "merge")
        graph.add_edge("qualifications_tailoring", "merge")
        graph.add_edge("projects_tailoring", "merge")
        graph.add_edge("merge", "render")
        graph.add_edge("render", END)
        self._compiled = graph.compile()

    def _resolve_active_sections(self, state: ResumeGraphState) -> list[str]:
        return state.get("sections") or self.default_sections

    async def run(self, state: ResumeGraphState) -> ResumeGraphState:
        return await self._compiled.ainvoke(state)

    async def strategy_and_basics_node(self, state: ResumeGraphState) -> dict[str, Any]:
        active_sections = self._resolve_active_sections(state)
        tailor_basics = "basics" in active_sections
        system, user = prompts.strategy_and_basics_prompt(
            resume=state["original_resume"],
            job_description=state["job_description"],
            style=self.style,
            tailor_basics=tailor_basics,
        )
        output = await self.llm_client.generate_structured(
            model=self.strategy_and_basics_model,
            system_prompt=system,
            user_prompt=user,
            response_model=StrategyAndBasicsOutput,
            session_id=state.get("job_id"),
        )
        if not tailor_basics:
            output = output.model_copy(update={"label": None, "summary": None})

        strategy = StrategyOutput(
            target_narrative=output.target_narrative,
            priority_keywords=output.priority_keywords,
            section_rules=output.section_rules,
            red_lines=output.red_lines,
        )
        res: dict[str, Any] = {
            "strategy_and_basics": output,
            "strategy": strategy,
        }
        if tailor_basics and (output.label is not None or output.summary is not None):
            res["tailored_basics"] = BasicsTailoringOutput(label=output.label, summary=output.summary)
        return res

    async def work_node(self, state: ResumeGraphState) -> dict[str, Any]:
        active_sections = self._resolve_active_sections(state)
        if "work" not in active_sections:
            return {}
        if not state["original_resume"].get("work"):
            return {"tailored_work": WorkTailoringOutput(work=[])}
        strategy_dict = state["strategy"].model_dump()
        system, user = prompts.work_prompt(
            resume=state["original_resume"],
            job_description=state["job_description"],
            strategy=strategy_dict,
            style=self.style,
        )
        output = await self.llm_client.generate_structured(
            model=self.work_model,
            system_prompt=system,
            user_prompt=user,
            response_model=WorkTailoringOutput,
            session_id=state.get("job_id"),
            validation_context={"original_resume": state["original_resume"]},
        )
        return {"tailored_work": output}

    async def qualifications_node(self, state: ResumeGraphState) -> dict[str, Any]:
        active_sections = self._resolve_active_sections(state)
        qual_sections = {"skills", "certificates", "education"} & set(active_sections)
        if not qual_sections:
            return {}
        
        has_any_data = any(
            state["original_resume"].get(k)
            for k in ("skills", "certificates", "education")
            if k in qual_sections
        )
        if not has_any_data:
            return {"tailored_qualifications": QualificationsTailoringOutput()}

        strategy_dict = state["strategy"].model_dump()
        system, user = prompts.qualifications_prompt(
            resume=state["original_resume"],
            job_description=state["job_description"],
            strategy=strategy_dict,
            active_sections=list(qual_sections),
        )
        output = await self.llm_client.generate_structured(
            model=self.qualifications_model,
            system_prompt=system,
            user_prompt=user,
            response_model=QualificationsTailoringOutput,
            session_id=state.get("job_id"),
            validation_context={"original_resume": state["original_resume"]},
        )
        return {"tailored_qualifications": output}

    async def projects_node(self, state: ResumeGraphState) -> dict[str, Any]:
        active_sections = self._resolve_active_sections(state)
        if "projects" not in active_sections:
            return {}
        if not state["original_resume"].get("projects"):
            return {"tailored_projects": ProjectsTailoringOutput(projects=[])}
        strategy_dict = state["strategy"].model_dump()
        system, user = prompts.projects_prompt(
            resume=state["original_resume"],
            job_description=state["job_description"],
            strategy=strategy_dict,
            style=self.style,
        )
        output = await self.llm_client.generate_structured(
            model=self.projects_model,
            system_prompt=system,
            user_prompt=user,
            response_model=ProjectsTailoringOutput,
            session_id=state.get("job_id"),
            validation_context={"original_resume": state["original_resume"]},
        )
        return {"tailored_projects": output}

    async def merge_node(self, state: ResumeGraphState) -> dict[str, dict]:
        final_resume = self.merger.merge(
            original_resume=state["original_resume"],
            tailored_strategy_and_basics=state.get("strategy_and_basics"),
            tailored_qualifications=state.get("tailored_qualifications"),
            tailored_basics=state.get("tailored_basics"),
            tailored_work=state.get("tailored_work"),
            tailored_education=state.get("tailored_education"),
            tailored_skills=state.get("tailored_skills"),
            tailored_projects=state.get("tailored_projects"),
            selected_certificates=state.get("selected_certificates"),
            tailored_optional_sections=state.get("tailored_optional_sections"),
        )
        self.validator.validate(final_resume, context="tailored resume", status_code=500, strict=False)
        return {"final_resume": final_resume}

    async def render_node(self, state: ResumeGraphState) -> dict[str, str]:
        output_dir: Path = state["output_dir"]
        if not state.get("final_resume"):
            raise AppError("Cannot render before merge completes.", code="render_without_resume", status_code=500)
        pdf_path = await self.renderer.render(
            resume=state["final_resume"],
            theme=state["theme"],
            output_dir=output_dir,
        )
        return {"pdf_path": str(pdf_path)}
