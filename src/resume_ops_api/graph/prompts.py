from __future__ import annotations

import json
from typing import Any


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=True, separators=(",", ":"))


def _apply_style(system: str, style: str | None) -> str:
    if style and style.strip():
        system += (
            f"\n\nWRITING STYLE AND LANGUAGE GUIDELINES:\n"
            f"You MUST adapt the writing style, vocabulary, tone, and formatting of the tailored text to match: '{style.strip()}'.\n"
            f"CRITICAL RULES FOR STYLE:\n"
            f"1. Apply the style dynamically in how the sentences are phrased and structured.\n"
            f"2. DO NOT insert literal labels or self-descriptions of the style. For example, if the style is 'cheerful', do NOT start the summary with 'As a cheerful product manager...'; instead, write the accomplishments with energetic, positive, and enthusiastic phrasing naturally.\n"
            f"3. If the style requests a regional language variant (e.g. 'australian english', 'british english'), use the correct spelling conventions (e.g. 'optimise', 'programme') and localized professional terminology.\n"
            f"4. If the style requests length properties (e.g. 'concise', 'verbose'), follow them strictly while adhering to the section constraints."
        )
    return system


def strategy_and_basics_prompt(
    resume: dict[str, Any],
    job_description: str,
    style: str | None = None,
    tailor_basics: bool = True,
) -> tuple[str, str]:
    basics_rules = ""
    if tailor_basics:
        basics_rules = (
            "\n\nBASICS SECTION (HEADLINE & SUMMARY) RULES:\n"
            "- Tailor only the professional label (headline/title) and the main summary paragraph of the basics section.\n"
            "- Write a single, concise professional summary paragraph aiming for under 100 words (3-4 sentences).\n"
            "- CRITICAL: The tailored summary MUST explicitly retain or include the mention of "
            "candidate education if it is high signalling (e.g. MBA from IIM Trichy).\n"
            "- Do not invent unsupported responsibilities or achievements.\n"
            "- Return label and summary fields matching the target narrative."
        )
    else:
        basics_rules = (
            "\n\nBASICS SECTION:\n"
            "- Basics tailoring is disabled. Return label=null and summary=null."
        )

    system = (
        "You are tailoring a resume without inventing facts. "
        "Formulate a coherent tailoring strategy for the candidate matching the target job description.\n"
        "Return structured JSON with keys: target_narrative, priority_keywords, section_rules, red_lines, label, and summary."
        f"{basics_rules}"
    )
    system = _apply_style(system, style)
    user = f"Job description:\n{job_description}\n\nMaster resume:\n{_json(resume)}"
    return system, user


def strategy_prompt(resume: dict[str, Any], job_description: str) -> tuple[str, str]:
    system = (
        "You are tailoring a resume without inventing facts. "
        "Return only structured JSON matching the following structure:\n"
        "{\n"
        "  \"target_narrative\": \"string\",\n"
        "  \"priority_keywords\": [\"string\"],\n"
        "  \"section_rules\": [\"string\"],\n"
        "  \"red_lines\": [\"string\"]\n"
        "}\n"
        "Use the full master resume for context to determine the tailoring strategy."
    )
    user = f"Job description:\n{job_description}\n\nMaster resume:\n{_json(resume)}"
    return system, user


