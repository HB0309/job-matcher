from dataclasses import dataclass, field
from datetime import datetime

from app.workers.connectors.base import RawJobPosting

# (level_name, substrings to match in title/description)
_LEVEL_PATTERNS: list[tuple[str, list[str]]] = [
    ("new_grad",  ["new grad", "new graduate", "university hire", "campus recruit", "fresh grad"]),
    ("entry",     ["entry level", "entry-level", "associate engineer", "associate software"]),
    ("junior",    ["junior ", "jr. ", "jr ", "jnr "]),
    ("mid",       ["mid level", "mid-level", " ii ", "intermediate"]),
    ("senior",    ["senior ", "sr. ", "sr ", "snr "]),
    ("staff",     ["staff engineer", "staff software", "staff security"]),
    ("principal", ["principal ", "lead engineer", "lead software", "lead security"]),
]


@dataclass
class NormalizedJob:
    connector_name: str
    source_target_id: str
    external_id: str
    title: str
    company: str
    url: str
    location: str | None = None
    posted_at: datetime | None = None
    raw_description: str | None = None
    normalized_level: str | None = None
    employment_type: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata_json: dict | None = None


def _detect_level(title: str, description: str | None) -> str | None:
    text = (title + " " + (description or "")[:2000]).lower()
    for level, patterns in _LEVEL_PATTERNS:
        if any(p in text for p in patterns):
            return level
    return None


def _extract_tags(description: str | None) -> list[str]:
    if not description:
        return []
    from app.workers.resume_parser import extract_skills
    return extract_skills(description)


def normalize(raw_jobs: list[RawJobPosting]) -> list[NormalizedJob]:
    results: list[NormalizedJob] = []
    for raw in raw_jobs:
        if not raw.title or not raw.url:
            continue
        results.append(NormalizedJob(
            connector_name=raw.connector_name,
            source_target_id=raw.source_target_id,
            external_id=raw.external_id,
            title=raw.title.strip(),
            company=raw.company,
            url=raw.url,
            location=raw.location,
            posted_at=raw.posted_at,
            raw_description=raw.raw_description,
            normalized_level=_detect_level(raw.title, raw.raw_description),
            employment_type=raw.employment_type,
            tags=list(dict.fromkeys(
                (raw.metadata.get("tags") or []) + _extract_tags(raw.raw_description)
            )),
            metadata_json=raw.metadata,
        ))
    return results
