import pytest

from app.workers.connectors.base import RawJobPosting
from app.workers.normalizer import NormalizedJob, _detect_level, normalize


def make_raw(**kwargs) -> RawJobPosting:
    defaults = dict(
        connector_name="greenhouse",
        source_target_id="t1",
        external_id="j1",
        title="Software Engineer",
        company="Acme",
        url="https://example.com/job/1",
        location="Remote",
        raw_description=None,
        employment_type=None,
        metadata=None,
    )
    defaults.update(kwargs)
    return RawJobPosting(**defaults)


# ---------------------------------------------------------------------------
# _detect_level
# ---------------------------------------------------------------------------

def test_detect_level_senior_in_title():
    assert _detect_level("Senior Software Engineer", None) == "senior"

def test_detect_level_junior_in_title():
    assert _detect_level("Junior Developer", None) == "junior"

def test_detect_level_new_grad():
    assert _detect_level("New Grad Software Engineer", None) == "new_grad"

def test_detect_level_staff():
    assert _detect_level("Staff Engineer", None) == "staff"

def test_detect_level_principal():
    assert _detect_level("Principal Engineer", None) == "principal"

def test_detect_level_none_for_generic():
    assert _detect_level("Accountant", None) is None

def test_detect_level_from_description():
    assert _detect_level("Engineer", "This is a senior role") == "senior"

def test_detect_level_title_wins_over_description():
    # Title has "junior", description has "senior" — first match in title wins
    result = _detect_level("Junior Engineer", "This is a senior level position")
    assert result == "junior"


# ---------------------------------------------------------------------------
# normalize
# ---------------------------------------------------------------------------

def test_normalize_basic_fields():
    raw = make_raw(title="  Software Engineer  ", company="Acme", url="https://example.com/1")
    results = normalize([raw])
    assert len(results) == 1
    job = results[0]
    assert job.title == "Software Engineer"  # stripped
    assert job.company == "Acme"
    assert job.url == "https://example.com/1"
    assert job.connector_name == "greenhouse"
    assert job.source_target_id == "t1"
    assert job.external_id == "j1"

def test_normalize_drops_missing_title():
    raw = make_raw(title="", url="https://example.com/1")
    assert normalize([raw]) == []

def test_normalize_drops_none_title():
    raw = make_raw(title=None, url="https://example.com/1")
    assert normalize([raw]) == []

def test_normalize_drops_missing_url():
    raw = make_raw(title="Engineer", url="")
    assert normalize([raw]) == []

def test_normalize_drops_none_url():
    raw = make_raw(title="Engineer", url=None)
    assert normalize([raw]) == []

def test_normalize_tags_is_list():
    raw = make_raw(raw_description=None)
    job = normalize([raw])[0]
    assert isinstance(job.tags, list)

def test_normalize_detects_level():
    raw = make_raw(title="Senior Software Engineer")
    job = normalize([raw])[0]
    assert job.normalized_level == "senior"

def test_normalize_level_none_for_generic():
    raw = make_raw(title="Accountant")
    job = normalize([raw])[0]
    assert job.normalized_level is None

def test_normalize_metadata_mapped():
    raw = make_raw(metadata={"foo": "bar"})
    job = normalize([raw])[0]
    assert job.metadata_json == {"foo": "bar"}

def test_normalize_multiple_mixed():
    raws = [
        make_raw(external_id="1", title="Senior Engineer"),
        make_raw(external_id="2", title=""),          # dropped
        make_raw(external_id="3", title="Staff Engineer"),
    ]
    results = normalize(raws)
    assert len(results) == 2
    assert {r.external_id for r in results} == {"1", "3"}

def test_normalize_returns_normalized_job_type():
    raw = make_raw()
    job = normalize([raw])[0]
    assert isinstance(job, NormalizedJob)
