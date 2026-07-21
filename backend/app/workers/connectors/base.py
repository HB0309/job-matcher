from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class JobQuery:
    preferred_titles: list[str]
    preferred_level: list[str] | None = None
    location_hint: str | None = None
    max_results_per_target: int | None = None


@dataclass
class SourceTargetDTO:
    id: str
    connector_name: str
    company_name: str
    base_url: str
    company_key: str | None = None
    target_slug: str | None = None
    config: dict = field(default_factory=dict)


@dataclass
class RawJobPosting:
    connector_name: str
    source_target_id: str
    external_id: str
    title: str
    company: str
    url: str
    location: str | None = None
    posted_at: datetime | None = None
    raw_description: str | None = None
    employment_type: str | None = None
    metadata: dict | None = None


class BaseConnector(Protocol):
    name: str

    def fetch_jobs(self, target: SourceTargetDTO, query: JobQuery) -> list[RawJobPosting]:
        ...