def work_prompt(
    resume: dict[str, Any],
    job_description: str,
    strategy: dict[str, Any],
    style: str | None = None,
) -> tuple[str, str]:
    work_items = resume.get("work", [])
    N = len(work_items)
    
    rules = []
    if N <= 2:
        rules.append("- Tailor the highlights normally by retaining only the highly relevant accomplishments and eliminating unrelated ones.")
    elif N == 3:
        rules.append(
            f"- For {work_items[0].get('name', 'Item 1')} and {work_items[1].get('name', 'Item 2')}: Tailor normally by retaining only the highly relevant accomplishments and eliminating unrelated ones.\n"
            f"- For {work_items[2].get('name', 'Item 3')}: Set the summary to an empty string (\"\"). Limit highlights strictly to 1 or 2 bullet points, keeping only the most relevant accomplishments and discarding the rest."
        )
    else:
        # N >= 4: partition into 4 tiers:
        # T1 (oldest 20%): max(1, round(N * 0.2)) items
        # T2 (next 20%): max(1, round(N * 0.2)) items
        # T3 (next 20%): max(1, round(N * 0.2)) items
        # T4 (newest remaining items - top 40%)
        t1_size = max(1, round(N * 0.2))
        t2_size = max(1, round(N * 0.2))
        t3_size = max(1, round(N * 0.2))
        t4_size = N - t1_size - t2_size - t3_size
        
        t4_items = work_items[:t4_size]
        t3_items = work_items[t4_size : t4_size + t3_size]
        t2_items = work_items[t4_size + t3_size : t4_size + t3_size + t2_size]
        t1_items = work_items[t4_size + t3_size + t2_size :]
        
        t4_names = [w.get("name", f"Item {i+1}") for i, w in enumerate(t4_items)]
        t3_names = [w.get("name", f"Item {i+t4_size+1}") for i, w in enumerate(t3_items)]
        t2_names = [w.get("name", f"Item {i+t4_size+t3_size+1}") for i, w in enumerate(t2_items)]
        t1_names = [w.get("name", f"Item {i+t4_size+t3_size+t2_size+1}") for i, w in enumerate(t1_items)]
        
        rules.append(
            f"- For {', '.join(t4_names)}: Tailor normally by retaining only the highly relevant highlights and eliminating unrelated ones, maintaining detail/bullets for matching skills.\n"
            f"- For {', '.join(t3_names)}: Include only as many highlights as makes sense (medium detail), focusing strictly on relevant achievements and eliminating unrelated ones.\n"
            f"- For {', '.join(t2_names)}: Set the summary to an empty string (\"\"). Limit highlights strictly to 1 or 2 bullet points if essential, keeping only the most relevant accomplishments and discarding the rest.\n"
            f"- For {', '.join(t1_names)}: Set the summary to an empty string (\"\"). Limit highlights strictly to exactly 1 bullet point focusing on the single most relevant accomplishment, and discard all other points."
        )


    system = (
        "Tailor only the summary and highlights for each work item. "
        "Do not change company names, positions, dates, locations, urls, or order. "
        "Do not invent unsupported responsibilities or achievements. "
        "CRITICAL: The output 'work' list MUST align 1:1 in length and order with the input list. "
        "Return EXACTLY the same number of work entries in the same order. Do not skip or drop any items. "
        "Return structured JSON with this key: work (a list of objects with summary and highlights).\n\n"
        "HIGHLIGHTS COUNT AND DETAIL RULES:\n" + "\n".join(rules)
    )
    system = _apply_style(system, style)
    user = (
        f"Job description:\n{job_description}\n\n"
        f"Strategy:\n{_json(strategy)}\n\n"
        f"Target work section:\n{_json(resume.get('work', []))}"
    )
    return system, user


def qualifications_prompt(
    resume: dict[str, Any],
    job_description: str,
    strategy: dict[str, Any],
    active_sections: list[str] | None = None,
) -> tuple[str, str]:
    active = set(active_sections or ["skills", "certificates", "education"])
    sections_rules = []
    
    if "skills" in active:
        sections_rules.append(
            "- SKILLS: Tailor the skills section by regrouping and prioritizing existing evidence from the candidate's skills. "
            "Keep JSON Resume skill objects. Do not invent unsupported skills. "
            "Structure the output into a maximum of 6 (ideally 4 to 6) distinct, high-impact categories/names. "
            "Under each category, include between 3 and 8 keywords (or fewer if not enough evidence exists) "
            "representing the most relevant technologies, tools, or methodologies."
        )
    else:
        sections_rules.append("- SKILLS: Skills tailoring is disabled. Return skills as an empty list [].")

    if "certificates" in active:
        sections_rules.append(
            "- CERTIFICATES: Select only certificates from the candidate's certificates list that have a strong, direct mapping "
            "to the target role's priority keywords. Return a maximum of 18 (or fewer if not meeting strict relevance). "
            "Do not rewrite or invent certificate names; use existing certificate names verbatim."
        )
    else:
        sections_rules.append("- CERTIFICATES: Certificate selection is disabled. Return certificates as an empty list [].")

    if "education" in active:
        sections_rules.append(
            "- EDUCATION: Tailor only education courses. Preserve institution, degree, dates, scores, and other metadata exactly. "
            "If the input education entries do not contain a courses field or it is empty, synthesize/suggest a list of 3-5 "
            "highly relevant, high-signaling academic courses based on the area of study and target job description/strategy. "
            "The output education list MUST align 1:1 in length and order with input education entries."
        )
    else:
        sections_rules.append("- EDUCATION: Education tailoring is disabled. Return education as an empty list [].")

    system = (
        "Tailor candidate qualifications (skills, certificates, education) without inventing facts.\n\n"
        "SECTION RULES:\n" + "\n".join(sections_rules) + "\n\n"
        "Return structured JSON with keys: skills (list of objects with name and keywords), "
        "certificates (list of strings), and education (list of objects with courses list)."
    )

    target_qualifications = {
        "skills": resume.get("skills", []) if "skills" in active else [],
        "certificates": resume.get("certificates", []) if "certificates" in active else [],
        "education": resume.get("education", []) if "education" in active else [],
    }

    user = (
        f"Job description:\n{job_description}\n\n"
        f"Strategy:\n{_json(strategy)}\n\n"
        f"Target qualifications:\n{_json(target_qualifications)}"
    )
    return system, user


