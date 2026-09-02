"""Pipeline stage metrics for a fetch-and-match run.

Records the count of jobs entering/leaving each stage plus a wall-clock timing,
then computes the drop rates and throughput that make good, defensible resume
numbers. Nothing here changes pipeline behaviour — it only observes.

Usage (in orchestrator.run_fetch_and_match):

    m = StageMetrics()
    ...
    m.stage("fetched", len(all_raw))
    with m.timed("normalize"):
        normalized = normalize(all_raw)
    m.stage("normalized", len(normalized))
    ...
    m.log_summary()          # prints the funnel + %s to the logger
    summary = m.as_dict()    # or grab the structured numbers
"""

from __future__ import annotations

import json
import logging
import sys
import time
from contextlib import contextmanager

log = logging.getLogger("job_matcher.run_metrics")

# Guarantee the funnel is emitted regardless of the host's logging config.
# (uvicorn's --log-level configures its own loggers; a bare getLogger otherwise
# propagates to a root that defaults to WARNING and silently drops our INFO.)
if not log.handlers:
    log.setLevel(logging.INFO)
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(_handler)
    log.propagate = False


class StageMetrics:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._order: list[str] = []
        self._timings: dict[str, float] = {}
        self._notes: dict[str, float | int | str] = {}
        self._t0 = time.perf_counter()

    def stage(self, name: str, count: int) -> None:
        """Record the number of jobs present at a named stage."""
        if name not in self._counts:
            self._order.append(name)
        self._counts[name] = count

    def note(self, key: str, value: float | int | str) -> None:
        """Record a scalar side-metric (e.g. score_max, matches_ge_0.5)."""
        self._notes[key] = value

    @contextmanager
    def timed(self, name: str):
        """Time a block of work (seconds), recorded under `name`."""
        start = time.perf_counter()
        try:
            yield
        finally:
            self._timings[name] = time.perf_counter() - start

    def _pct_drop(self, before: int, after: int) -> float:
        if before <= 0:
            return 0.0
        return round((before - after) / before * 100, 1)

    def as_dict(self) -> dict:
        """Structured summary: raw counts, per-stage drop %, and end-to-end %."""
        counts = self._counts
        fetched = counts.get("fetched", 0)
        # terminal stage of the funnel (strong_matches when present)
        terminal = counts.get(self._order[-1], 0) if self._order else 0

        drops: dict[str, float] = {}
        for prev, cur in zip(self._order, self._order[1:]):
            drops[f"{prev}->{cur}"] = self._pct_drop(counts[prev], counts[cur])

        total_seconds = round(time.perf_counter() - self._t0, 2)
        jobs_per_sec = round(fetched / total_seconds, 1) if total_seconds > 0 else 0.0

        return {
            "counts": {k: counts[k] for k in self._order},
            "stage_drop_pct": drops,
            "noise_cut_pct": self._pct_drop(fetched, terminal),  # headline: fetched -> strong_matches
            "notes": dict(self._notes),
            "timings_seconds": {k: round(v, 3) for k, v in self._timings.items()},
            "total_seconds": total_seconds,
            "jobs_per_second": jobs_per_sec,
        }

    def log_summary(self) -> dict:
        """Emit a human-readable funnel plus the JSON blob, and return the dict."""
        d = self.as_dict()
        lines = ["", "-- fetch/match funnel " + "-" * 30]
        for name in self._order:
            lines.append(f"  {name:<14} {self._counts[name]:>6}")
        lines.append("  " + "-" * 22)
        for edge, pct in d["stage_drop_pct"].items():
            lines.append(f"  drop {edge:<22} {pct:>5}%")
        terminal_name = self._order[-1] if self._order else "matched"
        lines.append(f"  NOISE CUT fetched->{terminal_name}  {d['noise_cut_pct']:>5}%")
        for key, val in d["notes"].items():
            lines.append(f"  note {key:<22} {val}")
        lines.append(f"  throughput  {d['jobs_per_second']} jobs/s over {d['total_seconds']}s")
        for stage, secs in d["timings_seconds"].items():
            lines.append(f"  time {stage:<20} {secs:>7}s")
        lines.append("-" * 52)
        log.info("\n".join(lines))
        log.info("run_metrics_json %s", json.dumps(d))
        return d
