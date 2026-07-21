"""Unit tests for intent_engine._classify — pure function, no DB needed."""
from unittest.mock import MagicMock

import pytest

from app.workers.intent_engine import _classify


def _saved(status: str = "saved"):
    obj = MagicMock()
    obj.status = status
    return obj


def _draft(status: str):
    obj = MagicMock()
    obj.status = status
    return obj


class TestClassify:
    def test_no_saved_job_returns_prepare_draft(self):
        intent, reasons = _classify(None, None)
        assert intent == "prepare_draft"

    def test_applied_returns_manual_only(self):
        intent, _ = _classify(_saved("applied"), None)
        assert intent == "manual_only"

    def test_applied_ignores_draft(self):
        intent, _ = _classify(_saved("applied"), _draft("approved"))
        assert intent == "manual_only"

    def test_saved_no_draft_returns_prepare_draft(self):
        intent, reasons = _classify(_saved("saved"), None)
        assert intent == "prepare_draft"
        assert any("no application draft" in r for r in reasons)

    def test_review_pending_returns_review_draft(self):
        intent, _ = _classify(_saved(), _draft("review_pending"))
        assert intent == "review_draft"

    def test_stale_returns_refresh_draft(self):
        intent, reasons = _classify(_saved(), _draft("stale"))
        assert intent == "refresh_draft"
        assert any("stale" in r for r in reasons)

    def test_approved_returns_start_apply(self):
        intent, _ = _classify(_saved(), _draft("approved"))
        assert intent == "start_apply"

    def test_discarded_returns_prepare_draft(self):
        intent, reasons = _classify(_saved(), _draft("discarded"))
        assert intent == "prepare_draft"
        assert any("discarded" in r for r in reasons)

    def test_unknown_draft_status_returns_prepare_draft(self):
        intent, _ = _classify(_saved(), _draft("draft"))
        assert intent == "prepare_draft"