def education_prompt(resume: dict[str, Any], job_description: str, strategy: dict[str, Any]) -> tuple[str, str]:
    system = (
        "Tailor only education courses. Preserve institution, degree, dates, scores, and other metadata exactly. "
        "CRITICAL: If the input 'education' entries do not contain a 'courses' field, or if the 'courses' list is empty, "
        "you may synthesize/suggest a list of 3-5 highly relevant, high-signaling academic courses or subjects based on the "
        "area of study (e.g. Business Administration, Aeronautical Engineering) and the target job description/strategy "
        "to showcase matching knowledge. If 'courses' are already present, select or tailor the most relevant ones. "
        "CRITICAL: The output 'education' list MUST align 1:1 in length and order with the input list. "
        "Return EXACTLY the same number of education entries in the same order. Do not skip or drop any items. "
        "Return structured JSON with this key: education (a list of objects with courses list)."
    )
    user = (
        f"Job description:\n{job_description}\n\n"
        f"Strategy:\n{_json(strategy)}\n\n"
        f"Master resume for context:\n{_json(resume)}\n\n"
        f"Target education section:\n{_json(resume.get('education', []))}"
    )
    return system, user


def skills_prompt(resume: dict[str, Any], job_description: str, strategy: dict[str, Any]) -> tuple[str, str]:
    system = (
        "Tailor the skills section by regrouping and prioritizing existing evidence from the master resume. "
        "Keep JSON Resume skill objects. Do not invent unsupported skills. "
        "Structure the output into a maximum of 6 (ideally 4 to 6) distinct, high-impact categories/names. "
        "Under each category, include between 3 and 8 keywords (or fewer if not enough evidence exists in the master resume) "
        "representing the most relevant technologies, tools, or methodologies. "
        "Return structured JSON with this key: skills (a list of objects with name and keywords)."
    )
    user = (
        f"Job description:\n{job_description}\n\n"
        f"Strategy:\n{_json(strategy)}\n\n"
        f"Master resume:\n{_json(resume)}"
    )
    return system, user


def projects_prompt(
    resume: dict[str, Any],
    job_description: str,
    strategy: dict[str, Any],
    style: str | None = None,
) -> tuple[str, str]:
    system = (
        "Choose only from existing projects. You may omit, reorder, and tailor descriptions and highlights. "
        "Select a maximum of 4 (ideally 2 to 4) projects that are most relevant to the target job description. "
        "For each project, write at most 3 relevant highlights and list at most 6 technologies/keywords used. "
        "CRITICAL: You MUST keep the 'name' of each project EXACTLY as provided in the master resume. "
        "Do not alter project names even slightly (e.g. spelling, casing, symbols), or they will be dropped during merge. "
        "For each project, retain or tailor its 'keywords' list (technologies used) matching the StackOverflow layout theme. "
        "Return structured JSON with this key: projects (a list of tailored project objects with name, description, highlights, and keywords)."
    )
    system = _apply_style(system, style)
    user = (
        f"Job description:\n{job_description}\n\n"
        f"Strategy:\n{_json(strategy)}\n\n"
        f"Projects section:\n{_json(resume.get('projects', []))}"
    )
    return system, user


def certificates_prompt(resume: dict[str, Any], job_description: str, strategy: dict[str, Any]) -> tuple[str, str]:
    system = (
        "Select only certificates that have a strong, direct mapping to the target role's priority keywords. "
        "Return a maximum of 18, but fewer if they do not meet a strict relevance threshold. "
        "Do not rewrite or invent certificate names; use existing certificate names verbatim. "
        "Return structured JSON with this key: certificates (a list of certificate names)."
    )
    user = (
        f"Job description:\n{job_description}\n\n"
        f"Strategy:\n{_json(strategy)}\n\n"
        f"Certificates:\n{_json(resume.get('certificates', []))}"
    )
    return system, user


def optional_sections_prompt(resume: dict[str, Any], job_description: str, strategy: dict[str, Any]) -> tuple[str, str]:
    system = (
        "Tailor optional sections only if they already exist. "
        "For interests, keep interest names grounded in the source and tailor keywords conservatively."
    )
    user = (
        f"Job description:\n{job_description}\n\n"
        f"Strategy:\n{_json(strategy)}\n\n"
        f"Master resume:\n{_json(resume)}\n\n"
        f"Optional sections:\n{_json({'interests': resume.get('interests', [])})}"
    )
    return system, user


def basics_prompt(
    resume: dict[str, Any],
    job_description: str,
    strategy: dict[str, Any],
    style: str | None = None,
) -> tuple[str, str]:
    system = (
        "Tailor only the professional label (headline/title) and the main summary paragraph "
        "of the basics section. "
        "Write a single, concise professional summary paragraph aiming for under 100 words (3-4 sentences). "
        "CRITICAL: The tailored summary MUST explicitly retain or include the mention of "
        "your education if it can be high signalling. For example, if you have an MBA from IIM Trichy, "
        "you can mention it. "
        "Do not invent unsupported responsibilities or achievements. "
        "Do not modify other basics details like name, email, phone, location, profiles, or url. "
        "Return structured JSON with keys: label and summary."
    )
    system = _apply_style(system, style)
    user = (
        f"Job description:\n{job_description}\n\n"
        f"Strategy:\n{_json(strategy)}\n\n"
        f"Master resume for context:\n{_json(resume)}\n\n"
        f"Target basics section:\n{_json(resume.get('basics', {}))}"
    )
    return system, user
