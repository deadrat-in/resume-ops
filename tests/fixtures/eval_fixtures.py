"""
Benchmark datasets for resume-ops LLM evaluation tests.
Includes realistic Master Resumes and target Job Descriptions.
"""
from __future__ import annotations

SAMPLE_MASTER_RESUME_BACKEND = {
    "basics": {
        "name": "Jane Doe",
        "label": "Senior Backend Engineer",
        "email": "jane.doe@example.com",
        "phone": "+1-555-0199",
        "summary": "Distributed systems engineer with 8 years of experience building Python and Go services.",
        "location": {"city": "San Francisco", "region": "CA", "countryCode": "US"}
    },
    "work": [
        {
            "name": "Tech Corp",
            "position": "Senior Software Engineer",
            "startDate": "2021-03",
            "endDate": "Present",
            "summary": "Lead backend developer for core payments and infrastructure services.",
            "highlights": [
                "Architected event-driven microservices using Python FastAPI, Kafka, and PostgreSQL processing 10M daily transactions.",
                "Reduced P99 API latency from 450ms to 85ms by optimizing SQL queries and Redis caching strategy.",
                "Mentored a team of 5 engineers and established CI/CD automation using Podman and GitHub Actions."
            ]
        },
        {
            "name": "DataScale Inc",
            "position": "Software Engineer",
            "startDate": "2018-06",
            "endDate": "2021-02",
            "summary": "Backend developer focusing on telemetry processing pipelines.",
            "highlights": [
                "Built streaming data ingestion pipelines handling 50k events/sec using Python, AsyncIO, and ClickHouse.",
                "Designed RESTful APIs and JSON schemas for customer analytics platform."
            ]
        }
    ],
    "education": [
        {
            "institution": "University of California, Berkeley",
            "area": "Computer Science",
            "studyType": "Bachelor of Science",
            "startDate": "2014-08",
            "endDate": "2018-05",
            "score": "3.8",
            "courses": ["CS162 Operating Systems", "CS170 Algorithms", "CS186 Database Systems"]
        }
    ],
    "skills": [
        {
            "name": "Languages & Frameworks",
            "keywords": ["Python", "FastAPI", "Go", "SQL", "AsyncIO", "Pydantic"]
        },
        {
            "name": "Infrastructure & Databases",
            "keywords": ["PostgreSQL", "Redis", "Kafka", "Docker", "Podman", "Kubernetes", "Linux"]
        }
    ],
    "projects": [
        {
            "name": "AsyncTaskQueue",
            "description": "Open-source Python task queue powered by Redis streams.",
            "highlights": ["Gained 1.2k GitHub stars", "Achieved 98% unit test coverage"],
            "keywords": ["Python", "Redis", "AsyncIO"]
        }
    ]
}

SAMPLE_JOB_DESCRIPTION_SENIOR_DEVOPS = """
We are looking for a Senior DevOps / Infrastructure Engineer to join our cloud platform team.
Key Responsibilities:
- Build and maintain containerized microservices and automated CI/CD pipelines.
- Optimize database performance, caching, and stream processing with PostgreSQL, Redis, and Kafka.
- Implement robust monitoring, tracing, and rate-limiting for backend APIs built in Python/Go.
- Requirements: 5+ years experience with Linux, Docker/Podman, Python, AsyncIO, and distributed systems.
"""
