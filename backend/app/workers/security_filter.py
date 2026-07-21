from app.workers.normalizer import NormalizedJob

_DISQUALIFYING_PHRASES = [
    # Security clearance
    "security clearance",
    "clearance required",
    "active clearance",
    "ts/sci",
    "top secret",
    "secret clearance",
    "dod clearance",
    "department of defense clearance",
    # US citizenship
    "us citizenship required",
    "u.s. citizenship required",
    "citizenship required",
    "must be a us citizen",
    "must be a u.s. citizen",
    "us citizens only",
    "requires us citizenship",
]


def filter_disqualifying_jobs(jobs: list[NormalizedJob]) -> list[NormalizedJob]:
    kept = []
    dropped = 0
    for job in jobs:
        haystack = " ".join(filter(None, [job.title, job.raw_description])).lower()
        if any(phrase in haystack for phrase in _DISQUALIFYING_PHRASES):
            dropped += 1
        else:
            kept.append(job)
    if dropped:
        print(f"[security_filter] dropped {dropped} jobs requiring clearance/citizenship")
    return kept
