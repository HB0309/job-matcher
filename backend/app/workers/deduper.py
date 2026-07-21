import re

from sqlalchemy.orm import Session

from app.models import JobPosting
from app.workers.normalizer import NormalizedJob

# ATS connectors preferred over aggregators when a cross-source duplicate is found
_ATS_PRIORITY = ["greenhouse", "lever", "ashby", "smartrecruiters", "workday"]

_RE_COMPANY_SUFFIX = re.compile(r"\b(inc|llc|ltd|corp|co|plc|gmbh|ag|sa|bv)\b\.?", re.I)
_RE_JOB_SUFFIX = re.compile(
    r"\b(remote|hybrid|on.?site|full.?time|part.?time|contract|temp|intern)\b", re.I
)
_RE_NONWORD = re.compile(r"[^\w\s]")
_RE_WS = re.compile(r"\s+")


def _normalize(text: str) -> str:
    t = text.lower()
    t = _RE_NONWORD.sub(" ", t)
    t = _RE_WS.sub(" ", t).strip()
    return t


def _fingerprint(company: str, title: str) -> str:
    c = _normalize(_RE_COMPANY_SUFFIX.sub("", company))
    t = _normalize(_RE_JOB_SUFFIX.sub("", title))
    return f"{c}|{t}"


def _connector_rank(name: str) -> int:
    try:
        return _ATS_PRIORITY.index(name)
    except ValueError:
        return len(_ATS_PRIORITY)  # aggregators rank last


def dedupe(
    jobs: list[NormalizedJob],
    db: Session,
    connector_map: dict[str, int],
) -> list[NormalizedJob]:
    """Return only jobs not already present in job_postings.

    Three passes:
    1. Within-batch fingerprint collapse — prefer ATS connector when title+company match.
    2. Exact (connector_id, source_target_id, external_id) match against DB.
    3. Fuzzy fingerprint match against existing DB rows for the same companies.
    """
    if not jobs:
        return []

    # Pass 1: collapse within-batch cross-source duplicates
    seen_fp: dict[str, NormalizedJob] = {}
    for job in jobs:
        fp = _fingerprint(job.company, job.title)
        prev = seen_fp.get(fp)
        if prev is None or _connector_rank(job.connector_name) < _connector_rank(prev.connector_name):
            seen_fp[fp] = job
    batch = list(seen_fp.values())

    # Pass 2: exact match against DB rows for the same source targets
    target_ids = list({j.source_target_id for j in batch})
    exact_rows = (
        db.query(JobPosting.connector_id, JobPosting.source_target_id, JobPosting.external_id)
        .filter(JobPosting.source_target_id.in_(target_ids))
        .all()
    )
    exact_keys = {(r.connector_id, r.source_target_id, r.external_id) for r in exact_rows}

    # Pass 3: fingerprint match against recent DB rows for the same companies
    companies = list({j.company for j in batch})
    fp_rows = (
        db.query(JobPosting.company, JobPosting.title)
        .filter(JobPosting.company.in_(companies))
        .all()
    )
    db_fps = {_fingerprint(r.company, r.title) for r in fp_rows}

    result: list[NormalizedJob] = []
    for job in batch:
        cid = connector_map.get(job.connector_name)
        if cid is None:
            continue
        if (cid, job.source_target_id, job.external_id) in exact_keys:
            continue
        if _fingerprint(job.company, job.title) in db_fps:
            continue
        result.append(job)
    return result
